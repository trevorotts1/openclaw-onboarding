#!/usr/bin/env python3
# =============================================================================
# SKILL 53 — BOOK WRITER :: INTAKE-ACCEPT (the target side of the 52 -> 53 route)
# -----------------------------------------------------------------------------
# THE DEFECT THIS EXISTS TO CLOSE (T0-28):
#
#   52-avatar-alchemist/scripts/aa_director.py decided a book intake was
#   "book-routed" because a sibling directory matching 53-*book* EXISTED. It
#   invoked nothing, this skill was never consulted, and the durable route.json
#   that downstream automation reads recorded a completed handoff for a run that
#   had never begun. A directory is not an acknowledgement.
#
# THIS IS THE ACKNOWLEDGEMENT. The caller forwards the intake; THIS skill decides
# whether it can accept it, and says so in a machine-readable receipt that only
# this skill produces. Acceptance is decided by this skill's OWN fail-closed
# intake gate (prove_bw_intake.evaluate, handoff mode) -- the same gate a real
# book run must pass -- never by a re-implementation of it here.
#
# THE RECEIPT is printed on STDOUT so the caller reads it from THIS process
# rather than from a file that could have been pre-planted. It carries the
# sha256 of the exact intake bytes that were forwarded, so a caller that
# forwards X cannot satisfy itself with a receipt minted for Y. With
# --receipt-out the same receipt is ALSO persisted; a failed persist is a hard
# error (exit 3), never a quiet acceptance.
#
#   AF-BK-ACCEPT-UNREADABLE — the forwarded intake cannot be read or parsed.
#   AF-BK-ACCEPT-WRONG-VERSION — the intake is not version=book. A brand intake
#                          belongs to Skill 52 and is refused here, loudly.
#   AF-BK-ACCEPT-REJECTED  — this skill's own intake gate refused the payload;
#                          the underlying AF-BK-* codes are carried through.
#
# EXIT: 0 ACCEPTED · 2 REJECTED (a real, reasoned refusal) · 3 USAGE/IO.
# USAGE:
#   bw_intake_accept.py --intake <intake.json|-> [--from-skill NAME]
#                       [--receipt-out PATH] [--json]
#   bw_intake_accept.py --self-test
# =============================================================================
"""Intake-accept for the Book Writer (Skill 53): the receipt Skill 52 must have."""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import prove_bw_intake as gate  # noqa: E402

SKILL_DIR = Path(__file__).resolve().parent.parent
SKILL_NAME = SKILL_DIR.name

AF_UNREADABLE = "AF-BK-ACCEPT-UNREADABLE"
AF_WRONG_VERSION = "AF-BK-ACCEPT-WRONG-VERSION"
AF_REJECTED = "AF-BK-ACCEPT-REJECTED"

EXIT_ACCEPTED = 0
EXIT_REJECTED = 2
EXIT_USAGE = 3

RECEIPT_KIND = "book-intake-accept/v1"


def _skill_version() -> str:
    f = SKILL_DIR / "skill-version.txt"
    try:
        return f.read_text(encoding="utf-8").strip()
    except OSError:
        return "unknown"


def _brand_skill_present() -> bool:
    """Mirror of aa_director._detect_book_skill_present, in the other direction:
    is a sibling Skill 52 (avatar-alchemist) resolvable from here? Never
    hardcoded to one directory name."""
    parent = SKILL_DIR.parent
    if not parent.is_dir():
        return False
    for d in parent.iterdir():
        try:
            if d.is_dir() and d.name.lower().startswith("52-") and "avatar" in d.name.lower():
                return True
        except OSError:
            continue
    return False


def _now_utc() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def decide(raw: bytes, from_skill: str = "") -> dict:
    """Decide acceptance for the exact forwarded BYTES. Returns the receipt dict.

    The sha256 is computed over the bytes as received, before parsing, so the
    receipt is bound to what was actually forwarded and not to a re-serialisation
    of it."""
    digest = hashlib.sha256(raw).hexdigest()
    receipt = {
        "kind": RECEIPT_KIND,
        "accepted": False,
        "target_skill": SKILL_NAME,
        "target_skill_version": _skill_version(),
        "decided_by": "prove_bw_intake.evaluate(handoff=True)",
        "from_skill": from_skill or None,
        "intake_sha256": digest,
        "decided_at_utc": _now_utc(),
        "reasons": [],
        "notes": [],
    }

    try:
        intake = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        receipt["reasons"].append({"code": AF_UNREADABLE,
                                   "message": "forwarded intake does not parse as JSON: %s" % exc})
        return receipt
    if not isinstance(intake, dict):
        receipt["reasons"].append({"code": AF_UNREADABLE,
                                   "message": "forwarded intake is not a JSON object"})
        return receipt

    version = ("" if intake.get("version") is None else str(intake.get("version"))).strip().lower()
    receipt["intake_version"] = version or None
    if version != "book":
        receipt["reasons"].append({
            "code": AF_WRONG_VERSION,
            "message": "this skill accepts version=book only (got %r); a brand intake belongs "
                       "to Skill 52 and is never served by the book pipeline" % intake.get("version")})
        return receipt

    result = gate.evaluate(intake, handoff=True, brand_skill_present=_brand_skill_present())
    if not result.passed:
        receipt["reasons"].append({
            "code": AF_REJECTED,
            "message": "this skill's own intake gate refused the forwarded payload"})
        for code, message in result.violations:
            receipt["reasons"].append({"code": code, "message": message})
        return receipt

    receipt["accepted"] = True
    receipt["notes"] = list(result.notes)
    receipt["notes"].append(
        "the forwarded shared-answer core clears prove_bw_intake in handoff mode; the "
        "full-run fields (mode, book_about, cover_description) are collected by this skill "
        "before a run and are NOT part of this acceptance")
    receipt["receipt_id"] = hashlib.sha256(
        ("%s|%s|%s|%s" % (RECEIPT_KIND, SKILL_NAME, digest, receipt["decided_at_utc"]))
        .encode("utf-8")).hexdigest()[:32]
    return receipt


