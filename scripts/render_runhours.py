#!/usr/bin/env python3
"""Render a PEAK run-hours aggregate JSON as a standalone HTML page.

Usage: python3 render_runhours.py <agg.json> <out.html | out-dir>

One chart per page — central plant, then field units — each an SVG of the
week: Monday to Sunday edge to edge, bars exact to 15 minutes, working hours as
a grey column per day, links on unit names and times on hover. The page prints
one chart per sheet. Given a directory, the file is named
`<site>-run-hours-<dates>.html`.

The page carries the aggregate as compact data plus a short drawing script, so
it stays small enough — about 30 KB for a hundred units — to hand to an inline
view as well as to save; a pre-drawn SVG of the same week is several times
larger. The data is checked here before it is written, so a malformed field
fails in Python rather than as a blank page.

The aggregate JSON (see "Aggregate schema" in references/run-hours.md) is the
renderer's only input. Every layout / colour / font value lives in a named
constant below so the whole look can be restyled in one place. The encodings
themselves are the render contract in that reference's Display section and
must not drift.

Standard library only — no third-party dependencies, by design, so the script
runs wherever the skill is unpacked.
"""
import json
import os
import re
import sys
from html import escape
from pathlib import Path

# ---- Colours -----------------------------------------------------------------
C_IN_HOURS     = "#8da3b3"   # running during working hours (grey-blue)
C_OUT_OF_HOURS = "#e8741a"   # running outside working hours (orange)
C_WH_BAND      = "#edf1f4"   # working-hours column behind each day
C_MIDNIGHT     = "#dfe4e9"   # faint midnight lines
C_HATCH_BG     = "#f6f7f9"   # no reliable data: hatch ground
C_HATCH_LINE   = "#c3ccd4"   # no reliable data: hatch stroke
C_TEXT         = "#1f2933"   # body text
C_MUTED        = "#6b7785"   # subtitle, day hours, group labels, chevrons
C_PAGE_BG      = "#f4f5f7"   # behind the cards
C_CARD         = "#ffffff"   # chart card
C_CARD_LINE    = "#e3e7eb"   # card border

# ---- Typography --------------------------------------------------------------
FONT_STACK  = 'Inter, "Segoe UI", Helvetica, Arial, sans-serif'
FS_TITLE    = 22
FS_SUBTITLE = 13
FS_LEGEND   = 13
FS_DAY      = 13
FS_HOURS    = 12
FS_GROUP    = 13
FS_ROW      = 13

# ---- Layout ------------------------------------------------------------------
WIDTH       = 1040
LABEL_COL   = 214    # the week starts here
RIGHT_PAD   = 16
LEFT_PAD    = 24     # title, legend and group labels
ROW_INDENT  = 36     # unit labels sit under their group label
LABEL_MAX_W = LABEL_COL - 50   # a longer label is cut with an ellipsis
TITLE_Y     = 38
SUBTITLE_Y  = 62
LEGEND_Y    = 78
LEGEND_W    = 24
GRID_TOP    = 108    # day headers start here; the columns run down from it
ROW_H       = 21
BAR_H       = 11
GROUP_H     = 28
GROUP_GAP   = 6
LEVEL_GAP   = 8
BOTTOM_PAD  = 18
BAR_OVERLAP = 0.3    # widen each piece a hair so a split bar reads as one

WEEK_SLOTS = 7 * 96
PAGE_IDS = {"Central plant": "page-central", "Field units": "page-field", "Other": "page-other"}

