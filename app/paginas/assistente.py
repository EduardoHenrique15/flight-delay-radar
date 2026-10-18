"""Pergunte aos dados: o assistente texto->SQL (docs/decisoes/007-texto-para-sql-com-travas.md).

Sem a chave do Gemini, ou sem cota, ele responde com as respostas gravadas de demonstração.
"""

import streamlit as st

from fdr import interface
from fdr.assistant.agent import Resposta
from fdr.assistant.eval import ler_perguntas

# Origem da resposta -> (rótulo, situação do selo)
ORIGENS = {
    "modelo": ("Consulta escrita pelo Gemini", "bom"),
    "cache": ("Consulta já aprovada antes", "bom"),
    "demonstracao": ("Resposta de demonstração", "neutro"),
    "recusa": ("Fora do alcance dos dados", "atencao"),
    "erro": ("Não foi possível responder", "critico"),
    "limite": ("Modo de demonstração", "neutro"),
}


def exemplos(assistente) -> list[str]:
    gravadas = assistente.demonstracao.perguntas()
    return (gravadas or [q["pergunta"] for q in ler_perguntas() if q.get("demo")])[:4]


def mostrar(resposta: Resposta) -> None:
    with st.chat_message("user", avatar=":material/person:"):
        st.markdown(resposta.pergunta)
    with st.chat_message("assistant", avatar=":material/database:"):
        rotulo, situacao = ORIGENS.get(resposta.origem, (resposta.origem, "neutro"))
        interface.html_bruto(interface.selo(rotulo, situacao))
        st.markdown(resposta.texto)
        if resposta.tabela is not None and not resposta.tabela.empty:
            st.dataframe(resposta.tabela, hide_index=True, width="stretch")
        if resposta.sql:
            with st.expander("Ver a consulta SQL"):
                st.code(resposta.sql, language="sql")
        for aviso in resposta.avisos:
            interface.nota(aviso)


with interface.pagina_protegida():
    assistente, trava = interface.assistente()
    interface.cabecalho(
        "Pergunte aos dados",
        "Perguntas em português, respostas do banco",
        "O assistente transforma a pergunta numa consulta SQL, que passa por travas de segurança "
        "e roda nos dados do app. O número vem sempre do banco, nunca do modelo de linguagem.",
        icone="conversa",
        meta=[
            ("Modelo de linguagem", "Gemini" if assistente.llm else "Demonstração"),
            ("Banco", "DuckDB · 6 tabelas"),
            ("Consultas", "Só leitura"),
        ],
    )
    st.session_state.setdefault("conversa", [])
    st.session_state.setdefault("perguntas_ao_modelo", 0)

    if assistente.llm is None:
        interface.aviso(
            "Modo de demonstração: este app está sem a chave do Gemini. As perguntas de exemplo "
            "têm consultas gravadas, que rodam de novo nos dados atuais."
        )
    else:
        interface.aviso(
            f"Até {assistente.uso.por_sessao} perguntas novas por visita e "
            f"{assistente.uso.por_dia} por dia (cota gratuita do Gemini). Depois disso, o "
            "assistente responde só às perguntas de exemplo."
        )

    interface.secao("Faça uma pergunta", "Ou comece por um dos exemplos abaixo.")
    # Dentro de um contêiner, a caixa de pergunta fica no corpo da página (e não presa embaixo).
    with st.container():
        digitada = st.chat_input(
            "Ex.: Qual companhia mais atrasou em julho de 2026?", max_chars=300
        )
    pergunta = None
    with st.container(key="exemplos"):
        botoes = st.columns(2, gap="small")
        for i, exemplo in enumerate(exemplos(assistente)):
            if botoes[i % 2].button(
                exemplo, key=f"exemplo_{i}", width="stretch", icon=":material/arrow_forward:"
            ):
                pergunta = exemplo
    pergunta = digitada or pergunta

    if pergunta:
        with trava, st.spinner("Consultando os dados..."):
            resposta = assistente.responder(
                pergunta, usadas_na_sessao=st.session_state["perguntas_ao_modelo"]
            )
        if resposta.tentativas:
            st.session_state["perguntas_ao_modelo"] += 1
        st.session_state["conversa"].append(resposta)

    if st.session_state["conversa"]:
        interface.secao("Conversa")
    for resposta in reversed(st.session_state["conversa"]):
        mostrar(resposta)

    interface.secao("Como o assistente responde")
    interface.etapas(
        [
            ("Pergunta", "Em português, sobre os voos, as companhias e os aeroportos do app."),
            (
                "Consulta",
                "O Gemini escreve uma consulta SQL a partir da descrição das tabelas, sem "
                "receber as linhas do banco.",
            ),
            (
                "Travas",
                "Só leitura (SELECT), só as 6 tabelas do app, sem arquivos nem rede, no máximo "
                "1.000 linhas e 10 segundos.",
            ),
            (
                "Resposta",
                "O DuckDB roda a consulta e os números da resposta saem da tabela, que aparece "
                "junto com o SQL.",
            ),
        ]
    )
