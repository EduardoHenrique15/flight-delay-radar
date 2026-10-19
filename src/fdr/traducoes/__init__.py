"""Traduções do app para o inglês: um módulo por página (e `comum` para as peças de
fdr.interface e fdr.painel), cada um com um dicionário TEXTOS {texto em português: em inglês}.
Os módulos são juntados aqui; uma chave repetida precisa ter a mesma tradução (teste)."""

import importlib
import pkgutil

MODULOS = [importlib.import_module(f"{__name__}.{m.name}") for m in pkgutil.iter_modules(__path__)]
TEXTOS: dict[str, str] = {}
for _modulo in MODULOS:
    TEXTOS.update(_modulo.TEXTOS)
