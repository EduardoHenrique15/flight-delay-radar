# ADR 004: DuckDB e dbt, em vez de um banco PostgreSQL

- **Situação:** aceita
- **Data:** 18/10/2026
- **Código:** `dbt/` (modelos e testes de qualidade), `src/fdr/ingest/` (carga) e
  `src/fdr/export.py` (exportação para o app).

## Contexto

O VRA chega em arquivos CSV mensais, com alguns milhões de voos desde 2022. O pipeline precisa:
- carregar esses arquivos, limpar e testar os dados;
- montar as tabelas do modelo e do app;
- rodar igual no computador do Eduardo, no CI e no workflow mensal do GitHub Actions;
- caber num app gratuito com cerca de 1 GB de memória.

O projeto não tem servidor nem orçamento. Ninguém escreve no banco além do próprio pipeline, e a
base é atualizada uma vez por mês.

## Decisão

1. **DuckDB como warehouse:** um arquivo (`data/warehouse.duckdb`), sem servidor. Ele lê CSV e
   Parquet direto e roda consultas analíticas em colunas, rápido o bastante para a base inteira
   num notebook comum.
2. **dbt para as transformações:** as camadas staging, intermediate e marts ficam em SQL
   versionado, com testes de qualidade (unicidade, valores aceitos, faixas de atraso, volume
   mensal e os números de referência de agosto de 2026). Se um teste falha, o pipeline para e
   o mês não entra no app.
3. **Parquet para o app:** só os 24 meses mais recentes vão para `data/marts/`, em Parquet
   compactado, consultados pelo DuckDB sob demanda. O banco do assistente (`data/app.duckdb`) é
   recriado pelo app a partir desses arquivos.

## Alternativas consideradas

1. **PostgreSQL (local ou na nuvem).** Exige um servidor rodando e uma conexão segura no app e no
   CI. A base cabe num arquivo, e o acesso é só leitura: o servidor não traz ganho.
2. **Só pandas, sem banco.** Ler milhões de linhas no pandas a cada etapa usa muita memória, e as
   regras (as-of, quarentena, agregações) ficam espalhadas em código Python, sem os testes de
   dados do dbt.
3. **BigQuery ou outro warehouse na nuvem.** Custo, credenciais no CI e dependência de conta
   externa, para um volume que o DuckDB resolve localmente.

## Consequências

- O pipeline inteiro roda com `python -m fdr.pipeline`, sem nada instalado além do Python.
- O CI roda o mesmo dbt build na amostra de `data/fixtures/`, e os testes de dados valem para
  qualquer mês novo.
- Um arquivo DuckDB aceita um escritor por vez. Não é problema aqui, porque só o pipeline escreve.
- O formato interno do DuckDB muda entre versões. Por isso o app recebe Parquet, que é estável, e
  não o arquivo do warehouse.
