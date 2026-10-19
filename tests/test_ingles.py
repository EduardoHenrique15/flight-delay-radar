"""O app em inglês: cada página abre sem erro, todo texto passado por `t()` tem tradução e o
texto visível não sobra em português. Usa os dados da amostra, como tests/test_app.py."""

import re

import pytest
from streamlit.testing.v1 import AppTest
from test_app import APP, PAGINAS, sem_erros

from fdr import idioma
from fdr.traducoes import MODULOS, TEXTOS

# Palavras que só existem em português. Nomes próprios (São Paulo, Brasília, aeroportos como
# "Piloto Osvaldo Marques Dias") não entram, nem o "/ Partidas" de propósito do painel.
PORTUGUES = re.compile(
    r"\b(voos?|atrasos?|horários?|companhias?|previsão|não|você|média|também|aeroportos?|"
    r"semana|meses|mês|chance de|taxa de)\b|(?<!/ )\bpartidas?\b|ção\b|ções\b",
    re.IGNORECASE,
)


def abrir_em_ingles(pagina: str) -> AppTest:
    app = AppTest.from_file(APP, default_timeout=60)
    app.session_state["idioma"] = "en"
    app.run()
    if pagina != PAGINAS[0]:
        app.switch_page(pagina).run()
    return app


def textos_visiveis(app: AppTest) -> list[str]:
    """O texto das páginas (sem o CSS e sem as tags) e os rótulos e opções dos widgets."""
    textos = []
    for bloco in app.markdown:
        if bloco.value.lstrip().startswith("<style"):
            continue
        textos.append(re.sub(r"<[^>]+>", " ", bloco.value))

    def percorrer(no) -> None:
        for filho in getattr(no, "children", {}).values():
            proto = getattr(filho, "proto", None)
            if proto is not None and not hasattr(filho, "children"):
                for campo in ("label", "placeholder", "help"):
                    textos.append(str(getattr(proto, campo, "") or ""))
                for opcao in getattr(proto, "options", []):
                    textos.append(str(getattr(opcao, "content", opcao)))
            percorrer(filho)

    percorrer(app.main)
    return textos


def sobra_em_portugues(app: AppTest) -> list[str]:
    return [texto.strip()[:120] for texto in textos_visiveis(app) if PORTUGUES.search(texto)]


@pytest.mark.parametrize("pagina", PAGINAS)
def test_pagina_em_ingles_sem_erro_e_sem_texto_faltando(dados_do_app, pagina):
    idioma.FALTANDO.clear()
    app = abrir_em_ingles(pagina)
    sem_erros(app)
    assert not idioma.FALTANDO, sorted(idioma.FALTANDO)
    assert not sobra_em_portugues(app)
    assert app.query_params["lang"] == "en"


def test_traducoes_sem_conflito_e_com_os_mesmos_campos():
    vistos: dict[str, str] = {}
    for modulo in MODULOS:
        for chave, traducao in modulo.TEXTOS.items():
            assert vistos.setdefault(chave, traducao) == traducao, f"tradução diferente: {chave}"
    campos = re.compile(r"\{(\w*)\}")
    diferentes = [
        chave
        for chave, traducao in TEXTOS.items()
        if sorted(campos.findall(chave)) != sorted(campos.findall(traducao))
    ]
    assert not diferentes, diferentes


def test_numeros_e_datas_em_ingles():
    from datetime import date

    from fdr import painel

    try:
        idioma.definir("en")
        assert painel.porcentagem(0.1234) == "12.3%"
        assert painel.numero(1234567) == "1,234,567"
        assert painel.nome_mes(date(2026, 8, 1)) == "Aug 2026"
        assert painel.data(date(2026, 10, 20)) == "Oct 20, 2026"
        assert painel.DIAS_SEMANA[0] == "Mon"
    finally:
        idioma.definir("pt")
    assert painel.porcentagem(0.1234) == "12,3%"
    assert painel.numero(1234567) == "1.234.567"
    assert painel.DIAS_SEMANA[0] == "seg"


def test_sobre_e_assistente_em_ingles_com_interacoes(dados_do_app, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    idioma.FALTANDO.clear()
    app = abrir_em_ingles("paginas/sobre.py")
    for segmento in ("companhia", "aeroporto_origem", "faixa_horaria", "mes"):
        app.session_state["segmento"] = segmento
        app.run()
        sem_erros(app)
        assert not sobra_em_portugues(app)
    app.slider(key="fracao_alerta").set_value(25).run()
    sem_erros(app)
    assert "Alerting the <b>25%</b>" in "\n".join(m.value for m in app.markdown)

    app = abrir_em_ingles("paginas/assistente.py")
    app.button(key="exemplo_0").click().run()  # sem chave: modo de demonstração
    sem_erros(app)
    pagina = "\n".join(m.value for m in app.markdown)
    # Com as respostas gravadas (data/demo/), o exemplo responde com a de demonstração.
    assert "Saved demo answer" in pagina and "Guardrails passed" in pagina
    assert "How the assistant was evaluated" in pagina
    assert not idioma.FALTANDO, sorted(idioma.FALTANDO)
    assert not sobra_em_portugues(app)
