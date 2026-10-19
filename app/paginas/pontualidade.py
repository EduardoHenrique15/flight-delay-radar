"""Pontualidade: exploração com filtros de período, companhia, aeroporto e rota.

Sem a análise de motivos: a justificativa do VRA vem vazia em 100% das linhas (docs/dados.md,
seção 4.3).
"""

import math
from datetime import date, timedelta

import altair as alt
import pandas as pd
import pydeck as pdk
import streamlit as st

from fdr import interface, painel

MIN_VOOS_CELULA = 30  # células do mapa de calor com menos voos ficam apagadas
LARGURA_EIXO_Y = 46  # a mesma largura do eixo nos dois gráficos de horário, para alinhá-los
MIN_VOOS_DIA = 20  # dias do calendário com menos voos ficam em branco
PIORES_DIAS = 5
# No mapa de rotas, só a parte escura da rampa: as cores claras somem sobre o mapa.
RAMPA_ROTAS = interface.RAMPA[2:]


def recorte(cia: str | None, origem: str | None, destino: str | None, cias) -> str:
    """O recorte dos filtros em palavras, para o resumo: " da Gol saindo de GRU (São Paulo)"."""
    cadastro = interface.dados("cadastro_aeroportos").set_index("icao")

    def aeroporto(icao: str) -> str:
        if icao not in cadastro.index:
            return icao
        return f"{cadastro.at[icao, 'iata']} ({cadastro.at[icao, 'cidade']})"

    partes = []
    if cia:
        partes.append(f" da {cias.set_index('cia').at[cia, 'nome']}")
    if origem:
        partes.append(f" saindo de {aeroporto(origem)}")
    if destino:
        partes.append(f" para {aeroporto(destino)}")
    return "".join(partes)


def grafico_por_hora(por_hora: pd.Series, horas: list[int]) -> alt.LayerChart:
    """Barras com a taxa de atraso de cada hora, alinhadas às colunas do mapa de calor; a hora
    mais crítica fica em preto, com o valor em cima."""
    tabela = pd.DataFrame({"hora": por_hora.index.astype(int), "taxa_atraso": por_hora.values})
    tabela["pico"] = tabela["hora"] == int(por_hora.idxmax())
    tabela["rotulo"] = [painel.porcentagem(t) for t in tabela["taxa_atraso"]]
    base = alt.Chart(tabela).encode(
        x=alt.X(
            "hora:O",
            scale=alt.Scale(domain=horas),
            axis=alt.Axis(labels=False, title=None, domain=True),
        ),
        y=alt.Y(
            "taxa_atraso:Q",
            title=None,
            axis=alt.Axis(
                format="%", tickCount=2, minExtent=LARGURA_EIXO_Y, maxExtent=LARGURA_EIXO_Y
            ),
        ),
        tooltip=[
            alt.Tooltip("hora:O", title="Hora"),
            alt.Tooltip("taxa_atraso:Q", title="Taxa de atraso", format=".1%"),
        ],
    )
    barras = base.mark_bar(width={"band": 0.72}).encode(
        color=alt.condition("datum.pico", alt.value(interface.PRETO), alt.value(interface.APAGADO))
    )
    valor = (
        base.transform_filter("datum.pico")
        .mark_text(dy=-8, fontWeight=700, color=interface.TINTA, font=interface.FONTE_TITULO)
        .encode(text="rotulo:N")
    )
    return barras + valor


