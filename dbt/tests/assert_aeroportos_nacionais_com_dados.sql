-- Os voos nacionais precisam de aeroportos com coordenadas (distância da rota) e fuso (hora
-- local). Se um aeródromo novo aparecer sem cadastro no OurAirports, o pipeline avisa.
with voos as (
    select f.origem, f.destino, o.latitude is null or o.diferenca_brasilia_h is null as sem_origem,
        d.latitude is null or d.diferenca_brasilia_h is null as sem_destino
    from {{ ref('fct_flights') }} f
    left join {{ ref('dim_airports') }} o on o.icao = f.origem
    left join {{ ref('dim_airports') }} d on d.icao = f.destino
    where f.nacional
)

select
    count(*) filter (where sem_origem or sem_destino) as voos_sem_dados,
    count(*) as voos_nacionais
from voos
having count(*) filter (where sem_origem or sem_destino)
    > {{ var('aeroportos_sem_dados_max_fracao') }} * count(*)
