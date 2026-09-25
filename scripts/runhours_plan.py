#!/usr/bin/env python3
"""Plan a run-hours pull: which week, which points, and in what order.

Usage:
    python3 runhours_plan.py window <site.json> <workdir> [--week-of YYYY-MM-DD] [--include LT,...]
    python3 runhours_plan.py plan <workdir> <discovery.json> [more.json ...] [--census census.json] [--cap N]
    python3 runhours_plan.py calls <workdir> [--pass 2]

window  Reads the saved search_sites result (timezone and working hours), fixes
        the last full Monday-to-Sunday week in site local time, writes
        <workdir>/window.json and prints the discovery and census calls to make.
plan    Sorts every discovered point with the rules in
        references/run-hours-signals.md, picks each unit's candidate points,
        orders the units for the view, splits them into a first pass of about
        --cap units and the rest, writes <workdir>/plan.json and prints the
        history calls to make.
calls   Prints the history calls for the later pass, once the user asks for it.

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

sys.path.insert(0, str(Path(__file__).resolve().parent))
from runhours_history import read_results  # noqa: E402

SIGNALS = Path(__file__).resolve().parent.parent / "references" / "run-hours-signals.md"

# ---- Tunables ----------------------------------------------------------------
CAP_UNITS       = 100    # first-pass size; central plant is always fetched whole
POINTS_PER_CALL = 36     # ~672 rows per point-week keeps a call under ~25k rows / ~2 MB
DISCOVERY_LIMIT = 2000   # favourites per discovery page, ~550 KB
CENSUS_LIMIT    = 5000   # equipment per census page, ~50 bytes each
DEFAULT_HOST    = "https://ace.cimenviro.com"
PAGE_ORDER      = ["Central plant", "Field units", "Other"]
ROLE_ORDER      = ["status", "analog", "command", "compressor"]
TRAILING_UNITS  = {"%", "percent", "w", "kw", "v", "a", "msv"}
DAY_KEYS        = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
DAY_ABBR        = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


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


def _split(cell):
    return [p.strip() for p in (cell or "").split(",") if p.strip()]


def _phrase(text):
    """Whole-word, case-insensitive matcher for one phrase."""
    return re.compile(r"(?<![a-z0-9])" + re.escape(text.lower()) + r"(?![a-z0-9])")


def normalise(name):
    """Lower-case name without brackets or a trailing unit, and whether it is (MSV)."""
    low = name.lower()
    msv = "(msv)" in low
    tokens = re.sub(r"\([^)]*\)", " ", low).split()
    while tokens and tokens[-1] in TRAILING_UNITS:
        tokens.pop()
    return " ".join(tokens), msv


def name_tokens(name):
    return [t for t in re.split(r"[^A-Za-z0-9]+", (name or "").upper()) if t]


def natural(text):
    """Sort key that orders 1, 2, 10 rather than 1, 10, 2; blanks last."""
    if not text:
        return [(1, "")]
    return [(0, int(t), "") if t.isdigit() else (0, -1, t.lower())
            for t in re.split(r"(\d+)", text) if t]


class Rules:
    """The tables of references/run-hours-signals.md, ready to classify with."""

    NEEDED = ("Equipment types", "Never charted", "Roles", "Never a run signal", "Which point wins")

    def __init__(self, path=SIGNALS):
        tables = read_tables(path)
        missing = [h for h in self.NEEDED if h not in tables]
        if missing:
            raise ValueError(f"{Path(path).name}: no table under '## {missing[0]}'")
        self.types = {}
        for order, row in enumerate(tables["Equipment types"]):
            self.types[row["Code"]] = {
                "code": row["Code"], "name": row["Equipment type"], "order": order,
                "page": row["Page"], "system": row["System"],
                "prefixes": [p.upper() for p in _split(row["Name starts with"])],
                "compressor_is_unit": row["Compressor is the unit"].lower() == "yes",
                "also_never": [_phrase(p) for p in _split(row["Also never"])],
            }
        self.never_charted = {c for row in tables["Never charted"] for c in _split(row["Codes"])}
        self.endings = {row["Role"]: [e.lower() for e in _split(row["Name ends with, best first"])]
                        for row in tables["Roles"]}
        self.never = [_phrase(p) for row in tables["Never a run signal"]
                      for p in _split(row["Name contains"])]
        self.components = [(len(p), int(row["Rank"]), _phrase(p))
                           for row in tables["Which point wins"]
                           for p in _split(row["Component named"]) if not p.startswith("(")]
        self.by_prefix = {p: code for code, ty in self.types.items() for p in ty["prefixes"]}
        self.compressor = _phrase("compressor")

    def classify(self, name, type_code):
        """(role, rank key) for a point name on this type, or None if it is no run signal."""
        n, msv = normalise(name)
        ty = self.types.get(type_code, {})
        if any(p.search(n) for p in self.never + ty.get("also_never", [])):
            return None
        match = None
        for role, ends in self.endings.items():
            for pos, end in enumerate(ends):
                if (n == end or n.endswith(" " + end)) and (match is None or len(end) > len(match[2])):
                    match = (role, pos, end)
        if not match:
            return None
        role, pos, end = match
        rank = self.component_rank(n)
        if end in ("load", "output") and rank != 2:
            return None                  # a coil's or a system's load, not the unit's
        if msv and role == "analog":
            role, pos = "status", 0      # an (MSV) speed is a state: off, low, high
        if self.compressor.search(n) and not ty.get("compressor_is_unit"):
            if role != "status":
                return None
            role = "compressor"
        weaker = end in ("occupancy", "load", "output")   # a schedule, or an indirect measure
        return role, (int(weaker), rank, pos, int(msv), len(n))

    def component_rank(self, n):
        """Rank of the most specific component phrase in the name; 2 when none."""
        hits = [(length, rank) for length, rank, rx in self.components if rx.search(n)]
        if not hits:
            return 2
        longest = max(length for length, _ in hits)
        return max(rank for length, rank in hits if length == longest)

    def charted_type(self, equipment_name, peak_type):
        """The in-scope type a unit is drawn under: its name's, when that says another.

        A 'Common - SHWP - 2' pair point is named by its second word, so it lands
        in the same group as the pumps it pairs.
        """
        tokens = name_tokens(equipment_name)
        word = tokens[1] if len(tokens) > 1 and tokens[0] == "COMMON" else (tokens or [""])[0]
        named = self.by_prefix.get(word)
        return named if named and named != peak_type else peak_type


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


def week_label(days):
    first, last = days[0], days[-1]
    head = f"Mon {first.day}"
    if first.month != last.month or first.year != last.year:
        head += f" {first:%b}" + (f" {first.year}" if first.year != last.year else "")
    return f"{head} to Sun {last.day} {last:%b} {last.year}"


def cmd_window(args):
    from zoneinfo import ZoneInfo           # stdlib from 3.9; needs the system tz database
    site = load_site(args.site)
    tz = ZoneInfo(site["timezone"])
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
    slots = working_slots(site.get("working_hours") or {})
    if not any(slots):
        sys.exit("working hours are empty (every day closed or 00:00). Ask the user what hours "
                 "to assess against, write them into site.json's working_hours in the same keys, "
                 'add "hours_source": "user", and run window again.')

    names = sorted({datetime.combine(d, time(12), tzinfo=tz).tzname() for d in dates})
    link = re.match(r"https?://[^/]+", site.get("site_link") or "")
    include = [c.strip() for c in (args.include or "").split(",") if c.strip()]
    window = {
        "site_id": site["site_id"], "site_name": site["site_name"],
        "timezone": site["timezone"], "tz_label": "/".join(names),
        "hours_source": site.get("hours_source", "site"),
        "start": start.strftime("%Y-%m-%dT%H:%M:%SZ"), "end": end.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "link_start": start.strftime("%Y-%m-%dT%H:%M:%S.000"),
        "link_end": end.strftime("%Y-%m-%dT%H:%M:%S.000"),
        "link_host": link.group(0) if link else DEFAULT_HOST,
        "label": week_label(dates),
        "days": [{"date": d.isoformat(), "label": f"{DAY_ABBR[i]} {d.day}", "wh": slots[i]}
                 for i, d in enumerate(dates)],
        "include": include,
    }
    (work / "window.json").write_text(json.dumps(window, indent=1))

    rules = Rules()
    codes = list(rules.types) + ["VSD"] + [c for c in include if c not in rules.types]
    discovery = {
        "query_name": "platform.favourites",
        "args": {"site_id": site["site_id"], "is_active": True, "metadata_type_codes": codes,
                 "limit": DISCOVERY_LIMIT, "start_index": 0},
        "fields": ["fav_id", "metadata_id", "metadata.name", "equipment_id", "equipment.name",
                   "equipment.metadata_type.type_code", "equipment.zone.level.level_name",
                   {"path": "history_available",
                    "args": {"start": window["start"], "end": window["end"], "end_exclusive": True}}],
    }
    census = {
        "query_name": "platform.equipment",
        "args": {"site_id": site["site_id"], "is_active": True, "limit": CENSUS_LIMIT},
        "fields": ["metadata_type.type_code", "metadata_type.type"],
    }
    print(f"{site['site_name']}: {window['label']} ({window['tz_label']}), "
          f"{window['start']} to {window['end']} UTC. Wrote {work / 'window.json'}.")
    print("Discovery (page with start_index while pagination.has_more):")
    print(json.dumps(discovery))
    print("Census (same, in parallel):")
    print(json.dumps(census))


# ---- plan --------------------------------------------------------------------
def common_pair_members(unit):
    """(type token, member numbers) for a 'Common - PCHWP - 3/4' pair point, else None."""
    tokens = name_tokens(unit["name"])
    if len(tokens) < 3 or tokens[0] != "COMMON":
        return None
    return tokens[1], {t for t in tokens[2:] if t.isdigit()}


def names_member(unit, type_token, numbers):
    tokens = name_tokens(unit["name"])
    return any(a == type_token and b in numbers for a, b in zip(tokens, tokens[1:]))


def signal_grade(unit):
    """2 for a status or analog, 1 for a command, 0 for a compressor status alone."""
    roles = {p["role"] for p in unit["pull"]}
    return 2 if roles & {"status", "analog"} else 1 if "command" in roles else 0


def read_units(paths):
    """Discovered points grouped by equipment, de-duplicated across pages."""
    units, seen = {}, set()
    for path in paths:
        for p in read_results(path):
            if p.get("fav_id") in seen:
                continue
            seen.add(p.get("fav_id"))
            eq = p.get("equipment") or {}
            unit = units.setdefault(p["equipment_id"], {
                "equipment_id": p["equipment_id"],
                "name": eq.get("name") or str(p["equipment_id"]),
                "peak_type": (eq.get("metadata_type") or {}).get("type_code"),
                "level": ((eq.get("zone") or {}).get("level") or {}).get("level_name"),
                "points": []})
            unit["points"].append(p)
    return list(units.values())


def read_census(paths):
    """Units per equipment type at the site, and each type's PEAK name."""
    counts, names = Counter(), {}
    for path in paths or []:
        for row in read_results(path):
            mt = row.get("metadata_type") or {}
            counts[mt.get("type_code")] += 1
            names[mt.get("type_code")] = mt.get("type")
    return counts, names


