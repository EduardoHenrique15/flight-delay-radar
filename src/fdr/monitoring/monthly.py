"""Monitoramento mensal do modelo, com regra de retreino e campeão contra desafiante (Fase 4).

Para cada mês novo publicado pela ANAC:
1. pontua o mês com o modelo campeão, que não viu esse mês;
2. mede PR-AUC, ROC-AUC, Brier, ECE e taxa prevista contra real, e as mesmas métricas do baseline;
3. calcula o PSI de cada variável contra o perfil do treino do campeão;
4. aplica a regra de retreino. Ela dispara se:
   - o modelo perder do baseline no mês (ganho de PR-AUC abaixo de zero). O ganho sobre o
     baseline não sobe nem desce com a taxa de atraso do mês, ao contrário da PR-AUC sozinha
     (decisão do Eduardo em 16/10/2026);
   - o ECE passar de 5 p.p.;
   - uma variável importante (as 5 de maior SHAP) tiver PSI de 0,25 ou mais;
   - já tiverem passado 6 meses desde o último retreino (ou desde o início do campeão);
5. se a regra disparar, treina um desafiante com os dados até o mês M - 2 (o que estaria
   publicado) e com as escolhas do ADR 005. Ele só vira campeão se ganhar no mês novo com
   folga: o intervalo de 95% do ganho de PR-AUC (bootstrap pareado por dia) fica acima de zero;
6. grava tudo em monitoring/history.json.

Histórico retroativo (`simular`): para o painel nascer com meses reais, um campeão "da época" é
treinado até out/2025 e o processo acima roda mês a mês de dez/2025 a ago/2026, sem olhar o
futuro. Os meses simulados ficam marcados como "simulacao"; os meses de produção, publicados
depois do modelo final da Fase 3, ficam em "producao".

Uso: python -m fdr.monitoring.monthly --historico   # reconstrói a simulação
     python -m fdr.monitoring.monthly               # processa os meses novos publicados
"""

import argparse
import json
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

from fdr.config import ARQUIVO_METRICAS, INICIO_TREINO, PASTA_MODELOS, RAIZ, WAREHOUSE
from fdr.features.build import ALVO
from fdr.model import baseline, final, train
from fdr.model.evaluate import intervalos_bootstrap_pareado, metricas
from fdr.model.registry import (
    ARQUIVO_PERFIL,
    ModeloAtraso,
    perfil_de_referencia,
    salvar_perfil,
)
from fdr.monitoring import drift

ARQUIVO_HISTORICO = RAIZ / "monitoring" / "history.json"
ARQUIVO_EXPLICACAO = PASTA_MODELOS / "explicacao_global.json"

ECE_MAXIMO = 0.05
MESES_MAXIMOS_SEM_RETREINO = 6
VARIAVEIS_IMPORTANTES = 5
FIM_TREINO_CAMPEAO_SIMULADO = date(2025, 10, 1)
INICIO_SIMULACAO = date(2025, 12, 1)
FIM_SIMULACAO = date(2026, 8, 1)


@dataclass
class Campeao:
    modelo: ModeloAtraso
    perfil: dict
    meses_em_uso: int = 0


