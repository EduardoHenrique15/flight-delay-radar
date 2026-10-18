"""Testes das regras simples da previsão no app. A paridade com o treino fica em
tests/test_pipeline_fixtures.py, que roda o pipeline na amostra."""

from datetime import date

import pytest

from fdr import previsao


@pytest.mark.parametrize(
    ("mes", "meses", "esperado"),
    [
        (date(2026, 8, 1), 1, date(2026, 9, 1)),
        (date(2026, 11, 1), 2, date(2027, 1, 1)),
        (date(2026, 1, 1), -2, date(2025, 11, 1)),
    ],
)
def test_somar_meses(mes, meses, esperado):
    assert previsao.somar_meses(mes, meses) == esperado


def test_faixas():
    assert previsao.faixa(0.05) == "baixa"
    assert previsao.faixa(0.10) == "média"
    assert previsao.faixa(0.249) == "média"
    assert previsao.faixa(0.25) == "alta"


def test_historico_defasado_depois_de_dois_meses():
    """Com dados até agosto: setembro e outubro usam o mesmo corte do treino (M - 2);
    novembro já usaria setembro, que ainda não saiu."""
    previsor = previsao.Previsor.__new__(previsao.Previsor)
    previsor.manifest = {"ultimo_mes_publicado": "2026-08-01", "defasagem_meses": 2}
    assert not previsor.historico_defasado(date(2026, 9, 20))
    assert not previsor.historico_defasado(date(2026, 10, 31))
    assert previsor.historico_defasado(date(2026, 11, 1))
