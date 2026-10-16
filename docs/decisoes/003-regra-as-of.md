# ADR 003: regra contra vazamento (as-of), defasagem de publicação e início do treino

- **Situação:** aceita (atualizada em 16/10/2026: seção "Atualização")
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
   o histórico até o próprio mês M) faz 3 dos 7 testes falharem.
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

## Atualização de 16/10/2026: variáveis da hora da previsão e intervalo de 1 mês

Uma revisão do projeto achou dois pontos em que a avaliação ficava mais fácil que a vida real.
O Eduardo aprovou as correções abaixo.

1. **Só entram no modelo variáveis que existem na hora da previsão.** Para um voo futuro, o app
   conhece a companhia, a rota, a data e a hora previstas e o histórico publicado. A malha do
   próprio mês (quantas partidas o aeroporto teve naquela hora, quanto durou cada voo
   programado) só é publicada junto com os atrasos, então saiu do modelo. No lugar dela entram
   versões típicas, calculadas com a mesma regra as-of:
   - partidas típicas por dia na origem, no mesmo dia da semana e hora (3 meses até o corte);
   - partidas típicas da mesma companhia na origem antes dessa hora (a posição do voo no dia);
   - duração programada típica da companhia na rota e a folga da programação (duração
     programada menos a real, 12 meses até o corte).

   A malha realizada continua na tabela, só para análise (`COLUNAS_SO_ANALISE` em
   `src/fdr/features/build.py`), e um teste garante que ela não entra no modelo.
2. **Sazonalidade:** taxa de atraso da rota, da origem e da companhia no mesmo mês do ano
   anterior (M − 12, sempre antes do corte). Ataca o ponto fraco do baseline em dezembro.
3. **Intervalo de 1 mês entre o treino e a avaliação** (`MESES_INTERVALO` em
   `src/fdr/config.py`). Quando o mês P é publicado, o calendário já está em P + 2: o modelo
   nunca prevê o mês logo depois do último rótulo que viu. Em cada janela de validação, o treino
   termina 2 meses antes do início da validação, e o treino final, avaliado no teste
   (jun a ago/2026), vai até abr/2026.
4. **Calendário na data local.** O dia da semana e os feriados usam a data no fuso do aeroporto
   de origem (`data_prevista_local`), a mesma referência da hora local.

`tests/test_no_leakage.py` cobre as variáveis novas: atrasos enormes nos meses M − 1 e M não
mudam nenhuma delas, e quebrar de propósito a regra da programação, da duração ou da
sazonalidade faz os testes falharem.
