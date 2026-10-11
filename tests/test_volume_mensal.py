"""Testes do script do ADR 001 (scripts/volume_mensal.py)."""

import importlib.util
from pathlib import Path

from test_load_raw import VOO_CANCELADO, VOO_REALIZADO, escrever_vra

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "volume_mensal.py"
especificacao = importlib.util.spec_from_file_location("volume_mensal", SCRIPT)
volume_mensal = importlib.util.module_from_spec(especificacao)
especificacao.loader.exec_module(volume_mensal)


def test_voos_diferentes_com_mesmos_horarios_contam_separado(tmp_path):
    outro_voo = ("AZU", "9999", *VOO_REALIZADO[2:])  # outra companhia, mesmos horários
    escrever_vra(tmp_path, "VRA_20268.csv", [VOO_REALIZADO, outro_voo, VOO_REALIZADO])

    linha = volume_mensal.calcular([tmp_path]).iloc[0]
    assert linha["linhas"] == 2  # a duplicata exata sai, o outro voo fica
    assert linha["nacionais_regulares_realizados"] == 2
    assert linha["fracao_atraso_15"] == 1.0  # os dois partiram 20 min atrasados


def test_primeira_pasta_tem_prioridade_e_meses_ficam_em_ordem(tmp_path):
    historico, janela = tmp_path / "historico", tmp_path / "janela"
    historico.mkdir()
    janela.mkdir()
    escrever_vra(historico, "VRA_20268.csv", [VOO_REALIZADO])
    escrever_vra(janela, "VRA_20268.csv", [VOO_REALIZADO, VOO_CANCELADO])
    escrever_vra(janela, "VRA_201912.csv", [VOO_CANCELADO])

    tabela = volume_mensal.calcular([historico, janela])
    assert list(tabela["mes"]) == ["2019-12", "2026-08"]
    assert tabela.set_index("mes").loc["2026-08", "linhas"] == 1
