"""Monta a tabela de variáveis do modelo (features_voos) a partir dos marts, sem vazamento.

Regra "as-of" (docs/decisoes/003-regra-as-of.md): a ANAC publica cada mês com cerca de L = 2 meses
de atraso. Quem prevê um voo do mês M só conhece os voos até o fim do mês M - L. Por isso, as
variáveis históricas de um voo do mês M usam apenas os meses até M - L (o "mês de corte"). Os
meses M - 1 e M nunca entram, nem os seguintes. O teste tests/test_no_leakage.py prova isso.

Uma linha por voo da base do modelo: voos nacionais (tipo N), regulares (DI = 0), realizados e com
partida prevista e real. O alvo é `atrasado_15` (partida mais de 15 min atrasada).

Toda variável do modelo pode ser calculada para um voo futuro, só com a companhia, a rota, a data
e a hora previstas e o histórico publicado. Por isso a malha do próprio mês (quantas partidas o
aeroporto teve naquela hora, quanto durou cada voo programado) não entra no modelo: ela só é
publicada junto com os atrasos. No lugar dela entram as versões típicas, tiradas do histórico.

Variáveis do modelo:
- calendário: hora local prevista, dia da semana, mês, feriado, véspera, dia seguinte, férias;
- voo: companhia, origem, destino, distância da rota;
- histórico as-of (janelas de 3 e 12 meses até o corte): taxa de atraso e número de voos da
  rota x hora, da companhia, do aeroporto de origem e do país;
- sazonalidade: taxa de atraso da rota, da origem e da companhia no mesmo mês do ano anterior;
- programação típica (3 meses até o corte): partidas por dia na origem no mesmo dia da semana e
  hora, e partidas da mesma companhia na origem antes dessa hora (posição do voo no dia);
- duração típica e folga (12 meses até o corte): duração programada média da companhia na rota e
  quanto ela passa da duração real média (folga da programação).

Colunas só para análise, fora do modelo (COLUNAS_SO_ANALISE): a malha realizada do mês.

Uso: python -m fdr.features.build
"""

import duckdb

from fdr.config import DEFASAGEM_PUBLICACAO_MESES, WAREHOUSE

JANELAS_MESES = (3, 12)
JANELA_PROGRAMACAO_MESES = 3
JANELA_DURACAO_MESES = 12
TABELA = "features_voos"

# Grãos do histórico: nome -> colunas da chave (além do mês).
GRAOS = {
    "rota_hora": ("origem", "destino", "hora_prevista_local"),
    "cia": ("cia",),
    "origem": ("origem",),
    "global": (),
}

# Grãos da sazonalidade (mesmo mês do ano anterior).
GRAOS_SAZONAIS = {
    "rota": ("origem", "destino"),
    "origem": ("origem",),
    "cia": ("cia",),
}

# Colunas que nunca podem virar variável: só se sabem depois do voo (PROIBIDAS) ou só são
# publicadas junto com os atrasos do mês (COLUNAS_SO_ANALISE).
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
COLUNAS_SO_ANALISE = frozenset({"partidas_programadas_origem_hora", "duracao_prevista_min"})
ALVO = "atrasado_15"

BASE = "nacional and regular and atrasado_15 is not null"


def _criar_meses_alvo(con: duckdb.DuckDBPyConnection, defasagem: int) -> None:
    if not 1 <= defasagem <= 12:
        raise ValueError("A defasagem precisa ficar entre 1 e 12 meses.")
    con.execute(f"""
        create or replace temp table meses_alvo as
        select distinct mes as mes_alvo, mes - to_months({int(defasagem)}) as mes_corte
        from fct_flights
    """)


