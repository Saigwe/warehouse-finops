-- Showback: query cost by team (from query tags), with idle cost shared in proportion to each team's usage
-- of the warehouse it ran on.
with wh as (
    select warehouse_name, sum(credits_used) as billed from metering group by 1
),
use as (
    select warehouse_name, team, sum(query_credits) as credits
    from queries group by 1, 2
),
shares as (
    select u.*, u.credits / sum(u.credits) over (partition by u.warehouse_name) as share
    from use u
)
select
    team,
    round(sum(s.credits) * $price, 2)                                         as query_usd,
    round(sum(s.share * greatest(w.billed - (select sum(credits) from use x where x.warehouse_name = s.warehouse_name), 0)) * $price, 2)
                                                                               as shared_idle_usd,
    round(sum(s.credits) * $price
          + sum(s.share * greatest(w.billed - (select sum(credits) from use x where x.warehouse_name = s.warehouse_name), 0)) * $price, 2)
                                                                               as total_usd
from shares s
join wh w using (warehouse_name)
group by team
order by total_usd desc
