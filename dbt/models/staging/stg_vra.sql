-- Uma linha por linha distinta de cada arquivo: renomeia, padroniza códigos e converte datas.
-- As duplicatas exatas dentro do mesmo arquivo caem aqui (docs/dados.md, seção 4.7).

with fonte as (

    select distinct
        arquivo_origem,
        "ICAO Empresa Aérea",
        "Número Voo",
        "Código Autorização (DI)",
        "Código Tipo Linha",
        "ICAO Aeródromo Origem",
        "ICAO Aeródromo Destino",
        "Partida Prevista",
        "Partida Real",
        "Chegada Prevista",
        "Chegada Real",
        "Situação Voo",
        "Código Justificativa"
    from {{ source('raw', 'raw_vra') }}

)

select
    -- Chave do voo: hash de todas as colunas originais (docs/dados.md, decisão 5).
    md5(concat_ws('|',
        "ICAO Empresa Aérea", "Número Voo", "Código Autorização (DI)", "Código Tipo Linha",
        "ICAO Aeródromo Origem", "ICAO Aeródromo Destino", "Partida Prevista", "Partida Real",
        "Chegada Prevista", "Chegada Real", "Situação Voo", "Código Justificativa"
    )) as voo_id,
    arquivo_origem,
    make_date(
        cast(regexp_extract(arquivo_origem, 'VRA_(\d{4})', 1) as integer),
        cast(regexp_extract(arquivo_origem, 'VRA_\d{4}(\d{1,2})\.', 1) as integer),
        1
    ) as mes_arquivo,
    {{ codigo_vra('"ICAO Empresa Aérea"') }} as cia,
    trim("Número Voo") as numero_voo,
    {{ codigo_vra('"Código Autorização (DI)"') }} as di,
    {{ codigo_vra('"Código Tipo Linha"') }} as tipo_linha,
    {{ codigo_vra('"ICAO Aeródromo Origem"') }} as origem,
    {{ codigo_vra('"ICAO Aeródromo Destino"') }} as destino,
    {{ data_vra('"Partida Prevista"') }} as partida_prevista,
    {{ data_vra('"Partida Real"') }} as partida_real,
    {{ data_vra('"Chegada Prevista"') }} as chegada_prevista,
    {{ data_vra('"Chegada Real"') }} as chegada_real,
    {{ codigo_vra('"Situação Voo"') }} as situacao,
    nullif({{ codigo_vra('"Código Justificativa"') }}, 'N/A') as justificativa
from fonte
