# ADR 007: assistente texto→SQL com travas, em vez de RAG

- **Situação:** aceita
- **Data:** 16/10/2026
- **Código:** `src/fdr/assistant/`. A avaliação fica em `eval/questions.yaml` e
  `src/fdr/assistant/eval.py`.

## Contexto

O app tem uma página "Pergunte aos dados": a pessoa escreve em português ("qual companhia mais
atrasou em julho?") e recebe a resposta.

As perguntas são sobre números (contagens, taxas, rankings, comparações no tempo) que estão em
tabelas. A cota gratuita do Gemini é de cerca de 20 pedidos por dia.

## Decisão

1. **O modelo escreve SQL, e o banco calcula.** O Gemini recebe:
   - a descrição das 6 tabelas do app, com os tipos e exemplos de valores tirados do próprio
     banco;
   - as convenções do projeto (por exemplo, o que é "taxa de atraso");
   - 5 exemplos de pergunta e SQL.

   Ele devolve um JSON estruturado: `pode_responder`, `sql` e `explicacao`.
2. **Duas camadas de travas, independentes:**
   - **Análise com o sqlglot:**
     - uma instrução só, só SELECT ou WITH;
     - só as 6 tabelas, pelo nome;
     - nenhuma função de arquivo, rede ou ambiente (`read_csv`, `glob`, `getenv`...);
     - nada de ATTACH, COPY, INSTALL, LOAD, PRAGMA ou SET;
     - LIMIT de no máximo 1000.
   - **Conexão com o banco:**
     - somente leitura;
     - `enable_external_access = false`, o que bloqueia arquivos e URLs mesmo que algo passe
       pela primeira camada;
     - configuração travada e tempo máximo de 10 s.

   `tests/test_assistant.py` traz 24 consultas maliciosas que precisam ser bloqueadas.
3. **Uma nova tentativa:** se o SQL for bloqueado ou der erro, o erro volta ao modelo uma vez. Se
   falhar de novo, o assistente explica e pede para reformular.
4. **Recusa:** perguntas que os dados não respondem (preço, clima, piloto) devem voltar com
   `pode_responder = false`.
5. **Cota:**
   - um cache das respostas aprovadas, que não gastam pedido;
   - limite de 3 perguntas por sessão e 6 por dia;
   - sem chave ou sem cota, o assistente usa as respostas gravadas de demonstração
     (`data/demo/assistant_cache.json`).
6. **Avaliação por resultado:** 31 perguntas com SQL de referência escrito à mão. O acerto é medido
   comparando o que as duas consultas devolvem, e não o texto do SQL. O modelo é chamado em 3
   lotes de 11 perguntas, um por dia, só com autorização.

## Alternativas consideradas

1. **RAG (buscar trechos de texto e pedir a resposta ao modelo).** Funciona para documentos, mas
   não calcula: "qual a taxa de atraso da Gol em julho" exige somar milhares de linhas. O modelo
   inventaria números.
2. **Mandar a tabela para o modelo** (os dados no prompt). Os dados têm milhões de linhas, não
   cabem e custariam a cota inteira.
3. **LangChain ou um agente com várias ferramentas.** Mais dependências e mais pedidos por
   pergunta, para um fluxo que cabe em uma chamada.
4. **Só a primeira camada de travas.** Um analisador pode ter falhas. A segunda camada, na
   conexão, garante que um SQL que escape não consiga ler arquivos nem escrever.

## Consequências

- O SQL usado aparece na resposta (transparência), e o resultado vem sempre do banco, nunca do
  modelo.
- As respostas do cache e da demonstração também passam pelas travas e são executadas de novo
  nos dados atuais.
- A qualidade depende da descrição das tabelas e dos exemplos. A avaliação mede isso, e uma
  melhoria pode ser comparada antes e depois, com outra rodada.
