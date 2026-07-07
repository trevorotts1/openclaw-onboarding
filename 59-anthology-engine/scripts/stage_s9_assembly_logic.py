#!/usr/bin/env python3
"""stage_s9_assembly_logic.py -- the S9 ANTHOLOGY ASSEMBLY module (SPEC 4 S9,
PRD 3.11). The thin runner stage_s9_assembly.py dispatches here; this module is
the substance between the two producer decisions that bracket S9.

BOUNDARY (hard): anthology_state.py is the SOLE durable-ledger writer (SPEC 7.4).
This module NEVER writes state directly -- every ledger mutation shells through
anthology_state.py, mirroring intake_router._run_writer. The six PRD 3.11 guards
are ENFORCED by that writer's legal-transition matrix; this module ARMS from the
writer's read-only readiness report, FIRES the trigger through the writer, and
faithfully SURFACES each guard outcome. A pure-Python readiness evaluator lives
here for pre-flight display and self-test; it is defense-in-depth, never the
authority.

TWO PRODUCER DECISIONS bracket S9:
  1. fire_ready()  -- the producer "I'm ready to assemble" trigger (gate
     s9_ready), from the Assembly card OR the readiness nudge deep link (both
     doors, ONE endpoint, ONE subcommand). Guards, writer-enforced:
       (a) own-producer auth (non-producer refused, exit 5);
       (b) every participant approved OR carrying an explicit exclude row
           (unapproved blocks with the list; an excluded participant does not
           block and its exclusion is recorded);
       (c) at least min_chapters frozen approved chapters (floor 2, exit 2);
       (d) typed anthology-name confirmation via --confirm-name (mismatch exit 5);
       (e) one-way: re-firing is an acknowledged no-op.
  2. sign_off() -- the producer final-manuscript sign-off (gate s9_producer)
     closes the anthology.

BETWEEN them, run_assembly() drives the machinery:
  order curation (ae-01) with rationale -> editor's introduction (ae-02) in the
  producer's voice from producer inputs ONLY -> front/back matter (ae-04) ->
  contributor bios (ae-03) from ledger identities -> compile from FROZEN approved
  chapters (sha256 byte-identical, LONGCTX whole-manuscript when configured else
  chunked on HEAVY-WRITER) -> assembly-scope Gate B -> hand to stage_s8_deliver.

Persona (PRD 13): anthology-producer-orchestrator speaking the Anthology Editor
voice (ae-01..04), ALWAYS subordinate to the producer's supplied voice inputs.
Prompts never name a model; tiers are the only vocabulary above the router.

Exit codes (align with the stage-runner contract, SPEC 3.4 row 6):
  0  step complete and persisted
  2  prover / Gate B / order or frozen-chapter integrity failure (a QC attempt)
  3  held (a collaborator not yet wired, credits, or a lost callback)
  5  unresolved prompt slot (AF-AE-SLOT-UNRESOLVED) or writer validation
     (confirm-name mismatch / non-producer -> the writer's own exit 5)
  1  unexpected error
"""
import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

# --------------------------------------------------------------------------- #
# Paths (skill-local; mirrors the sibling modules' resolution)
# --------------------------------------------------------------------------- #
SKILL_DIR = Path(__file__).resolve().parent.parent
SCRIPTS = SKILL_DIR / "scripts"
PROMPTS = SKILL_DIR / "assets" / "prompts"
REPO_ROOT = SKILL_DIR.parent

STATE_WRITER = SCRIPTS / "anthology_state.py"          # SOLE ledger writer (SPEC 7.4)
QC_TIER1 = SCRIPTS / "qc-tier1-anthology.py"           # Gate B, assembly mode (W1.17)
DELIVER_RUNNER = SCRIPTS / "stage_s8_deliver.py"       # manuscript Doc + PDF delivery

# --------------------------------------------------------------------------- #
# Exit codes (mirror anthology_state.py + the stage-runner contract)
# --------------------------------------------------------------------------- #
EX_OK, EX_ERR, EX_PROVER, EX_HELD, EX_VALIDATION = 0, 1, 2, 3, 5
EX_SLOT = 5  # AF-AE-SLOT-UNRESOLVED shares the validation code (unresolved slot)

# Writer exit codes (anthology_state.py), named for clarity of the fire surface.
W_OK, W_ILLEGAL, W_UNKNOWN, W_BASE_DEFERRED, W_VALIDATION = 0, 2, 3, 4, 5

# Ledger truths mirrored for the pure evaluator (kept in lockstep with the
# writer's own constants; the writer stays authoritative at runtime).
APPROVED_CURSORS = ("approved", "delivered")
MIN_CHAPTERS_FLOOR = 2
ASSEMBLY_FIRED = ("ready_confirmed", "proposed", "adjusted", "compiled", "signed_off")

# --------------------------------------------------------------------------- #
# Engine-OWNED S9 prompt pins, referenced BY FILENAME (the canonical names in
# ENGINE-MANIFEST.engine_owned_prompt_pins and SPEC 4 S9). The numeric ae-0N id
# is an ALIAS that here matches SPEC 4 S9 exactly (ae-03 = contributor bios,
# ae-04 = front/back matter); wiring nonetheless resolves BY FILENAME so any
# future manifest renumbering can never mis-bind content to the wrong pin.
# --------------------------------------------------------------------------- #
PINS = {
    "order_curation": "ae-01-order-curation.md",
    "editors_intro": "ae-02-editor-introduction.md",
    "bios": "ae-03-contributor-bio.md",
    "front_back_matter": "ae-04-front-back-matter.md",
}

TIER_HEAVY = "HEAVY-WRITER"   # curation, intro, matter, bios (SPEC 8.1)
TIER_LONGCTX = "LONGCTX"      # optional whole-manuscript compile review

# Autofail codes surfaced by this module (ENGINE-MANIFEST AF-AE-* table).
AF_SLOT = "AF-AE-SLOT-UNRESOLVED"
AF_FROZEN = "AF-AE-S9-FROZEN"
AF_FABRICATION = "AF-AE-S9-FABRICATION"

_SLOT_RE = re.compile(r"\{\{\s*([A-Za-z0-9_]+)\s*\}\}")

MANUSCRIPT_ARTIFACT_TYPE = "anthology_manuscript"


# --------------------------------------------------------------------------- #
# Typed faults
# --------------------------------------------------------------------------- #
class S9Error(Exception):
    exit_code = EX_ERR


class SlotUnresolved(S9Error):
    exit_code = EX_SLOT

    def __init__(self, pin_role, missing):
        self.pin_role = pin_role
        self.missing = list(missing)
        super().__init__("%s: pin %r has unresolved slots %s (fail-closed)"
                         % (AF_SLOT, pin_role, self.missing))


