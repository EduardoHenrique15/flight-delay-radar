-- Teste de regressão: o pipeline reproduz os números de referência de agosto de 2026
-- (PROJETO.md, seção 3.1), com tolerância de 0,1 p.p. Só roda se agosto de 2026 estiver carregado.
-- Recorte: voos realizados com os dois horários, sem duplicatas, antes da quarentena.

with base as (
    select *
    from {{ ref('int_flights') }}
    where mes_arquivo = date '2026-08-01' and realizado and atraso_partida_min is not null
),

esperado (recorte, voos, a15, a30, a60) as (
    values
        ('nacional', 67782, 15.7, 7.5, 2.5),
        ('nacional_regular', 67241, 15.7, 7.5, 2.5),
        ('internacional', 13452, 26.0, 14.6, 6.2),
        ('tam_nacional', 23588, 21.0, null, null),
        ('azu_nacional', 22969, 11.5, null, null),
        ('glo_nacional', 19984, 14.7, null, null)
),

obtido as (
    select
        recorte,
        count(*) as voos,
        100 * avg((atraso_partida_min > 15)::int) as a15,
        100 * avg((atraso_partida_min > 30)::int) as a30,
        100 * avg((atraso_partida_min > 60)::int) as a60
    from base,
        lateral (
            select unnest([
                case when tipo_linha = 'N' then 'nacional' end,
                case when tipo_linha = 'N' and di = '0' then 'nacional_regular' end,
                case when tipo_linha = 'I' then 'internacional' end,
                case when tipo_linha = 'N' and cia = 'TAM' then 'tam_nacional' end,
                case when tipo_linha = 'N' and cia = 'AZU' then 'azu_nacional' end,
                case when tipo_linha = 'N' and cia = 'GLO' then 'glo_nacional' end
            ]) as recorte
        )
    where recorte is not null
    group by recorte
)

select e.recorte, e.voos as voos_esperados, o.voos as voos_obtidos, e.a15, o.a15 as a15_obtido
from esperado e
left join obtido o using (recorte)
where exists (select 1 from base)
  and (
      o.voos is distinct from e.voos
      or abs(o.a15 - e.a15) > 0.1
      or (e.a30 is not null and abs(o.a30 - e.a30) > 0.1)
      or (e.a60 is not null and abs(o.a60 - e.a60) > 0.1)
  )
