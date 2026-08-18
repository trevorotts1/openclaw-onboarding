#!/usr/bin/env python3
# =============================================================================
# SKILL 59 — ANTHOLOGY ENGINE :: scripts/provision_sms_phone.py  (U23 tooling)
# GHL-GATED SMS PHONE PROVISIONER — the single CLI for the U23 family,
# ASSEMBLED from the 16 u23_modules files: it imports EVERY module under
# scripts/u23_modules/ BY NAME (the fail-closed empty package init + the
# main_skeleton dispatcher + phone_lister + provision_action + sms_verifier +
# sms_sender + golden_has_phone + attack_sms_failed + attack_no_phone +
# docs_u23 + house_rules + checklist_note + example_usage + the three sibling
# pytest batteries), wires them into ONE offline/online CLI, and runs the
# modules' own OFFLINE self-test batteries (golden PASS / attack FAIL) before
# any live surface. The LAW surfaces this file must keep exporting — the
# family's fixtures import them BY NAME as `provision_sms_phone as prov`:
# SMS_ENABLED_KEYS, _mask_number, _mask_destination, _sms_enabled,
# list_phone_numbers, provision_action, plan_action, _attack_numbers,
# self_test. This file carries NO check logic itself — a check family is
# exercised ONLY through its module so `--dry-run`, `--self-test`, and the
# live aggregate never drift apart (the U03/U04/U05/U06/U07/U08_U09 pattern).
#
# WHAT THIS IS (the ACTION is GHL-scope-gated; the tooling ships now):
#   The client's Convert and Flow location needs an SMS-capable phone number
#   BEFORE any SMS surface (stage gate nudges, snapshot-import notifications,
#   per-stage SMS links) can deliver. The v2 public surface this family uses:
#
#     GET    /phones/numbers?locationId=<loc>            list existing numbers
#     GET    /phones/numbers/<id>?locationId=<loc>       one number by id
#     POST   /phones/numbers                             provision a number
#     POST   /phones/numbers/<id>/send-test-message      send an SMS test message
#     POST   /conversations/messages/outbound            the extension verifier
#
#   IDEMPOTENCY LAW (GET-first, provision only if absent): the family LISTS the
#   location's existing numbers first and provisions ONLY when no number is
#   already present that matches the requested scope (SMS-capable). A location
#   that already carries an SMS-enabled number is VERIFIED, never re-provisioned
#   (exit 0, idempotent no-op — never a second number, never a second charge).
#
#   THE PROVISIONING ACTION STAYS GATED: this assembler NEVER provisions,
#   never sends, and never verifies a send without --execute. Default and
#   --dry-run are read-only / plan-only (no network in dry-run). The actual
#   POST that creates the number (and the test-message / outbound-message
#   POSTs) are GHL-scope actions: they run ONLY when the operator explicitly
#   passes --execute, which is exactly the GHL-gated scope boundary.
#
# CREDENTIAL DOCTRINE: the token + location are resolved BY LABEL exactly like
# every other adapter (reg.resolve_pit / reg.resolve_location:
# CONVERT_AND_FLOW_PIT / CONVERT_AND_FLOW_LOCATION_ID etc. across live process
# env then the three canonical client env stores). Values are NEVER printed
# (SET / NOT SET + masked location only). The browser User-Agent rides every
# request via reg.CafClient (W0.6/GK-09: services.leadconnectorhq.com is
# Cloudflare-fronted and 403s urllib's default UA — CF 1010). The engine's
# scope-vs-edge-block discrimination (ScopeDenied vs UpstreamBlockedError)
# applies to every read AND write: a bare 401/403 is NEVER reported as a scope
# problem, it is HELD.
#
# THE 16 u23_modules FILES (imported by name; each is STDLIB-only and
# self-tests itself — docs_u23.py carries the module inventory as data and
# its self-test proves the tree ships together):
#   __init__.py            fail-closed EMPTY package init (pure namespace)
#   main_skeleton.py       the family dispatcher CLI (plan / self-test /
#                          live aggregate; the ONE entry-point contract)
#   phone_lister.py        the LIVE PHONE LISTER — READ-ONLY GET-first side
#   provision_action.py    the TREVOR-GATED POST /phones/numbers ACTION
#   sms_verifier.py        the FAIL-CLOSED SMS SEND VERIFIER (outbound rail)
#   sms_sender.py          the GHL-GATED TEST-SMS SENDER (conversation rail)
#   golden_has_phone.py    the GOLDEN PHONE-PROVISIONED fixture
#   attack_sms_failed.py   the U23 ATTACK — the non-200 send MUST FAIL
#   attack_no_phone.py     the NO-PHONE ATTACK — the empty listing is refused
#   docs_u23.py            the U23 README/catalog data + drift gate
#   house_rules.py         the ONE canonical house-law constants surface
#   checklist_note.py      the READ-ONLY checklist gate (snapshot push flag)
#   example_usage.py       the fail-closed WORKED EXAMPLE of the U23 dispatch
#   test_phone_lister.py   offline pytest battery for phone_lister
#   test_provision_action.py offline pytest battery for provision_action
#   test_sms_verifier.py   offline pytest battery for sms_verifier
#
# AF ERROR CODES (fail-closed surfaces, house scheme):
#   AF-AE-U23-ASSEMBLY-INCOMPLETE   -> a u23_modules file is missing or a
#          module violates the one-entry-point self_test contract. STOP
#          (exit 2) — a law is never silently skipped.
#   AF-AE-PROVPHONE-NO-EXECUTE      -> a required label (PIT / location) is
#          NOT SET or resolves to a non-pit- value; or provisioning /
#          verification was requested without --execute. STOP (exit 2),
#          fail-closed.
#   AF-AE-PROVPHONE-READ-REFUSED    -> listing numbers for the location failed
#          (scope / validation / edge block / transport). STOP or HELD per
#          class — never a silent skip, never a provision-into-the-unknown.
#   AF-AE-PROVPHONE-CREATE-REFUSED  -> the location exists, no matching number,
#          and the POST /phones/numbers was rejected (validation / scope /
#          edge block / transport). STOP or HELD per class.
#   AF-AE-PROVPHONE-VERIFY-REFUSED  -> the verify read-back or the
#          send-test-message POST failed (scope / validation / edge /
#          transport). STOP or HELD per class.
#   AF-AE-PROVPHONE-VERIFY-STALLED  -> the verification read-back never
#          confirmed sending-capable within the bounded window. HELD (exit 3),
#          never a false pass.
#   AF-AE-PROVPHONE-ATTACK          -> an attack fixture tripped the OFFLINE
#          self-test. Exit 4 (enforced violation), never exit 1.
#
# EXIT CODES (house convention; nonzero STOPS/HELDs with an operator surface):
#   0  verified success (idempotent no-op / dry run counts as pass)
#   1  unexpected error
#   2  STOP refusal — usage error / missing credential / missing --execute
#   3  Convert and Flow API unreachable / verification not confirmed (retryable)
#   4  self-test FAILED — an assertion in the OFFLINE self-test tripped
#      (AF-AE-PROVPHONE-* family). A tamper NEVER masquerades as exit 1.
#   5  data or read-back mismatch (a required response field missing/renamed)
#
# MANIFEST-PENDING: after a PASSING run the tool writes
# manifest-pending/u23.json — the staged U23 manifest artifact (contract,
# verdict, the 16-module inventory, af-code family, exit-code contract,
# provenance) — so the manifest can be re-stamped from a machine-readable
# record once the operator approves. The write is fail-closed: it happens
# ONLY on a PASS (self-test pass or dry-run plan pass); a FAIL/HELD/STOP run
# writes nothing and removes nothing. ENGINE-MANIFEST.json / ENGINE-PIN.sha256
# are NEVER touched here.
#
# STDLIB ONLY (urllib + json via the registry and the family modules); calls
# NO model. DOCTRINE: move in silence; NOTHING Anthropic in any runtime file;
# Convert and Flow naming in every client surface; NEVER print a secret
# value; --dry-run and --self-test are OFFLINE.
# =============================================================================
"""provision_sms_phone.py — the U23 SMS phone provisioner assembled from the
16 u23_modules files: one CLI, offline self-test battery (golden has-phone
PASS / no-phone dry-run / sms-failed attack FAIL), JSON output, and the
manifest-pending/u23.json stage (Skill 59)."""

