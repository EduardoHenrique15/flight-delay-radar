"""Modelo de linguagem do assistente: o Gemini (SDK oficial google-genai) e um modelo falso para
os testes, mais o cache em disco e o controle de uso (cota de cerca de 20 pedidos por dia no
plano gratuito).

A chave vem de GEMINI_API_KEY (variável de ambiente, ou os secrets do Streamlit, que o app
repassa). Ela nunca é gravada nem impressa. O modelo pode ser trocado em GEMINI_MODEL.
"""

import json
import os
import re
import time
import unicodedata
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Protocol

# O gemini-2.5-flash não aceita mais contas novas (erro 404 em 17/10/2026).
MODELO_PADRAO = "gemini-3.8-flash"
# Servidor sobrecarregado (500/503): espera e tenta mais uma vez antes de desistir.
ERROS_PASSAGEIROS = {500, 503}
ESPERA_ERRO_PASSAGEIRO_S = 5.0
# Limite de pedidos por minuto (429): na avaliação, espera o tempo que o Google pede e tenta mais
# uma vez. O limite do dia não adianta esperar: só volta no dia seguinte.
ESPERA_LIMITE_POR_MINUTO_S = 60.0
ESPERA_MAXIMA_S = 120.0

# A resposta estruturada que o modelo precisa devolver (JSON).
ESQUEMA_RESPOSTA = {
    "type": "object",
    "properties": {
        "pode_responder": {"type": "boolean"},
        "sql": {"type": "string"},
        "explicacao": {"type": "string"},
    },
    "required": ["pode_responder", "sql", "explicacao"],
}


class ErroLLM(RuntimeError):
    """O modelo não respondeu ou respondeu fora do formato."""


class CotaEsgotada(ErroLLM):
    """429: o limite do plano gratuito acabou. `diaria` diz se foi o limite do dia (só volta no
    dia seguinte) ou o do minuto."""

    def __init__(self, mensagem: str, diaria: bool):
        super().__init__(mensagem)
        self.diaria = diaria


def _detalhes(erro) -> str:
    return json.dumps(getattr(erro, "details", None), default=str)


def cota_diaria(erro) -> bool:
    """O 429 do Google diz qual limite estourou (ex.: ...PerDayPerProjectPerModel)."""
    return "PerDay" in _detalhes(erro)


def espera_sugerida(erro) -> float:
    """O tempo que o Google pede para esperar (RetryInfo, ex.: "37s"), com um teto."""
    achado = re.search(r'"retryDelay":\s*"(\d+(?:\.\d+)?)s"', _detalhes(erro))
    espera = float(achado.group(1)) + 1 if achado else ESPERA_LIMITE_POR_MINUTO_S
    return min(espera, ESPERA_MAXIMA_S)


class ModeloLinguagem(Protocol):
    def gerar(self, sistema: str, mensagem: str) -> dict: ...


def normalizar(pergunta: str) -> str:
    """Chave do cache: minúsculas, sem acentos, sem pontuação nas pontas, espaços simples."""
    texto = unicodedata.normalize("NFKD", pergunta.lower())
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", texto).strip(" ?!.")


def _validar_resposta(bruta: dict) -> dict:
    if not isinstance(bruta, dict) or not set(ESQUEMA_RESPOSTA["required"]) <= set(bruta):
        raise ErroLLM("O modelo respondeu fora do formato combinado.")
    return {
        "pode_responder": bool(bruta["pode_responder"]),
        "sql": str(bruta["sql"]).strip(),
        "explicacao": str(bruta["explicacao"]).strip(),
    }


