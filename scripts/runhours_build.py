#!/usr/bin/env python3
"""Turn a run-hours plan and its history pulls into the view's aggregate.

Usage:
    python3 runhours_build.py <workdir> <history.json> [more.json ...] [--pass 2]

Reads <workdir>/window.json and plan.json, loads the pulled history, decides
each unit's row — status or analog, whichever shows less running — and writes
<workdir>/agg.json (the renderer's only input) and <workdir>/days.csv (per unit
per day, for follow-ups). Prints the notes to state with the view.

--pass 2 adds the later pass once its history has been pulled; pass every
history file from both passes.

Standard library only — no third-party dependencies, by design, so the script
runs wherever the skill is unpacked.
"""
import argparse
import csv
import json
import sys
from collections import Counter
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from runhours_history import load_rows  # noqa: E402

# ---- Tunables ----------------------------------------------------------------
SLOTS_PER_DAY   = 96     # 15-minute slots
WEEK            = 7 * SLOTS_PER_DAY
BRIDGE_SLOTS    = 4      # a gap up to an hour holds the last reading; longer is hatched
ANALOG_ON_SHARE = 0.05   # an analog is ON above 5% of its own weekly maximum
DISAGREE_HOURS  = 2.0    # status and analog this far apart (and 10%) get a note
NAMES_IN_NOTE   = 8      # list names in a note up to this many, then just count
PAGE_ORDER      = ["Central plant", "Field units", "Other"]
SIGNAL_WORDS    = {"status": "run status", "analog": "speed or other analog",
                   "command": "enable or command", "compressor": "compressor status"}


# ---- Slots -------------------------------------------------------------------
def slot_readings(rows, window):
    """fav_id -> {absolute slot: max reading}, on the site's wall clock."""
    from zoneinfo import ZoneInfo           # stdlib from 3.9; needs the system tz database
    tz = ZoneInfo(window["timezone"])
    monday = date.fromisoformat(window["days"][0]["date"])
    out = {}
    for row in rows:
        local = datetime.fromisoformat(str(row["ts"]).replace("Z", "+00:00")).astimezone(tz)
        day = (local.date() - monday).days
        if not 0 <= day < 7 or row.get("data") is None:
            continue
        slot = day * SLOTS_PER_DAY + (local.hour * 60 + local.minute) // 15
        cell = out.setdefault(str(row["fav_id"]), {})
        cell[slot] = max(float(row["data"]), cell.get(slot, float("-inf")))
    return out


def bridge(raw):
    """Hold the last reading across gaps of up to BRIDGE_SLOTS; leave longer gaps None."""
    out, i = list(raw), 0
    while i < WEEK:
        if out[i] is not None:
            i += 1
            continue
        j = i
        while j < WEEK and out[j] is None:
            j += 1
        if j - i <= BRIDGE_SLOTS:
            fill = out[i - 1] if i > 0 else (out[j] if j < WEEK else None)
            out[i:j] = [fill] * (j - i)
        i = j
    return out


def read_point(readings, point):
    """ON/OFF per slot for one pulled point, plus what the decision needs to know."""
    if not readings:
        return None
    raw = [readings.get(s) for s in range(WEEK)]
    values = [v for v in raw if v is not None]
    distinct = set(values)
    if point["role"] == "analog":
        top = max(values)
        cut = ANALOG_ON_SHARE * top if top > 0 else float("inf")
        is_on = lambda v: v > cut                                    # noqa: E731
    else:
        whole = all(float(v).is_integer() for v in distinct)
        multistate = "(msv)" in point["name"].lower() or (whole and min(distinct) >= 1
                                                          and max(distinct) >= 2)
        cut = 2 if multistate else 0.5                               # {1,2}: 2 is ON; {0,1}: 1 is ON
        is_on = lambda v: v >= cut                                   # noqa: E731
    on = [None if v is None else is_on(v) for v in bridge(raw)]
    return {"on": on, "stuck": len(distinct) == 1, "held": values[0] if len(distinct) == 1 else None,
            "hours": sum(1 for x in on if x) / 4}


