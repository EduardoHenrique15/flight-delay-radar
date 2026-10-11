"""Baixa os CSVs mensais do VRA do diretório de dados abertos da ANAC.

O diretório é uma listagem simples ("Index of"), organizada assim:
    .../Voo Regular Ativo (VRA)/<ano>/<MM - Mês>/VRA_<ano><mês>.csv

O programa lê as listagens, compara com o que já está em data/raw/vra/ e baixa só o que é novo
ou mudou (pela data e pelo tamanho que a listagem mostra). Pastas de meses futuros existem, mas
vazias: são tratadas como "ainda não publicado". Cada download fica registrado em
data/raw/vra/_downloads.json.

Se o site bloquear o acesso automático, o programa avisa quais meses faltam e onde baixá-los à
mão: basta colocar os arquivos em data/raw/vra/ com o nome original.

Uso:
    python -m fdr.ingest.download_vra --listar   # só mostra o que está disponível
    python -m fdr.ingest.download_vra            # baixa o que falta desde jan/2022
    python -m fdr.ingest.download_vra --inicio 2019-01 --fim 2021-12 --pasta data/raw/vra_historico
"""

import argparse
import json
import re
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from urllib.parse import quote, unquote, urljoin

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from fdr.config import INICIO_JANELA, PASTA_RAW_VRA

URL_BASE = "https://sistemas.anac.gov.br/dadosabertos/" + quote(
    "Voos e operações aéreas/Voo Regular Ativo (VRA)/"
)
USER_AGENT = (
    "flight-delay-radar/0.1 (projeto de estudo; "
    "+https://github.com/eduardohenrique15/flight-delay-radar)"
)
PAUSA_ENTRE_DOWNLOADS_S = 2.0
TIMEOUT_S = 60
REGISTRO = "_downloads.json"

# Uma linha da listagem: link, data (07-Oct-2026 07:50) e tamanho em bytes ("-" para pastas).
LINHA_LISTAGEM = re.compile(
    r'<a href="(?P<href>[^"]+)">[^<]*</a>\s*'
    r"(?:(?P<data>\d{2}-[A-Za-z]{3}-\d{4} \d{2}:\d{2})\s+(?P<tamanho>\d+|-))?"
)
PASTA_ANO = re.compile(r"^(\d{4})/$")
PASTA_MES = re.compile(r"^(\d{2}) - .+/$")
ARQUIVO_VRA = re.compile(r"^VRA_\d{5,6}\.csv$", re.IGNORECASE)


class AcessoBloqueadoError(RuntimeError):
    """O site recusou o acesso ou respondeu algo que não é a listagem/arquivo esperado."""


@dataclass(frozen=True)
class Item:
    """Uma entrada da listagem."""

    nome: str
    url: str
    data: datetime | None
    tamanho: int | None


@dataclass(frozen=True)
class ArquivoRemoto:
    ano: int
    mes: int
    item: Item


def criar_sessao() -> requests.Session:
    """Sessão com User-Agent honesto e novas tentativas com espera crescente."""
    sessao = requests.Session()
    sessao.headers["User-Agent"] = USER_AGENT
    tentativas = Retry(
        total=4,
        backoff_factor=2,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=("GET", "HEAD"),
    )
    sessao.mount("https://", HTTPAdapter(max_retries=tentativas))
    return sessao


def ler_listagem(html: str, url_pasta: str) -> list[Item]:
    """Extrai os itens de uma página "Index of", ignorando o link para a pasta de cima."""
    itens = []
    for achado in LINHA_LISTAGEM.finditer(html):
        href = achado.group("href")
        if href.startswith(("../", "?", "/")):
            continue
        data = achado.group("data")
        tamanho = achado.group("tamanho")
        itens.append(
            Item(
                nome=unquote(href),
                url=urljoin(url_pasta, href),
                data=datetime.strptime(data, "%d-%b-%Y %H:%M") if data else None,
                tamanho=int(tamanho) if tamanho and tamanho.isdigit() else None,
            )
        )
    return itens


def buscar_listagem(sessao: requests.Session, url: str) -> list[Item]:
    try:
        resposta = sessao.get(url, timeout=TIMEOUT_S)
    except requests.RequestException as erro:
        raise AcessoBloqueadoError(f"Não consegui acessar {url}: {erro}") from erro
    if resposta.status_code != 200 or "Index of" not in resposta.text:
        raise AcessoBloqueadoError(
            f"{url} respondeu {resposta.status_code} sem a listagem esperada "
            "(o site pode estar bloqueando acesso automático)."
        )
    return ler_listagem(resposta.text, url)


def listar_disponiveis(
    sessao: requests.Session,
    inicio: tuple[int, int] = INICIO_JANELA,
    fim: tuple[int, int] | None = None,
) -> list[ArquivoRemoto]:
    """Percorre anos e meses de `inicio` até `fim` (inclusive) e devolve os CSVs publicados."""
    fim = fim or (9999, 12)
    disponiveis = []
    for pasta_ano in buscar_listagem(sessao, URL_BASE):
        achado_ano = PASTA_ANO.match(pasta_ano.nome)
        if not achado_ano or not inicio[0] <= int(achado_ano.group(1)) <= fim[0]:
            continue
        ano = int(achado_ano.group(1))
        for pasta_mes in buscar_listagem(sessao, pasta_ano.url):
            achado_mes = PASTA_MES.match(pasta_mes.nome)
            if not achado_mes or not inicio <= (ano, int(achado_mes.group(1))) <= fim:
                continue
            mes = int(achado_mes.group(1))
            csvs = [i for i in buscar_listagem(sessao, pasta_mes.url) if ARQUIVO_VRA.match(i.nome)]
            disponiveis += [ArquivoRemoto(ano, mes, csv) for csv in csvs]
    return sorted(disponiveis, key=lambda a: (a.ano, a.mes))


