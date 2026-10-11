# ADR 003: regra contra vazamento (as-of), defasagem de publicação e início do treino

- **Situação:** aceita
- **Data:** 11/10/2026

## Contexto

As variáveis históricas (taxa de atraso da rota, da companhia, do aeroporto) são as mais
informativas. Elas também são as mais perigosas: se usarem dados que não existiriam no momento
da previsão, o modelo parece ótimo na avaliação e falha de verdade.

O ponto central é a **defasagem de publicação da ANAC**. Em 10/10/2026, o mês mais recente
publicado era agosto de 2026, com data de 07/10/2026, e setembro ainda não tinha saído
(`docs/dados.md`, seção 4.2). Ou seja: no começo de um mês M, conhecemos os voos só até o fim do
mês M − 2.

## Decisão

1. **Mês de corte = M − 2.** As variáveis históricas de um voo do mês M usam só os voos com mês
   até M − 2 (`DEFASAGEM_PUBLICACAO_MESES` em `src/fdr/config.py`). Os meses M − 1 e M nunca
   entram.
2. **Janelas de 3 e 12 meses terminando no corte**, nos grãos rota x hora local, companhia,
   aeroporto de origem e país. Cada taxa vem acompanhada do número de voos que a sustenta.
3. **A regra é implementada em SQL** (`src/fdr/features/build.py`) e provada por
   `tests/test_no_leakage.py`: atrasos enormes colocados nos meses M − 1 e M não mudam as
   variáveis de M, enquanto uma mudança no mês de corte muda. Quebrar a regra de propósito (usar
   o histórico até o próprio mês M) faz 3 dos 5 testes falharem.
4. **Os exemplos de treino começam em janeiro de 2023** (decisão do Eduardo em 11/10/2026). O ano
   de 2022 entra só como histórico. Assim, todo voo de treino tem 12 meses completos de
   histórico, e os meses de fevereiro a abril de 2022, ainda afetados pela pandemia
   (`001-janela-de-dados.md`), não viram exemplo de treino.

Na série completa, 92,43% dos voos da base do modelo têm histórico da mesma rota e hora nos 12
meses até o corte. Os demais são rotas ou horários novos, e os primeiros meses de 2022, que não
têm histórico.

## Alternativas consideradas

1. **Defasagem de 1 mês.** Daria variáveis mais frescas, mas em produção o mês M − 1 ainda não
   está publicado no começo do mês M. A avaliação ficaria otimista.
2. **Começar os exemplos em março de 2022** (o primeiro mês com algum histórico). Mais exemplos,
   mas com histórico curto e ainda no período afetado pela pandemia.
3. **Variáveis com janela móvel diária.** O VRA é publicado por mês, então o dado diário só existe
   depois do mês fechado. Não ganharia nada em relação ao corte mensal.

## Consequências

- Em produção, o corte de um voo futuro é o mais recente entre M − 2 e o último mês publicado. Se
  a ANAC atrasar mais a publicação, as variáveis ficam mais antigas, mas nunca vazam.
- A ANAC regera a série inteira a cada publicação (`docs/dados.md`, seção 4.1). Por isso a
  avaliação usa a versão atual dos meses antigos, e não exatamente o que estava publicado na
  época. É uma limitação pequena, já que as diferenças entre versões tendem a ser correções
  pontuais.
- O baseline e os modelos da Fase 3 usam a mesma tabela `features_voos`, com a mesma regra.
