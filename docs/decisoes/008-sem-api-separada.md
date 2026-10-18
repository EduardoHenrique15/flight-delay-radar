# ADR 008: sem API separada; o app roda só no Streamlit Community Cloud

- **Situação:** aceita
- **Data:** 18/10/2026
- **Código:** `app/` (páginas), `src/fdr/interface.py`, `src/fdr/painel.py` e
  `src/fdr/previsao.py`. O passo a passo da publicação está em `docs/deploy.md`.

## Contexto

O projeto precisa de um endereço público onde qualquer pessoa veja os dados, faça uma previsão e
pergunte ao assistente. Não há orçamento, e o público é pequeno (portfólio). A atualização dos
dados é mensal, por pull request.

## Decisão

1. **Um só processo:** o app Streamlit carrega o modelo (`models/model.txt`), lê os Parquet de
   `data/marts/` e chama o assistente. Não existe uma API REST separada para a previsão.
2. **Publicação no Streamlit Community Cloud**, direto do GitHub: cada merge na `main` atualiza o
   app. A chave do Gemini fica nos secrets do Streamlit, nunca no repositório.
3. **Os dados do app vão no git:** `data/marts/` tem alguns MB (o maior arquivo, `voos.parquet`,
   tem cerca de 9 MB), abaixo do limite de 50 MB por arquivo do GitHub. O
   `data/app.duckdb` não vai: o app o recria a partir dos Parquet.

## Alternativas consideradas

1. **API com FastAPI e o app como cliente.** Dois serviços para publicar, monitorar e manter
   gratuitos. Faz sentido quando outros sistemas consomem a previsão; aqui só o app consome.
2. **Hugging Face Spaces ou uma VM com Docker.** Funcionam, mas o Streamlit Cloud já lê o
   repositório, guarda os secrets e não pede Dockerfile.
3. **Dados num bucket ou num Release do GitHub.** Evita versionar Parquet, mas acrescenta um
   download no início do app e uma credencial ou um passo manual a cada mês.

## Consequências

- Publicar e atualizar é só fazer merge na `main`.
- O app gratuito "dorme" depois de alguns dias sem acesso; a primeira visita depois disso demora
  mais para abrir.
- Toda a computação precisa caber em cerca de 1 GB: o app consulta os Parquet com DuckDB sob
  demanda, sem carregar a base inteira no pandas, e guarda resultados com `st.cache_data`.
- Se um dia outro sistema precisar da previsão, `fdr.previsao.Previsor` já é independente do
  Streamlit e pode ganhar uma API em volta, sem mudar o modelo.
