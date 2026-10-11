-- Partida prevista dentro do mês do arquivo, com tolerância na virada (docs/dados.md, decisão 3).
select voo_id, mes, partida_prevista
from {{ ref('fct_flights') }}
where partida_prevista < mes
   or partida_prevista >= mes + interval 1 month + to_hours({{ var('tolerancia_virada_horas') }})
