"""Mudança na distribuição das variáveis: PSI (Population Stability Index) contra o perfil do
treino (models/reference_profile.json, gerado por fdr.model.registry).

PSI = soma, em cada faixa, de (atual - esperado) * ln(atual / esperado), com as frações de voos.
Faixas: os decis do treino (números) ou as categorias mais comuns (categorias), e uma faixa
para os ausentes. Leitura usual: abaixo de 0,10 estável; de 0,10 a 0,25 atenção; 0,25 ou mais,
mudança grande (PROJETO.md, Fase 4).

Faixas com menos de MIN_VOOS_FAIXA voos, no esperado e no atual, entram em "outras" (categorias)
ou não pesam (números): com poucos voos, a fração oscila por acaso e o PSI dispara à toa.
"""

import numpy as np
import pandas as pd

LIMITE_ATENCAO = 0.10
LIMITE_ALERTA = 0.25
MIN_VOOS_FAIXA = 100
PISO = 1e-4  # fração mínima, para o logaritmo não explodir em faixas vazias


def _psi(esperado: np.ndarray, atual: np.ndarray) -> float:
    esperado = np.clip(esperado, PISO, None)
    atual = np.clip(atual, PISO, None)
    return float(np.sum((atual - esperado) * np.log(atual / esperado)))


def fracoes_atuais(perfil: dict, serie: pd.Series) -> tuple[list[str], np.ndarray, np.ndarray]:
    """Faixas, frações esperadas (treino) e frações atuais (mês novo) de uma variável."""
    n = len(serie)
    ausentes = float(serie.isna().mean())
    if perfil["tipo"] == "categorica":
        faixas = list(perfil["frequencias"])
        esperado = [*perfil["frequencias"].values(), perfil["outras"]]
        valores = serie.dropna().astype("string")
        contagem = valores.value_counts()
        atual_faixas = [float(contagem.get(f, 0)) / n for f in faixas]
        atual = [*atual_faixas, max(1 - ausentes - sum(atual_faixas), 0.0)]
        faixas = [*faixas, "outras"]
    else:
        limites = np.asarray(perfil["limites"], dtype=float)
        valores = serie.dropna().to_numpy(dtype=float)
        posicoes = np.searchsorted(limites, valores, side="right")
        contagem = np.bincount(posicoes, minlength=len(limites) + 1)
        faixas = [f"faixa {i + 1}" for i in range(len(limites) + 1)]
        esperado = list(perfil["frequencias"])
        atual = list(contagem / n)
    faixas.append("ausentes")
    esperado.append(perfil["ausentes"])
    atual.append(ausentes)
    return faixas, np.asarray(esperado, dtype=float), np.asarray(atual, dtype=float)


def psi_variavel(perfil: dict, serie: pd.Series, voos_treino: int) -> float:
    """PSI de uma variável, ignorando faixas pequenas nos dois lados."""
    _, esperado, atual = fracoes_atuais(perfil, serie)
    n = len(serie)
    grandes = (esperado * voos_treino >= MIN_VOOS_FAIXA) | (atual * n >= MIN_VOOS_FAIXA)
    if perfil["tipo"] == "categorica":
        # As categorias pequenas juntam-se em "outras" (a penúltima faixa).
        pequenas = ~grandes
        pequenas[-2:] = False
        esperado[-2] += esperado[pequenas].sum()
        atual[-2] += atual[pequenas].sum()
        manter = ~pequenas
        return _psi(esperado[manter], atual[manter])
    return _psi(esperado[grandes], atual[grandes])


def nivel(psi: float) -> str:
    if psi >= LIMITE_ALERTA:
        return "alerta"
    if psi >= LIMITE_ATENCAO:
        return "atenção"
    return "estável"


def psi_todas(perfil: dict, dados: pd.DataFrame, voos_treino: int) -> dict[str, float]:
    return {
        coluna: round(psi_variavel(info, dados[coluna], voos_treino), 4)
        for coluna, info in perfil.items()
    }
