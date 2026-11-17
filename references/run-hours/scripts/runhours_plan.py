#!/usr/bin/env python3
"""Plan a run-hours pull: which week, which points, and in what order.

Usage:
    python3 runhours_plan.py window <site.json> <workdir> [--week-of YYYY-MM-DD]
                                    [--hours "Mon-Fri 08:00-18:00, Sat 09:00-13:00"]
    python3 runhours_plan.py plan <workdir> <discovery.json> [more.json ...] [--cap N]
    python3 runhours_plan.py calls <workdir> [--pass 2]
    python3 runhours_plan.py last <workdir> <last-reading.json>

window  Reads the saved search_sites result (timezone and working hours), fixes
        the last full Monday-to-Sunday week in site local time, writes
        <workdir>/window.json and prints the discovery call to make.
        --hours assesses against the user's hours instead of the site's.
plan    Keeps each unit's metadata listed for its equipment type in
        references/run-hours/run-hours-signals.md, orders the units for the view, splits them into a
        first pass of up to --cap units and the rest, writes
        <workdir>/plan.json and prints the history calls to make.
calls   Prints the history calls for the later pass, once the user asks for it.
last    Reads the latest-reading call the plan prints when nothing logged all
        week, and says when the site last reported, in site local time.

The rules are the reference's tables, parsed at run time — change a rule there,
not here. Standard library only — no third-party dependencies, by design, so
the script runs wherever the skill is unpacked.
"""
import argparse
import json
import re
import sys
from collections import Counter
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

sys.dont_write_bytecode = True             # leave no __pycache__ beside the skill
sys.path.insert(0, str(Path(__file__).resolve().parent))
from runhours_history import read_page, read_results  # noqa: E402

SIGNALS = Path(__file__).resolve().parent.parent / "run-hours-signals.md"

# ---- Tunables ----------------------------------------------------------------
CAP_UNITS       = 100    # first-pass size; central plant is always fetched whole
POINTS_PER_CALL = 36     # ~672 rows per point-week keeps a call under ~25k rows / ~2 MB
DISCOVERY_LIMIT = 1000   # units per discovery page: ~170 KB for a 100-unit office tower
PROBE_POINTS    = 20     # points asked for the latest reading when nothing logged all week,
                         # a type at a time; the call returns one row, the newest of them all
HISTORY_FIELDS  = ["fav_id", "ts", "data"]
DEFAULT_HOST    = "https://ace.cimenviro.com"
PAGE_ORDER      = ["Central plant", "Field units", "Other"]
DAY_KEYS        = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
DAY_ABBR        = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
NUMBERED        = re.compile(r"([A-Z]*)0*(\d+)([A-Z]*)")    # 'P01A' -> P, 1, A; '10' -> '', 10, ''


# ---- Reference tables ---------------------------------------------------------
def read_tables(path=SIGNALS):
    """Every pipe table in the reference, keyed by the ## heading above it."""
    tables, heading = {}, None
    lines = Path(path).read_text().splitlines()
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if line.startswith("## "):
            heading = line[3:].strip()
        elif line.startswith("|") and heading and heading not in tables:
            header = _cells(line)
            rows, i = [], i + 2                          # skip the --- separator
            while i < len(lines) and lines[i].strip().startswith("|"):
                rows.append(dict(zip(header, _cells(lines[i]))))
                i += 1
            tables[heading] = rows
            continue
        i += 1
    return tables


def _cells(line):
    return [c.strip().strip("`").strip() for c in line.strip().strip("|").split("|")]


def name_tokens(name):
    return [t for t in re.split(r"[^A-Za-z0-9]+", (name or "").upper()) if t]


def natural(text):
    """Sort key that orders 1, 2, 10 rather than 1, 10, 2; blanks last."""
    if not text:
        return [(1, "")]
    return [(0, int(t), "") if t.isdigit() else (0, -1, t.lower())
            for t in re.split(r"(\d+)", text) if t]


