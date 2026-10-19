"""Peças comuns às páginas do app Streamlit: recursos em cache, identidade visual, componentes,
gráficos e tratamento de erros.

- Dados com `st.cache_data` e recursos (conexões, modelo, assistente) com `st.cache_resource`.
- Toda página roda dentro de `pagina_protegida`: um erro vira uma mensagem clara para o usuário
  e o traceback vai só para o log.
- A chave do Gemini vem dos secrets do Streamlit ou da variável GEMINI_API_KEY. Sem chave, só o
  assistente muda (modo de demonstração).

Identidade visual: sinalização de aeroporto. Detalhes no bloco "Identidade visual" abaixo. O tema
do Streamlit está em .streamlit/config.toml, e o tema dos gráficos (Altair) é registrado aqui.
"""

import html
import logging
import os
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date

import altair as alt
import pandas as pd
import streamlit as st
import streamlit.components.v1 as componentes

from fdr import config, painel
from fdr.assistant.agent import Assistente, criar_assistente
from fdr.previsao import Previsor

log = logging.getLogger("fdr.app")

REPOSITORIO = "https://github.com/eduardohenrique15/flight-delay-radar"
AUTOR = "Eduardo Henrique de Sá"
LINKEDIN = "https://www.linkedin.com/in/eduardo-henrique15/"
GITHUB = "https://github.com/EduardoHenrique15"
PASTA_ESTATICA = config.RAIZ / "app" / "static"

# Identidade visual ------------------------------------------------------------------------------
# Inspirada na sinalização de aeroportos: as placas amarelas e pretas de Schiphol (Benno Wissing e
# Paul Mijksenaar: pouca informação por placa, pictogramas em quadros, seta preta num círculo
# branco), os painéis de partidas de letras que viram (Solari) e o mapa de atrasos por aeroporto
# do FlightAware (Misery Map). Tipografia condensada de transporte (Barlow) e números tabulares.
# Nos gráficos, o azul da sinalização é a série principal e o âmbar, a comparação (dupla validada
# no validador de paleta; o âmbar fica abaixo de 3:1 de contraste e por isso sempre tem legenda
# ou rótulo).
FUNDO = "#eceef1"
TINTA = "#14161a"
TEXTO = "#454b53"
SUAVE = "#7a818a"
LINHA = "#d4d8de"
GRADE = "#e4e7eb"
SUPERFICIE = "#ffffff"
PRETO = "#14161a"
AMARELO = "#ffc72c"
DESTAQUE = "#1d5fbf"  # série principal: o modelo, o voo escolhido
COMPARACAO = "#c98500"  # série de comparação: o baseline, o real, o que aumenta o risco
APAGADO = "#c3c8cf"  # opções fora de foco
# Rampa sequencial (âmbar, do claro ao escuro) para a taxa de atraso: mais escuro, mais atraso.
RAMPA = ["#fff3c4", "#ffe08a", "#ffcd4d", "#f0ad00", "#c48a00", "#8f6400", "#5c4000"]
FONTE = "'Barlow', 'Segoe UI', system-ui, sans-serif"
FONTE_TITULO = "'Barlow Semi Condensed', 'Barlow', 'Arial Narrow', sans-serif"
FONTE_NUMEROS = FONTE_TITULO
# Situação (cor do texto e do fundo): sempre com ícone e rótulo.
SITUACAO = {
    "bom": ("#0b6b2e", "#ddf3e4"),
    "atencao": ("#7a5200", "#fff0c2"),
    "critico": ("#a3221a", "#fde3e0"),
    "neutro": (TEXTO, "#e4e7eb"),
}
# As mesmas situações sobre o fundo preto do painel de partidas.
SITUACAO_NO_PAINEL = {"bom": "#4fd88a", "atencao": AMARELO, "critico": "#ff7a6b"}

# Pictogramas (24 x 24), no estilo dos quadros de sinalização.
PICTOGRAMAS = {
    "partidas": "M2.5 19h19v2h-19v-2zm19.57-9.36c-.21-.8-1.04-1.28-1.84-1.06L14.92 10l-6.9-6.43"
    "-1.93.51 4.14 7.17-4.97 1.33-1.97-1.54-1.45.39 2.59 4.49L21 11.49c.81-.23 1.28-1.05 "
    "1.07-1.85z",
    "relogio": "M11.99 2C6.47 2 2 6.48 2 12s4.47 10 9.99 10C17.52 22 22 17.52 22 12S17.52 2 "
    "11.99 2zM12 20c-4.42 0-8-3.58-8-8s3.58-8 8-8 8 3.58 8 8-3.58 8-8 8zm.5-13H11v6l5.25 "
    "3.15.75-1.23-4.5-2.67z",
    "aviao": "M21 16v-2l-8-5V3.5c0-.83-.67-1.5-1.5-1.5S10 2.67 10 3.5V9l-8 5v2l8-2.5V19l-2 "
    "1.5V22l3.5-1 3.5 1v-1.5L13 19v-5.5l8 2.5z",
    "grafico": "M3.5 18.49l6-6.01 4 4L22 6.92l-1.41-1.41-7.09 7.97-4-4L2 16.99z",
    "conversa": "M21 6h-2v9H6v2c0 .55.45 1 1 1h11l4 4V7c0-.55-.45-1-1-1zm-4 6V3c0-.55-.45-1-1-"
    "1H3c-.55 0-1 .45-1 1v14l4-4h10c.55 0 1-.45 1-1z",
    "info": "M11 7h2v2h-2zm0 4h2v6h-2zm1-9C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 "
    "2 12 2zm0 18c-4.41 0-8-3.59-8-8s3.59-8 8-8 8 3.59 8 8-3.59 8-8 8z",
}

AJUDA = {
    "pr_auc": "PR-AUC: mede se o modelo põe os voos que atrasam no topo da lista de risco. "
    "Vai de 0 a 1; um palpite ao acaso fica perto da taxa de atraso (cerca de 0,15).",
    "brier": "Brier: erro médio entre a probabilidade prevista e o que aconteceu (0 ou 1). "
    "Quanto menor, melhor.",
    "ece": "ECE: diferença média entre a probabilidade prevista e a taxa real, por faixas. "
    'Mede se "20% de chance" quer dizer 20% mesmo.',
    "psi": "PSI: quanto a distribuição de uma variável mudou em relação ao treino. Abaixo de "
    "0,10: estável; de 0,10 a 0,25: atenção; acima de 0,25: mudança forte.",
    "baseline": "Baseline: a taxa de atraso da rota naquele horário nos últimos 12 meses. É a "
    "régua que o modelo precisa vencer.",
}

# A largura total da página: as faixas e o rodapé saem do contêiner e vão de ponta a ponta com o
# truque da sombra (box-shadow + clip-path), sem criar rolagem horizontal.
PONTA_A_PONTA = "box-shadow: 0 0 0 100vmax {cor}; clip-path: inset(0 -100vmax);"

