"""Previsão, em três modos:
- um voo: a chance de atrasar, os fatores que mais pesaram (SHAP por tema), as outras companhias,
  o "e se" de outros horários e onde o voo fica entre todos;
- melhor horário: a chance em cada dia e hora de uma semana, para a mesma rota e companhia;
- comparar: dois voos lado a lado, com a diferença tema a tema.

As escolhas ficam na URL, com os códigos dos aeroportos e das companhias (ex.:
?origem=GRU&destino=POA&cia=AD&data=2026-10-23&hora=21), então o link abre a mesma previsão.

As variáveis saem da mesma consulta do treino (fdr.previsao), com o histórico até 2 meses antes
do voo.
"""

from datetime import date, timedelta
from urllib.parse import urlencode

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
MODOS = {"voo": "Um voo", "melhor": "Melhor horário da semana", "comparar": "Comparar dois voos"}
# Os nomes dos campos são também os nomes dos parâmetros na URL (o voo B usa o prefixo "b_").
CAMPOS = ("origem", "destino", "cia", "data", "hora")
DIFERENCAS_MOSTRADAS = 6
# Exemplos prontos: (título, origem, destino preferido, dia da semana, hora). Se a rota não
# existir nos dados, o destino vira o mais voado a partir da origem.
EXEMPLOS = [
    ("Sexta, 21h, saindo de Guarulhos", "SBGR", "SBPA", 5, 21),
    ("Ponte aérea, segunda às 18h", "SBSP", "SBRJ", 1, 18),
    ("Terça cedo, saindo de Brasília", "SBBR", "SBGR", 2, 6),
    ("Domingo à tarde em Recife", "SBRF", "SBGR", 7, 15),
]


def cartao_do_voo(
    resultado: dict, aeroportos: pd.DataFrame, nome_cia: str, titulo: str = "Cartão de embarque"
) -> str:
    """O voo escolhido como um cartão de embarque: o trecho à esquerda e, no canhoto, a chance
    de atraso com a régua de 0% a 50% e a marca da média dos voos. Na comparação, o título
    diz qual é o voo, e o cartão fica numa coluna só."""
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
        f'<div class="fdr-cartao{"" if titulo == "Cartão de embarque" else " compacto"}">'
        f'<div class="fdr-cartao-topo">'
        f"<div>{interface.pictograma('aviao')}{e(titulo)} <span>· Boarding pass</span>"
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


DIMINUI = "&#9664; Diminui<i> o risco</i>"
AUMENTA = "Aumenta<i> o risco</i> &#9654;"