def plural(n, word):
    """'1 unit', '2 units'; 'history call' becomes 'history calls'."""
    return f"{n} {word}" + ("" if n == 1 else "s")


UNIT_SUFFIX = re.compile(r"\s*\((?:msv|hz|rpm|%|v|a|kw|fahrenheit|ft/min)\)\s*$|\s+%$", re.I)


def base_name(name):
    """The metadata name without a unit in brackets: 'Supply Air Fan Speed (Hz)' -> 'Supply Air Fan Speed'."""
    prev, n = None, (name or "").strip()
    while prev != n:
        prev, n = n, UNIT_SUFFIX.sub("", n).strip()
    return n


def metadata_role(name):
    """'temp' for a leaving water temperature, 'status' for a status (or a speed state), else 'analog'."""
    b = base_name(name).lower()
    if b.endswith("temperature"):
        return "temp"
    if re.search(r"(status|running)$", b) or "(msv)" in (name or "").lower():
        return "status"
    return "analog"


class Rules:
    """The tables of references/run-hours/run-hours-signals.md: equipment types and the metadata to fetch."""

    NEEDED = ("Central plant", "Field units")

    def __init__(self, path=SIGNALS):
        tables = read_tables(path)
        missing = [h for h in self.NEEDED if h not in tables]
        if missing:
            raise ValueError(f"{Path(path).name}: no table under '## {missing[0]}'")
        self.types, self.lists, order = {}, {}, 0
        for page in ("Central plant", "Field units"):
            for row in tables[page]:
                code = row.get("Short code", "").strip()
                if not code or code in self.types:
                    raise ValueError(f"{Path(path).name}: '{page}' has a missing or repeated short code: {code!r}")
                names = [n.strip() for n in (row.get("Metadata to fetch") or "").split("·") if n.strip()]
                if not names:
                    raise ValueError(f"{Path(path).name}: {code} lists no metadata")
                self.types[code] = {"code": code, "name": row["Equipment type"], "order": order, "page": page}
                self.lists[code] = {base_name(n): i for i, n in enumerate(names)}
                order += 1

    def classify(self, name, *type_codes):
        """(role, rank key, speed state?) when the name is listed for one of these types, else None."""
        b = base_name(name)
        for code in type_codes:
            rank = self.lists.get(code, {}).get(b)
            if rank is not None:
                role = metadata_role(name)
                state = role == "status" and "(msv)" in name.lower() and "speed" in name.lower()
                return role, (rank, len(name)), state
        return None

    def charted_type(self, equipment_name, peak_type):
        """A unit with FCU in its name is a Fan Coil Unit, whatever its type in PEAK."""
        fcu = any(t == "FCU" or re.fullmatch(r"FCU\d+", t) for t in name_tokens(equipment_name))
        return "FCU" if fcu and "FCU" in self.types else peak_type


# ---- window ------------------------------------------------------------------
def load_site(path):
    try:
        rows = read_results(path)
        site = rows[0] if rows else None
    except ValueError:
        site = json.loads(Path(path).read_text())
    if not isinstance(site, dict) or "timezone" not in site:
        sys.exit(f"{path}: expected the search_sites result for one site, with timezone")
    return site


def _slot(hhmm):
    hours, minutes = (int(x) for x in str(hhmm or "0:0").split(":")[:2])
    return max(0, min(96, round((hours * 60 + minutes) / 15)))


def working_slots(hours):
    """Per-day [start, end) slots from the site's working_hours; None for a closed day."""
    days = []
    for key in DAY_KEYS:
        start, end = _slot(hours.get(f"{key}Start")), _slot(hours.get(f"{key}End"))
        if not hours.get(f"{key}Enabled") or start == end == 0:
            days.append(None)
        else:
            days.append([start, end if end > start else 96])   # past midnight: to midnight
    return days


HOURS_GROUP = re.compile(r"(?P<days>[a-z]+(?:\s*-\s*[a-z]+)?)\s+(?P<start>\d{1,2}:\d{2})\s*-\s*(?P<end>\d{1,2}:\d{2})")


