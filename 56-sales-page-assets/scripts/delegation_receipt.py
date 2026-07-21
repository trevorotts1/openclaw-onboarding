#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""delegation_receipt.py — the PROVIDER RECEIPT contract for delegated phases.

A10 / T0-09, T0-10. A delegated phase used to be proven by the existence of a file
the run itself wrote. That is a certificate minted on evidence its own subject
authored: the thing being judged supplied the proof it was judged by. This module
is the WRITING side of the replacement, and the requirer that consumes it.

THE CONTRACT
------------
A delegated tool (the image provider adapter, the media-upload rail, the document
API, the mail send, the remote page build) records ONE receipt line per real
provider round-trip into <run_dir>/delegation_receipts.jsonl:

    {"phase": "P3-IMAGES", "provider": "kie", "operation": "createTask",
     "provider_response_id": "<the provider's own id>", "http_status": 200,
     "remote_id": "<the id of the resource that now exists remotely>",
     "covers": ["<ledger identifiers this call produced>"],
     "recorded_by": "<the module that made the call>", "at": "<utc>"}

The requirer then refuses to attest the phase unless:
  * a receipt exists for the phase                                 (omission)
  * every receipt carries a 2xx integer http_status                (a failed call
    is not a delegation)
  * response id and remote id are real, non-placeholder strings
  * `recorded_by` is NOT one of the modules being certified — the SUBJECT of a
    certificate may not author that certificate's evidence   (self-authorship)
  * every identifier the run's own ledger claims is COVERED by a receipt line
    (a ledger row nobody called a provider for is not delegated)

WHAT THIS DOES AND DOES NOT BUY
-------------------------------
It structurally removes omission and self-authorship, and it binds the run's
ledger to a log produced by a different module at call time. It is not a defence
against an author who deliberately hand-forges a provider adapter log — no
offline, deterministic prover can be. It is honest about that rather than
claiming cryptographic provenance it does not have.

SEQUENCING (A10): this WRITING side lands before any phase REQUIRES it. Callers
in this release use `validate_if_present()` — receipts are validated strictly
whenever they exist, and their presence/absence is recorded on the certificate,
so a certificate can never silently imply provider-backed delegation it does not
have. `require()` is the hard form the delegated skills switch to once they emit
receipts on every path.

stdlib only. Exit 0 = pass, 2 = violation, 3 = usage / fail-closed.
"""

from __future__ import annotations

import argparse
import datetime
import inspect
import json
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

EXIT_OK = 0
EXIT_VIOLATION = 2
EXIT_FAILCLOSED = 3

RECEIPTS_REL = "delegation_receipts.jsonl"

# Modules that are the SUBJECT of a certificate. A receipt stamped with one of
# these was written by the thing being judged and is rejected outright.
SUBJECT_MODULES = frozenset({
    "run_signature_funnel",
    "run_sales_page_assets",
    "build_deck",
    "delegation_receipt",          # the requirer may not author its own evidence
    "__main__",                    # an orchestrator run as a script
})
# Any prove_* module is a judge, never a producer.
SUBJECT_PREFIXES = ("prove_",)

# Identifier values that are not identifiers.
PLACEHOLDER_IDS = frozenset({
    "", "-", "none", "null", "nil", "n/a", "na", "tbd", "todo", "todo:", "changeme",
    "placeholder", "example", "sample", "test", "fake", "dummy", "native", "unknown",
    "0", "00000000-0000-0000-0000-000000000000",
})


class ReceiptError(Exception):
    """A receipt store cannot be read -> fail-closed."""


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _caller_module() -> str:
    """The module that called record(), resolved from the stack. Deliberately NOT
    caller-supplied: a producer cannot label itself as somebody else through this
    API, so an orchestrator that writes its own receipt is stamped as such and the
    requirer rejects it."""
    for frame in inspect.stack()[2:]:
        name = frame.frame.f_globals.get("__name__", "")
        if name != __name__:
            filename = frame.frame.f_globals.get("__file__", "")
            if name == "__main__" and filename:
                return Path(filename).stem
            return name or Path(filename).stem or "unknown"
    return "unknown"


def is_subject_module(name: Any) -> bool:
    """True when `name` identifies a module that is certified by the evidence it
    would be writing (self-authorship)."""
    n = str(name or "").strip().split(".")[-1].lower()
    if not n:
        return True
    if n in SUBJECT_MODULES:
        return True
    return any(n.startswith(p) for p in SUBJECT_PREFIXES)


def _real_id(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    v = value.strip()
    return bool(v) and v.lower() not in PLACEHOLDER_IDS


def _status_ok(value: Any) -> bool:
    # bool is an int in Python; True must never read as a 2xx status.
    if isinstance(value, bool) or not isinstance(value, int):
        return False
    return 200 <= value < 300


# ---------------------------------------------------------------------------
# WRITER — the side that lands first.
# ---------------------------------------------------------------------------
def record(run_dir: Path,
           *,
           phase: str,
           provider: str,
           operation: str,
           provider_response_id: str,
           http_status: int,
           remote_id: str,
           covers: Optional[Sequence[str]] = None,
           extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Append ONE provider receipt for a real round-trip. Called by the delegated
    tool at call time — never by the orchestrator that is being certified."""
    entry: Dict[str, Any] = {
        "phase": str(phase),
        "provider": str(provider),
        "operation": str(operation),
        "provider_response_id": str(provider_response_id),
        "http_status": http_status,
        "remote_id": str(remote_id),
        "covers": [str(c) for c in (covers or [])],
        "recorded_by": _caller_module(),
        "at": _now(),
    }
    if extra:
        for k, v in extra.items():
            entry.setdefault(str(k), v)
    path = Path(run_dir) / RECEIPTS_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, sort_keys=True) + "\n")
    return entry


