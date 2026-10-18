"""Treino final e teste, usado uma única vez (docs/decisoes/005-escolha-do-modelo.md).

As decisões vêm travadas da validação (models/metrics.json, seção "validacao_modelos"): o modelo
escolhido pela regra de 1 erro-padrão, os hiperparâmetros, a calibração e o número de árvores
(a mediana das janelas da validação cruzada). Nada aqui é escolhido olhando o teste.

O que esta etapa faz:
1. Treina o modelo final nos meses de `treino_final` (até 2 meses antes do teste, ADR 003).
2. Avalia no teste: PR-AUC, ROC-AUC, Brier, ECE e curva de calibração, com intervalo de 95% por
   bootstrap de dias; ganho sobre o baseline com bootstrap pareado; lift nos 10% de maior risco.
3. Mede por segmento: companhia, os 10 aeroportos de origem com mais voos, faixa horária e mês.
4. Grava models/model.txt, models/metadata.json, models/reference_profile.json e a seção
   "modelo_final" do models/metrics.json.

Uso: python -m fdr.model.final
"""

import hashlib
import json
from datetime import date, datetime

import duckdb
import lightgbm as lgb
import numpy as np
import pandas as pd

from fdr.config import ARQUIVO_METRICAS, SEMENTE, WAREHOUSE
from fdr.features.build import ALVO
from fdr.model import baseline, train
from fdr.model.evaluate import (
    curva_calibracao,
    intervalos_bootstrap,
    intervalos_bootstrap_pareado,
    lift_no_topo,
    metricas,
)
from fdr.model.registry import (
    ModeloAtraso,
    perfil_de_referencia,
    salvar_perfil,
    versoes_bibliotecas,
)
from fdr.model.splits import Divisao, definir_divisao

VERSAO = "1"
MIN_VOOS_SEGMENTO = 1000
TOP_AEROPORTOS = 10
FAIXAS_HORARIAS = {
    "madrugada (0h-5h)": range(0, 6),
    "manhã (6h-11h)": range(6, 12),
    "tarde (12h-17h)": range(12, 18),
    "noite (18h-23h)": range(18, 24),
}


class DecisoesAusentesError(RuntimeError):
    """Falta a validação: as escolhas do modelo final precisam vir dela."""


def ler_decisoes(metricas_salvas: dict) -> dict:
    """As escolhas travadas na validação. O número de árvores é a mediana das janelas."""
    validacao = metricas_salvas.get("validacao_modelos")
    if not validacao:
        raise DecisoesAusentesError(
            "models/metrics.json não tem a seção validacao_modelos: "
            "rode python -m fdr.pipeline --stage validacao antes."
        )
    escolhido = validacao["escolha"]["escolhido"]
    if escolhido != "lightgbm":
        raise DecisoesAusentesError(
            f"A validação escolheu '{escolhido}'. O treino final só está pronto para o LightGBM."
        )
    calibracao = validacao["calibracao"]["lightgbm"]["escolhida"]
    if calibracao != "crua":
        raise DecisoesAusentesError(
            f"A validação escolheu a calibração '{calibracao}', que o treino final não aplica."
        )
    return {
        "modelo": escolhido,
        "parametros": validacao["lightgbm"]["parametros"],
        "arvores": int(np.median(validacao["lightgbm"]["arvores_por_corte"])),
        "arvores_por_corte": validacao["lightgbm"]["arvores_por_corte"],
        "calibracao": calibracao,
        "janela_baseline": int(validacao["janela_baseline"].rstrip("m")),
    }


