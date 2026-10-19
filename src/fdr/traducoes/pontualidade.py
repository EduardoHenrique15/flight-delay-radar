"""Traduções da página Pontualidade (app/paginas/pontualidade.py)."""

TEXTOS = {
    " da {cia}": " by {cia}",
    " saindo de {aeroporto}": " from {aeroporto}",
    " para {aeroporto}": " to {aeroporto}",
    "Hora": "Hour",
    "Dia": "Day",
    "Voos": "Flights",
    "Taxa de atraso": "Delay rate",
    "Hora prevista da partida (hora local)": "Scheduled departure hour (local time)",
    "{voos_texto} voos · {taxa_texto} com atraso": "{voos_texto} flights · {taxa_texto} delayed",
    "Quem atrasa, onde e quando": "Who is late, where and when",
    "Voos nacionais realizados. Um voo atrasou quando partiu mais de 15 minutos depois do "
    "horário previsto. Escolha o período, a companhia e a rota.": (
        "Domestic flights operated. A flight is delayed when it departs more than 15 minutes "
        "after the scheduled time. Pick the period, the airline and the route."
    ),
    "Critério": "Criterion",
    "Partida > 15 min": "Departure > 15 min",
    "Base": "Scope",
    "Voos nacionais": "Domestic flights",
    "Meses disponíveis": "Months available",
    "{inicio} a {fim}": "{inicio} to {fim}",
    "Período": "Period",
    "Todas": "All",
    "Todos": "All",
    "Escolha a origem primeiro": "Pick the origin first",
    "Nenhum voo com esses filtros. Tente um período maior ou outra combinação.": (
        "No flights with these filters. Try a longer period or another combination."
    ),
    "Voos no período": "Flights in the period",
    "acima de 15 min": "over 15 min",
    "Mês mais difícil": "Worst month",
    "{taxa} de atraso": "{taxa} delayed",
    "Hora mais crítica": "Worst hour",
    "As linhas mostram o período escolhido, mês a mês.": (
        "The lines show the chosen period, month by month."
    ),
    "De {inicio} a {fim}, <b>{taxa}</b> dos {voos} voos nacionais{recorte} partiram com mais de "
    "15 minutos de atraso. O mês mais difícil foi {pior_mes}, com <b>{taxa_pior}</b>": (
        "From {inicio} to {fim}, <b>{taxa}</b> of the {voos} domestic flights{recorte} departed "
        "more than 15 minutes late. The worst month was {pior_mes}, at <b>{taxa_pior}</b>"
    ),
    "; a hora mais crítica, a das {hora}h, com <b>{taxa}</b>": (
        "; the worst hour, {hora}h, at <b>{taxa}</b>"
    ),
    "Companhias": "Airlines",
    "Taxa de atraso das companhias com pelo menos {minimo} voos.": (
        "Delay rate of airlines with at least {minimo} flights."
    ),
    "Nenhuma companhia com voos suficientes nesse recorte.": (
        "No airline with enough flights in this selection."
    ),
    "Média das companhias do ranking: {taxa}": "Average of the ranked airlines: {taxa}",
    "As diferenças misturam rotas e horários diferentes: não é um ranking de qualidade das "
    "companhias.": (
        "The differences mix different routes and times: this is not a ranking of airline quality."
    ),
    "Evolução mensal": "Monthly trend",
    "Taxa de atraso em cada mês do período.": "Delay rate in each month of the period.",
    "pico: {taxa}": "peak: {taxa}",
    "Quando os voos mais atrasam": "When flights are most delayed",
    "Em cima, a taxa de atraso de cada hora prevista de partida (hora local do aeroporto); "
    "embaixo, a mesma taxa por dia da semana. Combinações com menos de {minimo} voos ficam em "
    "branco.": (
        "Top: the delay rate for each scheduled departure hour (airport local time); bottom: "
        "the same rate by day of the week. Combinations with fewer than {minimo} flights are "
        "left blank."
    ),
    "Dia a dia": "Day by day",
    "A taxa de atraso de cada dia do período, uma coluna por semana. Quanto mais escuro, mais "
    "atraso. Dias com menos de {minimo} voos ficam em branco; os {piores} piores dias têm a "
    "borda preta.": (
        "The delay rate of each day in the period, one column per week. Darker means more "
        "delay. Days with fewer than {minimo} flights are left blank; the {piores} worst days "
        "have a black border."
    ),
    "Os piores dias do período": "The worst days of the period",
    "As rotas no mapa": "Routes on the map",
    "As {rotas} rotas com mais voos no recorte (pelo menos 30 voos cada). A cor é a taxa de "
    "atraso; a espessura, o número de voos. Passe o mouse num arco para ver os números.": (
        "The {rotas} routes with the most flights in the selection (at least 30 flights each). "
        "Color is the delay rate; thickness, the number of flights. Hover over an arc to see "
        "the numbers."
    ),
    "mais voos": "more flights",
    "Os motivos dos atrasos não aparecem aqui: o campo de justificativa vem vazio em todos os "
    "arquivos da ANAC.": (
        "Delay causes are not shown here: the reason field is empty in every ANAC file."
    ),
}