def load(run_dir: Path) -> List[Dict[str, Any]]:
    """Every receipt line in the run's store. Raises ReceiptError when the store is
    present but unreadable/malformed — never returns a silently empty list for a
    corrupt file."""
    path = Path(run_dir) / RECEIPTS_REL
    if not path.is_file():
        return []
    out: List[Dict[str, Any]] = []
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ReceiptError(f"{RECEIPTS_REL} is unreadable ({exc})") from exc
    for lineno, line in enumerate(raw.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
        except ValueError as exc:
            raise ReceiptError(f"{RECEIPTS_REL} line {lineno} is not JSON ({exc})") from exc
        if not isinstance(obj, dict):
            raise ReceiptError(f"{RECEIPTS_REL} line {lineno} is not a JSON object")
        out.append(obj)
    return out


def present(run_dir: Path) -> bool:
    return (Path(run_dir) / RECEIPTS_REL).is_file()


def reset(run_dir: Path) -> None:
    """Drop the run's receipt store. For FIXTURE regeneration only — record() appends,
    so a golden example rebuilt twice would otherwise accumulate duplicate receipt
    lines. Never call this from a production path: deleting evidence mid-run is the
    behaviour these receipts exist to make impossible."""
    path = Path(run_dir) / RECEIPTS_REL
    if path.is_file():
        path.unlink()


# ---------------------------------------------------------------------------
# REQUIRER.
# ---------------------------------------------------------------------------
def _check_entries(entries: List[Dict[str, Any]],
                   phase: str,
                   af: str,
                   must_cover: Optional[Iterable[str]]) -> List[str]:
    fails: List[str] = []
    scoped = [e for e in entries if str(e.get("phase", "")).strip() == phase]
    if not scoped:
        fails.append(f"{af}-MISSING-PHASE: no provider receipt recorded for phase {phase!r}")
        return fails

    covered = set()
    for i, e in enumerate(scoped):
        who = f"{phase} receipt #{i} ({e.get('provider', '?')}/{e.get('operation', '?')})"
        if is_subject_module(e.get("recorded_by")):
            fails.append(
                f"{af}-SELF-AUTHORED: {who} was recorded by "
                f"{e.get('recorded_by')!r} — the subject of the certificate cannot "
                "author the evidence it is certified on")
        if not _status_ok(e.get("http_status")):
            fails.append(f"{af}-STATUS: {who} http_status {e.get('http_status')!r} "
                         "is not a 2xx integer (a failed call is not a delegation)")
        if not _real_id(e.get("provider_response_id")):
            fails.append(f"{af}-ID: {who} provider_response_id "
                         f"{e.get('provider_response_id')!r} is missing/placeholder")
        if not _real_id(e.get("remote_id")):
            fails.append(f"{af}-ID: {who} remote_id {e.get('remote_id')!r} is "
                         "missing/placeholder (no remote resource was named)")
        for c in e.get("covers") or []:
            if isinstance(c, str) and c.strip():
                covered.add(c.strip())

    if must_cover is not None:
        missing = sorted({str(c).strip() for c in must_cover if str(c).strip()} - covered)
        if missing:
            fails.append(
                f"{af}-COVERAGE: {len(missing)} ledger identifier(s) claimed by the run "
                f"have no provider receipt (e.g. {missing[:3]}) — a ledger row nobody "
                "called a provider for is not a delegated result")
    return fails


def require(run_dir: Path, phase: str, *,
            must_cover: Optional[Iterable[str]] = None,
            af: str = "AF-DELEG-RECEIPT") -> Tuple[bool, str]:
    """HARD form: the phase does not attest without a valid provider receipt."""
    try:
        entries = load(run_dir)
    except ReceiptError as exc:
        return False, f"{af}-MALFORMED: {exc}"
    if not entries:
        return False, (f"{af}-ABSENT: no {RECEIPTS_REL} in the run dir — the delegated "
                       f"phase {phase} has no provider evidence (fail-closed)")
    fails = _check_entries(entries, phase, af, must_cover)
    if fails:
        return False, " | ".join(fails)
    n = sum(1 for e in entries if str(e.get("phase", "")).strip() == phase)
    return True, f"{n} provider receipt(s) verified for {phase}"


def validate_if_present(run_dir: Path, phase: str, *,
                        must_cover: Optional[Iterable[str]] = None,
                        af: str = "AF-DELEG-RECEIPT") -> Tuple[bool, str, str]:
    """TRANSITIONAL form used while the delegated skills are being taught to write
    receipts (A10 sequencing: writer before requirer).

    Returns (ok, detail, state) where state is one of:
      "verified" — receipts exist for this phase and every rule holds
      "absent"   — no receipt store at all; the phase attests on ledger content
                   alone and the certificate RECORDS that it did
      "invalid"  — receipts exist but do not hold: that is a hard FAIL. A partial
                   or forged receipt can never be more permissive than none.
    """
    try:
        entries = load(run_dir)
    except ReceiptError as exc:
        return False, f"{af}-MALFORMED: {exc}", "invalid"
    if not entries:
        return True, (f"no {RECEIPTS_REL} present — {phase} attested on ledger content only "
                      "(recorded on the certificate as receipts_absent)"), "absent"
    fails = _check_entries(entries, phase, af, must_cover)
    if fails:
        return False, " | ".join(fails), "invalid"
    n = sum(1 for e in entries if str(e.get("phase", "")).strip() == phase)
    return True, f"{n} provider receipt(s) verified for {phase}", "verified"


def store_state(run_dir: Path) -> str:
    """'verified-store' / 'absent' / 'malformed' — the value a certificate records
    so a reader can tell whether the delegated phases were receipt-backed."""
    try:
        entries = load(run_dir)
    except ReceiptError:
        return "malformed"
    return "present" if entries else "absent"


# ---------------------------------------------------------------------------
# PROVIDER STUB — the ONLY fixture source the self-tests are allowed to use.
# It stands in for a delegated tool, so a test fixture is never authored by the
# run under test (A10: "the self-test must consume a fixture a provider stub
# produced, never one the run authored").
# ---------------------------------------------------------------------------
def stub_provider_call(run_dir: Path, *, phase: str, provider: str, operation: str,
                       remote_id: str, covers: Sequence[str],
                       http_status: int = 200) -> Dict[str, Any]:
    """Simulate one delegated provider round-trip and record its receipt. Lives in
    this module but is invoked THROUGH a distinct stub module in tests so that
    `recorded_by` never resolves to an orchestrator or a prover."""
    return record(run_dir, phase=phase, provider=provider, operation=operation,
                  provider_response_id=f"{provider}-resp-{abs(hash((phase, remote_id))) % 10**12:012d}",
                  http_status=http_status, remote_id=remote_id, covers=list(covers))


# ---------------------------------------------------------------------------
# Self-test.
# ---------------------------------------------------------------------------
def _self_test() -> int:
    import tempfile
    import types

    ok = True

    def say(good: bool, msg: str) -> None:
        nonlocal ok
        ok = ok and good
        print(f"SELF-TEST {'ok' if good else 'FAIL'}: {msg}")

    # A stub PROVIDER ADAPTER module — a module that is not the run under test.
    stub = types.ModuleType("kie_image_stub_adapter")
    stub.__file__ = "kie_image_stub_adapter.py"
    stub.__dict__["record"] = record
    stub.__dict__["stub_provider_call"] = stub_provider_call
    exec(  # noqa: S102 — build a real frame whose __name__ is the stub adapter
        "def emit(run_dir, phase, remote_ids, status=200):\n"
        "    for r in remote_ids:\n"
        "        stub_provider_call(run_dir, phase=phase, provider='kie',\n"
        "                           operation='createTask', remote_id=r,\n"
        "                           covers=[r], http_status=status)\n",
        stub.__dict__)

    with tempfile.TemporaryDirectory() as td:
        rd = Path(td)

        # (1) omission — no receipt store at all.
        good, detail = require(rd, "P3-IMAGES")
        say(not good and "ABSENT" in detail, f"omitted receipt store -> require() FAILS ({detail[:60]})")

        # (2) the stub provider writes real receipts -> require() passes and binds.
        stub.emit(rd, "P3-IMAGES", ["img-a", "img-b"])
        good, detail = require(rd, "P3-IMAGES", must_cover=["img-a", "img-b"])
        say(good, f"stub-provider receipts -> require() PASSES ({detail})")

        # (3) coverage — the run claims a ledger row nobody called a provider for.
        good, detail = require(rd, "P3-IMAGES", must_cover=["img-a", "img-b", "img-ghost"])
        say(not good and "COVERAGE" in detail,
            f"ledger row with no provider call -> COVERAGE fail ({detail[:70]})")

        # (4) wrong phase — a receipt for another phase does not attest this one.
        good, detail = require(rd, "P4-MEDIA")
        say(not good and "MISSING-PHASE" in detail,
            f"receipt for another phase -> MISSING-PHASE fail ({detail[:60]})")

    # (5) SELF-AUTHORSHIP — the orchestrator writes its own receipt.
    with tempfile.TemporaryDirectory() as td:
        rd = Path(td)
        subject = types.ModuleType("run_signature_funnel")
        subject.__file__ = "run_signature_funnel.py"
        subject.__dict__["record"] = record
        exec(  # noqa: S102
            "def emit(run_dir):\n"
            "    record(run_dir, phase='P3-IMAGES', provider='kie', operation='createTask',\n"
            "           provider_response_id='kie-resp-1', http_status=200,\n"
            "           remote_id='img-a', covers=['img-a'])\n",
            subject.__dict__)
        subject.emit(rd)
        entries = load(rd)
        stamped = entries and entries[0].get("recorded_by") == "run_signature_funnel"
        say(bool(stamped), f"orchestrator-written receipt is stamped with its own module "
                           f"({entries[0].get('recorded_by') if entries else None!r})")
        good, detail = require(rd, "P3-IMAGES", must_cover=["img-a"])
        say(not good and "SELF-AUTHORED" in detail,
            f"orchestrator-written receipt -> SELF-AUTHORED fail ({detail[:70]})")
        # and the transitional form must be no more permissive.
        good, detail, state = validate_if_present(rd, "P3-IMAGES", must_cover=["img-a"])
        say(not good and state == "invalid",
            f"self-authored receipt is 'invalid' under validate_if_present too (state={state})")

    # (6) a prover may not author evidence either.
    say(is_subject_module("prove_sf_build") and is_subject_module("run_sales_page_assets")
        and not is_subject_module("kie_image_stub_adapter"),
        "subject-module detection covers orchestrators + prove_* and clears provider adapters")

    # (7) non-2xx status and placeholder ids.
    with tempfile.TemporaryDirectory() as td:
        rd = Path(td)
        stub.emit(rd, "P3-IMAGES", ["img-a"], status=500)
        good, detail = require(rd, "P3-IMAGES", must_cover=["img-a"])
        say(not good and "STATUS" in detail, f"http 500 -> STATUS fail ({detail[:60]})")
    with tempfile.TemporaryDirectory() as td:
        rd = Path(td)
        stub.emit(rd, "P3-IMAGES", ["placeholder"])
        good, detail = require(rd, "P3-IMAGES")
        say(not good and "-ID" in detail, f"placeholder remote_id -> ID fail ({detail[:60]})")
    say(not _status_ok(True) and not _status_ok("200") and _status_ok(201),
        "http_status accepts only 2xx ints (True and '200' rejected)")

    # (8) a corrupt store is fail-closed, never an empty pass.
    with tempfile.TemporaryDirectory() as td:
        rd = Path(td)
        (rd / RECEIPTS_REL).write_text("{not json\n", encoding="utf-8")
        good, detail = require(rd, "P3-IMAGES")
        good2, detail2, state2 = validate_if_present(rd, "P3-IMAGES")
        say(not good and not good2 and state2 == "invalid",
            "corrupt receipt store is fail-closed in BOTH require() and validate_if_present()")

    # (9) transitional form: absent store attests but is REPORTED as absent.
    with tempfile.TemporaryDirectory() as td:
        rd = Path(td)
        good, detail, state = validate_if_present(rd, "P3-IMAGES")
        say(good and state == "absent" and store_state(rd) == "absent",
            "absent store -> attests with state='absent' (recorded on the certificate)")

    print("SELF-TEST RESULT:", "PASS (exit 0)" if ok else "FAIL (exit 1)")
    return 0 if ok else 1


# ---------------------------------------------------------------------------
# CLI — so a shell/tool step in a delegated skill can write a receipt directly.
# ---------------------------------------------------------------------------
def main(argv: List[str]) -> int:
    ap = argparse.ArgumentParser(
        description="Provider-receipt contract for delegated phases: --record writes one "
                    "receipt, --verify checks a phase. Exit 0 pass, 2 violation, 3 usage.")
    ap.add_argument("--run-dir", help="the run directory")
    ap.add_argument("--record", action="store_true", help="append one provider receipt")
    ap.add_argument("--verify", metavar="PHASE", help="require a valid receipt for PHASE")
    ap.add_argument("--phase")
    ap.add_argument("--provider")
    ap.add_argument("--operation", default="call")
    ap.add_argument("--response-id")
    ap.add_argument("--http-status", type=int)
    ap.add_argument("--remote-id")
    ap.add_argument("--covers", nargs="*", default=[])
    ap.add_argument("--must-cover", nargs="*", default=None)
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args(argv)

    if args.self_test:
        return _self_test()
    if not args.run_dir:
        print("USAGE ERROR: pass --run-dir (or --self-test).")
        return EXIT_FAILCLOSED
    run_dir = Path(args.run_dir).expanduser().resolve()

    if args.record:
        missing = [f for f, v in (("--phase", args.phase), ("--provider", args.provider),
                                  ("--response-id", args.response_id),
                                  ("--http-status", args.http_status),
                                  ("--remote-id", args.remote_id)) if v in (None, "")]
        if missing:
            print(f"USAGE ERROR: --record needs {', '.join(missing)}.")
            return EXIT_FAILCLOSED
        entry = record(run_dir, phase=args.phase, provider=args.provider,
                       operation=args.operation, provider_response_id=args.response_id,
                       http_status=args.http_status, remote_id=args.remote_id,
                       covers=args.covers)
        print(json.dumps(entry, sort_keys=True))
        return EXIT_OK

    if args.verify:
        ok, detail = require(run_dir, args.verify, must_cover=args.must_cover)
        print(("PASS: " if ok else "FAIL: ") + detail)
        return EXIT_OK if ok else EXIT_VIOLATION

    print("USAGE ERROR: pass --record, --verify PHASE, or --self-test.")
    return EXIT_FAILCLOSED


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
