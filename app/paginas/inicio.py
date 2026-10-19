"""Visão geral: os números do último mês, o painel de partidas com a chance prevista, o mapa dos
atrasos por aeroporto (clicável, como o Misery Map do FlightAware) e os caminhos para as outras
páginas."""

import math
from datetime import date, datetime, timedelta

import pydeck as pdk
import streamlit as st

from fdr import interface, painel
from fdr.previsao import Voo

TEXTOS_FAIXA = {"baixa": "No horário", "média": "Atenção", "alta": "Risco de atraso"}
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
    texto = f"{painel.decimal(abs(mudanca), 1)} p.p."
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
        else '<p class="fdr-nota">Poucos voos por rota neste aeroporto para comparar.</p>'
    )
    return (
        f'<div class="fdr-aeroporto"><div class="codigo">{e(linha.iata)}</div>'
        f'<div class="nome"><b>{e(linha.cidade)}{" (" + e(linha.uf) + ")" if linha.uf else ""}'
        f"</b><br>{e(linha.nome or '')}</div>"
        f'<div class="numeros"><div><div class="r">Partidas</div>'
        f'<div class="v">{e(painel.numero(linha.voos))}</div></div>'
        f'<div><div class="r">Atrasaram</div>'
        f'<div class="v">{e(painel.porcentagem(linha.taxa_atraso))}</div></div></div>'
        f'<div class="titulo-lista">Para onde os voos daqui mais atrasam</div>{lista}</div>'
    )


with interface.pagina_protegida():
    resumo = interface.dados("resumo_ultimo_mes")
    mes = painel.nome_mes(resumo["mes"])
    info = interface.manifest()
    primeiro = painel.nome_mes(datetime.fromisoformat(info["primeiro_mes"]).date())
    interface.cabecalho(
        "Aviação nacional · dados públicos da ANAC",
        "Pontualidade dos voos no Brasil",
        "Quanto os voos nacionais atrasam, onde e quando, a chance de atraso de um voo futuro e "
        "o desempenho mês a mês do modelo que faz essa previsão.",
        icone="partidas",
        meta=[
            ("Último mês publicado", mes),
            ("Período no app", f"{primeiro} a {mes}"),
            ("Processado em", f"{datetime.fromisoformat(info['gerado_em']):%d/%m/%Y}"),
        ],
    )

    geral = interface.dados("serie_mensal")
    anterior = geral.iloc[-2] if len(geral) > 1 else None
    rotulo_anterior = (
        f"vs. {painel.nome_mes(anterior['mes'].date())}" if anterior is not None else ""
    )
    numeros = [
        interface.Numero(
            "Voos nacionais realizados",
            painel.numero(resumo["voos_nacionais_realizados"]),
            rotulo_anterior,
            variacao=variacao_relativa(geral["voos"]),
            tendencia=list(geral["voos"]),
        ),
        interface.Numero(
            "Atraso acima de 15 min",
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
                "Companhia mais pontual",
                nome_cia,
                f"{painel.porcentagem(taxa_cia)} de atraso",
                f"Entre as companhias com pelo menos {painel.MIN_VOOS_DESTAQUE} voos no mês.",
                tendencia=list(serie_cia["taxa_atraso"]),
            )
        )
    if resumo["aeroporto_mais_atraso"]:
        codigo, taxa_aeroporto, cidade, icao_pior = resumo["aeroporto_mais_atraso"]
        serie_aeroporto = interface.dados("serie_mensal", None, icao_pior)
        numeros.append(
            interface.Numero(
                "Aeroporto com mais atraso",
                codigo,
                f"{painel.porcentagem(taxa_aeroporto)} de atraso · {cidade}",
                f"Entre os aeroportos com pelo menos {painel.MIN_VOOS_DESTAQUE} partidas no mês.",
                tendencia=list(serie_aeroporto["taxa_atraso"]),
            )
        )
    interface.numeros(numeros)
    interface.nota("As linhas mostram os últimos 12 meses.")

    if anterior is not None and resumo["cia_mais_pontual"] and resumo["aeroporto_mais_atraso"]:
        diferenca = (resumo["taxa_atraso"] - anterior["taxa_atraso"]) * 100
        comparacao = (
            "praticamente igual ao mês anterior"
            if abs(diferenca) < 0.05
            else f"{painel.decimal(abs(diferenca), 1)} p.p. "
            f"{'acima' if diferenca > 0 else 'abaixo'} de {painel.nome_mes(anterior['mes'].date())}"
        )
        e = interface._e
        interface.resumo(
            f"Em {e(mes)}, <b>{e(painel.porcentagem(resumo['taxa_atraso']))}</b> dos "
            f"{e(painel.numero(resumo['voos_nacionais_realizados']))} voos nacionais partiram com "
            f"mais de 15 minutos de atraso, {e(comparacao)}. {e(cidade)} ({e(codigo)}) teve a "
            "maior taxa entre os grandes aeroportos, "
            f"<b>{e(painel.porcentagem(taxa_aeroporto))}</b>; a {e(nome_cia)} foi a companhia "
            f"mais pontual, com <b>{e(painel.porcentagem(taxa_cia))}</b>."
        )

    # O tamanho do problema: as horas de atraso somadas no mês.
    impacto = interface.dados("impacto_do_mes", resumo["mes"])
    if impacto["voos_atrasados"]:
        e = interface._e
        horas = impacto["horas"]
        mediana = (
            f" Metade deles atrasou mais de {painel.numero(impacto['mediana_min'])} minutos."
            if impacto["mediana_min"] is not None
            else ""
        )
        interface.html_bruto(
            f'<div class="fdr-impacto"><div class="numero">{e(painel.numero(horas))}'
            f'<span>horas de atraso</span></div><div class="texto">Foi o que somaram, na '
            f"partida, os <b>{e(painel.numero(impacto['voos_atrasados']))} voos nacionais</b> que "
            f"saíram com mais de 15 minutos de atraso em {e(mes)}: o equivalente a "
            f"<b>{e(painel.numero(horas / 24))} dias</b> de espera.{e(mediana)}</div></div>"
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
        "Painel de partidas",
        f"As {len(tipicos)} rotas mais movimentadas de {mes}, cada uma com o voo mais comum "
        "(companhia, número e horário). A chance de atraso é a que o modelo prevê para o dia.",
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
        f"{painel.MESES_PT[dia.month - 1]} {dia.year}",
        legenda=[
            ("bom", "No horário: abaixo de 15%, a média dos voos"),
            ("atencao", "Atenção: de 15% a 25%"),
            ("critico", "Risco de atraso: 25% ou mais"),
        ],
    )

    interface.secao(
        "Onde os voos mais atrasam",
        f"Partidas nacionais em {mes}. Clique num aeroporto para ver para onde os voos dele mais "
        "atrasam.",
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
                    "{voos_texto} partidas · {taxa_texto} com atraso",
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
        interface.html_bruto(interface.legenda_do_mapa(minimo, maximo, "mais partidas"))
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
            dica = " Clique num aeroporto para ver outro."
            if not escolhidos and linha.icao == pior:
                dica = " Mostrando o aeroporto com mais atraso; clique em outro."
            interface.nota("Rotas com pelo menos 60 voos no mês." + ("" if escolhidos else dica))

    interface.secao("Para onde ir")
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
            st.page_link(pagina, label=titulo, icon=":material/arrow_forward:")
            interface.nota(texto)
