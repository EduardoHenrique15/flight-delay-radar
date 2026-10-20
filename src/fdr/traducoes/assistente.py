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
    # Gráfico, travas e placar da avaliação (etapa 4)
    "Travas cumpridas": "Guardrails passed",
    "Uma instrução só, de leitura (SELECT)": "A single read-only statement (SELECT)",
    "Só as 6 tabelas do app": "Only the app's 6 tables",
    "Sem funções de arquivo, rede ou sistema": "No file, network or system functions",
    "No máximo 1.000 linhas": "At most 1,000 rows",
    "Banco só de leitura, sem acesso externo": "Read-only database, no external access",
    "No máximo 10 segundos": "At most 10 seconds",
    "Como o assistente foi avaliado": "How the assistant was evaluated",
    "{perguntas} perguntas com resposta conhecida: o resultado do SQL do Gemini é comparado com "
    "o de um SQL de referência escrito à mão. Nas perguntas que os dados não respondem, o certo é "
    "recusar.": (
        "{perguntas} questions with a known answer: the result of Gemini's SQL is compared with "
        "that of a hand-written reference SQL. For questions the data cannot answer, the right "
        "move is to decline."
    ),
    "{parte} de {total}": "{parte} of {total}",
    "Acerto automático": "Automatic accuracy",
    "A métrica principal: o resultado precisa bater coluna por coluna.": (
        "The main metric: the result has to match column by column."
    ),
    "Na revisão manual": "After manual review",
    "contando as respostas com os mesmos números": "counting answers with the same numbers",
    "SQL válido": "Valid SQL",
    "nenhuma consulta bloqueada pelas travas": "no query blocked by the guardrails",
    "Recusas certas": "Correct refusals",
    "preço da passagem, clima, tripulação": "ticket price, weather, crew",
    "Por tipo de pergunta": "By question type",
    "Simples": "Simple",
    "Somas e rankings": "Sums and rankings",
    "Junções": "Joins",
    "No tempo": "Over time",
    "Recusas": "Refusals",
    "As que a avaliação marcou como erradas": "The ones the evaluation marked as wrong",
    "Revisadas à mão, rodando os dois SQLs nos dados do app.": (
        "Reviewed by hand, running both SQL queries on the app's data."
    ),
    "Mesmos números, outra forma": "Same numbers, different form",
    "Erro de verdade": "Actual error",
    "Sem revisão": "Not reviewed",
    "Modelo {modelo}, de {inicio} a {fim}, em {lotes} lotes (a cota gratuita do Gemini limita os "
    "pedidos por dia). Método e resultados completos em docs/assistente.md.": (
        "Model {modelo}, from {inicio} to {fim}, in {lotes} batches (Gemini's free quota limits "
        "requests per day). Full method and results in docs/assistente.md."
    ),
    # Revisão manual (eval/revisao.yaml) e as perguntas revisadas
    "Qual é o código ICAO da Gol?": "What is Gol's ICAO code?",
    "Quais as 5 companhias com mais voos nacionais atrasados mais de 1 hora em julho de 2026?": (
        "Which 5 airlines had the most domestic flights delayed over 1 hour in July 2026?"
    ),
    'Buscou os nomes que contêm "Gol" (ILIKE) e trouxe também a Cargolux e a TAAG Angola '
    "Airlines, em vez de só a Gol (GLO).": (
        'It searched for names containing "Gol" (ILIKE) and also returned Cargolux and TAAG '
        "Angola Airlines, instead of just Gol (GLO)."
    ),
    "Os mesmos 5 aeroportos, na mesma ordem e com os mesmos totais, identificados pelo nome em "
    "vez do código ICAO.": (
        "The same 5 airports, in the same order and with the same totals, identified by name "
        "instead of ICAO code."
    ),
    "A hora com a maior taxa de atraso (22h) está no topo, mas a resposta lista as 5 primeiras em "
    "vez de só uma.": (
        "The hour with the highest delay rate (10 pm) is at the top, but the answer lists the top "
        "5 instead of just one."
    ),
    "As mesmas 5 companhias, na mesma ordem e com os mesmos totais, identificadas pelo nome em "
    "vez do código ICAO.": (
        "The same 5 airlines, in the same order and with the same totals, identified by name "
        "instead of ICAO code."
    ),
    # Explicações das respostas de demonstração (data/demo/assistant_cache.json)
    "Soma a quantidade de voos realizados registrados na tabela pontualidade_mensal para o mês de "
    "julho de 2026.": (
        "Adds up the flights operated recorded in the pontualidade_mensal table for July 2026."
    ),
    "Calcula a taxa geral de atraso (partidas com mais de 15 minutos de atraso divididas pelo "
    "total de voos realizados com horário registrado) para todos os voos nacionais no mês de "
    "agosto de 2026.": (
        "Computes the overall delay rate (departures more than 15 minutes late divided by all "
        "operated flights with a recorded time) for all domestic flights in August 2026."
    ),
    "Agrupa os voos realizados por companhia no mês de agosto de 2026 (mes = '2026-08-01') e "
    "retorna o nome da companhia com o maior total.": (
        "Groups the operated flights by airline in August 2026 (mes = '2026-08-01') and returns "
        "the name of the airline with the highest total."
    ),
    "Calcula a taxa de atraso (voos com atraso superior a 15 minutos divididos pelos voos "
    "realizados com horário registrado) para cada mês de 2025 em voos nacionais, ordenando do "
    "maior para o menor para identificar o mês com a maior taxa.": (
        "Computes the delay rate (flights more than 15 minutes late divided by operated flights "
        "with a recorded time) for each month of 2025 on domestic flights, sorted from highest "
        "to lowest to find the month with the highest rate."
    ),
    "Calcula a taxa de atraso mensal (partidas com mais de 15 minutos de atraso divididas pelo "
    "total de voos realizados com registro de horário) para voos nacionais (tipo_linha = 'N') ao "
    "longo do ano de 2026.": (
        "Computes the monthly delay rate (departures more than 15 minutes late divided by all "
        "operated flights with a recorded time) for domestic flights (tipo_linha = 'N') "
        "throughout 2026."
    ),
    # Cota do Gemini acabou no meio do uso (o app cai no modo de demonstração)
    "cota do Gemini esgotada hoje": "Gemini quota used up for today",
    "limite por minuto do Gemini": "Gemini's per-minute limit",
    # Gemini fora do ar ou sobrecarregado (503)
    "o Gemini não respondeu agora": "Gemini did not respond right now",
    "O Gemini não respondeu agora. Tente de novo em instantes ou use uma das perguntas de "
    "exemplo.": (
        "Gemini did not respond right now. Try again in a moment or use one of the example "
        "questions."
    ),
}