def parse_hours(spec):
    """working_hours in the site record's own keys from 'Mon-Fri 08:00-18:00, Sat 09:00-13:00'.

    Groups are separated by commas or semicolons; a day range may wrap
    (Fri-Mon); an end of 00:00 or 24:00 is midnight. A day not named is closed.
    """
    def day(word):
        hit = [i for i, key in enumerate(DAY_KEYS) if len(word) >= 3 and key.startswith(word)]
        if not hit:
            raise ValueError(f"--hours: '{word}' is not a day (Mon, Tue, ... Sun)")
        return hit[0]

    hours = {f"{key}{part}": value for key in DAY_KEYS
             for part, value in (("Enabled", False), ("Start", "00:00"), ("End", "00:00"))}
    for group in (g.strip().lower() for g in re.split(r"[,;]", spec or "") if g.strip()):
        m = HOURS_GROUP.fullmatch(group)
        if not m:
            raise ValueError(f"--hours: cannot read '{group}'; write e.g. \"Mon-Fri 08:00-18:00, Sat 09:00-13:00\"")
        ends = [day(w.strip()) for w in m["days"].split("-")]
        first, last = ends[0], ends[-1]
        for i in range((last - first) % 7 + 1):
            key = DAY_KEYS[(first + i) % 7]
            hours.update({f"{key}Enabled": True, f"{key}Start": m["start"], f"{key}End": m["end"]})
    for key in DAY_KEYS:
        start, end = _slot(hours[f"{key}Start"]), _slot(hours[f"{key}End"])
        if hours[f"{key}Enabled"] and end and end <= start:
            raise ValueError(f"--hours: {key} ends at or before it starts")
    return hours


def week_label(days):
    first, last = days[0], days[-1]
    head = f"Mon {first.day}"
    if first.month != last.month or first.year != last.year:
        head += f" {first:%b}" + (f" {first.year}" if first.year != last.year else "")
    return f"{head} to Sun {last.day} {last:%b} {last.year}"


TZ_ALIAS = {   # legacy time-zone names PEAK sites carry, read as the zone they link to
    "Australia/ACT": "Australia/Sydney", "Australia/Canberra": "Australia/Sydney",
    "Australia/NSW": "Australia/Sydney", "Australia/North": "Australia/Darwin",
    "Australia/Queensland": "Australia/Brisbane", "Australia/South": "Australia/Adelaide",
    "Australia/Tasmania": "Australia/Hobart", "Australia/Victoria": "Australia/Melbourne",
    "Australia/West": "Australia/Perth", "Australia/Yancowinna": "Australia/Broken_Hill",
    "Australia/LHI": "Australia/Lord_Howe",
    "US/Eastern": "America/New_York", "US/Central": "America/Chicago", "US/Mountain": "America/Denver",
    "US/Pacific": "America/Los_Angeles", "US/Arizona": "America/Phoenix", "US/Alaska": "America/Anchorage",
    "US/Hawaii": "Pacific/Honolulu", "US/East-Indiana": "America/Indiana/Indianapolis",
    "US/Michigan": "America/Detroit",
    "Canada/Eastern": "America/Toronto", "Canada/Central": "America/Winnipeg",
    "Canada/Mountain": "America/Edmonton", "Canada/Pacific": "America/Vancouver",
    "Canada/Atlantic": "America/Halifax", "Canada/Newfoundland": "America/St_Johns",
    "GB": "Europe/London", "GB-Eire": "Europe/London", "Eire": "Europe/Dublin", "NZ": "Pacific/Auckland",
    "Singapore": "Asia/Singapore", "Hongkong": "Asia/Hong_Kong", "PRC": "Asia/Shanghai", "Japan": "Asia/Tokyo",
    "Brazil/East": "America/Sao_Paulo",
}


