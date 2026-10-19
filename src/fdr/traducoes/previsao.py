"""Traduções da página Previsão (app/paginas/previsao.py)."""

TEXTOS = {
    # Cabeçalho e modos
    "Qual a chance de o seu voo atrasar?": "What is the chance your flight will be delayed?",
    "Escolha a rota, a companhia, a data e a hora. O modelo estima a chance de a partida atrasar "
    "mais de 15 minutos, usando só o histórico publicado até 2 meses antes do voo.": (
        "Pick the route, airline, date and hour. The model estimates the chance that the "
        "departure is more than 15 minutes late, using only the history published up to 2 months "
        "before the flight."
    ),
    "Modelo": "Model",
    "Voos de": "Flights from",
    "{inicio} a {fim}": "{inicio} to {fim}",
    "Histórico": "History",
    "Até 2 meses antes": "Up to 2 months before",
    "O que você quer ver": "What do you want to see",
    "Um voo": "One flight",
    "Melhor horário da semana": "Best time of the week",
    "Comparar dois voos": "Compare two flights",
    # Exemplos
    "Comece por um exemplo": "Start with an example",
    "Sexta, 21h, saindo de Guarulhos": "Friday, 9 pm, from Guarulhos",
    "Ponte aérea, segunda às 18h": "Rio–São Paulo shuttle, Monday at 6 pm",
    "Terça cedo, saindo de Brasília": "Tuesday morning, from Brasília",
    "Domingo à tarde em Recife": "Sunday afternoon in Recife",
    # Formulário
    "Origem": "Origin",
    "Data do voo": "Flight date",
    "Semana a partir de": "Week starting on",
    "Hora prevista da partida": "Scheduled departure hour",
    "Nenhuma companhia voou essa rota nos 12 meses de histórico. Escolha outra.": (
        "No airline flew this route in the 12 months of history. Pick another one."
    ),
    # Cartão de embarque
    "Cartão de embarque": "Boarding pass",
    "· Boarding pass": "· Cartão de embarque",
    "Data": "Date",
    "Voos no horário": "Flights at this hour",
    "Chance de atrasar mais de 15 min": "Chance of a delay over 15 min",
    "média dos voos: {media}": "average flight: {media}",
    "Risco baixo": "Low risk",
    "Risco médio": "Medium risk",
    "Risco alto": "High risk",
    "Nos 12 meses de histórico, {taxa} dos {voos} voos dessa rota nesse horário atrasaram.": (
        "In the 12 months of history, {taxa} of the {voos} flights on this route at this hour "
        "were delayed."
    ),
    "Não houve voos dessa rota nesse horário nos 12 meses de histórico.": (
        "There were no flights on this route at this hour in the 12 months of history."
    ),
    "A ANAC ainda não publicou os dados de 2 meses antes deste voo. O modelo usa o último mês "
    "publicado ({mes}), um histórico mais velho do que no treino: a previsão fica menos "
    "confiável.": (
        "ANAC has not yet published the data from 2 months before this flight. The model uses the "
        "last published month ({mes}), an older history than in training: the prediction is less "
        "reliable."
    ),
    # Resumo e fatores
    "A chance prevista é de <b>{chance}</b>, acima da média dos voos ({media}).": (
        "The predicted chance is <b>{chance}</b>, above the average flight ({media})."
    ),
    "A chance prevista é de <b>{chance}</b>, abaixo da média dos voos ({media}).": (
        "The predicted chance is <b>{chance}</b>, below the average flight ({media})."
    ),
    " O que mais pesou foi <b>{tema}</b>, que aumentou a chance em {pontos} p.p.": (
        " What weighed most was <b>{tema}</b>, which raised the chance by {pontos} p.p."
    ),
    " O que mais pesou foi <b>{tema}</b>, que reduziu a chance em {pontos} p.p.": (
        " What weighed most was <b>{tema}</b>, which lowered the chance by {pontos} p.p."
    ),
    "O que mais pesou nesta previsão": "What weighed most in this prediction",
    "Quanto a chance mudaria, em pontos percentuais, sem cada tema. Calculado com o SHAP do "
    "próprio modelo, somado por tema.": (
        "How much the chance would change, in percentage points, without each theme. Computed "
        "with the model's own SHAP values, summed by theme."
    ),
    "Tema": "Theme",
    "Efeito": "Effect",
    "&#9664; Diminui<i> o risco</i>": "&#9664; Lowers<i> the risk</i>",
    "Aumenta<i> o risco</i> &#9654;": "Raises<i> the risk</i> &#9654;",
    "Nenhum fator se destacou: a previsão fica perto da média.": (
        "No factor stood out: the prediction stays close to the average."
    ),
    # Outras companhias e outros horários
    "Outras companhias": "Other airlines",
    "Mesma rota, data e horário.": "Same route, date and hour.",
    "Média dos voos: {media}": "Average flight: {media}",
    "O mesmo voo com cada companhia: a diferença vem do histórico de cada uma na rota, no "
    "aeroporto e na programação do dia.": (
        "The same flight with each airline: the difference comes from each one's history on the "
        "route, at the airport and in the day's schedule."
    ),
    "E se fosse em outro horário?": "What if it were at another hour?",
    "Mesma companhia, rota e data. Em cinza-claro, horários sem voos dessa rota no histórico.": (
        "Same airline, route and date. In light gray, hours with no flights on this route in the "
        "history."
    ),
    # Posição entre todos os voos
    "Onde este voo fica entre todos": "Where this flight stands among all flights",
    "Mais arriscado que {parcela} dos {voos} voos do período de teste ({inicio} a {fim}), pela "
    "chance prevista.": (
        "Riskier than {parcela} of the {voos} flights in the test period ({inicio} to {fim}), by "
        "predicted chance."
    ),
    "Chance prevista de atraso": "Predicted chance of delay",
    "Faixa": "Band",
    "Parcela dos voos": "Share of flights",
    "ESTE VOO": "THIS FLIGHT",
    # Melhor horário da semana
    "Calculando a semana...": "Computing the week...",
    "{origem} para {destino}": "{origem} to {destino}",
    "A rota {trecho} não teve voos em nenhum horário nos 12 meses de histórico: não dá para "
    "comparar horários.": (
        "The route {trecho} had no flights at any hour in the 12 months of history: hours cannot "
        "be compared."
    ),
    "{dia} às {hora}": "{dia} at {hora}",
    "Com a {cia}, de {trecho}, na semana que começa em {dia}: o horário com menor chance de "
    "atraso é <b>{melhor} ({chance_melhor})</b>; o com maior chance, <b>{pior} "
    "({chance_pior})</b>.": (
        "With {cia}, from {trecho}, in the week starting {dia}: the time with the lowest chance "
        "of delay is <b>{melhor} ({chance_melhor})</b>; the highest, <b>{pior} "
        "({chance_pior})</b>."
    ),
    "A semana hora a hora": "The week hour by hour",
    "A chance de atraso prevista para cada dia e hora de partida. Em cinza, horários em que a "
    "rota não teve voos nos 12 meses de histórico (ficam fora da escolha do melhor e do pior). "
    "Borda azul: o melhor horário; preta: o pior.": (
        "The predicted chance of delay for each day and departure hour. In gray, hours when the "
        "route had no flights in the 12 months of history (left out of the best and worst). Blue "
        "border: the best time; black: the worst."
    ),
    "Dia": "Day",
    "Chance de atraso": "Chance of delay",
    "Ver o melhor horário em detalhe ({quando})": "See the best time in detail ({quando})",
    # Comparar dois voos
    "Voo A": "Flight A",
    "Voo B": "Flight B",
    "Os dois voos têm praticamente a mesma chance de atraso.": (
        "Both flights have practically the same chance of delay."
    ),
    "O voo <b>{maior}</b> tem <b>{pontos} p.p.</b> a mais de chance de atraso que o voo {menor}.": (
        "Flight <b>{maior}</b> has a <b>{pontos} p.p.</b> higher chance of delay than flight "
        "{menor}."
    ),
    "De onde vem a diferença": "Where the difference comes from",
    "Para cada tema, quanto ele pesa a mais (ou a menos) no voo B do que no voo A, em pontos "
    "percentuais (SHAP por tema).": (
        "For each theme, how much more (or less) it weighs on flight B than on flight A, in "
        "percentage points (SHAP by theme)."
    ),
    "&#9664; Menos risco<i> no voo B</i>": "&#9664; Less risk<i> on flight B</i>",
    "Mais risco<i> no voo B</i> &#9654;": "More risk<i> on flight B</i> &#9654;",
    "Os temas pesam igual nos dois voos.": "The themes weigh the same on both flights.",
    # Link e nota final
    "Compartilhe esta previsão": "Share this prediction",
    "O link abre o app com as mesmas escolhas.": "The link opens the app with the same choices.",
    "É uma probabilidade, não uma garantia: cerca de 15% dos voos atrasam. O modelo não vê clima "
    "nem a rotação do avião. Confirme o horário com a companhia no dia do voo.": (
        "It is a probability, not a guarantee: about 15% of flights are delayed. The model does "
        "not see the weather or the aircraft rotation. Check the time with the airline on the day "
        "of the flight."
    ),
}
