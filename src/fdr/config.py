"""Caminhos e constantes do projeto. Os valores vêm do docs/PROJETO.md e do docs/dados.md."""

from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]

PASTA_DADOS = RAIZ / "data"
PASTA_RAW_VRA = PASTA_DADOS / "raw" / "vra"
WAREHOUSE = PASTA_DADOS / "warehouse.duckdb"

# Alvo principal: atraso na partida maior que 15 minutos (critério A15).
LIMIAR_ATRASO_MIN = 15

# Treino e análise começam em janeiro de 2022 (2020 e 2021 distorcidos pela pandemia).
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
