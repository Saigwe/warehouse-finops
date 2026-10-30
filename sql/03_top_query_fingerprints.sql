-- The most expensive query patterns. A fingerprint groups runs of the same query text.
select
    query_fingerprint,
    any_value(warehouse_name)                          as warehouse_name,
    any_value(model)                                   as model,
    count(*)                                           as runs,
    count(distinct cast(start_time as date))           as active_days,
    round(avg(execution_seconds), 1)                   as avg_seconds,
    round(avg(bytes_scanned) / 1e9, 2)                 as avg_gb_scanned,
    round(sum(query_credits) * $price, 2)              as cost_usd
from queries
group by query_fingerprint
order by cost_usd desc
limit 10
