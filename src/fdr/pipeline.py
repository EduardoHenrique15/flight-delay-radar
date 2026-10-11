"""Orquestra o pipeline. Por enquanto só a etapa de dados: carga -> dbt build -> exportação.

Uso: python -m fdr.pipeline --stage data
"""

import argparse
import os
import subprocess
import sys

import duckdb

from fdr.config import PASTA_DBT, PASTA_RAW_VRA, WAREHOUSE
from fdr.export import exportar
from fdr.ingest.load_raw import carregar_pasta


def rodar_dbt(*args: str) -> None:
    """Roda o dbt num processo separado, apontando para o warehouse por caminho absoluto.

    Assim o comando funciona de qualquer pasta e sem depender do dbt.exe no PATH. O processo
    separado também garante que o dbt solte o arquivo do banco antes da exportação.
    """
    ambiente = {**os.environ, "FDR_WAREHOUSE": str(WAREHOUSE.resolve())}
    comando = [
        sys.executable,
        "-c",
        "import sys; from dbt.cli.main import cli; sys.exit(cli())",
        *args,
    ]
    comando += ["--project-dir", str(PASTA_DBT), "--profiles-dir", str(PASTA_DBT)]
    if subprocess.run(comando, env=ambiente).returncode != 0:
        raise SystemExit(f"dbt {' '.join(args)} falhou. Veja as mensagens acima.")


def etapa_dados(forcar: bool = False) -> None:
    print("1/3 Carga dos CSVs do VRA")
    WAREHOUSE.parent.mkdir(parents=True, exist_ok=True)
    with duckdb.connect(str(WAREHOUSE)) as con:
        for nome, linhas in carregar_pasta(con, PASTA_RAW_VRA, forcar).items():
            print(f"    {nome:<16} {'sem mudanças' if linhas is None else f'{linhas:,} linhas'}")

    print("2/3 dbt build (modelos e testes de qualidade)")
    rodar_dbt("build")

    print("3/3 Exportação para o app")
    manifest = exportar()
    print(f"    De {manifest['primeiro_mes']} a {manifest['ultimo_mes']}:")
    for nome, info in manifest["tabelas"].items():
        print(f"    {nome:<20} {info['linhas']:>9,} linhas")


def main() -> None:
    parser = argparse.ArgumentParser(description="Pipeline do Flight Delay Radar.")
    parser.add_argument("--stage", choices=["data"], required=True)
    parser.add_argument("--forcar", action="store_true", help="recarrega todos os CSVs")
    args = parser.parse_args()
    if args.stage == "data":
        etapa_dados(args.forcar)
    print("Pronto.")


if __name__ == "__main__":
    sys.exit(main())
