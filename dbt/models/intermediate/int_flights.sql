-- Todos os voos, sem duplicatas, com o atraso calculado e o motivo de quarentena (se houver).
-- int_flights_clean e int_quarantine dividem esta tabela; os números de referência de agosto de
-- 2026 são conferidos aqui, antes da quarentena (docs/dados.md).

with sem_duplicatas as (

    -- O mesmo voo pode vir em dois arquivos vizinhos; fica o do arquivo mais recente
    -- (docs/dados.md, decisão 4).
    select *
    from {{ ref('stg_vra') }}
    qualify row_number() over (partition by voo_id order by mes_arquivo desc) = 1

),

calculado as (

    select
        *,
        -- As duas colunas trazem data e hora completas: a virada da meia-noite já está tratada.
        date_diff('minute', partida_prevista, partida_real) as atraso_partida_min,
        date_diff('minute', chegada_prevista, chegada_real) as atraso_chegada_min,
        date_diff('minute', partida_prevista, chegada_prevista) as duracao_prevista_min,
        situacao = 'REALIZADO' as realizado,
        situacao = 'CANCELADO' as cancelado,
        di = '0' as regular,
        tipo_linha = 'N' as nacional,
        partida_prevista is not null
            and count(*) over (
                partition by cia, numero_voo, partida_prevista, origem, destino, di
            ) > 1 as conflito_de_chave
    from sem_duplicatas

)

select
    * exclude (conflito_de_chave),
    case
        when partida_prevista < mes_arquivo
            or partida_prevista >= mes_arquivo + interval 1 month
                + to_hours({{ var('tolerancia_virada_horas') }})
            then 'partida prevista fora do mês do arquivo'
        when realizado
            and atraso_partida_min not between {{ var('atraso_min_minimo') }}
                and {{ var('atraso_min_maximo') }}
            then 'atraso fora da faixa aceita'
        when conflito_de_chave
            then 'conflito de chave'
    end as motivo_quarentena
from calculado
