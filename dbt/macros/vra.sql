{#- Converte as datas do VRA: 'null' vira nulo e o sufixo de nanossegundos é descartado. -#}
{% macro data_vra(coluna) -%}
    try_strptime(nullif(left(trim({{ coluna }}), 19), 'null'), '%Y-%m-%d %H:%M:%S')
{%- endmacro %}

{#- Texto vazio ou 'null' vira nulo; o resto fica em maiúsculas e sem espaços nas pontas. -#}
{% macro codigo_vra(coluna) -%}
    nullif(nullif(upper(trim({{ coluna }})), ''), 'NULL')
{%- endmacro %}