def mapa_de_calor(calor: pd.DataFrame, horas: list[int]) -> alt.Chart:
    return (
        alt.Chart(calor)
        .mark_rect(stroke=interface.SUPERFICIE, strokeWidth=2, cornerRadius=2)
        .encode(
            x=alt.X(
                "hora:O",
                title="Hora prevista da partida (hora local)",
                scale=alt.Scale(domain=horas),
                axis=alt.Axis(
                    labelAngle=0, labelExpr="datum.value + 'h'", labelOverlap="parity", domain=False
                ),
            ),
            y=alt.Y(
                "dia_semana:N",
                sort=list(painel.DIAS_SEMANA),
                title=None,
                axis=alt.Axis(minExtent=LARGURA_EIXO_Y, maxExtent=LARGURA_EIXO_Y),
            ),
            color=alt.Color(
                "taxa_atraso:Q",
                title="Taxa de atraso",
                scale=alt.Scale(range=interface.RAMPA),
                legend=alt.Legend(format="%", gradientLength=220, orient="bottom"),
            ),
            tooltip=[
                alt.Tooltip("dia_semana:N", title="Dia"),
                alt.Tooltip("hora:O", title="Hora"),
                alt.Tooltip("taxa_atraso:Q", title="Taxa de atraso", format=".1%"),
                alt.Tooltip("voos:Q", title="Voos", format=",.0f"),
            ],
        )
    )


def semana_do_ano(dia: date) -> int:
    """A coluna do dia no calendário: semanas de segunda a domingo, a partir de 1º de janeiro."""
    return (dia.timetuple().tm_yday - 1 + date(dia.year, 1, 1).weekday()) // 7


def calendario_do_ano(dias: pd.DataFrame, ano: int, maximo: float, legenda: bool) -> alt.LayerChart:
    """Um ano do calendário de atrasos, como o calendário de contribuições do GitHub: uma coluna
    por semana, uma linha por dia da semana. Os piores dias do período têm a borda preta."""
    do_ano = dias[dias["ano"] == ano]
    inicios = {semana_do_ano(date(ano, m, 1)): painel.MESES_PT[m - 1] for m in range(1, 13)}
    rotulos = "{" + ", ".join(f"'{s}': '{m}'" for s, m in inicios.items()) + "}"
    base = alt.Chart(do_ano).encode(
        x=alt.X(
            "semana:O",
            title=None,
            scale=alt.Scale(domain=list(range(54))),
            axis=alt.Axis(
                values=list(inicios),
                labelExpr=f"{rotulos}[datum.value]",
                labelAngle=0,
                domain=False,
            ),
        ),
        y=alt.Y(
            "dia_semana:N",
            sort=list(painel.DIAS_SEMANA),
            title=None,
            axis=alt.Axis(values=["seg", "qua", "sex"]),
        ),
        tooltip=[
            alt.Tooltip("rotulo:N", title="Dia"),
            alt.Tooltip("taxa_atraso:Q", title="Taxa de atraso", format=".1%"),
            alt.Tooltip("voos:Q", title="Voos", format=",.0f"),
        ],
    )
    celulas = base.mark_rect(stroke=interface.SUPERFICIE, strokeWidth=1.5, cornerRadius=2).encode(
        color=alt.Color(
            "taxa_atraso:Q",
            title="Taxa de atraso",
            scale=alt.Scale(range=interface.RAMPA, domain=[0, maximo], clamp=True),
            legend=alt.Legend(format="%", gradientLength=220, orient="bottom") if legenda else None,
        )
    )
    piores = base.transform_filter("datum.pior").mark_rect(
        filled=False, stroke=interface.PRETO, strokeWidth=2.5, cornerRadius=2
    )
    return celulas + piores


