#!/usr/bin/env python3
"""
fleet_validation_harness.py — POST-FAN-OUT VALIDATION, PER BOX (FLEET-FIX 4b / AUD-58).

Runs the five mandatory post-roll checks against every box in a wave and writes
the verdict into that box's persistent ledger row (`/tmp/<sweep>/<box>.json`,
see fleet_ledger.py).  It is the HARD GATE in front of the ONE batched fleet
roll: a wave is only green when EVERY box is green, and green is only ever
written from an explicit, parsed, positive probe result.

THE FIVE CHECKS (all five are REQUIRED — none is optional, none can be skipped)
------------------------------------------------------------------------------
  1. mc_api_token_store   MC_API_TOKEN store is REACHABLE on the box.
                          Runs the repo's own authoritative credential checker
                          (`shared-utils/check-credential.sh MC_API_TOKEN --json`)
                          and requires where_found != [] AND live_env_checked.
                          NOTE the exit-code trap: that script exits 3 for
                          NEEDS_BLOCK, which is a PERFECTLY HEALTHY verdict for
                          MC_API_TOKEN (it is not a model-provider key, so no
                          models.providers block will ever reference it).  We
                          judge the VERDICT, not the exit code.  The token VALUE
                          is never requested, never parsed and never written.
  2. writeback_probe      The Command Center write-back endpoint answers 2xx
                          (authorized) or 401 (reachable + enforcing auth).
                          ANYTHING else — 000/403/404/5xx/502/timeout — is a
                          FAIL: it means the box cannot write its work back.
  3. browser_probe        The agent-browser preflight passes on the box
                          (41-build-with-ai-playbook/scripts/06-verify-agent-browser.sh,
                          rc 0 + a PASS marker in its output).
  4. openclaw_ceiling     `openclaw --version` >= the declared minimum AND the
                          runRetries CEILING ROW is present in the box's config
                          and within the declared ceiling.  An ABSENT runRetries
                          row is a FAIL, not a default — that is the whole point
                          of the row (FLEET-FIX Area 3).
  5. repo_stamp           The onboarding checkout on the box reports the EXPECTED
                          version + commit sha.  This is the stale-checkout /
                          DOWNGRADE detector: `update-skills.sh` piped from a
                          stale clone silently rolls a box BACKWARDS, and the
                          only way to catch it is to demand the stamp.

FAIL-LOUD CONTRACT (why this is not a report, it is a gate)
-----------------------------------------------------------
  • Every check is FAIL-CLOSED.  Unparseable output, an empty response, a
    probe that never ran, an ssh that timed out, an expectation the operator
    never declared — every one of those is FAIL or UNKNOWN.  None of them is
    PASS.  There is no code path that turns "I don't know" into green.
  • Expectations must be DECLARED.  You cannot validate a repo stamp you never
    named.  Missing expectations abort the sweep (exit 4) BEFORE any box is
    touched — the harness refuses to run a gate it cannot fail.
  • Per-box isolation.  One box exploding never aborts the wave and never
    contaminates another box's row.
  • The wave cap (<= 20 boxes) is enforced here, not remembered.

BACKENDS
--------
  ssh    (default, LIVE)  probes run on the box over ssh — OPERATOR-LIVE
  local                   probes run on THIS box (operator-box canary)
  sim                     probes are served from a fixture file.  This is what
                          the test suite drives: a full 20-box fan-out with a
                          deliberately-broken box, entirely hermetic.

USAGE
-----
  python3 fleet_validation_harness.py \
      --sweep-id roll-v19-44-0 --boxes-file boxes.json \
      --expectations expectations.json --backend ssh --max-parallel 8

EXIT CODES
----------
  0  every box PASS
  2  at least one box FAIL          <- LOUD
  3  at least one box UNKNOWN       <- LOUD (UNKNOWN is never green)
  4  sweep refused (undeclared expectations / wave cap exceeded / bad manifest)
  1  fatal

AUD-58 / FLEET-FIX 4b.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))

import fleet_ledger as L  # noqa: E402

RED = "\033[0;31m"
YELLOW = "\033[1;33m"
GREEN = "\033[0;32m"
CYAN = "\033[0;36m"
BOLD = "\033[1m"
NC = "\033[0m"


def _out(msg: str = "") -> None:
    print(msg, file=sys.stdout, flush=True)


def _err(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


# ── the five required checks ──────────────────────────────────────────────────

CHECK_TOKEN = "mc_api_token_store"
CHECK_WRITEBACK = "writeback_probe"
CHECK_BROWSER = "browser_probe"
CHECK_CEILING = "openclaw_ceiling"
CHECK_STAMP = "repo_stamp"

REQUIRED_CHECKS: Tuple[str, ...] = (
    CHECK_TOKEN,
    CHECK_WRITEBACK,
    CHECK_BROWSER,
    CHECK_CEILING,
    CHECK_STAMP,
)

# Doctrine: never more than 20 boxes in a wave.
DEFAULT_WAVE_CAP = 20

# Expectations the operator MUST declare.  Each maps to the check it gates.
REQUIRED_EXPECTATIONS = {
    "writeback_url": CHECK_WRITEBACK,
    "openclaw_min_version": CHECK_CEILING,
    "run_retries_max": CHECK_CEILING,
    "repo_version": CHECK_STAMP,
    "repo_sha": CHECK_STAMP,
}


# ── probe commands (declared ONCE, executed by the backend) ───────────────────
#
# These are the exact commands the LIVE (ssh/local) backend runs on a box.  The
# sim backend never runs them — it serves canned output keyed by probe id — which
# is why a 20-box fan-out can be exercised hermetically in CI.

PROBE_TOKEN = "token_store"
PROBE_WRITEBACK = "writeback"
PROBE_BROWSER = "browser"
PROBE_VERSION = "openclaw_version"
PROBE_RUN_RETRIES = "run_retries"
PROBE_STAMP = "repo_stamp"


def probe_commands(repo_dir: str, writeback_url: str, send_bearer: bool = False) -> Dict[str, str]:
    """The live probe command for each probe id.

    SECRET DISCIPLINE — no secret value ever enters this process or the ledger:
      • the token probe asks the repo's OWN credential checker for a VERDICT
        (SET / where, never the value).  It does not cat or grep a secrets file.
      • the write-back probe sends NO bearer by default.  Two reasons, both
        load-bearing: (a) an unauthenticated POST cannot MUTATE a live Command
        Center — a probe that creates a junk task on 20 client boxes is a bug,
        not a check; (b) 401 is the healthy answer we are looking for anyway
        (reachable AND enforcing auth).  If an operator opts into
        `writeback_send_bearer`, the bearer is expanded by the REMOTE shell
        (`${MC_API_TOKEN:-}`) straight into curl's header — it is never echoed,
        never captured, never logged.
    """
    r = shlex.quote(repo_dir)
    url = shlex.quote(writeback_url)
    auth = ' -H "Authorization: Bearer ${MC_API_TOKEN:-}"' if send_bearer else ""
    return {
        PROBE_TOKEN: f"bash {r}/shared-utils/check-credential.sh MC_API_TOKEN --json",
        # 2xx = authorized, 401 = reachable and ENFORCING auth.  Both prove the
        # write-back lane is alive.  000 (connect failure) / 404 / 5xx do not.
        PROBE_WRITEBACK: (
            'curl -s -o /dev/null -w "%{http_code}" --max-time 20 '
            "-X POST -H 'Content-Type: application/json'" + auth +
            " --data '{\"probe\":\"fleet-validation\"}' " + url
        ),
        PROBE_BROWSER: f"bash {r}/41-build-with-ai-playbook/scripts/06-verify-agent-browser.sh 2>&1",
        PROBE_VERSION: "openclaw --version 2>/dev/null | head -1",
        # The runRetries CEILING ROW, read from whichever config store the box has.
        PROBE_RUN_RETRIES: (
            "python3 - <<'PY'\n"
            "import json,os\n"
            "for p in (os.path.expanduser('~/.openclaw/openclaw.json'), '/data/.openclaw/openclaw.json'):\n"
            "    try:\n"
            "        d=json.load(open(p))\n"
            "    except Exception:\n"
            "        continue\n"
            "    a=(d.get('agents') or {})\n"
            "    m=a.get('main') if isinstance(a,dict) else None\n"
            "    for src in (m, d):\n"
            "        if isinstance(src,dict) and src.get('runRetries') is not None:\n"
            "            print(src['runRetries']); raise SystemExit(0)\n"
            "print('ABSENT')\n"
            "PY"
        ),
        PROBE_STAMP: f"cat {r}/version 2>/dev/null; git -C {r} rev-parse HEAD 2>/dev/null",
    }


# ── backends ──────────────────────────────────────────────────────────────────

@dataclass
class ProbeResult:
    rc: int
    stdout: str = ""
    stderr: str = ""
    error: str = ""          # transport failure (ssh down, timeout) -> UNKNOWN, never PASS

    @property
    def transport_failed(self) -> bool:
        return bool(self.error)


class Backend:
    name = "base"

    def run(self, box: Dict[str, Any], probe_id: str, command: str, timeout: int = 90) -> ProbeResult:
        raise NotImplementedError


class LocalBackend(Backend):
    name = "local"

    def run(self, box, probe_id, command, timeout=90):
        try:
            p = subprocess.run(["bash", "-lc", command], capture_output=True,
                               text=True, timeout=timeout)
            return ProbeResult(p.returncode, p.stdout, p.stderr)
        except subprocess.TimeoutExpired:
            return ProbeResult(124, error=f"probe {probe_id} TIMED OUT after {timeout}s")
        except Exception as exc:                                  # pragma: no cover
            return ProbeResult(1, error=f"probe {probe_id} transport error: {exc}")


class SSHBackend(Backend):
    name = "ssh"

    def run(self, box, probe_id, command, timeout=90):
        target = box.get("ssh_target")
        if not target:
            return ProbeResult(1, error=f"box {box.get('name')!r} has no ssh_target in the manifest")
        argv = ["ssh", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=accept-new",
                "-o", f"ConnectTimeout={min(20, timeout)}", target, "bash -lc " + shlex.quote(command)]
        try:
            p = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
            # ssh's own transport failures (255) are UNKNOWN, not a box FAIL: we
            # could not ask the question, so we must not answer it.
            if p.returncode == 255:
                return ProbeResult(255, p.stdout, p.stderr,
                                   error=f"ssh transport failure to {target}: {(p.stderr or '').strip()[:200]}")
            return ProbeResult(p.returncode, p.stdout, p.stderr)
        except subprocess.TimeoutExpired:
            return ProbeResult(124, error=f"probe {probe_id} TIMED OUT after {timeout}s")
        except Exception as exc:                                  # pragma: no cover
            return ProbeResult(1, error=f"probe {probe_id} transport error: {exc}")


class SimBackend(Backend):
    """Fixture-driven backend.  Serves canned probe output so a 20-box fan-out —
    including deliberately-broken boxes — runs hermetically in CI.

    A probe with NO fixture entry returns rc=127 "no canned response", which the
    checks treat as a FAIL.  Even the *simulator* is fail-closed."""

    name = "sim"

    def __init__(self, fixture: Dict[str, Any]):
        self.fixture = fixture or {}

    def run(self, box, probe_id, command, timeout=90):
        entry = ((self.fixture.get("boxes") or {}).get(box.get("name")) or {}).get("probes", {}).get(probe_id)
        if entry is None:
            return ProbeResult(127, stderr=f"[sim] no canned response for probe {probe_id!r}")
        if entry.get("error"):
            return ProbeResult(int(entry.get("rc", 255)), entry.get("stdout", ""),
                               entry.get("stderr", ""), error=str(entry["error"]))
        return ProbeResult(int(entry.get("rc", 0)), entry.get("stdout", ""), entry.get("stderr", ""))


# ── check implementations (each returns status, reason, observed) ─────────────

@dataclass
class Outcome:
    status: str
    reason: str = ""
    observed: Dict[str, Any] = field(default_factory=dict)


# Redact the WHOLE secret-shaped token, not just its prefix — a half-redacted
# token is a leaked token.  (This regex earned its keep: the first version only
# matched the prefix and the ledger test caught the tail leaking through.)
_SECRET_ISH = re.compile(
    r"(?:Bearer\s+\S{6,}"                 # bearer headers
    r"|(?:sk|pit|pat|ghp|gho|xox[abps])-[A-Za-z0-9_\-]{4,}"   # provider/PIT/github/slack key shapes
    r"|eyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-.]+"               # JWTs
    r")"
)


def _scrub(text: str, limit: int = 240) -> str:
    """Never let a probe's raw output smuggle a secret into the ledger."""
    return _SECRET_ISH.sub("[REDACTED]", (text or "").strip())[:limit]


