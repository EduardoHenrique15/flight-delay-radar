"""Testes do assistente texto->SQL, sem rede: travas, fluxo com LLM falso, cache e limites."""

from datetime import date

import duckdb
import pytest

from fdr.assistant import guard, schema
from fdr.assistant.agent import Assistente, resumir
from fdr.assistant.llm import Cache, ControleDeUso, LLMFalso, normalizar

TABELAS = set(schema.TABELAS)


def criar(banco, tmp_path, respostas=None, demonstracao=None, sem_chave=False, **limites):
    demo = Cache(tmp_path / "demo.json")
    for pergunta, gravada in (demonstracao or {}).items():
        demo.guardar(pergunta, gravada)
    llm = None if sem_chave else LLMFalso(respostas or {})
    uso = ControleDeUso(tmp_path / "uso.json", **limites)
    return Assistente(banco, llm, Cache(tmp_path / "cache.json"), demo, uso), llm


# --- travas -------------------------------------------------------------------------------

MALICIOSAS = [
    "DROP TABLE voos",
    "SELECT 1 FROM voos; DELETE FROM voos",
    "select 1 from voos /* comentário */; drop table voos -- fim",
    "SeLeCt * FrOm VoOs; dRoP tAbLe voos",
    "COPY voos TO '/tmp/voos.csv'",
    "SELECT * FROM read_csv('/etc/passwd')",
    "SELECT * FROM '/etc/passwd'",
    "SELECT * FROM 'https://exemplo.com/dados.csv'",
    "SELECT * FROM voos WHERE cia IN (SELECT cia FROM read_parquet('x.parquet'))",
    "ATTACH 'outro.db' AS outro",
    "INSTALL httpfs",
    "LOAD httpfs",
    "PRAGMA database_list",
    "SET threads = 1",
    "INSERT INTO voos SELECT * FROM voos",
    "UPDATE voos SET cia = 'X'",
    "CREATE TABLE t AS SELECT 1",
    "SELECT * FROM raw_vra",
    "SELECT * FROM outro.main.voos",
    "SELECT getenv('GEMINI_API_KEY') FROM voos",
    "SELECT * FROM duckdb_settings()",
    "SELECT * FROM glob('*')",
    "SELECT * FROM voos LIMIT (SELECT 10)",
    "isto não é SQL",
]


@pytest.mark.parametrize("sql", MALICIOSAS)
def test_consultas_maliciosas_sao_bloqueadas(sql):
    with pytest.raises(guard.SQLBloqueado):
        guard.validar(sql, TABELAS)


@pytest.mark.parametrize(
    ("sql", "limite"),
    [
        ("select cia, count(*) from voos group by cia", "LIMIT 1000"),
        ("with x as (select * from voos) select count(*) from x", "LIMIT 1000"),
        ("select * from voos limit 5000", "LIMIT 1000"),
        ("select * from voos limit 10", "LIMIT 10"),
        ("select cia from voos union select cia from companhias", "LIMIT 1000"),
    ],
)
def test_consultas_validas_passam_com_limit(sql, limite):
    assert guard.validar(sql, TABELAS).endswith(limite)


def test_conexao_bloqueia_arquivos_e_escrita_mesmo_sem_a_analise(banco):
    con = guard.conectar(banco)
    for sql in (
        "select * from read_csv('/etc/passwd')",
        "attach '/tmp/outro.db' as outro",
        "create table t as select 1",
        "set enable_external_access = true",
    ):
        with pytest.raises(duckdb.Error):
            con.execute(sql)


def test_consulta_lenta_e_interrompida(banco):
    con = guard.conectar(banco)
    with pytest.raises(guard.SQLBloqueado, match="interrompida"):
        guard.executar(con, "select count(*) from range(100000000000)", tempo_maximo_s=0.5)


def test_exemplos_do_prompt_passam_pelas_travas_e_rodam(banco):
    con = guard.conectar(banco)
    for exemplo in schema.EXEMPLOS:
        guard.executar(con, guard.validar(exemplo["sql"], TABELAS))
    prompt = schema.montar_prompt_sistema(con)
    assert all(f"Tabela {t}" in prompt for t in TABELAS)
    assert "pode_responder = false" in prompt


# --- fluxo ----------------------------------------------------------------------------------

PERGUNTA = "Quantos voos a Gol fez?"
SQL_GOL = "select count(*) as voos from voos where cia = 'GLO'"


