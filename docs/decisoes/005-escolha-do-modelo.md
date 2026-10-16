# ADR 005: escolha do modelo final, da calibração e do número de árvores

- **Situação:** aceita
- **Data:** 16/10/2026
- **Dados:** `models/metrics.json`, seções `validacao_modelos` e `modelo_final`.

## Contexto

Três candidatos foram comparados nas 5 janelas da validação no tempo (mar/2025 a mai/2026):

- o baseline (taxa histórica da rota no horário);
- a regressão logística;
- o LightGBM.

O teste (jun a ago/2026) só podia ser usado uma vez, então todas as escolhas precisavam ser
travadas antes dele.

## Decisão

1. **Regra de 1 erro-padrão, pareada.** Fica o modelo mais simples (baseline, depois logística,
   depois LightGBM) cuja PR-AUC média esteja a menos de 1 erro-padrão da melhor.
   - O erro-padrão é o da **diferença** entre os dois modelos, janela a janela.
   - Motivo: a taxa de atraso muda muito entre as janelas (dezembro a fevereiro: 20,0%; março
     a maio: de 12,5% a 14,1%), e a PR-AUC de todos os modelos sobe e desce junto com ela. O
     erro-padrão de cada modelo sozinho mediria essa variação comum e faria o modelo mais simples
     ganhar quase sempre.
   - Resultado: o LightGBM (0,262) ganhou da logística (0,256) por 0,0059, mais que o
     erro-padrão da diferença (0,0043). Sobre o baseline (0,231), ganhou por 0,030, com
     erro-padrão de 0,010.
2. **Hiperparâmetros do LightGBM:** busca em 8 combinações na última janela da validação.
   Venceu `num_leaves` = 127, `min_child_samples` = 100 e `learning_rate` = 0,05.
3. **Número de árvores: a mediana das 5 janelas (219).** Cada janela define as suas árvores por
   parada antecipada nos 3 últimos meses do próprio treino, com paciência de 150 rodadas. A
   primeira versão usava só 1 mês e paciência de 50, e o número de árvores variou de 7 a 485:
   o sinal era instável. Com a correção, ficou entre 16 e 528, e a mediana (219) coincidiu com a
   da validação principal. O treino final usa 219 árvores fixas, sem parada antecipada.
4. **Calibração: nenhuma.** A calibração isotônica e a de Platt foram ajustadas fora do tempo:
   em cada janela, o calibrador aprende com as janelas anteriores. Nenhuma das duas melhorou o
   Brier do LightGBM (crua 0,1234, isotônica 0,1247, Platt 0,1245).
5. **Formato do modelo:** `models/model.txt`, o formato nativo do LightGBM, em vez de `joblib`
   (pickle). O arquivo não executa código ao ser aberto e não prende o app à versão do
   scikit-learn.
6. **Explicação:** o SHAP vem do próprio LightGBM (`pred_contrib=True`, o mesmo TreeSHAP da
   biblioteca `shap`), somado por tema. Assim o deploy não precisa de mais uma dependência.

## Alternativas consideradas

1. **Erro-padrão de cada modelo, sem parear.** Seria a regra mais comum, mas aqui o baseline
   ficaria "dentro de 1 erro-padrão" mesmo perdendo em todas as janelas.
2. **Árvores da validação principal** em vez da mediana. Neste caso deu o mesmo número (219).
   A mediana foi escolhida antes, por ser mais estável.
3. **Parada antecipada na própria janela de validação.** Inflaria a nota da validação usada na
   comparação.

## Consequências

- **Viés conhecido:** a busca de hiperparâmetros usou a janela 5, que também entra na média da
  comparação. O viés favorece um pouco o LightGBM. Ainda assim, ele também ganhou nas janelas 2
  e 4, e no teste, que nenhuma escolha usou, venceu o baseline com intervalo pareado acima de
  zero: PR-AUC +0,029 (IC 95%: +0,019 a +0,041).
- **Calibração no teste:** no total, ela ficou boa (ECE 1,24 p.p.), mas o modelo subestima as
  probabilidades altas (`docs/modelo.md`, seção 6). O monitoramento da Fase 4 acompanha o ECE
  mês a mês.
- **Retreino:** para retreinar, rode de novo a validação, que refaz as escolhas, e depois o treino
  final.
