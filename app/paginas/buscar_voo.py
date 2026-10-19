"""Buscar voo: o histórico real de um número de voo (ex.: G3 1400) nos últimos 12 meses, com a
pontualidade, a distribuição dos atrasos, os piores dias e a chance prevista para o próximo voo.

O número vai na URL (?voo=G3-1400), então o link abre a mesma busca.
"""

import re
from datetime import date, timedelta

import altair as alt
import pandas as pd
import streamlit as st

from fdr import interface, painel
from fdr.previsao import Voo

MESES_HISTORICO = 12
PIORES_DIAS = 5
MIN_VEZES_DIA_DA_SEMANA = 4  # dias da semana em que o voo partiu pelo menos 4 vezes em 3 meses
FAIXAS_ATRASO = [  # (rótulo, limite superior em minutos) da distribuição dos atrasos
    ("No horário ou antes", 0),
    ("1 a 15 min", 15),
    ("16 a 30 min", 30),
    ("31 a 60 min", 60),
    ("1 a 2 h", 120),
    ("Mais de 2 h", float("inf")),
]
# Rótulos curtos do eixo, para caber no celular; o tooltip mostra o rótulo completo.
EIXO_DA_FAIXA = dict(
    zip(
        [r for r, _ in FAIXAS_ATRASO],
        ["≤ 0", "1–15", "16–30", "31–60", "61–120", "> 120"],
        strict=True,
    )
)
SITUACAO_DA_FAIXA = {"baixa": ("Risco baixo", "bom"), "média": ("Risco médio", "atencao")}
SITUACAO_DA_FAIXA["alta"] = ("Risco alto", "critico")


def ler_numero(texto: str) -> tuple[str, str] | None:
    """ "G3 1400", "g3-1400", "GLO1400" ou "AD 4330" -> (código ICAO da companhia, número)."""
    achado = re.fullmatch(r"\s*([A-Za-z0-9]{2,3}?)[\s\-]*0*(\d{1,5})\s*", texto or "")
    if not achado:
        return None
    codigo, numero = achado.group(1).upper(), achado.group(2)
    icao = {iata: icao for icao, iata in painel.CODIGOS_IATA.items()}.get(codigo, codigo)
    return icao, numero


def numero_de_voo(cia: str, numero: str) -> str:
    return f"{painel.CODIGOS_IATA.get(cia, cia)} {numero}"


def duracao(minutos: float) -> str:
    """125 -> "2h05"; 40 -> "40 min"."""
    minutos = int(round(minutos))
    return f"{minutos // 60}h{minutos % 60:02d}" if minutos >= 60 else f"{minutos} min"


def faixa_do_atraso(minutos: float) -> str:
    return next(rotulo for rotulo, limite in FAIXAS_ATRASO if minutos <= limite)


def grafico_distribuicao(realizados: pd.DataFrame) -> alt.LayerChart:
    """Quantas partidas caíram em cada faixa de atraso. As faixas acima de 15 min (atraso, pelo
    critério da ANAC) ficam em âmbar."""
    contagem = (
        realizados["atraso_partida_min"]
        .map(faixa_do_atraso)
        .value_counts()
        .reindex([r for r, _ in FAIXAS_ATRASO], fill_value=0)
        .rename_axis("faixa")
        .reset_index(name="voos")
    )
    contagem["parcela"] = contagem["voos"] / contagem["voos"].sum()
    contagem["texto"] = [painel.porcentagem(p) for p in contagem["parcela"]]
    contagem["atrasou"] = [i >= 2 for i in range(len(contagem))]
    contagem["eixo"] = contagem["faixa"].map(EIXO_DA_FAIXA)
    base = alt.Chart(contagem).encode(
        x=alt.X(
            "eixo:N",
            sort=list(EIXO_DA_FAIXA.values()),
            title="Minutos de atraso na partida",
            axis=alt.Axis(labelAngle=0, titleFontWeight="normal", titleColor=interface.TEXTO),
        ),
        y=alt.Y("parcela:Q", title=None, axis=alt.Axis(format="%", tickCount=4)),
        tooltip=[
            alt.Tooltip("faixa:N", title="Atraso na partida"),
            alt.Tooltip("voos:Q", title="Partidas", format=",.0f"),
            alt.Tooltip("texto:N", title="Parcela"),
        ],
    )
    barras = base.mark_bar(width={"band": 0.62}).encode(
        color=alt.condition(
            "datum.atrasou", alt.value(interface.COMPARACAO), alt.value(interface.DESTAQUE)
        )
    )
    return barras + base.mark_text(dy=-8, color=interface.TEXTO).encode(text="texto:N")


