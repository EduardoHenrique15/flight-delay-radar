"""Descrição das tabelas que o assistente pode consultar (data/app.duckdb), para o prompt.

Os nomes, os tipos e os exemplos de valores vêm do próprio banco; o significado de cada coluna
está aqui, em português. Só estas tabelas passam pelas travas (guard.py).
"""

import duckdb

TABELAS = {
    "voos": {
        "descricao": (
            "Um voo por linha, nos últimos 24 meses publicados pela ANAC (VRA). Inclui voos "
            "nacionais e internacionais, regulares e extras, realizados e cancelados."
        ),
        "colunas": {
            "mes": "mês de referência do arquivo da ANAC (sempre o dia 1)",
            "data_prevista": "data prevista de partida, no fuso do aeroporto de origem",
            "cia": "código ICAO da companhia (ex.: AZU = Azul, GLO = Gol, TAM = LATAM)",
            "numero_voo": "número do voo, como texto",
            "tipo_linha": "N = nacional, I = internacional, C = fretamento/complementar, "
            "G = cargueiro",
            "regular": "verdadeiro para voo regular (autorização DI = 0)",
            "origem": "código ICAO do aeroporto de origem (ex.: SBGR = Guarulhos)",
            "destino": "código ICAO do aeroporto de destino",
            "hora_prevista": "hora local prevista da partida, de 0 a 23",
            "duracao_prevista_min": "duração programada do voo, em minutos",
            "situacao": "REALIZADO, CANCELADO ou NÃO INFORMADO",
            "atraso_partida_min": "minutos de atraso na partida (negativo = adiantado; vazio "
            "se o voo não foi realizado)",
            "atraso_chegada_min": "minutos de atraso na chegada",
            "atrasado_15": "verdadeiro se partiu mais de 15 min atrasado (vazio se não realizado)",
            "atrasado_30": "verdadeiro se partiu mais de 30 min atrasado",
            "atrasado_60": "verdadeiro se partiu mais de 60 min atrasado",
        },
    },
    "pontualidade_mensal": {
        "descricao": "Pontualidade e cancelamentos por mês, companhia, aeroporto de origem e tipo "
        "de linha, nos últimos 24 meses.",
        "colunas": {
            "mes": "mês (dia 1)",
            "cia": "código ICAO da companhia",
            "origem": "código ICAO do aeroporto de origem",
            "tipo_linha": "N, I, C ou G (ver a tabela voos)",
            "voos": "voos programados",
            "realizados": "voos realizados",
            "realizados_com_horario": "realizados com horário real registrado (base da taxa)",
            "atrasados_15": "partidas com mais de 15 min de atraso",
            "atrasados_30": "partidas com mais de 30 min de atraso",
            "atrasados_60": "partidas com mais de 60 min de atraso",
            "cancelados": "voos cancelados",
            "taxa_atraso_15": "atrasados_15 / realizados_com_horario (fração de 0 a 1)",
            "taxa_cancelamento": "cancelados / voos (fração de 0 a 1)",
        },
    },
    "atraso_rota_hora": {
        "descricao": "Voos e atrasos por mês, rota e hora prevista, só voos nacionais regulares "
        "realizados (a base do modelo de previsão).",
        "colunas": {
            "mes": "mês (dia 1)",
            "origem": "código ICAO da origem",
            "destino": "código ICAO do destino",
            "hora_prevista": "hora local prevista da partida, de 0 a 23",
            "voos": "voos realizados",
            "atrasados_15": "partidas com mais de 15 min de atraso",
        },
    },
    "aeroportos": {
        "descricao": "Um aeroporto por código ICAO, com nome, cidade, UF e coordenadas.",
        "colunas": {
            "icao": "código ICAO (ex.: SBGR)",
            "iata": "código IATA (ex.: GRU)",
            "nome": "nome do aeroporto",
            "cidade": "cidade",
            "uf": "sigla do estado (só no Brasil)",
            "pais": "código do país (BR = Brasil)",
            "latitude": "latitude em graus",
            "longitude": "longitude em graus",
            "fuso_iana": "fuso horário (ex.: America/Sao_Paulo)",
            "diferenca_brasilia_h": "horas a somar ao horário de Brasília para chegar à hora local",
        },
    },
    "companhias": {
        "descricao": "Uma companhia por código ICAO, com o nome (quando conhecido).",
        "colunas": {
            "cia": "código ICAO",
            "nome": "nome da companhia (ou o código, se desconhecido)",
            "nome_conhecido": "verdadeiro se o nome foi conferido",
            "brasileira": "verdadeiro para companhia brasileira",
            "voos": "voos na série inteira (desde jan/2022)",
            "voos_nacionais": "voos nacionais na série inteira",
        },
    },
    "rotas": {
        "descricao": "Um par origem-destino por linha, com a distância em linha reta.",
        "colunas": {
            "origem": "código ICAO da origem",
            "destino": "código ICAO do destino",
            "voos": "voos na série inteira",
            "domestica": "verdadeiro se origem e destino ficam no Brasil",
            "distancia_km": "distância em linha reta, em km",
        },
    },
}

