"""Testes das consultas do app (fdr.painel) com os marts da amostra: números de impacto,
calendário e mapa de rotas."""

import pytest

from fdr import painel


@pytest.fixture(scope="module")
def con(amostra_pipeline):
    return painel.conectar_marts(amostra_pipeline / "marts")


@pytest.fixture(scope="module")
def periodo(con):
    meses = painel.meses(con)
    return meses[0], meses[-1]


def test_impacto_do_mes_soma_os_minutos_dos_voos_atrasados(con, periodo):
    mes = periodo[1]
    impacto = painel.impacto_do_mes(con, mes)
    voos, minutos = con.execute(
        f"select count(*), sum(atraso_partida_min) from voos "
        f"where mes = ? and {painel.BASE} and atraso_partida_min > 15",
        [mes],
    ).fetchone()
    assert impacto["voos_atrasados"] == voos > 0
    assert impacto["horas"] == pytest.approx(minutos / 60)
    assert impacto["mediana_min"] > 15


def test_calendario_cobre_os_mesmos_voos_da_evolucao_mensal(con, periodo):
    dias = painel.calendario(con, *periodo)
    meses = painel.evolucao_mensal(con, *periodo)
    assert dias["voos"].sum() == meses["voos"].sum()
    assert dias["taxa_atraso"].between(0, 1).all()
    assert dias["data"].is_monotonic_increasing


def test_mapa_rotas_traz_as_rotas_mais_voadas_com_coordenadas(con, periodo):
    rotas = painel.mapa_rotas(con, *periodo, limite=5, minimo=1)
    assert 0 < len(rotas) <= 5
    assert rotas["voos"].is_monotonic_decreasing
    colunas = ["lon_origem", "lat_origem", "lon_destino", "lat_destino"]
    assert rotas[colunas].notna().all().all()
    origem = rotas.iloc[0]["origem"]
    so_dela = painel.mapa_rotas(con, *periodo, origem=origem, minimo=1)
    assert (so_dela["origem"] == origem).all()
