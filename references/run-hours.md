# Equipment run hours

When each unit ran across the last full week, against the site's working hours. One deliverable: a weekly HTML view, Monday to Sunday edge to edge, one row per unit, bars exact to 15 minutes, so out-of-hours running and units that never ran are obvious without reading any text.

Pipeline: resolve the site → fix the week → discover every point on the site's plant → pick each unit's points → pull history → decide each row → render. The scripts carry every rule; the model makes the calls and passes files between them.

## Scope

- **One site**: `search_sites(site_name=X, include_working_hours: true)`. Top score ≥ 0.9 → take it; otherwise show the top 3 and ask.
- **Working hours** come from the site, each day its own. A closed day has no working hours, so all its running is outside hours. All days closed or all `00:00` → the window step stops: ask what hours to assess against, never guess.
- **Window**: the last full Monday-to-Sunday week in site local time; today's week is never shown. A user-named week is fine (`--week-of`). The window step converts local midnights to UTC, daylight saving included.
- **Equipment**: every type in `references/run-hours-signals.md`, central plant first, then field units. VAVs, lighting, lifts and meters stay out unless the user asks (`--include LT`).
- **First pass**: about 100 units. Central plant is always pulled whole; field-unit types follow whole, in view order, while they fit. The rest is offered after the first view, never dropped silently.

## Data recipe

Work in one directory, e.g. `runhours/`. Every call's response is saved to a file before a script reads it: a large response is offloaded to a file with only the path returned — graceful, not a failure — and an inline one is written out verbatim.

| Step | Do | Keeps |
| --- | --- | --- |
| 1 | `search_sites` as above | the response, as `runhours/site.json` |
| 2 | `python3 scripts/runhours_plan.py window runhours/site.json runhours` | `window.json`; prints the discovery and census calls |
| 3 | Both printed calls, in parallel, with `execute_graphql_query` | the discovery pages and the census |
| 4 | `python3 scripts/runhours_plan.py plan runhours <discovery files> --census <census file>` | `plan.json`; prints the first-pass history calls |
| 5 | Each printed call as `execute_graphql_query(platform.history, …, fields: ["fav_id", "ts", "data"])`, in parallel | the history files |
| 6 | `python3 scripts/runhours_build.py runhours <history files>` | `agg.json`, `days.csv`; prints the notes |
| 7 | `python3 scripts/render_runhours.py runhours/agg.json runhours` | the HTML, named `<site>-run-hours-<dates>.html` |

- **Discovery reads every point on in-scope plant, names included**, not a list of metadata ids. The rules in `run-hours-signals.md` sort points by name, so metadata PEAK adds later is picked up without an edit. Page it with `start_index` while `pagination.has_more`; a 1,000-point mall is one page, ~270 KB, ~6 s.
- **The census** is the site's equipment types only, ~50 bytes a unit. It exists to name types the reference does not classify yet — otherwise a new PEAK type would vanish from the view unnoticed.
- **History**: the plan packs ~36 points per call, ~1.6 MB. The binding limit is payload size, not the 30 s timeout: past ~2 MB the gateway hard-fails with a 5xx — halve the call's `fav_ids` and retry.
- **Loading**: the scripts absorb every payload shape and filter to their own `fav_ids`, because the tool-results directory is shared across concurrent sessions. Never print raw rows or "sample" elements: one careless print puts the whole blob in context.
- **Nothing to draw** — the plan prints no history calls — stop there: say no plant at the site carries a usable run point, with the plan's summary and any unclassified types. No empty view.

## Which point draws the row

Each unit brings up to two genuine signals — its **status** and an **analog** (speed, frequency, current, power) — picked by `run-hours-signals.md`. A command is the fallback, and only where neither exists.

