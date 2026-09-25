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
import math
import re
import sys
from collections import Counter
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from runhours_history import load_rows  # noqa: E402

# ---- Tunables ----------------------------------------------------------------
SLOTS_PER_DAY   = 96     # 15-minute slots
WEEK            = 7 * SLOTS_PER_DAY
BRIDGE_SLOTS    = 4      # a gap up to an hour holds the last reading; longer is hatched ...
HOLD_FACTOR     = 1.5    # ... unless the point reports less often: then 1.5 times its usual interval
ANALOG_ON_SHARE = 0.05   # an analog is ON above 5% of its own weekly maximum
DISAGREE_HOURS  = 2.0    # status and analog this far apart (and 10%) get a note
ONE_OFF_RUNS    = 1      # a signal that switched on this often or less ...
PATTERN_RUNS    = 3      # ... gives way to one that switched on at least this often
CHANGE_LOG_SHARE = 0.5   # a point with readings in under half the week's slots ...
CHANGE_READINGS = 0.8    # ... where this share of readings differ from the one before logs on change
NAMES_IN_NOTE   = 8      # list names in a note up to this many, then just count
GENERIC_ZONE    = re.compile(r"(zone|area|default|all|general|none|n/?a|unassigned|site|building)\s*\d*", re.I)
PAGE_ORDER      = ["Central plant", "Field units", "Other"]
SIGNAL_WORDS    = {"status": "run status", "state": "speed state", "analog": "speed or other analog",
                   "compressor": "compressor status"}


# ---- Slots -------------------------------------------------------------------
def slot_readings(rows, window):
    """fav_id -> {"slots": {absolute slot: (max, last reading)}, "series": readings in time order}.

    Slots are on the site's wall clock. A slot is ON if the point was on at any
    reading in it; the gap after it holds the slot's last reading.
    """
    from zoneinfo import ZoneInfo           # stdlib from 3.9; needs the system tz database
    tz = ZoneInfo(window["timezone"])
    monday = date.fromisoformat(window["days"][0]["date"])
    stamped = []
    for row in rows:
        if row.get("data") is None:
            continue
        local = datetime.fromisoformat(str(row["ts"]).replace("Z", "+00:00")).astimezone(tz)
        day = (local.date() - monday).days
        if 0 <= day < 7:
            stamped.append((str(row["fav_id"]), local, day, float(row["data"])))
    out = {}
    for fav, local, day, value in sorted(stamped, key=lambda s: (s[0], s[1])):
        slot = day * SLOTS_PER_DAY + (local.hour * 60 + local.minute) // 15
        rec = out.setdefault(fav, {"slots": {}, "series": []})
        prev = rec["slots"].get(slot)
        rec["slots"][slot] = (max(value, prev[0]) if prev else value, value)
        rec["series"].append(value)
    return out


def bridge(raw, last, hold=BRIDGE_SLOTS, on_change=False, before=None):
    """Hold the last reading across gaps of up to `hold` slots; leave longer gaps None.

    A point logged on change of value holds every reading until the next, to the
    end of the week — silence is the value not changing. Before its first reading
    it holds `before` where that is known, and is left None where it is not.
    """
    out, i = list(raw), 0
    while i < WEEK:
        if out[i] is not None:
            i += 1
            continue
        j = i
        while j < WEEK and out[j] is None:
            j += 1
        if on_change and i == 0:
            out[i:j] = [before] * j
        elif on_change or j - i <= hold:
            fill = last[i - 1] if i > 0 else (out[j] if j < WEEK else None)
            out[i:j] = [fill] * (j - i)
        i = j
    return out