CSS = f"""
<style>
/* Esconde o que é do Streamlit e não do produto. */
[data-testid="stToolbarActions"], [data-testid="stMainMenu"], [data-testid="stAppDeployButton"],
[data-testid="stStatusWidget"], .stDeployButton, footer, [data-testid="stDecoration"] {{
    display: none !important;
}}
.stApp {{ font-variant-numeric: tabular-nums; }}
/* O Streamlit puxa cada bloco de Markdown 1rem para cima, contando com a margem do último
parágrafo. Os blocos em HTML deste app não têm essa margem: sem isto, encostariam no seguinte. */
[data-testid="stMarkdownContainer"] {{ margin-bottom: 0 !important; }}
[data-testid="stMarkdownContainer"] > p:last-child {{ margin-bottom: 0; }}
/* O CSS e o aviso do topo não ocupam lugar na página. */
[data-testid="stElementContainer"]:has(style) {{ display: none; }}
[data-testid="stElementContainer"]:has(.fdr-topo) {{ margin-bottom: -1rem; }}
.block-container {{ max-width: 1180px; padding-top: 3.75rem; padding-bottom: 0; }}

/* Barra do topo: preta, com a borda amarela das placas */
header[data-testid="stHeader"] {{ background: {PRETO}; border-bottom: 3px solid {AMARELO}; }}
[data-testid="stTopNavLink"] {{ border-radius: 2px !important; }}
[data-testid="stTopNavLink"] p {{
    color: #c9ced6 !important; font-family: {FONTE_TITULO}; font-weight: 600;
    text-transform: uppercase; letter-spacing: 0.07em; font-size: 0.86rem;
}}
[data-testid="stTopNavLink"]:hover {{ background: #2a2e35 !important; }}
[data-testid="stTopNavLink"][aria-current="page"] {{ background: {AMARELO} !important; }}
[data-testid="stTopNavLink"][aria-current="page"] p {{ color: {PRETO} !important; }}
[data-testid="stHeader"] button svg {{ color: #c9ced6; }}
.fdr-topo {{
    position: fixed; top: 0; right: 28px; height: 3.5rem; z-index: 999991; display: flex;
    align-items: center; gap: 8px; font-family: {FONTE_TITULO}; font-size: 0.78rem;
    font-weight: 600; letter-spacing: 0.12em; text-transform: uppercase; color: #9aa1ab;
    pointer-events: none;
}}
.fdr-topo i {{ width: 8px; height: 8px; background: #4fd88a; display: inline-block;
    box-shadow: 0 0 0 3px rgba(79, 216, 138, 0.2); }}
@media (max-width: 1100px) {{ .fdr-topo {{ display: none; }} }}

/* Faixa de título: de ponta a ponta, com o pictograma num quadro amarelo */
.fdr-faixa {{
    background: {PRETO}; color: #ffffff; padding: 40px 0 38px 0; margin: 0 0 2rem 0;
    {PONTA_A_PONTA.format(cor=PRETO)}
}}
.fdr-faixa-grade {{ display: grid; grid-template-columns: 84px minmax(0, 1fr) auto; gap: 28px;
    align-items: start; }}
.fdr-pictograma {{ width: 84px; height: 84px; background: {AMARELO}; display: flex;
    align-items: center; justify-content: center; border-radius: 3px; }}
.fdr-pictograma svg {{ width: 54px; height: 54px; fill: {PRETO}; }}
.fdr-sobretitulo {{
    font-family: {FONTE_TITULO}; font-size: 0.82rem; font-weight: 600; letter-spacing: 0.16em;
    text-transform: uppercase; color: {AMARELO}; margin: 0 0 0.45rem 0 !important;
}}
.fdr-titulo {{
    font-family: {FONTE_TITULO}; font-size: 2.75rem; line-height: 1.02; font-weight: 700;
    color: #ffffff; letter-spacing: 0.005em; text-transform: uppercase; margin: 0; padding: 0;
}}
.fdr-lead {{ font-size: 1.05rem !important; line-height: 1.5; color: #b9c0ca !important;
    max-width: 44rem; margin: 0.8rem 0 0 0 !important; }}
.fdr-faixa-meta {{ border-left: 1px solid #343840; padding-left: 22px; min-width: 170px; }}
.fdr-faixa-meta div {{ margin-bottom: 12px; }}
.fdr-faixa-meta .r {{ font-family: {FONTE_TITULO}; font-size: 0.72rem; color: #8b929c;
    text-transform: uppercase; letter-spacing: 0.12em; font-weight: 600; }}
.fdr-faixa-meta .v {{ font-family: {FONTE_TITULO}; font-size: 1.25rem; color: #ffffff;
    font-weight: 600; letter-spacing: 0.02em; }}
@media (max-width: 900px) {{
    .fdr-faixa-grade {{ grid-template-columns: 56px minmax(0, 1fr); gap: 18px; }}
    .fdr-faixa-meta {{ display: none; }}
    .fdr-pictograma {{ width: 56px; height: 56px; }}
    .fdr-pictograma svg {{ width: 36px; height: 36px; }}
    .fdr-titulo {{ font-size: 1.9rem; }}
    .fdr-faixa {{ padding: 28px 0 26px 0; }}
}}

/* Seções */
.fdr-secao {{ margin: 2.6rem 0 1rem 0; }}
.fdr-secao h3 {{
    display: flex; align-items: center; gap: 10px; font-family: {FONTE_TITULO};
    font-size: 1.15rem; font-weight: 700; color: {TINTA}; margin: 0; padding: 0;
    letter-spacing: 0.06em; text-transform: uppercase;
}}
.fdr-secao h3::before {{ content: ""; width: 12px; height: 12px; background: {AMARELO};
    border: 2px solid {PRETO}; flex: none; }}
.fdr-secao p {{ font-size: 0.94rem; color: {TEXTO}; margin: 0.35rem 0 0 24px;
    max-width: 50rem; line-height: 1.5; }}
.fdr-nota {{ font-size: 0.82rem !important; color: {SUAVE}; line-height: 1.5;
    margin: 0.5rem 0 0 0 !important; }}
/* Quadros (contêineres com borda criados por `quadro`) e rótulos dos campos */
[class*="st-key-quadro_"] {{
    background: {SUPERFICIE}; border-radius: 2px !important;
    border-top: 3px solid {PRETO} !important; padding: 20px 22px 22px 22px !important;
}}
/* Dentro de um quadro, a seção não precisa de tanto respiro em cima. */
[class*="st-key-quadro_"] .fdr-secao {{ margin-top: 0; }}
[class*="st-key-quadro_"] .fdr-secao p {{ margin-left: 0; }}
[data-testid="stWidgetLabel"] p {{
    font-family: {FONTE_TITULO}; font-weight: 600; text-transform: uppercase;
    letter-spacing: 0.08em; font-size: 0.76rem !important; color: {TEXTO};
}}
/* Exemplos (pills): etiquetas brancas que ficam amarelas ao passar o mouse */
button[data-variant="pills"] {{
    border-radius: 2px !important; background: {SUPERFICIE} !important;
    border: 1px solid {LINHA} !important; border-left: 4px solid {PRETO} !important;
    color: {TINTA} !important;
}}
button[data-variant="pills"]:hover {{
    background: {AMARELO} !important; border-color: {PRETO} !important;
}}
button[data-variant="pills"] p {{ font-weight: 600; }}
/* Seletor de modo (segmented control): o escolhido fica preto com letra amarela, como o menu */
button[data-variant="segmented_control"] {{
    background: {SUPERFICIE} !important; border-color: {LINHA} !important;
    color: {TINTA} !important; border-radius: 2px !important; padding: 8px 16px !important;
}}
button[data-variant="segmented_control"] p {{ font-family: {FONTE_TITULO}; font-weight: 700;
    text-transform: uppercase; letter-spacing: 0.06em; font-size: 0.88rem; }}
button[data-variant="segmented_control"][aria-checked="true"] {{
    background: {PRETO} !important; border-color: {PRETO} !important; color: {AMARELO} !important;
}}
button[data-variant="segmented_control"]:hover {{ border-color: {PRETO} !important; }}

/* Dicas dos gráficos: pretas, como as placas */
#vg-tooltip-element {{
    background: {PRETO} !important; color: #ffffff !important; border: none !important;
    border-radius: 2px !important; font-family: {FONTE} !important; font-size: 13px !important;
    box-shadow: 0 6px 18px rgba(0, 0, 0, 0.25) !important; padding: 8px 10px !important;
}}
#vg-tooltip-element td.key {{ color: {AMARELO} !important; }}
#vg-tooltip-element td.value {{ color: #ffffff !important; }}

/* Indicadores: uma régua única dividida */
.fdr-kpis {{
    display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
    background: {SUPERFICIE}; border: 1px solid {LINHA}; border-top: 3px solid {PRETO};
    border-radius: 2px; margin: 0;
}}
.fdr-kpi {{
    padding: 18px 22px 0 22px; border-left: 1px solid {LINHA}; display: flex;
    flex-direction: column; overflow: hidden;
}}
.fdr-kpi:first-child {{ border-left: none; }}
.fdr-kpi .rotulo {{ font-family: {FONTE_TITULO}; font-size: 0.78rem; color: {SUAVE};
    font-weight: 600; text-transform: uppercase; letter-spacing: 0.09em; }}
.fdr-kpi .valor {{
    font-family: {FONTE_NUMEROS}; font-size: 2.5rem; font-weight: 600; color: {TINTA};
    line-height: 1.08; margin: 6px 0 4px 0; white-space: nowrap; overflow: hidden;
    text-overflow: ellipsis;
}}
.fdr-kpi .detalhe {{ font-size: 0.85rem; color: {TEXTO}; line-height: 1.4; padding-bottom: 14px; }}
.fdr-kpi .variacao {{ display: inline-flex; align-items: center; gap: 4px; font-size: 0.8rem;
    font-weight: 700; padding: 1px 6px; border-radius: 2px; margin-right: 6px; }}
.fdr-kpi .tendencia {{ display: block; margin: auto -22px 0 -22px; width: calc(100% + 44px);
    height: 44px; }}
/* No celular, dois indicadores por linha */
@media (max-width: 760px) {{
    .fdr-kpis {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
    .fdr-kpi {{ padding: 14px 14px 0 14px; border-top: 1px solid {LINHA}; }}
    .fdr-kpi:nth-child(odd) {{ border-left: none; }}
    .fdr-kpi:nth-child(-n + 2) {{ border-top: none; }}
    .fdr-kpi .valor {{ font-size: 1.9rem; }}
    .fdr-kpi .detalhe {{ font-size: 0.8rem; }}
    .fdr-kpi .tendencia {{ margin: auto -14px 0 -14px; width: calc(100% + 28px); height: 34px; }}
}}

/* Selos de situação: cor + ícone + rótulo */
.fdr-selo {{
    display: inline-flex; align-items: center; gap: 6px; padding: 3px 9px 3px 7px;
    border-radius: 2px; font-family: {FONTE_TITULO}; font-size: 0.8rem; font-weight: 700;
    text-transform: uppercase; letter-spacing: 0.07em; line-height: 1.4;
}}
.fdr-selo svg {{ flex: none; }}

/* Resumo do mês */
.fdr-resumo {{ font-size: 1.22rem !important; line-height: 1.6; color: {TINTA};
    max-width: 56rem; margin: 1.8rem 0 0.6rem 0 !important; }}
.fdr-resumo b {{ background: linear-gradient(transparent 60%, {AMARELO} 60%); font-weight: 700; }}

/* Painel de partidas, com as letras que viram */
.fdr-painel {{ background: {PRETO}; border-radius: 3px; overflow: hidden;
    box-shadow: 0 1px 0 #000, 0 12px 28px rgba(20, 22, 26, 0.18); }}
.fdr-painel-topo {{ display: flex; justify-content: space-between; align-items: center;
    gap: 16px; padding: 16px 20px 14px 20px; border-bottom: 2px solid {AMARELO}; }}
.fdr-painel-topo .nome {{ display: flex; align-items: center; gap: 14px;
    font-family: {FONTE_TITULO}; font-weight: 700; font-size: 1.5rem; color: #ffffff;
    letter-spacing: 0.08em; text-transform: uppercase; }}
.fdr-painel-topo .nome svg {{ width: 30px; height: 30px; fill: {AMARELO}; }}
.fdr-painel-topo .nome small {{ color: #7d848e; font-weight: 600; font-size: 1.05rem; }}
.fdr-painel-topo .dia {{ font-family: {FONTE_TITULO}; color: {AMARELO}; font-weight: 600;
    letter-spacing: 0.1em; text-transform: uppercase; font-size: 0.95rem; text-align: right; }}
.fdr-painel-topo .dia small {{ display: block; color: #7d848e; font-size: 0.72rem;
    letter-spacing: 0.12em; }}
.fdr-painel-tabela {{ overflow-x: auto; }}
.fdr-painel table {{ width: 100%; border-collapse: collapse; margin: 0; }}
.fdr-painel th {{
    font-family: {FONTE_TITULO}; font-size: 0.72rem; font-weight: 600; letter-spacing: 0.14em;
    text-transform: uppercase; color: #8b929c; text-align: left; padding: 10px 14px 8px 14px;
    border: none; background: transparent; white-space: nowrap;
}}
.fdr-painel td {{
    font-family: {FONTE_TITULO}; font-size: 1.12rem; font-weight: 600; color: #f2f4f7;
    padding: 7px 14px; border: none; border-top: 1px solid #23272d; white-space: nowrap;
    letter-spacing: 0.02em;
}}
.fdr-painel tr:nth-child(even) td {{ background: #181b20; }}
.fdr-painel td.sub {{ color: #9aa1ab; font-weight: 500; font-size: 0.98rem; }}
.fdr-painel td.chance, .fdr-painel th.chance {{ text-align: right; }}
.fdr-painel td.chance {{ color: #ffffff; font-size: 1.2rem; }}
.fdr-painel .situacao {{ display: inline-flex; align-items: center; gap: 8px;
    text-transform: uppercase; font-size: 0.88rem; letter-spacing: 0.09em; }}
.flap {{
    display: inline-block; min-width: 0.78em; text-align: center; position: relative;
    margin-right: 2px; padding: 1px 3px; border-radius: 2px; color: #ffffff;
    background: linear-gradient(#2b2f37 0 50%, #22262c 50% 100%);
    animation: fdr-virar 0.55s cubic-bezier(.3, .7, .4, 1) both;
    animation-delay: calc(var(--i) * 28ms);
}}
.flap::after {{ content: ""; position: absolute; left: 0; right: 0; top: 50%; height: 1px;
    background: #0d0e11; }}
.flap.vazio {{ background: transparent; min-width: 0.4em; }}
.flap.vazio::after {{ display: none; }}
.flap.amarelo {{ color: {AMARELO}; }}
@keyframes fdr-virar {{
    0% {{ transform: rotateX(90deg); opacity: 0.1; }}
    60% {{ transform: rotateX(-12deg); opacity: 1; }}
    100% {{ transform: rotateX(0); opacity: 1; }}
}}
@media (prefers-reduced-motion: reduce) {{ .flap {{ animation: none; }} }}
.fdr-painel-legenda {{ display: flex; flex-wrap: wrap; gap: 18px; padding: 12px 20px;
    border-top: 1px solid #23272d; font-size: 0.82rem; color: #9aa1ab; }}
.fdr-painel-legenda span {{ display: inline-flex; align-items: center; gap: 6px; }}
@media (max-width: 760px) {{
    .fdr-painel .opcional {{ display: none; }}
    .fdr-painel td, .fdr-painel th {{ padding-left: 8px; padding-right: 8px; }}
    .fdr-painel td {{ font-size: 1rem; }}
    .fdr-painel-topo .nome small {{ display: none; }}
}}
@media (max-width: 480px) {{
    .fdr-painel .situacao .rotulo {{ display: none; }}
    .fdr-painel .flap {{ margin-right: 1px; padding: 1px 2px; }}
}}

/* Mapa: legenda e o painel do aeroporto escolhido */
.fdr-legenda-mapa {{ display: flex; flex-wrap: wrap; gap: 26px; align-items: center;
    font-size: 0.82rem; color: {TEXTO}; margin-top: 10px; }}
.fdr-legenda-mapa .rampa {{ display: inline-flex; align-items: center; gap: 8px; }}
.fdr-legenda-mapa .rampa i {{ width: 150px; height: 10px; display: inline-block;
    background: linear-gradient(90deg, {", ".join(RAMPA)}); border: 1px solid {LINHA}; }}
.fdr-legenda-mapa .tamanho {{ display: inline-flex; align-items: center; gap: 6px; }}
.fdr-legenda-mapa .tamanho b {{ display: inline-block; border-radius: 50%;
    border: 1.5px solid {TEXTO}; }}
.fdr-aeroporto {{ border-top: 3px solid {PRETO}; background: {SUPERFICIE};
    border-left: 1px solid {LINHA}; border-right: 1px solid {LINHA};
    border-bottom: 1px solid {LINHA}; padding: 18px 20px; }}
.fdr-aeroporto .codigo {{ font-family: {FONTE_TITULO}; font-size: 2.6rem; font-weight: 700;
    line-height: 1; color: {TINTA}; letter-spacing: 0.03em; }}
.fdr-aeroporto > .nome {{ font-size: 0.88rem; color: {TEXTO}; margin: 4px 0 14px 0; }}
.fdr-aeroporto .numeros {{ display: grid; grid-template-columns: 1fr 1fr; gap: 10px;
    padding: 12px 0; border-top: 1px solid {GRADE}; border-bottom: 1px solid {GRADE};
    margin-bottom: 14px; }}
.fdr-aeroporto .numeros .r {{ font-family: {FONTE_TITULO}; font-size: 0.72rem; color: {SUAVE};
    text-transform: uppercase; letter-spacing: 0.1em; font-weight: 600; }}
.fdr-aeroporto .numeros .v {{ font-family: {FONTE_TITULO}; font-size: 1.5rem; font-weight: 700;
    color: {TINTA}; }}
.fdr-aeroporto .titulo-lista {{ font-family: {FONTE_TITULO}; font-size: 0.78rem; color: {TEXTO};
    text-transform: uppercase; letter-spacing: 0.1em; font-weight: 700; margin-bottom: 10px; }}

/* Ranking em barras, com a marca da média quando houver */
.fdr-ranking {{ display: grid; gap: 9px; }}
.fdr-ranking .linha {{ display: grid; grid-template-columns: minmax(0, 10.5rem) 1fr 3.8rem;
    gap: 10px; align-items: center; font-size: 0.9rem; line-height: 1.35; color: {TINTA}; }}
.fdr-ranking .nome {{ white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
.fdr-ranking .nome b {{ font-family: {FONTE_TITULO}; font-weight: 700; letter-spacing: 0.03em;
    display: inline-block; min-width: 2.6em; }}
.fdr-ranking .trilha {{ position: relative; height: 10px; background: {GRADE};
    border-radius: 1px; }}
.fdr-ranking .trilha .barra {{ height: 100%; border-radius: 1px; }}
.fdr-ranking .trilha .ref {{ position: absolute; top: -4px; bottom: -4px; width: 3px;
    margin-left: -1px; background: {AMARELO}; outline: 1px solid {PRETO}; }}
.fdr-ranking .valor {{ font-family: {FONTE_NUMEROS}; text-align: right; font-weight: 700;
    font-size: 1rem; }}
.fdr-ranking .sub {{ color: {SUAVE}; font-weight: 400; }}
.fdr-ranking .legenda-ref {{ display: flex; align-items: center; gap: 8px; margin-top: 6px;
    font-size: 0.8rem; color: {TEXTO}; }}
.fdr-ranking .legenda-ref i {{ width: 3px; height: 16px; background: {AMARELO};
    outline: 1px solid {PRETO}; }}
/* Com o código da companhia num quadro, como no painel de partidas */
.fdr-ranking.chips {{ gap: 12px; }}
.fdr-ranking.chips .linha {{ grid-template-columns: minmax(0, 12.5rem) 1fr 4rem;
    font-size: 0.95rem; }}
.fdr-ranking.chips .nome b {{ background: {PRETO}; color: {AMARELO}; min-width: 2.5em;
    text-align: center; padding: 2px 0; margin-right: 8px; border-radius: 2px;
    font-size: 0.86rem; letter-spacing: 0.06em; }}
.fdr-ranking.chips .nome .sub {{ color: {TINTA}; font-weight: 500; }}
.fdr-ranking.chips .trilha {{ height: 14px; }}
.fdr-ranking .linha.destaque .valor, .fdr-ranking .linha.destaque .sub {{ color: {DESTAQUE};
    font-weight: 700; }}
.fdr-ranking.chips .linha.destaque .nome b {{ background: {DESTAQUE}; color: #ffffff; }}
.fdr-aeroporto .fdr-ranking .linha {{ grid-template-columns: minmax(0, 8rem) 1fr 3.4rem; }}
@media (max-width: 760px) {{
    .fdr-ranking.chips .linha {{ grid-template-columns: minmax(0, 9.5rem) 1fr 3.6rem; gap: 8px;
        font-size: 0.88rem; }}
}}

/* Placas de direção: amarelas, com a seta preta num círculo branco */
[class*="st-key-placas"] .stElementContainer:has(.stPageLink),
[class*="st-key-placas"] .stPageLink, [class*="st-key-placas"] .stPageLink > div,
[class*="st-key-placas"] .stPageLink a {{ width: 100% !important; }}
[class*="st-key-placas"] [data-testid="stPageLink"] a {{
    background: {AMARELO}; border-radius: 3px; padding: 14px 18px; width: 100%; display: flex;
    align-items: center; gap: 4px; border: none; min-height: 60px;
    transition: transform 0.12s, box-shadow 0.12s;
}}
[class*="st-key-placas"] [data-testid="stPageLink"] a:hover {{
    transform: translateY(-2px); box-shadow: 0 6px 0 {PRETO}; background: {AMARELO};
}}
[class*="st-key-placas"] [data-testid="stPageLink"] p {{
    color: {PRETO} !important; font-family: {FONTE_TITULO}; font-weight: 700;
    text-transform: uppercase; letter-spacing: 0.05em; font-size: 1.08rem;
}}
[class*="st-key-placas"] [data-testid="stIconMaterial"] {{
    color: {PRETO}; background: #ffffff; border-radius: 50%; width: 32px; height: 32px;
    display: inline-flex; align-items: center; justify-content: center; font-size: 22px;
    margin-right: 8px; flex: none;
}}

/* Número de impacto (Visão geral): uma placa amarela com o total de horas de atraso */
.fdr-impacto {{ display: grid; grid-template-columns: auto minmax(0, 1fr); gap: 28px;
    align-items: center; background: {AMARELO}; color: {PRETO}; border-radius: 3px;
    padding: 22px 28px; margin: 1.6rem 0 0 0; }}
.fdr-impacto .numero {{ font-family: {FONTE_NUMEROS}; font-size: 4.2rem; font-weight: 700;
    line-height: 0.95; letter-spacing: -0.01em; white-space: nowrap; }}
.fdr-impacto .numero span {{ display: block; font-size: 1rem; letter-spacing: 0.14em;
    text-transform: uppercase; margin-top: 6px; }}
.fdr-impacto .texto {{ font-size: 1.08rem; line-height: 1.55; max-width: 44rem; }}
@media (max-width: 760px) {{
    .fdr-impacto {{ grid-template-columns: 1fr; gap: 10px; padding: 18px 20px; }}
    .fdr-impacto .numero {{ font-size: 3rem; }}
}}

/* Calendário de atrasos (Pontualidade) */
.fdr-ano {{ font-family: {FONTE_TITULO}; font-weight: 700; font-size: 0.95rem;
    letter-spacing: 0.1em; color: {TINTA}; margin: 0.6rem 0 -0.6rem 0; }}
.fdr-piores {{ display: flex; flex-wrap: wrap; gap: 8px; margin-top: 4px; }}
.fdr-piores span {{ display: inline-flex; align-items: baseline; gap: 8px; padding: 5px 10px;
    border: 2px solid {PRETO}; border-radius: 2px; font-size: 0.88rem; background: {SUPERFICIE}; }}
.fdr-piores b {{ font-family: {FONTE_NUMEROS}; font-size: 1rem; }}
.fdr-piores-titulo {{ font-family: {FONTE_TITULO}; font-size: 0.76rem; font-weight: 700;
    letter-spacing: 0.1em; text-transform: uppercase; color: {TEXTO}; margin-top: 10px; }}

/* Quem fez (Sobre o modelo) */
.fdr-autor {{ display: grid; grid-template-columns: 84px minmax(0, 1fr); gap: 22px;
    align-items: center; }}
.fdr-autor .iniciais {{ width: 84px; height: 84px; border-radius: 3px; background: {PRETO};
    color: {AMARELO}; display: flex; align-items: center; justify-content: center;
    font-family: {FONTE_TITULO}; font-weight: 700; font-size: 2rem; letter-spacing: 0.04em; }}
.fdr-autor .nome {{ font-family: {FONTE_TITULO}; font-size: 1.6rem; font-weight: 700;
    color: {TINTA}; text-transform: uppercase; letter-spacing: 0.03em; }}
.fdr-autor .texto {{ font-size: 0.98rem; color: {TEXTO}; line-height: 1.55; margin-top: 4px;
    max-width: 46rem; }}
.fdr-autor .vaga {{ display: inline-flex; align-items: center; gap: 8px; margin-top: 10px;
    font-family: {FONTE_TITULO}; font-weight: 700; font-size: 0.82rem; letter-spacing: 0.08em;
    text-transform: uppercase; color: {PRETO}; background: {AMARELO}; padding: 4px 10px;
    border-radius: 2px; }}
.fdr-autor .vaga i {{ width: 8px; height: 8px; background: #0b6b2e; display: inline-block; }}
@media (max-width: 760px) {{
    .fdr-autor {{ grid-template-columns: 1fr; gap: 12px; }}
    .fdr-autor .iniciais {{ width: 56px; height: 56px; font-size: 1.4rem; }}
    .fdr-autor .nome {{ font-size: 1.3rem; }}
}}

/* Cartão de embarque (Previsão) */
.fdr-cartao {{ background: {SUPERFICIE}; border: 1px solid {LINHA}; border-radius: 6px;
    overflow: hidden; box-shadow: 0 10px 26px rgba(20, 22, 26, 0.09); }}
.fdr-cartao-topo {{ background: {PRETO}; color: {AMARELO}; display: flex; align-items: center;
    justify-content: space-between; height: 40px; padding: 0 24px; font-family: {FONTE_TITULO};
    font-weight: 700; font-size: 0.82rem; letter-spacing: 0.16em; text-transform: uppercase; }}
.fdr-cartao-topo div {{ display: flex; align-items: center; gap: 10px; }}
.fdr-cartao-topo span {{ color: #9aa1ab; }}
.fdr-cartao-topo svg {{ width: 18px; height: 18px; fill: {AMARELO}; transform: rotate(90deg); }}
.fdr-cartao-topo b {{ background: {AMARELO}; color: {PRETO}; padding: 1px 7px;
    border-radius: 2px; }}
.fdr-cartao-topo div:last-child {{ color: #ffffff; }}
.fdr-cartao-corpo {{ display: grid; grid-template-columns: minmax(0, 1.35fr) minmax(0, 1fr); }}
.fdr-cartao .trecho {{ padding: 24px 28px; }}
.fdr-cartao .canhoto {{ padding: 24px 28px; position: relative;
    border-left: 2px dashed {LINHA}; background: #fbfbfc; }}
.fdr-cartao .canhoto::before, .fdr-cartao .canhoto::after {{
    content: ""; position: absolute; left: -12px; width: 22px; height: 22px;
    border-radius: 50%; background: {FUNDO}; border: 1px solid {LINHA};
}}
/* Os recortes do picote ficam nas bordas do cartão: em cima, atravessando a faixa preta. */
.fdr-cartao .canhoto::before {{ top: -52px; }}
.fdr-cartao .canhoto::after {{ bottom: -12px; }}
.fdr-cartao .rotulo-pequeno {{
    font-family: {FONTE_TITULO}; font-size: 0.72rem; text-transform: uppercase;
    letter-spacing: 0.12em; color: {SUAVE}; font-weight: 600;
}}
.fdr-cartao .codigos {{ display: grid; grid-template-columns: auto 1fr auto; gap: 18px;
    align-items: center; margin-top: 4px; }}
.fdr-cartao .codigos .iata {{ font-family: {FONTE_TITULO}; font-size: 3.4rem; font-weight: 700;
    color: {TINTA}; letter-spacing: 0.02em; line-height: 1; }}
.fdr-cartao .rota {{ display: flex; align-items: center; gap: 10px; }}
.fdr-cartao .rota hr {{ flex: 1; border: none; border-top: 2px dashed {APAGADO}; margin: 0; }}
.fdr-cartao .rota svg {{ width: 30px; height: 30px; fill: {TINTA}; transform: rotate(90deg); }}
.fdr-cartao .cidades {{ display: flex; justify-content: space-between; gap: 12px;
    font-size: 0.9rem; color: {TEXTO}; margin-top: 6px; }}
.fdr-cartao .dados {{ display: grid; grid-template-columns: repeat(4, auto); gap: 12px 20px;
    justify-content: space-between; margin-top: 22px; padding-top: 16px;
    border-top: 1px solid {GRADE}; }}
.fdr-cartao .dados .v {{ font-family: {FONTE_TITULO}; font-size: 1.15rem; color: {TINTA};
    font-weight: 700; margin-top: 2px; }}
.fdr-cartao .chance {{ font-family: {FONTE_NUMEROS}; font-size: 4rem; font-weight: 700;
    color: {TINTA}; line-height: 1; margin: 8px 0 10px 0; }}
.fdr-cartao .comparacao {{ font-size: 0.88rem; color: {TEXTO}; line-height: 1.5;
    margin-top: 12px; }}
.fdr-cartao .barras {{ height: 34px; margin-top: 16px; opacity: 0.85;
    background: repeating-linear-gradient(90deg, {PRETO} 0 2px, transparent 2px 4px,
    {PRETO} 4px 5px, transparent 5px 8px, {PRETO} 8px 11px, transparent 11px 12px,
    {PRETO} 12px 13px, transparent 13px 16px); }}
.fdr-regua {{ position: relative; height: 10px; border-radius: 1px; background: {GRADE};
    margin: 18px 0 6px 0; }}
.fdr-regua .preenchido {{ position: absolute; left: 0; top: 0; bottom: 0; border-radius: 1px;
    background: {PRETO}; }}
.fdr-regua .marca {{ position: absolute; top: -5px; width: 4px; height: 20px;
    background: {AMARELO}; outline: 1px solid {PRETO}; }}
.fdr-regua-legenda {{ display: flex; justify-content: space-between; font-size: 0.76rem;
    color: {SUAVE}; }}
@media (max-width: 760px) {{
    .fdr-cartao-corpo {{ grid-template-columns: 1fr; }}
    .fdr-cartao .canhoto {{ border-left: none; border-top: 2px dashed {LINHA}; }}
    .fdr-cartao .canhoto::before {{ top: -12px; left: -12px; }}
    .fdr-cartao .canhoto::after {{ top: -12px; bottom: auto; left: auto; right: -12px; }}
    .fdr-cartao .codigos .iata {{ font-size: 2.4rem; }}
    .fdr-cartao .dados {{ grid-template-columns: repeat(2, auto); }}
    .fdr-cartao-topo {{ padding: 0 16px; }}
    .fdr-cartao-topo span {{ display: none; }}
    .fdr-cartao .trecho, .fdr-cartao .canhoto {{ padding: 20px 18px; }}
}}

/* Cartão compacto (Comparar dois voos): uma coluna só, como no celular */
.fdr-cartao.compacto .fdr-cartao-corpo {{ grid-template-columns: 1fr; }}
.fdr-cartao.compacto .canhoto {{ border-left: none; border-top: 2px dashed {LINHA}; }}
.fdr-cartao.compacto .canhoto::before {{ top: -12px; left: -12px; }}
.fdr-cartao.compacto .canhoto::after {{ top: -12px; bottom: auto; left: auto; right: -12px; }}
.fdr-cartao.compacto .codigos .iata {{ font-size: 2.6rem; }}
.fdr-cartao.compacto .dados {{ grid-template-columns: repeat(2, auto); }}
.fdr-cartao.compacto .chance {{ font-size: 3.2rem; }}
.fdr-cartao.compacto .fdr-cartao-topo span {{ display: none; }}
.fdr-cartao.compacto .trecho, .fdr-cartao.compacto .canhoto {{ padding: 20px 22px; }}

/* Fatores (Previsão) */
.fdr-fatores {{ display: grid; gap: 10px; }}
.fdr-fatores-cabecalho {{ display: grid; grid-template-columns: minmax(0, 15rem) 1fr 6rem;
    gap: 12px; font-family: {FONTE_TITULO}; font-size: 0.74rem; color: {SUAVE};
    text-transform: uppercase; letter-spacing: 0.1em; font-weight: 600; }}
.fdr-fatores-cabecalho div:nth-child(2) {{ display: flex; justify-content: space-between; }}
.fdr-fator {{ display: grid; grid-template-columns: minmax(0, 15rem) 1fr 6rem;
    align-items: center; gap: 12px; font-size: 0.94rem; color: {TINTA}; }}
.fdr-fator .barra {{ position: relative; height: 14px; }}
.fdr-fator .barra .eixo {{ position: absolute; left: 50%; top: -5px; bottom: -5px; width: 2px;
    background: {PRETO}; }}
.fdr-fator .barra .valor {{ position: absolute; top: 0; bottom: 0; border-radius: 1px; }}
.fdr-fator .numero {{ font-family: {FONTE_NUMEROS}; text-align: right;
    font-weight: 700; font-size: 1.02rem; white-space: nowrap; }}
/* No celular, o nome e o efeito em cima e a barra embaixo, na largura toda */
@media (max-width: 760px) {{
    .fdr-fatores .fdr-fator {{ grid-template-columns: 1fr auto;
        grid-template-areas: "nome numero" "barra barra"; gap: 4px 8px; font-size: 0.88rem; }}
    .fdr-fator > div:first-child {{ grid-area: nome; }}
    .fdr-fator .barra {{ grid-area: barra; }}
    .fdr-fator .numero {{ grid-area: numero; }}
    .fdr-fatores-cabecalho {{ grid-template-columns: 1fr; }}
    .fdr-fatores-cabecalho div:first-child, .fdr-fatores-cabecalho div:last-child,
    .fdr-fatores-cabecalho i {{ display: none; }}
}}
.fdr-fatores-cabecalho i {{ font-style: normal; }}

/* Linha do tempo em forma de rota (Monitoramento) */
.fdr-rota {{ display: grid; grid-auto-flow: column; grid-auto-columns: minmax(78px, 1fr);
    position: relative; padding: 8px 0 4px 0; overflow-x: auto; }}
.fdr-rota::before {{ content: ""; position: absolute; left: 39px; right: 39px; top: 25px;
    height: 3px; background: {PRETO}; }}
.fdr-parada {{ display: flex; flex-direction: column; align-items: center; gap: 8px;
    position: relative; text-align: center; }}
.fdr-parada .marco {{ width: 22px; height: 22px; border: 3px solid {PRETO};
    background: var(--cor, #ffffff); margin-top: 6px; z-index: 1; }}
.fdr-parada .mes {{ font-family: {FONTE_TITULO}; font-weight: 700; font-size: 0.92rem;
    text-transform: uppercase; letter-spacing: 0.04em; color: {TINTA}; }}
.fdr-parada .tipo {{ font-size: 0.74rem; color: {SUAVE}; line-height: 1.2; }}
.fdr-eventos {{ display: grid; gap: 10px; margin-top: 16px; }}
.fdr-evento {{ display: grid; grid-template-columns: 190px 1fr; gap: 16px; align-items: start;
    background: {SUPERFICIE}; border: 1px solid {LINHA}; border-left: 6px solid var(--cor);
    padding: 12px 16px; border-radius: 2px; }}
.fdr-evento .quando {{ font-family: {FONTE_TITULO}; font-weight: 700; font-size: 1rem;
    text-transform: uppercase; color: {TINTA}; }}
.fdr-evento .oque {{ font-size: 0.9rem; color: {TEXTO}; line-height: 1.5; }}
.fdr-evento .quando {{ display: flex; flex-direction: column; align-items: flex-start;
    gap: 6px; }}
@media (max-width: 760px) {{ .fdr-evento {{ grid-template-columns: 1fr; gap: 8px; }} }}

/* Etapas em forma de rota (Sobre o modelo) */
.fdr-etapas {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
    gap: 0; background: {SUPERFICIE}; border: 1px solid {LINHA};
    border-top: 3px solid {PRETO}; border-radius: 2px; }}
.fdr-etapa {{ padding: 18px 22px 20px 22px; border-left: 1px solid {LINHA}; position: relative; }}
.fdr-etapa:first-child {{ border-left: none; }}
.fdr-etapa .num {{ display: inline-flex; width: 30px; height: 30px; align-items: center;
    justify-content: center; background: {AMARELO}; color: {PRETO}; border: 2px solid {PRETO};
    font-family: {FONTE_TITULO}; font-weight: 700; font-size: 0.95rem; }}
.fdr-etapa .etapa-titulo {{ font-family: {FONTE_TITULO}; font-size: 1.12rem; font-weight: 700;
    text-transform: uppercase; letter-spacing: 0.04em; color: {TINTA}; margin: 12px 0 6px 0; }}
.fdr-etapa .detalhe {{ font-size: 0.9rem; color: {TEXTO}; line-height: 1.5; }}
.fdr-etapas.limites .num {{ background: {SUPERFICIE}; }}
@media (max-width: 760px) {{
    .fdr-etapa {{ border-left: none; border-top: 1px solid {LINHA}; }}
    .fdr-etapa:first-child {{ border-top: none; }}
}}

/* Aviso (texto de contexto, sem alarme) */
.fdr-aviso {{ border: 1px solid {LINHA}; border-left: 6px solid {AMARELO};
    background: {SUPERFICIE}; border-radius: 2px; padding: 12px 16px; font-size: 0.92rem;
    color: {TEXTO}; line-height: 1.5; margin: 0 0 1.4rem 0; }}

/* Tabela (PSI) */
.fdr-tabela-rolagem {{ overflow-x: auto; border: 1px solid {LINHA}; border-top: 3px solid {PRETO};
    border-radius: 2px; background: {SUPERFICIE}; }}
[class*="st-key-quadro_"] .fdr-tabela-rolagem {{ border: none; border-radius: 0; }}
.fdr-tabela {{ border-collapse: collapse; width: 100%; font-size: 0.92rem; margin: 0; }}
.fdr-tabela th, .fdr-tabela td {{ padding: 9px 14px; border: none;
    border-bottom: 1px solid {GRADE}; text-align: right; white-space: nowrap; }}
.fdr-tabela thead th {{ font-family: {FONTE_TITULO}; font-weight: 600; color: {TEXTO};
    font-size: 0.74rem; text-transform: uppercase; letter-spacing: 0.08em; background: #f6f7f8; }}
.fdr-tabela th:first-child {{ text-align: left; color: {TINTA}; }}
.fdr-tabela td {{ font-family: {FONTE_NUMEROS}; color: {TINTA}; font-weight: 600; }}
.fdr-tabela tbody tr:last-child th, .fdr-tabela tbody tr:last-child td {{ border-bottom: none; }}

/* Assistente */
[data-testid="stBottomBlockContainer"] {{ max-width: 1180px; }}
.stButton button {{ justify-content: flex-start; text-align: left; border-radius: 2px; }}
.st-key-exemplos .stButton button {{
    background: {SUPERFICIE}; border: 1px solid {LINHA}; border-left: 6px solid {AMARELO};
    padding: 12px 16px; min-height: 56px; font-size: 0.98rem;
}}
.st-key-exemplos .stButton button > div {{ justify-content: flex-start; width: 100%; }}
.st-key-exemplos .stButton button p {{ white-space: normal; text-align: left; }}
.st-key-exemplos .stButton button [data-testid="stIconMaterial"] {{ color: {PRETO}; }}
[data-testid="stChatInput"] {{ border-radius: 2px; border: 1px solid {LINHA};
    border-top: 3px solid {PRETO}; background: {SUPERFICIE}; }}
.st-key-exemplos .stButton button:hover {{ border-left-color: {PRETO}; color: {TINTA}; }}
[data-testid="stChatMessage"] {{ background: {SUPERFICIE}; border: 1px solid {LINHA};
    border-radius: 2px; padding: 14px 16px; }}

/* Rodapé de ponta a ponta */
.fdr-rodape {{
    background: {PRETO}; color: #b9c0ca; margin-top: 4rem; padding: 40px 0 34px 0;
    position: relative; box-shadow: 0 0 0 100vmax {PRETO};
    clip-path: inset(0 -100vmax -100vmax -100vmax);
}}
/* A linha amarela vai de ponta a ponta com o mesmo truque da sombra: um elemento que passasse
da largura da página criaria uma barra de rolagem lateral. */
.fdr-rodape::before {{ content: ""; position: absolute; top: 0; height: 3px; left: 0; right: 0;
    background: {AMARELO}; {PONTA_A_PONTA.format(cor=AMARELO)} }}
.fdr-rodape-grade {{ display: grid; grid-template-columns: 1.4fr 1fr 1fr; gap: 32px; }}
.fdr-rodape .marca {{ display: flex; align-items: center; gap: 12px; font-family: {FONTE_TITULO};
    font-weight: 700; font-size: 1.15rem; color: #ffffff; letter-spacing: 0.1em;
    text-transform: uppercase; }}
.fdr-rodape .marca span {{ width: 30px; height: 30px; background: {AMARELO}; display: flex;
    align-items: center; justify-content: center; border-radius: 3px; }}
.fdr-rodape .marca svg {{ width: 20px; height: 20px; fill: {PRETO}; }}
.fdr-rodape p {{ font-size: 0.86rem; line-height: 1.6; margin: 10px 0 0 0; color: #9aa1ab; }}
.fdr-rodape h4 {{ font-family: {FONTE_TITULO}; font-size: 0.76rem; color: {AMARELO};
    letter-spacing: 0.14em; text-transform: uppercase; margin: 0 0 8px 0; padding: 0; }}
.fdr-rodape a {{ color: #ffffff !important; text-decoration: none; display: block;
    font-size: 0.9rem; line-height: 1.9; }}
.fdr-rodape a:hover {{ color: {AMARELO} !important; }}
.fdr-rodape .contato {{ display: flex; flex-wrap: wrap; gap: 8px; margin-top: 14px; }}
.fdr-rodape .contato a {{ display: inline-block; border: 1px solid {AMARELO};
    color: {AMARELO} !important; padding: 4px 12px; border-radius: 2px;
    font-family: {FONTE_TITULO}; font-weight: 700; font-size: 0.82rem; letter-spacing: 0.08em;
    text-transform: uppercase; line-height: 1.6; }}
.fdr-rodape .contato a:hover {{ background: {AMARELO}; color: {PRETO} !important; }}
.fdr-rodape .vaga {{ color: #ffffff; font-weight: 600; }}
@media (max-width: 760px) {{ .fdr-rodape-grade {{ grid-template-columns: 1fr; gap: 20px; }} }}
</style>
"""