from __future__ import annotations

import argparse
import importlib
import io
import json
import os
import re
import subprocess
import sys
from pathlib import Path

# Sibling import bootstrap (house convention): the registry does the
# Cloudflare browser-UA wiring + LeadConnector client + label resolution we
# reuse. The u23_modules directory must also sit on sys.path so the family
# fixtures can import THIS module by name (import provision_sms_phone as
# prov/phone) exactly as running them as scripts puts scripts/ first.
sys.path.insert(0, str(Path(__file__).resolve().parent))
import anthology_registry as reg  # noqa: E402

EX_OK, EX_ERR, EX_STOP, EX_HELD, EX_MISMATCH = (
    reg.EX_OK, reg.EX_ERR, reg.EX_STOP, reg.EX_HELD, reg.EX_MISMATCH)
EX_VIOLATION = 4  # enforced violation detected (self-test FAILED)

SKILL_DIR = Path(__file__).resolve().parent.parent
MODULES_DIR = Path(__file__).resolve().parent / "u23_modules"
PENDING_DIR = SKILL_DIR / "manifest-pending"
PENDING_U23 = PENDING_DIR / "u23.json"

# The default client location is resolved BY LABEL (CONVERT_AND_FLOW_LOCATION_ID
# etc. via reg._live_client); the marker below is only the BY-LABEL placeholder.
LOCATION_BY_LABEL = "BY-LABEL"

# THE SIXTEEN u23_modules FILES — the assembly manifest for this CLI.
# Every name is imported BY NAME below (importlib, never exec'd from a path);
# a missing module is a STOP, never a silent skip (the fail-closed import
# contract of main_skeleton.load_modules). `role` is the one-line contract
# each module owns.
U23_MODULES = (
    ("__init__.py",             "fail-closed EMPTY package init (pure namespace)"),
    ("main_skeleton.py",        "the family dispatcher CLI (plan / self-test / live aggregate)"),
    ("phone_lister.py",         "the LIVE PHONE LISTER — READ-ONLY GET-first side of the phone surface"),
    ("provision_action.py",     "the TREVOR-GATED POST /phones/numbers provisioning ACTION"),
    ("sms_verifier.py",         "the FAIL-CLOSED SMS SEND VERIFIER (outbound rail, HTTP 200 + SID)"),
    ("sms_sender.py",           "the GHL-GATED TEST-SMS SENDER (conversation rail, bounded read-back)"),
    ("golden_has_phone.py",     "the GOLDEN PHONE-PROVISIONED fixture (idempotent no-op control)"),
    ("attack_sms_failed.py",    "the U23 ATTACK — the non-200 send MUST FAIL every SMS gate"),
    ("attack_no_phone.py",      "the NO-PHONE ATTACK — the empty listing is refused up front"),
    ("docs_u23.py",             "the U23 README/catalog data + drift gate"),
    ("house_rules.py",          "the ONE canonical house-law constants surface"),
    ("checklist_note.py",       "the READ-ONLY checklist gate (snapshot push flag)"),
    ("example_usage.py",        "the fail-closed WORKED EXAMPLE of the U23 dispatch"),
    ("test_phone_lister.py",    "offline pytest battery for phone_lister"),
    ("test_provision_action.py", "offline pytest battery for provision_action"),
    ("test_sms_verifier.py",    "offline pytest battery for sms_verifier"),
)

