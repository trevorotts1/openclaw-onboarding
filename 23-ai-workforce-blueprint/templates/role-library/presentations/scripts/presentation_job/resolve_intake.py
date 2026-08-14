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


def resolve(ledger_path: Path, source: str) -> dict:
    """Read the intake ledger and return the engine's --new intake dict.

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
    # A run with genuinely nothing stamped anywhere (verified: a completely
    # untouched real driver run, no upstream step involved) still resolves to
    # an empty chat_id here -- and MUST. This function never fabricates one;
    # presentation_job.py --new's own hard-fail on missing requester.chat_id
    # is the correct outcome for that case, not a bug this fix papers over.
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
    return intake


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--ledger", required=True, type=Path,
                   help="path to intake_ledger.json")
    p.add_argument("--out", required=True, type=Path,
                   help="path to write the engine's --new intake JSON")
    p.add_argument("--source", default="resolve-intake",
                   help="tag recorded in intake.source (which caller ran this)")
    args = p.parse_args(argv)

    try:
        intake = resolve(args.ledger, args.source)
    except UnknownPresentationType as exc:
        print(f"AF-DECK-TYPE-UNKNOWN: {exc}", file=sys.stderr)
        return 3

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