class Gemini:
    """Cliente do Gemini com resposta estruturada (JSON) e temperatura zero.

    `esperar_limite_por_minuto`: no 429 do limite por minuto, espera e tenta mais uma vez. Só a
    avaliação usa; no app, a pessoa não fica um minuto esperando a resposta."""

    def __init__(
        self, chave: str, modelo: str | None = None, esperar_limite_por_minuto: bool = False
    ):
        from google import genai  # importado só aqui: os testes não precisam do SDK

        self._cliente = genai.Client(api_key=chave)
        self.modelo = modelo or os.environ.get("GEMINI_MODEL") or MODELO_PADRAO
        self.esperar_limite_por_minuto = esperar_limite_por_minuto

    def gerar(self, sistema: str, mensagem: str) -> dict:
        from google.genai import errors, types

        config = types.GenerateContentConfig(
            system_instruction=sistema,
            temperature=0,
            response_mime_type="application/json",
            response_json_schema=ESQUEMA_RESPOSTA,
            # Sem ferramentas: desligar evita o aviso do SDK sobre chamada automática.
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        )
        for tentativa in (1, 2):
            try:
                resposta = self._cliente.models.generate_content(
                    model=self.modelo, contents=mensagem, config=config
                )
                break
            except errors.APIError as erro:
                if erro.code in ERROS_PASSAGEIROS and tentativa == 1:
                    time.sleep(ESPERA_ERRO_PASSAGEIRO_S)
                    continue
                if erro.code == 429:
                    diaria = cota_diaria(erro)
                    if not diaria and self.esperar_limite_por_minuto and tentativa == 1:
                        time.sleep(espera_sugerida(erro))
                        continue
                    limite = "do dia" if diaria else "por minuto"
                    raise CotaEsgotada(
                        f"O Gemini recusou o pedido (429): limite de pedidos {limite} do plano "
                        "gratuito.",
                        diaria,
                    ) from erro
                raise ErroLLM(f"O Gemini recusou o pedido ({erro.code}).") from erro
        try:
            return _validar_resposta(json.loads(resposta.text or ""))
        except json.JSONDecodeError as erro:
            raise ErroLLM("O Gemini respondeu algo que não é JSON.") from erro


@dataclass
class LLMFalso:
    """Modelo falso para os testes: devolve respostas predefinidas por pergunta, em ordem (para
    simular a nova tentativa), e conta as chamadas."""

    respostas: dict[str, list[dict]]
    chamadas: list[str] = field(default_factory=list)

    def gerar(self, sistema: str, mensagem: str) -> dict:
        pergunta = normalizar(mensagem.split("\n", 1)[0].removeprefix("Pergunta: "))
        self.chamadas.append(pergunta)
        fila = self.respostas.get(pergunta)
        if not fila:
            raise ErroLLM(f"Sem resposta preparada para: {pergunta}")
        return _validar_resposta(fila.pop(0) if len(fila) > 1 else fila[0])


class Cache:
    """Respostas já aprovadas (pergunta normalizada -> sql e explicação), num arquivo JSON."""

    def __init__(self, caminho: Path):
        self.caminho = caminho
        self._dados = json.loads(caminho.read_text(encoding="utf-8")) if caminho.exists() else {}

    def obter(self, pergunta: str) -> dict | None:
        return self._dados.get(normalizar(pergunta))

    def guardar(self, pergunta: str, resposta: dict) -> None:
        self._dados[normalizar(pergunta)] = {"pergunta": pergunta, **resposta}
        self.caminho.parent.mkdir(parents=True, exist_ok=True)
        self.caminho.write_text(
            json.dumps(self._dados, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

    def perguntas(self) -> list[str]:
        return [item["pergunta"] for item in self._dados.values()]


@dataclass
class ControleDeUso:
    """Limite de perguntas ao modelo por sessão e por dia (o dia fica gravado num arquivo)."""

    caminho: Path
    por_sessao: int = 3
    por_dia: int = 6

    def _usadas_hoje(self) -> int:
        if not self.caminho.exists():
            return 0
        registro = json.loads(self.caminho.read_text(encoding="utf-8"))
        return registro.get(date.today().isoformat(), 0)

    def motivo_bloqueio(self, usadas_na_sessao: int) -> str | None:
        if usadas_na_sessao >= self.por_sessao:
            return f"limite de {self.por_sessao} perguntas por sessão"
        if self._usadas_hoje() >= self.por_dia:
            return f"limite de {self.por_dia} perguntas por dia"
        return None

    def registrar(self) -> None:
        hoje = date.today().isoformat()
        self.caminho.parent.mkdir(parents=True, exist_ok=True)
        self.caminho.write_text(
            json.dumps({hoje: self._usadas_hoje() + 1}) + "\n", encoding="utf-8"
        )
