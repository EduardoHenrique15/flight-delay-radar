"""Carga das tabelas de apoio: aeroportos (OurAirports) e feriados nacionais (biblioteca holidays).

O arquivo de aeroportos é público (domínio público) e baixado à mão uma vez:
    https://davidmegginson.github.io/ourairports-data/airports.csv
e fica em data/raw/referencia/airports.csv, fora do git. As duas tabelas são recriadas a cada
execução: são pequenas e a carga leva menos de um segundo.

Uso: python -m fdr.ingest.reference
"""

from datetime import date
from pathlib import Path

import duckdb
import holidays

from fdr.config import ARQUIVO_AEROPORTOS, INICIO_JANELA, URL_AEROPORTOS, WAREHOUSE

COLUNAS_AEROPORTOS = (
    "ident",
    "type",
    "name",
    "latitude_deg",
    "longitude_deg",
    "iso_country",
    "iso_region",
    "municipality",
    "icao_code",
    "iata_code",
    "gps_code",
)


class ReferenciaAusenteError(FileNotFoundError):
    """O arquivo de aeroportos não está onde o pipeline espera."""


def carregar_aeroportos(con: duckdb.DuckDBPyConnection, caminho: Path = ARQUIVO_AEROPORTOS) -> int:
    """Recria raw_airports com as colunas usadas do OurAirports e devolve o número de linhas."""
    if not caminho.exists():
        raise ReferenciaAusenteError(
            f"Não achei {caminho}. Baixe {URL_AEROPORTOS} e salve nesse caminho."
        )
    caminho_sql = caminho.resolve().as_posix().replace("'", "''")
    colunas = ", ".join(COLUNAS_AEROPORTOS)
    con.execute(f"""
        create or replace table raw_airports as
        select {colunas}
        from read_csv('{caminho_sql}', header = true, all_varchar = true)
    """)
    return con.execute("select count(*) from raw_airports").fetchone()[0]


def carregar_feriados(
    con: duckdb.DuckDBPyConnection, ano_inicio: int = INICIO_JANELA[0], ano_fim: int | None = None
) -> int:
    """Recria raw_feriados com os feriados nacionais do Brasil, do início da janela até o ano
    seguinte ao atual (para cobrir previsões de voos futuros)."""
    ano_fim = ano_fim or date.today().year + 1
    feriados = holidays.Brazil(years=range(ano_inicio, ano_fim + 1), language="pt_BR")
    con.execute("create or replace table raw_feriados (data date, nome varchar)")
    con.executemany("insert into raw_feriados values (?, ?)", sorted(feriados.items()))
    return len(feriados)


def carregar_referencias(con: duckdb.DuckDBPyConnection) -> dict[str, int]:
    return {"aeroportos": carregar_aeroportos(con), "feriados": carregar_feriados(con)}


def main() -> None:
    WAREHOUSE.parent.mkdir(parents=True, exist_ok=True)
    with duckdb.connect(str(WAREHOUSE)) as con:
        for tabela, linhas in carregar_referencias(con).items():
            print(f"{tabela:<11} {linhas:>7,} linhas")


if __name__ == "__main__":
    main()
