-- Atrasos por mês, rota e hora prevista de partida, só na base do modelo (voos nacionais
-- regulares realizados com os dois horários). Alimenta o baseline e as variáveis históricas,
-- sempre filtrado por um mês de corte (regra as-of, PROJETO.md, seção 6.3).

select
    mes,
    origem,
    destino,
    hour(partida_prevista) as hora_prevista,
    count(*) as voos,
    count(*) filter (where atrasado_15) as atrasados_15
from {{ ref('fct_flights') }}
where nacional and regular and atrasado_15 is not null
group by all