def configurar_pagina() -> None:
    st.set_page_config(
        page_title="Flight Delay Radar",
        page_icon=str(PASTA_ESTATICA / "marca.svg"),
        layout="wide",
    )
    st.logo(str(PASTA_ESTATICA / "logo.svg"), size="large", link=REPOSITORIO)
    st.markdown(CSS, unsafe_allow_html=True)
    try:
        ultimo = painel.nome_mes(date.fromisoformat(manifest()["ultimo_mes"]))
        st.markdown(
            f'<div class="fdr-topo"><i></i>Dados da ANAC até {_e(ultimo)}</div>',
            unsafe_allow_html=True,
        )
    except Exception:  # sem dados, o aviso do topo some; as páginas mostram o erro
        log.exception("Sem o manifest dos marts")


# Componentes -------------------------------------------------------------------------------------


def _e(texto: object) -> str:
    return html.escape(str(texto))


def pictograma(nome: str) -> str:
    return f'<svg viewBox="0 0 24 24" aria-hidden="true"><path d="{PICTOGRAMAS[nome]}"/></svg>'


def cabecalho(
    sobretitulo: str,
    titulo: str,
    texto: str,
    icone: str = "partidas",
    meta: list[tuple[str, str]] | None = None,
) -> None:
    """A faixa preta do título, de ponta a ponta, com o pictograma num quadro amarelo e, à
    direita, até três dados de contexto (rótulo, valor)."""
    lateral = ""
    if meta:
        itens = "".join(
            f'<div><div class="r">{_e(r)}</div><div class="v">{_e(v)}</div></div>' for r, v in meta
        )
        lateral = f'<div class="fdr-faixa-meta">{itens}</div>'
    st.markdown(
        f'<div class="fdr-faixa"><div class="fdr-faixa-grade">'
        f'<div class="fdr-pictograma">{pictograma(icone)}</div>'
        f'<div><p class="fdr-sobretitulo">{_e(sobretitulo)}</p>'
        f'<h1 class="fdr-titulo">{_e(titulo)}</h1>'
        f'<p class="fdr-lead">{_e(texto)}</p></div>{lateral}</div></div>',
        unsafe_allow_html=True,
    )