def check_token_store(res: ProbeResult) -> Outcome:
    if res.transport_failed:
        return Outcome(L.UNKNOWN, f"could not reach box to check the MC_API_TOKEN store: {res.error}")
    if res.rc == 127:
        return Outcome(L.FAIL, "MC_API_TOKEN store probe did not run (no response) — fail-closed")
    try:
        doc = json.loads((res.stdout or "").strip() or "{}")
    except Exception:
        return Outcome(L.FAIL,
                       "MC_API_TOKEN store probe returned UNPARSEABLE output — fail-closed, never green",
                       {"raw": _scrub(res.stdout or res.stderr)})
    verdict = doc.get("verdict")
    where = doc.get("where_found") or []
    live_checked = bool(doc.get("live_env_checked"))
    observed = {"verdict": verdict, "stores_found": len(where), "live_env_checked": live_checked}
    # NB: exit 3 (NEEDS_BLOCK) is HEALTHY for MC_API_TOKEN — it is not a provider
    # key, so no models.providers block will ever reference it.  Judge the verdict.
    if verdict == "GENUINELY-ABSENT" or not where:
        return Outcome(L.FAIL,
                       "MC_API_TOKEN store UNREACHABLE — the token is not present in ANY store on this box; "
                       "write-back will 401 forever",
                       observed)
    if not live_checked:
        return Outcome(L.FAIL, "credential checker did not check the live process env — verdict not trustworthy",
                       observed)
    if verdict not in ("PRESENT_WITH_BLOCK", "NEEDS_BLOCK", "PRESENT"):
        return Outcome(L.FAIL, f"unrecognised credential verdict {verdict!r} — fail-closed", observed)
    return Outcome(L.PASS, f"token store reachable ({len(where)} store(s), verdict={verdict})", observed)


