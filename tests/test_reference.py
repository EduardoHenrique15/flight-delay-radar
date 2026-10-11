"""Testes da carga das referências: aeroportos (OurAirports) e feriados nacionais."""

from datetime import date

import duckdb
import pytest

from fdr.ingest.reference import ReferenciaAusenteError, carregar_aeroportos, carregar_feriados

CABECALHO = (
    "id,ident,type,name,latitude_deg,longitude_deg,elevation_ft,continent,iso_country,"
    "iso_region,municipality,scheduled_service,icao_code,iata_code,gps_code,local_code,"
    "home_link,wikipedia_link,keywords"
)


@pytest.fixture
def con():
    conexao = duckdb.connect()
    yield conexao
    conexao.close()


def test_carrega_aeroportos_com_as_colunas_usadas(con, tmp_path):
    arquivo = tmp_path / "airports.csv"
    arquivo.write_text(
        CABECALHO + "\n"
        '5906,"SBRF","large_airport","Recife Airport",-8.126,-34.923,33,"SA","BR","BR-PE",'
        '"Recife","yes","SBRF","REC","SBRF",,,,\n',
        encoding="utf-8",
    )
    assert carregar_aeroportos(con, arquivo) == 1
    assert con.execute("select ident, iata_code, iso_region from raw_airports").fetchone() == (
        "SBRF",
        "REC",
        "BR-PE",
    )
    assert "home_link" not in {c[0] for c in con.execute("describe raw_airports").fetchall()}


def test_arquivo_de_aeroportos_ausente_explica_onde_baixar(con, tmp_path):
    with pytest.raises(ReferenciaAusenteError, match="ourairports"):
        carregar_aeroportos(con, tmp_path / "nao_existe.csv")


def test_feriados_nacionais_em_portugues(con):
    total = carregar_feriados(con, 2025, 2026)
    assert total >= 18
    datas = dict(con.execute("select data, nome from raw_feriados").fetchall())
    assert datas[date(2026, 4, 21)] == "Tiradentes"
    assert date(2026, 12, 25) in datas
    assert min(datas).year == 2025 and max(datas).year == 2026