def test_pergunta_respondida_pelo_modelo_e_depois_pelo_cache(banco, tmp_path):
    respostas = {
        normalizar(PERGUNTA): [
            {"pode_responder": True, "sql": SQL_GOL, "explicacao": "Contei os voos da Gol."}
        ]
    }
    assistente, llm = criar(banco, tmp_path, respostas)
    primeira = assistente.responder(PERGUNTA)
    assert primeira.origem == "modelo" and primeira.tabela.iat[0, 0] == 2
    assert primeira.sql.endswith("LIMIT 1000") and primeira.texto.endswith("Resposta: 2.")
    segunda = assistente.responder("quantos voos a gol fez")  # mesma pergunta, outra escrita
    assert segunda.origem == "cache" and segunda.tabela.iat[0, 0] == 2
    assert len(llm.chamadas) == 1  # o cache não gasta cota


def test_pergunta_fora_dos_dados_e_recusada(banco, tmp_path):
    pergunta = "Qual o preço da passagem para o Rio?"
    respostas = {
        normalizar(pergunta): [
            {"pode_responder": False, "sql": "", "explicacao": "Não há preços nos dados."}
        ]
    }
    assistente, _ = criar(banco, tmp_path, respostas)
    resposta = assistente.responder(pergunta)
    assert resposta.origem == "recusa" and "preços" in resposta.texto and resposta.sql is None


def test_sql_bloqueado_ganha_uma_nova_tentativa(banco, tmp_path):
    respostas = {
        normalizar(PERGUNTA): [
            {"pode_responder": True, "sql": "DROP TABLE voos", "explicacao": "x"},
            {"pode_responder": True, "sql": SQL_GOL, "explicacao": "Contei os voos da Gol."},
        ]
    }
    assistente, llm = criar(banco, tmp_path, respostas)
    resposta = assistente.responder(PERGUNTA)
    assert resposta.origem == "modelo" and resposta.tentativas == 2
    assert len(llm.chamadas) == 2


def test_duas_falhas_seguidas_terminam_com_mensagem_clara(banco, tmp_path):
    respostas = {
        normalizar(PERGUNTA): [
            {"pode_responder": True, "sql": "DROP TABLE voos", "explicacao": "x"},
            {
                "pode_responder": True,
                "sql": "select coluna_que_nao_existe from voos",
                "explicacao": "x",
            },
        ]
    }
    assistente, llm = criar(banco, tmp_path, respostas)
    resposta = assistente.responder(PERGUNTA)
    assert resposta.origem == "erro" and resposta.tentativas == 2
    assert "reformular" in resposta.texto and len(llm.chamadas) == 2


def test_sem_chave_usa_as_respostas_de_demonstracao(banco, tmp_path):
    demo = {PERGUNTA: {"sql": SQL_GOL, "explicacao": "Contei os voos da Gol."}}
    assistente, _ = criar(banco, tmp_path, demonstracao=demo, sem_chave=True)
    gravada = assistente.responder(PERGUNTA)
    assert gravada.origem == "demonstracao" and gravada.tabela.iat[0, 0] == 2
    assert "demonstração" in gravada.avisos[0]
    outra = assistente.responder("Qual companhia mais atrasa?")
    assert outra.origem == "limite" and PERGUNTA in outra.texto


def test_limite_por_sessao_e_por_dia(banco, tmp_path):
    respostas = {
        normalizar(PERGUNTA): [{"pode_responder": True, "sql": SQL_GOL, "explicacao": "ok"}]
    }
    assistente, llm = criar(banco, tmp_path, respostas, por_sessao=3, por_dia=1)
    assert assistente.responder("Outra pergunta?", usadas_na_sessao=3).origem == "limite"
    assert assistente.responder(PERGUNTA).origem == "modelo"  # usa a única do dia
    assert assistente.uso.motivo_bloqueio(0) == "limite de 1 perguntas por dia"
    assert len(llm.chamadas) == 1


def test_normalizar_e_resumir():
    assert normalizar("  Qual é a TAXA de atraso?? ") == "qual e a taxa de atraso"
    import pandas as pd

    assert resumir(pd.DataFrame({"taxa": [0.1534]})) == "Resposta: 15,3%."
    assert resumir(pd.DataFrame({"voos": [1234567]})) == "Resposta: 1234567."
    assert resumir(pd.DataFrame()) == "A consulta não encontrou nenhum resultado."
    assert date.today()  # o controle de uso grava por dia