def secao(titulo: str, texto: str | None = None) -> None:
    corpo = f"<p>{_e(texto)}</p>" if texto else ""
    st.markdown(
        f'<div class="fdr-secao"><h3>{_e(titulo)}</h3>{corpo}</div>', unsafe_allow_html=True
    )


def nota(texto: str) -> None:
    st.markdown(f'<p class="fdr-nota">{_e(texto)}</p>', unsafe_allow_html=True)


@dataclass
class Numero:
    rotulo: str
    valor: str
    detalhe: str = ""
    ajuda: str = ""
    # Variação contra o período anterior: (texto, "sobe" ou "desce", "bom", "ruim" ou "neutro").
    variacao: tuple[str, str, str] | None = None
    tendencia: list[float] | None = None  # a série dos últimos meses, para a minilinha


def minilinha(valores: list[float], cor: str = DESTAQUE) -> str:
    """Linha de tendência em SVG (sem eixos), com o último ponto marcado."""
    if len(valores) < 2:
        return ""
    largura, altura, margem = 200, 44, 7
    menor, maior = min(valores), max(valores)
    amplitude = (maior - menor) or 1.0
    pontos = [
        (
            i * largura / (len(valores) - 1),
            margem + (altura - 2 * margem) * (1 - (v - menor) / amplitude),
        )
        for i, v in enumerate(valores)
    ]
    linha = " ".join(f"{x:.1f},{y:.1f}" for x, y in pontos)
    area = f"0,{altura} {linha} {largura},{altura}"
    x, y = pontos[-1]
    return (
        f'<svg class="tendencia" viewBox="0 0 {largura} {altura}" preserveAspectRatio="none">'
        f'<polygon points="{area}" fill="{cor}" fill-opacity="0.07"/>'
        f'<polyline points="{linha}" fill="none" stroke="{cor}" stroke-width="1.8" '
        f'vector-effect="non-scaling-stroke"/>'
        f'<rect x="{x - 4:.1f}" y="{y - 2.5:.1f}" width="5" height="5" fill="{cor}"/></svg>'
    )


