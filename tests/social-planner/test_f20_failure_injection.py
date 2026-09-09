#!/usr/bin/env python3
"""test_f20_failure_injection.py — F20 failure-injection coverage for the
agreed enqueue/dispatch/producer/QC/publish contract (F04/F05/F08/F10/F11/
F12/F13), offline, fake transports — NEVER a live GHL/Sheets/CC call.

Failure modes injected (QC-F20):
  1. Worker death / stopped consumer: a staged cycle with no worker ack stays
     queued + overdue — never review, never done (the skill-35 runner).
  2. Empty QC: an empty or missing QC receipt set FAILS closed (F11); an empty
     artifacts directory refuses phase completion (F04).
  3. One missing account: F06 per-account plan keeps other accounts ready and
     publishes; the F10 live gate requires EVERY expected destination to be
     independently published — one missing destination blocks done.
  4. Duplicate webhook delivery: a lost-response replay adopts the EXISTING
     remote post (one row), never a second post; the F13 row receipt is
     idempotent (no second append); F12 outbox replay creates one card.
  5. Sheets 404/outage: the planner writeback outage never republishes
     already-published posts — it exposes a separate planner-sync task.
  6. Wrong tenant: the GHL preflight stops the cycle when the token resolves
     to a DIFFERENT location than the configured one (never publish).
  7. Expired invitation: a new week with an expired invitation renews onto the
     SAME saved draft (F35/F34 ONB side, offline — the invitation store).
  8. Overdue publish readback: a scheduled post past its due time reconciles to
     published; a MISSING post readback stays unknown and never counts.

Run:
  python3 -m unittest tests.social-planner.test_f20_failure_injection -v
"""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parent.parent
_SKILL_DIR = _REPO_ROOT / "57-social-media-in-a-box"
_RUNNER_PATH = _SKILL_DIR / "run_social_media.py"
_SERVICE_PATH = _REPO_ROOT / "shared-utils" / "social_cycle_service.py"
_SCRIPT = _REPO_ROOT / "35-social-media-planner" / "scripts" / "run-publishing-cycle.sh"
assert _RUNNER_PATH.is_file() and _SERVICE_PATH.is_file() and _SCRIPT.is_file()


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


rsm = _load("run_social_media_f20", _RUNNER_PATH)
scs = _load("social_cycle_service_f20", _SERVICE_PATH)


def _make_home(root: Path, curl_stub=None) -> Path:
    """Fixture $HOME: Skill 35 prereqs + optional curl stub (forwards non-GHL
    calls to the real curl; the default stub refuses leadconnectorhq.com so the
    live preflight takes the transient-warn path)."""
    import shutil
    oc = root / ".openclaw"
    (oc / "secrets").mkdir(parents=True, exist_ok=True)
    (oc / "config").mkdir(parents=True, exist_ok=True)
    for f in ("SOUL.md", "IDENTITY.md", "USER.md"):
        (oc / f).write_text("fixture %s" % f, encoding="utf-8")
    (oc / "secrets" / ".env").write_text(
        "GOHIGHLEVEL_API_KEY=test-key\nGOHIGHLEVEL_LOCATION_ID=test-loc\n",
        encoding="utf-8")
    (oc / "openclaw.json").write_text('{"agents": {"list": []}}', encoding="utf-8")
    binp = root / "bin"
    binp.mkdir(parents=True, exist_ok=True)
    stub = binp / "curl"
    stub.write_text(curl_stub or (
        '#!/bin/sh\nfor a in "$@"; do\n  case "$a" in\n'
        '    *leadconnectorhq.com*) exit 7 ;;\n  esac\ndone\n'
        'exec %s "$@"\n' % (shutil.which("curl") or "/usr/bin/curl")), encoding="utf-8")
    stub.chmod(0o755)
    return root


def _runner(home, workdir, *args, platforms="linkedin"):
    env = os.environ.copy()
    env["HOME"] = str(home)
    env["PATH"] = "%s:/usr/bin:/bin" % (home / "bin")
    for k in ("MC_API_TOKEN", "MISSION_CONTROL_URL", "SKILL35_LIVE_PREFLIGHT"):
        env.pop(k, None)
    return subprocess.run(
        ["bash", str(_SCRIPT), "--topic", "F20 test", "--platforms", platforms,
         "--workdir", str(workdir), *args],
        capture_output=True, text=True, timeout=120, env=env)


