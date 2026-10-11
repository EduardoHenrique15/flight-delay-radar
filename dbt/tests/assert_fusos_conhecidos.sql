-- Confere o fuso de aeroportos conhecidos, quando eles aparecem nos dados.
with esperado (icao, diferenca) as (
    values ('SBGR', 0), ('SBEG', -1), ('SBRB', -2), ('SBFN', 1), ('SBCY', -1)
)
select e.icao, e.diferenca, a.diferenca_brasilia_h
from esperado e
join {{ ref('dim_airports') }} a using (icao)
where a.diferenca_brasilia_h is distinct from e.diferenca