def fatores(
    itens: list[dict],
    esquerda: str = DIMINUI,
    direita: str = AUMENTA,
    vazio: str = "Nenhum fator se destacou: a previsão fica perto da média.",
) -> str:
    """Barras divergentes, do fator que mais pesou para o que menos pesou: o que aumenta o risco
    fica à direita (âmbar) e o que diminui, à esquerda (azul). `esquerda` e `direita` são os
    títulos (HTML fixo do código, não texto do usuário)."""
    itens = sorted(itens, key=lambda f: -abs(f["pontos"]))
    if not itens:
        return f'<p class="fdr-nota">{interface._e(vazio)}</p>'
    maximo = max(abs(f["pontos"]) for f in itens)
    linhas = [
        f'<div class="fdr-fatores-cabecalho"><div>Tema</div><div><span>{esquerda}</span>'
        f'<span>{direita}</span></div><div class="numero">Efeito</div></div>'
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


@st.cache_data(show_spinner="Calculando a semana...", max_entries=64)
def chances_da_semana(origem: str, destino: str, cia: str, primeiro_dia: date) -> pd.DataFrame:
    """A chance do mesmo voo em cada hora de 7 dias seguidos (os que cabem no período da
    previsão), e se a rota teve voos naquele horário nos 12 meses de histórico."""
    previsor = interface.previsor()
    ultimo = previsor.periodo()[1]
    dias = [primeiro_dia + timedelta(days=d) for d in range(7)]
    voos = [Voo(cia, origem, destino, d, h) for d in dias if d <= ultimo for h in range(24)]
    resultados = previsor.prever(voos)
    return pd.DataFrame(
        {
            "dia": [r["voo"].data for r in resultados],
            "hora": [r["voo"].hora for r in resultados],
            "chance": [r["probabilidade"] for r in resultados],
            "com_voos": [r["voos_rota_hora_12m"] > 0 for r in resultados],
        }
    )


def rotulo_do_dia(dia: date) -> str:
    return f"{painel.DIAS_SEMANA[dia.weekday()]} {dia:%d/%m}"


def grade_da_semana(semana: pd.DataFrame, destaques: pd.DataFrame) -> alt.LayerChart:
    """Dia x hora, com a cor pela chance de atraso. Horários sem voos da rota no histórico ficam
    em cinza; o melhor e o pior horário levam a borda e o valor."""
    ordem = [rotulo_do_dia(d) for d in sorted(semana["dia"].unique())]
    base = alt.Chart(semana).encode(
        x=alt.X(
            "hora:O",
            title="Hora prevista da partida",
            axis=alt.Axis(labelAngle=0, labelExpr="datum.value + 'h'", labelOverlap="parity"),
        ),
        y=alt.Y("rotulo:N", sort=ordem, title=None),
        tooltip=[
            alt.Tooltip("rotulo:N", title="Dia"),
            alt.Tooltip("hora_texto:N", title="Partida"),
            alt.Tooltip("chance_texto:N", title="Chance de atraso"),
        ],
    )
    com_voos = (
        base.transform_filter("datum.com_voos")
        .mark_rect(stroke=interface.SUPERFICIE, strokeWidth=2, cornerRadius=2)
        .encode(
            color=alt.Color(
                "chance:Q",
                title="Chance de atraso",
                scale=alt.Scale(range=interface.RAMPA),
                legend=alt.Legend(format="%", gradientLength=220, orient="bottom"),
            )
        )
    )
    sem_voos = base.transform_filter("!datum.com_voos").mark_rect(
        color=interface.GRADE, stroke=interface.SUPERFICIE, strokeWidth=2, cornerRadius=2
    )
    marcas = alt.Chart(destaques).encode(x=alt.X("hora:O"), y=alt.Y("rotulo:N", sort=ordem))
    bordas = marcas.mark_rect(filled=False, strokeWidth=3, cornerRadius=2).encode(
        stroke=alt.Color(
            "tipo:N",
            scale=alt.Scale(domain=["melhor", "pior"], range=[interface.DESTAQUE, interface.PRETO]),
            legend=None,
        )
    )
    valores = marcas.mark_text(fontWeight=700, fontSize=11, font=interface.FONTE_TITULO).encode(
        text="chance_texto:N",
        color=alt.Color(
            "tipo:N",
            scale=alt.Scale(domain=["melhor", "pior"], range=[interface.PRETO, "#ffffff"]),
            legend=None,
        ),
    )
    return sem_voos + com_voos + bordas + valores


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
    e = interface._e

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
    for titulo, origem_ex, destino_ex, semana_ex, hora_ex in EXEMPLOS:
        destinos_ex = list(rotas.loc[rotas["origem"] == origem_ex, "destino"])
        destino_ex = destino_ex if destino_ex in destinos_ex else (destinos_ex or [None])[0]
        if destino_ex is None:
            continue
        dia_ex = proximo(semana_ex)
        cias_ex = previsor.companhias_na_rota(origem_ex, destino_ex, dia_ex)
        if cias_ex:
            exemplos[titulo] = (origem_ex, destino_ex, cias_ex[0], dia_ex, hora_ex)

    def aplicar_exemplo() -> None:
        escolhido = st.session_state.get("exemplo")
        if escolhido in exemplos:
            st.session_state.update(zip(CAMPOS, exemplos[escolhido], strict=True))
        st.session_state["exemplo"] = None  # o exemplo funciona como um botão

    iata_para_icao = {i: icao for icao, i in cadastro["iata"].items()}
    iata_da_cia = painel.CODIGOS_IATA
    cia_do_iata = {i: c for c, i in iata_da_cia.items()}

    def ler_link() -> None:
        """Na primeira vez que a página abre na sessão, as escolhas vêm da URL. Valores inválidos
        são ignorados: o formulário corrige o que não existir."""
        if st.session_state.get("_link_lido"):
            return
        st.session_state["_link_lido"] = True
        parametros = st.query_params
        if parametros.get("modo") in MODOS:
            st.session_state["modo"] = parametros["modo"]
        for prefixo in ("", "b_"):
            for nome in ("origem", "destino"):
                valor = parametros.get(prefixo + nome, "").upper()
                if valor:
                    st.session_state[prefixo + nome] = iata_para_icao.get(valor, valor)
            cia = parametros.get(prefixo + "cia", "").upper()
            if cia:
                st.session_state[prefixo + "cia"] = cia_do_iata.get(cia, cia)
            try:
                st.session_state[prefixo + "data"] = date.fromisoformat(
                    parametros.get(prefixo + "data", "")
                )
            except ValueError:
                pass
            hora = parametros.get(prefixo + "hora", "")
            if hora.isdigit() and 0 <= int(hora) <= 23:
                st.session_state[prefixo + "hora"] = int(hora)

    def parametros_do_voo(voo: Voo, prefixo: str = "", com_hora: bool = True) -> dict:
        parametros = {
            prefixo + "origem": cadastro.at[voo.origem, "iata"],
            prefixo + "destino": cadastro.at[voo.destino, "iata"],
            prefixo + "cia": iata_da_cia.get(voo.cia, voo.cia),
            prefixo + "data": voo.data.isoformat(),
        }
        if com_hora:
            parametros[prefixo + "hora"] = str(voo.hora)
        return parametros

    def escolher_voo(prefixo: str = "", com_hora: bool = True, empilhado: bool = False) -> Voo:
        """O formulário de um voo. Cada campo fica na URL com o nome do campo (com o prefixo do
        voo B) e guarda o valor quando o modo muda."""

        def campo(nome: str) -> dict:
            # persist_state: o valor fica guardado quando o modo muda e o campo some da tela.
            return {"key": prefixo + nome, "persist_state": "page"}

        def valido(nome: str, opcoes: list) -> None:
            if st.session_state.get(prefixo + nome) not in opcoes:
                st.session_state.pop(prefixo + nome, None)

        if empilhado:
            col_origem = col_destino = col_cia = col_data = col_hora = st.container()
        else:
            linha1 = st.columns(2, gap="medium")
            linha2 = st.columns(3 if com_hora else 2, gap="medium")
            col_origem, col_destino = linha1
            col_cia, col_data = linha2[0], linha2[1]
            col_hora = linha2[2] if com_hora else None
        valido("origem", origens)
        origem = col_origem.selectbox("Origem", origens, format_func=rotulo, **campo("origem"))
        destinos = list(rotas.loc[rotas["origem"] == origem, "destino"])
        valido("destino", destinos)
        destino = col_destino.selectbox("Destino", destinos, format_func=rotulo, **campo("destino"))
        # Os valores iniciais vão pela Session State (e não por value/index), como o resto do
        # formulário: assim o Streamlit não avisa que o campo tem dois valores iniciais.
        if not inicio <= st.session_state.get(prefixo + "data", hoje) <= fim:
            st.session_state[prefixo + "data"] = hoje
        st.session_state.setdefault(prefixo + "data", hoje)
        dia = col_data.date_input(
            "Data do voo" if com_hora else "Semana a partir de",
            min_value=inicio,
            max_value=fim,
            format="DD/MM/YYYY",
            **campo("data"),
        )
        cias = previsor.companhias_na_rota(origem, destino, dia)
        if not cias:
            st.info("Nenhuma companhia voou essa rota nos 12 meses de histórico. Escolha outra.")
            st.stop()
        valido("cia", cias)
        cia = col_cia.selectbox(
            "Companhia", cias, format_func=lambda c: nomes_cias.get(c, c), **campo("cia")
        )
        hora = 0
        if com_hora:
            st.session_state.setdefault(prefixo + "hora", 10)
            hora = col_hora.selectbox(
                "Hora prevista da partida",
                range(24),
                format_func=lambda h: f"{h:02d}:00",
                **campo("hora"),
            )
        return Voo(cia, origem, destino, dia, hora)

    def mostrar_um_voo() -> dict:
        with interface.quadro("voo"):
            if exemplos:
                st.pills(
                    "Comece por um exemplo",
                    list(exemplos),
                    key="exemplo",
                    on_change=aplicar_exemplo,
                )
            voo = escolher_voo()
        cias = previsor.companhias_na_rota(voo.origem, voo.destino, voo.data)
        outras = [Voo(c, voo.origem, voo.destino, voo.data, voo.hora) for c in cias]
        horarios = [Voo(voo.cia, voo.origem, voo.destino, voo.data, h) for h in range(24)]
        resultados = previsor.prever([voo, *outras, *horarios])
        principal = resultados[0]
        por_cia = resultados[1 : 1 + len(outras)]
        por_hora = resultados[1 + len(outras) :]

        interface.html_bruto(cartao_do_voo(principal, cadastro, nomes_cias.get(voo.cia, voo.cia)))
        if principal["historico_defasado"]:
            interface.nota(
                "A ANAC ainda não publicou os dados de 2 meses antes deste voo. O modelo usa o "
                f"último mês publicado ({painel.nome_mes(previsor.ultimo_mes_publicado)}), um "
                "histórico mais velho do que no treino: a previsão fica menos confiável."
            )

        # O resumo em uma frase: a chance contra a média e o fator que mais pesou.
        chance, media = principal["probabilidade"], principal["media_do_modelo"]
        lado = "acima" if chance > media else "abaixo"
        texto = (
            f"A chance prevista é de <b>{e(painel.porcentagem(chance))}</b>, {lado} da média dos "
            f"voos ({e(painel.porcentagem(media))})."
        )
        temas = sorted(
            principal["aumentam"] + principal["diminuem"], key=lambda f: -abs(f["pontos"])
        )
        if temas:
            verbo = "aumentou" if temas[0]["pontos"] > 0 else "reduziu"
            texto += (
                f" O que mais pesou foi <b>{e(temas[0]['tema'].lower())}</b>, que {verbo} a "
                f"chance em {e(painel.decimal(abs(temas[0]['pontos']), 1))} p.p."
            )
        interface.resumo(texto)

        with interface.quadro("fatores"):
            interface.secao(
                "O que mais pesou nesta previsão",
                "Quanto a chance mudaria, em pontos percentuais, sem cada tema. Calculado com o "
                "SHAP do próprio modelo, somado por tema.",
            )
            interface.html_bruto(fatores(principal["aumentam"] + principal["diminuem"]))

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
                destacar=painel.CODIGOS_IATA.get(voo.cia, voo.cia),
            )
            interface.nota(
                "O mesmo voo com cada companhia: a diferença vem do histórico de cada uma na "
                "rota, no aeroporto e na programação do dia."
            )
        with e_se, interface.quadro("horarios", altura="stretch"):
            interface.secao(
                "E se fosse em outro horário?",
                "Mesma companhia, rota e data. Em cinza-claro, horários sem voos dessa rota no "
                "histórico.",
            )
            interface.grafico(grafico_por_hora(por_hora, voo.hora), altura=200)

        metricas = interface.json_do_projeto("models/metrics.json")["modelo_final"]["teste"]
        faixas, abaixo = posicao_entre_os_voos(chance, metricas["curva_calibracao"])
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
                        alt.datum.este_voo,
                        alt.value(interface.DESTAQUE),
                        alt.value(interface.APAGADO),
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
        return parametros_do_voo(voo)

    def mostrar_melhor_horario() -> dict:
        with interface.quadro("semana_filtros"):
            voo = escolher_voo(com_hora=False)
        semana = chances_da_semana(voo.origem, voo.destino, voo.cia, voo.data).copy()
        semana["rotulo"] = [rotulo_do_dia(d) for d in semana["dia"]]
        semana["hora_texto"] = [f"{h:02d}:00" for h in semana["hora"]]
        semana["chance_texto"] = [painel.porcentagem(c) for c in semana["chance"]]
        parametros = parametros_do_voo(voo, com_hora=False)
        candidatos = semana[semana["com_voos"]]
        nome_cia = nomes_cias.get(voo.cia, voo.cia)
        trecho = f"{cadastro.at[voo.origem, 'iata']} para {cadastro.at[voo.destino, 'iata']}"
        if candidatos.empty:
            interface.aviso(
                f"A rota {trecho} não teve voos em nenhum horário nos 12 meses de histórico: não "
                "dá para comparar horários."
            )
            return parametros
        melhor = candidatos.loc[candidatos["chance"].idxmin()]
        pior = candidatos.loc[candidatos["chance"].idxmax()]

        def quando(linha) -> str:
            return f"{rotulo_do_dia(linha['dia'])} às {linha['hora_texto']}"

        interface.resumo(
            f"Com a {e(nome_cia)}, de {e(trecho)}, na semana que começa em "
            f"{e(f'{voo.data:%d/%m}')}: o horário com menor chance de atraso é "
            f"<b>{e(quando(melhor))} ({e(melhor['chance_texto'])})</b>; o com maior chance, "
            f"<b>{e(quando(pior))} ({e(pior['chance_texto'])})</b>."
        )
        destaques = pd.DataFrame([melhor, pior]).assign(tipo=["melhor", "pior"])
        with interface.quadro("semana"):
            interface.secao(
                "A semana hora a hora",
                "A chance de atraso prevista para cada dia e hora de partida. Em cinza, horários "
                "em que a rota não teve voos nos 12 meses de histórico (ficam fora da escolha do "
                "melhor e do pior). Borda azul: o melhor horário; preta: o pior.",
            )
            interface.grafico(grade_da_semana(semana, destaques), altura=330)

        def detalhar() -> None:
            st.session_state.update(data=melhor["dia"], hora=int(melhor["hora"]), modo="voo")

        st.button(
            f"Ver o melhor horário em detalhe ({quando(melhor)})",
            icon=":material/arrow_forward:",
            on_click=detalhar,
            key="detalhar_melhor",
        )
        return parametros

    def mostrar_comparacao() -> dict:
        # O voo B começa igual ao A, em outro horário, até a pessoa mudar.
        for nome in CAMPOS[:-1]:
            if "b_" + nome not in st.session_state and nome in st.session_state:
                st.session_state["b_" + nome] = st.session_state[nome]
        if "b_hora" not in st.session_state:
            st.session_state["b_hora"] = 18 if st.session_state.get("hora", 10) != 18 else 7
        coluna_a, coluna_b = st.columns(2, gap="medium")
        with coluna_a, interface.quadro("voo_a"):
            interface.secao("Voo A")
            voo_a = escolher_voo(empilhado=True)
        with coluna_b, interface.quadro("voo_b"):
            interface.secao("Voo B")
            voo_b = escolher_voo("b_", empilhado=True)
        resultado_a, resultado_b = previsor.prever([voo_a, voo_b])
        cartoes = st.columns(2, gap="medium")
        for coluna, resultado, titulo in (
            (cartoes[0], resultado_a, "Voo A"),
            (cartoes[1], resultado_b, "Voo B"),
        ):
            with coluna:
                nome = nomes_cias.get(resultado["voo"].cia, resultado["voo"].cia)
                interface.html_bruto(cartao_do_voo(resultado, cadastro, nome, titulo))

        diferenca = (resultado_b["probabilidade"] - resultado_a["probabilidade"]) * 100
        if abs(diferenca) < 0.05:
            frase = "Os dois voos têm praticamente a mesma chance de atraso."
        else:
            maior, menor = ("B", "A") if diferenca > 0 else ("A", "B")
            frase = (
                f"O voo <b>{maior}</b> tem <b>{e(painel.decimal(abs(diferenca), 1))} p.p.</b> a "
                f"mais de chance de atraso que o voo {menor}."
            )
        interface.resumo(frase)

        temas = sorted(set(resultado_a["temas"]) | set(resultado_b["temas"]))
        itens = [
            {"tema": t, "pontos": resultado_b["temas"].get(t, 0) - resultado_a["temas"].get(t, 0)}
            for t in temas
        ]
        itens = sorted(
            (i for i in itens if abs(i["pontos"]) >= 0.05), key=lambda i: -abs(i["pontos"])
        )[:DIFERENCAS_MOSTRADAS]
        with interface.quadro("diferenca"):
            interface.secao(
                "De onde vem a diferença",
                "Para cada tema, quanto ele pesa a mais (ou a menos) no voo B do que no voo A, em "
                "pontos percentuais (SHAP por tema).",
            )
            interface.html_bruto(
                fatores(
                    itens,
                    esquerda="&#9664; Menos risco<i> no voo B</i>",
                    direita="Mais risco<i> no voo B</i> &#9654;",
                    vazio="Os temas pesam igual nos dois voos.",
                )
            )
        return parametros_do_voo(voo_a) | parametros_do_voo(voo_b, "b_")

    ler_link()
    st.session_state.setdefault("modo", "voo")
    modo = st.segmented_control(
        "O que você quer ver", list(MODOS), format_func=MODOS.get, required=True, key="modo"
    )

    if modo == "melhor":
        parametros = mostrar_melhor_horario()
    elif modo == "comparar":
        parametros = mostrar_comparacao()
    else:
        parametros = mostrar_um_voo()
    parametros = {"modo": modo} | parametros
    st.query_params.from_dict(parametros)

    url = st.context.url
    if url:
        link = url.split("?")[0] + "?" + urlencode(parametros)
        with interface.quadro("link"):
            interface.secao(
                "Compartilhe esta previsão",
                "O link abre o app com as mesmas escolhas.",
            )
            interface.copiar_link(link)

    interface.nota(
        "É uma probabilidade, não uma garantia: cerca de 15% dos voos atrasam. O modelo não vê "
        "clima nem a rotação do avião. Confirme o horário com a companhia no dia do voo."
    )