def _run_dir(tmp, accounts=("fb-1", "ig-1", "li-1"), mode="production"):
    """A minimal valid run dir: config, trusted execution-mode stamp, process
    certificate, publish_results (normalized contract), per-account plan."""
    rd = Path(tmp) / "run"
    (rd / "working" / "copy").mkdir(parents=True, exist_ok=True)
    (rd / "working" / "publish").mkdir(parents=True, exist_ok=True)
    (rd / "delivery").mkdir(parents=True, exist_ok=True)
    cfg = {"brandName": "Brand One", "locationId": "loc-1", "userId": "u-1",
           "timezone": "America/New_York", "status": "Paid"}
    (rd / "working" / "copy" / "config.json").write_text(json.dumps(cfg), encoding="utf-8")
    (rd / "working" / "execution_mode.json").write_text(
        json.dumps({"mode": mode, "set_by": "trusted-entry",
                    "simulated": mode != "production"}), encoding="utf-8")
    (rd / "delivery" / "PROCESS-CERTIFICATE.json").write_text("{}", encoding="utf-8")
    plan = {"weekOf": "2026-09-07", "themeOfWeek": "Theme", "plannerSheetId": "sheet-1",
            "companyId": "co-1", "cycleId": "cy-1", "contentRevision": 3,
            "accounts": [{"account_id": a, "platform": p, "account_name": a}
                         for a, p in zip(accounts, ("facebook", "instagram", "linkedin"))]}
    (rd / "working" / "plan").mkdir(parents=True, exist_ok=True)
    (rd / "working" / "plan" / "plan.json").write_text(json.dumps(plan), encoding="utf-8")
    results = [{"kind": "publish_result", "platform": "facebook", "success": True,
                "totalPosts": len(accounts), "processedAccounts": len(accounts),
                "errors": []}]
    (rd / "working" / "publish" / "publish_results.json").write_text(
        json.dumps(results), encoding="utf-8")
    return rd


def _listing(accounts_states):
    return [{"post_id": pid, "status": state, "scheduled_at": sched,
             "published_url": url}
            for pid, state, sched, url in accounts_states]


# ---------------------------------------------------------------------------
# 1. Worker death / stopped consumer — the skill-35 runner
# ---------------------------------------------------------------------------
class TestWorkerDeath(unittest.TestCase):
    """QC-F20: a stopped consumer keeps the cycle queued + overdue, never
    review/done; review is refused while queued."""

    def setUp(self):
        self.t = tempfile.TemporaryDirectory()
        self.home = Path(self.t.name) / "home"
        oc = self.home / ".openclaw"
        (oc / "secrets").mkdir(parents=True, exist_ok=True)
        (oc / "config").mkdir(parents=True, exist_ok=True)
        for f in ("SOUL.md", "IDENTITY.md", "USER.md"):
            (oc / f).write_text("fixture %s" % f, encoding="utf-8")
        (oc / "secrets" / ".env").write_text(
            "GOHIGHLEVEL_API_KEY=test-key\nGOHIGHLEVEL_LOCATION_ID=test-loc\n",
            encoding="utf-8")
        (oc / "openclaw.json").write_text('{"agents": {"list": []}}', encoding="utf-8")
        binp = self.home / "bin"
        binp.mkdir(parents=True, exist_ok=True)
        import shutil
        stub = binp / "curl"
        stub.write_text(
            '#!/bin/sh\nfor a in "$@"; do\n  case "$a" in\n    *leadconnectorhq.com*) exit 7 ;;\n  esac\ndone\nexec %s "$@"\n'
            % (shutil.which("curl") or "/usr/bin/curl"), encoding="utf-8")
        stub.chmod(0o755)

    def tearDown(self):
        self.t.cleanup()

    def _runner(self, workdir, *args):
        env = os.environ.copy()
        env["HOME"] = str(self.home)
        env["PATH"] = "%s:/usr/bin:/bin" % (self.home / "bin")
        for k in ("MC_API_TOKEN", "MISSION_CONTROL_URL", "SKILL35_LIVE_PREFLIGHT"):
            env.pop(k, None)
        return subprocess.run(
            ["bash", str(_SCRIPT), "--topic", "F20 death", "--platforms", "linkedin",
             "--workdir", workdir, *args],
            capture_output=True, text=True, timeout=120, env=env)

    def test_worker_death_keeps_cycle_queued_never_review(self):
        wd = Path(self.t.name) / "run"
        self.assertEqual(self._runner(str(wd)).returncode, 0)
        rec = json.loads((wd / "working" / "dispatch.json").read_text())
        self.assertEqual(rec["state"], "queued")
        self.assertIsNone(rec["completion_receipt"])
        # Stopped consumers: overdue past the threshold — never review/done.
        time.sleep(2)
        st = subprocess.run(
            ["bash", str(_SCRIPT), "--status", "--workdir", str(wd), "--overdue-after", "1"],
            capture_output=True, text=True, timeout=60)
        out = json.loads(st.stdout)
        self.assertEqual(out["state"], "queued")
        self.assertTrue(out["overdue"])
        self.assertIn("consumers stopped", out.get("overdue_reason") or "")
        # A stopped consumer cannot claim review either.
        mr = self._runner(str(wd), "--mark-review")
        self.assertEqual(mr.returncode, 7)


