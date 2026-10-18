"""Flight Delay Radar: o app (docs/deploy.md).

Uso local:  streamlit run app/streamlit_app.py
No Streamlit Community Cloud, este é o arquivo principal (docs/deploy.md).
"""

import sys
from pathlib import Path

# No Streamlit Cloud o pacote não é instalado: o código de src/ entra pelo caminho.
SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import streamlit as st  # noqa: E402

from fdr import interface  # noqa: E402

interface.configurar_pagina()

PAGINAS = Path(__file__).parent / "paginas"
navegacao = st.navigation(
    [
        st.Page(PAGINAS / "inicio.py", title="Visão geral", default=True),
        st.Page(PAGINAS / "pontualidade.py", title="Pontualidade"),
        st.Page(PAGINAS / "previsao.py", title="Previsão"),
        st.Page(PAGINAS / "monitoramento.py", title="Monitoramento"),
        st.Page(PAGINAS / "assistente.py", title="Pergunte aos dados"),
        st.Page(PAGINAS / "sobre.py", title="Sobre o modelo"),
    ],
    position="top",
)
navegacao.run()
