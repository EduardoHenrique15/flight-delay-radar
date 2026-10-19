"""Testes da regra de alerta (fdr.model.pratica) e do models/uso_pratico.json versionado."""

import json

import numpy as np
import pytest

from fdr.config import RAIZ
from fdr.model.evaluate import lift_no_topo
from fdr.model.pratica import (
    PrevisoesDiferentesError,
    conferir,
    curva_de_alerta,
    regras_por_limiar,
)


@pytest.fixture
def previsoes():
    gerador = np.random.default_rng(7)
    p = gerador.uniform(0, 0.6, 5000)
    y = (gerador.uniform(0, 1, 5000) < p).astype(float)
    return y, p


def test_curva_de_alerta_reproduz_o_lift_e_cresce(previsoes):
    y, p = previsoes
    curva = curva_de_alerta(y, p, [0.05, 0.10, 0.50])
    dez = curva[1]
    assert dez["precisao"] == pytest.approx(lift_no_topo(y, p)["precisao"])
    assert dez["voos"] == 500
    assert dez["cobertura"] == pytest.approx(y[np.argsort(-p, kind="stable")[:500]].sum() / y.sum())
    coberturas = [c["cobertura"] for c in curva]
    assert coberturas == sorted(coberturas)
    assert [c["limiar"] for c in curva] == sorted((c["limiar"] for c in curva), reverse=True)


def test_regras_por_limiar_contam_os_voos_acima_do_limiar(previsoes):
    y, p = previsoes
    regra = regras_por_limiar(y, p, [0.3, 0.99])
    acima = p >= 0.3
    assert regra[0]["voos"] == acima.sum()
    assert regra[0]["precisao"] == pytest.approx(y[acima].mean())
    assert regra[1] == {
        "limiar": 0.99,
        "voos": 0,
        "fracao": 0.0,
        "precisao": None,
        "cobertura": 0.0,
    }


def test_conferir_para_quando_as_previsoes_mudaram():
    conferir("modelo", 0.3116, 0.3116)
    with pytest.raises(PrevisoesDiferentesError, match="rode-a de novo"):
        conferir("modelo", 0.30, 0.3116)


def test_uso_pratico_versionado_bate_com_o_metrics_json():
    """O 10% da curva é o mesmo lift do teste: as previsões são as do modelo final."""
    uso = json.loads((RAIZ / "models" / "uso_pratico.json").read_text(encoding="utf-8"))
    metricas = json.loads((RAIZ / "models" / "metrics.json").read_text(encoding="utf-8"))
    teste = metricas["modelo_final"]["teste"]
    assert uso["periodo"] == teste["periodo"]
    assert uso["voos"] == teste["voos"]
    assert uso["taxa_real"] == pytest.approx(teste["taxa_real"])
    for serie, lift in (("modelo", "lift_10pct"), ("baseline", "lift_10pct_baseline")):
        dez = next(c for c in uso["por_fracao"][serie] if c["fracao"] == 0.1)
        assert dez["voos"] == teste[lift]["voos"]
        assert dez["precisao"] == pytest.approx(teste[lift]["precisao"])


def test_cartao_do_modelo_usa_os_numeros_do_uso_pratico():
    uso = json.loads((RAIZ / "models" / "uso_pratico.json").read_text(encoding="utf-8"))
    texto = (RAIZ / "docs" / "modelo.md").read_text(encoding="utf-8")

    def pct(valor: float) -> str:
        return f"{valor:.1%}".replace(".", ",")

    def linha(serie: str, porcento: int) -> dict:
        return next(c for c in uso["por_fracao"][serie] if round(c["fracao"] * 100) == porcento)

    esperados = [f"{uso['voos']:,}".replace(",", "."), f"{uso['atrasos']:,}".replace(",", ".")]
    for porcento in (5, 10, 20, 30):
        modelo, base = linha("modelo", porcento), linha("baseline", porcento)
        esperados.append(
            f"| {porcento}% | {pct(modelo['precisao'])} | {pct(base['precisao'])} | "
            f"{pct(modelo['cobertura'])} | {pct(base['cobertura'])} |"
        )
    dez = linha("modelo", 10)
    esperados += [pct(1 - dez["precisao"]), pct(1 - dez["cobertura"])]
    faltando = [n for n in esperados if n not in texto]
    assert not faltando, f"docs/modelo.md sem os números de models/uso_pratico.json: {faltando}"