def test_cliente_gemini_monta_o_pedido_e_le_o_json_sem_rede(monkeypatch):
    """Substitui só a chamada HTTP: confere a configuração enviada e a leitura da resposta."""
    from types import SimpleNamespace

    from google.genai import errors

    from fdr.assistant.llm import ErroLLM, Gemini

    gemini = Gemini("chave-falsa", modelo="modelo-teste")
    enviado = {}

    def responder(model, contents, config):
        enviado.update(model=model, contents=contents, config=config)
        return SimpleNamespace(
            text='{"pode_responder": true, "sql": "select 1", "explicacao": "x"}'
        )

    monkeypatch.setattr(gemini._cliente.models, "generate_content", responder)
    assert gemini.gerar("sistema", "Pergunta: oi") == {
        "pode_responder": True,
        "sql": "select 1",
        "explicacao": "x",
    }
    assert enviado["model"] == "modelo-teste"
    assert enviado["config"].response_mime_type == "application/json"
    assert enviado["config"].temperature == 0
    assert enviado["config"].automatic_function_calling.disable

    def recusar(**_):
        raise errors.ClientError(429, {"error": {"message": "cota"}})

    monkeypatch.setattr(gemini._cliente.models, "generate_content", recusar)
    with pytest.raises(ErroLLM, match="429.*limite de pedidos"):
        gemini.gerar("sistema", "Pergunta: oi")


def test_gemini_tenta_de_novo_quando_o_servidor_esta_sobrecarregado(monkeypatch):
    """503 uma vez: espera e tenta de novo. 503 duas vezes: desiste com ErroLLM."""
    from types import SimpleNamespace

    from google.genai import errors

    from fdr.assistant import llm
    from fdr.assistant.llm import ErroLLM, Gemini

    esperas = []
    monkeypatch.setattr(llm.time, "sleep", esperas.append)
    gemini = Gemini("chave-falsa", modelo="modelo-teste")
    respostas = [
        errors.ServerError(503, {"error": {"message": "sobrecarregado"}}),
        SimpleNamespace(text='{"pode_responder": true, "sql": "select 1", "explicacao": "x"}'),
    ]

    def responder(**_):
        resposta = respostas.pop(0)
        if isinstance(resposta, Exception):
            raise resposta
        return resposta

    monkeypatch.setattr(gemini._cliente.models, "generate_content", responder)
    assert gemini.gerar("sistema", "Pergunta: oi")["sql"] == "select 1"
    assert esperas == [llm.ESPERA_ERRO_PASSAGEIRO_S]

    def sempre_503(**_):
        raise errors.ServerError(503, {"error": {"message": "sobrecarregado"}})

    monkeypatch.setattr(gemini._cliente.models, "generate_content", sempre_503)
    with pytest.raises(ErroLLM, match="503"):
        gemini.gerar("sistema", "Pergunta: oi")
    assert len(esperas) == 2  # uma espera só por pergunta


def test_gemini_distingue_o_limite_do_minuto_e_o_do_dia(monkeypatch):
    """Limite por minuto: na avaliação espera o tempo pedido e tenta de novo; no app, não espera.
    Limite do dia: desiste na hora, sem esperar."""
    from types import SimpleNamespace

    from google.genai import errors

    from fdr.assistant import llm
    from fdr.assistant.llm import CotaEsgotada, Gemini

    def erro_429(limite, espera="37s"):
        return errors.ClientError(
            429,
            {
                "error": {
                    "message": "cota",
                    "details": [
                        {"violations": [{"quotaId": f"GenerateRequests{limite}-FreeTier"}]},
                        {"retryDelay": espera},
                    ],
                }
            },
        )

    ok = SimpleNamespace(text='{"pode_responder": true, "sql": "select 1", "explicacao": "x"}')
    esperas = []
    monkeypatch.setattr(llm.time, "sleep", esperas.append)

    def sequencia(*respostas):
        fila = list(respostas)

        def responder(**_):
            resposta = fila.pop(0)
            if isinstance(resposta, Exception):
                raise resposta
            return resposta

        return responder

    avaliacao = Gemini("chave-falsa", modelo="m", esperar_limite_por_minuto=True)
    monkeypatch.setattr(
        avaliacao._cliente.models,
        "generate_content",
        sequencia(erro_429("PerMinutePerProjectPerModel"), ok),
    )
    assert avaliacao.gerar("sistema", "Pergunta: oi")["sql"] == "select 1"
    assert esperas == [38.0]

    monkeypatch.setattr(
        avaliacao._cliente.models,
        "generate_content",
        sequencia(erro_429("PerDayPerProjectPerModel")),
    )
    with pytest.raises(CotaEsgotada, match="do dia") as dia:
        avaliacao.gerar("sistema", "Pergunta: oi")
    assert dia.value.diaria
    assert esperas == [38.0]  # não espera pelo limite do dia

    app = Gemini("chave-falsa", modelo="m")
    monkeypatch.setattr(
        app._cliente.models, "generate_content", sequencia(erro_429("PerMinutePerProjectPerModel"))
    )
    with pytest.raises(CotaEsgotada, match="por minuto") as minuto:
        app.gerar("sistema", "Pergunta: oi")
    assert not minuto.value.diaria
    assert esperas == [38.0]  # o app não espera
