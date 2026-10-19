"""Dados do app Streamlit, sem depender do Streamlit: dá para testar e
reaproveitar fora do app.

O app lê só o que vai para o deploy:
- data/marts/*.parquet (24 meses), consultados com DuckDB sob demanda, sem carregar a base
  inteira no pandas (o Streamlit Cloud tem cerca de 1 GB de memória);
- data/marts/previsao/ (tabelas da previsão, fdr.previsao);
- models/*.json e monitoring/history.json.

O banco do assistente (data/app.duckdb) não é versionado: `garantir_banco_app` o recria a partir
dos Parquet quando falta ou quando os Parquet são mais novos.

Os caminhos são lidos de fdr.config na hora da chamada, para os testes poderem trocá-los.
"""

import json
import re
from datetime import date
from pathlib import Path

import duckdb
import pandas as pd

from fdr import config
from fdr.export import CONSULTAS, gerar_banco_app

TABELAS = tuple(CONSULTAS)
# Base das taxas de atraso do app: voos nacionais realizados com horário (a mesma convenção do
# assistente: atrasados_15 / realizados_com_horario).
BASE = "tipo_linha = 'N' and atrasado_15 is not null"
MIN_VOOS_DESTAQUE = 1000  # companhia e aeroporto do mês na página inicial
MIN_VOOS_RANKING = 300  # companhias no ranking da página de pontualidade
DIAS_SEMANA = ("seg", "ter", "qua", "qui", "sex", "sáb", "dom")
MESES_PT = ("jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez")


def _sql_path(caminho: Path) -> str:
    return caminho.resolve().as_posix().replace("'", "''")


def conectar_marts(pasta: Path | None = None) -> duckdb.DuckDBPyConnection:
    """DuckDB em memória com uma view para cada Parquet de data/marts/."""
    pasta = pasta or config.PASTA_MARTS
    con = duckdb.connect()
    for nome in TABELAS:
        arquivo = _sql_path(pasta / f"{nome}.parquet")
        con.execute(f"create view {nome} as select * from read_parquet('{arquivo}')")
    return con


def garantir_banco_app(pasta: Path | None = None, banco: Path | None = None) -> Path:
    """Recria o banco do assistente se ele não existe ou é mais velho que os Parquet."""
    pasta = pasta or config.PASTA_MARTS
    banco = banco or config.BANCO_APP
    mais_novo = max((pasta / f"{nome}.parquet").stat().st_mtime for nome in TABELAS)
    if not banco.exists() or banco.stat().st_mtime < mais_novo:
        banco.parent.mkdir(parents=True, exist_ok=True)
        gerar_banco_app(pasta, banco, list(TABELAS))
    return banco


def ler_json(caminho: Path) -> dict:
    return json.loads(caminho.read_text(encoding="utf-8"))


def manifest(pasta: Path | None = None) -> dict:
    return ler_json((pasta or config.PASTA_MARTS) / "manifest.json")


def nome_mes(mes: date) -> str:
    return f"{MESES_PT[mes.month - 1]}/{mes.year}"


def mes_curto(mes: date) -> str:
    """Ex.: "ago/26" (eixos dos gráficos)."""
    return f"{MESES_PT[mes.month - 1]}/{mes.year % 100:02d}"


def porcentagem(valor: float | None, casas: int = 1) -> str:
    if valor is None or pd.isna(valor):
        return "—"
    return f"{valor:.{casas}%}".replace(".", ",")


def decimal(valor: float, casas: int = 3, sinal: bool = False) -> str:
    return f"{valor:{'+' if sinal else ''}.{casas}f}".replace(".", ",")


def numero(valor: float) -> str:
    return f"{valor:,.0f}".replace(",", ".")


# Página inicial ---------------------------------------------------------------------------------


