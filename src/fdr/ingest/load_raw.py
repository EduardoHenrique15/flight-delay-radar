"""Carga dos CSVs mensais do VRA no DuckDB (tabela raw_vra), sem transformar os valores.

A carga é idempotente: cada arquivo substitui a carga anterior do mesmo arquivo. Como a ANAC
regera a série inteira a cada publicação (docs/dados.md, seção 4.1), o hash de cada arquivo fica
registrado em raw_vra_cargas, e um arquivo só é recarregado quando o conteúdo muda.

Uso: python -m fdr.ingest.load_raw [--pasta data/raw/vra] [--banco data/warehouse.duckdb] [--forcar]
"""

import argparse
import hashlib
import re
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

import duckdb

from fdr.config import COLUNAS_VRA, INICIO_JANELA, PASTA_RAW_VRA, WAREHOUSE

PADRAO_NOME = re.compile(r"^VRA_(\d{4})(\d{1,2})\.csv$", re.IGNORECASE)
PADRAO_ATUALIZADO = re.compile(r"^Atualizado em: (\d{4}-\d{2}-\d{2})$")
BOM_UTF8 = b"\xef\xbb\xbf"


class FormatoInvalidoError(ValueError):
    """O arquivo não segue o formato do VRA descrito em docs/dados.md."""


@dataclass(frozen=True)
class ArquivoVRA:
    """Metadados de um CSV mensal do VRA, lidos sem carregar os dados."""

    caminho: Path
    ano: int
    mes: int
    atualizado_em: date
    sha256: str
    linhas: int


def mes_do_arquivo(nome: str) -> tuple[int, int]:
    """Extrai (ano, mês) do nome do arquivo. Ex.: VRA_20221.csv -> (2022, 1)."""
    achado = PADRAO_NOME.match(nome)
    if not achado:
        raise FormatoInvalidoError(f"Nome fora do padrão VRA_<ano><mês>.csv: {nome}")
    ano, mes = int(achado.group(1)), int(achado.group(2))
    if not 1 <= mes <= 12:
        raise FormatoInvalidoError(f"Mês inválido no nome do arquivo: {nome}")
    return ano, mes


def inspecionar(caminho: Path) -> ArquivoVRA:
    """Confere o formato do arquivo (BOM, linha de metadado e cabeçalho) e calcula o hash."""
    ano, mes = mes_do_arquivo(caminho.name)
    bruto = caminho.read_bytes()
    if not bruto.startswith(BOM_UTF8):
        raise FormatoInvalidoError(f"{caminho.name}: esperava UTF-8 com BOM.")

    linhas = bruto[len(BOM_UTF8) :].decode("utf-8").splitlines()
    if len(linhas) < 2:
        raise FormatoInvalidoError(f"{caminho.name}: arquivo sem cabeçalho.")

    achado = PADRAO_ATUALIZADO.match(linhas[0].strip())
    if not achado:
        raise FormatoInvalidoError(
            f"{caminho.name}: a linha 1 deveria ser 'Atualizado em: AAAA-MM-DD', "
            f"mas é {linhas[0][:60]!r}."
        )

    cabecalho = tuple(c.strip().strip('"') for c in linhas[1].split(";"))
    if cabecalho != COLUNAS_VRA:
        raise FormatoInvalidoError(
            f"{caminho.name}: cabeçalho diferente do esperado. "
            f"Esperado {list(COLUNAS_VRA)}, encontrado {list(cabecalho)}."
        )

    return ArquivoVRA(
        caminho=caminho,
        ano=ano,
        mes=mes,
        atualizado_em=date.fromisoformat(achado.group(1)),
        sha256=hashlib.sha256(bruto).hexdigest(),
        linhas=sum(1 for linha in linhas[2:] if linha.strip()),
    )


def preparar_tabelas(con: duckdb.DuckDBPyConnection) -> None:
    """Cria raw_vra (dados como texto, colunas originais) e raw_vra_cargas (log de cargas)."""
    colunas = ",\n    ".join(f'"{c}" varchar' for c in COLUNAS_VRA)
    con.execute(f"""
        create table if not exists raw_vra (
            arquivo_origem varchar not null,
            {colunas},
            carregado_em timestamp not null
        )
    """)
    con.execute("""
        create table if not exists raw_vra_cargas (
            arquivo_origem varchar primary key,
            ano integer not null,
            mes integer not null,
            atualizado_em date not null,
            sha256 varchar not null,
            linhas bigint not null,
            carregado_em timestamp not null
        )
    """)


