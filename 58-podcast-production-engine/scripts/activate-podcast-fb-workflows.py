#!/usr/bin/env python3
"""activate-podcast-fb-workflows.py -- PER-CLIENT Facebook-ads activation for the podcast
snapshot's four Facebook-ad workflows.

WHY THIS EXISTS: the four FB-ad workflows (01a Update FB audience, 02 Fb Lead didn't
complete, 02a 2nd Fb interview, 03 LeadForm Fb Ad) ship in the template STRUCTURALLY
CORRECT but DRAFT with their Facebook account/audience/pixel/token fields BLANK -- because
the Facebook connection is inherently per-client (each client connects their own Facebook
Business account and picks their own Lead Forms / Custom Audiences / Pixel). Nothing about
Facebook can be fabricated in a fleet template. Once a client is ready to run ads and has
connected Facebook in the Convert-and-Flow (GoHighLevel) UI, this script fills the blank
Facebook fields with the client's real ids and PUBLISHES (activates) the four workflows.

PREREQUISITE (done by the client in the GHL UI, NOT here): connect the Facebook Business
account under Settings -> Integrations, then note the ad-account id (act_...), the Custom
Audience id(s), and the Pixel id + Conversions API access token. The Facebook Lead Form
TRIGGER (which page/form fires 02/02a/03) is added in the workflow builder because it must
select a live connected form -- see the printed checklist.

Auth (never printed): a Firebase refresh token, same internal rail as
verify-podcast-ghl-workflows.py. Reads --token-env (default the client refresh var, then
GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN). Writes ONLY to the --location you pass.

Idempotent + safe: with no --fb-* values it runs a DRY report (what it would fill/publish).
Pass --execute to write. Demote-trap-safe publish (re-asserts status/version/templates)."""
from __future__ import annotations
import argparse, json, os, ssl, sys, time, copy, urllib.request, urllib.error

FIREBASE_API_KEY_DEFAULT = "AIzaSyB_w3vXmsI7WeQtrIOkjR6xTRVN5uOieiE"  # GHL public Firebase web-app identifier - shared, non-secret, same value GHL embeds in its own SPA
FIREBASE_API_KEY = os.environ.get("FIREBASE_API_KEY") or FIREBASE_API_KEY_DEFAULT
BASE = "https://backend.leadconnectorhq.com"
CTX = ssl.create_default_context()
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
DEFAULT_LOC = "CjxATjhv9Gt21qSqURIt"

# name-substring -> which FB fields this workflow uses
FB_WORKFLOWS = [
    ("01a", "01a - Update Facebook audience", {"audience"}),
    ("02",  "02-Fb Podcast Lead That DID NOT COMPLETE", {"audience"}),
    ("02a", "02a-2nd Fb Podcast Interview", {"audience"}),
    ("03",  "03-Podcast LeadForm Fb Ad", {"capi"}),
]


def _source_secrets(names):
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


def _req(tok, method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method, headers={
        "token-id": tok, "channel": "APP", "source": "WEB_USER", "version": "2021-07-28",
        "Content-Type": "application/json", "Accept": "application/json", "User-Agent": UA})
    try:
        with urllib.request.urlopen(req, context=CTX, timeout=45) as r:
            txt = r.read().decode()
            return r.status, (json.loads(txt) if txt.strip() else {})
    except urllib.error.HTTPError as e:
        eb = e.read().decode() if e.fp else ""
        try:
            return e.code, json.loads(eb)
        except Exception:
            return e.code, {"_raw": eb[:300]}
    except Exception as e:  # noqa: BLE001
        return -1, {"_exc": str(e)[:300]}


CHECKLIST = """
PER-CLIENT FACEBOOK-ADS CONNECT CHECKLIST (do these in order):
  1. Client connects their Facebook Business account in Convert-and-Flow (GoHighLevel):
     Settings -> Integrations -> Facebook -> Connect. They authorize their OWN account.
  2. In the connected account, note: ad-account id (act_...), the Custom Audience id(s)
     for retargeting/lookalike, and the Pixel id + Conversions API access token.
  3. Re-run this script with --execute and the real ids:
       --fb-account act_XXXX --fb-audience 12345 --fb-pixel 67890 --fb-token TTT
     (it fills the blank Facebook fields and PUBLISHES the four workflows).
  4. In the workflow builder, add the Facebook Lead Form TRIGGER to 02 / 02a / 03
     (select the client's live connected Lead Form). It cannot be scripted because it
     must bind to a live form; the workflows are otherwise fully wired and published.
  5. Re-run scripts/verify-podcast-ghl-workflows.py and confirm the required 4 still PASS.
"""


def _match_workflow(rows, expected_name):
    """Match a workflow by full normalized name (case-insensitive, trimmed).

    Returns the first row whose name matches *exactly* after stripping
    and lowercasing both sides.  Returns None when no row matches.
    """
    target = expected_name.strip().lower()
    return next((r for r in rows if r.get("name", "").strip().lower() == target), None)


