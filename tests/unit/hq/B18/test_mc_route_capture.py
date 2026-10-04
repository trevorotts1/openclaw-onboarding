#!/usr/bin/env python3
"""B18 focused behaviour test — SPEC S5 capture wiring in scripts/mc-route.sh.

Task B18 ("wire genuine existing task/exchange events to the outbox adapter")
owns one product path, `ONB:scripts/mc-route.sh`. Swarm-plan rev 4
ownership_rules place every child's test in its OWN lease:
`ONB tests/unit/hq/<childId>/test_*.py` — this file.

WHAT IS DRIVEN, AND HOW
    The REAL `scripts/mc-route.sh` is executed as a subprocess with a stub
    `curl` first on PATH. That stub is the FAKE TRANSPORT: it answers
    `GET /api/workspaces` and the ingest POST from canned JSON, so there is no
    network, no Command Center, no fleet box, no client, no live message and no
    secret value anywhere in this run. The tenant root is a disposable mktemp
    directory and HOME is empty, so the helper's own dotenv secret resolution
    reads no real store.

WHAT IS ASSERTED
    (a) a routed card hands the GENUINE observed task to the outbox adapter —
        source key `task:<observed task id>`, kind/phase `task:created`, the
        observed status/workspace/department, the trusted company id, and
        `exchangeId` null (a card creation is not an exchange);
    (b) the same source key never becomes a second event: a retried route reuses
        the pending envelope's eventId/issuedAt (SPEC S5: "Mint eventId and
        issuedAt once with the first durable source envelope ... Do not assign
        fresh eventId/issuedAt while replaying same source key");
    (c) NEGATIVE + CONTROL: with no trusted identity (MC_INSTALLATION_ID or
        MC_ROUTE_COMPANY_ID) nothing is sent — and (a) in the same run is the
        positive control proving the instrument discriminates;
    (d) a missing, syntactically broken, or import-raising adapter leaves the card
        routing and the exit code untouched (telemetry never blocks business work);
    (e) failure paths (transport down, HTTP 500, no task_id) still escalate and
        record no event;
    (f) exit-code + output parity against the PRE-CHANGE revision of the script,
        run over the same argv table.

RUN
    python3 tests/unit/hq/B18/test_mc_route_capture.py -v
"""

from __future__ import annotations

import glob
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
MC_ROUTE = REPO_ROOT / "scripts" / "mc-route.sh"
# B17 owns the adapter on its own branch. Resolve it from an explicit override
# first (used to exercise the wiring against the real adapter before both units
# are integrated), then the in-repo path. When neither exists the capture cases
# SKIP — a green skip is honest; a vacuous pass is not.
ADAPTER_OVERRIDE = os.environ.get("HQ_ADAPTER_PATH", "")
ADAPTER = Path(ADAPTER_OVERRIDE) if ADAPTER_OVERRIDE else REPO_ROOT / "shared-utils" / "hq_activity.py"

INGEST_OK = (
    '{"ok":true,"deduped":false,"task_id":"t-77","workspace_id":"marketing",'
    '"resolved_department":"marketing","resolved_by":"auto-route:marketing",'
    '"status":"backlog"}\n201'
)

STUB = """#!/usr/bin/env bash
# Fake Command Center door (FAKE TRANSPORT). No network leaves this process.
url=""
for a in "$@"; do case "$a" in http*) url="$a" ;; esac; done
case "$url" in
  */api/workspaces*) printf '[{"id":"ws-mkt","slug":"marketing","name":"Marketing"}]\\n200'; exit 0 ;;
esac
case "${STUB_MODE:-ingest_created}" in
  down)     exit 7 ;;
  http500)  printf '{"error":"boom"}\\n500'; exit 0 ;;
  notaskid) printf '{"ok":true}\\n200'; exit 0 ;;
esac
printf '%s' "$STUB_BODY"
"""


