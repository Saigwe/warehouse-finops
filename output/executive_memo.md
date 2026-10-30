# Data warehouse spend: decision memo

**Bottom line:** we spend **$200,932 a year** on the warehouse. Four changes, together under a week of
engineering effort, cut that by **52% ($104,094 a year)** with no loss of service.

## What we found

1. **Make fct_events incremental** (saves $47,049/year, effort: 2 days). It is rebuilt 24 times a day, scanning 400 GB each run ($4,613/month). Change to an incremental dbt model that processes only new partitions (about 1/24 of the data).
2. **Shorten auto-suspend on BI_WH** (saves $44,392/year, effort: 5 minutes). 93.8% of its bill ($4,110/month) is idle time; auto-suspend is 60 minutes. Set AUTO_SUSPEND = 60 (seconds).
3. **Right-size TRANSFORM_WH for light models** (saves $11,055/year, effort: 1 day). 90% of its queries (excluding fct_events) scan under 0.55 GB, yet it runs as XLARGE. Run light models on LARGE (a separate warehouse for heavy builds).
4. **Cache the exec_revenue_tile query** (saves $1,596/year, effort: half a day). The same query runs 132 times a day; the data changes hourly. Materialise an hourly summary table and point the tile at it (or keep text identical to hit the result cache).

## Recommendation

Approve all four changes this sprint, starting with the five-minute auto-suspend fix. Add monthly cost showback by
team (below) so owners see what their workloads cost, and set a resource monitor alert at 110% of the new baseline.

## Showback by team (monthly)

| team | query_usd | shared_idle_usd | total_usd |
|---|---|---|---|
| data_platform | 4,612.69 | 2,689.24 | 7,301.93 |
| analytics | 2,303.16 | 1,342.76 | 3,645.93 |
| commercial | 186.32 | 2,840.69 | 3,027.01 |
| data_science | 877.78 | 295.47 | 1,173.25 |
| finance | 128.84 | 671.23 | 800.07 |
| operations | 130.29 | 665.88 | 796.16 |

*Method: query cost = runtime × warehouse credit rate; idle cost = billed credits minus query credits, shared across
teams in proportion to use. Savings are conservative estimates and assume unchanged query volume.*
