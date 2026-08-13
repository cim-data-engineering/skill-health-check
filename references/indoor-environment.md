# Indoor environment health snapshot

Thermal comfort by level, over the last 3 complete months plus the current month to date — four columns.

## Columns

| Column | Value |
| --- | --- |
| Level | Site levels with at least one thermal zone |
| Zones | Zones on that level that returned a score |
| Four month columns | Thermal comfort score for that month, `x.x%` |
| Chg | Current month minus start month, in pp |

## Bands

Score cells are conditionally formatted against these thresholds:

| Band | Score | Fill |
| --- | --- | --- |
| Excellent | ≥ 92% | success, strong |
| Good | ≥ 85% | success, light |
| Average | ≥ 75% | warning |
| Poor | < 75% | danger |

Print the key beneath the grid: `Excellent ≥92 · Good ≥85 · Average ≥75 · Poor <75`.

- `score` comes back as a raw `0.0–1.0` fraction — multiply by 100 and print to **1dp**. Band on the raw value, not the rounded one.
- The cell holds the number and nothing else — `93.4`, filled.
- Two greens for Excellent and Good rather than green and blue: one container step per colour would collapse the two bands holding most of the data, and blue is the accent, already carrying the links.

## Display

Band heatmap: one row per level, months as columns, each score cell filled with its band, the numeral still legible on the fill. Zones flanks it unfilled.

- Sort levels in building order, highest first and ground last — not by Chg. The reader is looking for *where* in the building comfort is drifting, and Chg already carries the direction.
- Site row closes the table.
- Zones stays a plain numeral. It sizes the level, so the reader knows whether a swing covers two zones or twenty.
- Bold the current month column only. A grid of bold figures reads as noise.
- Mark the current month `*` in the header and footnote it `* partial, to date`.
- Chg is signed with a glyph and coloured by direction: `▲ +1.4` green, `▼ -0.8` red, `– 0.0` grey and muted. Colour the text, never the cell — it is a movement, not a score, so the bands do not apply. Keep it at normal weight; bold black reads heavier than the scores beside it.

## Links

`level_id` is the level's own id, carried through from the rows that gave the level its name. Never guess it, and never substitute the level number or label.

Row label, over the full window — `summary_ts` is the first day of the current month, and `level_ids` scopes it to that row's level:

`https://ace.cimenviro.com/indoor-environment/thermal-comfort?summary_site_id={site_id}&summary_ts={current_month_start}&site_ids={site_id}&start_date={window_start}T00:00:00.000&end_date={today}T00:00:00.000&level_ids={level_id}`

Score cell, the same URL scoped to that month alone — `summary_ts` and `start_date` its first day, `end_date` the first day of the month after. `level_ids` stays on it.

The Site row uses the same URL without `level_ids`.

## Notes to print

- How the score is calculated: the share of zone readings inside the comfort band during site working hours. Quote the band the rows returned — `ideal_min`–`ideal_max`, commonly 21–24.9 °C (68–79 °F) — rather than the generic range. A zone scores 100% when every working-hours reading in the window fell inside its band.
- Zones counts what is configured on the level, which need not match the zones that returned a score.
- The Site row is its own rollup call, not the average of the rows above.
