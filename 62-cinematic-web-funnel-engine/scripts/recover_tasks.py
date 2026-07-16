#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""recover_tasks.py — idempotent task recovery/resume (Skill 62, U12).

Implements spec Section 11.2's restart rule ("recover `in_progress` tasks by
querying the provider before resubmitting") and CWFE-MANIFEST.json's
cross-cutting AF-CWFE-RESTART-DUPLICATE contract:

    {"af_code": "AF-CWFE-RESTART-DUPLICATE",
     "trigger": "a restarted/resumed run re-issues a paid provider call for a
     task already recorded complete in cost-ledger.json",
     "enforced_by": "scripts/recover_tasks.py (later unit)",
     "py_symbol": "recover_tasks.assert_no_duplicate_spend"}

Two responsibilities:

  1. ``recover_and_reconcile()`` — the ACTIVE recovery step. Reads
     ``scripts/state_engine.py``'s ``ProjectState.recover()`` report
     (read-only) and, for every task that actually reached the provider
     (``must_query_provider`` — has a ``provider_task_id``), queries the
     provider's REAL current status via ``MediaProvider.get_task()`` and
     reconciles the cost-ledger/task state to match:

       - provider reports ``success`` -> downloads the result (a producer
         that died between submission and download never left the paid
         artifact stranded) and transitions the task to ``complete``;
       - provider reports ``failed``/``cancelled`` -> transitions to
         ``failed`` (recorded, never silently dropped) — never re-submits
         automatically, so a normal producer re-invocation is what performs
         any retry, going through the SAME AF-CWFE-PAID-GATE and idempotency
         check every fresh paid call goes through;
       - provider reports anything else (``queued``/``processing``) -> left
         untouched, genuinely still running at the provider; re-check on the
         next recovery pass.

     Every task that NEVER reached the provider (``safe_to_requeue`` — no
     ``provider_task_id``, the process died before the provider call was
     ever sent) is transitioned to ``failed`` — this is what makes
     "safe to requeue" durable rather than a permanently wedged
     ``queued``/``submitted`` ledger entry blocking every future
     ``begin_task()`` call for that ``request_hash`` forever (a `queued` or
     `submitted` status is "active" per ``find_active_or_complete_entry()``,
     so without this reconciliation step a crashed pre-submission task would
     deadlock its own request_hash permanently). No paid spend was ever at
     risk for these — nothing was ever submitted to the provider.

  2. ``assert_no_duplicate_spend()`` — the MECHANICAL prover
     CWFE-MANIFEST.json names for AF-CWFE-RESTART-DUPLICATE. Independently
     audits ``cost-ledger.json`` for the violation state
     ``ProjectState.begin_task()``'s own idempotency check is SUPPOSED to
     make structurally impossible: two or more entries sharing the same
     ``request_hash`` that are simultaneously active-or-complete
     (``queued``/``submitted``/``in_progress``/``complete``). Fails closed
     (raises ``DuplicateSpendDetected``) by default so a caller can wire it
     as a real gate rather than a mere log line; ``fail_closed=False`` gives
     a non-raising bool+detail read for reporting/CLI use.

Never calls a provider itself outside ``recover_and_reconcile()``'s explicit,
narrow reconciliation step; never mutates state outside
``ProjectState.transition_task()``'s own locked, schema-validated,
state-machine-enforced path. No secret values ever pass through this module.

BUILD+TEST AGAINST MOCKED KIE FIXTURES ONLY (spec §19.2) — see
``FakeRecoveryProvider`` in ``self_test()`` below; nothing here makes a live
network call.

stdlib only. CLI:
    python3 recover_tasks.py --run-dir DIR --action recover
    python3 recover_tasks.py --run-dir DIR --action assert-no-duplicate-spend
    python3 recover_tasks.py --self-test
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_SCRIPT_DIR = Path(__file__).resolve().parent
_SKILL_DIR = _SCRIPT_DIR.parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))
if str(_SKILL_DIR) not in sys.path:
    sys.path.insert(0, str(_SKILL_DIR))

import state_engine as se  # noqa: E402
from providers import base as providers_base  # noqa: E402
from providers import kie as kie_provider  # noqa: E402