# Drawing script. K is the constants above, D the compact data; both injected.
SCRIPT = r"""
const X0 = K.labelCol, X1 = K.width - K.rightPad, DW = (X1 - X0) / 7, SW = DW / 96;
const esc = s => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/"/g, "&quot;");
const clock = s => String(Math.floor(s / 4) % 24).padStart(2, "0") + ":" + String(s % 4 * 15).padStart(2, "0");
const ampm = s => { const h = Math.floor(s / 4) % 24, m = s % 4 * 15;
  return (h % 12 || 12) + (m ? ":" + String(m).padStart(2, "0") : "") + (h < 12 ? "am" : "pm"); };
const when = (a, end) => { let i = Math.floor(a / 96), m = a % 96;
  if (end && m === 0 && a > 0) { i -= 1; m = 96; }
  return D.days[i][0] + " " + (m === 96 ? "24:00" : clock(m)); };
const dx = i => X0 + i * DW, px = a => X0 + a * SW;
const text = (x, y, s, size, fill, extra) =>
  `<text x="${x.toFixed(1)}" y="${y.toFixed(1)}" font-size="${size}" fill="${fill}" ${extra || ""}>${esc(s)}</text>`;
const tip = (name, s) => `<title>${esc(name)}\n${esc(s)}</title>`;

function row(r, y, fg, hatch) {
  const [name, runs, gaps, nodata, , link, point] = r, by = y + (K.rowH - K.barH) / 2;
  fg.push(`<a href="${esc(D.linkPrefix + link)}" target="_blank" rel="noopener"><text class="lbl" x="${K.rowIndent}" ` +
    `y="${(y + K.rowH / 2 + 4.5).toFixed(1)}" font-size="${K.fsRow}" fill="${K.text}"><title>Open the PEAK chart for ` +
    `${esc(name)}${point ? " (" + esc(point) + ")" : ""}</title><tspan class="nm">${esc(name)}</tspan>` +
    `<tspan fill="${K.muted}"> ›</tspan></text></a>`);
  if (nodata) {
    fg.push(`<rect x="${X0}" y="${by}" width="${X1 - X0}" height="${K.barH}" fill="url(#${hatch})">${tip(name, nodata)}</rect>`);
    return;
  }
  if (!runs.length) fg.push(`<rect x="${X0}" y="${y}" width="${X1 - X0}" height="${K.rowH}" fill="transparent">${tip(name, "Did not run this week")}</rect>`);
  for (const [a, b] of gaps)
    fg.push(`<rect x="${px(a).toFixed(2)}" y="${by}" width="${((b - a) * SW).toFixed(2)}" height="${K.barH}" ` +
      `fill="url(#${hatch})">${tip(name, "No data " + when(a) + " to " + when(b, 1))}</rect>`);
  for (const [a, b] of runs) {
    const t = tip(name, a === 0 && b === 672 ? "Running all week" : "On " + when(a) + " to " + when(b, 1));
    for (let i = Math.floor(a / 96); i <= Math.floor((b - 1) / 96); i++) {
      const o = i * 96, s = Math.max(a, o) - o, f = Math.min(b, o + 96) - o, w0 = D.days[i][1] || 0, w1 = D.days[i][2] || 0;
      for (const [lo, hi, c] of [[s, Math.min(f, w0), K.out], [Math.max(s, w0), Math.min(f, w1), K.in], [Math.max(s, w1), f, K.out]])
        if (hi > lo) fg.push(`<rect x="${px(o + lo).toFixed(2)}" y="${by}" width="${((hi - lo) * SW + K.overlap).toFixed(2)}" ` +
          `height="${K.barH}" fill="${c}">${t}</rect>`);
    }
  }
}

function chart(pi, el) {
  const [title, groups] = D.pages[pi], hatch = "hatch" + pi, bg = [], fg = [];
  fg.push(text(K.leftPad, K.titleY, title, K.fsTitle, K.text, 'font-weight="600"'));
  fg.push(text(K.leftPad, K.subtitleY, D.site + ", " + D.window + ". Grey columns are working hours.", K.fsSubtitle, K.muted));
  const legend = [[K.in, "During working hours"], [K.out, "Outside working hours"]];
  if (groups.some(g => g[1].some(r => r[3] || r[2].length))) legend.push([`url(#${hatch})`, "No reliable data"]);
  let lx = K.leftPad;
  for (const [fill, label] of legend) {
    fg.push(`<rect x="${lx}" y="${K.legendY}" width="${K.legendW}" height="${K.barH}" rx="2" fill="${fill}"/>`);
    fg.push(text(lx + K.legendW + 7, K.legendY + 10, label, K.fsLegend, K.text));
    lx += K.legendW + 7 + label.length * 7 + 26;
  }
  D.days.forEach((d, i) => {
    const cx = dx(i) + (d[1] === null ? 48 : (d[1] + d[2]) / 2) * SW;
    fg.push(text(cx, K.gridTop + 17, d[0], K.fsDay, K.text, 'font-weight="600" text-anchor="middle"'));
    fg.push(text(cx, K.gridTop + 33, d[1] === null ? "closed" : ampm(d[1]) + "-" + ampm(d[2]), K.fsHours, K.muted, 'text-anchor="middle"'));
  });
  let y = K.gridTop + 40;
  for (const [group, rows] of groups) {
    fg.push(text(K.leftPad, y + 19, group, K.fsGroup, K.muted, 'font-weight="600"'));
    y += K.groupH;
    for (const r of rows) { if (r[4]) y += K.levelGap; row(r, y, fg, hatch); y += K.rowH; }
    y += K.groupGap;
  }
  const bottom = y, height = y + K.bottomPad;
  D.days.forEach((d, i) => { if (d[1] !== null)
    bg.push(`<rect x="${(dx(i) + d[1] * SW).toFixed(2)}" y="${K.gridTop}" width="${((d[2] - d[1]) * SW).toFixed(2)}" ` +
      `height="${bottom - K.gridTop}" rx="4" fill="${K.band}"/>`); });
  for (let i = 0; i <= 7; i++)
    bg.push(`<line x1="${dx(i).toFixed(2)}" y1="${K.gridTop}" x2="${dx(i).toFixed(2)}" y2="${bottom}" stroke="${K.midnight}" stroke-width="1"/>`);
  const defs = `<defs><pattern id="${hatch}" width="5" height="5" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">` +
    `<rect width="5" height="5" fill="${K.hatchBg}"/><line x1="0" y1="0" x2="0" y2="5" stroke="${K.hatchLine}" stroke-width="1.5"/></pattern></defs>`;
  el.innerHTML = `<svg xmlns="http://www.w3.org/2000/svg" width="100%" viewBox="0 0 ${K.width} ${height}" role="img" ` +
    `aria-label="${esc(title + " run times against working hours at " + D.site + ", " + D.window)}">${defs}` +
    `<rect width="${K.width}" height="${height}" fill="${K.card}"/>${bg.join("")}${fg.join("")}</svg>`;
  el.querySelectorAll("text.lbl").forEach(label => {        // cut long names to the label column
    const nm = label.querySelector(".nm"); let s = nm.textContent;
    while (label.getComputedTextLength() > K.labelMaxW && s.length > 4) {
      s = s.slice(0, -1).replace(/[\s-]+$/, ""); nm.textContent = s + "…";
    }
  });
}

D.pages.forEach((p, i) => chart(i, document.getElementById(D.ids[i])));
"""


