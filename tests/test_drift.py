"""Testes do PSI (mudança na distribuição das variáveis)."""

import numpy as np
import pandas as pd
import pytest

from fdr.model import train
from fdr.model.registry import perfil_de_referencia
from fdr.monitoring import drift


def perfil_numerico(valores: np.ndarray) -> dict:
    limites = np.unique(np.quantile(valores, np.linspace(0, 1, 11)))[1:-1]
    contagem = np.bincount(
        np.searchsorted(limites, valores, side="right"), minlength=len(limites) + 1
    )
    return {
        "tipo": "numerica",
        "ausentes": 0.0,
        "limites": list(limites),
        "frequencias": list(contagem / len(valores)),
    }


def test_mesma_distribuicao_tem_psi_perto_de_zero():
    gerador = np.random.default_rng(0)
    perfil = perfil_numerico(gerador.normal(size=50_000))
    psi = drift.psi_variavel(perfil, pd.Series(gerador.normal(size=20_000)), 50_000)
    assert psi < 0.01
    assert drift.nivel(psi) == "estável"


def test_distribuicao_deslocada_dispara_alerta():
    gerador = np.random.default_rng(1)
    perfil = perfil_numerico(gerador.normal(size=50_000))
    psi = drift.psi_variavel(perfil, pd.Series(gerador.normal(1.0, size=20_000)), 50_000)
    assert psi >= drift.LIMITE_ALERTA
    assert drift.nivel(psi) == "alerta"


def test_ausentes_contam_como_faixa():
    gerador = np.random.default_rng(2)
    perfil = perfil_numerico(gerador.normal(size=50_000))
    serie = pd.Series(gerador.normal(size=20_000))
    serie[:6_000] = np.nan  # 30% de ausentes, contra 0% no treino
    assert drift.psi_variavel(perfil, serie, 50_000) >= drift.LIMITE_ALERTA


def test_categoria_nova_vai_para_outras_e_categoria_pequena_nao_pesa():
    perfil = {
        "tipo": "categorica",
        "ausentes": 0.0,
        "frequencias": {"AZU": 0.5, "GLO": 0.4999, "XYZ": 0.0001},
        "outras": 0.0,
    }
    # XYZ sumiu, mas tinha 1 voo em 10 mil: não pesa.
    estavel = pd.Series(["AZU"] * 5_000 + ["GLO"] * 5_000)
    assert drift.psi_variavel(perfil, estavel, 10_000) < 0.01
    # 30% dos voos de uma companhia nova: alerta.
    nova = pd.Series(["AZU"] * 3_500 + ["GLO"] * 3_500 + ["NOVA"] * 3_000)
    assert drift.psi_variavel(perfil, nova, 10_000) >= drift.LIMITE_ALERTA


@pytest.mark.parametrize(
    ("psi", "esperado"),
    [(0.0999, "estável"), (0.10, "atenção"), (0.2499, "atenção"), (0.25, "alerta")],
)
def test_niveis_nos_limites(psi, esperado):
    assert drift.nivel(psi) == esperado


def test_psi_de_todas_as_variaveis_com_o_perfil_do_registro():
    from sinteticos import dados_sinteticos

    dados = dados_sinteticos(por_mes=100)
    perfil = perfil_de_referencia(dados)
    psi = drift.psi_todas(perfil, dados, len(dados))
    assert set(psi) == set(train.VARIAVEIS)
    assert max(psi.values()) < 0.01  # o próprio treino contra o seu perfil
