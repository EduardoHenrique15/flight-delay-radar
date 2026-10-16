"""Fixtures compartilhadas pelos testes."""

import duckdb
import pytest


@pytest.fixture
def banco(tmp_path):
    """Um app.duckdb pequeno com as 6 tabelas e as colunas que o assistente conhece."""
    caminho = tmp_path / "app.duckdb"
    with duckdb.connect(str(caminho)) as con:
        con.execute("""
            create table voos as
            select date '2026-07-01' as mes, date '2026-07-10' as data_prevista, cia,
                   '1234' as numero_voo, 'N' as tipo_linha, true as regular, origem,
                   'SBRJ' as destino, 10::tinyint as hora_prevista,
                   60::smallint as duracao_prevista_min, 'REALIZADO' as situacao,
                   atraso::smallint as atraso_partida_min, atraso::smallint as atraso_chegada_min,
                   atraso > 15 as atrasado_15, atraso > 30 as atrasado_30,
                   atraso > 60 as atrasado_60
            from (values ('GLO', 'SBSP', 5), ('GLO', 'SBSP', 40), ('AZU', 'SBKP', 90))
                 t(cia, origem, atraso)
        """)
        con.execute("""
            create table pontualidade_mensal as
            select mes, cia, origem, tipo_linha, count(*) as voos, count(*) as realizados,
                   count(*) as realizados_com_horario, sum(atrasado_15::int) as atrasados_15,
                   sum(atrasado_30::int) as atrasados_30, sum(atrasado_60::int) as atrasados_60,
                   0 as cancelados, avg(atrasado_15::int) as taxa_atraso_15,
                   0.0 as taxa_cancelamento
            from voos group by all
        """)
        con.execute("""
            create table atraso_rota_hora as
            select mes, origem, destino, hora_prevista, count(*) as voos,
                   sum(atrasado_15::int) as atrasados_15
            from voos group by all
        """)
        con.execute("""
            create table aeroportos as select * from (values
                ('SBSP', 'CGH', 'Congonhas', 'São Paulo', 'SP', 'BR', -23.6, -46.6,
                 'America/Sao_Paulo', 0),
                ('SBKP', 'VCP', 'Viracopos', 'Campinas', 'SP', 'BR', -23.0, -47.1,
                 'America/Sao_Paulo', 0)
            ) t(icao, iata, nome, cidade, uf, pais, latitude, longitude, fuso_iana,
                diferenca_brasilia_h)
        """)
        con.execute("""
            create table companhias as select * from (values
                ('GLO', 'Gol', true, true, 2, 2), ('AZU', 'Azul', true, true, 1, 1)
            ) t(cia, nome, nome_conhecido, brasileira, voos, voos_nacionais)
        """)
        con.execute("""
            create table rotas as select origem, destino, count(*) as voos, true as domestica,
                   300.0 as distancia_km from voos group by all
        """)
    return caminho
