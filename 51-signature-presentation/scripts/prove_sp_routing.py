#!/usr/bin/env python3
# =============================================================================
# SKILL 51 — SIGNATURE PRESENTATION :: CLAIM / ROUTING GATE PROVER
# -----------------------------------------------------------------------------
# DETERMINISTIC, NO-AI, FAIL-CLOSED prover (Python stdlib only). This closes the
# single highest-severity skip of the audit: the entire SACRED signature method is
# opt-in via ONE self-declared field. The engine's SP gates all DEFER (no-op)
# unless intake.json records deck_type == "signature_presentation" (build_deck.py
# _sp_active). And prove_sp_intake only trips AF-SP-TYPE-MISMATCH when deck_type is
# PRESENT-and-different — a MISSING deck_type trips nothing. So a client asks for a
# "signature presentation", the authoring agent omits deck_type (or writes
# "webinar_deck"), every SP gate defers, and the deck builds through the generic
# path with NO 8-Questions-one-block gate, NO >=100-slide floor, NO <=2-case-study
# cap, NO Phase-3 no-pitch check — and still gets a green certificate.
#
# THE CLAIM SIDE OF THE GATE (what was missing):
#   If a run carries signature-presentation SIGNALS —
#     * working/copy/sp_intake.json is present, OR
#     * a Signature frame (rulebook|vault|quest|original) is set, OR
#     * a frame-selection question is present, OR
#     * the request/brief/topic names a "signature presentation" —
#   then intake.json's deck_type MUST equal "signature_presentation".
#   Otherwise: AF-SP-TYPE-UNDECLARED (fail-closed).
#
# Non-signature decks with NO signal PASS untouched — the defer switch stays
# correct for every other deck type; this gate only forces an SP run to DECLARE.
#
# Runs UNCONDITIONALLY in the engine (does NOT defer) — it is wired as the
# P-SP-CLAIM preflight (Phase 0.14) ahead of P-SP-INTAKE.
#
# AUTOFAIL CODES:
#   AF-SP-TYPE-UNDECLARED — SP signals present but deck_type not declared signature.
#   AF-SP-UNWIRED         — (--check-wiring) the engine is present but the SP claim/
#                           gate wrappers are not wired into build_deck.py.
#
# EXIT CODES:
#   0  PASS  — either a declared signature deck, or no SP signal at all.
#   2  AUTOFAIL — one or more AF-SP-* violations (fail-closed).
#   3  USAGE/IO — missing file, unreadable/invalid JSON (still fail-closed).
#
# USAGE:
#   python3 prove_sp_routing.py [intake.json | RUN_DIR] [--json]
#   python3 prove_sp_routing.py --run-dir RUN_DIR [--json]
#   python3 prove_sp_routing.py --check-wiring path/to/build_deck.py [--json]
#   python3 prove_sp_routing.py --self-test
# =============================================================================
"""Fail-closed deterministic claim/routing gate for the Signature Presentation method."""

import argparse
import json
import sys
from pathlib import Path

# ---- exit codes -------------------------------------------------------------
EXIT_PASS = 0
EXIT_AUTOFAIL = 2
EXIT_USAGE = 3

# ---- autofail codes ---------------------------------------------------------
AF_UNDECLARED = "AF-SP-TYPE-UNDECLARED"
AF_UNWIRED = "AF-SP-UNWIRED"

# ---- contract constants (kept in lockstep with prove_sp_intake) -------------
DECK_TYPE = "signature_presentation"
ALLOWED_FRAMES = ("rulebook", "vault", "quest", "original")
# The distinctive request phrases that name a signature presentation. Deliberately
# specific (never the bare word "signature") to avoid false positives on decks that
# merely mention a signature/logo.
SP_KEYWORDS = ("signature presentation", "signature-presentation", "signature deck")

