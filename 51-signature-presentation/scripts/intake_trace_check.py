#!/usr/bin/env python3
# =============================================================================
# QC/HEALER TOOLING — AF-INTAKE-BATCH conversation-trace scanner.
# Deterministic, fail-closed-on-detection, stdlib-only. NO AI at runtime.
# =============================================================================
"""
intake_trace_check.py — gives the previously-unimplemented AF-INTAKE-BATCH
auto-fail (delivery.conversation_contract.af_on_violation in
51-signature-presentation/intake/sp-8-questions.json) a real, runnable
scanner over an exported conversation transcript.

DOCTRINE (Trevor's ruling -- one-question-at-a-time wins; see
sp-8-questions.json delivery.conversation_contract and
deck-intake-questions.json ask_if / one-question-per-turn machinery): the
CLIENT-FACING conversation must offer a quick-vs-in-depth CHOICE first (for a
signature-presentation intake) and then ask exactly ONE bank question per
assistant turn, waiting for the owner's answer before asking the next.

SCOPE (per sp-8-questions.json delivery.conversation_contract.af_on_violation
and the intake-conversation guard doctrine): this is a POST-HOC QC/Healer
scan of a conversation TRANSCRIPT EXPORT. It NEVER inspects, runs inside, or
gates build_deck.py / run_signature_deck.py / deck-intake-driver.py --
those are the deterministic, real-time RECORD-layer gates
(prove_sp_intake.py / AF-SP-8Q-SPLIT) and are unaffected by this file.

WHAT THIS DETECTS (AF-INTAKE-BATCH):
  1. BATCH-IN-TURN     — an assistant turn asks 2 or more distinct bank
                          questions (matched against the migrated question
                          banks: sp-8-questions.json's 8 Questions + frame
                          question, and deck-intake-questions.json's full
                          question set) before the owner answers any of them.
                          VERBATIM-PROMPT EXEMPTION: when one or more bank
                          prompts appear VERBATIM (normalized, whitespace-
                          insensitive substring) in the turn, the turn
                          resolves to exactly THOSE bank id(s) -- a single
                          verbatim bank prompt's own internal '?' sentences
                          (e.g. frame_selection has 2) are never re-matched
                          against OTHER bank questions by incidental keyword
                          overlap (e.g. "transformational teaching" also
                          appearing in sp:q5/sp:q6) and double-counted as a
                          multi-question batch. Two or more DIFFERENT bank
                          prompts appearing verbatim in the same turn still
                          correctly fires BATCH-IN-TURN.
  2. BATCH-BY-QMARKS   — a lighter heuristic fallback: an assistant turn with
                          2+ sentences ending in '?' that resolves ZERO known
                          bank-question matches (elif fires ONLY when
                          len(bank_ids_in_turn) == 0 -- a turn that is
                          legitimately one bank question, verbatim or via
                          keyword match, plus one incidental clarifying '?'
                          is not double-counted against the same bank id).
  3. NO-CHOICE-OPENER  — a signature-presentation transcript (detected by the
                          presence of >=2 of the 8-Question ids/keywords
                          anywhere in the transcript) whose FIRST assistant
                          turn does not offer the quick-vs-in-depth choice.
  4. BANNED-PHRASE     — the exact documented anti-pattern phrase ("give me
                          whatever you have got and I will get moving") is
                          present verbatim.

TRANSCRIPT INPUT FORMATS (auto-detected):
  * JSON list of turn objects: [{"role": "assistant"|"owner"|"user", "text": "..."}]
    (also accepts "speaker" for "role" and "content"/"message" for "text").
  * Plain text with speaker-prefixed lines, e.g.:
      ASSISTANT: <text>
      OWNER: <text>
    (case-insensitive; ASSISTANT/AGENT/AI/BOT = assistant, OWNER/USER/CLIENT
    /HUMAN = owner). Consecutive lines with no new prefix are appended to the
    current turn.

EXIT CODES:
  0  PASS     — no AF-INTAKE-BATCH violation found
  2  AUTOFAIL — one or more AF-INTAKE-BATCH violations (fail-closed)
  3  USAGE/IO — missing file, unreadable/unparseable transcript

USAGE:
  python3 intake_trace_check.py TRANSCRIPT [--json]
  python3 intake_trace_check.py --self-test
"""

import argparse
import json
import re
import sys
from pathlib import Path

EXIT_PASS = 0
EXIT_AUTOFAIL = 2
EXIT_USAGE = 3

AF_CODE = "AF-INTAKE-BATCH"
BANNED_PHRASE = "give me whatever you have got"

