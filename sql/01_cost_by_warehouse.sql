-- Billed cost per warehouse, split into work (attributed to queries) and idle (billed while nothing ran).
with billed as (
    select warehouse_name, sum(credits_used) as billed_credits
    from metering group by 1
),
attributed as (
    select warehouse_name, sum(query_credits) as attributed_credits
    from queries group by 1
)
select
    b.warehouse_name,
    w.size,
    w.auto_suspend_s,
    round(b.billed_credits * $price, 2)                                        as billed_usd,
    round(least(a.attributed_credits, b.billed_credits) * $price, 2)          as work_usd,
    round(greatest(b.billed_credits - a.attributed_credits, 0) * $price, 2)   as idle_usd,
    round(100 * greatest(b.billed_credits - a.attributed_credits, 0) / b.billed_credits, 1) as idle_pct
from billed b
join attributed a using (warehouse_name)
join warehouses w using (warehouse_name)
order by billed_usd desc