def cmd_window(args):
    from zoneinfo import ZoneInfo           # stdlib from 3.9; needs the system tz database
    site = load_site(args.site)
    tz = ZoneInfo(TZ_ALIAS.get(site["timezone"], site["timezone"]))
    work = Path(args.workdir)
    work.mkdir(parents=True, exist_ok=True)

    today = date.fromisoformat(args.today) if args.today else datetime.now(tz).date()
    if args.week_of:
        ref = date.fromisoformat(args.week_of)
        monday = ref - timedelta(days=ref.weekday())
        if monday + timedelta(days=7) > today:
            sys.exit(f"the week of {args.week_of} has not finished in site local time")
    else:
        monday = today - timedelta(days=today.weekday() + 7)
    dates = [monday + timedelta(days=i) for i in range(7)]

    def utc(d):
        return datetime.combine(d, time(0), tzinfo=tz).astimezone(timezone.utc)

    start, end = utc(monday), utc(monday + timedelta(days=7))
    hours_source = site.get("hours_source", "site")
    if args.hours:
        site["working_hours"], hours_source = parse_hours(args.hours), "user"
    slots = working_slots(site.get("working_hours") or {})
    if not any(slots):
        sys.exit("working hours are empty (every day closed or 00:00). Ask the user what hours to "
                 'assess against and run window again with them, e.g. --hours "Mon-Fri 08:00-18:00, '
                 'Sat 09:00-13:00"; a day not named is closed.')

    names = sorted({datetime.combine(d, time(12), tzinfo=tz).tzname() for d in dates})
    link = re.match(r"https?://[^/]+", site.get("site_link") or "")
    window = {
        "site_id": site["site_id"], "site_name": site["site_name"],
        "timezone": TZ_ALIAS.get(site["timezone"], site["timezone"]), "tz_label": "/".join(names),
        "hours_source": hours_source,
        "start": start.strftime("%Y-%m-%dT%H:%M:%SZ"), "end": end.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "link_start": start.strftime("%Y-%m-%dT%H:%M:%S.000"),
        "link_end": end.strftime("%Y-%m-%dT%H:%M:%S.000"),
        "link_host": link.group(0) if link else DEFAULT_HOST,
        "label": week_label(dates),
        "days": [{"date": d.isoformat(), "label": f"{DAY_ABBR[i]} {d.day}", "wh": slots[i]}
                 for i, d in enumerate(dates)],
    }
    (work / "window.json").write_text(json.dumps(window, indent=1))

    rules = Rules()
    charted = list(rules.types)

    # One row per unit of an in-scope type, its points nested: the unit's name, type
    # and level travel once rather than on every point.
    discovery = {
        "query_name": "platform.equipment",
        "args": {"site_id": site["site_id"], "is_active": True, "metadata_type_codes": charted,
                 "limit": DISCOVERY_LIMIT, "start_index": 0},
        "fields": ["equipment_id", "name", "metadata_type.type_code", "zone.level.level_name",
                   "zone.zone_name.zone_name",
                   {"path": "favourites", "sub_fields": [
                       "fav_id", "is_active", "metadata.name",
                       {"path": "history_available",
                        "args": {"start": window["start"], "end": window["end"], "end_exclusive": True}}]}],
    }
    print(f"{site['site_name']}: {window['label']} ({window['tz_label']}), "
          f"{window['start']} to {window['end']} UTC. Wrote {work / 'window.json'}.")
    print("One call, exactly as printed. Save the response in "
          f"{work} under the names given.")
    print(f"Discovery -> discovery-0.json. Where its pagination.total is over {DISCOVERY_LIMIT}, "
          f"make the same call again for each further page, in parallel, with start_index "
          f"{DISCOVERY_LIMIT}, {2 * DISCOVERY_LIMIT}, ... -> discovery-{DISCOVERY_LIMIT}.json, "
          f"discovery-{2 * DISCOVERY_LIMIT}.json, ...:")
    print(json.dumps(discovery))



# ---- plan --------------------------------------------------------------------
def _number(tok):
    """(word, unit number) of a name token: 'P01A' -> ('P', '1A'), '10' -> ('', '10'), 'CHWP' -> ('CHWP', None)."""
    m = NUMBERED.fullmatch(tok)
    return (m.group(1), m.group(2) + m.group(3)) if m else (tok, None)


