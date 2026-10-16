"""Explicação do modelo com SHAP (PROJETO.md, seção 6.7).

Usa o TreeSHAP do próprio LightGBM (`predict(..., pred_contrib=True)`): é o mesmo algoritmo do
TreeExplainer da biblioteca shap, sem acrescentar uma dependência pesada ao deploy.

Com 37 variáveis, muitas parecidas (8 taxas históricas, por exemplo), a contribuição de cada uma
confunde. Por isso as contribuições são somadas por TEMA (GRUPOS), e cada tema vira uma frase
simples, em pontos percentuais: "Histórico da rota neste horário: +8,2 p.p.".

- global: a contribuição média, em valor absoluto, de cada tema e de cada variável, numa amostra
  do teste (models/explicacao_global.json);
- local: os temas que mais aumentam e mais diminuem o risco de um voo (`explicar_voo`).

Uso: python -m fdr.model.explain
"""

import json

import duckdb
import numpy as np
import pandas as pd

from fdr.config import ARQUIVO_METRICAS, PASTA_MODELOS, SEMENTE, WAREHOUSE
from fdr.model import train
from fdr.model.registry import ModeloAtraso

ARQUIVO_EXPLICACAO = "explicacao_global.json"
AMOSTRA_GLOBAL = 20_000

# Tema de cada variável, na ordem em que aparecem para o usuário.
GRUPOS = {
    "Histórico da rota neste horário": [c for c in train.HISTORICO if "_rota_hora_" in c],
    "Histórico da companhia": [c for c in train.HISTORICO if "_cia_" in c and "ano" not in c],
    "Histórico do aeroporto de origem": [
        c for c in train.HISTORICO if "_origem_" in c and "ano" not in c
    ],
    "Nível geral de atrasos no país": [c for c in train.HISTORICO if "_global_" in c],
    "Época do ano": [
        *(c for c in train.HISTORICO if c.endswith("_ano_anterior")),
        "mes_do_ano",
        "ferias_escolares",
    ],
    "Horário do voo": ["hora_prevista_local"],
    "Dia da semana": ["dia_semana"],
    "Feriados": ["feriado", "vespera_feriado", "pos_feriado"],
    "Movimento no aeroporto": ["partidas_tipicas_origem_hora", "partidas_cia_antes_tipicas"],
    "Rota e duração do voo": ["destino", "distancia_km", "duracao_tipica_min", "folga_tipica_min"],
    "Companhia": ["cia"],
    "Aeroporto de origem": ["origem"],
}


def _sigmoide(x: np.ndarray) -> np.ndarray:
    return 1 / (1 + np.exp(-x))