# The modules the main_skeleton dispatcher aggregates (main_skeleton.U23_MODULES).
DISPATCH_MODULE_NAMES = tuple(name for name, _ in (
    ("phone_lister", "the LIVE PHONE LISTER — READ-ONLY GET-first side of the phone surface"),
    ("provision_action", "the TREVOR-GATED POST /phones/numbers provisioning ACTION"),
    ("sms_verifier", "the FAIL-CLOSED SMS SEND VERIFIER (outbound rail, HTTP 200 + SID)"),
    ("sms_sender", "the GHL-GATED TEST-SMS SENDER (conversation rail, bounded read-back)"),
    ("golden_has_phone", "the GOLDEN PHONE-PROVISIONED fixture (idempotent no-op control)"),
    ("attack_sms_failed", "the U23 ATTACK — the non-200 send MUST FAIL every SMS gate"),
    ("attack_no_phone", "the NO-PHONE ATTACK — the empty listing is refused up front"),
    ("docs_u23", "the U23 README/catalog data + drift gate"),
    ("house_rules", "the ONE canonical house-law constants surface"),
    ("checklist_note", "the READ-ONLY checklist gate (snapshot push flag)"),
))

# The three sibling pytest batteries (imported for their provenance in the
# manifest-pending stage; the pytest run itself is the independent battery).
TEST_MODULES = ("test_phone_lister", "test_provision_action", "test_sms_verifier")

# The U23 verified surfaces, as the manifest-pending stage records them
# (main_skeleton.LIVE_GATES — the family's fixed gate order).
VERIFIED_ITEMS = (
    (1, "phone_lister", "the live phone read — GET /phones/numbers, masked markers, GET-first idempotency"),
    (2, "provision_action", "the provision surface — Trevor-gated --execute, create-only-absent, post-create read-back"),
    (3, "sms_verifier", "the SMS verification surface — the outbound send under --execute requiring HTTP 200 PLUS a SID"),
    (4, "attack_no_phone", "the no-phone attack boundary — the EMPTY / no-SMS-capable listing MUST be refused"),
    (5, "golden_has_phone", "the golden already-provisioned gate — the canonical SMS-PHONE-PROVISIONED state"),
    (6, "attack_sms_failed", "the attack boundary — the non-200 send fixture MUST fail while the golden control passes"),
    (7, "docs_u23", "the catalog drift gate — the family inventory and the four v2 surfaces as DATA"),
    (8, "house_rules", "the house-law constant gate — browser UA + version header + AF table pinned"),
    (9, "checklist_note", "the checklist gate — SMS phone number verified present before snapshot push"),
)

# The AF-AE-PROVPHONE-* autofail family, as the stage records it (the full
# family table lives in docs_u23.AF_CODES; house_rules pins every row against
# ENGINE-MANIFEST.json — stamped or PENDING).
AF_CODES = (
    ("AF-AE-PROVPHONE-NO-EXECUTE", 2,
     "provisioning (the create POST) or SMS verification (the send-test-message "
     "POST) was requested without the operator's explicit --execute (the Trevor "
     "gate) — a refusal, never a silent no-op and never a silent write"),
    ("AF-AE-PROVPHONE-READ-REFUSED", 3,
     "listing numbers for the location failed (scope / validation / edge block "
     "/ transport) — STOP (exit 2) or HELD (exit 3) per class, never a silent "
     "skip, never a provision-into-the-unknown"),
    ("AF-AE-PROVPHONE-CREATE-REFUSED", 3,
     "the POST /phones/numbers was rejected (validation / scope / edge block / "
     "transport), or the response carried no number id — STOP, HELD or MISMATCH "
     "per class, never recorded as provisioned"),
    ("AF-AE-PROVPHONE-VERIFY-REFUSED", 3,
     "the verify read-back or the send-test-message POST failed (scope / "
     "validation / edge / transport) — STOP or HELD per class, never a false pass"),
    ("AF-AE-PROVPHONE-VERIFY-STALLED", 3,
     "the verification read-back never confirmed sending-capable within the "
     "bounded window — HELD (exit 3), never a false pass"),
    ("AF-AE-PROVPHONE-READBACK-MISMATCH", 5,
     "the post-create read-back returned no number object for the created id — "
     "nothing is ever reported provisioned without read-back"),
    ("AF-AE-PROVPHONE-ATTACK", 4,
     "an attack fixture tripped the OFFLINE self-test (enforced violation)"),
)

# House exit-code contract (docs_u23.EXIT_CODES).
EXIT_CODES = {
    0: "verified success — all checks PASS (also plan / dry-run / self-test)",
    1: "unexpected error (top-level guard; never a secret leak)",
    2: "STOP refusal — label NOT SET / non-pit- value / usage / an ACTION "
       "(provision, send, verify) without --execute / a module missing from "
       "u23_modules/ (AF-AE-U23-ASSEMBLY-INCOMPLETE) / a genuine scope denial",
    3: "HELD — Convert and Flow API unreachable / verification not confirmed / "
       "upstream edge block (CF error 1010); retryable, never mislabeled as a "
       "scope problem",
    4: "self-test FAILED — an assertion in the OFFLINE self-test tripped "
       "(AF-AE-PROVPHONE-* / AF-AE-SMSVER-* / AF-AE-TEMPLATE-ATTACK family). "
       "A tamper NEVER masquerades as exit 1",
    5: "data or read-back mismatch — a create returned no number id / a verify "
       "read-back returned no number / a send returned 200 with no SID / the "
       "golden or attack fixture drifted; the fail-closed default",
}


