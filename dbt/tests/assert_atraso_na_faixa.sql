-- Nenhum voo fora da faixa de atraso aceita chega à tabela final.
select voo_id, atraso_partida_min
from {{ ref('fct_flights') }}
where realizado
  and atraso_partida_min not between {{ var('atraso_min_minimo') }} and {{ var('atraso_min_maximo') }}
