"""Pergunte aos dados: o assistente texto->SQL (docs/assistente.md e
docs/decisoes/007-texto-para-sql-com-travas.md).

Sem a chave do Gemini, ou sem cota, ele responde com as respostas gravadas de demonstração. Cada
resposta mostra a tabela, um gráfico quando a tabela pede (fdr.assistant.visual), o SQL e as
travas que ele cumpriu. No fim, o placar da avaliação (eval/results/).
"""

import altair as alt
import pandas as pd
import streamlit as st

from fdr import idioma, interface, painel
from fdr.assistant import visual
from fdr.assistant.agent import Resposta
from fdr.assistant.eval import ler_perguntas, placar
from fdr.assistant.guard import TRAVAS
from fdr.idioma import t

# Origem da resposta -> (rótulo, situação do selo)
ORIGENS = {
    "modelo": ("Consulta escrita pelo Gemini", "bom"),
    "cache": ("Consulta já aprovada antes", "bom"),
    "demonstracao": ("Resposta de demonstração", "neutro"),
    "recusa": ("Fora do alcance dos dados", "atencao"),
    "erro": ("Não foi possível responder", "critico"),
    "limite": ("Modo de demonstração", "neutro"),
}


CATEGORIAS = {
    "simples": "Simples",
    "agregacao": "Somas e rankings",
    "juncao": "Junções",
    "tempo": "No tempo",
    "recusa": "Recusas",
}
VEREDITOS = {
    "equivalente": ("Mesmos números, outra forma", "atencao"),
    "erro": ("Erro de verdade", "critico"),
    "sem revisão": ("Sem revisão", "neutro"),
}


def tabela_legivel(tabela: pd.DataFrame) -> pd.DataFrame:
    """A tabela do SQL com datas, taxas e contagens no formato do app (12,5%, ago/2026, 1.234).
    Só para mostrar: o gráfico usa os valores originais."""
    legivel = tabela.copy()
    for coluna in legivel.columns:
        serie = legivel[coluna]
        if pd.api.types.is_datetime64_any_dtype(serie) or (
            serie.dtype == object
            and serie.dropna().map(lambda v: hasattr(v, "year")).all()
            and serie.notna().any()
        ):
            datas = pd.to_datetime(serie).dt.date
            mensal = all(d.day == 1 for d in datas.dropna())
            legivel[coluna] = [
                "" if pd.isna(d) else (painel.nome_mes(d) if mensal else painel.data(d))
                for d in datas
            ]
        elif pd.api.types.is_bool_dtype(serie):
            continue
        elif pd.api.types.is_numeric_dtype(serie) and not visual.eh_rotulo_numerico(coluna):
            valores = serie.dropna()
            if "taxa" in coluna.lower() and valores.between(0, 1).all():
                legivel[coluna] = [painel.porcentagem(v) for v in serie]
            elif (valores % 1 == 0).all():
                legivel[coluna] = ["" if pd.isna(v) else painel.numero(v) for v in serie]
            else:
                legivel[coluna] = ["" if pd.isna(v) else painel.decimal(v, 2) for v in serie]
    return legivel


def grafico_da_resposta(tabela: pd.DataFrame) -> None:
    """O gráfico que a tabela pede (barras para rankings, linha para meses), ou nada."""
    escolha = visual.escolher(tabela)
    if escolha is None:
        return
    dados = tabela.copy()
    eixo = dados[escolha.x]
    if pd.api.types.is_datetime64_any_dtype(eixo) or eixo.map(lambda v: hasattr(v, "year")).all():
        datas = pd.to_datetime(eixo).dt.date
        funcao = painel.mes_curto if escolha.tipo == "linha" else painel.nome_mes
        dados["_rotulo"] = [funcao(d) for d in datas]
    else:
        dados["_rotulo"] = eixo.astype(str)
    if escolha.x_extra:
        dados["_rotulo"] = dados["_rotulo"] + " → " + dados[escolha.x_extra].astype(str)
    formato = ".1%" if escolha.porcentagem else ",.0f"
    if not escolha.porcentagem and not (dados[escolha.y].dropna() % 1 == 0).all():
        formato = ",.2f"
    ordem = list(dados["_rotulo"])
    medida = alt.Y(f"{escolha.y}:Q", title=None, axis=alt.Axis(format=formato, tickCount=4))
    dica = [
        alt.Tooltip("_rotulo:N", title=escolha.x),
        alt.Tooltip(f"{escolha.y}:Q", title=escolha.y, format=formato),
    ]
    if escolha.tipo == "linha":
        base = alt.Chart(dados).encode(
            x=alt.X("_rotulo:O", sort=ordem, title=None, axis=alt.Axis(labelAngle=0)),
            y=medida,
            tooltip=dica,
        )
        grafico = base.mark_line(color=interface.DESTAQUE) + base.mark_point(
            color=interface.DESTAQUE
        )
        altura = 240
    else:
        barras = alt.Chart(dados).encode(
            y=alt.Y("_rotulo:N", sort=ordem, title=None, axis=alt.Axis(labelLimit=260)),
            x=alt.X(f"{escolha.y}:Q", title=None, axis=alt.Axis(format=formato, tickCount=4)),
            tooltip=dica,
        )
        grafico = barras.mark_bar(color=interface.DESTAQUE, size=16) + barras.mark_text(
            align="left", dx=5, color=interface.TEXTO
        ).encode(text=alt.Text(f"{escolha.y}:Q", format=formato))
        altura = 34 * len(dados) + 20
    interface.grafico(grafico, altura=altura)