def pair_members(unit):
    """(name words, member numbers) for a COMMON record that names the units it pairs, else None.

    'Common - PCHWP - 3/4', 'SHWP P-10A/B - COMMON', 'AHU-CHWP-10-11-COMMON' and
    'PUMP-10&11-COMMON' all do. Only bare numbers count: 'VRV-L11-COMMON' is a
    level's group and 'EWH-COMMON' names no units, so neither is a pair.
    """
    tokens = name_tokens(unit["name"])
    if "COMMON" not in tokens:
        return None
    words, numbers, last = set(), set(), None
    for tok in (t for t in tokens if t != "COMMON"):
        word, number = _number(tok)
        if number is not None and not word:
            numbers.add(number)
            last = number
        elif len(tok) == 1 and last and last[-1].isalpha():
            numbers.add(last[:-1] + tok)                       # '10A/B': B is 10B
        else:
            words.add(word)
    return (words, numbers) if numbers else None


def member_of(unit, words, numbers):
    """Whether a unit is one of the pair: every word of the pair's name, and a number it lists."""
    own, number = set(), None
    for tok in name_tokens(unit["name"]):
        word, num = _number(tok)
        if word:
            own.add(word)
        if num is not None:
            number = num
    return number in numbers and words <= own


def signal_grade(unit):
    """1 for a unit drawn from a status or analog, else 0."""
    return 1 if {p["role"] for p in unit["pull"]} & {"status", "analog"} else 0


def read_units(paths):
    """Discovered units with their points, de-duplicated across pages.

    Reads the equipment-rooted discovery (points nested under each unit) and, for
    older saved runs, the point-per-row pages of platform.favourites.
    """
    units, seen = {}, set()

    def unit_for(eid, eq):
        return units.setdefault(eid, {
            "equipment_id": eid, "name": eq.get("name") or str(eid),
            "peak_type": (eq.get("metadata_type") or {}).get("type_code"),
            "level": ((eq.get("zone") or {}).get("level") or {}).get("level_name"),
            "zone": ((eq.get("zone") or {}).get("zone_name") or {}).get("zone_name"),
            "points": []})

    for path in paths:
        for row in read_results(path):
            if "favourites" in row:
                unit = unit_for(row["equipment_id"], row)
                points = row.get("favourites") or []
            else:
                unit, points = unit_for(row["equipment_id"], row.get("equipment") or {}), [row]
            for p in points:
                if p.get("is_active") is False or p.get("fav_id") in seen:
                    continue
                seen.add(p.get("fav_id"))
                unit["points"].append(p)
    return list(units.values())


SENSOR_ROLES = ("status", "analog")   # readings; a temperature is never used on its own
COMMAND_END = re.compile(r"(enable|command|occupancy)$", re.I)


def pick_points(unit, rules):
    """Every metadata listed for the unit's equipment type that the unit has, with history this week."""
    found = []
    for p in unit["points"]:
        name = (p.get("metadata") or {}).get("name") or ""
        hit = rules.classify(name, unit["peak_type"], unit["type"])
        if hit:
            role, key, state = hit
            found.append({"fav_id": p["fav_id"], "name": name, "role": role, "key": key, "state": state,
                          "live": bool(p.get("history_available"))})
    found.sort(key=lambda c: (c["key"], c["fav_id"]))
    pull, seen = [], set()
    for c in found:
        if c["live"] and base_name(c["name"]) not in seen:
            seen.add(base_name(c["name"]))
            pull.append(c)
    unit["temps"] = [{"fav_id": c["fav_id"], "name": c["name"], "role": "temp"} for c in pull if c["role"] == "temp"]
    if not any(c["role"] in SENSOR_ROLES for c in pull):
        pull = []                                  # a temperature is never the only metadata used
    unit["pull"] = [dict({k: c[k] for k in ("fav_id", "name", "role")}, **({"state": True} if c["state"] else {}))
                    for c in pull]
    if pull:
        return
    names = [(p.get("metadata") or {}).get("name") or "" for p in unit["points"]]
    readings = [c for c in found if c["role"] in SENSOR_ROLES]
    if readings:
        unit["why"] = "no history this week"
        best = readings[0]
        unit["probe"] = {"fav_id": best["fav_id"], "unit": unit["name"], "point": best["name"]}
    elif not unit["points"]:
        unit["why"] = "no points"
    elif "COMMON" in name_tokens(unit["name"]):
        unit["why"] = "shared record"
    elif unit["temps"]:
        unit["why"] = "temperature only"
    elif any(COMMAND_END.search(base_name(n)) for n in names):
        unit["why"] = "command only"
    else:
        unit["why"] = "no listed metadata"