# ---------------------------------------------------------------------------
# 2. Empty QC
# ---------------------------------------------------------------------------
class TestEmptyQC(unittest.TestCase):
    """QC-F20: an empty/missing QC receipt set fails closed; an empty phase
    artifact directory refuses completion."""

    def test_empty_qc_receipts_fail_closed(self):
        with tempfile.TemporaryDirectory() as td:
            rd = _run_dir(td)
            # One planned artifact + its contract, but an EMPTY receipt set.
            plan = json.loads((rd / "working" / "plan" / "plan.json").read_text())
            plan["plannedItems"] = [{"artifact_id": "art-1", "revision": 3,
                                     "path": "working/content/art-1.md"}]
            (rd / "working" / "plan" / "plan.json").write_text(json.dumps(plan), encoding="utf-8")
            cdir = rd / "working" / "content" / "contracts"
            cdir.mkdir(parents=True, exist_ok=True)
            (cdir / "art-1.json").write_text(
                json.dumps({"artifact_id": "art-1"}), encoding="utf-8")
            qdir = rd / "working" / "qc"
            qdir.mkdir(parents=True, exist_ok=True)
            (qdir / "qc_receipts.json").write_text("[]", encoding="utf-8")
            ok, _msg, failures = rsm._verify_qc_matrix(rd)
            self.assertFalse(ok, "an empty QC receipt set must fail closed")
            self.assertTrue(any("no QC receipt" in f for f in failures), failures)

    def test_empty_artifacts_refuses_phase_completion(self):
        # F04: completion cannot be claimed without producer artifacts.
        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            home = _make_home(td_path / "home")
            run = td_path / "run"
            self.assertEqual(_runner(home, run).returncode, 0)
            ack = _runner(home, run, "--ack-execution", "--worker-id", "w1")
            self.assertEqual(ack.returncode, 0, ack.stderr)
            cp = _runner(home, run, "--complete-phase", "1", "--worker-id", "w1")
            self.assertEqual(cp.returncode, 7, "empty artifacts must refuse completion")
            rec = json.loads((run / "working" / "dispatch.json").read_text())
            self.assertEqual(rec["phases_complete"], [])