def ranges(flags, want):
    """Merged [start, end) slot ranges where flags[i] is `want` (True for ON, None for a gap)."""
    out, start = [], None
    for i, flag in enumerate(list(flags) + ["end"]):
        if flag is want and start is None:
            start = i
        elif flag is not want and start is not None:
            out.append([start, i])
            start = None
    return out


def common_hours(a, b):
    """Hours ON for each of two points, over the slots both reported."""
    both = [(x, y) for x, y in zip(a["on"], b["on"]) if x is not None and y is not None]
    return sum(1 for x, _ in both if x) / 4, sum(1 for _, y in both if y) / 4


# ---- The row decision ----------------------------------------------------------
def decide(unit, points):
    """(chosen point, its reading, compared point, reason for no data, disagreement)."""
    got = {p["role"]: (p, points.get(str(p["fav_id"]))) for p in unit["pull"]}
    sp, sr = got.get("status", (None, None))
    ap, ar = got.get("analog", (None, None))
    if sp and ap:
        if sr and ar:
            if not sr["stuck"] and not ar["stuck"]:
                hs, ha = common_hours(sr, ar)
                gap = abs(hs - ha)
                split = (sp, hs, ap, ha) if gap >= max(DISAGREE_HOURS, 0.1 * max(hs, ha)) else None
                return ((ap, ar, sp) if ha < hs else (sp, sr, ap)) + (None, split)
            if sr["stuck"] and not ar["stuck"]:
                return ap, ar, sp, None, None
            if ar["stuck"] and not sr["stuck"]:
                return sp, sr, ap, None, None
            if (sr["hours"] > 0) == (ar["hours"] > 0):      # both held, and they agree
                return sp, sr, ap, None, None
            return None, None, None, (f"{sp['name']} and {ap['name']} each held one value "
                                      "all week and disagree, so run time is unknown"), None
        if not (sr or ar):
            return None, None, None, "No data this week", None
        p, r, other = (sp, sr, None) if sr else (ap, ar, None)
    else:
        p = unit["pull"][0]
        r, other = points.get(str(p["fav_id"])), None
        if not r:
            return None, None, None, "No data this week", None
    if p["role"] == "analog" and r["stuck"] and r["held"] > 0:
        return None, None, None, f"{p['name']} held one value all week, so run time is unknown", None
    return p, r, other, None, None


# ---- Text helpers --------------------------------------------------------------
def hhmm(slot):
    return "24:00" if slot >= SLOTS_PER_DAY else f"{slot * 15 // 60:02d}:{slot * 15 % 60:02d}"


def hours_text(wh):
    return "closed" if not wh else f"{hhmm(wh[0])}-{hhmm(wh[1])}"


def working_hours_note(window):
    groups = []
    for day in window["days"]:
        text = hours_text(day["wh"])
        if groups and groups[-1][1] == text:
            groups[-1][0].append(day["label"][:3])
        else:
            groups.append(([day["label"][:3]], text))
    parts = [(f"{d[0]}-{d[-1]}" if len(d) > 1 else d[0]) + f" {t}" for d, t in groups]
    source = "the site's PEAK settings" if window.get("hours_source") != "user" else "the user"
    return f"Working hours from {source}: {', '.join(parts)} ({window['tz_label']})."


def units_text(n):
    return f"{n} unit" + ("" if n == 1 else "s")


def listing(names):
    names = list(names)
    if len(names) <= NAMES_IN_NOTE:
        return ", ".join(names)
    return ", ".join(names[:NAMES_IN_NOTE]) + f" and {len(names) - NAMES_IN_NOTE} more"


def chart_link(window, unit, favs):
    return (f"{window['link_host']}/charts?split=false&splitbyunit=false&splitbyequip=false"
            f"&start={window['link_start']}&end={window['link_end']}&workinghours=true"
            f"&fav-{unit['equipment_id']}={','.join(str(f) for f in favs)}")


