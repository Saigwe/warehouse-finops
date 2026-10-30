# 3-minute walkthrough: Warehouse FinOps

A timed script for a Loom recording of about 3 minutes (screen plus camera bubble, 1080p). Say it in your own words; the lines are a guide, not a teleprompter.

**Open these tabs before you press record:** README, `output/cost_savings.png`, `finops/generate.py`, `finops/analyze.py`, `output/report.md`, `output/executive_memo.md`, `tests/test_finops.py`, GitHub Actions.

| Time | On screen | What to say |
|---|---|---|
| 0:00–0:20 | Portfolio card, then the README headline | Warehouse bills grow quietly and nobody can say which team or query is driving them. This review finds four changes, under a week of effort, that cut spend by 52%, about $104k a year. |
| 0:20–0:40 | `finops/generate.py` | The input is 30 days of usage shaped like Snowflake's ACCOUNT_USAGE views, query history and warehouse metering. It's simulated, with four realistic kinds of waste planted, so I can prove each one is found. |
| 0:40–1:10 | `finops/analyze.py`: attribution | Each query's cost is runtime times the warehouse's credit rate. Idle is billed credits minus query credits. Team showback comes from the query_tag JSON, with idle time shared by usage. |
| 1:10–1:35 | `output/report.md`: cost by warehouse and team | The key rule: attribution reconciles to the bill. Work plus idle equals billed for every warehouse, and the team showback sums to the total. Both are tested. |
| 1:35–2:05 | README: the four changes table | Make fct_events incremental, $47k; it was rebuilt 24 times a day. Shorten auto-suspend on BI_WH, $44k in five minutes, because 94% of its bill was idle. Right-size the transform warehouse, $11k. Cache the executive tile. |
| 2:05–2:25 | README: conservative savings | Savings are deliberately conservative: right-sizing assumes queries run 20% slower, and incremental builds keep 15% of the full-refresh cost. |
| 2:25–2:45 | `output/executive_memo.md` | Two audiences, two documents: a one-page decision memo for the CFO, and the full analysis for the data team. |
| 2:45–3:00 | `tests/test_finops.py`, then the README top | Four tests: it reconciles to the bill, finds all four planted wastes, and keeps savings material but below the total. Point it at real ACCOUNT_USAGE exports and it runs the same. Links are under the video. |

## Recording checklist
- Close email, chat and notifications. Zoom the browser to 125% so code is readable.
- Run `python -m finops.analyze` once before recording so the outputs are fresh.
- Keep to one take per section; Loom lets you trim. Aim for 2:45 to 3:10.
- Show real numbers on screen as you say them; never estimate on camera.
- Say "simulated data with planted problems" when you introduce it. This is a skills demonstration, not a rebuild of client work.

## After recording
1. Copy the Loom share link.
2. In `README.md`, replace the walkthrough line with `- [x] [3-minute Loom walkthrough](<your Loom link>)` and add the link under the title.
3. Add the link to this project's card on saigwe.github.io.
