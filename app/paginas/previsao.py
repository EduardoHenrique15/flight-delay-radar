"""Previsão: a chance de um voo futuro atrasar, os fatores que mais pesaram (SHAP por tema), a
comparação com a rota e com as outras companhias e o "e se" de outros horários.

As variáveis saem da mesma consulta do treino (fdr.previsao), com o histórico até 2 meses antes
do voo.
"""

from datetime import date, timedelta

import altair as alt
import pandas as pd
import streamlit as st

from fdr import interface, painel
from fdr.previsao import Voo

FAIXAS = {
    "baixa": ("Risco baixo", "bom"),
    "média": ("Risco médio", "atencao"),
    "alta": ("Risco alto", "critico"),
}
ESCALA_MAXIMA = 0.5  # a régua da probabilidade vai de 0% a 50%
# Exemplos prontos: (título, origem, destino preferido, dia da semana, hora). Se a rota não
# existir nos dados, o destino vira o mais voado a partir da origem.
EXEMPLOS = [
    ("Sexta, 21h, saindo de Guarulhos", "SBGR", "SBPA", 5, 21),
    ("Ponte aérea, segunda às 18h", "SBSP", "SBRJ", 1, 18),
    ("Terça cedo, saindo de Brasília", "SBBR", "SBGR", 2, 6),
    ("Domingo à tarde em Recife", "SBRF", "SBGR", 7, 15),
]


def cartao_do_voo(resultado: dict, aeroportos: pd.DataFrame, nome_cia: str) -> str:
    """O voo escolhido como um cartão de embarque: o trecho à esquerda e, no canhoto, a chance
    de atraso com a régua de 0% a 50% e a marca da média dos voos."""
    voo = resultado["voo"]
    origem, destino = aeroportos.loc[voo.origem], aeroportos.loc[voo.destino]
    texto_faixa, situacao = FAIXAS[resultado["faixa"]]
    chance = resultado["probabilidade"]
    media = resultado["media_do_modelo"]
    preenchido = min(chance / ESCALA_MAXIMA, 1) * 100
    marca = min(media / ESCALA_MAXIMA, 1) * 100
    if resultado["taxa_rota_hora_12m"] is not None:
        comparacao = (
            f"Nos 12 meses de histórico, {painel.porcentagem(resultado['taxa_rota_hora_12m'])} "
            f"dos {painel.numero(resultado['voos_rota_hora_12m'])} voos dessa rota nesse horário "
            "atrasaram."
        )
    else:
        comparacao = "Não houve voos dessa rota nesse horário nos 12 meses de histórico."
    dia = f"{painel.DIAS_SEMANA[voo.data.isoweekday() - 1]}, {voo.data:%d/%m/%Y}"
    codigo = painel.CODIGOS_IATA.get(voo.cia, voo.cia)
    e = interface._e

    def dado(rotulo: str, valor: str) -> str:
        return (
            f'<div><div class="rotulo-pequeno">{e(rotulo)}</div>'
            f'<div class="v">{e(valor)}</div></div>'
        )

    return (
        f'<div class="fdr-cartao"><div class="fdr-cartao-topo">'
        f"<div>{interface.pictograma('aviao')}Cartão de embarque <span>· Boarding pass</span>"
        f"</div><div><b>{e(codigo)}</b>{e(nome_cia)}</div></div>"
        f'<div class="fdr-cartao-corpo"><div class="trecho">'
        f'<div class="cidades rotulo-pequeno"><span>De</span><span>Para</span></div>'
        f'<div class="codigos"><span class="iata">{e(origem.iata)}</span>'
        f'<span class="rota"><hr>{interface.pictograma("aviao")}<hr></span>'
        f'<span class="iata">{e(destino.iata)}</span></div>'
        f'<div class="cidades"><span>{e(origem.cidade)}</span><span>{e(destino.cidade)}</span>'
        f'</div><div class="dados">{dado("Companhia", nome_cia)}{dado("Data", dia)}'
        f"{dado('Partida', f'{voo.hora:02d}:00')}"
        f"{dado('Voos no horário', painel.numero(resultado['voos_rota_hora_12m']))}</div></div>"
        f'<div class="canhoto"><div class="rotulo-pequeno">Chance de atrasar mais de 15 min</div>'
        f'<div class="chance">{e(painel.porcentagem(chance))}</div>'
        f"{interface.selo(texto_faixa, situacao)}"
        f'<div class="fdr-regua"><div class="preenchido" style="width:{preenchido:.1f}%"></div>'
        f'<div class="marca" style="left:{marca:.1f}%"></div></div>'
        f'<div class="fdr-regua-legenda"><span>0%</span>'
        f"<span>média dos voos: {e(painel.porcentagem(media))}</span><span>50%</span></div>"
        f'<div class="comparacao">{e(comparacao)}</div><div class="barras"></div></div>'
        f"</div></div>"
    )