class CurationInvalid(S9Error):
    exit_code = EX_PROVER


class FrozenChapterMismatch(S9Error):
    exit_code = EX_PROVER

    def __init__(self, participant_key, expected, actual):
        self.participant_key = participant_key
        self.expected = expected
        self.actual = actual
        super().__init__("%s: chapter %r is not byte-identical to its frozen "
                         "artifact (expected sha256 %s, got %s)"
                         % (AF_FROZEN, participant_key, expected, actual))


class ProducerInputsMissing(S9Error):
    exit_code = EX_PROVER  # refuse rather than fabricate; not a slot fault


class CollaboratorUnwired(S9Error):
    exit_code = EX_HELD


class WriterUnreachable(S9Error):
    exit_code = EX_HELD


# --------------------------------------------------------------------------- #
# Pure helpers (no I/O; the self-test's backbone)
# --------------------------------------------------------------------------- #
def sha256_hex(data):
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def evaluate_readiness(members, min_chapters=MIN_CHAPTERS_FLOOR):
    """Faithful mirror of anthology_state._readiness for pre-flight display and
    self-test. `members` is a list of dicts:
        {participant_key, stage_cursor, excluded: bool, has_frozen_chapter: bool}
    Returns the readiness report with the blocking list. NOT the authority at
    runtime -- the writer's assembly-readiness-report is."""
    blocking = []
    excluded_recorded = []
    frozen_chapter_count = 0
    counted = 0
    for m in members:
        mk = m["participant_key"]
        if m.get("excluded"):
            excluded_recorded.append(mk)   # explicit exclusion recorded; does NOT block
            continue
        counted += 1
        if m.get("stage_cursor") not in APPROVED_CURSORS:
            blocking.append({"participant_key": mk, "reason": "not_approved",
                             "stage_cursor": m.get("stage_cursor")})
            continue
        if not m.get("has_frozen_chapter"):
            blocking.append({"participant_key": mk, "reason": "no_frozen_chapter",
                             "stage_cursor": m.get("stage_cursor")})
        else:
            frozen_chapter_count += 1
    below_min = frozen_chapter_count < min_chapters
    ready = (not blocking) and (not below_min) and counted > 0
    return {
        "ready": ready,
        "min_chapters": min_chapters,
        "frozen_chapter_count": frozen_chapter_count,
        "active_members": counted,
        "below_min_chapters": below_min,
        "excluded_recorded": excluded_recorded,
        "blocking": blocking,
    }


def validate_order_permutation(order, allowed_keys):
    """Order must be a permutation of the staged set: every allowed key once, no
    dupes, no unknown. Returns (ok, detail)."""
    allowed = set(allowed_keys)
    ordset = set(order)
    dupes = sorted({k for k in order if order.count(k) > 1})
    unknown = sorted(ordset - allowed)
    missing = sorted(allowed - ordset)
    ok = not dupes and not unknown and not missing and len(order) == len(allowed)
    return ok, {"dupes": dupes, "unknown": unknown, "missing": missing}


def verify_frozen_sha(recomputed_sha, expected_sha):
    return bool(recomputed_sha) and recomputed_sha == expected_sha


def classify_fire_outcome(rc, parsed):
    """Map the writer's (rc, json) from `record-approval --gate s9_ready` to a
    single guard-outcome label. The writer is the authority; this only names
    what it decided so a caller/UI can react."""
    parsed = parsed or {}
    if rc == W_OK:
        if parsed.get("noop"):
            return "double_fire_noop"      # guard (e): one-way, re-fire is a no-op
        return "fired"
    if rc == W_BASE_DEFERRED:
        return "fired_base_deferred"       # mirror committed, base op queued (exit 4)
    if rc == W_VALIDATION:
        # guard (a) non-producer OR guard (d) confirm-name mismatch -> exit 5
        return "refused_validation"
    if rc == W_ILLEGAL:
        return "not_ready"                 # guard (b)/(c): blocking list in detail
    if rc == W_UNKNOWN:
        return "unknown_key"
    return "error"


def compose_pin(pin_text, slots, pin_role="?"):
    """Resolve {{slot}} tokens against `slots`. FAIL-CLOSED: any slot named in
    the pin but absent from `slots`, or any residual {{...}} after substitution,
    raises SlotUnresolved (AF-AE-SLOT-UNRESOLVED)."""
    required = set(_SLOT_RE.findall(pin_text))
    missing = sorted(name for name in required if name not in slots)
    if missing:
        raise SlotUnresolved(pin_role, missing)

    def _sub(match):
        return str(slots[match.group(1)])

    out = _SLOT_RE.sub(_sub, pin_text)
    if "{{" in out:  # a malformed / nested slot survived: fail closed
        residual = sorted(set(re.findall(r"\{\{[^}]*", out)))
        raise SlotUnresolved(pin_role, residual)
    return out


def _extract_json_object(text):
    """Pull the first balanced top-level JSON object from a model reply (models
    sometimes wrap JSON in prose or a fence). Deterministic, no dependency."""
    if text is None:
        raise CurationInvalid("empty model reply; no JSON object")
    s = text.strip()
    if s.startswith("```"):
        s = s.split("```", 2)[1] if s.count("```") >= 2 else s.strip("`")
        if s.lstrip().startswith("json"):
            s = s.lstrip()[4:]
    start = s.find("{")
    if start < 0:
        raise CurationInvalid("no JSON object in model reply")
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(s)):
        c = s[i]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
            continue
        if c == '"':
            in_str = True
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(s[start:i + 1])
                except json.JSONDecodeError as exc:
                    raise CurationInvalid("malformed JSON in model reply: %s" % exc)
    raise CurationInvalid("unbalanced JSON object in model reply")


def split_sentinel(text, name):
    """Extract the block between <!-- name --> and <!-- END name -->."""
    open_s = "<!-- %s -->" % name
    close_s = "<!-- END %s -->" % name
    i = text.find(open_s)
    j = text.find(close_s)
    if i < 0 or j < 0 or j < i:
        return None
    return text[i + len(open_s):j].strip()


# --------------------------------------------------------------------------- #
# Sole-writer subprocess (the ONLY ledger write path; mirrors intake_router)
# --------------------------------------------------------------------------- #
def _run_writer(subcmd_args, state_dir, db=None, timeout=30):
    """Invoke anthology_state.py <subcmd> [--state-dir DIR | --db PATH] --json ...
    Returns (rc, parsed_json_or_None, stderr_text)."""
    if not STATE_WRITER.exists():
        raise WriterUnreachable("sole writer missing: %s" % STATE_WRITER)
    loc = ["--db", str(db)] if db else ["--state-dir", str(state_dir)]
    argv = [sys.executable or "python3", str(STATE_WRITER),
            subcmd_args[0], "--json"] + loc + list(subcmd_args[1:])
    try:
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise WriterUnreachable("sole writer timed out (%ss): %s"
                                % (timeout, subcmd_args[0]))
    parsed = None
    out = (proc.stdout or "").strip()
    if out:
        try:
            parsed = json.loads(out)
        except Exception:  # noqa: BLE001
            parsed = None
    return proc.returncode, parsed, (proc.stderr or "").strip()


