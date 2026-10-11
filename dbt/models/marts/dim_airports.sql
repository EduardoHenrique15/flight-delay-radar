-- Um aeroporto por código ICAO que aparece nos voos, com nome, local, coordenadas e fuso.
-- O código do VRA é procurado no OurAirports por ident, depois icao_code, depois gps_code.
-- O fuso vem da UF (seed fusos_uf), com exceções por aeroporto (seed fusos_aeroportos).

with codigos as (
    select origem as icao from {{ ref('int_flights_clean') }}
    union
    select destino from {{ ref('int_flights_clean') }}
),

candidatos as (
    select
        c.icao,
        a.*,
        case
            when a.ident = c.icao then 1
            when a.icao_code = c.icao then 2
            else 3
        end as prioridade
    from codigos c
    join {{ ref('stg_airports') }} a
        on c.icao in (a.ident, a.icao_code, a.gps_code)
),

escolhido as (
    select *
    from candidatos
    qualify row_number() over (
        partition by icao order by prioridade, (tipo = 'closed'), ident
    ) = 1
)

select
    c.icao,
    e.iata,
    e.nome,
    e.cidade,
    e.uf,
    e.pais,
    e.latitude,
    e.longitude,
    coalesce(fa.fuso_iana, fu.fuso_iana) as fuso_iana,
    coalesce(fa.diferenca_brasilia_h, fu.diferenca_brasilia_h) as diferenca_brasilia_h,
    e.icao is not null as encontrado_no_ourairports
from codigos c
left join escolhido e using (icao)
left join {{ ref('fusos_aeroportos') }} fa on fa.icao = c.icao
left join {{ ref('fusos_uf') }} fu on fu.uf = e.uf
