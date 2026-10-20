"""Gemini fora do ar ou sobrecarregado (503): a pergunta de exemplo usa a resposta gravada, e as
outras recebem um aviso curto, sem o detalhe técnico."""

from test_assistant import PERGUNTA, SQL_GOL, criar

from fdr.assistant.llm import ErroLLM, normalizar


def test_gemini_fora_do_ar_usa_a_gravada_ou_avisa_sem_detalhe(banco, tmp_path):
    fora = ErroLLM("O Gemini recusou o pedido (503).")
    demo = {PERGUNTA: {"sql": SQL_GOL, "explicacao": "Contei os voos da Gol."}}
    respostas = {normalizar(PERGUNTA): [fora], "outra pergunta": [fora]}
    assistente, _ = criar(banco, tmp_path, respostas=respostas, demonstracao=demo)

    gravada = assistente.responder(PERGUNTA)
    assert gravada.origem == "demonstracao"
    assert "não respondeu agora" in gravada.avisos[0]

    outra = assistente.responder("Outra pergunta")
    assert outra.origem == "erro"
    assert "503" not in outra.texto and "Tente de novo" in outra.texto
    assert assistente.uso.motivo_bloqueio(0) is None  # o dia não fica marcado