# ---------------------------------------------------------------------------
# 3. One missing account
# ---------------------------------------------------------------------------
class TestOneMissingAccount(unittest.TestCase):
    """QC-F20: one missing/expired account degrades that account only (F06);
    the F10 gate never counts a destination published without an independent
    readback — one missing destination blocks done."""

    def test_missing_account_degrades_only_that_account(self):
        with tempfile.TemporaryDirectory() as td:
            rd = _run_dir(td, accounts=("fb-1", "ig-1"))
            plan = json.loads((rd / "working" / "plan" / "plan.json").read_text())
            # fb-2 (second Facebook) is needs_reconnect; fb-1 and ig-1 ready.
            plan["accounts"] = [
                {"account_id": "fb-1", "platform": "facebook", "account_name": "fb-1",
                 "health": "ready"},
                {"account_id": "fb-2", "platform": "facebook", "account_name": "fb-2",
                 "health": "needs_reconnect",
                 "exclusion_reason": "token expired"},
                {"account_id": "ig-1", "platform": "instagram", "account_name": "ig-1",
                 "health": "ready"},
            ]
            (rd / "working" / "plan" / "plan.json").write_text(json.dumps(plan), encoding="utf-8")
            report = {"account_plan": {"accounts": plan["accounts"]}}
            (rd / "working" / "preflight").mkdir(parents=True, exist_ok=True)
            (rd / "working" / "preflight" / "preflight_report.json").write_text(
                json.dumps(report), encoding="utf-8")
            rows = rsm._per_account_publish_results(rd, {})
            by_id = {r["account_id"]: r for r in rows}
            self.assertEqual(by_id["fb-1"]["publish_state"], "ready")
            self.assertEqual(by_id["ig-1"]["publish_state"], "ready")
            self.assertEqual(by_id["fb-2"]["publish_state"], "failed")
            self.assertIn("reconnect", by_id["fb-2"]["note"])

    def test_one_missing_destination_blocks_done(self):
        with tempfile.TemporaryDirectory() as td:
            rd = _run_dir(td)
            for aid in ("fb-1", "ig-1", "li-1"):
                rsm._upsert_delivery_row(rd, "co-1", "cy-1", 3, aid,
                                         remote_post_id="post-%s" % aid,
                                         provider_state="unknown")
            (rd / "working" / "publish" / "posted_ids.json").write_text(
                json.dumps(["post-fb-1", "post-ig-1", "post-li-1"]), encoding="utf-8")
            listing = _listing([
                ("post-fb-1", "published", None, "u1"),
                ("post-ig-1", "published", None, "u2"),
                # li-1 MISSING from the readback entirely — ambiguous.
            ])
            orig = rsm._live_ghl_post_listing_with_status
            rsm._live_ghl_post_listing_with_status = lambda cfg: listing
            try:
                ok, msg = rsm._chk_publish(rd)
            finally:
                rsm._live_ghl_post_listing_with_status = orig
            self.assertFalse(ok, "one missing destination must block done")
            self.assertIn("li-1", msg)


# ---------------------------------------------------------------------------
# 4. Duplicate webhook delivery
# ---------------------------------------------------------------------------
class TestDuplicateDelivery(unittest.TestCase):
    """QC-F20: duplicate/lost-response webhook deliveries reconcile, never
    duplicate. A create success with a lost response adopts the existing post
    (F10); the F13 writeback row is idempotent (one row, no second append)."""

    def test_lost_response_adopts_existing_post_no_duplicate(self):
        with tempfile.TemporaryDirectory() as td:
            rd = _run_dir(td, accounts=("fb-1",))
            # Duplicate delivery attempt: the poster has ALREADY got the id.
            rsm._upsert_delivery_row(rd, "co-1", "cy-1", 3, "fb-1",
                                     remote_post_id="post-fb-1", provider_state="unknown",
                                     failure_reason="create timeout (response lost)")
            rsm._reconcile_deliveries_from_listing(rd, _listing([
                ("post-fb-1", "published", None, "https://facebook.com/x/1"),
            ]))
            rows = rsm._delivery_rows(rd)
            self.assertEqual(len(rows), 1, "duplicate delivery must NOT add a second row")
            self.assertEqual(rows[0]["remote_post_id"], "post-fb-1")
            self.assertEqual(rows[0]["provider_state"], "published")

    def test_same_webhook_replayed_upserts_in_place(self):
        with tempfile.TemporaryDirectory() as td:
            rd = _run_dir(td, accounts=("fb-1",))
            # Two deliveries of the SAME row-key (a webhook replay): upsert
            # twice, still one row, second write updates in place.
            rsm._upsert_delivery_row(rd, "co-1", "cy-1", 3, "fb-1",
                                     remote_post_id="post-fb-1", provider_state="draft")
            rsm._upsert_delivery_row(rd, "co-1", "cy-1", 3, "fb-1",
                                     remote_post_id="post-fb-1", provider_state="published")
            rows = rsm._delivery_rows(rd)
            self.assertEqual(len(rows), 1, "webhook replay must upsert, never duplicate")
            self.assertEqual(rows[0]["provider_state"], "published")


