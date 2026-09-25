#!/usr/bin/env python3
"""Make the run-hours calls straight to the PEAK API, where the environment has credentials.

Usage:
    python3 runhours_fetch.py site <workdir> <site_id | name>
    python3 runhours_fetch.py discover <workdir>
    python3 runhours_fetch.py history <workdir> [--pass 2]
    python3 runhours_fetch.py call <workdir> <name> '<printed call>'

The recipe in references/run-hours.md makes its calls through the PEAK MCP, a
round trip each, saving every inline response by hand. In Claude Code, with PEAK
API credentials in the environment — ACCESS_TOKEN_URL, CLIENT_ID and either
OFFLINE_TOKEN_ACCESS or CLIENT_SECRET, the variables peak-api-helper reads —
this script makes the same calls itself: each printed call (platform.X) runs as
the core GraphQL query X on api.cimenviro.com, history in parallel, and every
response is written to <workdir> in the shape the plan and build steps read.

site      the site's timezone and working hours as site.json, in place of search_sites
discover  the window step's discovery pages and a full census (types by unit)
history   one pass of the plan's history calls, six at a time
call      any one printed call, e.g. the last-reading probe, saved as <name>.json

Without credentials it exits with status 2: make the calls through the MCP.
Prints sizes and timings only, never a token or a row. Standard library only —
no third-party dependencies, by design, so the script runs wherever the skill
is unpacked.
"""
import argparse
import json
import os
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

# ---- Tunables ----------------------------------------------------------------
API_URL       = "https://api.cimenviro.com"
WORKERS       = 6       # history calls in flight at once
CENSUS_LIMIT  = 5000    # units per census page, ~70 bytes each
TIMEOUT_S     = 60
RETRIES       = 3       # per call, on a 5xx, 429 or dropped connection
NO_CREDENTIALS = 2      # exit status: use the MCP instead

_token = {"value": None}
_lock = threading.Lock()


class Retryable(Exception):
    pass


# ---- Auth and transport ---------------------------------------------------------
def credentials():
    env = os.environ
    url, client = env.get("ACCESS_TOKEN_URL"), env.get("CLIENT_ID")
    offline, secret = env.get("OFFLINE_TOKEN_ACCESS"), env.get("CLIENT_SECRET")
    if not (url and client and (offline or secret)):
        print("No PEAK API credentials in the environment (ACCESS_TOKEN_URL, CLIENT_ID and "
              "OFFLINE_TOKEN_ACCESS or CLIENT_SECRET): make the calls through the PEAK MCP instead.")
        sys.exit(NO_CREDENTIALS)
    if secret and not offline:                    # a service account
        form = {"grant_type": "client_credentials", "client_id": client, "client_secret": secret}
    else:                                         # a user's offline token
        form = {"grant_type": "refresh_token", "client_id": client, "refresh_token": offline,
                **({"client_secret": secret} if secret else {})}
    return url, form


def token(stale=None):
    """A bearer token, fetched once and shared by every thread; `stale` is one the API refused."""
    with _lock:
        if _token["value"] and _token["value"] != stale:
            return _token["value"]
        url, form = credentials()
        req = urllib.request.Request(url, data=urllib.parse.urlencode(form).encode(),
                                     headers={"Content-Type": "application/x-www-form-urlencoded"})
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
                _token["value"] = json.load(resp)["access_token"]
        except (urllib.error.URLError, KeyError, ValueError) as exc:
            sys.exit(f"runhours_fetch: could not get a PEAK access token ({type(exc).__name__}); "
                     "check the credentials, or make the calls through the PEAK MCP")
        return _token["value"]


