"""Avaliação do assistente (PROJETO.md, seção 8.4) com as perguntas de eval/questions.yaml.

Métrica principal: acerto por execução. O resultado do SQL gerado precisa trazer o mesmo
conteúdo do SQL de referência: o mesmo número de linhas e, para cada coluna da referência, uma
coluna do resultado gerado com os mesmos valores, sem considerar a ordem das linhas e com
tolerância numérica. Colunas a mais (o nome junto do código, por exemplo) não contam como erro.
Nas perguntas que os dados não respondem, o certo é recusar.

O Gemini só é chamado com a autorização do Eduardo, em lotes de 11 perguntas, um por dia (a
cota gratuita é de cerca de 20 pedidos por dia, e uma nova tentativa gasta mais um). Entre uma
pergunta e outra há uma pausa de 15 s, porque o plano gratuito também limita os pedidos por
minuto (o lote 1 levou um erro 429 na 11ª pergunta sem a pausa).

Uso:
    python -m fdr.assistant.eval --referencia      # só confere os SQLs de referência (sem LLM)
    python -m fdr.assistant.eval --lote 1          # perguntas 1 a 11 (precisa de GEMINI_API_KEY)
    python -m fdr.assistant.eval --lote 2          # perguntas 12 a 22
    python -m fdr.assistant.eval --lote 3          # perguntas 23 a 31
    python -m fdr.assistant.eval --lote 1 --refazer 11   # refaz só a 11 no último arquivo do lote 1
    python -m fdr.assistant.eval --demo            # grava as respostas de demonstração
"""

import argparse
import json
import os
import tempfile
import time
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from fdr.assistant import guard, schema
from fdr.assistant.agent import Assistente
from fdr.assistant.llm import Cache, ControleDeUso, Gemini, ModeloLinguagem
from fdr.config import ARQUIVO_DEMO_ASSISTENTE, BANCO_APP, RAIZ

ARQUIVO_PERGUNTAS = RAIZ / "eval" / "questions.yaml"
PASTA_RESULTADOS = RAIZ / "eval" / "results"
TAMANHO_LOTE = 11  # 3 lotes; com as novas tentativas, cada lote fica abaixo de ~20 pedidos
TOLERANCIA = 1e-4
PAUSA_S = 15.0  # no máximo 4 pedidos por minuto


def ler_perguntas(caminho: Path = ARQUIVO_PERGUNTAS) -> list[dict]:
    return yaml.safe_load(caminho.read_text(encoding="utf-8"))


def _coluna_normalizada(serie: pd.Series) -> list:
    """Valores ordenados e comparáveis: números arredondados, datas e textos como texto."""
    valores = []
    for valor in serie.tolist():
        if valor is None or (isinstance(valor, float) and np.isnan(valor)):
            valores.append("<vazio>")
        elif isinstance(valor, bool | np.bool_):
            valores.append(str(bool(valor)))
        elif isinstance(valor, int | float | np.integer | np.floating):
            valores.append(round(float(valor), 4))
        else:
            valores.append(
                str(pd.Timestamp(valor).date()) if hasattr(valor, "year") else str(valor)
            )
    return sorted(valores, key=lambda v: (isinstance(v, str), v))


def _iguais(a: list, b: list) -> bool:
    if len(a) != len(b):
        return False
    for x, y in zip(a, b, strict=True):
        if isinstance(x, float) and isinstance(y, float):
            if abs(x - y) > TOLERANCIA * max(1.0, abs(y)):
                return False
        elif x != y:
            return False
    return True


def mesmo_resultado(gerado: pd.DataFrame, referencia: pd.DataFrame) -> bool:
    """Cada coluna da referência precisa ter uma coluna igual (em valores) no resultado gerado."""
    if len(gerado) != len(referencia):
        return False
    candidatas = [_coluna_normalizada(gerado[c]) for c in gerado.columns]
    usadas: set[int] = set()
    for coluna in referencia.columns:
        alvo = _coluna_normalizada(referencia[coluna])
        achou = next(
            (i for i, c in enumerate(candidatas) if i not in usadas and _iguais(c, alvo)), None
        )
        if achou is None:
            return False
        usadas.add(achou)
    return True


