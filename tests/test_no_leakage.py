"""Teste contra vazamento (docs/decisoes/003-regra-as-of.md).

Monta um banco pequeno com 6 meses de voos numa mesma rota. As variáveis de um voo de junho só
podem usar meses até abril (junho - 2 meses de defasagem). O teste muda de propósito os voos de
maio e junho para atrasos enormes e confere que as variáveis de junho não mudam. Depois muda
abril e confere que elas mudam: prova que o teste enxergaria um vazamento se ele existisse.
"""

import duckdb
import pytest

from fdr.features.build import ALVO, COLUNAS_SO_ANALISE, PROIBIDAS, TABELA, construir

MESES = [f"2025-{m:02d}-01" for m in range(5, 13)] + [f"2026-{m:02d}-01" for m in range(1, 7)]


def criar_banco(atrasos_por_mes: dict[str, int]) -> duckdb.DuckDBPyConnection:
    """10 voos por mês na rota SBRF-SBGR às 10h, na segunda quarta-feira de cada mês, de mai/2025
    a jun/2026; `atrasos_por_mes` diz quantos atrasaram (1 por padrão)."""
    con = duckdb.connect()
    linhas = []
    for mes in MESES:
        atrasos = atrasos_por_mes.get(mes, 1)
        for i in range(10):
            linhas.append((f"{mes}-{i}", mes, i < atrasos))
    con.execute("""
        create table voos_brutos (voo_id varchar, mes date, atrasou boolean)
    """)
    con.executemany("insert into voos_brutos values (?, ?, ?)", linhas)
    con.execute("""
        create table fct_flights as
        with dias as (
            -- todos os voos na segunda quarta-feira do mês
            select *, mes + to_days(((3 - isodow(mes) + 7) % 7 + 7)::int) as dia
            from voos_brutos
        )
        select
            voo_id, mes, dia::date as data_prevista, dia::date as data_prevista_local,
            dia + interval 10 hour as partida_prevista,
            true as nacional, true as regular, true as realizado, atrasou as atrasado_15,
            10 as hora_prevista_local, 'GLO' as cia, 'SBRF' as origem, 'SBGR' as destino,
            180 as duracao_prevista_min,
            dia + interval 13 hour as chegada_prevista,
            -- colunas que só se sabem depois do voo, e que não podem virar variável
            dia + interval 10 hour + to_minutes(case when atrasou then 600 else 0 end)
                as partida_real,
            dia + interval 13 hour + to_minutes(case when atrasou then 700 else 0 end)
                as chegada_real,
            case when atrasou then 600 else 0 end as atraso_partida_min,
            'REALIZADO' as situacao
        from dias
    """)
    con.execute("""
        create table dim_date as
        select data, isodow(data) as dia_semana, false as feriado, false as vespera_feriado,
               false as pos_feriado, false as ferias_escolares
        from (select cast(unnest(generate_series(date '2025-01-01', date '2026-12-31',
                                                 interval 1 day)) as date) as data)
    """)
    con.execute(
        "create table dim_routes as "
        "select 'SBRF' as origem, 'SBGR' as destino, 2100 as distancia_km"
    )
    return con


def variaveis_de_junho(con: duckdb.DuckDBPyConnection) -> list[tuple]:
    construir(con, defasagem=2)
    colunas = [
        c[0]
        for c in con.execute(f"describe {TABELA}").fetchall()
        if c[0] != ALVO and c[0] not in COLUNAS_SO_ANALISE
    ]
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
    # 3 meses até abril: fev, mar, abr = 30 voos, 12 atrasados. 12 meses: mai/2025 a abr/2026 =
    # 120 voos e 20 atrasados (1 por mês de mai a dez de 2025, mais 0 + 2 + 4 + 6).
    assert junho == [(30, pytest.approx(0.4), 120, pytest.approx(20 / 120))]


def test_meses_sem_historico_ficam_sem_taxa():
    con = criar_banco({})
    construir(con, defasagem=2)
    junho_2025 = con.execute(f"""
        select distinct taxa_rota_hora_12m, voos_rota_hora_12m, duracao_tipica_min
        from {TABELA} where mes = date '2025-06-01'
    """).fetchall()
    assert junho_2025 == [(None, 0, None)]  # o corte é abril de 2025, sem dados


def test_sazonalidade_usa_o_mesmo_mes_do_ano_anterior():
    con = criar_banco({"2025-06-01": 7})
    construir(con, defasagem=2)
    junho = con.execute(f"""
        select distinct taxa_rota_ano_anterior, voos_rota_ano_anterior
        from {TABELA} where mes = date '2026-06-01'
    """).fetchall()
    assert junho == [(pytest.approx(0.7), 10)]


def test_programacao_e_duracao_tipicas_vem_do_historico():
    """Junho usa a programação de fev a abr (3 meses até o corte) e as durações até abril."""
    con = criar_banco({"2026-04-01": 10})
    construir(con, defasagem=2)
    partidas, antes, duracao, folga = con.execute(f"""
        select distinct partidas_tipicas_origem_hora, partidas_cia_antes_tipicas,
               duracao_tipica_min, folga_tipica_min
        from {TABELA} where mes = date '2026-06-01'
    """).fetchone()
    # 30 partidas de fev a abr, todas em quartas-feiras; fev a abr de 2026 têm 13 quartas.
    assert partidas == pytest.approx(30 / 13)
    assert antes == 0  # nenhuma partida da GLO antes das 10h
    # 12 meses até abril: 120 voos de 180 min previstos; reais: 180 min, ou 280 min se atrasou.
    # Os 10 de abril atrasaram (280 min); nos outros 11 meses, 1 atrasado por mês.
    reais = (10 * 280 + 11 * (280 + 9 * 180)) / 120
    assert duracao == pytest.approx(180)
    assert folga == pytest.approx(180 - reais)


def test_nenhuma_coluna_proibida_vira_variavel():
    con = criar_banco({})
    construir(con, defasagem=2)
    colunas = {c[0] for c in con.execute(f"describe {TABELA}").fetchall()}
    assert colunas.isdisjoint(PROIBIDAS)
    assert ALVO in colunas
