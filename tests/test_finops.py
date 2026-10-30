import pytest

from finops.analyze import connect, query, run
from finops.generate import generate


@pytest.fixture(scope="module")
def result(tmp_path_factory):
    base = tmp_path_factory.mktemp("finops")
    return run(generate(base / "data"), base / "out"), base


def test_attribution_reconciles_to_the_bill(result):
    _, base = result
    con = connect(base / "data")
    by_wh = query(con, "01_cost_by_warehouse.sql")
    for w in by_wh:
        assert abs(w["work_usd"] + w["idle_usd"] - w["billed_usd"]) < 0.05
    teams = query(con, "02_cost_by_team.sql")
    assert abs(sum(t["total_usd"] for t in teams) - sum(w["billed_usd"] for w in by_wh)) < 1.0


def test_all_four_planted_wastes_are_found(result):
    res, _ = result
    titles = " | ".join(r.title for r in res["recommendations"])
    assert "auto-suspend on BI_WH" in titles
    assert "Right-size TRANSFORM_WH" in titles
    assert "fct_events incremental" in titles
    assert "exec_revenue_tile" in titles


def test_savings_are_material_but_below_total(result):
    res, _ = result
    share = res["saving_monthly"] / res["total_monthly"]
    assert 0.3 < share < 0.8


def test_outputs_written(result):
    _, base = result
    memo = (base / "out" / "executive_memo.md").read_text(encoding="utf-8")
    assert "Bottom line" in memo and "a year" in memo
    assert (base / "out" / "cost_savings.png").exists()
