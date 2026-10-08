#!/usr/bin/env python3
"""shared-utils/ghl_creds.py -- the ONE Convert and Flow (GHL) credential lookup (INF002).

Used by the Skill 59 credential gate and by the install QC of skills 05, 29, 35 and 36
(through shared-utils/ghl-creds.sh). Standard library only. Never prints a credential.

Order (Trevor's rule):
  1. LOCATION ID under every name it is kept under -- GHL_LOCATION_ID,
     GOHIGHLEVEL_LOCATION_ID, GOHIGHLEVEL_ALLOWED_LOCATION_IDS,
     CONVERT_AND_FLOW_LOCATION_ID / convert_and_flow_location (and the CAF/HIGHLEVEL
     spellings) -- in the live env, then every store: ~/.openclaw/secrets/.env,
     ~/.openclaw/.env, ~/clawd/secrets/.env, workspace/.env, workspace/secrets/.env,
     workspace/secrets.env, service-env/ai.openclaw.gateway.env (Mac ~/.openclaw, VPS
     /data/.openclaw and container /home/node/.openclaw roots).
  2. Not found -> the Convert and Flow private integration token (a pit- token under
     GHL_API_KEY, GOHIGHLEVEL_API_KEY, GHL_PRIVATE_TOKEN, GOHIGHLEVEL_CF_PIT,
     CONVERT_AND_FLOW_API_KEY ...). Ask the GHL API which location that location-scoped
     token belongs to and use it. The resolved id is cached in memory and in a small
     state file (an id and a short token fingerprint, never the token).
  3. Neither -> status "missing": the caller installs WITH A NOTE naming what is needed.

Nothing here writes or changes a credential. Agency tokens are never used for step 2.
"""
import hashlib
import json
import os
import re
import shlex
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

LOCATION_NAMES = (
    "GHL_LOCATION_ID",
    "GOHIGHLEVEL_LOCATION_ID",
    "GOHIGHLEVEL_ALLOWED_LOCATION_IDS",
    "CONVERT_AND_FLOW_LOCATION_ID",
    "convert_and_flow_location",
    "CAF_LOCATION_ID",
    "CAF_ALLOWED_LOCATION_IDS",
    "HIGHLEVEL_LOCATION_ID",
)
PIT_NAMES = (
    "GOHIGHLEVEL_API_KEY",
    "GHL_API_KEY",
    "GHL_PRIVATE_TOKEN",
    "GOHIGHLEVEL_CF_PIT",
    "CONVERT_AND_FLOW_API_KEY",
    "CONVERT_AND_FLOW_PIT",
    "CONVERT_AND_FLOW_PRIVATE_INTEGRATION_TOKEN",
    "CONVERTANDFLOW_API_KEY",
    "CONVERTFLOW_API_KEY",
    "GHL_PRIVATE_INTEGRATION_TOKEN",
    "GHL_PIT",
    "GOHIGHLEVEL_PIT",
)
API_BASE = "https://services.leadconnectorhq.com"

NOTE_MISSING = ("Installed. Convert and Flow location id or private integration token needed "
                "before this skill can reach the account. Add GOHIGHLEVEL_LOCATION_ID (or the "
                "pit- token as GOHIGHLEVEL_API_KEY) to ~/.openclaw/secrets/.env.")
NOTE_UNRESOLVED = ("Installed. A Convert and Flow private integration token was found but the "
                   "location it belongs to could not be read from the API (offline or no scope). "
                   "Add GOHIGHLEVEL_LOCATION_ID to ~/.openclaw/secrets/.env.")

_MEMO = {}


def store_paths():
    """Every env store, highest priority first. Roots: Mac ~/.openclaw, VPS /data/.openclaw,
    container /home/node/.openclaw."""
    home = os.path.expanduser("~")
    roots = [home + "/.openclaw", "/data/.openclaw", "/home/node/.openclaw"]
    out = []
    for r in roots:
        out += [r + "/secrets/.env", r + "/.env", r + "/workspace/secrets.env",
                r + "/workspace/.env", r + "/workspace/secrets/.env",
                r + "/service-env/ai.openclaw.gateway.env"]
    out += [home + "/clawd/secrets/.env", "/data/clawd/secrets/.env"]
    seen, ordered = set(), []
    for p in out:
        if p not in seen:
            seen.add(p)
            ordered.append(p)
    return ordered


def _parse(path):
    vals = {}
    try:
        with open(path, encoding="utf-8", errors="ignore") as fh:
            for raw in fh:
                line = raw.strip()
                if not line or line.startswith("#"):
                    continue
                if line.startswith("export "):
                    line = line[7:].strip()
                if "=" not in line:
                    continue
                k, v = line.split("=", 1)
                v = v.strip()
                if len(v) >= 2 and v[0] == v[-1] and v[0] in "'\"":
                    v = v[1:-1]
                vals[k.strip()] = v.strip()
    except OSError:
        pass
    return vals


def _is_location_id(v):
    return bool(re.fullmatch(r"[A-Za-z0-9]{12,40}", v or ""))


_PLACEHOLDER_RE = re.compile(
    r"(?i)(your[_-]|xxx|placeholder|changeme|change_me|replace|paste|example|dummy|todo|<|>|_here)")


def _is_real_pit(v):
    return bool(v) and v.startswith("pit-") and len(v) >= 20 and not _PLACEHOLDER_RE.search(v)


