---
name: health-check
description: Renders a single PEAK site health check inline in chat — equipment health by equipment type, indoor environment thermal comfort by level, or the assignee leaderboard — each as a monthly table with benchmark bands and deep links back into PEAK. Invoke ONLY via the /health-check slash command — never auto-trigger on PEAK questions, ticket workflows or dashboard requests. Once invoked, stay active for the rest of the session for repeat checks, other sites and drill-downs.
---

# Health check

One site, one check, rendered inline in chat. No file deliverable and no report — a table, its band key, a deep link into PEAK, and the caveats that stop the numbers being misread.

## Step 1 — Pick the check

Skip the question if the invocation already names one (`/health-check equipment 144 Edward`). Otherwise ask with `AskUserQuestion`:

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
| Assignee leaderboard | Last 6 complete months | `2026-02-01` → `2026-08-01` |

## Step 4 — Run the recipe

Read the one reference file for the chosen check and follow it. Do not read the other two.

## Step 5 — Render inline

In this order: table → band key → source link → notes → one line offering a follow-up (another check, another site, or a drill-down on a row).

## Conventions

**Bands** — every score cell carries one:

| Chip | Equipment health | Thermal comfort |
| --- | --- | --- |
| 🟢 Excellent | ≥ 99% | ≥ 92% |
| 🔵 Good | ≥ 97% | ≥ 85% |
| 🟡 Average | ≥ 90% | ≥ 75% |
| 🔴 Poor | < 90% | < 75% |

Print the matching key under the table: `🟢 Excellent ≥99 · 🔵 Good ≥97 · 🟡 Average ≥90 · 🔴 Poor <90`.

- Scores come back as raw `0.0–1.0` fractions — multiply by 100. Equipment health to **2dp**: those bands sit close together and 1dp rounds a value across a band edge, leaving the numeral and its chip disagreeing. Thermal comfort to **1dp**.
- A score cell is `🟢 99.21` — chip first, then the number. The chip carries the band so the reader never holds thresholds in their head.
- Bold the current month column only. A grid of bold figures reads as noise.
- Mark the current month `*` in the header and footnote it `* partial, to date`.
- Chg is the current month minus the start month, in pp, signed with a glyph: `▲ +0.39`, `▼ -0.80`, `– 0.00`. Never chip it.
- Counts (Equipment, Rules, Zones, Resolved, Open now) stay plain numerals — never chipped, never barred. They size the row; they are not performance.
- Close every table with a bold rollup row. It comes from its own rollup call, so it will not equal the average of the rows above — say so once in the notes and never reconcile the two.
- Row labels link into PEAK with a chevron: `[AHU >](url)`. Truncate past ~28 chars with `…`.
- Link dates are ISO `YYYY-MM-DDT00:00:00.000`, built from the same window as the table.
- A month with no data is `–` plus a note. Never invent a row, and never carry a value forward.