def _variacao(variacao: tuple[str, str, str]) -> str:
    texto, direcao, sentido = variacao
    cor, fundo = SITUACAO[{"bom": "bom", "ruim": "critico"}.get(sentido, "neutro")]
    seta = "&#9650;" if direcao == "sobe" else "&#9660;"
    estilo = f"color:{cor};background:{fundo}"
    return f'<span class="variacao" style="{estilo}">{seta} {_e(texto)}</span>'


def numeros(itens: list[Numero]) -> None:
    """Os indicadores numa régua única, dividida em colunas (uma coluna só no celular), com a
    variação contra o período anterior e a tendência quando houver."""
    celulas = "".join(
        f'<div class="fdr-kpi" title="{_e(n.ajuda)}"><div class="rotulo">{_e(n.rotulo)}</div>'
        f'<div class="valor">{_e(n.valor)}</div><div class="detalhe">'
        f"{_variacao(n.variacao) if n.variacao else ''}{_e(n.detalhe)}</div>"
        f"{minilinha(n.tendencia) if n.tendencia else ''}</div>"
        for n in itens
    )
    st.markdown(f'<div class="fdr-kpis">{celulas}</div>', unsafe_allow_html=True)


ICONES = {
    # Círculo (bom), triângulo (atenção), losango (crítico), traço (neutro).
    "bom": '<circle cx="6" cy="6" r="4.5"/>',
    "atencao": '<path d="M6 1.2 11 10.5H1z"/>',
    "critico": '<path d="M6 .8 11.2 6 6 11.2.8 6z"/>',
    "neutro": '<rect x="1" y="4.6" width="10" height="2.8"/>',
}