# ---- Build -------------------------------------------------------------------
def build(window, plan, rows, max_pass):
    units = [u for u in plan["units"] if u["pass"] <= max_pass]
    readings = slot_readings(rows, window)
    points = {str(p["fav_id"]): read_point(readings.get(str(p["fav_id"])), p)
              for u in units for p in u["pull"]}

    notes = {"split": [], "unverified": [], "command": [], "compressor": [], "nodata": [],
             "gaps": [], "drawn": Counter()}
    pages, csv_rows, prev = {}, [], None
    for u in (u for u in units if u["pull"]):
        chosen, reading, other, nodata, split = decide(u, points)
        row = {"name": u["name"], "runs": [], "gaps": [], "nodata": nodata, "point": None,
               "level_break": bool(prev and prev["type_name"] == u["type_name"]
                                   and prev["level"] != u["level"])}
        prev = u
        favs = [p["fav_id"] for p in u["pull"]]
        if chosen:
            favs = [chosen["fav_id"]] + ([other["fav_id"]] if other else [])
            row["point"] = chosen["name"]
            row["runs"] = ranges(reading["on"], True)
            row["gaps"] = ranges(reading["on"], None)
            notes["drawn"][chosen["role"]] += 1
            if split:
                sp, hs, ap, ha = split
                notes["split"].append(f"{u['name']} ({sp['name']} {hs:g} h, {ap['name']} {ha:g} h, "
                                      f"drew {chosen['name']})")
            if chosen["role"] == "status" and not other and reading["stuck"] and reading["hours"]:
                notes["unverified"].append(u["name"])
            if chosen["role"] in ("command", "compressor"):
                notes[chosen["role"]].append(u["name"])
            if row["gaps"]:
                notes["gaps"].append(u["name"])
            csv_rows += day_rows(window, u, chosen, reading)
        else:
            notes["nodata"].append(f"{u['name']} ({nodata.rstrip('.')})")
        row["href"] = chart_link(window, u, favs)
        page = pages.setdefault(u["page"], {})
        page.setdefault(u["type_name"], []).append(row)

    agg = {
        "site_name": window["site_name"], "window_label": window["label"],
        "tz_label": window["tz_label"],
        "days": [{"label": d["label"], "wh": d["wh"]} for d in window["days"]],
        "pages": [{"title": title, "groups": [{"name": g, "rows": rs} for g, rs in pages[title].items()]}
                  for title in PAGE_ORDER if title in pages],
        "footer": ("Each row is drawn from the unit's run status or a speed, current or power reading, "
                   "whichever shows less running when both report, and from an enable or command point "
                   "only where neither exists. Click a unit name to open its PEAK chart for the same "
                   "week with the points that decided the row. Hover a bar for exact on and off times. "
                   "Source: PEAK point history at 15-minute resolution, times in site local time "
                   f"({window['tz_label']})."),
    }
    agg["notes"] = note_lines(window, plan, units, notes, max_pass)
    return agg, csv_rows


def day_rows(window, unit, chosen, reading):
    out = []
    for i, day in enumerate(window["days"]):
        on = reading["on"][i * SLOTS_PER_DAY:(i + 1) * SLOTS_PER_DAY]
        wh = day["wh"] or [0, 0]
        lit = [s for s, x in enumerate(on) if x]
        out.append({"name": unit["name"], "type": unit["type_name"], "date": day["date"],
                    "run_h": len(lit) / 4,
                    "first_on": hhmm(lit[0]) if lit else "",
                    "last_off": hhmm(lit[-1] + 1) if lit else "",
                    "ooh_h": sum(1 for s in lit if not wh[0] <= s < wh[1]) / 4,
                    "signal": chosen["role"], "point": chosen["name"]})
    return out