HERE = Path(__file__).resolve().parent
SP_SPEC_PATH = HERE.parent / "intake" / "sp-8-questions.json"
# 23-ai-workforce-blueprint is a SIBLING skill dir on an installed box and in
# the repo (mirrors the resolution pattern in deck-intake-driver.py).
DECK_QUESTIONS_CANDIDATES = [
    HERE.parent.parent / "23-ai-workforce-blueprint" / "templates" / "role-library"
    / "presentations" / "intake" / "deck-intake-questions.json",
]

_STOPWORDS = {
    "the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "is", "are",
    "you", "your", "this", "that", "what", "do", "does", "should", "any", "at",
    "with", "beyond", "want", "would", "like", "if", "before", "i", "it", "be",
}


# ---------------------------------------------------------------------------
# Question-bank loading (the same migrated banks the driver now enforces)
# ---------------------------------------------------------------------------
def _keywords(prompt: str) -> set:
    words = re.findall(r"[a-z']+", prompt.lower())
    return {w for w in words if len(w) > 3 and w not in _STOPWORDS}


def load_bank_questions(sp_spec_path=None, deck_questions_path=None) -> dict:
    """Returns {question_id: {"prompt":..., "keywords": set(...)}} across
    both migrated banks. Missing files are tolerated (empty dict for that
    bank) so this scanner degrades gracefully rather than crashing QC."""
    bank = {}

    sp_path = Path(sp_spec_path) if sp_spec_path else SP_SPEC_PATH
    if sp_path.exists():
        try:
            spec = json.loads(sp_path.read_text(encoding="utf-8"))
            for q in spec.get("questions") or []:
                qid, prompt = q.get("id"), q.get("prompt") or ""
                if qid and prompt:
                    bank[f"sp:{qid}"] = {"prompt": prompt, "keywords": _keywords(prompt)}
            frame_q = spec.get("frame_selection_question") or {}
            if frame_q.get("prompt"):
                bank["sp:frame_selection"] = {
                    "prompt": frame_q["prompt"], "keywords": _keywords(frame_q["prompt"])
                }
        except (json.JSONDecodeError, OSError):
            pass

    dq_path = Path(deck_questions_path) if deck_questions_path else None
    candidates = [dq_path] if dq_path else DECK_QUESTIONS_CANDIDATES
    for c in candidates:
        if c and c.exists():
            try:
                dq = json.loads(c.read_text(encoding="utf-8"))
                for q in dq.get("questions") or []:
                    qid, prompt = q.get("id"), q.get("prompt") or ""
                    if qid and prompt:
                        bank[f"deck:{qid}"] = {"prompt": prompt, "keywords": _keywords(prompt)}
            except (json.JSONDecodeError, OSError):
                pass
            break

    return bank


# ---------------------------------------------------------------------------
# Transcript parsing
# ---------------------------------------------------------------------------
ASSISTANT_ALIASES = {"assistant", "agent", "ai", "bot", "buddy", "brainstorming-buddy"}
OWNER_ALIASES = {"owner", "user", "client", "human", "trevor"}

_PREFIX_RE = re.compile(r"^\s*([A-Za-z][A-Za-z\- ]{1,30}):\s?(.*)$")


def parse_transcript(raw: str) -> list:
    """Returns a list of {"role": "assistant"|"owner"|"other", "text": str}."""
    stripped = raw.strip()
    if not stripped:
        return []

    # Try JSON first.
    if stripped[0] in "[{":
        try:
            data = json.loads(stripped)
        except json.JSONDecodeError:
            data = None
        if isinstance(data, list):
            turns = []
            for item in data:
                if not isinstance(item, dict):
                    continue
                role_raw = str(item.get("role") or item.get("speaker") or "").strip().lower()
                text = item.get("text") or item.get("content") or item.get("message") or ""
                role = _normalize_role(role_raw)
                if text:
                    turns.append({"role": role, "text": str(text)})
            return turns

    # Fall back to plain-text speaker-prefixed parsing.
    turns = []
    current = None
    for line in raw.splitlines():
        m = _PREFIX_RE.match(line)
        if m and _normalize_role(m.group(1).strip().lower()) != "other":
            if current:
                turns.append(current)
            current = {"role": _normalize_role(m.group(1).strip().lower()), "text": m.group(2)}
        elif current is not None:
            current["text"] += "\n" + line
    if current:
        turns.append(current)
    return turns


def _normalize_role(role_raw: str) -> str:
    r = role_raw.strip().lower()
    if r in ASSISTANT_ALIASES:
        return "assistant"
    if r in OWNER_ALIASES:
        return "owner"
    return "other"


# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------
def _sentences(text: str) -> list:
    # Split on sentence-ending punctuation, keep only those ending in '?'.
    parts = re.split(r"(?<=[.?!])\s+", text.strip())
    return [p.strip() for p in parts if p.strip().endswith("?")]


def _match_bank_ids(sentence: str, bank: dict) -> set:
    words = _keywords(sentence)
    matched = set()
    for qid, info in bank.items():
        kws = info["keywords"]
        if not kws:
            continue
        overlap = words & kws
        # require a meaningful overlap (>=2 shared keywords, or 1 if the
        # bank question itself only has 1-2 keywords total) to avoid
        # false-positives on short generic questions.
        threshold = 1 if len(kws) <= 2 else 2
        if len(overlap) >= threshold:
            matched.add(qid)
    return matched


def _normalize_for_match(text: str) -> str:
    """Lowercase + collapse whitespace, for verbatim substring comparisons
    that must not be tripped up by newlines/indentation differences between
    how a prompt is authored in the bank JSON and how it is relayed in a
    transcript."""
    return re.sub(r"\s+", " ", text.strip().lower())


def _verbatim_bank_ids(text: str, bank: dict) -> set:
    """Bank ids whose FULL prompt text appears verbatim (normalized,
    whitespace-insensitive substring) inside `text`. Used to exempt a turn
    that asks one (or more) canonical bank question(s) verbatim from the
    keyword-overlap sentence scan below -- a verbatim prompt's own internal
    '?' sentences must resolve to ITS bank id only, not whatever else it
    happens to keyword-overlap with."""
    norm_text = _normalize_for_match(text)
    if not norm_text:
        return set()
    found = set()
    for qid, info in bank.items():
        prompt = info.get("prompt") or ""
        norm_prompt = _normalize_for_match(prompt)
        if norm_prompt and norm_prompt in norm_text:
            found.add(qid)
    return found


