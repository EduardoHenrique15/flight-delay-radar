"""Traduções da página Pergunte aos dados (app/paginas/assistente.py) e das mensagens fixas do
assistente (fdr.assistant.agent), com as perguntas de exemplo da avaliação (eval/questions.yaml)."""

TEXTOS = {
    # Página
    "Perguntas em português, respostas do banco": (
        "Questions in plain language, answers from the database"
    ),
    "O assistente transforma a pergunta numa consulta SQL, que passa por travas de segurança e "
    "roda nos dados do app. O número vem sempre do banco, nunca do modelo de linguagem.": (
        "The assistant turns your question into a SQL query, which goes through safety "
        "guardrails and runs on the app's data. The number always comes from the database, "
        "never from the language model."
    ),
    "Modelo de linguagem": "Language model",
    "Demonstração": "Demo",
    "Banco": "Database",
    "DuckDB · 6 tabelas": "DuckDB · 6 tables",
    "Consultas": "Queries",
    "Só leitura": "Read-only",
    "Modo de demonstração: este app está sem a chave do Gemini. As perguntas de exemplo têm "
    "consultas gravadas, que rodam de novo nos dados atuais.": (
        "Demo mode: this app has no Gemini key. The example questions have saved queries, which "
        "run again on the current data."
    ),
    "Até {por_sessao} perguntas novas por visita e {por_dia} por dia (cota gratuita do Gemini). "
    "Depois disso, o assistente responde só às perguntas de exemplo.": (
        "Up to {por_sessao} new questions per visit and {por_dia} per day (Gemini's free "
        "quota). After that, the assistant answers only the example questions."
    ),
    "Faça uma pergunta": "Ask a question",
    "Ou comece por um dos exemplos abaixo.": "Or start with one of the examples below.",
    "Ex.: Qual companhia mais atrasou em julho de 2026?": (
        "E.g.: Which airline had the most delays in July 2026?"
    ),
    "Consultando os dados...": "Querying the data...",
    "Conversa": "Conversation",
    "Ver a consulta SQL": "See the SQL query",
    "Como o assistente responde": "How the assistant answers",
    "Pergunta": "Question",
    "Em português, sobre os voos, as companhias e os aeroportos do app.": (
        "In English or Portuguese, about the app's flights, airlines and airports."
    ),
    "Consulta": "Query",
    "O Gemini escreve uma consulta SQL a partir da descrição das tabelas, sem receber as linhas "
    "do banco.": (
        "Gemini writes a SQL query from the description of the tables, without receiving any "
        "rows from the database."
    ),
    "Travas": "Guardrails",
    "Só leitura (SELECT), só as 6 tabelas do app, sem arquivos nem rede, no máximo 1.000 linhas "
    "e 10 segundos.": (
        "Read-only (SELECT), only the app's 6 tables, no files or network, at most 1,000 rows "
        "and 10 seconds."
    ),
    "Resposta": "Answer",
    "O DuckDB roda a consulta e os números da resposta saem da tabela, que aparece junto com o "
    "SQL.": (
        "DuckDB runs the query and the numbers in the answer come from the table, shown together "
        "with the SQL."
    ),
    # Origem da resposta
    "Consulta escrita pelo Gemini": "Query written by Gemini",
    "Consulta já aprovada antes": "Query approved before",
    "Resposta de demonstração": "Demo answer",
    "Fora do alcance dos dados": "Outside the data's scope",
    "Não foi possível responder": "Could not answer",
    "Modo de demonstração": "Demo mode",
    # Mensagens do assistente (fdr.assistant.agent)
    "A consulta não encontrou nenhum resultado.": "The query returned no results.",
    "Resposta: {valor}.": "Answer: {valor}.",
    "{linhas} linha(s) encontrada(s).": "{linhas} row(s) found.",
    "Escreva uma pergunta sobre os voos.": "Write a question about the flights.",
    "sem chave do Gemini": "no Gemini key",
    "limite de {0} perguntas por sessão": "limit of {0} questions per session",
    "limite de {0} perguntas por dia": "limit of {0} questions per day",
    "Resposta gravada de demonstração ({bloqueio}).": "Saved demo answer ({bloqueio}).",
    "O assistente está em modo de demonstração ({bloqueio}).": (
        "The assistant is in demo mode ({bloqueio})."
    ),
    "Experimente uma das perguntas de exemplo: {sugestoes}.": (
        "Try one of the example questions: {sugestoes}."
    ),
    "O assistente não conseguiu responder: {erro}": "The assistant could not answer: {erro}",
    "Os dados do projeto não têm essa informação.": "The project's data does not have that.",
    "Não consegui montar uma consulta válida para essa pergunta ({erro}). Tente reformular.": (
        "I could not build a valid query for that question ({erro}). Try rephrasing it."
    ),
    # Perguntas de exemplo (eval/questions.yaml, as marcadas com demo: true)
    "Quantos voos foram realizados em julho de 2026?": "How many flights operated in July 2026?",
    "Qual foi a taxa de atraso dos voos nacionais em agosto de 2026?": (
        "What was the delay rate of domestic flights in August 2026?"
    ),
    "Quais os 5 aeroportos de origem com mais voos nacionais cancelados em 2026?": (
        "Which 5 origin airports had the most cancelled domestic flights in 2026?"
    ),
    "Em que hora do dia os voos nacionais regulares têm a maior taxa de atraso?": (
        "At what hour of the day do scheduled domestic flights have the highest delay rate?"
    ),
    "Qual o nome da companhia com mais voos realizados em agosto de 2026?": (
        "What is the name of the airline with the most flights operated in August 2026?"
    ),
    "Em qual mês de 2025 a taxa de atraso dos voos nacionais foi maior?": (
        "In which month of 2025 was the delay rate of domestic flights highest?"
    ),
    "Como evoluiu a taxa de atraso dos voos nacionais mês a mês em 2026?": (
        "How did the delay rate of domestic flights change month by month in 2026?"
    ),
    "Vai chover em Guarulhos amanhã?": "Will it rain in Guarulhos tomorrow?",
}
