"""Testes da validação dos modelos: variáveis permitidas, regra de 1 erro-padrão, calibração e um
teste de fumaça do fluxo completo em dados sintéticos pequenos."""

from datetime import date

import duckdb
import numpy as np
import pandas as pd
import pytest

from fdr.features.build import ALVO, COLUNAS_SO_ANALISE, PROIBIDAS
from fdr.model import train
from fdr.model.splits import definir_divisao


def test_nenhuma_variavel_proibida_ou_alvo_entra_no_modelo():
    assert not set(train.VARIAVEIS) & PROIBIDAS
    # A malha realizada do mês sai junto com os atrasos: o app não teria esse dado.
    assert not set(train.VARIAVEIS) & COLUNAS_SO_ANALISE
    assert ALVO not in train.VARIAVEIS
    assert len(set(train.VARIAVEIS)) == len(train.VARIAVEIS)


def dados_sinteticos(por_mes: int = 400, semente: int = 0) -> pd.DataFrame:
    """Jan/2023 a ago/2026 no formato da features_voos. O atraso depende da companhia, da hora e
    de uma taxa histórica com ruído, para os modelos terem o que aprender."""
    gerador = np.random.default_rng(semente)
    meses = pd.date_range("2023-01-01", "2026-08-01", freq="MS")
    n = por_mes * len(meses)
    mes = np.repeat(meses.to_numpy(), por_mes)
    cia = gerador.choice(["AZU", "GLO", "TAM"], n)
    hora = gerador.integers(0, 24, n)
    logito = -1.8 + 0.6 * (cia == "GLO") + 0.05 * (hora - 12)
    verdade = 1 / (1 + np.exp(-logito))
    dados = pd.DataFrame(
        {
            "mes": mes,
            "data_prevista": mes + pd.to_timedelta(gerador.integers(0, 28, n), unit="D"),
            ALVO: (gerador.uniform(size=n) < verdade).astype("int8"),
            "cia": pd.Categorical(cia),
            "origem": pd.Categorical(gerador.choice(["SBGR", "SBSP", "SBBR", "SBKP"], n)),
            "destino": pd.Categorical(gerador.choice(["SBRJ", "SBCF", "SBPA"], n)),
            "hora_prevista_local": hora,
            "dia_semana": gerador.integers(1, 8, n),
            "mes_do_ano": pd.DatetimeIndex(mes).month,
        }
    )
    for coluna in train.BINARIAS:
        dados[coluna] = (gerador.uniform(size=n) < 0.05).astype(int)
    for coluna in train.CONTINUAS:
        dados[coluna] = gerador.uniform(0, 300, n)
    for coluna in train.HISTORICO:
        if coluna.startswith("taxa_"):
            valores = np.clip(verdade + gerador.normal(0, 0.05, n), 0, 1)
            if "global" not in coluna:
                valores[gerador.uniform(size=n) < 0.1] = np.nan  # sem histórico
        else:
            valores = gerador.integers(0, 500, n)
        dados[coluna] = valores
    numericas = [c for c in train.VARIAVEIS if c not in train.CATEGORICAS]
    dados[numericas] = dados[numericas].astype("float32")
    return dados


def test_matriz_usa_codigos_das_categorias_e_seleciona_linhas():
    dados = pd.DataFrame(
        {coluna: [1.0, 2.0, 3.0] for coluna in train.VARIAVEIS if coluna not in train.CATEGORICAS}
    )
    for coluna in train.CATEGORICAS:
        dados[coluna] = pd.Categorical(["A", None, "B"])
    x = train.matriz(dados, np.array([True, True, False]))
    cia = train.VARIAVEIS.index("cia")
    assert x.dtype == np.float32 and x.shape == (2, len(train.VARIAVEIS))
    assert x[0, cia] == 0 and np.isnan(x[1, cia])
    assert x[:, train.VARIAVEIS.index("dia_semana")].tolist() == [1.0, 2.0]


def test_regra_de_um_erro_padrao_fica_com_o_mais_simples_dentro_da_margem():
    pr_auc = {
        "baseline": [0.20, 0.25, 0.30, 0.22, 0.27],
        "logistica": [0.230, 0.279, 0.333, 0.251, 0.299],
        "lightgbm": [0.231, 0.281, 0.329, 0.252, 0.301],
    }
    escolha = train.regra_um_erro_padrao(pr_auc)
    assert escolha["melhor"] == "lightgbm"
    assert escolha["escolhido"] == "logistica"  # 0,0004 abaixo, dentro do erro-padrão
    assert not escolha["candidatos"]["baseline"]["dentro_de_1_erro_padrao"]


def test_regra_de_um_erro_padrao_fica_com_o_melhor_quando_ele_ganha_sempre():
    pr_auc = {
        "baseline": [0.20, 0.25, 0.30, 0.22, 0.27],
        "logistica": [0.22, 0.27, 0.32, 0.24, 0.29],
        "lightgbm": [0.25, 0.31, 0.35, 0.27, 0.33],
    }
    assert train.regra_um_erro_padrao(pr_auc)["escolhido"] == "lightgbm"


