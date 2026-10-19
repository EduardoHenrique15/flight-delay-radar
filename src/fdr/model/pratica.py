"""O modelo na prática: quantos atrasos uma regra de alerta pega (docs/modelo.md).

Uma regra simples de uso: "avisar os X% de voos com maior risco previsto". Para cada X, mede no
teste a precisão (dos avisados, quantos atrasaram) e a cobertura (dos atrasos, quantos foram
avisados), para o modelo e para o baseline. Também mede as regras por limiar de probabilidade
("avisar quando a chance passar de 30%").

Nada é escolhido aqui: as previsões são as do modelo salvo no teste, já usado uma única vez pela
etapa train. Antes de gravar, a etapa confere que as previsões refeitas reproduzem o PR-AUC do
models/metrics.json; se não reproduzirem (outro modelo ou outros dados), ela para.

Grava models/uso_pratico.json.

Uso: python -m fdr.pipeline --stage pratica
"""

import json

import duckdb
import numpy as np
import pandas as pd

from fdr.config import ARQUIVO_METRICAS, PASTA_MODELOS, WAREHOUSE
from fdr.features.build import ALVO
from fdr.model import baseline, train
from fdr.model.evaluate import metricas
from fdr.model.registry import ModeloAtraso

ARQUIVO_USO = "uso_pratico.json"
FRACOES = [f / 100 for f in range(1, 51)]  # avisar de 1% a 50% dos voos
LIMIARES = [f / 100 for f in range(10, 65, 5)]  # avisar quando a chance passar de 10% a 60%
TOLERANCIA = 1e-6


class PrevisoesDiferentesError(RuntimeError):
    """As previsões refeitas não batem com as do metrics.json."""


def curva_de_alerta(y: np.ndarray, p: np.ndarray, fracoes: list[float] = FRACOES) -> list[dict]:
    """Para cada fração de voos avisados (os de maior risco), a precisão e a cobertura. A ordem
    é a mesma do lift_no_topo, então a linha de 10% reproduz o lift do metrics.json."""
    y = np.asarray(y, dtype=float)
    p = np.asarray(p, dtype=float)
    ordem = np.argsort(-p, kind="stable")
    atrasos_acumulados = np.cumsum(y[ordem])
    total_atrasos = float(y.sum())
    curva = []
    for fracao in fracoes:
        quantidade = max(int(round(len(y) * fracao)), 1)
        pegos = float(atrasos_acumulados[quantidade - 1])
        curva.append(
            {
                "fracao": fracao,
                "voos": quantidade,
                "limiar": float(p[ordem[quantidade - 1]]),
                "precisao": pegos / quantidade,
                "cobertura": pegos / total_atrasos,
            }
        )
    return curva


def regras_por_limiar(y: np.ndarray, p: np.ndarray, limiares: list[float] = LIMIARES) -> list[dict]:
    """Para cada limiar de probabilidade, quantos voos seriam avisados e quantos atrasos."""
    y = np.asarray(y, dtype=float)
    p = np.asarray(p, dtype=float)
    regras = []
    for limiar in limiares:
        avisados = p >= limiar
        quantidade = int(avisados.sum())
        pegos = float(y[avisados].sum())
        regras.append(
            {
                "limiar": limiar,
                "voos": quantidade,
                "fracao": quantidade / len(y),
                "precisao": pegos / quantidade if quantidade else None,
                "cobertura": pegos / float(y.sum()),
            }
        )
    return regras


def conferir(nome: str, calculado: float, salvo: float) -> None:
    if abs(calculado - salvo) > TOLERANCIA:
        raise PrevisoesDiferentesError(
            f"PR-AUC do {nome} refeito ({calculado:.6f}) diferente do models/metrics.json "
            f"({salvo:.6f}). O modelo ou os dados mudaram depois da etapa train: rode-a de novo."
        )


def main() -> None:
    salvas = json.loads(ARQUIVO_METRICAS.read_text(encoding="utf-8"))
    final = salvas["modelo_final"]
    modelo = ModeloAtraso.carregar()
    inicio, fim = (pd.Timestamp(m).date() for m in final["teste"]["periodo"])
    with duckdb.connect(str(WAREHOUSE), read_only=True) as con:
        dados = train.carregar(con)
    teste = train.no_periodo(dados, inicio, fim)
    y = teste[ALVO].to_numpy()
    p_modelo = modelo.prever(teste)
    p_base = baseline.prever(teste, final["decisoes"]["janela_baseline"])[0]

    # O PR-AUC do baseline que a etapa train usou é o do modelo menos o ganho.
    pr_auc_base = final["teste"]["pr_auc"] - final["teste"]["ganho_sobre_baseline"]["pr_auc"]
    conferir("modelo", metricas(y, p_modelo)["pr_auc"], final["teste"]["pr_auc"])
    conferir("baseline", metricas(y, p_base)["pr_auc"], pr_auc_base)

    resultado = {
        "periodo": final["teste"]["periodo"],
        "voos": int(len(y)),
        "atrasos": int(y.sum()),
        "taxa_real": float(y.mean()),
        "por_fracao": {
            "modelo": curva_de_alerta(y, p_modelo),
            "baseline": curva_de_alerta(y, p_base),
        },
        "por_limiar": regras_por_limiar(y, p_modelo),
    }
    (PASTA_MODELOS / ARQUIVO_USO).write_text(
        json.dumps(resultado, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    print(f"Teste {inicio} a {fim}: {len(y):,} voos, {int(y.sum()):,} atrasos.")
    print("Avisar os voos de maior risco (modelo | baseline):")
    for m, b in zip(
        resultado["por_fracao"]["modelo"], resultado["por_fracao"]["baseline"], strict=True
    ):
        if round(m["fracao"] * 100) in (5, 10, 20, 30):
            print(
                f"  {m['fracao']:>4.0%} dos voos: precisão {m['precisao']:.1%} | "
                f"{b['precisao']:.1%}, cobertura {m['cobertura']:.1%} | {b['cobertura']:.1%}"
            )
    print(f"Gravado: models/{ARQUIVO_USO}.")


if __name__ == "__main__":
    main()