def posicao_entre_os_voos(chance: float, curva: list[dict]) -> tuple[pd.DataFrame, float]:
    """As faixas de risco dos voos do teste (models/metrics.json) e a fração de voos com risco
    menor que `chance` (interpolada dentro da faixa)."""
    faixas = pd.DataFrame(
        {
            "inicio": [c["faixa"][0] for c in curva],
            "fim": [c["faixa"][1] for c in curva],
            "voos": [c["voos"] for c in curva],
        }
    )
    total = faixas["voos"].sum()
    dentro = (chance - faixas["inicio"]) / (faixas["fim"] - faixas["inicio"])
    abaixo = (faixas["voos"] * dentro.clip(0, 1)).sum() / total
    faixas["parcela"] = faixas["voos"] / total
    faixas["rotulo"] = [
        f"{a * 100:.0f}–{b * 100:.0f}%"
        for a, b in zip(faixas["inicio"], faixas["fim"], strict=True)
    ]
    faixas["parcela_texto"] = [painel.porcentagem(v) for v in faixas["parcela"]]
    faixas["este_voo"] = (faixas["inicio"] <= chance) & (chance < faixas["fim"])
    return faixas, float(abaixo)


def fatores(resultado: dict) -> str:
    """Barras divergentes: o que aumenta (à direita, âmbar) e o que diminui (à esquerda, azul) o
    risco, do fator que mais pesou para o que menos pesou."""
    itens = sorted(resultado["aumentam"] + resultado["diminuem"], key=lambda f: -abs(f["pontos"]))
    if not itens:
        return '<p class="fdr-nota">Nenhum fator se destacou: a previsão fica perto da média.</p>'
    maximo = max(abs(f["pontos"]) for f in itens)
    linhas = [
        '<div class="fdr-fatores-cabecalho"><div>Tema</div><div><span>&#9664; Diminui<i> o risco'
        "</i></span><span>Aumenta<i> o risco</i> &#9654;</span></div>"
        '<div class="numero">Efeito</div></div>'
    ]
    for fator in itens:
        largura = 50 * abs(fator["pontos"]) / maximo
        cor = interface.COMPARACAO if fator["pontos"] > 0 else interface.DESTAQUE
        posicao = "left:50%" if fator["pontos"] > 0 else f"left:{50 - largura:.1f}%"
        numero = painel.decimal(fator["pontos"], 1, sinal=True)
        linhas.append(
            f'<div class="fdr-fator"><div>{interface._e(fator["tema"])}</div>'
            f'<div class="barra"><div class="eixo"></div><div class="valor" '
            f'style="{posicao};width:{largura:.1f}%;background:{cor}"></div></div>'
            f'<div class="numero">{numero} p.p.</div></div>'
        )
    return f'<div class="fdr-fatores">{"".join(linhas)}</div>'


