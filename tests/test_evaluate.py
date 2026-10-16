"""Testes das métricas de avaliação."""

import numpy as np
import pytest

from fdr.model.evaluate import (
    curva_calibracao,
    ece,
    intervalos_bootstrap,
    intervalos_bootstrap_pareado,
    lift_no_topo,
    metricas,
)


def test_ece_zero_quando_a_previsao_bate_com_a_taxa_real():
    # Faixa 0,2: 10 voos previstos a 20% e 2 atrasaram. Faixa 0,8: 10 a 80% e 8 atrasaram.
    p = np.array([0.2] * 10 + [0.8] * 10)
    y = np.array([1, 1] + [0] * 8 + [1] * 8 + [0, 0])
    assert ece(y, p) == pytest.approx(0.0)


def test_ece_mede_a_distancia_media_ponderada():
    p = np.array([0.1] * 10 + [0.9] * 30)
    y = np.array([0] * 10 + [1] * 15 + [0] * 15)  # 0% real em 0,1 e 50% real em 0,9
    assert ece(y, p) == pytest.approx((10 * 0.1 + 30 * 0.4) / 40)


def test_metricas_de_um_preditor_perfeito():
    y = np.array([0, 0, 1, 1])
    resultado = metricas(y, np.array([0.0, 0.0, 1.0, 1.0]))
    assert resultado["pr_auc"] == 1.0 and resultado["roc_auc"] == 1.0
    assert resultado["brier"] == 0.0 and resultado["voos"] == 4


def test_curva_de_calibracao_soma_todos_os_voos():
    gerador = np.random.default_rng(0)
    p = gerador.uniform(size=500)
    y = (gerador.uniform(size=500) < p).astype(int)
    assert sum(f["voos"] for f in curva_calibracao(y, p)) == 500


def test_bootstrap_por_dia_e_reprodutivel_e_contem_a_estimativa():
    gerador = np.random.default_rng(1)
    dias = np.repeat(np.arange(60), 50)
    p = gerador.uniform(size=len(dias))
    y = (gerador.uniform(size=len(dias)) < p).astype(int)
    a = intervalos_bootstrap(y, p, dias, amostras=50, semente=7)
    b = intervalos_bootstrap(y, p, dias, amostras=50, semente=7)
    assert a == b
    pontual = metricas(y, p)
    for nome in ("pr_auc", "roc_auc", "brier", "ece"):
        baixo, alto = a[nome]
        assert baixo <= pontual[nome] <= alto or nome == "ece"
        assert baixo < alto


def test_lift_no_topo_conta_os_atrasos_dos_voos_de_maior_risco():
    p = np.linspace(0, 1, 100)
    y = (p >= 0.9).astype(int)  # só os 10 de maior risco atrasam
    resultado = lift_no_topo(y, p, fracao=0.10)
    assert resultado["voos"] == 10
    assert resultado["precisao"] == pytest.approx(1.0)
    assert resultado["lift"] == pytest.approx(10.0)


def test_bootstrap_pareado_de_um_modelo_contra_ele_mesmo_da_zero():
    gerador = np.random.default_rng(2)
    dias = np.repeat(np.arange(40), 50)
    p = gerador.uniform(size=len(dias))
    y = (gerador.uniform(size=len(dias)) < p).astype(int)
    intervalos = intervalos_bootstrap_pareado(y, p, p, dias, amostras=30)
    assert all(baixo == alto == 0 for baixo, alto in intervalos.values())
    melhor = intervalos_bootstrap_pareado(y, p, np.full(len(p), 0.5), dias, amostras=30)
    assert melhor["roc_auc"][0] > 0  # o modelo com sinal ganha do chute constante
