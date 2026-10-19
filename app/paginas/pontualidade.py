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
from fdr.idioma import t

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
        partes.append(t(" da {cia}", cia=cias.set_index("cia").at[cia, "nome"]))
    if origem:
        partes.append(t(" saindo de {aeroporto}", aeroporto=aeroporto(origem)))
    if destino:
        partes.append(t(" para {aeroporto}", aeroporto=aeroporto(destino)))
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
            alt.Tooltip("hora:O", title=t("Hora")),
            alt.Tooltip("taxa_atraso:Q", title=t("Taxa de atraso"), format=".1%"),
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
                title=t("Hora prevista da partida (hora local)"),
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
                title=t("Taxa de atraso"),
                scale=alt.Scale(range=interface.RAMPA),
                legend=alt.Legend(format="%", gradientLength=220, orient="bottom"),
            ),
            tooltip=[
                alt.Tooltip("dia_semana:N", title=t("Dia")),
                alt.Tooltip("hora:O", title=t("Hora")),
                alt.Tooltip("taxa_atraso:Q", title=t("Taxa de atraso"), format=".1%"),
                alt.Tooltip("voos:Q", title=t("Voos"), format=",.0f"),
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
    inicios = {semana_do_ano(date(ano, m, 1)): painel.MESES[m - 1] for m in range(1, 13)}
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
            axis=alt.Axis(values=[painel.DIAS_SEMANA[d] for d in (0, 2, 4)]),
        ),
        tooltip=[
            alt.Tooltip("rotulo:N", title=t("Dia")),
            alt.Tooltip("taxa_atraso:Q", title=t("Taxa de atraso"), format=".1%"),
            alt.Tooltip("voos:Q", title=t("Voos"), format=",.0f"),
        ],
    )
    celulas = base.mark_rect(stroke=interface.SUPERFICIE, strokeWidth=1.5, cornerRadius=2).encode(
        color=alt.Color(
            "taxa_atraso:Q",
            title=t("Taxa de atraso"),
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
            "<br/>" + t("{voos_texto} voos · {taxa_texto} com atraso"),
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
        t("Pontualidade"),
        t("Quem atrasa, onde e quando"),
        t(
            "Voos nacionais realizados. Um voo atrasou quando partiu mais de 15 minutos depois "
            "do horário previsto. Escolha o período, a companhia e a rota."
        ),
        icone="relogio",
        meta=[
            (t("Critério"), t("Partida > 15 min")),
            (t("Base"), t("Voos nacionais")),
            (
                t("Meses disponíveis"),
                t(
                    "{inicio} a {fim}",
                    inicio=painel.nome_mes(meses[0]),
                    fim=painel.nome_mes(meses[-1]),
                ),
            ),
        ],
    )

    with interface.quadro("filtros"):
        inicio, fim = st.select_slider(
            t("Período"),
            options=meses,
            value=(meses[max(len(meses) - 12, 0)], meses[-1]),
            format_func=painel.nome_mes,
            key="periodo",  # com chave, a escolha não se perde quando o idioma muda o rótulo
        )
        filtros = st.columns(3)
        cia = filtros[0].selectbox(
            t("Companhia"),
            [None, *cias["cia"]],
            format_func=lambda c: t("Todas") if c is None else cias.set_index("cia").at[c, "nome"],
            key="filtro_cia",
        )
        origem = filtros[1].selectbox(
            t("Aeroporto de origem"),
            [None, *aeroportos["icao"]],
            format_func=lambda a: (
                t("Todos") if a is None else aeroportos.set_index("icao").at[a, "rotulo"]
            ),
            key="filtro_origem",
        )
        destino = None
        if origem:
            destinos = interface.dados("destinos", origem)
            destino = filtros[2].selectbox(
                t("Destino"),
                [None, *destinos["icao"]],
                format_func=lambda a: (
                    t("Todos") if a is None else destinos.set_index("icao").at[a, "rotulo"]
                ),
                key="filtro_destino",
            )
        else:
            filtros[2].selectbox(t("Destino"), [t("Escolha a origem primeiro")], disabled=True)

    evolucao = interface.dados("evolucao_mensal", inicio, fim, cia, origem, destino)
    if evolucao.empty:
        st.info(t("Nenhum voo com esses filtros. Tente um período maior ou outra combinação."))
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
            t("Voos no período"),
            painel.numero(total),
            t("{inicio} a {fim}", inicio=painel.nome_mes(inicio), fim=painel.nome_mes(fim)),
            tendencia=evolucao["voos"].tolist() if tendencia else None,
        ),
        interface.Numero(
            t("Taxa de atraso"),
            painel.porcentagem(taxa),
            t("acima de 15 min"),
            tendencia=evolucao["taxa_atraso"].tolist() if tendencia else None,
        ),
        interface.Numero(
            t("Mês mais difícil"),
            painel.nome_mes(pior_mes["mes"].date()),
            t("{taxa} de atraso", taxa=painel.porcentagem(pior_mes["taxa_atraso"])),
        ),
    ]
    if not por_hora.empty:
        numeros.append(
            interface.Numero(
                t("Hora mais crítica"),
                f"{int(por_hora.idxmax()):02d}h",
                t("{taxa} de atraso", taxa=painel.porcentagem(por_hora.max())),
            )
        )
    interface.numeros(numeros)
    if tendencia:
        interface.nota(t("As linhas mostram o período escolhido, mês a mês."))

    e = interface._e
    texto = t(
        "De {inicio} a {fim}, <b>{taxa}</b> dos {voos} voos nacionais{recorte} partiram com mais "
        "de 15 minutos de atraso. O mês mais difícil foi {pior_mes}, com <b>{taxa_pior}</b>",
        inicio=e(painel.nome_mes(inicio)),
        fim=e(painel.nome_mes(fim)),
        taxa=e(painel.porcentagem(taxa)),
        voos=e(painel.numero(total)),
        recorte=e(recorte(cia, origem, destino, cias)),
        pior_mes=e(painel.nome_mes(pior_mes["mes"].date())),
        taxa_pior=e(painel.porcentagem(pior_mes["taxa_atraso"])),
    )
    if not por_hora.empty:
        texto += t(
            "; a hora mais crítica, a das {hora}h, com <b>{taxa}</b>",
            hora=f"{int(por_hora.idxmax()):02d}",
            taxa=e(painel.porcentagem(por_hora.max())),
        )
    interface.resumo(texto + ".")

    esquerda, direita = st.columns(2, gap="medium")
    with esquerda, interface.quadro("companhias", altura="stretch"):
        interface.secao(
            t("Companhias"),
            t(
                "Taxa de atraso das companhias com pelo menos {minimo} voos.",
                minimo=painel.MIN_VOOS_RANKING,
            ),
        )
        ranking = interface.dados("ranking_companhias", inicio, fim, origem, destino)
        if ranking.empty:
            interface.nota(t("Nenhuma companhia com voos suficientes nesse recorte."))
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
                referencia=(
                    media,
                    t(
                        "Média das companhias do ranking: {taxa}",
                        taxa=painel.porcentagem(media),
                    ),
                ),
                chips=True,
            )
            interface.nota(
                t(
                    "As diferenças misturam rotas e horários diferentes: não é um ranking de "
                    "qualidade das companhias."
                )
            )
    with direita, interface.quadro("evolucao", altura="stretch"):
        interface.secao(t("Evolução mensal"), t("Taxa de atraso em cada mês do período."))
        interface.grafico(
            interface.grafico_linhas(
                evolucao,
                "mes",
                {"taxa_atraso": t("Taxa de atraso")},
                t("Taxa de atraso"),
                "%",
                marcas=[
                    (
                        pior_mes["mes"].date(),
                        t("pico: {taxa}", taxa=painel.porcentagem(pior_mes["taxa_atraso"])),
                    )
                ],
            ),
            altura=280,
        )

    with interface.quadro("horarios"):
        interface.secao(
            t("Quando os voos mais atrasam"),
            t(
                "Em cima, a taxa de atraso de cada hora prevista de partida (hora local do "
                "aeroporto); embaixo, a mesma taxa por dia da semana. Combinações com menos de "
                "{minimo} voos ficam em branco.",
                minimo=MIN_VOOS_CELULA,
            ),
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
            f"{painel.DIAS_SEMANA[d.weekday()]}, {painel.data(d)}" for d in dias["data"].dt.date
        ]
        piores = dias.nlargest(PIORES_DIAS, "taxa_atraso")
        dias["pior"] = dias.index.isin(piores.index)
        maximo = float(dias["taxa_atraso"].quantile(0.99))
        with interface.quadro("calendario"):
            interface.secao(
                t("Dia a dia"),
                t(
                    "A taxa de atraso de cada dia do período, uma coluna por semana. Quanto mais "
                    "escuro, mais atraso. Dias com menos de {minimo} voos ficam em branco; os "
                    "{piores} piores dias têm a borda preta.",
                    minimo=MIN_VOOS_DIA,
                    piores=len(piores),
                ),
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
                f'<div class="fdr-piores-titulo">{e(t("Os piores dias do período"))}</div>'
                f'<div class="fdr-piores">{itens}</div>'
            )

    # As rotas como arcos no mapa.
    rotas = interface.dados("mapa_rotas", inicio, fim, cia, origem, destino)
    if not rotas.empty:
        with interface.quadro("rotas"):
            interface.secao(
                t("As rotas no mapa"),
                t(
                    "As {rotas} rotas com mais voos no recorte (pelo menos 30 voos cada). A cor "
                    "é a taxa de atraso; a espessura, o número de voos. Passe o mouse num arco "
                    "para ver os números.",
                    rotas=len(rotas),
                ),
            )
            st.pydeck_chart(mapa_de_rotas(rotas), height=520)
            minimo, maximo = rotas["taxa_atraso"].quantile([0.05, 0.95])
            interface.html_bruto(
                interface.legenda_do_mapa(minimo, maximo, t("mais voos"), RAMPA_ROTAS)
            )

    interface.nota(
        t(
            "Os motivos dos atrasos não aparecem aqui: o campo de justificativa vem vazio em "
            "todos os arquivos da ANAC."
        )
    )
