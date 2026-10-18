"""Pergunte aos dados: o assistente texto->SQL (PROJETO.md, seção 8; docs/decisoes/007).

Sem a chave do Gemini, ou sem cota, ele responde com as respostas gravadas de demonstração.
"""

import streamlit as st

from fdr import interface
from fdr.assistant.agent import Resposta
from fdr.assistant.eval import ler_perguntas

ORIGENS = {
    "modelo": "Resposta do Gemini",
    "cache": "Resposta já aprovada antes (sem gastar cota)",
    "demonstracao": "Resposta gravada de demonstração",
    "recusa": "Fora do alcance dos dados",
    "erro": "Não deu certo",
    "limite": "Modo de demonstração",
}


def exemplos(assistente) -> list[str]:
    gravadas = assistente.demonstracao.perguntas()
    return (gravadas or [q["pergunta"] for q in ler_perguntas() if q.get("demo")])[:4]


def mostrar(resposta: Resposta) -> None:
    with st.chat_message("user"):
        st.markdown(resposta.pergunta)
    with st.chat_message("assistant", avatar="✈️"):
        st.markdown(resposta.texto)
        if resposta.tabela is not None and not resposta.tabela.empty:
            st.dataframe(resposta.tabela, hide_index=True, width="stretch")
        if resposta.sql:
            with st.expander("SQL usado"):
                st.code(resposta.sql, language="sql")
        legenda = ORIGENS.get(resposta.origem, resposta.origem)
        st.caption(" · ".join([legenda, *resposta.avisos]))


with interface.pagina_protegida():
    interface.titulo(
        "Pergunte aos dados",
        "Pergunte em português. O assistente escreve uma consulta SQL, que passa por travas de "
        "segurança e roda nos dados; o número vem sempre do banco, nunca do modelo de linguagem.",
    )
    assistente, trava = interface.assistente()
    st.session_state.setdefault("conversa", [])
    st.session_state.setdefault("perguntas_ao_modelo", 0)

    if assistente.llm is None:
        st.info(
            "Modo de demonstração: este app está sem a chave do Gemini. Escolha uma das "
            "perguntas de exemplo, que têm respostas gravadas (e rodam de novo nos dados atuais)."
        )
    else:
        st.caption(
            f"Até {assistente.uso.por_sessao} perguntas novas por visita e "
            f"{assistente.uso.por_dia} por dia (cota gratuita do Gemini). Depois disso, o "
            "assistente responde só às perguntas de exemplo."
        )

    pergunta = None
    botoes = st.columns(2)
    for i, exemplo in enumerate(exemplos(assistente)):
        if botoes[i % 2].button(exemplo, key=f"exemplo_{i}", width="stretch"):
            pergunta = exemplo
    digitada = st.chat_input("Ex.: Qual companhia mais atrasou em julho de 2026?", max_chars=300)
    pergunta = digitada or pergunta

    if pergunta:
        with trava, st.spinner("Consultando os dados..."):
            resposta = assistente.responder(
                pergunta, usadas_na_sessao=st.session_state["perguntas_ao_modelo"]
            )
        if resposta.tentativas:
            st.session_state["perguntas_ao_modelo"] += 1
        st.session_state["conversa"].append(resposta)

    for resposta in reversed(st.session_state["conversa"]):
        mostrar(resposta)

    st.caption(
        "Travas: só consultas de leitura (SELECT), só as 6 tabelas do app, sem acesso a arquivos "
        "ou à rede, no máximo 1.000 linhas e 10 segundos por consulta."
    )