def resumo_ultimo_mes(con: duckdb.DuckDBPyConnection) -> dict:
    """Os números do último mês publicado: voos, taxa de atraso, companhia mais pontual e
    aeroporto com mais atraso (com pelo menos MIN_VOOS_DESTAQUE voos)."""
    mes = con.execute("select max(mes) from voos").fetchone()[0]
    voos, taxa = con.execute(
        f"select count(*) filter (where situacao = 'REALIZADO' and tipo_linha = 'N'), "
        f"avg(atrasado_15::int) filter (where {BASE}) from voos where mes = ?",
        [mes],
    ).fetchone()
    cia = con.execute(
        f"""
        select coalesce(c.nome, v.cia), avg(v.atrasado_15::int) as taxa, v.cia
        from voos v left join companhias c using (cia)
        where v.mes = ? and {BASE}
        group by all having count(*) >= {MIN_VOOS_DESTAQUE}
        order by taxa limit 1
        """,
        [mes],
    ).fetchone()
    aeroporto = con.execute(
        f"""
        select coalesce(a.iata, v.origem), avg(v.atrasado_15::int) as taxa,
               coalesce(a.cidade, a.nome, v.origem), v.origem
        from voos v left join aeroportos a on a.icao = v.origem
        where v.mes = ? and {BASE}
        group by all having count(*) >= {MIN_VOOS_DESTAQUE}
        order by taxa desc limit 1
        """,
        [mes],
    ).fetchone()
    return {
        "mes": mes,
        "voos_nacionais_realizados": int(voos),
        "taxa_atraso": float(taxa) if taxa is not None else None,
        "cia_mais_pontual": cia,  # (nome, taxa, código ICAO)
        "aeroporto_mais_atraso": aeroporto,  # (código IATA, taxa, cidade, código ICAO)
    }


def impacto_do_mes(con: duckdb.DuckDBPyConnection, mes: date) -> dict:
    """Quanto os atrasos somaram no mês: voos nacionais que partiram mais de 15 minutos depois do
    previsto, as horas de atraso na partida somadas e a mediana dos minutos de atraso deles."""
    voos, minutos, mediana = con.execute(
        f"""
        select count(*), sum(atraso_partida_min), median(atraso_partida_min)
        from voos where mes = ? and {BASE} and atrasado_15
        """,
        [mes],
    ).fetchone()
    return {
        "voos_atrasados": int(voos),
        "horas": float(minutos or 0) / 60,
        "mediana_min": float(mediana) if mediana is not None else None,
    }


def serie_mensal(
    con: duckdb.DuckDBPyConnection,
    cia: str | None = None,
    origem: str | None = None,
    meses: int = 12,
) -> pd.DataFrame:
    """Os últimos meses: voos nacionais realizados e taxa de atraso (para as minilinhas e a
    variação contra o mês anterior)."""
    condicoes, parametros = ["tipo_linha = 'N'"], []
    for coluna, valor in (("cia", cia), ("origem", origem)):
        if valor:
            condicoes.append(f"{coluna} = ?")
            parametros.append(valor)
    return (
        con.execute(
            f"""
        select mes, count(*) filter (where situacao = 'REALIZADO') as voos,
               avg(atrasado_15::int) filter (where atrasado_15 is not null) as taxa_atraso
        from voos where {" and ".join(condicoes)}
        group by mes order by mes desc limit {int(meses)}
        """,
            parametros,
        )
        .df()
        .sort_values("mes", ignore_index=True)
    )


# Códigos IATA das companhias, como aparecem nos painéis dos aeroportos (G3 1032). As outras
# ficam com o código ICAO da ANAC.
CODIGOS_IATA = {"GLO": "G3", "AZU": "AD", "TAM": "LA", "ACN": "2F", "PTB": "2Z", "PAM": "7M"}