EXIT_OK = 0
EXIT_FAIL = 2
EXIT_USAGE = 3

# statuses find_active_or_complete_entry()/begin_task() treat as "active or
# complete" for idempotency purposes (state_engine.py's own convention,
# duplicated here as a small local constant rather than importing a private
# module-level list — matches this skill's existing small-helper-duplication
# pattern, e.g. _now()/_sha256_file() reappearing per-module).
_ACTIVE_OR_COMPLETE_STATUSES = ("queued", "submitted", "in_progress", "complete")

RECOVERY_LOG_FILENAME = "recovery-log.json"


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=False) + "\n", encoding="utf-8")


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


class RecoverTasksError(Exception):
    """Base class for every error this module raises."""


class DuplicateSpendDetected(RecoverTasksError):
    """Raised by assert_no_duplicate_spend(fail_closed=True) when two or
    more cost-ledger entries sharing the same request_hash are
    simultaneously active-or-complete — the exact condition
    ProjectState.begin_task()'s own idempotency check is supposed to make
    structurally impossible (AF-CWFE-RESTART-DUPLICATE)."""


# ---------------------------------------------------------------------------
# assert_no_duplicate_spend — AF-CWFE-RESTART-DUPLICATE's named prover
# ---------------------------------------------------------------------------
def assert_no_duplicate_spend(run_dir: Path, *, fail_closed: bool = True) -> Tuple[bool, str]:
    """Audits cost-ledger.json's entries[] for any request_hash that has MORE
    THAN ONE simultaneously active-or-complete entry. This is a standalone,
    independently re-derived check — it never trusts that begin_task()'s own
    idempotency guard actually ran correctly on every historical write; it
    re-reads the ledger from disk and re-computes the grouping itself every
    time it is called."""
    state = se.ProjectState(run_dir)
    if not state.exists("cost-ledger"):
        return True, "cost-ledger.json does not exist yet — nothing to audit"
    try:
        ledger = state.load("cost-ledger")
    except se.StateEngineError as exc:
        detail = f"cost-ledger.json failed to load/validate: {exc}"
        if fail_closed:
            raise DuplicateSpendDetected(detail) from exc
        return False, detail

    by_hash: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for entry in ledger["entries"]:
        if entry["status"] in _ACTIVE_OR_COMPLETE_STATUSES:
            by_hash[entry["request_hash"]].append(entry)

    violations = [
        f"request_hash={h} has {len(entries)} simultaneously active-or-complete task(s): "
        f"{[e['task_id'] for e in entries]!r} (statuses={[e['status'] for e in entries]!r})"
        for h, entries in sorted(by_hash.items())
        if len(entries) > 1
    ]
    if violations:
        detail = "; ".join(violations)
        if fail_closed:
            raise DuplicateSpendDetected(detail)
        return False, detail

    return True, (
        f"{len(ledger['entries'])} cost-ledger entr{'y' if len(ledger['entries']) == 1 else 'ies'} audited, "
        f"no duplicate active/complete request_hash found across {len(by_hash)} distinct request(s)"
    )


