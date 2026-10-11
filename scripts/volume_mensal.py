"""Volume e pontualidade mês a mês, para justificar a janela de dados (ADR 001).

Lê os CSVs do VRA de uma ou mais pastas (por exemplo, 2019-2021 baixados à parte em
data/raw/vra_historico/ e a janela do projeto em data/raw/vra/) e grava:
  - docs/decisoes/dados/volume_mensal.csv: uma linha por mês;
  - docs/decisoes/img/volume_mensal.png: o gráfico usado no ADR.

Meses cujo arquivo não traz nenhum voo realizado com horário (fevereiro e março de 2020 vieram
assim) aparecem no gráfico como lacuna, e não como zero: é falha do arquivo, não ausência de voos.

Uso:
    python scripts/volume_mensal.py --pastas data/raw/vra_historico data/raw/vra
    python scripts/volume_mensal.py --so-grafico   # redesenha a partir do CSV já gerado
"""

import argparse
from pathlib import Path

import duckdb
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

from fdr.ingest.load_raw import FormatoInvalidoError, inspecionar, mes_do_arquivo  # noqa: E402

AZUL = "#2a78d6"
TEXTO = "#0b0b0b"
TEXTO_SECUNDARIO = "#52514e"
GRADE = "#e4e3df"
FUNDO = "#fcfcfb"
PANDEMIA = ("2020-03-01", "2021-12-31")

CONSULTA = """
with distintas as (
    -- Duplicatas exatas saem considerando TODAS as colunas, como no pipeline (stg_vra).
    select distinct *
    from read_csv('{arquivo}', skip = 1, header = true, delim = ';', all_varchar = true)
),

linhas as (
    select
        "Código Tipo Linha" as tipo_linha,
        "Código Autorização (DI)" as di,
        "Situação Voo" as situacao,
        try_strptime(nullif(left("Partida Prevista", 19), 'null'), '%Y-%m-%d %H:%M:%S') as prevista,
        try_strptime(nullif(left("Partida Real", 19), 'null'), '%Y-%m-%d %H:%M:%S') as real
    from distintas
)
select
    count(*) as linhas,
    count(*) filter (where tipo_linha = 'N' and di = '0') as nacionais_regulares_programados,
    count(*) filter (
        where tipo_linha = 'N' and di = '0' and situacao = 'REALIZADO'
          and prevista is not null and real is not null
    ) as nacionais_regulares_realizados,
    avg((date_diff('minute', prevista, real) > 15)::int) filter (
        where tipo_linha = 'N' and di = '0' and situacao = 'REALIZADO'
          and prevista is not null and real is not null
    ) as fracao_atraso_15,
    avg((situacao = 'CANCELADO')::int) filter (where tipo_linha = 'N' and di = '0')
        as fracao_cancelados
from linhas
"""


def calcular(pastas: list[Path]) -> pd.DataFrame:
    """Uma linha por mês. Se o mesmo arquivo estiver em duas pastas, vale o da primeira."""
    arquivos = {}
    for pasta in pastas:
        for arquivo in sorted(pasta.glob("VRA_*.csv")):
            arquivos.setdefault(arquivo.name, arquivo)

    problemas, linhas = [], []
    for nome, arquivo in sorted(arquivos.items(), key=lambda item: mes_do_arquivo(item[0])):
        try:
            info = inspecionar(arquivo)
        except FormatoInvalidoError as erro:
            problemas.append(str(erro))
            continue
        caminho = arquivo.resolve().as_posix().replace("'", "''")
        resultado = duckdb.sql(CONSULTA.format(arquivo=caminho)).df().iloc[0].to_dict()
        for coluna in (
            "linhas",
            "nacionais_regulares_programados",
            "nacionais_regulares_realizados",
        ):
            resultado[coluna] = int(resultado[coluna])
        linhas.append({"mes": f"{info.ano}-{info.mes:02d}", "arquivo": nome, **resultado})
        print(f"{nome:<16} {int(resultado['nacionais_regulares_realizados']):>7,} voos")
    if problemas:
        raise SystemExit("Arquivos com formato diferente do esperado:\n" + "\n".join(problemas))
    return pd.DataFrame(linhas)


def meses_incompletos(tabela: pd.DataFrame) -> list[str]:
    """Meses com voos programados, mas nenhum realizado com horário: arquivo incompleto."""
    return list(tabela.loc[tabela["nacionais_regulares_realizados"] == 0, "mes"])