def check_writeback(res: ProbeResult, sent_bearer: bool = False) -> Outcome:
    """Spec contract (FLEET-FIX 4b): 2xx or 401 = PASS, anything else = FAIL."""
    if res.transport_failed:
        return Outcome(L.UNKNOWN, f"could not reach box to run the write-back probe: {res.error}")
    if res.rc == 127:
        return Outcome(L.FAIL, "write-back probe did not run (no response) — fail-closed")
    code = (res.stdout or "").strip().splitlines()[-1].strip() if (res.stdout or "").strip() else ""
    if not re.fullmatch(r"\d{3}", code):
        return Outcome(L.FAIL,
                       f"write-back probe returned NO HTTP status (got {_scrub(code, 60)!r}) — fail-closed",
                       {"raw": _scrub(res.stdout or res.stderr)})
    n = int(code)
    observed = {"http_status": n, "bearer_sent": bool(sent_bearer)}
    if 200 <= n <= 299:
        if not sent_bearer:
            # Still a PASS per the spec's 2xx/401 contract — but an UNAUTHENTICATED
            # 2xx means the middleware is not enforcing auth on this box, which the
            # operator must see, not discover later.
            observed["auth_enforced"] = False
            return Outcome(L.PASS,
                           f"write-back endpoint reachable ({n}) — WARNING: it answered 2xx to an "
                           "UNAUTHENTICATED probe, so the middleware is NOT enforcing auth on this box",
                           observed)
        observed["auth_enforced"] = True
        return Outcome(L.PASS, f"write-back endpoint authorized ({n})", observed)
    if n == 401:
        # 401 is a PASS by design: the lane is reachable AND enforcing auth.
        observed["auth_enforced"] = True
        return Outcome(L.PASS, "write-back endpoint reachable and enforcing auth (401)", observed)
    if n == 0:
        return Outcome(L.FAIL, "write-back endpoint UNREACHABLE (curl 000 — connection failed)", observed)
    return Outcome(L.FAIL,
                   f"write-back endpoint returned {n} — only 2xx or 401 prove a healthy write-back lane",
                   observed)