class AssembleError(Exception):
    """A fail-closed refusal raised by the assembly itself — a missing
    u23_modules file, a module violating the entry-point contract, or a
    manifest-pending stage that cannot be written."""


# ---------------------------------------------------------------------------
# THE LAW SURFACES the family's fixtures import BY NAME from THIS module
# (`import provision_sms_phone as prov/phone`): SMS_ENABLED_KEYS, _mask_number,
# _mask_destination, _sms_enabled, list_phone_numbers, provision_action,
# plan_action, _attack_numbers. Each is a ONE-LINE delegate to the family
# module that OWNS the law (the U23 never re-implements a law — the fixtures
# pin this file as the single authority, so the law must live exactly here).
# ---------------------------------------------------------------------------
def _sms_enabled(number: dict) -> bool:
    """Does this number carry SMS capability? Presence/truthiness only, on the
    fixed key set — never any other field of the number object."""
    for k in SMS_ENABLED_KEYS:
        v = number.get(k)
        if v is not None:
            return bool(v)
    return False


def _mask_number(num: str) -> str:
    """A non-reversible marker for a phone number: last 4 digits only."""
    num = (num or "").strip()
    digits = "".join(ch for ch in num if ch.isdigit())
    if len(digits) >= 4:
        return "...%s" % digits[-4:]
    return "(short number)"


def _mask_destination(dest: str) -> str:
    """A non-reversible marker for a verification destination: last 2 digits."""
    dest = (dest or "").strip()
    digits = "".join(ch for ch in dest if ch.isdigit())
    if len(digits) >= 2:
        return "...%s" % digits[-2:]
    return "(no digits)"


def list_phone_numbers(client, location_id: str):
    """GET /phones/numbers?locationId=<loc>. READ-ONLY. Returns a list of
    number dicts (each entry is only ever used for the SMS-capable marker and
    the masked number; no other field is read)."""
    out = client._request("GET", "/phones/numbers", query={"locationId": location_id})
    if isinstance(out, dict):
        for key in ("numbers", "data", "results"):
            v = out.get(key)
            if isinstance(v, list):
                return v
        return []
    if isinstance(out, list):
        return out
    return []


def provision_action(client, location_id: str, *, number_id: str = "",
                     verify_destination: str = "", execute: bool = False,
                     poll_interval_s: int = 5, poll_timeout_s: int = 120,
                     out=None, jsonout=None) -> int:
    """The GHL-gated provisioning ACTION, delegated BY NAME to the owning
    module (provision_action.py — the family never re-implements a law).
    GET-first idempotent; a create and the send-test-message POST run ONLY
    under --execute; the created number is read back before any report claims
    provisioned (a missing read-back is a MISMATCH, exit 5)."""
    return _dispatch("provision_action", "provision_action")(
        client, location_id,
        number_id=number_id, verify_destination=verify_destination,
        execute=execute, poll_interval_s=poll_interval_s,
        poll_timeout_s=poll_timeout_s, out=out, jsonout=jsonout)


def plan_action(client, location_id: str, *, out=None, jsonout=None) -> int:
    """READ-ONLY plan: list the location's numbers, report what provisioning
    WOULD do. No network in dry-run (plan is the dry-run body)."""
    return _dispatch("provision_action", "plan_action")(
        client, location_id, out=out, jsonout=jsonout)


def _attack_numbers():
    """The attack listing fixture — the numbers carried by the family's
    attack fixtures (provision_action._attack_numbers, never a live entry).
    Synthetic material only; a live id or number is never a fixture."""
    return _dispatch("provision_action", "_attack_numbers")()


# The field that marks a number as SMS-capable in the listing surface. The
# module reads presence/truthiness only, never any other field of a number.
SMS_ENABLED_KEYS = ("smsEnabled", "sms_enabled")


# ---------------------------------------------------------------------------
# The 16-file assembly — import EVERY u23_modules file BY NAME. The empty
# package init is imported for the namespace guarantee (importing the package
# succeeds only if __init__.py is intact); the check modules come through
# main_skeleton.load_modules (the ONE entry-point contract); the fixture /
# reporter / docs modules are imported for their surfaces and their self-test
# batteries; the three pytest batteries are imported for their provenance
# (their tests run as the independent pytest battery).
# ---------------------------------------------------------------------------
def _load_package() -> None:
    """Prove the package namespace container imports clean."""
    importlib.import_module("u23_modules")


def load_skeleton() -> object:
    """The main_skeleton dispatcher module (imported BY NAME)."""
    return importlib.import_module("u23_modules.main_skeleton")


def _dispatch(name: str, surface: str):
    """Import one u23_modules module BY NAME and return its surface (module
    attribute). Fail-closed: a missing module or a missing surface raises
    AssembleError (STOP) — the aggregate NEVER passes with a law silently
    absent."""
    try:
        mod = importlib.import_module("u23_modules.%s" % name)
    except ImportError as exc:
        raise AssembleError(
            "u23_modules file %s.py is missing — the 16-file assembly is "
            "incomplete (fail-closed: no module is ever skipped): %s"
            % (name, exc)) from exc
    attr = getattr(mod, surface, None)
    if attr is None:
        raise AssembleError(
            "u23_modules.%s does not expose %r — the U23 surface contract "
            "drifted" % (name, surface))
    return attr


