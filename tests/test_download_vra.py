"""Testes do download do VRA, sem internet: um site falso imita as listagens da ANAC."""

import json
from datetime import datetime
from urllib.parse import quote

import pytest

from fdr.ingest import download_vra as dv
from fdr.ingest.download_vra import AcessoBloqueadoError, ler_listagem, sincronizar


def listagem(titulo: str, linhas: list[tuple[str, str, str]]) -> str:
    """Página "Index of" no formato do servidor da ANAC (nome, data, tamanho)."""
    corpo = '<a href="../">../</a>\n' + "\n".join(
        f'<a href="{quote(nome)}">{nome}</a>{" " * 30}{data}{" " * 10}{tamanho}'
        for nome, data, tamanho in linhas
    )
    return (
        f"<html><head><title>Index of {titulo}</title></head><body>"
        f"<h1>Index of {titulo}</h1><hr><pre>{corpo}\n</pre><hr></body></html>"
    )


class Resposta:
    def __init__(self, status=200, texto="", conteudo=b"", tipo="text/html"):
        self.status_code = status
        self.text = texto
        self._conteudo = conteudo
        self.headers = {"Content-Type": tipo}

    def iter_content(self, chunk_size):
        yield self._conteudo

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


class SiteFalso:
    """Imita o diretório da ANAC: 2021 (fora da janela), jan/2022, ago/2026 e set/2026 vazio."""

    def __init__(self, conteudo_agosto=b"x" * 100):
        self.base = dv.URL_BASE
        self.arquivos = {
            "2021/12 - Dezembro/VRA_202112.csv": b"d" * 40,
            "2022/01 - Janeiro/VRA_20221.csv": b"j" * 50,
            "2026/08 - Agosto/VRA_20268.csv": conteudo_agosto,
        }
        self.data_agosto = "07-Oct-2026 07:50"
        self.pedidos = []

    def _url(self, caminho):
        return self.base + quote(caminho)

    def get(self, url, timeout=None, stream=False):
        self.pedidos.append(url)
        paginas = {
            self.base: listagem("/VRA/", [
                ("2021/", "13-Nov-2021 10:59", "-"),
                ("2022/", "05-Jun-2024 22:35", "-"),
                ("2026/", "05-Oct-2026 13:00", "-"),
            ]),
            self._url("2021/"): listagem("/VRA/2021/", [
                ("12 - Dezembro/", "05-Jun-2024 22:34", "-"),
            ]),
            self._url("2021/12 - Dezembro/"): listagem("/VRA/2021/12 - Dezembro/", [
                ("VRA_202112.csv", "07-Oct-2026 07:49", "40"),
            ]),
            self._url("2022/"): listagem("/VRA/2022/", [
                ("01 - Janeiro/", "05-Jun-2024 22:35", "-"),
            ]),
            self._url("2026/"): listagem("/VRA/2026/", [
                ("08 - Agosto/", "08-Oct-2026 10:59", "-"),
                ("09 - Setembro/", "08-Oct-2026 10:59", "-"),
            ]),
            self._url("2022/01 - Janeiro/"): listagem("/VRA/2022/01 - Janeiro/", [
                ("VRA_20221.csv", "07-Oct-2026 07:50", "50"),
                ("VRA_20221.json", "07-Oct-2026 07:50", "120"),
            ]),
            self._url("2026/08 - Agosto/"): listagem("/VRA/2026/08 - Agosto/", [
                ("VRA_20268.csv", self.data_agosto, str(len(self.arquivos[
                    "2026/08 - Agosto/VRA_20268.csv"]))),
                ("VRA_20268.json", "07-Oct-2026 07:50", "300"),
            ]),
            self._url("2026/09 - Setembro/"): listagem("/VRA/2026/09 - Setembro/", []),
        }  # fmt: skip
        if url in paginas:
            return Resposta(texto=paginas[url])
        for caminho, conteudo in self.arquivos.items():
            if url == self._url(caminho):
                return Resposta(conteudo=conteudo, tipo="text/csv")
        return Resposta(status=404, texto="não encontrado")