def hold_slots(slots):
    """How long a reading holds: 1.5 times the point's usual interval, and never under an hour.

    Most points report every 15 minutes, so a silence over an hour is an outage.
    Some are polled far less often — a status every 4 hours, with a reading at
    each change — and hold 6.
    """
    marks = sorted(slots)
    steps = sorted(b - a for a, b in zip(marks, marks[1:]))
    usual = steps[len(steps) // 2] if steps else 1
    return max(BRIDGE_SLOTS, math.ceil(HOLD_FACTOR * usual))


def logged_on_change(series):
    """Whether a point reports on change of value rather than every 15 minutes.

    Such a point sends a handful of readings a week, and nearly every one differs
    from the one before; a periodic point sends one a slot, mostly unchanged. A
    typical one sends ten readings a week, at 07:00 and 18:00, each a change.
    """
    if len(series) < 2 or len(series) > WEEK * CHANGE_LOG_SHARE:
        return False
    changes = sum(1 for a, b in zip(series, series[1:]) if a != b)
    return changes >= CHANGE_READINGS * (len(series) - 1)


def on_cut(point, distinct):
    """The reading at and above which a status, state or command point is ON.

    Binary: 1. A speed state (MSV) counts from 0 when the week shows a 0 — 0 is
    off — and otherwise from 1, the BACnet numbering, where 1 is off. Any other
    whole-number point numbered from 1 is read the same way.
    """
    if "(msv)" in point["name"].lower():
        return 1 if min(distinct) == 0 else 2
    whole = all(float(v).is_integer() for v in distinct)
    return 2 if whole and min(distinct) >= 1 and max(distinct) >= 2 else 0.5


def read_point(rec, point):
    """ON/OFF per slot for one pulled point, plus what the decision needs to know."""
    if not rec:
        return None
    slots, series = rec["slots"], rec["series"]
    raw = [slots[s][0] if s in slots else None for s in range(WEEK)]
    last = [slots[s][1] if s in slots else None for s in range(WEEK)]
    distinct = set(series)
    if point["role"] == "analog":
        top = max(series)
        cut = ANALOG_ON_SHARE * top if top > 0 else float("inf")
        is_on = lambda v: v > cut                                    # noqa: E731
    else:
        cut = on_cut(point, distinct)
        is_on = lambda v: v >= cut                                   # noqa: E731
    on_change = logged_on_change(series)
    before = None
    if on_change and distinct <= {0.0, 1.0} and all(a != b for a, b in zip(series, series[1:])):
        before = 1.0 - series[0]              # a switch that logs only changes was the other way before
    on = [None if v is None else is_on(v) for v in bridge(raw, last, hold_slots(slots), on_change, before)]
    return {"on": on, "stuck": len(distinct) == 1, "held": series[0] if len(distinct) == 1 else None,
            "hours": sum(1 for x in on if x) / 4, "runs": len(ranges(on, True)), "on_change": on_change}


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
class Row:
    """What decide() settled for one unit."""

    def __init__(self, point=None, reading=None, other=None, nodata=None, split=None, held=None):
        self.point, self.reading, self.other = point, reading, other
        self.nodata, self.split, self.held = nodata, split, held


def held_running(point, reading):
    """A speed or speed state held at one running value all week: it shows a setting, not when it ran.

    A true status held on is different — it says the unit ran — and is kept, named as unverified.
    """
    if not reading["stuck"]:
        return False
    if point["role"] == "analog":
        return reading["held"] > 0
    return bool(point.get("state")) and reading["hours"] > 0


def decide(unit, points):
    """Which sensor draws the row, following the decision table in references/run-hours.md."""
    got = {p["role"]: (p, points.get(str(p["fav_id"]))) for p in unit["pull"]}
    sp, sr = got.get("status", (None, None))
    ap, ar = got.get("analog", (None, None))
    if sp and ap and sr and ar:
        return both_signals(sp, sr, ap, ar)
    p, r = (sp, sr) if sr else (ap, ar) if ar else (unit["pull"][0], points.get(str(unit["pull"][0]["fav_id"])))
    if not r:
        return Row(nodata="No data this week")
    if held_running(p, r):
        what = "one state" if p.get("state") else "one value"
        return Row(nodata=f"{p['name']} held {what} all week, so run time is unknown", held=p)
    return Row(p, r)


def both_signals(sp, sr, ap, ar):
    """Status beside analog: set aside a held one; else whichever shows less running.

    A signal that switched on no more than once all week, beside one that
    switched on and off to a pattern, has stopped following the unit — a speed
    on for 15 minutes all week beside a status that ran thirteen times. It gives
    way however little it shows.
    """
    if not sr["stuck"] and not ar["stuck"]:
        hs, ha = common_hours(sr, ar)
        small, large = ((ap, ar), (sp, sr)) if ha < hs else ((sp, sr), (ap, ar))
        one_off = small[1]["runs"] <= ONE_OFF_RUNS and large[1]["runs"] >= PATTERN_RUNS
        chosen, other = (large, small) if one_off else (small, large)
        gap = abs(hs - ha)
        split = (sp, hs, ap, ha, one_off and small[0]) if gap >= max(DISAGREE_HOURS, 0.1 * max(hs, ha)) else None
        return Row(chosen[0], chosen[1], other[0], split=split)
    if sr["stuck"] and not ar["stuck"]:
        return Row(ap, ar, sp)
    if ar["stuck"] and not sr["stuck"]:
        return Row(sp, sr, ap)
    if (sr["hours"] > 0) == (ar["hours"] > 0):          # both held, and they agree
        return Row(sp, sr, ap)
    return Row(nodata=f"{sp['name']} and {ap['name']} each held one value all week and disagree, "
                      "so run time is unknown")


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


def by_type(units):
    return ", ".join(f"{t} {n}" for t, n in Counter(u["type_name"] for u in units).most_common())


def chart_link(window, unit, favs):
    return (f"{window['link_host']}/charts?split=false&splitbyunit=false&splitbyequip=false"
            f"&start={window['link_start']}&end={window['link_end']}&workinghours=true"
            f"&fav-{unit['equipment_id']}={','.join(str(f) for f in favs)}")


def signal_kind(point):
    return "state" if point.get("state") else point["role"]


def _words(text):
    return re.findall(r"[a-z0-9]+", (text or "").lower())


def _within(part, whole):
    """Whether part's words run, in order, somewhere in whole."""
    p, w = _words(part), _words(whole)
    return bool(p) and any(w[i:i + len(p)] == p for i in range(len(w) - len(p) + 1))


def where(unit):
    """([level, zone] for the label, "" where dropped, and hover text); the label keeps only what informs.

    A zone is dropped where it is a default (Zone1, All), repeats the level, or is in
    the unit's own name (FCU Kitchen-A in zone Kitchen); a level that a more
    specific zone repeats gives way to it ('Level 2' beside 'Level 2 Kitchen'), and
    'Level 3' is shortened to 'L3'. The hover keeps both as PEAK has them.
    """
    level, zone = (" ".join((unit.get(k) or "").split()) for k in ("level", "zone"))
    hover = " · ".join(x for x in (level, zone) if x)
    if zone and (GENERIC_ZONE.fullmatch(zone) or _within(zone, unit["name"]) or _within(zone, level)):
        zone = ""
    if level and zone and _within(level, zone):
        level = ""
    level = re.sub(r"\blevel\s+(\d+)\b", r"L\1", level, flags=re.I)
    return ([level, zone] if level or zone else []), hover


# ---- Build -------------------------------------------------------------------
def build(window, plan, rows, max_pass):
    units = [u for u in plan["units"] if u["pass"] <= max_pass]
    readings = slot_readings(rows, window)
    points = {str(p["fav_id"]): read_point(readings.get(str(p["fav_id"])), p)
              for u in units for p in u["pull"]}

    notes = {"split": [], "unverified": [], "compressor": [], "held": [], "on_change": [],
             "nodata": [], "gaps": [], "drawn": Counter()}
    pages, csv_rows, prev = {}, [], None
    for u in (u for u in units if u["pull"]):
        d = decide(u, points)
        row = {"name": u["name"], "runs": [], "gaps": [], "nodata": d.nodata, "point": None,
               "level_break": bool(prev and prev["type_name"] == u["type_name"]
                                   and prev["level"] != u["level"])}
        row["where"], row["where_full"] = where(u)
        prev = u
        favs = [p["fav_id"] for p in u["pull"]]
        if d.point:
            favs = [d.point["fav_id"]] + ([d.other["fav_id"]] if d.other else [])
            row["point"] = d.point["name"]
            row["runs"] = ranges(d.reading["on"], True)
            row["gaps"] = ranges(d.reading["on"], None)
            kind = signal_kind(d.point)
            notes["drawn"][kind] += 1
            if d.split:
                sp, hs, ap, ha, one_off = d.split
                why = f"; {one_off['name']} switched on only once" if one_off else ""
                notes["split"].append(f"{u['name']} ({sp['name']} {hs:g} h, {ap['name']} {ha:g} h, "
                                      f"drew {d.point['name']}{why})")
            if kind == "status" and not d.other and d.reading["stuck"] and d.reading["hours"]:
                notes["unverified"].append(u["name"])
            if kind == "compressor":
                notes["compressor"].append(u["name"])
            if d.reading["on_change"]:
                notes["on_change"].append(u["name"])
            if row["gaps"]:
                notes["gaps"].append(u["name"])
            csv_rows += day_rows(window, u, d.point, d.reading)
        elif d.held:
            notes["held"].append(u["name"])
        else:
            notes["nodata"].append(f"{u['name']} ({d.nodata.rstrip('.')})")
        row["href"] = chart_link(window, u, favs)
        page = pages.setdefault(u["page"], {})
        page.setdefault(u["type_name"], []).append(row)

    agg = {
        "site_name": window["site_name"], "window_label": window["label"],
        "tz_label": window["tz_label"],
        "days": [{"label": d["label"], "wh": d["wh"]} for d in window["days"]],
        "pages": [{"title": title, "groups": [{"name": g, "rows": rs} for g, rs in pages[title].items()]}
                  for title in PAGE_ORDER if title in pages],
        "footer": ("Each row is drawn from a sensor: the unit's run status or a speed, current or power "
                   "reading, whichever shows less running when both report. Units with only an enable or "
                   "schedule are left out. Click a unit name to open its PEAK chart for the same week with "
                   "the points that decided the row. Hover a bar for exact on and off times. Source: PEAK "
                   "point history at 15-minute resolution, times in site local time "
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
        out.append({"name": unit["name"], "type": unit["type_name"], "level": unit.get("level") or "",
                    "zone": unit.get("zone") or "", "date": day["date"],
                    "run_h": len(lit) / 4,
                    "first_on": hhmm(lit[0]) if lit else "",
                    "last_off": hhmm(lit[-1] + 1) if lit else "",
                    "ooh_h": sum(1 for s in lit if not wh[0] <= s < wh[1]) / 4,
                    "signal": signal_kind(chosen), "point": chosen["name"]})
    return out


def note_lines(window, plan, units, notes, max_pass):
    lines = [working_hours_note(window)]
    drawn = notes["drawn"]
    lines.append("Rows drawn from: " + ", ".join(f"{SIGNAL_WORDS[r]} {drawn[r]}"
                                                   for r in SIGNAL_WORDS if drawn[r]) + ".")
    if notes["split"]:
        lines.append(f"Status and analog disagreed at {units_text(len(notes['split']))}, each drawn "
                     f"from the one showing less running unless the other switched on only once: "
                     f"{listing(notes['split'])}.")
    if notes["held"]:
        lines.append(f"Speed held at one setting all week, so run time is unknown and the row is hatched: "
                     f"{listing(notes['held'])}.")
    if notes["unverified"]:
        lines.append(f"On all week from a status with no speed to check it against, which may be a "
                     f"stuck switch: {listing(notes['unverified'])}.")
    if notes["on_change"]:
        lines.append(f"Logged on change of value rather than every 15 minutes, so each reading holds until "
                     f"the next: {listing(notes['on_change'])}.")
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
    hit = {why: [u for u in skipped if u["why"] == why]
           for why in ("command only", "alarms only", "no history this week", "pair point, members charted",
                       "no points", "shared record", "sensors or setpoints only")}
    if hit["command only"]:
        lines.append("Only an enable, command or schedule, with no sensor to show the unit ran, not drawn: "
                     f"{listing(u['name'] for u in hit['command only'])} ({by_type(hit['command only'])}).")
    if hit["alarms only"]:
        lines.append(f"Plant with alarms but no run point, not drawn: {listing(u['name'] for u in hit['alarms only'])} "
                     f"({by_type(hit['alarms only'])}).")
    if hit["no history this week"]:
        lines.append(f"No history this week, not drawn: {listing(u['name'] for u in hit['no history this week'])}.")
    if hit["pair point, members charted"]:
        lines.append("Left out because their member units are shown: "
                     f"{listing(u['name'] for u in hit['pair point, members charted'])}.")
    if hit["no points"]:
        lines.append(f"No points in PEAK, not drawn: {by_type(hit['no points'])}.")
    if hit["shared record"]:
        n = len(hit["shared record"])
        lines.append(f"{n} shared COMMON record{'s carry' if n != 1 else ' carries'} no sensor of "
                     f"{'their' if n != 1 else 'its'} own, not drawn ({by_type(hit['shared record'])}).")
    if hit["sensors or setpoints only"]:
        records = hit["sensors or setpoints only"]
        n = len(records)
        lines.append(f"{n} record{'s carry' if n != 1 else ' carries'} only sensors, setpoints or dampers, "
                     f"not drawn ({by_type(records)}), e.g. {', '.join(u['name'] for u in records[:3])}.")
    if plan.get("unclassified"):
        lines.append("Equipment types the run-hours reference does not cover yet, not drawn: "
                     + ", ".join(f"{u['type']} ({u['units']})" for u in plan["unclassified"]) + ".")
    if plan.get("unknown_units"):
        lines.append(f"{units_text(plan['unknown_units'])} at the site are of a type the run-hours reference "
                     "does not cover yet, not drawn: PEAK has added a type. List the site's equipment "
                     "types to name it, and add it to references/run-hours-signals.md.")
    later = [u for u in plan["units"] if u["pull"] and u["pass"] > max_pass]
    if later:
        types = Counter(u["type_name"] for u in later)
        calls = sum(1 for c in plan["chunks"] if c["pass"] > max_pass)
        lines.append(f"Not fetched yet: {units_text(len(later))} in {len(types)} types ("
                     + ", ".join(f"{t} {n}" for t, n in types.items())
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
        writer = csv.DictWriter(fh, fieldnames=["name", "type", "level", "zone", "date", "run_h",
                                                "first_on", "last_off", "ooh_h", "signal", "point"])
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