def pick_points(unit, rules):
    """The points to pull for one unit: its status and analog, else a command, else a compressor."""
    found = {role: [] for role in ROLE_ORDER}
    for p in unit["points"]:
        name = (p.get("metadata") or {}).get("name") or ""
        hit = rules.classify(name, unit["type"])
        if hit:
            found[hit[0]].append({"fav_id": p["fav_id"], "metadata_id": p.get("metadata_id") or 0,
                                  "name": name, "role": hit[0], "key": hit[1],
                                  "live": bool(p.get("history_available"))})
    best = {}
    for role, cands in found.items():
        cands.sort(key=lambda c: (c["key"], c["metadata_id"]))
        best[role] = next((c for c in cands if c["live"]), None)
    pull = [best[r] for r in ("status", "analog") if best[r]]
    if not pull:
        pull = next(([best[r]] for r in ("command", "compressor") if best[r]), [])
    unit["pull"] = [{k: c[k] for k in ("fav_id", "name", "role")} for c in pull]
    if not pull:
        unit["why"] = "no history this week" if any(found.values()) else "no usable run point"


def drop_covered_pairs(units):
    """Drop a 'Common' pair point where a member is drawn from a signal at least as good.

    Kept where the pair is the only genuine record: a pair status beside members
    that carry only enables.
    """
    for unit in units:
        pair = common_pair_members(unit)
        if pair and unit["pull"] and any(
                other is not unit and other["type"] == unit["type"] and other["pull"]
                and names_member(other, *pair) and signal_grade(other) >= signal_grade(unit)
                for other in units):
            unit["why"], unit["pull"] = "pair point, members charted", []