def _criar_historicos(con: duckdb.DuckDBPyConnection) -> None:
    """Para cada mês-alvo e cada grão, soma voos e atrasos nas janelas que terminam no corte."""
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
                where {BASE}
                group by all
            )
            select m.mes_alvo, {selecao_chave}{somas}
            from meses_alvo m
            join mensal h
              on h.mes <= m.mes_corte
             and h.mes > m.mes_corte - to_months({maior})
            group by all
        """)


def _criar_sazonais(con: duckdb.DuckDBPyConnection) -> None:
    """Taxa de atraso no mesmo mês do ano anterior (M - 12), sempre anterior ao corte."""
    for nome, chave in GRAOS_SAZONAIS.items():
        colunas = ", ".join(chave)
        con.execute(f"""
            create or replace temp table sazonal_{nome} as
            with mensal as (
                select {colunas}, mes, count(*) as voos,
                       count(*) filter (where atrasado_15) as atrasados
                from fct_flights
                where {BASE}
                group by all
            )
            select m.mes_alvo, {", ".join(f"h.{c}" for c in chave)}, h.voos, h.atrasados
            from meses_alvo m
            join mensal h on h.mes = m.mes_alvo - to_months(12)
        """)


def _criar_programacao_tipica(con: duckdb.DuckDBPyConnection) -> None:
    """Partidas regulares por dia, por origem, companhia, dia da semana e hora local, na janela
    de programação que termina no corte (inclui os voos depois cancelados: eram programados)."""
    janela = JANELA_PROGRAMACAO_MESES
    con.execute(f"""
        create or replace temp table programacao_tipica as
        with programacao as (
            select f.origem, f.cia, f.mes, d.dia_semana, f.hora_prevista_local as hora,
                   count(*) as partidas
            from fct_flights f
            join dim_date d on d.data = f.data_prevista_local
            where f.regular and f.partida_prevista is not null
            group by all
        ),
        dias as (
            select date_trunc('month', data)::date as mes, dia_semana, count(*) as dias
            from dim_date
            group by all
        ),
        dias_na_janela as (
            select m.mes_alvo, d.dia_semana, sum(d.dias) as dias
            from meses_alvo m
            join dias d
              on d.mes <= m.mes_corte and d.mes > m.mes_corte - to_months({janela})
            group by all
        )
        select m.mes_alvo, p.origem, p.cia, p.dia_semana, p.hora,
               sum(p.partidas) / any_value(j.dias) as partidas_por_dia
        from meses_alvo m
        join programacao p
          on p.mes <= m.mes_corte and p.mes > m.mes_corte - to_months({janela})
        join dias_na_janela j on j.mes_alvo = m.mes_alvo and j.dia_semana = p.dia_semana
        group by all
    """)


def _criar_duracoes(con: duckdb.DuckDBPyConnection) -> None:
    """Duração programada média e folga (programada menos real) da companhia na rota e da rota,
    nos voos realizados da janela que termina no corte. Durações reais fora de 50% a 200% da
    programada (desvios, erros de registro) ficam de fora."""
    janela = JANELA_DURACAO_MESES
    graos = {"cia_rota": ("cia", "origem", "destino"), "rota": ("origem", "destino")}
    for nome, chave in graos.items():
        colunas = ", ".join(chave)
        con.execute(f"""
            create or replace temp table duracao_{nome} as
            with mensal as (
                select {colunas}, mes, count(*) as voos,
                       sum(duracao_prevista_min) as prevista,
                       sum(date_diff('minute', partida_real, chegada_real)) as soma_real
                from fct_flights
                where nacional and regular and realizado and duracao_prevista_min > 0
                  and date_diff('minute', partida_real, chegada_real)
                      between 0.5 * duracao_prevista_min and 2 * duracao_prevista_min
                group by all
            )
            select m.mes_alvo, {", ".join(f"h.{c}" for c in chave)},
                   sum(h.prevista) / sum(h.voos) as duracao_tipica_min,
                   (sum(h.prevista) - sum(h.soma_real)) / sum(h.voos) as folga_tipica_min
            from meses_alvo m
            join mensal h
              on h.mes <= m.mes_corte and h.mes > m.mes_corte - to_months({janela})
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


def _sazonal(nome: str, apelido: str) -> str:
    return (
        f"{apelido}.atrasados / nullif({apelido}.voos, 0) as taxa_{nome}_ano_anterior,\n"
        f"            coalesce({apelido}.voos, 0)::integer as voos_{nome}_ano_anterior"
    )