def check_browser(res: ProbeResult, marker: str = "PASS") -> Outcome:
    if res.transport_failed:
        return Outcome(L.UNKNOWN, f"could not reach box to run the browser probe: {res.error}")
    if res.rc == 127:
        return Outcome(L.FAIL, "browser probe did not run (no response) — fail-closed")
    blob = f"{res.stdout}\n{res.stderr}"
    if res.rc != 0:
        return Outcome(L.FAIL, f"agent-browser preflight FAILED (rc={res.rc})", {"tail": _scrub(blob)})
    if marker not in blob:
        # rc=0 with no PASS marker is exactly the shape of a fail-open. Refuse it.
        return Outcome(L.UNKNOWN,
                       f"agent-browser preflight exited 0 but printed no {marker!r} marker — "
                       "refusing to call that green",
                       {"tail": _scrub(blob)})
    return Outcome(L.PASS, "agent-browser preflight passed", {"tail": _scrub(blob, 120)})


def _parse_version(v: str) -> Optional[Tuple[int, ...]]:
    m = re.search(r"(\d+(?:\.\d+){1,3})", v or "")
    if not m:
        return None
    return tuple(int(x) for x in m.group(1).split("."))


def check_ceiling(version_res: ProbeResult, retries_res: ProbeResult,
                  min_version: str, run_retries_max: Any) -> Outcome:
    """`openclaw --version` + the runRetries CEILING ROW (FLEET-FIX Area 3)."""
    if version_res.transport_failed or retries_res.transport_failed:
        return Outcome(L.UNKNOWN,
                       f"could not reach box for the version/ceiling row: "
                       f"{version_res.error or retries_res.error}")
    if min_version in (None, "") or run_retries_max in (None, ""):
        return Outcome(L.FAIL,
                       "EXPECTATION NOT DECLARED (openclaw_min_version / run_retries_max) — "
                       "a gate with no expectation cannot fail, so it is not a gate")

    raw_version = (version_res.stdout or "").strip().splitlines()[0].strip() if (version_res.stdout or "").strip() else ""
    got = _parse_version(raw_version)
    want = _parse_version(str(min_version))
    observed: Dict[str, Any] = {"openclaw_version": raw_version or None}
    if version_res.rc != 0 or got is None:
        return Outcome(L.FAIL,
                       f"`openclaw --version` did not report a version (rc={version_res.rc}, "
                       f"output={_scrub(raw_version) or 'empty'}) — fail-closed",
                       observed)
    if want is None:
        return Outcome(L.FAIL, f"declared openclaw_min_version {min_version!r} is not a version", observed)
    if got < want:
        return Outcome(L.FAIL,
                       f"openclaw {raw_version} is BELOW the declared minimum {min_version} — "
                       "this box did not take the roll (or was DOWNGRADED by a stale checkout)",
                       observed)

    raw_retries = (retries_res.stdout or "").strip().splitlines()[-1].strip() if (retries_res.stdout or "").strip() else ""
    observed["run_retries"] = raw_retries or None
    if retries_res.rc != 0:
        return Outcome(L.FAIL, f"runRetries ceiling row could not be read (rc={retries_res.rc}) — fail-closed",
                       observed)
    if raw_retries in ("", "ABSENT", "None", "null"):
        return Outcome(L.FAIL,
                       "runRetries CEILING ROW IS ABSENT from this box's config — the ceiling is not "
                       "wired here; an absent row is a FAIL, never a default",
                       observed)
    try:
        n = int(raw_retries)
    except ValueError:
        return Outcome(L.FAIL, f"runRetries row is not an integer ({raw_retries!r}) — fail-closed", observed)
    observed["run_retries"] = n
    ceiling = int(run_retries_max)
    if n < 1:
        return Outcome(L.FAIL, f"runRetries={n} is not a usable ceiling (must be >= 1)", observed)
    if n > ceiling:
        return Outcome(L.FAIL,
                       f"runRetries={n} EXCEEDS the declared ceiling {ceiling} — an over-ceiling box "
                       "burns tokens in a retry furnace",
                       observed)
    return Outcome(L.PASS, f"openclaw {raw_version} >= {min_version}; runRetries={n} <= ceiling {ceiling}",
                   observed)