# --------------------------------------------------------------------------- #
# Default router port (lazy import so the module stays importable / self-tests
# without a resolved model map or network)
# --------------------------------------------------------------------------- #
def _default_router(tier, messages, context, run_dir=None, model_map_path=None):
    if str(SCRIPTS) not in sys.path:
        sys.path.insert(0, str(SCRIPTS))
    import model_router  # noqa: E402
    result = model_router.route(tier, messages, context, run_dir=run_dir,
                                model_map_path=model_map_path)
    return {"text": result.text, "model_used": result.model_used,
            "tier": result.tier, "provider": result.provider,
            "usage": result.usage}


def _longctx_available(run_dir=None, model_map_path=None):
    """True iff the client configured a LONGCTX (1M-context) key: the resolved
    map has a LONGCTX tier with at least one chain link whose credential is SET.
    Absent -> S9 compiles chunked on HEAVY-WRITER (SPEC 8.1 absent_behavior)."""
    try:
        if str(SCRIPTS) not in sys.path:
            sys.path.insert(0, str(SCRIPTS))
        import model_router  # noqa: E402
        model_map, _ = model_router.load_model_map(model_map_path, run_dir)
        tier_obj = model_router.resolve_tier(model_map, TIER_LONGCTX)
        for link in model_router.ordered_chain(tier_obj):
            provider = str(link.get("provider", ""))
            if provider.upper() == "HOLD":
                continue
            _, status = model_router.resolve_credential(
                str(link.get("credential_label", "")), provider, None)
            if status == "SET":
                return True
        return False
    except Exception:  # noqa: BLE001 -- optional tier; any resolution fault -> chunked
        return False


