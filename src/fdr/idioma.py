"""Idioma do app: português (padrão) ou inglês.

O texto em português fica no código, como sempre; `t()` devolve a tradução quando o idioma da
sessão é o inglês. As traduções ficam em fdr/traducoes/, um arquivo por página, com o texto em
português como chave:

    t("Voos de {inicio} a {fim}", inicio=..., fim=...)

A chave é o texto com os campos ({inicio}), nunca uma f-string: assim a mesma chave serve para
qualquer valor. Um texto sem tradução aparece em português e vai para `FALTANDO` (os testes do
app em inglês exigem que fique vazio).

O idioma vale para a thread que roda a página (cada sessão do Streamlit roda numa thread), e a
página o define no começo de cada execução com `definir`. Fora do app (pipeline, testes de
fdr.painel) o idioma é sempre o português.
"""

import threading
from collections.abc import Sequence

IDIOMAS = {"pt": "PT", "en": "EN"}
PADRAO = "pt"

_local = threading.local()
FALTANDO: set[str] = set()


def definir(codigo: str | None) -> str:
    _local.codigo = codigo if codigo in IDIOMAS else PADRAO
    return _local.codigo


def atual() -> str:
    return getattr(_local, "codigo", PADRAO)


def ingles() -> bool:
    return atual() == "en"


def t(texto: str, **campos: object) -> str:
    """O texto no idioma da sessão, com os campos preenchidos."""
    if ingles():
        from fdr.traducoes import TEXTOS

        traducao = TEXTOS.get(texto)
        if traducao is None:
            FALTANDO.add(texto)
            traducao = texto
    else:
        traducao = texto
    return traducao.format(**campos) if campos else traducao


class PorIdioma(Sequence):
    """Uma lista de rótulos (dias da semana, meses) que muda com o idioma da sessão."""

    def __init__(self, **por_idioma: Sequence[str]):
        self._por_idioma = por_idioma

    def _lista(self) -> Sequence[str]:
        return self._por_idioma.get(atual(), self._por_idioma[PADRAO])

    def __getitem__(self, indice):
        return self._lista()[indice]

    def __len__(self) -> int:
        return len(self._lista())


class Traduzidos(dict):
    """Um dicionário de textos fixos ({código: texto em português}) que devolve cada texto no
    idioma da sessão."""

    def __getitem__(self, chave):
        return t(super().__getitem__(chave))

    def get(self, chave, padrao=None):
        return self[chave] if chave in self else padrao