def load_all_modules(out=None) -> dict:
    """Import every one of the 16 u23_modules files. Returns {name: module}.
    Fail-closed: a missing file or a module violating its contract raises
    AssembleError (STOP) — the aggregate NEVER passes with a module silently
    absent."""
    out = out or sys.stderr
    _load_package()
    # The check modules resolve BY NAME (importlib.import_module(name) with
    # bare names inside main_skeleton.load_modules) — their own directory must
    # sit on sys.path for that to resolve, exactly as running the skeleton as
    # a script puts its own directory first.
    if str(MODULES_DIR) not in sys.path:
        sys.path.insert(0, str(MODULES_DIR))

    skeleton = load_skeleton()
    try:
        dispatched = skeleton.load_modules()
    except skeleton.SkeletonError as exc:
        raise AssembleError("check-module load failed: %s" % exc) from exc

    modules = {"main_skeleton": skeleton}
    modules.update(dispatched)
    missing = []
    # The family companion (the worked example) and the pytest batteries are
    # imported directly here (their self-tests prove their surfaces); the
    # worked example exercises the dispatch through the family's own modules.
    for name in ("example_usage",) + TEST_MODULES:
        try:
            modules[name] = importlib.import_module("u23_modules." + name)
        except ImportError:
            missing.append(name)
    if missing:
        raise AssembleError(
            "u23_modules file(s) not found: %s — the 16-file assembly is "
            "incomplete (fail-closed: no module is ever skipped)"
            % ", ".join(missing))
    if len(modules) != 15:
        raise AssembleError(
            "assembly loaded %d modules, expected 15 (main_skeleton + 10 "
            "dispatch modules + 1 companion + 3 pytest batteries)"
            % len(modules))
    return modules


# ---------------------------------------------------------------------------
# Offline self-test — run EVERY module's own battery (golden PASS / attack
# FAIL), plus the main_skeleton dispatcher battery, plus this assembler's own
# assembly assertions, plus the three sibling pytest batteries. NO network, NO
# credentials. Exit 4 on any failure. The task's three required discriminations
# are pinned explicitly: the golden has-phone state PASSES, the no-phone
# listing is refused (dry-run reports provision_needed TRUE), and the sms-
# failed attack FAILS while the golden 200-send control PASSES.
# ---------------------------------------------------------------------------
def _module_self_test(module, name: str, out) -> None:
    st = getattr(module, "self_test", None)
    if not callable(st):
        raise AssertionError(
            "module %s does not expose 'self_test' — every u23_modules "
            "module must prove itself offline" % name)
    dev = io.StringIO()
    try:
        rc = st(out=dev)
    except TypeError:
        rc = st()
    out.write(dev.getvalue())
    if rc != EX_OK:
        raise AssertionError("%s self_test returned exit %d" % (name, rc))


def _run_pytest(modules: dict, out) -> None:
    """The three sibling pytest batteries — the independent proof that the
    phone-law family (list / provision / send-verify) is pinned offline. A
    failed battery is an enforced violation, never a silent skip.

    ONE test is deselected from THIS vantage: test_sms_verifier's
    test_sibling_family_self_tests_stay_green spawns THIS driver as a
    subprocess (provision_sms_phone.py self-test). Run from inside this
    driver's own pytest run the two would recurse (driver -> pytest ->
    sibling test -> driver -> ...) until the subprocess timeout kills the
    chain. The test still ships and still runs from every OUTSIDE vantage
    (standalone pytest, CI, a parent driver) — where it proves this
    driver's self-test end-to-end — and with the deselect in place the
    nested driver run it spawns completes cleanly instead of recursing."""
    pkg = Path(modules["test_phone_lister"].__file__).resolve().parent
    tests = [str(pkg / (name + ".py")) for name in TEST_MODULES]
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "-q",
         "-k", "not sibling_family_self_tests_stay_green", *tests],
        capture_output=True, text=True, timeout=600)
    if proc.stdout:
        out.write(proc.stdout)
    if proc.returncode != 0:
        raise AssertionError(
            "pytest battery failed (exit %d): %s"
            % (proc.returncode, (proc.stderr or "").strip()[-400:]))


def _golden_phone_listing() -> dict:
    """The OFFLINE golden phone-provisioned control payload — the listing
    carrying EXACTLY ONE SMS-capable number, the state the GET-first
    idempotency law verifies without re-provisioning. Synthetic material
    only; every id and number masked; never a network call."""
    return {
        "numbers": [{
            "id": "num_GOLDEN", "phoneNumber": "+12025559876",
            "smsEnabled": True,
        }],
    }


def _empty_listing() -> dict:
    """The OFFLINE no-phone attack payload — a /phones/numbers listing with
    NO number at all, the exact shape a live GET /phones/numbers serves, the
    state the operator must provision. Synthetic material only; never a
    network call."""
    return {"numbers": []}