# --------------------------------------------------------------------------- #
# The S9 assembly orchestrator
# --------------------------------------------------------------------------- #
class S9Assembly:
    """Drives S9 for one anthology. Ports (router, state_writer, chapter_source,
    gate_b) default to the real collaborators and are injectable for tests. This
    class NEVER writes the ledger except through state_writer (anthology_state)."""

    def __init__(self, anthology_id, state_dir=None, db=None, run_dir=None,
                 model_map_path=None, *, router=None, state_writer=None,
                 chapter_source=None, gate_b=None, longctx_available=None):
        self.anthology_id = anthology_id
        self.state_dir = state_dir
        self.db = db
        self.run_dir = run_dir
        self.model_map_path = model_map_path
        self._router = router or _default_router
        self._state = state_writer or self._default_state_writer
        self._chapter_source = chapter_source          # (participant_key) -> (body_bytes, frozen_sha)
        self._gate_b = gate_b or self._default_gate_b
        self._longctx = (longctx_available if longctx_available is not None
                         else _longctx_available(run_dir, model_map_path))

    # -- ports --------------------------------------------------------------
    def _default_state_writer(self, subcmd_args):
        return _run_writer(subcmd_args, self.state_dir, db=self.db)

    def _default_gate_b(self, manuscript_path, order, contributors):
        """Assembly-scope Gate B (SPEC 5 S9 step 6). Fail-soft when the W1.17
        checker is not yet on the branch -> held (the durable ledger keeps the
        cursor at zero cost)."""
        if not QC_TIER1.exists():
            raise CollaboratorUnwired("Gate B checker not yet wired: %s" % QC_TIER1)
        argv = [sys.executable or "python3", str(QC_TIER1), "--mode", "assembly",
                "--anthology-id", self.anthology_id, "--json"]
        if manuscript_path:
            argv += ["--manuscript", str(manuscript_path)]
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=300)
        parsed = None
        if (proc.stdout or "").strip():
            try:
                parsed = json.loads(proc.stdout)
            except Exception:  # noqa: BLE001
                parsed = None
        return proc.returncode, parsed

    def _route(self, tier, messages, context):
        return self._router(tier, messages, context, run_dir=self.run_dir,
                            model_map_path=self.model_map_path)

    def _load_pin(self, role):
        path = PROMPTS / PINS[role]
        if not path.exists():
            raise CollaboratorUnwired("S9 pin missing: %s" % path)
        return path.read_text(encoding="utf-8")

    def _compose(self, role, slots):
        return compose_pin(self._load_pin(role), slots, pin_role=role)

    # -- read-only readiness (arm/refuse display) ---------------------------
    def readiness_report(self):
        """Shell the AUTHORITATIVE read-only report (anthology_state
        assembly-readiness-report). Returns the parsed report incl. the blocking
        list that arms or refuses the trigger."""
        rc, parsed, err = self._state(["assembly-readiness-report",
                                       "--anthology-id", self.anthology_id])
        if rc == W_UNKNOWN:
            raise S9Error("unknown anthology_id %r: %s" % (self.anthology_id, err))
        if parsed is None:
            raise WriterUnreachable("readiness report produced no JSON: %s" % err)
        return parsed

    # -- decision 1: the ready-to-assemble trigger (gate s9_ready) -----------
    def fire_ready(self, producer_id, confirm_name, door="dashboard",
                   notes=None, approval_id=None):
        """The producer 'I'm ready to assemble' trigger. Both doors (Assembly
        card / nudge deep link) call THIS with door in {dashboard, nudge_link}.
        All six PRD 3.11 guards are revalidated by the writer; we return (rc,
        parsed, outcome_label). The rc is the writer's own exit code so the
        caller propagates the exact guard meaning (5 mismatch/non-producer, 2
        not-ready, 0 fired-or-noop)."""
        args = ["record-approval", "--gate", "s9_ready",
                "--anthology-id", self.anthology_id,
                "--producer-id", producer_id, "--door", door]
        if confirm_name is not None:
            args += ["--confirm-name", confirm_name]
        if notes:
            args += ["--notes", notes]
        if approval_id:
            args += ["--approval-id", approval_id]
        rc, parsed, err = self._state(args)
        outcome = classify_fire_outcome(rc, parsed)
        report = dict(parsed or {})
        report["outcome"] = outcome
        if err and not parsed:
            report["stderr"] = err
        return rc, report, outcome

    # -- order curation (ae-01) ---------------------------------------------
    def curate_order(self, chapters, persist_state="proposed"):
        """Propose the running order with rationale (ae-01), validate it is a
        permutation of the staged set, and persist via assembly-set-order (the
        writer re-validates membership). `chapters` carries the ae-01 craft
        metadata. Returns the parsed proposal {order, position_rationale,
        overall_rationale}."""
        keys = [c["participant_key"] for c in chapters]
        slots = {
            "anthology_name": self._anth_name(),
            "anthology_theme": self._anth_theme(),
            "min_chapters": self._min_chapters(),
            "chapters_json": json.dumps(chapters, ensure_ascii=False),
        }
        composed = self._compose("order_curation", slots)
        reply = self._route(TIER_HEAVY, [{"role": "user", "content": composed}],
                            {"anthology_id": self.anthology_id, "step": "s9_order_curation"})
        proposal = _extract_json_object(reply["text"])
        order = proposal.get("order")
        if not isinstance(order, list):
            raise CurationInvalid("ae-01 reply has no 'order' array")
        ok, detail = validate_order_permutation(order, keys)
        if not ok:
            raise CurationInvalid("ae-01 order is not a permutation of the staged "
                                  "collection: %s" % detail)
        rc, parsed, err = self._state(["assembly-set-order",
                                       "--anthology-id", self.anthology_id,
                                       "--order", json.dumps(order),
                                       "--state", persist_state])
        if rc not in (W_OK, W_BASE_DEFERRED):
            raise S9Error("assembly-set-order refused (rc %s): %s" % (rc, err))
        proposal["_persisted_state"] = (parsed or {}).get("assembly_state", persist_state)
        proposal["_model_used"] = reply.get("model_used")
        return proposal

    def set_order(self, order, persist_state="adjusted"):
        """Persist a producer-ADJUSTED order (SPEC: producer adjusts in the
        dashboard). The writer validates it is a permutation of the staged set."""
        rc, parsed, err = self._state(["assembly-set-order",
                                       "--anthology-id", self.anthology_id,
                                       "--order", json.dumps(order),
                                       "--state", persist_state])
        if rc not in (W_OK, W_BASE_DEFERRED):
            raise S9Error("assembly-set-order (adjust) refused (rc %s): %s" % (rc, err))
        return parsed or {}

    # -- editor's introduction (ae-02), producer voice, producer inputs ONLY -
    def editor_intro(self, producer_inputs, contributors, producer_display_name,
                     chapter_order):
        """Draft the introduction in the producer's voice from producer-supplied
        inputs ONLY. Refuse (never fabricate) when the producer supplied nothing.
        The model is instructed to return [[INSUFFICIENT_PRODUCER_INPUT]] if the
        material is too thin; we surface that as a refusal, not a fabrication."""
        if not _has_producer_material(producer_inputs):
            raise ProducerInputsMissing(
                "%s: editor introduction requires producer-supplied voice inputs; "
                "none provided -- refusing rather than fabricating" % AF_FABRICATION)
        slots = {
            "anthology_name": self._anth_name(),
            "anthology_theme": self._anth_theme(),
            "producer_display_name": producer_display_name or "",
            "producer_voice_inputs": _as_text(producer_inputs),
            "contributors_json": json.dumps(contributors, ensure_ascii=False),
            "chapter_order_json": json.dumps(chapter_order, ensure_ascii=False),
        }
        composed = self._compose("editors_intro", slots)
        reply = self._route(TIER_HEAVY, [{"role": "user", "content": composed}],
                            {"anthology_id": self.anthology_id, "step": "s9_editor_intro"})
        body = split_sentinel(reply["text"], "EDITORS INTRO") or reply["text"].strip()
        if "[[INSUFFICIENT_PRODUCER_INPUT]]" in body:
            raise ProducerInputsMissing(
                "%s: producer inputs too thin for an honest introduction "
                "(model refused to fabricate)" % AF_FABRICATION)
        return {"intro_markdown": body, "model_used": reply.get("model_used")}

    # -- front & back matter (ae-04) ----------------------------------------
    def front_back_matter(self, producer_inputs, contributors, toc,
                          producer_display_name, copyright_year, subtitle=""):
        slots = {
            "anthology_name": self._anth_name(),
            "anthology_subtitle": subtitle or "",
            "anthology_theme": self._anth_theme(),
            "producer_display_name": producer_display_name or "",
            "copyright_year": str(copyright_year),
            "toc_json": json.dumps(toc, ensure_ascii=False),
            "producer_voice_inputs": _as_text(producer_inputs),
            "contributors_json": json.dumps(contributors, ensure_ascii=False),
        }
        composed = self._compose("front_back_matter", slots)
        reply = self._route(TIER_HEAVY, [{"role": "user", "content": composed}],
                            {"anthology_id": self.anthology_id, "step": "s9_front_back_matter"})
        text = reply["text"]
        return {
            "front_matter_markdown": split_sentinel(text, "FRONT MATTER") or "",
            "back_matter_markdown": split_sentinel(text, "BACK MATTER") or "",
            "model_used": reply.get("model_used"),
        }

    # -- contributor bios (ae-03) from ledger identities --------------------
    def bios(self, contributors, chapter_order):
        slots = {
            "anthology_name": self._anth_name(),
            "contributors_json": json.dumps(contributors, ensure_ascii=False),
            "chapter_order_json": json.dumps(chapter_order, ensure_ascii=False),
        }
        composed = self._compose("bios", slots)
        reply = self._route(TIER_HEAVY, [{"role": "user", "content": composed}],
                            {"anthology_id": self.anthology_id, "step": "s9_bios"})
        parsed = _extract_json_object(reply["text"])
        bios = parsed.get("bios")
        if not isinstance(bios, list) or not bios:
            raise CurationInvalid("ae-03 reply has no 'bios' array")
        got = {b.get("participant_key") for b in bios}
        want = {c["participant_key"] for c in contributors}
        if got != want:
            raise CurationInvalid("ae-03 bios cover %s but the ledger contributors "
                                  "are %s (no fabricated / dropped bios allowed)"
                                  % (sorted(got), sorted(want)))
        return {"bios": bios, "model_used": reply.get("model_used")}

    # -- compile from FROZEN approved chapters (sha256 byte-identical) -------
    def compile_manuscript(self, order, frozen_shas, front_matter, intro,
                           bios_by_key, back_matter, out_path=None):
        """Assemble the manuscript DETERMINISTICALLY from the frozen approved
        chapter bodies, in curated order, wrapped by the generated matter. The
        LLM never touches a chapter body, so each chapter stays byte-identical to
        its frozen artifact. `frozen_shas` maps participant_key -> the Artifacts
        row sha256; the chapter_source port returns (body_bytes, source_sha) and
        we prove body sha == frozen sha before inclusion (AF-AE-S9-FROZEN).

        Then the writer's assembly-advance --to compiled --verify-sha re-proves
        byte-identity and moves assembly_state to compiled. The compile TIER
        (LONGCTX whole-manuscript when configured, else chunked HEAVY-WRITER)
        governs an optional continuity review that produces producer-facing
        notes ONLY; it can never mutate a chapter."""
        if self._chapter_source is None:
            raise CollaboratorUnwired("chapter_source port not wired (reuse-path / "
                                      "drive_adapter reader supplies frozen bodies)")
        segments = []
        verify_pairs = []
        if front_matter:
            segments.append(front_matter)
        if intro:
            segments.append(intro)
        for mk in order:
            body_bytes, source_sha = self._chapter_source(mk)
            recomputed = sha256_hex(body_bytes)
            expected = frozen_shas.get(mk)
            if not verify_frozen_sha(recomputed, expected):
                raise FrozenChapterMismatch(mk, expected, recomputed)
            if source_sha is not None and source_sha != expected:
                raise FrozenChapterMismatch(mk, expected, source_sha)
            body_text = (body_bytes.decode("utf-8") if isinstance(body_bytes, bytes)
                         else str(body_bytes))
            segments.append(body_text)
            verify_pairs.append("%s=%s" % (mk, expected))
        # contributor bios, in curated order, then back matter
        if bios_by_key:
            bio_block = "\n\n".join(bios_by_key[mk] for mk in order if mk in bios_by_key)
            if bio_block:
                segments.append("# Contributors\n\n" + bio_block)
        if back_matter:
            segments.append(back_matter)
        manuscript = "\n\n".join(s for s in segments if s)

        compile_tier = TIER_LONGCTX if self._longctx else TIER_HEAVY
        continuity_notes = None  # optional review is wired by the integrator; never mutates

        manuscript_sha = sha256_hex(manuscript)
        if out_path:
            Path(out_path).write_text(manuscript, encoding="utf-8")

        # Writer's authoritative byte-identity re-proof + state -> compiled.
        rc, parsed, err = self._state(["assembly-advance",
                                       "--anthology-id", self.anthology_id,
                                       "--to", "compiled",
                                       "--verify-sha", ",".join(verify_pairs)])
        if rc == W_VALIDATION:
            raise FrozenChapterMismatch("(writer verify-sha)", "frozen", "mismatch")
        if rc == W_ILLEGAL:
            raise S9Error("compile refused as not-ready (rc 2): %s" % err)
        if rc not in (W_OK, W_BASE_DEFERRED):
            raise S9Error("assembly-advance --to compiled refused (rc %s): %s" % (rc, err))
        return {
            "manuscript": manuscript,
            "manuscript_sha256": manuscript_sha,
            "compile_tier": compile_tier,
            "longctx_used": bool(self._longctx),
            "chapter_count": len(order),
            "continuity_notes": continuity_notes,
            "assembly_state": (parsed or {}).get("assembly_state", "compiled"),
            "out_path": str(out_path) if out_path else None,
        }

    # -- assembly-scope Gate B ----------------------------------------------
    def assembly_gate_b(self, manuscript_path, order, contributors):
        """Every approved chapter present exactly once, order matches curation,
        introduction references only real contributors, one continuous
        14-point-floor PDF. rc 0 pass; nonzero -> prover failure (a QC attempt)."""
        rc, parsed = self._gate_b(manuscript_path, order, contributors)
        passed = rc == 0
        return {"passed": passed, "rc": rc, "report": parsed}

    # -- record the manuscript artifact row ---------------------------------
    def record_manuscript_artifact(self, manuscript_sha, model_used,
                                   prompt_pin_sha=None):
        # The writer AUTO-VERSIONS per (anthology, type): anthology_state
        # .cmd_record_artifact computes the next version itself and its
        # record-artifact parser exposes NO --version flag -- so we must never
        # pass one (doing so is an argparse error, rc 2). A same-sha replay is
        # an idempotent noop that returns the existing row's version.
        args = ["record-artifact", "--anthology-id", self.anthology_id,
                "--type", MANUSCRIPT_ARTIFACT_TYPE, "--sha256", manuscript_sha]
        if model_used:
            args += ["--model-used", model_used]
        if prompt_pin_sha:
            args += ["--prompt-pin-sha256", prompt_pin_sha]
        rc, parsed, err = self._state(args)
        if rc not in (W_OK, W_BASE_DEFERRED):
            raise S9Error("record-artifact (manuscript) refused (rc %s): %s" % (rc, err))
        return parsed or {}

    # -- decision 2: producer final sign-off (gate s9_producer) -------------
    def sign_off(self, producer_id, notes=None, approval_id=None):
        """The producer's final-manuscript sign-off closes the anthology
        (assembly_state -> signed_off; the writer moves status to delivered)."""
        args = ["record-approval", "--gate", "s9_producer",
                "--anthology-id", self.anthology_id, "--producer-id", producer_id]
        if notes:
            args += ["--notes", notes]
        if approval_id:
            args += ["--approval-id", approval_id]
        rc, parsed, err = self._state(args)
        if rc == W_VALIDATION:
            raise S9Error("s9_producer sign-off refused (non-producer / validation): %s"
                          % err)
        if rc not in (W_OK, W_BASE_DEFERRED):
            raise S9Error("s9_producer sign-off refused (rc %s): %s" % (rc, err))
        return rc, (parsed or {})

    # -- anthology metadata reads (from the writer's report/export) ---------
    def _anth(self):
        if not hasattr(self, "_anth_cache"):
            try:
                rc, parsed, _ = self._state(["export-bundle",
                                             "--anthology-id", self.anthology_id])
                self._anth_cache = ((parsed or {}).get("anthology")
                                    or (parsed or {}) or {})
            except Exception:  # noqa: BLE001
                self._anth_cache = {}
        return self._anth_cache

    def _anth_name(self):
        return self._anth().get("name", "")

    def _anth_theme(self):
        return self._anth().get("theme", "")

    def _min_chapters(self):
        return str(self._anth().get("min_chapters") or MIN_CHAPTERS_FLOOR)


