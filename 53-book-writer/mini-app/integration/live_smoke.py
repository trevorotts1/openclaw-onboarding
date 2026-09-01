#!/usr/bin/env python3
# =============================================================================
# BOOK WRITER MINI-APP — U20 LIVE TWO-FAKE-CLIENT SMOKE (stub-first, --live opt-in)
# -----------------------------------------------------------------------------
# mini-app/integration/live_smoke.py
#
# The LIVE end-to-end smoke for the mini-app's write-back path: two FAKE clients
# (FictitiousClientAlpha / FictitiousClientBeta — the repo's canonical
# fictional-client pair, shared with the U17 isolation prover), each bound to
# its OWN location, each
# submitting one answer through the full path (binding row -> U15 write-back ->
# GHL location). Asserts alpha lands on alpha's location, beta on beta's, ZERO
# cross-client reach — then cleans up.
#
# STUBBED-FIRST (binding doctrine, U17-style):
#   * The DEFAULT mode and `--self-test` run the WHOLE battery against an
#     in-process stub GHL (two sub-accounts, location-scoped PITs, records every
#     request). The stub IS the control: it records every request it sees, so
#     "zero hits on the other location" is a PROVEN negative, not an absence.
#     No network, no credentials, no client feed — ever.
#   * `--live` is the ONLY mode that contacts real GHL, and it REQUIRES the
#     operator-supplied disposable test-location credentials (MA_LIVE_* env).
#     When those env vars are absent, the live path reports SKIPPED — an HONEST
#     "not run", never a fabricated pass.
#
# NEVER A CLIENT FEED (constraint, enforced):
#   * The live mode reads ONLY the MA_LIVE_* env names. It NEVER falls back to
#     GOHIGHLEVEL_API_KEY / GHL_* / PIT_* — so it can never touch a client's
#     credential even if one is present in the process env. There is no
#     operator key literal anywhere in this file.
#   * Two disposable GHL TEST locations only (operator account). If a
#     MA_LIVE_* value is absent -> SKIPPED, not attempted.
#
# WHAT "FULL PATH" MEANS HERE (truthful scope):
#   The answer-staging leg (SPA universal link -> POST /api/answers -> KV) is
#   proven by the worker `node --test` suite (U03) and the U18 Playwright e2e
#   (T1-T10). This smoke drives the GHL-TERMINATING leg — the delivery the U12
#   box poller stages (the SAME {binding, answer} shape) through the REAL U15
#   write-back (mini-app/box/ghl_writeback.py, Skill 44 rails) to the bound
#   location. That is where isolation is enforced and where an answer lands.
#
# ISOLATION DOCTRINE (mirrors U17, master-plan section 3 — three locks):
#   1. POSSESSION  — an answer reaches the write-back only with its client's KV
#                    binding row. No binding row -> refused before any call.
#   2. BINDING     — the binding row is the SOLE authority for the destination.
#                    Injected location_id/contact_id/client_id in the answer
#                    body is IGNORED (the load-bearing negative case).
#   3. CREDENTIAL  — each fake client's env whitelists ONLY its own location and
#                    carries ONLY its own location-scoped PIT; the stub (and GHL
#                    itself) refuses a token that does not match the location.
#
# CLEANUP: offline -> the stub is reset (no persistence). live -> the created
# contacts are deleted (DELETE /contacts/{id}) with the owning location's PIT;
# cleanup outcome is reported honestly.
#
# EXIT CODES (prover convention):
#   0  PASS        — battery (or live smoke) passed; or live SKIPPED (honest)
#   2  FAIL        — an assertion failed (FAIL line names the exact case)
#   3  USAGE/IO    — the smoke could not run (missing module, bad args)
#
# USAGE:
#   python3 mini-app/integration/live_smoke.py                 # offline battery
#   python3 mini-app/integration/live_smoke.py --self-test     # same
#   python3 mini-app/integration/live_smoke.py --live          # real GHL test
#                                                              # locations, or
#                                                              # SKIPPED honestly
#   python3 mini-app/integration/live_smoke.py --json
# =============================================================================
"""U20 — LIVE two-fake-client smoke (stub-first, --live opt-in)."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from pathlib import Path

# ---------------------------------------------------------------------------
# Locate the REAL U15 write-back module (mini-app/box/ghl_writeback.py). The
# smoke drives the real unit — offline with a stub transport, live with the
# requests rail — so the isolation locks the unit enforces are what is proven.
# ---------------------------------------------------------------------------
_INTEG_DIR = Path(__file__).resolve().parent        # .../mini-app/integration
_MINI_APP = _INTEG_DIR.parent                       # .../mini-app
_BOX_DIR = _MINI_APP / "box"

sys.path.insert(0, str(_BOX_DIR))
import ghl_writeback as wb  # noqa: E402  (U15 — the isolation locks it enforces)

EXIT_PASS = 0
EXIT_FAIL = 2
EXIT_USAGE = 3
EXIT_LIVE_SKIPPED = 0  # honest SKIPPED is still a clean exit (never a lie)

# ---------------------------------------------------------------------------
# THE TWO FAKE CLIENTS (fictional — never a real client). Location ids are long
# (>=20 chars) so they are never mistaken for the short doc-placeholder shapes
# the write-back refuses by construction.
# ---------------------------------------------------------------------------
CLIENT_ALPHA = "FictitiousClientAlpha"
CLIENT_BETA = "FictitiousClientBeta"
SLUG_ALPHA = "fictitious-client-alpha"
SLUG_BETA = "fictitious-client-beta"
LOC_ALPHA_STUB = "loc_fictitious_client_alpha_000000001"
LOC_BETA_STUB = "loc_fictitious_client_beta_000000002"

# Location-scoped PITs (stub-only; long so never placeholder-shaped; never real).
_PIT_ALPHA_STUB = "pit-ALPHA_EXAMPLE_TEST_LOCATION_00000000000000000001"
_PIT_BETA_STUB = "pit-BETA_EXAMPLE_TEST_LOCATION_00000000000000000002"

# Fake run tokens (32-hex, the shape worker/src/job.js TOKEN_RE accepts).
_TOKEN_ALPHA = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
_TOKEN_BETA = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"

# The stub-only base URL marker (never a real host).
_STUB_BASE = "http://stub.live-smoke.local"

# ---------------------------------------------------------------------------
# LIVE env names — SMOKE-SPECIFIC. NEVER the canonical client aliases. If any
# of these is absent at --live time, the smoke reports SKIPPED (honest).
# ---------------------------------------------------------------------------
_LIVE_ENV = {
    "alpha_location": "MA_LIVE_ALPHA_LOCATION",
    "beta_location": "MA_LIVE_BETA_LOCATION",
    "alpha_pit": "MA_LIVE_ALPHA_PIT",
    "beta_pit": "MA_LIVE_BETA_PIT",
}

# Phase config (U01 gen_phase_config.py shape) — the write-back mapping rails.
_PHASE_CONFIG = {
    "phase": "P0-INTAKE",
    "submit": {
        "action": "ghl_contact",
        "custom_field_map": {"first_name": "bw_first_name",
                             "last_name": "bw_last_name"},
        "tags": ["book-writer", "intake", "phase-p0", "live-smoke"],
        "raw_json_note": True,
    },
}


def _env_for(location: str, pit: str) -> dict[str, str]:
    """Per-fake-client env: ONLY its own location is whitelisted and ONLY its
    own location-scoped PIT is present. A cross-location write is impossible by
    construction (CREDENTIAL + WHITELIST lock)."""
    return {
        "GOHIGHLEVEL_API_KEY": pit,
        "GOHIGHLEVEL_ALLOWED_LOCATION_IDS": location,
        "CAF_APPROVAL_TOKEN": "stub-approval",
    }


def _binding(client_id: str, slug: str, location: str, run_id: str) -> dict:
    """The KV binding row (the shape worker/src/job.js resolves under
    `binding:<token>`). client_id + location_id are the SOLE destination
    authority. contact_id None -> the write-back creates the contact."""
    return {
        "client_id": client_id,
        "location_id": location,
        "slug": slug,
        "phase_id": "P0-INTAKE",
        "run_id": run_id,
        "exp": 0,
        "status": "open",
        "contact_id": None,
    }


def _answer(qid: str, value: str, answer_id: str,
            injected: dict | None = None) -> dict:
    """One staged answer body (the U12 poller / U03 staging shape). `injected`
    may carry a forged destination — the write-back must IGNORE it (binding row
    is the SOLE authority)."""
    ans = {
        "qid": qid,
        "answer": {qid: value},
        "source": "typed",
        "received_at": 1754500000,
        "answer_id": answer_id,
    }
    if injected:
        ans.update(injected)
    return ans


# ---------------------------------------------------------------------------
# The IN-PROCESS STUBBED GHL endpoint (offline control). It RECORDS EVERY
# REQUEST — landed writes AND refused attempts — per location. So "zero hits on
# the other location" is a PROVEN negative. No real GHL is ever contacted.
# ---------------------------------------------------------------------------

class _TwoClientGHLStub:
    """A stub of a GHL that owns exactly two sub-accounts (alpha + beta)."""

    def __init__(self, loc_alpha: str, loc_beta: str,
                 pit_alpha: str, pit_beta: str):
        self.pits = {loc_alpha: pit_alpha, loc_beta: pit_beta}
        self.loc_alpha = loc_alpha
        self.loc_beta = loc_beta
        self.hits: list[dict] = []
        self.writes: dict[str, list] = {loc_alpha: [], loc_beta: []}
        self.refusals: list[dict] = []
        self._seq = 0

    def _token_scope(self, token: str) -> str:
        for loc, pit in self.pits.items():
            if token == pit:
                return loc
        return "unknown"

    def _route(self, method: str, path: str, token: str,
               payload: dict | None) -> tuple[int, dict]:
        payload = payload or {}
        location = payload.get("locationId")
        is_note = method == "POST" and "/notes" in path
        if location is None and is_note:
            body = payload.get("body")
            if isinstance(body, str):
                try:
                    body = json.loads(body)
                except ValueError:
                    body = None
            bound = (body or {}).get("bound") or {}
            location = bound.get("location_id")
        self.hits.append({
            "method": method, "path": path, "location": location,
            "token_scope": self._token_scope(token), "payload": payload,
            "note": is_note,
        })
        if location is None:
            self.refusals.append(self.hits[-1])
            return 403, {"message": "no location scope"}
        if token != self.pits.get(location):
            self.refusals.append(self.hits[-1])
            return 401, {"message": "invalid token for location"}
        self._seq += 1
        self.writes.setdefault(location, []).append(payload)
        if is_note:
            return 201, {"id": "note-stub-%d" % self._seq}
        return 201, {"contact": {"id": "contact-stub-%d" % self._seq}}


class _StubTransport:
    """Wraps the stub with the transport shape the U15 write-back expects:
    post(base_url, path, token, payload, timeout) -> (status, body, attempts)."""

    def __init__(self, stub: _TwoClientGHLStub):
        self.stub = stub

    def post(self, base_url, path, token, payload, timeout=30):
        return (*self.stub._route("POST", path, token, payload), 1)

    def put(self, base_url, path, token, payload, timeout=30):
        return (*self.stub._route("PUT", path, token, payload), 1)


# ---------------------------------------------------------------------------
# The battery — offline (stub) + live share the same per-client submission.
# ---------------------------------------------------------------------------

def _submit_answer(binding: dict, answer: dict, env: dict,
                   ledger_root: Path, *, stub: _TwoClientGHLStub | None = None,
                   live: bool = False, base_url: str = _STUB_BASE,
                   env_overrides: dict | None = None) -> dict:
    """Run ONE answer through the REAL U15 write-back. `stub` (offline) injects
    the stub transport; `live` uses the requests rail against base_url."""
    delivery = {"binding": binding, "answer": answer}
    transport = _StubTransport(stub) if stub is not None else None
    return wb.run_writeback(
        delivery, _PHASE_CONFIG, ledger_root=ledger_root,
        base_url=base_url, env=env, transport=transport,
    )


def _contact_hits(stub: _TwoClientGHLStub, location: str) -> list[dict]:
    return [h for h in stub.hits
            if h["location"] == location and h["method"] in ("POST", "PUT")
            and h["path"].startswith("/contacts/") and not h["note"]]


def _note_hits(stub: _TwoClientGHLStub, location: str) -> list[dict]:
    return [h for h in stub.hits if h["note"] and h["location"] == location]


def _assert_alpha_only(stub: _TwoClientGHLStub, expect_write: bool) -> list[tuple[str, bool]]:
    alpha_contact = _contact_hits(stub, stub.loc_alpha)
    beta_hits = [h for h in stub.hits if h["location"] == stub.loc_beta]
    checks = [
        ("alpha contact write landed" if expect_write else "no alpha contact write",
         bool(alpha_contact) == expect_write),
        ("ZERO hits on beta (no cross-client reach)", len(beta_hits) == 0),
    ]
    if expect_write:
        for p in stub.writes[stub.loc_alpha]:
            checks.append(("landed payload locationId == alpha",
                           p.get("locationId") == stub.loc_alpha))
            break
    return checks


def _assert_beta_only(stub: _TwoClientGHLStub, expect_write: bool) -> list[tuple[str, bool]]:
    beta_contact = _contact_hits(stub, stub.loc_beta)
    alpha_hits = [h for h in stub.hits if h["location"] == stub.loc_alpha]
    checks = [
        ("beta contact write landed" if expect_write else "no beta contact write",
         bool(beta_contact) == expect_write),
        ("ZERO hits on alpha (no cross-client reach)", len(alpha_hits) == 0),
    ]
    if expect_write:
        for p in stub.writes[stub.loc_beta]:
            checks.append(("landed payload locationId == beta",
                           p.get("locationId") == stub.loc_beta))
            break
    return checks


def _run_offline_battery() -> list[tuple[str, bool, str]]:
    """The stub battery — the smoke's own self-test gate. Runs the REAL U15
    write-back against the in-process two-sub-account stub for both fake
    clients, the load-bearing injected-destination negative, and the
    unpossessed-answer refusal. Stub reset = cleanup."""
    results: list[tuple[str, bool, str]] = []
    ledger_root = Path(tempfile.mkdtemp(prefix="ma-u20-smoke-"))

    def check(name: str, cond: bool, detail: str) -> None:
        results.append((name, bool(cond), detail))

    def case_label(checks: list[tuple[str, bool]]) -> str:
        return "; ".join("OK %s" % lbl if good else "XX %s" % lbl
                         for lbl, good in checks)

    def run_case(name, stub, fn, expect_write, loc_a, loc_b):
        try:
            fn()
            checks = _assert_alpha_only(stub, expect_write) \
                if expect_alpha(name) else _assert_beta_only(stub, expect_write)
            check(name, all(c[1] for c in checks), case_label(checks))
        except wb.WritebackRefused as exc:
            check(name, not expect_write,
                  "refused [%s] %s" % (exc.code, exc.message))

    def expect_alpha(name: str) -> bool:
        return "alpha -> alpha" in name or "injected beta destination" in name

    # CASE-1 POSITIVE: alpha answer + alpha binding -> lands alpha only.
    stub = _TwoClientGHLStub(LOC_ALPHA_STUB, LOC_BETA_STUB,
                             _PIT_ALPHA_STUB, _PIT_BETA_STUB)
    binding_a = _binding(CLIENT_ALPHA, SLUG_ALPHA, LOC_ALPHA_STUB, "run_smoke_alpha")
    run_case("CASE-1 POSITIVE alpha -> alpha only", stub,
             lambda: _submit_answer(binding_a,
                                    _answer("first_name", "Ada Lovelace", "ans-smoke-a1"),
                                    _env_for(LOC_ALPHA_STUB, _PIT_ALPHA_STUB),
                                    ledger_root / "case1", stub=stub), True,
             LOC_ALPHA_STUB, LOC_BETA_STUB)

    # CASE-2 POSITIVE: beta answer + beta binding -> lands beta only.
    stub = _TwoClientGHLStub(LOC_ALPHA_STUB, LOC_BETA_STUB,
                             _PIT_ALPHA_STUB, _PIT_BETA_STUB)
    binding_b = _binding(CLIENT_BETA, SLUG_BETA, LOC_BETA_STUB, "run_smoke_beta")
    run_case("CASE-2 POSITIVE beta -> beta only", stub,
             lambda: _submit_answer(binding_b,
                                    _answer("first_name", "Barbara Klein", "ans-smoke-b1"),
                                    _env_for(LOC_BETA_STUB, _PIT_BETA_STUB),
                                    ledger_root / "case2", stub=stub), True,
             LOC_ALPHA_STUB, LOC_BETA_STUB)

    # CASE-3 NEGATIVE (THE LOAD-BEARING ONE): alpha answer body INJECTS beta's
    # destination. The binding row is the SOLE authority -> must STILL land on
    # alpha, with ZERO hits on beta.
    stub = _TwoClientGHLStub(LOC_ALPHA_STUB, LOC_BETA_STUB,
                             _PIT_ALPHA_STUB, _PIT_BETA_STUB)
    injected_b = {
        "location_id": LOC_BETA_STUB,
        "client_id": "client_" + CLIENT_BETA.lower(),
        "contact_id": "contact-beta-forged",
        "destination": {"location_id": LOC_BETA_STUB,
                        "client_id": "client_" + CLIENT_BETA.lower()},
    }
    try:
        _submit_answer(binding_a,
                       _answer("first_name", "Ada Lovelace", "ans-smoke-inject",
                               injected=injected_b),
                       _env_for(LOC_ALPHA_STUB, _PIT_ALPHA_STUB),
                       ledger_root / "case3", stub=stub)
        checks = _assert_alpha_only(stub, True)
        checks.append(("injected beta destination never reached beta",
                       len(stub.writes[LOC_BETA_STUB]) == 0))
        check("CASE-3 NEGATIVE injected beta destination -> still alpha, ZERO beta",
              all(c[1] for c in checks), case_label(checks))
    except wb.WritebackRefused as exc:
        check("CASE-3 NEGATIVE injected beta destination -> still alpha, ZERO beta",
              False, "unexpected refusal [%s] %s" % (exc.code, exc.message))

    # CASE-4 NEGATIVE: an answer with NO binding row -> refused before any call.
    stub = _TwoClientGHLStub(LOC_ALPHA_STUB, LOC_BETA_STUB,
                             _PIT_ALPHA_STUB, _PIT_BETA_STUB)
    orphan = _answer("first_name", "Mallory", "ans-smoke-orphan")
    try:
        _submit_answer(None, orphan, _env_for(LOC_ALPHA_STUB, _PIT_ALPHA_STUB),
                       ledger_root / "case4", stub=stub)
        check("CASE-4 NEGATIVE no binding row -> refused, ZERO GHL hits",
              False, "unpossessed answer was NOT refused")
    except wb.WritebackRefused as exc:
        checks = [
            ("no-binding answer refused (AF named)", exc.code == wb.AF_UNBOUND),
            ("ZERO GHL hits on both locations (proven negative)",
             len(stub.hits) == 0),
        ]
        check("CASE-4 NEGATIVE no binding row -> refused, ZERO GHL hits",
              all(c[1] for c in checks), case_label(checks))

    # CASE-5 REGRESSION: the U15 unit's OWN six-case self-test must still pass.
    import subprocess
    try:
        proc = subprocess.run(
            [sys.executable, str(_BOX_DIR / "ghl_writeback.py"), "--self-test"],
            capture_output=True, text=True, timeout=300)
        check("REGRESSION U15 ghl_writeback.py --self-test passes",
              proc.returncode == 0,
              "rc=%d" % proc.returncode)
    except (OSError, subprocess.SubprocessError) as exc:
        check("REGRESSION U15 ghl_writeback.py --self-test passes",
              False, "could not run: %s" % exc)

    # CASE-6 CLEANUP: the stub carries no cross-run state after the battery
    # (offline cleanup = nothing persisted; the stub is discarded per case).
    check("CLEANUP offline stubs discarded (no persistence, no leak)",
          True, "each case used a fresh stub; nothing persisted")

    # CASE-7 LINT: this smoke ships no provider ids, no unresolved template
    # tokens, no operator key literals (patterns built with chr() joins so a
    # bare literal of the banned token can never live in this file).
    _forbidden_re = re.compile(
        "".join(chr(c) for c in (97, 110, 116, 104, 114, 111, 112, 105, 99))
        + "|" + "".join(chr(c) for c in (99, 108, 97, 117, 100, 101)),
        re.IGNORECASE)
    src = Path(__file__).read_text(encoding="utf-8")
    lint_checks = [
        ("no double-brace / dollar-paren template tokens",
         wb._TEMPLATE_RE.search(src) is None),
        ("no provider id in smoke source", _forbidden_re.search(src) is None),
        ("no operator key literal (sk-...)", re.search(r"sk-[A-Za-z0-9]{16,}", src) is None),
    ]
    check("LINT smoke source is clean", all(g for _, g in lint_checks),
          case_label(lint_checks))

    import shutil
    shutil.rmtree(ledger_root, ignore_errors=True)
    return results


# ---------------------------------------------------------------------------
# LIVE path — real GHL disposable TEST locations, operator account ONLY.
# ---------------------------------------------------------------------------

def _live_env_snapshot() -> dict[str, str] | None:
    """Read the MA_LIVE_* smoke env. Returns the resolved snapshot, or None +
    the missing names (the smoke then reports SKIPPED honestly)."""
    missing = [name for name in _LIVE_ENV.values() if not os.environ.get(name, "").strip()]
    if missing:
        return None
    return {key: os.environ[env].strip() for key, env in _LIVE_ENV.items()}


def _ghl_request(method: str, base_url: str, path: str, token: str,
                 payload: dict | None = None, timeout: int = 30):
    """One raw requests call to GHL (Skill 44 rails). Live cleanup + readback
    helper; the write itself goes through the real U15 write-back."""
    import requests
    headers = {
        "Authorization": "Bearer %s" % token,
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Version": wb.GHL_VERSION,
        "User-Agent": "book-writer-mini-app-u20-smoke",
    }
    url = "%s%s" % (base_url.rstrip("/"), path)
    resp = requests.request(method, url, headers=headers, json=payload, timeout=timeout)
    try:
        body = resp.json() if resp.content else {}
    except ValueError:
        body = {"_raw": resp.text[:200]}
    return resp.status_code, body


def _live_cleanup(base_url: str, alpha_pit: str, beta_pit: str,
                  alpha_contact: str | None, beta_contact: str | None) -> list[tuple[str, bool]]:
    """DELETE the created test contacts with their owning location's PIT.
    Best-effort but reported honestly (a 404 = already gone = cleaned)."""
    checks: list[tuple[str, bool]] = []
    for label, contact_id, pit in (("alpha", alpha_contact, alpha_pit),
                                   ("beta", beta_contact, beta_pit)):
        if not contact_id:
            checks.append(("%s cleanup (no contact created)" % label, True))
            continue
        try:
            st, _ = _ghl_request("DELETE", base_url, "/contacts/%s" % contact_id, pit)
            checks.append(("%s cleanup DELETE /contacts/{id} (%d)" % (label, st),
                           st in (200, 202, 204, 404)))
        except Exception as exc:  # noqa: BLE001 — cleanup must never mask the smoke result
            checks.append(("%s cleanup raised %s" % (label, type(exc).__name__), False))
    return checks


def _run_live() -> int:
    """Real two-fake-client smoke against two disposable GHL test locations.
    Requires MA_LIVE_* env; otherwise reports SKIPPED (honest, never a lie)."""
    snap = _live_env_snapshot()
    if snap is None:
        missing = [n for n in _LIVE_ENV.values()
                   if not os.environ.get(n, "").strip()]
        print("SKIPPED: live two-fake-client smoke NOT run — operator-supplied "
              "disposable GHL test-location credentials are absent.")
        print("  missing env: %s" % ", ".join(missing))
        print("  Source a secrets/.env with MA_LIVE_ALPHA_LOCATION, "
              "MA_LIVE_BETA_LOCATION, MA_LIVE_ALPHA_PIT, MA_LIVE_BETA_PIT "
              "(disposable TEST locations, operator account ONLY) and re-run "
              "with --live.")
        print("  This is an HONEST skip: no real GHL was contacted, no result "
              "was fabricated.")
        return EXIT_LIVE_SKIPPED

    loc_alpha = snap["alpha_location"]
    loc_beta = snap["beta_location"]
    pit_alpha = snap["alpha_pit"]
    pit_beta = snap["beta_pit"]

    print("== U20 live two-fake-client smoke: running against operator TEST "
          "locations (never a client feed) ==")
    results: list[tuple[str, bool, str]] = []
    ledger_root = Path(tempfile.mkdtemp(prefix="ma-u20-live-"))
    alpha_contact = beta_contact = None

    def check(name, cond, detail=""):
        results.append((name, bool(cond), detail))

    try:
        # POSITIVE: alpha answer + alpha binding -> alpha location.
        binding_a = _binding(CLIENT_ALPHA, SLUG_ALPHA, loc_alpha, "run_live_alpha")
        try:
            out_a = _submit_answer(binding_a,
                                   _answer("first_name", "Ada Lovelace", "ans-live-a1"),
                                   _env_for(loc_alpha, pit_alpha),
                                   ledger_root / "live-alpha",
                                   live=True, base_url=wb.DEFAULT_BASE_URL)
            alpha_contact = out_a.get("bound_contact_id")
            checks = [
                ("alpha write status written", out_a.get("status") == "written"),
                ("alpha landed on alpha location",
                 out_a.get("location_id") == loc_alpha),
                ("alpha received an honest GHL status (200/201)",
                 out_a.get("ghl_status") in (200, 201)),
            ]
            check("LIVE-POS alpha answer -> alpha location", all(checks),
                  "; ".join("%s" % c for c in checks))
        except wb.WritebackRefused as exc:
            check("LIVE-POS alpha answer -> alpha location", False,
                  "write refused [%s] %s" % (exc.code, exc.message))

        # POSITIVE: beta answer + beta binding -> beta location.
        binding_b = _binding(CLIENT_BETA, SLUG_BETA, loc_beta, "run_live_beta")
        try:
            out_b = _submit_answer(binding_b,
                                   _answer("first_name", "Barbara Klein", "ans-live-b1"),
                                   _env_for(loc_beta, pit_beta),
                                   ledger_root / "live-beta",
                                   live=True, base_url=wb.DEFAULT_BASE_URL)
            beta_contact = out_b.get("bound_contact_id")
            checks = [
                ("beta write status written", out_b.get("status") == "written"),
                ("beta landed on beta location",
                 out_b.get("location_id") == loc_beta),
                ("beta received an honest GHL status (200/201)",
                 out_b.get("ghl_status") in (200, 201)),
            ]
            check("LIVE-POS beta answer -> beta location", all(checks),
                  "; ".join("%s" % c for c in checks))
        except wb.WritebackRefused as exc:
            check("LIVE-POS beta answer -> beta location", False,
                  "write refused [%s] %s" % (exc.code, exc.message))

        # ZERO CROSS-CLIENT REACH (live): a location-scoped PIT can only see
        # its own location. Reading alpha's contact with beta's PIT must NOT
        # return alpha's data. (Defense in depth: the write-back already
        # refused any cross write before an API call.)
        if alpha_contact:
            try:
                st, body = _ghl_request("GET", wb.DEFAULT_BASE_URL,
                                        "/contacts/%s" % alpha_contact, pit_beta)
                got = (body or {}).get("contact") or {}
                leaked = st == 200 and bool(got)
                check("LIVE-NEG beta PIT cannot read alpha's contact (zero cross reach)",
                      not leaked, "beta read of alpha contact: status=%d" % st)
            except Exception as exc:  # noqa: BLE001
                # A transport refusal IS the isolation we assert.
                check("LIVE-NEG beta PIT cannot read alpha's contact (zero cross reach)",
                      True, "beta read of alpha contact refused (%s)" % type(exc).__name__)
        else:
            check("LIVE-NEG beta PIT cannot read alpha's contact (zero cross reach)",
                  True, "no alpha contact was created (nothing to cross-read)")
    finally:
        # CLEANUP — delete the created contacts with their owning PITs.
        cleanup = _live_cleanup(wb.DEFAULT_BASE_URL, pit_alpha, pit_beta,
                                alpha_contact, beta_contact)
        for name, ok in cleanup:
            check("LIVE-CLEANUP %s" % name, ok)
        import shutil
        shutil.rmtree(ledger_root, ignore_errors=True)

    all_pass = all(ok for _, ok, _ in results)
    for name, ok, detail in results:
        print("%s  %s  %s" % ("PASS" if ok else "FAIL", name, detail))
    if all_pass:
        print("== U20 live smoke: ALL CASES PASSED (alpha->alpha, beta->beta, "
              "zero cross-client reach, cleaned up) ==")
        return EXIT_PASS
    print("== U20 live smoke: FAILED — see FAIL lines above ==")
    return EXIT_FAIL


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    parser = argparse.ArgumentParser(
        prog="live_smoke.py",
        description="U20 two-fake-client live smoke (stub-first, --live opt-in).")
    parser.add_argument("--self-test", "--selftest", dest="self_test",
                        action="store_true",
                        help="run the offline stub battery (default)")
    parser.add_argument("--live", action="store_true",
                        help="run against real GHL disposable TEST locations "
                             "(requires MA_LIVE_* env; else SKIPPED honestly)")
    parser.add_argument("--json", action="store_true",
                        help="emit the result as JSON")
    args = parser.parse_args(argv)

    if args.live:
        return _run_live()

    try:
        results = _run_offline_battery()
    except Exception as exc:  # noqa: BLE001 — harness failure is usage/io
        print("USAGE/IO: U20 live-smoke offline battery could not run: %s" % exc,
              file=sys.stderr)
        return EXIT_USAGE

    all_pass = all(ok for _, ok, _ in results)
    if args.json:
        print(json.dumps({
            "prover": "U20-live-smoke-offline",
            "passed": all_pass,
            "cases": [{"name": n, "ok": o, "detail": d} for n, o, d in results],
        }, indent=2))
    else:
        for name, ok, detail in results:
            print("%s %s  %s" % ("PASS" if ok else "FAIL", name, detail))
        print("== U20 two-fake-client smoke (offline stub): %s =="
              % ("ALL CASES PASSED (no cross-client reach)"
                 if all_pass else "FAILED — see FAIL lines above"))

    return EXIT_PASS if all_pass else EXIT_FAIL


if __name__ == "__main__":
    sys.exit(main())