def avaliar(
    assistente: Assistente, perguntas: list[dict], referencia_con, pausa_s: float = 0.0
) -> list[dict]:
    resultados = []
    for posicao, item in enumerate(perguntas):
        if posicao and pausa_s:
            time.sleep(pausa_s)
        inicio = time.perf_counter()
        resposta = assistente.responder(item["pergunta"])
        latencia = time.perf_counter() - inicio
        registro = {
            "id": item["id"],
            "categoria": item["categoria"],
            "pergunta": item["pergunta"],
            "origem": resposta.origem,
            "sql_gerado": resposta.sql,
            "explicacao": resposta.explicacao,
            "resposta": resposta.texto,
            "tentativas": resposta.tentativas,
            "latencia_s": round(latencia, 2),
        }
        if item.get("recusar"):
            registro["acerto"] = resposta.origem == "recusa"
        elif resposta.tabela is None:
            registro["acerto"] = False
        else:
            esperado = guard.executar(
                referencia_con, guard.validar(item["sql"], set(schema.TABELAS))
            )
            registro["acerto"] = mesmo_resultado(resposta.tabela, esperado)
        resultados.append(registro)
    return resultados


def resumo(resultados: list[dict]) -> dict:
    respondiveis = [r for r in resultados if r["categoria"] != "recusa"]
    recusas = [r for r in resultados if r["categoria"] == "recusa"]

    def fracao(lista, condicao):
        return round(sum(1 for r in lista if condicao(r)) / len(lista), 4) if lista else None

    return {
        "perguntas": len(resultados),
        "acerto_execucao": fracao(respondiveis, lambda r: r["acerto"]),
        "sql_valido": fracao(respondiveis, lambda r: r["sql_gerado"] is not None),
        "bloqueadas_ou_com_erro": fracao(respondiveis, lambda r: r["origem"] == "erro"),
        "recusa_correta": fracao(recusas, lambda r: r["acerto"]),
        "com_nova_tentativa": fracao(resultados, lambda r: r["tentativas"] == 2),
        "latencia_media_s": round(float(np.mean([r["latencia_s"] for r in resultados])), 2)
        if resultados
        else None,
        "por_categoria": {
            categoria: fracao(
                [r for r in resultados if r["categoria"] == categoria], lambda r: r["acerto"]
            )
            for categoria in sorted({r["categoria"] for r in resultados})
        },
    }


def substituir(saida: dict, refeitos: list[dict], data: str) -> dict:
    """Troca os resultados refeitos no arquivo do lote, recalcula o resumo e registra o que foi
    refeito e quando (as outras perguntas continuam com o resultado original)."""
    novos = {r["id"]: r for r in refeitos}
    resultados = [novos.get(r["id"], r) for r in saida["resultados"]]
    refeitas = saida.get("refeitas", []) + [{"id": i, "data": data} for i in novos]
    return {**saida, "resumo": resumo(resultados), "resultados": resultados, "refeitas": refeitas}


def assistente_para_avaliacao(llm: ModeloLinguagem, banco: Path, pasta: Path) -> Assistente:
    """Sem cache (cada pergunta vai ao modelo) e sem os limites do app (o lote é o limite)."""
    return Assistente(
        banco,
        llm,
        Cache(pasta / "cache.json"),
        Cache(pasta / "demo.json"),
        ControleDeUso(pasta / "uso.json", por_sessao=10_000, por_dia=10_000),
    )


