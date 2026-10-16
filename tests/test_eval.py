"""Testes da avaliação do assistente: comparação de resultados, métricas e perguntas."""

import json
from collections import Counter

import pandas as pd
import pytest

from fdr.assistant import eval as avaliacao
from fdr.assistant import guard, schema
from fdr.assistant.llm import LLMFalso, normalizar


def test_resultado_igual_com_coluna_a_mais_e_outra_ordem():
    referencia = pd.DataFrame({"cia": ["GLO", "AZU"], "voos": [10, 20]})
    gerado = pd.DataFrame({"nome": ["Azul", "Gol"], "cia": ["AZU", "GLO"], "total": [20.0, 10.0]})
    assert avaliacao.mesmo_resultado(gerado, referencia)


def test_tolerancia_numerica_e_datas():
    referencia = pd.DataFrame({"taxa": [0.153412], "mes": [pd.Timestamp("2026-07-01")]})
    gerado = pd.DataFrame({"mes": ["2026-07-01"], "taxa": [0.15341]})
    assert avaliacao.mesmo_resultado(gerado, referencia)


@pytest.mark.parametrize(
    "gerado",
    [
        pd.DataFrame({"cia": ["GLO"]}),  # linha a menos
        pd.DataFrame({"cia": ["GLO", "TAM"], "voos": [10, 20]}),  # valor diferente
        pd.DataFrame({"cia": ["GLO", "AZU"]}),  # falta a coluna voos
    ],
)
def test_resultados_diferentes(gerado):
    referencia = pd.DataFrame({"cia": ["GLO", "AZU"], "voos": [10, 20]})
    assert not avaliacao.mesmo_resultado(gerado, referencia)


def test_perguntas_da_avaliacao():
    perguntas = avaliacao.ler_perguntas()
    assert len(perguntas) == 31
    assert len({p["id"] for p in perguntas}) == 31
    assert Counter(p["categoria"] for p in perguntas) == {
        "simples": 10,
        "agregacao": 8,
        "juncao": 5,
        "tempo": 5,
        "recusa": 3,
    }
    for p in perguntas:
        if p.get("recusar"):
            assert "sql" not in p
        else:
            guard.validar(p["sql"], set(schema.TABELAS))  # o SQL de referência passa nas travas
    assert sum(1 for p in perguntas if p.get("demo")) >= 6


def test_avaliacao_com_llm_falso(banco, tmp_path):
    perguntas = [
        {
            "id": 1,
            "categoria": "simples",
            "pergunta": "Quantos voos a Gol fez?",
            "sql": "SELECT count(*) FROM voos WHERE cia = 'GLO'",
        },
        {
            "id": 2,
            "categoria": "simples",
            "pergunta": "Quantos voos a Azul fez?",
            "sql": "SELECT count(*) FROM voos WHERE cia = 'AZU'",
        },
        {"id": 3, "categoria": "recusa", "pergunta": "Qual o preço da passagem?", "recusar": True},
    ]
    certo = {
        "pode_responder": True,
        "explicacao": "ok",
        "sql": "select count(*) as n, 'GLO' as cia from voos where cia = 'GLO'",
    }
    errado = {"pode_responder": True, "explicacao": "ok", "sql": "select count(*) from voos"}
    recusa = {"pode_responder": False, "explicacao": "Sem preços.", "sql": ""}
    llm = LLMFalso(
        {
            normalizar(p["pergunta"]): [r]
            for p, r in zip(perguntas, [certo, errado, recusa], strict=True)
        }
    )
    assistente = avaliacao.assistente_para_avaliacao(llm, banco, tmp_path)
    resultados = avaliacao.avaliar(assistente, perguntas, guard.conectar(banco))
    assert [r["acerto"] for r in resultados] == [True, False, True]
    resumo = avaliacao.resumo(resultados)
    assert resumo["acerto_execucao"] == 0.5 and resumo["recusa_correta"] == 1.0
    assert resumo["por_categoria"] == {"recusa": 1.0, "simples": 0.5}

    pasta = tmp_path / "results"
    pasta.mkdir()
    (pasta / "2026-10-16-lote1.json").write_text(
        json.dumps({"resultados": resultados}, default=str), encoding="utf-8"
    )
    destino = tmp_path / "demo.json"
    perguntas_reais = avaliacao.ler_perguntas
    try:
        avaliacao.ler_perguntas = lambda: [{"id": 1, "demo": True}, {"id": 2, "demo": True}]
        assert avaliacao.gravar_demo(pasta, destino) == 1  # só a que acertou
    finally:
        avaliacao.ler_perguntas = perguntas_reais
    gravada = json.loads(destino.read_text(encoding="utf-8"))
    assert list(gravada) == [normalizar("Quantos voos a Gol fez?")]
