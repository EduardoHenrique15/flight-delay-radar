"""Sobre o modelo: metodologia em linguagem simples, métricas do teste com intervalos e o
baseline, onde o modelo erra (por grupo), o uso na prática (regra de alerta), limitações e links.
Todos os números vêm de models/metrics.json, metadata.json, explicacao_global.json e
uso_pratico.json."""

import altair as alt
import pandas as pd
import streamlit as st

from fdr import config, interface, painel

SEGMENTOS = {
    "companhia": "Companhia",
    "aeroporto_origem": "Aeroporto de origem",
    "faixa_horaria": "Horário",
    "mes": "Mês",
}
FRACAO_INICIAL = 10  # % de voos avisados que a página mostra primeiro (o lift do metrics.json)


def grupos_do_segmento(segmento: str, linhas: list[dict]) -> pd.DataFrame:
    """As linhas de um segmento do metrics.json, com um nome legível para cada grupo."""
    grupos = pd.DataFrame(linhas).rename(columns={segmento: "codigo"})
    if segmento == "companhia":
        nomes = interface.dados("companhias").set_index("cia")["nome"].to_dict()
        grupos["grupo"] = [nomes.get(c, c) for c in grupos["codigo"]]
    elif segmento == "aeroporto_origem":
        cadastro = interface.dados("cadastro_aeroportos").set_index("icao")
        grupos["grupo"] = [
            f"{cadastro.at[c, 'iata']} · {cadastro.at[c, 'cidade']}" if c in cadastro.index else c
            for c in grupos["codigo"]
        ]
    elif segmento == "mes":
        grupos["grupo"] = [painel.nome_mes(pd.Timestamp(m).date()) for m in grupos["codigo"]]
        grupos = grupos.sort_values("codigo")
    else:
        grupos["grupo"] = [g[:1].upper() + g[1:] for g in grupos["codigo"]]
        grupos = grupos.sort_values("codigo", key=lambda c: c.str.extract(r"(\d+)h")[0].astype(int))
    return grupos.reset_index(drop=True)


def grafico_halteres(
    grupos: pd.DataFrame, campos: dict[str, tuple[str, str]], formato: str, titulo_x: str
) -> alt.LayerChart:
    """Um ponto por série em cada grupo, ligados por uma linha: a distância é a diferença."""
    ordem = list(grupos["grupo"])
    longo = grupos.melt(
        id_vars=["grupo", "voos"], value_vars=list(campos), var_name="serie", value_name="valor"
    )
    longo["serie"] = longo["serie"].map({k: rotulo for k, (rotulo, _) in campos.items()})
    cores = alt.Scale(
        domain=[rotulo for rotulo, _ in campos.values()], range=[cor for _, cor in campos.values()]
    )
    eixo_y = alt.Y("grupo:N", sort=ordem, title=None, axis=alt.Axis(labelLimit=200))
    linha = (
        alt.Chart(longo)
        .mark_rule(color=interface.APAGADO, strokeWidth=3)
        .encode(x=alt.X("min(valor):Q"), x2="max(valor):Q", y=eixo_y)
    )
    pontos = (
        alt.Chart(longo)
        .mark_circle(size=120, opacity=1)
        .encode(
            x=alt.X("valor:Q", title=titulo_x, axis=alt.Axis(format=formato, grid=True)),
            y=eixo_y,
            color=alt.Color(
                "serie:N", scale=cores, title=None, legend=alt.Legend(orient="top", offset=4)
            ),
            tooltip=[
                alt.Tooltip("grupo:N", title="Grupo"),
                alt.Tooltip("serie:N", title="Série"),
                alt.Tooltip("valor:Q", title="Valor", format=formato.replace("%", ".1%")),
                alt.Tooltip("voos:Q", title="Voos no teste", format=",.0f"),
            ],
        )
    )
    return linha + pontos


