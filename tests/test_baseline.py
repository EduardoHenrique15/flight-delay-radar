"""Testes do baseline: recurso entre níveis, escolha da janela e gravação das métricas."""

import json
from datetime import date

import numpy as np
import pandas as pd
import pytest

import fdr.model.baseline as baseline
from fdr.model.splits import definir_divisao

COLUNAS = [
    f"{tipo}_{nivel}_{j}m"
    for nivel in baseline.NIVEIS
    for j in (3, 12)
    for tipo in ("taxa", "voos")
]


def linha(**valores) -> dict:
    base = dict.fromkeys(COLUNAS, np.nan)
    base.update(valores)
    return base


def test_recorre_ao_nivel_seguinte_quando_falta_historico():
    pais = {"taxa_global_12m": 0.15, "voos_global_12m": 9}
    dados = pd.DataFrame(
        [
            linha(taxa_rota_hora_12m=0.5, voos_rota_hora_12m=40, **pais),
            linha(
                taxa_rota_hora_12m=0.9,
                voos_rota_hora_12m=5,
                taxa_cia_12m=0.2,
                voos_cia_12m=900,
                **pais,
            ),
            linha(taxa_origem_12m=0.3, voos_origem_12m=500, **pais),
            linha(**pais),
        ]
    )
    probabilidade, nivel = baseline.prever(dados, janela=12, min_voos=30)
    assert probabilidade.tolist() == [0.5, 0.2, 0.3, 0.15]
    assert nivel.tolist() == ["rota_hora", "cia", "origem", "global"]


def dados_sinteticos(semente: int = 0) -> pd.DataFrame:
    """44 meses (jan/2023 a ago/2026). Cada rota tem uma taxa verdadeira; o histórico de 12 meses
    estima essa taxa com menos ruído que o de 3 meses, então o baseline deve escolher 12."""
    gerador = np.random.default_rng(semente)
    meses = pd.date_range("2023-01-01", "2026-08-01", freq="MS")
    linhas = []
    for mes in meses:
        verdade = gerador.uniform(0.05, 0.4, size=300)
        dias = mes + pd.to_timedelta(gerador.integers(0, 28, size=300), unit="D")
        for t, dia in zip(verdade, dias, strict=True):
            linhas.append(
                linha(
                    mes=mes,
                    data_prevista=dia,
                    atrasado_15=int(gerador.uniform() < t),
                    taxa_rota_hora_3m=np.clip(t + gerador.normal(0, 0.15), 0, 1),
                    voos_rota_hora_3m=60,
                    taxa_rota_hora_12m=np.clip(t + gerador.normal(0, 0.03), 0, 1),
                    voos_rota_hora_12m=240,
                    taxa_global_3m=0.2,
                    voos_global_3m=1000,
                    taxa_global_12m=0.2,
                    voos_global_12m=4000,
                )
            )
    return pd.DataFrame(linhas)


def test_avaliacao_escolhe_a_janela_pela_validacao_e_testa_os_ultimos_meses(monkeypatch):
    monkeypatch.setattr("fdr.model.evaluate.AMOSTRAS_BOOTSTRAP", 20)
    dados = dados_sinteticos()
    divisao = definir_divisao(sorted(d.date() for d in dados["mes"].unique()))
    resultado = baseline.avaliar(dados, divisao)

    assert resultado["janela_escolhida"] == "12m"
    assert resultado["teste"]["periodo"] == ["2026-06-01", "2026-08-01"]
    assert resultado["teste"]["voos"] == 900
    assert sum(resultado["teste"]["nivel_usado"].values()) == pytest.approx(1.0)
    assert len(resultado["validacao_cruzada"]["12m"]) == 5


def test_metricas_sao_gravadas_sem_apagar_outras_secoes(tmp_path, monkeypatch):
    arquivo = tmp_path / "metrics.json"
    arquivo.write_text(json.dumps({"lightgbm": {"pr_auc": 0.5}}), encoding="utf-8")
    monkeypatch.setattr(baseline, "ARQUIVO_METRICAS", arquivo)
    divisao = definir_divisao(list(pd.date_range("2023-01-01", "2026-08-01", freq="MS").date))

    baseline.salvar_metricas("baseline", {"teste": {"pr_auc": 0.3}}, divisao)
    gravado = json.loads(arquivo.read_text(encoding="utf-8"))
    assert gravado["lightgbm"] == {"pr_auc": 0.5}
    assert gravado["baseline"]["teste"] == {"pr_auc": 0.3}
    assert gravado["divisao"]["teste"] == [date(2026, 6, 1).isoformat(), "2026-08-01"]