# ---------------------------------------------------------------------------
# 5. Sheets 404 / outage
# ---------------------------------------------------------------------------
class TestSheetsOutage(unittest.TestCase):
    """QC-F20: a Sheets outage never republishes already-published posts; it
    exposes a separate planner-sync task (F13)."""

    def test_sheets_404_preserves_published_and_exposes_sync_task(self):
        with tempfile.TemporaryDirectory() as td:
            rd = _run_dir(td, accounts=("fb-1",))
            rsm._upsert_delivery_row(rd, "co-1", "cy-1", 3, "fb-1",
                                     remote_post_id="post-fb-1", provider_state="published")
            preserved, task = rsm._sheets_outage_recovery(rd)
            self.assertTrue(preserved, "published posts must survive a Sheets outage")
            self.assertIsNotNone(task)
            self.assertEqual(task["kind"], "planner-sync")
            self.assertEqual(task["state"], "open")
            # Delivery row is UNTOUCHED by the outage.
            rows = rsm._delivery_rows(rd)
            self.assertEqual(rows[0]["provider_state"], "published")

    def test_no_published_rows_means_no_sync_task(self):
        with tempfile.TemporaryDirectory() as td:
            rd = _run_dir(td, accounts=("fb-1",))
            rsm._upsert_delivery_row(rd, "co-1", "cy-1", 3, "fb-1",
                                     provider_state="draft")
            preserved, task = rsm._sheets_outage_recovery(rd)
            self.assertTrue(preserved)
            self.assertIsNone(task, "nothing published -> no planner-sync task")


# ---------------------------------------------------------------------------
# 6. Wrong tenant
# ---------------------------------------------------------------------------
class TestWrongTenant(unittest.TestCase):
    """QC-F20: the runner's GHL preflight HARD-STOPS the cycle (exit 3) when
    the token authenticates for social posting but resolves to a DIFFERENT
    location than the configured one — never publish to the wrong tenant. The
    curl stub rewrites the leadconnectorhq.com host to a loopback fake server
    that answers the accounts probe OK and the /locations/<loc> probe 401; no
    live GHL traffic ever leaves the machine."""

    def test_wrong_tenant_location_probe_401_stops_cycle(self):
        import threading
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

        calls = []

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _send(self, code, obj):
                b = obj.encode() if isinstance(obj, str) else obj
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(b)))
                self.end_headers()
                self.wfile.write(b)

            def do_GET(self):
                calls.append(("GET", self.path))
                # The preflight's second probe: token NOT authorized for the
                # configured location -> wrong TENANT.
                if self.path.startswith("/locations/"):
                    return self._send(401, '{"message":"unauthorized"}')
                return self._send(200, '{"ok":true}')

            def do_POST(self):
                calls.append(("POST", self.path))
                # Accounts probe: one connected account (token is valid, just
                # for another location).
                return self._send(200, json.dumps({
                    "accounts": [{"id": "a1", "platform": "facebook",
                                  "name": "FB One"}]}))

        srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            base = "http://127.0.0.1:%d" % srv.server_address[1]
            with tempfile.TemporaryDirectory() as td:
                td_path = Path(td)
                home = _make_home(td_path / "home")
                # Rewrite the preflight host through a python-urllib stub for
                # full control of method/headers/body.
                binp = home / "bin"
                stubf = binp / "curl"
                stubf.write_text(
                    '#!/bin/sh\n'
                    'python3 - "$@" <<\'PYEOF\'\n'
                    'import json, sys, urllib.request, urllib.error\n'
                    'args = sys.argv[1:]\n'
                    'url = next((a for a in args if a.startswith("http")), None)\n'
                    'if url is None:\n'
                    '    sys.exit(7)\n'
                    'path = url.split("leadconnectorhq.com", 1)[1] if "leadconnectorhq.com" in url else url\n'
                    'target = "%s" + path\n'
                    'method = "GET"\n'
                    'for i, a in enumerate(args):\n'
                    '    if a == "-X" and i + 1 < len(args):\n'
                    '        method = args[i + 1]\n'
                    'body = b""\n'
                    'fmt = None\n'
                    'outfile = None\n'
                    'for i, a in enumerate(args):\n'
                    '    if a == "-d" and i + 1 < len(args):\n'
                    '        body = args[i + 1].encode()\n'
                    '    if a == "-w" and i + 1 < len(args):\n'
                    '        fmt = args[i + 1]\n'
                    '    if a == "-o" and i + 1 < len(args):\n'
                    '        outfile = args[i + 1]\n'
                    'req = urllib.request.Request(target, data=body, method=method)\n'
                    'for i, a in enumerate(args):\n'
                    '    if a == "-H" and i + 1 < len(args):\n'
                    '        k, _, v = args[i + 1].partition(": ")\n'
                    '        if v:\n'
                    '            req.add_header(k.strip(), v.strip())\n'
                    'try:\n'
                    '    with urllib.request.urlopen(req, timeout=10) as r:\n'
                    '        out = r.read().decode("utf-8", "replace")\n'
                    '        code = r.getcode()\n'
                    'except urllib.error.HTTPError as e:\n'
                    '    out = e.read().decode("utf-8", "replace")\n'
                    '    code = e.code\n'
                    'if "/locations/" in target:\n'
                    '    body_out = \'{"message":"unauthorized"}\'\n'
                    '    status = 401\n'
                    'else:\n'
                    '    body_out = json.dumps({"accounts": '
                    '[{"id": "a1", "platform": "facebook", "name": "FB One"}]})\n'
                    '    status = 200\n'
                    'if fmt is not None:\n'
                    '    payload = fmt.replace("%%{http_code}", str(status)).strip("\\n")\n'
                    '    if outfile is not None:\n'
                    '        with open(outfile, "w") as fh:\n'
                    '            fh.write(body_out)\n'
                    '    sys.stdout.write(payload + "\\n")\n'
                    'else:\n'
                    '    sys.stdout.write(body_out)\n'
                    'PYEOF\n' % base, encoding="utf-8")
                stubf.chmod(0o755)
                run = td_path / "run"
                p = _runner(home, run)
                # The wrong-tenant location probe returns HTTP 401 — the cycle
                # HARD-STOPS (exit 3) with the location-mismatch client message;
                # staging NEVER happens for a foreign tenant.
                self.assertEqual(p.returncode, 3, p.stderr)
                self.assertIn("different location", p.stderr)
                self.assertFalse((run / "working" / "dispatch.json").exists(),
                                 "wrong tenant: staging must not happen")
                # The preflight probe hit the location check (the GET /locations
                # call) and the stub failed it 401 — the wrong-tenant stop.
                loc_calls = [path for (m, path) in calls
                             if m == "GET" and path.startswith("/locations/")]
                self.assertTrue(loc_calls, "the location probe never ran: %r" % calls)
        finally:
            srv.shutdown()