def mapa_de_rotas(rotas: pd.DataFrame) -> pdk.Deck:
    """As rotas como arcos entre os aeroportos: a cor é a taxa de atraso; a espessura, os voos."""
    minimo, maximo = rotas["taxa_atraso"].quantile([0.05, 0.95])
    maior = float(rotas["voos"].max())
    arcos = rotas.assign(
        cor=[
            interface.cor_da_taxa(t, minimo, maximo, RAMPA_ROTAS, 210) for t in rotas["taxa_atraso"]
        ],
        # Em pixels (o padrão do ArcLayer). O pydeck transforma qualquer texto em expressão, por
        # isso as unidades não são passadas como texto.
        largura=[1 + 6 * math.sqrt(v / maior) for v in rotas["voos"]],
        rota=[
            f"{o} → {d}" for o, d in zip(rotas["iata_origem"], rotas["iata_destino"], strict=True)
        ],
        voos_texto=[painel.numero(v) for v in rotas["voos"]],
        taxa_texto=[painel.porcentagem(t) for t in rotas["taxa_atraso"]],
    )
    pontas = pd.concat(
        [
            rotas[["iata_origem", "lon_origem", "lat_origem"]].set_axis(
                ["iata", "lon", "lat"], axis=1
            ),
            rotas[["iata_destino", "lon_destino", "lat_destino"]].set_axis(
                ["iata", "lon", "lat"], axis=1
            ),
        ]
    ).drop_duplicates("iata")
    return pdk.Deck(
        layers=[
            pdk.Layer(
                "ArcLayer",
                id="rotas",
                data=arcos,
                get_source_position="[lon_origem, lat_origem]",
                get_target_position="[lon_destino, lat_destino]",
                get_source_color="cor",
                get_target_color="cor",
                get_width="largura",
                get_height=0.25,
                pickable=True,
                auto_highlight=True,
                highlight_color=[29, 95, 191, 230],
            ),
            pdk.Layer(
                "ScatterplotLayer",
                data=pontas,
                get_position="[lon, lat]",
                get_radius=45_000,
                radius_min_pixels=2,
                get_fill_color=[20, 22, 26, 220],
            ),
        ],
        initial_view_state=pdk.ViewState(latitude=-16.5, longitude=-52, zoom=3.15, pitch=30),
        map_provider="carto",
        map_style=pdk.map_styles.CARTO_LIGHT,
        tooltip={
            "html": "<b style='font-size:15px'>{rota}</b><br/>{cidade_origem} → {cidade_destino}"
            "<br/>{voos_texto} voos · {taxa_texto} com atraso",
            "style": {
                "fontFamily": "Barlow, sans-serif",
                "fontSize": "13px",
                "backgroundColor": interface.PRETO,
                "color": "#ffffff",
                "borderRadius": "2px",
            },
        },
    )


