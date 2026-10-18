"""Pontualidade: exploração com filtros de período, companhia, aeroporto e rota.

Sem a análise de motivos: a justificativa do VRA vem vazia em 100% das linhas (docs/dados.md,
seção 4.3).
"""

import altair as alt
import streamlit as st

from fdr import interface, painel

with interface.pagina_protegida():
    interface.titulo(
        "Pontualidade",
        "Voos nacionais realizados. Atraso = partida mais de 15 minutos depois do previsto.",
    )

    meses = interface.dados("meses")
    inicio, fim = st.select_slider(
        "Período",
        options=meses,
        value=(meses[max(len(meses) - 12, 0)], meses[-1]),
        format_func=painel.nome_mes,
    )
    filtros = st.columns(3)
    cias = interface.dados("companhias")
    cia = filtros[0].selectbox(
        "Companhia",
        [None, *cias["cia"]],
        format_func=lambda c: "Todas" if c is None else cias.set_index("cia").at[c, "nome"],
    )
    aeroportos = interface.dados("aeroportos")
    origem = filtros[1].selectbox(
        "Aeroporto de origem",
        [None, *aeroportos["icao"]],
        format_func=lambda a: (
            "Todos" if a is None else aeroportos.set_index("icao").at[a, "rotulo"]
        ),
    )
    destino = None
    if origem:
        destinos = interface.dados("destinos", origem)
        destino = filtros[2].selectbox(
            "Destino (rota)",
            [None, *destinos["icao"]],
            format_func=lambda a: (
                "Todos" if a is None else destinos.set_index("icao").at[a, "rotulo"]
            ),
        )
    else:
        filtros[2].selectbox("Destino (rota)", ["Escolha a origem primeiro"], disabled=True)

    evolucao = interface.dados("evolucao_mensal", inicio, fim, cia, origem, destino)
    if evolucao.empty:
        st.info("Nenhum voo com esses filtros. Tente um período maior ou outra combinação.")
        st.stop()

    total = int(evolucao["voos"].sum())
    taxa = float((evolucao["taxa_atraso"] * evolucao["voos"]).sum() / total)
    resumo = st.columns(2)
    resumo[0].metric("Voos no período", painel.numero(total))
    resumo[1].metric("Taxa de atraso", painel.porcentagem(taxa))

    esquerda, direita = st.columns(2)
    with esquerda:
        st.subheader("Ranking das companhias")
        ranking = interface.dados("ranking_companhias", inicio, fim, origem, destino)
        if ranking.empty:
            st.caption(f"Nenhuma companhia com pelo menos {painel.MIN_VOOS_RANKING} voos.")
        else:
            st.altair_chart(
                interface.grafico_barras(ranking, "companhia", "taxa_atraso", "Taxa de atraso"),
                width="stretch",
            )
            st.caption(
                f"Companhias com pelo menos {painel.MIN_VOOS_RANKING} voos. As diferenças misturam "
                "rotas e horários: não é um ranking de qualidade."
            )
    with direita:
        st.subheader("Evolução mensal")
        st.altair_chart(
            interface.grafico_linhas(
                evolucao, "mes", {"taxa_atraso": "Taxa de atraso"}, "Taxa de atraso", "%"
            ),
            width="stretch",
        )

    st.subheader("Quando os voos mais atrasam")
    calor = interface.dados("mapa_de_calor", inicio, fim, cia, origem, destino)
    st.altair_chart(
        alt.Chart(calor)
        .mark_rect()
        .encode(
            x=alt.X("hora:O", title="Hora prevista da partida (local)"),
            y=alt.Y("dia_semana:N", sort=list(painel.DIAS_SEMANA), title=None),
            color=alt.Color(
                "taxa_atraso:Q",
                title="Atraso",
                scale=alt.Scale(scheme="oranges"),
                legend=alt.Legend(format="%"),
            ),
            tooltip=[
                alt.Tooltip("dia_semana:N", title="Dia"),
                alt.Tooltip("hora:O", title="Hora"),
                alt.Tooltip("taxa_atraso:Q", title="Taxa de atraso", format=".1%"),
                alt.Tooltip("voos:Q", title="Voos", format=",.0f"),
            ],
        ),
        width="stretch",
    )
    st.caption(
        "Os motivos dos atrasos não aparecem aqui: o campo de justificativa vem vazio em todos "
        "os arquivos da ANAC."
    )