def voos_tipicos(con: duckdb.DuckDBPyConnection, mes: date, rotas: int = 8) -> pd.DataFrame:
    """As rotas mais movimentadas do mês, cada uma com a companhia, a hora e o número de voo
    mais comuns."""
    return con.execute(
        f"""
        with combinacoes as (
            select origem, destino, cia, hora_prevista as hora, count(*) as voos
            from voos where mes = ? and {BASE}
            group by all
        ),
        mais_voadas as (
            select origem, destino, sum(voos) as total from combinacoes
            group by all order by total desc limit {int(rotas)}
        ),
        escolhidas as (
            select c.origem, c.destino, c.cia, c.hora, m.total
            from combinacoes c join mais_voadas m using (origem, destino)
            qualify row_number() over (partition by c.origem, c.destino order by c.voos desc) = 1
        ),
        contagem_numeros as (
            select origem, destino, cia, hora_prevista as hora, numero_voo, count(*) as vezes
            from voos where mes = ? and {BASE}
            group by origem, destino, cia, hora_prevista, numero_voo
        ),
        numeros as (
            select * from contagem_numeros
            qualify row_number() over (
                partition by origem, destino, cia, hora order by vezes desc, numero_voo
            ) = 1
        )
        select e.*, n.numero_voo
        from escolhidas e left join numeros n using (origem, destino, cia, hora)
        order by e.hora, e.origem
        """,
        [mes, mes],
    ).df()


def rotas_com_atraso(
    con: duckdb.DuckDBPyConnection, mes: date, origem: str, minimo: int = 60, limite: int = 7
) -> pd.DataFrame:
    """As rotas que partem de um aeroporto com a maior taxa de atraso no mês (como no Misery Map
    do FlightAware: escolher um aeroporto mostra para onde os voos dele mais atrasam)."""
    return con.execute(
        f"""
        select v.destino, coalesce(a.iata, v.destino) as iata,
               coalesce(a.cidade, a.nome, v.destino) as cidade, count(*) as voos,
               avg(v.atrasado_15::int) as taxa_atraso
        from voos v left join aeroportos a on a.icao = v.destino
        where v.mes = ? and v.origem = ? and {BASE}
        group by all having count(*) >= ?
        order by taxa_atraso desc limit {int(limite)}
        """,
        [mes, origem, minimo],
    ).df()


def mapa_aeroportos(con: duckdb.DuckDBPyConnection, mes: date, minimo: int = 50) -> pd.DataFrame:
    """Partidas e taxa de atraso por aeroporto de origem no mês, com as coordenadas."""
    return con.execute(
        f"""
        select v.origem as icao, coalesce(a.iata, v.origem) as iata, a.nome, a.cidade, a.uf,
               a.latitude, a.longitude, count(*) as voos,
               avg(v.atrasado_15::int) as taxa_atraso
        from voos v join aeroportos a on a.icao = v.origem
        where v.mes = ? and {BASE} and a.latitude is not null
        group by all having count(*) >= ?
        order by voos desc
        """,
        [mes, minimo],
    ).df()


# Pontualidade -----------------------------------------------------------------------------------


def meses(con: duckdb.DuckDBPyConnection) -> list[date]:
    return [m for (m,) in con.execute("select distinct mes from voos order by mes").fetchall()]