def icone_situacao(situacao: str, cor: str) -> str:
    return f'<svg width="12" height="12" viewBox="0 0 12 12" fill="{cor}">{ICONES[situacao]}</svg>'


def selo(texto: str, situacao: str = "neutro") -> str:
    """HTML de um selo com ícone e rótulo (a cor nunca vai sozinha)."""
    cor, fundo = SITUACAO[situacao]
    estilo = f"color:{cor};background:{fundo}"
    return (
        f'<span class="fdr-selo" style="{estilo}">{icone_situacao(situacao, cor)}{_e(texto)}</span>'
    )


def letras(texto: str, inicio: int = 0, classe: str = "") -> str:
    """O texto em placas de letras que viram (painel Solari), com um atraso por letra."""
    return "".join(
        f'<span class="flap{" vazio" if c == " " else ""} {classe}" style="--i:{inicio + i}">'
        f"{'&nbsp;' if c == ' ' else _e(c)}</span>"
        for i, c in enumerate(texto)
    )


@dataclass
class Partida:
    hora: str
    voo: str
    companhia: str
    origem: str
    destino: str
    cidade_destino: str
    chance: str
    situacao: str  # "bom", "atencao" ou "critico"
    texto_situacao: str


def painel_de_partidas(partidas: list[Partida], dia: str, legenda: list[tuple[str, str]]) -> None:
    """Um painel de partidas de aeroporto, com a chance de atraso prevista pelo modelo.
    `legenda`: (situação, texto) de cada faixa de risco."""
    linhas = []
    for n, p in enumerate(partidas):
        atraso = n * 6  # cada linha começa a virar um pouco depois da anterior
        cor = SITUACAO_NO_PAINEL[p.situacao]
        linhas.append(
            f"<tr><td>{letras(p.hora, atraso, 'amarelo')}</td>"
            f"<td class='opcional'>{letras(p.voo, atraso + 4)}</td>"
            f"<td>{letras(p.origem, atraso + 2)}</td><td>{letras(p.destino, atraso + 3)}</td>"
            f"<td class='sub opcional'>{_e(p.cidade_destino)}</td>"
            f"<td class='sub opcional'>{_e(p.companhia)}</td>"
            f"<td class='chance'>{_e(p.chance)}</td>"
            f"<td><span class='situacao' style='color:{cor}'>{icone_situacao(p.situacao, cor)}"
            f"<span class='rotulo'>{_e(p.texto_situacao)}</span></span></td></tr>"
        )
    cabecalho_tabela = (
        "<tr><th>Partida</th><th class='opcional'>Voo</th><th>De</th><th>Para</th>"
        "<th class='opcional'>Destino</th><th class='opcional'>Companhia</th>"
        "<th class='chance'>Chance</th><th>Previsão</th></tr>"
    )
    itens_legenda = "".join(
        f"<span style='color:{SITUACAO_NO_PAINEL[s]}'>{icone_situacao(s, SITUACAO_NO_PAINEL[s])}"
        f"<span style='color:#9aa1ab'>{_e(t)}</span></span>"
        for s, t in legenda
    )
    st.markdown(
        f'<div class="fdr-painel"><div class="fdr-painel-topo">'
        f'<div class="nome">{pictograma("partidas")}Partidas <small>/ Departures</small></div>'
        f'<div class="dia">{_e(dia)}<small>Chance de atraso prevista pelo modelo</small></div>'
        f'</div><div class="fdr-painel-tabela"><table><thead>{cabecalho_tabela}</thead>'
        f"<tbody>{''.join(linhas)}</tbody></table></div>"
        f'<div class="fdr-painel-legenda">{itens_legenda}</div></div>',
        unsafe_allow_html=True,
    )


