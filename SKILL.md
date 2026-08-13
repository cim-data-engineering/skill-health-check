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

Order is the same on every target: visual → key → source link → notes → one line offering a follow-up (another check, another site, or a drill-down on a row).

Visual, not a bare table. The reference gives the shape. Use the richest surface the client offers, in order:

1. Inline in the conversation — whatever rendering surface it exposes. Always preferred.
2. Otherwise one self-contained `.html` file, and hand back the path.
3. Only if neither is available, a plain markdown table — no cell colour there, so the key under it carries the bands.

Every shape is plain HTML — a `<table>` with cell backgrounds, a `<span>` on a track — so no chart library, no CDN, no build step, and the same markup carries from target 1 to target 2.

Holding across all three checks:

- The band is the cell's background colour and nothing else — conditional formatting against the thresholds in the reference. No marker in the text: the cell holds its number, the fill holds its band. Use the client's semantic colour variables rather than hex, so the fills survive dark mode.
- No emoji anywhere, in any target — not on cells, not on rank or status. Text glyphs are fine where they carry meaning: `▲ ▼ –` on a change, `█ ░` on a bar.
- Only scored cells are formatted. Counts stay plain numerals — they size the row; they are not performance.
- Close every table with a bold rollup row. It comes from its own rollup call, so it will not equal the average of the rows above — say so once in the notes and never reconcile the two.
- Row labels link into PEAK with a chevron: `[AHU >](url)`. Truncate labels past ~28 chars with `…`.
- Link dates are ISO `YYYY-MM-DDT00:00:00.000`, built from the same window as the table.
- Missing data is `–` plus a note. Never invent a row, and never carry a value forward.
