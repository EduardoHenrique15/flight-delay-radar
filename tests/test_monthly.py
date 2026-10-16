"""Testes do monitoramento mensal: regra de retreino, promoção e histórico retroativo."""

from datetime import date

import numpy as np
import pytest
from sinteticos import dados_sinteticos

from fdr.monitoring import drift, monthly

DECISOES = {
    "modelo": "lightgbm",
    "parametros": {"num_leaves": 7, "min_child_samples": 50, "learning_rate": 0.1},
    "arvores": 20,
    "arvores_por_corte": [20],
    "calibracao": "crua",
    "janela_baseline": 12,
}


def avaliacao(ganho=0.01, ece=0.02, psi=None):
    return {"ganho_pr_auc": ganho, "modelo": {"ece": ece}, "psi": psi or {}}


def test_regra_nao_dispara_quando_tudo_esta_dentro_dos_limites():
    assert monthly.regra_retreino(avaliacao(ganho=0.0, ece=0.05), 5, ["hora"]) == []


@pytest.mark.parametrize(
    ("argumentos", "trecho"),
    [
        ({"ganho": -0.0001}, "perdeu do baseline"),
        ({"ece": 0.0501}, "ECE"),
        ({"psi": {"hora": drift.LIMITE_ALERTA}}, "PSI de 0.25 em hora"),
    ],
)
def test_cada_gatilho_dispara_o_retreino(argumentos, trecho):
    motivos = monthly.regra_retreino(avaliacao(**argumentos), 0, ["hora"])
    assert len(motivos) == 1 and trecho in motivos[0]


def test_psi_alto_em_variavel_pouco_importante_nao_dispara():
    assert monthly.regra_retreino(avaliacao(psi={"feriado": 0.9}), 0, ["hora"]) == []


def test_seis_meses_em_uso_disparam_o_retreino():
    assert monthly.regra_retreino(avaliacao(), 5, []) == []
    assert monthly.regra_retreino(avaliacao(), 6, []) == ["6 meses desde o último retreino"]


def test_desafiante_so_e_promovido_quando_ganha_com_folga():
    gerador = np.random.default_rng(3)
    dias = np.repeat(np.arange(30), 200)
    verdade = gerador.uniform(0.05, 0.5, len(dias))
    y = (gerador.uniform(size=len(dias)) < verdade).astype(int)
    ruim = np.clip(verdade + gerador.normal(0, 0.3, len(dias)), 0, 1)
    assert not monthly.comparar(y, ruim, ruim, dias)["promovido"]  # empate
    assert monthly.comparar(y, ruim, verdade, dias)["promovido"]  # o desafiante é melhor
    assert not monthly.comparar(y, verdade, ruim, dias)["promovido"]  # o desafiante é pior


def test_mes_menos():
    assert monthly.mes_menos(date(2026, 1, 1), 2) == date(2025, 11, 1)
    assert monthly.mes_menos(date(2025, 12, 1), -1) == date(2026, 1, 1)


@pytest.fixture(scope="module")
def simulacao():
    dados = dados_sinteticos(por_mes=300)
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(monthly, "MESES_MAXIMOS_SEM_RETREINO", 2)  # força retreinos
        mp.setattr("fdr.model.evaluate.AMOSTRAS_BOOTSTRAP", 30)
        return monthly.simular(
            dados,
            DECISOES,
            importantes=["hora_prevista_local"],
            fim_treino=date(2025, 10, 1),
            inicio=date(2025, 12, 1),
            fim=date(2026, 5, 1),
            avisar=lambda _: None,
        )


def test_simulacao_processa_os_meses_em_ordem(simulacao):
    meses = [m["mes"] for m in simulacao["meses"]]
    assert meses == [
        "2025-12-01",
        "2026-01-01",
        "2026-02-01",
        "2026-03-01",
        "2026-04-01",
        "2026-05-01",
    ]
    assert simulacao["campeao_inicial_treino"] == ["2023-01-01", "2025-10-01"]
    assert all(m["tipo"] == "simulacao" for m in simulacao["meses"])


def test_simulacao_nunca_olha_o_futuro(simulacao):
    """O campeão e cada desafiante só usam meses até M - 2 (o que estaria publicado)."""
    for entrada in simulacao["meses"]:
        limite = monthly.mes_menos(date.fromisoformat(entrada["mes"]), 2).isoformat()
        assert entrada["campeao_treino"][1] <= limite
        if entrada["retreino"]["disparou"]:
            assert entrada["retreino"]["desafiante_treino"][1] == limite


def test_retreino_dispara_e_contador_volta_a_zero_depois_de_cada_retreino(simulacao):
    retreinos = [m for m in simulacao["meses"] if m["retreino"]["disparou"]]
    assert retreinos, "com no máximo 2 meses sem retreino, a simulação precisa retreinar"
    for entrada in simulacao["meses"]:
        esperado = 0 if entrada["retreino"]["disparou"] else entrada["meses_em_uso"] + 1
        assert entrada["meses_em_uso_seguinte"] == esperado


def test_simulacao_exige_o_intervalo_de_2_meses():
    with pytest.raises(ValueError, match="2 meses"):
        monthly.simular(
            dados_sinteticos(por_mes=20),
            DECISOES,
            [],
            fim_treino=date(2025, 11, 1),
            inicio=date(2025, 12, 1),
            fim=date(2025, 12, 1),
        )


def test_historico_e_gravado_com_as_regras(tmp_path):
    caminho = tmp_path / "monitoring" / "history.json"
    historico = monthly.ler_historico(caminho)
    assert historico["producao"]["meses"] == []
    monthly.gravar_historico(historico, caminho)
    relido = monthly.ler_historico(caminho)
    assert relido["regras"]["ece_maximo"] == monthly.ECE_MAXIMO