def cor_da_taxa(
    taxa: float, minimo: float, maximo: float, rampa: list[str] = RAMPA, alfa: int = 225
) -> list[int]:
    """A taxa de atraso na rampa âmbar, em RGBA para o pydeck (mais escuro = mais atraso)."""
    posicao = 0.0 if maximo <= minimo else min(max((taxa - minimo) / (maximo - minimo), 0.0), 1.0)
    hexa = rampa[min(int(posicao * len(rampa)), len(rampa) - 1)]
    return [int(hexa[i : i + 2], 16) for i in (1, 3, 5)] + [alfa]


def legenda_do_mapa(minimo: float, maximo: float, tamanho: str, rampa: list[str] = RAMPA) -> str:
    """A legenda dos mapas: a rampa de cor da taxa de atraso e o que o tamanho representa."""
    return (
        f'<div class="fdr-legenda-mapa"><span class="rampa">{_e(painel.porcentagem(minimo, 0))}'
        f'<i style="background:linear-gradient(90deg, {", ".join(rampa)})"></i>'
        f"{_e(painel.porcentagem(maximo, 0))} com atraso</span>"
        f'<span class="tamanho"><b style="width:8px;height:8px"></b>'
        f'<b style="width:16px;height:16px"></b><b style="width:26px;height:26px"></b>'
        f"{_e(tamanho)}</span></div>"
    )


def ranking(
    linhas: list[tuple[str, str, float, str]],
    maximo: float,
    cor: str = PRETO,
    referencia: tuple[float, str] | None = None,
    chips: bool = False,
    destacar: str | None = None,
) -> None:
    """Barras horizontais em HTML: (código, nome, valor de 0 a 1, texto do valor)."""
    st.markdown(
        ranking_html(linhas, maximo, cor, referencia, chips, destacar), unsafe_allow_html=True
    )


def ranking_html(
    linhas: list[tuple[str, str, float, str]],
    maximo: float,
    cor: str = PRETO,
    referencia: tuple[float, str] | None = None,
    chips: bool = False,
    destacar: str | None = None,
) -> str:
    """`referencia`: (valor, legenda) de uma marca amarela em cada barra (por exemplo, a média).
    `chips`: o código vai num quadro preto, como no painel de partidas. `destacar`: o código da
    linha que fica em azul (a escolha do usuário)."""
    maximo = maximo or 1
    marca = (
        f'<i class="ref" style="left:{100 * min(referencia[0] / maximo, 1):.1f}%"></i>'
        if referencia
        else ""
    )
    itens = "".join(
        f'<div class="linha{" destaque" if codigo == destacar else ""}"><div class="nome">'
        f'<b>{_e(codigo)}</b> <span class="sub">{_e(nome)}</span></div>'
        f'<div class="trilha"><div class="barra" style="width:{100 * valor / maximo:.1f}%;'
        f'background:{DESTAQUE if codigo == destacar else cor}"></div>{marca}</div>'
        f'<div class="valor">{_e(texto)}</div></div>'
        for codigo, nome, valor, texto in linhas
    )
    legenda = f'<div class="legenda-ref"><i></i>{_e(referencia[1])}</div>' if referencia else ""
    return f'<div class="fdr-ranking{" chips" if chips else ""}">{itens}{legenda}</div>'


def quadro(nome: str, altura: int | str = "content"):
    """Um quadro branco com a borda preta em cima (contêiner com borda do Streamlit). A chave
    `quadro_<nome>` é o que o CSS usa para achá-lo."""
    return st.container(border=True, key=f"quadro_{nome}", height=altura)


def etapas(itens: list[tuple[str, str]], limites: bool = False) -> None:
    """Passos numerados lado a lado (um embaixo do outro no celular). `limites`: o número fica
    num quadro branco, para as limitações não parecerem mais um passo."""
    cartoes = "".join(
        f'<div class="fdr-etapa"><span class="num">{i}</span>'
        f'<div class="etapa-titulo">{_e(titulo)}</div><div class="detalhe">{_e(texto)}</div></div>'
        for i, (titulo, texto) in enumerate(itens, start=1)
    )
    classe = "fdr-etapas limites" if limites else "fdr-etapas"
    st.markdown(f'<div class="{classe}">{cartoes}</div>', unsafe_allow_html=True)


def copiar_link(link: str) -> None:
    """O link num campo só de leitura e um botão "Copiar link" que avisa quando copiou. Usa a
    área de transferência do navegador e, se ela não estiver disponível (por exemplo, fora do
    https), seleciona o texto e copia do jeito antigo."""
    seguro = html.escape(link, quote=True)
    componentes.html(
        f"""
<div style="display:flex;gap:8px;font-family:Barlow,'Segoe UI',system-ui,sans-serif">
  <input id="link" readonly value="{seguro}" onclick="this.select()"
    style="flex:1;min-width:0;padding:10px 12px;border:1px solid {LINHA};border-radius:2px;
    font-family:'JetBrains Mono',Consolas,monospace;font-size:13px;color:{TINTA};
    background:#f6f7f8">
  <button id="copiar" type="button"
    style="flex:none;padding:0 18px;border:none;border-radius:2px;background:{AMARELO};
    color:{PRETO};font-weight:700;font-size:14px;letter-spacing:.06em;text-transform:uppercase;
    cursor:pointer">Copiar link</button>
</div>
<script>
const campo = document.getElementById("link"), botao = document.getElementById("copiar");
function avisar(texto) {{
  botao.textContent = texto;
  setTimeout(() => {{ botao.textContent = "Copiar link"; }}, 2000);
}}
function jeitoAntigo() {{
  campo.select();
  try {{ avisar(document.execCommand("copy") ? "Copiado ✓" : "Use Ctrl+C"); }}
  catch (e) {{ avisar("Use Ctrl+C"); }}
}}
botao.addEventListener("click", () => {{
  if (navigator.clipboard && window.isSecureContext) {{
    navigator.clipboard.writeText(campo.value).then(() => avisar("Copiado ✓"), jeitoAntigo);
  }} else {{
    jeitoAntigo();
  }}
}});
</script>
""",
        height=48,
    )


def resumo(texto_html: str) -> None:
    """O parágrafo de resumo. Recebe HTML já escapado, com os números em <b>."""
    st.markdown(f'<p class="fdr-resumo">{texto_html}</p>', unsafe_allow_html=True)


def aviso(texto: str) -> None:
    st.markdown(f'<div class="fdr-aviso">{_e(texto)}</div>', unsafe_allow_html=True)


def html_bruto(conteudo: str) -> None:
    st.markdown(conteudo, unsafe_allow_html=True)