# The claim/gate wrappers the engine (Skill 23 build_deck.py) must carry + register.
#
# A10 / T0-12 — `_chk_sp_intake_trace` joins the required set. SKILL.md declares that
# every rule is machine-enforced by a fail-closed prover and never advisory, and then
# declared the intake-trace checker advisory and non-gating. The rule that defines this
# skill's value — choice-first, one question per turn — was the one rule nothing
# enforced: an eight-question batched interaction that then produced a structurally
# valid intake record passed every preflight and reached a signed certificate, because
# the run supplied its own intake RECORD as the only evidence of how the intake was
# CONDUCTED. Listing the wrapper here makes --check-wiring refuse an engine that does
# not carry the gate, so the enforcement cannot silently go missing again.
WIRE_SYMBOLS = ("_chk_sp_claim", "_chk_sp_intake", "_chk_sp_structure", "_chk_sp_no_pitch",
                "_chk_sp_intake_trace")


# ---- small helpers ----------------------------------------------------------
def _nonempty_str(value):
    return isinstance(value, str) and value.strip() != ""


def _read_json_safe(path: Path):
    try:
        obj = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return obj if isinstance(obj, dict) else None


def _resolve_deck_type(obj):
    if isinstance(obj, dict) and isinstance(obj.get("deck_type"), str):
        return obj["deck_type"].strip().lower()
    return None


def _resolve_frame(obj):
    """Resolve a SELECTED frame value (lowercased) from any supported shape —
    mirrors prove_sp_intake._resolve_frame (the subset that indicates an SP run)."""
    if not isinstance(obj, dict):
        return None
    if _nonempty_str(obj.get("signature_frame")):
        return obj["signature_frame"].strip().lower()
    answers = obj.get("answers")
    if isinstance(answers, dict):
        for key in ("signature_frame", "frame", "frame_selection"):
            if _nonempty_str(answers.get(key)):
                return answers[key].strip().lower()
    fsq = obj.get("frame_selection_question")
    if isinstance(fsq, dict):
        for key in ("selected", "value", "answer", "chosen"):
            if _nonempty_str(fsq.get(key)):
                return fsq[key].strip().lower()
    return None


def _gather_request_text(*objs):
    parts = []
    for obj in objs:
        if not isinstance(obj, dict):
            continue
        for k in ("request", "brief", "topic", "title", "presentation_topic",
                  "presentation_title", "deck_topic", "ask", "goal", "description"):
            v = obj.get(k)
            if isinstance(v, str):
                parts.append(v)
        answers = obj.get("answers")
        if isinstance(answers, dict):
            for v in answers.values():
                if isinstance(v, str):
                    parts.append(v)
    return " ".join(parts)


# ---- signal detection + core evaluation -------------------------------------
def detect_signals(intake, sp_intake=None, sp_intake_present=False, request_text=""):
    """Return an ordered list of human-readable SP signals detected on the run."""
    signals = []
    if sp_intake_present:
        signals.append("an sp_intake.json is present in the run dir")
    for label, obj in (("intake.json", intake), ("sp_intake.json", sp_intake)):
        if not isinstance(obj, dict):
            continue
        fr = _resolve_frame(obj)
        if fr in ALLOWED_FRAMES:
            signals.append("a Signature frame (%s) is set in %s" % (fr, label))
        if isinstance(obj.get("frame_selection_question"), dict):
            signals.append("a frame-selection question is present in %s" % label)
    text = (request_text or "").lower()
    for kw in SP_KEYWORDS:
        if kw in text:
            signals.append("the request names a %r" % kw)
            break
    seen, out = set(), []
    for s in signals:
        if s not in seen:
            seen.add(s)
            out.append(s)
    return out