def contribuicoes(modelo: ModeloAtraso, dados: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    """SHAP de cada variável (em log-odds) e o valor de partida (a média do modelo)."""
    brutas = modelo.booster.predict(train.matriz(modelo.preparar(dados)), pred_contrib=True)
    return brutas[:, :-1], brutas[:, -1]


def agrupar(shap: np.ndarray) -> pd.DataFrame:
    """Soma as contribuições das variáveis de cada tema (ainda em log-odds)."""
    indices = {v: i for i, v in enumerate(train.VARIAVEIS)}
    return pd.DataFrame(
        {
            tema: shap[:, [indices[v] for v in variaveis]].sum(axis=1)
            for tema, variaveis in GRUPOS.items()
        }
    )


def efeito_em_pontos(shap_grupos: pd.DataFrame, logito_total: np.ndarray) -> pd.DataFrame:
    """Quanto a probabilidade cai se o tema for retirado, em pontos percentuais: a diferença entre
    a previsão completa e a previsão sem a contribuição daquele tema."""
    completa = _sigmoide(logito_total)[:, None]
    sem_tema = _sigmoide(logito_total[:, None] - shap_grupos.to_numpy())
    return pd.DataFrame((completa - sem_tema) * 100, columns=shap_grupos.columns)


def explicar_voos(modelo: ModeloAtraso, dados: pd.DataFrame, fatores: int = 3) -> list[dict]:
    """Para cada voo: a probabilidade e os temas que mais aumentam e mais diminuem o risco."""
    shap, partida = contribuicoes(modelo, dados)
    logito = shap.sum(axis=1) + partida
    pontos = efeito_em_pontos(agrupar(shap), logito)
    explicacoes = []
    for i, linha in pontos.iterrows():
        ordenada = linha.sort_values()
        explicacoes.append(
            {
                "probabilidade": float(_sigmoide(logito[i])),
                "media_do_modelo": float(_sigmoide(partida[i])),
                "aumentam": [
                    {"tema": t, "pontos": round(float(v), 1)}
                    for t, v in ordenada[::-1].items()
                    if v > 0.05
                ][:fatores],
                "diminuem": [
                    {"tema": t, "pontos": round(float(v), 1)}
                    for t, v in ordenada.items()
                    if v < -0.05
                ][:fatores],
            }
        )
    return explicacoes


def frase(fator: dict) -> str:
    """Ex.: {"tema": "Horário do voo", "pontos": 8.2} -> "Horário do voo: +8,2 p.p."."""
    numero = f"{fator['pontos']:+.1f}".replace(".", ",")
    return f"{fator['tema']}: {numero} p.p."


def importancia_global(modelo: ModeloAtraso, dados: pd.DataFrame) -> dict:
    """Média do |SHAP| por tema (em log-odds e em pontos percentuais) e por variável."""
    shap, partida = contribuicoes(modelo, dados)
    logito = shap.sum(axis=1) + partida
    grupos = agrupar(shap)
    pontos = efeito_em_pontos(grupos, logito)
    por_tema = sorted(
        (
            {
                "tema": tema,
                "shap_medio_abs": float(grupos[tema].abs().mean()),
                "pontos_medios_abs": float(pontos[tema].abs().mean()),
            }
            for tema in GRUPOS
        ),
        key=lambda r: -r["shap_medio_abs"],
    )
    por_variavel = sorted(
        (
            {"variavel": v, "shap_medio_abs": float(np.abs(shap[:, i]).mean())}
            for i, v in enumerate(train.VARIAVEIS)
        ),
        key=lambda r: -r["shap_medio_abs"],
    )
    return {"voos": int(len(dados)), "por_tema": por_tema, "por_variavel": por_variavel}


def main() -> None:
    from fdr.model import figuras  # matplotlib só aqui: o app não precisa dele

    modelo = ModeloAtraso.carregar()
    inicio, fim = modelo.metadados["teste"]
    with duckdb.connect(str(WAREHOUSE), read_only=True) as con:
        dados = train.carregar(con)
    teste = train.no_periodo(dados, pd.Timestamp(inicio).date(), pd.Timestamp(fim).date())
    amostra = teste.sample(n=min(AMOSTRA_GLOBAL, len(teste)), random_state=SEMENTE)

    importancia = importancia_global(modelo, amostra.reset_index(drop=True))
    importancia["periodo"] = [inicio, fim]
    (PASTA_MODELOS / ARQUIVO_EXPLICACAO).write_text(
        json.dumps(importancia, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    metricas = json.loads(ARQUIVO_METRICAS.read_text(encoding="utf-8"))
    for caminho in figuras.gerar_todas(metricas, importancia):
        print(f"Gráfico: {caminho}")

    print(f"Temas que mais pesam ({importancia['voos']:,} voos do teste):")
    for item in sorted(importancia["por_tema"], key=lambda r: -r["pontos_medios_abs"]):
        print(f"    {item['tema']:<36} {item['pontos_medios_abs']:5.2f} p.p. em média")
    print("Três voos de exemplo (os de maior risco previsto da amostra):")
    p = modelo.prever(amostra)
    exemplos = amostra.iloc[np.argsort(-p)[:3]].reset_index(drop=True)
    for voo, explicacao in zip(exemplos.itertuples(), explicar_voos(modelo, exemplos), strict=True):
        print(
            f"  {voo.cia} {voo.origem}->{voo.destino} às {int(voo.hora_prevista_local)}h, "
            f"{voo.data_prevista:%d/%m/%Y}: {explicacao['probabilidade']:.0%} de chance de atraso"
        )
        for fator in explicacao["aumentam"] + explicacao["diminuem"]:
            print(f"      {frase(fator)}")
    print(f"Gravado: models/{ARQUIVO_EXPLICACAO}.")


if __name__ == "__main__":
    main()
