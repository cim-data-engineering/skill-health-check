# Equipment health snapshot

Health by equipment type, over the last 3 complete months plus the current month to date.

## Columns

| Column | Value |
| --- | --- |
| Equipment type | Types with at least one scored rule |
| Equipment | Distinct equipment of that type carrying a scored rule |
| Rules | Distinct scored rules on that type |
| Four month columns | Equipment health score for that month, `x.xx%` |
| Chg | Current month minus start month, in pp |

## Data recipe

`search_equipment_health_scores` over the window, grouped by equipment type for the rows and by site for the rollup — each at `month` for the cells and `all` for the counts. Resolve the returned type ids to names with `search_equipment_types`.

`score` is a `0.0–1.0` fraction; `equipment_count` and `task_count` are the Equipment and Rules columns.

Counts come from the `all` calls only — never sum the months and never read one month. `all` counts distinct equipment and rules across the whole window, so it is legitimately higher than any single month.

## Display

- Sort by Chg descending, so the biggest improvement leads and any decline closes.
- Site row sits after the sort, separated from it.
- Show every equipment type, not a sample.
- Exclude equipment type `BACER` / `Bacer (System)` — platform health checks, not building plant.

## Link

Per type, on the row label:

`https://ace.cimenviro.com/dashboard/equipment-health?site_ids={site_id}&start_date={window_start}T00:00:00.000&end_date={today}T00:00:00.000&equipment_type_ids={type_id}`

The Site row uses the same URL without `equipment_type_ids`.