def treinar_periodo(
    dados: pd.DataFrame,
    inicio: date,
    fim: date,
    decisoes: dict,
    teste: tuple[date, date] | None = None,
) -> ModeloAtraso:
    """LightGBM nos meses de `inicio` a `fim`, com o número de árvores fixo (sem parada
    antecipada). Usado no treino final e nos retreinos do monitoramento (Fase 4)."""
    meses = dados["mes"].to_numpy()
    linhas = (meses >= np.datetime64(inicio)) & (meses <= np.datetime64(fim))
    base = lgb.Dataset(
        train.matriz(dados, linhas),
        label=dados[ALVO].to_numpy()[linhas],
        feature_name=list(train.VARIAVEIS),
        categorical_feature=[train.VARIAVEIS.index(c) for c in train.CATEGORICAS],
    )
    booster = lgb.train(
        {**train.PARAMETROS_FIXOS, **decisoes["parametros"]},
        base,
        num_boost_round=decisoes["arvores"],
    )
    metadados = {
        "versao": VERSAO,
        "treinado_em": datetime.now().isoformat(timespec="seconds"),
        "modelo": decisoes["modelo"],
        "treino": [inicio.isoformat(), fim.isoformat()],
        "teste": [d.isoformat() for d in teste] if teste else None,
        "voos_treino": int(linhas.sum()),
        "variaveis": list(train.VARIAVEIS),
        "parametros": {**train.PARAMETROS_FIXOS, **decisoes["parametros"]},
        "arvores": decisoes["arvores"],
        "arvores_por_corte_validacao": decisoes["arvores_por_corte"],
        "calibracao": decisoes["calibracao"],
        "categorias": {c: [str(v) for v in dados[c].cat.categories] for c in train.CATEGORICAS},
        "semente": SEMENTE,
        "bibliotecas": versoes_bibliotecas(),
        "hash_dados_treino": hash_dos_dados(dados[linhas]),
    }
    return ModeloAtraso(booster, metadados)


def treinar_final(dados: pd.DataFrame, divisao: Divisao, decisoes: dict) -> ModeloAtraso:
    """O modelo final: treino em `divisao.treino_final`, avaliado depois no teste."""
    return treinar_periodo(dados, *divisao.treino_final, decisoes, teste=divisao.teste)


def hash_dos_dados(dados: pd.DataFrame) -> str:
    """Impressão digital do treino: voos e atrasos por mês e a soma de cada variável numérica.
    Muda se os dados mudarem, sem precisar guardar os dados."""
    resumo = dados.groupby("mes", observed=True)[ALVO].agg(["size", "sum"]).astype(int)
    numericas = [c for c in train.VARIAVEIS if c not in train.CATEGORICAS]
    somas = dados[numericas].astype("float64").sum().round(3)
    texto = resumo.to_csv() + somas.to_csv()
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


def _segmentos(teste: pd.DataFrame, p_modelo: np.ndarray, p_base: np.ndarray) -> dict:
    """Métricas por segmento, só onde há voos suficientes e as duas classes."""
    teste = teste.assign(_modelo=p_modelo, _base=p_base)
    grupos = {
        "companhia": teste["cia"].astype("string"),
        "aeroporto_origem": teste["origem"].astype("string"),
        "faixa_horaria": teste["hora_prevista_local"].map(
            {h: nome for nome, horas in FAIXAS_HORARIAS.items() for h in horas}
        ),
        "mes": teste["mes"].dt.strftime("%Y-%m"),
    }
    maiores_origens = set(grupos["aeroporto_origem"].value_counts().head(TOP_AEROPORTOS).index)
    resultado = {}
    for nome, chave in grupos.items():
        linhas = []
        for valor, parte in teste.groupby(chave, observed=True):
            if nome == "aeroporto_origem" and valor not in maiores_origens:
                continue
            y = parte[ALVO].to_numpy()
            if len(parte) < MIN_VOOS_SEGMENTO or y.min() == y.max():
                continue
            modelo = metricas(y, parte["_modelo"].to_numpy())
            referencia = metricas(y, parte["_base"].to_numpy())
            linhas.append(
                {
                    nome: str(valor),
                    **{k: round(v, 6) if isinstance(v, float) else v for k, v in modelo.items()},
                    "pr_auc_baseline": round(referencia["pr_auc"], 6),
                }
            )
        resultado[nome] = sorted(linhas, key=lambda r: -r["voos"])
    return resultado


