"""Apoio à atualização mensal automática (.github/workflows/monthly.yml).

- `verificar`: compara o último mês baixado em data/raw/vra/ com o último mês do app
  (data/marts/manifest.json) e escreve `novo=true|false` e `desde=AAAA-MM-01` (o último mês que o
  app já tinha). Sem mês novo, o workflow termina com sucesso sem fazer nada.
- `pr`: escreve, em Markdown, o corpo do pull request com os meses novos: voos, métricas do
  modelo e do baseline, PSI das variáveis importantes e a decisão de retreino.

Uso:
    python -m fdr.monitoring.resumo verificar
    python -m fdr.monitoring.resumo pr --desde 2026-08-01
"""

import argparse
import json
import re
from datetime import date
from pathlib import Path

from fdr.config import PASTA_MARTS, PASTA_RAW_VRA, RAIZ
from fdr.monitoring import drift
from fdr.painel import descrever_retreino, nome_mes

ARQUIVO_VRA = re.compile(r"^VRA_(\d{4})(\d{1,2})\.csv$", re.IGNORECASE)


def ultimo_mes_baixado(pasta: Path = PASTA_RAW_VRA) -> date | None:
    meses = []
    for arquivo in pasta.glob("*.csv"):
        encontrado = ARQUIVO_VRA.match(arquivo.name)
        if encontrado and 1 <= int(encontrado.group(2)) <= 12:
            meses.append(date(int(encontrado.group(1)), int(encontrado.group(2)), 1))
    return max(meses, default=None)


def ultimo_mes_do_app(pasta: Path = PASTA_MARTS) -> date:
    manifest = json.loads((pasta / "manifest.json").read_text(encoding="utf-8"))
    return date.fromisoformat(manifest["ultimo_mes"])


def verificar(pasta_raw: Path = PASTA_RAW_VRA, pasta_marts: Path = PASTA_MARTS) -> dict:
    baixado = ultimo_mes_baixado(pasta_raw)
    app = ultimo_mes_do_app(pasta_marts)
    return {"novo": baixado is not None and baixado > app, "desde": app}


def corpo_do_pr(historico: dict, desde: date) -> str:
    meses = [m for m in historico["producao"]["meses"] if date.fromisoformat(m["mes"]) > desde]
    linhas = [
        "Atualização mensal automática: dados novos da ANAC, monitoramento do modelo e marts do "
        "app. Revise e faça o merge; o Streamlit Cloud atualiza sozinho.",
        "",
    ]
    if not meses:
        linhas.append("Nenhum mês novo entrou no monitoramento.")
    for registro in meses:
        modelo, baseline = registro["modelo"], registro["baseline"]
        mes = nome_mes(date.fromisoformat(registro["mes"]))
        linhas += [
            f"### {mes}",
            "",
            f"- Voos avaliados: {registro['voos']:,}".replace(",", "."),
            f"- PR-AUC: modelo {modelo['pr_auc']:.3f}, baseline {baseline['pr_auc']:.3f} "
            f"(ganho {registro['ganho_pr_auc']:+.3f})",
            f"- Taxa de atraso: real {modelo['taxa_real']:.1%}, prevista "
            f"{modelo['taxa_prevista']:.1%}; ECE {modelo['ece'] * 100:.1f} p.p.",
        ]
        importantes = historico.get("variaveis_importantes", [])
        psi = ", ".join(
            f"{v} {registro['psi'][v]:.3f} ({drift.nivel(registro['psi'][v])})"
            for v in importantes
            if v in registro["psi"]
        )
        if psi:
            linhas.append(f"- PSI das variáveis importantes: {psi}")
        linhas += [f"- {descrever_retreino(registro['retreino'])}", ""]
    return "\n".join(linhas)


def main() -> None:
    parser = argparse.ArgumentParser(description="Apoio à atualização mensal.")
    comando = parser.add_subparsers(dest="comando", required=True)
    comando.add_parser("verificar", help="há mês novo baixado?")
    pr = comando.add_parser("pr", help="corpo do pull request")
    pr.add_argument("--desde", type=date.fromisoformat, required=True)
    args = parser.parse_args()
    if args.comando == "verificar":
        situacao = verificar()
        print(f"novo={'true' if situacao['novo'] else 'false'}")
        print(f"desde={situacao['desde'].isoformat()}")
    else:
        historico = json.loads((RAIZ / "monitoring" / "history.json").read_text(encoding="utf-8"))
        print(corpo_do_pr(historico, args.desde))


if __name__ == "__main__":
    main()
