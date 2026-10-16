"""Modelos com aprendizado: regressão logística e LightGBM, avaliados no tempo (PROJETO.md, 6.4
e 6.5).

Esta etapa usa só os meses de treino e validação. O teste fica intocado até a escolha estar
travada (Fase 3, parte 2). O que ela faz, em ordem:

1. Ajusta os hiperparâmetros do LightGBM (num_leaves, min_child_samples, learning_rate) na
   validação principal, o último corte antes do teste. O número de árvores sai da parada
   antecipada num mês reservado do fim do treino, e não da validação, para a métrica da
   validação continuar limpa.
2. Treina baseline, regressão logística e LightGBM em cada um dos cortes da validação cruzada
   no tempo e mede PR-AUC, ROC-AUC, Brier e ECE em cada janela de validação.
3. Escolhe o modelo pela regra de 1 erro-padrão: o mais simples (baseline, depois logística,
   depois LightGBM) cuja PR-AUC média fique a menos de 1 erro-padrão da melhor. O erro-padrão é
   o da diferença entre os dois modelos, corte a corte: os cortes têm taxas de atraso muito
   diferentes (dezembro pesa), e a comparação pareada tira essa variação comum.
4. Compara a probabilidade crua com a calibrada (isotônica e Platt) fora do tempo: o calibrador
   de cada corte é ajustado nas validações dos cortes anteriores e avaliado no corte seguinte.

O resultado vai para models/metrics.json, na seção "validacao_modelos".

Uso: python -m fdr.model.train
"""

import json
import time
from dataclasses import dataclass
from datetime import date

import duckdb
import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline, make_pipeline
from sklearn.preprocessing import FunctionTransformer, OneHotEncoder, StandardScaler

from fdr.config import ARQUIVO_METRICAS, INICIO_TREINO, SEMENTE, WAREHOUSE
from fdr.features.build import ALVO, JANELAS_MESES, TABELA
from fdr.model import baseline
from fdr.model.evaluate import ece, metricas
from fdr.model.splits import Divisao, definir_divisao

# Variáveis do modelo (PROJETO.md, seção 6.2). Todas conhecidas antes do voo.
CATEGORICAS = ("cia", "origem", "destino")
CALENDARIO = ("hora_prevista_local", "dia_semana", "mes_do_ano")
BINARIAS = ("feriado", "vespera_feriado", "pos_feriado", "ferias_escolares")
CONTINUAS = ("duracao_prevista_min", "distancia_km", "partidas_programadas_origem_hora")
HISTORICO = tuple(
    f"{tipo}_{nivel}_{j}m"
    for nivel in baseline.NIVEIS
    for j in JANELAS_MESES
    for tipo in ("taxa", "voos")
)
VARIAVEIS = CATEGORICAS + CALENDARIO + BINARIAS + CONTINUAS + HISTORICO

# Ordem de simplicidade para a regra de 1 erro-padrão.
MODELOS = ("baseline", "logistica", "lightgbm")

# Regressão logística: com poucas dezenas de variáveis, 600 mil voos bastam para estimar os
# coeficientes, e a amostra mantém o treino leve na memória.
AMOSTRA_MAX_LOGISTICA = 600_000
MIN_FREQUENCIA_CATEGORIA = 200  # categorias mais raras viram "outras" no one-hot

# LightGBM: poucos hiperparâmetros, como pede a seção 6.5.
GRADE_LIGHTGBM = tuple(
    {"num_leaves": folhas, "min_child_samples": minimo, "learning_rate": taxa}
    for folhas in (31, 127)
    for minimo in (100, 1000)
    for taxa in (0.05, 0.1)
)
PARAMETROS_FIXOS = {
    "objective": "binary",
    "metric": "average_precision",
    "feature_fraction": 0.8,
    "bagging_fraction": 0.8,
    "bagging_freq": 1,
    "seed": SEMENTE,
    "deterministic": True,
    "force_row_wise": True,
    "verbosity": -1,
}
MAX_ARVORES = 3000
PACIENCIA = 50  # rodadas sem melhora na parada antecipada