# ---------------------------------------------------------------------------
# recover_and_reconcile — the active recovery step
# ---------------------------------------------------------------------------
def recover_and_reconcile(
    run_dir: Path,
    *,
    provider: Optional[providers_base.MediaProvider] = None,
    media_dir: Optional[Path] = None,
) -> Tuple[bool, str]:
    """Idempotent: calling this repeatedly is always safe — a project with
    nothing in_progress is a trivial no-op success, and a task already
    reconciled to complete/failed on a prior call is never touched again
    (ProjectState.recover() only ever reports queued/submitted/in_progress
    entries, and this function's own transitions move every entry it
    touches OUT of that set)."""
    state = se.ProjectState(run_dir)
    provider = provider or kie_provider.KieProvider()
    if not state.exists("cost-ledger"):
        return True, "cost-ledger.json does not exist yet — nothing to recover"

    report = state.recover()
    log: Dict[str, Any] = {
        "checked_at": _now(),
        "in_progress_count_before": report["in_progress_count"],
        "reconciled": [],
        "errors": [],
    }

    # Tasks that never reached the provider: no spend was ever at risk
    # (nothing was ever submitted), but a permanently 'queued'/'submitted'
    # entry with no provider_task_id would otherwise wedge every future
    # begin_task() call for its request_hash. Free it by transitioning to
    # 'failed' so a normal producer re-invocation opens a clean, fresh task.
    for entry in report["safe_to_requeue"]:
        try:
            state.transition_task(
                entry["task_id"], "failed",
                retry_reason=(
                    "recover_tasks: process died before this task ever reached the provider "
                    "(no provider_task_id recorded) — safe to retry via a fresh producer call; "
                    "no spend occurred"
                ),
            )
            log["reconciled"].append({"task_id": entry["task_id"], "action": "failed-never-submitted"})
        except se.StateEngineError as exc:
            log["errors"].append({"task_id": entry["task_id"], "error": str(exc)})

    # Tasks that DID reach the provider: query REAL current status before
    # doing anything else (spec 11.2 "recover in_progress tasks by querying
    # the provider before resubmitting" — never a blind resubmit, and never
    # a second paid call for a request_hash already open).
    for entry in report["must_query_provider"]:
        provider_task_id = entry["provider_task_id"]
        try:
            handle = provider.get_task(provider_task_id)
        except providers_base.ProviderTaskError as exc:
            log["errors"].append(
                {"task_id": entry["task_id"], "provider_task_id": provider_task_id, "error": str(exc)}
            )
            continue

        if handle.status == "success" or handle.status == "complete":
            try:
                dest_dir = Path(media_dir) if media_dir is not None else Path(run_dir) / "media" / "recovered"
                destination = dest_dir / f"{entry['task_id']}"
                written = provider.download_results(provider_task_id, str(destination))
                local_path = Path(written[0])
                hash_sha256 = _sha256_file(local_path)
                state.transition_task(
                    entry["task_id"], "complete", actual_cost_usd=entry["estimated_cost_usd"]
                )
                log["reconciled"].append({
                    "task_id": entry["task_id"], "provider_task_id": provider_task_id,
                    "action": "completed-via-recovery", "local_path": str(local_path),
                    "hash_sha256": hash_sha256,
                })
            except (providers_base.ProviderTaskError, se.StateEngineError) as exc:
                log["errors"].append(
                    {"task_id": entry["task_id"], "provider_task_id": provider_task_id, "error": str(exc)}
                )
        elif handle.status in ("failed", "cancelled"):
            try:
                state.transition_task(
                    entry["task_id"], "failed",
                    retry_reason=(
                        f"recover_tasks: provider reports status={handle.status!r} "
                        f"(detail={handle.detail!r}) for provider_task_id={provider_task_id}"
                    ),
                )
                log["reconciled"].append(
                    {"task_id": entry["task_id"], "provider_task_id": provider_task_id, "action": f"failed-{handle.status}"}
                )
            except se.StateEngineError as exc:
                log["errors"].append({"task_id": entry["task_id"], "error": str(exc)})
        else:
            # queued/processing at the provider — genuinely still running.
            # Leave it as-is; nothing to reconcile yet, re-check next pass.
            log["reconciled"].append(
                {"task_id": entry["task_id"], "provider_task_id": provider_task_id, "action": "still-in-progress-no-change"}
            )

    log_path = Path(run_dir) / RECOVERY_LOG_FILENAME
    existing: List[Dict[str, Any]] = []
    if log_path.exists():
        try:
            existing = json.loads(log_path.read_text(encoding="utf-8"))
            if not isinstance(existing, list):
                existing = []
        except json.JSONDecodeError:
            existing = []
    existing.append(log)
    _write_json(log_path, existing)

    ok = not log["errors"]
    detail = (
        f"recovered {len(log['reconciled'])} task(s) "
        f"({len(report['must_query_provider'])} queried at the provider, "
        f"{len(report['safe_to_requeue'])} freed without a provider call), "
        f"{len(log['errors'])} error(s)"
    )
    return ok, detail


