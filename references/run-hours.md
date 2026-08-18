# Equipment run hours

When plant actually runs versus when the building is occupied, over the last 7 complete local days. One deliverable: a Gantt — rows are equipment, bars span the typical ON envelope, working hours shaded behind them, so out-of-hours running is visible at a glance.

Pipeline: resolve the site → one favourites call → bulk history pull saved to disk → one script computes the stats and renders the visual.

## Scope

- **One site**: `search_sites(site_name=X, include_working_hours: true)`. Top score ≥ 0.9 → take it; otherwise show the top 3 and ask. Keep the returned `timezone` and per-day `working_hours`.
- **Degenerate working hours** — all `00:00`, or every day disabled — ask what occupancy hours to assess against. Never guess, and never fall back to a default. Common on sites commissioned without hours.
- **Equipment**: if the user named a scope, use it; otherwise default to central plant + AHU (`CH, CT, HWB, PCHWP, CWP, SCHW, PHWP, SHW, AHU`) and state the assumption in the output rather than asking.
- **VAV is a hard exclusion** — point counts are enormous and box-level status is not a run-hours signal. Offer the AHU serving the zone instead. Treat FCU the same unless the user insists.
- **Window**: the last 7 complete local days, yesterday backwards. Today is always excluded — a partial day drags average stop times earlier. Never day-sample: lead/lag plant and optimum-start AHUs make any single day wrong. Explicit user overrides are fine.

## Data recipe

Compute the UTC fetch window from the site timezone — local midnight expressed in UTC. Brisbane UTC+10 → local day D is `(D-1)T14:00Z → (D)T14:00Z`; Chicago UTC-5 → `(D)T05:00Z → (D+1)T05:00Z`. Note the weekday/weekend split.

**Status points — one call.** Look up tier-1 `metadata_id`s for the scoped type codes in `references/run-hours-status-points.md` (`1_status` rows), then:

`execute_graphql_query(platform.favourites, args: {site_id, metadata_ids: [...], is_active: true, limit: 200}, fields: ["fav_id", "metadata_id", "equipment.name", "equipment.metadata_type.type", {path: "history_available", args: {start, end, end_exclusive: true}}])`

- A type that returns nothing → retry it with its `2_enable_command` ids, then `3_analog_proxy` (analog above 5% of observed max = ON). Flag fallback rows.
- **One favourite per physical unit**, ranked in this order: drop `history_available: false`; prefer the non-`HLI` name; then keep the `metadata_id` listed first for that type in the lookup — the plain binary status ahead of its `(MSV)` variant. All three rules are needed. A single chiller commonly returns four favourites (base and `-HLI`, each carrying plain and MSV status), and the two variants use *different* ON/OFF conventions, so leaving both in double-counts the unit and reads it under conflicting rules.
- Scoped types that return nothing at any tier get named in the notes — otherwise the omission is silent and the reader cannot tell "no such plant here" from "present but unmonitored".
- No equipment listing, no cache file, no scope gate — whatever this call returns is the point list. Large lists are handled by chunking the pull, not by asking.

**Bulk pull.** `execute_graphql_query(platform.history, args: {fav_ids: [...], start, end, end_exclusive: true}, fields: ["fav_id", "ts", "data"])`. Fetch all three fields — real `ts` and `fav_id` let the script derive the grid itself, so no index math and no DST bugs. All status points × 7 days fits one call (measured against the live gateway: 43 points × 7 days ≈ 29 k rows ≈ 2 MB succeeded, in ~15 s). The binding limit is payload **size**, not the 30 s timeout. Keep each call under ~2 MB / ~25 k rows; past that the gateway hard-fails with a Cloudflare 502 — on any 5xx, halve the fav_id batch or the window and retry.

**Loading.** An oversized response is offloaded to a file with only the path returned; that is graceful, not a failure. Load with `load_rows` from `scripts/runhours_history.py` — it absorbs the varying payload shapes, filters to your own fav_ids and de-dups across files, all of which matter because the tool-results directory is shared across concurrent sessions. Never print raw rows or "sample" elements: one careless print puts the whole blob in context. Inspect derived files only — `wc -l`, `head`, or the module's `summarise()`.

