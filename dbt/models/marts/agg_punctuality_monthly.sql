-- Pontualidade e cancelamentos por mês, companhia, aeroporto de origem e tipo de linha.

select
    mes,
    cia,
    origem,
    tipo_linha,
    count(*) as voos,
    count(*) filter (where realizado) as realizados,
    count(atrasado_15) as realizados_com_horario,
    count(*) filter (where atrasado_15) as atrasados_15,
    count(*) filter (where atrasado_30) as atrasados_30,
    count(*) filter (where atrasado_60) as atrasados_60,
    count(*) filter (where cancelado) as cancelados,
    avg(atrasado_15::int) as taxa_atraso_15,
    avg(cancelado::int) as taxa_cancelamento
from {{ ref('fct_flights') }}
group by all
