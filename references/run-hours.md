# Equipment run hours

When each unit ran across the last full week, against the site's working hours. One deliverable: a weekly HTML view, Monday to Sunday edge to edge, one row per unit, bars exact to 15 minutes, so out-of-hours running and units that never ran are obvious without reading any text.

Pipeline: resolve the site → fix the week → discover every point on the site's plant → pick each unit's sensors → pull history → decide each row → render. The scripts carry every rule; the model makes the calls and passes files between them.

## Scope

- **One site**: `search_sites(site_name=X, include_working_hours: true)`. Top score ≥ 0.9 → take it; otherwise show the top 3 and ask.
- **Working hours** come from the site, each day its own. A closed day has no working hours, so all its running is outside hours. All days closed or all `00:00` → the window step stops: ask what hours to assess against, never guess.
- **Window**: the last full Monday-to-Sunday week in site local time; today's week is never shown. A user-named week is fine (`--week-of`). The window step converts local midnights to UTC, daylight saving included.
- **Equipment**: every type in `references/run-hours-signals.md`, central plant first, then field units. VAVs, lighting, lifts and meters stay out unless the user asks (`--include LT`).
- **Sensors only**: a row is drawn only from a sensor that reports the unit running — a run status, a speed, current or power reading, a compressor status. An enable, command or occupancy schedule says what the unit was told to do, not that it ran, so a unit with nothing else is left off the chart and named in the notes, as is plant with no points at all.
- **First pass**: about 100 units. Central plant is always pulled whole; each field-unit type follows whole where it still fits, and one too big for the pass waits for the later pass without holding back the smaller types after it. The rest is offered after the first view, never dropped silently.

## Data recipe

Work in one directory, e.g. `runhours/`. Every call's response is saved to a file before a script reads it: a large response is offloaded to a file with only the path returned — graceful, not a failure — and an inline one is written out verbatim.

| Step | Do | Keeps |
| --- | --- | --- |
| 1 | `search_sites` as above | the response, as `runhours/site.json` |
| 2 | `python3 scripts/runhours_plan.py window runhours/site.json runhours` | `window.json`; prints the discovery call and the two census counts |
| 3 | All three printed calls, in parallel, with `execute_graphql_query` | `discovery-0.json` (more pages if any), `census-all.json`, `census-known.json` |
| 4 | `python3 scripts/runhours_plan.py plan runhours runhours/discovery-*.json --census runhours/census-all.json runhours/census-known.json` | `plan.json`; prints the first-pass history calls |
| 5 | Each printed call as `execute_graphql_query(platform.history, …, fields: ["fav_id", "ts", "data"])`, in parallel | the history files |
| 6 | `python3 scripts/runhours_build.py runhours <history files>` | `agg.json`, `days.csv`; prints the notes |
| 7 | `python3 scripts/render_runhours.py runhours/agg.json runhours` | the HTML, named `<site>-run-hours-<dates>.html` |

- **Discovery is one row per unit with its points nested**, names, level and zone included, not a list of metadata ids: the rules in `run-hours-signals.md` sort points by name, so metadata PEAK adds later is picked up without an edit. A unit's name, type and level travel once rather than on every point — about 45% smaller than a point per row, 162 KB for 207 Pacific Highway's 117 units. A page holds 1,000 units; where `pagination.total` is over that, fetch the other pages in parallel with `start_index` 1000, 2000, … rather than one after another. Units with no points come back too, so plant never integrated is counted in the notes.
- **The census is two counts**: every unit at the site, and units of a type the two tables know, each `limit: 1` so only `pagination.total` matters (~200 bytes each). Equal counts mean no unit is of a type PEAK added after the tables were written; a difference is named in the notes. The tables cover PEAK's whole catalogue as of September 2026.
- **History**: the plan packs ~36 points per call, ~1.6 MB. The binding limit is payload size, not the 30 s timeout: past ~2 MB the gateway hard-fails with a 5xx — halve the call's `fav_ids` and retry.
- **Loading**: the scripts absorb every payload shape and filter to their own `fav_ids`, because the tool-results directory is shared across concurrent sessions. Never print raw rows or "sample" elements: one careless print puts the whole blob in context.
- **Nothing to draw** — the plan prints no history calls — stop there and say why, as the plan does: either no plant carries a sensor that shows running (with the summary and any unclassified types), or none of the units with one logged anything all week, which is the site's data feed down, not the plant. For the second the plan prints a last-reading call; make it and say since when (Darling Quarter: 1 April 2026). No empty view.

