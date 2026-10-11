# Dados: o que a Fase 0 descobriu sobre o VRA

Reconhecimento feito em 10/10/2026 com 6 arquivos mensais do VRA (Voo Regular Ativo) da ANAC.
O passo a passo e as tabelas completas estão em `notebooks/00_reconhecimento.ipynb`.

| Arquivo | Mês | Linhas | Duplicatas exatas |
| --- | --- | --- | --- |
| `VRA_20221.csv` | janeiro de 2022 | 73.465 | 0 |
| `VRA_20236.csv` | junho de 2023 | 79.762 | 0 |
| `VRA_20265.csv` | maio de 2026 | 82.120 | 18 |
| `VRA_20266.csv` | junho de 2026 | 81.119 | 0 |
| `VRA_20267.csv` | julho de 2026 | 89.499 | 11 |
| `VRA_20268.csv` | agosto de 2026 | 88.064 | 44 |

## 1. Onde estão os arquivos

- Diretório: https://sistemas.anac.gov.br/dadosabertos/, pasta "Voos e operações aéreas" >
  "Voo Regular Ativo (VRA)".
- Nome: `VRA_<ano><mês sem zero à esquerda>.csv`. Exemplos: `VRA_20221.csv` é janeiro de 2022 e
  `VRA_20236.csv` é junho de 2023. Ainda falta ver um mês de 10 a 12 para confirmar o padrão
  `VRA_202510.csv`.
- Não achamos dicionário de dados na pasta. As dúvidas da seção 5 ficam em aberto.

## 2. Formato do arquivo

O formato é **o mesmo nos 6 meses, de janeiro de 2022 a agosto de 2026**. Não há versões de layout
diferentes para mapear.

- UTF-8 com BOM e quebras de linha CRLF.
- Linha 1: metadado `Atualizado em: AAAA-MM-DD`, que precisa ser pulada. O cabeçalho vem na linha 2.
- Separador `;`, todos os campos entre aspas duplas.
- Ausentes: `null` nas datas e `N/A` na justificativa.
- Datas em `AAAA-MM-DD HH:MM:SS`. **Só os meses de 2026** trazem, em cerca de 8% das linhas, sufixo
  de nanossegundos (`.100000000`). Janeiro de 2022 e junho de 2023 não trazem. Cortar nos 19
  primeiros caracteres funciona para os dois casos.
- Nenhuma data inválida depois desse corte.

## 3. Dicionário das colunas

| Coluna original | Nome no projeto | Tipo | Observações |
| --- | --- | --- | --- |
| `ICAO Empresa Aérea` | `cia` | texto | 68 a 80 companhias por mês |
| `Número Voo` | `numero_voo` | texto | manter como texto (`0084`, `Z5134`) |
| `Código Autorização (DI)` | `di` | texto | `0` = regular (cerca de 96%); também `1`–`4`, `6`, `7`, `9`, `D`, `E` |
| `Código Tipo Linha` | `tipo_linha` | texto | `N`, `I`, `C`, `G` em todos os meses; `X` só em 2022 e 2023 |
| `ICAO Aeródromo Origem` | `origem` | texto | 241 a 254 aeródromos por mês |
| `ICAO Aeródromo Destino` | `destino` | texto | |
| `Partida Prevista` | `partida_prevista` | data e hora | `null` em 2.243 a 2.777 linhas por mês, nunca com DI = `0` |
| `Partida Real` | `partida_real` | data e hora | `null` em todos os cancelados e "NÃO INFORMADO" |
| `Chegada Prevista` | `chegada_prevista` | data e hora | |
| `Chegada Real` | `chegada_real` | data e hora | |
| `Situação Voo` | `situacao` | texto | `REALIZADO`, `CANCELADO` e, em 2022 e 2023, `NÃO INFORMADO` |
| `Código Justificativa` | `justificativa` | texto | **100% `N/A` nos 6 meses** |

Não existe matrícula da aeronave.

## 4. Descobertas

### 4.1 Os arquivos antigos são regerados a cada publicação

Os 6 arquivos, inclusive janeiro de 2022, têm a mesma linha `Atualizado em: 2026-10-07`. A ANAC
regera a série inteira a cada publicação, e qualquer mês antigo pode mudar.

### 4.2 Defasagem de publicação: 2 meses

Em 10/10/2026, setembro de 2026 ainda não tinha saído e agosto estava publicado desde 07/10.
**L = 2**, como a especificação supunha.

### 4.3 Justificativas nunca preenchidas

`Código Justificativa` é `N/A` em 100% das linhas dos 6 meses, de 2022 a 2026.

### 4.4 Situação "NÃO INFORMADO"