def request(method, path, body=None):
    """One API request with a bearer token: retried on 5xx, 429 or a dropped connection, re-authorised on 401."""
    bearer = token()
    for attempt in range(1, RETRIES + 1):
        req = urllib.request.Request(f"{API_URL}{path}", method=method,
                                     data=json.dumps(body).encode() if body is not None else None,
                                     headers={"Authorization": f"Bearer {bearer}",
                                              "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
                return json.load(resp)
        except urllib.error.HTTPError as exc:
            if exc.code == 401 and attempt < RETRIES:
                bearer = token(stale=bearer)
                continue
            if exc.code != 429 and exc.code < 500:
                raise SystemExit(f"runhours_fetch: HTTP {exc.code} on {path}")
            if attempt == RETRIES:
                raise Retryable(f"HTTP {exc.code} on {path}")
        except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
            if attempt == RETRIES:
                raise Retryable(f"{type(exc).__name__} on {path}")
        time.sleep(2 ** attempt)
    raise Retryable(f"no response on {path}")


# ---- Printed call -> GraphQL -------------------------------------------------------
def _literal(value):
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(_literal(v) for v in value) + "]"
    if value is None:
        return "null"
    return json.dumps(value)                      # numbers and strings read the same in GraphQL


def _args(args):
    return "(" + ", ".join(f"{k}: {_literal(v)}" for k, v in args.items()) + ")" if args else ""


def _selection(fields):
    """Dotted paths and {path, args, sub_fields} objects, merged into one selection set."""
    tree = {}

    def add(node, field):
        if isinstance(field, str):
            head, _, rest = field.partition(".")
            child = node.setdefault(head, {"args": None, "kids": {}})
            if rest:
                add(child["kids"], rest)
        else:
            child = node.setdefault(field["path"], {"args": None, "kids": {}})
            child["args"] = field.get("args")
            for sub in field.get("sub_fields") or []:
                add(child["kids"], sub)

    def render(node):
        return " ".join(f"{name}{_args(spec['args'])}" + (f" {{ {render(spec['kids'])} }}" if spec["kids"] else "")
                        for name, spec in node.items())

    for f in fields:
        add(tree, f)
    return render(tree)


def run(call):
    """Rows of one printed call ({query_name: 'platform.X', args, fields}) as core GraphQL."""
    service, _, root = call["query_name"].partition(".")
    if service != "platform":
        raise ValueError(f"only platform.* calls run here, not {call['query_name']}")
    query = f"{{ {root}{_args(call.get('args'))} {{ {_selection(call['fields'])} }} }}"
    payload = request("POST", "/graphql", {"query": query})
    if payload.get("errors"):
        raise ValueError(f"GraphQL error on {root}: {json.dumps(payload['errors'])[:300]}")
    return (payload.get("data") or {}).get(root) or []


def paged(call):
    """Every page of a call: core GraphQL has no pagination block, so page while pages come back full."""
    rows, limit = [], call["args"]["limit"]
    start = call["args"].get("start_index", 0)
    while True:
        page = run({**call, "args": {**call["args"], "start_index": start}})
        rows.append(page)
        if len(page) < limit:
            return rows
        start += limit


def save(path, rows):
    text = json.dumps({"results": rows})
    Path(path).write_text(text)
    return len(text)


def kb(n):
    return f"{n / 1024:.0f} KB"


# ---- Commands ----------------------------------------------------------------
def cmd_site(args):
    work = Path(args.workdir)
    work.mkdir(parents=True, exist_ok=True)
    ref = args.site.strip()
    if not ref.isdigit():
        pattern = ref if "%" in ref else f"%{ref}%"
        hits = run({"query_name": "platform.sites", "args": {"site_name": pattern, "is_active": True},
                    "fields": ["site_id", "site_name"]})
        exact = [h for h in hits if h["site_name"].lower() == ref.lower()]
        if len(exact or hits) != 1:
            listed = "; ".join(f"{h['site_id']} {h['site_name']}" for h in hits[:10]) or "none"
            sys.exit(f"'{ref}' matches {len(hits)} sites ({listed}): pass the site_id")
        ref = str((exact or hits)[0]["site_id"])
    site = (request("GET", f"/sites/{ref}").get("data") or {}).get("site")
    if not site:
        sys.exit(f"runhours_fetch: no site {ref}")
    row = {"site_id": site["site_id"], "site_name": site["site_name"], "timezone": site["timezone"],
           "working_hours": site.get("working_hours"),
           "site_link": f"https://ace.cimenviro.com/sites/manage-sites/{site['site_id']}"}
    save(work / "site.json", [row])
    print(f"{row['site_name']} (site {row['site_id']}, {row['timezone']}): wrote {work / 'site.json'}")


def cmd_discover(args):
    work = Path(args.workdir)
    calls = json.loads((work / "calls.json").read_text())
    base = calls["census"][0]["args"]
    census = {"query_name": "platform.equipment", "fields": ["metadata_type.type_code", "metadata_type.type"],
              "args": {"site_id": base["site_id"], "is_active": base.get("is_active", True),
                       "limit": CENSUS_LIMIT, "start_index": 0}}
    t0 = time.time()
    with ThreadPoolExecutor(2) as pool:
        pages, census_pages = pool.map(paged, [calls["discovery"], census])
    for old in work.glob("discovery-*.json"):
        old.unlink()
    for i, page in enumerate(pages):
        points = sum(len(u.get("favourites") or []) for u in page)
        print(f"discovery-{i}.json: {len(page)} units, {points} points, {kb(save(work / f'discovery-{i}.json', page))}")
    units = [u for page in census_pages for u in page]
    print(f"census.json: {len(units)} units, {kb(save(work / 'census.json', units))}")
    print(f"Discovery and census in {time.time() - t0:.1f} s. Next: runhours_plan.py plan {work} "
          f"{' '.join(str(work / f'discovery-{i}.json') for i in range(len(pages)))} --census {work / 'census.json'}")


def cmd_history(args):
    work = Path(args.workdir)
    window = json.loads((work / "window.json").read_text())
    plan = json.loads((work / "plan.json").read_text())
    chunks = [c["fav_ids"] for c in plan["chunks"] if c["pass"] == args.pass_no]
    if not chunks:
        sys.exit(f"runhours_fetch: the plan has no pass {args.pass_no} history calls")
    for old in work.glob(f"history-p{args.pass_no}-*.json"):
        old.unlink()

    def pull(item):
        name, fav_ids = item
        call = {"query_name": "platform.history", "fields": ["fav_id", "ts", "data"],
                "args": {"fav_ids": fav_ids, "start": window["start"], "end": window["end"],
                         "end_exclusive": True}}
        try:
            rows = run(call)
        except Retryable:
            if len(fav_ids) == 1:
                raise
            half = len(fav_ids) // 2                 # too big for the gateway: halve and retry
            return pull((f"{name}a", fav_ids[:half])) + pull((f"{name}b", fav_ids[half:]))
        return [(name, len(fav_ids), len(rows), save(work / f"history-p{args.pass_no}-{name}.json", rows))]

    t0 = time.time()
    with ThreadPoolExecutor(WORKERS) as pool:
        done = [r for result in pool.map(pull, [(f"{i:02d}", c) for i, c in enumerate(chunks)]) for r in result]
    total = sum(r[3] for r in done)
    print(f"History pass {args.pass_no}: {len(done)} calls, {sum(r[1] for r in done)} points, "
          f"{sum(r[2] for r in done)} rows, {kb(total)}, in {time.time() - t0:.1f} s. "
          f"Files: {work}/history-p{args.pass_no}-*.json")


def cmd_call(args):
    work = Path(args.workdir)
    call = json.loads(args.call)
    if "query_name" not in call:                  # a printed history call is its args alone
        call = {"query_name": "platform.history", "fields": ["fav_id", "ts", "data"], "args": call}
    rows = run(call)
    print(f"{args.name}.json: {len(rows)} rows, {kb(save(work / f'{args.name}.json', rows))}")


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    s = sub.add_parser("site", help="the site's timezone and working hours, as site.json")
    s.add_argument("workdir")
    s.add_argument("site", help="site_id, or a name to match")
    d = sub.add_parser("discover", help="the discovery pages and a full census")
    d.add_argument("workdir")
    h = sub.add_parser("history", help="one pass of the plan's history calls")
    h.add_argument("workdir")
    h.add_argument("--pass", dest="pass_no", type=int, default=1)
    c = sub.add_parser("call", help="one printed call, saved as <name>.json")
    c.add_argument("workdir")
    c.add_argument("name")
    c.add_argument("call", help="the call as printed, JSON")
    args = parser.parse_args(argv[1:])
    try:
        {"site": cmd_site, "discover": cmd_discover, "history": cmd_history, "call": cmd_call}[args.command](args)
    except (Retryable, ValueError, KeyError, OSError) as exc:
        sys.exit(f"runhours_fetch: {exc}")


if __name__ == "__main__":
    main(sys.argv)
