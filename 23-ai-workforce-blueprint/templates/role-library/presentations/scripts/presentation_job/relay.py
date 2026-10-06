"""PRES-052 — supervised, acknowledged event relay for Claude host transports.

The defect: the Claude notification path (51-signature-presentation
``bin/presentation-outbox-queue`` + "relay those rows yourself when the run
finishes" in the three host adapters) is a finish-only queue. Rows land in
``working/outbox.jsonl`` with no identity, no delivery state, no
acknowledgement, no resume reconciliation, and no live view: a host that
relays at the end cannot show stage/waiting/stalled/retrying/progress while
the job runs, and a queued row reads as if the client was notified.

This module is the fix:

* typed scoped identity on every row — company / presentation / run /
  task / stage / event id, plus revision;
* durable delivery state per row — queued, acknowledged per destination
  (local host vs Command Center), lease holder/expiry, retry deadline;
* no cwd guessing — the run dir is explicit (state store), never inferred;
* local and CC destinations acknowledge SEPARATELY — a CC outage never
  suppresses local progress;
* reconcile-on-resume — pending rows re-queue, acknowledged rows stay
  acknowledged, the logical display deduplicates retries;
* transport readiness by PROBE, not by executable presence — an installed
  but unready OpenClaw gateway (or an unauthenticated board) reports
  NOT READY;
* queued is not delivered — nothing here can certify "client notified"
  from a queued-only row;
* never touches Telegram credentials — no ``*BOT_TOKEN*`` env is read,
  no api.telegram.org call exists in this file; the default local channel
  is the host viewer itself.

File layout (all under the run dir, so two companies / two decks can
never read each other rows — isolation is the directory):

* ``working/relay/ledger.jsonl`` — one JSON row per emit AND per retry
  attempt (retries retained, never overwritten);
* ``working/relay/display.json`` — the deduped LOGICAL view:
  ``{event_id: latest visible row}`` — retries update one key, so the
  display never duplicates logical progress.

Concurrency: every mutation goes through the caller's StateStore.save
(state.json, atomic) for the seq/revision counters; the jsonl append is
O_APPEND (single-writer engine under RunLock in production). Readers
(viewer, --relay-status) never lock.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

SCHEMA = "pres-relay-v1"

#: Delivery states. ``queued`` is the initial state and is NEVER a delivery
#: claim — see certify_notified().
STATE_QUEUED = "queued"
STATE_ACKED_LOCAL = "acked_local"
STATE_ACKED_CC = "acked_cc"
STATE_ACKED_BOTH = "acked_both"
STATE_TIMEOUT = "timeout"

#: Row kinds the engine emits. Free-form kinds from callers are passed
#: through; these are the ones the viewer renders with dedicated labels.
KIND_SESSION_OPEN = "session_open"
KIND_STAGE_START = "stage_start"
KIND_STAGE_DONE = "stage_done"
KIND_WAITING_CONFIG = "waiting_configuration"
KIND_STALLED = "stalled"
KIND_RETRYING = "retrying"
KIND_PROGRESS = "progress"
KIND_BLOCKED = "blocked"
KIND_ACK = "ack"
KIND_DONE = "done"

#: report.py dispatch kinds map onto relay kinds 1:1 for these names.
DISPATCH_KINDS = ("ack", "progress", "blocked", "done")

#: After this many unacknowledged attempts a row becomes visibly TIMEOUT
#: (retained, never dropped).
MAX_ATTEMPTS = 5

RELAY_DIRNAME = "relay"
LEDGER_NAME = "ledger.jsonl"
DISPLAY_NAME = "display.json"


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def ack_timeout_s(env: Optional[Dict[str, str]] = None) -> float:
    """Seconds before an unacknowledged row needs a retry.

    Env ``PRESENTATION_RELAY_ACK_TIMEOUT_S``, default 30. Non-positive or
    unparsable values fall back to the default — a zero timeout would mark
    everything timed-out instantly.
    """
    src = os.environ if env is None else env
    try:
        val = float(src.get("PRESENTATION_RELAY_ACK_TIMEOUT_S", "") or 0)
    except (TypeError, ValueError):
        return 30.0
    return val if val > 0 else 30.0


def _relay_dir(run_dir: Path) -> Path:
    return Path(run_dir) / "working" / RELAY_DIRNAME


def _ledger_path(run_dir: Path) -> Path:
    return _relay_dir(run_dir) / LEDGER_NAME


def _display_path(run_dir: Path) -> Path:
    return _relay_dir(run_dir) / DISPLAY_NAME


def scope(state: Dict[str, Any], run_dir: Path) -> Dict[str, str]:
    """Typed scoped identity for this run. Never guesses, never invents.

    company      — state intake client/client_name, else "operator"
    presentation — state intake deck_slug, else the run dir name
    run_id       — state job_id, else the run dir name
    run_name     — the run dir name (filesystem identity)
    """
    intake = state.get("intake") if isinstance(state.get("intake"), dict) else {}
    company = str(
        (intake.get("client") if isinstance(intake, dict) else "")
        or (intake.get("client_name") if isinstance(intake, dict) else "")
        or state.get("client_name")
        or state.get("client")
        or "operator"
    )
    presentation = str(
        (intake.get("deck_slug") if isinstance(intake, dict) else "")
        or Path(state.get("run_dir") or run_dir).name
        or Path(run_dir).name
    )
    run_id = str(state.get("job_id") or Path(run_dir).name)
    return {
        "company": company,
        "presentation": presentation,
        "run_id": run_id,
        "run_name": Path(run_dir).name,
    }


def _next_seq(state: Dict[str, Any]) -> int:
    relay = state.get("relay") if isinstance(state.get("relay"), dict) else {}
    try:
        return int(relay.get("seq", 0)) + 1
    except (TypeError, ValueError):
        return 1


def _revision(state: Dict[str, Any]) -> int:
    relay = state.get("relay") if isinstance(state.get("relay"), dict) else {}
    try:
        return int(relay.get("revision", 1))
    except (TypeError, ValueError):
        return 1


def _append_ledger(run_dir: Path, row: Dict[str, Any]) -> None:
    d = _relay_dir(run_dir)
    d.mkdir(parents=True, exist_ok=True)
    with open(_ledger_path(run_dir), "a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, sort_keys=True, default=str) + "\n")


def _read_ledger(run_dir: Path) -> List[Dict[str, Any]]:
    p = _ledger_path(run_dir)
    if not p.is_file():
        return []
    rows: List[Dict[str, Any]] = []
    try:
        with open(p, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except ValueError:
                    continue
                if isinstance(obj, dict):
                    rows.append(obj)
    except OSError:
        return []
    return rows


def _write_display(run_dir: Path, display: Dict[str, Any]) -> None:
    d = _relay_dir(run_dir)
    d.mkdir(parents=True, exist_ok=True)
    tmp = _display_path(run_dir).with_suffix(".json.tmp")
    try:
        tmp.write_text(json.dumps(display, indent=2, sort_keys=True, default=str),
                       encoding="utf-8")
        os.replace(tmp, _display_path(run_dir))
    except OSError:
        try:
            tmp.unlink()
        except OSError:
            pass


def read_display(run_dir: Path) -> Dict[str, Any]:
    """The deduped logical view. Rebuilt from the ledger when absent."""
    p = _display_path(run_dir)
    if p.is_file():
        try:
            obj = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(obj, dict):
                return obj
        except (ValueError, OSError):
            pass
    # No display file (older run, or deleted): rebuild from the ledger so a
    # resume never reports "no progress" for work the ledger proves.
    display: Dict[str, Any] = {}
    for row in _read_ledger(run_dir):
        eid = row.get("event_id")
        if eid:
            display[str(eid)] = _visible_row(row)
    return display


def _visible_row(row: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "event_id": row.get("event_id"),
        "seq": row.get("seq"),
        "kind": row.get("kind"),
        "stage": row.get("stage"),
        # Typed scoped identity stays on the logical view: retry rows and
        # the two-client isolation checks read the SCOPED IDs from here,
        # never from a guessed path.
        "company": row.get("company", ""),
        "presentation": row.get("presentation", ""),
        "run_id": row.get("run_id", ""),
        "task_id": row.get("task_id", ""),
        "revision": row.get("revision"),
        "state": row.get("state"),
        "attempts_local": row.get("attempts_local", 0),
        "attempts_cc": row.get("attempts_cc", 0),
        "retry_not_before": row.get("retry_not_before"),
        "display_text": row.get("display_text", ""),
        "updated_at": row.get("created_at"),
    }


def _payload_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _lease_snapshot(run_dir: Path) -> Dict[str, str]:
    """Read-only lease holder snapshot. Absent lease = empty holder."""
    p = Path(run_dir) / "working" / ".lease.json"
    if not p.is_file():
        return {"holder": "", "expires_at": ""}
    try:
        doc = json.loads(p.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return {"holder": "", "expires_at": ""}
    if not isinstance(doc, dict):
        return {"holder": "", "expires_at": ""}
    holder = doc.get("holder") or doc.get("who") or ""
    if isinstance(holder, dict):
        holder = str(holder.get("who") or holder.get("pid") or "")
    return {"holder": str(holder or ""),
            "expires_at": str(doc.get("expires_at") or doc.get("expires") or "")}


def emit(state: Dict[str, Any], run_dir: Path, kind: str, display_text: str,
         *, stage: str = "", task_id: str = "",
         store: Any = None) -> Dict[str, Any]:
    """Emit one logical event. Never raises — a relay failure must never
    break a run (the engine's own state/events remain the source of truth).

    Returns the row (with ``relayed: False`` when persistence failed).
    """
    try:
        return _emit(state, run_dir, kind, display_text,
                     stage=stage, task_id=task_id, store=store)
    except Exception:  # noqa: BLE001 — relay is best-effort, never fatal
        return {"event_id": "", "state": STATE_QUEUED, "relayed": False}


def _emit(state: Dict[str, Any], run_dir: Path, kind: str, display_text: str,
          *, stage: str, task_id: str, store: Any) -> Dict[str, Any]:
    run_dir = Path(run_dir)
    sc = scope(state, run_dir)
    seq = _next_seq(state)
    rev = _revision(state)
    timeout = ack_timeout_s()
    now = _now_iso()
    lease = _lease_snapshot(run_dir)
    row = {
        "schema": SCHEMA,
        "company": sc["company"],
        "presentation": sc["presentation"],
        "run_id": sc["run_id"],
        "run_name": sc["run_name"],
        "task_id": task_id,
        "stage": stage,
        "event_id": uuid.uuid4().hex[:16],
        "seq": seq,
        "revision": rev,
        "kind": kind,
        "state": STATE_QUEUED,
        "created_at": now,
        "lease_holder": lease["holder"],
        "lease_expires_at": lease["expires_at"],
        "retry_not_before": now,
        "ack_timeout_s": timeout,
        "attempts_local": 0,
        "attempts_cc": 0,
        "acked_local_at": "",
        "acked_cc_at": "",
        "payload_hash": _payload_hash(f"{kind}\x00{stage}\x00{display_text}"),
        "display_text": display_text,
    }
    _append_ledger(run_dir, row)
    display = read_display(run_dir)
    display[row["event_id"]] = _visible_row(row)
    _write_display(run_dir, display)
    relay = state.setdefault("relay", {})
    if isinstance(relay, dict):
        relay["seq"] = seq
        relay["revision"] = rev
        relay["last_event_at"] = now
    if store is not None:
        try:
            store.save(state)
        except Exception:  # noqa: BLE001 — state save failure is the
            pass           # engine's problem, not the relay's
    row["relayed"] = True
    return row


def session_open(state: Dict[str, Any], run_dir: Path,
                 store: Any = None) -> Dict[str, Any]:
    """Open (or re-open) the supervised session. Bumps the revision when a
    prior session exists so resume rows are distinguishable from first-run
    rows without duplicating logical progress."""
    relay = state.get("relay") if isinstance(state.get("relay"), dict) else {}
    if relay.get("seq"):
        try:
            state.setdefault("relay", {})["revision"] = _revision(state) + 1
        except Exception:  # noqa: BLE001
            pass
    sc = scope(state, run_dir)
    return emit(state, run_dir, KIND_SESSION_OPEN,
                f"Relay session open for {sc['presentation']} "
                f"(run {sc['run_name']}, revision {_revision(state)}). "
                f"Supervised viewer active from job start — queued is not delivered.",
                store=store)


def observe_dispatch(state: Dict[str, Any], run_dir: Path, kind: str,
                     message: str, outcome: str,
                     *, stage: str = "", store: Any = None) -> Dict[str, Any]:
    """Record a report.py dispatch outcome as a relay row.

    outcome in {"pass", "fail", "undetermined"} (CheckResult value).
    PASS on the local transport acknowledges the matching logical event;
    anything else leaves it queued with a visible retry deadline — an
    acknowledgement timeout is therefore VISIBLE, never silent.
    """
    relay_kind = kind if kind in DISPATCH_KINDS else KIND_PROGRESS
    if outcome == "pass":
        text = f"[{relay_kind}] {message} — acknowledged (local)."
        row = emit(state, run_dir, relay_kind, text, stage=stage, store=None)
        try:
            ack_local(state, run_dir, row["event_id"], store=store)
            row = dict(row)
            row["state"] = STATE_ACKED_LOCAL
        except Exception:  # noqa: BLE001
            pass
        return row
    if outcome == "fail":
        text = (f"[{relay_kind}] {message} — NO TRANSPORT (queued, "
                f"not delivered; retry on sweep).")
    else:
        text = (f"[{relay_kind}] {message} — outcome {outcome} (queued, "
                f"acknowledgement pending; retry deadline "
                f"{ack_timeout_s():.0f}s).")
    return emit(state, run_dir, relay_kind, text, stage=stage, store=store)


def ack_local(state: Dict[str, Any], run_dir: Path, event_id: str,
              store: Any = None) -> bool:
    """Acknowledge one logical event on the LOCAL destination."""
    return _ack(state, run_dir, event_id, "local", store)


def ack_cc(state: Dict[str, Any], run_dir: Path, event_id: str,
           store: Any = None) -> bool:
    """Acknowledge one logical event on the CC destination. Independent of
    the local ack — a CC outage never suppresses local progress."""
    return _ack(state, run_dir, event_id, "cc", store)


def _ack(state: Dict[str, Any], run_dir: Path, event_id: str, dest: str,
         store: Any) -> bool:
    run_dir = Path(run_dir)
    rows = _read_ledger(run_dir)
    target = None
    for row in reversed(rows):
        if str(row.get("event_id") or "") == event_id:
            target = row
            break
    now = _now_iso()
    if target is None:
        return False
    prev = target.get("state") or STATE_QUEUED
    if dest == "local":
        target["attempts_local"] = int(target.get("attempts_local") or 0) + 1
        target["acked_local_at"] = now
        target["state"] = (STATE_ACKED_BOTH if prev == STATE_ACKED_CC
                           else STATE_ACKED_LOCAL)
    else:
        target["attempts_cc"] = int(target.get("attempts_cc") or 0) + 1
        target["acked_cc_at"] = now
        target["state"] = (STATE_ACKED_BOTH if prev == STATE_ACKED_LOCAL
                           else STATE_ACKED_CC)
    target["created_at"] = target.get("created_at") or now
    _append_ledger(run_dir, dict(target))
    display = read_display(run_dir)
    display[event_id] = _visible_row(target)
    _write_display(run_dir, display)
    if store is not None:
        try:
            store.save(state)
        except Exception:  # noqa: BLE001
            pass
    return True


def note_attempt(state: Dict[str, Any], run_dir: Path, event_id: str,
                 dest: str, *, store: Any = None) -> bool:
    """Record one unacknowledged attempt: bumps the attempt counter, pushes
    the retry deadline out with bounded backoff, retains the retry row."""
    run_dir = Path(run_dir)
    rows = _read_ledger(run_dir)
    target = None
    for row in reversed(rows):
        if str(row.get("event_id") or "") == event_id:
            target = row
            break
    if target is None:
        return False
    if target.get("state") in (STATE_ACKED_LOCAL, STATE_ACKED_CC, STATE_ACKED_BOTH):
        return True  # already acknowledged — no retry row
    now_ts = time.time()
    timeout = ack_timeout_s()
    if dest == "cc":
        target["attempts_cc"] = int(target.get("attempts_cc") or 0) + 1
        attempts = int(target["attempts_cc"])
    else:
        target["attempts_local"] = int(target.get("attempts_local") or 0) + 1
        attempts = int(target["attempts_local"])
    if attempts >= MAX_ATTEMPTS:
        target["state"] = STATE_TIMEOUT
        target["display_text"] = (
            (target.get("display_text") or "")
            + f" — ACK TIMEOUT after {attempts} attempts (visible, retained; "
              "re-emit a new event to retry, this row will not certify delivery).")
    else:
        backoff = min(timeout * (2 ** max(0, attempts - 1)), 3600.0)
        target["retry_not_before"] = datetime.fromtimestamp(
            now_ts + backoff, tz=timezone.utc).astimezone().isoformat(timespec="seconds")
    _append_ledger(run_dir, dict(target))
    display = read_display(run_dir)
    display[event_id] = _visible_row(target)
    _write_display(run_dir, display)
    if store is not None:
        try:
            store.save(state)
        except Exception:  # noqa: BLE001
            pass
    return True


def reconcile(state: Dict[str, Any], run_dir: Path,
              store: Any = None) -> Dict[str, Any]:
    """Reconcile pending events on resume. Idempotent.

    * acknowledged rows (either destination) are skipped — never re-queued,
      never duplicated in the logical display;
    * queued rows whose retry deadline passed get one retry row each
      (attempt counters retained across the outage);
    * timed-out rows stay visible, never resurrected silently.
    """
    run_dir = Path(run_dir)
    display = read_display(run_dir)
    now_ts = time.time()
    requeued = 0
    skipped_acked = 0
    pending = 0
    timed_out = 0
    for event_id, vis in list(display.items()):
        st = vis.get("state")
        if st in (STATE_ACKED_LOCAL, STATE_ACKED_CC, STATE_ACKED_BOTH):
            skipped_acked += 1
            continue
        if st == STATE_TIMEOUT:
            timed_out += 1
            continue
        pending += 1
        try:
            not_before = datetime.fromisoformat(
                str(vis.get("retry_not_before") or "")).timestamp()
        except (ValueError, TypeError):
            not_before = 0.0
        if now_ts >= not_before:
            # One retry row, same logical event id — the display key is
            # unchanged, so logical progress cannot duplicate.
            retry_row = {
                "schema": SCHEMA,
                # Re-derive the scoped identity from STATE (the run's own
                # typed ids), never from a display row that may only carry
                # a truncated visible view — a retry row must stay scoped.
                "company": vis.get("company") or scope(state, run_dir)["company"],
                "presentation": vis.get("presentation")
                               or scope(state, run_dir)["presentation"],
                "run_id": (scope(state, run_dir))["run_id"],
                "run_name": Path(run_dir).name,
                "task_id": vis.get("task_id", "") or "",
                "stage": vis.get("stage", ""),
                "event_id": event_id,
                "seq": _next_seq(state),
                "revision": _revision(state),
                "kind": vis.get("kind", KIND_PROGRESS),
                "state": STATE_QUEUED,
                "created_at": _now_iso(),
                "lease_holder": _lease_snapshot(run_dir)["holder"],
                "lease_expires_at": "",
                "retry_not_before": _now_iso(),
                "ack_timeout_s": ack_timeout_s(),
                "attempts_local": vis.get("attempts_local", 0),
                "attempts_cc": vis.get("attempts_cc", 0),
                "payload_hash": "",
                "display_text": (vis.get("display_text") or "")
                                + " — re-queued on resume (no ack recorded).",
                "reconciled": True,
            }
            if isinstance(state.get("relay"), dict):
                state["relay"]["seq"] = retry_row["seq"]
            _append_ledger(run_dir, retry_row)
            requeued += 1
    if store is not None:
        try:
            store.save(state)
        except Exception:  # noqa: BLE001
            pass
    summary = {
        "requeued": requeued,
        "skipped_acked": skipped_acked,
        "pending": pending,
        "timed_out": timed_out,
        "logical_events": len(display),
    }
    emit(state, run_dir, KIND_PROGRESS,
         f"Relay reconcile on resume: {requeued} re-queued, "
         f"{skipped_acked} acknowledged (kept), {timed_out} timed-out "
         f"(retained), {len(display)} logical events total. "
         "No lost or duplicated logical progress.",
         store=store)
    return summary


def certify_notified(run_dir: Path) -> Tuple[bool, str]:
    """Can ANY row certify the client was notified? A queued-only receipt
    NEVER certifies — only a recorded acknowledgement does."""
    display = read_display(run_dir)
    for vis in display.values():
        if vis.get("kind") in (KIND_SESSION_OPEN,) and len(display) == 1:
            continue
        if vis.get("state") in (STATE_ACKED_LOCAL, STATE_ACKED_CC, STATE_ACKED_BOTH):
            return True, (
                f"client notified: YES — event {vis.get('event_id')} "
                f"acknowledged ({vis.get('state')}).")
    if not display:
        return False, "client notified: NO — no relay events recorded."
    return False, ("client notified: NO — rows are queued only; a queued "
                   "receipt cannot certify the client was notified.")


# ---------------------------------------------------------------------------
# Transport readiness — by probe, never by executable presence.
# ---------------------------------------------------------------------------

def probe_openclaw_gateway(env: Optional[Dict[str, str]] = None,
                           timeout_s: float = 0.0) -> Dict[str, Any]:
    """Probe the OpenClaw gateway transport for REAL readiness.

    ``shutil.which("openclaw")`` resolving is necessary but NOT sufficient:
    an installed-but-unready gateway (no listener, no auth, broken CLI)
    must report NOT READY. The probe runs the real CLI in dry-run mode so
    nothing is ever sent.

    Default timeout 60 s: a live gateway dry-run was measured at ~40 s wall
    on the operator box, so a 10 s bound would misreport a healthy-but-slow
    gateway as UNREADY. Override with PRESENTATION_RELAY_PROBE_TIMEOUT_S.
    """
    src = os.environ if env is None else env
    if timeout_s <= 0:
        try:
            timeout_s = float(src.get("PRESENTATION_RELAY_PROBE_TIMEOUT_S") or 0)
        except (TypeError, ValueError):
            timeout_s = 0.0
        if timeout_s <= 0:
            timeout_s = 60.0
    # shutil.which consults os.environ's PATH; when a caller injects an
    # isolated env (hermetic tests), resolve against THAT path instead so
    # the probe measures the injected world, not the ambient one.
    path = src.get("PATH") if isinstance(src, dict) else None
    cli = shutil.which("openclaw", path=path)
    if not cli:
        return {"name": "openclaw-gateway", "ready": False,
                "detail": "openclaw CLI not found on PATH."}
    channel = (src.get("PRESENTATION_NOTIFY_CHANNEL") or "telegram").strip() \
        or "telegram"
    argv = [cli, "message", "send", "--channel", channel,
            "--target", "0", "--message", "relay readiness probe",
            "--json", "--dry-run"]
    try:
        proc = subprocess.run(argv, shell=False, capture_output=True,
                              text=True, timeout=timeout_s)
    except subprocess.TimeoutExpired:
        return {"name": "openclaw-gateway", "ready": False,
                "detail": f"openclaw CLI present at {cli} but the readiness "
                          f"probe timed out after {timeout_s:.0f}s — "
                          "installed but UNREADY."}
    except OSError as exc:
        return {"name": "openclaw-gateway", "ready": False,
                "detail": f"openclaw CLI present at {cli} but cannot be "
                          f"executed ({exc}) — installed but UNREADY."}
    if proc.returncode != 0:
        detail = ((proc.stderr or proc.stdout) or "").strip()[:200]
        return {"name": "openclaw-gateway", "ready": False,
                "detail": f"openclaw CLI present at {cli} but the readiness "
                          f"probe exited {proc.returncode} ({detail}) — "
                          "installed but UNREADY."}
    return {"name": "openclaw-gateway", "ready": True,
            "detail": f"openclaw gateway probe accepted (dry-run) via {cli}."}


def probe_cc(env: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """Probe the Command Center destination. Ready requires a configured
    board URL AND an authenticated identity (token) — a URL alone, or an
    executable somewhere, never counts."""
    src = dict(os.environ) if env is None else dict(env)
    base = (src.get("COMMAND_CENTER_URL")
            or src.get("MISSION_CONTROL_URL") or "").strip().rstrip("/")
    if not base:
        return {"name": "cc-board", "ready": False,
                "detail": "CC board disabled "
                          "(COMMAND_CENTER_URL/MISSION_CONTROL_URL unset)."}
    token = (src.get("CC_API_TOKEN") or src.get("MC_API_TOKEN") or "").strip()
    if not token:
        return {"name": "cc-board", "ready": False,
                "detail": f"CC board URL {base} is configured but no "
                          "authenticated identity (CC_API_TOKEN/MC_API_TOKEN "
                          "unset) — NOT READY."}
    return {"name": "cc-board", "ready": True,
            "detail": f"CC board configured at {base} with an authenticated "
                      "identity (token present, value never logged)."}


def probe_local(run_dir: Path) -> Dict[str, Any]:
    """The local host destination (file ledger + supervised viewer). Always
    ready when the run dir is writable — it is DURABILITY, never a delivery
    certificate (see certify_notified)."""
    try:
        _relay_dir(Path(run_dir)).mkdir(parents=True, exist_ok=True)
        return {"name": "local-viewer", "ready": True,
                "detail": f"local relay ledger writable at "
                          f"{_ledger_path(run_dir)} (durability only — "
                          "queued is not delivered)."}
    except OSError as exc:
        return {"name": "local-viewer", "ready": False,
                "detail": f"local relay ledger not writable: {exc}."}


def probe_transports(run_dir: Path,
                     env: Optional[Dict[str, str]] = None) -> List[Dict[str, Any]]:
    """Readiness for every destination, by probe. Local and CC are
    independent — a CC failure never affects the local verdict."""
    return [probe_local(run_dir),
            probe_openclaw_gateway(env),
            probe_cc(env)]


# ---------------------------------------------------------------------------
# Supervised viewer — the "watch from job start" surface.
# ---------------------------------------------------------------------------

_STATE_LABEL = {
    STATE_QUEUED: "QUEUED (not delivered)",
    STATE_ACKED_LOCAL: "ACKED local",
    STATE_ACKED_CC: "ACKED cc",
    STATE_ACKED_BOTH: "ACKED local+cc",
    STATE_TIMEOUT: "TIMEOUT (visible, retained)",
}


def render_status(run_dir: Path, state: Optional[Dict[str, Any]] = None,
                  env: Optional[Dict[str, str]] = None) -> str:
    """Human-readable supervised view: per-stage delivery state, transport
    readiness, and the honest client-notified verdict. Safe to poll from job
    start — it reads files only, takes no lock."""
    run_dir = Path(run_dir)
    lines = [f"relay status: run {run_dir.name}"]
    if state is None:
        sp = run_dir / "state.json"
        if sp.is_file():
            try:
                state = json.loads(sp.read_text(encoding="utf-8"))
            except (ValueError, OSError):
                state = {}
        else:
            state = {}
    assert isinstance(state, dict)
    sc = scope(state, run_dir)
    lines.append(f"scope: company={sc['company']} "
                 f"presentation={sc['presentation']} run_id={sc['run_id']}")
    lines.append("transports (by probe, not by executable presence):")
    for probe in probe_transports(run_dir, env):
        mark = "READY" if probe["ready"] else "NOT READY"
        lines.append(f"  [{mark}] {probe['name']}: {probe['detail']}")
    display = read_display(run_dir)
    if not display:
        lines.append("events: none yet (viewer active — rows appear from job start).")
    else:
        lines.append(f"events: {len(display)} logical "
                     "(retries update one row each — no duplicates):")
        for vis in sorted(display.values(), key=lambda v: (v.get("seq") or 0)):
            label = _STATE_LABEL.get(vis.get("state") or "", vis.get("state"))
            lines.append(f"  #{vis.get('seq')} [{label}] "
                         f"{vis.get('kind')}/{vis.get('stage') or '-'}: "
                         f"{vis.get('display_text') or ''}")
    ok, verdict = certify_notified(run_dir)
    lines.append(verdict)
    _ = ok
    return "\n".join(lines) + "\n"
