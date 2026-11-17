# Equipment run hours

When each unit ran across the last full week, against the site's working hours: one row per unit, Monday to Sunday, bars exact to 15 minutes. [run-hours-signals.md](run-hours-signals.md) sets which metadata draws each row.

## Scope

- **Site**: `search_sites(site_name=X, include_working_hours: true)`. Take a top score of 0.9 or more; otherwise show the top 3 and ask.
- **Week**: the last full Monday to Sunday in site local time, or the week the user names (`--week-of YYYY-MM-DD`).
- **Working hours**: the site's, day by day. A closed day counts all its running as outside hours. When the site has none, the window step stops: ask the user, never guess, and run it again with `--hours "Mon-Fri 08:00-18:00, Sat 09:00-13:00"`, where a day not named is closed. The same flag assesses against hours the user names.
- **Equipment**: the types in [Central plant](run-hours-signals.md#central-plant) and [Field units](run-hours-signals.md#field-units), drawn from their listed metadata only.
- **First pass**: up to 100 units, central plant always whole, then each field-unit type that fits whole. The rest is offered after the view, never dropped silently.

## Data recipe

Work in one directory, `runhours/`. Make each printed call exactly as printed, and save its response under the file name printed with it: copy an offloaded response's file there, or write an inline one out verbatim. Never print raw rows; the scripts read the files.

| Step | Do | Saves |
| --- | --- | --- |
| 1 | `search_sites` as above | `runhours/site.json` |
| 2 | `python3 references/run-hours/scripts/runhours_plan.py window runhours/site.json runhours` | `window.json`; prints the discovery call |
| 3 | The discovery call, with `execute_graphql_query` | `discovery-0.json` |
| 4 | `python3 references/run-hours/scripts/runhours_plan.py plan runhours runhours/discovery-*.json` | `plan.json`; prints the history calls |
| 5 | Each history call, in parallel, with `execute_graphql_query` | `history-1-1.json`, `history-1-2.json`, … |
| 6 | `python3 references/run-hours/scripts/runhours_build.py runhours runhours/history-*.json` | `agg.json`, `days.csv`; prints the notes |
| 7 | `python3 references/run-hours/scripts/render_runhours.py runhours/agg.json runhours` | `<site>-run-hours-<dates>.html` |

- **More than 1,000 units**: where `discovery-0.json`'s `pagination.total` is over 1,000, make the call again with `start_index` 1000, 2000, …, saved as `discovery-1000.json`, ….
- **A history call fails with a 5xx**: it is too large. Split its `fav_ids` into two calls and save both (`history-1-2a.json`, `history-1-2b.json`).
- **Nothing to draw**: when the plan prints no history calls, say why as it does, with no empty view. If it prints a latest-reading call instead, the site's data feed is down: save the response as `last-reading.json` and run `runhours_plan.py last runhours runhours/last-reading.json` to say when the site last reported.
- **Later pass**: on yes, `runhours_plan.py calls runhours` prints its calls (`history-2-1.json`, …). Pull them, then run step 6 again over every history file with `--pass 2`, and step 7.

## Display

Two charts, **Central plant** then **Field units**, each on its own card and printed on its own sheet.

| Element | Encoding |
| --- | --- |
| Groups | One per equipment type, in the order of the rows in [run-hours-signals.md](run-hours-signals.md) |
| Rows | Every drawn unit, by level then name; an empty row is a unit that did not run |
| Working hours | A grey column on each day, headed with its hours; a closed day says "closed" |
| Bars | Exact to 15 minutes: grey-blue during working hours, orange outside them, hatched where there is no reliable data |
| Labels | The unit name with a "›", its level and zone muted beside it |
| Hover | On and off times, or why the data is not reliable |
| Not shown | "Not shown: 305 units." under a chart whose other units wait for the later pass |

No totals and no hour ticks. Colours and layout are constants at the top of `render_runhours.py`, and its docstring holds the aggregate schema for a hand-rolled view.

Hand over the HTML file every time, and render it inline once where the client can. Never paste the HTML as text.

## Links

Each unit name opens its PEAK chart for the same week, built by step 6:

`{host}/charts?split=true&splitbyunit=true&splitbyequip=false&start={UTC start}.000&end={UTC end}.000&workinghours=true&fav-{equipment_id}={fav_ids}`

- `fav_ids` is every metadata fetched for the unit, the one the row is drawn from first. A Common record's leaving water temperature goes under that record's own `fav-{equipment_id}`.
- `host` comes from the site's `site_link`; start and end are local midnight on the Monday and the following Monday, in UTC.

## Notes to print

Under the view, the notes step 6 prints, in its order, then the offer of the later pass if there is one.

Follow-ups, such as a single unit, weekdays only or run-hour totals, re-script from `days.csv`. Never re-pull the same window.
