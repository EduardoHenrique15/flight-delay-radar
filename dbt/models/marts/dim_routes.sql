-- Uma rota por par origem-destino, com a distância em linha reta (fórmula de haversine).

with rotas as (
    select origem, destino, count(*) as voos
    from {{ ref('int_flights_clean') }}
    group by origem, destino
)

select
    r.origem,
    r.destino,
    r.voos,
    o.pais = 'BR' and d.pais = 'BR' as domestica,
    round(
        2 * 6371 * asin(sqrt(
            pow(sin(radians(d.latitude - o.latitude) / 2), 2)
            + cos(radians(o.latitude)) * cos(radians(d.latitude))
            * pow(sin(radians(d.longitude - o.longitude) / 2), 2)
        ))
    ) as distancia_km
from rotas r
left join {{ ref('dim_airports') }} o on o.icao = r.origem
left join {{ ref('dim_airports') }} d on d.icao = r.destino
