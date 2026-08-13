# Assignee leaderboard

Who closed the work, over the last 6 complete months.

## Columns

| Column | Value |
| --- | --- |
| Rank | Position by actions resolved |
| Assignee | Action ticket assignee full name |
| Company | Assignee company name |
| Resolved | Actions resolved in the window |
| Completion rate | `resolved / (resolved + open now)` as a percentage |
| Open now | Actions currently open, as at today |

## Data recipe

Two reads of `tickets.tickets`, both scoped to the site, type escalated, unarchived, selecting only the assignee — nothing else is needed, because the counts are row counts:

1. **Resolved** — status Closed, resolved within the window.
2. **Open now** — unresolved, status New / In Progress / On Hold, no date bound. This is what brings in assignees who resolved nothing but are still carrying work.

Filtering to Closed is what excludes Not Doing. The resolved window alone does not, because a Not Doing action carries a resolved date too. Status ids: 1 New, 3 In Progress, 6 Closed, 7 On Hold, 8 Not Doing.

The assignee's `entity` is the company — name and type (contractor, client or customer) — so no separate user lookup.

There is no server-side group-by, so the per-assignee counts are made here. Each response's `pagination.total` is the count the filter matched, so take the Total row from that rather than summing rows.

## Display

- Rank by Resolved descending, tie-break on completion rate descending.
- 🏆 replaces the rank numeral at 1. Nothing on 2 or 3.
- Completion rate is a 10-character bar with the value beside it: `████████░░ 82%`.
- Resolved and Open now are plain numerals. No bars.
- Open now is bolded when non-zero, left plain at zero.
- Actions with no assignee are not ranked — carry them in a trailing `Unassigned` row so the Total still reconciles.
- Close with a bold Total row, separated from the rank.
- Truncate assignee and company past ~28 chars with `…`.

## Link

On the table, not per row:

`https://ace.cimenviro.com/reports/tickets?site_ids={site_id}&start_date={window_start}T00:00:00.000&end_date={window_last_day}T00:00:00.000&grouping=assignee`

`window_last_day` is the last day of the last complete month — for a window ending `2026-08-01`, that is `2026-07-31`.