def mes_menos(mes: date, meses: int) -> date:
    indice = mes.year * 12 + mes.month - 1 - meses
    return date(indice // 12, indice % 12 + 1, 1)


def variaveis_importantes(caminho: Path = ARQUIVO_EXPLICACAO) -> list[str]:
    """As de maior SHAP médio no teste (models/explicacao_global.json)."""
    if not caminho.exists():
        return []
    explicacao = json.loads(caminho.read_text(encoding="utf-8"))
    return [v["variavel"] for v in explicacao["por_variavel"][:VARIAVEIS_IMPORTANTES]]


def avaliar_mes(campeao: Campeao, dados_mes: pd.DataFrame, janela: int) -> dict:
    y = dados_mes[ALVO].to_numpy()
    p = campeao.modelo.prever(dados_mes)
    p_base = baseline.prever(dados_mes, janela)[0]
    modelo = metricas(y, p)
    referencia = metricas(y, p_base)
    psi = drift.psi_todas(campeao.perfil, dados_mes, campeao.modelo.metadados["voos_treino"])
    return {
        "voos": modelo.pop("voos"),
        "modelo": {k: round(v, 6) for k, v in modelo.items()},
        "baseline": {k: round(v, 6) for k, v in referencia.items() if k != "voos"},
        "ganho_pr_auc": round(modelo["pr_auc"] - referencia["pr_auc"], 6),
        "psi": psi,
        "psi_alertas": {v: drift.nivel(x) for v, x in psi.items() if x >= drift.LIMITE_ATENCAO},
    }


def regra_retreino(avaliacao: dict, meses_em_uso: int, importantes: list[str]) -> list[str]:
    """Os motivos para retreinar; lista vazia = não retreina."""
    motivos = []
    if avaliacao["ganho_pr_auc"] < 0:
        motivos.append(f"perdeu do baseline (ganho de PR-AUC {avaliacao['ganho_pr_auc']:+.4f})")
    if avaliacao["modelo"]["ece"] > ECE_MAXIMO:
        motivos.append(f"ECE de {avaliacao['modelo']['ece']:.1%} (máximo {ECE_MAXIMO:.0%})")
    for variavel in importantes:
        if avaliacao["psi"].get(variavel, 0.0) >= drift.LIMITE_ALERTA:
            motivos.append(f"PSI de {avaliacao['psi'][variavel]:.2f} em {variavel}")
    if meses_em_uso >= MESES_MAXIMOS_SEM_RETREINO:
        motivos.append(f"{meses_em_uso} meses desde o último retreino")
    return motivos


def comparar(y: np.ndarray, p_campeao, p_desafiante, dias) -> dict:
    """O desafiante só vence se o ganho de PR-AUC tiver intervalo de 95% acima de zero."""
    ganho = metricas(y, p_desafiante)["pr_auc"] - metricas(y, p_campeao)["pr_auc"]
    intervalo = intervalos_bootstrap_pareado(y, p_desafiante, p_campeao, dias)["pr_auc"]
    return {
        "ganho_pr_auc": round(ganho, 6),
        "ganho_pr_auc_intervalo_95": [round(v, 6) for v in intervalo],
        "promovido": bool(intervalo[0] > 0),
    }


def processar_mes(
    dados: pd.DataFrame,
    mes: date,
    campeao: Campeao,
    decisoes: dict,
    importantes: list[str],
    tipo: str,
) -> tuple[dict, Campeao]:
    """Avalia um mês, decide o retreino e devolve a entrada do histórico e o campeão seguinte."""
    dados_mes = train.no_periodo(dados, mes, mes)
    avaliacao = avaliar_mes(campeao, dados_mes, decisoes["janela_baseline"])
    motivos = regra_retreino(avaliacao, campeao.meses_em_uso, importantes)
    entrada = {
        "mes": mes.isoformat(),
        "tipo": tipo,
        "campeao_treino": campeao.modelo.metadados["treino"],
        "meses_em_uso": campeao.meses_em_uso,
        **avaliacao,
        "retreino": {"disparou": bool(motivos), "motivos": motivos},
    }
    proximo = Campeao(campeao.modelo, campeao.perfil, campeao.meses_em_uso + 1)
    if motivos:
        inicio, fim = date(*INICIO_TREINO, 1), mes_menos(mes, 2)
        desafiante = final.treinar_periodo(dados, inicio, fim, decisoes)
        resultado = comparar(
            dados_mes[ALVO].to_numpy(),
            campeao.modelo.prever(dados_mes),
            desafiante.prever(dados_mes),
            dados_mes["data_prevista"].to_numpy(),
        )
        entrada["retreino"]["desafiante_treino"] = [inicio.isoformat(), fim.isoformat()]
        entrada["retreino"].update(resultado)
        # Houve retreino: o contador volta a zero, com ou sem promoção.
        proximo = Campeao(campeao.modelo, campeao.perfil, 0)
        if resultado["promovido"]:
            perfil = perfil_de_referencia(train.no_periodo(dados, inicio, fim))
            proximo = Campeao(desafiante, perfil, 0)
    entrada["meses_em_uso_seguinte"] = proximo.meses_em_uso
    return entrada, proximo


def meses_entre(inicio: date, fim: date) -> list[date]:
    meses, atual = [], inicio
    while atual <= fim:
        meses.append(atual)
        atual = mes_menos(atual, -1)
    return meses


def simular(
    dados: pd.DataFrame,
    decisoes: dict,
    importantes: list[str],
    fim_treino: date = FIM_TREINO_CAMPEAO_SIMULADO,
    inicio: date = INICIO_SIMULACAO,
    fim: date = FIM_SIMULACAO,
    avisar=print,
) -> dict:
    """Histórico retroativo: o campeão "da época" é treinado até `fim_treino` e cada mês de
    `inicio` a `fim` é processado em ordem, só com o que estaria publicado."""
    if mes_menos(inicio, 2) < fim_treino:
        raise ValueError("O primeiro mês simulado precisa vir 2 meses depois do fim do treino.")
    treino = (date(*INICIO_TREINO, 1), fim_treino)
    campeao = Campeao(
        final.treinar_periodo(dados, *treino, decisoes),
        perfil_de_referencia(train.no_periodo(dados, *treino)),
    )
    meses = []
    for mes in meses_entre(inicio, fim):
        entrada, campeao = processar_mes(dados, mes, campeao, decisoes, importantes, "simulacao")
        meses.append(entrada)
        retreino = entrada["retreino"]
        situacao = "sem retreino"
        if retreino["disparou"]:
            situacao = "desafiante promovido" if retreino["promovido"] else "campeão mantido"
        avisar(
            f"    {mes:%m/%Y}: PR-AUC {entrada['modelo']['pr_auc']:.4f}, ganho sobre o baseline "
            f"{entrada['ganho_pr_auc']:+.4f}, ECE {entrada['modelo']['ece']:.1%} -> {situacao}"
        )
        for motivo in retreino["motivos"]:
            avisar(f"        motivo: {motivo}")
    return {"campeao_inicial_treino": [d.isoformat() for d in treino], "meses": meses}


def regras() -> dict:
    return {
        "ganho_pr_auc_minimo": 0.0,
        "ece_maximo": ECE_MAXIMO,
        "psi_alerta": drift.LIMITE_ALERTA,
        "psi_atencao": drift.LIMITE_ATENCAO,
        "meses_maximos_sem_retreino": MESES_MAXIMOS_SEM_RETREINO,
        "promocao": "intervalo de 95% do ganho de PR-AUC do desafiante acima de zero",
    }


def ler_historico(caminho: Path = ARQUIVO_HISTORICO) -> dict:
    if caminho.exists():
        return json.loads(caminho.read_text(encoding="utf-8"))
    return {"simulacao": None, "producao": {"meses": []}}


def gravar_historico(historico: dict, caminho: Path = ARQUIVO_HISTORICO) -> None:
    historico["gerado_em"] = datetime.now().isoformat(timespec="seconds")
    historico["regras"] = regras()
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(json.dumps(historico, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _carregar() -> tuple[pd.DataFrame, list[date]]:
    with duckdb.connect(str(WAREHOUSE), read_only=True) as con:
        return train.carregar(con), train.meses_disponiveis(con)


def main() -> None:
    parser = argparse.ArgumentParser(description="Monitoramento mensal do modelo.")
    parser.add_argument("--historico", action="store_true", help="reconstrói a simulação")
    args = parser.parse_args()
    executar(historico_retroativo=args.historico)


def executar(historico_retroativo: bool = False) -> None:
    decisoes = final.ler_decisoes(json.loads(ARQUIVO_METRICAS.read_text(encoding="utf-8")))
    importantes = variaveis_importantes()
    historico = ler_historico()
    historico["variaveis_importantes"] = importantes
    dados, meses = _carregar()

    if historico_retroativo:
        print(f"Histórico retroativo: campeão treinado até {FIM_TREINO_CAMPEAO_SIMULADO:%m/%Y}.")
        print(f"Meses simulados: {INICIO_SIMULACAO:%m/%Y} a {FIM_SIMULACAO:%m/%Y}.")
        historico["simulacao"] = simular(dados, decisoes, importantes)
        gravar_historico(historico)
        print(f"Gravado: {ARQUIVO_HISTORICO.relative_to(RAIZ)}.")
        return

    modelo = ModeloAtraso.carregar()
    perfil = json.loads((PASTA_MODELOS / ARQUIVO_PERFIL).read_text(encoding="utf-8"))
    producao = historico["producao"]["meses"]
    ultimo = date.fromisoformat(producao[-1]["mes"] if producao else modelo.metadados["teste"][1])
    em_uso = producao[-1]["meses_em_uso_seguinte"] if producao else 0
    campeao = Campeao(modelo, perfil, em_uso)
    novos = [m for m in meses if m > ultimo]
    if not novos:
        print(f"Nenhum mês novo depois de {ultimo:%m/%Y}: nada a monitorar.")
        return
    for mes in novos:
        entrada, campeao = processar_mes(dados, mes, campeao, decisoes, importantes, "producao")
        producao.append(entrada)
        ganho = entrada["ganho_pr_auc"]
        print(f"    {mes:%m/%Y}: PR-AUC {entrada['modelo']['pr_auc']:.4f}, ganho {ganho:+.4f}")
        if entrada["retreino"].get("promovido"):
            campeao.modelo.salvar()
            salvar_perfil(campeao.perfil)
            print("        desafiante promovido: models/ atualizado")
    gravar_historico(historico)
    print(f"Gravado: {ARQUIVO_HISTORICO.relative_to(RAIZ)}.")


if __name__ == "__main__":
    main()
