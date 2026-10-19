"""Testes do app com o AppTest do Streamlit: cada página abre sem erro, com e sem a chave do
Gemini, usando os dados da amostra (data/fixtures/vra/) e os arquivos versionados do modelo e do
monitoramento. Nenhum teste chama o Gemini."""

import re

import pytest
from streamlit.testing.v1 import AppTest

from fdr import config, painel
from fdr.config import RAIZ

APP = str(RAIZ / "app" / "streamlit_app.py")
TITULOS = {
    "paginas/inicio.py": "Pontualidade dos voos no Brasil",
    "paginas/pontualidade.py": "Quem atrasa, onde e quando",
    "paginas/previsao.py": "Qual a chance de o seu voo atrasar?",
    "paginas/buscar_voo.py": "Como o seu voo costuma se sair?",
    "paginas/monitoramento.py": "O modelo continua acertando?",
    "paginas/assistente.py": "Perguntas em português, respostas do banco",
    "paginas/sobre.py": "Como a previsão é feita, quanto ela acerta e onde ela erra",
}
PAGINAS = tuple(TITULOS)


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
    assert "Dados até jul/2026" in texto(app)
    assert "horas de atraso" in texto(app)
    assert "linkedin.com/in/eduardo-henrique15" in texto(app)  # o contato no rodapé


def test_pontualidade_resume_o_recorte(dados_do_app):
    app = abrir("paginas/pontualidade.py")
    sem_erros(app)
    assert "partiram com mais de 15 minutos de atraso" in texto(app)
    assert "Média das companhias do ranking" in texto(app)
    assert "Os piores dias do período" in texto(app)
    assert app.get("deck_gl_json_chart")  # o mapa de rotas


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
    # Trocar a hora refaz a previsão sem erro, e a escolha vai para a URL.
    app.selectbox(key="hora").set_value(18).run()
    sem_erros(app)
    assert app.query_params["hora"] == "18"
    assert app.query_params["modo"] == "voo"


def test_previsao_melhor_horario_e_comparacao(dados_do_app):
    app = abrir("paginas/previsao.py")
    app.session_state["modo"] = "melhor"
    app.run()
    sem_erros(app)
    pagina = texto(app)
    assert "A semana hora a hora" in pagina or "não dá para comparar horários" in pagina
    app.session_state["modo"] = "comparar"
    app.run()
    sem_erros(app)
    assert "De onde vem a diferença" in texto(app)
    assert app.query_params["b_hora"] == "18"  # o voo B começa em outro horário


def test_buscar_voo_mostra_o_historico_e_o_proximo_voo(dados_do_app, amostra_pipeline):
    con = painel.conectar_marts(amostra_pipeline / "marts")
    cia, numero = con.execute(
        "select cia, numero_voo from voos where tipo_linha = 'N' and situacao = 'REALIZADO' "
        "group by all order by count(*) desc, cia, numero_voo limit 1"
    ).fetchone()
    app = abrir("paginas/buscar_voo.py")
    sem_erros(app)
    # Código ICAO, com hífen e zeros à esquerda: a busca entende e mostra o código IATA.
    app.text_input(key="voo").set_value(f"{cia}-00{numero}").run()
    sem_erros(app)
    pagina = texto(app)
    rotulo = f"{painel.CODIGOS_IATA.get(cia, cia)}-{numero.lstrip('0')}"
    assert app.query_params["voo"] == rotulo
    assert "Partidas realizadas" in pagina
    assert "O próximo voo, pelo modelo" in pagina
    # Um número que não existe na base avisa, sem erro.
    app.text_input(key="voo").set_value("G3 99999").run()
    sem_erros(app)
    assert "Nenhuma partida nacional do voo G3 99999" in texto(app)


def test_sobre_mostra_onde_o_modelo_erra_e_a_regra_de_alerta(dados_do_app):
    app = abrir("paginas/sobre.py")
    sem_erros(app)
    assert "Onde o modelo erra" in texto(app)
    assert "Avisando os <b>10%</b>" in texto(app)
    for segmento in ("aeroporto_origem", "faixa_horaria", "mes"):
        app.session_state["segmento"] = segmento
        app.run()
        sem_erros(app)
    app.slider(key="fracao_alerta").set_value(25).run()
    sem_erros(app)
    assert "Avisando os <b>25%</b>" in texto(app)


def test_assistente_sem_chave_fica_em_modo_de_demonstracao(dados_do_app, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    app = abrir("paginas/assistente.py")
    assert "Modo de demonstração" in texto(app)
    assert "Como o assistente foi avaliado" in texto(app)  # o placar de eval/results/
    # A pergunta de exemplo responde com a gravada (data/demo/), sem chamar o Gemini, e mostra
    # as travas; a da evolução mês a mês ganha um gráfico de linha.
    app.button(key="exemplo_4").click().run()
    sem_erros(app)
    assert app.chat_message
    assert "Travas cumpridas" in texto(app)
    assert app.get("vega_lite_chart")


def test_pagina_com_erro_mostra_mensagem_sem_traceback(dados_do_app, monkeypatch):
    monkeypatch.setattr(config, "PASTA_MARTS", config.RAIZ / "pasta-que-nao-existe")
    app = abrir("paginas/inicio.py")
    assert not app.exception
    assert "Algo deu errado" in app.error[0].value
