---
name: health-check
description: Renders a single PEAK site health check inline in chat — equipment health by equipment type, indoor environment thermal comfort by level, or the assignee leaderboard — each rendered visually with benchmark bands and deep links back into PEAK. Invoke ONLY via the /health-check slash command — never auto-trigger on PEAK questions, ticket workflows or dashboard requests. Once invoked, stay active for the rest of the session for repeat checks, other sites and drill-downs.
---

# Health check

One site, one check, rendered inline in chat. No report — a visual, its band key, a deep link into PEAK, and the caveats that stop the numbers being misread. A file only as the fallback in Step 5.

## Step 1 — Pick the check

Skip the question if the invocation already names one (`/health-check equipment Skyline Tower`). Otherwise ask with `AskUserQuestion`:

| Option | Renders | Then read |
| --- | --- | --- |
| Equipment health snapshot | Health by equipment type, monthly | `references/equipment-health.md` |
| Indoor environment health snapshot | Thermal comfort by level, monthly | `references/indoor-environment.md` |
| Assignee leaderboard | Who closed the work | `references/assignee-leaderboard.md` |

## Step 2 — Resolve the site

One site per run. `search_sites(keyword:"…")` → `site_id`, `site_name`, `timezone`. Ask once if no site was named; if several match, list them and ask which. Reuse the resolved site for the rest of the session — never re-ask.

## Step 3 — Set the window

Dates are the site's own calendar days, so "today" means today at the site. `local_end_date` is **exclusive** on every PEAK search tool: the end bound is the day *after* the last day you want.

| Check | Window | At 2026-08-13 |
| --- | --- | --- |
| Equipment health, Indoor environment | First of the month 3 complete months back → tomorrow. Four columns: the last 3 complete months plus the current month to date | `2026-05-01` → `2026-08-14`, columns May, Jun, Jul, Aug\* |
| Assignee leaderboard | 90 days back → tomorrow, so today counts | `2026-05-15` → `2026-08-14`, covering 15 May – 13 Aug |

## Step 4 — Run the recipe

Read the one reference file for the chosen check and follow it. Do not read the other two.

## Step 5 — Render

Order is the same on every target: visual → band key → source link → notes → one line offering a follow-up (another check, another site, or a drill-down on a row).

Visual, not a bare table. The shape follows the check:

- **Equipment health, Indoor environment** — band heatmap: one row per entity, months as columns, each score cell filled with its band, the numeral still legible on the fill. Count and change columns flank it uncoloured.
- **Assignee leaderboard** — ranked rows: completion rate as a bar on a 0–100 track with the value beside it, rank and counts as plain numerals. Not a heatmap — one rate and some counts, not a score moving across months.

Use the richest surface the client offers, in order:

1. Inline in the conversation — whatever rendering surface it exposes. Always preferred.
2. Otherwise one self-contained `.html` file, and hand back the path.
3. Only if neither is available, the markdown table with emoji chips.

Both shapes are plain HTML — a `<table>` with cell backgrounds, a `<span>` on a track — so no chart library, no CDN, no build step, and the same markup carries from target 1 to target 2.

In the heatmap, row labels and score cells both link into PEAK: the label over the full window, the cell scoped to its own month. The leaderboard links once, on the table.

## Conventions

**Bands** — every score cell carries one:

| Chip | Equipment health | Thermal comfort | Fill |
| --- | --- | --- | --- |
| 🟢 Excellent | ≥ 99% | ≥ 92% | success, strong |
| 🔵 Good | ≥ 97% | ≥ 85% | success, light |
| 🟡 Average | ≥ 90% | ≥ 75% | warning |
| 🔴 Poor | < 90% | < 75% | danger |

Print the matching key under the table: `🟢 Excellent ≥99 · 🔵 Good ≥97 · 🟡 Average ≥90 · 🔴 Poor <90`.

- Scores come back as raw `0.0–1.0` fractions — multiply by 100. Equipment health to **2dp**: those bands sit close together and 1dp rounds a value across a band edge, leaving the numeral and its chip disagreeing. Thermal comfort to **1dp**.
- A score cell is `🟢 99.21` — chip first, then the number. The chip carries the band so the reader never holds thresholds in their head. The chip *is* the band — rendered as an emoji in markdown, as the cell's background fill in HTML. Never both. Use the client's semantic colour variables for the fill rather than hex, so the bands survive dark mode.
- Two greens for Excellent and Good rather than green and blue: one container step per colour would collapse the two bands holding most of the data, and blue is the accent, already carrying links and the rate bar. Keep the rate bar itself one accent fill on a plain track — a bar coloured by band puts two scales in one table.
- Bold the current month column only. A grid of bold figures reads as noise.
- Mark the current month `*` in the header and footnote it `* partial, to date`.
- Chg is the current month minus the start month, in pp, signed with a glyph: `▲ +0.39`, `▼ -0.80`, `– 0.00`. Never chip it.
- Counts (Equipment, Rules, Zones, Resolved, Open now) stay plain numerals — never chipped, never barred. They size the row; they are not performance.
- Close every table with a bold rollup row. It comes from its own rollup call, so it will not equal the average of the rows above — say so once in the notes and never reconcile the two.
- Row labels link into PEAK with a chevron: `[AHU >](url)`. Truncate past ~28 chars with `…`.
- Link dates are ISO `YYYY-MM-DDT00:00:00.000`, built from the same window as the table.
- A month with no data is `–` plus a note. Never invent a row, and never carry a value forward.