def _first(names, sources, valid, first_of_list=False):
    """First valid value for any of `names` (case-insensitive) in `sources`
    [(label, mapping)], env first. A placeholder in one source never shadows a real value
    in another. Returns (value, "label:NAME") or (None, "")."""
    wanted = {n.lower(): n for n in names}
    for label, mapping in sources:
        by_lower = {k.lower(): (k, v) for k, v in mapping.items()}
        for lname in wanted:                       # honour the preferred-name order
            if lname not in by_lower:
                continue
            key, val = by_lower[lname]
            val = (val or "").strip().strip("'\"")
            if first_of_list and "," in val:
                val = val.split(",", 1)[0].strip()
            if val and valid(val):
                return val, "%s:%s" % (label, key)
    return None, ""


def sources_for(environ, stores):
    out = [("env", dict(environ))]
    for p in stores:
        out.append(("file:" + p, _parse(p)))
    return out


def _fp(pit):
    return hashlib.sha256(pit.encode()).hexdigest()[:12]


def _default_cache_path():
    for root in ("/data/.openclaw", os.path.expanduser("~/.openclaw")):
        if os.path.isdir(root):
            return root + "/state/ghl-location-cache.json"
    return None


def _http_get(url, pit):
    req = urllib.request.Request(url, headers={
        "Authorization": "Bearer " + pit, "Version": "2021-07-28",
        "Accept": "application/json",
        # GHL sits behind Cloudflare, which rejects the default Python agent (error 1010).
        "User-Agent": "Mozilla/5.0 (compatible; openclaw-onboarding)"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, ""
    except Exception:  # noqa: BLE001 - offline / DNS / TLS: unresolved, never a crash
        return 0, ""


def location_for_pit(pit, http=None):
    """Ask the API which location a location-scoped token belongs to. Exactly one
    location visible -> that id; none or several (an agency token) -> None."""
    status, body = (http or _http_get)(API_BASE + "/locations/search?limit=2", pit)
    if status != 200:
        return None
    try:
        locs = json.loads(body).get("locations") or []
    except (ValueError, AttributeError):
        return None
    ids = [l.get("id") for l in locs if isinstance(l, dict) and _is_location_id(l.get("id"))]
    return ids[0] if len(ids) == 1 and len(locs) == 1 else None


def _cache_get(fp, path):
    if fp in _MEMO:
        return _MEMO[fp]
    try:
        v = json.loads(Path(path).read_text()).get(fp) if path else None
    except (OSError, ValueError):
        v = None
    return v if _is_location_id(v or "") else None


def _cache_put(fp, loc, path):
    _MEMO[fp] = loc
    if not path:
        return
    try:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        try:
            data = json.loads(p.read_text())
        except (OSError, ValueError):
            data = {}
        data[fp] = loc
        p.write_text(json.dumps(data, indent=1) + "\n")
    except OSError:
        pass


def resolve(environ=None, stores=None, http=None, cache_path="default", use_api=True):
    """Returns {"status": "ok"|"missing"|"unresolved", "location_id", "location_source",
    "pit", "pit_source", "note"}. `pit` is returned for in-process use only and is never
    printed by the CLI. status ok = location known (by name or via the API)."""
    environ = os.environ if environ is None else environ
    stores = store_paths() if stores is None else stores
    cache_path = _default_cache_path() if cache_path == "default" else cache_path
    srcs = sources_for(environ, stores)
    loc, loc_src = _first(LOCATION_NAMES, srcs, _is_location_id, first_of_list=True)
    pit, pit_src = _first(PIT_NAMES, srcs, _is_real_pit)
    res = {"status": "ok", "location_id": loc, "location_source": loc_src,
           "pit": pit, "pit_source": pit_src, "note": ""}
    if loc:
        return res
    if pit and use_api:
        fp = _fp(pit)
        loc = _cache_get(fp, cache_path)
        src = "state-cache"
        if not loc:
            loc = location_for_pit(pit, http)
            src = "api:/locations/search via " + pit_src
            if loc:
                _cache_put(fp, loc, cache_path)
        if loc:
            res.update(location_id=loc, location_source=src)
            return res
    if pit:
        res.update(status="unresolved", note=NOTE_UNRESOLVED)
    else:
        res.update(status="missing", note=NOTE_MISSING)
    return res


def shell_exports(res, environ=None):
    """`export` lines for eval. Sets only what is currently empty. The PIT, when it was
    found in a store but not in the env, is exported into the shell only (never printed
    anywhere else); the location id is an identifier, not a credential."""
    environ = os.environ if environ is None else environ
    lines = ["export GHL_CREDS_STATUS=%s" % shlex.quote(res["status"]),
             "export GHL_CREDS_NOTE=%s" % shlex.quote(res["note"])]
    if res["location_id"] and not environ.get("GOHIGHLEVEL_LOCATION_ID"):
        lines.append("export GOHIGHLEVEL_LOCATION_ID=%s" % shlex.quote(res["location_id"]))
    if res["pit"] and not environ.get("GOHIGHLEVEL_API_KEY"):
        lines.append("export GOHIGHLEVEL_API_KEY=%s" % shlex.quote(res["pit"]))
    return "\n".join(lines)


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    res = resolve()
    if "--json" in argv:
        print(json.dumps({k: v for k, v in res.items() if k != "pit"}, indent=1))
    else:
        print(shell_exports(res))
    return 0


if __name__ == "__main__":
    sys.exit(main())
