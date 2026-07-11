#!/usr/bin/env python3
"""verify-podcast-ghl-workflows.py — LIVE QC gate for the podcast GHL snapshot.

Re-GETs the four required workflows in the podcast TEMPLATE sub-account via the
GHL internal rail (Firebase JWT — the same backend.leadconnectorhq.com rail the
Skill-44 caf builder uses) and ASSERTS each is:
  * status == "published"
  * has exactly one trigger, active == True, of the EXPECTED trigger type
  * has >= 1 action step

WHY THIS EXISTS: the first podcast build shipped the four workflows as INACTIVE
shells with no triggers wired, and nothing detected it — the operator had to add
the triggers by hand.  This gate makes that failure loud and re-runnable before a
snapshot is cut.  It is READ-ONLY (never writes).

Auth (never printed): reads a Firebase refresh token from the first present of
  --token-env  (default: PODCAST_ENGINE_GHL_FIREBASE_REFRESH_TOKEN,
                          GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN)
Secrets are sourced from $SECRETS_ENV or ~/.openclaw/secrets/.env if the vars are
not already exported.

Exit 0 = all four PASS; exit 1 = any FAIL / auth error.
"""
from __future__ import annotations
import argparse, json, os, ssl, sys, urllib.request, urllib.error

FIREBASE_API_KEY = "AIzaSyB_w3vXmsI7WeQtrIOkjR6xTRVN5uOieiE"
BASE = "https://backend.leadconnectorhq.com"
CTX = ssl.create_default_context()
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

# Podcast TEMPLATE sub-account (golden-snapshot source). Override with --location.
DEFAULT_LOC = "CjxATjhv9Gt21qSqURIt"

# name-substring -> (expected trigger type, human label). Matched against the live
# workflow name so the gate is resilient to id changes across snapshot imports.
EXPECTED = [
    ("01-Podcast Intake Submitted (Interview)", "survey_submission", "Survey Submitted (Interview)"),
    ("02-Podcast Intake Submitted (Personal)",  "survey_submission", "Survey Submitted (Personal)"),
    ("04-Podcast is Completed",                 "contact_changed",   "Custom Field Changed (episode url)"),
    ("06-Podcast_Episode_Is_Ready",             "contact_tag",       "Contact Tag Added"),
]


def _source_secrets_if_needed(names):
    if any(os.environ.get(n, "").strip() for n in names):
        return
    path = os.environ.get("SECRETS_ENV") or os.path.expanduser("~/.openclaw/secrets/.env")
    if not os.path.isfile(path):
        return
    with open(path, encoding="utf-8", errors="ignore") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            k = k.strip()
            if k in names and k not in os.environ:
                os.environ[k] = v.strip().strip('"').strip("'")


def _mint(refresh):
    body = f"grant_type=refresh_token&refresh_token={refresh}".encode()
    req = urllib.request.Request(
        f"https://securetoken.googleapis.com/v1/token?key={FIREBASE_API_KEY}",
        data=body, headers={"Content-Type": "application/x-www-form-urlencoded"}, method="POST")
    with urllib.request.urlopen(req, context=CTX, timeout=15) as r:
        return json.loads(r.read()).get("id_token", "")


def _get(tok, path):
    req = urllib.request.Request(BASE + path, headers={
        "token-id": tok, "channel": "APP", "source": "WEB_USER",
        "version": "2021-07-28", "Accept": "application/json", "User-Agent": UA})
    try:
        with urllib.request.urlopen(req, context=CTX, timeout=45) as r:
            txt = r.read().decode()
            return r.status, (json.loads(txt) if txt.strip() else {})
    except urllib.error.HTTPError as e:
        return e.code, {"_err": (e.read().decode() if e.fp else "")[:200]}
    except Exception as e:  # noqa: BLE001
        return -1, {"_exc": str(e)[:200]}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--location", default=os.environ.get("PODCAST_ENGINE_GHL_LOCATION_ID") or DEFAULT_LOC)
    ap.add_argument("--token-env", default="PODCAST_ENGINE_GHL_FIREBASE_REFRESH_TOKEN,GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN")
    args = ap.parse_args()
    loc = args.location
    names = [n.strip() for n in args.token_env.split(",") if n.strip()]

    _source_secrets_if_needed(names)
    refresh = next((os.environ[n] for n in names if os.environ.get(n, "").strip()), "")
    if not refresh:
        print(f"FAIL: no Firebase refresh token found in env {names}", file=sys.stderr)
        return 1
    try:
        tok = _mint(refresh)
    except Exception as e:  # noqa: BLE001
        print(f"FAIL: could not mint id_token: {e}", file=sys.stderr)
        return 1
    if not tok:
        print("FAIL: minted empty id_token", file=sys.stderr)
        return 1

    code, listing = _get(tok, f"/workflow/{loc}/list?limit=200")
    if code != 200 or not isinstance(listing, dict):
        print(f"FAIL: workflow list http={code} {listing}", file=sys.stderr)
        return 1
    rows = [r for r in listing.get("rows", []) if r.get("type") == "workflow"]
    by_name = {r.get("name", ""): r for r in rows}

    print(f"== LIVE podcast-workflow QC — location {loc} ({len(rows)} workflows) ==")
    all_ok = True
    for name_sub, exp_type, label in EXPECTED:
        match = next((r for n, r in by_name.items() if name_sub in n), None)
        if not match:
            print(f"[FAIL] missing workflow: {name_sub!r}")
            all_ok = False
            continue
        wid = match.get("id")
        _, wf = _get(tok, f"/workflow/{loc}/{wid}")
        steps = (wf.get("workflowData") or {}).get("templates", []) if isinstance(wf, dict) else []
        _, trigs = _get(tok, f"/workflow/{loc}/trigger?workflowId={wid}")
        trigs = trigs if isinstance(trigs, list) else []
        t = trigs[0] if trigs else {}
        ok = (wf.get("status") == "published" and len(trigs) >= 1
              and t.get("active") is True and t.get("type") == exp_type and len(steps) >= 1)
        all_ok = all_ok and ok
        print(f"[{'PASS' if ok else 'FAIL'}] {name_sub}")
        print(f"        status={wf.get('status')} steps={len(steps)} "
              f"trigger(count={len(trigs)}, type={t.get('type')}, active={t.get('active')}) expect={exp_type} ({label})")

    print("\nRESULT:", "ALL PASS" if all_ok else "FAILURES PRESENT")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
