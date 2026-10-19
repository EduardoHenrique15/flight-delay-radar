"""Traduções da página Sobre o modelo (app/paginas/sobre.py)."""

TEXTOS = {
    # Cabeçalho e como funciona
    "Como a previsão é feita, quanto ela acerta e onde ela erra": (
        "How the prediction works, how often it is right and where it goes wrong"
    ),
    "Um LightGBM treinado com os voos nacionais regulares, validado sempre no futuro e comparado "
    "com um baseline simples. Todos os números abaixo vêm dos arquivos gerados pelo pipeline.": (
        "A LightGBM trained on scheduled domestic flights, always validated on future data and "
        "compared with a simple baseline. Every number below comes from the files the pipeline "
        "generates."
    ),
    "Algoritmo": "Algorithm",
    "Voos no treino": "Training flights",
    "Teste": "Test",
    "{inicio} a {fim}": "{inicio} to {fim}",
    "Como funciona": "How it works",
    "O que prevê": "What it predicts",
    "A chance de um voo nacional regular partir com mais de 15 minutos de atraso.": (
        "The chance that a scheduled domestic flight departs more than 15 minutes late."
    ),
    "Com o quê": "With what",
    "Companhia, rota, data, hora, feriados e o histórico de atrasos até 2 meses antes do voo. Um "
    "teste garante que nada do futuro entra.": (
        "Airline, route, date, hour, holidays and the delay history up to 2 months before the "
        "flight. A test guarantees that nothing from the future leaks in."
    ),
    "Treino": "Training",
    "{voos} voos, de {inicio} a {fim}. Escolhido em 5 janelas de validação, contra o baseline e "
    "uma regressão logística.": (
        "{voos} flights, from {inicio} to {fim}. Chosen over 5 validation windows, against the "
        "baseline and a logistic regression."
    ),
    "{periodo}, {voos} voos, usado uma única vez, depois de todas as escolhas.": (
        "{periodo}, {voos} flights, used only once, after every choice was made."
    ),
    # Resultado no teste
    "IC 95%: {baixo} a {alto}": "95% CI: {baixo} to {alto}",
    "Resultado no teste": "Test results",
    "O baseline é a taxa histórica de atraso da rota no horário (PR-AUC {baseline} no teste). O "
    "ganho do modelo é de {ganho}, com intervalo de 95% de {baixo} a {alto}: pequeno, mas "
    "consistente.": (
        "The baseline is the route's historical delay rate at that hour (PR-AUC {baseline} on "
        "the test). The model's gain is {ganho}, with a 95% interval from {baixo} to {alto}: "
        "small, but consistent."
    ),
    "{ganho} sobre o baseline · {intervalo}": "{ganho} over the baseline · {intervalo}",
    "Chance de um voo que atrasou receber risco maior que um que não atrasou.": (
        "The chance that a delayed flight gets a higher risk than one that was not delayed."
    ),
    "Calibração (ECE)": "Calibration (ECE)",
    "a probabilidade prevista bate com a taxa real": (
        "the predicted probability matches the actual rate"
    ),
    "Top 10% de risco": "Top 10% risk",
    "atrasaram · {lift}x a média · baseline {baseline}": (
        "were delayed · {lift}x the average · baseline {baseline}"
    ),
    "Dos 10% de voos com maior risco previsto, a parcela que atrasou de verdade.": (
        "Of the 10% of flights with the highest predicted risk, the share that was actually "
        "delayed."
    ),
    "Intervalos de 95% por bootstrap pareado por dia.": (
        "95% intervals from a bootstrap paired by day."
    ),
    "O que mais pesa nas previsões": "What weighs most in the predictions",
    "Efeito médio de cada tema na chance de atraso, em pontos percentuais (SHAP).": (
        "Average effect of each theme on the chance of delay, in percentage points (SHAP)."
    ),
    "Pontos percentuais": "Percentage points",
    "Tema": "Theme",
    "Efeito": "Effect",
    "Probabilidade prevista contra a taxa real": "Predicted probability vs. actual rate",
    "No teste, por faixas de risco. Na diagonal, o previsto bate com o real.": (
        "On the test, by risk band. On the diagonal, predicted matches actual."
    ),
    "Prevista pelo modelo": "Predicted by the model",
    "Taxa real de atraso": "Actual delay rate",
    "Faixa": "Band",
    "Prevista": "Predicted",
    "Real": "Actual",
    "Voos": "Flights",
    "Acima da diagonal, o modelo subestima o risco: acontece nas faixas altas.": (
        "Above the diagonal, the model underestimates the risk: this happens in the high bands."
    ),
    # Onde o modelo erra
    "Onde o modelo erra": "Where the model goes wrong",
    "O mesmo teste, separado por grupos. O PR-AUC muda com a taxa de atraso de cada grupo; por "
    "isso, compare o modelo com o baseline na mesma linha, e não uma linha com a outra.": (
        "The same test, split into groups. PR-AUC changes with each group's delay rate, so "
        "compare the model with the baseline on the same row, not one row with another."
    ),
    "Separar por": "Split by",
    "Horário": "Time of day",
    "Madrugada (0h-5h)": "Overnight (0h-5h)",
    "Manhã (6h-11h)": "Morning (6h-11h)",
    "Tarde (12h-17h)": "Afternoon (12h-17h)",
    "Noite (18h-23h)": "Evening (18h-23h)",
    "acima": "above",
    "abaixo": "below",
    "O modelo supera o baseline em <b>todos os {grupos} grupos</b> deste recorte.": (
        "The model beats the baseline in <b>all {grupos} groups</b> of this split."
    ),
    "O modelo supera o baseline em {venceu} de {grupos} grupos; em {nomes}, não.": (
        "The model beats the baseline in {venceu} of {grupos} groups; in {nomes}, it does not."
    ),
    "O maior erro de calibração é em <b>{grupo}</b>: previu {previsto} de atrasos, e foram {real} "
    "(a previsão ficou {pontos} p.p. {sentido} do real).": (
        "The largest calibration error is in <b>{grupo}</b>: it predicted {previsto} delays, "
        "and there were {real} (the prediction was {pontos} p.p. {sentido} the actual rate)."
    ),
    "Acerto em cada grupo": "Accuracy in each group",
    "PR-AUC do modelo e do baseline (maior é melhor).": (
        "PR-AUC of the model and of the baseline (higher is better)."
    ),
    "Atrasos previstos contra os reais": "Predicted vs. actual delays",
    "A taxa média prevista pelo modelo e a taxa real de atraso no grupo.": (
        "The model's average predicted rate and the group's actual delay rate."
    ),
    "Voos com mais de 15 min de atraso": "Flights delayed more than 15 min",
    "Modelo": "Model",
    "Baseline": "Baseline",
    "Previsto": "Predicted",
    "Grupo": "Group",
    "Valor": "Value",
    "Voos no teste": "Flights in the test",
    "Só grupos com pelo menos {minimo} voos no teste; aeroportos: os 10 com mais partidas.": (
        "Only groups with at least {minimo} flights in the test; airports: the 10 with the most "
        "departures."
    ),
    # Usar o modelo na prática
    "Usar o modelo na prática": "Using the model in practice",
    "Uma regra simples: avisar os passageiros dos voos com maior risco previsto. Quanto mais voos "
    "avisados, mais atrasos o aviso pega, mas mais avisos são alarme falso.": (
        "A simple rule: alert the passengers on the flights with the highest predicted risk. "
        "The more flights alerted, the more delays the alert catches, but the more alerts are "
        "false alarms."
    ),
    "Falta o models/uso_pratico.json: rode python -m fdr.pipeline --stage pratica.": (
        "models/uso_pratico.json is missing: run python -m fdr.pipeline --stage pratica."
    ),
    "Avisar os voos de maior risco (% de todos os voos)": (
        "Alert the highest-risk flights (% of all flights)"
    ),
    "Voos avisados": "Flights alerted",
    "de {voos} no teste · chance a partir de {limiar}": (
        "of {voos} in the test · chance from {limiar}"
    ),
    "Atrasaram, dos avisados": "Delayed, among those alerted",
    "{lift}x a média ({media}) · baseline {baseline}": (
        "{lift}x the average ({media}) · baseline {baseline}"
    ),
    "A precisão do aviso: dos voos avisados, a parcela que atrasou de verdade.": (
        "The alert's precision: of the flights alerted, the share that was actually delayed."
    ),
    "Atrasos pegos": "Delays caught",
    "de {atrasos} atrasos · baseline {baseline}": "of {atrasos} delays · baseline {baseline}",
    "A cobertura do aviso: dos voos que atrasaram, a parcela que foi avisada.": (
        "The alert's recall: of the flights that were delayed, the share that was alerted."
    ),
    "Alarmes falsos": "False alarms",
    "dos avisos, o voo saiu no horário": "of the alerts, the flight left on time",
    "Avisando os <b>{porcento}%</b> de voos com maior risco, <b>{precisao}</b> deles atrasaram, "
    "{lift} vezes a média, e o aviso pegou <b>{cobertura}</b> de todos os atrasos. Em troca, "
    "{alarmes} dos avisos seriam alarme falso. Com o baseline, a mesma regra pega "
    "{cobertura_base} dos atrasos.": (
        "Alerting the <b>{porcento}%</b> of flights with the highest risk, <b>{precisao}</b> of "
        "them were delayed, {lift} times the average, and the alert caught <b>{cobertura}</b> "
        "of all delays. In exchange, {alarmes} of the alerts would be false alarms. With the "
        "baseline, the same rule catches {cobertura_base} of the delays."
    ),
    "Quantos atrasos o aviso pega": "How many delays the alert catches",
    "A curva de ganho no teste. Avisar ao acaso pega a mesma parcela dos atrasos que a de voos "
    "avisados (a linha tracejada).": (
        "The gain curve on the test. Alerting at random catches the same share of delays as the "
        "share of flights alerted (the dashed line)."
    ),
    "Voos avisados (os de maior risco)": "Flights alerted (the highest-risk ones)",
    "Ao acaso": "At random",
    "Série": "Series",
    "Do teste, usado uma única vez. Sem clima e sem a rotação do avião, o modelo erra muitos "
    "atrasos: serve para priorizar, não para garantir.": (
        "From the test, used only once. Without weather or aircraft rotation, the model misses "
        "many delays: it is for prioritizing, not for guaranteeing."
    ),
    # Limitações
    "Limitações": "Limitations",
    "Sem clima": "No weather",
    "O VRA não traz o tempo, uma das maiores causas de atraso.": (
        "VRA has no weather data, one of the main causes of delay."
    ),
    "Sem a rotação do avião": "No aircraft rotation",
    "O atraso do voo anterior do mesmo avião não entra; a posição do voo no dia da companhia é só "
    "uma aproximação.": (
        "The delay of the same aircraft's previous flight is not used; the flight's position in "
        "the airline's day is only an approximation."
    ),
    "Risco alto subestimado": "High risk underestimated",
    "Nas faixas de maior risco a taxa real passa da prevista, e companhias pequenas têm mais "
    "erro.": (
        "In the highest-risk bands the actual rate exceeds the predicted one, and small airlines "
        "have more error."
    ),
    "Só atraso": "Delays only",
    "Cancelados ficam de fora. Não serve para garantir um voo, ranquear companhias ou pedir "
    "indenização.": (
        "Cancellations are left out. It is not for guaranteeing a flight, ranking airlines or "
        "claiming compensation."
    ),
    # Quem fez e links
    "Quem fez": "Who built it",
    "Projeto pessoal, de ponta a ponta: o download dos dados da ANAC, o warehouse com testes de "
    "qualidade, o modelo validado no tempo, o monitoramento com regra de retreino, o assistente "
    "com IA e este app.": (
        "A personal end-to-end project: the download of ANAC's data, the warehouse with quality "
        "tests, the model validated over time, the monitoring with a retraining rule, the AI "
        "assistant and this app."
    ),
    "Aberto a vagas em Ciência de Dados, Machine Learning e IA": (
        "Open to roles in Data Science, Machine Learning and AI"
    ),
    "Falar comigo no LinkedIn": "Talk to me on LinkedIn",
    "Outros projetos no GitHub": "Other projects on GitHub",
    "Para saber mais": "Learn more",
    "Decisões (ADRs)": "Decisions (ADRs)",
    "Os dados da ANAC": "ANAC's data",
}