def check_repo_stamp(res: ProbeResult, want_version: str, want_sha: str) -> Outcome:
    """The stale-checkout / DOWNGRADE detector."""
    if res.transport_failed:
        return Outcome(L.UNKNOWN, f"could not reach box to read the repo stamp: {res.error}")
    if not want_version or not want_sha:
        return Outcome(L.FAIL,
                       "EXPECTATION NOT DECLARED (repo_version / repo_sha) — refusing to 'validate' "
                       "a stamp nobody named")
    lines = [ln.strip() for ln in (res.stdout or "").splitlines() if ln.strip()]
    if res.rc != 0 or len(lines) < 2:
        return Outcome(L.FAIL,
                       f"repo stamp unreadable on this box (rc={res.rc}, lines={len(lines)}) — "
                       "the onboarding checkout is missing or broken",
                       {"raw": _scrub(res.stdout or res.stderr)})
    got_version, got_sha = lines[0], lines[-1]
    observed = {"version": got_version, "sha": got_sha[:12]}
    if got_version != want_version:
        return Outcome(L.FAIL,
                       f"repo stamp version MISMATCH: box={got_version} expected={want_version} — "
                       "this box did not take the roll (a stale checkout DOWNGRADES boxes)",
                       observed)
    n = min(len(want_sha), len(got_sha), 40)
    if n < 7 or got_sha[:n].lower() != want_sha[:n].lower():
        return Outcome(L.FAIL,
                       f"repo stamp sha MISMATCH: box={got_sha[:12]} expected={want_sha[:12]} — "
                       "same version string, DIFFERENT code",
                       observed)
    return Outcome(L.PASS, f"repo stamp {got_version} @ {got_sha[:12]}", observed)


