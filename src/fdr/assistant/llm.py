"""Modelo de linguagem do assistente: o Gemini (SDK oficial google-genai) e um modelo falso para
os testes, mais o cache em disco e o controle de uso (cota de cerca de 20 pedidos por dia no
plano gratuito; PROJETO.md, seção 8.3).

A chave vem de GEMINI_API_KEY (variável de ambiente, ou os secrets do Streamlit, que o app
repassa). Ela nunca é gravada nem impressa. O modelo pode ser trocado em GEMINI_MODEL.
"""

import json
import os
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Protocol

MODELO_PADRAO = "gemini-2.5-flash"

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
    """Cliente do Gemini com resposta estruturada (JSON) e temperatura zero."""

    def __init__(self, chave: str, modelo: str | None = None):
        from google import genai  # importado só aqui: os testes não precisam do SDK

        self._cliente = genai.Client(api_key=chave)
        self.modelo = modelo or os.environ.get("GEMINI_MODEL") or MODELO_PADRAO

    def gerar(self, sistema: str, mensagem: str) -> dict:
        from google.genai import errors, types

        try:
            resposta = self._cliente.models.generate_content(
                model=self.modelo,
                contents=mensagem,
                config=types.GenerateContentConfig(
                    system_instruction=sistema,
                    temperature=0,
                    response_mime_type="application/json",
                    response_json_schema=ESQUEMA_RESPOSTA,
                ),
            )
        except errors.APIError as erro:
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
