"""Monitoramento: o desempenho do modelo mês a mês, o PSI das variáveis mais importantes e a
linha do tempo dos retreinos, lidos de monitoring/history.json (docs/decisoes/006).
"""

from datetime import date

import streamlit as st

from fdr import interface, painel
from fdr.monitoring.drift import nivel

FUNDO_PSI = {"atenção": "#fdf3d7", "alerta": "#fbe9e9"}


def tabela_psi(meses, importantes: list[str]) -> str:
    e = interface._e
    cabecalho = "".join(f"<th>{e(painel.NOMES_VARIAVEIS.get(v, v))}</th>" for v in importantes)
    linhas = []
    for _, mes in meses.iloc[::-1].iterrows():
        celulas = []
        for variavel in importantes:
            valor = mes["psi"].get(variavel)
            if valor is None:
                celulas.append("<td>—</td>")
                continue
            fundo = FUNDO_PSI.get(nivel(valor), "transparent")
            celulas.append(f'<td style="background:{fundo}">{painel.decimal(valor)}</td>')
        linhas.append(
            f"<tr><th>{e(painel.nome_mes(mes['mes'].date()))}</th>{''.join(celulas)}</tr>"
        )
    return (
        f'<div class="fdr-tabela-rolagem"><table class="fdr-tabela"><thead><tr><th>Mês</th>'
        f"{cabecalho}</tr></thead><tbody>{''.join(linhas)}</tbody></table></div>"
    )


def situacao_do_retreino(retreino: dict) -> tuple[str, str, str, str]:
    """(cor do marco, rótulo curto, texto do selo, situação do selo) do mês."""
    if retreino.get("promovido"):
        return interface.DESTAQUE, "promovido", "Desafiante promovido", "bom"
    if retreino.get("disparou") and retreino.get("adiado"):
        return interface.AMARELO, "adiado", "Retreino adiado", "atencao"
    if retreino.get("disparou"):
        return interface.AMARELO, "mantido", "Campeão mantido", "atencao"
    return interface.SUPERFICIE, "sem retreino", "Sem retreino", "neutro"


def linha_do_tempo(meses, treino_inicial: date) -> str:
    """Os meses como paradas de uma rota, a partir do treino do primeiro campeão, e os meses em
    que uma regra disparou, com o que aconteceu."""
    e = interface._e
    paradas = [
        f'<div class="fdr-parada"><div class="marco" style="--cor:{interface.PRETO}"></div>'
        f'<div class="mes">{e(painel.mes_curto(treino_inicial))}</div>'
        f'<div class="tipo">treino do campeão</div></div>'
    ]
    eventos = []
    for _, mes in meses.iterrows():
        retreino = mes["retreino"]
        cor, curto, texto_selo, situacao = situacao_do_retreino(retreino)
        nome = painel.nome_mes(mes["mes"].date())
        paradas.append(
            f'<div class="fdr-parada" title="{e(nome)}"><div class="marco" style="--cor:{cor}">'
            f'</div><div class="mes">{e(painel.mes_curto(mes["mes"].date()))}</div>'
            f'<div class="tipo">{e(curto)}</div></div>'
        )
        if retreino.get("disparou"):
            eventos.append(
                f'<div class="fdr-evento" style="--cor:{cor}"><div class="quando">{e(nome)}'
                f"{interface.selo(texto_selo, situacao)}</div>"
                f'<div class="oque">{e(painel.descrever_retreino(retreino))}</div></div>'
            )
    lista = (
        f'<div class="fdr-eventos">{"".join(eventos)}</div>'
        if eventos
        else '<p class="fdr-nota">Nenhuma regra disparou até agora.</p>'
    )
    return f'<div class="fdr-rota">{"".join(paradas)}</div>{lista}'


