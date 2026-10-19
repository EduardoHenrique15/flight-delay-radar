"""Visão geral: os números do último mês, o painel de partidas com a chance prevista, o mapa dos
atrasos por aeroporto (clicável, como o Misery Map do FlightAware) e os caminhos para as outras
páginas."""

import math
from datetime import date, datetime, timedelta

import pydeck as pdk
import streamlit as st

from fdr import interface, painel
from fdr.idioma import Traduzidos, t
from fdr.previsao import Voo

TEXTOS_FAIXA = Traduzidos({"baixa": "No horário", "média": "Atenção", "alta": "Risco de atraso"})
SITUACOES_FAIXA = {"baixa": "bom", "média": "atencao", "alta": "critico"}


def variacao_relativa(serie) -> tuple[str, str, str] | None:
    """Variação percentual do último mês contra o anterior (mais voos não é bom nem ruim)."""
    if len(serie) < 2 or not serie.iloc[-2]:
        return None
    mudanca = serie.iloc[-1] / serie.iloc[-2] - 1
    return (painel.porcentagem(abs(mudanca)), "sobe" if mudanca >= 0 else "desce", "neutro")


def variacao_em_pontos(serie) -> tuple[str, str, str] | None:
    """Variação em pontos percentuais; para atraso, subir é ruim."""
    if len(serie) < 2:
        return None
    mudanca = (serie.iloc[-1] - serie.iloc[-2]) * 100
    texto = t("{pontos} p.p.", pontos=painel.decimal(abs(mudanca), 1))
    return (texto, "sobe" if mudanca >= 0 else "desce", "ruim" if mudanca >= 0 else "bom")


def numero_de_voo(cia: str, numero) -> str:
    """Ex.: G3 1032, como nos painéis dos aeroportos."""
    codigo = painel.CODIGOS_IATA.get(cia, cia)
    return f"{codigo} {numero}" if numero else codigo


def painel_do_aeroporto(linha, rotas) -> str:
    e = interface._e
    lista = (
        interface.ranking_html(
            [
                (r.iata, r.cidade, r.taxa_atraso, painel.porcentagem(r.taxa_atraso))
                for r in rotas.itertuples()
            ],
            maximo=float(rotas["taxa_atraso"].max()),
            cor=interface.COMPARACAO,
        )
        if len(rotas)
        else '<p class="fdr-nota">'
        f"{e(t('Poucos voos por rota neste aeroporto para comparar.'))}</p>"
    )
    return (
        f'<div class="fdr-aeroporto"><div class="codigo">{e(linha.iata)}</div>'
        f'<div class="nome"><b>{e(linha.cidade)}{" (" + e(linha.uf) + ")" if linha.uf else ""}'
        f"</b><br>{e(linha.nome or '')}</div>"
        f'<div class="numeros"><div><div class="r">{e(t("Partidas"))}</div>'
        f'<div class="v">{e(painel.numero(linha.voos))}</div></div>'
        f'<div><div class="r">{e(t("Atrasaram"))}</div>'
        f'<div class="v">{e(painel.porcentagem(linha.taxa_atraso))}</div></div></div>'
        f'<div class="titulo-lista">{e(t("Para onde os voos daqui mais atrasam"))}</div>'
        f"{lista}</div>"
    )