def gravar_demo(pasta: Path = PASTA_RESULTADOS, destino: Path = ARQUIVO_DEMO_ASSISTENTE) -> int:
    """Respostas de demonstração: as perguntas marcadas com demo que o modelo acertou."""
    marcadas = {q["id"] for q in ler_perguntas() if q.get("demo")}
    demo = Cache(destino)
    gravadas = 0
    for arquivo in sorted(pasta.glob("*-lote*.json")):
        for r in json.loads(arquivo.read_text(encoding="utf-8"))["resultados"]:
            if r["id"] in marcadas and r["acerto"] and r["sql_gerado"]:
                demo.guardar(r["pergunta"], {"sql": r["sql_gerado"], "explicacao": r["explicacao"]})
                gravadas += 1
    return gravadas


def main() -> None:
    parser = argparse.ArgumentParser(description="Avaliação do assistente texto->SQL.")
    grupo = parser.add_mutually_exclusive_group(required=True)
    grupo.add_argument("--referencia", action="store_true", help="confere os SQLs de referência")
    grupo.add_argument("--lote", type=int, choices=[1, 2, 3], help="lote de 11 perguntas")
    grupo.add_argument("--demo", action="store_true", help="grava as respostas de demonstração")
    parser.add_argument(
        "--refazer", type=int, nargs="+", metavar="ID", help="com --lote: refaz só estas perguntas"
    )
    args = parser.parse_args()
    if args.refazer and not args.lote:
        parser.error("--refazer precisa de --lote")
    perguntas = ler_perguntas()
    con = guard.conectar(BANCO_APP)

    if args.referencia:
        for item in perguntas:
            if not item.get("recusar"):
                tabela = guard.executar(con, guard.validar(item["sql"], set(schema.TABELAS)))
                print(f"{item['id']:>3} {len(tabela):>4} linha(s)  {item['pergunta'][:70]}")
        return
    if args.demo:
        print(f"{gravar_demo()} respostas gravadas em {ARQUIVO_DEMO_ASSISTENTE.relative_to(RAIZ)}.")
        return

    chave = os.environ.get("GEMINI_API_KEY")
    if not chave:
        raise SystemExit("Defina GEMINI_API_KEY no terminal antes de rodar a avaliação.")
    lote = perguntas[(args.lote - 1) * TAMANHO_LOTE : args.lote * TAMANHO_LOTE]
    hoje = date.today().isoformat()
    anteriores = sorted(PASTA_RESULTADOS.glob(f"*-lote{args.lote}.json"))
    if args.refazer:
        if not anteriores:
            raise SystemExit(f"Nenhum resultado do lote {args.lote} para refazer.")
        lote = [q for q in lote if q["id"] in set(args.refazer)]
        if not lote:
            raise SystemExit(f"Nenhuma dessas perguntas está no lote {args.lote}.")
    llm = Gemini(chave)
    with tempfile.TemporaryDirectory() as pasta:
        assistente = assistente_para_avaliacao(llm, BANCO_APP, Path(pasta))
        resultados = avaliar(assistente, lote, con, pausa_s=PAUSA_S)
    if args.refazer:
        arquivo = anteriores[-1]
        anterior = json.loads(arquivo.read_text(encoding="utf-8"))
        if anterior["modelo"] != llm.modelo:
            raise SystemExit(f"O lote foi feito com {anterior['modelo']}, não com {llm.modelo}.")
        saida = substituir(anterior, resultados, hoje)
    else:
        arquivo = PASTA_RESULTADOS / f"{hoje}-lote{args.lote}.json"
        saida = {
            "data": hoje,
            "modelo": llm.modelo,
            "lote": args.lote,
            "resumo": resumo(resultados),
            "resultados": resultados,
        }
    PASTA_RESULTADOS.mkdir(parents=True, exist_ok=True)
    texto = json.dumps(saida, ensure_ascii=False, indent=2, default=str)
    arquivo.write_text(texto + "\n", encoding="utf-8")
    for r in resultados:
        situacao = "certo" if r["acerto"] else "ERRADO"
        print(f"{r['id']:>3} {situacao:<6} {r['origem']:<12} {r['pergunta'][:60]}")
    print(json.dumps(saida["resumo"], ensure_ascii=False, indent=2))
    print(f"Gravado: {arquivo.relative_to(RAIZ)}.")


if __name__ == "__main__":
    main()
