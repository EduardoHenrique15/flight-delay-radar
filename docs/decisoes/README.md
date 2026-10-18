# Decisões do projeto (ADRs)

Registros curtos de decisões, com contexto, alternativas e consequências. Os números citados vêm
de arquivos gerados pelo projeto (em `dados/` ou nas tabelas do pipeline), nunca digitados à mão.

| ADR | Decisão | Situação |
| --- | --- | --- |
| [001](001-janela-de-dados.md) | Janela de dados a partir de janeiro de 2022 | aceita |
| [002](002-alvo-a15.md) | Alvo A15, só voos realizados, nacionais e regulares | aceita |
| [003](003-regra-as-of.md) | Regra contra vazamento, defasagem de 2 meses, treino a partir de 2023, variáveis da hora da previsão e intervalo de 1 mês | aceita |
| [004](004-duckdb-e-dbt.md) | DuckDB e dbt como warehouse e transformações; Parquet para o app | aceita |
| [005](005-escolha-do-modelo.md) | Modelo final (LightGBM) pela regra de 1 erro-padrão pareada, sem calibração, 219 árvores | aceita |
| [006](006-regra-de-retreino.md) | Retreino quando o modelo perde do baseline no mês, ECE > 5 p.p., PSI alto ou 6 meses; desafiante só vence com folga | aceita |
| [007](007-texto-para-sql-com-travas.md) | Assistente que escreve SQL com duas camadas de travas, em vez de RAG | aceita |
| [008](008-sem-api-separada.md) | Sem API separada: o app roda só no Streamlit Community Cloud, com os dados no git | aceita |