# ── per-box orchestration ─────────────────────────────────────────────────────

def validate_box(box: Dict[str, Any], backend: Backend, expectations: Dict[str, Any],
                 sweep_id: str, ledger_root: Optional[str], expect_sha: str,
                 timeout: int = 90) -> Dict[str, Any]:
    """Run all five checks against ONE box and finalize its ledger row.

    Never raises: an internal explosion is recorded as UNKNOWN on that box so one
    bad box can never take the wave down with it."""
    name = box["name"]
    repo_dir = box.get("repo_dir") or expectations.get("repo_dir") or "$HOME/openclaw-onboarding"
    send_bearer = bool(expectations.get("writeback_send_bearer"))
    cmds = probe_commands(repo_dir, str(expectations.get("writeback_url") or ""), send_bearer)

    def probe(pid: str) -> ProbeResult:
        return backend.run(box, pid, cmds[pid], timeout)

    try:
        if not expectations.get("writeback_url"):
            wb = Outcome(L.FAIL, "EXPECTATION NOT DECLARED (writeback_url) — cannot probe an endpoint nobody named")
        else:
            wb = check_writeback(probe(PROBE_WRITEBACK), send_bearer)

        outcomes = {
            CHECK_TOKEN: check_token_store(probe(PROBE_TOKEN)),
            CHECK_WRITEBACK: wb,
            CHECK_BROWSER: check_browser(probe(PROBE_BROWSER),
                                         str(expectations.get("browser_pass_marker") or "PASS")),
            CHECK_CEILING: check_ceiling(probe(PROBE_VERSION), probe(PROBE_RUN_RETRIES),
                                         expectations.get("openclaw_min_version"),
                                         expectations.get("run_retries_max")),
            CHECK_STAMP: check_repo_stamp(probe(PROBE_STAMP),
                                          str(expectations.get("repo_version") or ""),
                                          str(expectations.get("repo_sha") or "")),
        }
    except Exception as exc:                                       # pragma: no cover
        outcomes = {c: Outcome(L.UNKNOWN, f"harness error on this box: {exc}") for c in REQUIRED_CHECKS}

    # Defence in depth: every reason and every observed string is scrubbed on the
    # way OUT, so a future check that forgets to scrub still cannot leak a secret
    # into a ledger row (or into the loud failure banner).
    for check, oc in outcomes.items():
        observed = {k: (_scrub(v, 400) if isinstance(v, str) else v)
                    for k, v in (oc.observed or {}).items()}
        L.record_check(sweep_id, name, check, oc.status, _scrub(oc.reason, 400), observed,
                       ledger_root, expect_sha)
    return L.finalize(sweep_id, name, REQUIRED_CHECKS, ledger_root, expect_sha)


