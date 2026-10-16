"""Testes da explicação do modelo (SHAP por tema) e dos gráficos."""

import numpy as np
import pytest
from sinteticos import dados_sinteticos

from fdr.model import explain, figuras, final, train
from fdr.model.splits import definir_divisao

DECISOES = {
    "modelo": "lightgbm",
    "parametros": {"num_leaves": 15, "min_child_samples": 50, "learning_rate": 0.1},
    "arvores": 30,
    "arvores_por_corte": [30],
    "calibracao": "crua",
    "janela_baseline": 12,
}


@pytest.fixture(scope="module")
def modelo_e_teste():
    dados = dados_sinteticos(por_mes=200)
    divisao = definir_divisao(sorted(d.date() for d in dados["mes"].unique()))
    modelo = final.treinar_final(dados, divisao, DECISOES)
    teste = train.no_periodo(dados, *divisao.teste).reset_index(drop=True)
    return modelo, teste


def test_cada_variavel_esta_em_exatamente_um_tema():
    variaveis = [v for lista in explain.GRUPOS.values() for v in lista]
    assert sorted(variaveis) == sorted(train.VARIAVEIS)


def test_contribuicoes_somam_a_previsao(modelo_e_teste):
    modelo, teste = modelo_e_teste
    shap, partida = explain.contribuicoes(modelo, teste)
    probabilidade = 1 / (1 + np.exp(-(shap.sum(axis=1) + partida)))
    np.testing.assert_allclose(probabilidade, modelo.prever(teste), rtol=1e-6)
    temas = explain.agrupar(shap)
    np.testing.assert_allclose(temas.sum(axis=1), shap.sum(axis=1), rtol=1e-9)


def test_explicacao_local_traz_fatores_ordenados_e_frases(modelo_e_teste):
    modelo, teste = modelo_e_teste
    explicacao = explain.explicar_voos(modelo, teste.head(5))[0]
    aumentam = [f["pontos"] for f in explicacao["aumentam"]]
    diminuem = [f["pontos"] for f in explicacao["diminuem"]]
    assert aumentam == sorted(aumentam, reverse=True) and all(v > 0 for v in aumentam)
    assert diminuem == sorted(diminuem) and all(v < 0 for v in diminuem)
    assert len(aumentam) <= 3 and len(diminuem) <= 3
    assert explain.frase({"tema": "Horário do voo", "pontos": 8.25}) == "Horário do voo: +8,2 p.p."


def test_graficos_sao_gerados_a_partir_dos_jsons(modelo_e_teste, tmp_path):
    modelo, teste = modelo_e_teste
    importancia = explain.importancia_global(modelo, teste)
    assert {t["tema"] for t in importancia["por_tema"]} == set(explain.GRUPOS)
    janela = {"periodo": ["2026-03-01", "2026-05-01"], "pr_auc": 0.25}
    curva = [{"voos": 500, "prevista_media": 0.15, "taxa_real": 0.16}]
    metricas = {
        "validacao_modelos": {"validacao_cruzada": {"baseline": [janela], "lightgbm": [janela]}},
        "baseline": {"teste": {"pr_auc": 0.28, "curva_calibracao": curva}},
        "modelo_final": {"teste": {"pr_auc": 0.31, "curva_calibracao": curva}},
    }
    caminhos = figuras.gerar_todas(metricas, importancia, tmp_path)
    assert [c.name for c in caminhos] == [
        "pr_auc_por_janela.png",
        "calibracao_teste.png",
        "shap_temas.png",
    ]
    assert all(c.stat().st_size > 10_000 for c in caminhos)
