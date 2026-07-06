#!/usr/bin/env python3
"""Credit-out queue mechanics for the Podcast Production Engine (Skill 58).

Implements PRD Step-cross-cutting (Section 5), furnace-design Guardrail 6, and
dashboard-design Sections 5.2/8.4:

  "Cross-cutting at every step ... any insufficient-credits error moves the job to
   the credit-out queue with full payload and partial state (60-day maximum, daily
   age-check, resume from resume_stage)."

What this module owns (the MECHANICS, not the datastore):
  1. Detect an insufficient-credits failure from any of the four paid services
     (kie_ai, ollama_cloud, openrouter, fish_audio).
  2. HOLD a job: move it to the queued_credit_out state, carrying its FULL inbound
     payload and any partial state already produced, recording queued_service,
     queued_at, resume_stage, and a precomputed queue_deadline (queued_at + 60 days).
  3. DAILY AGE-CHECK (invoked by the daily smoke test, never by its own cron): age
     out anything past the 60-day deadline (drop, purge payload, aged-out founder
     notice) and drain jobs whose depleted service has flipped back to funded.
  4. RESUME from resume_stage when credits return, RETAINING the held payload and
     partial state so the pipeline continues from where it left off. The payload is
     purged at age-out (here) and, elsewhere, at complete or failed by the writer
     (dashboard-design 10.2), never on resume.

What this module deliberately does NOT do (furnace doctrine, Guardrail 6):
  - It creates NO cron and NO standalone poller. A held job is a JSON/SQLite record,
    not a process. The queue is examined at exactly two moments: inside the daily
    smoke-test run (age-check plus drain), and event-driven when the operator marks
    credits restored. This module supplies the logic those two callers invoke.
  - It NEVER opens podcast-engine.db read-write. dashboard-design D3/5.4 makes
    podcast_state.py the SOLE writer; this module delegates every persistence write
    to that writer through a backend adapter, so the one-writer contract holds.
  - It NEVER sends a raw alert. furnace Guardrail 7 makes alert-dedup.py the only
    path to the founder channel; this module routes holds and age-outs through an
    injected alert hook (default: an operator-only stdout note). No client-facing
    message is ever emitted (move in silence).

Secrecy: the held payload may carry contact detail; it is stored through the writer
and never printed. A redaction filter scrubs secret-shaped and contact-shaped
substrings from anything this module emits to a log or report.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Callable, Iterable, Optional, Protocol

# ---------------------------------------------------------------------------
# Constants (mirror furnace-design Section 8 and dashboard-design Section 5.2)
# ---------------------------------------------------------------------------

AGE_OUT_DAYS = 60  # queue_max_hold_days: hard 60-day maximum hold

# The four paid services that can report insufficient credits mid-run.
PAID_SERVICES = ("kie_ai", "ollama_cloud", "openrouter", "fish_audio")

INSUFFICIENT_CREDITS_CLASS = "insufficient_credits"

# Canonical SQLite forward-stage vocabulary (dashboard-design Section 5.2). These
# are the only stages a job may resume into.
FORWARD_STAGES = (
    "received",
    "researching",
    "writing",
    "in_qc",
    "generating_art",
    "producing_audio",
    "publishing",
    "enrolling",
)

# The terminal / holding states a job can never "resume into".
TERMINAL_OR_HOLD_STAGES = ("complete", "failed", "queued_credit_out", "aged_out")

# The webhook file-ledger uses a shorter vocabulary (webhook-design Section 3.2).
# PRD Section 6.5 requires the two layers stay in lockstep, so callers from either
# layer are accepted and normalized to the SQLite vocabulary above.
_LEDGER_TO_SQLITE = {
    "qc": "in_qc",
    "art": "generating_art",
    "audio": "producing_audio",
}

# Insufficient-credits signatures, compiled case-insensitively. Providers phrase the
# same condition many ways; a 402 status is the strongest single signal.
_CREDIT_PATTERNS = re.compile(
    r"(?:"
    r"insufficient(?:\s+|_)(?:credit|credits|balance|funds|quota)"
    r"|not\s+enough\s+credit"
    r"|out\s+of\s+credit"
    r"|no\s+credit(?:s)?\s+(?:left|remaining|available)"
    r"|payment\s+required"
    r"|exceeded\s+your\s+current\s+quota"
    r"|quota\s+exceeded"
    r"|top\s+up\s+your\s+(?:account|balance|wallet)"
    r"|add\s+(?:more\s+)?credit"
    r"|wallet\s+(?:is\s+)?empty"
    r"|balance\s+(?:is\s+)?too\s+low"
    r"|account\s+balance\s+is\s+(?:zero|0)"
    r")",
    re.IGNORECASE,
)

# Secret-shaped and contact-shaped patterns scrubbed from any emitted string.
_REDACT_PATTERNS = [
    re.compile(r"\bpit-[A-Za-z0-9._-]+"),
    re.compile(r"\bsk-[A-Za-z0-9._-]+"),
    re.compile(r"\b(?:Bearer|Authorization)\s+[A-Za-z0-9._-]+", re.IGNORECASE),
    re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
    re.compile(r"(?<!\d)(?:\+?\d[\s().-]?){9,}\d(?!\d)"),
]


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def _parse_iso(value: str) -> datetime:
    """Parse an ISO 8601 timestamp, tolerating a trailing Z and naive values."""
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def redact(text: str) -> str:
    """Scrub secret-shaped and contact-shaped substrings before emission."""
    if not text:
        return text
    out = text
    for pat in _REDACT_PATTERNS:
        out = pat.sub("[REDACTED]", out)
    return out


# ---------------------------------------------------------------------------
# Pure logic (no datastore, fully unit-testable)
# ---------------------------------------------------------------------------


def is_insufficient_credits(
    error: Optional[str] = None, status_code: Optional[int] = None
) -> bool:
    """Return True when an error is the insufficient-credits failure class.

    A 402 Payment Required status is authoritative on its own. Otherwise the error
    text is matched against the provider-agnostic credit signatures above.
    """
    if status_code == 402:
        return True
    if error and _CREDIT_PATTERNS.search(error):
        return True
    return False


def normalize_stage(stage: str) -> str:
    """Map a webhook-ledger stage name onto the canonical SQLite vocabulary."""
    if stage is None:
        raise ValueError("stage is required")
    key = stage.strip()
    return _LEDGER_TO_SQLITE.get(key, key)


def is_resumable_stage(stage: str) -> bool:
    """A job may only resume into a non-terminal forward stage."""
    return normalize_stage(stage) in FORWARD_STAGES


def compute_deadline(queued_at: str | datetime, hold_days: int = AGE_OUT_DAYS) -> str:
    """queue_deadline = queued_at + hold_days, precomputed for cheap queries."""
    base = queued_at if isinstance(queued_at, datetime) else _parse_iso(queued_at)
    return _iso(base + timedelta(days=hold_days))


def age_days(queued_at: str | datetime, now: Optional[datetime] = None) -> int:
    base = queued_at if isinstance(queued_at, datetime) else _parse_iso(queued_at)
    now = now or _now_utc()
    return max(0, (now - base).days)


def days_until_ageout(
    queued_at: str | datetime,
    now: Optional[datetime] = None,
    hold_days: int = AGE_OUT_DAYS,
) -> int:
    return hold_days - age_days(queued_at, now)


def is_aged_out(
    queued_at: str | datetime,
    now: Optional[datetime] = None,
    hold_days: int = AGE_OUT_DAYS,
) -> bool:
    return age_days(queued_at, now) >= hold_days


@dataclass
class HeldJob:
    """The queue-relevant projection of a job (a subset of podcast_jobs)."""

    job_id: str
    client_id: str
    queued_service: str
    queued_at: str
    resume_stage: str
    queue_state: str = "held"

    @property
    def deadline(self) -> str:
        return compute_deadline(self.queued_at)


def select_aged_out(
    held_jobs: Iterable[HeldJob],
    now: Optional[datetime] = None,
    hold_days: int = AGE_OUT_DAYS,
) -> list[HeldJob]:
    """Held jobs past the hold_days deadline, oldest first."""
    now = now or _now_utc()
    aged = [j for j in held_jobs if j.queue_state == "held" and is_aged_out(j.queued_at, now, hold_days)]
    return sorted(aged, key=lambda j: j.queued_at)


def select_drainable(
    held_jobs: Iterable[HeldJob], restored_services: Iterable[str]
) -> list[HeldJob]:
    """Held jobs whose depleted service has flipped back to funded, oldest first."""
    restored = {s for s in restored_services}
    drain = [j for j in held_jobs if j.queue_state == "held" and j.queued_service in restored]
    return sorted(drain, key=lambda j: j.queued_at)


# ---------------------------------------------------------------------------
# Persistence backend (writes delegated to the sole writer, podcast_state.py)
# ---------------------------------------------------------------------------


class StateBackend(Protocol):
    """The persistence surface the queue needs. Production wraps podcast_state.py."""

    def hold(
        self,
        job_id: str,
        client_id: str,
        service: str,
        resume_stage: str,
        queued_at: str,
        payload: Optional[dict],
        partial_state: Optional[dict],
    ) -> None: ...

    def resume(self, job_id: str) -> None: ...

    def age_out(self, job_id: str) -> None: ...

    def purge_payload(self, job_id: str) -> None: ...

    def list_held(self, client_id: Optional[str] = None) -> list[HeldJob]: ...


class MemoryBackend:
    """In-memory backend for tests and standalone dry runs. Not for production."""

    def __init__(self) -> None:
        self.jobs: dict[str, dict] = {}
        self.payloads: dict[str, dict] = {}

    def hold(self, job_id, client_id, service, resume_stage, queued_at, payload, partial_state):
        self.jobs[job_id] = {
            "job_id": job_id,
            "client_id": client_id,
            "queued_service": service,
            "queued_at": queued_at,
            "resume_stage": normalize_stage(resume_stage),
            "queue_state": "held",
            "status": "queued_credit_out",
            "queue_deadline": compute_deadline(queued_at),
        }
        if payload is not None or partial_state is not None:
            self.payloads[job_id] = {
                "payload_json": payload,
                "partial_state_json": partial_state,
            }

    def resume(self, job_id):
        job = self.jobs[job_id]
        job["queue_state"] = "resumed"
        job["status"] = job["resume_stage"]
        # Payload and partial state are RETAINED so the pipeline continues from
        # where it left off. Purge happens at age-out and, elsewhere, at
        # complete/failed (dashboard-design 10.2), never on resume.

    def age_out(self, job_id):
        job = self.jobs[job_id]
        job["queue_state"] = "aged_out"
        job["status"] = "failed"
        job["aged_out_at"] = _iso(_now_utc())
        self.purge_payload(job_id)

    def purge_payload(self, job_id):
        self.payloads.pop(job_id, None)

    def list_held(self, client_id=None):
        out = []
        for job in self.jobs.values():
            if job["queue_state"] != "held":
                continue
            if client_id and job["client_id"] != client_id:
                continue
            out.append(
                HeldJob(
                    job_id=job["job_id"],
                    client_id=job["client_id"],
                    queued_service=job["queued_service"],
                    queued_at=job["queued_at"],
                    resume_stage=job["resume_stage"],
                    queue_state="held",
                )
            )
        return out


class PodcastStateBackend:
    """Delegates every write to the sole writer, scripts/podcast_state.py.

    dashboard-design Section 5.4 defines the subcommands: hold, resume,
    sweep-aged-out, and (for reads) a queue listing. This adapter shells to that
    writer so the one-writer contract is never broken. Payload and partial state
    are handed to the writer via a temp file so no secret rides on argv.
    """

    def __init__(self, state_cmd: list[str]):
        # e.g. ["python3", "scripts/podcast_state.py"]
        self.state_cmd = list(state_cmd)

    def _run(self, args: list[str], stdin: Optional[str] = None) -> str:
        proc = subprocess.run(
            self.state_cmd + args,
            input=stdin,
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            raise RuntimeError(
                "podcast_state.py "
                + " ".join(args[:2])
                + " failed rc="
                + str(proc.returncode)
                + ": "
                + redact(proc.stderr.strip())
            )
        return proc.stdout

    def hold(self, job_id, client_id, service, resume_stage, queued_at, payload, partial_state):
        args = [
            "hold",
            "--job-id",
            job_id,
            "--service",
            service,
            "--resume-stage",
            normalize_stage(resume_stage),
        ]
        blob = None
        if payload is not None or partial_state is not None:
            blob = json.dumps(
                {"payload_json": payload, "partial_state_json": partial_state}
            )
            args += ["--payload-stdin"]
        self._run(args, stdin=blob)

    def resume(self, job_id):
        self._run(["resume", "--job-id", job_id])

    def age_out(self, job_id):
        # sweep-aged-out drops, purges the payload, and alerts in one writer call.
        self._run(["sweep-aged-out", "--job-id", job_id])

    def purge_payload(self, job_id):
        self._run(["purge-payload", "--job-id", job_id])

    def list_held(self, client_id=None):
        args = ["list", "--queue", "held", "--json"]
        if client_id:
            args += ["--client-id", client_id]
        raw = self._run(args)
        rows = json.loads(raw or "[]")
        return [
            HeldJob(
                job_id=r["job_id"],
                client_id=r["client_id"],
                queued_service=r.get("queued_service", ""),
                queued_at=r["queued_at"],
                resume_stage=r.get("resume_stage") or "received",
                queue_state="held",
            )
            for r in rows
        ]


# ---------------------------------------------------------------------------
# Alert routing (sole path is alert-dedup.py; default is operator stdout only)
# ---------------------------------------------------------------------------

AlertHook = Callable[[str, str, str, str, int], None]


def operator_stdout_alert(
    client_id: str, service: str, failure_class: str, message: str, affected: int
) -> None:
    """Default alert sink: an OPERATOR-only note on stdout. Never client-facing."""
    line = (
        "[OPERATOR ALERT] client="
        + client_id
        + " service="
        + service
        + " class="
        + failure_class
        + " affected="
        + str(affected)
        + " :: "
        + redact(message)
    )
    print(line, file=sys.stderr)


def make_alert_dedup_hook(alert_cmd: list[str]) -> AlertHook:
    """Route founder alerts through alert-dedup.py (furnace Guardrail 7).

    alert-dedup.py owns keying (client + service + failure_class), the 6-hour
    window, the storm cap, and the gateway-only Telegram path. This hook only
    hands it the key and payload; it never sends Telegram itself.
    """

    def _hook(client_id, service, failure_class, message, affected):
        subprocess.run(
            list(alert_cmd)
            + [
                "notify",
                "--client",
                client_id,
                "--service",
                service,
                "--failure-class",
                failure_class,
                "--affected",
                str(affected),
                "--message",
                redact(message),
            ],
            check=False,
        )

    return _hook


# ---------------------------------------------------------------------------
# The queue orchestrator
# ---------------------------------------------------------------------------


@dataclass
class CreditQueue:
    backend: StateBackend
    alert_hook: AlertHook = operator_stdout_alert
    hold_days: int = AGE_OUT_DAYS

    def hold(
        self,
        job_id: str,
        client_id: str,
        service: str,
        resume_stage: str,
        payload: Optional[dict] = None,
        partial_state: Optional[dict] = None,
        now: Optional[datetime] = None,
    ) -> dict:
        """Move a job to the credit-out queue, preserving full payload plus state.

        The job resumes at resume_stage when the depleted service is funded again.
        Exactly one first-occurrence founder alert is routed (dedup owns repeats).
        """
        if service not in PAID_SERVICES:
            raise ValueError("unknown paid service: " + str(service))
        if not is_resumable_stage(resume_stage):
            raise ValueError("resume_stage not a resumable forward stage: " + str(resume_stage))
        now = now or _now_utc()
        queued_at = _iso(now)
        self.backend.hold(
            job_id=job_id,
            client_id=client_id,
            service=service,
            resume_stage=normalize_stage(resume_stage),
            queued_at=queued_at,
            payload=payload,
            partial_state=partial_state,
        )
        affected = len(self.backend.list_held(client_id=client_id))
        self.alert_hook(
            client_id,
            service,
            INSUFFICIENT_CREDITS_CLASS,
            service + " reported insufficient credits. Episode held; will resume when funded.",
            affected,
        )
        return {
            "action": "held",
            "job_id": job_id,
            "service": service,
            "resume_stage": normalize_stage(resume_stage),
            "queued_at": queued_at,
            "queue_deadline": compute_deadline(queued_at, self.hold_days),
        }

    def resume(self, job_id: str) -> dict:
        """Event-driven resume (operator marks credits restored for one job)."""
        self.backend.resume(job_id)
        return {"action": "resumed", "job_id": job_id}

    def age_check_and_drain(
        self,
        restored_services: Optional[Iterable[str]] = None,
        client_id: Optional[str] = None,
        now: Optional[datetime] = None,
    ) -> dict:
        """The daily maintenance pass, invoked by podcast-smoke-test.py only.

        1. Age out every held job past its 60-day deadline (drop, purge payload,
           one aged-out founder notice per job through the alert hook).
        2. Drain every held job whose depleted service has flipped back to funded.

        Returns a summary the smoke test logs. Creates no cron of its own.
        """
        now = now or _now_utc()
        restored = list(restored_services or [])
        held = self.backend.list_held(client_id=client_id)

        aged = select_aged_out(held, now, self.hold_days)
        aged_ids = []
        for job in aged:
            self.backend.age_out(job.job_id)
            self.alert_hook(
                job.client_id,
                job.queued_service,
                "queue_aged_out",
                "Held episode aged out at the 60-day maximum and was dropped; payload purged.",
                1,
            )
            aged_ids.append(job.job_id)

        # Recompute after age-out so a just-dropped job is never also drained.
        still_held = [j for j in held if j.job_id not in set(aged_ids)]
        drainable = select_drainable(still_held, restored)
        resumed_ids = []
        for job in drainable:
            self.backend.resume(job.job_id)
            resumed_ids.append(job.job_id)

        if resumed_ids and restored:
            for svc in restored:
                svc_jobs = [j.job_id for j in drainable if j.queued_service == svc]
                if svc_jobs:
                    self.alert_hook(
                        client_id or (drainable[0].client_id if drainable else ""),
                        svc,
                        "service_restored",
                        svc + " restored; " + str(len(svc_jobs)) + " queued episode(s) resuming.",
                        len(svc_jobs),
                    )

        return {
            "checked": len(held),
            "aged_out": aged_ids,
            "resumed": resumed_ids,
            "restored_services": restored,
            "checked_at": _iso(now),
        }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_backend(args) -> StateBackend:
    if args.backend == "memory":
        return MemoryBackend()
    if args.backend == "state":
        state_cmd = args.state_cmd.split() if args.state_cmd else ["python3", "scripts/podcast_state.py"]
        return PodcastStateBackend(state_cmd)
    raise SystemExit("unknown backend: " + args.backend)


def _build_alert_hook(args) -> AlertHook:
    if args.alert_cmd:
        return make_alert_dedup_hook(args.alert_cmd.split())
    return operator_stdout_alert


def _load_json_arg(value: Optional[str]) -> Optional[dict]:
    if not value:
        return None
    if value == "-":
        return json.load(sys.stdin)
    if os.path.exists(value):
        with open(value, "r", encoding="utf-8") as fh:
            return json.load(fh)
    return json.loads(value)


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="credit_queue.py",
        description="Credit-out queue mechanics (hold, resume, daily age-check, 60-day age-out).",
    )
    parser.add_argument("--backend", choices=["memory", "state"], default="state")
    parser.add_argument(
        "--state-cmd",
        default="",
        help="command that runs podcast_state.py, e.g. 'python3 scripts/podcast_state.py'",
    )
    parser.add_argument(
        "--alert-cmd",
        default="",
        help="command that runs alert-dedup.py; omit for operator-stdout alerts",
    )
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--json", action="store_true", help="emit machine-readable output")
    sub = parser.add_subparsers(dest="command", required=True)

    p_classify = sub.add_parser("classify", parents=[common], help="report whether an error is the insufficient-credits class")
    p_classify.add_argument("--error", default="")
    p_classify.add_argument("--status-code", type=int, default=None)

    p_hold = sub.add_parser("hold", parents=[common], help="hold a job in the credit-out queue")
    p_hold.add_argument("--job-id", required=True)
    p_hold.add_argument("--client-id", required=True)
    p_hold.add_argument("--service", required=True, choices=list(PAID_SERVICES))
    p_hold.add_argument("--resume-stage", required=True)
    p_hold.add_argument("--payload", default="", help="inline JSON, a file path, or - for stdin")
    p_hold.add_argument("--partial-state", default="", help="inline JSON, a file path, or - for stdin")

    p_resume = sub.add_parser("resume", parents=[common], help="resume one held job (credits restored)")
    p_resume.add_argument("--job-id", required=True)

    p_age = sub.add_parser(
        "age-check",
        parents=[common],
        help="daily maintenance: age out 60-day holds and drain restored services (smoke-test only)",
    )
    p_age.add_argument("--client-id", default=None)
    p_age.add_argument(
        "--restored-service",
        action="append",
        default=[],
        help="a service that has flipped back to funded; repeatable",
    )

    args = parser.parse_args(argv)

    if args.command == "classify":
        verdict = is_insufficient_credits(args.error or None, args.status_code)
        out = {"insufficient_credits": verdict}
        print(json.dumps(out) if args.json else ("YES" if verdict else "NO"))
        return 0 if verdict else 1

    backend = _build_backend(args)
    queue = CreditQueue(backend=backend, alert_hook=_build_alert_hook(args))

    try:
        if args.command == "hold":
            result = queue.hold(
                job_id=args.job_id,
                client_id=args.client_id,
                service=args.service,
                resume_stage=args.resume_stage,
                payload=_load_json_arg(args.payload),
                partial_state=_load_json_arg(args.partial_state),
            )
        elif args.command == "resume":
            result = queue.resume(args.job_id)
        elif args.command == "age-check":
            result = queue.age_check_and_drain(
                restored_services=args.restored_service,
                client_id=args.client_id,
            )
        else:  # pragma: no cover
            parser.error("unknown command")
            return 2
    except ValueError as exc:
        print(redact(str(exc)), file=sys.stderr)
        return 3

    print(json.dumps(result, indent=2) if args.json else redact(json.dumps(result)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