## Compute

One script, over the loaded rows:

- Group by `fav_id` and local day; expect 96 rows/day on the 15-minute grid, deriving the actual cadence from `ts` deltas if it differs. Flag short days and exclude partial days from the averages.
- ON/OFF: value set `{0,1}` → 1 is ON; `{1,2}` → 2 is ON; anything else → treat the max as ON and note the values seen.
- Per equipment: weekday average daily run hours (Σ ÷ 5, zero-run days included), weekend average (Σ ÷ 2), average start and stop across the days the unit ran (stop = end of the last ON interval), and OOH = ON time outside working hours (all weekend ON time is OOH when weekends are unoccupied).
- **Typical-ON envelope (`segs`).** Mark each 15-minute slot ON per the rule above; a slot is *typical-ON* if it was ON on at least 50% of the weekday days. `segs` is the list of contiguous typical-ON runs as `[start_min, end_min]`, minutes from local midnight within `[0,1440]`. This — not a naive average start→stop — is what the bar draws, and it is the one field the renderer needs that the per-day CSV cannot reconstruct, because it stays correct for across-midnight, 24/7 and cycling units.
- Write **two artifacts**: the per-day CSV (`name,date,run_h,first_on,last_off,ooh_h`) for reuse, and the render-aggregate JSON below. The renderer consumes the aggregate, not the CSV.

Follow-ups — weekend view, one-equipment drilldown, unit conversions — re-script from the file already on disk. Never re-pull the same window.

## Display

Run `python3 scripts/render_runhours.py <agg.json> <out.svg>`, then hand the SVG to the richest visual surface the client offers — in Claude Chat, a single `show_widget` call. Never `cat` or paste the SVG into the conversation, and don't re-invent the chart each run.

Colours, fonts and layout are named constants at the top of the renderer — restyle there, not in prose.

The encodings, for a hand-rolled variant that should stay in the family: horizontal Gantt, one row per equipment, grouped by type. Fixed 00:00→24:00 axis at identical scale on every row. Working-hours band shaded behind each group's rows. Each seg split at the band edges — the portion inside in the in-hours colour, the portions outside in the out-of-hours colour — so a 24/7 unit renders out/in/out and cycling units render their envelope. Right-hand annotation per row. `ran: false` keeps its row, drawn without a bar. Legend below the last group.

Close with one-line anomaly flags only: zero runtime, weekend OOH, pre-dawn starts, run-on past close, heavy cycling. No essay, no table, no workbook.

## Notes to print

- No deep link — PEAK has no equipment run-hours view. The per-day CSV on disk is the drill-down surface.
- The working hours assessed against, and whether they came from the site or from the user.
- Scoped equipment types that returned no points at any tier.
- Equipment whose signal came from a fallback tier (enable command or analog proxy) rather than a status point.
- Partial or short days excluded from the averages, and any unexpected value set seen on a point.

## Tool sequence

```
search_sites             (include_working_hours: true)
execute_graphql_query    (platform.favourites — one call, with history_available)
execute_graphql_query    (platform.history — bulk to disk, chunked under ~2 MB)
<script>                 (load_rows → stats → per-day CSV + aggregate JSON)
render_runhours.py       (aggregate JSON → standalone SVG)
show_widget              (the visual, once)
```

## Aggregate schema

`scripts/render_runhours.py` is the only consumer. A hand-rolled fallback should target the same shape.

```json
{
  "site_name": "str",
  "window_label": "str",           // e.g. "10-16 Aug 2026"
  "wh_start_min": 480,             // weekday working-hours band start, minutes from local midnight
  "wh_end_min": 1080,              // band end
  "type_order": ["Chiller", "Air Handling Units"],
  "equipment": [
    {
      "name": "str", "type": "str",
      "wd_run": 0.0,               // avg weekday daily run hours
      "we_run": 0.0,               // avg weekend daily run hours
      "wd_ooh": 0.0,               // avg weekday daily out-of-hours run hours
      "segs": [[0, 1440]],         // typical-ON envelope, minutes from midnight
      "lbl": "str",                // "HH:MM-HH:MM", or "no runtime this week"
      "ran": true
    }
  ]
}
```
