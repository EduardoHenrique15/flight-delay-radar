"""Monitoramento: o desempenho do modelo mês a mês, o PSI das variáveis mais importantes e a
linha do tempo dos retreinos, lidos de monitoring/history.json (docs/decisoes/006).
"""

import pandas as pd
import streamlit as st

from fdr import interface, painel
from fdr.monitoring.drift import nivel


def cor_psi(valor: float | None) -> str:
    cores = {"atenção": "rgba(245, 165, 36, 0.35)", "alerta": "rgba(248, 81, 73, 0.45)"}
    return f"background-color: {cores[nivel(valor)]}" if valor and nivel(valor) in cores else ""


with interface.pagina_protegida():
    interface.titulo(
        "Monitoramento",
        "Como o modelo se saiu em cada mês, comparado com o baseline, e quando foi retreinado.",
    )
    historico = interface.json_do_projeto("monitoring/history.json")
    meses = painel.meses_monitorados(historico)
    if meses.empty:
        st.info("Ainda não há meses monitorados.")
        st.stop()

    if (meses["tipo"] == "simulacao").any():
        st.info(
            "Os meses de "
            f"{painel.nome_mes(meses.loc[meses['tipo'] == 'simulacao', 'mes'].min().date())} a "
            f"{painel.nome_mes(meses.loc[meses['tipo'] == 'simulacao', 'mes'].max().date())} "
            "são uma simulação honesta do passado: um modelo treinado só até out/2025 foi "
            "avaliado mês a mês, sem olhar o futuro, com as mesmas regras de retreino de "
            "produção. Os meses seguintes entram aqui pelo pipeline mensal."
        )

    ultimo = meses.iloc[-1]
    colunas = st.columns(4)
    colunas[0].metric(
        "PR-AUC do último mês",
        painel.decimal(ultimo["pr_auc_modelo"]),
        f"{painel.decimal(ultimo['pr_auc_modelo'] - ultimo['pr_auc_baseline'], sinal=True)} "
        "sobre o baseline",
        help=interface.AJUDA["pr_auc"],
    )
    colunas[1].metric(
        "ECE",
        f"{painel.decimal(ultimo['ece'] * 100, 1)} p.p.",
        help=interface.AJUDA["ece"],
    )
    colunas[2].metric("Taxa real de atraso", painel.porcentagem(ultimo["taxa_real"]))
    colunas[3].metric("Taxa prevista", painel.porcentagem(ultimo["taxa_prevista"]))

    esquerda, direita = st.columns(2)
    with esquerda:
        st.subheader("PR-AUC: modelo contra baseline", help=interface.AJUDA["pr_auc"])
        st.altair_chart(
            interface.grafico_linhas(
                meses,
                "mes",
                {"pr_auc_modelo": "Modelo", "pr_auc_baseline": "Baseline"},
                "PR-AUC",
                ".2f",
            ),
            width="stretch",
        )
        vitorias = int((meses["pr_auc_modelo"] > meses["pr_auc_baseline"]).sum())
        st.caption(f"O modelo ganhou do baseline em {vitorias} de {len(meses)} meses.")
    with direita:
        st.subheader("Taxa de atraso: prevista e real")
        st.altair_chart(
            interface.grafico_linhas(
                meses,
                "mes",
                {"taxa_prevista": "Prevista pelo modelo", "taxa_real": "Real"},
                "Taxa de atraso",
                "%",
            ),
            width="stretch",
        )
        st.caption("Dezembro é o mês mais difícil: a taxa real sobe mais do que o modelo prevê.")

    st.subheader("Brier: modelo contra baseline", help=interface.AJUDA["brier"])
    st.altair_chart(
        interface.grafico_linhas(
            meses, "mes", {"brier_modelo": "Modelo", "brier_baseline": "Baseline"}, "Brier", ".3f"
        ),
        width="stretch",
    )

    st.subheader("Mudança nas variáveis (PSI)", help=interface.AJUDA["psi"])
    importantes = historico["variaveis_importantes"]
    psi = pd.DataFrame(
        [
            {
                "Mês": painel.nome_mes(m["mes"].date()),
                **{painel.NOMES_VARIAVEIS.get(v, v): m["psi"].get(v) for v in importantes},
            }
            for _, m in meses.iterrows()
        ]
    ).set_index("Mês")
    st.dataframe(psi.style.format("{:.3f}").map(cor_psi), width="stretch")
    st.caption(
        "As 5 variáveis que mais pesam no modelo, fora mês do ano, feriados e férias (essas "
        "mudam todo mês por definição). PSI de 0,25 ou mais em uma delas dispara o retreino."
    )

    st.subheader("Linha do tempo dos retreinos")
    regras = historico["regras"]
    st.caption(
        "Regras: retreina se o modelo perder do baseline no mês, se o ECE passar de "
        f"{regras['ece_maximo'] * 100:.0f} p.p., se o PSI de uma variável importante passar de "
        f"0,25 ou a cada {regras['meses_maximos_sem_retreino']} meses. O desafiante só substitui "
        "o campeão se o ganho de PR-AUC tiver intervalo de 95% acima de zero."
    )
    for _, mes in meses.iloc[::-1].iterrows():
        icone = (
            "🔄"
            if mes["retreino"].get("promovido")
            else ("⚠️" if mes["retreino"]["disparou"] else "✅")
        )
        st.markdown(
            f"{icone} **{painel.nome_mes(mes['mes'].date())}** — "
            f"{painel.descrever_retreino(mes['retreino'])}"
        )