def borrow_shared_temperature(units):
    """A heating unit with no leaving water temperature of its own takes its type's Common record's."""
    for ty in {u["type"] for u in units}:
        commons = [u for u in units if u["type"] == ty and u.get("temps") and "COMMON" in name_tokens(u["name"])]
        if len(commons) != 1:
            continue
        src, t = commons[0], commons[0]["temps"][0]
        for u in units:
            if u is not src and u["type"] == ty and u["pull"] and not any(p["role"] == "temp" for p in u["pull"]):
                u["pull"].append({"fav_id": t["fav_id"], "name": t["name"], "role": "temp",
                                  "equipment_id": src["equipment_id"], "shared": src["name"]})


def drop_covered_pairs(units):
    """Drop a COMMON pair record where a member is drawn from a signal at least as good.

    Kept where the pair is the only record of the pumps running: a pair status
    beside members that carry only enables, which are not drawn.
    """
    for unit in units:
        pair = pair_members(unit)
        if pair and unit["pull"] and any(
                other is not unit and other["type"] == unit["type"] and other["pull"]
                and not pair_members(other) and member_of(other, *pair)
                and signal_grade(other) >= signal_grade(unit)
                for other in units):
            unit["why"], unit["pull"] = "pair point, members charted", []


def assign_passes(units, cap):
    """Central plant in the first pass whole; each field type whole where it still fits under cap.

    A type too big to fit waits for the later pass without holding back the
    smaller types after it; while the first pass is still empty, the next type
    goes in whatever its size, so there is always a first view.
    """
    count = sum(1 for u in units if u["pull"] and u["page"] == "Central plant")
    for u in units:
        u["pass"] = 1
    for type_code in dict.fromkeys(u["type"] for u in units if u["page"] != "Central plant"):
        group = [u for u in units if u["type"] == type_code]
        size = sum(1 for u in group if u["pull"])
        fits = cap is None or count == 0 or count + size <= cap
        for u in group:
            u["pass"] = 1 if fits else 2
        count += size if fits else 0


def cmd_plan(args):
    work = Path(args.workdir)
    window = json.loads((work / "window.json").read_text())
    rules = Rules()

    units = []
    for unit in read_units(args.discovery):
        peak = unit["peak_type"]
        if peak not in rules.types:
            continue                       # a type not in the tables is not charted
        unit["type"] = rules.charted_type(unit["name"], peak)
        ty = rules.types[unit["type"]]
        unit["type_name"], unit["page"] = ty["name"], ty["page"]
        if unit["type"] != peak:
            unit["regrouped_from"] = rules.types[peak]["name"]
        pick_points(unit, rules)
        units.append(unit)
    drop_covered_pairs(units)
    borrow_shared_temperature(units)

    def order(u):
        ty = rules.types.get(u["type"])
        return (PAGE_ORDER.index(u["page"]), ty["order"] if ty else 999, u["type_name"],
                natural(u["level"]), natural(u["name"]))

    units.sort(key=order)
    assign_passes(units, args.cap if args.cap and args.cap > 0 else None)
    chunks = []
    for pass_no in (1, 2):
        favs = list(dict.fromkeys(p["fav_id"] for u in units if u["pass"] == pass_no for p in u["pull"]))
        chunks += [{"pass": pass_no, "fav_ids": favs[i:i + POINTS_PER_CALL]}
                   for i in range(0, len(favs), POINTS_PER_CALL)]

    dead = [u for u in units if u.get("why") == "no history this week"]
    plan = {
        "units": [{k: u.get(k) for k in ("equipment_id", "name", "type", "type_name", "page",
                                          "level", "zone", "regrouped_from",
                                          "pass", "pull", "why")}
                  for u in units],
        "chunks": chunks,
        "outage": bool(dead) and not any(u["pull"] for u in units),
        "probe": probe_points(dead) if dead and not chunks else [],
    }
    (work / "plan.json").write_text(json.dumps(plan, indent=1))
    print(f"{window['site_name']}: {window['label']}. Wrote {work / 'plan.json'}.")
    print_summary(plan)
    if not chunks:
        print_nothing_to_draw(window, plan, dead, work)
        return
    print_calls(window, plan, 1, work)


