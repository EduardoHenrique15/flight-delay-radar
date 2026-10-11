-- Feriados nacionais. Datas com dois feriados (raro) viram uma linha só.
select data, string_agg(nome, ' / ') as nome
from {{ source('raw', 'raw_feriados') }}
group by data