# ---------------------------------------------------------------------------
# Test-support fixtures — never used by any production code path.
# ---------------------------------------------------------------------------
class FakeRecoveryProvider:
    """A minimal fake MediaProvider (duck-typed to providers.base.MediaProvider
    for exactly the two methods recover_and_reconcile() calls) whose
    get_task() responses are pre-programmed per provider_task_id. NEVER
    touches the network (spec §19.2)."""

    name = "kie"

    def __init__(self, statuses: Dict[str, str]) -> None:
        self._statuses = dict(statuses)  # provider_task_id -> status
        self.get_task_calls: List[str] = []
        self.download_calls: List[str] = []

    def get_task(self, task_id: str) -> providers_base.TaskHandle:
        self.get_task_calls.append(task_id)
        status = self._statuses.get(task_id, "processing")
        detail = "fixture failure" if status == "failed" else None
        return providers_base.TaskHandle(task_id=task_id, provider=self.name, model_id="", status=status, detail=detail)

    def download_results(self, task_id: str, destination: str) -> List[str]:
        self.download_calls.append(task_id)
        dest = Path(destination)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(f"FIXTURE-RECOVERED-CLIP::{task_id}".encode("utf-8"))
        return [str(dest)]


def self_test() -> int:
    import shutil
    import tempfile

    fails = 0

    def check(label: str, cond: bool) -> None:
        nonlocal fails
        if cond:
            print(f"  [PASS] {label}")
        else:
            print(f"  [FAIL] {label}")
            fails += 1

    tmp = Path(tempfile.mkdtemp(prefix="cwfe-recover-tasks-selftest-"))
    try:
        state = se.ProjectState(tmp)
        state.create_project(
            project_id="proj-recover-selftest", client_slug="acme", project_slug="launch",
            deliverable_type="cinematic-landing-page", budget_cap_usd=10.0,
        )

        # ---- clean project: nothing to recover, nothing to audit ----------
        passed, detail = recover_and_reconcile(tmp, provider=FakeRecoveryProvider({}))
        check(f"recover_and_reconcile is a clean no-op with no cost-ledger entries yet ({detail})", passed)
        passed, detail = assert_no_duplicate_spend(tmp, fail_closed=False)
        check(f"assert_no_duplicate_spend passes on an empty ledger ({detail})", passed)

        # ---- entry_a: process died BEFORE ever reaching the provider ------
        # (transitioned to 'submitted' without a provider_task_id -- the
        # narrow crash window state_engine.py's own recover() docstring
        # names explicitly: "the process died before the provider call was
        # actually sent").
        entry_a = state.begin_task(
            provider="kie", model="kie-bytedance-seedance-1.5-pro", operation="generate_video",
            params={"scene": "scene-a-never-submitted"}, estimated_cost_usd=0.20, seconds=4,
        )
        state.transition_task(entry_a["task_id"], "submitted")  # deliberately NO provider_task_id

        # ---- entry_b: process died AFTER the provider accepted it; the
        # provider will now report it succeeded ------------------------------
        entry_b = state.begin_task(
            provider="kie", model="kie-bytedance-seedance-1.5-pro", operation="generate_video",
            params={"scene": "scene-b-will-succeed"}, estimated_cost_usd=0.20, seconds=4,
        )
        state.transition_task(entry_b["task_id"], "submitted", provider_task_id="kie-task-success-1")
        state.transition_task(entry_b["task_id"], "in_progress")

        # ---- entry_c: process died mid-flight; the provider will now
        # report it actually failed -------------------------------------------
        entry_c = state.begin_task(
            provider="kie", model="kie-bytedance-seedance-1.5-pro", operation="generate_video",
            params={"scene": "scene-c-will-fail"}, estimated_cost_usd=0.20, seconds=4,
        )
        state.transition_task(entry_c["task_id"], "submitted", provider_task_id="kie-task-failed-1")
        state.transition_task(entry_c["task_id"], "in_progress")

        # ---- entry_d: process died mid-flight; the provider reports it is
        # still genuinely processing -------------------------------------------
        entry_d = state.begin_task(
            provider="kie", model="kie-bytedance-seedance-1.5-pro", operation="generate_video",
            params={"scene": "scene-d-still-running"}, estimated_cost_usd=0.20, seconds=4,
        )
        state.transition_task(entry_d["task_id"], "submitted", provider_task_id="kie-task-stillrunning-1")
        state.transition_task(entry_d["task_id"], "in_progress")

        recovery = state.recover()
        check(
            "state.recover() reports all 4 in-flight tasks (1 safe_to_requeue + 3 must_query_provider)",
            recovery["in_progress_count"] == 4 and len(recovery["safe_to_requeue"]) == 1
            and len(recovery["must_query_provider"]) == 3,
        )

        fake_provider = FakeRecoveryProvider({
            "kie-task-success-1": "success",
            "kie-task-failed-1": "failed",
            "kie-task-stillrunning-1": "processing",
        })
        passed, detail = recover_and_reconcile(tmp, provider=fake_provider)
        check(f"recover_and_reconcile PASSES and reconciles every entry with no errors ({detail})", passed)

        ledger = state.load("cost-ledger")
        by_id = {e["task_id"]: e for e in ledger["entries"]}
        check("entry_a (never submitted) is now 'failed'", by_id[entry_a["task_id"]]["status"] == "failed")
        check("entry_b (provider succeeded) is now 'complete'", by_id[entry_b["task_id"]]["status"] == "complete")
        check(
            "entry_b's actual_cost_usd was recorded from recovery",
            by_id[entry_b["task_id"]]["actual_cost_usd"] == entry_b["estimated_cost_usd"],
        )
        check("entry_c (provider reports failed) is now 'failed'", by_id[entry_c["task_id"]]["status"] == "failed")
        check("entry_d (provider still processing) is UNCHANGED at 'in_progress'", by_id[entry_d["task_id"]]["status"] == "in_progress")
        check(
            "entry_a's retry_reason names it never reached the provider (not a generic failure)",
            "ever reached the provider" in (by_id[entry_a["task_id"]]["retry_reason"] or ""),
        )
        check(
            "fake_provider.get_task() was called for all 3 must_query_provider tasks, never for entry_a",
            sorted(fake_provider.get_task_calls) == ["kie-task-failed-1", "kie-task-stillrunning-1", "kie-task-success-1"],
        )
        check("entry_b's recovered clip was actually downloaded to disk", fake_provider.download_calls == ["kie-task-success-1"])

        # 2 log entries so far: the very first "clean project" no-op call
        # above ALSO wrote a log entry (create_project() already created an
        # empty cost-ledger.json, so that call did not hit the "does not
        # exist yet" early-return) plus this reconciliation call.
        recovered_local_path = None
        recovery_log = json.loads((tmp / RECOVERY_LOG_FILENAME).read_text(encoding="utf-8"))
        check("recovery-log.json was written and accumulated the clean-noop + this reconciliation call", (tmp / RECOVERY_LOG_FILENAME).exists() and len(recovery_log) == 2)
        for r in recovery_log[-1]["reconciled"]:
            if r["task_id"] == entry_b["task_id"]:
                recovered_local_path = r["local_path"]
        check("recovery-log.json records entry_b's recovered local_path", recovered_local_path is not None and Path(recovered_local_path).exists())

        # ---- idempotent re-run: entry_d still processing, nothing else to do ----
        fake_provider2 = FakeRecoveryProvider({"kie-task-stillrunning-1": "processing"})
        passed, detail = recover_and_reconcile(tmp, provider=fake_provider2)
        check(f"re-running recover_and_reconcile is idempotent (only entry_d remains in-flight) ({detail})", passed)
        check(
            "the second recovery pass only queried entry_d's provider_task_id (a,b,c were already reconciled out of the in-flight set)",
            fake_provider2.get_task_calls == ["kie-task-stillrunning-1"],
        )
        recovery_log_2 = json.loads((tmp / RECOVERY_LOG_FILENAME).read_text(encoding="utf-8"))
        check("recovery-log.json accumulates across passes (append-only)", len(recovery_log_2) == 3)

        # Resolve entry_d to a terminal state directly (simulating its own
        # normal eventual completion) so the CLI checks below -- which use
        # the REAL KieProvider() (no injected fake) -- never attempt a live
        # provider call against a lingering in_progress task.
        state.transition_task(entry_d["task_id"], "complete", actual_cost_usd=entry_d["estimated_cost_usd"])

        # ---- assert_no_duplicate_spend: clean ledger passes -----------------
        passed, detail = assert_no_duplicate_spend(tmp, fail_closed=False)
        check(f"assert_no_duplicate_spend passes on a reconciled, duplicate-free ledger ({detail})", passed)

        # ---- REQUIRED BREAK-IT: fabricate a duplicate active request_hash ---
        ledger = state.load("cost-ledger")
        original_entry = next(e for e in ledger["entries"] if e["task_id"] == entry_d["task_id"])
        duplicate_entry = dict(original_entry)
        duplicate_entry["task_id"] = "t-fabricated-duplicate-0001"
        duplicate_entry["provider_task_id"] = "kie-task-duplicate-fabricated"
        duplicate_entry["status"] = "in_progress"
        ledger["entries"].append(duplicate_entry)
        state.save("cost-ledger", ledger)

        passed, detail = assert_no_duplicate_spend(tmp, fail_closed=False)
        check(f"assert_no_duplicate_spend DETECTS a fabricated duplicate active request_hash ({detail})", not passed)
        check("violation detail names the shared request_hash", original_entry["request_hash"] in detail)

        try:
            assert_no_duplicate_spend(tmp, fail_closed=True)
            check("assert_no_duplicate_spend(fail_closed=True) raises on the same fabricated duplicate", False)
        except DuplicateSpendDetected:
            check("assert_no_duplicate_spend(fail_closed=True) raises on the same fabricated duplicate", True)

        # restore the ledger to its clean state for the CLI checks below.
        ledger["entries"] = [e for e in ledger["entries"] if e["task_id"] != "t-fabricated-duplicate-0001"]
        state.save("cost-ledger", ledger)
        passed, _ = assert_no_duplicate_spend(tmp, fail_closed=False)
        check("assert_no_duplicate_spend passes again once the fabricated duplicate is removed", passed)

        # ---- CLI wiring ------------------------------------------------------
        import subprocess

        result = subprocess.run(
            [sys.executable, str(_SCRIPT_DIR / "recover_tasks.py"), "--run-dir", str(tmp), "--action", "recover"],
            capture_output=True, text=True,
        )
        check(f"CLI --action recover exits 0 (stderr={result.stderr!r})", result.returncode == 0)

        result = subprocess.run(
            [sys.executable, str(_SCRIPT_DIR / "recover_tasks.py"), "--run-dir", str(tmp), "--action", "assert-no-duplicate-spend"],
            capture_output=True, text=True,
        )
        check(f"CLI --action assert-no-duplicate-spend exits 0 on a clean ledger (stderr={result.stderr!r})", result.returncode == 0)

    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    if fails:
        print(f"RESULT: FAIL — {fails} self-test check(s) failed.", file=sys.stderr)
        return 1
    print("RESULT: PASS — task recovery/resume self-test green.")
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(
        description="Idempotent task recovery/resume for the Cinematic and Web Funnel Engine "
        "(Skill 62, U12, AF-CWFE-RESTART-DUPLICATE)."
    )
    parser.add_argument("--run-dir", help="project run directory (required unless --self-test)")
    parser.add_argument("--action", choices=["recover", "assert-no-duplicate-spend"], default="recover")
    parser.add_argument("--self-test", action="store_true", help="run the built-in offline self-test and exit")
    args = parser.parse_args()

    if args.self_test:
        sys.exit(self_test())

    if not args.run_dir:
        print("USAGE ERROR: --run-dir is required (unless --self-test)", file=sys.stderr)
        sys.exit(EXIT_USAGE)
    run_dir = Path(args.run_dir)
    if not run_dir.is_dir():
        print(f"USAGE ERROR: --run-dir does not exist: {run_dir}", file=sys.stderr)
        sys.exit(EXIT_USAGE)

    if args.action == "recover":
        passed, detail = recover_and_reconcile(run_dir)
    else:
        try:
            passed, detail = assert_no_duplicate_spend(run_dir, fail_closed=False)
        except DuplicateSpendDetected as exc:  # pragma: no cover — fail_closed=False never raises
            passed, detail = False, str(exc)

    if passed:
        print(f"[PASS] {args.action} — {detail}")
        sys.exit(EXIT_OK)
    print(f"[FAIL] {args.action} — {detail}", file=sys.stderr)
    sys.exit(EXIT_FAIL)


if __name__ == "__main__":
    main()