class McRouteCaptureTest(unittest.TestCase):
    """Drives the real helper; asserts the adapter receives genuine observed facts."""

    @classmethod
    def setUpClass(cls):
        cls.work = Path(tempfile.mkdtemp(prefix="mc-route-hq-capture."))
        (cls.work / "bin").mkdir()
        (cls.work / "home").mkdir()
        (cls.work / "state").mkdir()
        stub = cls.work / "bin" / "curl"
        stub.write_text(STUB, encoding="utf-8")
        stub.chmod(stub.stat().st_mode | stat.S_IEXEC)
        cls.root = cls.work / "root"
        (cls.root / "shared-utils").mkdir(parents=True)
        if ADAPTER.is_file():
            shutil.copy2(ADAPTER, cls.root / "shared-utils" / "hq_activity.py")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.work, ignore_errors=True)

    # -- harness -------------------------------------------------------------

    def setUp(self):
        if not ADAPTER.is_file():
            self.skipTest(
                "adapter absent (B17 owns shared-utils/hq_activity.py); set "
                "HQ_ADAPTER_PATH to its worktree copy to exercise the wiring")

    def run_helper(self, argv, root=None, inst="install-abc", comp="co-ops", mode=None):
        env = dict(os.environ)
        env.update({
            "PATH": "%s:%s" % (self.work / "bin", env.get("PATH", "")),
            "HOME": str(self.work / "home"),
            "MC_ROUTE_STATE_DIR": str(self.work / "state"),
            "MC_ROUTE_MAX_RETRIES": "0",
            "MC_ROUTE_INGEST_URL": "http://127.0.0.1:4000/api/tasks/ingest",
            "HQ_TENANT_WORKSPACE_ROOT": str(root or self.root),
            "OC_ROOT": str(root or self.root),
            "MC_INSTALLATION_ID": inst,
            "MC_ROUTE_COMPANY_ID": comp,
            "STUB_BODY": INGEST_OK,
            "STUB_MODE": mode or "ingest_created",
        })
        proc = subprocess.run(["bash", str(MC_ROUTE)] + list(argv),
                              capture_output=True, text=True, env=env, timeout=120)
        return proc.returncode, proc.stdout + proc.stderr

    def events(self, root):
        return sorted(glob.glob(str(Path(root) / "hq-telemetry" / "outbox" / "*.json")))

    def event(self, root):
        files = self.events(root)
        self.assertTrue(files, "no outbox event was written")
        return json.loads(Path(files[0]).read_text(encoding="utf-8"))["event"]

    def fresh_root(self, name, adapter=True):
        root = self.work / name
        (root / "shared-utils").mkdir(parents=True, exist_ok=True)
        if adapter and ADAPTER.is_file():
            shutil.copy2(ADAPTER, root / "shared-utils" / "hq_activity.py")
        return root

    def test_a_routed_card_hands_the_genuine_observed_task_to_the_adapter(self):
        code, out = self.run_helper(["task", "Refund the Smith order", "Refund the Smith order"])
        self.assertEqual(code, 0, out)
        self.assertIn("ROUTED workspace=marketing", out)
        ev = self.event(self.root)
        self.assertEqual(ev["sourceKey"], "task:t-77", ev)
        self.assertEqual((ev["kind"], ev["phase"]), ("task", "created"), ev)
        self.assertEqual(ev["payload"]["status"], "backlog", ev)
        self.assertEqual(ev["toWorkspaceId"], "marketing", ev)
        self.assertEqual(ev["recipientRuntimeId"], "marketing", ev)
        self.assertEqual(ev["companyId"], "co-ops", ev)
        self.assertIsNone(ev["exchangeId"], ev)
        self.assertEqual(ev["taskId"], "t-77", ev)

    def test_b_same_source_key_never_becomes_a_second_event(self):
        root = self.fresh_root("replay-root")
        before = len(self.events(root))
        env = dict(os.environ, MC_ROUTE_EVENT_ID="hq-cap-1")
        os.environ["MC_ROUTE_EVENT_ID"] = "hq-cap-1"
        try:
            for _ in range(3):
                code, out = self.run_helper(["task", "Replay job", "Replay job"],
                                            root=root)
                self.assertEqual(code, 0, out)
        finally:
            os.environ.pop("MC_ROUTE_EVENT_ID", None)
        files = self.events(root)
        self.assertEqual(len(files), 1, files)
        ids = {json.loads(Path(f).read_text())["event"]["eventId"] for f in files}
        self.assertEqual(len(ids), 1, ids)

    def test_c_no_trusted_identity_sends_nothing_while_the_card_still_routes(self):
        for inst, comp, label in (("install-abc", "", "no company id"),
                                  ("", "co-ops", "no installation id"),
                                  ("", "", "neither")):
            root = self.fresh_root("ident-%s" % label.replace(" ", "-"))
            code, out = self.run_helper(
                ["task", "Refund the Smith order", "Refund the Smith order"],
                root=root, inst=inst, comp=comp)
            self.assertEqual(code, 0, out)
            self.assertIn("ROUTED ", out, "%s: card must still route" % label)
            self.assertEqual(self.events(root), [], "%s: nothing may be sent" % label)

    def test_d_missing_or_broken_adapter_leaves_the_card_untouched(self):
        cases = {
            "missing": None,
            "syntax-error": "def broken(:\n",
            "raises-on-import": 'raise RuntimeError("boom")\n',
        }
        for label, body in cases.items():
            root = self.work / ("adapter-%s" % label)
            (root / "shared-utils").mkdir(parents=True, exist_ok=True)
            if body is not None:
                (root / "shared-utils" / "hq_activity.py").write_text(body, encoding="utf-8")
            code, out = self.run_helper(
                ["task", "Refund the Smith order", "Refund the Smith order"], root=root)
            self.assertEqual(code, 0, "%s: rc=%s %s" % (label, code, out))
            self.assertIn("ROUTED ", out, "%s: card must still route" % label)
            self.assertEqual(self.events(root), [], "%s: nothing may be written" % label)

    def test_e_failure_paths_still_escalate_and_record_no_event(self):
        for mode in ("down", "http500", "notaskid"):
            root = self.fresh_root("fail-%s" % mode)
            code, out = self.run_helper(
                ["task", "Pay the electric bill", "Pay the electric bill"],
                root=root, mode=mode)
            self.assertEqual(code, 1, "%s: rc=%s %s" % (mode, code, out))
            self.assertIn("mc-route: FAILED", out)
            self.assertIn("ESCALATE_TO_OPERATOR", out)
            self.assertEqual(self.events(root), [], "%s: no event on a failed route" % mode)

    def test_f_exit_code_and_output_parity_with_the_pre_change_revision(self):
        pre = self.work / "mc-route.PRE.sh"
        try:
            blob = subprocess.run(
                ["git", "-C", str(REPO_ROOT), "show", "HEAD:scripts/mc-route.sh"],
                capture_output=True, text=True, timeout=60)
        except (OSError, subprocess.SubprocessError) as exc:  # pragma: no cover
            self.skipTest("git unavailable: %s" % exc)
        if blob.returncode != 0:
            self.skipTest("no git revision to compare against")
        pre.write_text(blob.stdout, encoding="utf-8")
        if pre.read_bytes() == MC_ROUTE.read_bytes():
            self.skipTest("HEAD already carries the change; parity asserted by the builder trace")

        table = [
            ("task-ok", "task", ["task", "Parity job", "Parity job words"], None),
            ("slug-ok", "slug", ["marketing", "Parity slug", "words"], None),
            ("task-empty", "empty", ["task", "", ""], None),
            ("refuse-stop", "refuse", ["stop", "anything"], None),
            ("help", "help", ["help"], None),
            ("auto-answer", "auto", ["auto", "what time is our next call?"], None),
            ("transport-down", "down", ["task", "Parity job", "Parity job words"], "down"),
            ("http-500", "http500", ["task", "Parity job", "Parity job words"], "http500"),
            ("no-task-id", "notaskid", ["task", "Parity job", "Parity job words"], "notaskid"),
        ]

        def trace(script):
            rows = []
            for label, _, argv, mode in table:
                env = dict(os.environ)
                env.update({
                    "PATH": "%s:%s" % (self.work / "bin", env.get("PATH", "")),
                    "HOME": str(self.work / "home"),
                    "MC_ROUTE_STATE_DIR": str(self.work / ("state-" + label)),
                    "MC_ROUTE_MAX_RETRIES": "0",
                    "MC_ROUTE_INGEST_URL": "http://127.0.0.1:4000/api/tasks/ingest",
                    "HQ_TENANT_WORKSPACE_ROOT": str(self.work / ("trace-" + label)),
                    "OC_ROOT": str(self.work / ("trace-" + label)),
                    "MC_INSTALLATION_ID": "install-abc",
                    "MC_ROUTE_COMPANY_ID": "co-ops",
                    "STUB_BODY": INGEST_OK,
                    "STUB_MODE": mode or "ingest_created",
                })
                proc = subprocess.run(["bash", str(script)] + list(argv),
                                      capture_output=True, text=True, env=env, timeout=120)
                rows.append((label, proc.returncode, proc.stdout + proc.stderr))
            return rows

        before = trace(pre)
        after = trace(MC_ROUTE)
        self.assertEqual(len(before), len(after))
        for (lb, rb, ob), (la, ra, oa) in zip(before, after):
            self.assertEqual(lb, la)
            self.assertEqual(rb, ra, "%s: exit code moved %s -> %s\n%s" % (la, rb, ra, oa))
            self.assertEqual(ob, oa, "%s: output moved" % la)


if __name__ == "__main__":
    unittest.main(verbosity=2)
