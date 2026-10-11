"""Baseline: a taxa histórica de atraso, sem aprendizado (PROJETO.md, seção 6.5).

A probabilidade de um voo atrasar é a taxa de atraso da mesma rota no mesmo horário, no histórico
as-of (até o mês de corte). Se a rota x hora tiver menos de MIN_VOOS_HISTORICO voos no histórico,
usa a taxa da companhia; se faltar, a do aeroporto de origem; por fim, a do país.

São testadas duas janelas de histórico (3 e 12 meses). A escolha usa só a validação; o teste é
calculado uma única vez, para a janela escolhida. O resultado vai para models/metrics.json,
na seção "baseline".

Uso: python -m fdr.model.baseline
"""

import json
from datetime import date, datetime

import duckdb
import numpy as np
import pandas as pd

from fdr.config import (
    ARQUIVO_METRICAS,
    INICIO_TREINO,
    MIN_VOOS_HISTORICO,
    WAREHOUSE,
)
from fdr.features.build import ALVO, JANELAS_MESES, TABELA
from fdr.model.evaluate import curva_calibracao, intervalos_bootstrap, metricas
from fdr.model.splits import Divisao, definir_divisao

NIVEIS = ("rota_hora", "cia", "origem", "global")


def prever(
    dados: pd.DataFrame, janela: int, min_voos: int = MIN_VOOS_HISTORICO
) -> tuple[np.ndarray, np.ndarray]:
    """Devolve a probabilidade prevista e o nível usado em cada voo."""
    probabilidade = np.full(len(dados), np.nan)
    nivel = np.full(len(dados), None, dtype=object)
    for nome in NIVEIS:  # do mais específico para o mais geral
        taxa = dados[f"taxa_{nome}_{janela}m"].to_numpy(dtype=float)
        voos = dados[f"voos_{nome}_{janela}m"].to_numpy(dtype=float)
        minimo = 1 if nome == "global" else min_voos
        usar = np.isnan(probabilidade) & ~np.isnan(taxa) & (voos >= minimo)
        probabilidade[usar] = taxa[usar]
        nivel[usar] = nome
    return probabilidade, nivel


def _avaliar_periodo(dados: pd.DataFrame, inicio: date, fim: date, janela: int) -> dict:
    periodo = dados[(dados["mes"] >= pd.Timestamp(inicio)) & (dados["mes"] <= pd.Timestamp(fim))]
    p, _ = prever(periodo, janela)
    return {"periodo": [inicio.isoformat(), fim.isoformat()], **metricas(periodo[ALVO], p)}


def avaliar(dados: pd.DataFrame, divisao: Divisao) -> dict:
    """Compara as janelas na validação, escolhe uma e avalia o teste uma única vez."""
    validacao = {
        f"{janela}m": [
            _avaliar_periodo(dados, *corte.validacao, janela) for corte in divisao.cortes
        ]
        for janela in JANELAS_MESES
    }
    media_pr_auc = {
        nome: float(np.mean([c["pr_auc"] for c in cortes])) for nome, cortes in validacao.items()
    }
    escolhida = max(media_pr_auc, key=media_pr_auc.get)
    janela = int(escolhida.rstrip("m"))

    inicio, fim = divisao.teste
    teste = dados[(dados["mes"] >= pd.Timestamp(inicio)) & (dados["mes"] <= pd.Timestamp(fim))]
    p, nivel = prever(teste, janela)
    y = teste[ALVO].to_numpy()
    niveis, contagens = np.unique(nivel.astype(str), return_counts=True)
    return {
        "descricao": "taxa histórica as-of da rota x hora, com recurso a companhia, origem e país",
        "min_voos_historico": MIN_VOOS_HISTORICO,
        "validacao_cruzada": validacao,
        "pr_auc_medio_validacao": media_pr_auc,
        "janela_escolhida": escolhida,
        "teste": {
            "periodo": [inicio.isoformat(), fim.isoformat()],
            **metricas(y, p),
            "intervalo_95": intervalos_bootstrap(y, p, teste["data_prevista"].to_numpy()),
            "nivel_usado": {
                str(n): round(float(c) / len(y), 4) for n, c in zip(niveis, contagens, strict=True)
            },
            "curva_calibracao": curva_calibracao(y, p),
        },
    }


def carregar(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    # Precisão simples (float) basta para taxas e contagens e corta a memória pela metade.
    historico = [
        f"cast({tipo}_{nivel}_{j}m as float) as {tipo}_{nivel}_{j}m"
        for nivel in NIVEIS
        for j in JANELAS_MESES
        for tipo in ("taxa", "voos")
    ]
    colunas = ["mes", "data_prevista", f"cast({ALVO} as tinyint) as {ALVO}", *historico]
    inicio = date(*INICIO_TREINO, 1)
    consulta = f"select {', '.join(colunas)} from {TABELA} where mes >= ?"
    return con.execute(consulta, [inicio]).df()


def salvar_metricas(secao: str, conteudo: dict, divisao: Divisao) -> None:
    """Atualiza uma seção do models/metrics.json, mantendo as outras."""
    ARQUIVO_METRICAS.parent.mkdir(parents=True, exist_ok=True)
    atual = (
        json.loads(ARQUIVO_METRICAS.read_text(encoding="utf-8"))
        if ARQUIVO_METRICAS.exists()
        else {}
    )
    atual["divisao"] = divisao.para_json()
    atual[secao] = {"gerado_em": datetime.now().isoformat(timespec="seconds"), **conteudo}
    ARQUIVO_METRICAS.write_text(
        json.dumps(atual, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def main() -> None:
    with duckdb.connect(str(WAREHOUSE), read_only=True) as con:
        dados = carregar(con)
    divisao = definir_divisao(sorted(d.date() for d in dados["mes"].unique()))
    resultado = avaliar(dados, divisao)
    salvar_metricas("baseline", resultado, divisao)

    teste = resultado["teste"]
    print(f"Janela escolhida na validação: {resultado['janela_escolhida']}")
    print(f"PR-AUC médio na validação: {resultado['pr_auc_medio_validacao']}")
    print(f"Teste {teste['periodo'][0]} a {teste['periodo'][1]} ({teste['voos']:,} voos):")
    for nome in ("pr_auc", "roc_auc", "brier", "ece"):
        baixo, alto = teste["intervalo_95"][nome]
        print(f"  {nome:<8} {teste[nome]:.4f}  (IC 95%: {baixo:.4f} a {alto:.4f})")
    print(f"  taxa real {teste['taxa_real']:.2%}, prevista {teste['taxa_prevista']:.2%}")
    print(f"Nível usado no teste: {teste['nivel_usado']}")
    print(f"Métricas gravadas em {ARQUIVO_METRICAS}.")


if __name__ == "__main__":
    main()
