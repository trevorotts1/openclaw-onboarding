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

HARNESS IDENTITY (ENF-17): `recorded_by` is a label, and a JSONL line is text anyone can
append. Every line a real adapter process writes therefore also carries `harness_sig`, an
HMAC under the OPERATOR KEY (prove_sf_cert.load_operator_key — a secret the AI session does
not hold) over the line and the run it belongs to. `require_signed()` / `verify_delivery_store()`
are the CLIENT-DELIVERY forms: an ABSENT store, an UNSIGNED line, a line signed for another
run, or one with a bad signature all FAIL. A line the AI appended by hand cannot be signed.

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
import hashlib
import hmac
import inspect
import json
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

EXIT_OK = 0
EXIT_VIOLATION = 2
EXIT_FAILCLOSED = 3

RECEIPTS_REL = "delegation_receipts.jsonl"
SIG_FIELD = "harness_sig"
# Set ONLY by this module's own CLI (a separate adapter process naming itself); a library
# caller cannot relabel itself — see _caller_module().
_CLI_ADAPTER: Optional[str] = None

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
    if _CLI_ADAPTER:
        return _CLI_ADAPTER
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


_CERT_MOD: Any = None


def _cert_module() -> Any:
    """prove_sf_cert, found next to this file whatever the caller's sys.path (a consumer
    may load this module by file path). sys.path is never mutated."""
    global _CERT_MOD
    if _CERT_MOD is None:
        try:
            import prove_sf_cert as mod
        except ImportError:
            import importlib.util
            spec = importlib.util.spec_from_file_location(
                "s49_prove_sf_cert", Path(__file__).resolve().parent / "prove_sf_cert.py")
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
        _CERT_MOD = mod
    return _CERT_MOD


def _operator_key(run_dir: Optional[Path] = None) -> Optional[str]:
    try:
        return _cert_module().load_operator_key(run_dir)[0]
    except Exception:  # noqa: BLE001 — no key available == cannot sign, never a crash
        return None


def _entry_sig(entry: Dict[str, Any], key: str) -> str:
    body = {k: v for k, v in entry.items() if k != SIG_FIELD}
    return hmac.new(key.encode("utf-8"),
                    json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8"),
                    hashlib.sha256).hexdigest()


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
        "run_id": Path(run_dir).resolve().name,
        "at": _now(),
    }
    if extra:
        for k, v in extra.items():
            entry.setdefault(str(k), v)
    key = _operator_key(Path(run_dir))
    if key:  # a process without the operator key writes an UNSIGNED line, which delivery refuses
        entry[SIG_FIELD] = _entry_sig(entry, key)
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
def _sig_fails(e: Dict[str, Any], who: str, af: str, key: Optional[str],
               run_id: Optional[str]) -> List[str]:
    sig = e.get(SIG_FIELD)
    if not isinstance(sig, str) or not sig:
        return [f"{af}-UNSIGNED: {who} carries no harness signature — a hand-written line "
                "is not provider evidence"]
    if key is None:
        return [f"{af}-UNSIGNED: no operator key to verify {who}'s harness signature (fail-closed)"]
    if not hmac.compare_digest(_entry_sig(e, key), sig):
        return [f"{af}-UNSIGNED: {who} harness signature does not match the operator key — forged"]
    if run_id is not None and e.get("run_id") != run_id:
        return [f"{af}-UNSIGNED: {who} was signed for run {e.get('run_id')!r}, not {run_id!r}"]
    return []


