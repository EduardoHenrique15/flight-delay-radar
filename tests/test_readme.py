"""Os números de resultado dos READMEs (pt e en) batem com models/metrics.json e com o
histórico do monitoramento. Se o modelo for retreinado, este teste avisa que os READMEs precisam
ser atualizados."""

import json

import pytest

from fdr.config import RAIZ

METRICAS = json.loads((RAIZ / "models" / "metrics.json").read_text(encoding="utf-8"))
TESTE = METRICAS["modelo_final"]["teste"]
BASELINE = METRICAS["baseline"]["teste"]
HISTORICO = json.loads((RAIZ / "monitoring" / "history.json").read_text(encoding="utf-8"))


def numero(valor: float, casas: int, decimal: str) -> str:
    return f"{valor:.{casas}f}".replace(".", decimal)


def milhar(valor: int, separador: str) -> str:
    return f"{valor:,}".replace(",", separador)


@pytest.mark.parametrize(
    ("arquivo", "decimal", "separador"),
    [("README.md", ",", "."), ("README.en.md", ".", ",")],
)
def test_readme_usa_os_numeros_gerados(arquivo, decimal, separador):
    texto = (RAIZ / arquivo).read_text(encoding="utf-8")
    baixo, alto = TESTE["intervalo_95"]["pr_auc"]
    ganho = TESTE["ganho_sobre_baseline"]["pr_auc"]
    meses = HISTORICO["simulacao"]["meses"] + HISTORICO["producao"]["meses"]
    vitorias = sum(m["modelo"]["pr_auc"] > m["baseline"]["pr_auc"] for m in meses)
    esperados = [
        milhar(TESTE["voos"], separador),
        numero(TESTE["pr_auc"], 3, decimal),
        numero(baixo, 3, decimal),
        numero(alto, 3, decimal),
        numero(BASELINE["pr_auc"], 3, decimal),
        "+" + numero(ganho, 3, decimal),
        numero(TESTE["roc_auc"], 3, decimal),
        numero(TESTE["ece"] * 100, 2, decimal) + " p.p.",
        numero(TESTE["lift_10pct"]["precisao"] * 100, 1, decimal) + "%",
        numero(TESTE["lift_10pct"]["lift"], 2, decimal),
        numero(TESTE["lift_10pct_baseline"]["precisao"] * 100, 1, decimal) + "%",
        f"{vitorias} " + ("de" if decimal == "," else "of") + f" {len(meses)}",
    ]
    faltando = [n for n in esperados if n not in texto]
    assert not faltando, f"{arquivo} sem os números de models/metrics.json: {faltando}"
