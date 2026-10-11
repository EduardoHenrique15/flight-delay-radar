"""Monta a amostra de dados usada nos testes e no CI (data/fixtures/vra/).

Sorteia linhas reais de 3 meses do VRA e inclui de propósito os casos difíceis que o pipeline
precisa tratar: duplicatas exatas, voo repetido em dois arquivos, cancelados, voos sem partida
prevista, virada da meia-noite, partida prevista no mês seguinte, atrasos fora da faixa aceita e
conflito de chave. As linhas são copiadas byte a byte, no mesmo formato dos arquivos da ANAC.

Uso: python scripts/criar_fixtures.py [--origem data/raw/vra] [--destino data/fixtures/vra]
"""

import argparse
import random
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

MESES = ["VRA_20265.csv", "VRA_20266.csv", "VRA_20267.csv"]
SORTEIO_POR_MES = 1200
SEMENTE = 42
BOM = "﻿"


def campos(linha: str) -> list[str]:
    return [c.strip('"') for c in linha.split(";")]


def data(texto: str) -> datetime | None:
    return None if texto == "null" else datetime.strptime(texto[:19], "%Y-%m-%d %H:%M:%S")


def atraso(c: list[str]) -> float | None:
    prevista, real = data(c[6]), data(c[7])
    return None if prevista is None or real is None else (real - prevista).total_seconds() / 60


def escolher(linhas: list[str], inicio_mes: datetime) -> list[str]:
    """Sorteio + casos difíceis, sem repetir linha (as duplicatas entram depois)."""
    sorteio = random.Random(SEMENTE)
    escolhidas = dict.fromkeys(sorteio.sample(linhas, SORTEIO_POR_MES))
    fim_mes = (inicio_mes + timedelta(days=32)).replace(day=1)

    def primeiras(condicao, n):
        achadas = [linha for linha in linhas if condicao(campos(linha))][:n]
        escolhidas.update(dict.fromkeys(achadas))

    primeiras(lambda c: c[10] == "CANCELADO" and c[3] == "N", 20)
    primeiras(lambda c: c[6] == "null", 10)
    primeiras(lambda c: c[3] == "N" and c[0] in {"GLO", "AZU", "TAM"} and (a := atraso(c))
              is not None and 0 < a < 120 and data(c[6]).day != data(c[7]).day, 3)  # fmt: skip
    primeiras(lambda c: (p := data(c[6])) is not None and p >= fim_mes, 3)
    primeiras(lambda c: (a := atraso(c)) is not None and not -120 <= a <= 1440, 4)

    chaves = Counter(tuple(campos(linha)[i] for i in (0, 1, 2, 4, 5, 6)) for linha in linhas)
    conflito = next((k for k, n in chaves.items() if n > 1 and k[5] != "null"), None)
    if conflito:
        primeiras(lambda c: tuple(c[i] for i in (0, 1, 2, 4, 5, 6)) == conflito, 4)
    return list(escolhidas)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--origem", type=Path, default=Path("data/raw/vra"))
    parser.add_argument("--destino", type=Path, default=Path("data/fixtures/vra"))
    args = parser.parse_args()
    args.destino.mkdir(parents=True, exist_ok=True)

    selecoes = {}
    for nome in MESES:
        texto = (args.origem / nome).read_bytes().decode("utf-8-sig")
        metadado, cabecalho, *linhas = [linha for linha in texto.split("\r\n") if linha]
        ano, mes = int(nome[4:8]), int(nome[8:-4])
        selecoes[nome] = (metadado, cabecalho, escolher(linhas, datetime(ano, mes, 1)))

    # Duplicatas exatas no mesmo arquivo (3 linhas repetidas por mês).
    for _, _, linhas in selecoes.values():
        linhas.extend(linhas[:3])
    # O mesmo voo em dois arquivos: o 1º voo de junho com partida prevista em julho vai também
    # para o arquivo de julho, como acontece de verdade entre julho e agosto de 2026.
    _, _, junho = selecoes["VRA_20266.csv"]
    fronteira = next(
        linha for linha in junho if (p := data(campos(linha)[6])) and p >= datetime(2026, 7, 1)
    )
    selecoes["VRA_20267.csv"][2].append(fronteira)

    for nome, (metadado, cabecalho, linhas) in selecoes.items():
        conteudo = BOM + "\r\n".join([metadado, cabecalho, *linhas]) + "\r\n"
        (args.destino / nome).write_bytes(conteudo.encode("utf-8"))
        print(f"{nome}: {len(linhas)} linhas")


if __name__ == "__main__":
    main()
