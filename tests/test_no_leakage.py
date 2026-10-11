"""Teste contra vazamento (PROJETO.md, seção 6.3).

Monta um banco pequeno com 6 meses de voos numa mesma rota. As variáveis de um voo de junho só
podem usar meses até abril (junho - 2 meses de defasagem). O teste muda de propósito os voos de
maio e junho para atrasos enormes e confere que as variáveis de junho não mudam. Depois muda
abril e confere que elas mudam: prova que o teste enxergaria um vazamento se ele existisse.
"""

import duckdb
import pytest

from fdr.features.build import ALVO, PROIBIDAS, TABELA, construir

MESES = ["2026-01-01", "2026-02-01", "2026-03-01", "2026-04-01", "2026-05-01", "2026-06-01"]


def criar_banco(atrasos_por_mes: dict[str, int]) -> duckdb.DuckDBPyConnection:
    """10 voos por mês na rota SBRF-SBGR às 10h; `atrasos_por_mes` diz quantos atrasaram."""
    con = duckdb.connect()
    linhas = []
    for mes in MESES:
        for i in range(10):
            linhas.append((f"{mes}-{i}", mes, i < atrasos_por_mes.get(mes, 1)))
    con.execute("""
        create table voos_brutos (voo_id varchar, mes date, atrasou boolean)
    """)
    con.executemany("insert into voos_brutos values (?, ?, ?)", linhas)
    con.execute("""
        create table fct_flights as
        select
            voo_id, mes, mes + interval 9 day as data_prevista,
            mes + interval 9 day + interval 10 hour as partida_prevista,
            true as nacional, true as regular, atrasou as atrasado_15,
            10 as hora_prevista_local, 'GLO' as cia, 'SBRF' as origem, 'SBGR' as destino,
            180 as duracao_prevista_min,
            -- colunas que só se sabem depois do voo, e que não podem virar variável
            mes + interval 9 day + interval 10 hour
                + to_minutes(case when atrasou then 600 else 0 end) as partida_real,
            case when atrasou then 600 else 0 end as atraso_partida_min,
            'REALIZADO' as situacao
        from voos_brutos
    """)
    con.execute("""
        create table dim_date as
        select cast(unnest(generate_series(date '2026-01-01', date '2026-12-31', interval 1 day))
               as date) as data,
               3 as dia_semana, false as feriado, false as vespera_feriado,
               false as pos_feriado, false as ferias_escolares
    """)
    con.execute(
        "create table dim_routes as "
        "select 'SBRF' as origem, 'SBGR' as destino, 2100 as distancia_km"
    )
    return con


def variaveis_de_junho(con: duckdb.DuckDBPyConnection) -> list[tuple]:
    construir(con, defasagem=2)
    colunas = [c[0] for c in con.execute(f"describe {TABELA}").fetchall() if c[0] != ALVO]
    return con.execute(
        f"select {', '.join(colunas)} from {TABELA} where mes = date '2026-06-01' order by voo_id"
    ).fetchall()


def test_meses_depois_do_corte_nao_mudam_as_variaveis():
    normal = variaveis_de_junho(criar_banco({}))
    # Maio e junho passam a ter todos os voos com 10 horas de atraso.
    alterado = variaveis_de_junho(criar_banco({"2026-05-01": 10, "2026-06-01": 10}))
    assert normal == alterado


def test_mes_de_corte_muda_as_variaveis():
    """Controle: se abril (o mês de corte de junho) muda, as variáveis de junho têm que mudar."""
    normal = variaveis_de_junho(criar_banco({}))
    alterado = variaveis_de_junho(criar_banco({"2026-04-01": 10}))
    assert normal != alterado


def test_janelas_de_3_e_12_meses_terminam_no_corte():
    con = criar_banco({"2026-01-01": 0, "2026-02-01": 2, "2026-03-01": 4, "2026-04-01": 6})
    construir(con, defasagem=2)
    junho = con.execute(f"""
        select distinct voos_rota_hora_3m, taxa_rota_hora_3m, voos_rota_hora_12m,
               taxa_rota_hora_12m
        from {TABELA} where mes = date '2026-06-01'
    """).fetchall()
    # 3 meses até abril: fev, mar, abr = 30 voos, 12 atrasados. 12 meses: jan a abr = 40 e 12.
    assert junho == [(30, pytest.approx(0.4), 40, pytest.approx(0.3))]


def test_meses_sem_historico_ficam_sem_taxa():
    con = criar_banco({})
    construir(con, defasagem=2)
    fevereiro = con.execute(f"""
        select distinct taxa_rota_hora_12m, voos_rota_hora_12m
        from {TABELA} where mes = date '2026-02-01'
    """).fetchall()
    assert fevereiro == [(None, 0)]  # o corte de fevereiro é dezembro de 2025, sem dados


def test_nenhuma_coluna_proibida_vira_variavel():
    con = criar_banco({})
    construir(con, defasagem=2)
    colunas = {c[0] for c in con.execute(f"describe {TABELA}").fetchall()}
    assert colunas.isdisjoint(PROIBIDAS)
    assert ALVO in colunas