# Pares pergunta -> SQL que mostram ao modelo as convenções do projeto (few-shot).
EXEMPLOS = [
    {
        "pergunta": "Qual a taxa de atraso da Gol em julho de 2026?",
        "sql": (
            "SELECT sum(atrasados_15) / sum(realizados_com_horario) AS taxa_atraso\n"
            "FROM pontualidade_mensal\n"
            "WHERE cia = 'GLO' AND tipo_linha = 'N' AND mes = DATE '2026-07-01'"
        ),
    },
    {
        "pergunta": "Quais os 5 aeroportos com mais partidas no último mês?",
        "sql": (
            "SELECT a.nome, a.cidade, sum(p.voos) AS partidas\n"
            "FROM pontualidade_mensal p JOIN aeroportos a ON a.icao = p.origem\n"
            "WHERE p.mes = (SELECT max(mes) FROM pontualidade_mensal)\n"
            "GROUP BY a.nome, a.cidade ORDER BY partidas DESC LIMIT 5"
        ),
    },
    {
        "pergunta": "Em que hora do dia os voos de Congonhas para o Santos Dumont mais atrasam?",
        "sql": (
            "SELECT hora_prevista, sum(atrasados_15) / sum(voos) AS taxa_atraso,\n"
            "       sum(voos) AS voos\n"
            "FROM atraso_rota_hora\n"
            "WHERE origem = 'SBSP' AND destino = 'SBRJ'\n"
            "GROUP BY hora_prevista HAVING sum(voos) >= 30 ORDER BY taxa_atraso DESC LIMIT 5"
        ),
    },
    {
        "pergunta": "Quantos voos foram cancelados por mês em 2026?",
        "sql": (
            "SELECT mes, sum(cancelados) AS cancelados\n"
            "FROM pontualidade_mensal WHERE year(mes) = 2026\n"
            "GROUP BY mes ORDER BY mes"
        ),
    },
    {
        "pergunta": "Qual foi o maior atraso registrado num voo da Azul saindo de Viracopos?",
        "sql": (
            "SELECT data_prevista, numero_voo, destino, atraso_partida_min\n"
            "FROM voos WHERE cia = 'AZU' AND origem = 'SBKP' AND situacao = 'REALIZADO'\n"
            "ORDER BY atraso_partida_min DESC LIMIT 1"
        ),
    },
]

REGRAS = """Regras:
- Responda só com dados das tabelas abaixo, em SQL do DuckDB.
- Uma única instrução SELECT (pode usar WITH). Nunca altere dados.
- Use os códigos ICAO das companhias e aeroportos (consulte companhias e aeroportos pelo nome).
- "Taxa de atraso" é atrasados_15 / realizados_com_horario (pontualidade_mensal) ou
  atrasados_15 / voos (atraso_rota_hora). Sem outra indicação, use voos nacionais
  (tipo_linha = 'N').
- Datas: mes é sempre o dia 1 do mês (DATE 'AAAA-MM-01').
- Limite os resultados (LIMIT) a no máximo 50 linhas, a menos que a pergunta peça um total.
- Se a pergunta não puder ser respondida com estas tabelas (preço, clima, motivo do atraso,
  nome de passageiro, futuro), devolva pode_responder = false e explique o que falta."""


def descrever(con: duckdb.DuckDBPyConnection) -> str:
    """Texto com as tabelas, tipos, significado e exemplos de valores, para o prompt."""
    partes = []
    for tabela, info in TABELAS.items():
        tipos = dict(
            con.execute(f"select column_name, column_type from (describe {tabela})").fetchall()
        )
        linhas = [f"Tabela {tabela}: {info['descricao']}"]
        for coluna, significado in info["colunas"].items():
            exemplo = _exemplos(con, tabela, coluna, tipos.get(coluna, ""))
            linhas.append(f"  - {coluna} ({tipos.get(coluna, '?')}): {significado}{exemplo}")
        partes.append("\n".join(linhas))
    periodo = con.execute("select min(mes), max(mes) from voos").fetchone()
    cabecalho = f"Período disponível: {periodo[0]:%m/%Y} a {periodo[1]:%m/%Y}."
    return cabecalho + "\n\n" + "\n\n".join(partes)


def _exemplos(con: duckdb.DuckDBPyConnection, tabela: str, coluna: str, tipo: str) -> str:
    if tipo != "VARCHAR" or coluna in {"nome", "cidade", "numero_voo", "fuso_iana"}:
        return ""
    valores = con.execute(
        f"select {coluna}, count(*) from {tabela} where {coluna} is not null "
        f"group by 1 order by 2 desc limit 5"
    ).fetchall()
    return f" (exemplos: {', '.join(str(v) for v, _ in valores)})" if valores else ""


def montar_prompt_sistema(con: duckdb.DuckDBPyConnection) -> str:
    exemplos = "\n\n".join(f"Pergunta: {e['pergunta']}\nSQL:\n{e['sql']}" for e in EXEMPLOS)
    return (
        "Você é o assistente de dados do Flight Delay Radar. Converte perguntas em português "
        "sobre voos no Brasil em SQL do DuckDB.\n\n"
        f"{REGRAS}\n\n{descrever(con)}\n\nExemplos:\n\n{exemplos}"
    )
