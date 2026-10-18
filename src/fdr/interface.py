"""Peças comuns às páginas do app Streamlit: recursos em cache, estilo, gráficos e tratamento de
erros.

- Dados com `st.cache_data` e recursos (conexões, modelo, assistente) com `st.cache_resource`.
- Toda página roda dentro de `pagina_protegida`: um erro vira uma mensagem clara para o usuário
  e o traceback vai só para o log.
- A chave do Gemini vem dos secrets do Streamlit ou da variável GEMINI_API_KEY. Sem chave, só o
  assistente muda (modo de demonstração).
"""

import logging
import os
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager

import altair as alt
import pandas as pd
import streamlit as st

from fdr import config, painel
from fdr.assistant.agent import Assistente, criar_assistente
from fdr.previsao import Previsor

log = logging.getLogger("fdr.app")

REPOSITORIO = "https://github.com/eduardohenrique15/flight-delay-radar"
AMBAR = "#F5A524"
CINZA = "#8A94A6"
AZUL = "#5B8DEF"

AJUDA = {
    "pr_auc": "PR-AUC: mede se o modelo põe os voos que atrasam no topo da lista de risco. "
    "Vai de 0 a 1; um palpite ao acaso fica perto da taxa de atraso (cerca de 0,15).",
    "brier": "Brier: erro médio entre a probabilidade prevista e o que aconteceu (0 ou 1). "
    "Quanto menor, melhor.",
    "ece": "ECE: diferença média entre a probabilidade prevista e a taxa real, por faixas. "
    'Mede se "20% de chance" quer dizer 20% mesmo.',
    "psi": "PSI: quanto a distribuição de uma variável mudou em relação ao treino. Abaixo de "
    "0,10: estável; de 0,10 a 0,25: atenção; acima de 0,25: mudança forte.",
    "baseline": "Baseline: a taxa de atraso da rota naquele horário nos últimos 12 meses. É a "
    "régua que o modelo precisa vencer.",
}

CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@500&display=swap');
[data-testid="stMetricValue"] {{
    font-family: 'JetBrains Mono', ui-monospace, monospace;
    color: {AMBAR};
}}
.fdr-subtitulo {{ color: {CINZA}; font-size: 1.05rem; margin-top: -0.6rem; }}
.fdr-faixa {{ font-family: 'JetBrains Mono', ui-monospace, monospace; font-weight: 600; }}
</style>
"""


def configurar_pagina() -> None:
    st.set_page_config(page_title="Flight Delay Radar", page_icon="✈️", layout="wide")
    st.markdown(CSS, unsafe_allow_html=True)


def titulo(texto: str, subtitulo: str) -> None:
    st.title(texto)
    st.markdown(f'<p class="fdr-subtitulo">{subtitulo}</p>', unsafe_allow_html=True)


@contextmanager
def pagina_protegida() -> Iterator[None]:
    """Nenhum traceback chega ao usuário: a mensagem é curta e o detalhe vai para o log."""
    try:
        yield
    except Exception:
        log.exception("Erro na página")
        st.error(
            "Algo deu errado ao montar esta página. Tente recarregar; se continuar, os dados "
            "podem estar sendo atualizados."
        )


# Recursos ---------------------------------------------------------------------------------------


@st.cache_resource(show_spinner=False)
def _conexao_marts():
    return painel.conectar_marts()


def consultar(funcao: Callable, *args):
    """Roda uma consulta de fdr.painel num cursor próprio (o DuckDB não divide uma conexão entre
    threads, e cada sessão do Streamlit roda numa thread)."""
    with _conexao_marts().cursor() as cursor:
        return funcao(cursor, *args)


@st.cache_data(show_spinner=False, ttl=3600)
def dados(nome: str, *args):
    """Resultado em cache de uma consulta de fdr.painel, pelo nome da função."""
    return consultar(getattr(painel, nome), *args)


@st.cache_data(show_spinner=False)
def manifest() -> dict:
    return painel.manifest()


@st.cache_data(show_spinner=False)
def json_do_projeto(caminho_relativo: str) -> dict:
    return painel.ler_json(config.RAIZ / caminho_relativo)


@st.cache_resource(show_spinner="Carregando o modelo...")
def previsor() -> Previsor:
    return Previsor(config.PASTA_MARTS / "previsao")


def chave_gemini() -> str | None:
    try:
        chave = st.secrets.get("GEMINI_API_KEY")
    except Exception:  # sem secrets.toml, o Streamlit levanta erro ao ler
        chave = None
    return chave or os.environ.get("GEMINI_API_KEY") or None


@st.cache_resource(show_spinner=False)
def _assistente(chave: str | None) -> tuple[Assistente, threading.Lock]:
    banco = painel.garantir_banco_app()
    return criar_assistente(chave, banco), threading.Lock()


def assistente() -> tuple[Assistente, threading.Lock]:
    """O assistente e uma trava: a conexão do assistente atende uma pergunta por vez."""
    return _assistente(chave_gemini())


# Gráficos ---------------------------------------------------------------------------------------


def grafico_barras(tabela: pd.DataFrame, categoria: str, valor: str, titulo_valor: str):
    return (
        alt.Chart(tabela)
        .mark_bar(color=AMBAR, cornerRadiusEnd=3)
        .encode(
            x=alt.X(f"{valor}:Q", title=titulo_valor, axis=alt.Axis(format="%")),
            y=alt.Y(f"{categoria}:N", sort="x", title=None, axis=alt.Axis(labelLimit=220)),
            tooltip=[
                alt.Tooltip(f"{categoria}:N", title="Companhia"),
                alt.Tooltip(f"{valor}:Q", title=titulo_valor, format=".1%"),
                alt.Tooltip("voos:Q", title="Voos", format=",.0f"),
            ],
        )
    )


def grafico_linhas(tabela: pd.DataFrame, x: str, series: dict[str, str], titulo_y: str, formato):
    """Uma linha por coluna de `series` ({coluna: rótulo}), com cores fixas (âmbar, cinza, azul)."""
    longa = tabela.melt(id_vars=[x], value_vars=list(series), var_name="serie", value_name="valor")
    longa["serie"] = longa["serie"].map(series)
    # Mês como texto ("ago/2026"), na ordem do tempo: um eixo de datas mudaria o dia pelo fuso.
    ordem = sorted(longa[x].unique())
    longa["mes_rotulo"] = [painel.nome_mes(pd.Timestamp(m).date()) for m in longa[x]]
    rotulos = [painel.nome_mes(pd.Timestamp(m).date()) for m in ordem]
    cores = alt.Scale(domain=list(series.values()), range=[AMBAR, CINZA, AZUL][: len(series)])
    return (
        alt.Chart(longa)
        .mark_line(point=True, strokeWidth=2.5)
        .encode(
            x=alt.X("mes_rotulo:O", title=None, sort=rotulos, axis=alt.Axis(labelAngle=0)),
            y=alt.Y("valor:Q", title=titulo_y, axis=alt.Axis(format=formato)),
            color=alt.Color("serie:N", scale=cores, legend=alt.Legend(title=None, orient="top")),
            tooltip=[
                alt.Tooltip("mes_rotulo:O", title="Mês"),
                alt.Tooltip("serie:N", title="Série"),
                alt.Tooltip("valor:Q", title=titulo_y, format=formato.replace("%", ".1%")),
            ],
        )
    )