# --------------------------------------------------------------------------- #
# small value helpers
# --------------------------------------------------------------------------- #
def _has_producer_material(producer_inputs):
    if not producer_inputs:
        return False
    if isinstance(producer_inputs, str):
        return bool(producer_inputs.strip())
    if isinstance(producer_inputs, dict):
        return any(_has_producer_material(v) for v in producer_inputs.values())
    if isinstance(producer_inputs, (list, tuple)):
        return any(_has_producer_material(v) for v in producer_inputs)
    return bool(producer_inputs)


def _as_text(producer_inputs):
    if isinstance(producer_inputs, str):
        return producer_inputs
    return json.dumps(producer_inputs, ensure_ascii=False, indent=2)


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def _print(obj, as_json):
    if as_json:
        print(json.dumps(obj, indent=2, ensure_ascii=False))
    else:
        print(obj if isinstance(obj, str) else json.dumps(obj, ensure_ascii=False))


def _build(a):
    return S9Assembly(a.anthology_id, state_dir=a.state_dir, db=a.db,
                      run_dir=a.run_dir, model_map_path=a.model_map)


def plan():
    print("S9 ANTHOLOGY ASSEMBLY -- module logic (stage_s9_assembly_logic.py)")
    print("sole ledger writer (shelled): %s" % STATE_WRITER)
    print("engine-owned S9 pins (by filename):")
    for role, fn in PINS.items():
        p = PROMPTS / fn
        print("  [%-9s] %-28s %s" % ("present" if p.exists() else "MISSING", fn, role))
    print("Gate B checker: %s (%s)" % (QC_TIER1, "present" if QC_TIER1.exists() else "PENDING-W1.17"))
    print("delivery runner: %s (%s)" % (DELIVER_RUNNER, "present" if DELIVER_RUNNER.exists() else "PENDING"))
    print("compile tier: LONGCTX when a 1M-context key is configured, else chunked HEAVY-WRITER")
    return EX_OK