# ---- Data --------------------------------------------------------------------
def check(agg):
    """Fail on a malformed aggregate here, not as a blank page in the browser."""
    days = agg["days"]
    if len(days) != 7:
        raise ValueError(f"expected 7 days, got {len(days)}")
    for d in days:
        if d["wh"] is not None and not (0 <= d["wh"][0] < d["wh"][1] <= 96):
            raise ValueError(f"bad working hours {d['wh']} on {d['label']}")
    for page in agg["pages"]:
        for group in page["groups"]:
            for r in group["rows"]:
                for a, b in r["runs"] + r.get("gaps", []):
                    if not 0 <= a < b <= WEEK_SLOTS:
                        raise ValueError(f"bad slot range {[a, b]} on {r['name']}")
                if not r["href"].startswith("http"):
                    raise ValueError(f"bad link on {r['name']}")


def compact(agg):
    """The aggregate as the drawing script reads it: rows as short arrays, links sharing a prefix."""
    rows = [r for p in agg["pages"] for g in p["groups"] for r in g["rows"]]
    prefix = os.path.commonprefix([r["href"] for r in rows]) if rows else ""
    prefix = prefix[:prefix.rfind("&") + 1] if "&" in prefix else ""
    return {
        "site": agg["site_name"], "window": agg["window_label"], "linkPrefix": prefix,
        "days": [[d["label"]] + (d["wh"] or [None, None]) for d in agg["days"]],
        "ids": [PAGE_IDS.get(p["title"], f"page-{i}") for i, p in enumerate(agg["pages"])],
        "pages": [[p["title"], [[g["name"], [[r["name"], r["runs"], r.get("gaps", []), r.get("nodata") or "",
                                              int(bool(r.get("level_break"))), r["href"][len(prefix):],
                                              r.get("point") or ""] for r in g["rows"]]]
                                for g in p["groups"]]] for p in agg["pages"]],
    }


