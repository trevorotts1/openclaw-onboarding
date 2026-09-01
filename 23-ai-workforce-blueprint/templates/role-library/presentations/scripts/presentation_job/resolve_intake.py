#!/usr/bin/env python3
"""presentation_job/resolve_intake.py -- the ONE place a shell caller turns an
intake_ledger.json into the engine's --new intake JSON.

fix/deck-type-routing-bypass
-----------------------------
Two callers (presentation-canonical-entry.sh and presentation-intake-poll.sh)
each used to build this JSON independently: one had its own broken deck-type
normalizer (a "legal" set that accidentally included the two values needing
translation, so the alias remap never fired), the other did no normalization
at all and silently defaulted to from_scratch. This script replaces BOTH
inline copies. There is now exactly one implementation, imported by both
callers, and it shares its deck-type vocabulary with the engine and the
launcher via vocab.py.

It also closes the second reported hole: the old inline `python3 -c "..."`
blocks string-interpolated ledger-derived values (client name, chat id)
directly into python SOURCE via bash `'$VAR'` substitution. A client name
containing a single quote (e.g. "O'Brien Group") broke the literal; the
SyntaxError was then swallowed by `2>/dev/null || true`, so the intake JSON
was silently never written and the caller fell through to the fallback path.
Untrusted content never becomes source text here: the ledger path is the
only thing passed on argv, its content is read with json.load(), and the
output is written with json.dump() -- ledger values are DATA the whole way
through, never formatted into code.

USAGE
  python3 resolve_intake.py --ledger LEDGER_JSON --out INTAKE_JSON \\
      --source canonical-entry|intake-poll

EXIT CODES
  0  intake JSON written to --out
  2  usage error (missing/unreadable --ledger)
  3  AF-DECK-TYPE-UNKNOWN -- the ledger's presentation_type/deck_type value is
     neither canonical nor a known alias (see vocab.py). Nothing is written
     to --out. The caller MUST treat this as a loud, blocking failure --
     never fall back to a legacy runner and report success.
  4  AF-REQUESTER-MISSING -- no requester_chat_id could be resolved from
     either working/copy/intake.json or the ledger's own top-level fields.
     Nothing is written to --out. FAULT-04 fix: this used to emit an intake
     with `requester: {"chat_id": "", ...}` -- a known-invalid artifact that
     presentation_job.py --new was guaranteed to reject one step later (fix
     F1's own hard-fail). Failing here, loudly, at the point the field is
     actually missing, replaces that guaranteed-downstream-rejection with a
     message that names the missing field and where it should have come
     from -- never a silent handoff of an artifact the next gate will bounce.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Optional

if __package__ in (None, ""):
    # Allow `python3 resolve_intake.py` (no -m) by ensuring the package
    # parent is importable, mirroring the other scripts in this directory.
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from presentation_job.vocab import (  # type: ignore
        normalize_presentation_type, UnknownPresentationType,
    )
else:
    from .vocab import normalize_presentation_type, UnknownPresentationType


class MissingRequester(RuntimeError):
    """Raised by resolve() when no source (working/copy/intake.json,
    the ledger's own top-level fields) carries a non-empty requester chat id.

    FAULT-04 fix: this replaces the old silent behaviour of emitting
    `requester: {"chat_id": "", ...}` -- an artifact presentation_job.py
    --new was guaranteed to hard-fail on one step later (fix F1). Callers
    MUST treat this as a loud, blocking failure, exactly like
    UnknownPresentationType -- never catch it to fabricate a chat_id or to
    write an intake anyway. See main()'s EXIT CODES doc (exit 4)."""

class UnknownIntakeDepth(ValueError):
    """FIX 36(3): an explicit --intake-depth / PRESENTATION_INTAKE_DEPTH value
    outside the QUICK|IN-DEPTH vocabulary. Loud, blocking, exit 5 — never
    silently mapped to QUICK. Distinct from run-mode --mode (Ultra|Standard|
    Economy), which is a different axis and is never accepted here."""


# The four upsell fields intake/upsell-questions.json's storeTarget maps
# under pre_presentation_capture (WANT_SALES_CHECKOUT / its declined-reason
# waiver, WANT_VSL_PAGE / its declined-reason waiver). Each entry is
# (canonical pre_presentation_capture field name, the question's own `id` in
# upsell-questions.json -- the ledger entries[] key the real driver writes).
_UPSELL_FIELDS = (
    ("WANT_SALES_CHECKOUT", "want_sales_checkout"),
    ("SALES_CHECKOUT_DECLINED_REASON", "sales_checkout_declined_reason"),
    ("WANT_VSL_PAGE", "want_vsl_page"),
    ("VSL_PAGE_DECLINED_REASON", "vsl_page_declined_reason"),
)


def _entry_raw_value(entries: dict, key: str) -> Optional[str]:
    """Read one intake_ledger.json entry's answer, tolerating every REAL
    driver's shape -- never inventing a value.

    Every sanctioned writer nests the answer under entries[key]; reading it
    at the ledger's TOP level (the pre-fix behavior) always returns None
    against a real ledger -- that was the whole bug. But the two sanctioned
    deck-intake-driver.py copies disagree on the entry's own inner key:

      - 23-ai-workforce-blueprint/scripts/deck-intake-driver.py (this repo's
        top-level dev copy) writes entries[qid] = {"answer": raw,
        "normalized": canonical, ...} -- "normalized" is the canonicalized
        form and is preferred (mirrors _apply_type_picker_derivation's own
        pt_entry.get("normalized", pt_entry.get("answer")) precedence in
        that same file).
      - .../templates/role-library/presentations/scripts/deck-intake-
        driver.py (the copy a deployed client box's intake_bridge.py parent
        walk actually resolves to) writes entries[qid] = {"value": raw}
        instead.

    Tries every recognized sub-key; also tolerates a bare-string entry (some
    non-driver writer could plausibly store one). Returns None -- never a
    fabricated default -- if the entry is absent or every recognized
    sub-field is empty.
    """
    entry = entries.get(key)
    if isinstance(entry, dict):
        for subkey in ("normalized", "value", "answer"):
            val = entry.get(subkey)
            if val:
                return val
        return None
    if isinstance(entry, str) and entry:
        return entry
    return None


def _read_json_dict(path: Path) -> dict:
    """Read a JSON file, tolerating absence/corruption -- returns {} rather
    than raising. Shared by the ledger read and the intake.json sibling read
    below; never a source of a hard crash on a merely-missing file."""
    if not path.is_file():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as fh:
            loaded = json.load(fh)
        return loaded if isinstance(loaded, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


# ---------------------------------------------------------------------------
# FIX 36(3) — intake-depth vocabulary (QUICK vs IN-DEPTH).
#
# The interview_depth question (deck-intake-questions.json Q9, subfield
# standard_mode) records the client's chosen intake depth. Its vocabulary is
# deliberately DIFFERENT from (and must never collide with) FIX 38's run-mode
# vocabulary (--mode / PRESENTATION_MODE = Ultra|Standard|Economy only):
#
#   intake depth (this file)  : --intake-depth quick|in-depth, env
#                               PRESENTATION_INTAKE_DEPTH, ledger field
#                               interview_depth / STANDARD_MODE
#   run mode (FIX 38/11)      : --mode Ultra|Standard|Economy, env
#                               PRESENTATION_MODE
#
# Never reuse --mode for both meanings. Resolution order, never fabricating:
#   1. explicit --intake-depth CLI value (canonical entry passes what the
#      operator/caller stated),
#   2. env PRESENTATION_INTAKE_DEPTH,
#   3. the ledger's interview_depth entry (the real driver writes the
#      client's QUICK/IN-DEPTH answer there),
#   4. working/copy/intake.json's standard_mode / interview_depth fields
#      (upstream dispatch steps stamp the derived value there),
#   5. the question's own schema default: QUICK.
# The resolved value is emitted as intake["standard_mode"] — the subfield
# name the engine's standard_mode contract already speaks.
INTAKE_DEPTH_ENV = "PRESENTATION_INTAKE_DEPTH"
INTAKE_DEPTH_LEGAL = ("quick", "in-depth")
_INTAKE_DEPTH_LEDGER_KEYS = ("interview_depth", "standard_mode", "STANDARD_MODE")

def _resolve_intake_depth(explicit: Optional[str], entries: dict,
                          intake_copy: dict) -> str:
    """Return the deck's intake depth ('QUICK' or 'IN-DEPTH'); never None.

    Every source is normalized case-insensitively (a ledger value of
    'in depth'/'In-Depth'/'IN DEPTH' is the same IN-DEPTH answer); a value
    that is PRESENT but not in the vocabulary is a loud AF-INTAKE-DEPTH-
    INVALID refusal (via UnknownIntakeDepth), never a silent QUICK fallback
    -- this is what keeps run-mode vocabulary (ultra|standard|economy) from
    ever leaking into the intake-depth axis."""
    def _canon(val) -> Optional[str]:
        if val is None:
            return None
        s = str(val).strip().lower().replace("_", "-").replace(" ", "-")
        if s == "indepth":
            s = "in-depth"
        return s if s in INTAKE_DEPTH_LEGAL else None

    def _legal_or_raise(stage: str, val) -> Optional[str]:
        canon = _canon(val)
        if val is not None and canon is None:
            raise UnknownIntakeDepth(
                f"intake depth {stage} {val!r} is not a legal depth; the "
                f"vocabulary is exactly quick|in-depth (env {INTAKE_DEPTH_ENV}). "
                "Run-mode --mode (Ultra|Standard|Economy) is a DIFFERENT axis "
                "and is never accepted here.")
        return canon

    for cand in (
        _legal_or_raise("--intake-depth", explicit),
        _legal_or_raise(f"env {INTAKE_DEPTH_ENV}", os.environ.get(INTAKE_DEPTH_ENV)),
        _legal_or_raise(
            "ledger interview_depth",
            _entry_raw_value(entries, _INTAKE_DEPTH_LEDGER_KEYS[0])
            or _entry_raw_value(entries, _INTAKE_DEPTH_LEDGER_KEYS[1])
            or _entry_raw_value(entries, _INTAKE_DEPTH_LEDGER_KEYS[2])),
        _legal_or_raise("intake.json standard_mode",
                        intake_copy.get("standard_mode")),
        _legal_or_raise("intake.json interview_depth",
                        intake_copy.get("interview_depth")),
        _legal_or_raise(
            "intake.json pre_presentation_capture.standard_mode",
            (intake_copy.get("pre_presentation_capture") or {})
            .get("standard_mode") if isinstance(
                intake_copy.get("pre_presentation_capture"), dict) else None),
        "quick",  # the question schema's documented default
    ):
        if cand:
            return "IN-DEPTH" if cand == "in-depth" else "QUICK"
    # Unreachable: the tuple always ends with the schema default. Kept only so
    # a future edit cannot fall through to None.
    raise ValueError("intake-depth resolution fell through -- never happens")

def _resolve_upsell_capture(entries: dict, intake_copy: dict) -> dict:
    """FAULT-05 fix -- resolve the client's upsell answers (sales+checkout
    page, VSL page, and their verbatim declined-reason waivers) into the
    canonical pre_presentation_capture.* shape, tolerating every real shape
    they can be found in, and NEVER fabricating a value (in particular,
    never defaulting WANT_SALES_CHECKOUT to its schema "yes" here -- that
    default belongs to the interview layer that asks the question; this
    function only ever carries forward an answer that was actually
    captured somewhere on disk).

    Checked, most-authoritative first (mirrors the client/chat_id precedent
    a few lines below: working/copy/intake.json is "per-deck and durable" --
    upstream steps can stamp it after the interview -- so it outranks the
    raw ledger):
      1. working/copy/intake.json's NESTED `pre_presentation_capture.<field>`
         -- the documented contract (intake_writer.py / the app-bridge path).
      2. working/copy/intake.json's FLAT top-level `<field>` -- the real
         chat-driver shape (deck-intake-driver.py's cmd_complete() writes
         upsell answers flat, with no pre_presentation_capture wrapper at
         all -- verified against the live Wave E intake.json).
      3. The ledger's own entries[], via _entry_raw_value(), tried under
         both the question's own lowercase `id` (what every real driver
         copy actually uses as the entries[] key) and the UPPERCASE
         storeOn field name (some ledgers -- verified against the live
         Wave E ledger -- carry both keys pointing at the identical value;
         tolerated, never required).

    Returns only the fields that actually resolved to a non-empty value --
    an unanswered/unasked question is simply absent, never stamped with an
    empty string or a guessed default. A "no" answer's declined-reason
    value is returned completely unmodified (no .strip()/.lower()) so it
    survives verbatim, exactly as the client typed it -- silence is never
    consent, and neither is this function's own rewording.
    """
    nested = intake_copy.get("pre_presentation_capture")
    if not isinstance(nested, dict):
        nested = {}

    capture: dict = {}
    for field, qid in _UPSELL_FIELDS:
        val = nested.get(field)
        if not val:
            val = intake_copy.get(field)
        if not val:
            val = _entry_raw_value(entries, qid) or _entry_raw_value(entries, field)
        if val:
            capture[field] = val
    return capture


def resolve(ledger_path: Path, source: str,
            intake_depth: Optional[str] = None) -> dict:
    """Read the intake ledger and return the engine's --new intake dict.

    ``intake_depth`` is FIX 36(3)'s explicit --intake-depth value from the
    caller (None = not stated; env/ledger/schema-default then decide).
    Raises UnknownPresentationType if the ledger's presentation_type/deck_type
    value does not resolve through vocab.normalize_presentation_type(). Never
    defaults it -- an absent or garbled value is exactly the case that must
    fail loudly, not build a deck of the wrong type.
    """
    ledger = _read_json_dict(ledger_path)

    entries = ledger.get("entries")
    if not isinstance(entries, dict):
        entries = {}

    # fix/deck-type-routing-bypass (adversarial-verifier follow-up): the
    # REAL deck-intake-driver.py (either sanctioned copy) nests the answer
    # under entries.presentation_type -- never at the ledger's top level.
    # Reading only ledger.get("presentation_type")/ledger.get("deck_type")
    # (the pre-fix code below, kept ONLY as a defensive fallback for a
    # hand-authored/legacy flat ledger) returned None against every real
    # ledger and hard-failed the door for every legitimate intake, including
    # from_scratch. See _entry_raw_value() above for the two real nested
    # shapes this now reads.
    raw_ptype = (
        _entry_raw_value(entries, "presentation_type")
        or _entry_raw_value(entries, "deck_type")
        or ledger.get("presentation_type")
        or ledger.get("deck_type")
    )
    ptype = normalize_presentation_type(raw_ptype)  # raises UnknownPresentationType

    # requester_chat_id / client_name -- follow-up to fix/deck-type-routing-
    # bypass. presentation_job.py --new hard-fails a job with no requester
    # (fix F1: a deck with nobody to report to must not start). The pre-fix
    # read here was `ledger.get("requester_chat_id")` / `ledger.get(
    # "client_name")` -- the ledger's TOP level, same mistake class as the
    # presentation_type bug above. Verified empirically by running BOTH
    # sanctioned deck-intake-driver.py copies end-to-end (55-question real
    # intake, from_scratch and signature/existing_content) and dumping every
    # artifact: NEITHER copy's 55-question schema contains a question about
    # requester identity, so neither ever writes requester_chat_id/client_name
    # anywhere in intake_ledger.json -- not top level, not nested in entries.
    # That top-level ledger read was therefore dead code against every real
    # driver ledger, same as the presentation_type bug.
    #
    # cc_board.py's OWN precedent (resolve_requester(), the function CC-board
    # registration and build_deck.py's run-begin ingest both already call for
    # this exact purpose) reads working/copy/intake.json's FLAT
    # requester_chat_id / requester_channel instead -- "per-deck and durable"
    # per its own docstring. That file is a sibling of the ledger under the
    # same run_dir (working/copy/intake.json vs working/interview/
    # intake_ledger.json) and, unlike the ledger, is read-modify-written by
    # the driver (derive_legacy_fields() merges on top of whatever is already
    # there) -- so a requester_chat_id/client_name stamped into it by an
    # upstream dispatch step (CC board ingest, a Telegram/box trigger,
    # run_signature_deck.py) survives the interview untouched, where a
    # ledger-only read would never see it. This resolver now reads THAT file
    # first, matching the established precedent, with the ledger's flat
    # top-level kept only as a legacy/hand-authored fallback.
    #
    # FAULT-04 fix (orchestrator-verified against the live Wave E run): a run
    # with genuinely nothing stamped anywhere (verified: a completely
    # untouched real driver run, no upstream step involved) used to resolve
    # to an empty chat_id here and hand that forward as if it were a valid
    # artifact. It is NOT one: presentation_job.py --new hard-fails a job
    # with no requester.chat_id (fix F1 -- a deck with nobody to report to
    # must not start), so every such intake was GUARANTEED to be rejected by
    # the very next step, having already told its own caller "resolved ...
    # -> $OUT" as if it had succeeded. This function still never fabricates
    # a chat_id -- that has not changed -- but it now refuses to hand
    # forward the empty-string case at all: see the raise below. A resolve
    # that cannot find a real requester now fails HERE, loudly, naming
    # exactly what is missing and where it should come from, instead of
    # silently deferring that same failure one step downstream.
    intake_copy_path = ledger_path.parent.parent / "copy" / "intake.json"
    intake_copy = _read_json_dict(intake_copy_path)

    client = str(
        intake_copy.get("client_name")
        or ledger.get("client_name") or ledger.get("client")
        or ledger.get("requester_name") or "operator"
    )
    chat_id = str(
        intake_copy.get("requester_chat_id")
        or ledger.get("requester_chat_id") or ledger.get("chat_id") or ""
    )
    channel = str(intake_copy.get("requester_channel") or "")

    if not chat_id:
        raise MissingRequester(
            "no resolvable requester.chat_id for this run. Checked "
            f"'requester_chat_id' in {intake_copy_path} (per-deck and "
            "durable -- the field an upstream dispatch step such as CC "
            "board ingest, a Telegram/box trigger, or run_signature_deck.py "
            "is expected to stamp there) and the ledger's own top-level "
            f"'requester_chat_id'/'chat_id' fields in {ledger_path}; none "
            "carried a value. presentation_job.py --new hard-fails a job "
            "with no requester (fix F1) -- a deck with nobody to report "
            "progress or completion to must not start. This resolver will "
            "never invent a chat_id: stamp one into "
            f"{intake_copy_path}'s requester_chat_id (+ requester_channel) "
            "at the source that owns this run, then re-run resolve_intake.py."
        )

    requester = {"chat_id": chat_id, "client_name": client}
    if channel:
        requester["channel"] = channel

    intake = {
        "presentation_type": ptype,
        "requester": requester,
        "client": client,
        # deck_type mirrors presentation_type here for the engine's own intake
        # JSON; it is a DIFFERENT axis from the SOP-governed working/copy/
        # intake.json deck_type field derive_legacy_fields() writes
        # (deck-intake-driver.py) and is not read by the SP claim gate.
        "deck_type": ptype,
        "source": source,
    }
    if ptype == "signature":
        # signature_source -- the sibling of the presentation_type bug this
        # whole file exists to fix, in its QUIET form: it has the identical
        # nested-vs-flat mismatch (the real drivers nest the answer under
        # entries.signature_source, same two shapes as presentation_type --
        # verified empirically against both real drivers' signature/
        # existing_content ledgers) but the pre-fix read here,
        # `ledger.get("signature_source", "from_scratch")`, is a TOP-level
        # ledger read that never matches either real shape -- so it silently
        # fell through to the baked-in "from_scratch" default on EVERY real
        # signature run, regardless of what the client actually answered.
        # No exception, no log line -- a wrong value accepted without
        # complaint. Unlike presentation_type/requester, this axis only
        # feeds creation_mode (from_scratch vs content_general), never
        # deck_type/routing (derive_legacy_fields), so correcting the read
        # cannot mis-route a deck to the wrong manifest/phases -- it only
        # makes the SAME already-computed creation_mode axis honor the
        # client's real answer instead of silently overriding it. Falls back
        # to the old top-level flat read (hand-authored/legacy ledger), then
        # to the schema's own real default ("from_scratch") only when the
        # question was genuinely never asked/answered -- never fabricated.
        intake["signature_source"] = (
            _entry_raw_value(entries, "signature_source")
            or ledger.get("signature_source")
            or "from_scratch"
        )

    # FAULT-05 fix: carry the client's upsell answers (sales+checkout page --
    # DEFAULT YES at the interview layer -- and VSL page, plus their
    # verbatim declined-reason waivers) forward into the resolved engine
    # intake. Before this fix the resolved intake carried only 6 keys and
    # these answers -- captured for real in either the ledger or
    # working/copy/intake.json -- never survived this step in ANY shape.
    # Emitted in the documented NESTED shape (pre_presentation_capture.*);
    # downstream readers that check pre_presentation_capture first (the
    # sales_checkout_builder.py / vsl_builder.py gates, and this same
    # nested-only shape presentation_job's own frozen state.json["intake"]
    # snapshot can be a fallback source for) get it directly. Omitted
    # entirely -- never emitted as an empty object -- when nothing resolved,
    # matching this file's own never-fabricate rule for every other field.
    capture = _resolve_upsell_capture(entries, intake_copy)
    if capture:
        intake["pre_presentation_capture"] = capture

    # FIX 36(3): intake depth (QUICK|IN-DEPTH) — resolved explicitly, never
    # silently defaulted: the schema default only applies when the question
    # was genuinely never answered anywhere. An explicit caller value that is
    # not in the vocabulary raises (loud AF-INTAKE-DEPTH-INVALID via main()).
    if intake_depth is not None and str(intake_depth).strip().lower().replace(
            "_", "-").replace(" ", "-").replace("indepth", "in-depth") \
            not in ("quick", "in-depth"):
        raise UnknownIntakeDepth(
            f"--intake-depth {intake_depth!r} is not a legal depth; the vocabulary "
            f"is exactly quick|in-depth (env {INTAKE_DEPTH_ENV}). Run-mode --mode "
            "(Ultra|Standard|Economy) is a DIFFERENT axis and is never accepted here."
        )
    intake["standard_mode"] = _resolve_intake_depth(
        intake_depth, entries, intake_copy)

    return intake


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--ledger", required=True, type=Path,
                   help="path to intake_ledger.json")
    p.add_argument("--out", required=True, type=Path,
                   help="path to write the engine's --new intake JSON")
    p.add_argument("--source", default="resolve-intake",
                   help="tag recorded in intake.source (which caller ran this)")
    p.add_argument("--intake-depth", default=None, choices=list(INTAKE_DEPTH_LEGAL),
                   help="FIX 36(3): the deck's intake depth, quick|in-depth "
                        "(the interview_depth question's standard_mode). "
                        "Distinct from run-mode --mode (Ultra|Standard|Economy) "
                        "-- never reuse --mode for this axis. Falls back to env "
                        f"{INTAKE_DEPTH_ENV}, then the ledger's interview_depth "
                        "answer, then the schema default QUICK.")
    args = p.parse_args(argv)

    try:
        intake = resolve(args.ledger, args.source, intake_depth=args.intake_depth)
    except UnknownPresentationType as exc:
        print(f"AF-DECK-TYPE-UNKNOWN: {exc}", file=sys.stderr)
        return 3
    except MissingRequester as exc:
        print(f"AF-REQUESTER-MISSING: {exc}", file=sys.stderr)
        return 4
    except UnknownIntakeDepth as exc:
        print(f"AF-INTAKE-DEPTH-INVALID: {exc}", file=sys.stderr)
        return 5

    args.out.parent.mkdir(parents=True, exist_ok=True)
    tmp = args.out.with_suffix(args.out.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(intake, fh, indent=2)
    os.replace(tmp, args.out)
    print(f"resolved presentation_type={intake['presentation_type']!r} "
          f"client={intake['client']!r} -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
