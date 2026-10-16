"""Testes da carga bruta do VRA, com arquivos pequenos no mesmo formato dos reais."""

from datetime import date
from pathlib import Path

import duckdb
import pytest

from fdr.config import COLUNAS_VRA
from fdr.ingest.load_raw import (
    FormatoInvalidoError,
    carregar_arquivo,
    carregar_pasta,
    fora_da_janela,
    inspecionar,
    mes_do_arquivo,
)

VOO_REALIZADO = (
    "GLO", "1234", "0", "N", "SBRF", "SBGR",
    "2026-08-01 10:00:00", "2026-08-01 10:20:00.100000000",
    "2026-08-01 13:00:00", "2026-08-01 13:15:00", "REALIZADO", "N/A",
)  # fmt: skip
VOO_CANCELADO = (
    "AZU", "4321", "0", "N", "SBKP", "SBRF",
    "2026-08-02 23:50:00", "null", "2026-08-03 03:00:00", "null", "CANCELADO", "N/A",
)  # fmt: skip


def escrever_vra(
    pasta: Path,
    nome: str,
    voos: list[tuple[str, ...]],
    atualizado_em: str = "2026-10-07",
    cabecalho: tuple[str, ...] = COLUNAS_VRA,
) -> Path:
    """Grava um CSV como os da ANAC: BOM, CRLF, metadado na linha 1 e tudo entre aspas."""
    linhas = [f"Atualizado em: {atualizado_em}", ";".join(f'"{c}"' for c in cabecalho)]
    linhas += [";".join(f'"{v}"' for v in voo) for voo in voos]
    caminho = pasta / nome
    caminho.write_bytes(b"\xef\xbb\xbf" + "\r\n".join(linhas).encode("utf-8") + b"\r\n")
    return caminho


@pytest.fixture
def con():
    conexao = duckdb.connect()
    yield conexao
    conexao.close()


@pytest.mark.parametrize(
    ("nome", "esperado"),
    [
        ("VRA_20221.csv", (2022, 1)),
        ("VRA_20236.csv", (2023, 6)),
        ("VRA_202610.csv", (2026, 10)),
        ("VRA_202612.csv", (2026, 12)),
    ],
)
def test_mes_do_arquivo(nome, esperado):
    assert mes_do_arquivo(nome) == esperado


@pytest.mark.parametrize("nome", ["VRA_2026.csv", "VRA_202613.csv", "VRA_20260.csv", "dados.csv"])
def test_nome_fora_do_padrao_falha(nome):
    with pytest.raises(FormatoInvalidoError):
        mes_do_arquivo(nome)


def test_inspecionar_le_metadados(tmp_path):
    caminho = escrever_vra(tmp_path, "VRA_20268.csv", [VOO_REALIZADO, VOO_CANCELADO])
    info = inspecionar(caminho)
    assert (info.ano, info.mes) == (2026, 8)
    assert info.atualizado_em == date(2026, 10, 7)
    assert info.linhas == 2
    assert len(info.sha256) == 64


def test_cabecalho_diferente_falha(tmp_path):
    cabecalho = (*COLUNAS_VRA[:-1], "Justificativa")
    caminho = escrever_vra(tmp_path, "VRA_20268.csv", [VOO_REALIZADO], cabecalho=cabecalho)
    with pytest.raises(FormatoInvalidoError, match="cabeçalho"):
        inspecionar(caminho)


def test_sem_linha_de_metadado_falha(tmp_path):
    caminho = escrever_vra(tmp_path, "VRA_20268.csv", [VOO_REALIZADO])
    texto = caminho.read_bytes().decode("utf-8-sig").split("\r\n", 1)[1]
    caminho.write_bytes(b"\xef\xbb\xbf" + texto.encode("utf-8"))
    with pytest.raises(FormatoInvalidoError, match="Atualizado em"):
        inspecionar(caminho)


