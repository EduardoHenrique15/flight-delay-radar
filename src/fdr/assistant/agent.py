"""Pergunta em português -> SQL -> travas -> execução -> resposta.

Ordem de busca de uma resposta:
1. o cache de respostas já aprovadas (sem gastar cota);
2. o modelo de linguagem, se houver chave e cota; com UMA nova tentativa se o SQL for bloqueado
   pelas travas ou der erro, mandando o erro ao modelo;
3. sem chave ou sem cota: as respostas gravadas de demonstração (data/demo/assistant_cache.json).

O SQL é sempre revalidado e executado de novo no banco do app (somente leitura), inclusive o que
vem do cache: a tabela mostrada corresponde sempre aos dados atuais.
"""

from dataclasses import dataclass, field
from pathlib import Path

import duckdb
import pandas as pd

from fdr.assistant import guard, schema
from fdr.assistant.llm import Cache, ControleDeUso, ErroLLM, Gemini, ModeloLinguagem
from fdr.config import ARQUIVO_CACHE_ASSISTENTE, ARQUIVO_DEMO_ASSISTENTE, ARQUIVO_USO_ASSISTENTE


@dataclass
class Resposta:
    pergunta: str
    texto: str
    origem: str  # "cache", "modelo", "demonstracao", "recusa", "erro" ou "limite"
    sql: str | None = None
    tabela: pd.DataFrame | None = None
    explicacao: str = ""
    tentativas: int = 0
    avisos: list[str] = field(default_factory=list)


def resumir(tabela: pd.DataFrame) -> str:
    """Frase curta sobre o resultado, sem gastar outro pedido ao modelo."""
    if tabela.empty:
        return "A consulta não encontrou nenhum resultado."
    if tabela.shape == (1, 1):
        valor = tabela.iat[0, 0]
        if isinstance(valor, float):
            valor = f"{valor:.1%}" if 0 <= valor <= 1 else f"{valor:,.2f}".replace(",", "_")
            valor = valor.replace(".", ",").replace("_", ".")
        return f"Resposta: {valor}."
    return f"{len(tabela)} linha(s) encontrada(s)."


class Assistente:
    def __init__(
        self,
        banco: Path,
        llm: ModeloLinguagem | None,
        cache: Cache,
        demonstracao: Cache,
        uso: ControleDeUso,
    ):
        self.con: duckdb.DuckDBPyConnection = guard.conectar(banco)
        self.llm = llm
        self.cache = cache
        self.demonstracao = demonstracao
        self.uso = uso
        self.tabelas = set(schema.TABELAS)
        self._sistema: str | None = None

    @property
    def sistema(self) -> str:
        if self._sistema is None:
            self._sistema = schema.montar_prompt_sistema(self.con)
        return self._sistema

    def _executar(self, sql: str) -> tuple[str, pd.DataFrame]:
        aprovado = guard.validar(sql, self.tabelas)
        try:
            return aprovado, guard.executar(self.con, aprovado)
        except duckdb.Error as erro:
            raise guard.SQLBloqueado(f"Erro ao executar: {str(erro).splitlines()[0]}") from erro

    def _de_gravada(self, pergunta: str, gravada: dict, origem: str) -> Resposta:
        sql, tabela = self._executar(gravada["sql"])
        texto = f"{gravada['explicacao']} {resumir(tabela)}".strip()
        return Resposta(pergunta, texto, origem, sql, tabela, gravada["explicacao"])

    def responder(self, pergunta: str, usadas_na_sessao: int = 0) -> Resposta:
        pergunta = pergunta.strip()
        if not pergunta:
            return Resposta(pergunta, "Escreva uma pergunta sobre os voos.", "erro")

        gravada = self.cache.obter(pergunta)
        if gravada:
            return self._de_gravada(pergunta, gravada, "cache")

        bloqueio = "sem chave do Gemini" if self.llm is None else None
        bloqueio = bloqueio or self.uso.motivo_bloqueio(usadas_na_sessao)
        if bloqueio:
            exemplo = self.demonstracao.obter(pergunta)
            if exemplo:
                resposta = self._de_gravada(pergunta, exemplo, "demonstracao")
                resposta.avisos.append(f"Resposta gravada de demonstração ({bloqueio}).")
                return resposta
            sugestoes = "; ".join(self.demonstracao.perguntas()[:4])
            texto = f"O assistente está em modo de demonstração ({bloqueio})."
            if sugestoes:
                texto += f" Experimente uma das perguntas de exemplo: {sugestoes}."
            return Resposta(pergunta, texto, "limite")

        return self._perguntar_ao_modelo(pergunta)

    def _perguntar_ao_modelo(self, pergunta: str) -> Resposta:
        mensagem = f"Pergunta: {pergunta}"
        erro_anterior = None
        for tentativa in (1, 2):
            if erro_anterior:
                mensagem = (
                    f"Pergunta: {pergunta}\n\nO SQL anterior foi recusado: {erro_anterior}\n"
                    "Corrija e devolva um novo SQL."
                )
            try:
                self.uso.registrar()
                bruta = self.llm.gerar(self.sistema, mensagem)
            except ErroLLM as erro:
                texto = f"O assistente não conseguiu responder: {erro}"
                return Resposta(pergunta, texto, "erro", tentativas=tentativa)
            if not bruta["pode_responder"]:
                texto = bruta["explicacao"] or "Os dados do projeto não têm essa informação."
                return Resposta(pergunta, texto, "recusa", tentativas=tentativa)
            try:
                sql, tabela = self._executar(bruta["sql"])
            except guard.SQLBloqueado as erro:
                erro_anterior = str(erro)
                continue
            self.cache.guardar(pergunta, {"sql": sql, "explicacao": bruta["explicacao"]})
            texto = f"{bruta['explicacao']} {resumir(tabela)}".strip()
            return Resposta(
                pergunta, texto, "modelo", sql, tabela, bruta["explicacao"], tentativas=tentativa
            )
        return Resposta(
            pergunta,
            f"Não consegui montar uma consulta válida para essa pergunta ({erro_anterior}). "
            "Tente reformular.",
            "erro",
            tentativas=2,
        )


def criar_assistente(chave: str | None = None, banco: Path | None = None) -> Assistente:
    """O assistente do app: Gemini se houver chave; sem chave, só o modo de demonstração."""
    from fdr.config import BANCO_APP

    return Assistente(
        banco or BANCO_APP,
        Gemini(chave) if chave else None,
        Cache(ARQUIVO_CACHE_ASSISTENTE),
        Cache(ARQUIVO_DEMO_ASSISTENTE),
        ControleDeUso(ARQUIVO_USO_ASSISTENTE),
    )