with interface.pagina_protegida():
    resumo = interface.dados("resumo_ultimo_mes")
    mes = painel.nome_mes(resumo["mes"])
    info = interface.manifest()
    primeiro = painel.nome_mes(datetime.fromisoformat(info["primeiro_mes"]).date())
    interface.cabecalho(
        t("Aviação nacional · dados públicos da ANAC"),
        t("Pontualidade dos voos no Brasil"),
        t(
            "Quanto os voos nacionais atrasam, onde e quando, a chance de atraso de um voo futuro "
            "e o desempenho mês a mês do modelo que faz essa previsão."
        ),
        icone="partidas",
        meta=[
            (t("Último mês publicado"), mes),
            (t("Período no app"), t("{inicio} a {fim}", inicio=primeiro, fim=mes)),
            (t("Processado em"), painel.data(datetime.fromisoformat(info["gerado_em"]).date())),
        ],
    )

    geral = interface.dados("serie_mensal")
    anterior = geral.iloc[-2] if len(geral) > 1 else None
    rotulo_anterior = (
        t("vs. {mes}", mes=painel.nome_mes(anterior["mes"].date())) if anterior is not None else ""
    )
    numeros = [
        interface.Numero(
            t("Voos nacionais realizados"),
            painel.numero(resumo["voos_nacionais_realizados"]),
            rotulo_anterior,
            variacao=variacao_relativa(geral["voos"]),
            tendencia=list(geral["voos"]),
        ),
        interface.Numero(
            t("Atraso acima de 15 min"),
            painel.porcentagem(resumo["taxa_atraso"]),
            rotulo_anterior,
            variacao=variacao_em_pontos(geral["taxa_atraso"]),
            tendencia=list(geral["taxa_atraso"]),
        ),
    ]
    if resumo["cia_mais_pontual"]:
        nome_cia, taxa_cia, codigo_cia = resumo["cia_mais_pontual"]
        serie_cia = interface.dados("serie_mensal", codigo_cia)
        numeros.append(
            interface.Numero(
                t("Companhia mais pontual"),
                nome_cia,
                t("{taxa} de atraso", taxa=painel.porcentagem(taxa_cia)),
                t(
                    "Entre as companhias com pelo menos {minimo} voos no mês.",
                    minimo=painel.MIN_VOOS_DESTAQUE,
                ),
                tendencia=list(serie_cia["taxa_atraso"]),
            )
        )
    if resumo["aeroporto_mais_atraso"]:
        codigo, taxa_aeroporto, cidade, icao_pior = resumo["aeroporto_mais_atraso"]
        serie_aeroporto = interface.dados("serie_mensal", None, icao_pior)
        numeros.append(
            interface.Numero(
                t("Aeroporto com mais atraso"),
                codigo,
                t(
                    "{taxa} de atraso · {cidade}",
                    taxa=painel.porcentagem(taxa_aeroporto),
                    cidade=cidade,
                ),
                t(
                    "Entre os aeroportos com pelo menos {minimo} partidas no mês.",
                    minimo=painel.MIN_VOOS_DESTAQUE,
                ),
                tendencia=list(serie_aeroporto["taxa_atraso"]),
            )
        )
    interface.numeros(numeros)
    interface.nota(t("As linhas mostram os últimos 12 meses."))

    if anterior is not None and resumo["cia_mais_pontual"] and resumo["aeroporto_mais_atraso"]:
        diferenca = (resumo["taxa_atraso"] - anterior["taxa_atraso"]) * 100
        mes_anterior = painel.nome_mes(anterior["mes"].date())
        pontos = painel.decimal(abs(diferenca), 1)
        if abs(diferenca) < 0.05:
            comparacao = t("praticamente igual ao mês anterior")
        elif diferenca > 0:
            comparacao = t("{pontos} p.p. acima de {mes}", pontos=pontos, mes=mes_anterior)
        else:
            comparacao = t("{pontos} p.p. abaixo de {mes}", pontos=pontos, mes=mes_anterior)
        e = interface._e
        interface.resumo(
            t(
                "Em {mes}, <b>{taxa}</b> dos {voos} voos nacionais partiram com mais de 15 "
                "minutos de atraso, {comparacao}. {cidade} ({codigo}) teve a maior taxa entre os "
                "grandes aeroportos, <b>{taxa_aeroporto}</b>; a {cia} foi a companhia mais "
                "pontual, com <b>{taxa_cia}</b>.",
                mes=e(mes),
                taxa=e(painel.porcentagem(resumo["taxa_atraso"])),
                voos=e(painel.numero(resumo["voos_nacionais_realizados"])),
                comparacao=e(comparacao),
                cidade=e(cidade),
                codigo=e(codigo),
                taxa_aeroporto=e(painel.porcentagem(taxa_aeroporto)),
                cia=e(nome_cia),
                taxa_cia=e(painel.porcentagem(taxa_cia)),
            )
        )

    # O tamanho do problema: as horas de atraso somadas no mês.
    impacto = interface.dados("impacto_do_mes", resumo["mes"])
    if impacto["voos_atrasados"]:
        e = interface._e
        horas = impacto["horas"]
        mediana = (
            t(
                " Metade deles atrasou mais de {minutos} minutos.",
                minutos=painel.numero(impacto["mediana_min"]),
            )
            if impacto["mediana_min"] is not None
            else ""
        )
        texto_impacto = t(
            "Foi o que somaram, na partida, os <b>{voos} voos nacionais</b> que saíram com mais "
            "de 15 minutos de atraso em {mes}: o equivalente a <b>{dias} dias</b> de espera.",
            voos=e(painel.numero(impacto["voos_atrasados"])),
            mes=e(mes),
            dias=e(painel.numero(horas / 24)),
        )
        interface.html_bruto(
            f'<div class="fdr-impacto"><div class="numero">{e(painel.numero(horas))}'
            f'<span>{e(t("horas de atraso"))}</span></div><div class="texto">{texto_impacto}'
            f"{e(mediana)}</div></div>"
        )

    # Painel de partidas: voos típicos das rotas mais movimentadas, com a chance prevista.
    previsor = interface.previsor()
    inicio_previsao, fim_previsao = previsor.periodo()
    dia = min(max(date.today() + timedelta(days=1), inicio_previsao), fim_previsao)
    tipicos = interface.dados("voos_tipicos", resumo["mes"])
    cadastro = interface.dados("cadastro_aeroportos").set_index("icao")
    nomes_cias = interface.dados("companhias").set_index("cia")["nome"].to_dict()
    resultados = previsor.prever(
        [Voo(v.cia, v.origem, v.destino, dia, int(v.hora)) for v in tipicos.itertuples()]
    )
    interface.secao(
        t("Painel de partidas"),
        t(
            "As {rotas} rotas mais movimentadas de {mes}, cada uma com o voo mais comum "
            "(companhia, número e horário). A chance de atraso é a que o modelo prevê para o dia.",
            rotas=len(tipicos),
            mes=mes,
        ),
    )
    interface.painel_de_partidas(
        [
            interface.Partida(
                hora=f"{r['voo'].hora:02d}:00",
                voo=numero_de_voo(r["voo"].cia, v.numero_voo),
                companhia=nomes_cias.get(r["voo"].cia, r["voo"].cia),
                origem=cadastro.at[r["voo"].origem, "iata"],
                destino=cadastro.at[r["voo"].destino, "iata"],
                cidade_destino=cadastro.at[r["voo"].destino, "cidade"],
                chance=painel.porcentagem(r["probabilidade"]),
                situacao=SITUACOES_FAIXA[r["faixa"]],
                texto_situacao=TEXTOS_FAIXA[r["faixa"]],
            )
            for r, v in zip(resultados, tipicos.itertuples(), strict=True)
        ],
        dia=f"{painel.DIAS_SEMANA[dia.isoweekday() - 1]} {dia.day:02d} "
        f"{painel.MESES[dia.month - 1]} {dia.year}",
        legenda=[
            ("bom", t("No horário: abaixo de 15%, a média dos voos")),
            ("atencao", t("Atenção: de 15% a 25%")),
            ("critico", t("Risco de atraso: 25% ou mais")),
        ],
    )

    interface.secao(
        t("Onde os voos mais atrasam"),
        t(
            "Partidas nacionais em {mes}. Clique num aeroporto para ver para onde os voos dele "
            "mais atrasam.",
            mes=mes,
        ),
    )
    aeroportos = interface.dados("mapa_aeroportos", resumo["mes"])
    minimo, maximo = aeroportos["taxa_atraso"].quantile([0.05, 0.95])
    pontos = aeroportos.assign(
        cor=[interface.cor_da_taxa(t, minimo, maximo) for t in aeroportos["taxa_atraso"]],
        raio=[2300 * math.sqrt(v) for v in aeroportos["voos"]],
        taxa_texto=[painel.porcentagem(t) for t in aeroportos["taxa_atraso"]],
        voos_texto=[painel.numero(v) for v in aeroportos["voos"]],
        cidade=aeroportos["cidade"].fillna(aeroportos["iata"]),
    )
    mapa, lado = st.columns([1.75, 1], gap="large")
    with mapa:
        evento = st.pydeck_chart(
            pdk.Deck(
                layers=[
                    pdk.Layer(
                        "ScatterplotLayer",
                        id="aeroportos",
                        data=pontos,
                        get_position="[longitude, latitude]",
                        get_radius="raio",
                        get_fill_color="cor",
                        get_line_color=[20, 22, 26, 170],
                        line_width_min_pixels=1,
                        stroked=True,
                        pickable=True,
                        auto_highlight=True,
                        highlight_color=[29, 95, 191, 200],
                    )
                ],
                initial_view_state=pdk.ViewState(latitude=-14.8, longitude=-52, zoom=3.15),
                map_provider="carto",
                map_style=pdk.map_styles.CARTO_LIGHT,
                tooltip={
                    "html": "<b style='font-size:15px'>{iata}</b> · {cidade}<br/>"
                    + t("{voos_texto} partidas · {taxa_texto} com atraso"),
                    "style": {
                        "fontFamily": "Barlow, sans-serif",
                        "fontSize": "13px",
                        "backgroundColor": interface.PRETO,
                        "color": "#ffffff",
                        "borderRadius": "2px",
                    },
                },
            ),
            height=480,
            on_select="rerun",
            selection_mode="single-object",
            key="mapa_aeroportos",
        )
        interface.html_bruto(interface.legenda_do_mapa(minimo, maximo, t("mais partidas")))
    with lado:
        escolhidos = []
        if evento is not None:
            escolhidos = (evento.get("selection") or {}).get("objects", {}).get("aeroportos", [])
        # Sem clique, o aeroporto com mais atraso do mês (ou, sem ele, o mais movimentado).
        pior = resumo["aeroporto_mais_atraso"][3] if resumo["aeroporto_mais_atraso"] else None
        icao = escolhidos[0]["icao"] if escolhidos else pior
        linha = next(aeroportos[aeroportos["icao"] == icao].itertuples(), None)
        if linha is None:
            linha = next(aeroportos.itertuples(), None)
        if linha is not None:
            rotas = interface.dados("rotas_com_atraso", resumo["mes"], linha.icao)
            interface.html_bruto(painel_do_aeroporto(linha, rotas))
            dica = t(" Clique num aeroporto para ver outro.")
            if not escolhidos and linha.icao == pior:
                dica = t(" Mostrando o aeroporto com mais atraso; clique em outro.")
            interface.nota(t("Rotas com pelo menos 60 voos no mês.") + ("" if escolhidos else dica))

    interface.secao(t("Para onde ir"))
    placas = st.container(key="placas")
    atalhos = placas.columns(3, gap="medium")
    for coluna, (pagina, titulo, texto) in zip(
        atalhos,
        [
            (
                "paginas/previsao.py",
                "Prever o risco de um voo",
                "Rota, companhia, data e hora: a chance de atraso e o que mais pesa nela.",
            ),
            (
                "paginas/pontualidade.py",
                "Explorar a pontualidade",
                "Ranking das companhias, horários críticos e evolução mês a mês.",
            ),
            (
                "paginas/assistente.py",
                "Perguntar aos dados",
                "Pergunte em português; o assistente escreve o SQL e mostra a consulta.",
            ),
        ],
        strict=True,
    ):
        with coluna:
            st.page_link(
                pagina,
                label=t(titulo),
                icon=":material/arrow_forward:",
                query_params=interface.com_idioma({}),
            )
            interface.nota(t(texto))