def _check_entries(entries: List[Dict[str, Any]],
                   phase: str,
                   af: str,
                   must_cover: Optional[Iterable[str]],
                   signed_for: Optional[Path] = None) -> List[str]:
    fails: List[str] = []
    scoped = [e for e in entries if str(e.get("phase", "")).strip() == phase]
    if not scoped:
        fails.append(f"{af}-MISSING-PHASE: no provider receipt recorded for phase {phase!r}")
        return fails
    key = _operator_key(signed_for) if signed_for is not None else None
    run_id = Path(signed_for).resolve().name if signed_for is not None else None

    covered = set()
    for i, e in enumerate(scoped):
        who = f"{phase} receipt #{i} ({e.get('provider', '?')}/{e.get('operation', '?')})"
        if signed_for is not None:
            fails.extend(_sig_fails(e, who, af, key, run_id))
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
            af: str = "AF-DELEG-RECEIPT",
            signed: bool = False) -> Tuple[bool, str]:
    """HARD form: the phase does not attest without a valid provider receipt. With
    signed=True (the client-delivery form) every receipt must also carry a valid harness
    signature for THIS run."""
    try:
        entries = load(run_dir)
    except ReceiptError as exc:
        return False, f"{af}-MALFORMED: {exc}"
    if not entries:
        return False, (f"{af}-ABSENT: no {RECEIPTS_REL} in the run dir — the delegated "
                       f"phase {phase} has no provider evidence (fail-closed)")
    fails = _check_entries(entries, phase, af, must_cover, Path(run_dir) if signed else None)
    if fails:
        return False, " | ".join(fails)
    n = sum(1 for e in entries if str(e.get("phase", "")).strip() == phase)
    return True, f"{n} provider receipt(s) verified for {phase}" + (" (harness-signed)" if signed else "")


def require_signed(run_dir: Path, phase: str, *,
                   must_cover: Optional[Iterable[str]] = None,
                   af: str = "AF-DELEG-RECEIPT") -> Tuple[bool, str]:
    """CLIENT-DELIVERY form (ENF-17): an absent store, an unsigned/forged line, or a line
    signed for another run FAILS. 'absent' is never an attestation."""
    return require(run_dir, phase, must_cover=must_cover, af=af, signed=True)


