# Equipment health snapshot

Health by equipment type, over the last 3 complete months plus the current month to date — four columns.

## Columns

| Column | Value |
| --- | --- |
| Equipment type | Types with at least one scored rule |
| Equipment | Distinct equipment of that type carrying a scored rule |
| Rules | Distinct scored rules on that type |
| Four month columns | Equipment health score for that month, `x.x%` |
| Chg | Current month minus start month, in pp |

## Bands

Score cells are filled against these thresholds:

| Band | Score | Fill |
| --- | --- | --- |
| Excellent | ≥ 99% | success, strong |
| Good | ≥ 97% | success, light |
| Average | ≥ 90% | warning |
| Poor | < 90% | danger |

Print the key beneath the grid: `Excellent ≥99 · Good ≥97 · Average ≥90 · Poor <90`.

- `score` comes back as a raw `0.0–1.0` fraction — multiply by 100 and print to **1dp**. Band on the raw value, not the rounded one: these bands sit close together, so a score that rounds up onto an edge keeps the fill its raw value earned.
- The cell holds the number and nothing else — `99.2`, filled.
- Two greens for Excellent and Good rather than green and blue: one container step per colour would collapse the two bands holding most of the data, and blue is the accent, already carrying the links.

## Display

Band heatmap: one row per equipment type, months as columns, each score cell filled with its band, the numeral still legible on the fill. Equipment and Rules flank it unfilled.

- Sort by Chg descending, so the biggest improvement leads and any decline closes.
- Site row sits after the sort, separated from it.
- Show every equipment type, not a sample.
- Exclude equipment type `BACER` / `Bacer (System)` — platform health checks, not building plant.
- Bold the current month column only. A grid of bold figures reads as noise.
- Mark the current month `*` in the header and footnote it `* partial, to date`.
- Chg is signed with a glyph and coloured by direction: `▲ +0.4` green, `▼ -0.8` red, `– 0.0` grey and muted. Colour the text, never the cell — it is a movement, not a score, so the bands do not apply. Keep it at normal weight; bold black reads heavier than the scores beside it.

## Links

Row label, over the full window:

`https://ace.cimenviro.com/dashboard/equipment-health?site_ids={site_id}&start_date={window_start}T00:00:00.000&end_date={today}T00:00:00.000&equipment_type_ids={type_id}`

Score cell, the same URL with `start_date` / `end_date` scoped to that month alone.

The Site row uses the same URL without `equipment_type_ids`.