def desenhar(tabela: pd.DataFrame, destino: Path) -> None:
    """Dois painéis com o mesmo eixo do tempo: volume em cima, pontualidade embaixo."""
    tabela = tabela.copy()
    lacunas = meses_incompletos(tabela)
    tabela.loc[tabela["mes"].isin(lacunas), "nacionais_regulares_realizados"] = float("nan")
    meses = pd.to_datetime(tabela["mes"])
    figura, (volume, atraso) = plt.subplots(
        2, 1, figsize=(10, 6.2), sharex=True, gridspec_kw={"height_ratios": [3, 2]}
    )
    figura.patch.set_facecolor(FUNDO)
    paineis = [
        (
            volume,
            tabela["nacionais_regulares_realizados"] / 1000,
            "Voos nacionais regulares realizados (mil por mês)",
        ),
        (atraso, tabela["fracao_atraso_15"] * 100, "Partidas com mais de 15 min de atraso (%)"),
    ]
    for eixo, valores, titulo in paineis:
        eixo.set_facecolor(FUNDO)
        eixo.axvspan(pd.Timestamp(PANDEMIA[0]), pd.Timestamp(PANDEMIA[1]), color=GRADE, lw=0)
        eixo.plot(meses, valores, color=AZUL, lw=2, marker="o", ms=3)
        eixo.set_title(titulo, loc="left", fontsize=11, color=TEXTO, pad=8)
        eixo.grid(axis="y", color=GRADE, lw=0.8)
        eixo.set_ylim(bottom=0)
        for lado in ("top", "right", "left"):
            eixo.spines[lado].set_visible(False)
        eixo.spines["bottom"].set_color(GRADE)
        eixo.tick_params(colors=TEXTO_SECUNDARIO, labelsize=9, length=0)
    volume.text(
        pd.Timestamp("2020-06-01"), volume.get_ylim()[1] * 0.95, "Pandemia\n(mar/2020 a dez/2021)",
        va="top", fontsize=9, color=TEXTO_SECUNDARIO,
    )  # fmt: skip
    volume.axvline(pd.Timestamp("2022-01-01"), color=TEXTO_SECUNDARIO, lw=1, ls="--")
    volume.text(
        pd.Timestamp("2022-02-01"), volume.get_ylim()[1] * 0.08, "início da janela\ndo projeto",
        fontsize=9, color=TEXTO_SECUNDARIO,
    )  # fmt: skip
    if lacunas:
        inicio, fim = pd.Timestamp(min(lacunas)), pd.Timestamp(max(lacunas))
        for eixo in (volume, atraso):
            eixo.axvspan(inicio, fim + pd.offsets.MonthEnd(0), fill=False, hatch="///",
                         edgecolor=TEXTO_SECUNDARIO, lw=0)  # fmt: skip
    fonte = "Fonte: ANAC, Voo Regular Ativo (VRA). Voos nacionais (tipo N) e regulares (DI = 0)."
    if lacunas:
        nomes = " e ".join(pd.Timestamp(m).strftime("%m/%Y") for m in lacunas)
        fonte += f" Hachurado: {nomes}, arquivos incompletos (nenhum voo com horário registrado)."
    figura.text(0.01, 0.005, fonte, fontsize=8, color=TEXTO_SECUNDARIO)
    figura.tight_layout(rect=(0, 0.03, 1, 1))
    destino.parent.mkdir(parents=True, exist_ok=True)
    figura.savefig(destino, dpi=150, facecolor=FUNDO)
    plt.close(figura)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--pastas", type=Path, nargs="+")
    parser.add_argument("--so-grafico", action="store_true", help="redesenha a partir do CSV")
    parser.add_argument("--saida", type=Path, default=Path("docs/decisoes/dados/volume_mensal.csv"))
    parser.add_argument("--grafico", type=Path, default=Path("docs/decisoes/img/volume_mensal.png"))
    args = parser.parse_args()
    if args.so_grafico:
        desenhar(pd.read_csv(args.saida, dtype={"mes": str}), args.grafico)
        print(f"Gráfico redesenhado em {args.grafico}.")
        return
    if not args.pastas:
        parser.error("informe --pastas (ou use --so-grafico)")

    tabela = calcular(args.pastas)
    args.saida.parent.mkdir(parents=True, exist_ok=True)
    tabela.round(4).to_csv(args.saida, index=False, lineterminator="\n")
    desenhar(tabela, args.grafico)
    print(f"{len(tabela)} meses. Tabela em {args.saida}, gráfico em {args.grafico}.")


if __name__ == "__main__":
    main()
