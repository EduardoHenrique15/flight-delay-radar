"""Dados sintéticos no formato da tabela features_voos, para os testes dos modelos."""

import numpy as np
import pandas as pd

from fdr.features.build import ALVO
from fdr.model import train


def dados_sinteticos(por_mes: int = 400, semente: int = 0) -> pd.DataFrame:
    """Jan/2023 a ago/2026 no formato da features_voos. O atraso depende da companhia, da hora e
    de uma taxa histórica com ruído, para os modelos terem o que aprender."""
    gerador = np.random.default_rng(semente)
    meses = pd.date_range("2023-01-01", "2026-08-01", freq="MS")
    n = por_mes * len(meses)
    mes = np.repeat(meses.to_numpy(), por_mes)
    cia = gerador.choice(["AZU", "GLO", "TAM"], n)
    hora = gerador.integers(0, 24, n)
    logito = -1.8 + 0.6 * (cia == "GLO") + 0.05 * (hora - 12)
    verdade = 1 / (1 + np.exp(-logito))
    dados = pd.DataFrame(
        {
            "mes": mes,
            "data_prevista": mes + pd.to_timedelta(gerador.integers(0, 28, n), unit="D"),
            ALVO: (gerador.uniform(size=n) < verdade).astype("int8"),
            "cia": pd.Categorical(cia),
            "origem": pd.Categorical(gerador.choice(["SBGR", "SBSP", "SBBR", "SBKP"], n)),
            "destino": pd.Categorical(gerador.choice(["SBRJ", "SBCF", "SBPA"], n)),
            "hora_prevista_local": hora,
            "dia_semana": gerador.integers(1, 8, n),
            "mes_do_ano": pd.DatetimeIndex(mes).month,
        }
    )
    for coluna in train.BINARIAS:
        dados[coluna] = (gerador.uniform(size=n) < 0.05).astype(int)
    for coluna in train.CONTINUAS:
        dados[coluna] = gerador.uniform(0, 300, n)
    for coluna in train.HISTORICO:
        if coluna.startswith("taxa_"):
            valores = np.clip(verdade + gerador.normal(0, 0.05, n), 0, 1)
            if "global" not in coluna:
                valores[gerador.uniform(size=n) < 0.1] = np.nan  # sem histórico
        else:
            valores = gerador.integers(0, 500, n)
        dados[coluna] = valores
    numericas = [c for c in train.VARIAVEIS if c not in train.CATEGORICAS]
    dados[numericas] = dados[numericas].astype("float32")
    return dados
