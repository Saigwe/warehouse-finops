"""Generate 30 days of Snowflake-style usage data (ACCOUNT_USAGE shapes) with four planted kinds of waste.

1. BI_WH has a 60-minute auto-suspend, so it burns credits idling between dashboard refreshes.
2. TRANSFORM_WH is X-Large but runs small dbt models (oversized warehouse).
3. dbt model `fct_events` is fully rebuilt every hour instead of incrementally.
4. A dashboard tile re-runs an identical query every 5 minutes (result-cache candidate).
"""
from __future__ import annotations

import csv
import json
import random
from datetime import datetime, timedelta
from pathlib import Path

CREDITS_PER_HOUR = {"XSMALL": 1, "SMALL": 2, "MEDIUM": 4, "LARGE": 8, "XLARGE": 16}
WAREHOUSES = [
    {"warehouse_name": "BI_WH", "size": "MEDIUM", "auto_suspend_s": 3600},
    {"warehouse_name": "TRANSFORM_WH", "size": "XLARGE", "auto_suspend_s": 60},
    {"warehouse_name": "ADHOC_WH", "size": "SMALL", "auto_suspend_s": 60},
    {"warehouse_name": "DS_WH", "size": "LARGE", "auto_suspend_s": 300},
]
START = datetime(2026, 9, 1)
DAYS = 30


def _q(qid, start, secs, wh, user, role, team, model, gb, fingerprint):
    return {"query_id": f"q{qid}", "start_time": start.isoformat(),
            "end_time": (start + timedelta(seconds=secs)).isoformat(), "warehouse_name": wh, "user_name": user,
            "role_name": role, "query_tag": json.dumps({"team": team, "model": model}),
            "execution_seconds": round(secs, 1), "bytes_scanned": int(gb * 1e9), "query_fingerprint": fingerprint}


def generate(out_dir: str | Path, seed: int = 4) -> Path:
    rng = random.Random(seed)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    queries, busy = [], {w["warehouse_name"]: set() for w in WAREHOUSES}
    qid = 0

    def add(start, secs, wh, *rest):
        nonlocal qid
        qid += 1
        queries.append(_q(qid, start, secs, wh, *rest))
        hour = start.replace(minute=0, second=0, microsecond=0)
        busy[wh].add(hour)

    for d in range(DAYS):
        day = START + timedelta(days=d)
        # (3) fct_events full refresh every hour on TRANSFORM_WH: big scan, long runtime
        for h in range(24):
            add(day + timedelta(hours=h, minutes=5), rng.uniform(420, 540), "TRANSFORM_WH", "DBT_SVC", "TRANSFORMER",
                "data_platform", "fct_events", rng.uniform(380, 420), "fp_fct_events_full_refresh")
        # (2) small dbt models on an XL warehouse
        for h in range(0, 24, 2):
            for m in range(12):
                add(day + timedelta(hours=h, minutes=10 + m), rng.uniform(20, 60), "TRANSFORM_WH", "DBT_SVC",
                    "TRANSFORMER", "analytics", f"stg_model_{m}", rng.uniform(0.05, 0.6), f"fp_stg_model_{m}")
        # (4) dashboard tile refreshing every 5 minutes in office hours, identical query
        for minute in range(8 * 60, 19 * 60, 5):
            add(day + timedelta(minutes=minute), rng.uniform(8, 14), "BI_WH", "LOOKER_SVC", "REPORTER",
                "commercial", "exec_revenue_tile", rng.uniform(2, 3), "fp_exec_revenue_tile")
        # normal BI usage
        for _ in range(rng.randint(40, 70)):
            add(day + timedelta(minutes=rng.randint(8 * 60, 19 * 60)), rng.uniform(5, 40), "BI_WH",
                f"analyst_{rng.randint(1, 12)}", "ANALYST", rng.choice(["commercial", "finance", "operations"]),
                "adhoc_dashboard", rng.uniform(0.5, 8), f"fp_adhoc_{rng.randint(1, 400)}")
        # ad hoc and data science
        for _ in range(rng.randint(15, 30)):
            add(day + timedelta(minutes=rng.randint(9 * 60, 18 * 60)), rng.uniform(10, 300), "ADHOC_WH",
                f"analyst_{rng.randint(1, 12)}", "ANALYST", rng.choice(["finance", "operations"]), "adhoc",
                rng.uniform(0.1, 20), f"fp_adhoc_sql_{rng.randint(1, 900)}")
        for _ in range(rng.randint(3, 8)):
            add(day + timedelta(minutes=rng.randint(9 * 60, 17 * 60)), rng.uniform(300, 1500), "DS_WH",
                f"ds_{rng.randint(1, 4)}", "DATA_SCIENTIST", "data_science", "feature_build", rng.uniform(20, 150),
                f"fp_ds_{rng.randint(1, 40)}")

    # Metering: a warehouse is billed for every hour it is running. Hours with queries count fully; with a long
    # auto-suspend, the warehouse keeps running for the suspend window after the last query of each busy block.
    metering = []
    by_hour: dict[tuple[str, str], list[dict]] = {}
    for q in queries:
        by_hour.setdefault((q["warehouse_name"], q["start_time"][:13]), []).append(q)
    for w in WAREHOUSES:
        rate = CREDITS_PER_HOUR[w["size"]]
        hours = sorted(busy[w["warehouse_name"]])
        tail = max(1, round(w["auto_suspend_s"] / 3600))
        running = set(hours)
        if w["auto_suspend_s"] >= 3600:
            for h in hours:
                running |= {h + timedelta(hours=k) for k in range(1, tail + 1)}
        # Running hours with no queries are billed in full; busy hours are billed for the active fraction plus the
        # suspend window, approximated as the full hour on warehouses that rarely suspend.
        for h in sorted(running):
            in_hour = by_hour.get((w["warehouse_name"], h.strftime("%Y-%m-%dT%H")), [])
            if not in_hour or w["auto_suspend_s"] >= 3600:
                frac = 1.0
            else:
                # each run keeps the warehouse up for its runtime plus the auto-suspend window
                frac = min(1.0, sum(q["execution_seconds"] + w["auto_suspend_s"] for q in in_hour) / 3600)
            metering.append({"warehouse_name": w["warehouse_name"], "start_time": h.isoformat(),
                             "credits_used": round(rate * frac, 4)})

    for name, rows in [("warehouses", WAREHOUSES), ("query_history", queries), ("warehouse_metering_history", metering)]:
        with (out / f"{name}.csv").open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)
    return out


if __name__ == "__main__":
    print(generate("data"))