# ── manifest / expectations ───────────────────────────────────────────────────

def load_boxes(path: Optional[str], inline: List[str]) -> List[Dict[str, Any]]:
    boxes: List[Dict[str, Any]] = []
    if path:
        doc = json.loads(Path(path).read_text(encoding="utf-8"))
        raw = doc.get("boxes", doc) if isinstance(doc, dict) else doc
        if not isinstance(raw, list):
            raise ValueError("boxes file must be a JSON array (or {\"boxes\": [...]})")
        for b in raw:
            if isinstance(b, str):
                boxes.append({"name": b})
            elif isinstance(b, dict) and b.get("name"):
                boxes.append(b)
            else:
                raise ValueError(f"box entry missing 'name': {b!r}")
    for n in inline:
        boxes.append({"name": n})
    seen, uniq = set(), []
    for b in boxes:
        if b["name"] in seen:
            continue
        seen.add(b["name"])
        uniq.append(b)
    return uniq


def missing_expectations(exp: Dict[str, Any]) -> List[str]:
    return [k for k in sorted(REQUIRED_EXPECTATIONS) if not exp.get(k)]


# ── CLI ───────────────────────────────────────────────────────────────────────

def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="post-fan-out per-box fleet validation harness (AUD-58)")
    ap.add_argument("--sweep-id", required=True, help="sweep name — becomes /tmp/<sweep>/")
    ap.add_argument("--boxes-file", help="JSON manifest of boxes")
    ap.add_argument("--box", action="append", default=[], help="box name (repeatable)")
    ap.add_argument("--expectations", help="JSON file of declared expectations")
    ap.add_argument("--backend", choices=["ssh", "local", "sim"], default="ssh")
    ap.add_argument("--sim-fixture", help="fixture file (required for --backend sim)")
    ap.add_argument("--ledger-root", default=None, help="default /tmp")
    ap.add_argument("--max-parallel", type=int, default=8)
    ap.add_argument("--wave-cap", type=int, default=DEFAULT_WAVE_CAP)
    ap.add_argument("--timeout", type=int, default=90)
    ap.add_argument("--resume", action="store_true",
                    help="skip boxes already PASS under the SAME expectations")
    ap.add_argument("--json", action="store_true", help="emit the sweep rollup as JSON on stdout")
    args = ap.parse_args(argv)

    # ── manifest ──
    try:
        boxes = load_boxes(args.boxes_file, args.box)
    except Exception as exc:
        _err(f"{RED}[fleet-validate] REFUSING TO RUN: bad box manifest — {exc}{NC}")
        return 4
    if not boxes:
        _err(f"{RED}[fleet-validate] REFUSING TO RUN: zero boxes. A sweep over no boxes is not a green sweep.{NC}")
        return 4
    if len(boxes) > args.wave_cap:
        _err(f"{RED}[fleet-validate] REFUSING TO RUN: {len(boxes)} boxes exceeds the wave cap "
             f"({args.wave_cap}). Doctrine: <= {DEFAULT_WAVE_CAP} boxes per wave. Split the wave.{NC}")
        return 4

    # ── expectations (fail-closed BEFORE any box is touched) ──
    exp: Dict[str, Any] = {}
    if args.expectations:
        try:
            exp = json.loads(Path(args.expectations).read_text(encoding="utf-8"))
        except Exception as exc:
            _err(f"{RED}[fleet-validate] REFUSING TO RUN: unreadable expectations file — {exc}{NC}")
            return 4
    miss = missing_expectations(exp)
    if miss:
        _err(f"{RED}{BOLD}[fleet-validate] REFUSING TO RUN — UNDECLARED EXPECTATIONS: {', '.join(miss)}{NC}")
        _err(f"{RED}  A gate you cannot fail is not a gate. Declare every expectation, then re-run.{NC}")
        return 4

    # ── backend ──
    if args.backend == "sim":
        if not args.sim_fixture:
            _err(f"{RED}[fleet-validate] --backend sim requires --sim-fixture{NC}")
            return 4
        try:
            fixture = json.loads(Path(args.sim_fixture).read_text(encoding="utf-8"))
        except Exception as exc:
            _err(f"{RED}[fleet-validate] unreadable sim fixture — {exc}{NC}")
            return 4
        backend: Backend = SimBackend(fixture)
    elif args.backend == "local":
        backend = LocalBackend()
    else:
        backend = SSHBackend()

    esha = L.expectations_sha(exp)
    root = args.ledger_root
    sdir = L.sweep_dir(args.sweep_id, root)
    sdir.mkdir(parents=True, exist_ok=True)

    _out(f"{CYAN}[fleet-validate] sweep={args.sweep_id} boxes={len(boxes)} backend={backend.name} "
         f"ledger={sdir}/<box>.json expectations={esha}{NC}")

    # ── fan-out (per-box isolation) ──
    def work(box: Dict[str, Any]) -> Dict[str, Any]:
        if args.resume and L.should_skip(L.load_row(args.sweep_id, box["name"], root), esha):
            _out(f"  {GREEN}SKIP{NC} {box['name']}  (already PASS under these expectations)")
            return L.load_row(args.sweep_id, box["name"], root)
        try:
            row = validate_box(box, backend, exp, args.sweep_id, root, esha, args.timeout)
        except Exception as exc:                                   # pragma: no cover
            L.record_check(args.sweep_id, box["name"], CHECK_TOKEN, L.UNKNOWN,
                           f"harness crashed on this box: {exc}", {}, root, esha)
            row = L.finalize(args.sweep_id, box["name"], REQUIRED_CHECKS, root, esha)
        colour = {L.PASS: GREEN, L.FAIL: RED, L.UNKNOWN: YELLOW}.get(row["status"], YELLOW)
        _out(f"  {colour}{row['status']:<7}{NC} {box['name']}")
        return row

    with ThreadPoolExecutor(max_workers=max(1, args.max_parallel)) as pool:
        rows = list(pool.map(work, boxes))

    doc = L.rollup(args.sweep_id, root, [b["name"] for b in boxes])

    # ── LOUD verdict ──
    bad = [r for r in rows if r.get("status") != L.PASS]
    _out("")
    if doc["verdict"] == L.PASS:
        _out(f"{GREEN}{BOLD}================ FLEET VALIDATION: PASS ({doc['counts'][L.PASS]}/{len(boxes)} boxes) ================{NC}")
    else:
        banner = f"================ FLEET VALIDATION: {doc['verdict']} ================"
        _err(f"{RED}{BOLD}{banner}{NC}")
        _err(f"{RED}  PASS={doc['counts'][L.PASS]}  FAIL={doc['counts'][L.FAIL]}  "
             f"UNKNOWN={doc['counts'][L.UNKNOWN]}  of {len(boxes)} boxes{NC}")
        for r in sorted(bad, key=lambda x: x.get("box", "")):
            _err(f"{RED}  {r.get('status'):<7} {r.get('box')}{NC}")
            for reason in r.get("reasons", []):
                _err(f"{RED}      - {reason}{NC}")
        _err(f"{RED}{BOLD}  THE FLEET ROLL IS BLOCKED. Fix the boxes above, then re-run with --resume.{NC}")
        _err(f"{RED}  Per-box detail: {sdir}/<box>.json  |  rollup: {L.sweep_rollup_path(args.sweep_id, root)}{NC}")

    if args.json:
        _out(json.dumps(doc, indent=2))
    return L.exit_code_for(doc["verdict"])


if __name__ == "__main__":
    sys.exit(main())
