"""Monta a tabela de variáveis do modelo (features_voos) a partir dos marts, sem vazamento.

Regra "as-of" (PROJETO.md, seção 6.3): a ANAC publica cada mês com cerca de L = 2 meses de atraso.
Quem prevê um voo do mês M só conhece os voos até o fim do mês M - L. Por isso, as variáveis
históricas de um voo do mês M usam apenas os meses até M - L (o "mês de corte"). Os meses M - 1 e
M nunca entram, nem os seguintes. O teste tests/test_no_leakage.py prova isso.

Uma linha por voo da base do modelo: voos nacionais (tipo N), regulares (DI = 0), realizados e com
partida prevista e real. O alvo é `atrasado_15` (partida mais de 15 min atrasada).

Variáveis (todas conhecidas antes do voo):
- calendário: hora local prevista, dia da semana, mês, feriado, véspera, dia seguinte, férias;
- voo: companhia, origem, destino, duração prevista, distância da rota;
- congestionamento programado: partidas regulares previstas na origem naquela data e hora;
- histórico as-of: taxa de atraso e número de voos da rota x hora, da companhia, do aeroporto de
  origem e do país, nas janelas de 3 e 12 meses que terminam no mês de corte.

Uso: python -m fdr.features.build
"""

import duckdb

from fdr.config import DEFASAGEM_PUBLICACAO_MESES, WAREHOUSE

JANELAS_MESES = (3, 12)
TABELA = "features_voos"

# Grãos do histórico: nome -> colunas da chave (além do mês).
GRAOS = {
    "rota_hora": ("origem", "destino", "hora_prevista_local"),
    "cia": ("cia",),
    "origem": ("origem",),
    "global": (),
}

# Colunas que nunca podem virar variável: só se sabem depois do voo (PROJETO.md, seção 6.2).
PROIBIDAS = frozenset(
    {
        "partida_real",
        "chegada_real",
        "atraso_partida_min",
        "atraso_chegada_min",
        "atrasado_30",
        "atrasado_60",
        "situacao",
        "justificativa",
        "realizado",
        "cancelado",
        "nao_informado",
    }
)
ALVO = "atrasado_15"


def _criar_historicos(con: duckdb.DuckDBPyConnection, defasagem: int) -> None:
    """Para cada mês-alvo e cada grão, soma voos e atrasos nas janelas que terminam no corte."""
    con.execute(f"""
        create or replace temp table meses_alvo as
        select distinct mes as mes_alvo, mes - to_months({int(defasagem)}) as mes_corte
        from fct_flights
    """)
    maior = max(JANELAS_MESES)
    for nome, chave in GRAOS.items():
        colunas = ", ".join(f"h.{c}" for c in chave)
        colunas_base = ", ".join(chave)
        selecao_chave = f"{colunas}, " if chave else ""
        agrupamento_base = f"{colunas_base}, " if chave else ""
        somas = ",\n".join(
            f"sum(h.{coluna}) filter (where h.mes > m.mes_corte - to_months({j})) as {coluna}_{j}m"
            for j in JANELAS_MESES
            for coluna in ("voos", "atrasados")
        )
        con.execute(f"""
            create or replace temp table hist_{nome} as
            with mensal as (
                select {agrupamento_base}mes, count(*) as voos,
                       count(*) filter (where atrasado_15) as atrasados
                from fct_flights
                where nacional and regular and atrasado_15 is not null
                group by all
            )
            select m.mes_alvo, {selecao_chave}{somas}
            from meses_alvo m
            join mensal h
              on h.mes <= m.mes_corte
             and h.mes > m.mes_corte - to_months({maior})
            group by all
        """)


def _taxas(nome: str, apelido: str) -> str:
    """Colunas de taxa e volume de um grão, para cada janela."""
    partes = []
    for j in JANELAS_MESES:
        partes.append(
            f"{apelido}.atrasados_{j}m / nullif({apelido}.voos_{j}m, 0) as taxa_{nome}_{j}m"
        )
        partes.append(f"coalesce({apelido}.voos_{j}m, 0)::integer as voos_{nome}_{j}m")
    return ",\n            ".join(partes)


def construir(con: duckdb.DuckDBPyConnection, defasagem: int = DEFASAGEM_PUBLICACAO_MESES) -> int:
    """Cria a tabela features_voos no banco e devolve o número de linhas."""
    _criar_historicos(con, defasagem)
    con.execute(f"""
        create or replace table {TABELA} as
        with base as (
            select *
            from fct_flights
            where nacional and regular and atrasado_15 is not null
        ),

        partidas_programadas as (
            -- Programação regular: conhecida antes do voo, inclusive os que depois cancelaram.
            select origem, data_prevista, hora_prevista_local, count(*) as partidas
            from fct_flights
            where regular and partida_prevista is not null
            group by all
        )

        select
            f.voo_id,
            f.mes,
            f.data_prevista,
            f.atrasado_15::int as {ALVO},
            -- calendário
            f.hora_prevista_local,
            d.dia_semana,
            month(f.data_prevista) as mes_do_ano,
            d.feriado::int as feriado,
            d.vespera_feriado::int as vespera_feriado,
            d.pos_feriado::int as pos_feriado,
            d.ferias_escolares::int as ferias_escolares,
            -- voo
            f.cia,
            f.origem,
            f.destino,
            f.duracao_prevista_min,
            r.distancia_km,
            -- congestionamento programado
            coalesce(p.partidas, 0) as partidas_programadas_origem_hora,
            -- histórico as-of
            {_taxas("rota_hora", "hr")},
            {_taxas("cia", "hc")},
            {_taxas("origem", "ho")},
            {_taxas("global", "hg")}
        from base f
        left join dim_date d on d.data = f.data_prevista
        left join dim_routes r on r.origem = f.origem and r.destino = f.destino
        left join partidas_programadas p
          on p.origem = f.origem and p.data_prevista = f.data_prevista
         and p.hora_prevista_local = f.hora_prevista_local
        left join hist_rota_hora hr
          on hr.mes_alvo = f.mes and hr.origem = f.origem and hr.destino = f.destino
         and hr.hora_prevista_local = f.hora_prevista_local
        left join hist_cia hc on hc.mes_alvo = f.mes and hc.cia = f.cia
        left join hist_origem ho on ho.mes_alvo = f.mes and ho.origem = f.origem
        left join hist_global hg on hg.mes_alvo = f.mes
    """)
    return con.execute(f"select count(*) from {TABELA}").fetchone()[0]


def main() -> None:
    with duckdb.connect(str(WAREHOUSE)) as con:
        linhas = construir(con)
        resumo = con.execute(f"""
            select min(mes), max(mes), round(avg({ALVO}), 4),
                   round(avg((voos_rota_hora_12m > 0)::int), 4)
            from {TABELA}
        """).fetchone()
    print(f"{TABELA}: {linhas:,} voos de {resumo[0]} a {resumo[1]}.")
    print(f"Taxa de atraso (alvo): {resumo[2]:.2%}.")
    print(f"Voos com histórico da rota x hora nos 12 meses: {resumo[3]:.2%}.")


if __name__ == "__main__":
    main()