def self_test(modules: dict, out=None, *, run_pytest: bool = True) -> int:
    """OFFLINE self-test: the modules' own golden+attack batteries plus the
    dispatcher battery, the assembly's file-count assertions, the family-law
    gate (golden has-phone PASS / no-phone dry-run / sms-failed attack FAIL),
    and the sibling pytest batteries. Any failure is exit 4 (AF-AE-PROVPHONE-
    ATTACK family) — a tamper NEVER masquerades as exit 1. On a clean pass the
    manifest-pending stage is written."""
    out = out or sys.stderr
    dev = io.StringIO()
    try:
        # 1. the assembly is complete: exactly the 16 files exist.
        on_disk = sorted(p.name for p in MODULES_DIR.glob("*.py"))
        expected = sorted(name for name, _ in U23_MODULES)
        assert on_disk == expected, (
            "u23_modules tree drifted: disk carries %d files, the 16-file "
            "assembly contract names %d (%s)"
            % (len(on_disk), len(expected),
               ", ".join(sorted(set(on_disk) ^ set(expected)))))
        # 2. every module's own battery passes (golden PASS / attack FAIL).
        #    The dispatch modules and the family companion (the worked
        #    example) all expose self_test(out=None) -> int; the pytest
        #    batteries are proven by the pytest run (step 7), never by a
        #    phantom self_test contract.
        for name, mod in modules.items():
            if name in ("main_skeleton",) + TEST_MODULES:
                continue  # skeleton battery in step 3; pytest batteries in step 7
            _module_self_test(mod, name, dev)
        # 3. the dispatcher battery passes (main_skeleton.self_test runs the
        #    dispatch modules through the one-entry-point contract, the
        #    execute-gate law, the browser-UA law and the credential law).
        skeleton = modules["main_skeleton"]
        dispatch_only = {k: v for k, v in modules.items()
                         if k in DISPATCH_MODULE_NAMES}
        sk_rc = skeleton.self_test(dispatch_only, out=dev)
        assert sk_rc == EX_OK, \
            "main_skeleton dispatcher self-test returned exit %d" % sk_rc
        # 4. the family-law gate, exercised through the modules' own surfaces:
        #    (a) the golden has-phone state PASSES — the idempotent no-op,
        #    (b) the no-phone listing is REFUSED and the dry-run plan reports
        #        provision_needed TRUE (never a clean read, never a silent
        #        fallback), (c) the sms-failed attack FAILS every SMS gate
        #        while the golden 200-send control PASSES — the pass/fail
        #        splits discriminate the ONE-variable boundaries, never a
        #        broken instrument.
        golden = modules["golden_has_phone"]
        no_phone = modules["attack_no_phone"]
        sms_failed = modules["attack_sms_failed"]
        # 4a. golden has-phone -> PASS (exit 0), never a re-provision.
        with _redirect_stdout(io.StringIO()):
            rc = golden.payload(None, out=io.StringIO())
        assert rc == EX_OK, \
            "the golden has-phone state must PASS (exit 0), got %s" % rc
        # 4b. no-phone: the empty listing is REFUSED up front — never a clean
        #     read; and the dry-run plan (the module's own plan surface)
        #     reports provision_needed TRUE for a no-phone listing.
        try:
            no_phone.verify(_empty_listing())
            raise AssertionError("the empty listing was NOT refused")
        except no_phone.NoPhoneError:
            pass
        with _redirect_stdout(io.StringIO()):
            rc = no_phone.payload(_empty_listing(), out=io.StringIO())
        assert rc == EX_STOP, \
            "the no-phone payload without --execute must STOP (exit 2), got %s" % rc
        plan = no_phone.dry_run(_empty_listing())
        assert plan.get("provision_needed") is True, \
            "the no-phone dry-run must report provision_needed TRUE: %s" % plan
        # 4c. sms-failed attack: the non-200 send MUST FAIL (exit 5) while the
        #     golden 200-send control PASSES (exit 0).
        rc = sms_failed.verify_send(sms_failed.ATTACK_SEND_RECORD,
                                    out=io.StringIO())
        assert rc == EX_MISMATCH, \
            "the sms-failed attack must FAIL (exit 5), got %s" % rc
        rc = sms_failed.verify_send(sms_failed.GOLDEN_SEND_RECORD,
                                    out=io.StringIO())
        assert rc == EX_OK, \
            "the golden 200-send control must PASS (exit 0), got %s" % rc
        # 5. the never-a-real-token classifier (the masked-marker law):
        #    markers are non-reversible and never leak a full value.
        assert _mask_number("+12025559876") == "...9876"
        assert _mask_number("") == "(short number)"
        assert _mask_destination("+12025550123") == "...23"
        assert _sms_enabled(_golden_phone_listing()["numbers"][0]) is True
        assert _sms_enabled({}) is False
        # 6. docs_u23's catalog is the assembly's catalog (4 surfaces, 14
        #    modules, exit codes 0..5 — its self-test already pinned the
        #    counts; here we pin the shared constants).
        docs = modules["docs_u23"]
        assert len(docs.surfaces()) >= 4, \
            "docs_u23 surface count drifted below the 4-surface contract"
        assert len(docs.modules()) >= 14, \
            "docs_u23 module count drifted below the 14-module contract"
        assert len(docs.af_codes()) >= 22, \
            "docs_u23 af-code count drifted below the 22-row family table"
        # 7. the sibling pytest batteries (the independent proof).
        if run_pytest:
            _run_pytest(modules, dev)
    except AssertionError as exc:
        sys.stderr.write("[provision_sms_phone] SELF-TEST FAILED "
                         "(AF-AE-PROVPHONE-ATTACK family): %s\n" % exc)
        return EX_VIOLATION
    except AssembleError as exc:
        sys.stderr.write("[provision_sms_phone] SELF-TEST FAILED "
                         "(AF-AE-PROVPHONE-ATTACK family): %s\n" % exc)
        return EX_VIOLATION

    out.write(dev.getvalue())
    out.write("[provision_sms_phone] assembled self-test: OK (16 u23_modules "
              "files imported, 11 module batteries + dispatcher battery + "
              "family-law gate [golden has-phone PASS / no-phone dry-run / "
              "sms-failed attack FAIL + golden control PASS] + 3 pytest "
              "batteries + assembly assertions all pass)\n")
    return EX_OK


