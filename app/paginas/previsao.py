"""Previsão: a chance de um voo futuro atrasar, os fatores que mais pesaram (SHAP em frases), a
comparação com a rota e com as outras companhias e o "e se" de outros horários.

As variáveis saem da mesma consulta do treino (fdr.previsao), com o histórico até 2 meses antes
do voo.
"""

from datetime import date

import altair as alt
import pandas as pd
import streamlit as st

from fdr import interface, painel
from fdr.model.explain import frase
from fdr.previsao import Voo

CORES_FAIXA = {"baixa": "#3FB950", "média": interface.AMBAR, "alta": "#F85149"}


def rotulos(tabela: pd.DataFrame) -> dict[str, str]:
    return dict(zip(tabela["icao"], tabela["rotulo"], strict=True))


with interface.pagina_protegida():
    interface.titulo(
        "Previsão de atraso",
        "Escolha a rota, a companhia, a data e a hora. O modelo diz a chance de a partida "
        "atrasar mais de 15 minutos.",
    )
    previsor = interface.previsor()
    rotas = previsor.rotas()
    aeroportos = rotulos(interface.dados("aeroportos"))
    nomes_cias = interface.dados("companhias").set_index("cia")["nome"].to_dict()

    def nome_aeroporto(icao: str) -> str:
        return aeroportos.get(icao, icao)

    # Das origens e destinos mais voados para os menos (a ordem de rotas()).
    origens = list(
        rotas.groupby("origem", sort=False)["voos"].sum().sort_values(ascending=False).index
    )
    padrao_origem = 0
    linha1 = st.columns(3)
    origem = linha1[0].selectbox("Origem", origens, index=padrao_origem, format_func=nome_aeroporto)
    destinos = list(rotas.loc[rotas["origem"] == origem, "destino"])
    destino = linha1[1].selectbox("Destino", destinos, format_func=nome_aeroporto)

    inicio, fim = previsor.periodo()
    hoje = date.today()
    dia = linha1[2].date_input(
        "Data do voo",
        value=min(max(hoje, inicio), fim),
        min_value=inicio,
        max_value=fim,
        format="DD/MM/YYYY",
    )
    cias = previsor.companhias_na_rota(origem, destino, dia)
    if not cias:
        st.info("Nenhuma companhia voou essa rota nos 12 meses de histórico. Escolha outra rota.")
        st.stop()
    linha2 = st.columns(3)
    cia = linha2[0].selectbox("Companhia", cias, format_func=lambda c: nomes_cias.get(c, c))
    hora = linha2[1].selectbox(
        "Hora prevista da partida", range(24), index=10, format_func=lambda h: f"{h:02d}h"
    )

    voo = Voo(cia, origem, destino, dia, hora)
    outras = [Voo(c, origem, destino, dia, hora) for c in cias]
    horarios = [Voo(cia, origem, destino, dia, h) for h in range(24)]
    resultados = previsor.prever([voo, *outras, *horarios])
    principal = resultados[0]
    por_cia = resultados[1 : 1 + len(outras)]
    por_hora = resultados[1 + len(outras) :]

    if principal["historico_defasado"]:
        st.warning(
            "Para este mês, a ANAC ainda não publicou os dados de 2 meses antes. O modelo usa o "
            f"último mês publicado ({painel.nome_mes(previsor.ultimo_mes_publicado)}), um "
            "histórico mais velho do que no treino: a previsão fica menos confiável."
        )

    st.divider()
    esquerda, direita = st.columns([1, 2])
    with esquerda:
        faixa = principal["faixa"]
        st.metric(
            "Chance de atrasar mais de 15 min", painel.porcentagem(principal["probabilidade"])
        )
        st.markdown(
            f'Chance <span class="fdr-faixa" style="color:{CORES_FAIXA[faixa]}">{faixa}</span>',
            unsafe_allow_html=True,
        )
        if principal["taxa_rota_hora_12m"] is not None:
            st.caption(
                f"Nos 12 meses de histórico, {painel.porcentagem(principal['taxa_rota_hora_12m'])} "
                f"dos {painel.numero(principal['voos_rota_hora_12m'])} voos dessa rota nesse "
                "horário atrasaram."
            )
        else:
            st.caption("Sem voos dessa rota nesse horário no histórico de 12 meses.")
        st.caption(
            f"Média do modelo para um voo qualquer: "
            f"{painel.porcentagem(principal['media_do_modelo'])}."
        )
    with direita:
        st.markdown("**O que mais pesou nesta previsão**")
        if principal["aumentam"]:
            st.markdown("Aumentam o risco:")
            for fator in principal["aumentam"]:
                st.markdown(f"- 🔺 {frase(fator)}")
        if principal["diminuem"]:
            st.markdown("Diminuem o risco:")
            for fator in principal["diminuem"]:
                st.markdown(f"- 🔻 {frase(fator)}")
        st.caption(
            "Cada fator diz quanto a chance cairia, em pontos percentuais, sem aquele tema "
            "(SHAP do próprio modelo, somado por tema)."
        )

    st.divider()
    comparacao, e_se = st.columns(2)
    with comparacao:
        st.subheader("Outras companhias, mesma rota e hora")
        tabela = pd.DataFrame(
            {
                "Companhia": [nomes_cias.get(r["voo"].cia, r["voo"].cia) for r in por_cia],
                "chance": [r["probabilidade"] for r in por_cia],
            }
        ).sort_values("chance")
        st.altair_chart(
            alt.Chart(tabela)
            .mark_bar(cornerRadiusEnd=3)
            .encode(
                x=alt.X("chance:Q", title="Chance de atraso", axis=alt.Axis(format="%")),
                y=alt.Y("Companhia:N", sort="x", title=None),
                color=alt.condition(
                    alt.datum.Companhia == nomes_cias.get(cia, cia),
                    alt.value(interface.AMBAR),
                    alt.value(interface.CINZA),
                ),
                tooltip=[alt.Tooltip("chance:Q", title="Chance", format=".1%"), "Companhia:N"],
            ),
            width="stretch",
        )
    with e_se:
        st.subheader("E se fosse em outro horário?")
        curva = pd.DataFrame({"hora": range(24), "chance": [r["probabilidade"] for r in por_hora]})
        base = alt.Chart(curva).encode(
            x=alt.X("hora:Q", title="Hora prevista da partida", scale=alt.Scale(domain=[0, 23])),
            y=alt.Y("chance:Q", title="Chance de atraso", axis=alt.Axis(format="%")),
            tooltip=[
                alt.Tooltip("hora:Q", title="Hora"),
                alt.Tooltip("chance:Q", title="Chance", format=".1%"),
            ],
        )
        destaque = base.transform_filter(alt.datum.hora == hora).mark_point(
            size=120, filled=True, color=interface.AMBAR
        )
        st.altair_chart(
            base.mark_line(color=interface.CINZA, strokeWidth=2.5) + destaque, width="stretch"
        )
        st.caption("Mesma companhia, rota e data; só muda a hora.")

    st.caption(
        "É uma probabilidade, não uma garantia: cerca de 15% dos voos atrasam. O modelo não vê "
        "clima nem a rotação do avião. Consulte a companhia no dia do voo."
    )
