"""O gráfico automático da resposta (fdr.assistant.visual), o placar da avaliação
(fdr.assistant.eval.placar), as respostas de demonstração e os números de docs/assistente.md."""

import json
from datetime import date

import pandas as pd
import pytest

from fdr.assistant import eval as avaliacao
from fdr.assistant.llm import Cache
from fdr.assistant.visual import escolher
from fdr.config import RAIZ


def test_grafico_de_linha_para_meses_e_de_barras_para_rankings():
    meses = pd.DataFrame(
        {
            "mes": pd.to_datetime(["2026-01-01", "2026-02-01", "2026-03-01"]),
            "taxa": [0.1, 0.2, 0.15],
        }
    )
    linha = escolher(meses)
    assert (linha.tipo, linha.x, linha.y, linha.porcentagem) == ("linha", "mes", "taxa", True)

    ranking = pd.DataFrame({"nome": ["Azul", "Gol"], "cia": ["AZU", "GLO"], "voos": [741, 395]})
    barras = escolher(ranking)
    assert (barras.tipo, barras.x, barras.y, barras.porcentagem) == (
        "barras",
        "nome",
        "voos",
        False,
    )

    # A hora é rótulo, e a taxa vem antes da contagem.
    horas = pd.DataFrame({"hora_prevista": [22, 23], "taxa_atraso": [0.24, 0.22], "voos": [5, 4]})
    assert (escolher(horas).x, escolher(horas).y) == ("hora_prevista", "taxa_atraso")

    rotas = pd.DataFrame(
        {"origem": ["SBGR", "SBBE"], "destino": ["SBRF", "SBPA"], "km": [2100, 3000]}
    )
    assert escolher(rotas).x_extra == "destino"


def test_sem_grafico_para_um_numero_ou_tabelas_grandes():
    assert escolher(pd.DataFrame({"voos": [86746]})) is None
    assert escolher(pd.DataFrame({"nome": ["Gol"], "voos": [1]})) is None
    assert escolher(pd.DataFrame({"a": ["x", "y"], "b": ["z", "w"]})) is None
    grande = pd.DataFrame({"cidade": [f"c{i}" for i in range(40)], "voos": range(40)})
    assert escolher(grande) is None
    assert escolher(None) is None


def resultado(id_, categoria, acerto, sql="SELECT 1", origem="modelo"):
    return {
        "id": id_,
        "categoria": categoria,
        "pergunta": f"Pergunta {id_}",
        "origem": origem,
        "sql_gerado": sql,
        "explicacao": f"Explicação {id_}",
        "tentativas": 1,
        "latencia_s": 2.0,
        "acerto": acerto,
    }


def gravar(pasta, nome, lote, resultados, data="2026-10-17"):
    conteudo = {"data": data, "modelo": "modelo-x", "lote": lote, "resultados": resultados}
    (pasta / nome).write_text(json.dumps(conteudo), encoding="utf-8")


def test_placar_junta_o_ultimo_arquivo_de_cada_lote_e_a_revisao(tmp_path):
    gravar(tmp_path, "2026-10-17-lote1.json", 1, [resultado(1, "simples", False)])
    # Um arquivo mais novo do mesmo lote substitui o anterior.
    gravar(tmp_path, "2026-10-18-lote1.json", 1, [resultado(1, "simples", True)], "2026-10-18")
    gravar(
        tmp_path,
        "2026-10-19-lote2.json",
        2,
        [
            resultado(2, "agregacao", False),
            resultado(3, "agregacao", False),
            resultado(4, "recusa", True, sql=None, origem="recusa"),
        ],
        "2026-10-19",
    )
    revisao = tmp_path / "revisao.yaml"
    revisao.write_text(
        "- {id: 2, veredito: equivalente, nota: iguais}\n- {id: 3, veredito: erro, nota: x}\n",
        encoding="utf-8",
    )
    placar = avaliacao.placar(tmp_path, revisao)
    assert placar["perguntas"] == 4 and placar["lotes"] == 2
    assert (placar["acertos"], placar["acertos_revisados"]) == (2, 3)
    assert (placar["recusas_certas"], placar["recusas"]) == (1, 1)
    assert placar["sql_valido"] == placar["respondiveis"] == 3
    assert placar["datas"] == ["2026-10-18", "2026-10-19"]
    assert placar["por_categoria"] == {"simples": (1, 1), "agregacao": (0, 2), "recusa": (1, 1)}
    assert [e["veredito"] for e in placar["erradas"]] == ["equivalente", "erro"]
    assert avaliacao.placar(tmp_path / "vazia", revisao) is None


def test_demo_grava_so_as_marcadas_que_o_modelo_acertou(tmp_path, monkeypatch):
    monkeypatch.setattr(
        avaliacao,
        "ler_perguntas",
        lambda: [{"id": 1, "demo": True}, {"id": 2, "demo": True}, {"id": 3}],
    )
    gravar(
        tmp_path,
        "2026-10-17-lote1.json",
        1,
        [
            resultado(1, "simples", True),
            resultado(2, "simples", False),
            resultado(3, "simples", True),
        ],
    )
    destino = tmp_path / "demo.json"
    assert avaliacao.gravar_demo(tmp_path, destino) == 1
    assert Cache(destino).perguntas() == ["Pergunta 1"]


PLACAR = avaliacao.placar()


@pytest.mark.skipif(PLACAR is None, reason="sem eval/results/")
def test_docs_e_readmes_usam_os_numeros_da_avaliacao():
    textos = {
        "docs/assistente.md": (",", " de "),
        "README.md": (",", " de "),
        "README.en.md": (".", " of "),
    }
    for arquivo, (decimal, de) in textos.items():
        texto = (RAIZ / arquivo).read_text(encoding="utf-8")
        taxa = f"{PLACAR['acertos'] / PLACAR['perguntas']:.1%}".replace(".", decimal)
        esperados = [
            f"{PLACAR['acertos']}{de}{PLACAR['perguntas']}",
            f"{PLACAR['acertos_revisados']}{de}{PLACAR['perguntas']}",
            taxa,
        ]
        faltando = [n for n in esperados if n not in texto]
        assert not faltando, f"{arquivo} sem os números de eval/results/: {faltando}"


@pytest.mark.skipif(PLACAR is None, reason="sem eval/results/")
def test_docs_listam_as_categorias_e_as_revisadas():
    texto = (RAIZ / "docs" / "assistente.md").read_text(encoding="utf-8")
    for nome, (certas, total) in PLACAR["por_categoria"].items():
        assert f"{certas} de {total}" in texto, nome
    for erro in PLACAR["erradas"]:
        assert f"| {erro['id']} |" in texto, erro["id"]
    assert date.fromisoformat(PLACAR["datas"][0])  # as datas são ISO