CALIBRACOES = ("crua", "isotonica", "platt")
EMPATE_BRIER = 1e-4  # diferenças menores que isso no Brier são empate; desempata o ECE


@dataclass
class Previsoes:
    """Previsões de um modelo numa janela de validação."""

    y: np.ndarray
    p: np.ndarray


def meses_disponiveis(con: duckdb.DuckDBPyConnection) -> list[date]:
    return [m for (m,) in con.execute(f"select distinct mes from {TABELA} order by 1").fetchall()]


def carregar(con: duckdb.DuckDBPyConnection, antes_de: date | None = None) -> pd.DataFrame:
    """Lê a tabela de variáveis do início do treino até antes de `antes_de`, em precisão simples."""
    numericas = [c for c in VARIAVEIS if c not in CATEGORICAS]
    colunas = [
        "mes",
        "data_prevista",
        f"cast({ALVO} as tinyint) as {ALVO}",
        *CATEGORICAS,
        *(f"cast({c} as float) as {c}" for c in numericas),
    ]
    consulta = f"select {', '.join(colunas)} from {TABELA} where mes >= ? and mes < ?"
    dados = con.execute(consulta, [date(*INICIO_TREINO, 1), antes_de or date.max]).df()
    for coluna in CATEGORICAS:
        dados[coluna] = dados[coluna].astype("category")
    return dados


def no_periodo(dados: pd.DataFrame, inicio: date, fim: date) -> pd.DataFrame:
    meses = dados["mes"]
    return dados[(meses >= pd.Timestamp(inicio)) & (meses <= pd.Timestamp(fim))]


def matriz(dados: pd.DataFrame, linhas: np.ndarray | None = None) -> np.ndarray:
    """Variáveis em float32 para o LightGBM. Categorias viram o código (sem categoria: NaN).

    `linhas` (máscara booleana) seleciona os voos coluna a coluna, sem copiar o DataFrame. Montar
    a matriz aqui também evita a cópia em float64 que o LightGBM faria a partir do DataFrame.
    """
    if linhas is None:
        linhas = np.ones(len(dados), dtype=bool)
    saida = np.empty((int(linhas.sum()), len(VARIAVEIS)), dtype=np.float32)
    for i, coluna in enumerate(VARIAVEIS):
        if coluna in CATEGORICAS:
            codigos = dados[coluna].cat.codes.to_numpy()[linhas].astype(np.float32)
            codigos[codigos < 0] = np.nan
            saida[:, i] = codigos
        else:
            saida[:, i] = dados[coluna].to_numpy(dtype=np.float32, na_value=np.nan)[linhas]
    return saida


def treinar_lightgbm(
    dados: pd.DataFrame,
    treino: tuple[date, date],
    parametros: dict,
    max_arvores: int = MAX_ARVORES,
) -> lgb.Booster:
    """Treina nos meses de treino menos o último, que fica reservado para a parada antecipada."""
    meses = dados["mes"].to_numpy()
    inicio, ultimo = np.datetime64(treino[0]), np.datetime64(treino[1])
    ajuste = (meses >= inicio) & (meses < ultimo)
    parada = meses == ultimo
    alvo = dados[ALVO].to_numpy()
    base_ajuste = lgb.Dataset(
        matriz(dados, ajuste),
        label=alvo[ajuste],
        feature_name=list(VARIAVEIS),
        categorical_feature=[VARIAVEIS.index(c) for c in CATEGORICAS],
    )
    base_parada = lgb.Dataset(matriz(dados, parada), label=alvo[parada], reference=base_ajuste)
    return lgb.train(
        {**PARAMETROS_FIXOS, **parametros},
        base_ajuste,
        num_boost_round=max_arvores,
        valid_sets=[base_parada],
        callbacks=[lgb.early_stopping(PACIENCIA, verbose=False)],
    )


