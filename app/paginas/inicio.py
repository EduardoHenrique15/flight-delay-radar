"""Início: o que o app faz, os números do último mês e os atalhos para as outras páginas."""

from datetime import datetime

import streamlit as st

from fdr import interface, painel

with interface.pagina_protegida():
    interface.titulo(
        "Flight Delay Radar",
        "Atrasos dos voos nacionais com os dados públicos da ANAC: o que aconteceu, o risco de "
        "um voo atrasar e como o modelo se comporta mês a mês.",
    )
    resumo = interface.dados("resumo_ultimo_mes")
    mes = painel.nome_mes(resumo["mes"])

    st.subheader(f"Último mês publicado: {mes}")
    colunas = st.columns(4)
    colunas[0].metric(
        "Voos nacionais realizados", painel.numero(resumo["voos_nacionais_realizados"])
    )
    colunas[1].metric(
        "Atrasaram mais de 15 min",
        painel.porcentagem(resumo["taxa_atraso"]),
    )
    if resumo["cia_mais_pontual"]:
        nome, taxa = resumo["cia_mais_pontual"]
        colunas[2].metric(
            "Companhia mais pontual",
            nome,
            f"{painel.porcentagem(taxa)} de atraso",
            delta_color="off",
            delta_arrow="off",
            help=f"Entre as companhias com pelo menos {painel.MIN_VOOS_DESTAQUE} voos no mês.",
        )
    if resumo["aeroporto_mais_atraso"]:
        codigo, taxa, nome = resumo["aeroporto_mais_atraso"]
        colunas[3].metric(
            "Aeroporto com mais atraso",
            codigo,
            f"{painel.porcentagem(taxa)} de atraso",
            delta_color="off",
            delta_arrow="off",
            help=f"{nome}. Partidas de aeroportos com pelo menos {painel.MIN_VOOS_DESTAQUE} voos "
            "no mês.",
        )

    st.divider()
    atalhos = st.columns(3)
    with atalhos[0]:
        st.page_link("paginas/pontualidade.py", label="Explorar a pontualidade", icon="📊")
        st.caption("Ranking das companhias, horários críticos e evolução mês a mês.")
    with atalhos[1]:
        st.page_link("paginas/previsao.py", label="Prever o risco de um voo", icon="🛫")
        st.caption("Escolha rota, companhia, data e hora e veja o que mais pesa.")
    with atalhos[2]:
        st.page_link("paginas/assistente.py", label="Perguntar aos dados", icon="💬")
        st.caption("Pergunte em português; o assistente escreve o SQL e mostra a consulta.")

    info = interface.manifest()
    gerado = datetime.fromisoformat(info["gerado_em"])
    st.caption(
        f"Dados de {painel.nome_mes(datetime.fromisoformat(info['primeiro_mes']).date())} a "
        f"{mes}, atualizados em {gerado:%d/%m/%Y}. Fonte: VRA (Voo Regular Ativo) da ANAC, que "
        "publica cada mês com cerca de 2 meses de defasagem."
    )