def carregar_arquivo(
    con: duckdb.DuckDBPyConnection, caminho: Path, forcar: bool = False
) -> int | None:
    """Carrega um arquivo e devolve o número de linhas, ou None se o conteúdo não mudou."""
    info = inspecionar(caminho)
    preparar_tabelas(con)

    anterior = con.execute(
        "select sha256 from raw_vra_cargas where arquivo_origem = ?", [caminho.name]
    ).fetchone()
    if anterior and anterior[0] == info.sha256 and not forcar:
        return None

    agora = datetime.now()
    caminho_sql = caminho.resolve().as_posix().replace("'", "''")
    con.begin()
    try:
        con.execute("delete from raw_vra where arquivo_origem = ?", [caminho.name])
        con.execute(
            f"""
            insert into raw_vra
            select ?, *, ?
            from read_csv('{caminho_sql}', skip = 1, header = true, delim = ';',
                          quote = '"', all_varchar = true)
            """,
            [caminho.name, agora],
        )
        carregadas = con.execute(
            "select count(*) from raw_vra where arquivo_origem = ?", [caminho.name]
        ).fetchone()[0]
        if carregadas != info.linhas:
            raise FormatoInvalidoError(
                f"{caminho.name}: o arquivo tem {info.linhas} linhas de dados, "
                f"mas a leitura trouxe {carregadas}."
            )
        con.execute("delete from raw_vra_cargas where arquivo_origem = ?", [caminho.name])
        con.execute(
            "insert into raw_vra_cargas values (?, ?, ?, ?, ?, ?, ?)",
            [caminho.name, info.ano, info.mes, info.atualizado_em, info.sha256, carregadas, agora],
        )
        con.commit()
    except Exception:
        con.rollback()
        raise
    return carregadas


def fora_da_janela(pasta: Path, inicio: tuple[int, int] = INICIO_JANELA) -> list[str]:
    """Arquivos da pasta anteriores ao início da janela de dados (ADR 001): não são carregados."""
    return sorted(
        (arq.name for arq in pasta.glob("VRA_*.csv") if mes_do_arquivo(arq.name) < inicio),
        key=mes_do_arquivo,
    )


def carregar_pasta(
    con: duckdb.DuckDBPyConnection,
    pasta: Path,
    forcar: bool = False,
    inicio: tuple[int, int] = INICIO_JANELA,
) -> dict[str, int | None]:
    """Carrega os VRA_*.csv da pasta a partir de `inicio`, em ordem cronológica. Arquivos mais
    antigos são ignorados, e o que deles tiver ficado de cargas anteriores sai do banco."""
    preparar_tabelas(con)
    antigos = fora_da_janela(pasta, inicio)
    carregados_antes = [
        nome for (nome,) in con.execute("select arquivo_origem from raw_vra_cargas").fetchall()
    ]
    for nome in carregados_antes:
        if mes_do_arquivo(nome) < inicio:
            con.execute("delete from raw_vra where arquivo_origem = ?", [nome])
            con.execute("delete from raw_vra_cargas where arquivo_origem = ?", [nome])
    arquivos = sorted(
        (arq for arq in pasta.glob("VRA_*.csv") if arq.name not in antigos),
        key=lambda p: mes_do_arquivo(p.name),
    )
    return {arq.name: carregar_arquivo(con, arq, forcar) for arq in arquivos}


def main() -> None:
    parser = argparse.ArgumentParser(description="Carrega os CSVs do VRA no DuckDB.")
    parser.add_argument("--pasta", type=Path, default=PASTA_RAW_VRA)
    parser.add_argument("--banco", type=Path, default=WAREHOUSE)
    parser.add_argument("--forcar", action="store_true", help="recarrega mesmo sem mudança")
    args = parser.parse_args()

    args.banco.parent.mkdir(parents=True, exist_ok=True)
    for nome in fora_da_janela(args.pasta):
        print(f"{nome:<16} ignorado (antes do início da janela de dados)")
    with duckdb.connect(str(args.banco)) as con:
        resultado = carregar_pasta(con, args.pasta, args.forcar)
        for nome, linhas in resultado.items():
            situacao = "sem mudanças" if linhas is None else f"{linhas:>7,} linhas carregadas"
            print(f"{nome:<16} {situacao}")
        total = con.execute("select count(*) from raw_vra").fetchone()[0]
    print(f"Total em raw_vra: {total:,} linhas ({len(resultado)} arquivos).")


if __name__ == "__main__":
    main()
