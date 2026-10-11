"""Exporta os marts para o app: Parquet em data/marts/ e o banco do assistente em data/app.duckdb.

Só os últimos meses publicados vão para o deploy (PROJETO.md, seção 3.3), e a tabela de voos vai
enxuta: sem o hash do voo, sem colunas sempre vazias e com tipos menores. Com isso, 24 meses
ficam em cerca de 9 MB, longe do limite de 50 MB por arquivo do GitHub.

Uso: python -m fdr.export [--meses 24]
"""

import argparse
import json
from datetime import datetime
from pathlib import Path

import duckdb

from fdr.config import BANCO_APP, MESES_DEPLOY, PASTA_MARTS, TAMANHO_MAX_ARQUIVO_MB, WAREHOUSE

# Nome no app -> (consulta sobre o warehouse, ordem). As tabelas com a coluna "mes" são
# recortadas na janela do deploy; as dimensões vão inteiras (são pequenas).
CONSULTAS = {
    "voos": (
        """
        select
            mes,
            data_prevista,
            cia,
            numero_voo,
            tipo_linha,
            regular,
            origem,
            destino,
            cast(hora_prevista_local as tinyint) as hora_prevista,
            cast(duracao_prevista_min as smallint) as duracao_prevista_min,
            situacao,
            cast(atraso_partida_min as smallint) as atraso_partida_min,
            cast(atraso_chegada_min as smallint) as atraso_chegada_min,
            atrasado_15,
            atrasado_30,
            atrasado_60
        from fct_flights
        """,
        "mes, cia, origem, destino, data_prevista",
    ),
    "pontualidade_mensal": (
        "select * from agg_punctuality_monthly",
        "mes, cia, origem, tipo_linha",
    ),
    "atraso_rota_hora": ("select * from agg_route_hour", "mes, origem, destino, hora_prevista"),
    "aeroportos": ("select * exclude (encontrado_no_ourairports) from dim_airports", "icao"),
    "companhias": ("select * from dim_airlines", "cia"),
    "rotas": ("select * from dim_routes", "origem, destino"),
}


class ExportacaoError(RuntimeError):
    """A exportação produziu algo que não pode ir para o repositório."""


def exportar(
    warehouse: Path = WAREHOUSE,
    pasta_marts: Path = PASTA_MARTS,
    banco_app: Path = BANCO_APP,
    meses: int = MESES_DEPLOY,
) -> dict:
    """Gera os Parquet, o banco do assistente e um manifest.json; devolve o manifest."""
    pasta_marts.mkdir(parents=True, exist_ok=True)
    with duckdb.connect(str(warehouse), read_only=True) as con:
        ultimo_mes = con.execute("select max(mes) from fct_flights").fetchone()[0]
        if ultimo_mes is None:
            raise ExportacaoError("fct_flights está vazia: rode a carga e o dbt antes de exportar.")
        primeiro_mes = con.execute(
            "select cast(? - to_months(?) as date)", [ultimo_mes, meses - 1]
        ).fetchone()[0]

        tabelas = {}
        for nome, (consulta, ordem) in CONSULTAS.items():
            destino = pasta_marts / f"{nome}.parquet"
            colunas = [c[0] for c in con.execute(f"describe {consulta}").fetchall()]
            filtro = (
                f"where mes between '{primeiro_mes}' and '{ultimo_mes}'" if "mes" in colunas else ""
            )
            recorte = f"select * from ({consulta}) {filtro} order by {ordem}"
            con.execute(
                f"copy ({recorte}) to '{_sql_path(destino)}' "
                "(format parquet, compression zstd, compression_level 9)"
            )
            linhas = con.execute(f"select count(*) from ({recorte})").fetchone()[0]
            tabelas[nome] = {"arquivo": destino.name, "linhas": linhas}

    _gerar_banco_app(pasta_marts, banco_app, list(CONSULTAS))

    manifest = {
        "gerado_em": datetime.now().isoformat(timespec="seconds"),
        "primeiro_mes": primeiro_mes.isoformat(),
        "ultimo_mes": ultimo_mes.isoformat(),
        "meses": meses,
        "tabelas": tabelas,
    }
    _verificar_tamanhos([pasta_marts / t["arquivo"] for t in tabelas.values()] + [banco_app])
    (pasta_marts / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return manifest


def _gerar_banco_app(pasta_marts: Path, banco_app: Path, nomes: list[str]) -> None:
    """Recria o banco do assistente só com as tabelas exportadas (PROJETO.md, seção 8.2)."""
    banco_app.unlink(missing_ok=True)
    with duckdb.connect(str(banco_app)) as app:
        for nome in nomes:
            origem = _sql_path(pasta_marts / f"{nome}.parquet")
            app.execute(f"create table {nome} as select * from read_parquet('{origem}')")
        app.execute("checkpoint")


def _verificar_tamanhos(arquivos: list[Path]) -> None:
    grandes = [
        f"{a.name} ({a.stat().st_size / 1e6:.1f} MB)"
        for a in arquivos
        if a.stat().st_size > TAMANHO_MAX_ARQUIVO_MB * 1e6
    ]
    if grandes:
        raise ExportacaoError(
            f"Arquivos acima de {TAMANHO_MAX_ARQUIVO_MB} MB: {', '.join(grandes)}. "
            "Reduza a janela (--meses) ou agregue mais antes de versionar."
        )


def _sql_path(caminho: Path) -> str:
    return caminho.resolve().as_posix().replace("'", "''")


def main() -> None:
    parser = argparse.ArgumentParser(description="Exporta os marts para o app.")
    parser.add_argument("--meses", type=int, default=MESES_DEPLOY)
    args = parser.parse_args()
    manifest = exportar(meses=args.meses)
    print(f"Exportado de {manifest['primeiro_mes']} a {manifest['ultimo_mes']}:")
    for nome, info in manifest["tabelas"].items():
        print(f"  {nome:<20} {info['linhas']:>9,} linhas")


if __name__ == "__main__":
    main()