## Which point draws the row

Each unit brings up to two sensors — its **status** and an **analog** (speed, frequency, current, power) — picked by `run-hours-signals.md`. A compressor status stands in only where neither exists.

| The unit has | The row is drawn from |
| --- | --- |
| Status and analog, both changing | Whichever shows less running, over the slots both reported. The usual faults — a status stuck on, an enable mapped as status, a speed output idling above zero — all add hours, so the smaller count is the genuine one. The exception is a signal that switched on no more than once all week beside one that switched on and off to a pattern: it has stopped following the unit and gives way, however little it shows (100 Arthur Street: a pump speed on for 15 minutes beside a status that ran on thirteen occasions) |
| Status and analog, one held at one value all week | The one that changes. A status on all week beside a speed that follows the trading day is the textbook case |
| Status and analog, both held | Status when they agree; hatched as no reliable data when they don't |
| Status only | Status. On all week is kept, and named in the notes as unverified |
| Analog or speed state only | The analog. Held at one running value all week is hatched — it shows a setting, not when the unit ran (180 fan coils at Diageo 1HQ hold `Fan Speed (MSV)` at 3 or 4 all week); held at zero or off, it did not run |
| Only a compressor status | The compressor, named in the notes: it cannot show whether the fan ran |
| Only an enable, command or schedule | Not drawn: no sensor shows the unit ran. Named in the notes |
| No point with history | Not drawn; named in the notes |

- **ON**: a binary point is ON at 1; a multistate one at its running states — for an `(MSV)` state, 1 and above where the week shows a 0 (numbered from 0, 0 is off), else 2 and above (numbered from 1, the BACnet convention, 1 is off); an analog above 5% of its own maximum for the week.
- **Slots** are the site's wall clock, 15 minutes each; a slot is ON if any reading in it is. A reading holds until the next for up to an hour — or, for a point that reports less often, one and a half times its own usual interval: at 100 Arthur Street some statuses are polled every 4 hours, with a reading at each change, and hold 6. A longer silence is hatched, never drawn as off.
- **Change-of-value logging**: a point that sends a handful of readings a week, nearly each one a change, is logged on change rather than every 15 minutes, so each reading holds until the next — silence is the value not changing. A two-state point was the other way before its first reading; anything else is hatched until then. 100 Arthur Street logs 39 of its drawn units this way: `Mon 07:22=1 · Mon 17:39=0 · Tue 06:58=1 …`.
- **"Common" pair points** — `Common - PCHWP - 3/4`, `FB SHP Pump P-10A/B - COMMON`, `AHU-CHWP-10-11-COMMON` — are left out where a member unit is drawn from a sensor at least as good as the pair's own, and kept where they are the only record of the pumps running. A COMMON record that names no member numbers (`EWH-OFFICE-COMMON`) is drawn like any unit if it has a sensor. A pair is grouped with its members.
- **Mistyped units** — the name says one type, PEAK another — are grouped by the name only for the pairs in the reference's **Regrouped by name** table (fan coils typed as AHU or PAC, kitchen fans typed as exhaust fans, primary and secondary pumps), and the notes say so. A location code opening a name (`CH AHU-12 Kitchen`, `EC Boiler-01`) never regroups a unit.

## Display

Two pages, stacked in one file and printing one chart per sheet: **Central plant**, then **Field units**. A page with no rows is left out.

| Element | Encoding |
| --- | --- |
| Groups | One per equipment type, labelled with its PEAK type name, in the order of the types table: cooling, heating, hot water, air, water services; then packaged, terminal and extract units |
| Rows | Every drawn unit, including one that never ran — an empty row is the signal. By level, then name in natural order (1, 2, 10), with a small gap between levels |
| Days | Monday to Sunday edge to edge, faint midnight lines behind the bars; running through midnight is one unbroken bar |
| Working hours | A grey column on each day, headed "Mon 14" over "9am-10pm". A closed day has no column and says "closed" |
| Bars | Exact to 15 minutes: grey-blue during working hours, orange outside them, hatched where there is no reliable data |
| Legend | During working hours, Outside working hours, and No reliable data only when a page uses it |
| Labels | The unit name, indented under the group, cut with "…" when too long, a "›" after each. Its level and zone sit right-aligned before the week, smaller and muted: `L21 · Tenant-Open-Office`. A default zone (`Zone1`), one that repeats the level or is in the name, is left out; a long zone is shortened while 8 characters of it show, else the level stands alone, else neither: never a fragment. Hovering gives the full name, the point used, and level and zone as PEAK has them |
| Hover | "On Mon 14 07:00 to Tue 15 01:15", "Running all week", "Did not run this week", or why the data is not reliable |

