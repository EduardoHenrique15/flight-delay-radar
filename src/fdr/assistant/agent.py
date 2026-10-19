"""Pergunta em português -> SQL -> travas -> execução -> resposta.

Ordem de busca de uma resposta:
1. o cache de respostas já aprovadas (sem gastar cota);
2. o modelo de linguagem, se houver chave e cota; com UMA nova tentativa se o SQL for bloqueado
   pelas travas ou der erro, mandando o erro ao modelo;
3. sem chave ou sem cota: as respostas gravadas de demonstração (data/demo/assistant_cache.json).

O SQL é sempre revalidado e executado de novo no banco do app (somente leitura), inclusive o que
vem do cache: a tabela mostrada corresponde sempre aos dados atuais.

Idioma (`responder(..., idioma="en")`): as mensagens fixas saem em inglês (fdr.idioma), o modelo
explica em inglês e o cache guarda as respostas em inglês numa chave à parte ("[en] pergunta").
As respostas de demonstração são gravadas em português: em inglês, a pergunta de exemplo
traduzida acha a gravada pela pergunta original. Em português (o padrão), nada muda.
"""

import re
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

import duckdb
import pandas as pd

from fdr import idioma
from fdr.assistant import guard, schema
from fdr.assistant.llm import Cache, ControleDeUso, ErroLLM, Gemini, ModeloLinguagem
from fdr.config import ARQUIVO_CACHE_ASSISTENTE, ARQUIVO_DEMO_ASSISTENTE, ARQUIVO_USO_ASSISTENTE
from fdr.idioma import t

PEDIDO_EM_INGLES = "Escreva a explicação em inglês."
NUMERO = r"\d+"


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
        return t("A consulta não encontrou nenhum resultado.")
    if tabela.shape == (1, 1):
        valor = tabela.iat[0, 0]
        if isinstance(valor, float):
            valor = f"{valor:.1%}" if 0 <= valor <= 1 else f"{valor:,.2f}"
            if not idioma.ingles():
                valor = valor.replace(",", "_").replace(".", ",").replace("_", ".")
        return t("Resposta: {valor}.", valor=valor)
    return t("{linhas} linha(s) encontrada(s).", linhas=len(tabela))


def _traduzir_com_numeros(texto: str) -> str:
    """Um motivo de bloqueio ("limite de 3 perguntas por sessão") no idioma da sessão: a chave da
    tradução troca cada número por {0}, {1}..."""
    if not idioma.ingles():
        return texto
    numeros = re.findall(NUMERO, texto)
    contador = iter(range(len(numeros)))
    molde = re.sub(NUMERO, lambda _: f"{{{next(contador)}}}", texto)
    return t(molde).format(*numeros)


def _original_em_portugues(pergunta: str) -> str | None:
    """A pergunta em português de uma pergunta de exemplo traduzida (fdr.traducoes)."""
    from fdr.assistant.llm import normalizar
    from fdr.traducoes import TEXTOS

    alvo = normalizar(pergunta)
    return next((pt for pt, en in TEXTOS.items() if normalizar(en) == alvo), None)


@contextmanager
def _no_idioma(codigo: str):
    anterior = idioma.atual()
    idioma.definir(codigo)
    try:
        yield
    finally:
        idioma.definir(anterior)


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
        explicacao = gravada["explicacao"]
        if idioma.ingles() and origem == "demonstracao":
            from fdr.traducoes import TEXTOS  # as gravadas de demonstração estão em português

            explicacao = TEXTOS.get(explicacao, explicacao)
        texto = f"{explicacao} {resumir(tabela)}".strip()
        return Resposta(pergunta, texto, origem, sql, tabela, explicacao)

    def responder(self, pergunta: str, usadas_na_sessao: int = 0, idioma: str = "pt") -> Resposta:
        with _no_idioma(idioma):
            return self._responder(pergunta.strip(), usadas_na_sessao)

    def _chave_do_cache(self, pergunta: str) -> str:
        return f"[en] {pergunta}" if idioma.ingles() else pergunta

    def _demonstracao(self, pergunta: str) -> dict | None:
        exemplo = self.demonstracao.obter(pergunta)
        if exemplo is None and idioma.ingles():
            original = _original_em_portugues(pergunta)
            exemplo = self.demonstracao.obter(original) if original else None
        return exemplo

    def _responder(self, pergunta: str, usadas_na_sessao: int) -> Resposta:
        if not pergunta:
            return Resposta(pergunta, t("Escreva uma pergunta sobre os voos."), "erro")

        gravada = self.cache.obter(self._chave_do_cache(pergunta))
        if gravada:
            return self._de_gravada(pergunta, gravada, "cache")

        bloqueio = "sem chave do Gemini" if self.llm is None else None
        bloqueio = bloqueio or self.uso.motivo_bloqueio(usadas_na_sessao)
        if bloqueio:
            bloqueio = _traduzir_com_numeros(bloqueio)
            exemplo = self._demonstracao(pergunta)
            if exemplo:
                resposta = self._de_gravada(pergunta, exemplo, "demonstracao")
                resposta.avisos.append(
                    t("Resposta gravada de demonstração ({bloqueio}).", bloqueio=bloqueio)
                )
                return resposta
            perguntas = self.demonstracao.perguntas()[:4]
            if idioma.ingles():
                from fdr.traducoes import TEXTOS

                perguntas = [TEXTOS.get(p, p) for p in perguntas]
            sugestoes = "; ".join(perguntas)
            texto = t("O assistente está em modo de demonstração ({bloqueio}).", bloqueio=bloqueio)
            if sugestoes:
                texto += " " + t(
                    "Experimente uma das perguntas de exemplo: {sugestoes}.", sugestoes=sugestoes
                )
            return Resposta(pergunta, texto, "limite")

        return self._perguntar_ao_modelo(pergunta)

    def _perguntar_ao_modelo(self, pergunta: str) -> Resposta:
        # O pedido ao modelo é sempre em português; em inglês, só a explicação muda de idioma.
        pedido = f"\n\n{PEDIDO_EM_INGLES}" if idioma.ingles() else ""
        mensagem = f"Pergunta: {pergunta}{pedido}"
        erro_anterior = None
        for tentativa in (1, 2):
            if erro_anterior:
                mensagem = (
                    f"Pergunta: {pergunta}\n\nO SQL anterior foi recusado: {erro_anterior}\n"
                    f"Corrija e devolva um novo SQL.{pedido}"
                )
            try:
                self.uso.registrar()
                bruta = self.llm.gerar(self.sistema, mensagem)
            except ErroLLM as erro:
                texto = t("O assistente não conseguiu responder: {erro}", erro=erro)
                return Resposta(pergunta, texto, "erro", tentativas=tentativa)
            if not bruta["pode_responder"]:
                texto = bruta["explicacao"] or t("Os dados do projeto não têm essa informação.")
                return Resposta(pergunta, texto, "recusa", tentativas=tentativa)
            try:
                sql, tabela = self._executar(bruta["sql"])
            except guard.SQLBloqueado as erro:
                erro_anterior = str(erro)
                continue
            self.cache.guardar(
                self._chave_do_cache(pergunta), {"sql": sql, "explicacao": bruta["explicacao"]}
            )
            texto = f"{bruta['explicacao']} {resumir(tabela)}".strip()
            return Resposta(
                pergunta, texto, "modelo", sql, tabela, bruta["explicacao"], tentativas=tentativa
            )
        return Resposta(
            pergunta,
            t(
                "Não consegui montar uma consulta válida para essa pergunta ({erro}). "
                "Tente reformular.",
                erro=erro_anterior,
            ),
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
