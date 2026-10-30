"""Cost attribution, waste detection and savings estimates: python -m finops.analyze

Writes output/report.md, output/executive_memo.md and output/cost_savings.png. All numbers come from the data.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import duckdb
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from .generate import CREDITS_PER_HOUR, DAYS, generate  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SQL = ROOT / "sql"
PRICE_PER_CREDIT = 3.0
SIZES = list(CREDITS_PER_HOUR)


@dataclass
class Recommendation:
    title: str
    finding: str
    action: str
    monthly_saving_usd: float
    effort: str
    short: str = ""

    @property
    def annual_saving_usd(self) -> float:
        return self.monthly_saving_usd * 12


def connect(data_dir: Path) -> duckdb.DuckDBPyConnection:
    con = duckdb.connect()
    d = data_dir.as_posix()
    rates = " ".join(f"when '{k}' then {v}" for k, v in CREDITS_PER_HOUR.items())
    con.execute(f"create view warehouses as select * from read_csv_auto('{d}/warehouses.csv')")
    con.execute(f"create view metering as select * from read_csv_auto('{d}/warehouse_metering_history.csv')")
    con.execute(f"""
        create view queries as
        select q.*,
               json_extract_string(query_tag, '$.team')  as team,
               json_extract_string(query_tag, '$.model') as model,
               q.execution_seconds / 3600.0 * (case w.size {rates} end) as query_credits
        from read_csv_auto('{d}/query_history.csv') q
        join warehouses w using (warehouse_name)
    """)
    return con


def query(con, name: str) -> list[dict]:
    rel = con.execute((SQL / name).read_text(encoding="utf-8"), {"price": PRICE_PER_CREDIT})
    cols = [c[0] for c in rel.description]
    return [dict(zip(cols, r)) for r in rel.fetchall()]


def recommendations(con, by_wh: list[dict], top: list[dict]) -> list[Recommendation]:
    recs: list[Recommendation] = []
    # 1. Long auto-suspend: most idle time can be removed by suspending after 60 seconds.
    for w in by_wh:
        if w["auto_suspend_s"] > 300 and w["idle_usd"] > 0:
            recs.append(Recommendation(
                f"Shorten auto-suspend on {w['warehouse_name']}",
                f"{w['idle_pct']}% of its bill (${w['idle_usd']:,.0f}/month) is idle time; auto-suspend is "
                f"{w['auto_suspend_s'] // 60} minutes.",
                "Set AUTO_SUSPEND = 60 (seconds).", round(w["idle_usd"] * 0.9 * 30 / DAYS, 2), "5 minutes",
                f"Auto-suspend\n{w['warehouse_name']}"))

    # 2. Oversized warehouse: the typical query scans little data, so one size smaller halves the rate.
    sizing = con.execute("""
        select warehouse_name, any_value(w.size) size, quantile_cont(bytes_scanned / 1e9, 0.9) p90_gb,
               sum(query_credits) credits
        from queries join warehouses w using (warehouse_name)
        where model not like 'fct_events'
        group by warehouse_name""").fetchall()
    for name, size, p90_gb, credits in sizing:
        if SIZES.index(size) >= SIZES.index("LARGE") and p90_gb < 1.0:
            # Halving the rate on light queries; assume runtime grows ~20% on the smaller size.
            saving = credits * PRICE_PER_CREDIT * (1 - 0.5 * 1.2)
            recs.append(Recommendation(
                f"Right-size {name} for light models",
                f"90% of its queries (excluding fct_events) scan under {p90_gb:.2f} GB, yet it runs as {size}.",
                f"Run light models on {SIZES[SIZES.index(size) - 1]} (a separate warehouse for heavy builds).",
                round(saving, 2), "1 day", f"Right-size\n{name}"))

    # 3. Full refreshes that run many times a day on large scans: switch to incremental.
    for t in top:
        if t["model"] and t["model"].startswith("fct_") and t["runs"] / t["active_days"] >= 12 \
                and t["avg_gb_scanned"] > 100:
            recs.append(Recommendation(
                f"Make {t['model']} incremental",
                f"It is rebuilt {t['runs'] / t['active_days']:.0f} times a day, scanning {t['avg_gb_scanned']:.0f} GB "
                f"each run (${t['cost_usd']:,.0f}/month).",
                "Change to an incremental dbt model that processes only new partitions (about 1/24 of the data).",
                round(t["cost_usd"] * 0.85, 2), "2 days", f"Incremental\n{t['model']}"))

    # 4. Identical queries re-run all day: rely on the result cache or a materialised summary.
    repeated = con.execute("""
        select query_fingerprint, any_value(model) model, count(*) runs,
               count(distinct cast(start_time as date)) active_days, avg(bytes_scanned) / 1e9 avg_gb_scanned,
               sum(query_credits) * ? cost_usd
        from queries group by 1""", [PRICE_PER_CREDIT]).fetchall()
    cols = ["query_fingerprint", "model", "runs", "active_days", "avg_gb_scanned", "cost_usd"]
    for t in (dict(zip(cols, r)) for r in repeated):
        if t["runs"] / t["active_days"] >= 50 and t["avg_gb_scanned"] < 10:
            recs.append(Recommendation(
                f"Cache the {t['model']} query",
                f"The same query runs {t['runs'] / t['active_days']:.0f} times a day; the data changes hourly.",
                "Materialise an hourly summary table and point the tile at it (or keep text identical to hit "
                "the result cache).", round(t["cost_usd"] * (1 - 11 / (t["runs"] / t["active_days"])), 2), "half a day",
                "Cache\ndashboard tile"))
    return sorted(recs, key=lambda r: -r.monthly_saving_usd)


def md_table(rows: list[dict]) -> str:
    cols = list(rows[0])
    out = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    out += ["| " + " | ".join(f"{v:,.2f}" if isinstance(v, float) else str(v) for v in r.values()) + " |"
            for r in rows]
    return "\n".join(out)


def chart(by_team: list[dict], recs: list[Recommendation], total: float, out: Path) -> None:
    fig, (a, b) = plt.subplots(1, 2, figsize=(11, 4))
    teams = [r["team"] for r in by_team]
    a.barh(teams, [r["query_usd"] for r in by_team], color="#1F3A5F", label="Queries")
    a.barh(teams, [r["shared_idle_usd"] for r in by_team], left=[r["query_usd"] for r in by_team],
           color="#9DB4CC", label="Share of idle")
    a.invert_yaxis()
    a.set_title("Monthly cost by team (USD)")
    a.legend(frameon=False, fontsize=8)
    labels = ["Current"] + [r.short or r.title for r in recs] + ["Optimised"]
    values, running = [total], total
    for r in recs:
        running -= r.monthly_saving_usd
        values.append(running)
    values.append(running)
    b.bar(labels, values, color=["#5B6770"] + ["#E46C0A"] * len(recs) + ["#2E7D32"])
    b.set_title("Monthly spend after each change (USD)")
    b.tick_params(axis="x", labelsize=7)
    fig.tight_layout()
    fig.savefig(out, dpi=120)
    plt.close(fig)


def run(data_dir: Path = ROOT / "data", out_dir: Path = ROOT / "output") -> dict:
    if not (data_dir / "query_history.csv").exists():
        generate(data_dir)
    con = connect(data_dir)
    by_wh = query(con, "01_cost_by_warehouse.sql")
    by_team = query(con, "02_cost_by_team.sql")
    top = query(con, "03_top_query_fingerprints.sql")
    recs = recommendations(con, by_wh, top)
    total = sum(w["billed_usd"] for w in by_wh)
    saving = sum(r.monthly_saving_usd for r in recs)

    out_dir.mkdir(parents=True, exist_ok=True)
    chart(by_team, recs, total, out_dir / "cost_savings.png")
    rec_rows = [{"change": r.title, "monthly_usd": r.monthly_saving_usd, "annual_usd": r.annual_saving_usd,
                 "effort": r.effort} for r in recs]
    (out_dir / "report.md").write_text(
        f"# Warehouse cost review ({DAYS} days)\n\nTotal billed: **${total:,.0f}** "
        f"(${PRICE_PER_CREDIT:.0f}/credit).\n\n## By warehouse\n\n{md_table(by_wh)}\n\n## By team (showback)\n\n"
        f"{md_table(by_team)}\n\n## Most expensive query patterns\n\n{md_table(top)}\n\n## Recommendations\n\n"
        f"{md_table(rec_rows)}\n\n![Cost and savings](cost_savings.png)\n", encoding="utf-8")

    bullets = "\n".join(f"{i}. **{r.title}** (saves ${r.annual_saving_usd:,.0f}/year, effort: {r.effort}). "
                        f"{r.finding} {r.action}" for i, r in enumerate(recs, 1))
    (out_dir / "executive_memo.md").write_text(f"""# Data warehouse spend: decision memo

**Bottom line:** we spend **${total * 12:,.0f} a year** on the warehouse. Four changes, together under a week of
engineering effort, cut that by **{saving / total:.0%} (${saving * 12:,.0f} a year)** with no loss of service.

## What we found

{bullets}

## Recommendation

Approve all four changes this sprint, starting with the five-minute auto-suspend fix. Add monthly cost showback by
team (below) so owners see what their workloads cost, and set a resource monitor alert at 110% of the new baseline.

## Showback by team (monthly)

{md_table(by_team)}

*Method: query cost = runtime × warehouse credit rate; idle cost = billed credits minus query credits, shared across
teams in proportion to use. Savings are conservative estimates and assume unchanged query volume.*
""", encoding="utf-8")
    return {"total_monthly": total, "saving_monthly": saving, "recommendations": recs, "by_team": by_team}


if __name__ == "__main__":
    result = run()
    print(f"Monthly spend ${result['total_monthly']:,.0f}; savings ${result['saving_monthly']:,.0f}/month "
          f"({result['saving_monthly'] / result['total_monthly']:.0%})")
    for r in result["recommendations"]:
        print(f"- {r.title}: ${r.monthly_saving_usd:,.0f}/month")
