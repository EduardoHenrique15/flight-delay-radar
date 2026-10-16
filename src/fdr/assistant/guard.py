"""Travas do SQL gerado pelo modelo (PROJETO.md, seção 8.2). Duas camadas independentes:

1. Análise do SQL com o sqlglot, antes de executar: uma instrução só, só SELECT/WITH, só as
   tabelas permitidas, nenhuma função de arquivo ou rede, nada de ATTACH/COPY/INSTALL/LOAD/
   PRAGMA/SET, e LIMIT de no máximo 1000.
2. A conexão: somente leitura, sem acesso externo (`enable_external_access = false` impede
   ler arquivos e URLs mesmo que algo passe pela primeira camada), configuração travada e tempo
   máximo de 10 s.
"""

import re
import threading
from pathlib import Path

import duckdb
import pandas as pd
import sqlglot
from sqlglot import exp

LIMITE_LINHAS = 1000
TEMPO_MAXIMO_S = 10.0

# Funções que leem arquivos, rede ou o ambiente. Bloqueadas pelo nome, em qualquer lugar.
PADRAO_FUNCAO_PROIBIDA = re.compile(
    r"^(read_|parquet_|csv_|json_|sniff_|glob$|query$|query_table|getenv|current_setting|"
    r"duckdb_|pragma_|load|install|httpfs|iceberg|delta_scan|sqlite_|postgres_|mysql_)",
    re.IGNORECASE,
)
TIPOS_PROIBIDOS = (
    exp.Insert,
    exp.Update,
    exp.Delete,
    exp.Merge,
    exp.Drop,
    exp.Create,
    exp.Alter,
    exp.Command,
    exp.Copy,
    exp.Set,
    exp.Pragma,
    exp.Attach,
    exp.Detach,
    exp.Use,
    exp.Transaction,
)


class SQLBloqueado(ValueError):
    """O SQL não passou pelas travas. A mensagem diz o motivo, em português."""


def _nome_funcao(no: exp.Expression) -> str:
    if isinstance(no, exp.Anonymous):
        return str(no.this)
    return no.sql_name() if hasattr(no, "sql_name") else type(no).__name__


def validar(sql: str, tabelas_permitidas: set[str]) -> str:
    """Devolve o SQL aprovado (com LIMIT) ou levanta SQLBloqueado."""
    try:
        instrucoes = [i for i in sqlglot.parse(sql, read="duckdb") if i is not None]
    except sqlglot.errors.ParseError as erro:
        raise SQLBloqueado(f"SQL inválido: {erro}") from erro
    if len(instrucoes) != 1:
        raise SQLBloqueado("Só é permitida uma instrução por consulta.")
    arvore = instrucoes[0]
    if not isinstance(arvore, exp.Query):
        raise SQLBloqueado("Só consultas SELECT (ou WITH ... SELECT) são permitidas.")

    for no in arvore.walk():
        if isinstance(no, TIPOS_PROIBIDOS):
            raise SQLBloqueado(f"Comando não permitido: {type(no).__name__.upper()}.")
        if isinstance(no, exp.Func) and PADRAO_FUNCAO_PROIBIDA.match(_nome_funcao(no)):
            raise SQLBloqueado(f"Função não permitida: {_nome_funcao(no)}.")

    ctes = {cte.alias_or_name.lower() for cte in arvore.find_all(exp.CTE)}
    for tabela in arvore.find_all(exp.Table):
        if not isinstance(tabela.this, exp.Identifier):
            raise SQLBloqueado("Só tabelas pelo nome são permitidas no FROM.")
        if tabela.args.get("db") or tabela.args.get("catalog"):
            raise SQLBloqueado("Tabelas de outros bancos não são permitidas.")
        nome = tabela.name.lower()
        if nome not in tabelas_permitidas and nome not in ctes:
            raise SQLBloqueado(f"Tabela não permitida: {tabela.name}.")

    limite = arvore.args.get("limit")
    if limite is None:
        arvore = arvore.limit(LIMITE_LINHAS)
    else:
        valor = limite.expression
        if not isinstance(valor, exp.Literal) or not valor.is_int:
            raise SQLBloqueado("O LIMIT precisa ser um número inteiro.")
        if int(valor.this) > LIMITE_LINHAS:
            arvore = arvore.limit(LIMITE_LINHAS)
    return arvore.sql(dialect="duckdb")


def conectar(banco: Path) -> duckdb.DuckDBPyConnection:
    """Conexão somente leitura, sem acesso a arquivos ou rede e com a configuração travada."""
    con = duckdb.connect(str(banco), read_only=True, config={"enable_external_access": False})
    # Conexões ao mesmo arquivo no mesmo processo dividem a configuração: travar uma vez basta.
    if not con.execute("select current_setting('lock_configuration')").fetchone()[0]:
        con.execute("SET lock_configuration = true")
    return con


def executar(
    con: duckdb.DuckDBPyConnection, sql: str, tempo_maximo_s: float = TEMPO_MAXIMO_S
) -> pd.DataFrame:
    """Executa com tempo máximo: passado o limite, a consulta é interrompida."""
    relogio = threading.Timer(tempo_maximo_s, con.interrupt)
    relogio.start()
    try:
        return con.execute(sql).df()
    except duckdb.InterruptException as erro:
        raise SQLBloqueado(
            f"A consulta passou de {tempo_maximo_s:.0f} s e foi interrompida."
        ) from erro
    finally:
        relogio.cancel()
