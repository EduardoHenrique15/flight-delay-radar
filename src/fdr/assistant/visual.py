"""Gráfico automático da resposta do assistente: olha a tabela que o SQL devolveu e escolhe um
gráfico simples, ou nenhum.

- linha: uma coluna de tempo (mês ou data) e uma coluna numérica, com pelo menos 3 linhas;
- barras: uma coluna de rótulos (companhia, aeroporto, cidade, hora...) e uma coluna numérica,
  de 2 a 15 linhas;
- nenhum: um número só, tabelas sem coluna numérica ou grandes demais para ler num gráfico.

A escolha não depende do modelo de linguagem: é uma regra fixa sobre a tabela, testável.
"""

from dataclasses import dataclass

import pandas as pd

MAX_BARRAS = 15
MIN_PONTOS_LINHA = 3
# Colunas que são rótulos mesmo sendo números (hora do dia, trimestre, ano).
ROTULOS_NUMERICOS = ("hora", "trimestre", "ano", "dia_semana")


@dataclass
class Grafico:
    tipo: str  # "linha" ou "barras"
    x: str  # a coluna do eixo x (tempo ou rótulo)
    y: str  # a coluna numérica
    porcentagem: bool  # os valores são taxas de 0 a 1
    x_extra: str | None = None  # uma segunda coluna de rótulo (o destino de uma rota)


def _eh_tempo(serie: pd.Series) -> bool:
    if pd.api.types.is_datetime64_any_dtype(serie):
        return True
    if serie.dtype == object and len(serie) and all(hasattr(v, "year") for v in serie.dropna()):
        return True  # datas do DuckDB como datetime.date
    return False


def eh_rotulo_numerico(nome: str) -> bool:
    return any(parte in str(nome).lower() for parte in ROTULOS_NUMERICOS)


def escolher(tabela: pd.DataFrame | None) -> Grafico | None:
    if tabela is None or len(tabela) < 2 or tabela.shape[1] < 2:
        return None
    numericas = [
        c
        for c in tabela.columns
        if pd.api.types.is_numeric_dtype(tabela[c])
        and not pd.api.types.is_bool_dtype(tabela[c])
        and not eh_rotulo_numerico(str(c))
    ]
    if not numericas:
        return None
    # A medida: uma taxa, se houver; senão a última coluna numérica (SELECT rótulo, medida).
    taxas = [c for c in numericas if "taxa" in str(c).lower()]
    y = taxas[0] if taxas else numericas[-1]
    porcentagem = bool(tabela[y].dropna().between(0, 1).all()) and "taxa" in str(y).lower()

    tempo = [c for c in tabela.columns if c != y and _eh_tempo(tabela[c])]
    if tempo and len(tabela) >= MIN_PONTOS_LINHA:
        return Grafico("linha", tempo[0], y, porcentagem)

    rotulos = [c for c in tabela.columns if c not in numericas]
    if rotulos and len(tabela) <= MAX_BARRAS:
        if "origem" in rotulos and "destino" in rotulos:  # uma rota: "SBGR → SBRF"
            return Grafico("barras", "origem", y, porcentagem, x_extra="destino")
        return Grafico("barras", rotulos[0], y, porcentagem)
    return None