with interface.pagina_protegida():
    meses = interface.dados("meses")
    cias = interface.dados("companhias")
    aeroportos = interface.dados("aeroportos")
    interface.cabecalho(
        "Pontualidade",
        "Quem atrasa, onde e quando",
        "Voos nacionais realizados. Um voo atrasou quando partiu mais de 15 minutos depois do "
        "horário previsto. Escolha o período, a companhia e a rota.",
        icone="relogio",
        meta=[
            ("Critério", "Partida > 15 min"),
            ("Base", "Voos nacionais"),
            ("Meses disponíveis", f"{painel.nome_mes(meses[0])} a {painel.nome_mes(meses[-1])}"),
        ],
    )

    with interface.quadro("filtros"):
        inicio, fim = st.select_slider(
            "Período",
            options=meses,
            value=(meses[max(len(meses) - 12, 0)], meses[-1]),
            format_func=painel.nome_mes,
        )
        filtros = st.columns(3)
        cia = filtros[0].selectbox(
            "Companhia",
            [None, *cias["cia"]],
            format_func=lambda c: "Todas" if c is None else cias.set_index("cia").at[c, "nome"],
        )
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
                "Destino",
                [None, *destinos["icao"]],
                format_func=lambda a: (
                    "Todos" if a is None else destinos.set_index("icao").at[a, "rotulo"]
                ),
            )
        else:
            filtros[2].selectbox("Destino", ["Escolha a origem primeiro"], disabled=True)

    evolucao = interface.dados("evolucao_mensal", inicio, fim, cia, origem, destino)
    if evolucao.empty:
        st.info("Nenhum voo com esses filtros. Tente um período maior ou outra combinação.")
        st.stop()

    calor = interface.dados("mapa_de_calor", inicio, fim, cia, origem, destino)
    total = int(evolucao["voos"].sum())
    taxa = float((evolucao["taxa_atraso"] * evolucao["voos"]).sum() / total)
    pior_mes = evolucao.loc[evolucao["taxa_atraso"].idxmax()]
    por_hora = calor.groupby("hora").apply(
        lambda g: (g["taxa_atraso"] * g["voos"]).sum() / g["voos"].sum(), include_groups=False
    )
    voos_hora = calor.groupby("hora")["voos"].sum()
    por_hora = por_hora[voos_hora >= MIN_VOOS_CELULA]
    tendencia = len(evolucao) >= 3
    numeros = [
        interface.Numero(
            "Voos no período",
            painel.numero(total),
            f"{painel.nome_mes(inicio)} a {painel.nome_mes(fim)}",
            tendencia=evolucao["voos"].tolist() if tendencia else None,
        ),
        interface.Numero(
            "Taxa de atraso",
            painel.porcentagem(taxa),
            "acima de 15 min",
            tendencia=evolucao["taxa_atraso"].tolist() if tendencia else None,
        ),
        interface.Numero(
            "Mês mais difícil",
            painel.nome_mes(pior_mes["mes"].date()),
            f"{painel.porcentagem(pior_mes['taxa_atraso'])} de atraso",
        ),
    ]
    if not por_hora.empty:
        numeros.append(
            interface.Numero(
                "Hora mais crítica",
                f"{int(por_hora.idxmax()):02d}h",
                f"{painel.porcentagem(por_hora.max())} de atraso",
            )
        )
    interface.numeros(numeros)
    if tendencia:
        interface.nota("As linhas mostram o período escolhido, mês a mês.")

    e = interface._e
    texto = (
        f"De {e(painel.nome_mes(inicio))} a {e(painel.nome_mes(fim))}, "
        f"<b>{e(painel.porcentagem(taxa))}</b> dos {e(painel.numero(total))} voos nacionais"
        f"{e(recorte(cia, origem, destino, cias))} partiram com mais de 15 "
        f"minutos de atraso. O mês mais difícil foi {e(painel.nome_mes(pior_mes['mes'].date()))}, "
        f"com <b>{e(painel.porcentagem(pior_mes['taxa_atraso']))}</b>"
    )
    if not por_hora.empty:
        texto += (
            f"; a hora mais crítica, a das {int(por_hora.idxmax()):02d}h, com "
            f"<b>{e(painel.porcentagem(por_hora.max()))}</b>"
        )
    interface.resumo(texto + ".")

    esquerda, direita = st.columns(2, gap="medium")
    with esquerda, interface.quadro("companhias", altura="stretch"):
        interface.secao(
            "Companhias",
            f"Taxa de atraso das companhias com pelo menos {painel.MIN_VOOS_RANKING} voos.",
        )
        ranking = interface.dados("ranking_companhias", inicio, fim, origem, destino)
        if ranking.empty:
            interface.nota("Nenhuma companhia com voos suficientes nesse recorte.")
        else:
            media = float((ranking["taxa_atraso"] * ranking["voos"]).sum() / ranking["voos"].sum())
            interface.ranking(
                [
                    (
                        painel.CODIGOS_IATA.get(linha.cia, linha.cia),
                        linha.companhia,
                        linha.taxa_atraso,
                        painel.porcentagem(linha.taxa_atraso),
                    )
                    for linha in ranking.itertuples()
                ],
                maximo=max(float(ranking["taxa_atraso"].max()), media) * 1.1,
                referencia=(media, f"Média das companhias do ranking: {painel.porcentagem(media)}"),
                chips=True,
            )
            interface.nota(
                "As diferenças misturam rotas e horários diferentes: não é um ranking de "
                "qualidade das companhias."
            )
    with direita, interface.quadro("evolucao", altura="stretch"):
        interface.secao("Evolução mensal", "Taxa de atraso em cada mês do período.")
        interface.grafico(
            interface.grafico_linhas(
                evolucao,
                "mes",
                {"taxa_atraso": "Taxa de atraso"},
                "Taxa de atraso",
                "%",
                marcas=[
                    (pior_mes["mes"].date(), f"pico: {painel.porcentagem(pior_mes['taxa_atraso'])}")
                ],
            ),
            altura=280,
        )

    with interface.quadro("horarios"):
        interface.secao(
            "Quando os voos mais atrasam",
            "Em cima, a taxa de atraso de cada hora prevista de partida (hora local do "
            "aeroporto); embaixo, a mesma taxa por dia da semana. Combinações com menos de "
            f"{MIN_VOOS_CELULA} voos ficam em branco.",
        )
        calor = calor[calor["voos"] >= MIN_VOOS_CELULA]
        horas = sorted({int(h) for h in calor["hora"]} | {int(h) for h in por_hora.index})
        if not por_hora.empty:
            interface.grafico(grafico_por_hora(por_hora, horas), altura=90)
        interface.grafico(mapa_de_calor(calor, horas), altura=300)

    # Dia a dia: um calendário por ano, como o de contribuições do GitHub.
    ultimo_dia = date(fim.year + fim.month // 12, fim.month % 12 + 1, 1) - timedelta(days=1)
    dias = interface.dados("calendario", inicio, fim, cia, origem, destino)
    dias = dias[(dias["voos"] >= MIN_VOOS_DIA)]
    dias = dias[(dias["data"].dt.date >= inicio) & (dias["data"].dt.date <= ultimo_dia)].copy()
    if not dias.empty:
        dias["ano"] = dias["data"].dt.year
        dias["semana"] = [semana_do_ano(d) for d in dias["data"].dt.date]
        dias["dia_semana"] = [painel.DIAS_SEMANA[d.weekday()] for d in dias["data"].dt.date]
        dias["rotulo"] = [
            f"{painel.DIAS_SEMANA[d.weekday()]}, {d:%d/%m/%Y}" for d in dias["data"].dt.date
        ]
        piores = dias.nlargest(PIORES_DIAS, "taxa_atraso")
        dias["pior"] = dias.index.isin(piores.index)
        maximo = float(dias["taxa_atraso"].quantile(0.99))
        with interface.quadro("calendario"):
            interface.secao(
                "Dia a dia",
                "A taxa de atraso de cada dia do período, uma coluna por semana. Quanto mais "
                f"escuro, mais atraso. Dias com menos de {MIN_VOOS_DIA} voos ficam em branco; os "
                f"{len(piores)} piores dias têm a borda preta.",
            )
            anos = sorted(dias["ano"].unique())
            for ano in anos:
                interface.html_bruto(f'<p class="fdr-ano">{int(ano)}</p>')
                interface.grafico(
                    calendario_do_ano(dias, int(ano), maximo, legenda=ano == anos[-1]),
                    # O último ano leva a legenda, que o Streamlit conta dentro da altura.
                    altura=230 if ano == anos[-1] else 150,
                )
            itens = "".join(
                f"<span>{e(r.rotulo)} <b>{e(painel.porcentagem(r.taxa_atraso))}</b></span>"
                for r in piores.itertuples()
            )
            interface.html_bruto(
                f'<div class="fdr-piores-titulo">Os piores dias do período</div>'
                f'<div class="fdr-piores">{itens}</div>'
            )

    # As rotas como arcos no mapa.
    rotas = interface.dados("mapa_rotas", inicio, fim, cia, origem, destino)
    if not rotas.empty:
        with interface.quadro("rotas"):
            interface.secao(
                "As rotas no mapa",
                f"As {len(rotas)} rotas com mais voos no recorte (pelo menos 30 voos cada). A cor "
                "é a taxa de atraso; a espessura, o número de voos. Passe o mouse num arco para "
                "ver os números.",
            )
            st.pydeck_chart(mapa_de_rotas(rotas), height=520)
            minimo, maximo = rotas["taxa_atraso"].quantile([0.05, 0.95])
            interface.html_bruto(
                interface.legenda_do_mapa(minimo, maximo, "mais voos", RAMPA_ROTAS)
            )

    interface.nota(
        "Os motivos dos atrasos não aparecem aqui: o campo de justificativa vem vazio em todos "
        "os arquivos da ANAC."
    )