def probe_points(dead):
    """Up to PROBE_POINTS of the units' best points, taken a type at a time so every type is asked."""
    by_type = {}
    for u in dead:
        by_type.setdefault(u["type"], []).append(u["probe"])
    out, queues = [], list(by_type.values())
    while queues and len(out) < PROBE_POINTS:
        out += [q.pop(0) for q in queues][:PROBE_POINTS - len(out)]
        queues = [q for q in queues if q]
    return out


WHY_TEXT = {"temperature only": "only a temperature, which is never used on its own",
            "no listed metadata": "none of the metadata listed for its type",
            "no history this week": "a run point, but no history this week",
            "command only": "only an enable, command or schedule, no sensor",
            "shared record": "a COMMON record with no sensor of its own",
            "no points": "no points in PEAK",
            "pair point, members charted": "a COMMON pair record whose members are drawn"}


def print_summary(plan):
    for pass_no, label in ((1, "First pass"), (2, "Later pass")):
        drawn = [u for u in plan["units"] if u["pull"] and u["pass"] == pass_no]
        if not drawn:
            continue
        types = Counter(u["type_name"] for u in drawn)
        calls = sum(1 for c in plan["chunks"] if c["pass"] == pass_no)
        points = sum(len(u["pull"]) for u in drawn)
        detail = (": " + ", ".join(f"{t} {n}" for t, n in types.items())) if pass_no == 2 else ""
        print(f"{label}: {plural(len(drawn), 'unit')} in {plural(len(types), 'type')}, "
              f"{plural(points, 'point')}, {plural(calls, 'history call')}{detail}.")
    for why, n in Counter(u["why"] for u in plan["units"] if not u["pull"]).items():
        print(f"Not drawn: {plural(n, 'unit')}, {WHY_TEXT.get(why, why)}.")
    regrouped = Counter(f"{u['regrouped_from']} as {u['type_name']}"
                        for u in plan["units"] if u["regrouped_from"] and u["pull"])
    if regrouped:
        print("Regrouped by name: " + ", ".join(f"{k} {n}" for k, n in regrouped.items()) + ".")


def history_call(args):
    return {"query_name": "platform.history", "args": args, "fields": HISTORY_FIELDS}


def print_nothing_to_draw(window, plan, dead, work):
    if plan["outage"]:
        print(f"Nothing to draw: none of the {plural(len(dead), 'unit')} with listed metadata logged any "
              f"history from {window['start']} to {window['end']}, so the site's data feed looks down. "
              "Say so rather than showing an empty view. To say since when, make this call exactly as "
              f"printed: it returns one row, the newest reading of any of these "
              f"{plural(len(plan['probe']), 'point')}. Save it as {work / 'last-reading.json'}, then run "
              f"runhours_plan.py last {work} {work / 'last-reading.json'}")
        print(json.dumps(history_call({"fav_ids": [p["fav_id"] for p in plan["probe"]], "latest": True})))
    else:
        print("Nothing to draw: no unit at the site has the metadata listed for its equipment type in "
              "run-hours-signals.md. Say so with the summary above rather than showing an empty view.")


