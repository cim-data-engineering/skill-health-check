---
name: health-check
description: Renders a single PEAK site health check inline in chat — equipment health by equipment type, indoor environment thermal comfort by level, or the assignee leaderboard — each rendered visually with benchmark bands and deep links back into PEAK. Invoke ONLY via the /health-check slash command — never auto-trigger on PEAK questions, ticket workflows or dashboard requests. Once invoked, stay active for the rest of the session for repeat checks, other sites and drill-downs.
---

# Health check

One site, one check, rendered inline in chat. No report — a visual, its key, a deep link into PEAK, and the caveats that stop the numbers being misread. A file only as the fallback in Step 3.

## Step 1 — Pick the check

Skip the question if the invocation already names one (`/health-check equipment Skyline Tower`). Otherwise ask with `AskUserQuestion`:

| Option | Renders | Read |
| --- | --- | --- |
| Equipment health snapshot | Health by equipment type, monthly | `references/equipment-health.md` |
| Indoor environment health snapshot | Thermal comfort by level, monthly | `references/indoor-environment.md` |
| Assignee leaderboard | Who closed the work, last 90 days | `references/assignee-leaderboard.md` |

## Step 2 — Run the recipe

Read the one reference for the chosen check and follow it end to end — columns, bands, data, display, links, notes. Do not read the other two.

## Step 3 — Render

**Visualise it. Attempt that first, every time, without being asked.** Writing the figures out as a markdown table is the failure this step exists to prevent — it is what you will reach for by default, and it is not what this skill produces. The user should never have to follow up with "now visualise it".

So before you write anything, look at what your client can actually render, and take the richest visual surface it offers — a rendered HTML view, a live preview, an inline visual component, a document, or a file you write and hand back. Any of them beats a table. You are not picking the most convenient surface; you are picking the most visual one.

Fall back to a plain markdown table only after a real attempt has failed — you looked, and the client exposes no way to render HTML at all. Then say in one line that you fell back and why, and let the key under it carry the bands. Never fall back silently. Never fall back because a table is quicker or because the numbers are already in hand. Never print a table beside a visual you have already rendered.

With the visual, in order: visual → key → source link → notes. Then one line in chat offering a follow-up — another check, another site, or a drill-down on a row. Nothing else.

Holding across all three checks:

- The band is the cell's background fill and nothing else — conditional formatting against the thresholds in the reference. No marker in the text: the cell holds its number, the fill holds its band.
- No emoji anywhere — not on cells, not on rank or status. Text glyphs are fine where they carry meaning: `▲ ▼ –` on a change.
- The change column is a direction, not a score: green up, red down, grey flat, at normal weight. Never a band fill, never bold, never body-text black — it sits beside the scores and must not out-weigh them.
- Only score cells are filled. Counts stay plain — they size the row; they are not performance.
- Close every table with a bold rollup row. It comes from its own rollup call, so it will not equal the average of the rows above — say so once in the notes and never reconcile the two.
- Row labels link into PEAK, the link text carrying a chevron: `AHU ›`. Truncate labels past ~28 chars with `…`.
- Link dates are ISO `YYYY-MM-DDT00:00:00.000`, built from the same window as the grid.
- Missing data is `–` plus a note. Never invent a row, and never carry a value forward.
