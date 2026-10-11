-- A quarentena de cada mês precisa ficar abaixo do limite (2%); acima disso o pipeline para.
select
    mes_arquivo,
    count(*) filter (where motivo_quarentena is not null) as em_quarentena,
    count(*) as total
from {{ ref('int_flights') }}
group by mes_arquivo
having count(*) filter (where motivo_quarentena is not null)
    > {{ var('quarentena_max_fracao') }} * count(*)
