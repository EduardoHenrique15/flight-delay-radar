"""Testes do app com o AppTest do Streamlit: cada página abre sem erro, com e sem a chave do
Gemini, usando os dados da amostra (data/fixtures/vra/) e os arquivos versionados do modelo e do
monitoramento. Nenhum teste chama o Gemini."""

import re

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

from fdr import config
from fdr.config import RAIZ

APP = str(RAIZ / "app" / "streamlit_app.py")
TITULOS = {
    "paginas/inicio.py": "Pontualidade dos voos no Brasil",
    "paginas/pontualidade.py": "Quem atrasa, onde e quando",
    "paginas/previsao.py": "Qual a chance de o seu voo atrasar?",
    "paginas/monitoramento.py": "O modelo continua acertando?",
    "paginas/assistente.py": "Perguntas em português, respostas do banco",
    "paginas/sobre.py": "Como a previsão é feita, quanto ela acerta e onde ela erra",
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


def texto(app: AppTest) -> str:
    """Todo o texto em Markdown/HTML da página (títulos e cartões são HTML próprio)."""
    return "\n".join(m.value for m in app.markdown)


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
    assert f'<h1 class="fdr-titulo">{TITULOS[pagina]}</h1>' in texto(app)


def test_inicio_mostra_os_numeros_do_ultimo_mes(dados_do_app):
    app = abrir("paginas/inicio.py")
    assert "Voos nacionais realizados" in texto(app)
    assert "Dados da ANAC até jul/2026" in texto(app)


def test_pontualidade_resume_o_recorte(dados_do_app):
    app = abrir("paginas/pontualidade.py")
    sem_erros(app)
    assert "partiram com mais de 15 minutos de atraso" in texto(app)
    assert "Média das companhias do ranking" in texto(app)


def test_monitoramento_mostra_a_linha_do_tempo(dados_do_app):
    app = abrir("paginas/monitoramento.py")
    sem_erros(app)
    assert 'class="fdr-rota"' in texto(app)
    assert "treino do campeão" in texto(app)


def test_previsao_mostra_a_chance_e_os_fatores(dados_do_app):
    app = abrir("paginas/previsao.py")
    sem_erros(app)
    pagina = texto(app)
    assert "Chance de atrasar mais de 15 min" in pagina
    assert re.search(r'class="chance">\d+,\d%<', pagina)
    assert "O que mais pesou nesta previsão" in pagina
    # Trocar a hora refaz a previsão sem erro.
    app.selectbox[-1].set_value(18).run()
    sem_erros(app)


def test_assistente_sem_chave_fica_em_modo_de_demonstracao(dados_do_app, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    app = abrir("paginas/assistente.py")
    assert "Modo de demonstração" in texto(app)
    app.button[0].click().run()  # pergunta de exemplo: responde sem chamar o Gemini
    sem_erros(app)
    assert app.chat_message


def test_pagina_com_erro_mostra_mensagem_sem_traceback(dados_do_app, monkeypatch):
    monkeypatch.setattr(config, "PASTA_MARTS", config.RAIZ / "pasta-que-nao-existe")
    app = abrir("paginas/inicio.py")
    assert not app.exception
    assert "Algo deu errado" in app.error[0].value
