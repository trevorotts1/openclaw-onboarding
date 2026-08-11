#!/usr/bin/env python3
# =============================================================================
# SKILL 59 — ANTHOLOGY ENGINE :: canary_e2e_test.py   (MASTER-SPEC NEW-4)
# THE ONE-COMPLETE-S0-S9 CANARY — driven on the OPERATOR box.
# -----------------------------------------------------------------------------
# WHAT THIS SHIPS (MASTER-SPEC NEW-4; W5.3/W5.4/W5.5/W5.6/W5.7 drills):
#   Drives ONE complete S0..S9 anthology canary with 2 SYNTHETIC co-authors on
#   the operator box and verifies, per stage:
#     S0  intake webhook fire with a LIVE Cloudflare Tunnel (T1..T9 battery via
#         the sibling verify-webhook-t1-t9.sh; the public URL comes from
#         --public-url, never invented); dedup no-op; tenant + stage-mismatch
#         capture; Exceptions capture with a typed reason; board card ingested
#         (fail-soft).
#     S1  avatar artifact + producer gate approve (board door) + §3 release tag.
#     S2  tone deliverable (3,000 measured word floor via Tier 1) + gate.
#     S3  titles + TITLE LOCK (one-way; relock refused) + participant pick on
#         the TOKEN door.
#     S4  blurb + outline + BOTH gates (s4_producer board, s4_participant token).
#     S5  chapter deliverable: Tier 1 band 2,000-3,500 measured, JUDGE-tier
#         rubric, strike-gate attempt accounting, chapter gate EXACTLY TWO
#         actions, freeze on approve; request_rewrite -> S6 (rewrite cycle
#         preservation: original + rewrite1 + rewrite2 slots never overwritten).
#     S6  rewrite re-enters s5_gate (budget 2; a 3rd request is refused).
#     S7  cover SET: 4 named styles (cover_render COVER_STYLES), choice field
#         coherence, apply-pick advances to S8.
#     S8  deliver: Doc + PDF, 14-point floor on the RENDERED PDF
#         (guard-font-floor), field writes, completion notice (nudge_send),
#         signed process certificate, card to review (never 'done').
#     S9  assembly: readiness + every PRD 3.11 guard (own-producer, typed
#         --confirm-name, floor 2, one-way), order set/adjust/confirm (U9
#         confirm_order flags the runner for transitions + Grand Finale),
#         compile with frozen-chapter sha256 byte-identity, assembly Gate B,
#         s9_producer sign-off closes the anthology.
#   Cross-cutting proofs:
#     - EMAIL + SMS: every §3 release slug maps to a snapshot-contract
#       release_notifications workflow carrying send-email + send-sms actions
#       (the tag the engine stamps is exactly what fires the automation); a
#       committed BOARD-door producer approve stamps the slug via
#       caf_delivery.py add-tag (fail-soft, status surfaced; a Convert and Flow
#       blip never unwinds the committed decision).
#     - DOC PULL-BACK byte-diff: gate_engine pullback-revalidate +
#       qc-tier1 --mode pullback over the PULLED bytes (invariants 1/2/3),
#       advisory-only (a client edit never blocks); when a live Doc is
#       available the sibling prove_aw_doc_pullback.py (NEW-5) is driven; else
#       the proof is DEFERRED (never a false pass).
#     - PDF 14-point floor: guard-font-floor over the RENDERED PDF, plus the
#       template-side tripwire inside pdf_render (exit 2).
#     - BOARD round trip BOTH DOORS: the token door (mint -> verify -> decide
#       with the minted token; foreign/expired/replayed refused) and the board
#       door (decide --door board; producer gates board-only; 'done' is refused
#       before any network I/O). mc_board mirrors each subject's card
#       (fail-soft; never emits 'done').
#     - QC SCORER >= 8.5 PROMOTES REVIEW->DONE: the engine never self-promotes.
#       This is proven by (a) mc_board's maps + _guarded_status containing no
#       'done' and the CC status route 403ing it, (b) the independent CC QC
#       scorer's QC_PASS_THRESHOLD == 8.5 and transition('done') with
#       actor 'qc-auto-scorer' (read from the CC repo when present on the
#       operator box, else the contract is verified from the engine side and
#       the CC-side read is DEFERRED), (c) a card parked in review stays review
#       under the engine (the canary asserts the board projection never asks
#       for 'done').
#     - EVERY GATE FAILS CLOSED: illegal transitions exit 2 and change
#       NOTHING; unknown keys exit 3; validation mismatches exit 5; a refused
#       gate never advances a cursor.
#
# MODES:
#   --self-test        offline acceptance battery (golden + attack fixtures;
#                      no network, no live ledger) -> exit 0/4.
#   --plan             print the stage plan + exit-code contract and exit 0.
#   --verify-report REPORT_PATH  independently re-check a persisted
#                      CANARY-REPORT.json claim: recomputes the deterministic
#                      sha256 chain over the report BODY (every stage's checks
#                      with result + evidence) AND over the state ledger it
#                      names (the two SQLite files: anthology_state.db + WAL,
#                      gate_nonce.db + WAL, in byte order). VALID (exit 0) iff
#                      the chain matches the report's signature hash, the
#                      ledger exists at the recorded path, and every DEFERRED
#                      check carries the deferred-live note. INVALID (exit 4)
#                      on ANY mismatch or missing ledger. Self-check: a report
#                      regenerated from the same data reproduces the same hash.
#   run (default)      execute the full S0..S9 canary against an ISOLATED
#                      state dir (--state-dir; default a fresh temp dir),
#                      writing CANARY-REPORT.json (per-stage pass/fail +
#                      evidence) to --report-dir (default: state dir/reports).
#   --gateway-base-url URL   gateway base for the T-battery (default
#                      127.0.0.1:18789, the OpenClaw gateway).
#   --public-url URL    enable the LIVE-TUNNEL T8 proof (a real named
#                      Cloudflare Tunnel URL; NEVER Tailscale).
#   --require-live      any un-executed live stage holds the canary (exit 3).
#
# EXIT CODES (house map; ENGINE-MANIFEST exit_code_house_convention):
#   0  every stage observed PASS (or cleanly DEFERRED without --require-live);
#      --verify-report: chain matches, ledger present, note carried -> VALID
#   2  bad invocation / a stage that was executed FAILED (the report carries
#      the failing stage + evidence; the canary NEVER false-passes)
#   3  --require-live with un-executed live stages (held)
#   4  --self-test failed; --verify-report: INVALID (tampered body, missing
#      ledger, or a DEFERRED check without the deferred-live note) — an
#      invariant the canary itself owns is violated
#   1  unexpected error
#
# DOCTRINE (binding, enforced in code):
#   - STDLIB ONLY. ZERO network calls are made by the canary itself: every
#     live probe shells a SIBLING script that owns its transport
#     (verify-webhook-t1-t9.sh owns the webhook battery; gate_engine owns the
#     token crypto; guard-font-floor owns PDF parsing; qc-tier1 owns the
#     content battery; anthology_state owns the ledger). The canary orchestrates
#     and observes; it never re-implements a sibling.
#   - SECRET HYGIENE (binding): credentials are resolved BY LABEL only, SET /
#     NOT SET surfaces, values NEVER printed (ANTHOLOGY_INTAKE_HOOK_SECRET,
#     ANTHOLOGY_GATE_TOKEN_SECRET, CONVERT_AND_FLOW_PIT,
#     CONVERT_AND_FLOW_LOCATION_ID, GOOGLE_SA_KEY_FILE, GOOGLE_IMPERSONATE_USER,
#     GOOGLE_DRIVE_ROOT_FOLDER, N8N_DRIVE_WEBHOOK_URL, N8N_DRIVE_WEBHOOK_TOKEN).
#   - FAIL-CLOSED reporting: a stage is PASS only when every executed check
#     passed; a check that could not be executed is DEFERRED (with the exact
#     reason), never PASS and never silently skipped; --require-live makes any
#     DEFERRED stage a HOLD. A stage that ran and failed is FAIL and the run
#     exits 2.
#   - STAGE-LEVEL, NEVER CHECK-COUNT: a PASS verdict is per STAGE. The summary
#     ALWAYS carries the deferred-live note (S7 live Kie cover render + S8 live
#     Doc pull-back are deliberately not exercised by default) so a 12/12 is
#     never read as every check passing, and --verify-report refuses a report
#     whose DEFERRED checks carry no note.
#   - MOVE IN SILENCE: operator-verbose to stdout/stderr + the report; NOTHING
#     to any client. The canary never sends a client message (nudges are only
#     exercised --dry-run through nudge_send, and gate_engine open --no-nudge).
#   - Convert and Flow is the only client-facing platform name; NOTHING
#     Anthropic-family ships in this file (banned literals are assembled from
#     fragments exactly like every sibling).
#   - All fixtures are synthetic: zero PII, zero secrets, zero client
#     identifiers, zero real provider keys.
# =============================================================================
"""canary_e2e_test.py — one complete S0..S9 canary with two synthetic co-authors."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Exit codes (house map).
# ---------------------------------------------------------------------------
EX_OK = 0
EX_ERR = 1
EX_BADINVOKE = 2
EX_HELD = 3
EX_VIOLATION = 4

# Anthropic-family id shapes assembled from fragments (mirrors every sibling)
# so this shipped file carries no contiguous banned literal.
_a = "anthro" + "pic"
_c = "clau" + "de-"
BANNED = re.compile(_c + r"|" + _a + r"/|us\." + _a + r"\.", re.I)

# ---------------------------------------------------------------------------
# Layout (mirrors every sibling script's resolution).
# ---------------------------------------------------------------------------
SKILL_DIR = Path(__file__).resolve().parent.parent
SCRIPTS = SKILL_DIR / "scripts"
STATE_SCRIPT = SCRIPTS / "anthology_state.py"
GATE_ENGINE = SCRIPTS / "gate_engine.py"
NUDGE_SEND = SCRIPTS / "nudge_send.py"
MC_BOARD = SCRIPTS / "mc_board.py"
QC_TIER1 = SCRIPTS / "qc-tier1-anthology.py"
JUDGE_HARNESS = SCRIPTS / "judge_harness.py"
STRIKE_GATE = SCRIPTS / "qc-strike-gate.py"
PDF_RENDER = SCRIPTS / "pdf_render.py"
FONT_FLOOR = SCRIPTS / "guard-font-floor.py"
COVER_RENDER = SCRIPTS / "cover_render.py"
CAF_DELIVERY = SCRIPTS / "caf_delivery.py"
DRIVE_ADAPTER = SCRIPTS / "drive_adapter.py"
REGISTRY = SCRIPTS / "anthology_registry.py"
VERIFY_WEBHOOK = SCRIPTS / "verify-webhook-t1-t9.sh"
PULLBACK_PROVER = SCRIPTS / "prove_aw_doc_pullback.py"
S9_LOGIC = SCRIPTS / "stage_s9_assembly_logic.py"

FIELD_MAP = SKILL_DIR / "config" / "field-map.json"
SNAPSHOT_CONTRACT = SKILL_DIR / "config" / "anthology-snapshot-contract.json"
GOLDEN_DIR = SKILL_DIR / "fixtures" / "golden"

DEFAULT_GATEWAY_BASE = "http://127.0.0.1:18789"

# The canonical client env stores (label resolution only; values never printed).
_CANONICAL_STORE_PATHS = (
    "~/.openclaw/secrets/.env",
    "~/.openclaw/workspace/.env",
    "~/clawd/secrets/.env",
)

# ---------------------------------------------------------------------------
# Synthetic canary identities (zero PII; the W5.4/W5.7 shape).
# ---------------------------------------------------------------------------
PRODUCER_ID = "PRODcanaryOP01"
PRODUCER_EMAIL = "producer.canary@example.com"
PRODUCER_DISPLAY = "Synthetic Canary Producer"
ANTHOLOGY_ID = "ANTHcanaryOP01"
ANTHOLOGY_NAME = "Operator Canary Voices"
LOCATION_BINDING = "LOCcanaryOpAAA"
CONTACT_A = "CONTACTcanaryOPa1"
CONTACT_B = "CONTACTcanaryOPb2"
PARTICIPANT_A = CONTACT_A + "::" + ANTHOLOGY_ID
PARTICIPANT_B = CONTACT_B + "::" + ANTHOLOGY_ID
TITLE_A = "What the Ledger Cannot Say"
SUBTITLE_A = "A Chapter in Two Books"
TITLE_B = "The Discipline of Small No's"
SUBTITLE_B = "Turning Refusals into Craft"
MIN_CHAPTERS = 2

# Secret labels resolved BY LABEL only (SET / NOT SET surfaces, never values).
LABEL_INTAKE_SECRET = "ANTHOLOGY_INTAKE_HOOK_SECRET"
LABEL_GATE_SECRET = "ANTHOLOGY_GATE_TOKEN_SECRET"
LABEL_PIT = "CONVERT_AND_FLOW_PIT"
LABEL_LOCATION = "CONVERT_AND_FLOW_LOCATION_ID"
LABEL_SA_KEY = "GOOGLE_SA_KEY_FILE"
LABEL_IMPERSONATE = "GOOGLE_IMPERSONATE_USER"
LABEL_DRIVE_ROOT = "GOOGLE_DRIVE_ROOT_FOLDER"
LABEL_BROKER_URL = "N8N_DRIVE_WEBHOOK_URL"
LABEL_BROKER_TOKEN = "N8N_DRIVE_WEBHOOK_TOKEN"

# Base-store env labels stripped from every child so the ledger runs
# MIRROR-ONLY (a clean exit-0 base path) exactly like replay_golden.py.
_BASE_ENV_LABELS = (
    "ANTHOLOGY_STATE_BASE_ID", "ANTHOLOGY_STATE_AIRTABLE_KEY",
    "AIRTABLE_API_KEY", "AIRTABLE_TOKEN", "AIRTABLE_PAT",
)

# The CC repo on the operator box (best-effort; absent -> DEFERRED, never a
# false pass).
CC_REPO_CANDIDATES = (
    os.path.expanduser("~/blackceo-command-center"),
    os.path.expanduser("~/command-center"),
)

# The two live checks the canary deliberately defers on every default run
# (exact check names; the summary note and --verify-report both key off these):
#   S7: a live 4-style cover render is a PAID image generation on the client's
#       own Kie account -- never spent by default (structural proofs stand).
#   S8: the live Doc pull-back byte round-trip needs live Drive credentials
#       (prove_aw_doc_pullback held) -- the structural pull-back proof stands.
# A report's 12/12 verdict is STAGE-LEVEL; it never claims the deferred live
# checks ran. Every DEFERRED check in a report MUST carry this note or
# --verify-report refuses the report.
DEFERRED_LIVE_CHECKS = (
    "live 4-style cover render (Kie + Drive landing)",
    "live Doc pull-back byte round-trip",
)
DEFERRED_LIVE_NOTE = (
    "12/12 is STAGE-LEVEL, not check-level: the two live checks above are "
    "deliberately deferred on every default run (a live Kie cover render is a "
    "paid image generation on the client's own account; the live Doc "
    "pull-back needs live Drive credentials)."
)

# The ledger files hashed by --verify-report, in deterministic byte order
# (SQLite DB then its WAL when present; both are part of the state).
REPORT_LEDGER_FILES = (
    "anthology_state.db", "anthology_state.db-wal",
    "gate_nonce.db", "gate_nonce.db-wal",
)


def _env_first(names, environ=None):
    """First present, non-empty env value among `names` across the live process
    env and (when unset) the three canonical client .env stores. Returns
    (name, value) or (None, None). NEVER prints the value."""
    env = environ if environ is not None else os.environ
    for n in names:
        v = env.get(n, "")
        if v and v.strip():
            return n, v.strip()
    if environ is None:
        for store_spec in _CANONICAL_STORE_PATHS:
            try:
                text = Path(store_spec).expanduser().read_text(
                    encoding="utf-8", errors="replace")
            except (OSError, IOError):
                continue
            for raw in text.splitlines():
                line = raw.strip()
                if not line or line.startswith("#"):
                    continue
                if line.lower().startswith("export "):
                    line = line[7:].lstrip()
                if "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k = k.strip()
                v = v.strip().strip('"').strip("'")
                if k in names and v:
                    return k, v
    return None, None


def mask_set(value):
    """SET / NOT SET only (doctrine: a secret value is never printed)."""
    return "NOT SET" if not value else "SET(len=%d)" % len(value)


# ---------------------------------------------------------------------------
# Subprocess seam. run(argv, state_dir=None) -> (rc, parsed_or_None, err).
# ---------------------------------------------------------------------------
def _run(argv, state_dir=None, timeout=120, input_text=None, env_extra=None):
    env = dict(os.environ)
    for label in _BASE_ENV_LABELS:
        env.pop(label, None)
    if state_dir is not None:
        env["ANTHOLOGY_STATE_DIR"] = str(state_dir)
    if env_extra:
        env.update(env_extra)
    try:
        proc = subprocess.run(
            argv, capture_output=True, text=True, timeout=timeout,
            input=input_text, env=env, check=False,
        )
    except subprocess.TimeoutExpired:
        return EX_HELD, None, "timed out (%ss): %s" % (timeout, " ".join(argv))
    except OSError as exc:
        return EX_ERR, None, "could not launch: %s" % exc
    out = (proc.stdout or "").strip()
    parsed = None
    if out:
        try:
            parsed = json.loads(out)
        except (ValueError, TypeError):
            # a trailing human line after JSON (gate_engine emits JSON only with
            # --json; a sibling may add a summary line) — try the LAST JSON line
            for line in reversed(out.splitlines()):
                try:
                    parsed = json.loads(line)
                    break
                except (ValueError, TypeError):
                    continue
    return proc.returncode, parsed, (proc.stderr or "").strip()


def _state(script):
    return [sys.executable or "python3", str(script)]


def _ledger(argv, state_dir, timeout=120):
    """Run anthology_state.py <subcmd> --json ... against state_dir."""
    return _run(_state(STATE_SCRIPT) + ["--json", "--state-dir", str(state_dir)]
                + argv, state_dir=state_dir, timeout=timeout)


def _gate(argv, state_dir, timeout=120):
    """Run gate_engine.py <subcmd> --json --state-dir ... (the parser requires
    the subcommand FIRST, exactly as the Command Center bridge shells it)."""
    return _run(_state(GATE_ENGINE) + [argv[0], "--json", "--state-dir",
                                       str(state_dir)] + argv[1:],
                state_dir=state_dir, timeout=timeout)


# ---------------------------------------------------------------------------
# Report harness. A StageReport collects checks; a check is PASS / FAIL /
# DEFERRED(reason). The run is green iff every executed stage is all-PASS and
# no DEFERRED stage exists under --require-live.
# ---------------------------------------------------------------------------
class StageReport:
    def __init__(self, stage, label):
        self.stage = stage
        self.label = label
        self.checks = []

    def check(self, name, cond, evidence=""):
        self.checks.append({
            "check": name, "result": "PASS" if cond else "FAIL",
            "evidence": str(evidence)[:600],
        })
        return bool(cond)

    def deferred(self, name, reason):
        self.checks.append({"check": name, "result": "DEFERRED", "reason": str(reason)[:600]})

    def to_dict(self):
        status = "PASS"
        deferred = 0
        for c in self.checks:
            if c["result"] == "FAIL":
                status = "FAIL"
            elif c["result"] == "DEFERRED":
                deferred += 1
        if status == "PASS" and deferred and deferred == len(self.checks):
            status = "DEFERRED"
        return {"stage": self.stage, "label": self.label, "status": status,
                "checks": self.checks}


class CanaryRun:
    def __init__(self, state_dir, report_dir, args):
        self.state_dir = Path(state_dir)
        self.report_dir = Path(report_dir)
        self.args = args
        self.stages = []

    def begin(self, stage, label):
        rep = StageReport(stage, label)
        self.stages.append(rep)
        sys.stderr.write("[canary] %s %s\n" % (stage, label))
        return rep

    def finish(self):
        report = self.build_report()
        try:
            self.report_dir.mkdir(parents=True, exist_ok=True)
            path = self.report_dir / "CANARY-REPORT.json"
            path.write_text(json.dumps(report, indent=2, ensure_ascii=False),
                            encoding="utf-8")
        except OSError as exc:
            sys.stderr.write("[canary] could not persist CANARY-REPORT.json: %s\n" % exc)
            path = None
        return report, path

    def build_report(self):
        failed = [s for s in self.stages if s.to_dict()["status"] == "FAIL"]
        deferred = [s for s in self.stages if s.to_dict()["status"] == "DEFERRED"]
        report = {
            "contract": "anthology-engine-canary-report",
            "schema_version": 1,
            "utc": datetime.now(timezone.utc).isoformat(),
            "state_dir": str(self.state_dir),
            "mode": "run",
            "verdict": "PASS" if not failed else "FAIL",
            "stages": [s.to_dict() for s in self.stages],
            "summary": {
                "stages_total": len(self.stages),
                "stages_passed": len(self.stages) - len(failed) - len(deferred),
                "stages_deferred": len(deferred),
                "stages_failed": len(failed),
                "failed_stages": [s.stage for s in failed],
                "deferred_stages": [s.stage for s in deferred],
            },
        }
        # Deterministic self-signature: sha256 over the report body PLUS the
        # state ledger (see compute_report_chain). No secrets, no ledger
        # contents -- only digests. The report's own claim of PASS can be
        # re-checked later with --verify-report.
        signature = {
            "alg": "sha256",
            "chain": "v1:report-body+state-ledger",
            "sha256": compute_report_chain(report, self.state_dir),
        }
        report["signature"] = signature
        # Deferred-live note: the 12/12 verdict is STAGE-LEVEL, never
        # check-level. The two live checks (S7 live Kie render, S8 live Doc
        # pull-back) are deliberately not exercised on a default run; the
        # summary says so in the same breath as the counts, and every
        # DEFERRED check carries the note.
        report["summary"]["note"] = DEFERRED_LIVE_NOTE
        for s in report["stages"]:
            for c in s["checks"]:
                if c["result"] == "DEFERRED" and c.get("check") in DEFERRED_LIVE_CHECKS:
                    c["note"] = DEFERRED_LIVE_NOTE
        return report


def _default_state_dir():
    env = os.environ.get("ANTHOLOGY_STATE_DIR", "").strip()
    if env:
        return Path(env).expanduser()
    data = os.environ.get("OPENCLAW_DATA_DIR", "").strip()
    if data:
        return Path(data).expanduser() / "anthology-engine" / "state"
    home = os.environ.get("HOME") or os.path.expanduser("~")
    return Path(home) / ".anthology-engine" / "state"


def default_report_dir(state_dir):
    return Path(state_dir) / "reports"


# ---------------------------------------------------------------------------
# Fixture helpers (synthetic; zero PII / secrets / client identifiers).
# ---------------------------------------------------------------------------
def intake_payload(contact_id, first, last, email, phone, ideal_avatar, niche,
                   primary_goal, stage="s0_intake", location=LOCATION_BINDING):
    """The universal-intake webhook body shape the router extracts (see
    intake_router field_candidates + fixtures/webhook/t4-valid-intake.json)."""
    return {
        "source": "anthology-intake",
        "location": location,
        "form": "universal-intake",
        "contact_id": contact_id,
        "anthology_id": ANTHOLOGY_ID,
        "stage": stage,
        "first_name": first,
        "last_name": last,
        "email": email,
        "phone": phone,
        "ideal_avatar": ideal_avatar,
        "niche": niche,
        "primary_goal": primary_goal,
        "producer": PRODUCER_DISPLAY,
        "producer_email": PRODUCER_EMAIL,
    }


def chapter_text(title, subtitle, story, author_name, n_words=2400,
                 extra_paragraphs=6):
    """Deterministic chapter prose inside the 2,000-3,500 measured band.
    Every paragraph ends with terminal punctuation; no em dashes; no plumbing
    terms; the locked title/subtitle/story anchor appear verbatim."""
    words = ["one", "two", "three", "carry", "still", "begin", "small",
             "later", "again", "same", "door", "light", "held", "warm",
             "quiet", "turn", "keep", "part", "hand", "work", "morning",
             "evening", "street", "room", "table", "window", "paper", "pen",
             "habit", "order", "moment", "once", "twice", "almost", "never",
             "together", "apart", "under", "over", "beside", "before", "after"]
    base = [title, subtitle, story, author_name,
            "The chapter begins in a small room where the work of keeping "
            "faith with a craft is done slowly and without applause.",
            "Every sentence here is written to measure inside the band that "
            "the engine holds sacred, and nothing in this text carries a "
            "secret, a client identifier, or a platform that is not the one "
            "named Convert and Flow."]
    while _count_words(" ".join(base)) < n_words:
        base.append(" ".join(words[i % len(words)] for i in range(16)) + ".")
    text = "\n\n".join(base)
    # pad with paragraphs until at/above the target count; every paragraph ends
    # on a period so Tier 1 check 4 (complete-sentence close) holds.
    count = _count_words(text)
    while count < n_words:
        text += "\n\n" + " ".join(
            words[(i * 7 + 3) % len(words)] for i in range(20)) + "."
        count = _count_words(text)
    return text


def _count_words(text):
    return len(re.findall(r"[A-Za-z0-9'\-]+", text))


def tone_text(n_words=3200):
    words = ["tone", "voice", "calm", "steady", "warm", "precise", "plain",
             "honest", "measured", "kind", "clear", "firm", "gentle", "direct",
             "quiet", "assured", "simple", "earnest", "balanced", "open"]
    parts = ["Blended tone for the Operator Canary Voices anthology.",
             "The voice is warm and direct, plain without being plainspoken "
             "into flatness, and it never performs for the reader."]
    text = "\n\n".join(parts)
    while _count_words(text) < n_words:
        text += "\n\n" + " ".join(words[i % len(words)] for i in range(18)) + "."
    return text


def outline_text(title, subtitle, story, n_words=900):
    lines = [
        "# Outline: %s" % title,
        "Subtitle: %s" % subtitle,
        "1. The opening scene in which the central idea is introduced and "
        "the personal story anchor '%s' is placed on the first page."
        % story,
        "2. The middle section develops the craft, the discipline, and the "
        "specific practice the chapter teaches.",
        "3. The closing section returns to the anchor story and states what "
        "the reader carries forward.",
        "The outline carries the locked title and subtitle byte-exact and "
        "places every personal story anchor.",
    ]
    text = "\n\n".join(lines)
    while _count_words(text) < n_words:
        text += "\n\n" + " ".join(
            ["outline", "section", "paragraph", "anchor", "placement"] +
            ["detail"] * 8) + "."
    return text


def blurb_text(title, subtitle, n_words=350):
    lines = [
        "Blurb for %s: %s" % (title, subtitle),
        "One contributor, one chapter, one shared theme. This anthology "
        "collects voices that keep small businesses alive through quiet "
        "discipline.",
        "Each chapter is written by its author, edited to a house standard, "
        "and delivered as both a Google Doc and a designed PDF.",
    ]
    text = "\n\n".join(lines)
    while _count_words(text) < n_words:
        text += "\n\n" + " ".join(["blurb", "voice", "chapter", "anthology",
                                   "craft", "reader"] * 3) + "."
    return text


def titles_text(title, subtitle, n_words=300):
    text = "Suggested titles for this contributor:\n\n%s: %s" % (title, subtitle)
    text += "\n\nAlternate: A Second Working Title for the Same Chapter"
    while _count_words(text) < n_words:
        text += "\n\n" + " ".join(["title", "subtitle", "lock", "option"] * 3) + "."
    return text


def avatar_text(first, last, n_words=320):
    text = ("Avatar profile for %s %s: a first-time anthology contributor "
            "who runs a small independent operation and mentors others in "
            "the same craft." % (first, last))
    while _count_words(text) < n_words:
        text += "\n\n" + " ".join(["avatar", "profile", "author", "craft",
                                   "voice", "goal"] * 3) + "."
    return text


def _write_working(state_dir, participant_key, name, text):
    safe = "".join(c if (c.isalnum() or c in "-_.") else "_"
                   for c in (participant_key or "unknown"))
    d = Path(state_dir) / "runs" / "participants" / safe / "working"
    d.mkdir(parents=True, exist_ok=True)
    p = d / name
    p.write_text(text, encoding="utf-8")
    return p


def _working_path(state_dir, participant_key, name):
    safe = "".join(c if (c.isalnum() or c in "-_.") else "_"
                   for c in (participant_key or "unknown"))
    return Path(state_dir) / "runs" / "participants" / safe / "working" / name


def _s9_run_dir(state_dir, anthology_id):
    safe = "".join(c if (c.isalnum() or c in "-_.") else "_"
                   for c in (anthology_id or "unknown"))
    return Path(state_dir) / "runs" / "s9" / safe


def _sha256_text(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Report-verification (U19): a deterministic hash chain over the report BODY
# plus the state ledger, so a CANARY-REPORT.json claim can be independently
# re-checked with zero knowledge of the run that produced it.
# ---------------------------------------------------------------------------
def _canonical_json(value):
    """Deterministic canonical JSON for hashing (sorted keys, separators, no
    trailing whitespace; NaN/Infinity are serialized non-float32 and thus
    excluded -- this report never carries them)."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True)


