"""Testes do app com o AppTest do Streamlit: cada página abre sem erro, com e sem a chave do
Gemini, usando os dados da amostra (data/fixtures/vra/) e os arquivos versionados do modelo e do
monitoramento. Nenhum teste chama o Gemini."""

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

from fdr import config
from fdr.config import RAIZ

APP = str(RAIZ / "app" / "streamlit_app.py")
TITULOS = {
    "paginas/inicio.py": "Flight Delay Radar",
    "paginas/pontualidade.py": "Pontualidade",
    "paginas/previsao.py": "Previsão de atraso",
    "paginas/monitoramento.py": "Monitoramento",
    "paginas/assistente.py": "Pergunte aos dados",
    "paginas/sobre.py": "Sobre o modelo",
}
PAGINAS = tuple(TITULOS)


@pytest.fixture
def dados_do_app(amostra_pipeline, tmp_path, monkeypatch):
    """O app lendo os marts da amostra; o banco do assistente é recriado numa pasta temporária."""
    monkeypatch.setattr(config, "PASTA_MARTS", amostra_pipeline / "marts")
    monkeypatch.setattr(config, "BANCO_APP", tmp_path / "app.duckdb")
    st.cache_data.clear()
    st.cache_resource.clear()
    yield
    st.cache_data.clear()
    st.cache_resource.clear()


def abrir(pagina: str) -> AppTest:
    app = AppTest.from_file(APP, default_timeout=60)
    app.run()
    if pagina != PAGINAS[0]:
        app.switch_page(pagina).run()
    return app


def sem_erros(app: AppTest) -> None:
    assert not app.exception, [e.value for e in app.exception]
    assert not app.error, [e.value for e in app.error]


@pytest.mark.parametrize("com_chave", [False, True], ids=["sem_chave", "com_chave"])
@pytest.mark.parametrize("pagina", PAGINAS)
def test_cada_pagina_abre_sem_erro(dados_do_app, monkeypatch, pagina, com_chave):
    if com_chave:
        monkeypatch.setenv("GEMINI_API_KEY", "chave-falsa")  # o cliente só conecta ao perguntar
    else:
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    app = abrir(pagina)
    sem_erros(app)
    assert app.title[0].value == TITULOS[pagina]


def test_inicio_mostra_os_numeros_do_ultimo_mes(dados_do_app):
    app = abrir("paginas/inicio.py")
    rotulos = [m.label for m in app.metric]
    assert "Voos nacionais realizados" in rotulos
    assert "Último mês publicado: jul/2026" in [s.value for s in app.subheader]


def test_previsao_mostra_a_chance_e_os_fatores(dados_do_app):
    app = abrir("paginas/previsao.py")
    sem_erros(app)
    chance = next(m for m in app.metric if m.label.startswith("Chance"))
    assert chance.value.endswith("%")
    # Trocar a hora refaz a previsão sem erro.
    app.selectbox[-1].set_value(18).run()
    sem_erros(app)


def test_assistente_sem_chave_fica_em_modo_de_demonstracao(dados_do_app, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    app = abrir("paginas/assistente.py")
    assert any("Modo de demonstração" in i.value for i in app.info)
    app.button[0].click().run()  # pergunta de exemplo: responde sem chamar o Gemini
    sem_erros(app)
    assert app.chat_message


def test_pagina_com_erro_mostra_mensagem_sem_traceback(dados_do_app, monkeypatch):
    monkeypatch.setattr(config, "PASTA_MARTS", config.RAIZ / "pasta-que-nao-existe")
    app = abrir("paginas/inicio.py")
    assert not app.exception
    assert "Algo deu errado" in app.error[0].value