def construir(con: duckdb.DuckDBPyConnection, defasagem: int = DEFASAGEM_PUBLICACAO_MESES) -> int:
    """Cria a tabela features_voos no banco e devolve o número de linhas."""
    _criar_meses_alvo(con, defasagem)
    _criar_historicos(con)
    _criar_sazonais(con)
    _criar_programacao_tipica(con)
    _criar_duracoes(con)
    con.execute(f"""
        create or replace table {TABELA} as
        with base as (
            select f.*, d.dia_semana
            from fct_flights f
            left join dim_date d on d.data = f.data_prevista_local
            where f.nacional and f.regular and f.atrasado_15 is not null
        ),

        partidas_programadas as (
            -- Malha realizada do mês: só para análise (sai junto com os atrasos do mês).
            select origem, data_prevista_local, hora_prevista_local, count(*) as partidas
            from fct_flights
            where regular and partida_prevista is not null
            group by all
        ),

        chaves_cia as (
            select distinct mes, origem, cia, dia_semana, hora_prevista_local from base
        ),

        cia_antes as (
            -- Partidas típicas da mesma companhia na origem, no mesmo dia da semana, antes da
            -- hora do voo: a posição do voo no dia da companhia (atrasos se acumulam).
            select k.mes, k.origem, k.cia, k.dia_semana, k.hora_prevista_local,
                   coalesce(sum(t.partidas_por_dia), 0) as partidas
            from chaves_cia k
            left join programacao_tipica t
              on t.mes_alvo = k.mes and t.origem = k.origem and t.cia = k.cia
             and t.dia_semana = k.dia_semana and t.hora < k.hora_prevista_local
            group by all
        ),

        origem_hora as (
            select mes_alvo, origem, dia_semana, hora, sum(partidas_por_dia) as partidas
            from programacao_tipica
            group by all
        )

        select
            f.voo_id,
            f.mes,
            f.data_prevista_local as data_prevista,
            f.atrasado_15::int as {ALVO},
            -- calendário (data e hora locais da origem)
            f.hora_prevista_local,
            f.dia_semana,
            month(f.data_prevista_local) as mes_do_ano,
            d.feriado::int as feriado,
            d.vespera_feriado::int as vespera_feriado,
            d.pos_feriado::int as pos_feriado,
            d.ferias_escolares::int as ferias_escolares,
            -- voo
            f.cia,
            f.origem,
            f.destino,
            r.distancia_km,
            -- histórico as-of
            {_taxas("rota_hora", "hr")},
            {_taxas("cia", "hc")},
            {_taxas("origem", "ho")},
            {_taxas("global", "hg")},
            -- sazonalidade: mesmo mês do ano anterior
            {_sazonal("rota", "sr")},
            {_sazonal("origem", "so")},
            {_sazonal("cia", "sc")},
            -- programação típica (as-of)
            coalesce(oh.partidas, 0) as partidas_tipicas_origem_hora,
            ca.partidas as partidas_cia_antes_tipicas,
            -- duração típica e folga da programação (as-of), da companhia na rota ou da rota
            coalesce(dc.duracao_tipica_min, dr.duracao_tipica_min) as duracao_tipica_min,
            coalesce(dc.folga_tipica_min, dr.folga_tipica_min) as folga_tipica_min,
            -- só para análise (fora do modelo)
            coalesce(p.partidas, 0) as partidas_programadas_origem_hora,
            f.duracao_prevista_min
        from base f
        left join dim_date d on d.data = f.data_prevista_local
        left join dim_routes r on r.origem = f.origem and r.destino = f.destino
        left join partidas_programadas p
          on p.origem = f.origem and p.data_prevista_local = f.data_prevista_local
         and p.hora_prevista_local = f.hora_prevista_local
        left join hist_rota_hora hr
          on hr.mes_alvo = f.mes and hr.origem = f.origem and hr.destino = f.destino
         and hr.hora_prevista_local = f.hora_prevista_local
        left join hist_cia hc on hc.mes_alvo = f.mes and hc.cia = f.cia
        left join hist_origem ho on ho.mes_alvo = f.mes and ho.origem = f.origem
        left join hist_global hg on hg.mes_alvo = f.mes
        left join sazonal_rota sr
          on sr.mes_alvo = f.mes and sr.origem = f.origem and sr.destino = f.destino
        left join sazonal_origem so on so.mes_alvo = f.mes and so.origem = f.origem
        left join sazonal_cia sc on sc.mes_alvo = f.mes and sc.cia = f.cia
        left join origem_hora oh
          on oh.mes_alvo = f.mes and oh.origem = f.origem and oh.dia_semana = f.dia_semana
         and oh.hora = f.hora_prevista_local
        left join cia_antes ca
          on ca.mes = f.mes and ca.origem = f.origem and ca.cia = f.cia
         and ca.dia_semana = f.dia_semana and ca.hora_prevista_local = f.hora_prevista_local
        left join duracao_cia_rota dc
          on dc.mes_alvo = f.mes and dc.cia = f.cia and dc.origem = f.origem
         and dc.destino = f.destino
        left join duracao_rota dr
          on dr.mes_alvo = f.mes and dr.origem = f.origem and dr.destino = f.destino
    """)
    return con.execute(f"select count(*) from {TABELA}").fetchone()[0]


def main() -> None:
    with duckdb.connect(str(WAREHOUSE)) as con:
        linhas = construir(con)
        resumo = con.execute(f"""
            select min(mes), max(mes), round(avg({ALVO}), 4),
                   round(avg((voos_rota_hora_12m > 0)::int), 4),
                   round(avg((voos_rota_ano_anterior > 0)::int), 4),
                   round(avg((duracao_tipica_min is not null)::int), 4)
            from {TABELA}
        """).fetchone()
    print(f"{TABELA}: {linhas:,} voos de {resumo[0]} a {resumo[1]}.")
    print(f"Taxa de atraso (alvo): {resumo[2]:.2%}.")
    print(f"Voos com histórico da rota x hora nos 12 meses: {resumo[3]:.2%}.")
    print(f"Voos com a rota no mesmo mês do ano anterior: {resumo[4]:.2%}.")
    print(f"Voos com duração típica da rota: {resumo[5]:.2%}.")


if __name__ == "__main__":
    main()
