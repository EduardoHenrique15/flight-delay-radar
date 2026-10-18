"""Previsão de voos futuros no app, com as mesmas variáveis do treino (paridade).

O app não tem o warehouse, só os arquivos de data/marts/. Por isso a previsão tem duas metades:

1. Exportação (com o warehouse, no pipeline): as tabelas de histórico as-of dos próximos
   MESES_PREVISAO meses depois do último publicado (features.build.criar_tabelas_asof), mais o
   calendário desses meses e as distâncias das rotas, vão para data/marts/previsao/ em Parquet.
2. App: `Previsor` carrega esses Parquet num DuckDB em memória e roda a MESMA consulta do treino
   (features.build.consulta_variaveis) sobre os voos escolhidos. O teste de paridade
   (tests/test_pipeline_fixtures.py) confere que as variáveis saem iguais às da tabela de treino.

Corte: um voo do mês M usa os meses até M - 2, como no treino. Se M - 2 ainda não foi publicado,
usa o último mês publicado: o histórico fica mais velho que no treino, e o app avisa
(`historico_defasado`).

Uso: python -m fdr.previsao   (exporta as tabelas a partir do warehouse)
"""

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

from fdr.config import DEFASAGEM_PUBLICACAO_MESES, PASTA_MARTS, WAREHOUSE
from fdr.features import build
from fdr.model import explain, train
from fdr.model.registry import ModeloAtraso

PASTA_PREVISAO = PASTA_MARTS / "previsao"
MESES_PREVISAO = 4
TABELAS = (*build.TABELAS_ASOF, "dim_date", "dim_routes")
ARQUIVO_MANIFEST = "manifest.json"

# Faixas da probabilidade de atraso mostradas no app. A taxa média de atraso da base é de cerca
# de 15% (docs/modelo.md): abaixo dela o risco é baixo; acima de 25%, alto.
LIMITE_MEDIA = 0.15
LIMITE_ALTA = 0.25