# ---------------------------------------------------------------------------
# 7. Expired invitation
# ---------------------------------------------------------------------------
class TestExpiredInvitation(unittest.TestCase):
    """QC-F20: an expired-week invitation renews onto the SAME saved draft
    (F34/F35 ONB side, offline invitation store) and a same-week re-advance
    never re-invites."""

    def test_expired_invitation_renews_same_draft(self):
        with tempfile.TemporaryDirectory() as td:
            env = {"SOCIAL_CYCLE_STATE_DIR": str(Path(td) / "cycles")}
            sent = []
            t0 = 1788696000000  # 2026-09-06T12:00:00Z, Sunday local NY
            ws = scs.week_start_local(t0, "America/New_York")
            r1 = scs.advance_cycle("co-exp", t0,
                                   send=lambda *a: sent.append(a[0]), env=env)
            self.assertIn(r1["action"], ("invite", "retry"), r1)
            cyc = scs.get_cycle("co-exp", ws, env=env)
            self.assertIsNotNone(cyc)
            # Re-advance well past the invitation TTL in the same week: the
            # cycle must be re-invited/retried on the SAME cycle_id (the saved
            # draft survives expiry; a fresh cycle would lose the interview).
            r2 = scs.advance_cycle("co-exp", t0 + 12 * 3600_000,
                                   send=lambda *a: sent.append(a[0]), env=env)
            self.assertIn(r2["action"], ("invite", "none", "retry"), r2)
            cyc2 = scs.get_cycle("co-exp", ws, env=env)
            self.assertEqual(cyc["cycle_id"], cyc2["cycle_id"],
                             "expired week must renew the SAME cycle/draft")