def assign_passes(units, cap):
    """Central plant in the first pass whole; field types follow whole while they fit under cap."""
    count = sum(1 for u in units if u["pull"] and u["page"] == "Central plant")
    cut = False
    for u in units:
        u["pass"] = 1
    for type_code in dict.fromkeys(u["type"] for u in units if u["page"] != "Central plant"):
        group = [u for u in units if u["type"] == type_code]
        size = sum(1 for u in group if u["pull"])
        cut = cut or (cap is not None and count + size > cap)
        for u in group:
            u["pass"] = 2 if cut else 1
        count += 0 if cut else size


def cmd_plan(args):
    work = Path(args.workdir)
    window = json.loads((work / "window.json").read_text())
    rules = Rules()
    include = set(window.get("include") or [])
    census, census_names = read_census(args.census)

    units, unknown = [], Counter()
    for unit in read_units(args.discovery):
        peak = unit["peak_type"]
        if peak not in rules.types and peak not in include:
            unknown[peak] += 1
            continue
        unit["type"] = rules.charted_type(unit["name"], peak) if peak in rules.types else peak
        ty = rules.types.get(unit["type"])
        unit["type_name"] = ty["name"] if ty else census_names.get(peak, peak)
        unit["page"] = ty["page"] if ty else "Other"
        if unit["type"] != peak:
            unit["regrouped_from"] = rules.types[peak]["name"]
        pick_points(unit, rules)
        units.append(unit)
    drop_covered_pairs(units)

    def order(u):
        ty = rules.types.get(u["type"])
        return (PAGE_ORDER.index(u["page"]), ty["order"] if ty else 999, u["type_name"],
                natural(u["level"]), natural(u["name"]))

    units.sort(key=order)
    assign_passes(units, args.cap if args.cap and args.cap > 0 else None)
    chunks = []
    for pass_no in (1, 2):
        favs = [p["fav_id"] for u in units if u["pass"] == pass_no for p in u["pull"]]
        chunks += [{"pass": pass_no, "fav_ids": favs[i:i + POINTS_PER_CALL]}
                   for i in range(0, len(favs), POINTS_PER_CALL)]

    # Types in neither table: named in the notes, so a new PEAK type is a visible gap.
    known = set(rules.types) | rules.never_charted | include | {None}
    unclassified = Counter({c: n for c, n in (census or unknown).items() if c not in known})
    plan = {
        "units": [{k: u.get(k) for k in ("equipment_id", "name", "type", "type_name", "page",
                                          "level", "regrouped_from", "pass", "pull", "why")}
                  for u in units],
        "chunks": chunks,
        "unclassified": [{"code": c, "type": census_names.get(c, c), "units": n}
                         for c, n in unclassified.most_common()],
    }
    (work / "plan.json").write_text(json.dumps(plan, indent=1))
    print(f"{window['site_name']}: {window['label']}. Wrote {work / 'plan.json'}.")
    print_summary(plan)
    print_calls(window, plan, 1)