def grafico_mensal(meses: pd.DataFrame) -> alt.LayerChart:
    """A parcela de partidas no horário em cada mês, com a média dos voos nacionais tracejada."""
    meses = meses.assign(
        mes_rotulo=[painel.mes_curto(m) for m in meses["mes"]],
        texto=[painel.porcentagem(v) for v in meses["no_horario"]],
        media_texto=[painel.porcentagem(v) for v in meses["media"]],
    )
    ordem = list(meses["mes_rotulo"])
    eixo_x = alt.X(
        "mes_rotulo:O", sort=ordem, title=None, axis=alt.Axis(labelAngle=0, labelOverlap="parity")
    )
    escala = alt.Scale(domain=[0, 1])
    base = alt.Chart(meses).encode(
        x=eixo_x,
        tooltip=[
            alt.Tooltip("mes_rotulo:O", title="Mês"),
            alt.Tooltip("texto:N", title="No horário (este voo)"),
            alt.Tooltip("media_texto:N", title="No horário (média nacional)"),
            alt.Tooltip("partidas:Q", title="Partidas", format=",.0f"),
        ],
    )
    barras = base.mark_bar(width={"band": 0.6}, color=interface.DESTAQUE).encode(
        y=alt.Y("no_horario:Q", title=None, scale=escala, axis=alt.Axis(format="%", tickCount=5))
    )
    media = base.mark_line(color=interface.COMPARACAO, strokeDash=[5, 3], strokeWidth=2).encode(
        y=alt.Y("media:Q", scale=escala)
    )
    return barras + media