def evaluate(intake, *, sp_intake=None, sp_intake_present=False, request_text=""):
    """Return a list of (AF_CODE, message) failures. Empty list == PASS.

    `declared` is read STRICTLY from intake.json's deck_type — the same field the
    engine's _sp_active switch reads — so declaring signature only in sp_intake.json
    (which the engine does not consult for the switch) does NOT clear this gate."""
    declared = _resolve_deck_type(intake) == DECK_TYPE
    # request text can arrive explicitly (engine/CLI gather) OR live inside the
    # intake/sp_intake records themselves — cover both.
    derived = _gather_request_text(intake if isinstance(intake, dict) else {},
                                   sp_intake if isinstance(sp_intake, dict) else {})
    text = " ".join(t for t in (request_text, derived) if t)
    signals = detect_signals(intake, sp_intake, sp_intake_present, text)
    if signals and not declared:
        dt = _resolve_deck_type(intake)
        return [(AF_UNDECLARED,
                 "signature-presentation signals present (%s) but intake.json deck_type is %r "
                 "(must be %r) — a signature presentation cannot be built through the generic "
                 "path by omitting or mis-declaring deck_type"
                 % ("; ".join(signals), dt, DECK_TYPE))]
    return []


def evaluate_run_dir(run_dir):
    """Engine entrypoint: read the run dir's intake + sp_intake and evaluate the
    claim gate. Reads the SAME intake.json the engine's _sp_active switch reads."""
    run_dir = Path(run_dir)
    intake = _read_json_safe(run_dir / "working" / "copy" / "intake.json")
    if intake is None:
        intake = _read_json_safe(run_dir / "intake.json")
    if intake is None:
        intake = _read_json_safe(run_dir / "working" / "intake.json")
    sp_path = run_dir / "working" / "copy" / "sp_intake.json"
    sp_intake = _read_json_safe(sp_path)
    request_text = _gather_request_text(intake or {}, sp_intake or {})
    return evaluate(intake or {}, sp_intake=sp_intake,
                    sp_intake_present=sp_path.is_file(), request_text=request_text)


def decide_exit(failures):
    return EXIT_PASS if not failures else EXIT_AUTOFAIL


# ---- wire-presence check ----------------------------------------------------
def check_wiring(engine_path):
    """Assert the engine build_deck.py DEFINES + REGISTERS the four SP wrappers
    (the claim gate + the three sacred gates). Returns [(code, msg)]; [] == wired.
    Only meaningful when the engine file exists (verify.sh gates on that)."""
    p = Path(engine_path)
    if not p.is_file():
        return [("USAGE", "engine build_deck.py not found: %s" % p)]
    try:
        src = p.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return [("USAGE", "cannot read engine: %s" % exc)]
    fails = []
    for sym in WIRE_SYMBOLS:
        if ("def %s(" % sym) not in src:
            fails.append((AF_UNWIRED, "engine build_deck.py has no %s definition" % sym))
        # registration in PREFLIGHT_REQUIRED: the symbol referenced as a checker
        # (the 4th tuple element ends "<symbol>)").
        if ("%s)" % sym) not in src:
            fails.append((AF_UNWIRED,
                          "%s is defined but not registered in PREFLIGHT_REQUIRED" % sym))
    return fails


# ---- runner -----------------------------------------------------------------
def prove(path, as_json=False):
    p = Path(path)
    if p.is_dir():
        failures = evaluate_run_dir(p)
        return _emit(str(p), failures, as_json)
    intake = _read_json_safe(p)
    if intake is None:
        return _emit(str(p), [("USAGE", "intake file not found or not a JSON object: %s" % p)], as_json)
    sp_path = p.parent / "sp_intake.json"
    sp_intake = _read_json_safe(sp_path)
    request_text = _gather_request_text(intake, sp_intake or {})
    failures = evaluate(intake, sp_intake=sp_intake,
                        sp_intake_present=sp_path.is_file(), request_text=request_text)
    return _emit(str(p), failures, as_json)


def _emit(source, failures, as_json):
    usage = any(c == "USAGE" for c, _ in failures)
    if as_json:
        print(json.dumps({
            "gate": "signature-presentation-claim-routing",
            "source": source,
            "pass": not failures,
            "failures": [{"code": c, "message": m} for c, m in failures],
        }, indent=2))
    else:
        print("== Signature Presentation :: claim / routing gate ==")
        print("source: %s" % source)
        if not failures:
            print("RESULT: PASS — declared signature deck, or no SP signal (generic path allowed).")
        else:
            print("RESULT: FAIL (fail-closed) — %d violation(s):" % len(failures))
            for code, msg in failures:
                print("  [%s] %s" % (code, msg))
    if usage:
        return EXIT_USAGE
    return decide_exit(failures)


