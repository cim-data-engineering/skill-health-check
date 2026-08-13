# Indoor environment health snapshot

Thermal comfort by level, over the last 3 complete months plus the current month to date.

## Columns

| Column | Value |
| --- | --- |
| Level | Site levels with at least one thermal zone |
| Zones | Zones on that level that returned a score |
| Four month columns | Thermal comfort score for that month, `x.x%` |
| Chg | Current month minus start month, in pp |

## Data recipe

`search_indoor_environment` on temperature over the window, grouped by level for the rows and by site for the rollup, both at `month`.

Level rows carry `level_name` and the level's own comfort band as `ideal_min` / `ideal_max`, so the notes should quote the band the data returned rather than the typical range. `score` is a `0.0–1.0` fraction.

Days with no calculated score are dropped, and a level that scored nothing across the window does not appear at all — the grid is already limited to levels with a scored zone. A sparse month is normal rather than an error.

Zones is not on those rows. Take it from `platform.levels`, counting each level's `zones`. That counts zones *configured* on the level, which is not the same as the zones that returned a score: a level can carry zones with no temperature point, and the levels list also includes levels the comfort grid omits. Note it; never adjust one number to match the other.

Never build the grid zone by zone — that is one row per zone per month, hundreds of rows for the same picture. Drill to zone only when the user asks about a named level.

## Display

- Sort levels in building order, highest first and ground last — not by Chg. The reader is looking for *where* in the building comfort is drifting, and Chg already carries the direction.
- Site row closes the table.
- Zones stays a plain numeral. It sizes the level, so the reader knows whether a swing covers two zones or twenty.

## Link

Per level, on the row label — `summary_ts` is the first day of the current month:

`https://ace.cimenviro.com/indoor-environment/thermal-comfort?summary_site_id={site_id}&summary_ts={current_month_start}&site_ids={site_id}&start_date={window_start}T00:00:00.000&end_date={today}T00:00:00.000`

## Notes to print

- How the score is calculated: the share of zone readings inside the comfort band during site working hours. Quote the band the rows returned — `ideal_min`–`ideal_max`, commonly 21–24.9 °C (68–79 °F) — rather than the generic range. A zone scores 100% when every working-hours reading in the window fell inside its band.