def grafico_cobertura(modelo: pd.DataFrame, base: pd.DataFrame, fracao: float) -> alt.LayerChart:
    """A curva de ganho: a parcela dos atrasos pegos ao avisar os X% de voos de maior risco."""
    origem = pd.DataFrame({"fracao": [0.0], "cobertura": [0.0]})
    curvas = pd.concat(
        [
            pd.concat([origem, modelo]).assign(serie="Modelo"),
            pd.concat([origem, base]).assign(serie="Baseline"),
            pd.DataFrame({"fracao": [0.0, 0.5], "cobertura": [0.0, 0.5], "serie": "Ao acaso"}),
        ]
    )
    cores = alt.Scale(
        domain=["Modelo", "Baseline", "Ao acaso"],
        range=[interface.DESTAQUE, interface.COMPARACAO, interface.APAGADO],
    )
    linhas = (
        alt.Chart(curvas)
        .mark_line(strokeWidth=2.5)
        .encode(
            x=alt.X(
                "fracao:Q",
                title="Voos avisados (os de maior risco)",
                axis=alt.Axis(format="%", grid=True),
                scale=alt.Scale(domain=[0, 0.5]),
            ),
            y=alt.Y(
                "cobertura:Q",
                title="Atrasos pegos",
                axis=alt.Axis(format="%"),
                scale=alt.Scale(domain=[0, 1]),
            ),
            color=alt.Color(
                "serie:N", scale=cores, title=None, legend=alt.Legend(orient="top", offset=4)
            ),
            strokeDash=alt.condition(
                "datum.serie == 'Ao acaso'", alt.value([4, 4]), alt.value([1, 0])
            ),
            tooltip=[
                alt.Tooltip("serie:N", title="Série"),
                alt.Tooltip("fracao:Q", title="Voos avisados", format=".0%"),
                alt.Tooltip("cobertura:Q", title="Atrasos pegos", format=".1%"),
            ],
        )
    )
    marca = (
        alt.Chart(pd.DataFrame({"fracao": [fracao]}))
        .mark_rule(color=interface.PRETO, strokeDash=[2, 3])
        .encode(x="fracao:Q")
    )
    ponto = (
        alt.Chart(modelo[modelo["fracao"].round(2) == round(fracao, 2)])
        .mark_circle(size=110, color=interface.DESTAQUE, opacity=1)
        .encode(x="fracao:Q", y="cobertura:Q")
    )
    return marca + linhas + ponto


def mostrar_onde_erra(segmentos: dict) -> None:
    e = interface._e
    interface.secao(
        "Onde o modelo erra",
        "O mesmo teste, separado por grupos. O PR-AUC muda com a taxa de atraso de cada grupo; "
        "por isso, compare o modelo com o baseline na mesma linha, e não uma linha com a outra.",
    )
    disponiveis = [k for k in SEGMENTOS if segmentos.get(k)]
    st.session_state.setdefault("segmento", disponiveis[0])
    segmento = st.segmented_control(
        "Separar por", disponiveis, format_func=SEGMENTOS.get, required=True, key="segmento"
    )
    grupos = grupos_do_segmento(segmento, segmentos[segmento])
    altura = 38 * len(grupos) + 40

    perdeu = grupos[grupos["pr_auc"] <= grupos["pr_auc_baseline"]]
    grupos["desvio"] = grupos["taxa_prevista"] - grupos["taxa_real"]
    pior = grupos.loc[grupos["desvio"].abs().idxmax()]
    sentido = "acima" if pior["desvio"] > 0 else "abaixo"
    if perdeu.empty:
        texto = f"O modelo supera o baseline em <b>todos os {len(grupos)} grupos</b> deste recorte."
    else:
        nomes = ", ".join(f"<b>{e(g)}</b>" for g in perdeu["grupo"])
        texto = (
            f"O modelo supera o baseline em {len(grupos) - len(perdeu)} de {len(grupos)} grupos; "
            f"em {nomes}, não."
        )
    pontos = painel.decimal(abs(pior["desvio"]) * 100, 1)
    texto += (
        f" O maior erro de calibração é em <b>{e(pior['grupo'])}</b>: previu "
        f"{e(painel.porcentagem(pior['taxa_prevista']))} de atrasos, e foram "
        f"{e(painel.porcentagem(pior['taxa_real']))} (a previsão ficou {e(pontos)} p.p. "
        f"{sentido} do real)."
    )
    interface.resumo(texto)

    esquerda, direita = st.columns(2, gap="medium")
    with esquerda, interface.quadro("acerto_grupo", altura="stretch"):
        interface.secao(
            "Acerto em cada grupo",
            "PR-AUC do modelo e do baseline (maior é melhor).",
        )
        interface.grafico(
            grafico_halteres(
                grupos,
                {
                    "pr_auc_baseline": ("Baseline", interface.COMPARACAO),
                    "pr_auc": ("Modelo", interface.DESTAQUE),
                },
                ".2f",
                "PR-AUC",
            ),
            altura=altura,
        )
    with direita, interface.quadro("calibracao_grupo", altura="stretch"):
        interface.secao(
            "Atrasos previstos contra os reais",
            "A taxa média prevista pelo modelo e a taxa real de atraso no grupo.",
        )
        interface.grafico(
            grafico_halteres(
                grupos,
                {
                    "taxa_real": ("Real", interface.PRETO),
                    "taxa_prevista": ("Previsto", interface.DESTAQUE),
                },
                "%",
                "Voos com mais de 15 min de atraso",
            ),
            altura=altura,
        )
    interface.nota(
        "Só grupos com pelo menos 1.000 voos no teste; aeroportos: os 10 com mais partidas."
    )