def travas_cumpridas() -> None:
    itens = "".join(f"<li><b>✓</b>{interface._e(t(trava))}</li>" for trava in TRAVAS)
    interface.html_bruto(
        f'<div class="fdr-travas"><span>{interface._e(t("Travas cumpridas"))}</span>'
        f"<ul>{itens}</ul></div>"
    )


def mostrar_placar() -> None:
    resultado = placar()
    if resultado is None:
        return
    e = interface._e
    interface.secao(
        t("Como o assistente foi avaliado"),
        t(
            "{perguntas} perguntas com resposta conhecida: o resultado do SQL do Gemini é "
            "comparado com o de um SQL de referência escrito à mão. Nas perguntas que os dados "
            "não respondem, o certo é recusar.",
            perguntas=resultado["perguntas"],
        ),
    )

    def de(parte: int, total: int) -> str:
        return t("{parte} de {total}", parte=parte, total=total)

    interface.numeros(
        [
            interface.Numero(
                t("Acerto automático"),
                painel.porcentagem(resultado["acertos"] / resultado["perguntas"]),
                de(resultado["acertos"], resultado["perguntas"]),
                t("A métrica principal: o resultado precisa bater coluna por coluna."),
            ),
            interface.Numero(
                t("Na revisão manual"),
                de(resultado["acertos_revisados"], resultado["perguntas"]),
                t("contando as respostas com os mesmos números"),
            ),
            interface.Numero(
                t("SQL válido"),
                de(resultado["sql_valido"], resultado["respondiveis"]),
                t("nenhuma consulta bloqueada pelas travas"),
            ),
            interface.Numero(
                t("Recusas certas"),
                de(resultado["recusas_certas"], resultado["recusas"]),
                t("preço da passagem, clima, tripulação"),
            ),
        ]
    )
    esquerda, direita = st.columns([2, 3], gap="medium")
    with esquerda, interface.quadro("placar_categorias", altura="stretch"):
        interface.secao(t("Por tipo de pergunta"))
        interface.ranking(
            [
                ("", t(CATEGORIAS.get(nome, nome)), certas / total, de(certas, total))
                for nome, (certas, total) in resultado["por_categoria"].items()
            ],
            maximo=1.0,
            cor=interface.DESTAQUE,
        )
    with direita, interface.quadro("placar_erros", altura="stretch"):
        interface.secao(
            t("As que a avaliação marcou como erradas"),
            t("Revisadas à mão, rodando os dois SQLs nos dados do app."),
        )
        linhas = []
        for erro in resultado["erradas"]:
            rotulo, situacao = VEREDITOS.get(erro["veredito"], VEREDITOS["sem revisão"])
            linhas.append(
                f'<div class="fdr-erro-eval"><div>{interface.selo(t(rotulo), situacao)}</div>'
                f'<div class="pergunta">{e(t(erro["pergunta"]))}</div>'
                f'<div class="nota">{e(t(erro["nota"]))}</div></div>'
            )
        interface.html_bruto("".join(linhas))
    interface.nota(
        t(
            "Modelo {modelo}, de {inicio} a {fim}, em {lotes} lotes (a cota gratuita do Gemini "
            "limita os pedidos por dia). Método e resultados completos em docs/assistente.md.",
            modelo=resultado["modelo"],
            inicio=painel.data(pd.Timestamp(resultado["datas"][0]).date()),
            fim=painel.data(pd.Timestamp(resultado["datas"][1]).date()),
            lotes=resultado["lotes"],
        )
    )