class _redirect_stdout:
    """Minimal context manager (house style: no pytest dependency in the
    dispatch path)."""

    def __init__(self, buf):
        self._buf = buf
        self._old = None

    def __enter__(self):
        self._old = sys.stdout
        sys.stdout = self._buf
        return self._buf

    def __exit__(self, *exc):
        sys.stdout = self._old
        return False


# ---------------------------------------------------------------------------
# Offline plan — no network, no credentials. The dispatcher's plan, with the
# assembly's stage-record on the side. Prints ONE JSON object on stdout.
# ---------------------------------------------------------------------------
def dry_run(modules: dict, out=None) -> int:
    out = out or sys.stderr
    skeleton = modules["main_skeleton"]
    with _redirect_stdout(io.StringIO()):
        rc = skeleton.plan(modules, out=out)
    if rc != EX_OK:
        return rc
    print(json.dumps({
        "contract": "anthology-engine-u23-dispatch-plan",
        "schema_version": 1,
        "kind": "dry-run",
        "location": LOCATION_BY_LABEL,
        "location_masked": "BY-LABEL",
        "gates": [name for name, _ in
                  getattr(skeleton, "LIVE_GATES", ())],
        "modules": [name for name, _ in U23_MODULES],
        "provision_needed": True,
        "dry_run": True,
        "note": "offline plan only — no network, no credential needed; a "
                "LIVE read must ride reg.CafClient (CAF_BROWSER_UA on every "
                "request — CF 1010 law); the PROVISIONING ACTION requires "
                "--execute (Trevor-gated) and is create-only-absent with a "
                "post-create read-back",
    }, indent=2, sort_keys=True))
    out.write("[provision_sms_phone] dry-run plan: OK (offline — no network, "
              "no credential needed; an SMS-capable number already present "
              "live is an idempotent no-op, never re-provisioned)\n")
    return EX_OK


# ---------------------------------------------------------------------------
# Live dispatch — the main_skeleton's fail-closed aggregate over the fixed
# gate order. The live READ is GHL-gated; the tooling ships now. The
# PROVISIONING ACTION (provision / verify) requires --execute (the Trevor
# gate), enforced at the CLI surface before any credential resolution.
# ---------------------------------------------------------------------------
def verify_live(modules: dict, location_id: str, *, execute: bool = False,
                out=None) -> int:
    out = out or sys.stderr
    skeleton = modules["main_skeleton"]
    return skeleton.verify_live(modules, location_id, execute=execute, out=out)


# ---------------------------------------------------------------------------
# Manifest-pending stage — manifest-pending/u23.json. Written ONLY after a
# PASS (self-test pass or dry-run plan pass); a FAIL/HELD/STOP run writes
# nothing. The record is the machine-readable input to a later manifest
# re-stamp — the ENGINE-MANIFEST.json / ENGINE-PIN.sha256 / verify.sh are
# NEVER touched here.
# ---------------------------------------------------------------------------
def _pending_payload(kind: str, *, verdict: str = "PASS") -> dict:
    return {
        "contract": "anthology-engine-u23-sms-phone",
        "schema_version": 1,
        "kind": kind,  # "self-test" | "dry-run" | "verify"
        "verdict": verdict,
        "script": "provision_sms_phone.py",
        "authored_by": "U23",
        "u23_modules": [
            {"name": name, "role": role} for name, role in U23_MODULES
        ],
        "check_modules": list(DISPATCH_MODULE_NAMES),
        "verified_items": [
            {"item": i, "id": item_id, "title": title}
            for i, item_id, title in VERIFIED_ITEMS
        ],
        "af_codes": [
            {"code": code, "exit": exit_code, "meaning": meaning}
            for code, exit_code, meaning in AF_CODES
        ],
        "exit_codes": EXIT_CODES,
        "checks": {},
        "fail_closed": {
            "any_fail": False,
            "note": "the no-phone listing is refused UP FRONT "
                    "(AF-AE-PROVPHONE-NO-PHONE) and the non-200 send attack "
                    "FAILS every SMS-verification gate with the golden "
                    "200-send control PASSING — the pass/fail splits "
                    "discriminate the ONE-variable boundaries, never a "
                    "broken instrument; the PROVISIONING ACTION requires "
                    "--execute (Trevor-gated), never a silent write.",
        },
    }


def write_pending(payload: dict, *, mode: str = "self-test", out=None) -> None:
    """Write manifest-pending/u23.json (fail-closed: only after a PASS).

    The directory is created if absent; the file is written atomically
    (temp + rename) so a crash mid-write never leaves a partial stage. The
    ENGINE-MANIFEST.json / ENGINE-PIN.sha256 / verify.sh are NEVER touched."""
    out = out or sys.stderr
    try:
        PENDING_DIR.mkdir(parents=True, exist_ok=True)
        tmp = PENDING_DIR / ("u23.json.tmp-%d" % os.getpid())
        tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n",
                       encoding="utf-8")
        tmp.replace(PENDING_U23)
    except OSError as exc:
        raise AssembleError("cannot write %s: %s" % (PENDING_U23, exc)) from exc
    out.write("[provision_sms_phone] manifest-pending stage written: %s (%s)\n"
              % (PENDING_U23, mode))