Existe só em janeiro de 2022 (62 voos) e junho de 2023 (53 voos). Esses voos têm partida prevista,
mas não têm partida real: não dá para saber se voaram nem se atrasaram. A maioria é nacional com
DI = `0` (24 em janeiro de 2022 e 49 em junho de 2023).

### 4.5 Tipo de linha `X`

Existe só em 2022 (491 voos) e 2023 (649 voos), e não aparece nos meses de 2026. É uma mistura de
voos internacionais e cargueiros (ARG, LAE, ETH, LCO, GTI). Não afeta o modelo, que usa só `N`.

### 4.6 Bordas do mês

- O arquivo de um mês traz de 15 a 33 voos com partida prevista **depois** do fim do mês, até
  36 horas depois. Nenhum vem com partida prevista antes do início do mês.
- Os voos nacionais (`N`) nunca passam de 6 horas depois da virada. Os que vão além disso são todos
  internacionais (`I`) ou cargueiros (`G`).
- Um mesmo voo apareceu em dois arquivos: GLO 9610 (tipo `C`, partida prevista 01/08/2026 01:05)
  está em julho e em agosto, com os mesmos horários.

### 4.7 Duplicatas e chave do voo

- Duplicatas exatas existem só nos meses de 2026 (18, 0, 11 e 44 de maio a agosto). Em agosto, todas
  são de voos `I` e `G`.
- A combinação companhia + número do voo + partida prevista + origem + destino + DI **não é única**.
  Há poucas linhas em conflito: mesmo voo, mesma partida prevista e partidas reais diferentes (por
  exemplo AAL 0905 em maio de 2026). São todas de voos `I` e `C`, nenhuma de `N`.

### 4.8 Atrasos extremos

| Mês | Menor atraso (min) | Maior atraso (min) | Fora de −120 a 1.440 min |
| --- | --- | --- | --- |
| jan/2022 | −2.040 | 4.739 | 0,32% |
| jun/2023 | −1.468 | 4.309 | 0,16% |
| mai/2026 | −4.348 | 2.865 | 0,05% |
| jun/2026 | −1.453 | 3.894 | 0,05% |
| jul/2026 | −1.191 | 3.706 | 0,06% |
| ago/2026 | −1.444 | 4.548 | 0,07% |

A quarentena fica bem abaixo do limite de 2%.

### 4.9 Números de referência de agosto de 2026: reproduzidos

Recorte: voos realizados, com partida prevista e real, sem duplicatas exatas.

| Recorte | Voos | > 15 min | > 30 min | > 60 min |
| --- | --- | --- | --- | --- |
| Nacional (`N`) | 67.782 | 15,7% | 7,5% | 2,5% |
| Nacional regular (`N`, DI = `0`): base do modelo | 67.241 | 15,7% | 7,5% | 2,5% |
| Internacional (`I`) | 13.452 | 26,0% | 14,6% | 6,2% |
| LATAM (TAM), nacional | 23.588 | 21,0% | | |
| Azul (AZU), nacional | 22.969 | 11,5% | | |
| Gol (GLO), nacional | 19.984 | 14,7% | | |

Cancelamentos em voos nacionais: 1,6%.

### 4.10 Panorama dos 6 meses

| Mês | Voos (base do modelo) | > 15 min (base do modelo) | > 15 min (internacional) | Cancelados (nacional) |
| --- | --- | --- | --- | --- |
| jan/2022 | 58.501 | 15,4% | 28,9% | 3,7% |
| jun/2023 | 61.124 | 14,5% | 28,7% | 3,7% |
| mai/2026 | 63.393 | 13,3% | 22,3% | 1,4% |
| jun/2026 | 61.913 | 17,4% | 23,5% | 2,0% |
| jul/2026 | 67.005 | 14,5% | 26,0% | 1,7% |
| ago/2026 | 67.241 | 15,7% | 26,0% | 1,6% |

- A taxa de atraso da base do modelo varia de 13,3% a 17,4% entre meses vizinhos, o que dá sinal
  para o monitoramento mensal.
- Os cancelamentos em 2022 e 2023 são mais que o dobro dos de 2026. Pode ser mudança real ou de
  critério de registro. Vale olhar a série completa na Fase 2.
- A ordem das companhias muda: em janeiro de 2022 a TAM era a mais pontual (12,8%); em 2026 é a que
  mais atrasa (16,3% a 21,5%).

### 4.11 Fuso horário

- A hora com menos partidas nacionais é sempre a 1 h da manhã, nos 6 meses. Em UTC, o vale cairia
  por volta das 4 h. Isso confirma o **horário de Brasília**.
