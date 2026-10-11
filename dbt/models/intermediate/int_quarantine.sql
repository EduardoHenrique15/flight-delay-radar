-- Voos rejeitados pelas regras de qualidade, com o motivo. Nada é apagado sem rastro.
select *
from {{ ref('int_flights') }}
where motivo_quarentena is not null