def prever_lightgbm(modelo: lgb.Booster, dados: pd.DataFrame) -> np.ndarray:
    return modelo.predict(matriz(dados), num_iteration=modelo.best_iteration)


def criar_logistica() -> Pipeline:
    """One-hot nas categorias e no calendário; números padronizados (PROJETO.md, seção 6.5)."""
    contagens = [c for c in HISTORICO if c.startswith("voos_")]
    contagens.append("partidas_programadas_origem_hora")
    taxas = [c for c in HISTORICO if c.startswith("taxa_")]
    preparo = ColumnTransformer(
        [
            (
                "categorias",
                OneHotEncoder(
                    min_frequency=MIN_FREQUENCIA_CATEGORIA,
                    handle_unknown="infrequent_if_exist",
                ),
                [*CATEGORICAS, *CALENDARIO],
            ),
            ("binarias", SimpleImputer(strategy="most_frequent"), list(BINARIAS)),
            (
                "contagens",
                make_pipeline(
                    SimpleImputer(strategy="constant", fill_value=0),
                    FunctionTransformer(np.log1p),
                    StandardScaler(),
                ),
                contagens,
            ),
            # Sem histórico, a taxa fica vazia: entra a mediana e um indicador de ausência.
            (
                "taxas",
                make_pipeline(
                    SimpleImputer(strategy="median", add_indicator=True), StandardScaler()
                ),
                taxas,
            ),
            (
                "voo",
                make_pipeline(SimpleImputer(strategy="median"), StandardScaler()),
                ["duracao_prevista_min", "distancia_km"],
            ),
        ]
    )
    return make_pipeline(preparo, LogisticRegression(C=1.0, max_iter=2000))


def treinar_logistica(
    dados: pd.DataFrame, treino: tuple[date, date], amostra_max: int = AMOSTRA_MAX_LOGISTICA
) -> Pipeline:
    meses = dados["mes"].to_numpy()
    linhas = np.flatnonzero(
        (meses >= np.datetime64(treino[0])) & (meses <= np.datetime64(treino[1]))
    )
    if len(linhas) > amostra_max:
        linhas = np.sort(np.random.default_rng(SEMENTE).choice(linhas, amostra_max, replace=False))
    janela = dados.iloc[linhas]
    return criar_logistica().fit(janela[list(VARIAVEIS)], janela[ALVO].to_numpy())


def prever_logistica(modelo: Pipeline, dados: pd.DataFrame) -> np.ndarray:
    return modelo.predict_proba(dados[list(VARIAVEIS)])[:, 1]


def _logito(p: np.ndarray) -> np.ndarray:
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return np.log(p / (1 - p)).reshape(-1, 1)


def ajustar_calibrador(metodo: str, y: np.ndarray, p: np.ndarray):
    """Devolve uma função que leva a probabilidade crua à calibrada."""
    if metodo == "crua":
        return lambda q: q
    if metodo == "isotonica":
        iso = IsotonicRegression(y_min=0, y_max=1, out_of_bounds="clip").fit(p, y)
        return iso.predict
    platt = LogisticRegression().fit(_logito(p), y)
    return lambda q: platt.predict_proba(_logito(q))[:, 1]


