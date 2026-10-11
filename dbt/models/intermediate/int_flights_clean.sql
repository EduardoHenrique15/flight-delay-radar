-- Voos que passaram em todas as regras de qualidade.
select * exclude (motivo_quarentena)
from {{ ref('int_flights') }}
where motivo_quarentena is null