def verify_delivery_store(run_dir: Path, phases: Iterable[str] = (),
                          af: str = "AF-DELEG-RECEIPT") -> Tuple[bool, str]:
    """Gate for a client-delivery package (83 check / assemble): the store must exist, be
    non-empty, and EVERY line must be harness-signed for this run and not authored by a
    certified module; each named phase must be covered by at least one such line."""
    run_dir = Path(run_dir)
    try:
        entries = load(run_dir)
    except ReceiptError as exc:
        return False, f"{af}-MALFORMED: {exc}"
    if not entries:
        return False, (f"{af}-ABSENT: no {RECEIPTS_REL} in {run_dir.name} — a client delivery "
                       "without a provider receipt store is not provider-backed (fail-closed)")
    key = _operator_key(run_dir)
    fails: List[str] = []
    for i, e in enumerate(entries):
        who = f"receipt line #{i} ({e.get('phase', '?')}/{e.get('provider', '?')})"
        fails.extend(_sig_fails(e, who, af, key, run_dir.resolve().name))
        if is_subject_module(e.get("recorded_by")):
            fails.append(f"{af}-SELF-AUTHORED: {who} recorded by {e.get('recorded_by')!r}")
    for ph in phases:
        if not any(str(e.get("phase", "")).strip() == ph for e in entries):
            fails.append(f"{af}-MISSING-PHASE: no provider receipt recorded for phase {ph!r}")
    if fails:
        return False, " | ".join(fails)
    return True, f"{len(entries)} harness-signed provider receipt(s) verified"


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
    """'present' / 'unsigned' / 'absent' / 'malformed' — the value a certificate records
    so a reader can tell whether the delegated phases were receipt-backed. 'present' now
    means every line is harness-signed for this run; a hand-written store reads 'unsigned'."""
    try:
        entries = load(run_dir)
    except ReceiptError:
        return "malformed"
    if not entries:
        return "absent"
    ok, _ = verify_delivery_store(run_dir)
    return "present" if ok else "unsigned"


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

    # (10) ENF-17 — CLIENT-DELIVERY form: the receipt store must be present AND harness-signed.
    import os
    saved = os.environ.get("SF_OPERATOR_KEY_FILE")
    with tempfile.TemporaryDirectory() as keydir, tempfile.TemporaryDirectory() as td:
        kf = Path(keydir) / "operator.key"
        kf.write_text("selftest-operator-key-0123456789abcdef\n", encoding="utf-8")
        kf.chmod(0o600)
        rd = Path(td) / "run-a"
        rd.mkdir()
        os.environ["SF_OPERATOR_KEY_FILE"] = str(kf)
        try:
            good, detail = verify_delivery_store(rd, ["P3-IMAGES"])
            say(not good and "ABSENT" in detail, f"absent store fails a client delivery ({detail[:60]})")
            # a line the AI hand-appends: well-formed, honest-looking, unsigned
            (rd / RECEIPTS_REL).write_text(json.dumps({
                "phase": "P3-IMAGES", "provider": "kie", "operation": "createTask",
                "provider_response_id": "kie-resp-1", "http_status": 200, "remote_id": "img-a",
                "covers": ["img-a"], "recorded_by": "kie_image_adapter", "at": _now()}) + "\n",
                encoding="utf-8")
            good, detail = verify_delivery_store(rd, ["P3-IMAGES"])
            good2, detail2 = require_signed(rd, "P3-IMAGES", must_cover=["img-a"])
            say(not good and not good2 and "UNSIGNED" in detail and "UNSIGNED" in detail2,
                "self-written (unsigned) receipt line fails delivery in both signed forms")
            say(store_state(rd) == "unsigned", "a hand-written store reads 'unsigned', never 'present'")
            reset(rd)
            stub.emit(rd, "P3-IMAGES", ["img-a"])  # adapter process holding the operator key
            good, detail = verify_delivery_store(rd, ["P3-IMAGES"])
            good2, detail2 = require_signed(rd, "P3-IMAGES", must_cover=["img-a"])
            say(good and good2 and store_state(rd) == "present",
                f"harness-signed adapter receipts pass delivery ({detail})")
            good, detail = verify_delivery_store(rd, ["P3-IMAGES", "P4-MEDIA"])
            say(not good and "MISSING-PHASE" in detail, "a phase with no receipt fails delivery")
            # signature is bound to the run: the same file dropped into another run fails
            other = Path(td) / "run-b"
            other.mkdir()
            (other / RECEIPTS_REL).write_text((rd / RECEIPTS_REL).read_text(encoding="utf-8"), encoding="utf-8")
            good, detail = verify_delivery_store(other)
            say(not good and "UNSIGNED" in detail, "receipts copied into another run fail (run-bound signature)")
            # a line edited after signing fails
            line = json.loads((rd / RECEIPTS_REL).read_text(encoding="utf-8").splitlines()[0])
            line["covers"] = ["img-a", "img-ghost"]
            (rd / RECEIPTS_REL).write_text(json.dumps(line) + "\n", encoding="utf-8")
            good, detail = verify_delivery_store(rd)
            say(not good and "forged" in detail, "an edited signed line fails (signature no longer matches)")
            # without the operator key nothing verifies
            os.environ.pop("SF_OPERATOR_KEY_FILE", None)
            reset(rd)
            stub.emit(rd, "P3-IMAGES", ["img-a"])   # unsigned: no key in this process
            good, detail = verify_delivery_store(rd)
            say(not good and "UNSIGNED" in detail, "no operator key -> receipts are unsigned and delivery fails")
        finally:
            if saved is None:
                os.environ.pop("SF_OPERATOR_KEY_FILE", None)
            else:
                os.environ["SF_OPERATOR_KEY_FILE"] = saved

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
    ap.add_argument("--verify-delivery", nargs="*", metavar="PHASE", default=None,
                    help="CLIENT-DELIVERY gate (ENF-17): store present, every line harness-signed "
                         "for this run, each named PHASE covered")
    ap.add_argument("--adapter", help="the adapter process's own name, for --record (the line is "
                                      "only delivery-valid when the process holds the operator key)")
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
    global _CLI_ADAPTER
    _CLI_ADAPTER = (args.adapter or "").strip() or None

    if args.verify_delivery is not None:
        ok, detail = verify_delivery_store(run_dir, args.verify_delivery)
        print(("PASS: " if ok else "FAIL: ") + detail)
        return EXIT_OK if ok else EXIT_VIOLATION

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

    print("USAGE ERROR: pass --record, --verify PHASE, --verify-delivery, or --self-test.")
    return EXIT_FAILCLOSED


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