def note_lines(window, plan, units, notes, max_pass):
    lines = [working_hours_note(window)]
    drawn = notes["drawn"]
    lines.append("Rows drawn from: " + ", ".join(f"{SIGNAL_WORDS[r]} {drawn[r]}"
                                                   for r in SIGNAL_WORDS if drawn[r]) + ".")
    if notes["split"]:
        lines.append(f"Status and analog disagreed at {units_text(len(notes['split']))}, each drawn "
                     f"from the one showing less running: {listing(notes['split'])}.")
    if notes["unverified"]:
        lines.append(f"On all week from a status with no speed to check it against, which may be a "
                     f"stuck switch: {listing(notes['unverified'])}.")
    if notes["command"]:
        lines.append(f"Drawn from an enable or command, so they show what the unit was told to do, not "
                     f"confirmed running: {listing(notes['command'])}.")
    if notes["compressor"]:
        lines.append(f"Compressor status only, so they show when the compressor ran, not whether the "
                     f"fan did: {listing(notes['compressor'])}.")
    if notes["nodata"]:
        lines.append(f"Hatched, no reliable data: {listing(notes['nodata'])}.")
    if notes["gaps"]:
        lines.append(f"Hatched stretches are data gaps over an hour: {listing(notes['gaps'])}.")
    regrouped = [u for u in units if u.get("regrouped_from")]
    for (was, name), n in Counter((u["regrouped_from"], u["type_name"]) for u in regrouped).items():
        lines.append(f"{units_text(n)} typed {was} in PEAK, grouped with {name} as their names say.")
    skipped = [u for u in units if not u["pull"]]
    for why in ("no usable run point", "no history this week", "pair point, members charted"):
        hit = [u for u in skipped if u["why"] == why]
        if not hit:
            continue
        if why == "pair point, members charted":
            lines.append(f"Left out because their member units are shown: {listing(u['name'] for u in hit)}.")
        elif why == "no history this week":
            lines.append(f"No history this week, not drawn: {listing(u['name'] for u in hit)}.")
        else:
            by_type = Counter(u["type_name"] for u in hit)
            central = [u["name"] for u in hit if u["page"] == "Central plant"]
            text = ", ".join(f"{t} {n}" for t, n in by_type.most_common())
            lines.append(f"No usable run point, not drawn: {text}"
                         + (f" (central plant: {listing(central)})" if central else "") + ".")
    if plan.get("unclassified"):
        lines.append("Equipment types the run-hours reference does not cover yet, not drawn: "
                     + ", ".join(f"{u['type']} ({u['units']})" for u in plan["unclassified"]) + ".")
    later = [u for u in plan["units"] if u["pull"] and u["pass"] > max_pass]
    if later:
        by_type = Counter(u["type_name"] for u in later)
        calls = sum(1 for c in plan["chunks"] if c["pass"] > max_pass)
        lines.append(f"Not fetched yet: {units_text(len(later))} in {len(by_type)} types ("
                     + ", ".join(f"{t} {n}" for t, n in by_type.items())
                     + f"), {calls} more history calls. Offer to fetch them.")
    return lines


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("workdir")
    parser.add_argument("history", nargs="+", help="saved platform.history results")
    parser.add_argument("--pass", dest="max_pass", type=int, default=1,
                        help="include the later pass (2) once it has been pulled")
    args = parser.parse_args(argv[1:])
    work = Path(args.workdir)
    try:
        window = json.loads((work / "window.json").read_text())
        plan = json.loads((work / "plan.json").read_text())
        fav_ids = [p["fav_id"] for u in plan["units"] if u["pass"] <= args.max_pass
                   for p in u["pull"]]
        rows = load_rows(args.history, fav_ids)
        agg, days = build(window, plan, rows, args.max_pass)
    except (OSError, ValueError, KeyError) as exc:
        sys.exit(f"runhours_build: {exc}")
    (work / "agg.json").write_text(json.dumps(agg, indent=1))
    with open(work / "days.csv", "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=["name", "type", "date", "run_h", "first_on",
                                                "last_off", "ooh_h", "signal", "point"])
        writer.writeheader()
        writer.writerows(days)
    drawn = sum(len(g["rows"]) for p in agg["pages"] for g in p["groups"])
    print(f"{window['site_name']}: {drawn} rows from {len(rows)} history rows. "
          f"Wrote {work / 'agg.json'} and {work / 'days.csv'}.")
    print("Notes:")
    for line in agg["notes"]:
        print(f"- {line}")


if __name__ == "__main__":
    main(sys.argv)