def rodape() -> None:
    """O rodapé de ponta a ponta, igual em todas as páginas."""
    links_projeto = [
        ("Código no GitHub", REPOSITORIO),
        ("Cartão do modelo", f"{REPOSITORIO}/blob/main/docs/modelo.md"),
        ("Decisões de projeto (ADRs)", f"{REPOSITORIO}/tree/main/docs/decisoes"),
    ]
    links_dados = [
        (
            "VRA: Voo Regular Ativo (ANAC)",
            "https://www.gov.br/anac/pt-br/assuntos/dados-e-estatisticas",
        ),
        ("Aeroportos (OurAirports)", "https://ourairports.com/data/"),
        ("Como os dados foram tratados", f"{REPOSITORIO}/blob/main/docs/dados.md"),
    ]

    def lista(itens: list[tuple[str, str]]) -> str:
        return "".join(
            f'<a href="{_e(url)}" target="_blank" rel="noopener">{_e(t)}</a>' for t, url in itens
        )

    st.markdown(
        f'<div class="fdr-rodape"><div class="fdr-rodape-grade"><div>'
        f'<div class="marca"><span>{pictograma("partidas")}</span>Flight Delay Radar</div>'
        f"<p>Pontualidade dos voos nacionais com os dados públicos da ANAC, previsão de atraso "
        f"com LightGBM validada no tempo, monitoramento mês a mês e um assistente que responde "
        f"em SQL.</p><p>Projeto de {_e(AUTOR)}. "
        f'<span class="vaga">Aberto a vagas em Ciência de Dados, Machine Learning e IA.</span>'
        f'</p><div class="contato"><a href="{_e(LINKEDIN)}" target="_blank" rel="noopener">'
        f'LinkedIn</a><a href="{_e(GITHUB)}" target="_blank" rel="noopener">GitHub</a></div>'
        f"</div>"
        f"<div><h4>Projeto</h4>{lista(links_projeto)}</div>"
        f"<div><h4>Dados</h4>{lista(links_dados)}</div></div></div>",
        unsafe_allow_html=True,
    )


@contextmanager
def pagina_protegida() -> Iterator[None]:
    """Nenhum traceback chega ao usuário: a mensagem é curta e o detalhe vai para o log. O
    rodapé aparece sempre, com ou sem erro."""
    try:
        yield
    except Exception:
        log.exception("Erro na página")
        st.error(
            "Algo deu errado ao montar esta página. Tente recarregar; se continuar, os dados "
            "podem estar sendo atualizados."
        )
    finally:
        rodape()


# Recursos ---------------------------------------------------------------------------------------


@st.cache_resource(show_spinner=False)
def _conexao_marts():
    return painel.conectar_marts()


def consultar(funcao: Callable, *args):
    """Roda uma consulta de fdr.painel num cursor próprio (o DuckDB não divide uma conexão entre
    threads, e cada sessão do Streamlit roda numa thread)."""
    with _conexao_marts().cursor() as cursor:
        return funcao(cursor, *args)


@st.cache_data(show_spinner=False, ttl=3600)
def dados(nome: str, *args):
    """Resultado em cache de uma consulta de fdr.painel, pelo nome da função."""
    return consultar(getattr(painel, nome), *args)


@st.cache_data(show_spinner=False)
def manifest() -> dict:
    return painel.manifest()


@st.cache_data(show_spinner=False)
def json_do_projeto(caminho_relativo: str) -> dict:
    return painel.ler_json(config.RAIZ / caminho_relativo)


@st.cache_resource(show_spinner="Carregando o modelo...")
def previsor() -> Previsor:
    return Previsor(config.PASTA_MARTS / "previsao")


def chave_gemini() -> str | None:
    try:
        chave = st.secrets.get("GEMINI_API_KEY")
    except Exception:  # sem secrets.toml, o Streamlit levanta erro ao ler
        chave = None
    return chave or os.environ.get("GEMINI_API_KEY") or None


@st.cache_resource(show_spinner=False)
def _assistente(chave: str | None) -> tuple[Assistente, threading.Lock]:
    banco = painel.garantir_banco_app()
    return criar_assistente(chave, banco), threading.Lock()


def assistente() -> tuple[Assistente, threading.Lock]:
    """O assistente e uma trava: a conexão do assistente atende uma pergunta por vez."""
    return _assistente(chave_gemini())


# Gráficos ---------------------------------------------------------------------------------------


@alt.theme.register("fdr", enable=True)
def _tema_dos_graficos() -> alt.theme.ThemeConfig:
    eixo = {
        "labelColor": TEXTO,
        "titleColor": TEXTO,
        "labelFont": FONTE,
        "titleFont": FONTE_TITULO,
        "labelFontSize": 13,
        "titleFontSize": 11,
        "titleFontWeight": 600,
        "gridColor": GRADE,
        "domain": False,
        "ticks": False,
        "labelPadding": 6,
        "titlePadding": 10,
    }
    return {
        "config": {
            "background": "transparent",
            "font": FONTE,
            # Números no padrão brasileiro nos eixos e nas dicas: 12,5% e 1.234.
            "locale": {
                "number": {
                    "decimal": ",",
                    "thousands": ".",
                    "grouping": [3],
                    "currency": ["R$ ", ""],
                }
            },
            "view": {"stroke": None},
            "axis": eixo,
            "axisX": {"grid": False, "domain": True, "domainColor": TINTA, "domainWidth": 1.5},
            "legend": {
                "labelColor": TEXTO,
                "titleColor": TEXTO,
                "labelFont": FONTE,
                "titleFont": FONTE_TITULO,
                "labelFontSize": 13,
                "titleFontSize": 11,
                "titleFontWeight": 600,
                "symbolSize": 90,
                "symbolType": "square",
                "orient": "top",
                "direction": "horizontal",
            },
            "range": {"category": [DESTAQUE, COMPARACAO], "heatmap": RAMPA, "ramp": RAMPA},
            "line": {"strokeWidth": 2.25},
            "point": {"size": 56, "filled": True, "shape": "square"},
            "bar": {"cornerRadiusEnd": 1},
            "text": {"font": FONTE, "fontSize": 12, "color": TEXTO},
        }
    }


def grafico(chart: alt.Chart | alt.LayerChart, altura: int = 300) -> None:
    """Mostra um gráfico Altair com o tema do projeto (e não o do Streamlit)."""
    st.altair_chart(chart.properties(height=altura), theme=None, width="stretch")


def grafico_linhas(
    tabela: pd.DataFrame,
    x: str,
    series: dict[str, str],
    titulo_y: str,
    formato: str,
    marcas: list[tuple[date, str]] | None = None,
):
    """Uma linha por coluna de `series` ({coluna: rótulo}), no máximo duas: a primeira é a
    principal (azul); a segunda, a comparação (âmbar). `marcas`: meses com uma linha vertical e um
    rótulo (por exemplo, um retreino)."""
    longa = tabela.melt(id_vars=[x], value_vars=list(series), var_name="serie", value_name="valor")
    longa["serie"] = longa["serie"].map(series)
    # Mês como texto ("ago/26"), na ordem do tempo: um eixo de datas mudaria o dia pelo fuso.
    ordem = sorted(longa[x].unique())
    longa["mes_rotulo"] = [painel.mes_curto(pd.Timestamp(m).date()) for m in longa[x]]
    rotulos = [painel.mes_curto(pd.Timestamp(m).date()) for m in ordem]
    cores = alt.Scale(domain=list(series.values()), range=[DESTAQUE, COMPARACAO][: len(series)])
    eixo_x = alt.X(
        "mes_rotulo:O",
        title=None,
        sort=rotulos,
        axis=alt.Axis(labelAngle=0, labelOverlap="parity"),
        scale=alt.Scale(domain=rotulos),
    )
    base = alt.Chart(longa).encode(
        x=eixo_x,
        y=alt.Y("valor:Q", title=titulo_y, axis=alt.Axis(format=formato, tickCount=5)),
        # Uma série só dispensa legenda: o título da seção já diz o que é.
        color=alt.Color(
            "serie:N", scale=cores, legend=alt.Legend(title=None) if len(series) > 1 else None
        ),
        tooltip=[
            alt.Tooltip("mes_rotulo:O", title="Mês"),
            alt.Tooltip("serie:N", title="Série"),
            alt.Tooltip("valor:Q", title=titulo_y, format=formato.replace("%", ".1%")),
        ],
    )
    camadas = base.mark_line() + base.mark_point(stroke=SUPERFICIE, strokeWidth=1.5)
    if marcas:
        tabela_marcas = pd.DataFrame(
            {
                "mes_rotulo": [painel.mes_curto(m) for m, _ in marcas],
                "texto": [t for _, t in marcas],
            }
        )
        # O rótulo fica à direita da linha, ou à esquerda quando a marca está no fim do eixo.
        tabela_marcas["fim"] = [
            rotulos.index(m) > 0.6 * (len(rotulos) - 1) for m in tabela_marcas["mes_rotulo"]
        ]
        regra = alt.Chart(tabela_marcas).encode(x=eixo_x)
        rotulo = {
            "baseline": "top",
            "fontWeight": 700,
            "color": TINTA,
            "font": FONTE_TITULO,
            "fontSize": 13,
        }
        camadas = (
            regra.mark_rule(color=TINTA, strokeDash=[3, 3], strokeWidth=1.5)
            + regra.transform_filter("!datum.fim")
            .mark_text(align="left", dx=6, dy=2, **rotulo)
            .encode(y=alt.value(0), text="texto:N")
            + regra.transform_filter("datum.fim")
            .mark_text(align="right", dx=-6, dy=2, **rotulo)
            .encode(y=alt.value(0), text="texto:N")
            + camadas
        )
    return camadas
