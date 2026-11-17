# Equipment run hours

When each unit ran over the last full week, against the site's working hours — one row per unit, Monday to Sunday, bars to 15 minutes. Which metadata draws each row is set in [run-hours-signals.md](run-hours-signals.md).

## Scope

- One site: `search_sites(site_name=X, include_working_hours: true)`. Take a top score of 0.9 or more, otherwise show the top 3 and ask.
- The last full Monday-to-Sunday week in site local time, or the week the user names with `--week-of`.
- Working hours come from the site, day by day. A closed day counts all its running as out of hours. If the site has none, the window step stops — ask the user what hours to use, never guess, and run it again with `--hours "Mon-Fri 08:00-18:00, Sat 09:00-13:00"`. A day not named is closed.
- Every unit of an equipment type in [Central plant](run-hours-signals.md#central-plant) and [Field units](run-hours-signals.md#field-units), however many.

## Data recipe

Work in `runhours/`, with the `search_sites` response saved as `site.json`. Make each printed call exactly as printed and save the response under the name printed with it — copy an offloaded response's file there, write an inline one out verbatim. Never print raw rows.

1. **Window** — `python3 references/run-hours/scripts/runhours_plan.py window runhours/site.json runhours`. Prints the discovery call.
2. **Discovery** — the printed call, saved as `discovery-0.json`. Over 1,000 units, repeat it with `start_index` 1000, 2000, … as `discovery-1000.json`, ….
3. **Plan** — `python3 references/run-hours/scripts/runhours_plan.py plan runhours runhours/discovery-*.json`. Prints the history calls.
4. **History** — each printed call, in parallel, saved as `history-1.json`, `history-2.json`, …. A call that fails with a 5xx is too big — split its `fav_ids` in two and save both halves (`history-2a.json`, `history-2b.json`).
5. **Build** — `python3 references/run-hours/scripts/runhours_build.py runhours runhours/history-*.json`. Writes `agg.json` and `days.csv`, prints the notes.
6. **Render** — `python3 references/run-hours/scripts/render_runhours.py runhours/agg.json runhours`. Writes `<site>-run-hours-<dates>.html`.

No history calls means nothing to draw — say why, as the plan does, and show no empty view. If the plan prints a latest-reading call instead, the site's data feed is down: save it as `last-reading.json` and run `runhours_plan.py last runhours runhours/last-reading.json` to say when the site last reported.

## Display

Two charts — Central plant, then Field units — each on its own card and printed on its own sheet. Monday to Sunday edge to edge, bars exact to 15 minutes.

- Group rows by equipment type, in the order of the rows in [run-hours-signals.md](run-hours-signals.md). Sort each group by level, then name.
- Show every drawn unit, including one that never ran. The empty row is the signal.
- Working hours are a grey column on each day. A closed day has none and says "closed".
- Bars are grey-blue during working hours and orange outside them. Hatch where there is no reliable data.
- Label each row with the unit name and `›`, its level and zone muted beside it.
- Hover gives the on and off times, or why the data is not reliable.
- No totals, no hour ticks. Restyle through the constants at the top of `render_runhours.py` — its docstring also holds the aggregate schema for a hand-rolled view.

Hand over the HTML file every time and render it inline once where the client can. Never paste the HTML as text.

## Links

Unit name, over the same week — built by the build step, as no tool returns the chart page:

`{host}/charts?split=true&splitbyunit=true&splitbyequip=false&start={UTC start}.000&end={UTC end}.000&workinghours=true&fav-{equipment_id}={fav_ids}`

`fav_ids` is every metadata fetched for the unit, the one the row is drawn from first, so the chart shows why the row reads as it does. A Common record's leaving water temperature goes under that record's own `fav-{equipment_id}`. `host` comes off the site's `site_link`; start and end are local midnight on the Monday and the following Monday, in UTC.

## Notes to print

The notes the build step prints, in its order, under the view.

Follow-ups — a single unit, weekdays only, run-hour totals — re-script from `days.csv`. Never re-pull the same window.