def companhias(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """Companhias com voos nacionais na janela do app, das que mais voam para as que menos."""
    return con.execute(f"""
        select v.cia, coalesce(c.nome, v.cia) as nome, count(*) as voos
        from voos v left join companhias c using (cia)
        where {BASE}
        group by all order by voos desc
    """).df()


def aeroportos(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """Aeroportos de origem de voos nacionais, com um rótulo para os filtros."""
    return con.execute(f"""
        select v.origem as icao,
               coalesce(coalesce(a.iata, v.origem) || ' · ' || a.nome, v.origem) as rotulo,
               count(*) as voos
        from voos v left join aeroportos a on a.icao = v.origem
        where {BASE}
        group by all order by voos desc
    """).df()


def _filtro(
    inicio: date, fim: date, cia: str | None, origem: str | None, destino: str | None
) -> tuple[str, list]:
    condicoes = [BASE, "mes between ? and ?"]
    parametros: list = [inicio, fim]
    for coluna, valor in (("cia", cia), ("origem", origem), ("destino", destino)):
        if valor:
            condicoes.append(f"v.{coluna} = ?")
            parametros.append(valor)
    return " and ".join(condicoes), parametros


def ranking_companhias(con, inicio, fim, origem=None, destino=None) -> pd.DataFrame:
    filtro, parametros = _filtro(inicio, fim, None, origem, destino)
    return con.execute(
        f"""
        select v.cia, coalesce(c.nome, v.cia) as companhia, count(*) as voos,
               avg(v.atrasado_15::int) as taxa_atraso
        from voos v left join companhias c using (cia)
        where {filtro}
        group by all having count(*) >= {MIN_VOOS_RANKING}
        order by taxa_atraso
        """,
        parametros,
    ).df()


def calendario(con, inicio, fim, cia=None, origem=None, destino=None) -> pd.DataFrame:
    """Taxa de atraso dia a dia (data prevista da partida) no período."""
    filtro, parametros = _filtro(inicio, fim, cia, origem, destino)
    return con.execute(
        f"""
        select v.data_prevista as data, count(*) as voos, avg(v.atrasado_15::int) as taxa_atraso
        from voos v where {filtro}
        group by all order by data
        """,
        parametros,
    ).df()


def mapa_rotas(
    con, inicio, fim, cia=None, origem=None, destino=None, limite: int = 150, minimo: int = 30
) -> pd.DataFrame:
    """As rotas mais voadas do período (até `limite`), com as coordenadas das duas pontas e a
    taxa de atraso. Rotas com menos de `minimo` voos ficam de fora."""
    filtro, parametros = _filtro(inicio, fim, cia, origem, destino)
    return con.execute(
        f"""
        select v.origem, v.destino, o.iata as iata_origem, d.iata as iata_destino,
               o.cidade as cidade_origem, d.cidade as cidade_destino,
               o.longitude as lon_origem, o.latitude as lat_origem,
               d.longitude as lon_destino, d.latitude as lat_destino,
               count(*) as voos, avg(v.atrasado_15::int) as taxa_atraso
        from voos v
        join aeroportos o on o.icao = v.origem
        join aeroportos d on d.icao = v.destino
        where {filtro} and o.latitude is not null and d.latitude is not null
        group by all having count(*) >= {int(minimo)}
        order by voos desc limit {int(limite)}
        """,
        parametros,
    ).df()


def mapa_de_calor(con, inicio, fim, cia=None, origem=None, destino=None) -> pd.DataFrame:
    """Taxa de atraso por hora prevista e dia da semana."""
    filtro, parametros = _filtro(inicio, fim, cia, origem, destino)
    dados = con.execute(
        f"""
        select isodow(v.data_prevista) as dia, v.hora_prevista as hora, count(*) as voos,
               avg(v.atrasado_15::int) as taxa_atraso
        from voos v where {filtro}
        group by all
        """,
        parametros,
    ).df()
    dados["dia_semana"] = dados["dia"].map(lambda d: DIAS_SEMANA[int(d) - 1])
    return dados


def evolucao_mensal(con, inicio, fim, cia=None, origem=None, destino=None) -> pd.DataFrame:
    filtro, parametros = _filtro(inicio, fim, cia, origem, destino)
    return con.execute(
        f"""
        select v.mes, count(*) as voos, avg(v.atrasado_15::int) as taxa_atraso
        from voos v where {filtro}
        group by all order by v.mes
        """,
        parametros,
    ).df()


def cadastro_aeroportos(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """Todos os aeroportos, com o código IATA, a cidade e um rótulo curto para os filtros."""
    return con.execute("""
        select icao, coalesce(iata, icao) as iata, coalesce(cidade, nome, icao) as cidade, nome,
               coalesce(iata, icao) || ' · ' || coalesce(cidade, nome, icao) as rotulo
        from aeroportos
    """).df()


def destinos(con, origem: str) -> pd.DataFrame:
    return con.execute(
        f"""
        select v.destino as icao,
               coalesce(coalesce(a.iata, v.destino) || ' · ' || a.nome, v.destino) as rotulo,
               count(*) as voos
        from voos v left join aeroportos a on a.icao = v.destino
        where {BASE} and v.origem = ?
        group by all order by voos desc
        """,
        [origem],
    ).df()


# Nome de cada variável do modelo para o usuário (as que aparecem no monitoramento).
NOMES_VARIAVEIS = {
    "hora_prevista_local": "Hora do voo",
    "dia_semana": "Dia da semana",
    "mes_do_ano": "Mês do ano",
    "cia": "Companhia",
    "origem": "Aeroporto de origem",
    "destino": "Destino",
    "taxa_rota_hora_3m": "Atraso da rota no horário (3 meses)",
    "taxa_rota_hora_12m": "Atraso da rota no horário (12 meses)",
    "voos_rota_hora_3m": "Voos da rota no horário (3 meses)",
    "voos_rota_hora_12m": "Voos da rota no horário (12 meses)",
    "taxa_cia_3m": "Atraso da companhia (3 meses)",
    "taxa_cia_12m": "Atraso da companhia (12 meses)",
    "taxa_origem_3m": "Atraso do aeroporto (3 meses)",
    "taxa_origem_12m": "Atraso do aeroporto (12 meses)",
    "partidas_tipicas_origem_hora": "Movimento típico no aeroporto",
    "partidas_cia_antes_tipicas": "Voos da companhia antes no dia",
    "folga_tipica_min": "Folga da programação",
    "duracao_tipica_min": "Duração típica do voo",
    "distancia_km": "Distância",
}


# Monitoramento ----------------------------------------------------------------------------------


def historico_monitoramento(caminho: Path | None = None) -> dict:
    return ler_json(caminho or config.RAIZ / "monitoring" / "history.json")


def meses_monitorados(historico: dict) -> pd.DataFrame:
    """Uma linha por mês (simulação e produção), com as métricas do modelo e do baseline."""
    linhas = []
    for registro in historico["simulacao"]["meses"] + historico["producao"]["meses"]:
        linhas.append(
            {
                "mes": pd.Timestamp(registro["mes"]),
                "tipo": registro["tipo"],
                "voos": registro["voos"],
                "pr_auc_modelo": registro["modelo"]["pr_auc"],
                "pr_auc_baseline": registro["baseline"]["pr_auc"],
                "brier_modelo": registro["modelo"]["brier"],
                "brier_baseline": registro["baseline"]["brier"],
                "taxa_real": registro["modelo"]["taxa_real"],
                "taxa_prevista": registro["modelo"]["taxa_prevista"],
                "ece": registro["modelo"]["ece"],
                "retreino": registro["retreino"],
                "psi": registro["psi"],
            }
        )
    return pd.DataFrame(linhas)


def descrever_retreino(retreino: dict) -> str:
    """O que aconteceu com a regra de retreino no mês, em uma frase."""
    if not retreino["disparou"]:
        return "Sem retreino: nenhuma regra disparou."
    # Os motivos vêm do monitoramento com ponto decimal ("ECE de 10.3%"): no app, vírgula.
    motivos = re.sub(r"(\d)\.(\d)", r"\1,\2", "; ".join(retreino["motivos"]))
    if retreino.get("adiado"):
        return f"Regra disparou ({motivos}), mas o retreino foi adiado: {retreino['adiado']}."
    baixo, alto = retreino["ganho_pr_auc_intervalo_95"]
    ganho = (
        f"ganho de PR-AUC do desafiante: {retreino['ganho_pr_auc']:+.3f} "
        f"(IC 95%: {baixo:+.3f} a {alto:+.3f})"
    ).replace(".", ",")
    decisao = "desafiante promovido" if retreino["promovido"] else "campeão mantido"
    return f"Retreino ({motivos}): {ganho}, {decisao}."
