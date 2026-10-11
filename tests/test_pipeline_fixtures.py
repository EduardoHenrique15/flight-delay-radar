"""Teste de ponta a ponta: roda o pipeline de dados (carga, dbt build e exportação) na amostra
de data/fixtures/vra/, em pastas temporárias, sem tocar nos dados reais."""

import json
import os
import subprocess
import sys

import duckdb
import pytest

from fdr.config import ARQUIVO_AEROPORTOS_FIXTURE, PASTA_FIXTURES_VRA


def linhas_de_dados(pasta) -> int:
    """Conta as linhas de voo dos CSVs (sem a linha de metadado e o cabeçalho)."""
    return sum(
        len([linha for linha in arq.read_bytes().splitlines() if linha]) - 2
        for arq in pasta.glob("VRA_*.csv")
    )


@pytest.fixture(scope="module")
def pipeline(tmp_path_factory):
    pasta = tmp_path_factory.mktemp("pipeline")
    ambiente = {
        **os.environ,
        "FDR_PASTA_VRA": str(PASTA_FIXTURES_VRA),
        "FDR_ARQUIVO_AEROPORTOS": str(ARQUIVO_AEROPORTOS_FIXTURE),
        "FDR_WAREHOUSE": str(pasta / "warehouse.duckdb"),
        "FDR_PASTA_MARTS": str(pasta / "marts"),
        "FDR_BANCO_APP": str(pasta / "app.duckdb"),
    }
    resultado = subprocess.run(
        [sys.executable, "-m", "fdr.pipeline", "--stage", "data"],
        env=ambiente,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert resultado.returncode == 0, resultado.stdout[-3000:] + resultado.stderr[-3000:]
    con = duckdb.connect(ambiente["FDR_WAREHOUSE"], read_only=True)
    yield con, pasta
    con.close()


def test_carga_traz_todas_as_linhas(pipeline):
    con, _ = pipeline
    assert con.execute("select count(*) from raw_vra").fetchone()[0] == linhas_de_dados(
        PASTA_FIXTURES_VRA
    )


def test_duplicatas_removidas_no_arquivo_e_entre_arquivos(pipeline):
    con, _ = pipeline
    bruto = con.execute("select count(*) from raw_vra").fetchone()[0]
    por_arquivo = con.execute("select count(*) from stg_vra").fetchone()[0]
    total = con.execute("select count(*) from int_flights").fetchone()[0]
    assert bruto - por_arquivo == 9  # 3 duplicatas exatas em cada um dos 3 meses
    assert por_arquivo - total == 1  # 1 voo repetido em junho e julho


def test_atraso_e_a_diferenca_entre_real_e_prevista(pipeline):
    con, _ = pipeline
    errados = con.execute("""
        select count(*) from fct_flights
        where atraso_partida_min <> date_diff('minute', partida_prevista, partida_real)
    """).fetchone()[0]
    assert errados == 0


def test_virada_da_meia_noite(pipeline):
    con, _ = pipeline
    casos = con.execute("""
        select atraso_partida_min from fct_flights
        where nacional and cast(partida_real as date) > cast(partida_prevista as date)
          and atraso_partida_min between 0 and 120
    """).fetchall()
    assert casos, "a amostra deveria ter voos que atrasaram passando da meia-noite"
    assert all(0 <= a <= 120 for (a,) in casos)


def test_datas_com_nanossegundos_sao_lidas(pipeline):
    con, _ = pipeline
    com_sufixo = con.execute(
        """select count(*) from raw_vra where "Partida Prevista" like '%.%'"""
    ).fetchone()[0]
    assert com_sufixo > 0
    # Só vira nulo o que já era 'null' no arquivo: nenhuma data com sufixo se perde.
    nulas_no_arquivo = con.execute("""
        select count(*) from (select distinct * exclude (carregado_em) from raw_vra)
        where "Partida Prevista" = 'null'
    """).fetchone()[0]
    nulas_na_staging = con.execute(
        "select count(*) from stg_vra where partida_prevista is null"
    ).fetchone()[0]
    assert nulas_na_staging == nulas_no_arquivo


def test_quarentena_guarda_os_motivos(pipeline):
    con, _ = pipeline
    motivos = {
        m
        for (m,) in con.execute("select distinct motivo_quarentena from int_quarantine").fetchall()
    }
    assert {"atraso fora da faixa aceita", "conflito de chave"} <= motivos
    na_final = con.execute(
        "select count(*) from fct_flights where voo_id in (select voo_id from int_quarantine)"
    ).fetchone()[0]
    assert na_final == 0


def test_cancelados_e_voos_sem_previsao_ficam_sem_alvo(pipeline):
    con, _ = pipeline
    cancelados, sem_previsao, com_alvo_indevido = con.execute("""
        select
            count(*) filter (where cancelado),
            count(*) filter (where partida_prevista is null),
            count(*) filter (where (cancelado or partida_prevista is null)
                             and atrasado_15 is not null)
        from fct_flights
    """).fetchone()
    assert cancelados > 0 and sem_previsao > 0
    assert com_alvo_indevido == 0


def test_exportacao_gera_os_arquivos_do_app(pipeline):
    _, pasta = pipeline
    manifest = json.loads((pasta / "marts" / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["ultimo_mes"] == "2026-07-01"
    assert all(info["linhas"] > 0 for info in manifest["tabelas"].values())
    assert (pasta / "app.duckdb").exists()


def test_todo_voo_tem_aeroporto_e_companhia_nas_dimensoes(pipeline):
    con, _ = pipeline
    sem_aeroporto, sem_companhia = con.execute("""
        select
            count(*) filter (where o.icao is null or d.icao is null),
            count(*) filter (where c.cia is null)
        from fct_flights f
        left join dim_airports o on o.icao = f.origem
        left join dim_airports d on d.icao = f.destino
        left join dim_airlines c on c.cia = f.cia
    """).fetchone()
    assert (sem_aeroporto, sem_companhia) == (0, 0)


def test_hora_local_usa_o_fuso_da_origem(pipeline):
    con, _ = pipeline
    errados = con.execute("""
        select count(*) from fct_flights f join dim_airports a on a.icao = f.origem
        where f.partida_prevista is not null and a.diferenca_brasilia_h is not null
          and f.hora_prevista_local <> (f.hora_prevista_brasilia + a.diferenca_brasilia_h + 24) % 24
    """).fetchone()[0]
    fora_de_brasilia = con.execute("""
        select count(*) from fct_flights f join dim_airports a on a.icao = f.origem
        where a.diferenca_brasilia_h <> 0 and f.partida_prevista is not null
    """).fetchone()[0]
    assert errados == 0
    assert fora_de_brasilia > 0, "a amostra deveria ter voos saindo de outro fuso"


def test_calendario_tem_feriados(pipeline):
    con, _ = pipeline
    tiradentes = con.execute(
        "select feriado, nome_feriado from dim_date where data = date '2026-04-21'"
    ).fetchone()
    assert tiradentes == (True, "Tiradentes")