def mostrar_uso_pratico() -> None:
    e = interface._e
    interface.secao(
        "Usar o modelo na prática",
        "Uma regra simples: avisar os passageiros dos voos com maior risco previsto. Quanto mais "
        "voos avisados, mais atrasos o aviso pega, mas mais avisos são alarme falso.",
    )
    caminho = config.PASTA_MODELOS / "uso_pratico.json"
    if not caminho.exists():
        interface.aviso(
            "Falta o models/uso_pratico.json: rode python -m fdr.pipeline --stage pratica."
        )
        return
    uso = interface.json_do_projeto("models/uso_pratico.json")
    modelo = pd.DataFrame(uso["por_fracao"]["modelo"])
    base = pd.DataFrame(uso["por_fracao"]["baseline"])

    with interface.quadro("alerta"):
        st.session_state.setdefault("fracao_alerta", FRACAO_INICIAL)
        porcento = st.slider(
            "Avisar os voos de maior risco (% de todos os voos)",
            min_value=int(round(modelo["fracao"].min() * 100)),
            max_value=int(round(modelo["fracao"].max() * 100)),
            step=1,
            format="%d%%",
            key="fracao_alerta",
        )
        linha = modelo[modelo["fracao"].round(2) == round(porcento / 100, 2)].iloc[0]
        linha_base = base[base["fracao"].round(2) == round(porcento / 100, 2)].iloc[0]
        lift = linha["precisao"] / uso["taxa_real"]
        interface.numeros(
            [
                interface.Numero(
                    "Voos avisados",
                    painel.numero(linha["voos"]),
                    f"de {painel.numero(uso['voos'])} no teste · chance a partir de "
                    f"{painel.porcentagem(linha['limiar'])}",
                ),
                interface.Numero(
                    "Atrasaram, dos avisados",
                    painel.porcentagem(linha["precisao"]),
                    f"{painel.decimal(lift, 1)}x a média ({painel.porcentagem(uso['taxa_real'])})"
                    f" · baseline {painel.porcentagem(linha_base['precisao'])}",
                    "A precisão do aviso: dos voos avisados, a parcela que atrasou de verdade.",
                ),
                interface.Numero(
                    "Atrasos pegos",
                    painel.porcentagem(linha["cobertura"]),
                    f"de {painel.numero(uso['atrasos'])} atrasos · baseline "
                    f"{painel.porcentagem(linha_base['cobertura'])}",
                    "A cobertura do aviso: dos voos que atrasaram, a parcela que foi avisada.",
                ),
                interface.Numero(
                    "Alarmes falsos",
                    painel.porcentagem(1 - linha["precisao"]),
                    "dos avisos, o voo saiu no horário",
                ),
            ]
        )
        alarmes = 1 - linha["precisao"]
        interface.resumo(
            f"Avisando os <b>{porcento}%</b> de voos com maior risco, "
            f"<b>{e(painel.porcentagem(linha['precisao']))}</b> deles atrasaram, "
            f"{e(painel.decimal(lift, 1))} vezes a média, e o aviso pegou "
            f"<b>{e(painel.porcentagem(linha['cobertura']))}</b> de todos os atrasos. "
            f"Em troca, {e(painel.porcentagem(alarmes))} dos avisos seriam alarme falso. "
            f"Com o baseline, a mesma regra pega {e(painel.porcentagem(linha_base['cobertura']))}"
            " dos atrasos."
        )

    with interface.quadro("curva_ganho"):
        interface.secao(
            "Quantos atrasos o aviso pega",
            "A curva de ganho no teste. Avisar ao acaso pega a mesma parcela dos atrasos que a "
            "de voos avisados (a linha tracejada).",
        )
        interface.grafico(grafico_cobertura(modelo, base, porcento / 100), altura=300)
    interface.nota(
        "Do teste, usado uma única vez. Sem clima e sem a rotação do avião, o modelo erra muitos "
        "atrasos: serve para priorizar, não para garantir."
    )


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

    mostrar_onde_erra(teste["segmentos"])
    mostrar_uso_pratico()

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