# --------------------------------------------------------------------------- #
# Self-test
# --------------------------------------------------------------------------- #
def self_test():
    """Run in-process assertions against _match_workflow only.  No network."""
    ok = True

    def check(label, cond):
        nonlocal ok
        ok = ok and cond
        print("  [%s] %s" % ("PASS" if cond else "FAIL", label))

    rows = [
        {"id": "1", "name": "01a - Update Facebook audience"},
        {"id": "2", "name": "02-Fb Podcast Lead That DID NOT COMPLETE"},
        {"id": "3", "name": "02a-2nd Fb Podcast Interview"},
        {"id": "4", "name": "03-Podcast LeadForm Fb Ad"},
        {"id": "5", "name": "01a-fake-decoy-workflow-that-shares-prefix"},
    ]

    print("== self-test: exact match passes ==")
    m = _match_workflow(rows, "01a - Update Facebook audience")
    check("exact-match-found", m is not None and m["id"] == "1")
    check("exact-match-no-false-hit-on-prefix-rival",
          m is not None and m["name"] == "01a - Update Facebook audience")

    m2 = _match_workflow(rows, "02-Fb Podcast Lead That DID NOT COMPLETE")
    check("exact-match-long-name", m2 is not None and m2["id"] == "2")

    print("== self-test: prefix-only match is rejected ==")
    m_pfx = _match_workflow(rows, "01a")
    check("prefix-only-rejected", m_pfx is None)

    m_pfx2 = _match_workflow(rows, "01a -")
    check("partial-name-rejected", m_pfx2 is None)

    print("== self-test: case/whitespace variants match ==")
    m_case = _match_workflow(rows, "  03-podcast leadform fb ad  ")
    check("lowercase-and-whitespace-ok", m_case is not None and m_case["id"] == "4")

    m_mixed = _match_workflow(rows, "02a-2ND FB PODCAST INTERVIEW")
    check("mixed-case-ok", m_mixed is not None and m_mixed["id"] == "3")

    print("== self-test: fully-missing name yields None ==")
    m_nope = _match_workflow(rows, "NON-EXISTENT WORKFLOW")
    check("missing-name-returns-none", m_nope is None)

    print("== self-test: %s ==" % ("ALL ASSERTIONS PASSED" if ok else "FAILED"))
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--location", default=os.environ.get("GHL_LOCATION_ID") or os.environ.get("PODCAST_ENGINE_GHL_LOCATION_ID") or "")
    ap.add_argument("--token-env", default="PODCAST_ENGINE_GHL_FIREBASE_REFRESH_TOKEN,GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN")
    ap.add_argument("--fb-account", default="")
    ap.add_argument("--fb-audience", default="")
    ap.add_argument("--fb-pixel", default="")
    ap.add_argument("--fb-token", default="")
    ap.add_argument("--execute", action="store_true")
    ap.add_argument("--self-test", dest="self_test", action="store_true")
    args = ap.parse_args()
    if args.self_test:
        return self_test()
    if not args.location:
        print("FAIL: --location (or GHL_LOCATION_ID / PODCAST_ENGINE_GHL_LOCATION_ID env) is required - "
              "this script WRITES to the target sub-account", file=sys.stderr)
        return 1
    loc = args.location
    names = [n.strip() for n in args.token_env.split(",") if n.strip()]
    _source_secrets(names)
    refresh = next((os.environ[n] for n in names if os.environ.get(n, "").strip()), "")
    if not refresh:
        print(f"FAIL: no Firebase refresh token in {names}", file=sys.stderr); return 1
    tok = _mint(refresh)
    if not tok:
        print("FAIL: could not mint id_token", file=sys.stderr); return 1

    have_fb = any([args.fb_account, args.fb_audience, args.fb_pixel, args.fb_token])
    print(f"== FB-ads activation -- location {loc} ==")
    print(CHECKLIST)
    if not have_fb:
        print("No --fb-* values supplied: reporting current state only (nothing written).")

    code, listing = _req(tok, "GET", f"/workflow/{loc}/list?limit=200")
    rows = [r for r in (listing.get("rows", []) if isinstance(listing, dict) else []) if r.get("type") == "workflow"]
    ok_all = True
    for key, sub, uses in FB_WORKFLOWS:
        match = _match_workflow(rows, sub)
        if not match:
            print(f"[MISS] {key}: no workflow matching {sub!r}"); ok_all = False; continue
        wid = match["id"]
        _, wf = _req(tok, "GET", f"/workflow/{loc}/{wid}")
        templates = copy.deepcopy((wf.get("workflowData") or {}).get("templates", []))
        filled = []
        for s in templates:
            a = s.get("attributes", {}); typ = s.get("type") or a.get("type")
            if typ in ("facebook_add_to_custom_audience", "facebook_remove_from_custom_audience"):
                if args.fb_account: a["facebook_account_id"] = args.fb_account
                if args.fb_audience: a["facebook_custom_audience_id"] = args.fb_audience
                filled.append("audience")
            elif typ == "facebook_conversion_api":
                if args.fb_pixel: a["pixel_id"] = args.fb_pixel
                if args.fb_token: a["access_token"] = args.fb_token
                filled.append("capi")
        status_now = wf.get("status")
        if not args.execute or not have_fb:
            print(f"[DRY ] {key} {wid} status={status_now} fb_steps={filled} would_publish={have_fb}")
            continue
        body = {"name": wf.get("name"), "version": wf.get("version", 1), "status": "published",
                "meta": wf.get("meta") or {}, "workflowData": {"templates": templates},
                "triggersChanged": False, "oldTriggers": [], "newTriggers": []}
        pc, pr = _req(tok, "PUT", f"/workflow/{loc}/{wid}", body)
        _, v = _req(tok, "GET", f"/workflow/{loc}/{wid}")
        ok = pc == 200 and v.get("status") == "published"
        ok_all = ok_all and ok
        print(f"[{'PUB ' if ok else 'FAIL'}] {key} {wid} http={pc} status_now={v.get('status')} fb_steps_filled={filled}")
        if pc != 200:
            print("        err:", json.dumps(pr)[:200])
        time.sleep(0.5)

    print("\nNOTE: publishing a FB workflow REQUIRES its FB custom-audience/CAPI fields be non-empty"
          " (GoHighLevel validates published actions). Supply all --fb-* ids the workflow uses.")
    return 0 if ok_all else 1


if __name__ == "__main__":
    sys.exit(main())
