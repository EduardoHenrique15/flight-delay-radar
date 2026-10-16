"""Registro do modelo: salva e carrega o modelo final com o que for preciso para usá-lo.

Arquivos em models/:
- model.txt: o LightGBM no formato nativo (texto). Não é pickle: abre em qualquer versão
  compatível do LightGBM e não executa código ao carregar.
- metadata.json: versão, datas, meses de treino e teste, variáveis, hiperparâmetros, número de
  árvores, calibração, categorias de companhia/origem/destino (a codificação usada no treino),
  versões das bibliotecas e um hash dos dados de treino.
- reference_profile.json: a distribuição de cada variável no treino, base do PSI na Fase 4.

Uso no app e no monitoramento: `ModeloAtraso.carregar()` e `.prever(dados)`.
"""

import json
from dataclasses import dataclass
from importlib.metadata import version
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd

from fdr.config import PASTA_MODELOS
from fdr.model import train

ARQUIVO_MODELO = "model.txt"
ARQUIVO_METADADOS = "metadata.json"
ARQUIVO_PERFIL = "reference_profile.json"
BIBLIOTECAS = ("lightgbm", "scikit-learn", "numpy", "pandas", "duckdb")
FAIXAS_PERFIL = 10
MAX_CATEGORIAS_PERFIL = 30


def versoes_bibliotecas() -> dict[str, str]:
    return {nome: version(nome) for nome in BIBLIOTECAS}


@dataclass
class ModeloAtraso:
    """O LightGBM final com a codificação das categorias usada no treino."""

    booster: lgb.Booster
    metadados: dict

    def preparar(self, dados: pd.DataFrame) -> pd.DataFrame:
        """Recodifica as categorias com a lista do treino (categoria nova vira ausente)."""
        dados = dados.copy()
        for coluna, categorias in self.metadados["categorias"].items():
            valores = dados[coluna].astype("string")
            valores = valores.where(valores.isin(categorias))
            dados[coluna] = pd.Categorical(valores, categories=categorias)
        return dados

    def prever(self, dados: pd.DataFrame) -> np.ndarray:
        """Probabilidade de atraso acima de 15 min para cada voo."""
        return self.booster.predict(train.matriz(self.preparar(dados)))

    def salvar(self, pasta: Path = PASTA_MODELOS) -> None:
        pasta.mkdir(parents=True, exist_ok=True)
        # Gravado pelo Python: o LightGBM em C++ não aceita acentos no caminho no Windows
        # ("Área de Trabalho").
        (pasta / ARQUIVO_MODELO).write_text(self.booster.model_to_string(), encoding="utf-8")
        _gravar_json(pasta / ARQUIVO_METADADOS, self.metadados)

    @classmethod
    def carregar(cls, pasta: Path = PASTA_MODELOS) -> "ModeloAtraso":
        metadados = json.loads((pasta / ARQUIVO_METADADOS).read_text(encoding="utf-8"))
        if metadados["variaveis"] != list(train.VARIAVEIS):
            raise ValueError("O modelo salvo usa outras variáveis: treine de novo.")
        texto = (pasta / ARQUIVO_MODELO).read_text(encoding="utf-8")
        return cls(lgb.Booster(model_str=texto), metadados)


def perfil_de_referencia(dados: pd.DataFrame) -> dict:
    """Distribuição de cada variável no treino: faixas por decis (números) ou frequência das
    categorias mais comuns (o resto vira "outras"). A fração de ausentes fica à parte."""
    perfil = {}
    for coluna in train.VARIAVEIS:
        serie = dados[coluna]
        ausentes = float(serie.isna().mean())
        if coluna in train.CATEGORICAS:
            frequencias = serie.astype("string").value_counts(normalize=True, dropna=True)
            topo = frequencias.head(MAX_CATEGORIAS_PERFIL)
            perfil[coluna] = {
                "tipo": "categorica",
                "ausentes": ausentes,
                "frequencias": {str(k): float(v) for k, v in topo.items()},
                "outras": float(max(1 - ausentes - topo.sum(), 0.0)),
            }
        else:
            valores = serie.dropna().to_numpy(dtype=float)
            limites = np.unique(np.quantile(valores, np.linspace(0, 1, FAIXAS_PERFIL + 1)))
            internos = limites[1:-1]
            contagem = np.bincount(
                np.searchsorted(internos, valores, side="right"), minlength=len(internos) + 1
            )
            perfil[coluna] = {
                "tipo": "numerica",
                "ausentes": ausentes,
                "limites": [float(v) for v in internos],
                "frequencias": [float(c) / len(serie) for c in contagem],
            }
    return perfil


def salvar_perfil(perfil: dict, pasta: Path = PASTA_MODELOS) -> None:
    _gravar_json(pasta / ARQUIVO_PERFIL, perfil)


def _gravar_json(caminho: Path, conteudo: dict) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(json.dumps(conteudo, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