def exemplos(assistente) -> list[str]:
    """As perguntas de exemplo, no idioma da sessão (as gravadas estão em português)."""
    gravadas = assistente.demonstracao.perguntas()
    return [
        t(p) for p in (gravadas or [q["pergunta"] for q in ler_perguntas() if q.get("demo")])[:6]
    ]


def mostrar(resposta: Resposta) -> None:
    with st.chat_message("user", avatar=":material/person:"):
        st.markdown(resposta.pergunta)
    with st.chat_message("assistant", avatar=":material/database:"):
        rotulo, situacao = ORIGENS.get(resposta.origem, (resposta.origem, "neutro"))
        interface.html_bruto(interface.selo(t(rotulo), situacao))
        st.markdown(resposta.texto)
        if resposta.tabela is not None and not resposta.tabela.empty:
            grafico_da_resposta(resposta.tabela)
            st.dataframe(tabela_legivel(resposta.tabela), hide_index=True, width="stretch")
        if resposta.sql:
            travas_cumpridas()
            with st.expander(t("Ver a consulta SQL")):
                st.code(resposta.sql, language="sql")
        for aviso in resposta.avisos:
            interface.nota(aviso)


with interface.pagina_protegida():
    assistente, trava = interface.assistente()
    interface.cabecalho(
        t("Pergunte aos dados"),
        t("Perguntas em português, respostas do banco"),
        t(
            "O assistente transforma a pergunta numa consulta SQL, que passa por travas de "
            "segurança e roda nos dados do app. O número vem sempre do banco, nunca do modelo de "
            "linguagem."
        ),
        icone="conversa",
        meta=[
            (t("Modelo de linguagem"), "Gemini" if assistente.llm else t("Demonstração")),
            (t("Banco"), t("DuckDB · 6 tabelas")),
            (t("Consultas"), t("Só leitura")),
        ],
    )
    st.session_state.setdefault("conversa", [])
    st.session_state.setdefault("perguntas_ao_modelo", 0)

    if assistente.llm is None:
        interface.aviso(
            t(
                "Modo de demonstração: este app está sem a chave do Gemini. As perguntas de "
                "exemplo têm consultas gravadas, que rodam de novo nos dados atuais."
            )
        )
    else:
        interface.aviso(
            t(
                "Até {por_sessao} perguntas novas por visita e {por_dia} por dia (cota gratuita "
                "do Gemini). Depois disso, o assistente responde só às perguntas de exemplo.",
                por_sessao=assistente.uso.por_sessao,
                por_dia=assistente.uso.por_dia,
            )
        )

    interface.secao(t("Faça uma pergunta"), t("Ou comece por um dos exemplos abaixo."))
    # Dentro de um contêiner, a caixa de pergunta fica no corpo da página (e não presa embaixo).
    with st.container():
        digitada = st.chat_input(
            t("Ex.: Qual companhia mais atrasou em julho de 2026?"), max_chars=300
        )
    pergunta = None
    with st.container(key="exemplos"):
        botoes = st.columns(2, gap="small")
        for i, exemplo in enumerate(exemplos(assistente)):
            if botoes[i % 2].button(
                exemplo, key=f"exemplo_{i}", width="stretch", icon=":material/arrow_forward:"
            ):
                pergunta = exemplo
    pergunta = digitada or pergunta

    if pergunta:
        with trava, st.spinner(t("Consultando os dados...")):
            resposta = assistente.responder(
                pergunta,
                usadas_na_sessao=st.session_state["perguntas_ao_modelo"],
                idioma=idioma.atual(),
            )
        if resposta.tentativas:
            st.session_state["perguntas_ao_modelo"] += 1
        st.session_state["conversa"].append(resposta)

    if st.session_state["conversa"]:
        interface.secao(t("Conversa"))
    for resposta in reversed(st.session_state["conversa"]):
        mostrar(resposta)

    interface.secao(t("Como o assistente responde"))
    interface.etapas(
        [
            (
                t("Pergunta"),
                t("Em português, sobre os voos, as companhias e os aeroportos do app."),
            ),
            (
                t("Consulta"),
                t(
                    "O Gemini escreve uma consulta SQL a partir da descrição das tabelas, sem "
                    "receber as linhas do banco."
                ),
            ),
            (
                t("Travas"),
                t(
                    "Só leitura (SELECT), só as 6 tabelas do app, sem arquivos nem rede, no "
                    "máximo 1.000 linhas e 10 segundos."
                ),
            ),
            (
                t("Resposta"),
                t(
                    "O DuckDB roda a consulta e os números da resposta saem da tabela, que "
                    "aparece junto com o SQL."
                ),
            ),
        ]
    )

    mostrar_placar()