def scan_transcript(turns: list, bank: dict) -> dict:
    violations = []

    for idx, turn in enumerate(turns):
        if turn["role"] != "assistant":
            continue
        text = turn["text"]
        lowered = text.lower()

        if BANNED_PHRASE in lowered:
            violations.append({
                "code": AF_CODE,
                "reason": "BANNED-PHRASE",
                "turn_index": idx,
                "detail": f"turn {idx} contains the banned batch anti-pattern phrase '{BANNED_PHRASE}'.",
            })

        qsentences = _sentences(text)

        # Verbatim-prompt exemption: when one or more canonical bank prompts
        # appear VERBATIM in this turn, resolve the turn to exactly those
        # bank id(s) and SKIP the per-sentence keyword-overlap qmark scan
        # entirely for it -- otherwise a single compliant bank question
        # whose own prompt text keyword-overlaps OTHER bank questions (e.g.
        # frame_selection's 2 internal '?' sentences overlapping sp:q5 /
        # sp:q6 on "transformational"/"teaching") gets miscounted as a
        # multi-question batch. Two or more DIFFERENT prompts verbatim in
        # the same turn is a real batch and still fires below.
        verbatim_ids = _verbatim_bank_ids(text, bank)

        if verbatim_ids:
            bank_ids_in_turn = verbatim_ids
        elif len(qsentences) < 2:
            continue
        else:
            bank_ids_in_turn = set()
            for s in qsentences:
                bank_ids_in_turn |= _match_bank_ids(s, bank)

        if len(bank_ids_in_turn) >= 2:
            violations.append({
                "code": AF_CODE,
                "reason": "BATCH-IN-TURN",
                "turn_index": idx,
                "matched_question_ids": sorted(bank_ids_in_turn),
                "detail": (
                    f"turn {idx} asks {len(bank_ids_in_turn)} distinct bank questions "
                    f"({sorted(bank_ids_in_turn)}) in a single assistant message."
                ),
            })
        elif len(bank_ids_in_turn) == 0 and len(qsentences) >= 2:
            violations.append({
                "code": AF_CODE,
                "reason": "BATCH-BY-QMARKS",
                "turn_index": idx,
                "question_count": len(qsentences),
                "detail": f"turn {idx} asks {len(qsentences)} separate questions in a single assistant message.",
            })

    # NO-CHOICE-OPENER: only meaningful for a transcript that is clearly a
    # signature-presentation intake (>=2 of the 8-Question/frame ids appear
    # anywhere across assistant turns).
    sp_ids_seen = set()
    for turn in turns:
        if turn["role"] != "assistant":
            continue
        sp_ids_seen |= {qid for qid in _match_bank_ids(turn["text"], bank) if qid.startswith("sp:")}
    if len(sp_ids_seen) >= 2:
        first_assistant = next((t for t in turns if t["role"] == "assistant"), None)
        if first_assistant is not None:
            opener = first_assistant["text"].lower()
            offers_choice = "quick" in opener and re.search(r"in.?depth|in depth", opener)
            if not offers_choice:
                violations.append({
                    "code": AF_CODE,
                    "reason": "NO-CHOICE-OPENER",
                    "turn_index": 0,
                    "detail": (
                        "signature-presentation transcript detected (>=2 of the 8 Questions "
                        "answered/asked) but the first assistant turn does not offer the "
                        "quick-vs-in-depth interview choice first."
                    ),
                })

    return {
        "af_code": AF_CODE,
        "pass": len(violations) == 0,
        "turns_scanned": len(turns),
        "assistant_turns": sum(1 for t in turns if t["role"] == "assistant"),
        "violations": violations,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="intake_trace_check.py",
        description="QC/Healer scan of a conversation transcript for AF-INTAKE-BATCH.",
    )
    parser.add_argument("transcript", nargs="?", help="Path to the transcript export (JSON or plain text).")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON only.")
    parser.add_argument("--sp-spec", help="Explicit path to sp-8-questions.json.")
    parser.add_argument("--deck-questions", help="Explicit path to deck-intake-questions.json.")
    parser.add_argument("--self-test", action="store_true", help="Run the offline self-test; exit 0 on pass.")
    args = parser.parse_args(argv)

    if args.self_test:
        return 0 if _self_test() else 1

    if not args.transcript:
        parser.error("transcript path is required (or pass --self-test)")

    tpath = Path(args.transcript)
    if not tpath.exists():
        print(json.dumps({"status": "error", "message": f"transcript not found: {tpath}"}))
        return EXIT_USAGE

    try:
        raw = tpath.read_text(encoding="utf-8")
    except OSError as exc:
        print(json.dumps({"status": "error", "message": f"cannot read transcript: {exc}"}))
        return EXIT_USAGE

    turns = parse_transcript(raw)
    if not turns:
        print(json.dumps({"status": "error", "message": "transcript parsed to zero turns (unparseable format)"}))
        return EXIT_USAGE

    bank = load_bank_questions(args.sp_spec, args.deck_questions)
    result = scan_transcript(turns, bank)

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        status = "PASS" if result["pass"] else "AUTOFAIL"
        print(f"[intake_trace_check] {status} -- {result['assistant_turns']} assistant turn(s) scanned, "
              f"{len(result['violations'])} violation(s)")
        for v in result["violations"]:
            print(f"  [{v['code']}/{v['reason']}] {v['detail']}")

    return EXIT_PASS if result["pass"] else EXIT_AUTOFAIL


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------
def _self_test() -> bool:
    print("[intake_trace_check] --self-test: starting...")
    ok = True
    bank = load_bank_questions()

    # Test 1: a clean, one-question-per-turn signature intake -> PASS.
    clean = [
        {"role": "assistant", "text": "Love this -- QUICK or IN-DEPTH, which would you like?"},
        {"role": "owner", "text": "quick"},
        {"role": "assistant", "text": "What is the title of your Signature Presentation?"},
        {"role": "owner", "text": "The Signature Talk"},
        {"role": "assistant", "text": "Any specific pain points to address in the avatar section?"},
        {"role": "owner", "text": "the overlooked mid-career expert"},
    ]
    res = scan_transcript(clean, bank)
    t1 = res["pass"]
    ok = ok and t1
    print(f"[self-test] Test 1 {'PASS' if t1 else 'FAIL'}: clean one-at-a-time transcript passes "
          f"(violations={res['violations']})")

    # Test 2: the exact banned batch anti-pattern (real 8Q batch dump) -> AUTOFAIL BATCH-IN-TURN.
    batch = [
        {"role": "assistant", "text": (
            "What is the title of your Signature Presentation? "
            "Do you want me to provide other possible titles before I start writing? "
            "Any specific pain points to address in the avatar section? "
            "What product(s) will you offer at the end?"
        )},
        {"role": "owner", "text": "give me whatever you have got and I will get moving"},
    ]
    res = scan_transcript(batch, bank)
    codes = {v["reason"] for v in res["violations"]}
    t2 = (not res["pass"]) and "BATCH-IN-TURN" in codes
    ok = ok and t2
    print(f"[self-test] Test 2 {'PASS' if t2 else 'FAIL'}: batched 8Q-style dump -> AF-INTAKE-BATCH/BATCH-IN-TURN "
          f"(violations={sorted(codes)})")

    # Test 3: the banned phrase itself, verbatim, in an ASSISTANT turn -> BANNED-PHRASE.
    banned = [
        {"role": "assistant", "text": "Just give me whatever you have got and I will get moving."},
    ]
    res = scan_transcript(banned, bank)
    codes = {v["reason"] for v in res["violations"]}
    t3 = (not res["pass"]) and "BANNED-PHRASE" in codes
    ok = ok and t3
    print(f"[self-test] Test 3 {'PASS' if t3 else 'FAIL'}: banned anti-pattern phrase detected "
          f"(violations={sorted(codes)})")

    # Test 4: generic 2-questions-in-one-turn (not bank-matched) -> BATCH-BY-QMARKS fallback.
    qmarks = [
        {"role": "assistant", "text": "How's your day going? Do you like tacos or pizza better?"},
    ]
    res = scan_transcript(qmarks, bank)
    codes = {v["reason"] for v in res["violations"]}
    t4 = (not res["pass"]) and "BATCH-BY-QMARKS" in codes
    ok = ok and t4
    print(f"[self-test] Test 4 {'PASS' if t4 else 'FAIL'}: generic 2-questions-in-one-turn fallback detection "
          f"(violations={sorted(codes)})")

    # Test 5: signature transcript that skips the choice-first opener -> NO-CHOICE-OPENER.
    no_choice = [
        {"role": "assistant", "text": "What is the title of your Signature Presentation?"},
        {"role": "owner", "text": "The Signature Talk"},
        {"role": "assistant", "text": "Any specific pain points to address in the avatar section?"},
        {"role": "owner", "text": "the overlooked mid-career expert"},
    ]
    res = scan_transcript(no_choice, bank)
    codes = {v["reason"] for v in res["violations"]}
    t5 = (not res["pass"]) and "NO-CHOICE-OPENER" in codes
    ok = ok and t5
    print(f"[self-test] Test 5 {'PASS' if t5 else 'FAIL'}: signature transcript w/o choice-first opener "
          f"(violations={sorted(codes)})")

    # Test 6: plain-text speaker-prefixed transcript parses correctly.
    plain = "ASSISTANT: What is the title of your Signature Presentation?\nOWNER: The Signature Talk\n"
    turns = parse_transcript(plain)
    t6 = len(turns) == 2 and turns[0]["role"] == "assistant" and turns[1]["role"] == "owner"
    ok = ok and t6
    print(f"[self-test] Test 6 {'PASS' if t6 else 'FAIL'}: plain-text speaker-prefixed transcript parses "
          f"({turns})")

    # Test 7: EVERY canonical bank prompt (all 8 SP questions + frame_selection
    # from sp-8-questions.json, plus every prompt in deck-intake-questions.json
    # if present) asked VERBATIM, alone, in its own assistant turn inside an
    # otherwise-compliant choice-first / one-question-per-turn conversation,
    # must PASS. This is the regression guard for the LIVE-CONFIRMED bug
    # (E2): the frame_selection prompt has 2 internal '?' sentences that
    # keyword-overlap sp:q5/sp:q6, so a single compliant question was
    # miscounted as a 3-question BATCH-IN-TURN ([sp:frame_selection, sp:q5,
    # sp:q6]) even though it was asked one-per-turn, verbatim, alone.
    opener = {"role": "assistant", "text": "Love this -- QUICK or IN-DEPTH, which would you like?"}
    opener_reply = {"role": "owner", "text": "quick"}
    t7 = True
    t7_failures = []
    if not bank:
        t7 = False
        t7_failures.append("bank loaded 0 questions -- sp-8-questions.json / "
                            "deck-intake-questions.json not found from this environment")
    for qid, info in sorted(bank.items()):
        prompt = info.get("prompt") or ""
        if not prompt:
            continue
        convo = [
            opener,
            opener_reply,
            {"role": "assistant", "text": prompt},
            {"role": "owner", "text": "answer"},
        ]
        res = scan_transcript(convo, bank)
        if not res["pass"]:
            t7 = False
            t7_failures.append((qid, res["violations"]))
    ok = ok and t7
    print(f"[self-test] Test 7 {'PASS' if t7 else 'FAIL'}: every canonical bank prompt "
          f"({len(bank)} loaded) passes when asked verbatim, one-per-turn "
          f"(failures={t7_failures})")

    print(f"[intake_trace_check] --self-test: {'ALL PASS' if ok else 'FAILED'}")
    return ok


if __name__ == "__main__":
    sys.exit(main())
