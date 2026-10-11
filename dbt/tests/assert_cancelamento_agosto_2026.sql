-- Cancelamentos em voos nacionais de agosto de 2026: 1,6% (PROJETO.md, seção 3.1).
select round(100 * avg(cancelado::int), 1) as pct_cancelados
from {{ ref('int_flights') }}
where mes_arquivo = date '2026-08-01' and tipo_linha = 'N'
having count(*) > 0 and round(100 * avg(cancelado::int), 1) <> 1.6