def constants():
    return {
        "in": C_IN_HOURS, "out": C_OUT_OF_HOURS, "band": C_WH_BAND, "midnight": C_MIDNIGHT,
        "hatchBg": C_HATCH_BG, "hatchLine": C_HATCH_LINE, "text": C_TEXT, "muted": C_MUTED, "card": C_CARD,
        "fsTitle": FS_TITLE, "fsSubtitle": FS_SUBTITLE, "fsLegend": FS_LEGEND, "fsDay": FS_DAY,
        "fsHours": FS_HOURS, "fsGroup": FS_GROUP, "fsRow": FS_ROW,
        "width": WIDTH, "labelCol": LABEL_COL, "rightPad": RIGHT_PAD, "leftPad": LEFT_PAD,
        "rowIndent": ROW_INDENT, "labelMaxW": LABEL_MAX_W, "titleY": TITLE_Y, "subtitleY": SUBTITLE_Y,
        "legendY": LEGEND_Y, "legendW": LEGEND_W, "gridTop": GRID_TOP, "rowH": ROW_H, "barH": BAR_H,
        "groupH": GROUP_H, "groupGap": GROUP_GAP, "levelGap": LEVEL_GAP, "bottomPad": BOTTOM_PAD,
        "overlap": BAR_OVERLAP,
    }


def _js(obj):
    return json.dumps(obj, separators=(",", ":"), ensure_ascii=False).replace("</", "<\\/")


# ---- Render ------------------------------------------------------------------
def render(agg):
    check(agg)
    data = compact(agg)
    sections = "\n".join(f'  <section class="page" id="{i}" aria-label="{escape(p[0])}"></section>'
                         for i, p in zip(data["ids"], data["pages"]))
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(agg['site_name'])} Run Hours</title>
<style>
  :root {{ --bg: {C_PAGE_BG}; --card: {C_CARD}; --line: {C_CARD_LINE}; --muted: {C_MUTED}; --text: {C_TEXT}; }}
  * {{ box-sizing: border-box; }}
  body {{ margin: 0; background: var(--bg); color: var(--text); font-family: {FONT_STACK}; }}
  main {{ max-width: {WIDTH + 32}px; margin: 0 auto; padding: 24px 16px 48px; }}
  .page {{ background: var(--card); border: 1px solid var(--line); border-radius: 12px;
           padding: 8px; margin: 0 0 24px; overflow: hidden; }}
  .page svg {{ display: block; font-family: inherit; }}
  .page svg a {{ cursor: pointer; }}
  .page svg a:hover .nm, .page svg a:focus .nm {{ text-decoration: underline; }}
  footer {{ color: var(--muted); font-size: 12px; line-height: 1.6; padding: 0 4px; }}
  @media print {{
    body {{ background: #fff; }}
    main {{ max-width: none; padding: 0; }}
    .page {{ border: none; border-radius: 0; padding: 0; margin: 0; break-after: page; }}
    footer {{ display: none; }}
  }}
</style>
</head>
<body>
<main>
{sections}
  <noscript><p>This view draws with JavaScript. Open the file in a web browser.</p></noscript>
  <footer>{escape(agg.get('footer', ''))}</footer>
</main>
<script>
const K = {_js(constants())};
const D = {_js(data)};
{SCRIPT.strip()}
</script>
</body>
</html>
"""


def default_name(agg):
    site = re.sub(r"[^a-z0-9]+", "-", agg["site_name"].lower()).strip("-")
    words = [w for w in agg["window_label"].split() if w not in ("Mon", "Sun", "to")]
    return f"{site}-run-hours-{'-'.join(words).lower()}.html"


def main(argv):
    if len(argv) != 3:
        sys.exit("usage: python3 render_runhours.py <agg.json> <out.html | out-dir>")
    try:
        with open(argv[1]) as fh:
            agg = json.load(fh)
    except (OSError, ValueError) as exc:
        sys.exit(f"could not read aggregate JSON {argv[1]}: {exc}")
    try:
        page = render(agg)
        out = Path(argv[2])
        out = out / default_name(agg) if out.is_dir() else out
    except (KeyError, TypeError, IndexError, ValueError) as exc:
        sys.exit(f"aggregate JSON is missing or has a malformed field: {exc}")
    try:
        out.write_text(page)
    except OSError as exc:
        sys.exit(f"could not write HTML {out}: {exc}")
    print(out)


if __name__ == "__main__":
    main(sys.argv)