| The unit has | The row is drawn from |
| --- | --- |
| Status and analog, both changing | Whichever shows less running, over the slots both reported. The usual faults — a status stuck on, an enable mapped as status, a speed output idling above zero — all add hours, so the smaller count is the genuine one |
| Status and analog, one held at one value all week | The one that changes. A status on all week beside a speed that follows the trading day is the textbook case |
| Status and analog, both held | Status when they agree; hatched as no reliable data when they don't |
| Status only | Status. On all week is kept, and named in the notes as unverified |
| Analog only | The analog. Held at one non-zero value all week is hatched — run time is unknown |
| Neither, but an enable or command | The command, named in the notes: it shows what the unit was told to do, not confirmed running |
| Only a compressor status | The compressor, named in the notes: it cannot show whether the fan ran |
| No point with history | Not drawn; named in the notes |

- **ON**: a binary point is ON at 1; a multistate one (`(MSV)`, or states numbered from 1) at 2 and above; an analog above 5% of its own maximum for the week.
- **Slots** are the site's wall clock, 15 minutes each. A gap of up to an hour holds the last reading; a longer one is hatched, never drawn as off.
- **"Common" pair points** are left out where a member unit is drawn from a signal at least as good as the pair's own, and kept where they are the only genuine record — a pair's status beside members that carry only enables. A pair is grouped with its members.
- **Mistyped units** — the name says one type, PEAK another, FCUs typed as AHU being the common case — are grouped by the name, and the notes say so.

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
| Labels | Indented under the group, cut with "…" when too long, a "›" after each; hovering gives the full name and the point used |
| Hover | "On Mon 14 07:00 to Tue 15 01:15", "Running all week", "Did not run this week", or why the data is not reliable |

No totals, no hour ticks, no part-hour shading, and never an em or en dash in the page. Colours, fonts and layout are named constants at the top of the renderer — restyle there, not in prose.

Hand over the HTML file every time, and render the same view inline where the client can — in Claude Chat, one `show_widget` call with the file's contents, ~25 KB for a hundred units. Never paste the HTML into the conversation as text. Under it, the notes, then the offer of the later pass if there is one.

## Links

Each unit name opens its PEAK chart for the same week, with working hours on. No tool returns the chart page, so this link is built, by the build step:

`{host}/charts?split=false&splitbyunit=false&splitbyequip=false&start={UTC start}.000&end={UTC end}.000&workinghours=true&fav-{equipment_id}={fav_ids}`

- `host` comes off the site's `site_link`; start and end are local midnight on the Monday and the following Monday, in UTC.
- `fav_ids` lists the point drawn first, then the point it was checked against, so the chart shows why the row reads as it does.

## Notes to print

The build step prints them, in this order; state them under the view.

- The working hours assessed against, and whether they came from the site or the user.
- How many rows came from each kind of signal, and every unit whose status and analog disagreed.
- Units on all week from a status with nothing to check it against — possibly a stuck switch.
- Units drawn from a command or a compressor status, and why each is weaker.
- Hatched rows and data gaps.
- Mistyped units regrouped, Common pairs left out, and units with no usable point or no history.
- Equipment types the reference does not cover yet.
- The later pass not yet fetched, by type and unit count. Offer it in one line: on yes, `python3 scripts/runhours_plan.py calls runhours` prints its calls; pull them, re-run the build with `--pass 2` and every history file, and render again.

Follow-ups — a single unit, a weekday or weekend view, run-hour totals — re-script from `days.csv` and the files on disk. Never re-pull the same window.

## Tool sequence

```
search_sites              (include_working_hours: true) → runhours/site.json
runhours_plan.py window   → window.json, the two discovery calls
execute_graphql_query     (platform.favourites, paged, and platform.equipment, in parallel)
runhours_plan.py plan     → plan.json, the first-pass history calls
execute_graphql_query     (platform.history, one per printed call, in parallel)
runhours_build.py         → agg.json, days.csv, the notes
render_runhours.py        → the HTML file
show_widget               (the same file inline, once)
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
              "point": "str"               // the point the row was drawn from
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