def print_summary(plan):
    for pass_no, label in ((1, "First pass"), (2, "Later pass")):
        drawn = [u for u in plan["units"] if u["pull"] and u["pass"] == pass_no]
        if not drawn and pass_no == 2:
            continue
        types = Counter(u["type_name"] for u in drawn)
        calls = sum(1 for c in plan["chunks"] if c["pass"] == pass_no)
        points = sum(len(u["pull"]) for u in drawn)
        detail = (": " + ", ".join(f"{t} {n}" for t, n in types.items())) if pass_no == 2 else ""
        print(f"{label}: {len(drawn)} units in {len(types)} types, {points} points, "
              f"{calls} history calls{detail}.")
    for why, n in Counter(u["why"] for u in plan["units"] if not u["pull"]).items():
        print(f"Not drawn: {n} units, {why}.")
    regrouped = Counter(f"{u['regrouped_from']} as {u['type_name']}"
                        for u in plan["units"] if u["regrouped_from"])
    if regrouped:
        print("Regrouped by name: " + ", ".join(f"{k} {n}" for k, n in regrouped.items()) + ".")
    if plan["unclassified"]:
        print("Unclassified types at this site: "
              + ", ".join(f"{u['type']} ({u['code']}) {u['units']}" for u in plan["unclassified"]))


def print_calls(window, plan, pass_no):
    chunks = [c for c in plan["chunks"] if c["pass"] == pass_no]
    label = "first pass" if pass_no == 1 else "later pass"
    print(f"History calls, {label} (platform.history, fields fav_id, ts, data): {len(chunks)}")
    for chunk in chunks:
        print(json.dumps({"fav_ids": chunk["fav_ids"], "start": window["start"],
                          "end": window["end"], "end_exclusive": True}))


def cmd_calls(args):
    work = Path(args.workdir)
    window = json.loads((work / "window.json").read_text())
    print_calls(window, json.loads((work / "plan.json").read_text()), args.pass_no)


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    w = sub.add_parser("window", help="fix the week and print the discovery calls")
    w.add_argument("site", help="saved search_sites result for the site")
    w.add_argument("workdir")
    w.add_argument("--week-of", help="any date in the Monday-to-Sunday week to show")
    w.add_argument("--include", help="never-charted type codes the user asked for, e.g. LT")
    w.add_argument("--today", help=argparse.SUPPRESS)
    p = sub.add_parser("plan", help="pick points and passes from the discovery pages")
    p.add_argument("workdir")
    p.add_argument("discovery", nargs="+", help="saved platform.favourites pages")
    p.add_argument("--census", action="append", help="saved platform.equipment pages")
    p.add_argument("--cap", type=int, default=CAP_UNITS,
                   help=f"first-pass units (default {CAP_UNITS}; 0 fetches everything)")
    c = sub.add_parser("calls", help="print the history calls for one pass of an existing plan")
    c.add_argument("workdir")
    c.add_argument("--pass", dest="pass_no", type=int, default=2)
    args = parser.parse_args(argv[1:])
    try:
        {"window": cmd_window, "plan": cmd_plan, "calls": cmd_calls}[args.command](args)
    except (ValueError, KeyError) as exc:
        sys.exit(f"runhours_plan: {exc}")


if __name__ == "__main__":
    main(sys.argv)
