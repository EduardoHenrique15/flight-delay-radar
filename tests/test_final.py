"""Teste de fumaça do treino final (em dados sintéticos, em segundos) e do registro do modelo."""

import time

import numpy as np
import pytest
from sinteticos import dados_sinteticos

from fdr.model import final, registry, train
from fdr.model.splits import definir_divisao

DECISOES = {
    "modelo": "lightgbm",
    "parametros": {"num_leaves": 15, "min_child_samples": 50, "learning_rate": 0.1},
    "arvores": 30,
    "arvores_por_corte": [20, 30, 40],
    "calibracao": "crua",
    "janela_baseline": 12,
}


def validacao_salva(**mudancas) -> dict:
    validacao = {
        "escolha": {"escolhido": "lightgbm"},
        "lightgbm": {
            "parametros": DECISOES["parametros"],
            "arvores_por_corte": [165, 16, 528, 236, 219],
        },
        "calibracao": {"lightgbm": {"escolhida": "crua"}},
        "janela_baseline": "12m",
    }
    validacao.update(mudancas)
    return {"validacao_modelos": validacao}


def test_decisoes_vem_da_validacao_com_a_mediana_das_arvores():
    decisoes = final.ler_decisoes(validacao_salva())
    assert decisoes["arvores"] == 219
    assert decisoes["parametros"] == DECISOES["parametros"]
    assert decisoes["janela_baseline"] == 12


def test_sem_validacao_ou_com_outro_modelo_o_treino_final_para():
    with pytest.raises(final.DecisoesAusentesError, match="stage validacao"):
        final.ler_decisoes({})
    with pytest.raises(final.DecisoesAusentesError, match="logistica"):
        final.ler_decisoes(validacao_salva(escolha={"escolhido": "logistica"}))


@pytest.fixture(scope="module")
def treinado():
    dados = dados_sinteticos()
    divisao = definir_divisao(sorted(d.date() for d in dados["mes"].unique()))
    inicio = time.perf_counter()
    modelo = final.treinar_final(dados, divisao, DECISOES)
    resultado = final.avaliar_teste(modelo, dados, divisao, janela=12)
    return dados, divisao, modelo, resultado, time.perf_counter() - inicio


def test_fumaca_do_treino_final_em_menos_de_30_segundos(treinado):
    dados, divisao, modelo, resultado, segundos = treinado
    assert segundos < 30
    assert modelo.booster.num_trees() == DECISOES["arvores"]
    assert modelo.metadados["treino"] == [d.isoformat() for d in divisao.treino_final]
    # O treino final termina 2 meses antes do teste (intervalo de 1 mês, ADR 003).
    assert modelo.metadados["treino"][1] == "2026-04-01"
    assert resultado["periodo"] == ["2026-06-01", "2026-08-01"]
    assert resultado["voos"] == 3 * 400
    assert set(resultado["segmentos"]) == {"companhia", "aeroporto_origem", "faixa_horaria", "mes"}
    for nome in ("pr_auc", "roc_auc", "brier", "ece"):
        assert nome in resultado["ganho_sobre_baseline_intervalo_95"]
    assert resultado["roc_auc"] > 0.55  # há sinal nos dados sintéticos


def test_treino_final_e_reprodutivel(treinado):
    dados, divisao, modelo, _, _ = treinado
    de_novo = final.treinar_final(dados, divisao, DECISOES)
    teste = train.no_periodo(dados, *divisao.teste)
    np.testing.assert_allclose(de_novo.prever(teste), modelo.prever(teste))
    assert de_novo.metadados["hash_dados_treino"] == modelo.metadados["hash_dados_treino"]


def test_modelo_salvo_e_carregado_preve_igual(treinado, tmp_path):
    dados, divisao, modelo, _, _ = treinado
    pasta = tmp_path / "Área de Trabalho"  # acento no caminho, como no Windows do Eduardo
    modelo.salvar(pasta)
    carregado = registry.ModeloAtraso.carregar(pasta)
    teste = train.no_periodo(dados, *divisao.teste).copy()
    np.testing.assert_allclose(carregado.prever(teste), modelo.prever(teste))
    # Categoria que o treino não viu (companhia nova) não quebra a previsão.
    teste["cia"] = teste["cia"].astype("string").where(teste.index % 2 == 0, "NOVA")
    assert np.isfinite(carregado.prever(teste)).all()


def test_perfil_de_referencia_soma_um_em_cada_variavel(treinado):
    dados, divisao, _, _, _ = treinado
    perfil = registry.perfil_de_referencia(train.no_periodo(dados, *divisao.treino_final))
    assert set(perfil) == set(train.VARIAVEIS)
    for coluna, info in perfil.items():
        total = info["ausentes"] + sum(
            info["frequencias"].values() if info["tipo"] == "categorica" else info["frequencias"]
        )
        total += info.get("outras", 0.0)
        assert total == pytest.approx(1.0), coluna