def comparar_calibracao(previsoes: list[Previsoes]) -> dict:
    """Calibração fora do tempo: no corte k, o calibrador aprende com os cortes 1 a k-1."""
    resultados = {metodo: [] for metodo in CALIBRACOES}
    for k in range(1, len(previsoes)):
        y_ajuste = np.concatenate([v.y for v in previsoes[:k]])
        p_ajuste = np.concatenate([v.p for v in previsoes[:k]])
        alvo = previsoes[k]
        for metodo in CALIBRACOES:
            q = ajustar_calibrador(metodo, y_ajuste, p_ajuste)(alvo.p)
            resultados[metodo].append(
                _arredondar(
                    {
                        "brier": float(np.mean((q - alvo.y) ** 2)),
                        "ece": ece(alvo.y.astype(float), q),
                        "taxa_prevista": float(q.mean()),
                    }
                )
            )
    medias = {
        metodo: {nome: float(np.mean([r[nome] for r in lista])) for nome in ("brier", "ece")}
        for metodo, lista in resultados.items()
    }
    melhor_brier = min(m["brier"] for m in medias.values())
    empatados = [m for m in CALIBRACOES if medias[m]["brier"] - melhor_brier < EMPATE_BRIER]
    escolhida = min(empatados, key=lambda m: medias[m]["ece"])
    return {"por_corte": resultados, "media": medias, "escolhida": escolhida}


def regra_um_erro_padrao(pr_auc: dict[str, list[float]], ordem=MODELOS) -> dict:
    """O mais simples cuja PR-AUC média fica a menos de 1 erro-padrão (pareado) da melhor."""
    medias = {m: float(np.mean(v)) for m, v in pr_auc.items()}
    melhor = max(medias, key=medias.get)
    candidatos = {}
    for modelo in ordem:
        diferencas = np.array(pr_auc[melhor]) - np.array(pr_auc[modelo])
        erro = float(np.std(diferencas, ddof=1) / np.sqrt(len(diferencas)))
        candidatos[modelo] = _arredondar(
            {
                "pr_auc_medio": medias[modelo],
                "diferenca_para_melhor": float(diferencas.mean()),
                "erro_padrao_diferenca": erro,
                "dentro_de_1_erro_padrao": bool(diferencas.mean() <= erro),
            }
        )
    escolhido = next(m for m in ordem if candidatos[m]["dentro_de_1_erro_padrao"])
    return {"melhor": melhor, "escolhido": escolhido, "candidatos": candidatos}


def _arredondar(valores: dict) -> dict:
    return {k: round(v, 6) if isinstance(v, float) else v for k, v in valores.items()}


def validar(
    dados: pd.DataFrame,
    divisao: Divisao,
    janela_baseline: int = 12,
    grade: tuple[dict, ...] = GRADE_LIGHTGBM,
    avisar=print,
) -> dict:
    """Busca de hiperparâmetros, validação cruzada no tempo, escolha e calibração."""
    principal = divisao.validacao_principal
    validacao_principal = no_periodo(dados, *principal.validacao)
    y_principal = validacao_principal[ALVO].to_numpy()

    avisar(f"Busca de hiperparâmetros do LightGBM ({len(grade)} combinações)")
    busca = []
    for parametros in grade:
        inicio = time.perf_counter()
        modelo = treinar_lightgbm(dados, principal.treino, parametros)
        pr_auc = metricas(y_principal, prever_lightgbm(modelo, validacao_principal))["pr_auc"]
        busca.append({**parametros, "arvores": modelo.best_iteration, "pr_auc": pr_auc})
        avisar(
            f"    {parametros} -> {modelo.best_iteration} árvores, PR-AUC {pr_auc:.4f}"
            f" ({time.perf_counter() - inicio:.0f} s)"
        )
    melhor_busca = max(busca, key=lambda r: r["pr_auc"])
    parametros = {k: melhor_busca[k] for k in grade[0]}

    por_modelo = {m: [] for m in MODELOS}
    previsoes = {m: [] for m in MODELOS}
    arvores = []
    for numero, corte in enumerate(divisao.cortes, start=1):
        avisar(f"Corte {numero}/{len(divisao.cortes)}: validação {corte.validacao[0]:%m/%Y}")
        validacao = no_periodo(dados, *corte.validacao)
        y = validacao[ALVO].to_numpy()
        lightgbm = treinar_lightgbm(dados, corte.treino, parametros)
        arvores.append(lightgbm.best_iteration)
        p_modelo = {
            "baseline": baseline.prever(validacao, janela_baseline)[0],
            "logistica": prever_logistica(treinar_logistica(dados, corte.treino), validacao),
            "lightgbm": prever_lightgbm(lightgbm, validacao),
        }
        for modelo, p in p_modelo.items():
            previsoes[modelo].append(Previsoes(y, p))
            por_modelo[modelo].append(
                {
                    "periodo": [corte.validacao[0].isoformat(), corte.validacao[1].isoformat()],
                    **_arredondar(metricas(y, p)),
                }
            )
            avisar(f"    {modelo:<10} PR-AUC {por_modelo[modelo][-1]['pr_auc']:.4f}")

    resumo = {
        modelo: {
            f"{nome}_medio": round(float(np.mean([c[nome] for c in cortes])), 6)
            for nome in ("pr_auc", "roc_auc", "brier", "ece")
        }
        for modelo, cortes in por_modelo.items()
    }
    escolha = regra_um_erro_padrao({m: [c["pr_auc"] for c in v] for m, v in por_modelo.items()})
    calibracao = {m: comparar_calibracao(previsoes[m]) for m in ("logistica", "lightgbm")}
    return {
        "variaveis": list(VARIAVEIS),
        "janela_baseline": f"{janela_baseline}m",
        "logistica": {
            "amostra_max": AMOSTRA_MAX_LOGISTICA,
            "min_frequencia_categoria": MIN_FREQUENCIA_CATEGORIA,
        },
        "lightgbm": {
            "busca": {
                "corte": [d.isoformat() for d in principal.validacao],
                "resultados": [_arredondar(r) for r in busca],
            },
            "parametros": parametros,
            "arvores_por_corte": arvores,
        },
        "validacao_cruzada": por_modelo,
        "resumo": resumo,
        "escolha": escolha,
        "calibracao": calibracao,
    }