# ---------------------------------------------------------------------------
# CLI — house shape: --dry-run / --self-test / --json accepted as flags AND
# as a positional subcommand (--self-test / --selftest normalize exactly as
# anthology_registry.py and the U02..U10_U13 siblings). The PROVISIONING
# ACTION is a positional subcommand ('provision' / 'verify') that REQUIRES
# --execute (the Trevor gate), enforced before any credential resolution.
# ---------------------------------------------------------------------------
def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="provision_sms_phone.py",
        description="The U23 GHL-gated LeadConnector SMS phone provisioner "
                    "assembled from the 16 u23_modules files: offline "
                    "self-test battery (golden has-phone PASS / no-phone "
                    "dry-run / sms-failed attack FAIL), offline plan, and "
                    "the Trevor-gated PROVISIONING ACTION for the client's "
                    "Convert and Flow location (Skill 59) — one CLI, the "
                    "manifest-pending stage written after a PASS.")
    ap.add_argument("--location-id", default="",
                    help="override the Convert and Flow location id "
                         "(default: the CLIENT-standard location labels "
                         "CONVERT_AND_FLOW_LOCATION_ID / "
                         "GOHIGHLEVEL_LOCATION_ID / GHL_LOCATION_ID; "
                         "masked on every surface, never printed in full)")
    ap.add_argument("--dry-run", action="store_true",
                    help="offline plan only — no network, no credential "
                         "(default: live verify)")
    ap.add_argument("--json", action="store_true",
                    help="emit a machine-readable summary on stdout (default "
                         "on for verify/plan)")
    ap.add_argument("--execute", action="store_true",
                    help="the Trevor gate for the PROVISIONING ACTION — "
                         "REQUIRED before any number is provisioned or any "
                         "message is sent; without it the ACTION is a STOP "
                         "(exit 2, AF-AE-PROVPHONE-NO-EXECUTE), never a "
                         "silent write; with it, provisioning is "
                         "create-only-absent with a post-create read-back")
    ap.add_argument("--no-pytest", action="store_true",
                    help="skip the sibling pytest batteries inside --self-test "
                         "(dispatch self-test only; the offline batteries "
                         "still run)")
    ap.add_argument("--selftest", "--self-test", dest="self_test",
                    action="store_true",
                    help="run the offline self-test (golden + attack "
                         "fixtures, pytest batteries) and exit")
    ap.add_argument("cmd", nargs="?", choices=["verify", "plan", "provision",
                                               "self-test"],
                    help="positional subcommand form (verify / plan / "
                         "provision / self-test)")

    if argv is None:
        argv = sys.argv[1:]
    argv = list(argv)
    # Normalize --self-test / --selftest -> --self-test so the flag form never
    # collides with the positional subcommand form.
    if "--self-test" in argv and "--selftest" not in argv:
        argv = ["--self-test" if a == "--self-test" else a for a in argv]
    args = ap.parse_args(argv)
    # Positional subcommand form (house shape): self-test -> the offline
    # battery; plan -> the offline dry-run.
    if args.cmd == "self-test":
        args.self_test = True
    elif args.cmd == "plan":
        args.dry_run = True

    try:
        modules = load_all_modules()

        if args.self_test:
            rc = self_test(modules, out=sys.stderr,
                           run_pytest=not args.no_pytest)
            if rc == EX_OK:
                write_pending(_pending_payload("self-test"), mode="self-test")
            return rc

        if args.dry_run:
            rc = dry_run(modules, out=sys.stderr)
            if rc == EX_OK:
                write_pending(_pending_payload("dry-run"), mode="dry-run")
            return rc

        if args.cmd == "provision" or args.cmd == "verify":
            # The Trevor gate, enforced at the CLI surface: a PROVISIONING
            # ACTION (or the SMS verification send) without --execute is a
            # STOP (exit 2), never a silent no-op and never a silent write.
            # WITH --execute the family's create-only-absent contract holds.
            if not args.execute:
                reg._stop(sys.stderr,
                          "%s REFUSED: no --execute (the Trevor gate)."
                          % args.cmd,
                          ["An ACTION without --execute is a STOP "
                           "(AF-AE-PROVPHONE-NO-EXECUTE / "
                           "AF-AE-SMSVER-NO-EXECUTE), never a silent "
                           "write. Re-run with --execute to authorize the "
                           "ACTION — it is create-only-absent with a "
                           "post-create read-back (marker %s)."
                           % reg._mask_location(args.location_id or "BY-LABEL")])
                return EX_STOP
            return verify_live(modules, args.location_id,
                               execute=True, out=sys.stderr)

        # ---- live aggregate (PIT-gated for the live surfaces) ----
        rc = verify_live(modules, args.location_id, execute=False,
                         out=sys.stderr)
        if rc == EX_OK:
            write_pending(_pending_payload("verify"), mode="verify")
        return rc

    except reg.ScopeDenied as exc:
        sys.stderr.write("[provision_sms_phone] STOP: %s\n" % exc)
        return EX_STOP
    except reg.UpstreamBlockedError as exc:
        sys.stderr.write("[provision_sms_phone] HELD: %s\n" % exc)
        return EX_HELD
    except reg.CafUnreachable as exc:
        sys.stderr.write("[provision_sms_phone] HELD: %s\n" % exc)
        return EX_HELD
    except AssembleError as exc:
        sys.stderr.write("[provision_sms_phone] STOP/FAIL: %s\n" % exc)
        return EX_STOP
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001 — top-level guard, never leaks a secret
        sys.stderr.write("[provision_sms_phone] unexpected error: %s: %s\n"
                         % (type(exc).__name__, exc))
        return EX_ERR


if __name__ == "__main__":
    sys.exit(main())