# ---- self-test --------------------------------------------------------------
def self_test():
    ok = True

    def check_pass(name, **kw):
        nonlocal ok
        intake = kw.pop("intake")
        failures = evaluate(intake, **kw)
        good = (not failures) and decide_exit(failures) == EXIT_PASS
        ok = ok and good
        print("  [%s] VALID %-26s -> exit %d %s"
              % ("PASS" if good else "MISS", name, decide_exit(failures),
                 "" if good else ("(unexpected: %r)" % failures)))

    def check_fail(name, expect_code, **kw):
        nonlocal ok
        intake = kw.pop("intake")
        failures = evaluate(intake, **kw)
        codes = [c for c, _ in failures]
        good = bool(failures) and decide_exit(failures) != EXIT_PASS and expect_code in codes
        ok = ok and good
        print("  [%s] VIOLATION %-22s -> exit %d codes=%s (want %s)"
              % ("PASS" if good else "MISS", name, decide_exit(failures), codes, expect_code))

    declared = {"deck_type": DECK_TYPE, "signature_frame": "rulebook"}
    generic = {"deck_type": "webinar_deck", "topic": "quarterly ops review"}

    print("== self-test: VALID fixtures (must PASS / exit 0) ==")
    check_pass("declared-signature", intake=declared, sp_intake_present=True)
    check_pass("generic-deck-no-signal", intake=generic)
    check_pass("empty-intake-no-signal", intake={})

    print("== self-test: VIOLATION fixtures (must FAIL / exit nonzero) ==")
    # sp_intake present but deck_type omitted
    check_fail("sp-intake-undeclared", AF_UNDECLARED, intake={}, sp_intake_present=True)
    # a signature frame set but deck_type omitted
    check_fail("frame-set-undeclared", AF_UNDECLARED, intake={"signature_frame": "quest"})
    # frame-selection question present but deck_type omitted
    check_fail("frame-question-undeclared", AF_UNDECLARED,
               intake={"frame_selection_question": {"selected": "vault"}})
    # request names a signature presentation but deck_type omitted
    check_fail("request-keyword-undeclared", AF_UNDECLARED,
               intake={"request": "please build me a Signature Presentation for my program"})
    # mis-declared as a webinar deck while carrying an sp_intake artifact
    check_fail("misdeclared-with-sp-intake", AF_UNDECLARED,
               intake={"deck_type": "webinar_deck"}, sp_intake_present=True)

    print("== self-test: %s ==" % ("ALL ASSERTIONS PASSED" if ok else "FAILED"))
    return 0 if ok else 1


# ---- main -------------------------------------------------------------------
def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Fail-closed claim/routing gate for the Signature Presentation method (Skill 51).")
    ap.add_argument("path", nargs="?", default=None,
                    help="an intake.json OR a run dir (contains working/copy/).")
    ap.add_argument("--run-dir", dest="run_dir", default=None, help="the run dir (contains working/copy/).")
    ap.add_argument("--check-wiring", dest="check_wiring", default=None,
                    help="assert the engine build_deck.py wires the SP claim/gate wrappers.")
    ap.add_argument("--json", action="store_true", help="emit machine-readable JSON.")
    ap.add_argument("--self-test", dest="self_test", action="store_true",
                    help="run built-in VALID + VIOLATION fixtures and exit.")
    args = ap.parse_args(argv)

    if args.self_test:
        return self_test()
    if args.check_wiring:
        failures = check_wiring(args.check_wiring)
        return _emit(args.check_wiring, failures, args.json)
    target = args.run_dir or args.path
    if not target:
        ap.error("provide an intake.json / run dir, or --run-dir, --check-wiring, or --self-test")
    return prove(target, as_json=args.json)


if __name__ == "__main__":
    sys.exit(main())