def janela_do_baseline() -> int:
    """A janela que o baseline escolheu na validação (models/metrics.json); 12 meses se faltar."""
    if ARQUIVO_METRICAS.exists():
        metricas_salvas = json.loads(ARQUIVO_METRICAS.read_text(encoding="utf-8"))
        escolhida = metricas_salvas.get("baseline", {}).get("janela_escolhida")
        if escolhida:
            return int(escolhida.rstrip("m"))
    return 12


def main() -> None:
    with duckdb.connect(str(WAREHOUSE), read_only=True) as con:
        divisao = definir_divisao(meses_disponiveis(con))
        # O teste nunca é lido aqui: só os meses até o fim da validação principal.
        dados = carregar(con, antes_de=divisao.teste[0])
    print(f"{len(dados):,} voos carregados ({len(VARIAVEIS)} variáveis), sem os meses do teste.")
    resultado = validar(dados, divisao, janela_do_baseline())
    baseline.salvar_metricas("validacao_modelos", resultado, divisao)

    print("\nMédia na validação cruzada no tempo:")
    for modelo, valores in resultado["resumo"].items():
        print(
            f"    {modelo:<10} PR-AUC {valores['pr_auc_medio']:.4f}"
            f"  ROC-AUC {valores['roc_auc_medio']:.4f}"
            f"  Brier {valores['brier_medio']:.4f}  ECE {valores['ece_medio']:.4f}"
        )
    escolha = resultado["escolha"]
    print(
        f"Melhor PR-AUC média: {escolha['melhor']}. Regra de 1 erro-padrão: {escolha['escolhido']}."
    )
    for modelo in ("logistica", "lightgbm"):
        calibracao = resultado["calibracao"][modelo]
        medias = ", ".join(
            f"{m} Brier {v['brier']:.4f} ECE {v['ece']:.4f}" for m, v in calibracao["media"].items()
        )
        print(f"Calibração {modelo}: {medias} -> {calibracao['escolhida']}")
    print(f"Resultados gravados em {ARQUIVO_METRICAS} (seção validacao_modelos).")


if __name__ == "__main__":
    main()
