# Assignee leaderboard

Who closed the work, over the last 90 days including today.

## Columns

| Column | Value |
| --- | --- |
| Rank | Position by actions resolved |
| Assignee | Action ticket assignee full name |
| Company | Assignee company name |
| Resolved | Actions resolved in the window |
| Completion rate | `resolved / (resolved + open now)` as a percentage |
| Open now | Actions currently open, as at today |

No bands. Completion rate is a rate against a track, not a score against a benchmark, so there is no key to print under this table.

## Data recipe

Two reads of `tickets.tickets`, both scoped to the site, type escalated, unarchived, selecting only the assignee — nothing else is needed, because the counts are row counts:

1. **Resolved** — status Closed, resolved within the window.
2. **Open now** — unresolved, status New / In Progress / On Hold, no date bound. This is what brings in assignees who resolved nothing but are still carrying work.

Filtering to Closed is what excludes Not Doing. The resolved window alone does not, because a Not Doing action carries a resolved date too. Status ids: 1 New, 3 In Progress, 6 Closed, 7 On Hold, 8 Not Doing.

The assignee's `entity` is the company — name and type (contractor, client or customer) — so no separate user lookup.

There is no server-side group-by, so the per-assignee counts are made here. Each response's `pagination.total` is the count the filter matched, so take the Total row from that rather than summing rows.

## Display

Ranked rows, not a heatmap — one rate and some counts, not a score moving across months.

- Rank by Resolved descending, tie-break on completion rate descending.
- Rank stays a plain numeral all the way down — no marker on the leader. Bold the top row if it needs to stand out.
- Completion rate is a bar on a 0–100 track with the value beside it — one accent fill on a plain track, never coloured by value, which would put two scales in one grid.
- Rank, Resolved and Open now are plain numerals. No bars.
- Open now is bolded when non-zero, left plain at zero.
- Actions with no assignee are not ranked — carry them in a trailing `Unassigned` row so the Total still reconciles.
- Close with a bold Total row, separated from the rank.
- Truncate assignee and company past ~28 chars with `…`.

## Link

On the table, not per row:

`https://ace.cimenviro.com/reports/tickets?site_ids={site_id}&grouping=assignee&relative_date=last_90_days&include_today=true`