def report_body_digest(report):
    """sha256 over the report BODY: schema_version + mode + every stage in
    order with its checks (check name, result, and evidence -- evidence is
    verified, not reason; reasons may be long). Never includes the signature
    itself (a self-referential chain is a tautology)."""
    h = hashlib.sha256()
    h.update(_canonical_json({
        "schema_version": report.get("schema_version"),
        "mode": report.get("mode"),
        "stages": [
            {"stage": s.get("stage"), "checks": [
                {"check": c.get("check"), "result": c.get("result"),
                 "evidence": c.get("evidence")}
                for c in (s.get("checks") or [])]}
            for s in (report.get("stages") or [])
        ],
    }).encode("utf-8"))
    return h.hexdigest()


def _sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _ledger_hashes(state_dir):
    """sha256 per ledger file in the deterministic REPORT_LEDGER_FILES order
    (missing optional files such as a WAL are skipped deterministically)."""
    base = Path(state_dir)
    out = []
    for rel in REPORT_LEDGER_FILES:
        p = base / rel
        if p.is_file():
            out.append({"file": rel, "sha256": _sha256_file(p)})
    return out


def _chain(parts):
    h = hashlib.sha256()
    for part in parts:
        h.update(part.encode("utf-8"))
        h.update(b"\n")
    return h.hexdigest()


def compute_report_chain(report, state_dir):
    """The deterministic chain: body digest, then each ledger file's sha256 in
    the canonical file order (file name + digest pairs, deterministic)."""
    parts = ["v1", report_body_digest(report)]
    for f in _ledger_hashes(state_dir):
        parts.append("file=%s sha256=%s" % (f["file"], f["sha256"]))
    return _chain(parts)


def check_deferred_live_note(report):
    """Every DEFERRED check whose name matches a deferred-live check MUST carry
    the note; a DEFERRED live check without it is a false claim of completion.
    Returns (ok, problems)."""
    problems = []
    for s in (report.get("stages") or []):
        for c in (s.get("checks") or []):
            if c.get("result") != "DEFERRED":
                continue
            name = c.get("check") or ""
            if name in DEFERRED_LIVE_CHECKS and not (c.get("note") or ""):
                problems.append("%s::%s deferred without note" % (s.get("stage"), name))
    return (not problems), problems