with interface.pagina_protegida():
    historico = interface.json_do_projeto("monitoring/history.json")
    meses = painel.meses_monitorados(historico)
    treino_inicial = date.fromisoformat(historico["simulacao"]["campeao_inicial_treino"][1])
    promocoes = [m["retreino"] for m in meses.to_dict("records") if m["retreino"].get("promovido")]
    treino_atual = (
        date.fromisoformat(promocoes[-1]["desafiante_treino"][1]) if promocoes else treino_inicial
    )
    interface.cabecalho(
        "Monitoramento",
        "O modelo continua acertando?",
        "Cada mês publicado pela ANAC é um teste novo. O modelo é comparado com o baseline, a "
        "calibração é conferida e as variáveis são vigiadas. Quando uma regra dispara, um "
        "desafiante é treinado e só substitui o campeão se vencer com folga.",
        icone="grafico",
        meta=[
            ("Meses monitorados", str(len(meses))),
            ("Campeão atual", f"treino até {painel.nome_mes(treino_atual)}"),
            ("Retreinos promovidos", str(len(promocoes))),
        ],
    )
    if meses.empty:
        st.info("Ainda não há meses monitorados.")
        st.stop()

    simulados = meses[meses["tipo"] == "simulacao"]
    if not simulados.empty:
        interface.aviso(
            f"De {painel.nome_mes(simulados['mes'].min().date())} a "
            f"{painel.nome_mes(simulados['mes'].max().date())}, uma simulação do passado: um "
            f"modelo treinado só até {painel.nome_mes(treino_inicial)} foi avaliado mês a mês, "
            "sem olhar o futuro, com as mesmas regras de retreino de produção. Os meses seguintes "
            "entram pelo pipeline mensal."
        )

    ultimo = meses.iloc[-1]
    vitorias = int((meses["pr_auc_modelo"] > meses["pr_auc_baseline"]).sum())
    interface.numeros(
        [
            interface.Numero(
                f"PR-AUC em {painel.nome_mes(ultimo['mes'].date())}",
                painel.decimal(ultimo["pr_auc_modelo"]),
                f"{painel.decimal(ultimo['pr_auc_modelo'] - ultimo['pr_auc_baseline'], sinal=True)}"
                " sobre o baseline",
                interface.AJUDA["pr_auc"],
                tendencia=list(meses["pr_auc_modelo"]),
            ),
            interface.Numero(
                "Meses vencendo o baseline",
                f"{vitorias} de {len(meses)}",
                "pela PR-AUC",
                tendencia=list(meses["pr_auc_modelo"] - meses["pr_auc_baseline"]),
            ),
            interface.Numero(
                "Calibração (ECE)",
                f"{painel.decimal(ultimo['ece'] * 100, 1)} p.p.",
                "limite para retreino: 5 p.p.",
                interface.AJUDA["ece"],
                tendencia=list(meses["ece"]),
            ),
            interface.Numero(
                f"Atraso real em {painel.nome_mes(ultimo['mes'].date())}",
                painel.porcentagem(ultimo["taxa_real"]),
                f"previsto pelo modelo: {painel.porcentagem(ultimo['taxa_prevista'])}",
                tendencia=list(meses["taxa_real"]),
            ),
        ]
    )
    interface.nota(
        "As linhas mostram cada mês monitorado. No segundo indicador, a linha é a diferença de "
        "PR-AUC entre o modelo e o baseline."
    )

    regras = historico["regras"]
    with interface.quadro("retreinos"):
        interface.secao(
            "Linha do tempo dos retreinos",
            "O retreino dispara se o modelo perder do baseline no mês, se o ECE passar de "
            f"{regras['ece_maximo'] * 100:.0f} p.p., se o PSI de uma variável importante passar "
            f"de 0,25 ou a cada {regras['meses_maximos_sem_retreino']} meses. O desafiante só "
            "substitui o campeão se o ganho de PR-AUC tiver intervalo de 95% acima de zero.",
        )
        interface.html_bruto(linha_do_tempo(meses, treino_inicial))

    marcas = [
        (m["mes"].date(), "retreino")
        for m in meses.to_dict("records")
        if m["retreino"].get("promovido")
    ]
    esquerda, direita = st.columns(2, gap="medium")
    with esquerda, interface.quadro("pr_auc", altura="stretch"):
        interface.secao(
            "PR-AUC: modelo contra baseline",
            "Quanto maior, melhor o modelo separa os voos que atrasam.",
        )
        interface.grafico(
            interface.grafico_linhas(
                meses,
                "mes",
                {"pr_auc_modelo": "Modelo", "pr_auc_baseline": "Baseline"},
                "PR-AUC",
                ".2f",
                marcas=marcas,
            ),
            altura=260,
        )
    with direita, interface.quadro("taxas", altura="stretch"):
        interface.secao(
            "Taxa de atraso: prevista e real",
            "Dezembro é o mês mais difícil: a taxa real sobe mais do que o modelo prevê.",
        )
        interface.grafico(
            interface.grafico_linhas(
                meses,
                "mes",
                {"taxa_prevista": "Prevista pelo modelo", "taxa_real": "Real"},
                "Taxa de atraso",
                "%",
                marcas=marcas,
            ),
            altura=260,
        )

    with interface.quadro("psi"):
        interface.secao(
            "Mudança nas variáveis (PSI)",
            "As 5 variáveis que mais pesam no modelo, fora mês do ano, feriados e férias (essas "
            "mudam todo mês por definição). Amarelo: atenção (0,10 ou mais). Vermelho: mudança "
            "forte (0,25 ou mais), que dispara o retreino.",
        )
        interface.html_bruto(tabela_psi(meses, historico["variaveis_importantes"]))
