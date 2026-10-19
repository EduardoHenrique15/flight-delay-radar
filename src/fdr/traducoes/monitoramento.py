"""Traduções da página Monitoramento (app/paginas/monitoramento.py)."""

TEXTOS = {
    "O modelo continua acertando?": "Is the model still getting it right?",
    "Cada mês publicado pela ANAC é um teste novo. O modelo é comparado com o baseline, a "
    "calibração é conferida e as variáveis são vigiadas. Quando uma regra dispara, um desafiante "
    "é treinado e só substitui o campeão se vencer com folga.": (
        "Each new month ANAC publishes is a new test. The model is compared with the baseline, its "
        "calibration is checked and its features are watched. When a rule fires, a challenger "
        "is trained, and it only replaces the champion if it wins by a clear margin."
    ),
    "Meses monitorados": "Months monitored",
    "Campeão atual": "Current champion",
    "treino até {mes}": "trained through {mes}",
    "Retreinos promovidos": "Retrainings promoted",
    "Ainda não há meses monitorados.": "No months monitored yet.",
    "De {inicio} a {fim}, uma simulação do passado: um modelo treinado só até {treino} foi "
    "avaliado mês a mês, sem olhar o futuro, com as mesmas regras de retreino de produção. Os "
    "meses seguintes entram pelo pipeline mensal.": (
        "From {inicio} to {fim}, a backtest: a model trained only through {treino} was evaluated "
        "month by month, without looking ahead, with the same retraining rules as production. "
        "Later months come in through the monthly pipeline."
    ),
    "PR-AUC em {mes}": "PR-AUC in {mes}",
    "{ganho} sobre o baseline": "{ganho} over the baseline",
    "Meses vencendo o baseline": "Months beating the baseline",
    "{vitorias} de {total}": "{vitorias} of {total}",
    "pela PR-AUC": "by PR-AUC",
    "Calibração (ECE)": "Calibration (ECE)",
    "limite para retreino: 5 p.p.": "retraining threshold: 5 p.p.",
    "Atraso real em {mes}": "Actual delays in {mes}",
    "previsto pelo modelo: {taxa}": "predicted by the model: {taxa}",
    "As linhas mostram cada mês monitorado. No segundo indicador, a linha é a diferença de "
    "PR-AUC entre o modelo e o baseline.": (
        "The lines show each monitored month. In the second indicator, the line is the PR-AUC "
        "difference between the model and the baseline."
    ),
    "Linha do tempo dos retreinos": "Retraining timeline",
    "O retreino dispara se o modelo perder do baseline no mês, se o ECE passar de {ece} p.p., "
    "se o PSI de uma variável importante passar de {psi} ou a cada {meses} meses. O desafiante "
    "só substitui o campeão se o ganho de PR-AUC tiver intervalo de 95% acima de zero.": (
        "Retraining fires if the model loses to the baseline in a month, if ECE goes above {ece} "
        "p.p., if the PSI of an important feature goes above {psi}, or every {meses} months. The "
        "challenger only replaces the champion if its PR-AUC gain has a 95% interval above zero."
    ),
    "treino do campeão": "champion trained",
    "promovido": "promoted",
    "Desafiante promovido": "Challenger promoted",
    "adiado": "postponed",
    "Retreino adiado": "Retraining postponed",
    "mantido": "kept",
    "Campeão mantido": "Champion kept",
    "sem retreino": "no retraining",
    "Sem retreino": "No retraining",
    "Nenhuma regra disparou até agora.": "No rule has fired so far.",
    "retreino": "retraining",
    "PR-AUC: modelo contra baseline": "PR-AUC: model vs. baseline",
    "Quanto maior, melhor o modelo separa os voos que atrasam.": (
        "The higher, the better the model separates the flights that get delayed."
    ),
    "Modelo": "Model",
    "Baseline": "Baseline",
    "Taxa de atraso: prevista e real": "Delay rate: predicted and actual",
    "Dezembro é o mês mais difícil: a taxa real sobe mais do que o modelo prevê.": (
        "December is the hardest month: the actual rate rises more than the model predicts."
    ),
    "Prevista pelo modelo": "Predicted by the model",
    "Real": "Actual",
    "Taxa de atraso": "Delay rate",
    "Mudança nas variáveis (PSI)": "Feature drift (PSI)",
    "As 5 variáveis que mais pesam no modelo, fora mês do ano, feriados e férias (essas mudam "
    "todo mês por definição). Amarelo: atenção ({atencao} ou mais). Vermelho: mudança forte "
    "({forte} ou mais), que dispara o retreino.": (
        "The model's 5 most important features, leaving out month of the year, holidays and "
        "school breaks (they change every month by design). Yellow: watch ({atencao} or more). "
        "Red: strong shift ({forte} or more), which fires retraining."
    ),
}
