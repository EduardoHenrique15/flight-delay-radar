"""Sobre o modelo: metodologia em linguagem simples, métricas do teste com intervalos e o
baseline, limitações e links. Todos os números vêm de models/metrics.json, metadata.json e
explicacao_global.json."""

import altair as alt
import pandas as pd
import streamlit as st

from fdr import interface, painel

with interface.pagina_protegida():
    metricas = interface.json_do_projeto("models/metrics.json")
    metadados = interface.json_do_projeto("models/metadata.json")
    explicacao = interface.json_do_projeto("models/explicacao_global.json")
    teste = metricas["modelo_final"]["teste"]
    baseline = metricas["baseline"]["teste"]
    inicio_teste, fim_teste = (pd.Timestamp(m).date() for m in teste["periodo"])
    inicio_treino, fim_treino = (pd.Timestamp(m).date() for m in metadados["treino"])

    interface.cabecalho(
        "Sobre o modelo",
        "Como a previsão é feita, quanto ela acerta e onde ela erra",
        "Um LightGBM treinado com os voos nacionais regulares, validado sempre no futuro e "
        "comparado com um baseline simples. Todos os números abaixo vêm dos arquivos gerados "
        "pelo pipeline.",
        icone="info",
        meta=[
            ("Algoritmo", "LightGBM"),
            ("Voos no treino", painel.numero(metadados["voos_treino"])),
            ("Teste", f"{painel.nome_mes(inicio_teste)} a {painel.nome_mes(fim_teste)}"),
        ],
    )

    interface.secao("Como funciona")
    interface.etapas(
        [
            (
                "O que prevê",
                "A chance de um voo nacional regular partir com mais de 15 minutos de atraso.",
            ),
            (
                "Com o quê",
                "Companhia, rota, data, hora, feriados e o histórico de atrasos até 2 meses "
                "antes do voo. Um teste garante que nada do futuro entra.",
            ),
            (
                "Treino",
                f"{painel.numero(metadados['voos_treino'])} voos, de "
                f"{painel.nome_mes(inicio_treino)} a {painel.nome_mes(fim_treino)}. Escolhido "
                "em 5 janelas de validação, contra o baseline e uma regressão logística.",
            ),
            (
                "Teste",
                f"{painel.nome_mes(inicio_teste)} a {painel.nome_mes(fim_teste)}, "
                f"{painel.numero(teste['voos'])} voos, usado uma única vez, depois de todas "
                "as escolhas.",
            ),
        ]
    )

    def intervalo(nome: str, casas: int = 3) -> str:
        baixo, alto = teste["intervalo_95"][nome]
        return f"IC 95%: {painel.decimal(baixo, casas)} a {painel.decimal(alto, casas)}"

    ganho = teste["ganho_sobre_baseline"]["pr_auc"]
    ganho_baixo, ganho_alto = teste["ganho_sobre_baseline_intervalo_95"]["pr_auc"]
    lift = teste["lift_10pct"]
    interface.secao(
        "Resultado no teste",
        f"O baseline é a taxa histórica de atraso da rota no horário (PR-AUC "
        f"{painel.decimal(baseline['pr_auc'])} no teste). O ganho do modelo é de "
        f"{painel.decimal(ganho, sinal=True)}, com intervalo de 95% de "
        f"{painel.decimal(ganho_baixo, sinal=True)} a {painel.decimal(ganho_alto, sinal=True)}: "
        "pequeno, mas consistente.",
    )
    interface.numeros(
        [
            interface.Numero(
                "PR-AUC",
                painel.decimal(teste["pr_auc"]),
                f"{painel.decimal(ganho, sinal=True)} sobre o baseline · {intervalo('pr_auc')}",
                interface.AJUDA["pr_auc"],
            ),
            interface.Numero(
                "ROC-AUC",
                painel.decimal(teste["roc_auc"]),
                intervalo("roc_auc"),
                "Chance de um voo que atrasou receber risco maior que um que não atrasou.",
            ),
            interface.Numero(
                "Calibração (ECE)",
                f"{painel.decimal(teste['ece'] * 100, 1)} p.p.",
                "a probabilidade prevista bate com a taxa real",
                interface.AJUDA["ece"],
            ),
            interface.Numero(
                "Top 10% de risco",
                painel.porcentagem(lift["precisao"]),
                f"atrasaram · {painel.decimal(lift['lift'], 2)}x a média · baseline "
                f"{painel.porcentagem(teste['lift_10pct_baseline']['precisao'])}",
                "Dos 10% de voos com maior risco previsto, a parcela que atrasou de verdade.",
            ),
        ]
    )
    interface.nota("Intervalos de 95% por bootstrap pareado por dia.")

    esquerda, direita = st.columns(2, gap="medium")
    with esquerda, interface.quadro("temas", altura="stretch"):
        interface.secao(
            "O que mais pesa nas previsões",
            "Efeito médio de cada tema na chance de atraso, em pontos percentuais (SHAP).",
        )
        temas = pd.DataFrame(explicacao["por_tema"])
        temas["texto"] = [f"{painel.decimal(v, 1)} p.p." for v in temas["pontos_medios_abs"]]
        barras = alt.Chart(temas).encode(
            x=alt.X("pontos_medios_abs:Q", title="Pontos percentuais", axis=alt.Axis(grid=True)),
            y=alt.Y("tema:N", sort="-x", title=None, axis=alt.Axis(labelLimit=240)),
            tooltip=[alt.Tooltip("tema:N", title="Tema"), alt.Tooltip("texto:N", title="Efeito")],
        )
        interface.grafico(
            barras.mark_bar(color=interface.DESTAQUE, size=14)
            + barras.mark_text(align="left", dx=6, color=interface.TEXTO, fontSize=11).encode(
                text="texto:N"
            ),
            altura=34 * len(temas),
        )
    with direita, interface.quadro("calibracao", altura="stretch"):
        interface.secao(
            "Probabilidade prevista contra a taxa real",
            "No teste, por faixas de risco. Na diagonal, o previsto bate com o real.",
        )
        curva = pd.DataFrame(teste["curva_calibracao"])
        curva["faixa_texto"] = [
            f"{painel.porcentagem(a, 0)} a {painel.porcentagem(b, 0)}" for a, b in curva["faixa"]
        ]
        curva = curva.drop(columns="faixa")
        limite = float(max(curva["prevista_media"].max(), curva["taxa_real"].max())) * 1.05
        diagonal = (
            alt.Chart(pd.DataFrame({"x": [0, limite], "y": [0, limite]}))
            .mark_line(color=interface.APAGADO, strokeDash=[4, 4])
            .encode(x="x:Q", y="y:Q")
        )
        pontos = alt.Chart(curva).encode(
            x=alt.X(
                "prevista_media:Q",
                title="Prevista pelo modelo",
                axis=alt.Axis(format="%", grid=True),
                scale=alt.Scale(domain=[0, limite]),
            ),
            y=alt.Y(
                "taxa_real:Q",
                title="Taxa real de atraso",
                axis=alt.Axis(format="%"),
                scale=alt.Scale(domain=[0, limite]),
            ),
            tooltip=[
                alt.Tooltip("faixa_texto:N", title="Faixa"),
                alt.Tooltip("prevista_media:Q", title="Prevista", format=".1%"),
                alt.Tooltip("taxa_real:Q", title="Real", format=".1%"),
                alt.Tooltip("voos:Q", title="Voos", format=",.0f"),
            ],
        )
        interface.grafico(
            diagonal
            + pontos.mark_line(color=interface.DESTAQUE)
            + pontos.mark_point(color=interface.DESTAQUE, stroke="white", strokeWidth=2),
            altura=34 * len(temas),
        )
        interface.nota("Acima da diagonal, o modelo subestima o risco: acontece nas faixas altas.")

    interface.secao("Limitações")
    interface.etapas(
        [
            ("Sem clima", "O VRA não traz o tempo, uma das maiores causas de atraso."),
            (
                "Sem a rotação do avião",
                "O atraso do voo anterior do mesmo avião não entra; a posição do voo no dia da "
                "companhia é só uma aproximação.",
            ),
            (
                "Risco alto subestimado",
                "Nas faixas de maior risco a taxa real passa da prevista, e companhias pequenas "
                "têm mais erro.",
            ),
            (
                "Só atraso",
                "Cancelados ficam de fora. Não serve para garantir um voo, ranquear companhias "
                "ou pedir indenização.",
            ),
        ],
        limites=True,
    )

    interface.secao("Quem fez")
    with interface.quadro("autor"):
        interface.html_bruto(
            '<div class="fdr-autor"><div class="iniciais">EH</div><div>'
            f'<div class="nome">{interface._e(interface.AUTOR)}</div>'
            '<div class="texto">Projeto pessoal, de ponta a ponta: o download dos dados da ANAC, '
            "o warehouse com testes de qualidade, o modelo validado no tempo, o monitoramento "
            "com regra de retreino, o assistente com IA e este app.</div>"
            '<div class="vaga"><i></i>Aberto a vagas em Ciência de Dados, Machine Learning e '
            "IA</div></div></div>"
        )
        with st.container(key="placas_contato"):
            contato = st.columns(2, gap="small")
            contato[0].page_link(
                interface.LINKEDIN, label="Falar comigo no LinkedIn", icon=":material/north_east:"
            )
            contato[1].page_link(
                interface.GITHUB, label="Outros projetos no GitHub", icon=":material/north_east:"
            )

    interface.secao("Para saber mais")
    with st.container(key="placas"):
        colunas = st.columns(4, gap="small")
        for coluna, (titulo, caminho) in zip(
            colunas,
            [
                ("Código no GitHub", ""),
                ("Cartão do modelo", "/blob/main/docs/modelo.md"),
                ("Decisões (ADRs)", "/tree/main/docs/decisoes"),
                ("Os dados da ANAC", "/blob/main/docs/dados.md"),
            ],
            strict=True,
        ):
            coluna.page_link(
                f"{interface.REPOSITORIO}{caminho}", label=titulo, icon=":material/north_east:"
            )
