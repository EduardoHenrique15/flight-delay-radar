"""Testes do apoio à atualização mensal: detecção de mês novo e corpo do pull request."""

import json
from datetime import date

from fdr.config import RAIZ
from fdr.monitoring import resumo


def test_ultimo_mes_baixado_le_os_nomes_do_vra(tmp_path):
    for nome in ("VRA_20261.csv", "VRA_20269.csv", "VRA_202610.csv", "_downloads.json", "x.csv"):
        (tmp_path / nome).write_text("", encoding="utf-8")
    assert resumo.ultimo_mes_baixado(tmp_path) == date(2026, 10, 1)
    assert resumo.ultimo_mes_baixado(tmp_path / "vazia") is None


def test_verificar_compara_com_o_manifest_do_app(tmp_path):
    raw, marts = tmp_path / "raw", tmp_path / "marts"
    raw.mkdir()
    marts.mkdir()
    (marts / "manifest.json").write_text(json.dumps({"ultimo_mes": "2026-08-01"}), "utf-8")
    (raw / "VRA_20268.csv").write_text("", encoding="utf-8")
    assert resumo.verificar(raw, marts) == {"novo": False, "desde": date(2026, 8, 1)}
    (raw / "VRA_20269.csv").write_text("", encoding="utf-8")
    assert resumo.verificar(raw, marts)["novo"]


def test_corpo_do_pr_com_os_meses_novos():
    historico = json.loads((RAIZ / "monitoring" / "history.json").read_text(encoding="utf-8"))
    simulados = historico["simulacao"]["meses"]
    historico["producao"]["meses"] = simulados[-2:]  # finge que os 2 últimos vieram da produção
    corpo = resumo.corpo_do_pr(historico, date.fromisoformat(simulados[-2]["mes"]))
    assert corpo.count("### ") == 1  # só o mês depois de `desde`
    assert "PR-AUC: modelo" in corpo and "PSI das variáveis importantes" in corpo
    assert "Nenhum mês novo" in resumo.corpo_do_pr(historico, date(2030, 1, 1))