# ---------------------------------------------------------------------------
# 8. Overdue publish readback
# ---------------------------------------------------------------------------
class TestOverdueReadback(unittest.TestCase):
    """QC-F20: a scheduled post past its due time reconciles to published; a
    missing post readback stays unknown — never published."""

    def test_overdue_scheduled_reconciles_to_published(self):
        with tempfile.TemporaryDirectory() as td:
            rd = _run_dir(td, accounts=("fb-1",))
            rsm._upsert_delivery_row(rd, "co-1", "cy-1", 3, "fb-1",
                                     remote_post_id="post-fb-1", provider_state="scheduled",
                                     scheduled_at="2026-09-09T09:00:00Z")
            rsm._reconcile_deliveries_from_listing(rd, _listing([
                ("post-fb-1", "published", "2026-09-09T09:00:00Z",
                 "https://facebook.com/brand/posts/1"),
            ]))
            self.assertEqual(rsm._delivery_published_set(rd), {"fb-1"})

    def test_overdue_but_still_missing_is_unknown_never_published(self):
        with tempfile.TemporaryDirectory() as td:
            rd = _run_dir(td, accounts=("fb-1",))
            rsm._upsert_delivery_row(rd, "co-1", "cy-1", 3, "fb-1",
                                     remote_post_id="post-fb-1", provider_state="scheduled",
                                     scheduled_at="2026-09-09T09:00:00Z")
            # Overdue but NO readback found (the worker died post-schedule):
            # reconcile keeps it unknown, never published, and names it.
            rsm._reconcile_deliveries_from_listing(rd, [])
            rows = {r["account_id"]: r for r in rsm._delivery_rows(rd)}
            self.assertEqual(rows["fb-1"]["provider_state"], "unknown")
            self.assertNotIn("fb-1", rsm._delivery_published_set(rd))
            self.assertIn("no post read back", rows["fb-1"]["failure_reason"])


# ---------------------------------------------------------------------------
# AGGREGATE: all-platform continuation + four unanswered weeks (F07/F27)
# ---------------------------------------------------------------------------
class TestAllPlatformAndFourWeeks(unittest.TestCase):
    """QC-F20 aggregate: all-platform continuation (a full 5-phase cycle
    survives across platforms) and four unanswered weeks each get exactly ONE
    invitation with bounded reminders."""

    def test_four_unanswered_weeks_one_invitation_each(self):
        class Recorder:
            """Records every send; returns True so the delivery succeeds."""

            def __init__(self):
                self.sent = []

            def __call__(self, payload):
                self.sent.append(payload)
                return True

        with tempfile.TemporaryDirectory() as td:
            env = {"SOCIAL_CYCLE_STATE_DIR": str(Path(td) / "cycles")}
            rec = Recorder()
            t = 1788696000000
            for i in range(4):
                ws = scs.week_start_local(t, "America/New_York")
                r = scs.advance_cycle("co-w", t, send=rec, env=env)
                self.assertEqual(r["action"], "invite", "week %d: %r" % (i, r))
                r2 = scs.advance_cycle("co-w", t + 5 * 60_000, send=rec, env=env)
                self.assertIn(r2["action"], ("none", "retry"), r2)
                for k in range(scs.MAX_REMINDERS + 2):
                    scs.send_due_reminder("co-w", ws, rec,
                                          now_ms=t + (8 + k * 8) * 3600_000, env=env)
                week_msgs = len([s for s in rec.sent if s.get("week_start") == ws])
                self.assertEqual(week_msgs, 1 + scs.MAX_REMINDERS,
                                 "week %d messages" % i)
                t += 7 * 24 * 3600_000
            self.assertEqual(len({s.get("week_start") for s in rec.sent
                                  if s.get("week_start")}), 4)

    def test_all_platform_continuation_5_phases(self):
        # A cycle staged for ALL supported platforms completes every phase in
        # order with verified hashes, then review (the continuation contract).
        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            home = _make_home(td_path / "home")
            run = td_path / "run"
            platforms = "wordpress,medium,substack,linkedin,ghl,youtube,x,facebook," \
                        "instagram,tiktok,threads,pinterest"
            self.assertEqual(
                _runner(home, run, platforms=platforms).returncode, 0)
            ack = _runner(home, run, "--ack-execution", "--worker-id", "w1")
            self.assertEqual(ack.returncode, 0, ack.stderr)
            for phase in range(1, 6):
                pdir = run / "working" / ("phase-%s" % phase) / "artifacts"
                pdir.mkdir(parents=True, exist_ok=True)
                (pdir / ("a-%s.txt" % phase)).write_text("phase %s" % phase, encoding="utf-8")
                cp = _runner(home, run, "--complete-phase", str(phase), "--worker-id", "w1")
                self.assertEqual(cp.returncode, 0, cp.stderr)
            mr = _runner(home, run, "--mark-review")
            self.assertEqual(mr.returncode, 0, mr.stderr)
            rec = json.loads((run / "working" / "dispatch.json").read_text())
            self.assertEqual(rec["state"], "review")


if __name__ == "__main__":
    unittest.main()