def grafico_por_hora(por_hora: list[dict], hora: int) -> alt.LayerChart:
    """A chance do mesmo voo em cada hora do dia. A hora escolhida fica em azul, com o valor; as
    horas sem voos da rota no histórico ficam mais claras."""
    curva = pd.DataFrame(
        {
            "hora": range(24),
            "chance": [r["probabilidade"] for r in por_hora],
            "chance_texto": [painel.porcentagem(r["probabilidade"]) for r in por_hora],
            "hora_texto": [f"{h:02d}:00" for h in range(24)],
            "com_voos": [r["voos_rota_hora_12m"] > 0 for r in por_hora],
        }
    )
    curva["grupo"] = [
        "escolhida" if h == hora else ("com voos" if v else "sem voos")
        for h, v in zip(curva["hora"], curva["com_voos"], strict=True)
    ]
    # Folga em cima para o rótulo da hora escolhida não cobrir as barras vizinhas.
    teto = float(curva["chance"].max()) * 1.3
    base = alt.Chart(curva).encode(
        x=alt.X(
            "hora:O",
            title="Hora prevista da partida",
            axis=alt.Axis(labelAngle=0, labelExpr="datum.value % 3 == 0 ? datum.value + 'h' : ''"),
        ),
        y=alt.Y(
            "chance:Q",
            title=None,
            axis=alt.Axis(format="%", tickCount=4),
            scale=alt.Scale(domain=[0, teto], nice=False),
        ),
        tooltip=[
            alt.Tooltip("hora_texto:N", title="Partida"),
            alt.Tooltip("chance_texto:N", title="Chance"),
        ],
    )
    barras = base.mark_bar(width={"band": 0.74}).encode(
        color=alt.Color(
            "grupo:N",
            scale=alt.Scale(
                domain=["escolhida", "com voos", "sem voos"],
                range=[interface.DESTAQUE, "#a9b0b9", "#dde1e6"],
            ),
            legend=None,
        )
    )
    escolhida = base.transform_filter(alt.datum.hora == hora)
    valor = escolhida.mark_text(
        baseline="top", fontWeight=700, color=interface.DESTAQUE, font=interface.FONTE_TITULO
    ).encode(y=alt.value(0), text=alt.value(f"{hora:02d}h"))
    chance = escolhida.mark_text(
        baseline="top", dy=15, fontWeight=700, color=interface.DESTAQUE, font=interface.FONTE_TITULO
    ).encode(y=alt.value(0), text="chance_texto:N")
    return barras + valor + chance


