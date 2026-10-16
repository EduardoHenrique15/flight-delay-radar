# ADR 006: regra de retreino e campeão contra desafiante

- **Situação:** aceita
- **Data:** 16/10/2026
- **Código:** `src/fdr/monitoring/monthly.py` e `src/fdr/monitoring/drift.py`. O histórico fica
  em `monitoring/history.json`.

## Contexto

A cada mês a ANAC publica um mês novo, com cerca de 2 meses de atraso. O modelo precisa ser
avaliado nesse mês, que ele não viu, e retreinado quando piorar. A especificação propunha
retreinar quando "a PR-AUC do mês cair mais de 10% em relação à média do teste".

O problema dessa regra é que a PR-AUC depende da taxa de atraso do mês. Na validação, a PR-AUC
do próprio baseline foi de 0,178 (mar a mai/2025, 12,5% de atrasos) a 0,310 (dez/2025 a
fev/2026, 20,0% de atrasos), sem que nada mudasse no modelo. Uma regra baseada na PR-AUC sozinha
dispararia à toa nos meses de pouco atraso e deixaria passar problemas nos meses de muito
atraso.

## Decisão

O retreino dispara (decisão do Eduardo em 16/10/2026) quando acontece qualquer uma destas
situações:

1. **O modelo perde do baseline no mês:** o ganho de PR-AUC sobre a taxa histórica da rota no
   horário fica abaixo de zero. Os dois são medidos no mesmo mês, então a taxa de atraso do mês
   afeta os dois do mesmo jeito.
2. **A calibração se perde:** o ECE passa de 5 p.p.
3. **Uma variável importante muda de distribuição:** PSI de 0,25 ou mais em uma das 5 variáveis
   de maior SHAP (`models/explicacao_global.json`). Faixas com menos de 100 voos não pesam no
   PSI.
4. **O modelo envelhece:** passaram 6 meses desde o último retreino.

**Campeão contra desafiante:**
- O desafiante é treinado com os dados até o mês M − 2, o que estaria publicado, e com as escolhas
  do ADR 005 (mesmos hiperparâmetros e 219 árvores).
- Ele só vira campeão se ganhar no mês novo com folga: o intervalo de 95% do ganho de PR-AUC,
  num bootstrap pareado por dia, precisa ficar acima de zero.
- Com ou sem promoção, o contador de meses volta a zero.

**Histórico retroativo:**
- Um campeão "da época" é treinado com os dados até out/2025.
- O processo roda mês a mês de dez/2025 a ago/2026 (9 meses), só com o que estaria publicado em
  cada mês.
- Os meses simulados ficam marcados como `simulacao`. Os meses publicados depois do modelo final
  da Fase 3 ficam em `producao`.

## Alternativas consideradas

1. **Queda da PR-AUC sobre o teste (a regra da especificação).** É sensível à taxa de atraso do
   mês, pelo motivo explicado no contexto.
2. **Queda da ROC-AUC.** Ela não depende da taxa de atraso, mas não diz se o modelo ainda vale a
   pena em relação à regra simples, que é a pergunta que interessa.
3. **Promover o desafiante sempre que tiver PR-AUC maior.** Num mês só (cerca de 65 mil voos),
   diferenças pequenas são ruído, e o modelo trocaria de um lado para o outro.
4. **Refazer a busca de hiperparâmetros a cada retreino.** Leva de 20 a 60 minutos e mudaria
   pouco. Ela fica para quando o desempenho cair de forma persistente.

## Consequências

- O monitoramento só mede o mês 2 meses depois de ele acontecer, porque os atrasos reais só saem
  com a publicação da ANAC.
- Se um desafiante for promovido em produção, `models/model.txt`, `metadata.json` e
  `reference_profile.json` são atualizados. A mudança fica visível no PR do pipeline mensal
  (Fase 6).
- Os meses simulados usaram hiperparâmetros escolhidos com dados até mai/2026. Ainda assim, cada
  treino e cada avaliação respeitam o que estaria publicado no mês.
