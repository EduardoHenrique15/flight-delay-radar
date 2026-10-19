"""Traduções das peças comuns: menu, topo, rodapé e componentes de fdr.interface, e os textos de
fdr.painel (retreino, nomes das variáveis)."""

TEXTOS = {
    # Menu
    "Visão geral": "Overview",
    "Pontualidade": "On-time performance",
    "Previsão": "Prediction",
    "Buscar voo": "Flight lookup",
    "Monitoramento": "Monitoring",
    "Pergunte aos dados": "Ask the data",
    "Sobre o modelo": "About the model",
    # Topo e rodapé
    "Dados até {mes}": "Data through {mes}",
    "Pontualidade dos voos nacionais com os dados públicos da ANAC, previsão de atraso com "
    "LightGBM validada no tempo, monitoramento mês a mês e um assistente que responde em SQL.": (
        "On-time performance of Brazil's domestic flights from ANAC's public data, delay "
        "prediction with LightGBM validated over time, month-by-month monitoring and an "
        "assistant that answers in SQL."
    ),
    "Projeto de {autor}.": "A project by {autor}.",
    "Aberto a vagas em Ciência de Dados, Machine Learning e IA.": (
        "Open to roles in Data Science, Machine Learning and AI."
    ),
    "Projeto": "Project",
    "Dados": "Data",
    "Código no GitHub": "Code on GitHub",
    "Cartão do modelo": "Model card",
    "Decisões de projeto (ADRs)": "Design decisions (ADRs)",
    "VRA: Voo Regular Ativo (ANAC)": "VRA: active scheduled flights (ANAC)",
    "Aeroportos (OurAirports)": "Airports (OurAirports)",
    "Como os dados foram tratados": "How the data was processed",
    "Algo deu errado ao montar esta página. Tente recarregar; se continuar, os dados podem estar "
    "sendo atualizados.": (
        "Something went wrong while building this page. Try reloading; if it persists, the data "
        "may be being updated."
    ),
    # Componentes
    "Copiar link": "Copy link",
    "Copiado ✓": "Copied ✓",
    "Use Ctrl+C": "Use Ctrl+C",
    "{taxa} com atraso": "{taxa} delayed",
    "Partidas": "Departures",
    "/ Departures": "/ Partidas",
    "Chance de atraso prevista pelo modelo": "Chance of delay predicted by the model",
    "Partida": "Departure",
    "Voo": "Flight",
    "De": "From",
    "Para": "To",
    "Destino": "Destination",
    "Companhia": "Airline",
    "Chance": "Chance",
    "Mês": "Month",
    "Série": "Series",
    # Ajuda das métricas
    "PR-AUC: mede se o modelo põe os voos que atrasam no topo da lista de risco. Vai de 0 a 1; "
    "um palpite ao acaso fica perto da taxa de atraso (cerca de 0,15).": (
        "PR-AUC: measures whether the model puts the flights that get delayed at the top of the "
        "risk list. It ranges from 0 to 1; a random guess stays near the delay rate (about 0.15)."
    ),
    "Brier: erro médio entre a probabilidade prevista e o que aconteceu (0 ou 1). Quanto menor, "
    "melhor.": (
        "Brier: mean error between the predicted probability and what happened (0 or 1). Lower "
        "is better."
    ),
    'ECE: diferença média entre a probabilidade prevista e a taxa real, por faixas. Mede se "20% '
    'de chance" quer dizer 20% mesmo.': (
        "ECE: mean difference between the predicted probability and the actual rate, by bands. "
        'It checks whether "a 20% chance" really means 20%.'
    ),
    "PSI: quanto a distribuição de uma variável mudou em relação ao treino. Abaixo de 0,10: "
    "estável; de 0,10 a 0,25: atenção; acima de 0,25: mudança forte.": (
        "PSI: how much a feature's distribution changed compared with training. Below 0.10: "
        "stable; 0.10 to 0.25: watch; above 0.25: strong shift."
    ),
    "Baseline: a taxa de atraso da rota naquele horário nos últimos 12 meses. É a régua que o "
    "modelo precisa vencer.": (
        "Baseline: the route's delay rate at that hour over the last 12 months. It is the bar "
        "the model has to beat."
    ),
    # Retreino (fdr.painel e monitoring/history.json)
    "Sem retreino: nenhuma regra disparou.": "No retraining: no rule fired.",
    "Regra disparou ({motivos}), mas o retreino foi adiado: {adiado}.": (
        "A rule fired ({motivos}), but retraining was postponed: {adiado}."
    ),
    "ganho de PR-AUC do desafiante: {ganho} (IC 95%: {baixo} a {alto})": (
        "challenger's PR-AUC gain: {ganho} (95% CI: {baixo} to {alto})"
    ),
    "Retreino ({motivos}): {ganho}, {decisao}.": "Retraining ({motivos}): {ganho}, {decisao}.",
    "desafiante promovido": "challenger promoted",
    "campeão mantido": "champion kept",
    "{0} meses desde o último retreino": "{0} months since the last retraining",
    "ECE de {0} (máximo {1})": "ECE of {0} (maximum {1})",
    "sem meses novos publicados desde o treino do campeão": (
        "no new months published since the champion was trained"
    ),
    # Nomes das variáveis do modelo (fdr.painel.NOMES_VARIAVEIS)
    "Hora do voo": "Flight hour",
    "Dia da semana": "Day of the week",
    "Mês do ano": "Month of the year",
    "Aeroporto de origem": "Origin airport",
    "Atraso da rota no horário (3 meses)": "Route delay at that hour (3 months)",
    "Atraso da rota no horário (12 meses)": "Route delay at that hour (12 months)",
    "Voos da rota no horário (3 meses)": "Route flights at that hour (3 months)",
    "Voos da rota no horário (12 meses)": "Route flights at that hour (12 months)",
    "Atraso da companhia (3 meses)": "Airline delay (3 months)",
    "Atraso da companhia (12 meses)": "Airline delay (12 months)",
    "Atraso do aeroporto (3 meses)": "Airport delay (3 months)",
    "Atraso do aeroporto (12 meses)": "Airport delay (12 months)",
    "Movimento típico no aeroporto": "Typical airport traffic",
    "Voos da companhia antes no dia": "Airline's earlier flights that day",
    "Folga da programação": "Schedule slack",
    "Duração típica do voo": "Typical flight duration",
    "Distância": "Distance",
    # Temas da explicação do modelo (fdr.model.explain.GRUPOS e models/explicacao_global.json)
    "Histórico da rota neste horário": "Route history at this hour",
    "Horário do voo": "Flight time",
    "Rota e duração do voo": "Route and flight duration",
    "Época do ano": "Time of year",
    "Movimento no aeroporto": "Airport traffic",
    "Histórico da companhia": "Airline history",
    "Nível geral de atrasos no país": "Overall delay level in the country",
    "Feriados": "Holidays",
    "Histórico do aeroporto de origem": "Origin airport history",
}
