-- Um voo por linha, pronto para análise. O mês de referência é o mês do arquivo da ANAC.
-- Os horários do VRA estão no horário de Brasília (docs/dados.md, seção 4.11); a hora local de
-- partida usa o fuso do aeroporto de origem.

select
    voo_id,
    mes_arquivo as mes,
    cast(partida_prevista as date) as data_prevista,
    cast(partida_prevista + to_hours(coalesce(o.diferenca_brasilia_h, 0)) as date)
        as data_prevista_local,
    cia,
    numero_voo,
    di,
    regular,
    tipo_linha,
    nacional,
    f.origem,
    f.destino,
    partida_prevista,
    hour(partida_prevista) as hora_prevista_brasilia,
    hour(partida_prevista + to_hours(coalesce(o.diferenca_brasilia_h, 0)))
        as hora_prevista_local,
    partida_real,
    chegada_prevista,
    chegada_real,
    duracao_prevista_min,
    situacao,
    realizado,
    cancelado,
    situacao = 'NÃO INFORMADO' as nao_informado,
    atraso_partida_min,
    atraso_chegada_min,
    -- Só faz sentido para voos realizados com os dois horários. Partida antecipada conta como
    -- "não atrasado", mas o valor real fica em atraso_partida_min.
    case when atraso_partida_min is not null
        then atraso_partida_min > {{ var('limiar_atraso_min') }} end as atrasado_15,
    case when atraso_partida_min is not null then atraso_partida_min > 30 end as atrasado_30,
    case when atraso_partida_min is not null then atraso_partida_min > 60 end as atrasado_60,
    justificativa,
    arquivo_origem
from {{ ref('int_flights_clean') }} f
left join {{ ref('dim_airports') }} o on o.icao = f.origem