def avaliar_teste(modelo: ModeloAtraso, dados: pd.DataFrame, divisao: Divisao, janela: int):
    teste = train.no_periodo(dados, *divisao.teste)
    y = teste[ALVO].to_numpy()
    dias = teste["data_prevista"].to_numpy()
    p_modelo = modelo.prever(teste)
    p_base = baseline.prever(teste, janela)[0]
    resultado = {
        "periodo": [d.isoformat() for d in divisao.teste],
        **metricas(y, p_modelo),
        "intervalo_95": intervalos_bootstrap(y, p_modelo, dias),
        "ganho_sobre_baseline": {
            nome: metricas(y, p_modelo)[nome] - metricas(y, p_base)[nome]
            for nome in ("pr_auc", "roc_auc", "brier", "ece")
        },
        "ganho_sobre_baseline_intervalo_95": intervalos_bootstrap_pareado(
            y, p_modelo, p_base, dias
        ),
        "lift_10pct": lift_no_topo(y, p_modelo),
        "lift_10pct_baseline": lift_no_topo(y, p_base),
        "curva_calibracao": curva_calibracao(y, p_modelo),
        "segmentos": _segmentos(teste, p_modelo, p_base),
    }
    return resultado


def main() -> None:
    metricas_salvas = json.loads(ARQUIVO_METRICAS.read_text(encoding="utf-8"))
    decisoes = ler_decisoes(metricas_salvas)
    with duckdb.connect(str(WAREHOUSE), read_only=True) as con:
        divisao = definir_divisao(train.meses_disponiveis(con))
        dados = train.carregar(con)
    print(f"{len(dados):,} voos carregados.")
    print(f"Decisões da validação: {decisoes['parametros']}, {decisoes['arvores']} árvores.")

    modelo = treinar_final(dados, divisao, decisoes)
    inicio, fim = divisao.treino_final
    print(f"Treino final: {inicio} a {fim} ({modelo.metadados['voos_treino']:,} voos).")
    treino = train.no_periodo(dados, inicio, fim)
    modelo.salvar()
    salvar_perfil(perfil_de_referencia(treino))

    resultado = avaliar_teste(modelo, dados, divisao, decisoes["janela_baseline"])
    baseline.salvar_metricas(
        "modelo_final",
        {"versao": VERSAO, "decisoes": decisoes, "teste": resultado},
        divisao,
    )

    inicio, fim = resultado["periodo"]
    print(f"Teste {inicio} a {fim} ({resultado['voos']:,} voos), usado uma única vez:")
    for nome in ("pr_auc", "roc_auc", "brier", "ece"):
        baixo, alto = resultado["intervalo_95"][nome]
        ganho = resultado["ganho_sobre_baseline"][nome]
        g_baixo, g_alto = resultado["ganho_sobre_baseline_intervalo_95"][nome]
        print(f"  {nome:<8} {resultado[nome]:.4f} (IC 95%: {baixo:.4f} a {alto:.4f})")
        print(
            f"           ganho sobre o baseline {ganho:+.4f} (IC: {g_baixo:+.4f} a {g_alto:+.4f})"
        )
    print(f"  taxa real {resultado['taxa_real']:.2%}, prevista {resultado['taxa_prevista']:.2%}")
    lift, lift_base = resultado["lift_10pct"], resultado["lift_10pct_baseline"]
    print(f"  10% de maior risco: {lift['precisao']:.1%} atrasaram (lift {lift['lift']:.2f})")
    print(f"  baseline nos 10%: {lift_base['precisao']:.1%} (lift {lift_base['lift']:.2f})")
    print("Gravados: models/model.txt, metadata.json, reference_profile.json e metrics.json.")


if __name__ == "__main__":
    main()