def precisa_baixar(remoto: ArquivoRemoto, pasta: Path, registro: dict) -> bool:
    """Baixa se o arquivo não existe, se o tamanho mudou ou se a data da listagem mudou."""
    local = pasta / remoto.item.nome
    if not local.exists():
        return True
    if remoto.item.tamanho is not None and local.stat().st_size != remoto.item.tamanho:
        return True
    anterior = registro.get(remoto.item.nome, {}).get("data_remota")
    atual = remoto.item.data.isoformat() if remoto.item.data else None
    # Arquivo colocado à mão (sem registro) e com o mesmo tamanho: confia nele.
    return anterior is not None and anterior != atual


def baixar(sessao: requests.Session, remoto: ArquivoRemoto, pasta: Path) -> int:
    """Baixa para um arquivo temporário e só troca o original quando o download termina."""
    destino = pasta / remoto.item.nome
    parcial = destino.with_suffix(destino.suffix + ".part")
    try:
        with sessao.get(remoto.item.url, stream=True, timeout=TIMEOUT_S) as resposta:
            tipo = resposta.headers.get("Content-Type", "")
            if resposta.status_code != 200 or "text/html" in tipo:
                raise AcessoBloqueadoError(
                    f"{remoto.item.url} respondeu {resposta.status_code} ({tipo or 'sem tipo'})."
                )
            with parcial.open("wb") as saida:
                for bloco in resposta.iter_content(chunk_size=1 << 20):
                    saida.write(bloco)
    except requests.RequestException as erro:
        parcial.unlink(missing_ok=True)
        raise AcessoBloqueadoError(f"Falha ao baixar {remoto.item.url}: {erro}") from erro

    tamanho = parcial.stat().st_size
    if remoto.item.tamanho is not None and tamanho != remoto.item.tamanho:
        parcial.unlink()
        raise AcessoBloqueadoError(
            f"{remoto.item.nome}: baixei {tamanho} bytes, a listagem dizia {remoto.item.tamanho}."
        )
    parcial.replace(destino)
    return tamanho


def ler_registro(pasta: Path) -> dict:
    caminho = pasta / REGISTRO
    return json.loads(caminho.read_text(encoding="utf-8")) if caminho.exists() else {}


def salvar_registro(pasta: Path, registro: dict) -> None:
    (pasta / REGISTRO).write_text(
        json.dumps(registro, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def sincronizar(
    pasta: Path = PASTA_RAW_VRA,
    sessao: requests.Session | None = None,
    pausa_s: float = PAUSA_ENTRE_DOWNLOADS_S,
    inicio: tuple[int, int] = INICIO_JANELA,
    fim: tuple[int, int] | None = None,
) -> dict[str, str]:
    """Baixa o que falta no período e devolve {arquivo: situação}."""
    sessao = sessao or criar_sessao()
    pasta.mkdir(parents=True, exist_ok=True)
    registro = ler_registro(pasta)
    situacao = {}
    for remoto in listar_disponiveis(sessao, inicio, fim):
        nome = remoto.item.nome
        if not precisa_baixar(remoto, pasta, registro):
            situacao[nome] = "já estava em dia"
            continue
        tamanho = baixar(sessao, remoto, pasta)
        registro[nome] = {
            "url": remoto.item.url,
            "data_remota": remoto.item.data.isoformat() if remoto.item.data else None,
            "tamanho": tamanho,
            "baixado_em": datetime.now().isoformat(timespec="seconds"),
        }
        salvar_registro(pasta, registro)
        situacao[nome] = f"baixado ({tamanho / 1e6:.1f} MB)"
        time.sleep(pausa_s)
    return situacao


def ano_mes(texto: str) -> tuple[int, int]:
    """Converte "2019-01" em (2019, 1), para os argumentos --inicio e --fim."""
    try:
        ano, mes = (int(parte) for parte in texto.split("-"))
    except ValueError as erro:
        raise argparse.ArgumentTypeError(f"use o formato AAAA-MM (ex.: 2019-01): {texto}") from erro
    if not 1 <= mes <= 12:
        raise argparse.ArgumentTypeError(f"mês inválido: {texto}")
    return ano, mes


def main() -> None:
    parser = argparse.ArgumentParser(description="Baixa os CSVs do VRA da ANAC.")
    parser.add_argument("--pasta", type=Path, default=PASTA_RAW_VRA)
    parser.add_argument("--listar", action="store_true", help="só lista, sem baixar")
    parser.add_argument("--inicio", type=ano_mes, default=INICIO_JANELA, help="AAAA-MM")
    parser.add_argument("--fim", type=ano_mes, default=None, help="AAAA-MM (inclusive)")
    args = parser.parse_args()

    try:
        if args.listar:
            for remoto in listar_disponiveis(criar_sessao(), args.inicio, args.fim):
                item = remoto.item
                tamanho = f"{item.tamanho / 1e6:6.1f} MB" if item.tamanho else "     ?"
                print(f"{remoto.ano}-{remoto.mes:02d}  {item.nome:<16} {tamanho}  {item.data}")
            return
        for nome, situacao in sincronizar(args.pasta, inicio=args.inicio, fim=args.fim).items():
            print(f"{nome:<16} {situacao}")
    except AcessoBloqueadoError as erro:
        raise SystemExit(
            f"Download automático falhou: {erro}\n"
            f"Baixe os arquivos à mão em {unquote(URL_BASE)} e coloque em {args.pasta} "
            "com o nome original (ex.: VRA_20268.csv). A carga usa o que estiver lá."
        ) from erro


if __name__ == "__main__":
    main()
