"""Traduções da página Buscar voo (app/paginas/buscar_voo.py)."""

TEXTOS = {
    "Como o seu voo costuma se sair?": "How does your flight usually do?",
    "Digite o número do voo, como aparece no cartão de embarque. Você vê quantas vezes ele saiu "
    "no horário nos últimos 12 meses, o tamanho dos atrasos e a chance prevista para o próximo "
    "voo.": (
        "Type the flight number as it appears on your boarding pass. You see how often it left "
        "on time in the last 12 months, how long the delays were and the predicted chance for "
        "the next flight."
    ),
    "Histórico": "History",
    "Últimos {meses} meses": "Last {meses} months",
    "Base": "Scope",
    "Voos nacionais": "Domestic flights",
    "Fonte": "Source",
    "Número do voo": "Flight number",
    "Ex.: G3 1400, AD 4330 ou LA 3321": "E.g. G3 1400, AD 4330 or LA 3321",
    "Os voos mais comuns das rotas mais movimentadas de {mes}": (
        "The most common flights on the busiest routes in {mes}"
    ),
    "Digite o código da companhia e o número do voo, por exemplo G3 1400 (Gol), AD 4330 (Azul) "
    "ou LA 3321 (LATAM).": (
        "Type the airline code and the flight number, for example G3 1400 (Gol), AD 4330 (Azul) "
        "or LA 3321 (LATAM)."
    ),
    "Nenhuma partida nacional do voo {voo} nos últimos {meses} meses de dados da ANAC. Confira "
    "o código da companhia e o número.": (
        "No domestic departures of flight {voo} in the last {meses} months of ANAC data. Check "
        "the airline code and the number."
    ),
    "{origem} para {destino}": "{origem} to {destino}",
    "Partida mais comum": "Most common departure",
    "nos últimos {meses} meses": "in the last {meses} months",
    "de {inicio} a {fim}": "from {inicio} to {fim}",
    "{inicio} a {fim}": "{inicio} to {fim}",
    "Partidas realizadas": "Departures flown",
    "Saíram no horário": "Left on time",
    "até 15 min · média nacional {taxa}": "up to 15 min · national average {taxa}",
    "Atraso típico": "Typical delay",
    "mediana, quando atrasou mais de 15 min": "median, when more than 15 min late",
    "Cancelados": "Cancelled",
    "das partidas programadas": "of scheduled departures",
    "acima": "above",
    "abaixo": "below",
    "{periodo}, o {voo} partiu {partidas} vezes, e {taxa} delas no horário, {comparacao} da "
    "média dos voos nacionais ({media}).": (
        "{periodo}, {voo} departed {partidas} times, {taxa} of them on time, {comparacao} the "
        "domestic average ({media})."
    ),
    "Quando atrasou, a mediana foi de {mediana}.": "When it was late, the median was {mediana}.",
    "Quanto ele atrasa": "How late it runs",
    "As partidas pelo atraso em relação ao horário previsto. Em âmbar, as que contam como "
    "atraso (mais de 15 min).": (
        "Departures by delay against the scheduled time. In amber, the ones that count as "
        "delayed (more than 15 min)."
    ),
    "Minutos de atraso na partida": "Departure delay in minutes",
    "Atraso na partida": "Departure delay",
    "Parcela": "Share",
    "No horário ou antes": "On time or early",
    "1 a 15 min": "1 to 15 min",
    "16 a 30 min": "16 to 30 min",
    "31 a 60 min": "31 to 60 min",
    "1 a 2 h": "1 to 2 h",
    "Mais de 2 h": "Over 2 h",
    "Mês a mês": "Month by month",
    "A parcela de partidas no horário. A linha tracejada é a média dos voos nacionais no mesmo "
    "mês.": "The share of on-time departures. The dashed line is the domestic average that month.",
    "No horário (este voo)": "On time (this flight)",
    "No horário (média nacional)": "On time (domestic average)",
    "Os maiores atrasos do período": "The longest delays in the period",
    "Trechos deste número de voo": "Legs of this flight number",
    "O mesmo número pode fazer mais de um trecho (por exemplo, com escala).": (
        "The same number can fly more than one leg (for example, with a stop)."
    ),
    "O próximo voo, pelo modelo": "The next flight, according to the model",
    "{dia_semana}, {data} às {hora}": "{dia_semana}, {data} at {hora}",
    "O primeiro dia da previsão em que o {voo} costuma voar, de {origem} para {destino}.": (
        "The first day in the forecast window when {voo} usually flies, from {origem} to {destino}."
    ),
    "Risco baixo": "Low risk",
    "Risco médio": "Medium risk",
    "Risco alto": "High risk",
    "Chance de atrasar": "Chance of delay",
    "O modelo não tem previsão para a {companhia} de {origem} para {destino} em {data}. "
    "Escolha outra data na página de previsão.": (
        "The model has no prediction for {companhia} from {origem} to {destino} on {data}. Pick "
        "another date on the prediction page."
    ),
    "O {voo} não teve um dia da semana regular nos últimos 3 meses, então não dá para saber "
    "quando é o próximo. Escolha a data na página de previsão.": (
        "{voo} had no regular day of the week in the last 3 months, so the next one can't be "
        "known. Pick the date on the prediction page."
    ),
    "Ver a previsão completa": "See the full prediction",
    "O histórico é o das partidas nacionais registradas pela ANAC com esse número de voo. Uma "
    "companhia pode reaproveitar um número em outra rota ou horário ao longo do tempo.": (
        "The history covers the domestic departures ANAC recorded under this flight number. An "
        "airline may reuse a number on another route or time over the years."
    ),
}