with interface.pagina_protegida():
    previsor = interface.previsor()
    inicio, fim = previsor.periodo()
    interface.cabecalho(
        "Previsão",
        "Qual a chance de o seu voo atrasar?",
        "Escolha a rota, a companhia, a data e a hora. O modelo estima a chance de a partida "
        "atrasar mais de 15 minutos, usando só o histórico publicado até 2 meses antes do voo.",
        icone="aviao",
        meta=[
            ("Modelo", "LightGBM"),
            ("Voos de", f"{inicio:%d/%m/%Y} a {fim:%d/%m/%Y}"),
            ("Histórico", "Até 2 meses antes"),
        ],
    )
    rotas = previsor.rotas()
    cadastro = interface.dados("cadastro_aeroportos").set_index("icao")
    nomes_cias = interface.dados("companhias").set_index("cia")["nome"].to_dict()

    def rotulo(icao: str) -> str:
        return cadastro.at[icao, "rotulo"] if icao in cadastro.index else icao

    # Das origens e destinos mais voados para os menos (a ordem de rotas()).
    origens = list(
        rotas.groupby("origem", sort=False)["voos"].sum().sort_values(ascending=False).index
    )
    hoje = min(max(date.today(), inicio), fim)

    def proximo(dia_da_semana: int) -> date:
        """O próximo dia da semana (1 = segunda) dentro do período da previsão."""
        dia = hoje + timedelta(days=(dia_da_semana - hoje.isoweekday()) % 7)
        return dia if dia <= fim else hoje

    exemplos = {}
    for titulo, origem_ex, destino_ex, semana, hora_ex in EXEMPLOS:
        destinos_ex = list(rotas.loc[rotas["origem"] == origem_ex, "destino"])
        destino_ex = destino_ex if destino_ex in destinos_ex else (destinos_ex or [None])[0]
        if destino_ex is None:
            continue
        dia_ex = proximo(semana)
        cias_ex = previsor.companhias_na_rota(origem_ex, destino_ex, dia_ex)
        if cias_ex:
            exemplos[titulo] = (origem_ex, destino_ex, cias_ex[0], dia_ex, hora_ex)

    def aplicar_exemplo() -> None:
        escolhido = st.session_state.get("prev_exemplo")
        if escolhido in exemplos:
            origem_ex, destino_ex, cia_ex, dia_ex, hora_ex = exemplos[escolhido]
            st.session_state.update(
                prev_origem=origem_ex,
                prev_destino=destino_ex,
                prev_cia=cia_ex,
                prev_dia=dia_ex,
                prev_hora=hora_ex,
            )
        st.session_state["prev_exemplo"] = None  # o exemplo funciona como um botão

    st.session_state.setdefault("prev_dia", hoje)
    st.session_state.setdefault("prev_hora", 10)
    with interface.quadro("voo"):
        if exemplos:
            st.pills(
                "Comece por um exemplo",
                list(exemplos),
                key="prev_exemplo",
                on_change=aplicar_exemplo,
            )
        linha1 = st.columns([1, 1], gap="medium")
        origem = linha1[0].selectbox("Origem", origens, format_func=rotulo, key="prev_origem")
        destinos = list(rotas.loc[rotas["origem"] == origem, "destino"])
        if st.session_state.get("prev_destino") not in destinos:
            st.session_state.pop("prev_destino", None)
        destino = linha1[1].selectbox("Destino", destinos, format_func=rotulo, key="prev_destino")
        linha2 = st.columns([1, 1, 1], gap="medium")
        if not inicio <= st.session_state["prev_dia"] <= fim:
            st.session_state["prev_dia"] = hoje
        dia = linha2[1].date_input(
            "Data do voo",
            min_value=inicio,
            max_value=fim,
            format="DD/MM/YYYY",
            key="prev_dia",
        )
        cias = previsor.companhias_na_rota(origem, destino, dia)
        if not cias:
            st.info("Nenhuma companhia voou essa rota nos 12 meses de histórico. Escolha outra.")
            st.stop()
        if st.session_state.get("prev_cia") not in cias:
            st.session_state.pop("prev_cia", None)
        cia = linha2[0].selectbox(
            "Companhia", cias, format_func=lambda c: nomes_cias.get(c, c), key="prev_cia"
        )
        hora = linha2[2].selectbox(
            "Hora prevista da partida",
            range(24),
            format_func=lambda h: f"{h:02d}:00",
            key="prev_hora",
        )

    voo = Voo(cia, origem, destino, dia, hora)
    outras = [Voo(c, origem, destino, dia, hora) for c in cias]
    horarios = [Voo(cia, origem, destino, dia, h) for h in range(24)]
    resultados = previsor.prever([voo, *outras, *horarios])
    principal = resultados[0]
    por_cia = resultados[1 : 1 + len(outras)]
    por_hora = resultados[1 + len(outras) :]

    interface.html_bruto(cartao_do_voo(principal, cadastro, nomes_cias.get(cia, cia)))
    if principal["historico_defasado"]:
        interface.nota(
            "A ANAC ainda não publicou os dados de 2 meses antes deste voo. O modelo usa o último "
            f"mês publicado ({painel.nome_mes(previsor.ultimo_mes_publicado)}), um histórico mais "
            "velho do que no treino: a previsão fica menos confiável."
        )

    # O resumo em uma frase: a chance contra a média e o fator que mais pesou.
    e = interface._e
    chance, media = principal["probabilidade"], principal["media_do_modelo"]
    lado = "acima" if chance > media else "abaixo"
    texto = (
        f"A chance prevista é de <b>{e(painel.porcentagem(chance))}</b>, {lado} da média dos "
        f"voos ({e(painel.porcentagem(media))})."
    )
    temas = sorted(principal["aumentam"] + principal["diminuem"], key=lambda f: -abs(f["pontos"]))
    if temas:
        verbo = "aumentou" if temas[0]["pontos"] > 0 else "reduziu"
        texto += (
            f" O que mais pesou foi <b>{e(temas[0]['tema'].lower())}</b>, que {verbo} a chance "
            f"em {e(painel.decimal(abs(temas[0]['pontos']), 1))} p.p."
        )
    interface.resumo(texto)

    with interface.quadro("fatores"):
        interface.secao(
            "O que mais pesou nesta previsão",
            "Quanto a chance mudaria, em pontos percentuais, sem cada tema. Calculado com o SHAP "
            "do próprio modelo, somado por tema.",
        )
        interface.html_bruto(fatores(principal))

    comparacao, e_se = st.columns(2, gap="medium")
    with comparacao, interface.quadro("companhias", altura="stretch"):
        interface.secao("Outras companhias", "Mesma rota, data e horário.")
        ordenados = sorted(por_cia, key=lambda r: r["probabilidade"])
        interface.ranking(
            [
                (
                    painel.CODIGOS_IATA.get(r["voo"].cia, r["voo"].cia),
                    nomes_cias.get(r["voo"].cia, r["voo"].cia),
                    r["probabilidade"],
                    painel.porcentagem(r["probabilidade"]),
                )
                for r in ordenados
            ],
            maximo=max(max(r["probabilidade"] for r in por_cia), media) * 1.1,
            cor=interface.APAGADO,
            referencia=(media, f"Média dos voos: {painel.porcentagem(media)}"),
            chips=True,
            destacar=painel.CODIGOS_IATA.get(cia, cia),
        )
        interface.nota(
            "O mesmo voo com cada companhia: a diferença vem do histórico de cada uma na rota, "
            "no aeroporto e na programação do dia."
        )
    with e_se, interface.quadro("horarios", altura="stretch"):
        interface.secao(
            "E se fosse em outro horário?",
            "Mesma companhia, rota e data. Em cinza-claro, horários sem voos dessa rota no "
            "histórico.",
        )
        interface.grafico(grafico_por_hora(por_hora, hora), altura=200)

    metricas = interface.json_do_projeto("models/metrics.json")["modelo_final"]["teste"]
    faixas, abaixo = posicao_entre_os_voos(principal["probabilidade"], metricas["curva_calibracao"])
    inicio_teste, fim_teste = (pd.Timestamp(m).date() for m in metricas["periodo"])
    with interface.quadro("posicao"):
        interface.secao(
            "Onde este voo fica entre todos",
            f"Mais arriscado que {painel.porcentagem(abaixo, 0)} dos "
            f"{painel.numero(metricas['voos'])} voos do período de teste "
            f"({painel.nome_mes(inicio_teste)} a {painel.nome_mes(fim_teste)}), pela chance "
            "prevista.",
        )
        base_faixas = alt.Chart(faixas).encode(
            x=alt.X(
                "rotulo:O",
                title="Chance prevista de atraso",
                sort=list(faixas["rotulo"]),
                axis=alt.Axis(labelAngle=0),
            ),
            y=alt.Y("parcela:Q", title=None, axis=alt.Axis(format="%", tickCount=4)),
            tooltip=[
                alt.Tooltip("rotulo:N", title="Faixa"),
                alt.Tooltip("parcela_texto:N", title="Parcela dos voos"),
            ],
        )
        interface.grafico(
            base_faixas.mark_bar(width={"band": 0.6}).encode(
                color=alt.condition(
                    alt.datum.este_voo, alt.value(interface.DESTAQUE), alt.value(interface.APAGADO)
                )
            )
            + base_faixas.mark_text(dy=-8, color=interface.TEXTO).encode(text="parcela_texto:N")
            + base_faixas.transform_filter(alt.datum.este_voo)
            .mark_text(
                dy=-24, fontWeight=700, color=interface.DESTAQUE, font=interface.FONTE_TITULO
            )
            .encode(text=alt.value("ESTE VOO")),
            altura=220,
        )

    interface.nota(
        "É uma probabilidade, não uma garantia: cerca de 15% dos voos atrasam. O modelo não vê "
        "clima nem a rotação do avião. Confirme o horário com a companhia no dia do voo."
    )