def somar_meses(mes: date, meses: int) -> date:
    total = mes.year * 12 + mes.month - 1 + meses
    return date(total // 12, total % 12 + 1, 1)


def faixa(probabilidade: float) -> str:
    if probabilidade >= LIMITE_ALTA:
        return "alta"
    if probabilidade >= LIMITE_MEDIA:
        return "média"
    return "baixa"


def exportar(
    con: duckdb.DuckDBPyConnection,
    pasta: Path = PASTA_PREVISAO,
    meses: int = MESES_PREVISAO,
    defasagem: int = DEFASAGEM_PUBLICACAO_MESES,
    alvos: list[date] | None = None,
) -> dict:
    """Grava as tabelas da previsão em Parquet e devolve o manifest. `alvos` troca os meses
    previstos (o teste de paridade usa meses que já têm voos)."""
    ultimo = con.execute("select max(mes) from fct_flights").fetchone()[0]
    if ultimo is None:
        raise ValueError("fct_flights está vazia: rode o pipeline de dados antes.")
    alvos = alvos or [somar_meses(ultimo, k) for k in range(1, meses + 1)]
    build.criar_tabelas_asof(con, defasagem, alvos)

    pasta.mkdir(parents=True, exist_ok=True)
    fim = somar_meses(max(alvos), 1)
    consultas = {nome: f"select * from {nome}" for nome in build.TABELAS_ASOF}
    consultas["dim_date"] = (
        f"select * from dim_date where data >= '{min(alvos)}' and data < '{fim}' order by data"
    )
    consultas["dim_routes"] = "select origem, destino, distancia_km from dim_routes"
    for nome, consulta in consultas.items():
        destino = (pasta / f"{nome}.parquet").resolve().as_posix().replace("'", "''")
        con.execute(f"copy ({consulta}) to '{destino}' (format parquet, compression zstd)")

    manifest = {
        "ultimo_mes_publicado": ultimo.isoformat(),
        "defasagem_meses": defasagem,
        "meses": [m.isoformat() for m in sorted(alvos)],
    }
    (pasta / ARQUIVO_MANIFEST).write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return manifest


@dataclass
class Voo:
    cia: str
    origem: str
    destino: str
    data: date
    hora: int


class Previsor:
    """Variáveis e probabilidade de atraso de voos futuros, a partir de data/marts/previsao/."""

    def __init__(self, pasta: Path = PASTA_PREVISAO, modelo: ModeloAtraso | None = None):
        self.manifest = json.loads((pasta / ARQUIVO_MANIFEST).read_text(encoding="utf-8"))
        self.modelo = modelo or ModeloAtraso.carregar()
        self.con = duckdb.connect()
        for nome in TABELAS:
            arquivo = (pasta / f"{nome}.parquet").resolve().as_posix().replace("'", "''")
            self.con.execute(f"create table {nome} as select * from read_parquet('{arquivo}')")

    @property
    def meses(self) -> list[date]:
        return [date.fromisoformat(m) for m in self.manifest["meses"]]

    @property
    def ultimo_mes_publicado(self) -> date:
        return date.fromisoformat(self.manifest["ultimo_mes_publicado"])

    def periodo(self) -> tuple[date, date]:
        """Primeiro e último dia que o app aceita para a previsão."""
        return self.meses[0], date.fromordinal(somar_meses(self.meses[-1], 1).toordinal() - 1)

    def historico_defasado(self, dia: date) -> bool:
        """Verdadeiro quando o voo usa histórico mais velho que no treino (corte depois do último
        mês publicado)."""
        mes = date(dia.year, dia.month, 1)
        return somar_meses(mes, -self.manifest["defasagem_meses"]) > self.ultimo_mes_publicado

    def rotas(self) -> pd.DataFrame:
        """Rotas com voos da base do modelo nos 12 meses até o corte do primeiro mês previsto,
        das mais voadas para as menos."""
        return self.con.execute(
            "select origem, destino, sum(voos_12m) as voos from hist_rota_hora "
            "where mes_alvo = ? group by all order by voos desc, origem, destino",
            [self.meses[0]],
        ).df()

    def companhias_na_rota(self, origem: str, destino: str, dia: date) -> list[str]:
        """Companhias que voaram a rota nos 12 meses até o corte do mês do voo."""
        linhas = self.con.execute(
            "select cia from duracao_cia_rota where mes_alvo = ? and origem = ? and destino = ? "
            "order by cia",
            [date(dia.year, dia.month, 1), origem, destino],
        ).fetchall()
        return [cia for (cia,) in linhas]

    def variaveis(self, voos: list[Voo]) -> pd.DataFrame:
        """As variáveis do modelo, com a mesma consulta e os mesmos tipos do treino."""
        inicio, fim = self.periodo()
        for voo in voos:
            if not inicio <= voo.data <= fim:
                raise ValueError(f"Data fora do período da previsão ({inicio} a {fim}).")
        entrada = pd.DataFrame(
            {
                "voo_id": [str(i) for i in range(len(voos))],
                "mes": [date(v.data.year, v.data.month, 1) for v in voos],
                "data_prevista_local": [v.data for v in voos],
                "hora_prevista_local": [int(v.hora) for v in voos],
                "cia": [v.cia for v in voos],
                "origem": [v.origem for v in voos],
                "destino": [v.destino for v in voos],
            }
        )
        self.con.register("voos_entrada", entrada)
        self.con.execute("""
            create or replace temp table voos_previsao as
            select voo_id, mes::date as mes, data_prevista_local::date as data_prevista_local,
                   null::boolean as atrasado_15, hora_prevista_local::integer as
                   hora_prevista_local, cia, origem, destino
            from voos_entrada
        """)
        self.con.unregister("voos_entrada")
        consulta = build.consulta_variaveis(build.FONTE_PREVISAO, com_analise=False)
        dados = self.con.execute(
            f"select * from ({consulta}) order by cast(voo_id as integer)"
        ).df()
        numericas = [c for c in train.VARIAVEIS if c not in train.CATEGORICAS]
        dados[numericas] = dados[numericas].astype("float32")
        return dados

    def prever(self, voos: list[Voo]) -> list[dict]:
        """Probabilidade, faixa, fatores (SHAP por tema) e a taxa histórica da rota no horário."""
        dados = self.variaveis(voos)
        explicacoes = explain.explicar_voos(self.modelo, dados)
        resultados = []
        for voo, (_, linha), explicacao in zip(voos, dados.iterrows(), explicacoes, strict=True):
            historica = linha["taxa_rota_hora_12m"]
            resultados.append(
                {
                    **explicacao,
                    "voo": voo,
                    "faixa": faixa(explicacao["probabilidade"]),
                    "taxa_rota_hora_12m": None if np.isnan(historica) else float(historica),
                    "voos_rota_hora_12m": int(linha["voos_rota_hora_12m"]),
                    "historico_defasado": self.historico_defasado(voo.data),
                }
            )
        return resultados


def main() -> None:
    with duckdb.connect(str(WAREHOUSE), read_only=True) as con:
        manifest = exportar(con)
    print(
        f"Previsão: meses {manifest['meses'][0]} a {manifest['meses'][-1]}, com dados até "
        f"{manifest['ultimo_mes_publicado']}. Gravado em data/marts/previsao/."
    )


if __name__ == "__main__":
    main()