with interface.pagina_protegida():
    interface.cabecalho(
        "Buscar voo",
        "Como o seu voo costuma se sair?",
        "Digite o número do voo, como aparece no cartão de embarque. Você vê quantas vezes ele "
        "saiu no horário nos últimos 12 meses, o tamanho dos atrasos e a chance prevista para o "
        "próximo voo.",
        icone="busca",
        meta=[
            ("Histórico", f"Últimos {MESES_HISTORICO} meses"),
            ("Base", "Voos nacionais"),
            ("Fonte", "ANAC · VRA"),
        ],
    )
    resumo_mes = interface.dados("resumo_ultimo_mes")
    ultimo_mes = resumo_mes["mes"]
    cadastro = interface.dados("cadastro_aeroportos").set_index("icao")
    nomes_cias = interface.dados("companhias").set_index("cia")["nome"].to_dict()
    tipicos = interface.dados("voos_tipicos", ultimo_mes)
    sugestoes = [numero_de_voo(v.cia, v.numero_voo) for v in tipicos.itertuples() if v.numero_voo]

    # Na primeira vez que a página abre na sessão, o voo vem da URL (?voo=G3-1400).
    if not st.session_state.get("_voo_lido"):
        st.session_state["_voo_lido"] = True
        da_url = st.query_params.get("voo", "").replace("-", " ").strip()
        if da_url:
            st.session_state["voo"] = da_url
    st.session_state.setdefault("voo", sugestoes[0] if sugestoes else "")

    def usar_sugestao() -> None:
        if st.session_state.get("sugestao"):
            st.session_state["voo"] = st.session_state["sugestao"]
        st.session_state["sugestao"] = None

    with interface.quadro("busca"):
        texto = st.text_input(
            "Número do voo", key="voo", placeholder="Ex.: G3 1400, AD 4330 ou LA 3321"
        )
        if sugestoes:
            st.pills(
                f"Os voos mais comuns das rotas mais movimentadas de {painel.nome_mes(ultimo_mes)}",
                sugestoes,
                key="sugestao",
                on_change=usar_sugestao,
            )

    lido = ler_numero(texto)
    if lido is None:
        interface.aviso(
            "Digite o código da companhia e o número do voo, por exemplo G3 1400 (Gol), "
            "AD 4330 (Azul) ou LA 3321 (LATAM)."
        )
        st.stop()
    cia, numero = lido
    st.query_params.from_dict({"voo": f"{painel.CODIGOS_IATA.get(cia, cia)}-{numero}"})

    todos = interface.dados("historico_do_voo", cia, numero)
    inicio_janela = (pd.Timestamp(ultimo_mes) - pd.DateOffset(months=MESES_HISTORICO - 1)).date()
    janela = todos[todos["mes"].dt.date >= inicio_janela]
    rotulo_voo = numero_de_voo(cia, numero)
    if janela.empty:
        interface.aviso(
            f"Nenhuma partida nacional do voo {rotulo_voo} nos últimos {MESES_HISTORICO} meses "
            "de dados da ANAC. Confira o código da companhia e o número."
        )
        st.stop()

    realizados = janela[(janela["situacao"] == "REALIZADO") & janela["atraso_partida_min"].notna()]
    rotas = janela.groupby(["origem", "destino"]).size().sort_values(ascending=False).rename("voos")
    origem, destino = rotas.index[0]
    na_rota = janela[(janela["origem"] == origem) & (janela["destino"] == destino)]
    hora = int(na_rota["hora_prevista"].mode().iloc[0])
    nome_cia = nomes_cias.get(cia, cia)

    def iata(icao: str) -> str:
        return cadastro.at[icao, "iata"] if icao in cadastro.index else icao

    def cidade(icao: str) -> str:
        return cadastro.at[icao, "cidade"] if icao in cadastro.index else icao

    e = interface._e
    numero_em_letras = interface.letras(rotulo_voo, 0, "amarelo")
    interface.html_bruto(
        f'<div class="fdr-placa-voo"><div class="numero">{numero_em_letras}'
        f'</div><div class="trecho">{e(iata(origem))} → {e(iata(destino))}'
        f"<small>{e(cidade(origem))} para {e(cidade(destino))} · {e(nome_cia)}</small></div>"
        f'<div class="hora">{hora:02d}:00<small>Partida mais comum</small></div></div>'
    )

    # Os números do voo e a média dos voos nacionais no mesmo período.
    no_horario = (
        float((~realizados["atrasado_15"].astype(bool)).mean()) if len(realizados) else None
    )
    atrasados = realizados[realizados["atrasado_15"].astype(bool)]
    mediana_atraso = float(atrasados["atraso_partida_min"].median()) if len(atrasados) else None
    cancelados = float((janela["situacao"] == "CANCELADO").mean())
    # O voo pode ter começado a operar no meio da janela: o período e a média nacional usam só
    # os meses em que ele voou.
    primeiro_mes = janela["mes"].min().date()
    meses_do_voo = janela["mes"].dt.to_period("M").nunique()
    periodo = (
        f"nos últimos {MESES_HISTORICO} meses"
        if meses_do_voo >= MESES_HISTORICO
        else f"de {painel.nome_mes(primeiro_mes)} a {painel.nome_mes(ultimo_mes)}"
    )
    geral = interface.dados("serie_mensal", None, None, MESES_HISTORICO)
    no_periodo = geral[pd.to_datetime(geral["mes"]).dt.date >= primeiro_mes]
    taxa_nacional = float(
        (no_periodo["taxa_atraso"] * no_periodo["voos"]).sum() / no_periodo["voos"].sum()
    )
    interface.numeros(
        [
            interface.Numero(
                "Partidas realizadas",
                painel.numero(len(realizados)),
                f"{painel.nome_mes(primeiro_mes)} a {painel.nome_mes(ultimo_mes)}",
            ),
            interface.Numero(
                "Saíram no horário",
                painel.porcentagem(no_horario),
                f"até 15 min · média nacional {painel.porcentagem(1 - taxa_nacional)}",
            ),
            interface.Numero(
                "Atraso típico",
                duracao(mediana_atraso) if mediana_atraso is not None else "—",
                "mediana, quando atrasou mais de 15 min",
            ),
            interface.Numero(
                "Cancelados", painel.porcentagem(cancelados), "das partidas programadas"
            ),
        ]
    )

    if no_horario is not None:
        comparacao = "acima" if no_horario > 1 - taxa_nacional else "abaixo"
        texto_resumo = (
            f"{periodo[0].upper()}{periodo[1:]}, o <b>{e(rotulo_voo)}</b> partiu "
            f"{e(painel.numero(len(realizados)))} vezes, e <b>{e(painel.porcentagem(no_horario))}"
            f"</b> delas no horário, {comparacao} da média dos voos nacionais "
            f"({e(painel.porcentagem(1 - taxa_nacional))})."
        )
        if mediana_atraso is not None:
            texto_resumo += (
                f" Quando atrasou, a mediana foi de <b>{e(duracao(mediana_atraso))}</b>."
            )
        interface.resumo(texto_resumo)

    if len(realizados):
        esquerda, direita = st.columns(2, gap="medium")
        with esquerda, interface.quadro("distribuicao", altura="stretch"):
            interface.secao(
                "Quanto ele atrasa",
                "As partidas pelo atraso em relação ao horário previsto. Em âmbar, as que contam "
                "como atraso (mais de 15 min).",
            )
            interface.grafico(grafico_distribuicao(realizados), altura=240)
        with direita, interface.quadro("mensal", altura="stretch"):
            interface.secao(
                "Mês a mês",
                "A parcela de partidas no horário. A linha tracejada é a média dos voos "
                "nacionais no mesmo mês.",
            )
            por_mes = (
                realizados.groupby("mes")
                .agg(partidas=("atrasado_15", "size"), atrasos=("atrasado_15", "sum"))
                .reset_index()
            )
            por_mes["no_horario"] = 1 - por_mes["atrasos"] / por_mes["partidas"]
            media = geral.set_index("mes")["taxa_atraso"]
            por_mes["media"] = [1 - media.get(m, float("nan")) for m in por_mes["mes"]]
            por_mes["mes"] = [m.date() for m in por_mes["mes"]]
            interface.grafico(grafico_mensal(por_mes), altura=240)

        piores = realizados.nlargest(PIORES_DIAS, "atraso_partida_min")
        piores = piores[piores["atraso_partida_min"] > 15]
        if not piores.empty:
            itens = "".join(
                f"<span>{e(painel.DIAS_SEMANA[d.weekday()])}, {d:%d/%m/%Y} "
                f"<b>{e(duracao(m))}</b></span>"
                for d, m in zip(
                    piores["data_prevista"].dt.date, piores["atraso_partida_min"], strict=True
                )
            )
            interface.html_bruto(
                '<div class="fdr-piores-titulo">Os maiores atrasos do período</div>'
                f'<div class="fdr-piores">{itens}</div>'
            )

    if len(rotas) > 1:
        with interface.quadro("trechos"):
            interface.secao(
                "Trechos deste número de voo",
                "O mesmo número pode fazer mais de um trecho (por exemplo, com escala).",
            )
            interface.ranking(
                [
                    (f"{iata(o)}–{iata(d)}", f"{cidade(o)} para {cidade(d)}", v, painel.numero(v))
                    for (o, d), v in rotas.head(6).items()
                ],
                maximo=float(rotas.max()),
                cor=interface.PRETO,
            )

    # O próximo voo provável: o primeiro dia do período da previsão num dia da semana em que o
    # voo costuma partir (nos últimos 3 meses), na rota e no horário mais comuns.
    previsor = interface.previsor()
    inicio_previsao, fim_previsao = previsor.periodo()
    corte = (pd.Timestamp(ultimo_mes) - pd.DateOffset(months=2)).date()
    recentes = janela[janela["mes"].dt.date >= corte]
    dias_semana = recentes["data_prevista"].dt.weekday.value_counts()
    dias_semana = set(dias_semana[dias_semana >= MIN_VEZES_DIA_DA_SEMANA].index)
    dia = min(max(date.today() + timedelta(days=1), inicio_previsao), fim_previsao)
    while dias_semana and dia.weekday() not in dias_semana and dia < fim_previsao:
        dia += timedelta(days=1)
    regular = bool(dias_semana) and dia.weekday() in dias_semana
    with interface.quadro("proximo"):
        interface.secao("O próximo voo, pelo modelo")
        if regular and cia in previsor.companhias_na_rota(origem, destino, dia):
            resultado = previsor.prever([Voo(cia, origem, destino, dia, hora)])[0]
            texto_faixa, situacao = SITUACAO_DA_FAIXA[resultado["faixa"]]
            interface.html_bruto(
                f'<div class="fdr-proximo"><div><div class="quando">'
                f"{e(painel.DIAS_SEMANA[dia.weekday()])}, {dia:%d/%m/%Y} às {hora:02d}:00</div>"
                f'<div class="texto">O primeiro dia da previsão em que o {e(rotulo_voo)} costuma '
                f"voar, de {e(iata(origem))} para {e(iata(destino))}.</div>"
                f"{interface.selo(texto_faixa, situacao)}</div>"
                f'<div class="chance">{e(painel.porcentagem(resultado["probabilidade"]))}'
                f"<small>Chance de atrasar</small></div></div>"
            )
        elif regular:
            interface.nota(
                f"O modelo não tem previsão para a {nome_cia} de {iata(origem)} para "
                f"{iata(destino)} em {dia:%d/%m/%Y}. Escolha outra data na página de previsão."
            )
        else:
            interface.nota(
                f"O {rotulo_voo} não teve um dia da semana regular nos últimos 3 meses, então não "
                "dá para saber quando é o próximo. Escolha a data na página de previsão."
            )
        with st.container(key="placas_previsao"):
            st.page_link(
                "paginas/previsao.py",
                label="Ver a previsão completa",
                icon=":material/arrow_forward:",
                query_params={
                    "modo": "voo",
                    "origem": iata(origem),
                    "destino": iata(destino),
                    "cia": painel.CODIGOS_IATA.get(cia, cia),
                    "data": dia.isoformat(),
                    "hora": str(hora),
                },
            )

    interface.nota(
        "O histórico é o das partidas nacionais registradas pela ANAC com esse número de voo. "
        "Uma companhia pode reaproveitar um número em outra rota ou horário ao longo do tempo."
    )