No totals, no hour ticks, no part-hour shading, and never an em or en dash in the page. Colours, fonts and layout are named constants at the top of the renderer — restyle there, not in prose.

Hand over the HTML file every time, and render the same view inline where the client can: the file's contents, once, to whatever inline view it offers, ~25 KB for a hundred units. Never paste the HTML into the conversation as text. Under it, the notes, then the offer of the later pass if there is one.

## Links

Each unit name opens its PEAK chart for the same week, with working hours on. No tool returns the chart page, so this link is built, by the build step:

`{host}/charts?split=false&splitbyunit=false&splitbyequip=false&start={UTC start}.000&end={UTC end}.000&workinghours=true&fav-{equipment_id}={fav_ids}`

- `host` comes off the site's `site_link`; start and end are local midnight on the Monday and the following Monday, in UTC.
- `fav_ids` lists the point drawn first, then the point it was checked against, so the chart shows why the row reads as it does.

## Notes to print

The build step prints them, in this order; state them under the view.

- The working hours assessed against, and whether they came from the site or the user.
- How many rows came from each kind of sensor, and every unit whose status and analog disagreed.
- Speeds held at one setting all week, hatched.
- Units on all week from a status with nothing to check it against — possibly a stuck switch.
- Units logged on change of value, held between readings.
- Units drawn from a compressor status, and why that is weaker.
- Hatched rows and data gaps.
- Mistyped units regrouped, Common pairs left out.
- What was not drawn and why, one line each: only an enable or schedule; plant alarms but no run point (named — plant whose running is not integrated); no history this week; no points in PEAK; shared COMMON records; records with only sensors, setpoints or dampers (counted, most are zone records).
- Equipment types the reference does not cover yet.
- The later pass not yet fetched, by type and unit count. Offer it in one line: on yes, `python3 scripts/runhours_plan.py calls runhours` prints its calls; pull them, re-run the build with `--pass 2` and every history file, and render again.

Follow-ups — a single unit, a weekday or weekend view, run-hour totals — re-script from `days.csv` and the files on disk. Never re-pull the same window.

## Tool sequence

```
search_sites              (include_working_hours: true) → runhours/site.json
runhours_plan.py window   → window.json, the discovery call and two census counts
execute_graphql_query     (platform.equipment discovery, and the two counts, in parallel)
runhours_plan.py plan     → plan.json, the first-pass history calls
execute_graphql_query     (platform.history, one per printed call, in parallel)
runhours_build.py         → agg.json, days.csv, the notes
render_runhours.py        → the HTML file
inline view               (the same file, once, where the client has one)
```

## Aggregate schema

`scripts/render_runhours.py` is the only consumer. A hand-rolled view should target the same shape. Slots are 15-minute steps from Monday 00:00 local, 0 to 672, as `[start, end)`.

```json
{
  "site_name": "str",
  "window_label": "str",           // "Mon 14 to Sun 20 Sep 2026"
  "tz_label": "str",               // "BST"
  "days": [{"label": "Mon 14", "wh": [36, 88]}],   // wh: working-hours slots that day, or null when closed
  "pages": [
    {
      "title": "Central plant",
      "groups": [
        {
          "name": "Chiller",
          "rows": [
            {
              "name": "str",
              "href": "str",               // the PEAK chart link
              "runs": [[28, 100]],         // ON ranges across the week; may cross midnight
              "gaps": [[300, 310]],        // no data for over an hour: hatched
              "nodata": null,              // or why the whole row is hatched
              "level_break": false,        // small gap above: first unit of a new level
              "point": "str",              // the point the row was drawn from
              "where": ["L21", "Tenant-Open-Office"],   // level and zone for the label, "" where left out; [] for neither
              "where_full": "str"          // level and zone as PEAK has them, for the hover
            }
          ]
        }
      ]
    }
  ],
  "footer": "str",
  "notes": ["str"]
}
```