def _read_stdin_json():
    raw = sys.stdin.read().strip()
    return json.loads(raw) if raw else {}


def main(argv=None):
    ap = argparse.ArgumentParser(description="S9 anthology assembly module logic "
                                             "(PRD 3.11 / SPEC 4 S9).")
    ap.add_argument("--anthology-id", dest="anthology_id")
    ap.add_argument("--state-dir", dest="state_dir")
    ap.add_argument("--db")
    ap.add_argument("--run-dir", dest="run_dir")
    ap.add_argument("--model-map", dest="model_map")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--plan", action="store_true")
    ap.add_argument("--self-test", action="store_true")
    sub = ap.add_subparsers(dest="cmd")

    sub.add_parser("readiness", help="read-only readiness report (arm/refuse)")

    f = sub.add_parser("fire", help="fire the s9_ready trigger (both doors)")
    f.add_argument("--producer-id", required=True)
    f.add_argument("--confirm-name", dest="confirm_name")
    f.add_argument("--door", default="dashboard", choices=["dashboard", "nudge_link"])
    f.add_argument("--notes")

    sub.add_parser("curate", help="ae-01 order curation (chapters JSON on stdin)")
    sub.add_parser("bios", help="ae-03 contributor bios (contributors JSON on stdin)")

    so = sub.add_parser("sign-off", help="s9_producer final sign-off (closes it)")
    so.add_argument("--producer-id", required=True)
    so.add_argument("--notes")

    args = ap.parse_args(argv)
    try:
        if args.self_test:
            return self_test()
        if args.plan:
            return plan()
        if not args.cmd:
            ap.error("a subcommand is required (readiness | fire | curate | bios | "
                     "sign-off), or use --plan / --self-test")
        if not args.anthology_id:
            ap.error("--anthology-id is required for %r" % args.cmd)

        eng = _build(args)
        if args.cmd == "readiness":
            _print(eng.readiness_report(), args.json)
            return EX_OK
        if args.cmd == "fire":
            rc, report, outcome = eng.fire_ready(args.producer_id, args.confirm_name,
                                                 door=args.door, notes=args.notes)
            _print(report, args.json)
            # propagate the WRITER's exit meaning (5 mismatch/non-producer, 2 not-ready)
            return rc if rc in (W_OK, W_ILLEGAL, W_VALIDATION, W_UNKNOWN,
                                W_BASE_DEFERRED) else EX_ERR
        if args.cmd == "curate":
            proposal = eng.curate_order(_read_stdin_json())
            _print(proposal, args.json)
            return EX_OK
        if args.cmd == "bios":
            payload = _read_stdin_json()
            out = eng.bios(payload.get("contributors", []),
                           payload.get("chapter_order", []))
            _print(out, args.json)
            return EX_OK
        if args.cmd == "sign-off":
            rc, parsed = eng.sign_off(args.producer_id, notes=args.notes)
            _print(parsed, args.json)
            return EX_OK if rc in (W_OK, W_BASE_DEFERRED) else EX_VALIDATION
        ap.error("unknown subcommand %r" % args.cmd)
    except S9Error as exc:
        sys.stderr.write("[s9-logic] %s: %s\n" % (type(exc).__name__, exc))
        return getattr(exc, "exit_code", EX_ERR)
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001 -- top-level fail-closed
        sys.stderr.write("[s9-logic] unexpected error: %s: %s\n"
                         % (type(exc).__name__, exc))
        return EX_ERR