def test_sem_bom_falha(tmp_path):
    caminho = escrever_vra(tmp_path, "VRA_20268.csv", [VOO_REALIZADO])
    caminho.write_bytes(caminho.read_bytes()[3:])
    with pytest.raises(FormatoInvalidoError, match="BOM"):
        inspecionar(caminho)


def test_carga_preserva_valores_como_texto(con, tmp_path):
    caminho = escrever_vra(tmp_path, "VRA_20268.csv", [VOO_REALIZADO, VOO_CANCELADO])
    assert carregar_arquivo(con, caminho) == 2

    linha = con.execute(
        'select "Número Voo", "Partida Real", arquivo_origem '
        "from raw_vra where \"Situação Voo\" = 'REALIZADO'"
    ).fetchone()
    assert linha == ("1234", "2026-08-01 10:20:00.100000000", "VRA_20268.csv")
    cancelado = con.execute(
        'select "Partida Real" from raw_vra where "Situação Voo" = \'CANCELADO\''
    ).fetchone()
    assert cancelado == ("null",)


def test_carga_repetida_nao_duplica(con, tmp_path):
    caminho = escrever_vra(tmp_path, "VRA_20268.csv", [VOO_REALIZADO, VOO_CANCELADO])
    assert carregar_arquivo(con, caminho) == 2
    assert carregar_arquivo(con, caminho) is None
    assert carregar_arquivo(con, caminho, forcar=True) == 2
    assert con.execute("select count(*) from raw_vra").fetchone() == (2,)
    assert con.execute("select count(*) from raw_vra_cargas").fetchone() == (1,)


def test_arquivo_regerado_substitui_a_carga_anterior(con, tmp_path):
    caminho = escrever_vra(tmp_path, "VRA_20268.csv", [VOO_REALIZADO, VOO_CANCELADO])
    carregar_arquivo(con, caminho)

    escrever_vra(tmp_path, "VRA_20268.csv", [VOO_REALIZADO], atualizado_em="2026-11-07")
    assert carregar_arquivo(con, caminho) == 1
    assert con.execute("select count(*) from raw_vra").fetchone() == (1,)
    assert con.execute("select atualizado_em from raw_vra_cargas").fetchone() == (
        date(2026, 11, 7),
    )


def test_carregar_pasta_carrega_cada_mes_uma_vez(con, tmp_path):
    escrever_vra(tmp_path, "VRA_20267.csv", [VOO_REALIZADO])
    escrever_vra(tmp_path, "VRA_20268.csv", [VOO_REALIZADO, VOO_CANCELADO])
    escrever_vra(tmp_path, "VRA_202610.csv", [VOO_CANCELADO])

    resultado = carregar_pasta(con, tmp_path)
    assert list(resultado) == ["VRA_20267.csv", "VRA_20268.csv", "VRA_202610.csv"]
    assert list(resultado.values()) == [1, 2, 1]
    assert set(carregar_pasta(con, tmp_path).values()) == {None}
    assert con.execute("select count(*) from raw_vra").fetchone() == (4,)


def test_arquivos_antes_da_janela_sao_ignorados_e_removidos(con, tmp_path):
    """Um mês de 2021 esquecido na pasta não entra, e uma carga antiga dele sai do banco."""
    antigo = escrever_vra(tmp_path, "VRA_202112.csv", [VOO_REALIZADO])
    escrever_vra(tmp_path, "VRA_20268.csv", [VOO_REALIZADO, VOO_CANCELADO])
    carregar_arquivo(con, antigo)  # como se tivesse sido carregado antes da regra
    assert fora_da_janela(tmp_path) == ["VRA_202112.csv"]

    resultado = carregar_pasta(con, tmp_path)
    assert list(resultado) == ["VRA_20268.csv"]
    arquivos = {a for (a,) in con.execute("select distinct arquivo_origem from raw_vra").fetchall()}
    cargas = {a for (a,) in con.execute("select arquivo_origem from raw_vra_cargas").fetchall()}
    assert arquivos == cargas == {"VRA_20268.csv"}
