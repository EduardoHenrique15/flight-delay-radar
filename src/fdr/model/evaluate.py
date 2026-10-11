"""Métricas de avaliação (PROJETO.md, seção 6.6): PR-AUC, ROC-AUC, Brier, ECE e calibração,
com intervalo de confiança por bootstrap reamostrando DIAS inteiros (voos do mesmo dia são
correlacionados: chuva, pane, congestionamento afetam muitos voos juntos)."""

import numpy as np
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score

from fdr.config import AMOSTRAS_BOOTSTRAP, SEMENTE

FAIXAS_CALIBRACAO = 10


def ece(y: np.ndarray, p: np.ndarray, faixas: int = FAIXAS_CALIBRACAO) -> float:
    """Erro de calibração esperado: diferença média entre a probabilidade prevista e a taxa real,
    em faixas de mesma largura (0-10%, 10-20%, ...), ponderada pelo número de voos."""
    indices = np.minimum((p * faixas).astype(int), faixas - 1)
    total = 0.0
    for faixa in range(faixas):
        dentro = indices == faixa
        if dentro.any():
            total += dentro.sum() * abs(p[dentro].mean() - y[dentro].mean())
    return float(total / len(y))


def metricas(y: np.ndarray, p: np.ndarray) -> dict:
    y = np.asarray(y, dtype=float)
    p = np.asarray(p, dtype=float)
    return {
        "voos": int(len(y)),
        "pr_auc": float(average_precision_score(y, p)),
        "roc_auc": float(roc_auc_score(y, p)),
        "brier": float(brier_score_loss(y, p)),
        "ece": ece(y, p),
        "taxa_real": float(y.mean()),
        "taxa_prevista": float(p.mean()),
    }


def curva_calibracao(y: np.ndarray, p: np.ndarray, faixas: int = FAIXAS_CALIBRACAO) -> list[dict]:
    y = np.asarray(y, dtype=float)
    p = np.asarray(p, dtype=float)
    indices = np.minimum((p * faixas).astype(int), faixas - 1)
    curva = []
    for faixa in range(faixas):
        dentro = indices == faixa
        if dentro.any():
            curva.append(
                {
                    "faixa": [faixa / faixas, (faixa + 1) / faixas],
                    "voos": int(dentro.sum()),
                    "prevista_media": float(p[dentro].mean()),
                    "taxa_real": float(y[dentro].mean()),
                }
            )
    return curva


def intervalos_bootstrap(
    y: np.ndarray,
    p: np.ndarray,
    dias: np.ndarray,
    amostras: int = AMOSTRAS_BOOTSTRAP,
    semente: int = SEMENTE,
    nivel: float = 0.95,
) -> dict[str, list[float]]:
    """Intervalo de confiança de cada métrica, sorteando dias com reposição."""
    y = np.asarray(y, dtype=float)
    p = np.asarray(p, dtype=float)
    _, grupo = np.unique(np.asarray(dias), return_inverse=True)
    linhas_por_dia = [np.flatnonzero(grupo == g) for g in range(grupo.max() + 1)]
    gerador = np.random.default_rng(semente)

    valores: dict[str, list[float]] = {}
    for _ in range(amostras):
        sorteados = gerador.integers(0, len(linhas_por_dia), len(linhas_por_dia))
        linhas = np.concatenate([linhas_por_dia[d] for d in sorteados])
        if y[linhas].min() == y[linhas].max():
            continue  # amostra com uma classe só: AUC indefinida
        for nome, valor in metricas(y[linhas], p[linhas]).items():
            if nome != "voos":
                valores.setdefault(nome, []).append(valor)

    caudas = [(1 - nivel) / 2 * 100, (1 + nivel) / 2 * 100]
    return {
        nome: [float(v) for v in np.percentile(lista, caudas)] for nome, lista in valores.items()
    }