def test_ler_listagem_entende_pastas_e_arquivos():
    html = listagem("/x/", [
        ("03 - Março/", "30-Apr-2026 10:34", "-"),
        ("VRA_202510.csv", "07-Oct-2026 07:50", "12146027"),
    ])  # fmt: skip
    pasta, arquivo = ler_listagem(html, "https://exemplo/x/")
    assert pasta.nome == "03 - Março/" and pasta.tamanho is None
    assert pasta.url == "https://exemplo/x/03%20-%20Mar%C3%A7o/"
    assert arquivo.nome == "VRA_202510.csv"
    assert arquivo.tamanho == 12146027
    assert arquivo.data == datetime(2026, 10, 7, 7, 50)


def test_baixa_so_a_janela_e_ignora_json_e_meses_vazios(tmp_path):
    site = SiteFalso()
    situacao = sincronizar(tmp_path, sessao=site, pausa_s=0)

    assert list(situacao) == ["VRA_20221.csv", "VRA_20268.csv"]
    assert (tmp_path / "VRA_20268.csv").read_bytes() == b"x" * 100
    assert not any("2021" in url for url in site.pedidos[1:])
    assert not list(tmp_path.glob("*.json.part")) and not (tmp_path / "VRA_20268.json").exists()
    registro = json.loads((tmp_path / "_downloads.json").read_text(encoding="utf-8"))
    assert registro["VRA_20268.csv"]["tamanho"] == 100


def test_segunda_rodada_nao_baixa_de_novo(tmp_path):
    site = SiteFalso()
    sincronizar(tmp_path, sessao=site, pausa_s=0)
    situacao = sincronizar(tmp_path, sessao=site, pausa_s=0)
    assert set(situacao.values()) == {"já estava em dia"}


def test_arquivo_regerado_pela_anac_e_baixado_de_novo(tmp_path):
    site = SiteFalso()
    sincronizar(tmp_path, sessao=site, pausa_s=0)

    site.arquivos["2026/08 - Agosto/VRA_20268.csv"] = b"y" * 100  # mesmo tamanho
    site.data_agosto = "07-Nov-2026 07:50"  # data nova na listagem
    situacao = sincronizar(tmp_path, sessao=site, pausa_s=0)
    assert situacao["VRA_20268.csv"].startswith("baixado")
    assert (tmp_path / "VRA_20268.csv").read_bytes() == b"y" * 100


def test_arquivo_colocado_a_mao_com_mesmo_tamanho_e_mantido(tmp_path):
    (tmp_path / "VRA_20268.csv").write_bytes(b"m" * 100)
    situacao = sincronizar(tmp_path, sessao=SiteFalso(), pausa_s=0)
    assert situacao["VRA_20268.csv"] == "já estava em dia"
    assert (tmp_path / "VRA_20268.csv").read_bytes() == b"m" * 100


def test_pagina_de_bloqueio_vira_erro_claro(tmp_path):
    class SiteBloqueado(SiteFalso):
        def get(self, url, timeout=None, stream=False):
            return Resposta(status=403, texto="<html>Acesso negado</html>")

    with pytest.raises(AcessoBloqueadoError, match="403"):
        sincronizar(tmp_path, sessao=SiteBloqueado(), pausa_s=0)


def test_download_incompleto_nao_substitui_o_arquivo(tmp_path, monkeypatch):
    site = SiteFalso()
    original = site.get

    def get_truncado(url, timeout=None, stream=False):
        resposta = original(url, timeout, stream)
        if url.endswith("VRA_20268.csv"):
            resposta._conteudo = b"x" * 10  # listagem diz 100 bytes
        return resposta

    monkeypatch.setattr(site, "get", get_truncado)
    (tmp_path / "VRA_20268.csv").write_bytes(b"antigo")
    with pytest.raises(AcessoBloqueadoError, match="baixei 10 bytes"):
        sincronizar(tmp_path, sessao=site, pausa_s=0)
    assert (tmp_path / "VRA_20268.csv").read_bytes() == b"antigo"
    assert not list(tmp_path.glob("*.part"))


def test_periodo_escolhido_baixa_so_os_meses_pedidos(tmp_path):
    situacao = sincronizar(
        tmp_path, sessao=SiteFalso(), pausa_s=0, inicio=(2021, 6), fim=(2022, 12)
    )
    assert list(situacao) == ["VRA_202112.csv", "VRA_20221.csv"]


@pytest.mark.parametrize("texto", ["2019", "2019-13", "jan-2019"])
def test_periodo_em_formato_errado_falha(texto):
    import argparse

    with pytest.raises(argparse.ArgumentTypeError):
        dv.ano_mes(texto)
