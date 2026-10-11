-- Detecta arquivo truncado: o volume do mês precisa ficar entre 50% e 150% da mediana dos meses
-- carregados nos 12 meses anteriores. Só avalia meses com pelo menos 3 meses de comparação.
with por_mes as (
    select mes_arquivo, count(*) as voos
    from {{ ref('int_flights') }}
    group by mes_arquivo
),

comparado as (
    select
        a.mes_arquivo,
        a.voos,
        median(b.voos) as mediana_anterior,
        count(b.voos) as meses_comparados
    from por_mes a
    left join por_mes b
        on b.mes_arquivo < a.mes_arquivo
       and b.mes_arquivo >= a.mes_arquivo - interval 12 month
    group by a.mes_arquivo, a.voos
)

select *
from comparado
where meses_comparados >= 3
  and (voos < 0.5 * mediana_anterior or voos > 1.5 * mediana_anterior)
