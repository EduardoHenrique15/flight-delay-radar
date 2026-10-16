"""Testes da divisão no tempo entre treino, validação e teste."""

from datetime import date

import pytest

from fdr.model.splits import DivisaoInvalidaError, definir_divisao


def meses(inicio: tuple[int, int], fim: tuple[int, int]) -> list[date]:
    lista, (ano, mes) = [], inicio
    while (ano, mes) <= fim:
        lista.append(date(ano, mes, 1))
        ano, mes = (ano + 1, 1) if mes == 12 else (ano, mes + 1)
    return lista


def test_divisao_da_serie_do_projeto():
    divisao = definir_divisao(meses((2022, 1), (2026, 8)))
    assert divisao.teste == (date(2026, 6, 1), date(2026, 8, 1))
    assert divisao.validacao_principal.validacao == (date(2026, 3, 1), date(2026, 5, 1))
    # 1 mês de intervalo: o treino termina em janeiro, e fevereiro fica de fora.
    assert divisao.validacao_principal.treino == (date(2023, 1, 1), date(2026, 1, 1))
    assert divisao.treino_final == (date(2023, 1, 1), date(2026, 4, 1))
    assert divisao.intervalo == 1
    assert [c.validacao[0] for c in divisao.cortes] == [
        date(2025, 3, 1),
        date(2025, 6, 1),
        date(2025, 9, 1),
        date(2025, 12, 1),
        date(2026, 3, 1),
    ]


def test_treino_comeca_em_2023_e_nunca_alcanca_validacao_nem_teste():
    divisao = definir_divisao(meses((2022, 1), (2026, 8)))
    for corte in divisao.cortes:
        assert corte.treino[0] == date(2023, 1, 1)
        assert corte.treino[1] < corte.validacao[0]
        # sempre pelo menos 1 mês inteiro entre o fim do treino e a avaliação
        assert (corte.validacao[0].year - corte.treino[1].year) * 12 + (
            corte.validacao[0].month - corte.treino[1].month
        ) == 2
        assert corte.validacao[1] < divisao.teste[0]


def test_meses_insuficientes_falham_com_mensagem_clara():
    with pytest.raises(DivisaoInvalidaError, match="insuficientes"):
        definir_divisao(meses((2026, 5), (2026, 7)))


def test_sem_intervalo_o_treino_encosta_na_validacao():
    divisao = definir_divisao(meses((2022, 1), (2026, 8)), intervalo=0)
    assert divisao.validacao_principal.treino[1] == date(2026, 2, 1)
    assert divisao.treino_final[1] == date(2026, 5, 1)
