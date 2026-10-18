"""Sobre o modelo: metodologia em linguagem simples, métricas do teste com intervalos e o
baseline, limitações e links. Todos os números vêm de models/metrics.json e metadata.json."""

import pandas as pd
import streamlit as st

from fdr import config, interface, painel

with interface.pagina_protegida():
    interface.titulo(
        "Sobre o modelo",
        "Como a previsão é feita, o quanto ela acerta e onde ela erra.",
    )
    metricas = interface.json_do_projeto("models/metrics.json")
    metadados = interface.json_do_projeto("models/metadata.json")
    teste = metricas["modelo_final"]["teste"]
    baseline = metricas["baseline"]["teste"]
    inicio_teste, fim_teste = (pd.Timestamp(m).date() for m in teste["periodo"])
    inicio_treino, fim_treino = (pd.Timestamp(m).date() for m in metadados["treino"])

    st.subheader("Como funciona")
    st.markdown(
        f"""
- **O que prevê:** a chance de um voo nacional regular partir com mais de 15 minutos de atraso.
- **Com o quê:** só o que se sabe antes do voo: companhia, rota, data, hora, feriados e o
  histórico de atrasos **até 2 meses antes** (a ANAC publica cada mês com 2 meses de defasagem).
  Essa regra é testada contra vazamento de informação do futuro.
- **Modelo:** LightGBM (árvores de decisão em sequência), treinado com
  {painel.numero(metadados["voos_treino"])} voos de {painel.nome_mes(inicio_treino)} a
  {painel.nome_mes(fim_treino)}.
- **Validação no tempo:** o modelo foi escolhido em 5 janelas de validação, sempre treinando no
  passado e avaliando no futuro, contra um baseline e uma regressão logística.
- **Teste:** {painel.nome_mes(inicio_teste)} a {painel.nome_mes(fim_teste)}
  ({painel.numero(teste["voos"])} voos), usado **uma única vez**, depois de todas as escolhas.
"""
    )

    st.subheader("Resultado no teste")

    def intervalo(nome: str, casas: int = 3) -> str:
        baixo, alto = teste["intervalo_95"][nome]
        return f"IC 95%: {painel.decimal(baixo, casas)} a {painel.decimal(alto, casas)}"

    ganho = teste["ganho_sobre_baseline"]["pr_auc"]
    ganho_baixo, ganho_alto = teste["ganho_sobre_baseline_intervalo_95"]["pr_auc"]
    colunas = st.columns(4)
    colunas[0].metric(
        "PR-AUC",
        painel.decimal(teste["pr_auc"]),
        f"{painel.decimal(ganho, sinal=True)} sobre o baseline",
        help=interface.AJUDA["pr_auc"],
    )
    colunas[0].caption(intervalo("pr_auc"))
    colunas[1].metric(
        "ROC-AUC",
        painel.decimal(teste["roc_auc"]),
        help="ROC-AUC: chance de um voo que atrasou receber risco maior que um que não atrasou.",
    )
    colunas[1].caption(intervalo("roc_auc"))
    colunas[2].metric(
        "ECE", f"{painel.decimal(teste['ece'] * 100, 1)} p.p.", help=interface.AJUDA["ece"]
    )
    colunas[2].caption("Probabilidades bem calibradas na média.")
    lift = teste["lift_10pct"]
    colunas[3].metric(
        "Voos de maior risco",
        painel.porcentagem(lift["precisao"]),
        f"{painel.decimal(lift['lift'], 2)}x a média",
        delta_color="off",
        delta_arrow="off",
        help="Entre os 10% de voos com maior risco previsto, quantos atrasaram de fato.",
    )
    colunas[3].caption(f"Baseline: {painel.porcentagem(teste['lift_10pct_baseline']['precisao'])}.")
    st.markdown(
        f"O ganho de PR-AUC sobre o baseline (a taxa histórica da rota no horário) é de "
        f"**{painel.decimal(ganho, sinal=True)}**, com intervalo de 95% de "
        f"{painel.decimal(ganho_baixo, sinal=True)} a {painel.decimal(ganho_alto, sinal=True)}: "
        "pequeno, mas consistente. O baseline já é forte; o modelo soma o efeito da hora, do "
        "dia da semana, do movimento no aeroporto e da época do ano."
    )
    st.caption(
        f"Baseline no teste: PR-AUC {painel.decimal(baseline['pr_auc'])}. Intervalos de 95% "
        "por bootstrap pareado por dia."
    )

    imagens = st.columns(3)
    for coluna, (arquivo, legenda) in zip(
        imagens,
        [
            ("pr_auc_por_janela.png", "PR-AUC em cada janela da validação"),
            ("calibracao_teste.png", "Probabilidade prevista contra a taxa real"),
            ("shap_temas.png", "O que mais pesa nas previsões (SHAP por tema)"),
        ],
        strict=True,
    ):
        caminho = config.RAIZ / "docs" / "img" / arquivo
        if caminho.exists():
            coluna.image(str(caminho), caption=legenda)

    st.subheader("Limitações")
    st.markdown(
        """
- **Sem clima** e **sem a rotação do avião**: o VRA não traz nenhum dos dois.
- **Programação típica, e não a real:** para um voo futuro, o modelo usa o movimento que o
  aeroporto costuma ter, e não a programação exata do dia.
- **Probabilidades altas são subestimadas**, e há mais erro em companhias pequenas.
- **Cancelados ficam de fora:** a probabilidade é de atraso, e não de cancelamento.
- **Não serve** para garantir que um voo vai ou não atrasar, para ranquear a qualidade das
  companhias nem para pedidos de indenização.
"""
    )

    st.subheader("Para saber mais")
    st.markdown(
        f"""
- [Código no GitHub]({interface.REPOSITORIO})
- [Cartão do modelo]({interface.REPOSITORIO}/blob/main/docs/modelo.md)
- [Decisões de projeto (ADRs)]({interface.REPOSITORIO}/tree/main/docs/decisoes)
- [Dados: o VRA da ANAC]({interface.REPOSITORIO}/blob/main/docs/dados.md)
"""
    )
