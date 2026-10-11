"""Caminhos e constantes do projeto. Os valores vêm do docs/PROJETO.md e do docs/dados.md.

Os caminhos de dados podem ser trocados por variáveis de ambiente (FDR_PASTA_VRA,
FDR_ARQUIVO_AEROPORTOS, FDR_WAREHOUSE, FDR_PASTA_MARTS, FDR_BANCO_APP). Os testes e o CI usam
isso para rodar o pipeline na amostra de data/fixtures/ sem tocar nos dados reais.
"""

import os
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]


def _caminho(variavel: str, padrao: Path) -> Path:
    return Path(os.environ[variavel]) if os.environ.get(variavel) else padrao


PASTA_DADOS = RAIZ / "data"
PASTA_RAW_VRA = _caminho("FDR_PASTA_VRA", PASTA_DADOS / "raw" / "vra")
PASTA_FIXTURES_VRA = PASTA_DADOS / "fixtures" / "vra"
ARQUIVO_AEROPORTOS = _caminho(
    "FDR_ARQUIVO_AEROPORTOS", PASTA_DADOS / "raw" / "referencia" / "airports.csv"
)
ARQUIVO_AEROPORTOS_FIXTURE = PASTA_DADOS / "fixtures" / "referencia" / "airports.csv"
URL_AEROPORTOS = "https://davidmegginson.github.io/ourairports-data/airports.csv"
WAREHOUSE = _caminho("FDR_WAREHOUSE", PASTA_DADOS / "warehouse.duckdb")
PASTA_DBT = RAIZ / "dbt"

# O que vai para o deploy: marts em Parquet e o banco do assistente (PROJETO.md, seção 2).
PASTA_MARTS = _caminho("FDR_PASTA_MARTS", PASTA_DADOS / "marts")
BANCO_APP = _caminho("FDR_BANCO_APP", PASTA_DADOS / "app.duckdb")
MESES_DEPLOY = 24
TAMANHO_MAX_ARQUIVO_MB = 50

# Alvo principal: atraso na partida maior que 15 minutos (critério A15).
LIMIAR_ATRASO_MIN = 15

# Treino e análise começam em janeiro de 2022: 2020 e 2021 foram outro regime de operação
# (docs/decisoes/001-janela-de-dados.md).
INICIO_JANELA = (2022, 1)

# Defasagem de publicação da ANAC em meses, medida na Fase 0 (docs/dados.md, seção 4.2).
DEFASAGEM_PUBLICACAO_MESES = 2

# Cabeçalho exato do VRA, igual de jan/2022 a ago/2026 (docs/dados.md, seção 2).
COLUNAS_VRA = (
    "ICAO Empresa Aérea",
    "Número Voo",
    "Código Autorização (DI)",
    "Código Tipo Linha",
    "ICAO Aeródromo Origem",
    "ICAO Aeródromo Destino",
    "Partida Prevista",
    "Partida Real",
    "Chegada Prevista",
    "Chegada Real",
    "Situação Voo",
    "Código Justificativa",
)
