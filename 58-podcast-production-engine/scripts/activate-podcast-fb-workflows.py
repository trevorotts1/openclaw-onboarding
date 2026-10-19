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

ROUTE (GU-015 / GU-004 sections 2.5, 3.2, 5.7): the read route is chosen EXPLICITLY and
recorded. When the public status/definition adapter's capability is enabled for this
tenant (workflows.list + workflows.definition.read), the public adapter
(ghl-public-adapter-0.1, services.leadconnectorhq.com, per-operation Version) is the
PRIMARY read route. Otherwise -- capability record absent/disabled, adapter package not
installed, or the public read refuses -- reads use the standalone private Firebase rail
below as a BOUNDED fallback. The fill + publish path stays on the private rail: the public
V4 definition write is disabled (B-V4-S, staging-only) and public publish parity is NOT
verified here, so no public write is claimed. This is a route decision, not parity: the
public and private payload shapes have never been proven equivalent.

Auth (never printed): public route resolves the location PIT through the frozen alias
chain (PODCAST_ENGINE_GHL_PIT first for Skill 58). Private fallback reads a Firebase
refresh token: --token-env (default the client refresh var, then
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

# exact live template name -> which FB fields this workflow uses.
# _match_workflow() compares the WHOLE name, so these must be the names the
# snapshot actually ships -- truncated names match nothing.
FB_WORKFLOWS = [
    ("01a", "01a - Update Facebook audience when survey completed (must update to work)", {"audience"}),
    ("02",  "02-Fb Podcast Lead That DID NOT COMPLETE INTERVIEW (MUST ADD TRIGGER FOR FB LEAD FORM AD related to Podcast)", {"audience"}),
    ("02a", "02a-2nd Fb Podcast Interview (Lead That DID NOT COMPLETE INTERVIEW (MUST ADD TRIGGER FOR FB LEAD FORM AD related to Podcast)", {"audience"}),
    ("03",  "03-Podcast LeadForm Fb Ad submitted (MUST ADD TRIGGER FOR FB LEAD FORM AD)", {"capi"}),
]

# ---- route policy (frozen vocabulary; never promoted without evidence) -----------------
PUBLIC_READ_OPS = ("workflows.list", "workflows.definition.read")
PUBLIC_WRITE_OPS = ("workflows.definition.update", "workflows.status.publish")
PUBLIC_ENGINE_ENV = "GHL_PUBLIC_ENGINE_PATH"
CAPABILITIES_ENV = "GHL_PUBLIC_CAPABILITIES_FILE"
PARITY_STATE = "unverified: public reads were never proven byte-equivalent to the private workflowData payload"


def _public_engine_root():
    """Directory holding the `cli_anything` package, or None. Bounded lookup only."""
    from pathlib import Path
    here = Path(__file__).resolve()
    candidates = []
    if os.environ.get(PUBLIC_ENGINE_ENV):
        candidates.append(Path(os.environ[PUBLIC_ENGINE_ENV]).expanduser())
    # Sibling skill install (operator repo and fleet layout share this shape).
    candidates.append(here.parents[2] / "44-convert-and-flow-operator" / "tools" / "engine")
    candidates.append(Path.home() / ".openclaw" / "skills" / "44-convert-and-flow-operator" / "tools" / "engine")
    for root in candidates:
        if (root / "cli_anything" / "gohighlevel" / "public" / "__init__.py").is_file():
            return root
    return None


def _load_capabilities(path, tenant):
    """Strict capability record -> ({op: Capability}, reason).

    Shape: {"tenant": "<location>", "capabilities": {"<op>": {<Capability fields>}}}.
    A missing/mismatched/invalid record yields ({}, reason); the gate stays default-deny.
    """
    if not path:
        return {}, "capability record absent (default-deny; state/ghl-public-capabilities.json)"
    try:
        with open(os.path.expanduser(path), encoding="utf-8") as fh:
            doc = json.load(fh)
    except Exception as exc:  # noqa: BLE001 - a bad record is a fallback reason, not a crash
        return {}, "capability record unreadable (%s)" % type(exc).__name__
    if not isinstance(doc, dict) or str(doc.get("tenant", "")) != str(tenant):
        return {}, "capability record tenant does not match --location"
    rows = doc.get("capabilities")
    if not isinstance(rows, dict) or not rows:
        return {}, "capability record carries no capabilities"
    root = _public_engine_root()
    if root is None:
        return {}, "public adapter package not importable"
    sys.path.insert(0, str(root))
    try:
        from cli_anything.gohighlevel.public.capability import Capability
    except Exception as exc:  # noqa: BLE001
        return {}, "public capability module not importable (%s)" % type(exc).__name__
    out = {}
    for op, row in rows.items():
        if not isinstance(row, dict):
            return {}, "capability row %r is not an object" % (op,)
        try:
            out[str(op)] = Capability(operation_id=str(op), **row)
        except Exception as exc:  # noqa: BLE001 - ContractViolation and TypeError both refuse
            return {}, "capability row %r invalid (%s)" % (op, type(exc).__name__)
    return out, ""


def select_route(location, capability_path, forced="auto"):
    """Explicit read-route choice. Returns a record; never guesses parity."""
    record = {
        "read_route": "private-firebase",
        "write_route": "private-firebase",
        "parity": PARITY_STATE,
        "public_operations": [],
        "reason": "",
    }
    if forced == "private":
        record["reason"] = "--route private (explicit)"
        return record
    if forced == "public":
        record["reason"] = "--route public requested; capability record still must enable every read op"
    root = _public_engine_root()
    if root is None:
        record["reason"] = ("public adapter package not importable (set %s or install Skill 44)"
                            % PUBLIC_ENGINE_ENV)
        return record
    caps, why = _load_capabilities(capability_path, location)
    if why:
        record["reason"] = why
        return record
    missing = [op for op in PUBLIC_READ_OPS if not (caps.get(op) and caps[op].enabled)]
    if missing:
        blocks = []
        for op in missing:
            cap = caps.get(op)
            block = getattr(cap, "activation_blocked", None)
            blocks.append("%s=%s" % (op, getattr(block, "reason", "disabled")))
        record["reason"] = "public read capability disabled: " + "; ".join(blocks)
        return record
    record.update(
        read_route="public",
        public_operations=list(PUBLIC_READ_OPS),
        reason=("capability enabled for %s at tenant %s; private Firebase rail retained as "
                "bounded fallback" % (", ".join(PUBLIC_READ_OPS), location)),
    )
    return record


def _public_read(location, capability_path):
    """Read the four workflows through the frozen public adapter (read-only).

    Returns (rows, reason). Rows are public `workflow` records; `definition` keys are
    added only when the definition read succeeded. Nothing here writes.
    """
    caps, why = _load_capabilities(capability_path, location)
    if why:
        return None, why
    root = _public_engine_root()
    sys.path.insert(0, str(root))
    try:
        from cli_anything.gohighlevel.public import PublicGhlAdapter
        from cli_anything.gohighlevel.public.auth import AuthKind, TenantBinding, resolve_auth
        from cli_anything.gohighlevel.public.capability import CapabilityGate
        from cli_anything.gohighlevel.public.transport import RequestsTransport
        from cli_anything.gohighlevel.public.workflow_v4 import RecordingTransport
    except Exception as exc:  # noqa: BLE001
        return None, "public adapter import failed (%s)" % type(exc).__name__
    try:
        auth = resolve_auth(kind=AuthKind.location_pit, location_id=location,
                            prefer_engine_tenant=True)
    except Exception as exc:  # noqa: BLE001 - no PIT -> bounded fallback, never a silent zero
        return None, "public auth resolution failed (%s)" % type(exc).__name__
    gate = CapabilityGate(caps, tenant=location)
    recorder = RecordingTransport(RequestsTransport())
    adapter = PublicGhlAdapter(auth=auth, transport=recorder, capability=gate)
    tenant = TenantBinding(location_id=location, source="cli:--location")

    def body(mark):
        if mark >= len(recorder.records):
            return None
        rec = recorder.records[mark]
        if rec.error_kind != "none" or not rec.body:
            return None
        try:
            return json.loads(rec.body.decode("utf-8"))
        except Exception:  # noqa: BLE001
            return None

    mark = len(recorder)
    listed = adapter.call(operation_id="workflows.list", tenant=tenant)
    if listed.status.value != "ok":
        return None, "public workflows.list status=%s" % listed.status.value
    payload = body(mark)
    rows = payload if isinstance(payload, list) else None
    if rows is None and isinstance(payload, dict):
        rows = next((payload[k] for k in ("workflows", "rows", "data")
                     if isinstance(payload.get(k), list)), None)
    if rows is None:
        return None, "public workflows.list payload carried no workflow array"
    out = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        rec = dict(row)
        width = rec.get("id") or rec.get("_id")
        if width:
            mark = len(recorder)
            read = adapter.call(operation_id="workflows.definition.read", tenant=tenant,
                                path_params={"workflowId": str(width)})
            if read.status.value == "ok":
                rec["definition"] = body(mark)
        out.append(rec)
    return out, "public read ok"


def _route_rows(tok, loc, route):
    """Read rows for the selected route. A public read failure falls back to the private
    rail (reads have no side effect), and the fallback is named in the returned reason."""
    if route["read_route"] == "public":
        rows, why = _public_read(loc, route.get("capability_path"))
        if rows is not None:
            return rows, "public"
        if not tok:
            return [], ("public read refused (" + why + "); private fallback unavailable "
                        "because no Firebase refresh token is configured")
        return _list_workflows(tok, loc)[1], "private-firebase after public read refused: " + why
    return _list_workflows(tok, loc)[1], "private-firebase"


def _status_of(row):
    if isinstance(row.get("definition"), dict):
        return row["definition"].get("status") or row.get("status")
    return row.get("status")


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


def _list_workflows(tok, loc):
    """Page /workflow/{loc}/list -- one GET only returns 200 rows, and real
    sub-accounts hold more (341 rows has been observed), which silently hid
    workflows from every reader."""
    rows, off = [], 0
    while off < 10000:  # ponytail: 10k-row ceiling; raise it only if a sub-account grows past that
        code, page = _req(tok, "GET", f"/workflow/{loc}/list?limit=100&offset={off}&type=workflow")
        page_rows = page.get("rows", []) if code == 200 and isinstance(page, dict) else []
        rows.extend(r for r in page_rows if r.get("type") == "workflow")
        if code != 200 or len(page_rows) < 100:
            break
        off += 100
    return code, rows


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

    rows = [{"id": str(i + 1), "name": name} for i, (_key, name, _uses) in enumerate(FB_WORKFLOWS)]
    rows.append({"id": "5", "name": "01a-fake-decoy-workflow-that-shares-prefix"})

    print("== self-test: exact match passes ==")
    m = _match_workflow(rows, FB_WORKFLOWS[0][1])
    check("exact-match-found", m is not None and m["id"] == "1")
    check("exact-match-no-false-hit-on-prefix-rival",
          m is not None and m["name"] == FB_WORKFLOWS[0][1])

    m2 = _match_workflow(rows, FB_WORKFLOWS[1][1])
    check("exact-match-long-name", m2 is not None and m2["id"] == "2")

    print("== self-test: prefix-only match is rejected ==")
    m_pfx = _match_workflow(rows, "01a")
    check("prefix-only-rejected", m_pfx is None)

    m_pfx2 = _match_workflow(rows, "01a -")
    check("partial-name-rejected", m_pfx2 is None)

    print("== self-test: truncated (pre-fix) name is rejected ==")
    m_old = _match_workflow(rows, "01a - Update Facebook audience")
    check("truncated-name-rejected", m_old is None)

    print("== self-test: case/whitespace variants match ==")
    m_case = _match_workflow(rows, "  %s  " % FB_WORKFLOWS[3][1].lower())
    check("lowercase-and-whitespace-ok", m_case is not None and m_case["id"] == "4")

    m_mixed = _match_workflow(rows, FB_WORKFLOWS[2][1].upper())
    check("mixed-case-ok", m_mixed is not None and m_mixed["id"] == "3")

    print("== self-test: fully-missing name yields None ==")
    m_nope = _match_workflow(rows, "NON-EXISTENT WORKFLOW")
    check("missing-name-returns-none", m_nope is None)

    print("== self-test: route choice is explicit and never claims parity ==")
    rec = select_route("loc_route_test", "", forced="private")
    check("forced-private", rec["read_route"] == "private-firebase")
    rec = select_route("loc_route_test", "/nonexistent-capabilities.json")
    check("absent-record-falls-back",
          rec["read_route"] == "private-firebase" and "capability" in rec["reason"])
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        path = os.path.join(td, "caps.json")
        full = {
            "tenant": "loc_route_test",
            "capabilities": {
                op: {"contract_verified": True, "adapter_built": True,
                     "offline_tests_passed": True, "read_verified": True, "enabled": True}
                for op in PUBLIC_READ_OPS
            },
        }
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(full, fh)
        rec = select_route("loc_route_test", path)
        if _public_engine_root() is None:
            check("public-package-absent-falls-back",
                  rec["read_route"] == "private-firebase" and "not importable" in rec["reason"])
            print("  [SKIP] enabled-capability-selects-public (public adapter package absent)")
        else:
            check("enabled-capability-selects-public", rec["read_route"] == "public")
            check("parity-never-promoted", rec["parity"].startswith("unverified"))
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(dict(full, tenant="some_other_tenant"), fh)
        rec = select_route("loc_route_test", path)
        check("tenant-mismatch-falls-back",
              rec["read_route"] == "private-firebase" and "tenant" in rec["reason"])
        partial = {"tenant": "loc_route_test",
                   "capabilities": {PUBLIC_READ_OPS[0]: full["capabilities"][PUBLIC_READ_OPS[0]]}}
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(partial, fh)
        rec = select_route("loc_route_test", path)
        check("one-disabled-read-op-falls-back",
              rec["read_route"] == "private-firebase" and PUBLIC_READ_OPS[1] in rec["reason"])

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
    ap.add_argument("--route", choices=("auto", "public", "private"), default="auto",
                    help="read route. auto = public status/definition adapter when its capability is "
                         "enabled for this tenant, else the bounded private Firebase fallback")
    ap.add_argument("--capabilities", default=os.environ.get(CAPABILITIES_ENV) or "",
                    help="capability record JSON (tenant + per-operation Capability fields)")
    ap.add_argument("--self-test", dest="self_test", action="store_true")
    args = ap.parse_args()
    if args.self_test:
        return self_test()
    if not args.location:
        print("FAIL: --location (or GHL_LOCATION_ID / PODCAST_ENGINE_GHL_LOCATION_ID env) is required - "
              "this script WRITES to the target sub-account", file=sys.stderr)
        return 1
    loc = args.location
    route = select_route(loc, args.capabilities, args.route)
    route["capability_path"] = args.capabilities
    have_fb = any([args.fb_account, args.fb_audience, args.fb_pixel, args.fb_token])
    will_write = bool(args.execute and have_fb)
    print(f"== FB-ads activation -- location {loc} ==")
    print(f"== ROUTE: read_primary={route['read_route']} write={route['write_route']} "
          f"parity={route['parity']} ==")
    print(f"   read reason: {route['reason']}")
    print("   write reason: the public V4 definition write is disabled (B-V4-S, staging-only) and "
          "public publish parity is unverified; the private Firebase publish rail is the bounded fallback")
    print(CHECKLIST)
    if not have_fb:
        print("No --fb-* values supplied: reporting current state only (nothing written).")

    # The private token is needed for a private read, or for the write leg (always private).
    tok = ""
    if route["read_route"] != "public" or will_write:
        names = [n.strip() for n in args.token_env.split(",") if n.strip()]
        _source_secrets(names)
        refresh = next((os.environ[n] for n in names if os.environ.get(n, "").strip()), "")
        if not refresh:
            print(f"FAIL: private Firebase rail selected but no refresh token in {names}", file=sys.stderr)
            return 1
        tok = _mint(refresh)
        if not tok:
            print("FAIL: could not mint id_token", file=sys.stderr); return 1

    rows, used = _route_rows(tok, loc, route)
    if used.startswith("public") is False and route["read_route"] == "public" and not rows:
        print(f"FAIL: {used}", file=sys.stderr)
        return 1
    print(f"== ROUTE USED: {used} ==")
    ok_all = True
    for key, sub, uses in FB_WORKFLOWS:
        match = _match_workflow(rows, sub)
        if not match:
            print(f"[MISS] {key}: no workflow matching {sub!r}"); ok_all = False; continue
        wid = match["id"]
        status_now = _status_of(match)
        if not will_write:
            print(f"[DRY ] {key} {wid} status={status_now} route={used} would_publish={have_fb}")
            continue
        # Mutation stays on the private rail: read the full workflowData, fill, publish.
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
        status_now = wf.get("status") or status_now
        body = {"name": wf.get("name"), "version": wf.get("version", 1), "status": "published",
                "meta": wf.get("meta") or {}, "workflowData": {"templates": templates},
                "triggersChanged": False, "oldTriggers": [], "newTriggers": []}
        pc, pr = _req(tok, "PUT", f"/workflow/{loc}/{wid}", body)
        _, v = _req(tok, "GET", f"/workflow/{loc}/{wid}")
        ok = pc == 200 and v.get("status") == "published"
        ok_all = ok_all and ok
        print(f"[{'PUB ' if ok else 'FAIL'}] {key} {wid} http={pc} status_now={v.get('status')} "
              f"fb_steps_filled={filled} write_route=private-firebase")
        if pc != 200:
            print("        err:", json.dumps(pr)[:200])
        time.sleep(0.5)

    print("\nNOTE: publishing a FB workflow REQUIRES its FB custom-audience/CAPI fields be non-empty"
          " (GoHighLevel validates published actions). Supply all --fb-* ids the workflow uses.")
    return 0 if ok_all else 1


if __name__ == "__main__":
    sys.exit(main())
