"""Testes da exportação dos marts, com um warehouse pequeno montado na hora."""

import json

import duckdb
import pytest

import fdr.export
from fdr.export import ExportacaoError, exportar


@pytest.fixture
def warehouse(tmp_path):
    """Warehouse com 3 meses e as colunas que a exportação usa."""
    caminho = tmp_path / "warehouse.duckdb"
    with duckdb.connect(str(caminho)) as con:
        con.execute("""
            create table fct_flights as
            select
                mes::date as mes,
                (mes + interval 2 day)::date as data_prevista,
                'GLO' as cia,
                '1234' as numero_voo,
                'N' as tipo_linha,
                true as regular,
                'SBRF' as origem,
                'SBGR' as destino,
                mes + interval 2 day + interval 10 hour as partida_prevista,
                180 as duracao_prevista_min,
                'REALIZADO' as situacao,
                20 as atraso_partida_min,
                5 as atraso_chegada_min,
                true as atrasado_15,
                false as atrasado_30,
                false as atrasado_60,
                'hash' as voo_id
            from (values (date '2026-06-01'), (date '2026-07-01'), (date '2026-08-01')) t(mes)
        """)
        con.execute(
            "create table agg_punctuality_monthly as "
            "select mes, 'GLO' as cia, 'SBRF' as origem, 'N' as tipo_linha, 1 as voos "
            "from fct_flights"
        )
        con.execute(
            "create table agg_route_hour as "
            "select mes, 'SBRF' as origem, 'SBGR' as destino, 10 as hora_prevista, 1 as voos "
            "from fct_flights"
        )
    return caminho


def test_exporta_so_a_janela_pedida(warehouse, tmp_path):
    marts, app = tmp_path / "marts", tmp_path / "app.duckdb"
    manifest = exportar(warehouse, marts, app, meses=2)

    assert manifest["primeiro_mes"] == "2026-07-01"
    assert manifest["ultimo_mes"] == "2026-08-01"
    assert {nome: t["linhas"] for nome, t in manifest["tabelas"].items()} == {
        "voos": 2,
        "pontualidade_mensal": 2,
        "atraso_rota_hora": 2,
    }
    assert json.loads((marts / "manifest.json").read_text(encoding="utf-8")) == manifest


def test_voos_saem_enxutos(warehouse, tmp_path):
    marts = tmp_path / "marts"
    exportar(warehouse, marts, tmp_path / "app.duckdb", meses=24)
    colunas = duckdb.sql(f"describe select * from '{marts / 'voos.parquet'}'").fetchall()
    nomes = {c[0] for c in colunas}
    assert "voo_id" not in nomes
    assert "hora_prevista" in nomes
    assert duckdb.sql(f"select count(*) from '{marts / 'voos.parquet'}'").fetchone() == (3,)


def test_banco_do_assistente_tem_so_as_tabelas_exportadas(warehouse, tmp_path):
    app = tmp_path / "app.duckdb"
    exportar(warehouse, tmp_path / "marts", app, meses=24)
    with duckdb.connect(str(app), read_only=True) as con:
        tabelas = {t[0] for t in con.execute("show tables").fetchall()}
    assert tabelas == {"voos", "pontualidade_mensal", "atraso_rota_hora"}


def test_reexportar_substitui_o_banco(warehouse, tmp_path):
    marts, app = tmp_path / "marts", tmp_path / "app.duckdb"
    exportar(warehouse, marts, app, meses=24)
    exportar(warehouse, marts, app, meses=1)
    with duckdb.connect(str(app), read_only=True) as con:
        assert con.execute("select count(*) from voos").fetchone() == (1,)


def test_warehouse_vazio_falha(tmp_path):
    caminho = tmp_path / "vazio.duckdb"
    with duckdb.connect(str(caminho)) as con:
        con.execute("create table fct_flights (mes date)")
    with pytest.raises(ExportacaoError, match="vazia"):
        exportar(caminho, tmp_path / "marts", tmp_path / "app.duckdb")


def test_arquivo_grande_demais_falha(warehouse, tmp_path, monkeypatch):
    monkeypatch.setattr(fdr.export, "TAMANHO_MAX_ARQUIVO_MB", 0.0001)
    with pytest.raises(ExportacaoError, match="acima de"):
        exportar(warehouse, tmp_path / "marts", tmp_path / "app.duckdb")