def test_calibracao_corrige_probabilidades_infladas():
    gerador = np.random.default_rng(1)
    previsoes = []
    for _ in range(5):
        verdade = gerador.uniform(0.02, 0.4, 20_000)
        y = (gerador.uniform(size=verdade.size) < verdade).astype(float)
        previsoes.append(train.Previsoes(y, np.clip(verdade * 1.8, 0, 1)))  # o dobro, quase
    resultado = train.comparar_calibracao(previsoes)
    media = resultado["media"]
    assert resultado["escolhida"] in {"isotonica", "platt"}
    assert media[resultado["escolhida"]]["brier"] < media["crua"]["brier"]
    assert len(resultado["por_corte"]["crua"]) == 4  # o primeiro corte só serve de ajuste


def test_carregar_nao_le_os_meses_do_teste():
    dados = dados_sinteticos(por_mes=5)
    dados["cia"] = dados["cia"].astype(str)
    dados["origem"] = dados["origem"].astype(str)
    dados["destino"] = dados["destino"].astype(str)
    with duckdb.connect() as con:
        con.register("sinteticos", dados)
        con.execute("""
            create table features_voos as
            select * replace (mes::date as mes, data_prevista::date as data_prevista)
            from sinteticos
        """)
        meses = train.meses_disponiveis(con)
        lidos = train.carregar(con, antes_de=date(2026, 6, 1))
    assert meses[-1] == date(2026, 8, 1)
    assert lidos["mes"].max() == pd.Timestamp("2026-05-01")
    assert all(lidos[c].dtype == "category" for c in train.CATEGORICAS)


@pytest.fixture(scope="module")
def validacao():
    dados = dados_sinteticos()
    divisao = definir_divisao(sorted(d.date() for d in dados["mes"].unique()))
    dados = dados[dados["mes"] < pd.Timestamp(divisao.teste[0])]
    grade = (
        {"num_leaves": 7, "min_child_samples": 50, "learning_rate": 0.1},
        {"num_leaves": 15, "min_child_samples": 50, "learning_rate": 0.1},
    )
    return dados, divisao, grade, train.validar(dados, divisao, grade=grade, avisar=lambda _: None)


def test_validacao_completa_em_dados_sinteticos(validacao):
    _, divisao, grade, resultado = validacao
    assert set(resultado["validacao_cruzada"]) == set(train.MODELOS)
    assert all(len(v) == len(divisao.cortes) for v in resultado["validacao_cruzada"].values())
    assert len(resultado["lightgbm"]["busca"]["resultados"]) == len(grade)
    assert resultado["lightgbm"]["parametros"] in [dict(p) for p in grade]
    assert resultado["escolha"]["escolhido"] in train.MODELOS
    assert set(resultado["calibracao"]) == {"logistica", "lightgbm"}
    # A validação nunca passa do fim da validação principal (o teste fica de fora).
    ultimo = max(c["periodo"][1] for v in resultado["validacao_cruzada"].values() for c in v)
    assert ultimo == divisao.validacao_principal.validacao[1].isoformat()
    # Há sinal nos dados: os modelos com aprendizado batem o acaso.
    resumo = resultado["resumo"]
    assert resumo["logistica"]["roc_auc_medio"] > 0.55  # o acaso dá 0,5
    assert resumo["lightgbm"]["roc_auc_medio"] > 0.55


def test_validacao_e_reprodutivel(validacao):
    dados, divisao, grade, resultado = validacao
    de_novo = train.validar(dados, divisao, grade=grade[:1], avisar=lambda _: None)
    primeira = next(r for r in resultado["lightgbm"]["busca"]["resultados"] if r["num_leaves"] == 7)
    assert de_novo["lightgbm"]["busca"]["resultados"][0] == primeira
    assert de_novo["validacao_cruzada"]["logistica"] == resultado["validacao_cruzada"]["logistica"]


def test_parada_antecipada_usa_os_ultimos_meses_do_treino(monkeypatch):
    dados = dados_sinteticos(por_mes=100)
    tamanhos = {}
    original = train.lgb.train

    def espiar(parametros, base, **kwargs):
        tamanhos["ajuste"] = len(base.label)
        tamanhos["parada"] = len(kwargs["valid_sets"][0].label)
        return original(parametros, base, **kwargs)

    monkeypatch.setattr(train.lgb, "train", espiar)
    parametros = {"num_leaves": 7, "min_child_samples": 20, "learning_rate": 0.1}
    train.treinar_lightgbm(dados, (date(2023, 1, 1), date(2023, 12, 1)), parametros, 20)
    assert tamanhos == {"ajuste": 9 * 100, "parada": train.MESES_PARADA * 100}