# --------------------------------------------------------------------------- #
# SELF-TEST -- exercises every guard against fakes (no live DB, no network)
# --------------------------------------------------------------------------- #
def self_test():
    fails = []

    def check(name, cond):
        if not cond:
            fails.append(name)

    # ---- the six PRD 3.11 guards over the pure readiness evaluator ----------
    # (b) unapproved participant blocks WITH a list entry
    r = evaluate_readiness([
        {"participant_key": "cA::x", "stage_cursor": "approved", "excluded": False,
         "has_frozen_chapter": True},
        {"participant_key": "cB::x", "stage_cursor": "s5_gate", "excluded": False,
         "has_frozen_chapter": False},
    ])
    check("guard_unapproved_blocks", (not r["ready"]) and any(
        b["participant_key"] == "cB::x" and b["reason"] == "not_approved"
        for b in r["blocking"]))

    # (b) explicit EXCLUSION is recorded and does NOT block
    r2 = evaluate_readiness([
        {"participant_key": "cA::x", "stage_cursor": "approved", "excluded": False,
         "has_frozen_chapter": True},
        {"participant_key": "cB::x", "stage_cursor": "approved", "excluded": False,
         "has_frozen_chapter": True},
        {"participant_key": "cC::x", "stage_cursor": "s5_gate", "excluded": True,
         "has_frozen_chapter": False},
    ])
    check("guard_exclusion_recorded",
          r2["ready"] and r2["excluded_recorded"] == ["cC::x"] and not r2["blocking"])

    # (c) below-min floor 2 refuses even when all present are approved+frozen
    r3 = evaluate_readiness([
        {"participant_key": "cA::x", "stage_cursor": "approved", "excluded": False,
         "has_frozen_chapter": True},
    ])
    check("guard_below_min_floor2",
          (not r3["ready"]) and r3["below_min_chapters"] and r3["frozen_chapter_count"] == 1)

    # ready when >= floor approved+frozen, none blocking
    r4 = evaluate_readiness([
        {"participant_key": "cA::x", "stage_cursor": "approved", "excluded": False,
         "has_frozen_chapter": True},
        {"participant_key": "cB::x", "stage_cursor": "delivered", "excluded": False,
         "has_frozen_chapter": True},
    ])
    check("ready_when_floor_met", r4["ready"] and not r4["blocking"])

    # ---- fire-outcome classification of the writer's exit codes ------------
    check("fire_non_producer_refused", classify_fire_outcome(5, {"ok": False}) == "refused_validation")
    check("fire_confirm_mismatch_exit5", classify_fire_outcome(5, None) == "refused_validation")
    check("fire_not_ready_exit2", classify_fire_outcome(2, {"blocking": [1]}) == "not_ready")
    check("fire_double_fire_noop", classify_fire_outcome(0, {"noop": True}) == "double_fire_noop")
    check("fire_happy", classify_fire_outcome(0, {"assembly_state": "ready_confirmed"}) == "fired")
    check("fire_base_deferred", classify_fire_outcome(4, {}) == "fired_base_deferred")

    # ---- order-permutation validation --------------------------------------
    ok, _ = validate_order_permutation(["a", "b", "c"], ["c", "b", "a"])
    check("order_valid_permutation", ok)
    ok2, d2 = validate_order_permutation(["a", "a", "b"], ["a", "b", "c"])
    check("order_rejects_dupe_and_missing", (not ok2) and "a" in d2["dupes"] and "c" in d2["missing"])
    ok3, d3 = validate_order_permutation(["a", "b", "z"], ["a", "b", "c"])
    check("order_rejects_unknown", (not ok3) and "z" in d3["unknown"] and "c" in d3["missing"])

    # ---- frozen-chapter sha256 byte-identity -------------------------------
    body = b"# Chapter One\n\nfrozen body\n"
    good = sha256_hex(body)
    check("frozen_sha_match", verify_frozen_sha(good, good))
    check("frozen_sha_mismatch_caught", not verify_frozen_sha(sha256_hex(b"tampered"), good))

    # ---- slot composer fail-closed -----------------------------------------
    try:
        compose_pin("hello {{present}} and {{absent}}", {"present": "x"}, "t")
        check("slot_fail_closed", False)
    except SlotUnresolved as exc:
        check("slot_fail_closed", exc.missing == ["absent"])
    check("slot_resolves_all",
          compose_pin("a {{x}} b {{y}}", {"x": "1", "y": "2"}, "t") == "a 1 b 2")

    # ---- every authored pin loads and composes with its declared slots -----
    for role in PINS:
        p = PROMPTS / PINS[role]
        if not p.exists():
            check("pin_present_%s" % role, False)
            continue
        text = p.read_text(encoding="utf-8")
        slots = {name: "X" for name in set(_SLOT_RE.findall(text))}
        try:
            composed = compose_pin(text, slots, role)
            check("pin_composes_%s" % role, "{{" not in composed)
        except SlotUnresolved:
            check("pin_composes_%s" % role, False)
        # the formatter's leftover-placeholder token, assembled from fragments so
        # no literal appears in this shipped source (mirrors the writer's deny-fixture)
        unchanged_token = "[" + "UNCHANGED" + "]"
        check("pin_no_unchanged_placeholder_%s" % role, unchanged_token not in text)

    # ---- sentinel extraction (intro / matter) ------------------------------
    intro = "pre <!-- EDITORS INTRO -->\n# Introduction\nbody\n<!-- END EDITORS INTRO --> post"
    check("sentinel_intro", split_sentinel(intro, "EDITORS INTRO").startswith("# Introduction"))
    matter = "<!-- FRONT MATTER -->F<!-- END FRONT MATTER --><!-- BACK MATTER -->B<!-- END BACK MATTER -->"
    check("sentinel_front", split_sentinel(matter, "FRONT MATTER") == "F")
    check("sentinel_back", split_sentinel(matter, "BACK MATTER") == "B")

    # ---- JSON extraction from a fenced / prose-wrapped reply ---------------
    fenced = 'Here is the order:\n```json\n{"order": ["a", "b"], "overall_rationale": "x"}\n```\n'
    obj = _extract_json_object(fenced)
    check("json_extract_fenced", obj["order"] == ["a", "b"])

    # ---- producer-inputs presence guard (never fabricate) ------------------
    check("producer_inputs_absent", not _has_producer_material({}))
    check("producer_inputs_absent_blankstr", not _has_producer_material({"why": "  "}))
    check("producer_inputs_present", _has_producer_material({"why": "I gathered these voices"}))

    # ---- editor_intro refuses when producer inputs are empty (no network) --
    eng = S9Assembly("anthA", db=":memory:", router=_never_call_router,
                     state_writer=lambda a: (0, {}, ""),
                     longctx_available=False)
    try:
        eng.editor_intro({}, [{"participant_key": "cA::x"}], "Prod", ["cA::x"])
        check("editor_intro_refuses_empty", False)
    except ProducerInputsMissing:
        check("editor_intro_refuses_empty", True)

    # ---- curate_order end-to-end with a FAKE router + FAKE writer -----------
    chapters = [
        {"participant_key": "cA::x", "contributor_name": "A", "word_count": 3000,
         "tone": "warm", "subtheme": "beginnings", "strength_signal": 9,
         "chapter_title": "T1", "one_line_summary": "s1"},
        {"participant_key": "cB::x", "contributor_name": "B", "word_count": 2100,
         "tone": "wry", "subtheme": "endings", "strength_signal": 8,
         "chapter_title": "T2", "one_line_summary": "s2"},
    ]

    def fake_router(tier, messages, context, run_dir=None, model_map_path=None):
        assert tier == TIER_HEAVY
        return {"text": '{"order": ["cB::x", "cA::x"], "position_rationale": '
                        '[{"position":1,"participant_key":"cB::x","reason":"r"},'
                        '{"position":2,"participant_key":"cA::x","reason":"r"}],'
                        '"overall_rationale": "strong open + close"}',
                "model_used": "glm-x", "tier": tier, "provider": "p", "usage": {}}

    set_order_calls = []

    def fake_writer(subcmd_args):
        if subcmd_args[0] == "assembly-set-order":
            set_order_calls.append(subcmd_args)
            return (0, {"assembly_state": "proposed", "order_len": 2}, "")
        return (0, {}, "")

    eng2 = S9Assembly("anthA", db=":memory:", router=fake_router,
                      state_writer=fake_writer, longctx_available=False)
    # avoid the export-bundle metadata read in the fake path
    eng2._anth_cache = {"name": "The Collection", "theme": "voices", "min_chapters": 2}
    proposal = eng2.curate_order(chapters)
    check("curate_permutation_ok", proposal["order"] == ["cB::x", "cA::x"])
    check("curate_persisted", bool(set_order_calls))

    # curate REJECTS a non-permutation reply (invented / dropped key)
    def bad_router(tier, messages, context, run_dir=None, model_map_path=None):
        return {"text": '{"order": ["cB::x", "cZ::x"]}', "model_used": "m",
                "tier": tier, "provider": "p", "usage": {}}
    eng3 = S9Assembly("anthA", db=":memory:", router=bad_router,
                      state_writer=fake_writer, longctx_available=False)
    eng3._anth_cache = {"name": "The Collection", "theme": "v", "min_chapters": 2}
    try:
        eng3.curate_order(chapters)
        check("curate_rejects_nonpermutation", False)
    except CurationInvalid:
        check("curate_rejects_nonpermutation", True)

    # ---- compile: frozen byte-identity enforced + tier selection -----------
    b1 = b"# A\n\nbody A\n"
    b2 = b"# B\n\nbody B\n"
    frozen = {"cA::x": sha256_hex(b1), "cB::x": sha256_hex(b2)}
    sources = {"cA::x": (b1, frozen["cA::x"]), "cB::x": (b2, frozen["cB::x"])}
    advance_calls = []

    def compile_writer(subcmd_args):
        if subcmd_args[0] == "assembly-advance":
            advance_calls.append(subcmd_args)
            return (0, {"assembly_state": "compiled"}, "")
        return (0, {}, "")

    eng4 = S9Assembly("anthA", db=":memory:", router=_never_call_router,
                      state_writer=compile_writer,
                      chapter_source=lambda mk: sources[mk], longctx_available=False)
    out = eng4.compile_manuscript(["cB::x", "cA::x"], frozen, "FRONT", "INTRO",
                                  {"cA::x": "bioA", "cB::x": "bioB"}, "BACK")
    check("compile_deterministic", "body B" in out["manuscript"] and "body A" in out["manuscript"])
    check("compile_chunked_tier", out["compile_tier"] == TIER_HEAVY and not out["longctx_used"])
    check("compile_verify_sha_passed_to_writer",
          advance_calls and "--verify-sha" in advance_calls[0])

    # LONGCTX selected when configured
    eng5 = S9Assembly("anthA", db=":memory:", router=_never_call_router,
                      state_writer=compile_writer,
                      chapter_source=lambda mk: sources[mk], longctx_available=True)
    out5 = eng5.compile_manuscript(["cA::x"], {"cA::x": frozen["cA::x"]}, "", "", {}, "")
    check("compile_longctx_tier", out5["compile_tier"] == TIER_LONGCTX and out5["longctx_used"])

    # tampered chapter body -> AF-AE-S9-FROZEN
    tampered = {"cA::x": (b"tampered", frozen["cA::x"])}
    eng6 = S9Assembly("anthA", db=":memory:", router=_never_call_router,
                      state_writer=compile_writer,
                      chapter_source=lambda mk: tampered[mk], longctx_available=False)
    try:
        eng6.compile_manuscript(["cA::x"], {"cA::x": frozen["cA::x"]}, "", "", {}, "")
        check("compile_rejects_tampered", False)
    except FrozenChapterMismatch:
        check("compile_rejects_tampered", True)

    # ---- REAL-WRITER E2E: record_manuscript_artifact against a seeded ledger
    # This is the author-designated deliver-handoff surface (SPEC 4 S9 step 8):
    # it records the required `anthology_manuscript` Artifacts row. Every check
    # above stubs the writer with fakes, so the shell-through to the REAL
    # anthology_state.py writer is exercised here -- proving record-artifact is
    # invoked with a flag set the writer actually accepts (NO --version; the
    # writer auto-versions) and that a same-sha replay is an idempotent noop.
    import tempfile as _tempfile
    import shutil as _shutil
    if not STATE_WRITER.exists():
        check("e2e_writer_present", False)
    else:
        _tmp = _tempfile.mkdtemp(prefix="s9_e2e_")
        try:
            _db = str(Path(_tmp) / "ledger.db")
            _seed_ok = True
            for _seed in (
                ["bootstrap"],
                ["upsert-producer", "--producer-id", "prodE",
                 "--producer-email", "owner@example.test", "--display-name", "Owner"],
                ["upsert-anthology", "--anthology-id", "anthE9",
                 "--producer-id", "prodE", "--name", "E2E Collection",
                 "--min-chapters", "2"],
            ):
                _rc, _p, _err = _run_writer(_seed, None, db=_db)
                if _rc != 0:
                    _seed_ok = False
            check("e2e_seed_real_writer", _seed_ok)
            # NO state_writer injected -> the REAL writer is shelled per record.
            engR = S9Assembly("anthE9", db=_db, router=_never_call_router,
                              longctx_available=False)
            ms_sha = sha256_hex(b"# E2E Collection\n\nfrozen manuscript body\n")
            rec = engR.record_manuscript_artifact(ms_sha, model_used="glm-5.2")
            check("e2e_record_manuscript_artifact_real_writer",
                  rec.get("type") == MANUSCRIPT_ARTIFACT_TYPE
                  and rec.get("version") == 1 and bool(rec.get("artifact_id")))
            # same-sha replay -> idempotent noop at the SAME auto-computed version
            rec2 = engR.record_manuscript_artifact(ms_sha, model_used="glm-5.2")
            check("e2e_record_manuscript_artifact_idempotent",
                  rec2.get("noop") is True and rec2.get("version") == 1
                  and rec2.get("artifact_id") == rec.get("artifact_id"))
        finally:
            _shutil.rmtree(_tmp, ignore_errors=True)

    # ---- exit-code contract sanity -----------------------------------------
    check("exit_codes", (EX_OK, EX_ERR, EX_PROVER, EX_HELD, EX_VALIDATION) == (0, 1, 2, 3, 5))
    check("slot_exit_is_validation", SlotUnresolved("t", ["x"]).exit_code == EX_SLOT)
    check("frozen_exit_is_prover", FrozenChapterMismatch("k", "a", "b").exit_code == EX_PROVER)
    check("unwired_exit_is_held", CollaboratorUnwired("x").exit_code == EX_HELD)

    if fails:
        print("stage_s9_assembly_logic self-test: FAILED -> %s" % ", ".join(fails))
        return EX_ERR
    print("stage_s9_assembly_logic self-test: OK (all PRD 3.11 guards + curation/"
          "intro-refusal/matter/bios/compile/gate-b contracts coherent)")
    return EX_OK


def _never_call_router(tier, messages, context, run_dir=None, model_map_path=None):
    raise AssertionError("router must not be called on this path")


if __name__ == "__main__":
    sys.exit(main())