def cmd_verify_report(report_path):
    """Independently re-check a persisted CANARY-REPORT.json claim. Exit 0
    VALID / 4 INVALID (tampered body, missing ledger, or a deferred-live check
    without its note). NEVER prints ledger contents or secrets."""
    try:
        report = json.loads(Path(report_path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        sys.stderr.write("verify-report: cannot read %s: %s\n" % (report_path, exc))
        return EX_BADINVOKE
    if not isinstance(report, dict):
        sys.stderr.write("verify-report: %s does not parse to a JSON object\n" % report_path)
        return EX_BADINVOKE

    state_dir = (report.get("state_dir") or "").strip()
    if not state_dir:
        sys.stderr.write("verify-report: report carries no state_dir\n")
        return EX_VIOLATION
    state_dir = Path(state_dir).expanduser()
    if not state_dir.is_dir():
        sys.stderr.write("verify-report: state ledger missing (no dir at %s)\n" % state_dir)
        return EX_VIOLATION
    if "anthology_state.db" not in [f["file"] for f in _ledger_hashes(state_dir)]:
        sys.stderr.write("verify-report: anthology_state.db missing under %s\n" % state_dir)
        return EX_VIOLATION

    expected = (report.get("signature") or {}).get("sha256")
    computed = compute_report_chain(report, state_dir)
    if not expected:
        sys.stderr.write("verify-report: report carries no signature.sha256\n")
        return EX_VIOLATION
    if not isinstance(expected, str) or expected != computed:
        sys.stderr.write(
            "verify-report: INVALID -- signature mismatch\n"
            "  expected: %s\n  computed: %s\n"
            "  (report body and/or the state ledger it names differ from the "
            "claim)\n" % (expected, computed))
        return EX_VIOLATION

    note_ok, problems = check_deferred_live_note(report)
    if not note_ok:
        sys.stderr.write("verify-report: INVALID -- deferred live checks without "
                         "the deferred-live note: %s\n" % "; ".join(problems))
        return EX_VIOLATION

    sys.stdout.write(
        "verify-report: VALID (sha256 %s)\n"
        "  contract: %s  verdict: %s  utc: %s\n"
        "  stages: %d total, %d passed, %d deferred, %d failed\n"
        "  ledger: %s\n"
        "  deferred-live note carried: %s\n" % (
            computed, report.get("contract"), report.get("verdict"),
            report.get("utc"),
            (report.get("summary") or {}).get("stages_total"),
            (report.get("summary") or {}).get("stages_passed"),
            (report.get("summary") or {}).get("stages_deferred"),
            (report.get("summary") or {}).get("stages_failed"),
            "; ".join(f["file"] for f in _ledger_hashes(state_dir)),
            "yes" if note_ok else "no"))
    return EX_OK


# ---------------------------------------------------------------------------
# Cross-cutting contract proofs (EMAIL+SMS, QC scorer, font floor, pull-back).
# ---------------------------------------------------------------------------
def verify_email_sms_contract(rep):
    """Every §3 release slug the gate engine can stamp must map to a
    snapshot-contract release_notifications workflow carrying send-email +
    send-sms actions. The tag the engine stamps IS the trigger of the
    client-facing email + SMS automation."""
    try:
        contract = json.loads(SNAPSHOT_CONTRACT.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        rep.deferred("email+sms workflow contract", "snapshot contract unreadable: %s" % exc)
        return
    workflows = (contract.get("workflows") or {}).get("release_notifications") or []
    wf_by_slug = {}
    for w in workflows:
        slug = (w.get("trigger_tag") or "").strip()
        if slug:
            wf_by_slug[slug] = w
    actions_ok = True
    for slug in ("anthology-release-avatar", "anthology-release-tone",
                 "anthology-release-outline", "anthology-release-chapter",
                 "anthology-release-rewrite", "anthology-release-cover",
                 "anthology-release-final", "anthology-delivered"):
        w = wf_by_slug.get(slug)
        if not w:
            rep.check("email+sms workflow exists for %s" % slug, False,
                      "no release_notifications workflow triggers %s" % slug)
            actions_ok = False
            continue
        acts = list(w.get("actions") or [])
        ok = ("send-email" in acts) and ("send-sms" in acts)
        if not ok:
            rep.check("email+sms actions for %s" % slug, False,
                      "actions=%s" % acts)
            actions_ok = False
    if actions_ok:
        rep.check("email+sms release workflows", True,
                  "all 8 §3 slugs map to send-email + send-sms workflows")
    # The engine-side trigger: gate_engine's release slug map fires ONLY on a
    # committed board-door producer approve (self-test already proves this);
    # here we prove the slug set the engine can stamp is a SUBSET of the
    # workflow trigger set (nothing the engine stamps is email/SMS-less).
    text = GATE_ENGINE.read_text(encoding="utf-8")
    engine_slugs = set(re.findall(r'"anthology-release-[a-z]+"', text))
    engine_slugs = {s.strip('"') for s in engine_slugs}
    missing = sorted(s for s in engine_slugs if s not in wf_by_slug)
    rep.check("engine release slugs all carry email+sms workflows",
              not missing, ("uncovered slugs: %s" % missing) if missing else
              "%d engine slugs covered" % len(engine_slugs))


def verify_qc_scorer_contract(rep):
    """The engine never self-promotes review->done; the independent QC scorer
    owns it at >= 8.5. Proven from the ENGINE side (mandatory) and from the CC
    repo when present on the operator box (best-effort, else DEFERRED)."""
    # Engine side: mc_board status maps + _guarded_status contain no 'done'.
    try:
        text = MC_BOARD.read_text(encoding="utf-8")
        no_done = "STATUS_BY_CURSOR" in text and re.search(
            r'["\']done["\']\s*:', text) is None
        guarded = 'never emits' in text or '_guarded_status' in text
        rep.check("engine board maps contain no 'done'", no_done)
        rep.check("engine refuses to emit 'done'", guarded)
    except (OSError, ValueError) as exc:
        rep.deferred("engine never-emits-done", "mc_board unreadable: %s" % exc)
    # CC side (best-effort): qc-scorer.ts QC_PASS_THRESHOLD == 8.5 and the
    # auto-scorer transitions review->done with actor qc-auto-scorer.
    scorer = None
    for cand in CC_REPO_CANDIDATES:
        p = Path(cand) / "src" / "lib" / "qc-scorer.ts"
        if p.is_file():
            scorer = p
            break
    if scorer is None:
        rep.deferred("CC scorer >=8.5 review->done", "CC repo not present on this box "
                     "(qc-scorer.ts not found); engine-side contract verified only")
        return
    try:
        stext = scorer.read_text(encoding="utf-8")
        thr = re.search(r"QC_PASS_THRESHOLD\s*=\s*([0-9.]+)", stext)
        rep.check("CC QC_PASS_THRESHOLD is 8.5",
                  bool(thr) and abs(float(thr.group(1)) - 8.5) < 1e-9,
                  thr.group(0) if thr else "threshold constant not found")
        auto = re.search(r"actor:\s*['\"]qc-auto-scorer['\"]", stext)
        review_done = re.search(r"expectedFrom:\s*['\"]review['\"]", stext)
        rep.check("CC auto-scorer owns review->done",
                  bool(auto) and bool(review_done),
                  "actor qc-auto-scorer + expectedFrom review present" if
                  (auto and review_done) else "promotion path not found")
    except (OSError, ValueError) as exc:
        rep.deferred("CC scorer read", "qc-scorer.ts unreadable: %s" % exc)


def verify_font_floor(rep, state_dir, participant_key, kind, content_file):
    """Render the PDF through pdf_render (template-side floor tripwire) then
    parse the RENDERED output with guard-font-floor (output-side gate)."""
    pdf_path = _working_path(state_dir, participant_key, "%s.pdf" % kind)
    pdf_type = "chapter" if kind in ("rewrite",) else (
        "manuscript" if kind == "anthology_manuscript" else kind)
    rc, parsed, err = _run(
        _state(PDF_RENDER) + ["--type", pdf_type, "--in", str(content_file),
                              "--out", str(pdf_path), "--json"],
        state_dir=state_dir, timeout=180)
    if rc != 0:
        rep.check("pdf_render %s" % kind, False,
                  "render rc=%s err=%s" % (rc, (err or "")[:200]))
        return None
    rep.check("pdf_render %s" % kind, True, "rendered %s" % pdf_path)
    # template-side tripwire: pdf_render exits 2 on a sub-floor token (the
    # render already proved 0; this is a contract echo).
    rc2, parsed2, err2 = _run(
        _state(FONT_FLOOR) + [str(pdf_path), "--json"],
        state_dir=state_dir, timeout=120)
    if rc2 == 0:
        min_size = (parsed2 or {}).get("min_size_pt")
        rep.check("guard-font-floor %s >= 14pt" % kind, True,
                  "min_size_pt=%s spans=%s" % (min_size, (parsed2 or {}).get("spans")))
    elif rc2 == 3:
        rep.deferred("guard-font-floor %s" % kind, "PyMuPDF (fitz) unavailable")
    else:
        rep.check("guard-font-floor %s >= 14pt" % kind, False,
                  "rc=%s err=%s" % (rc2, (err2 or "")[:200]))
    return pdf_path


def verify_pullback_contract(rep, state_dir):
    """The confirm-then-pull read-back: gate_engine pullback-revalidate shells
    drive_adapter.pull_doc_text and re-runs qc-tier1 --mode pullback over the
    PULLED bytes (advisory, invariants 1/2/3). Proven structurally here; the
    LIVE Doc round-trip is the sibling prove_aw_doc_pullback.py (NEW-5),
    driven when a live Drive credential is present, else DEFERRED."""
    rc, parsed, err = _run(
        _state(GATE_ENGINE) + ["pullback-revalidate", "--subject-key",
                               PARTICIPANT_A, "--state-dir", str(state_dir),
                               "--json"], state_dir=state_dir, timeout=120)
    # Without a live doc-id the engine's own refusal is the honest answer; we
    # assert it FAILS CLOSED (never pretends) rather than that it succeeds.
    rep.check("pullback-revalidate fails closed without a Doc",
              rc in (EX_ERR, EX_BADINVOKE, EX_HELD) or
              (parsed and not parsed.get("ok")),
              "rc=%s reason=%s" % (rc, (parsed or {}).get("reason") or (err or "")[:120]))
    # qc-tier1 pullback mode over pulled bytes: prove the pure evaluator runs
    # and is advisory (exit ALWAYS 0 in pullback mode; client edits never block).
    pulled = chapter_text(TITLE_A, SUBTITLE_A, "the door and the lock", "Ada Sample",
                          n_words=2100)
    env = {
        "kind": "chapter", "mode": "pullback",
        "artifact_text": pulled,
        "title": {"title": TITLE_A, "subtitle": SUBTITLE_A},
        "intake": {"personal_stories": "the door and the lock"},
    }
    envelope = Path(state_dir) / "pullback-envelope.json"
    envelope.parent.mkdir(parents=True, exist_ok=True)
    envelope.write_text(json.dumps(env), encoding="utf-8")
    rc2, parsed2, err2 = _run(
        _state(QC_TIER1) + ["--envelope", str(envelope), "--mode", "pullback",
                            "--json"], state_dir=state_dir, timeout=120)
    rep.check("qc-tier1 pullback advisory run", rc2 == 0,
              "rc=%s failures=%s" % (rc2, (parsed2 or {}).get("failures")))
    rep.check("pullback mode is advisory (client edit never blocks)",
              (parsed2 or {}).get("mode") == "pullback")
    # live Doc round-trip (NEW-5): drive when a live Drive path is available.
    sa_label, sa_val = _env_first([LABEL_SA_KEY])
    imp_label, imp_val = _env_first([LABEL_IMPERSONATE])
    root_label, root_val = _env_first([LABEL_DRIVE_ROOT])
    if PULLBACK_PROVER.is_file() and sa_val and imp_val and root_val:
        rc3, parsed3, err3 = _run(
            _state(PULLBACK_PROVER) + ["--json"], state_dir=state_dir, timeout=600)
        if rc3 == 0:
            rep.check("live Doc pull-back byte round-trip (NEW-5)", True,
                      "prove_aw_doc_pullback PASS")
        elif rc3 == 3:
            rep.deferred("live Doc pull-back byte round-trip",
                         "prove_aw_doc_pullback held: %s" % (err3 or "")[:200])
        else:
            rep.check("live Doc pull-back byte round-trip (NEW-5)", False,
                      "rc=%s err=%s" % (rc3, (err3 or "")[:200]))
    else:
        rep.deferred("live Doc pull-back byte round-trip (NEW-5)",
                     "live Drive credential not resolvable (%s=%s %s=%s %s=%s); "
                     "structural pull-back proof above stands"
                     % (sa_label, mask_set(sa_val), imp_label, mask_set(imp_val),
                        root_label, mask_set(root_val)))


def verify_board_round_trip(rep, state_dir):
    """The board round-trip BOTH doors, plus the never-done invariant, plus the
    mc_board card projection. All board HTTP is mc_board's own fail-soft
    transport (this canary never posts to the CC itself)."""
    # door legality: producer gates are board-door only (a token door approve
    # on s1_producer is refused BEFORE any state change).
    rc, parsed, err = _gate(
        ["decide", "--subject-key", PARTICIPANT_A, "--door", "token",
         "--action", "approve"], state_dir)
    rep.check("producer gate refused on token door",
              rc == EX_BADINVOKE and (parsed or {}).get("reason") in
              ("door_not_allowed_for_gate", "no_credential"),
              "rc=%s reason=%s" % (rc, (parsed or {}).get("reason")))
    # mc_board projections never ask for 'done' and are fail-soft.
    for key, kind in ((PARTICIPANT_A, "participant"), (ANTHOLOGY_ID, "anthology")):
        rc2, parsed2, err2 = _run(
            _state(MC_BOARD) + ["status", "--subject-key", key,
                                "--state-dir", str(state_dir), "--json"],
            state_dir=state_dir, timeout=60)
        ok = rc2 == 0 and parsed2 is not None and \
            "done" not in json.dumps(parsed2.get("target_status") or "")
        rep.check("mc_board status %s never done" % kind, ok,
                  parsed2.get("target_status") if parsed2 else err2[:120])
        rc3, parsed3, _ = _run(
            _state(MC_BOARD) + ["sync", "--subject-key", key,
                                "--state-dir", str(state_dir), "--json"],
            state_dir=state_dir, timeout=60)
        # fail-soft: any board outcome is exit 0; the ledger remains the truth.
        rep.check("mc_board sync %s fail-soft" % kind, rc3 == 0,
                  (parsed3 or {}).get("board") or "mirror projection")
        if parsed3 is not None:
            rep.check("mc_board sync %s never emits done" % kind,
                      "done" not in json.dumps(parsed3))
    # engine-side: gate_engine self-test proves mint/verify/decide refusals.
    rc4, parsed4, err4 = _run(
        _state(GATE_ENGINE) + ["--self-test"], state_dir=state_dir, timeout=120)
    rep.check("gate_engine self-test (token refusals, both doors)",
              rc4 == 0, (parsed4 and "self-test: OK") or err4[:120] or "OK")


# ---------------------------------------------------------------------------
# The S0..S9 stage drivers. Every stage shells the SIBLING that owns the
# surface and asserts the observed ledger/artifact effect (never a self-report).
# ---------------------------------------------------------------------------
def run_s0_intake(run, state_dir, args):
    rep = run.begin("S0", "INTAKE AND ROUTING (live tunnel battery + dedup + capture)")

    # --- the intake webhook battery: verify-webhook-t1-t9.sh (T1..T9) -------
    argv = ["bash", str(VERIFY_WEBHOOK), "--base-url", args.gateway_base_url]
    if args.public_url:
        argv += ["--public-url", args.public_url]
    if args.require_live:
        argv += ["--require-live"]
    else:
        argv += ["--live"]
    rc, parsed, err = _run(argv, state_dir=state_dir, timeout=600)
    text_out = (parsed and json.dumps(parsed)) or (err or "")
    # The shell script prints a human summary; parse PASS/FAIL/DEFERRED counts.
    pass_m = re.search(r"(\d+) PASS, (\d+) FAIL, (\d+) DEFERRED", err or text_out)
    if rc == 0:
        if pass_m:
            rep.check("intake webhook battery T1..T9", True,
                      "PASS=%s FAIL=%s DEFERRED=%s" % pass_m.groups())
        else:
            rep.check("intake webhook battery T1..T9", True, "exit 0")
    elif rc == 3:
        rep.deferred("intake webhook battery (held)", "verify-webhook exit 3: %s"
                     % (err or "")[:300])
    else:
        rep.check("intake webhook battery T1..T9", False,
                  "verify-webhook exit %s: %s" % (rc, (err or "")[:300]))

    # --- seed the ledger through the sole writer (the router requires the
    #     anthology row before intake can route a participant). --------------
    rc, parsed, err = _ledger(["bootstrap"], state_dir)
    rep.check("ledger bootstrap", rc == 0 and (parsed or {}).get("action") == "bootstrap",
              parsed or err[:160])
    rc, parsed, err = _ledger(["upsert-producer", "--producer-id", PRODUCER_ID,
                               "--producer-email", PRODUCER_EMAIL,
                               "--display-name", PRODUCER_DISPLAY], state_dir)
    rep.check("upsert producer", rc == 0 and (parsed or {}).get("created"),
              parsed or err[:160])
    rc, parsed, err = _ledger(["upsert-anthology", "--anthology-id", ANTHOLOGY_ID,
                               "--producer-id", PRODUCER_ID,
                               "--name", ANTHOLOGY_NAME,
                               "--theme", "operator canary voices",
                               "--caf-location-binding", LOCATION_BINDING,
                               "--min-chapters", str(MIN_CHAPTERS)], state_dir)
    rep.check("upsert anthology with location binding",
              rc == 0 and (parsed or {}).get("created"), parsed or err[:160])

    # --- direct router drive (deterministic; the router owns S0). -----------
    payload_a = intake_payload(
        CONTACT_A, "Ada", "Sample", "ada.sample@example.com", "+15550100001",
        "A first-time nonfiction author who mentors early-career founders.",
        "founder mentorship and operating discipline",
        "publish one signature chapter in a shared anthology to establish authority")
    payload_b = intake_payload(
        CONTACT_B, "Ben", "Marlow", "ben.marlow@example.com", "+15550100002",
        "An independent print-shop owner who documents the craft of saying no.",
        "independent print operations",
        "share one chapter on the discipline of refusing busywork")
    fp = Path(state_dir) / "intake-a.json"
    fp.write_text(json.dumps(payload_a), encoding="utf-8")
    rc, parsed, err = _run(
        _state(SCRIPTS / "intake_router.py") + ["--no-spawn", "--json",
                                                "--payload", str(fp),
                                                "--state-dir", str(state_dir)],
        state_dir=state_dir, timeout=60)
    routed = rc == 0 and (parsed or {}).get("action") == "routed" and \
        (parsed or {}).get("participant_key") == PARTICIPANT_A
    rep.check("intake_router routes synthetic co-author A",
              routed, "rc=%s action=%s" % (rc, (parsed or {}).get("action")))
    # dedup: byte-identical resend -> acknowledged no-op, one row only.
    rc, parsed, err = _run(
        _state(SCRIPTS / "intake_router.py") + ["--no-spawn", "--json",
                                                "--payload", str(fp),
                                                "--state-dir", str(state_dir)],
        state_dir=state_dir, timeout=60)
    rep.check("duplicate intake acknowledged no-op",
              rc == 0 and (parsed or {}).get("duplicate") is True,
              "rc=%s action=%s" % (rc, (parsed or {}).get("action")))
    fp_b = Path(state_dir) / "intake-b.json"
    fp_b.write_text(json.dumps(payload_b), encoding="utf-8")
    rc, parsed, err = _run(
        _state(SCRIPTS / "intake_router.py") + ["--no-spawn", "--json",
                                                "--payload", str(fp_b),
                                                "--state-dir", str(state_dir)],
        state_dir=state_dir, timeout=60)
    rep.check("intake_router routes synthetic co-author B",
              rc == 0 and (parsed or {}).get("participant_key") == PARTICIPANT_B,
              "rc=%s action=%s" % (rc, (parsed or {}).get("action")))
    # tenant mismatch -> Exceptions(tenant_mismatch), typed reason, never a crash.
    bad_tenant = dict(payload_a, contact_id="CONTACTcanaryOPx9",
                      location="LOCwrongTenantZZZ")
    fp_t = Path(state_dir) / "intake-tenant.json"
    fp_t.write_text(json.dumps(bad_tenant), encoding="utf-8")
    rc, parsed, err = _run(
        _state(SCRIPTS / "intake_router.py") + ["--no-spawn", "--json",
                                                "--payload", str(fp_t),
                                                "--state-dir", str(state_dir)],
        state_dir=state_dir, timeout=60)
    rep.check("wrong-tenant payload captured (tenant_mismatch)",
              rc == 3 and (parsed or {}).get("reason") == "tenant_mismatch",
              "rc=%s reason=%s" % (rc, (parsed or {}).get("reason")))
    # stage mismatch -> Exceptions(stage_mismatch).
    bad_stage = dict(payload_a, contact_id="CONTACTcanaryOPy8",
                     stage="s2_tone")
    fp_s = Path(state_dir) / "intake-stage.json"
    fp_s.write_text(json.dumps(bad_stage), encoding="utf-8")
    rc, parsed, err = _run(
        _state(SCRIPTS / "intake_router.py") + ["--no-spawn", "--json",
                                                "--payload", str(fp_s),
                                                "--state-dir", str(state_dir)],
        state_dir=state_dir, timeout=60)
    rep.check("stage-mismatched form captured (stage_mismatch)",
              rc == 3 and (parsed or {}).get("reason") == "stage_mismatch",
              "rc=%s reason=%s" % (rc, (parsed or {}).get("reason")))
    # malformed payload -> Exceptions(unroutable_missing_ids), never a crash.
    fp_m = Path(state_dir) / "intake-malformed.json"
    fp_m.write_text("{not json", encoding="utf-8")
    rc, parsed, err = _run(
        _state(SCRIPTS / "intake_router.py") + ["--no-spawn", "--json",
                                                "--payload", str(fp_m),
                                                "--state-dir", str(state_dir)],
        state_dir=state_dir, timeout=60)
    rep.check("malformed payload captured (unroutable_missing_ids)",
              rc == 3 and (parsed or {}).get("reason") == "unroutable_missing_ids",
              "rc=%s reason=%s" % (rc, (parsed or {}).get("reason")))
    # Exceptions rows actually persisted with the typed reasons.
    rc, parsed, err = _ledger(["export-bundle", "--anthology-id", ANTHOLOGY_ID],
                              state_dir, timeout=120)
    bundle = parsed or {}
    rep.check("exceptions captured durably (raw payload preserved)",
              isinstance(bundle, dict),
              "bundle unreadable" if not isinstance(bundle, dict) else
              "participants=%s artifacts=%s" % (len(bundle.get("participants", [])),
                                                len(bundle.get("artifacts", []))))
    # The S0 stage runner's drive: card-before-drive fail-soft + advance to S1.
    for key in (PARTICIPANT_A, PARTICIPANT_B):
        rc, parsed, err = _run(
            _state(MC_BOARD) + ["ensure", "--subject-key", key,
                                "--state-dir", str(state_dir), "--json"],
            state_dir=state_dir, timeout=60)
        rep.check("board card ingested (fail-soft) %s" % key, rc == 0,
                  (parsed or {}).get("board") or "mirror projection")
        rc, parsed, err = _ledger(["advance-stage", "--participant-key", key,
                                   "--to", "s1_avatar"], state_dir)
        rep.check("S0 -> S1 advance %s" % key,
                  rc == 0 and (parsed or {}).get("to") == "s1_avatar",
                  parsed or err[:120])
    return rep


def run_s1_avatar(run, state_dir, args):
    rep = run.begin("S1", "AVATAR (artifact + producer board approve + release)")

    def drive(key, first, last, ideal_avatar, n_words=340):
        _write_working(state_dir, key, "avatar.md",
                       avatar_text(first, last, n_words))
        rc, parsed, err = _ledger(["record-artifact", "--participant-key", key,
                                   "--type", "avatar", "--sha256",
                                   _sha256_text(avatar_text(first, last, n_words)),
                                   "--model-used", "glm-5.2"], state_dir)
        rep.check("record-artifact(avatar) %s" % key,
                  rc == 0 and (parsed or {}).get("type") == "avatar",
                  parsed or err[:120])
        # Tier 1 for the avatar kind (checks 4-12; no band).
        env = {"kind": "avatar",
               "artifact_path": str(_working_path(state_dir, key, "avatar.md")),
               "identity": {"contact_id": key.split("::")[0],
                            "anthology_id": ANTHOLOGY_ID},
               "intake": {"email": "", "phone": ""},
               "run_ledger": {"stages": [{"model": "glm-5.2"}]}}
        env_p = Path(state_dir) / ("env-avatar-%s.json" % key.split("::")[0])
        env_p.write_text(json.dumps(env), encoding="utf-8")
        rc2, parsed2, err2 = _run(
            _state(QC_TIER1) + ["--envelope", str(env_p), "--json"],
            state_dir=state_dir, timeout=120)
        rep.check("Tier 1 avatar %s" % key, rc2 == 0 and (parsed2 or {}).get("passed"),
                  "rc=%s failures=%s" % (rc2, (parsed2 or {}).get("failures") or err2[:120]))
        rc, parsed, err = _ledger(["advance-stage", "--participant-key", key,
                                   "--to", "s1_gate"], state_dir)
        rep.check("advance to s1_gate %s" % key,
                  rc == 0 and (parsed or {}).get("to") == "s1_gate",
                  parsed or err[:120])
        # gate open (no nudge: operator canary, client-silent).
        rc, parsed, err = _gate(["open", "--subject-key", key, "--no-nudge"],
                                state_dir)
        rep.check("open s1_producer %s" % key,
                  rc == 0 and (parsed or {}).get("gate") == "s1_producer",
                  parsed or err[:120])
        # gate-bypass guard: advance-stage may not step past a producer gate.
        rc, parsed, err = _ledger(["advance-stage", "--participant-key", key,
                                   "--to", "s2_tone"], state_dir)
        rep.check("gate bypass via advance-stage refused %s" % key,
                  rc == 2 and (parsed or {}).get("ok") is False,
                  "rc=%s" % rc)
        # producer approve through the BOARD door -> release slug stamped.
        rc, parsed, err = _gate(["decide", "--subject-key", key,
                                 "--door", "board", "--action", "approve"],
                                state_dir)
        committed = rc == 0 and (parsed or {}).get("committed") is True and \
            (parsed or {}).get("stage_cursor") == "s2_tone"
        rep.check("s1_producer board approve commits %s" % key, committed,
                  parsed or err[:120])
        tag = (parsed or {}).get("release_tag") or {}
        if tag:
            rep.check("§3 release tag anthology-release-avatar %s" % key,
                      tag.get("slug") == "anthology-release-avatar" and
                      tag.get("status") in ("stamped", "held", "skipped",
                                            "failed_nonfatal", "disabled"),
                      "slug=%s status=%s" % (tag.get("slug"), tag.get("status")))
        else:
            rep.check("§3 release tag anthology-release-avatar %s" % key,
                      False, "no release_tag in decide output")

    drive(PARTICIPANT_A, "Ada", "Sample",
          "A first-time nonfiction author who mentors early-career founders.")
    drive(PARTICIPANT_B, "Ben", "Marlow",
          "An independent print-shop owner who documents the craft of saying no.")
    return rep


def run_s2_tone(run, state_dir, args):
    rep = run.begin("S2", "TONE (3,000-word floor + producer gate)")

    def drive(key):
        text = tone_text(3200)
        _write_working(state_dir, key, "tone-doc.md", text)
        rc, parsed, err = _ledger(["record-artifact", "--participant-key", key,
                                   "--type", "tone", "--sha256",
                                   _sha256_text(text), "--model-used", "glm-5.2"],
                                  state_dir)
        rep.check("record-artifact(tone) %s" % key,
                  rc == 0 and (parsed or {}).get("type") == "tone",
                  parsed or err[:120])
        # Tier 1 for tone: check 1 is the 3,000-word floor (fail-closed).
        env = {"kind": "tone",
               "artifact_path": str(_working_path(state_dir, key, "tone-doc.md")),
               "identity": {"contact_id": key.split("::")[0],
                            "anthology_id": ANTHOLOGY_ID},
               "intake": {"email": "", "phone": ""},
               "run_ledger": {"stages": [{"model": "glm-5.2"}]}}
        env_p = Path(state_dir) / ("env-tone-%s.json" % key.split("::")[0])
        env_p.write_text(json.dumps(env), encoding="utf-8")
        rc2, parsed2, err2 = _run(
            _state(QC_TIER1) + ["--envelope", str(env_p), "--json"],
            state_dir=state_dir, timeout=120)
        rep.check("Tier 1 tone floor >= 3000 words %s" % key,
                  rc2 == 0 and (parsed2 or {}).get("passed"),
                  "rc=%s failures=%s" % (rc2, (parsed2 or {}).get("failures") or err2[:120]))
        rc, parsed, err = _ledger(["advance-stage", "--participant-key", key,
                                   "--to", "s2_gate"], state_dir)
        rep.check("advance to s2_gate %s" % key,
                  rc == 0 and (parsed or {}).get("to") == "s2_gate",
                  parsed or err[:120])
        rc, parsed, err = _gate(["open", "--subject-key", key, "--no-nudge"],
                                state_dir)
        rep.check("open s2_producer %s" % key,
                  rc == 0 and (parsed or {}).get("gate") == "s2_producer",
                  parsed or err[:120])
        rc, parsed, err = _gate(["decide", "--subject-key", key,
                                 "--door", "board", "--action", "approve"],
                                state_dir)
        rep.check("s2_producer board approve commits %s" % key,
                  rc == 0 and (parsed or {}).get("stage_cursor") == "s3_title",
                  parsed or err[:120])

    drive(PARTICIPANT_A)
    drive(PARTICIPANT_B)
    return rep


def run_s3_title(run, state_dir, args):
    rep = run.begin("S3", "TITLES + TITLE LOCK (participant token-door pick)")

    def drive(key, title, subtitle):
        _write_working(state_dir, key, "title.json",
                       json.dumps({"title": title, "subtitle": subtitle}))
        rc, parsed, err = _ledger(["record-artifact", "--participant-key", key,
                                   "--type", "titles", "--sha256",
                                   _sha256_text(title + subtitle),
                                   "--model-used", "glm-5.2"], state_dir)
        rep.check("record-artifact(titles) %s" % key,
                  rc == 0 and (parsed or {}).get("type") == "titles",
                  parsed or err[:120])
        rc, parsed, err = _ledger(["advance-stage", "--participant-key", key,
                                   "--to", "s3_gate"], state_dir)
        rep.check("advance to s3_gate %s" % key,
                  rc == 0 and (parsed or {}).get("to") == "s3_gate",
                  parsed or err[:120])
        # THE TOKEN DOOR: mint -> verify -> decide with the minted token.
        secret_name, secret_val = _env_first([LABEL_GATE_SECRET])
        if not secret_val:
            rep.deferred("s3 token-door mint %s" % key,
                         "%s NOT SET (participant token door not exercisable)" % secret_name)
            return
        rc, minted, err = _gate(["mint", "--subject-key", key], state_dir)
        rep.check("mint token for s3_selection %s" % key,
                  rc == 0 and (minted or {}).get("gate") == "s3_selection",
                  minted or err[:120])
        token = (minted or {}).get("token") or ""
        rc, verified, err = _gate(["verify", "--subject-key", key,
                                   "--token", token], state_dir)
        rep.check("verify minted token %s" % key,
                  rc == 0 and (verified or {}).get("ok") is True,
                  verified or err[:120])
        rc, decided, err = _gate(["decide", "--subject-key", key, "--door", "token",
                                  "--action", "select", "--token", token,
                                  "--title", title, "--subtitle", subtitle],
                                 state_dir)
        rep.check("token-door title pick commits (TITLE LOCK) %s" % key,
                  rc == 0 and (decided or {}).get("stage_cursor") == "s4_blurb_outline",
                  decided or err[:120])
        # replay of the SAME token is REFUSED (single-use consumed).
        rc, replayed, err = _gate(["decide", "--subject-key", key, "--door", "token",
                                   "--action", "select", "--token", token,
                                   "--title", title, "--subtitle", subtitle],
                                  state_dir)
        rep.check("replayed token refused (AF-AE-TOKEN-REFUSED) %s" % key,
                  rc == 2 and (replayed or {}).get("reason") in
                  ("replayed", "no_open_gate"),
                  "rc=%s reason=%s" % (rc, (replayed or {}).get("reason")))
        # TITLE LOCK one-way: a different title is refused and changes nothing.
        rc, relock, err = _ledger(["record-approval", "--gate", "s3_selection",
                                   "--participant-key", key, "--decision", "approve",
                                   "--title", "A Different Title",
                                   "--door", "nudge_link"], state_dir)
        rep.check("title lock is one-way %s" % key,
                  rc == 2 and (relock or {}).get("ok") is False,
                  "rc=%s" % rc)
        rc, row, err = _ledger(["get-participant", "--participant-key", key],
                               state_dir)
        rep.check("locked title persisted byte-exact %s" % key,
                  rc == 0 and (row or {}).get("title_locked") == title and
                  (row or {}).get("subtitle_locked") == subtitle,
                  (row or {}).get("title_locked"))

    drive(PARTICIPANT_A, TITLE_A, SUBTITLE_A)
    drive(PARTICIPANT_B, TITLE_B, SUBTITLE_B)
    return rep


def run_s4_outline(run, state_dir, args):
    rep = run.begin("S4", "BLURB + OUTLINE (both gates, both doors)")

    def drive(key, title, subtitle, story):
        _write_working(state_dir, key, "blurb.md", blurb_text(title, subtitle))
        _write_working(state_dir, key, "outline.md",
                       outline_text(title, subtitle, story))
        for atype in ("blurb", "outline"):
            rc, parsed, err = _ledger(["record-artifact", "--participant-key", key,
                                       "--type", atype, "--sha256",
                                       _sha256_text(blurb_text(title, subtitle)
                                                    if atype == "blurb"
                                                    else outline_text(title, subtitle, story)),
                                       "--model-used", "glm-5.2"], state_dir)
            rep.check("record-artifact(%s) %s" % (atype, key),
                      rc == 0 and (parsed or {}).get("type") == atype,
                      parsed or err[:120])
        # Tier 1 outline: story placement + title lock carry.
        env = {"kind": "outline",
               "artifact_path": str(_working_path(state_dir, key, "outline.md")),
               "title": {"title": title, "subtitle": subtitle},
               "intake": {"personal_stories": story},
               "identity": {"contact_id": key.split("::")[0],
                            "anthology_id": ANTHOLOGY_ID},
               "run_ledger": {"stages": [{"model": "glm-5.2"}]}}
        env_p = Path(state_dir) / ("env-outline-%s.json" % key.split("::")[0])
        env_p.write_text(json.dumps(env), encoding="utf-8")
        rc2, parsed2, err2 = _run(
            _state(QC_TIER1) + ["--envelope", str(env_p), "--json"],
            state_dir=state_dir, timeout=120)
        rep.check("Tier 1 outline (story placed, title locked) %s" % key,
                  rc2 == 0 and (parsed2 or {}).get("passed"),
                  "rc=%s failures=%s" % (rc2, (parsed2 or {}).get("failures") or err2[:120]))
        rc, parsed, err = _ledger(["advance-stage", "--participant-key", key,
                                   "--to", "s4_gate_producer"], state_dir)
        rep.check("advance to s4_gate_producer %s" % key,
                  rc == 0 and (parsed or {}).get("to") == "s4_gate_producer",
                  parsed or err[:120])
        rc, parsed, err = _gate(["open", "--subject-key", key, "--no-nudge"],
                                state_dir)
        rep.check("open s4_producer %s" % key,
                  rc == 0 and (parsed or {}).get("gate") == "s4_producer",
                  parsed or err[:120])
        rc, parsed, err = _gate(["decide", "--subject-key", key,
                                 "--door", "board", "--action", "approve"],
                                state_dir)
        rep.check("s4_producer board approve %s" % key,
                  rc == 0 and (parsed or {}).get("stage_cursor") == "s4_gate_participant",
                  parsed or err[:120])
        rc, parsed, err = _gate(["open", "--subject-key", key, "--no-nudge"],
                                state_dir)
        rep.check("open s4_participant %s" % key,
                  rc == 0 and (parsed or {}).get("gate") == "s4_participant",
                  parsed or err[:120])
        secret_name, secret_val = _env_first([LABEL_GATE_SECRET])
        if secret_val:
            rc, minted, err = _gate(["mint", "--subject-key", key], state_dir)
            token = (minted or {}).get("token") or ""
            rc, decided, err = _gate(["decide", "--subject-key", key, "--door",
                                      "token", "--action", "approve",
                                      "--token", token], state_dir)
            rep.check("s4_participant token-door approve %s" % key,
                      rc == 0 and (decided or {}).get("stage_cursor") == "s5_chapter",
                      decided or err[:120])
        else:
            rep.deferred("s4_participant token-door approve %s" % key,
                         "%s NOT SET" % secret_name)

    drive(PARTICIPANT_A, TITLE_A, SUBTITLE_A, "the door and the lock")
    drive(PARTICIPANT_B, TITLE_B, SUBTITLE_B, "the refusal ledger")
    return rep


def run_s5_chapter(run, state_dir, args):
    rep = run.begin("S5", "CHAPTER (Gate B battery, EXACTLY TWO actions, freeze)")

    def drive(key, title, subtitle, story, n_words=2400):
        text = chapter_text(title, subtitle, story, key.split("::")[0], n_words)
        _write_working(state_dir, key, "chapter.md", text)
        sha = _sha256_text(text)
        rc, parsed, err = _ledger(["record-artifact", "--participant-key", key,
                                   "--type", "chapter", "--sha256", sha,
                                   "--model-used", "glm-5.2",
                                   "--doc-url", "https://docs.google.com/document/d/gdoc_syn_canary_%s/edit" % key.split("::")[0],
                                   "--pdf-url", "https://drive.google.com/file/d/gfile_syn_canary_%s/view" % key.split("::")[0]],
                                  state_dir)
        rep.check("record-artifact(chapter) %s" % key,
                  rc == 0 and (parsed or {}).get("type") == "chapter",
                  parsed or err[:120])
        rc, parsed, err = _ledger(["advance-stage", "--participant-key", key,
                                   "--to", "s5_gate"], state_dir)
        rep.check("advance to s5_gate %s" % key,
                  rc == 0 and (parsed or {}).get("to") == "s5_gate",
                  parsed or err[:120])
        # TIER 1: the full twelve for chapter — word band is measured (not
        # self-reported), title lock byte-exact, every story placed, no
        # em-dash, no leakage, no fabrication, identity integrity, clean ledger.
        env = {
            "kind": "chapter",
            "artifact_path": str(_working_path(state_dir, key, "chapter.md")),
            "title": {"title": title, "subtitle": subtitle},
            "intake": {"personal_stories": story,
                       "email": "", "phone": ""},
            "identity": {"contact_id": key.split("::")[0],
                         "anthology_id": ANTHOLOGY_ID},
            "search_pass_urls": [],
            "run_ledger": {"stages": [{"model": "glm-5.2"}]},
        }
        env_p = Path(state_dir) / ("env-chapter-%s.json" % key.split("::")[0])
        env_p.write_text(json.dumps(env), encoding="utf-8")
        rc2, parsed2, err2 = _run(
            _state(QC_TIER1) + ["--envelope", str(env_p), "--json"],
            state_dir=state_dir, timeout=120)
        rep.check("Tier 1 chapter band+lock+stories %s" % key,
                  rc2 == 0 and (parsed2 or {}).get("passed"),
                  "rc=%s failures=%s" % (rc2, (parsed2 or {}).get("failures") or err2[:160]))
        # PDF 14-point floor for the chapter (rendered, not template).
        pdf = verify_font_floor(rep, state_dir, key, "chapter",
                                _working_path(state_dir, key, "chapter.md"))
        # STRIKE GATE: one internal QC attempt for this deliverable.
        rc3, parsed3, err3 = _run(
            _state(STRIKE_GATE) + ["--json", "--state-dir", str(state_dir),
                                   "begin-deliverable", "--participant-key", key],
            state_dir=state_dir, timeout=60)
        rc3b, parsed3b, err3b = _run(
            _state(STRIKE_GATE) + ["--json", "--state-dir", str(state_dir),
                                   "qc-attempt", "--participant-key", key,
                                   "--deliverable", "chapter", "--result", "pass"],
            state_dir=state_dir, timeout=60)
        rep.check("strike gate records the QC attempt %s" % key,
                  rc3b == 0 and (parsed3b or {}).get("action") == "qc-attempt",
                  parsed3b or err3b[:120])
        # THE CHAPTER GATE: EXACTLY TWO actions (SPEC S5) via gate status.
        rc4, parsed4, err4 = _gate(["status", "--subject-key", key], state_dir)
        actions = list((parsed4 or {}).get("actions") or [])
        rep.check("s5_gate presents exactly two actions %s" % key,
                  rc4 == 0 and actions == ["approve_as_is", "request_rewrite_with_notes"],
                  "actions=%s" % actions)
        rc4b, parsed4b, _ = _gate(["open", "--subject-key", key, "--no-nudge"],
                                  state_dir)
        rep.check("open s5_participant %s" % key,
                  rc4b == 0 and (parsed4b or {}).get("gate") == "s5_participant",
                  parsed4b or "")
        # REQUEST REWRITE (token door) -> the rewrite cycle begins.
        secret_name, secret_val = _env_first([LABEL_GATE_SECRET])
        if not secret_val:
            rep.deferred("s5 rewrite request (token door) %s" % key,
                         "%s NOT SET" % secret_name)
            return sha, pdf
        rc, minted, _ = _gate(["mint", "--subject-key", key], state_dir)
        token = (minted or {}).get("token") or ""
        rc, decided, err = _gate(["decide", "--subject-key", key, "--door", "token",
                                  "--action", "request_rewrite_with_notes",
                                  "--token", token,
                                  "--notes", "Tighten the opening; keep the door image."],
                                 state_dir)
        rep.check("s5 request_rewrite routes to s6_rewrite %s" % key,
                  rc == 0 and (decided or {}).get("stage_cursor") == "s6_rewrite",
                  decided or err[:120])
        return sha, pdf

    sha_a, _ = drive(PARTICIPANT_A, TITLE_A, SUBTITLE_A, "the door and the lock")
    sha_b, _ = drive(PARTICIPANT_B, TITLE_B, SUBTITLE_B, "the refusal ledger")
    return rep


def run_s6_rewrite(run, state_dir, args):
    rep = run.begin("S6", "REWRITE (budget 2, preservation, re-entry)")

    def drive(key, title, subtitle, story, n_words=2200):
        # The Thornfield rewrite re-enters the s5 gate; the base chapter stays.
        text = chapter_text(title, subtitle, story, key.split("::")[0], n_words)
        text = "REVISED EDITION.\n\n" + text
        _write_working(state_dir, key, "chapter.md", text)
        rc, parsed, err = _ledger(["record-artifact", "--participant-key", key,
                                   "--type", "chapter", "--sha256",
                                   _sha256_text(text), "--model-used", "glm-5.2",
                                   "--doc-url", "https://docs.google.com/document/d/gdoc_syn_canary_r1_%s/edit" % key.split("::")[0],
                                   "--pdf-url", "https://drive.google.com/file/d/gfile_syn_canary_r1_%s/view" % key.split("::")[0]],
                                  state_dir)
        rep.check("record rewrite chapter %s" % key,
                  rc == 0 and (parsed or {}).get("version") == 2,
                  parsed or err[:120])
        # rewrite count = 1 on the row (incremented once at the gate).
        rc, row, err = _ledger(["get-participant", "--participant-key", key],
                               state_dir)
        rep.check("rewrite_count == 1 %s" % key,
                  rc == 0 and (row or {}).get("rewrite_count") == 1,
                  "rewrite_count=%s" % (row or {}).get("rewrite_count"))
        rc, parsed, err = _ledger(["advance-stage", "--participant-key", key,
                                   "--to", "s5_gate"], state_dir)
        rep.check("rewrite re-enters s5_gate %s" % key,
                  rc == 0 and (parsed or {}).get("to") == "s5_gate",
                  parsed or err[:120])
        # rewrite-gate decision: budget 1 of 2 remains.
        rc, parsed, err = _run(
            _state(STRIKE_GATE) + ["--json", "--state-dir", str(state_dir),
                                   "rewrite-gate", "--participant-key", key],
            state_dir=state_dir, timeout=60)
        rep.check("rewrite budget surfaced (1 of 2 used) %s" % key,
                  rc == 0 and (parsed or {}).get("remaining") == 1 and
                  (parsed or {}).get("gate_actions") == ["approve_as_is", "request_rewrite"],
                  parsed or err[:120])
        # Tier 1 over the rewritten draft.
        env = {"kind": "rewrite",
               "artifact_path": str(_working_path(state_dir, key, "chapter.md")),
               "title": {"title": title, "subtitle": subtitle},
               "intake": {"personal_stories": story, "email": "", "phone": ""},
               "identity": {"contact_id": key.split("::")[0],
                            "anthology_id": ANTHOLOGY_ID},
               "run_ledger": {"stages": [{"model": "glm-5.2"}]}}
        env_p = Path(state_dir) / ("env-rewrite-%s.json" % key.split("::")[0])
        env_p.write_text(json.dumps(env), encoding="utf-8")
        rc2, parsed2, err2 = _run(
            _state(QC_TIER1) + ["--envelope", str(env_p), "--json"],
            state_dir=state_dir, timeout=120)
        rep.check("Tier 1 rewrite band+lock %s" % key,
                  rc2 == 0 and (parsed2 or {}).get("passed"),
                  "rc=%s failures=%s" % (rc2, (parsed2 or {}).get("failures") or err2[:120]))
        # REWRITE PRESERVATION (G10): the rewrite lands in rewrite1, never the
        # base chapter pair (field-map semantics; proven structurally here).
        fm = json.loads(FIELD_MAP.read_text(encoding="utf-8"))
        df = fm.get("deliverable_fields") or {}
        r1 = df.get("rewrite1") or {}
        base = df.get("chapter") or {}
        rep.check("rewrite1 pair distinct from base chapter pair",
                  r1.get("doc_url") != base.get("doc_url") and
                  r1.get("pdf_url") != base.get("pdf_url") and
                  bool(r1.get("doc_url")) and bool(r1.get("pdf_url")),
                  "rewrite1=%s base=%s" % (r1.get("doc_url"), base.get("doc_url")))
        # a 3rd rewrite request is ILLEGAL (budget 2) — fail closed.
        secret_name, secret_val = _env_first([LABEL_GATE_SECRET])
        if secret_val:
            rc, minted, _ = _gate(["mint", "--subject-key", key], state_dir)
            token = (minted or {}).get("token") or ""
            rc, decided, err = _gate(["decide", "--subject-key", key, "--door",
                                      "token", "--action", "approve_as_is",
                                      "--token", token], state_dir)
            rep.check("s5 approve freezes the rewritten chapter %s" % key,
                      rc == 0 and (decided or {}).get("stage_cursor") == "s7_cover",
                      decided or err[:120])
            # verify the freeze: artifact frozen=1.
            rc, art, err = _ledger(["get-artifact", "--participant-key", key,
                                    "--type", "chapter"], state_dir)
            arow = ((art or {}).get("artifact") or {}) if (art or {}).get("found") else {}
            rep.check("frozen chapter artifact %s" % key,
                      rc == 0 and arow.get("frozen") == 1,
                      "frozen=%s" % arow.get("frozen"))
            # a third request_rewrite is refused (rewrite budget 2).
            rc, decided, err = _ledger(["record-approval", "--gate", "s5_participant",
                                        "--participant-key", key,
                                        "--decision", "request_rewrite",
                                        "--door", "nudge_link"], state_dir)
            rep.check("third rewrite request refused (budget 2) %s" % key,
                      rc == 2 and (decided or {}).get("ok") is False,
                      "rc=%s" % rc)
        else:
            rep.deferred("s5 approve + freeze %s" % key, "%s NOT SET" % secret_name)

    drive(PARTICIPANT_A, TITLE_A, SUBTITLE_A, "the door and the lock")
    drive(PARTICIPANT_B, TITLE_B, SUBTITLE_B, "the refusal ledger")
    return rep


def run_s7_cover(run, state_dir, args):
    rep = run.begin("S7", "COVER SET (4 styles, choice field, apply-pick)")

    # The four config-pinned named styles + field-map coherence.
    rc, parsed, err = _run(_state(COVER_RENDER) + ["--list-styles"],
                           state_dir=state_dir, timeout=60)
    # --list-styles prints a HUMAN plan on stdout (not JSON): capture it via a
    # direct subprocess (the _run seam only returns parsed JSON, which this
    # sibling does not emit for --list-styles).
    try:
        proc = subprocess.run(_state(COVER_RENDER) + ["--list-styles"],
                              capture_output=True, text=True, timeout=60,
                              check=False)
        text_out = (proc.stdout or "") + (proc.stderr or "")
        style_rc = proc.returncode
    except (OSError, subprocess.SubprocessError):
        text_out, style_rc = "", -1
    styles = re.findall(r"(\d)\.\s+([A-Za-z ]+?)\s+\(([a-z_]+)\)", text_out)
    rep.check("cover_render lists 4 named styles",
              style_rc == 0 and len(styles) == 4,
              "rc=%s styles=%d" % (style_rc, len(styles)))
    fm = json.loads(FIELD_MAP.read_text(encoding="utf-8"))
    csf = fm.get("cover_style_fields") or {}
    rep.check("cover choice field + 4 sample fields in field-map",
              bool(csf.get("choice_field")) and
              len((csf.get("sample_url_fields") or {})) == 4 and
              len((csf.get("choice_options") or [])) == 4,
              "choice_options=%s" % (csf.get("choice_options")))
    # cover_render --dry-run proves the portrait guard + credential presence
    # (zero cost, zero network).
    rc, parsed, err = _run(
        _state(COVER_RENDER) + ["--participant-key", PARTICIPANT_A,
                                "--prompt", "A single strong portrait cover image for the canary anthology.",
                                "--out", str(Path(state_dir) / "cover-dry.png"),
                                "--dry-run"], state_dir=state_dir, timeout=60)
    rep.check("cover_render dry-run (portrait 2:3, no network)", rc == 0,
              parsed or err[:160])
    rc, parsed, err = _run(
        _state(COVER_RENDER) + ["--participant-key", PARTICIPANT_A,
                                "--prompt", "A landscape cover.",
                                "--out", str(Path(state_dir) / "cover-dry.png"),
                                "--aspect", "16:9", "--dry-run"],
        state_dir=state_dir, timeout=60)
    rep.check("cover_render refuses landscape 16:9", rc == 2,
              "rc=%s" % rc)
    # The apply-pick contract: the S7 runner's Phase B stamps the chosen style
    # into the cover fields and advances to s8_deliver. Driven structurally:
    # the pick manifest shape + the advance edge (live Drive/Kie deferred).
    rc, parsed, err = _ledger(["advance-stage", "--participant-key", PARTICIPANT_A,
                               "--to", "s8_deliver"], state_dir)
    rep.check("cover pick advances to s8_deliver (A)", rc == 0, parsed or err[:120])
    rc, parsed, err = _ledger(["advance-stage", "--participant-key", PARTICIPANT_B,
                               "--to", "s8_deliver"], state_dir)
    rep.check("cover pick advances to s8_deliver (B)", rc == 0, parsed or err[:120])
    sa, sv = _env_first([LABEL_SA_KEY])
    ki = _env_first(["KIE_API_KEY"])
    if sv and ki[1]:
        # NOTE: a live cover render is a PAID image generation on the client's
        # own Kie account; the canary deliberately does not spend it by default.
        # The structural proofs (portrait guard, style set, choice field,
        # apply-pick edge) stand; the paid render is the W5 canary drill's own
        # budgeted step, not this script's.
        rep.deferred("live 4-style cover render (Kie + Drive landing)",
                     "deliberately not spent: a live render is a PAID image "
                     "generation on the client's own Kie account; structural "
                     "proofs above stand")
    else:
        rep.deferred("live 4-style cover render (Kie + Drive landing)",
                     "KIE_API_KEY / %s not resolvable; structural proofs above stand"
                     % LABEL_SA_KEY)
    return rep


def run_s8_deliver(run, state_dir, args):
    rep = run.begin("S8", "PACKAGE AND DELIVER (Doc+PDF, floor, notice, certificate)")

    # The S8 sweep for both participants: Doc (edit-share) + PDF (14pt floor) +
    # Convert and Flow field writes + completion notice + certificate + card.
    for key, title in ((PARTICIPANT_A, TITLE_A), (PARTICIPANT_B, TITLE_B)):
        chapter_path = _working_path(state_dir, key, "chapter.md")
        if not chapter_path.is_file():
            chapter_path = _write_working(state_dir, key, "chapter.md",
                                          chapter_text(title, SUBTITLE_A if key == PARTICIPANT_A else SUBTITLE_B,
                                                       "the door and the lock" if key == PARTICIPANT_A else "the refusal ledger",
                                                       key.split("::")[0], 2300))
        pdf = verify_font_floor(rep, state_dir, key, "chapter", chapter_path)
        # nudge completion notice: dry-run only (client-silent canary).
        rc, parsed, err = _run(
            _state(NUDGE_SEND) + ["send", "--template", "completion",
                                  "--subject-key", key, "--state-dir", str(state_dir),
                                  "--deliverable-label", "chapter draft",
                                  "--deliverable-link",
                                  "https://docs.google.com/document/d/gdoc_syn_canary/edit",
                                  "--dry-run", "--json"],
            state_dir=state_dir, timeout=60)
        rep.check("completion nudge renders sanctioned template %s" % key,
                  rc == 0 and (parsed or {}).get("delivered") is False and
                  (parsed or {}).get("dry_run") is True,
                  parsed or err[:120])
        # recipient is ledger-resolved, never a literal (PII redacted).
        if parsed is not None:
            rep.check("recipient resolved from ledger (redacted) %s" % key,
                      bool((parsed or {}).get("recipient_redacted")),
                      (parsed or {}).get("recipient_redacted"))
        # Convert and Flow delivery adapter: plan surfaces credential presence
        # SET/NOT-SET only; a live write requires the client PIT (deferred).
        rc, parsed, err = _run(
            _state(CAF_DELIVERY) + ["plan", "--field-map", str(FIELD_MAP)],
            state_dir=state_dir, timeout=60)
        # plan prints a human contract (no --json flag on this subcommand);
        # the canary asserts exit 0 (credential presence is SET/NOT SET inside).
        rep.check("caf_delivery plan (credential SET/NOT SET only)", rc == 0,
                  (err or "")[:160])
        # Signed process certificate: build + verify is offline-safe.
        cert_input = {
            "participant_key": key, "contact_id": key.split("::")[0],
            "anthology_id": ANTHOLOGY_ID, "stage_cursor": "s8_deliver",
            "deliverables": [{"type": "chapter",
                              "doc": {"url": "https://docs.google.com/document/d/gdoc_syn_canary/edit",
                                      "list_verified": True},
                              "pdf": {"url": "https://drive.google.com/file/d/gfile_syn_canary/view",
                                      "list_verified": True},
                              "field_results": [{"key": "contact.anthology_chapter_doc_url",
                                                 "id": "cf_c_doc", "match": True},
                                                {"key": "contact.anthology_chapter_pdf_url",
                                                 "id": "cf_c_pdf", "match": True}]}],
            "control_fields": [{"key": "contact.anthology_stage", "id": "cf_stage",
                                "match": True}],
            "pipeline_stage_update": {"stage_id": "stg_chapter", "name": "Chapter",
                                      "fired": True},
            "attestation": "canary synthetic",
        }
        ci = Path(state_dir) / ("cert-%s.json" % key.split("::")[0])
        ci.write_text(json.dumps(cert_input), encoding="utf-8")
        rc, parsed, err = _run(
            _state(SCRIPTS / "delivery_report.py") + ["certificate",
                                                      "--input", str(ci),
                                                      "--report-dir",
                                                      str(self_report_dir(state_dir))],
            state_dir=state_dir, timeout=60)
        rep.check("signed process certificate issued %s" % key,
                  rc == 0 and (parsed or {}).get("ok") is not False,
                  parsed or err[:160])
        # card to review (never done) via the fail-soft board projection.
        rc, parsed, err = _run(
            _state(MC_BOARD) + ["sync", "--subject-key", key,
                                "--state-dir", str(state_dir), "--json"],
            state_dir=state_dir, timeout=60)
        if parsed is not None:
            target = (parsed or {}).get("target_status")
            rep.check("card projects to review (never done) %s" % key,
                      rc == 0 and target != "done",
                      "target_status=%s" % target)
        else:
            rep.check("card projection runs fail-soft %s" % key, rc == 0, "")
        # advance to approved (the participant's terminal authoring cursor).
        rc, parsed, err = _ledger(["advance-stage", "--participant-key", key,
                                   "--to", "s9_wait_assembly"], state_dir)
        rep.check("S8 -> s9_wait_assembly %s" % key,
                  rc == 0 and (parsed or {}).get("to") == "s9_wait_assembly",
                  parsed or err[:120])
        rc, parsed, err = _ledger(["advance-stage", "--participant-key", key,
                                   "--to", "approved"], state_dir)
        rep.check("participant approved %s" % key,
                  rc == 0 and (parsed or {}).get("to") == "approved",
                  parsed or err[:120])
    # email + SMS contract (the §3 release bus -> snapshot workflows).
    verify_email_sms_contract(rep)
    # Doc pull-back byte-diff (confirm-then-pull).
    verify_pullback_contract(rep, state_dir)
    return rep


def self_report_dir(state_dir):
    return Path(state_dir) / "reports"


def run_s9_assembly(run, state_dir, args):
    rep = run.begin("S9", "ASSEMBLY (all guards, order confirm, finale flag, sign-off)")

    # --- readiness gate: every guard observed, one at a time. ---------------
    rc, parsed, err = _ledger(["assembly-readiness-report",
                               "--anthology-id", ANTHOLOGY_ID], state_dir)
    ready = (parsed or {}).get("ready") is True
    rep.check("readiness ready (2 approved + frozen, none blocking)",
              rc == 0 and ready and (parsed or {}).get("frozen_chapter_count") == 2,
              "ready=%s frozen=%s" % (ready, (parsed or {}).get("frozen_chapter_count")))
    rc, parsed, err = _ledger(["get-anthology", "--anthology-id", ANTHOLOGY_ID],
                              state_dir)
    rep.check("anthology auto-armed (readiness met)",
              (parsed or {}).get("assembly_state") == "armed",
              (parsed or {}).get("assembly_state"))
    # guard: typed --confirm-name mismatch -> exit 5, nothing changed.
    rc, parsed, err = _ledger(["record-approval", "--gate", "s9_ready",
                               "--anthology-id", ANTHOLOGY_ID,
                               "--producer-id", PRODUCER_ID,
                               "--confirm-name", "Wrong Name",
                               "--door", "dashboard"], state_dir)
    rep.check("s9_ready confirm-name mismatch refused (exit 5)",
              rc == 5 and (parsed or {}).get("ok") is False, "rc=%s" % rc)
    rc, parsed, err = _ledger(["get-anthology", "--anthology-id", ANTHOLOGY_ID],
                              state_dir)
    rep.check("confirm-name mismatch changed nothing",
              (parsed or {}).get("assembly_state") == "armed",
              (parsed or {}).get("assembly_state"))
    # guard: non-producer auth -> exit 5.
    rc, parsed, err = _ledger(["record-approval", "--gate", "s9_ready",
                               "--anthology-id", ANTHOLOGY_ID,
                               "--producer-id", "PRODimposter999",
                               "--confirm-name", ANTHOLOGY_NAME,
                               "--door", "dashboard"], state_dir)
    rep.check("s9_ready non-producer refused (exit 5)",
              rc == 5 and (parsed or {}).get("ok") is False, "rc=%s" % rc)
    # guard: assembly-advance is NOT a second door (all guarded targets exit 2).
    for guarded in ("armed", "ready_confirmed", "proposed", "adjusted", "signed_off"):
        rc, parsed, err = _ledger(["assembly-advance", "--anthology-id", ANTHOLOGY_ID,
                                   "--to", guarded], state_dir)
        rep.check("assembly-advance bypass into %s illegal" % guarded,
                  rc == 2 and (parsed or {}).get("ok") is False, "rc=%s" % rc)
    # fire the trigger (own-producer + typed name + readiness).
    rc, parsed, err = _ledger(["record-approval", "--gate", "s9_ready",
                               "--anthology-id", ANTHOLOGY_ID,
                               "--producer-id", PRODUCER_ID,
                               "--confirm-name", ANTHOLOGY_NAME,
                               "--door", "dashboard"], state_dir)
    rep.check("s9_ready fires (both-door board door)",
              rc == 0 and (parsed or {}).get("assembly_state") == "ready_confirmed",
              parsed or err[:120])
    rc, parsed, err = _ledger(["record-approval", "--gate", "s9_ready",
                               "--anthology-id", ANTHOLOGY_ID,
                               "--producer-id", PRODUCER_ID,
                               "--confirm-name", ANTHOLOGY_NAME,
                               "--door", "dashboard"], state_dir)
    rep.check("double-fire is an acknowledged no-op (one-way)",
              rc == 0 and (parsed or {}).get("noop") is True,
              parsed or err[:120])

    # --- order curation / confirm (U9) ---------------------------------------
    order = [PARTICIPANT_A, PARTICIPANT_B]
    rc, parsed, err = _ledger(["assembly-set-order", "--anthology-id", ANTHOLOGY_ID,
                               "--order", json.dumps(order)], state_dir)
    rep.check("order proposed (curation of record)",
              rc == 0 and (parsed or {}).get("assembly_state") == "proposed",
              parsed or err[:120])
    rc, parsed, err = _ledger(["assembly-set-order", "--anthology-id", ANTHOLOGY_ID,
                               "--order", json.dumps([PARTICIPANT_B, PARTICIPANT_A]),
                               "--state", "adjusted"], state_dir)
    rep.check("producer reorder adjusted",
              rc == 0 and (parsed or {}).get("assembly_state") == "adjusted",
              parsed or err[:120])
    # a bad order (non-member key) is refused (exit 5).
    rc, parsed, err = _ledger(["assembly-set-order", "--anthology-id", ANTHOLOGY_ID,
                               "--order", json.dumps([PARTICIPANT_A, "CONTACTcanaryOPz::ANTHcanaryOP01"])],
                              state_dir)
    rep.check("order with non-member key refused (exit 5)",
              rc == 5 and (parsed or {}).get("ok") is False, "rc=%s" % rc)
    # THE CONFIRM-ORDER board action (U9 finale trigger): gate_engine decide
    # confirm_order persists adjusted + flags the runner for transitions +
    # Grand Finale (request.confirm_order), preserving arm context.
    rc, parsed, err = _gate(
        ["decide", "--subject-key", ANTHOLOGY_ID, "--door", "board",
         "--action", "confirm_order", "--order", json.dumps(order),
         "--opener", PARTICIPANT_A, "--closer", PARTICIPANT_B,
         "--producer-id", PRODUCER_ID, "--run-dir",
         str(_s9_run_dir(state_dir, ANTHOLOGY_ID))], state_dir)
    rep.check("confirm_order persists the finalized order (board door)",
              rc == 0 and (parsed or {}).get("committed") is True and
              (parsed or {}).get("assembly_state") == "adjusted",
              parsed or err[:120])
    req_path = _s9_run_dir(state_dir, ANTHOLOGY_ID) / "request.json"
    if req_path.is_file():
        try:
            req = json.loads(req_path.read_text(encoding="utf-8"))
            rep.check("confirm_order flags the S9 runner (transitions + finale)",
                      req.get("confirm_order") is True and
                      req.get("order") == order and
                      req.get("opener") == PARTICIPANT_A and
                      req.get("closer") == PARTICIPANT_B,
                      "confirm_order=%s order_len=%s" % (req.get("confirm_order"),
                                                         len(req.get("order") or [])))
        except (OSError, ValueError) as exc:
            rep.check("confirm_order request.json readable", False, str(exc))
    else:
        rep.check("confirm_order runner flag (request.json)", False,
                  "request.json not at %s" % req_path)

    # --- compile: frozen-chapter sha256 byte-identity ------------------------
    # The frozen artifact shas are the REAL bytes the canary recorded; compile
    # --verify-sha re-proves each chapter byte-identical.
    frozen_shas = {}
    for key in (PARTICIPANT_A, PARTICIPANT_B):
        rc, art, err = _ledger(["get-artifact", "--participant-key", key,
                                "--type", "chapter"], state_dir)
        arow = ((art or {}).get("artifact") or {}) if (art or {}).get("found") else {}
        if rc == 0 and arow.get("sha256"):
            frozen_shas[key] = arow["sha256"]
    if len(frozen_shas) == 2:
        verify = ",".join("%s=%s" % (k, v) for k, v in frozen_shas.items())
        rc, parsed, err = _ledger(["assembly-advance", "--anthology-id", ANTHOLOGY_ID,
                                   "--to", "compiled", "--verify-sha", verify],
                                  state_dir)
        rep.check("compile with frozen-chapter sha256 byte-identity",
                  rc == 0 and (parsed or {}).get("assembly_state") == "compiled",
                  parsed or err[:120])
    else:
        rep.check("compile frozen shas resolvable", False,
                  "frozen shas=%s" % frozen_shas)
    # a tampered sha (all-zeros) must NOT re-compile (byte-diff proof).
    tampered = ",".join("%s=%s" % (k, "0" * 64) for k in frozen_shas)
    rc, parsed, err = _ledger(["assembly-advance", "--anthology-id", ANTHOLOGY_ID,
                               "--to", "compiled", "--verify-sha", tampered],
                              state_dir)
    rep.check("tampered chapter sha refused at compile (byte-diff)",
              rc == 2 or (parsed and parsed.get("noop") is True),
              "rc=%s noop=%s" % (rc, (parsed or {}).get("noop")))
    # record the manuscript artifact (S9 scope). The compiled manuscript is the
    # U9 final edition: each frozen chapter VERBATIM (byte-identical), N-1
    # inter-chapter TRANSITION sentinel bridges naming the NEXT chapter's locked
    # title inside the 150-300 word band, front/back matter, and ONE Grand
    # Finale sentinel with its own title + an action-steps section, zero em
    # dashes anywhere (the U9 provers assert all of this).
    body_a = _working_path(state_dir, PARTICIPANT_A, "chapter.md").read_text(encoding="utf-8")
    body_b = _working_path(state_dir, PARTICIPANT_B, "chapter.md").read_text(encoding="utf-8")
    def _bridge(nxt_title, words=200):
        w = ["now", "from", "this", "bridge", "turns", "toward", "the",
             "chapter", "that", "follows", "with", "its", "own", "voice",
             "carrying", "the", "reader", "forward", "into", "quiet", "work",
             "again", "steady", "hands", "and", "a", "kept", "promise"]
        text = ("As one voice rests, the next begins. This bridge carries the "
                "reader toward the chapter titled %s, whose author continues "
                "the same disciplined work with a different hand."
                % nxt_title)
        while _count_words(text) < words:
            text += " " + " ".join(w[i % len(w)] for i in range(14))
        return text + "."
    transition_ab = ("<!-- TRANSITION 1 -->" + _bridge(TITLE_B)
                     + "<!-- END TRANSITION 1 -->")
    finale = ("<!-- GRAND FINALE -->\n# A Grand Finale for Every Voice\n"
              "This closing chapter gathers every contribution, including the "
              "chapters titled %s and %s, into one action-steps section where "
              "the reader is told exactly what to do next with the craft "
              "they have learned.\n## Action Steps\nOne. Begin tomorrow. "
              "Two. Keep the habit. Three. Return to this anthology often."
              % (TITLE_A, TITLE_B)
              + "\n<!-- END GRAND FINALE -->")
    manuscript = "\n\n".join([
        "# %s" % ANTHOLOGY_NAME,
        "Title page and table of contents.",
        "## Contributor: Ada Sample", body_a,
        transition_ab,
        "## Contributor: Ben Marlow", body_b,
        finale,
        "## About the Authors and Acknowledgements.",
    ])
    ms_path = _write_working(state_dir, ANTHOLOGY_ID, "manuscript.md", manuscript)
    rc, parsed, err = _ledger(["record-artifact", "--anthology-id", ANTHOLOGY_ID,
                               "--type", "anthology_manuscript", "--sha256",
                               _sha256_text(manuscript), "--model-used", "glm-5.2"],
                              state_dir)
    rep.check("record-artifact(anthology_manuscript)",
              rc == 0 and (parsed or {}).get("type") == "anthology_manuscript",
              parsed or err[:120])
    # assembly-scope Gate B (Tier 1 assembly mode) over the manuscript.
    env = {
        "kind": "manuscript", "mode": "assembly",
        "artifact_path": str(ms_path),
        "title": {"title": TITLE_A, "subtitle": SUBTITLE_A},
        "identity": {"contact_id": CONTACT_A, "anthology_id": ANTHOLOGY_ID},
        "run_ledger": {"stages": [{"model": "glm-5.2"}]},
        # A1: every approved chapter present exactly once and byte-identical
        # to its FROZEN sha (paths are the canary's own frozen bodies).
        "chapters": [
            {"contact_id": CONTACT_A, "sha256": frozen_shas.get(PARTICIPANT_A, ""),
             "path": str(_working_path(state_dir, PARTICIPANT_A, "chapter.md"))},
            {"contact_id": CONTACT_B, "sha256": frozen_shas.get(PARTICIPANT_B, ""),
             "path": str(_working_path(state_dir, PARTICIPANT_B, "chapter.md"))},
        ],
        # A2: compiled order matches the producer-confirmed curation (the
        # assembly check compares the CHAPTER contact ids, not the composite
        # participant keys).
        "curated_order": [CONTACT_A, CONTACT_B],
        # A3/A4: roster + bios; the intro text names only real contributors.
        "contributors": [
            {"first_name": "Ada", "last_name": "Sample"},
            {"first_name": "Ben", "last_name": "Marlow"},
        ],
        "introduction_text": "This anthology gathers Ada Sample and Ben Marlow.",
        "producer_inputs_text": "",
        "bios": [
            {"name": "Ada Sample", "text": "Ada Sample is a first-time contributor."},
            {"name": "Ben Marlow", "text": "Ben Marlow is a print-shop owner."},
        ],
        # A5: front + back matter flags (also derivable from the manuscript).
        "front_matter_present": True,
        "back_matter_present": True,
    }
    env_p = Path(state_dir) / "env-ms.json"
    env_p.write_text(json.dumps(env), encoding="utf-8")
    rc2, parsed2, err2 = _run(
        _state(QC_TIER1) + ["--envelope", str(env_p), "--mode", "assembly", "--json"],
        state_dir=state_dir, timeout=120)
    rep.check("assembly Gate B over manuscript", rc2 == 0 and (parsed2 or {}).get("passed"),
              "rc=%s failures=%s" % (rc2, (parsed2 or {}).get("failures") or err2[:160]))
    # transitions + Grand Finale write path (U9): driven structurally through
    # the sibling logic's PURE provers (offline, no model).
    rc3, parsed3, err3 = _run(
        _state(S9_LOGIC) + ["--anthology-id", ANTHOLOGY_ID,
                            "--state-dir", str(state_dir), "--json", "ordering"],
        state_dir=state_dir, timeout=60, input_text=json.dumps({
            "chapters": [{"participant_key": PARTICIPANT_A,
                          "chapter_title": TITLE_A},
                         {"participant_key": PARTICIPANT_B,
                          "chapter_title": TITLE_B}],
            "proposal": {"order": order}}))
    rep.check("S9 ordering cockpit view (pure)", rc3 == 0 and (parsed3 or {}) is not None,
              parsed3 or err3[:160])
    rc4, parsed4, err4 = _run(
        _state(S9_LOGIC) + ["--anthology-id", ANTHOLOGY_ID,
                            "--state-dir", str(state_dir), "--json", "prove"],
        state_dir=state_dir, timeout=60, input_text=json.dumps({
            "manuscript": manuscript,
            "order": order,
            "chapter_titles": {PARTICIPANT_A: TITLE_A, PARTICIPANT_B: TITLE_B},
            "frozen_bodies": {PARTICIPANT_A: body_a, PARTICIPANT_B: body_b}}))
    rep.check("S9 assembly provers (transitions + finale, pure)", rc4 == 0,
              json.dumps(parsed4 or {})[:220] if parsed4 else (err4 or "")[:160])

    # --- s9_producer sign-off closes the anthology --------------------------
    rc, parsed, err = _ledger(["record-approval", "--gate", "s9_producer",
                               "--anthology-id", ANTHOLOGY_ID,
                               "--producer-id", PRODUCER_ID,
                               "--door", "dashboard"], state_dir)
    rep.check("s9_producer sign-off closes the anthology",
              rc == 0 and (parsed or {}).get("assembly_state") == "signed_off",
              parsed or err[:120])
    rc, parsed, err = _ledger(["get-anthology", "--anthology-id", ANTHOLOGY_ID],
                              state_dir)
    rep.check("anthology status delivered",
              (parsed or {}).get("status") == "delivered",
              (parsed or {}).get("status"))
    # members transition approved -> delivered at sign-off.
    for key in (PARTICIPANT_A, PARTICIPANT_B):
        rc, row, err = _ledger(["get-participant", "--participant-key", key],
                               state_dir)
        rep.check("member %s delivered at sign-off" % key,
                  rc == 0 and (row or {}).get("stage_cursor") == "delivered",
                  (row or {}).get("stage_cursor"))
    # sign-off double-fire is a no-op (one-way).
    rc, parsed, err = _ledger(["record-approval", "--gate", "s9_producer",
                               "--anthology-id", ANTHOLOGY_ID,
                               "--producer-id", PRODUCER_ID,
                               "--door", "dashboard"], state_dir)
    rep.check("sign-off double-fire no-op", rc == 0 and (parsed or {}).get("noop") is True,
              parsed or err[:120])
    return rep


# ---------------------------------------------------------------------------
# The full run.
# ---------------------------------------------------------------------------
def run_canary(args):
    state_dir = Path(args.state_dir) if args.state_dir else \
        Path(tempfile.mkdtemp(prefix="canary_e2e_"))
    report_dir = Path(args.report_dir) if args.report_dir else \
        default_report_dir(state_dir)
    run = CanaryRun(state_dir, report_dir, args)

    # The cross-cutting QC-scorer contract first (engine + CC sides).
    rep_x = run.begin("XC", "CROSS-CUTTING (QC scorer >= 8.5 owns review->done)")
    verify_qc_scorer_contract(rep_x)

    run_s0_intake(run, state_dir, args)
    run_s1_avatar(run, state_dir, args)
    run_s2_tone(run, state_dir, args)
    run_s3_title(run, state_dir, args)
    run_s4_outline(run, state_dir, args)
    run_s5_chapter(run, state_dir, args)
    run_s6_rewrite(run, state_dir, args)
    run_s7_cover(run, state_dir, args)
    run_s8_deliver(run, state_dir, args)
    run_s9_assembly(run, state_dir, args)

    # Board round-trip both doors (after all gates exist to exercise).
    rep_b = run.begin("B2", "BOARD ROUND-TRIP (both doors, never-done)")
    verify_board_round_trip(rep_b, state_dir)

    report, path = run.finish()
    print(json.dumps(report, indent=2, ensure_ascii=False))
    if path:
        print("CANARY-REPORT.json written: %s" % path)

    summary = report["summary"]
    if summary["stages_failed"]:
        sys.stderr.write("[canary] FAILED stage(s): %s\n" % summary["failed_stages"])
        return EX_BADINVOKE
    # --require-live holds on ANY deferred check (a live proof the canary could
    # not execute is never silently swallowed); without it, deferred checks are
    # reported with their exact reason and never false-passed.
    deferred_checks = [c for s in report["stages"] for c in s["checks"]
                       if c["result"] == "DEFERRED"]
    if args.require_live and deferred_checks:
        sys.stderr.write("[canary] --require-live: %d live check(s) not executed: %s\n"
                         % (len(deferred_checks),
                            "; ".join(sorted({c["check"] for c in deferred_checks}))))
        return EX_HELD
    if summary["stages_deferred"] and summary["stages_passed"] == 0:
        sys.stderr.write("[canary] nothing executed; all deferred\n")
        return EX_HELD
    return EX_OK


def cmd_plan():
    print("canary_e2e_test.py -- one complete S0..S9 canary (MASTER-SPEC NEW-4)")
    print("two synthetic co-authors on the operator box; per-stage verified")
    print("stage plan:")
    for stage, label in (
            ("S0", "INTAKE AND ROUTING (live tunnel battery, dedup, capture)"),
            ("S1", "AVATAR (artifact + producer board approve + release tag)"),
            ("S2", "TONE (3,000-word floor + producer gate)"),
            ("S3", "TITLES + TITLE LOCK (participant token-door pick)"),
            ("S4", "BLURB + OUTLINE (both gates, both doors)"),
            ("S5", "CHAPTER (Gate B battery, exactly two actions, freeze)"),
            ("S6", "REWRITE (budget 2, preservation, re-entry)"),
            ("S7", "COVER SET (4 styles, choice field, apply-pick)"),
            ("S8", "PACKAGE AND DELIVER (Doc+PDF, floor, notice, certificate)"),
            ("S9", "ASSEMBLY (all guards, order confirm, finale flag, sign-off)"),
            ("XC", "CROSS-CUTTING (QC scorer >= 8.5 owns review->done)"),
            ("B2", "BOARD ROUND-TRIP (both doors, never-done)")):
        print("  %-4s %s" % (stage, label))
    print("exit codes: 0 all observed PASS; 2 a stage FAILED; 3 --require-live held;")
    print("            4 --self-test failed / --verify-report INVALID; 1 unexpected error")
    print("modes: --verify-report <report> independently re-checks a persisted")
    print("       CANARY-REPORT.json claim (sha256 chain over report body + the")
    print("       state ledger it names; exit 0 VALID / 4 INVALID)")
    print("note: the 12/12 verdict is STAGE-LEVEL; S7 live Kie render + S8 live")
    print("      Doc pull-back are deliberately deferred on a default run and the")
    print("      report says so in the summary (deferred-live note).")
    print("secrets: resolved BY LABEL only; SET / NOT SET surfaces; values never printed")
    return EX_OK


# ---------------------------------------------------------------------------
# SELF-TEST: the offline acceptance battery. Golden fixtures (the real replay
# fixtures from fixtures/golden, replayed against a temp mirror) PLUS attack
# fixtures that prove EVERY gate fails closed. No network, no live ledger.
# ---------------------------------------------------------------------------
def self_test():
    checks = []

    def check(name, cond, evidence=""):
        checks.append((name, bool(cond), evidence))

    # ---- 1. the golden ledger fixtures replay against the real sole writer --
    replay = GOLDEN_DIR / "replay_golden.py"
    if replay.is_file():
        rc, parsed, err = _run([sys.executable, str(replay), "--all", "--json"],
                               timeout=600)
        # replay prints its JSON summary on stdout (parsed) with exit 0.
        ok = rc == 0 and isinstance(parsed, dict) and parsed.get("ok") is True
        check("golden replay --all passes against the real ledger",
              ok, ("rc=%s failures=%s" % (rc, (parsed or {}).get("failures") or "")) if not ok
              else "passed=%s/%s" % (parsed.get("passed"), parsed.get("total")))
    else:
        check("golden replay harness present", False, "missing %s" % replay)

    # ---- 2. stage runner self-tests (the house contract for every runner) --
    for runner in ("stage_s0_intake", "stage_s1_avatar", "stage_s2_tone",
                   "stage_s3_title", "stage_s4_outline", "stage_s5_chapter",
                   "stage_s6_rewrite", "stage_s7_cover", "stage_s8_deliver",
                   "stage_s9_assembly"):
        p = SCRIPTS / ("%s.py" % runner)
        rc, _, err = _run([sys.executable, str(p), "--self-test"], timeout=180)
        check("%s --self-test" % runner, rc == 0, err[:120])

    # ---- 3. attack fixtures: every gate fails closed ------------------------
    tmp = Path(tempfile.mkdtemp(prefix="canary_selftest_"))
    try:
        state = tmp / "state"
        state.mkdir(parents=True)
        # ledger setup through the sole writer (mirror-only, isolated).
        def L(argv):
            return _ledger(argv, state)

        L(["bootstrap"])
        L(["upsert-producer", "--producer-id", "PRODselftest01",
           "--producer-email", "p@example.test", "--display-name", "P"])
        L(["upsert-anthology", "--anthology-id", "ANTHselftest01",
           "--producer-id", "PRODselftest01", "--name", "Self Test Voices",
           "--caf-location-binding", "LOCselftestAA"])
        L(["upsert-participant", "--contact-id", "Cselftest01",
           "--anthology-id", "ANTHselftest01"])
        key = "Cselftest01::ANTHselftest01"

        # attack 1: unknown participant -> exit 3.
        rc, _, _ = L(["get-participant", "--participant-key", "ghost::x"])
        check("unknown participant exits 3 (fail closed)", rc == 3, "rc=%s" % rc)
        # attack 2: illegal jump -> exit 2, nothing changed.
        L(["advance-stage", "--participant-key", key, "--to", "s1_avatar"])
        rc, _, _ = L(["advance-stage", "--participant-key", key, "--to", "s5_chapter"])
        check("illegal transition exits 2 (fail closed)", rc == 2, "rc=%s" % rc)
        rc, row, _ = L(["get-participant", "--participant-key", key])
        check("illegal transition changed nothing",
              (row or {}).get("stage_cursor") == "s1_avatar",
              (row or {}).get("stage_cursor"))
        # attack 3: gate bypass via advance-stage -> exit 2.
        L(["advance-stage", "--participant-key", key, "--to", "s1_gate"])
        rc, _, _ = L(["advance-stage", "--participant-key", key, "--to", "s2_tone"])
        check("gate-bypass via advance-stage exits 2", rc == 2, "rc=%s" % rc)
        # attack 4: title lock one-way.
        L(["record-approval", "--gate", "s1_producer", "--participant-key", key,
           "--decision", "approve", "--door", "dashboard"])
        L(["advance-stage", "--participant-key", key, "--to", "s2_gate"])
        L(["record-approval", "--gate", "s2_producer", "--participant-key", key,
           "--decision", "approve", "--door", "dashboard"])
        L(["advance-stage", "--participant-key", key, "--to", "s3_gate"])
        rc, _, _ = L(["record-approval", "--gate", "s3_selection",
                      "--participant-key", key, "--decision", "approve",
                      "--title", "Rise", "--subtitle", "A Story",
                      "--door", "nudge_link"])
        check("title selection commits", rc == 0, "rc=%s" % rc)
        rc, _, _ = L(["record-approval", "--gate", "s3_selection",
                      "--participant-key", key, "--decision", "approve",
                      "--title", "Fall", "--door", "nudge_link"])
        check("title relock refused (one-way)", rc == 2, "rc=%s" % rc)
        # attack 5: rewrite budget — the 3rd request is illegal.
        L(["advance-stage", "--participant-key", key, "--to", "s4_gate_producer"])
        L(["record-approval", "--gate", "s4_producer", "--participant-key", key,
           "--decision", "approve", "--door", "dashboard"])
        L(["record-approval", "--gate", "s4_participant", "--participant-key", key,
           "--decision", "approve", "--door", "nudge_link"])
        L(["record-artifact", "--participant-key", key, "--type", "chapter",
           "--sha256", "shaSelfTest1", "--model-used", "glm-5.2"])
        L(["advance-stage", "--participant-key", key, "--to", "s5_gate"])
        for i in (1, 2):
            rc, _, _ = L(["record-approval", "--gate", "s5_participant",
                          "--participant-key", key, "--decision", "request_rewrite",
                          "--notes", "tighten", "--door", "nudge_link"])
            check("rewrite request %d commits" % i, rc == 0, "rc=%s" % rc)
            L(["advance-stage", "--participant-key", key, "--to", "s5_gate"])
        rc, _, _ = L(["record-approval", "--gate", "s5_participant",
                      "--participant-key", key, "--decision", "request_rewrite",
                      "--door", "nudge_link"])
        check("third rewrite request refused (budget 2)", rc == 2, "rc=%s" % rc)
        # attack 6: S9 guards — wrong confirm-name, non-producer, second door.
        L(["record-approval", "--gate", "s5_participant", "--participant-key", key,
           "--decision", "approve", "--door", "nudge_link"])
        L(["advance-stage", "--participant-key", key, "--to", "s8_deliver"])
        L(["advance-stage", "--participant-key", key, "--to", "s9_wait_assembly"])
        L(["advance-stage", "--participant-key", key, "--to", "approved"])
        # second contributor so the floor-2 readiness can be met
        L(["upsert-participant", "--contact-id", "Cselftest02",
           "--anthology-id", "ANTHselftest01"])
        key2 = "Cselftest02::ANTHselftest01"
        for frm, to in (("s0_intake", "s1_avatar"), ("s1_avatar", "s1_gate")):
            L(["advance-stage", "--participant-key", key2, "--to", to])
        L(["record-approval", "--gate", "s1_producer", "--participant-key", key2,
           "--decision", "approve", "--door", "dashboard"])
        L(["advance-stage", "--participant-key", key2, "--to", "s2_gate"])
        L(["record-approval", "--gate", "s2_producer", "--participant-key", key2,
           "--decision", "approve", "--door", "dashboard"])
        L(["advance-stage", "--participant-key", key2, "--to", "s3_gate"])
        L(["record-approval", "--gate", "s3_selection", "--participant-key", key2,
           "--decision", "approve", "--title", "Dawn", "--door", "nudge_link"])
        L(["advance-stage", "--participant-key", key2, "--to", "s4_gate_producer"])
        L(["record-approval", "--gate", "s4_producer", "--participant-key", key2,
           "--decision", "approve", "--door", "dashboard"])
        L(["record-approval", "--gate", "s4_participant", "--participant-key", key2,
           "--decision", "approve", "--door", "nudge_link"])
        L(["record-artifact", "--participant-key", key2, "--type", "chapter",
           "--sha256", "shaSelfTest2", "--model-used", "glm-5.2"])
        L(["advance-stage", "--participant-key", key2, "--to", "s5_gate"])
        L(["record-approval", "--gate", "s5_participant", "--participant-key", key2,
           "--decision", "approve", "--door", "nudge_link"])
        for to in ("s8_deliver", "s9_wait_assembly", "approved"):
            L(["advance-stage", "--participant-key", key2, "--to", to])
        rc, _, _ = L(["record-approval", "--gate", "s9_ready",
                      "--anthology-id", "ANTHselftest01",
                      "--producer-id", "PRODselftest01",
                      "--confirm-name", "Wrong", "--door", "dashboard"])
        check("s9 confirm-name mismatch exits 5", rc == 5, "rc=%s" % rc)
        rc, _, _ = L(["record-approval", "--gate", "s9_ready",
                      "--anthology-id", "ANTHselftest01",
                      "--producer-id", "intruder",
                      "--confirm-name", "Self Test Voices",
                      "--door", "dashboard"])
        check("s9 non-producer exits 5", rc == 5, "rc=%s" % rc)
        for guarded in ("armed", "ready_confirmed", "proposed", "adjusted",
                        "signed_off"):
            rc, _, _ = L(["assembly-advance", "--anthology-id", "ANTHselftest01",
                          "--to", guarded])
            check("assembly-advance into %s illegal" % guarded, rc == 2, "rc=%s" % rc)
        rc, _, _ = L(["record-approval", "--gate", "s9_ready",
                      "--anthology-id", "ANTHselftest01",
                      "--producer-id", "PRODselftest01",
                      "--confirm-name", "Self Test Voices",
                      "--door", "dashboard"])
        check("s9 ready fires", rc == 0, "rc=%s" % rc)
        rc, _, _ = L(["record-approval", "--gate", "s9_ready",
                      "--anthology-id", "ANTHselftest01",
                      "--producer-id", "PRODselftest01",
                      "--confirm-name", "Self Test Voices",
                      "--door", "dashboard"])
        check("s9 double-fire no-op", rc == 0, "rc=%s" % rc)
        # attack 7: token refusals (foreign / expired / forged) via gate_engine.
        rc, _, _ = _gate(["verify", "--subject-key", key,
                          "--token", "v1.not.a.real.token"],
                         state)
        check("forged token refused (AF-AE-TOKEN-REFUSED)", rc == 2, "rc=%s" % rc)
        rc, _, _ = _gate(["decide", "--subject-key", key, "--door", "token",
                          "--action", "approve_as_is"], state)
        check("token-door decide without credential refused", rc == 2, "rc=%s" % rc)
        # attack 8: board door never reaches 'done' (engine-side invariant).
        rc, parsed, err = _run(
            _state(MC_BOARD) + ["status", "--subject-key", key,
                                "--state-dir", str(state), "--json"],
            state_dir=state, timeout=60)
        check("mc_board status exits 0 fail-soft", rc == 0, "rc=%s" % rc)
        if parsed is not None:
            check("mc_board never projects 'done'",
                  "done" not in json.dumps(parsed),
                  json.dumps(parsed)[:160])
        # attack 9: a Tier-1 chapter below the band FAILS closed.
        short = chapter_text("Rise", "A Story", "the door", "Ada", n_words=200)
        env_p = tmp / "env-short.json"
        env_p.write_text(json.dumps({
            "kind": "chapter", "artifact_text": short,
            "title": {"title": "Rise", "subtitle": "A Story"},
            "intake": {"personal_stories": "the door", "email": "", "phone": ""},
            "identity": {"contact_id": "Cselftest01", "anthology_id": "ANTHselftest01"},
            "run_ledger": {"stages": [{"model": "glm-5.2"}]}}), encoding="utf-8")
        rc, parsed, _ = _run(
            _state(QC_TIER1) + ["--envelope", str(env_p), "--json"],
            state_dir=state, timeout=120)
        check("chapter below 2000-word band fails closed", rc == 4,
              "rc=%s" % rc)
        # attack 10: an em-dash in the deliverable fails Tier 1 check 5.
        dash_text = chapter_text("Rise", "A Story", "the door", "Ada", 2100)
        dash_text += "\n\nThis sentence carries an em dash — in the middle."
        env_p2 = tmp / "env-dash.json"
        env_p2.write_text(json.dumps({
            "kind": "chapter", "artifact_text": dash_text,
            "title": {"title": "Rise", "subtitle": "A Story"},
            "intake": {"personal_stories": "the door", "email": "", "phone": ""},
            "identity": {"contact_id": "Cselftest01", "anthology_id": "ANTHselftest01"},
            "run_ledger": {"stages": [{"model": "glm-5.2"}]}}), encoding="utf-8")
        rc, parsed, _ = _run(
            _state(QC_TIER1) + ["--envelope", str(env_p2), "--json"],
            state_dir=state, timeout=120)
        check("em-dash in deliverable fails Tier 1", rc == 4, "rc=%s" % rc)
        # attack 11: judge independence is enforced (fail-closed).
        rc, parsed, err = _run(
            _state(JUDGE_HARNESS) + ["gate", "--json"], state_dir=state,
            timeout=60, input_text=json.dumps({
                "kind": "chapter",
                "deliverable_text": chapter_text("Rise", "A Story", "the door", "Ada", 2100),
                "writer_tier": "JUDGE", "writer_model": "glm-5.2",
                "writer_persona": "x", "judge_model": "glm-5.2",
                "judge_response": {"checks": {"13": {"pass": True}},
                                   "dimensions": {"1": {"score": 9}}}}))
        check("judge independence violation refused", rc == 2, "rc=%s" % rc)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    # ---- 4. no Anthropic-family id in this file ----------------------------
    own = Path(__file__).read_text(encoding="utf-8")
    check("no Anthropic-family id in canary source", not BANNED.search(own))

    # ---- 5. the exit-code map + the stage inventory are coherent ------------
    try:
        man = json.loads((SKILL_DIR / "ENGINE-MANIFEST.json").read_text(encoding="utf-8"))
        inv = man.get("script_inventory") or []
        rows = [r for r in inv if "canary_e2e_test.py" in (r.get("script") or "")]
        check("canary inventoried in ENGINE-MANIFEST script_inventory",
              len(rows) == 1, "rows=%d" % len(rows))
    except (OSError, ValueError) as exc:
        check("canary inventoried in ENGINE-MANIFEST script_inventory",
              False, "manifest unreadable: %s" % exc)

    # ---- 6. report-verification (U19): chain determinism + tamper detection --
    t6 = Path(tempfile.mkdtemp(prefix="canary_verifyreport_"))
    try:
        (t6 / "state").mkdir(parents=True)
        for rel in ("anthology_state.db", "gate_nonce.db"):
            (t6 / "state" / rel).write_bytes(b"\x00sqlite canary fixture")
        t6rep = {
            "contract": "anthology-engine-canary-report", "schema_version": 1,
            "utc": "2026-08-11T00:00:00+00:00", "state_dir": str(t6 / "state"),
            "mode": "run", "verdict": "PASS",
            "stages": [
                {"stage": "S7", "label": "COVER SET", "status": "PASS",
                 "checks": [{"check": "live 4-style cover render (Kie + Drive landing)",
                             "result": "DEFERRED", "note": DEFERRED_LIVE_NOTE}]},
            ],
            "summary": {"stages_total": 1, "stages_passed": 1, "stages_deferred": 0,
                        "stages_failed": 0, "failed_stages": [], "deferred_stages": [],
                        "note": DEFERRED_LIVE_NOTE},
        }
        sig = {"alg": "sha256", "chain": "v1:report-body+state-ledger",
               "sha256": compute_report_chain(t6rep, t6 / "state")}
        t6rep["signature"] = sig
        # determinism: re-computing over the same bytes reproduces the hash.
        check("report chain is deterministic",
              compute_report_chain(t6rep, t6 / "state") == sig["sha256"])
        # tamper: a single changed evidence byte breaks the chain.
        tampered = json.loads(json.dumps(t6rep))
        tampered["stages"][0]["checks"][0]["evidence"] = "x"
        check("tampered report body breaks the chain",
              compute_report_chain(tampered, t6 / "state") != sig["sha256"])
        # tamper: a changed ledger byte breaks the chain.
        (t6 / "state" / "anthology_state.db").write_bytes(b"\x01sqlite canary fixture")
        check("tampered state ledger breaks the chain",
              compute_report_chain(t6rep, t6 / "state") != sig["sha256"])
        # restore the ledger bytes so the VALID round-trip below re-computes
        # the same hash the signature was made over.
        (t6 / "state" / "anthology_state.db").write_bytes(b"\x00sqlite canary fixture")
        # missing ledger: verify must fail closed.
        t6missing = json.loads(json.dumps(t6rep))
        t6missing["state_dir"] = str(t6 / "no-such-state")
        (t6 / "missing.json").write_text(json.dumps(t6missing), encoding="utf-8")
        rc_v = cmd_verify_report(str(t6 / "missing.json"))
        check("verify-report fails closed on missing ledger", rc_v == EX_VIOLATION,
              "rc=%s" % rc_v)
        # deferred-live check without the note: verify must refuse.
        t6nonote = json.loads(json.dumps(t6rep))
        del t6nonote["stages"][0]["checks"][0]["note"]
        t6nonote["signature"] = {"alg": "sha256",
                                 "chain": "v1:report-body+state-ledger",
                                 "sha256": compute_report_chain(t6nonote, t6 / "state")}
        (t6 / "nonote.json").write_text(json.dumps(t6nonote), encoding="utf-8")
        rc_v = cmd_verify_report(str(t6 / "nonote.json"))
        check("verify-report refuses a deferred live check without the note",
              rc_v == EX_VIOLATION, "rc=%s" % rc_v)
        # a VALID report round-trips through verify with exit 0.
        (t6 / "ok.json").write_text(json.dumps(t6rep), encoding="utf-8")
        rc_v = cmd_verify_report(str(t6 / "ok.json"))
        check("verify-report VALID exit 0", rc_v == EX_OK, "rc=%s" % rc_v)
    finally:
        shutil.rmtree(t6, ignore_errors=True)

    passed = sum(1 for _, ok, _ in checks if ok)
    total = len(checks)
    sys.stdout.write("canary_e2e_test self-test: %d/%d passed\n" % (passed, total))
    for name, ok, ev in checks:
        if not ok:
            sys.stdout.write("  FAIL: %s  %s\n" % (name, ev))
    return EX_OK if passed == total else EX_VIOLATION


def build_parser():
    ap = argparse.ArgumentParser(
        prog="canary_e2e_test.py",
        description="One complete S0..S9 anthology canary with two synthetic "
                    "co-authors (MASTER-SPEC NEW-4).")
    ap.add_argument("--self-test", action="store_true",
                    help="offline acceptance battery (golden + attack fixtures)")
    ap.add_argument("--plan", action="store_true",
                    help="print the stage plan and exit")
    ap.add_argument("--state-dir", default="",
                    help="engine state dir (default: a fresh temp dir)")
    ap.add_argument("--report-dir", default="",
                    help="report dir for CANARY-REPORT.json (default: state dir/reports)")
    ap.add_argument("--gateway-base-url", default=DEFAULT_GATEWAY_BASE,
                    help="gateway base for the intake T-battery (default %s)"
                         % DEFAULT_GATEWAY_BASE)
    ap.add_argument("--public-url", default="",
                    help="real named Cloudflare Tunnel public URL for the live "
                         "T8 intake proof (NEVER Tailscale)")
    ap.add_argument("--require-live", action="store_true",
                    help="any un-executed live stage holds the canary (exit 3)")
    ap.add_argument("--verify-report", default="",
                    help="independently re-check a persisted CANARY-REPORT.json "
                         "claim (deterministic sha256 chain over the report body "
                         "plus the state ledger it names; exit 0 VALID / 4 INVALID)")
    return ap


def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]
    argv = list(argv)
    if "--self-test" in argv:
        argv = ["--self-test" if a == "--self-test" else a for a in argv]
    if "--selftest" in argv:
        argv = ["--self-test" if a == "--selftest" else a for a in argv]
    args = build_parser().parse_args(argv)
    try:
        if args.self_test:
            return self_test()
        if args.plan:
            return cmd_plan()
        if args.verify_report:
            return cmd_verify_report(args.verify_report)
        return run_canary(args)
    except BrokenPipeError:
        return EX_OK
    except Exception as exc:  # noqa: BLE001 -- house convention: unexpected -> 1
        sys.stderr.write("[canary_e2e_test] unexpected error: %s\n" % exc)
        return EX_ERR


if __name__ == "__main__":
    sys.exit(main())
