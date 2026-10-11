-- Uma companhia por código ICAO. O nome vem do seed companhias (só os conhecidos com segurança;
-- os demais ficam com o código). Sem seed, é brasileira quem opera voo nacional: só empresa
-- brasileira pode fazer voo doméstico no Brasil.

with voos as (
    select
        cia,
        count(*) as voos,
        count(*) filter (where nacional) as voos_nacionais
    from {{ ref('int_flights_clean') }}
    group by cia
)

select
    v.cia,
    coalesce(s.nome, v.cia) as nome,
    s.nome is not null as nome_conhecido,
    coalesce(s.brasileira, v.voos_nacionais > 0) as brasileira,
    v.voos,
    v.voos_nacionais
from voos v
left join {{ ref('companhias') }} s on s.icao = v.cia
