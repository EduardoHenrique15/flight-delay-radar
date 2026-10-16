"""Gráficos do modelo para o README e o docs/modelo.md, gerados a partir dos JSONs de models/.

Nenhum número é digitado: tudo vem de models/metrics.json e models/explicacao_global.json.
"""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from fdr.config import RAIZ  # noqa: E402

PASTA_IMAGENS = RAIZ / "docs" / "img"
AZUL = "#2a78d6"
CINZA = "#8a8984"
TEXTO = "#0b0b0b"
TEXTO_SECUNDARIO = "#52514e"
GRADE = "#e4e3df"
FUNDO = "#fcfcfb"
FONTE = "Fonte: ANAC, Voo Regular Ativo (VRA). Voos nacionais regulares realizados."


def _estilo(eixo, titulo: str, grade: str = "y") -> None:
    eixo.set_facecolor(FUNDO)
    eixo.set_title(titulo, loc="left", fontsize=11, color=TEXTO, pad=8)
    eixo.grid(axis=grade, color=GRADE, lw=0.8)
    eixo.set_axisbelow(True)
    for lado in ("top", "right", "left", "bottom"):
        eixo.spines[lado].set_visible(False)
    eixo.tick_params(length=0, colors=TEXTO_SECUNDARIO, labelsize=9)


def _salvar(figura, nome: str, pasta: Path, nota: str = "") -> Path:
    figura.patch.set_facecolor(FUNDO)
    figura.text(0.01, 0.01, f"{FONTE} {nota}".strip(), fontsize=8, color=TEXTO_SECUNDARIO)
    figura.tight_layout(rect=(0, 0.04, 1, 1))
    pasta.mkdir(parents=True, exist_ok=True)
    caminho = pasta / nome
    figura.savefig(caminho, dpi=150, facecolor=FUNDO)
    plt.close(figura)
    return caminho


def validacao_por_janela(metricas: dict, pasta: Path = PASTA_IMAGENS) -> Path:
    """PR-AUC de cada modelo em cada janela da validação e no teste."""
    cortes = metricas["validacao_modelos"]["validacao_cruzada"]
    rotulos = [f"{c['periodo'][0][5:7]}/{c['periodo'][0][2:4]}" for c in cortes["baseline"]]
    teste_final = metricas["modelo_final"]["teste"]
    teste_base = metricas["baseline"]["teste"]
    series = {
        "Baseline (taxa histórica)": ([c["pr_auc"] for c in cortes["baseline"]], teste_base, CINZA),
        "LightGBM": ([c["pr_auc"] for c in cortes["lightgbm"]], teste_final, AZUL),
    }
    figura, eixo = plt.subplots(figsize=(10, 4.2))
    posicoes = list(range(len(rotulos) + 1))
    for nome, (valores, teste, cor) in series.items():
        eixo.plot(
            posicoes, [*valores, teste["pr_auc"]], color=cor, lw=2, marker="o", ms=5, label=nome
        )
        eixo.text(
            posicoes[-1] + 0.08,
            teste["pr_auc"],
            f"{teste['pr_auc']:.3f}".replace(".", ","),
            color=cor,
            va="center",
            fontsize=9,
        )
    eixo.axvspan(posicoes[-1] - 0.4, posicoes[-1] + 0.4, color=GRADE, lw=0)
    eixo.set_xticks(posicoes, [*(f"validação\n{r}" for r in rotulos), "teste\n06 a 08/26"])
    eixo.set_ylim(bottom=0)
    eixo.legend(frameon=False, fontsize=9, loc="upper left")
    _estilo(eixo, "PR-AUC por janela de 3 meses (maior é melhor)")
    return _salvar(figura, "pr_auc_por_janela.png", pasta, "Cada janela começa no mês indicado.")


def calibracao_teste(metricas: dict, pasta: Path = PASTA_IMAGENS) -> Path:
    """Probabilidade prevista x taxa real no teste, por faixa de 10 p.p."""
    figura, eixo = plt.subplots(figsize=(6.2, 5.4))
    eixo.plot([0, 0.7], [0, 0.7], color=GRADE, lw=1.5)
    for nome, curva, cor in (
        ("Baseline", metricas["baseline"]["teste"]["curva_calibracao"], CINZA),
        ("LightGBM", metricas["modelo_final"]["teste"]["curva_calibracao"], AZUL),
    ):
        pontos = [f for f in curva if f["voos"] >= 100]
        eixo.plot(
            [f["prevista_media"] for f in pontos],
            [f["taxa_real"] for f in pontos],
            color=cor,
            lw=2,
            marker="o",
            ms=5,
            label=nome,
        )
    eixo.set_xlabel("probabilidade prevista", color=TEXTO_SECUNDARIO)
    eixo.set_ylabel("taxa real de atraso", color=TEXTO_SECUNDARIO)
    eixo.legend(frameon=False, fontsize=9, loc="upper left")
    _estilo(eixo, "Calibração no teste (sobre a diagonal = acerto)", grade="both")
    return _salvar(figura, "calibracao_teste.png", pasta, "Faixas com 100 voos ou mais.")


def temas_shap(importancia: dict, pasta: Path = PASTA_IMAGENS) -> Path:
    """Quanto cada tema muda a probabilidade, em média, no teste."""
    temas = sorted(importancia["por_tema"], key=lambda r: r["pontos_medios_abs"])
    figura, eixo = plt.subplots(figsize=(10, 5.2))
    eixo.barh(
        [t["tema"] for t in temas], [t["pontos_medios_abs"] for t in temas], color=AZUL, height=0.6
    )
    for i, t in enumerate(temas):
        eixo.text(
            t["pontos_medios_abs"] + 0.05,
            i,
            f"{t['pontos_medios_abs']:.1f}".replace(".", ","),
            va="center",
            fontsize=9,
            color=TEXTO_SECUNDARIO,
        )
    _estilo(eixo, "O que mais pesa na previsão: efeito médio de cada tema (p.p.)", grade="x")
    nota = f"SHAP do LightGBM em {importancia['voos']:,} voos do teste.".replace(",", ".")
    return _salvar(figura, "shap_temas.png", pasta, nota)


def gerar_todas(metricas: dict, importancia: dict, pasta: Path = PASTA_IMAGENS) -> list[Path]:
    return [
        validacao_por_janela(metricas, pasta),
        calibracao_teste(metricas, pasta),
        temas_shap(importancia, pasta),
    ]
