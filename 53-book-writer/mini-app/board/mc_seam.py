#!/usr/bin/env python3
# =============================================================================
# BOOK WRITER MINI-APP (Wave C) :: U16 — MC BOARD SEAM (marketing kanban,
# fail-soft)
# -----------------------------------------------------------------------------
# mini-app/board/mc_seam.py
#
# The ONE seam that wires the Book Writer mini-app's run lifecycle onto the
# shared Command Center board card helper (53-book-writer/scripts/mc_board.py,
# a byte-for-byte vendored copy of 50-email-engine/mc_board.py). It encodes the
# mini-app's board conventions so the box-side ingest / pipeline code never has
# to repeat them:
#
#   START          -> begin_run: open ONE card on the MARKETING tasks lane
#                     (backlog -> in_progress). The resolved real department
#                     slug is `marketing` (WIRING-SPEC section 8 + master-plan
#                     section 6: skill-53 maps to "marketing"; an unrecognized
#                     slug would silently drop the card, so we never pass one).
#   PER-ANSWER     -> card_advance(phase_id="intake-<qid>", status="in_progress",
#                     note="answer recorded <qid>") — the per-answer heartbeat.
#   PIPELINE DONE  -> complete_run(status="review", deliverable_url=...) —
#                     NEVER "done". THE BOARD CONTRACT: only the independent QC
#                     scorer promotes review -> done (PASS >= 8.5). A producer
#                     that posted "done" would skip the QC column.
#   GATE FAILURE   -> block_run(phase_id, af_code) — a failed run is VISIBLE
#                     on the board (blocked), never stranded at in_progress.
#
# FAIL-SOFT (binding, master-plan section 8):
#   A board outage / missing COMMAND_CENTER_URL / HTTP error is CAUGHT, logged
#   to stderr, and the run CONTINUES. The board is a VIEW, never a gate. Every
#   public function returns a value and NEVER raises. Crucially, a board outage
#   never loses the run's staging: the seam records a LOCAL phase -> board-
#   receipt mapping (run/checkpoints/mc-board-seam.json) on EVERY call
#   regardless of the board's answer, so a later reconcile can distinguish
#   "card landed" from "board was down" and nothing is silently dropped.
#
# GATE-RECEIPTS MAPPING:
#   run/checkpoints/gate-receipts.json is the assembler's authority
#   (run_book_writer.load_gate_receipts reads {gate_id, approved,
#   approved_by, approved_at}; a human approval can never be self-attested).
#   The mini-app gate flow (GATE-1/2/3/4/433) produces exactly that shape;
#   `record_gate_approval` is the seam's writer — it APPENDS a well-formed
#   receipt (never overwrites existing ones) so the assembler's gate
#   requirement is satisfied unchanged. The seam's OWN phase -> board-receipt
#   mapping (mc-board-seam.json) is distinct so it can never corrupt the
#   assembler's schema.
#
# ISOLATION (master-plan section 3):
#   The seam NEVER creates a cross-client card. begin_run requires client_id;
#   it is folded into the card title ("Book Writer Intake — <client>") and the
#   board receipt is stamped with the client_id + run_dir, and the mc_board
#   receipt (mc_task_id) is stored under THAT run's dir. A different client /
#   run dir can never recover another client's task_id. `record_gate_approval`
#   stamps the receipt with the run_dir's client context for the same reason.
#
# NO NEW CC ENDPOINT: the seam ONLY calls mc_board's existing routes
# (POST /api/tasks/ingest, GET/PATCH /api/tasks/{id}) — cc-compat preserved
# (master-plan section 6). No Anthropic ids anywhere. No real ids — every
# fixture/client value below is a placeholder.
#
# EXIT CODES (self-test):
#   0  PASS
#   2  FAILED (a seam assertion broke — the seam itself never raises in prod)
#
# USAGE:
#   python3 mc_seam.py --self-test          # stubbed-board proof (see below)
#   python3 mc_seam.py --phase-map          # print the canonical phase map
#   python3 mc_seam.py --gate-receipts RUN_DIR  # print assembler gate receipts
#
# SELF-TEST (per-unit gate, master-plan section 9):
#   Runs the ENTIRE lifecycle against a STUBBED board (no network): begin ->
#   per-answer advance -> complete_run(review, NOT done) -> block_run on a
#   simulated AF-BK gate failure -> fail-soft when the board is UNREACHABLE
#   (stub raises; the seam still records a local receipt and returns cleanly).
# =============================================================================
"""Book Writer mini-app mc_board seam — marketing-lane card, review-NOT-done,
fail-soft. Thin, guaranteed non-raising wrappers over the vendored mc_board."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Canonical mini-app board conventions (single source of truth, self-tested)
# ---------------------------------------------------------------------------

# The RESOLVED real, mandatory, always-seeded fleet department this lineage
# resolves to (WIRING-SPEC section 8 + master-plan section 6): skill-53 maps to
# "marketing" (see 23-ai-workforce-blueprint/skill-department-map.json). An
# UNRECOGNIZED slug makes mc_board fail soft and silently drop/misroute the
# card — never pass anything else from the mini-app.
DEPARTMENT_SLUG = "marketing"

# Master-plan section 6's canonical card slug / source / persona for a mini-app
# run. A card is still PER-RUN and PER-CLIENT: the idempotency key inside
# mc_board is derived from slug+title, and title carries the client_id, so
# every client gets its own card even though the slug is shared.
CARD_SLUG = "book-writer-mini-app"
CARD_SOURCE = "book-writer-mini-app"
CARD_PERSONA = "Book Writer"

# The receipt subdir run_book_writer.py pins for Skill 53 (RECEIPT_SUBDIR =
# ("run", "checkpoints")) so the board receipt lives in the SAME
# run/checkpoints/ dir as the front-door nonce and the assembler's
# gate-receipts.json.
RECEIPT_SUBDIR = ("run", "checkpoints")

# The seam's OWN phase -> board-receipt mapping (distinct from the assembler's
# gate-receipts.json so neither can corrupt the other's schema).
SEAM_RECEIPT_FILENAME = "mc-board-seam.json"

# Assembler gate-receipts file (run_book_writer.load_gate_receipts authority).
GATE_RECEIPTS_FILENAME = "gate-receipts.json"
GATE_RECEIPTS_SCHEMA = "book-writer-gate-receipts-v1"

# The mini-app phases that are HUMAN GATE checkpoints (assembler requires a
# receipt for each). P0-INTAKE is an intake, not a gate. Canonical order is the
# manifest's gates_order (full then 4x3x3) — the map is data, kept here so the
# seam and the assembler agree without re-reading the manifest.
GATE_PHASE_IDS = (
    "GATE-1-title",
    "GATE-2-outline",
    "GATE-3-approval",
    "GATE-4-approval-r2",
    "GATE-433",
)

# The only statuses the seam's wrappers ever target. "review" is the producer's
# terminal move; "blocked" the gate-failure dead-end. "done" is NEVER produced
# here — review -> done is the independent QC scorer's exclusive move
# (THE BOARD CONTRACT). Kept as a guard even though mc_board already hard-blocks
# it, belt-and-suspenders.
_PRODUCER_FORBIDDEN = frozenset({"done"})

EXIT_OK = 0
EXIT_FAIL = 2


def _utcnow() -> str:
    import time
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


# ---------------------------------------------------------------------------
# Board loading — injectable for the stub self-test, default is the vendored
# mc_board shipped with the skill.
# ---------------------------------------------------------------------------

def _board_paths() -> list:
    """The dirs mc_board lives in (root + scripts/), in load order. The skill
    vendors one copy at 53-book-writer/scripts/mc_board.py (and older copies at
    the skill root); import the first that resolves."""
    here = Path(__file__).resolve().parent
    skill_root = here.parent.parent  # 53-book-writer/
    return [skill_root / "scripts", skill_root]


def _load_board():
    """Import the vendored shared mc_board module. Raises ImportError if no
    copy resolves — every public wrapper catches this (fail-soft)."""
    import importlib
    prev = list(sys.path)
    try:
        for d in _board_paths():
            if str(d) not in sys.path:
                sys.path.insert(0, str(d))
        try:
            return importlib.import_module("mc_board")
        except ImportError:
            # one more try with only the skill root — some vendored copies sit
            # directly at the root
            if str(_board_paths()[1]) not in sys.path:
                sys.path.insert(0, str(_board_paths()[1]))
            return importlib.import_module("mc_board")
    finally:
        sys.path[:] = prev


# ---------------------------------------------------------------------------
# Local receipt helpers — FAIL-SOFT: never raise, never lose the mapping.
# ---------------------------------------------------------------------------

def _receipt_dir(run_dir) -> Path:
    return Path(run_dir).joinpath(*RECEIPT_SUBDIR)


def _seam_receipt_path(run_dir) -> Path:
    return _receipt_dir(run_dir) / SEAM_RECEIPT_FILENAME


def _read_seam_receipt(run_dir) -> dict:
    p = _seam_receipt_path(run_dir)
    if not p.is_file():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _record(run_dir, *, op, phase_id, ok, task_id=None, client_id=None,
            af_code=None, detail=""):
    """Append one phase -> board-receipt entry to the seam's OWN mapping file.
    Runs on EVERY call regardless of the board's answer (a board outage is
    recorded, never silently swallowed). Best-effort: any write failure is
    logged and ignored — the board is a view, never a gate."""
    try:
        receipt = _read_seam_receipt(run_dir)
        entries = receipt.setdefault("entries", [])
        entries.append({
            "op": op,
            "phase_id": phase_id,
            "ok": bool(ok),
            "task_id": task_id,
            "client_id": client_id,
            "af_code": af_code,
            "detail": detail,
            "at_utc": _utcnow(),
        })
        receipt.setdefault("schema", "book-writer-mc-board-seam-v1")
        receipt.setdefault("department_slug", DEPARTMENT_SLUG)
        if client_id:
            receipt["client_id"] = client_id
        p = _seam_receipt_path(run_dir)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
        tmp.replace(p)
    except OSError as exc:
        _log("seam receipt write failed (%s)" % exc, "ERR")


def _log(msg: str, severity: str = "INFO") -> None:
    print("[mc_seam:%s] %s" % (severity, msg), file=sys.stderr, flush=True)


# ---------------------------------------------------------------------------
# Public seam API — guaranteed non-raising (belt-and-suspenders on top of
# mc_board's own fail-soft internals). Every function also writes the local
# phase -> board-receipt mapping even when the board is down.
# ---------------------------------------------------------------------------

def begin_run(run_dir, *, client_id, title=None, env=None, board=None):
    """Open the run's marketing-lane card (backlog -> in_progress).

    ``client_id`` is REQUIRED — the card is per-run AND per-client (folded into
    the title; the mc_board idempotency key is derived from slug+title, so no
    two clients collide, and the board receipt lives in THIS run's dir, so no
    other client can recover it). Returns the task_id str or None (fail-soft).
    Never raises."""
    try:
        board_mod = board if board is not None else _load_board()
        client = str(client_id or "").strip() or "CLIENT"
        card_title = title or ("Book Writer Intake — %s" % client)
        tid = board_mod.begin_run(
            run_dir,
            slug=CARD_SLUG,
            title=card_title,
            department=DEPARTMENT_SLUG,
            persona=CARD_PERSONA,
            source=CARD_SOURCE,
            env=env,
            receipt_subdir=RECEIPT_SUBDIR,
        )
        _record(run_dir, op="begin", phase_id="intake",
                ok=tid is not None, task_id=tid, client_id=client,
                detail="card opened (backlog -> in_progress)")
        return tid
    except Exception as exc:  # noqa: BLE001 — board hookup must NEVER break the run.
        _log("begin_run best-effort skip (%s: %s)" % (type(exc).__name__, exc), "ERR")
        _record(run_dir, op="begin", phase_id="intake", ok=False,
                client_id=str(client_id or "").strip() or None,
                detail="begin skipped: %s" % type(exc).__name__)
        return None


def card_advance(run_dir, task_id=None, *, qid, note=None, env=None, board=None):
    """Per-answer heartbeat: advance the run's card to
    (phase_id="intake-<qid>", status="in_progress"). task_id is recovered from
    the board receipt when not supplied. FAIL-SOFT: returns False (never
    raises) on any board problem. Never "done"."""
    try:
        board_mod = board if board is not None else _load_board()
        q = str(qid or "").strip()
        if not q:
            _log("card_advance skipped — qid is empty.", "WARN")
            _record(run_dir, op="advance", phase_id="intake", ok=False,
                    task_id=task_id, detail="empty qid")
            return False
        phase_id = "intake-%s" % q
        ok = board_mod.card_advance(
            run_dir, task_id, phase_id=phase_id, status="in_progress",
            note=note or ("answer recorded %s" % q), env=env,
            receipt_subdir=RECEIPT_SUBDIR,
        )
        _record(run_dir, op="advance", phase_id=phase_id, ok=ok,
                task_id=task_id, detail="answer recorded %s" % q)
        return bool(ok)
    except Exception as exc:  # noqa: BLE001
        _log("card_advance best-effort skip (%s: %s)" % (type(exc).__name__, exc), "ERR")
        _record(run_dir, op="advance", phase_id="intake-%s" % (qid or ""),
                ok=False, task_id=task_id,
                detail="advance skipped: %s" % type(exc).__name__)
        return False


def complete_run(run_dir, task_id=None, *, phase_id="deliver", note=None,
                 deliverable_url="", env=None, board=None):
    """Terminal producer move: the card goes to `review` (never `done`). The
    deliverable_url, when supplied, is registered on the card. review -> done is
    the independent QC scorer's exclusive move. FAIL-SOFT: returns False on any
    board problem; never raises."""
    try:
        board_mod = board if board is not None else _load_board()
        target = "review"  # THE BOARD CONTRACT — producer never posts done.
        ok = board_mod.complete_run(
            run_dir, task_id, phase_id=phase_id,
            note=note or "certified — awaiting QC promotion",
            status=target, deliverable_url=deliverable_url, env=env,
            receipt_subdir=RECEIPT_SUBDIR,
        )
        _record(run_dir, op="complete", phase_id=phase_id, ok=ok,
                task_id=task_id, detail="moved to %s" % target)
        return bool(ok)
    except Exception as exc:  # noqa: BLE001
        _log("complete_run best-effort skip (%s: %s)" % (type(exc).__name__, exc), "ERR")
        _record(run_dir, op="complete", phase_id=phase_id, ok=False,
                task_id=task_id, detail="complete skipped: %s" % type(exc).__name__)
        return False


def block_run(run_dir, task_id=None, *, phase_id="", af_code="gate-failed",
              note=None, env=None, board=None):
    """Move the run's card to the fail-soft `blocked` status when a gate FAILS
    (AF-BK-*), so a blocked run is VISIBLE on the board instead of stranding
    forever at in_progress (FIX-XC-06). `blocked` is reachable from ANY status
    in one hop and is NEVER `done`. FAIL-SOFT: never raises."""
    try:
        board_mod = board if board is not None else _load_board()
        ph = str(phase_id or "").strip()
        code = str(af_code or "gate-failed").strip() or "gate-failed"
        detail = note
        if not detail:
            detail = "BLOCKED at %s (gate failed) — AF code %s" % (ph or "run", code) \
                if ph else "run BLOCKED (a gate failed) — AF code %s" % code
        ok = board_mod.block_run(
            run_dir, task_id, phase_id=ph, note=detail, env=env,
            receipt_subdir=RECEIPT_SUBDIR,
        )
        _record(run_dir, op="block", phase_id=ph or "blocked", ok=ok,
                task_id=task_id, af_code=code, detail=detail)
        return bool(ok)
    except Exception as exc:  # noqa: BLE001
        _log("block_run best-effort skip (%s: %s)" % (type(exc).__name__, exc), "ERR")
        _record(run_dir, op="block", phase_id=phase_id or "blocked", ok=False,
                task_id=task_id, af_code=af_code,
                detail="block skipped: %s" % type(exc).__name__)
        return False


# ---------------------------------------------------------------------------
# Gate-receipts mapping — the assembler's authority file
# (run/checkpoints/gate-receipts.json). APPEND-only, never self-attesting.
# ---------------------------------------------------------------------------

def gate_receipts_path(run_dir) -> Path:
    return _receipt_dir(run_dir) / GATE_RECEIPTS_FILENAME


def read_gate_receipts(run_dir) -> dict:
    """Read the assembler gate-receipts file. Returns the canonical object
    ({schema, receipts:[]}) even when absent/empty. Never raises."""
    p = gate_receipts_path(run_dir)
    if p.is_file():
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(data, dict) and isinstance(data.get("receipts"), list):
                return data
        except (OSError, ValueError):
            pass
    return {"schema": GATE_RECEIPTS_SCHEMA, "receipts": []}


def record_gate_approval(run_dir, *, gate_id, approved_by, reply="",
                         approved_at=None, client_id=None, env=None, board=None):
    """Write ONE human-gate approval receipt into the assembler's
    gate-receipts.json in the EXACT shape run_book_writer.load_gate_receipts
    requires ({gate_id, approved:true, approved_by, approved_at}); an approval
    can never be self-attested away. APPENDS to the existing receipts array —
    never overwrites prior approvals (an edit after approval must be a NEW
    record, which the assembler's byte-exact lock then catches).

    ALSO records the seam's phase -> board-receipt mapping for this gate and
    moves the run's card to `review` for that phase (never `done`). FAIL-SOFT:
    the local receipt is written even when the board is down. Never raises."""
    try:
        p = gate_receipts_path(run_dir)
        p.parent.mkdir(parents=True, exist_ok=True)
        obj = read_gate_receipts(run_dir)
        gid = str(gate_id or "").strip()
        by = str(approved_by or "").strip()
        if not gid or not by:
            _log("record_gate_approval skipped — gate_id and approved_by are required.", "WARN")
            return False
        record = {
            "gate_id": gid,
            "approved": True,
            "approved_by": by,
            "approved_at": approved_at or _utcnow(),
        }
        if reply:
            record["reply"] = str(reply)
        obj["receipts"].append(record)
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(obj, indent=2), encoding="utf-8")
        tmp.replace(p)

        # Board reflection: the gate phase is done -> card to `review`.
        complete_run(run_dir, phase_id=gid,
                     note="gate approved by %s — awaiting QC promotion" % by,
                     env=env, board=board)
        _record(run_dir, op="gate-approval", phase_id=gid, ok=True,
                client_id=client_id, detail="receipt written + card to review")
        return True
    except Exception as exc:  # noqa: BLE001 — the approval must never break the run.
        _log("record_gate_approval best-effort skip (%s: %s)" % (type(exc).__name__, exc), "ERR")
        return False


# ---------------------------------------------------------------------------
# Phase map — the canonical phase -> board-card mapping (self-test asserts it)
# ---------------------------------------------------------------------------

def phase_map() -> dict:
    """The canonical mini-app phase -> board receipt mapping. Data, kept here
    so the seam and the assembler agree without re-reading the manifest."""
    return {
        "P0-INTAKE": {"board_phase": "intake", "kind": "intake"},
        "GATE-1-title": {"board_phase": "GATE-1-title", "kind": "gate"},
        "GATE-2-outline": {"board_phase": "GATE-2-outline", "kind": "gate"},
        "GATE-3-approval": {"board_phase": "GATE-3-approval", "kind": "gate"},
        "GATE-4-approval-r2": {"board_phase": "GATE-4-approval-r2", "kind": "gate"},
        "GATE-433": {"board_phase": "GATE-433", "kind": "gate"},
    }


# ---------------------------------------------------------------------------
# Self-test — STUBBED board, no network. Exercises the full lifecycle +
# block_run on gate failure + fail-soft when the board is unreachable.
# ---------------------------------------------------------------------------

class _StubBoard:
    """In-memory stand-in for mc_board. Records every call so the test can
    assert the seam targeted exactly the right statuses / phases. `raise_on`
    simulates a board OUTAGE (fail-soft must still win)."""

    def __init__(self):
        self.calls = []
        self.task_id = "stub-task-0001"
        self.status = "backlog"
        self.raise_on = None  # set to "begin"/"advance"/"complete"/"block" to simulate an outage

    def _bump(self, name):
        if self.raise_on == name:
            raise ConnectionError("simulated board outage")
        self.calls.append(name)

    def begin_run(self, run_dir, *, slug, title, department, persona="", source="",
                  description="", env=None, receipt_subdir=None, **kw):
        self._bump("begin")
        self.calls.append(("begin", slug, title, department, persona, source))
        self.status = "in_progress"
        return self.task_id

    def card_advance(self, run_dir, task_id=None, *, phase_id, status, note="",
                     deliverable_url="", env=None, receipt_subdir=None, **kw):
        self._bump("advance")
        self.calls.append(("advance", task_id, phase_id, status, note))
        self.status = status
        return True

    def complete_run(self, run_dir, task_id=None, *, phase_id="deliver", note="",
                     status="review", deliverable_url="", env=None,
                     receipt_subdir=None, **kw):
        self._bump("complete")
        self.calls.append(("complete", task_id, phase_id, status, note, deliverable_url))
        self.status = status
        return True

    def block_run(self, run_dir, task_id=None, *, phase_id="", note="", env=None,
                  receipt_subdir=None, **kw):
        self._bump("block")
        self.calls.append(("block", task_id, phase_id, note))
        self.status = "blocked"
        return True


def _selftest() -> int:
    import tempfile
    results = []

    def T(name, ok):
        results.append((name, bool(ok)))

    with tempfile.TemporaryDirectory() as td:
        run_dir = Path(td) / "run-client-a"
        run_dir.mkdir(parents=True)
        stub = _StubBoard()

        # ---- 1. begin_run: marketing-lane card + local receipt -------------
        tid = begin_run(run_dir, client_id="client-a", board=stub)
        T("begin_run returns task_id", tid == "stub-task-0001")
        T("begin targets marketing department", ("begin", CARD_SLUG, "Book Writer Intake — client-a",
                                                 DEPARTMENT_SLUG, CARD_PERSONA, CARD_SOURCE) in stub.calls)
        seam = _read_seam_receipt(run_dir)
        T("seam receipt records begin", any(e["op"] == "begin" and e["ok"] for e in seam.get("entries", [])))
        T("seam receipt stamps department", seam.get("department_slug") == "marketing")
        T("seam receipt stamps client", seam.get("client_id") == "client-a")

        # ---- 2. per-answer card_advance ------------------------------------
        ok = card_advance(run_dir, tid, qid="first_name", board=stub)
        T("advance returns True", ok is True)
        T("advance targeted intake-<qid> in_progress",
          ("advance", "stub-task-0001", "intake-first_name", "in_progress", "answer recorded first_name") in stub.calls)
        seam = _read_seam_receipt(run_dir)
        T("seam receipt records advance", any(e["op"] == "advance" and e["phase_id"] == "intake-first_name"
                                              and e["ok"] for e in seam.get("entries", [])))

        # ---- 3. complete_run -> review, NEVER done --------------------------
        ok = complete_run(run_dir, tid, phase_id="deliver",
                          deliverable_url="https://placeholder.local/bundle", board=stub)
        T("complete_run returns True", ok is True)
        T("complete targeted review (not done)",
          ("complete", "stub-task-0001", "deliver", "review", "certified — awaiting QC promotion",
           "https://placeholder.local/bundle") in stub.calls)
        T("complete never targeted done",
          not any(c[0] == "complete" and c[3] == "done" for c in stub.calls))

        # ---- 4. block_run on a gate failure (AF-BK-*) -----------------------
        ok = block_run(run_dir, tid, phase_id="P5-CHAPTERS", af_code="AF-BK-CHAP-COUNT", board=stub)
        T("block_run returns True", ok is True)
        T("block targeted blocked status",
          ("block", "stub-task-0001", "P5-CHAPTERS",
           "BLOCKED at P5-CHAPTERS (gate failed) — AF code AF-BK-CHAP-COUNT") in stub.calls)
        seam = _read_seam_receipt(run_dir)
        T("seam receipt records block with af_code",
          any(e["op"] == "block" and e["af_code"] == "AF-BK-CHAP-COUNT" and e["phase_id"] == "P5-CHAPTERS"
              for e in seam.get("entries", [])))

        # ---- 5. FAIL-SOFT: board unreachable (stub raises) ------------------
        down = _StubBoard()
        down.raise_on = "begin"
        tid_down = begin_run(run_dir, client_id="client-a", board=down)
        T("begin fail-soft returns None on outage", tid_down is None)
        seam = _read_seam_receipt(run_dir)
        T("outage still records a local begin entry",
          any(e["op"] == "begin" and not e["ok"] for e in seam.get("entries", [])))
        T("no cross-client receipt leak", all(e.get("client_id") in (None, "client-a")
                                              for e in seam.get("entries", [])))

        # outage on advance: returns False, run continues, receipt still written
        down2 = _StubBoard()
        down2.raise_on = "advance"
        ok2 = card_advance(run_dir, "stub-task-0001", qid="niche", board=down2)
        T("advance fail-soft returns False on outage", ok2 is False)
        seam = _read_seam_receipt(run_dir)
        T("outage advance still recorded locally",
          any(e["op"] == "advance" and e["phase_id"] == "intake-niche" and not e["ok"]
              for e in seam.get("entries", [])))

        # ---- 6. gate-receipts mapping: assembler shape, append-only ---------
        before = read_gate_receipts(run_dir)
        T("empty gate-receipts reads canonical shape",
          before == {"schema": GATE_RECEIPTS_SCHEMA, "receipts": []})
        ok = record_gate_approval(run_dir, gate_id="GATE-1-title",
                                  approved_by="Client A", reply="Locked.",
                                  client_id="client-a", board=_StubBoard())
        T("record_gate_approval returns True", ok is True)
        after = read_gate_receipts(run_dir)
        T("gate receipt has assembler shape",
          len(after["receipts"]) == 1
          and after["receipts"][0]["gate_id"] == "GATE-1-title"
          and after["receipts"][0]["approved"] is True
          and after["receipts"][0]["approved_by"] == "Client A"
          and bool(after["receipts"][0].get("approved_at")))
        # a SECOND approval for the same gate must APPEND, not overwrite
        ok = record_gate_approval(run_dir, gate_id="GATE-1-title",
                                  approved_by="Client A", reply="Re-locked (edit).",
                                  client_id="client-a", board=_StubBoard())
        after2 = read_gate_receipts(run_dir)
        T("gate receipts are append-only (edit never overwrites)",
          len(after2["receipts"]) == 2)
        # a missing approved_by can never fabricate a receipt
        ok_bad = record_gate_approval(run_dir, gate_id="GATE-2-outline", approved_by="")
        after3 = read_gate_receipts(run_dir)
        T("empty approved_by cannot fabricate a receipt",
          ok_bad is False and len(after3["receipts"]) == 2)

        # ---- 7. phase map is complete over the gate set ---------------------
        pm = phase_map()
        T("phase map covers every gate phase",
          all(g in pm for g in GATE_PHASE_IDS))
        T("phase map intake is intake-kind", pm["P0-INTAKE"]["kind"] == "intake")

        # ---- 8. isolation: a second client gets its OWN card/receipt --------
        run_b = Path(td) / "run-client-b"
        run_b.mkdir(parents=True)
        stub_b = _StubBoard()
        stub_b.task_id = "stub-task-0002"
        tid_b = begin_run(run_b, client_id="client-b", board=stub_b)
        T("second client gets a distinct task_id", tid_b == "stub-task-0002")
        T("client-b card title carries client-b",
          ("begin", CARD_SLUG, "Book Writer Intake — client-b",
           DEPARTMENT_SLUG, CARD_PERSONA, CARD_SOURCE) in stub_b.calls)
        seam_b = _read_seam_receipt(run_b)
        T("client-b receipt stamped client-b", seam_b.get("client_id") == "client-b")
        T("client-a receipt never contains client-b task",
          all(e.get("task_id") != "stub-task-0002"
              for e in _read_seam_receipt(run_dir).get("entries", [])))

    failed = [n for n, ok in results if not ok]
    for n, ok in results:
        print("%s  %s" % ("PASS" if ok else "FAIL", n))
    if failed:
        print("== U16 mc_seam self-test: FAILED (%d) ==" % len(failed))
        return EXIT_FAIL
    print("== U16 mc_seam self-test: ALL ASSERTIONS PASSED ==")
    return EXIT_OK


def _cli(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Book Writer mini-app mc_board seam (U16).")
    ap.add_argument("--self-test", dest="self_test", action="store_true",
                    help="run the stubbed-board self-test and exit")
    ap.add_argument("--phase-map", dest="phase_map_flag", action="store_true",
                    help="print the canonical phase -> board receipt map and exit")
    ap.add_argument("--gate-receipts", dest="gate_receipts", metavar="RUN_DIR",
                    help="print the assembler gate-receipts file for RUN_DIR")
    args = ap.parse_args(argv)

    if args.self_test:
        return _selftest()
    if args.phase_map_flag:
        print(json.dumps(phase_map(), indent=2))
        return EXIT_OK
    if args.gate_receipts:
        rd = Path(args.gate_receipts).resolve()
        if not rd.is_dir():
            print("FATAL: run dir not found: %s" % rd, file=sys.stderr)
            return 3
        print(json.dumps(read_gate_receipts(rd), indent=2))
        return EXIT_OK
    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(_cli())
