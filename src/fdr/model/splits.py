"""Divisão dos meses em treino, validação e teste, sempre no tempo (ADR 003).

Nunca se embaralha: o modelo é sempre avaliado em meses depois dos que viu no treino.
- teste: os últimos MESES_TESTE meses, usados uma única vez, no fim;
- validação cruzada no tempo (rolling origin): CORTES_VALIDACAO janelas de MESES_VALIDACAO meses,
  uma depois da outra, logo antes do teste. Em cada corte, o treino vai do início até
  MESES_INTERVALO meses antes da janela de validação (janela expansiva). O último corte é a
  validação principal.

O intervalo simula a defasagem dos rótulos: quando o mês P é publicado, o calendário já está em
P + 2, e o modelo nunca prevê o mês logo depois do último rótulo que viu. Com 1 mês de intervalo,
a primeira previsão de cada avaliação fica 2 meses depois do fim do treino, como na vida real.
O treino final, avaliado no teste, segue a mesma regra.
"""

from dataclasses import dataclass
from datetime import date

from fdr.config import (
    CORTES_VALIDACAO,
    INICIO_TREINO,
    MESES_INTERVALO,
    MESES_TESTE,
    MESES_VALIDACAO,
)

MIN_MESES_TREINO = 6


@dataclass(frozen=True)
class Corte:
    treino: tuple[date, date]
    validacao: tuple[date, date]


@dataclass(frozen=True)
class Divisao:
    cortes: tuple[Corte, ...]
    teste: tuple[date, date]
    treino_final: tuple[date, date]
    intervalo: int

    @property
    def validacao_principal(self) -> Corte:
        return self.cortes[-1]

    def para_json(self) -> dict:
        def texto(intervalo):
            return [d.isoformat() for d in intervalo]

        return {
            "intervalo_meses": self.intervalo,
            "cortes": [
                {"treino": texto(c.treino), "validacao": texto(c.validacao)} for c in self.cortes
            ],
            "treino_final": texto(self.treino_final),
            "teste": texto(self.teste),
        }


class DivisaoInvalidaError(ValueError):
    """Não há meses suficientes para treino, validação e teste."""


def definir_divisao(
    meses: list[date],
    inicio_treino: tuple[int, int] = INICIO_TREINO,
    meses_teste: int = MESES_TESTE,
    meses_validacao: int = MESES_VALIDACAO,
    cortes: int = CORTES_VALIDACAO,
    intervalo: int = MESES_INTERVALO,
) -> Divisao:
    """Monta a divisão a partir dos meses disponíveis (o primeiro dia de cada mês)."""
    inicio = date(*inicio_treino, 1)
    meses = sorted({m for m in meses if m >= inicio})
    teste = meses[-meses_teste:]
    resto = meses[:-meses_teste]

    lista = []
    for k in range(cortes, 0, -1):
        fim = len(resto) - (k - 1) * meses_validacao
        validacao = resto[fim - meses_validacao : fim]
        treino = resto[: max(fim - meses_validacao - intervalo, 0)]
        if len(validacao) == meses_validacao and len(treino) >= MIN_MESES_TREINO:
            lista.append(Corte((treino[0], treino[-1]), (validacao[0], validacao[-1])))
    treino_final = resto[: max(len(resto) - intervalo, 0)]
    if len(teste) < meses_teste or not lista or len(treino_final) < MIN_MESES_TREINO:
        raise DivisaoInvalidaError(
            f"Meses insuficientes a partir de {inicio}: {len(meses)} disponíveis."
        )
    return Divisao(
        tuple(lista), (teste[0], teste[-1]), (treino_final[0], treino_final[-1]), intervalo
    )