def print_calls(window, plan, pass_no, work):
    chunks = [c for c in plan["chunks"] if c["pass"] == pass_no]
    label = "first pass" if pass_no == 1 else "later pass"
    if not chunks:
        print(f"No history calls for the {label}: every unit with listed metadata is in the other pass.")
        return
    names = f"history-{pass_no}-1.json" + (f" to history-{pass_no}-{len(chunks)}.json" if len(chunks) > 1 else "")
    print(f"History calls, {label}: {len(chunks)}. Make each exactly as printed, in parallel, and save "
          f"the responses in {work} as {names}, in the order printed:")
    for chunk in chunks:
        print(json.dumps(history_call({"fav_ids": chunk["fav_ids"], "start": window["start"],
                                       "end": window["end"], "end_exclusive": True})))


def cmd_calls(args):
    work = Path(args.workdir)
    window = json.loads((work / "window.json").read_text())
    print_calls(window, json.loads((work / "plan.json").read_text()), args.pass_no, work)


def cmd_last(args):
    """When the site last reported: the newest reading of the points the plan probed."""
    from zoneinfo import ZoneInfo           # stdlib from 3.9; needs the system tz database
    work = Path(args.workdir)
    window = json.loads((work / "window.json").read_text())
    probe = {str(p["fav_id"]): p for p in json.loads((work / "plan.json").read_text()).get("probe") or []}
    if not probe:
        raise ValueError("plan.json has no probe: the last step follows a plan with nothing to draw")
    rows = [r for r in read_results(args.response) if str(r.get("fav_id")) in probe and r.get("ts")]
    if not rows:
        print(f"None of the {plural(len(probe), 'point')} asked has a reading in PEAK's history at all: "
              "the site's points have never reported, or their history is not reaching PEAK. Say so.")
        return
    newest = max(rows, key=lambda r: datetime.fromisoformat(str(r["ts"]).replace("Z", "+00:00")))
    local = datetime.fromisoformat(str(newest["ts"]).replace("Z", "+00:00")).astimezone(
        ZoneInfo(window["timezone"]))
    p = probe[str(newest["fav_id"])]
    print(f"The site's run points last reported {local:%a} {local.day} {local:%b %Y %H:%M} {local.tzname()}, "
          f"the newest reading of the {plural(len(probe), 'point')} sampled across its types "
          f"({p['unit']}, {p['point']}). Say its data feed has been down since then, and that there is "
          f"no run-hours view for {window['label']}.")


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    w = sub.add_parser("window", help="fix the week and print the discovery calls")
    w.add_argument("site", help="saved search_sites result for the site")
    w.add_argument("workdir")
    w.add_argument("--week-of", help="any date in the Monday-to-Sunday week to show")
    w.add_argument("--hours", help='the user\'s working hours, e.g. "Mon-Fri 08:00-18:00, Sat 09:00-13:00"; '
                                   "a day not named is closed")
    w.add_argument("--today", help=argparse.SUPPRESS)
    p = sub.add_parser("plan", help="pick points and passes from the discovery pages")
    p.add_argument("workdir")
    p.add_argument("discovery", nargs="+", help="saved discovery pages")
    p.add_argument("--cap", type=int, default=CAP_UNITS,
                   help=f"first-pass units (default {CAP_UNITS}; 0 fetches everything)")
    c = sub.add_parser("calls", help="print the history calls for one pass of an existing plan")
    c.add_argument("workdir")
    c.add_argument("--pass", dest="pass_no", type=int, default=2)
    last = sub.add_parser("last", help="say when the site last reported, from the saved latest-reading call")
    last.add_argument("workdir")
    last.add_argument("response", help="saved response of the latest-reading call")
    args = parser.parse_args(argv[1:])
    try:
        {"window": cmd_window, "plan": cmd_plan, "calls": cmd_calls, "last": cmd_last}[args.command](args)
    except (ValueError, KeyError) as exc:
        sys.exit(f"runhours_plan: {exc}")


if __name__ == "__main__":
    main(sys.argv)
