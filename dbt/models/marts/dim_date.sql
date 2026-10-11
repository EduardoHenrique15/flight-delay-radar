-- Um dia por linha, de 1º de janeiro do primeiro ano com voos até o fim do último ano com feriados
-- (o ano seguinte ao atual), para servir também às previsões de voos futuros.

with limites as (
    select
        (select make_date(year(min(partida_prevista)), 1, 1) from {{ ref('int_flights_clean') }})
            as inicio,
        (select make_date(year(max(data)), 12, 31) from {{ ref('stg_feriados') }}) as fim
),

dias as (
    select cast(unnest(generate_series(inicio, fim, interval 1 day)) as date) as data
    from limites
),

feriados as (
    select data, nome from {{ ref('stg_feriados') }}
)

select
    d.data,
    year(d.data) as ano,
    month(d.data) as mes,
    isodow(d.data) as dia_semana,
    ['segunda', 'terça', 'quarta', 'quinta', 'sexta', 'sábado', 'domingo'][isodow(d.data)]
        as nome_dia_semana,
    isodow(d.data) >= 6 as fim_de_semana,
    f.nome is not null as feriado,
    f.nome as nome_feriado,
    d.data + 1 in (select data from feriados) as vespera_feriado,
    d.data - 1 in (select data from feriados) as pos_feriado,
    -- Férias escolares aproximadas: janeiro, julho e a segunda quinzena de dezembro.
    month(d.data) in (1, 7) or (month(d.data) = 12 and day(d.data) >= 15) as ferias_escolares
from dias d
left join feriados f using (data)