def _emit(receipt: dict, as_json: bool) -> None:
    if as_json:
        print(json.dumps(receipt, indent=2))
        return
    if receipt["accepted"]:
        print("ACCEPTED [%s]: receipt %s for intake sha256 %s"
              % (SKILL_NAME, receipt["receipt_id"], receipt["intake_sha256"][:16]))
        for n in receipt["notes"]:
            print("  - %s" % n)
    else:
        print("REJECTED [%s]: %d reason(s) for intake sha256 %s"
              % (SKILL_NAME, len(receipt["reasons"]), receipt["intake_sha256"][:16]),
              file=sys.stderr)
        for r in receipt["reasons"]:
            print("  [%s] %s" % (r["code"], r["message"]), file=sys.stderr)


def _read(path: str) -> bytes:
    if path == "-":
        return sys.stdin.buffer.read()
    return Path(path).read_bytes()


def self_test() -> int:
    checks = []
    core = {
        "version": "book", "first_name": "Jordan", "last_name": "Rivers",
        "ideal_avatar": "aspiring women founders in the wellness space",
        "niche": "holistic business coaching",
        "primary_goal": "launch a profitable, purpose-led practice",
        "tone_style_1": "Maya Angelou in Letter to My Daughter", "tone_style_2": "N/A",
        "book_stories": "The night I closed my first clinic and started over.",
    }
    raw = json.dumps(core).encode("utf-8")
    ok = decide(raw)
    checks.append(("a complete book handoff is ACCEPTED", ok["accepted"] is True))
    checks.append(("...and carries a receipt id", bool(ok.get("receipt_id"))))
    checks.append(("...bound to the forwarded bytes",
                   ok["intake_sha256"] == hashlib.sha256(raw).hexdigest()))
    checks.append(("...naming this skill as the decider",
                   ok["target_skill"] == SKILL_NAME))

    missing = dict(core)
    missing.pop("niche")
    bad = decide(json.dumps(missing).encode("utf-8"))
    checks.append(("an incomplete handoff is REJECTED", bad["accepted"] is False))
    checks.append(("...with no receipt id minted", "receipt_id" not in bad))
    checks.append(("...carrying this skill's own AF code",
                   any(r["code"] == "AF-BK-INTAKE-MISSING" for r in bad["reasons"])))

    brand = dict(core)
    brand["version"] = "brand"
    br = decide(json.dumps(brand).encode("utf-8"))
    checks.append(("a version=brand payload is REFUSED here", br["accepted"] is False))
    checks.append(("...with AF-BK-ACCEPT-WRONG-VERSION",
                   any(r["code"] == AF_WRONG_VERSION for r in br["reasons"])))

    junk = decide(b"{not json")
    checks.append(("unparseable bytes are REJECTED", junk["accepted"] is False))
    checks.append(("...with AF-BK-ACCEPT-UNREADABLE",
                   any(r["code"] == AF_UNREADABLE for r in junk["reasons"])))

    # Two different payloads must never share a receipt-bound digest.
    other = dict(core)
    other["niche"] = "a different niche entirely"
    checks.append(("a different payload yields a different digest",
                   decide(json.dumps(other).encode("utf-8"))["intake_sha256"]
                   != ok["intake_sha256"]))

    ok_all = True
    for label, good in checks:
        print("  [%s] %s" % ("OK" if good else "XX", label))
        ok_all = ok_all and good
    print("== bw_intake_accept self-test: %s ==" %
          ("ALL ASSERTIONS PASSED" if ok_all else "FAILED"))
    return 0 if ok_all else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Book Writer (Skill 53) intake-accept: the receipt a routing caller must have.")
    ap.add_argument("--intake", help="path to the forwarded intake JSON, or - for stdin")
    ap.add_argument("--from-skill", default="", help="the calling skill's directory name")
    ap.add_argument("--receipt-out", help="also persist the receipt to this path")
    ap.add_argument("--json", action="store_true", help="emit the receipt as JSON on stdout")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args(argv)

    if args.self_test:
        return self_test()
    if not args.intake:
        ap.error("--intake is required (or use --self-test)")

    try:
        raw = _read(args.intake)
    except OSError as exc:
        print("USAGE/IO: cannot read forwarded intake %s: %s" % (args.intake, exc), file=sys.stderr)
        return EXIT_USAGE

    receipt = decide(raw, from_skill=args.from_skill)

    if args.receipt_out:
        try:
            out = Path(args.receipt_out)
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
        except OSError as exc:
            # Never let a persist failure read as a quiet acceptance.
            print("USAGE/IO: decided but could not persist the receipt to %s: %s"
                  % (args.receipt_out, exc), file=sys.stderr)
            return EXIT_USAGE

    _emit(receipt, args.json)
    return EXIT_ACCEPTED if receipt["accepted"] else EXIT_REJECTED


if __name__ == "__main__":
    sys.exit(main())
