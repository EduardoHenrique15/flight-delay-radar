-- Aeroportos do OurAirports com nomes e tipos padronizados. A UF só existe para o Brasil.

select
    upper(trim(ident)) as ident,
    upper(trim(icao_code)) as icao_code,
    upper(trim(gps_code)) as gps_code,
    upper(trim(iata_code)) as iata,
    name as nome,
    municipality as cidade,
    iso_country as pais,
    case when iso_country = 'BR' then replace(iso_region, 'BR-', '') end as uf,
    try_cast(latitude_deg as double) as latitude,
    try_cast(longitude_deg as double) as longitude,
    type as tipo
from {{ source('raw', 'raw_airports') }}