- A duração prevista mediana é de 235 minutos de Guarulhos para Manaus e também de 235 minutos de
  Manaus para Guarulhos. No horário local de cada aeroporto, a diferença seria de cerca de 2 horas.
  Os dois lados estão no mesmo fuso.

## 5. Dúvidas em aberto

Sem o dicionário de dados da ANAC, estes significados continuam sendo inferências a partir dos dados:

- `Código Tipo Linha`: `C` parece fretamento ou voo complementar (GLO, AZU, SID, TTL); `G` parece
  cargueiro (LTG, QTR, LCO, GTI, TPA); `X` (só até 2023) é misto, internacional e carga.
- `Código Autorização (DI)`: só sabemos que `0` é o voo regular. Os outros códigos ficam fora do
  modelo de qualquer jeito.
- Fuso: horário de Brasília, inferido pelos dados (seção 4.11).

Nada disso bloqueia a Fase 1, porque o modelo usa só `N` com DI = `0`.

## 6. Decisões tomadas

1. **Um único layout** na staging, sem mapeamento por versão. Se um arquivo vier com cabeçalho
   diferente, a carga falha com uma mensagem clara.
2. **Recarregar a janela inteira a cada mês**, e não só o mês novo, porque a ANAC regera a série
   (seção 4.1). A carga guarda a data "Atualizado em" e o hash de cada arquivo, e só recarrega o que
   mudou.
3. **Mês do voo = mês do arquivo da ANAC.** Usar o mês da partida prevista criaria "meses" com
   poucas dezenas de voos (por exemplo, setembro de 2026 a partir dos voos de 1º de setembro que
   vêm no arquivo de agosto). A partida prevista pode passar até **48 horas** da virada; o que
   passar disso vai para a quarentena. Os voos `N` ficam todos dentro de 6 horas.
4. **Duplicatas removidas também entre arquivos**: se o mesmo voo aparece em dois meses, fica uma
   linha só, a do arquivo mais recente.
5. **Chave do voo**: hash de todas as colunas originais, porque a combinação natural não é única.
   Linhas com a mesma combinação natural e horários reais diferentes vão para a quarentena com o
   motivo "conflito de chave". Isso não afeta nenhum voo `N` nos 6 meses.
6. **"NÃO INFORMADO"** entra em `accepted_values` como terceira situação. Esses voos ficam fora do
   alvo (não são nem realizados nem cancelados) e são contados à parte.
7. **Justificativas fora do app**: a análise de motivos sai da página de Pontualidade e vira uma
   limitação no README e no `docs/modelo.md`.
8. **Voos sem partida prevista não vão para a quarentena.** São 2.200 a 2.800 por mês (cerca de 3%),
   todos com DI diferente de `0`: voos extras, sem horário programado. Não são erro de dado, e
   colocá-los na quarentena estouraria o limite de 2% todo mês. Eles ficam em `fct_flights`, sem
   atraso calculado, e não entram no modelo, que usa só DI = `0`.

## 7. Diferenças em relação ao `PROJETO.md` (versão 2.1)

| Seção | O que dizia | O que os dados mostraram | Ajuste |
| --- | --- | --- | --- |
| 3.1 | Confirmar se outros meses seguem o layout de agosto | Mesmo layout de 2022 a 2026 | Sem mapeamento por versão |
| 3.1 | Confirmar se meses antigos são reatualizados | Todos os arquivos com a mesma data de atualização | Recarregar a janela inteira (decisão 2) |
| 3.1 | Nanossegundos em cerca de 7,5% das linhas | Só nos meses de 2026 | Nenhum: o corte em 19 caracteres serve para todos |
| 3.1 | Situação: `REALIZADO`, `CANCELADO` | Também `NÃO INFORMADO` em 2022 e 2023 | Decisão 6 |
| 3.1 | Tipo de linha: `N`, `I`, `G`, `C` | Também `X` em 2022 e 2023 | Só registrar |
| 3.1.1 | Conferir se algum mês tem justificativas | 100% `N/A` nos 6 meses | Decisão 7 |
| 3.4 | Fuso provavelmente de Brasília | Confirmado pelos dados nos 6 meses | Sem ajuste |
| 5.2 | Tolerância de 6 h na virada do mês | Voos `I` e `G` até 36 h depois | Tolerância de 48 h (decisão 3) |
| 3.4 | Partida real sem partida prevista vai para a quarentena | São voos extras (DI ≠ 0), cerca de 3% do mês | Ficam fora da quarentena (decisão 8) |
| 5.2 | "Nenhuma duplicata depois da limpeza" | Duplicatas também entre arquivos; chave natural não é única | Decisões 4 e 5 |
| 6.3 | L = 2, a confirmar | Setembro ainda não saiu em 10/10/2026 | L = 2 confirmado |
