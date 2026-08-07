#!/usr/bin/env python3
# =============================================================================
# BOOK WRITER MINI-APP — U17 TWO-FAKE-CLIENT ISOLATION PROVER (HARD GATE)
# -----------------------------------------------------------------------------
# mini-app/prove/prove_mini_app_isolation.py
#
# THE HARD GATE OF THE WHOLE MINI-APP BUILD (MASTER-PLAN section 9 + section 3).
# It proves, with an in-process STUBBED GHL endpoint, that a run for ONE client
# can NEVER reach ANOTHER client's GHL sub-account — client A's answers NEVER
# land on client B's location, regardless of what the answer body claims.
#
# WHY THIS IS A PROVER, NOT A UNIT TEST:
#   * The GHL stub is IN-PROCESS and RECORDS EVERY REQUEST it sees (contact
#     writes, note writes, and refused/auth-failed attempts). That is what makes
#     "nothing landed on client B" a PROVEN NEGATIVE — the stub saw nothing for
#     B — instead of an unverifiable absence.
#   * Two FAKE clients (FictitiousClientAlpha -> location-alpha, FictitiousClientBeta
#     -> location-beta), each with their OWN KV binding row (the same
#     `binding:<token>` shape the Worker resolves in worker/src/job.js). The
#     binding row is the SOLE destination authority.
#   * The cases merge POSITIVE + NEGATIVE into one battery. The load-bearing
#     NEGATIVE injects client B's destination INTO client A's answer body and
#     demands the answer STILL lands on alpha with ZERO hits on beta.
#
# ISOLATION DOCTRINE (section 3, enforced end-to-end here):
#   1. POSSESSION — an answer reaches the write-back only with its client's KV
#      binding row. No binding row -> REFUSED before any call (zero stub hits).
#   2. BINDING — the server-side KV binding row is the SOLE authority for the
#      destination. client_id + location_id come ONLY from the binding row; any
#      injected location_id / contact_id / client_id / destination inside the
#      answer body is IGNORED (this is the property the hard negative proves).
#   3. CREDENTIAL + WHITELIST — each fake client's env whitelists ONLY its own
#      location and carries ONLY its own location-scoped PIT. Even a buggy
#      handler could not authenticate to the other client's location: the stub
#      additionally rejects any write whose bearer token does not match the
#      payload's location (defense in depth at the transport too).
#
# EXIT CODES (prover convention):
#   0  PASS      — every positive + negative case in the battery passed.
#   2  AUTOFAIL  — at least one case failed; the FAIL line names the EXACT case.
#   3  USAGE/IO  — the prover could not run (missing unit, bad args).
#
# USAGE:
#   python3 mini-app/prove/prove_mini_app_isolation.py [--self-test] [--json]
#
# No real GHL is ever contacted: the stub IS the transport. No real client
# names/credentials: FictitiousClientAlpha / FictitiousClientBeta and stub PITs only.
# No operator keys, no provider ids, no unresolved template tokens anywhere.
# =============================================================================
"""U17 — two-fake-client isolation prover (hard gate) over the U15 write-back."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

# ---------------------------------------------------------------------------
# Locate the U15 write-back module (mini-app/box/ghl_writeback.py). The prover
# drives the REAL unit through its injected-transport seam; the stub IS the
# transport, so the isolation locks the unit enforces are what is being proven.
# ---------------------------------------------------------------------------
_PROVE_DIR = Path(__file__).resolve().parent      # .../mini-app/prove
_MINI_APP = _PROVE_DIR.parent                     # .../mini-app
_BOX_DIR = _MINI_APP / "box"

sys.path.insert(0, str(_BOX_DIR))
import ghl_writeback as wb  # noqa: E402  (U15 — the isolation locks it enforces)

# Exit codes (prover convention, mirrored from _bw_common)
EXIT_PASS = 0
EXIT_AUTOFAIL = 2
EXIT_USAGE = 3

# ---------------------------------------------------------------------------
# The TWO FAKE CLIENTS (fictional — never a real client, never a real id).
# location ids are long (>=20 chars) so they are never mistaken for the short
# doc-placeholder shapes the write-back refuses by construction.
# ---------------------------------------------------------------------------
CLIENT_A = "FictitiousClientAlpha"
CLIENT_B = "FictitiousClientBeta"
LOC_ALPHA = "loc_alpha_example_client_0001"     # client A's own sub-account
LOC_BETA = "loc_beta_example_client_0002"       # client B's own sub-account

# Location-scoped PITs, one per fake sub-account (stub-only tokens; long so they
# are never placeholder-shaped; never a real credential).
_PIT_ALPHA = "pit-ALPHA_LOCATION_PIT_0000000000000000000000000001"
_PIT_BETA = "pit-BETA_LOCATION_PIT_0000000000000000000000000002"

# Fake run tokens (32-hex, the shape worker/src/job.js TOKEN_RE accepts at mint
# time — the KV binding row, not the token, is the authority).
_TOKEN_A = "a1b2c3d4e5f60718293a4b5c6d7e8f90"
_TOKEN_B = "f0e1d2c3b4a59687766554433221100f"

# ---------------------------------------------------------------------------
# THE TWO CLIENTS' OWN KV BINDING ROWS (`binding:<token>` — the same key shape
# worker/src/job.js resolves with kv.get("binding:" + token)). Each row binds
# its client to ITS OWN location. The prover resolves the delivery's binding
# ONLY from this store — never from the answer body.
# ---------------------------------------------------------------------------
_KV_BINDINGS = {
    "binding:" + _TOKEN_A: {
        "client_id": "client_fictitious_alpha",
        "location_id": LOC_ALPHA,
        "slug": "fictitious-client-alpha",
        "phase_id": "P0-INTAKE",
        "run_id": "run_alpha_u17",
        "exp": 0,
        "status": "open",
        "contact_id": None,
    },
    "binding:" + _TOKEN_B: {
        "client_id": "client_fictitious_beta",
        "location_id": LOC_BETA,
        "slug": "fictitious-client-beta",
        "phase_id": "P0-INTAKE",
        "run_id": "run_beta_u17",
        "exp": 0,
        "status": "open",
        "contact_id": None,
    },
}


def _kv_binding(token: str) -> dict | None:
    """Resolve a KV binding row by run token (mirrors job.js
    `kv.get("binding:" + token, {type:"json"})`). None = no binding row — the
    answer is unpossessed and must be refused."""
    return _KV_BINDINGS.get("binding:" + token)


# Phase config (U01 gen_phase_config.py shape) — the write-back mapping rails.
_PHASE_CONFIG = {
    "phase": "P0-INTAKE",
    "submit": {
        "action": "ghl_contact",
        "custom_field_map": {"first_name": "bw_first_name",
                             "last_name": "bw_last_name"},
        "tags": ["book-writer", "intake", "phase-p0"],
        "raw_json_note": True,
    },
}


def _answer(qid: str, value: str, answer_id: str,
            injected: dict | None = None) -> dict:
    """One staged answer body (U12 poller shape). `injected` may carry a forged
    destination (location_id / contact_id / client_id / destination) — the
    write-back must IGNORE every injected field: the binding row is the SOLE
    authority."""
    ans = {
        "qid": qid,
        "answer": {qid: value},
        "source": "typed",
        "received_at": 1754500000,
        "answer_id": answer_id,
    }
    if injected:
        ans.update(injected)  # location_id / contact_id / client_id / destination
    return ans


def _delivery(binding: dict | None, answer: dict) -> dict:
    """Build the delivery {binding, answer} handed to the U15 write-back. The
    binding is resolved from the client's own KV row (or None for an unpossessed
    answer)."""
    return {"binding": binding, "answer": answer}


def _env_for(location: str) -> dict[str, str]:
    """Per-fake-client env: ONLY its own location is whitelisted and ONLY its
    own location-scoped PIT is present. A cross-client write is impossible by
    construction (CREDENTIAL + WHITELIST lock)."""
    pit = _PIT_ALPHA if location == LOC_ALPHA else _PIT_BETA
    return {
        "GOHIGHLEVEL_API_KEY": pit,
        "GOHIGHLEVEL_ALLOWED_LOCATION_IDS": location,
        "CAF_APPROVAL_TOKEN": "stub-approval",
    }


# ---------------------------------------------------------------------------
# The IN-PROCESS STUBBED GHL endpoint (the control).
# It RECORDS EVERY REQUEST — landed writes AND refused attempts — per location.
# So "zero hits on beta" is a PROVEN negative: the stub was watching beta the
# whole time and saw nothing. No real GHL is ever contacted.
# ---------------------------------------------------------------------------

class _TwoClientGHLStub:
    """A stub of a GHL that owns exactly two sub-accounts (alpha + beta).

    Auth rule (location-scoped PIT, defense in depth): a request's bearer token
    must equal the PIT of the payload's locationId (or, for a note write that
    carries no locationId, the location bound inside the note body), else 401.
    The stub records every request in `hits`, lands approved writes in
    `writes[location]`, and keeps refused attempts in `refusals`.
    """

    def __init__(self):
        self.pits = {LOC_ALPHA: _PIT_ALPHA, LOC_BETA: _PIT_BETA}
        self.hits: list[dict] = []          # every request the stub received
        self.writes: dict[str, list] = {LOC_ALPHA: [], LOC_BETA: []}  # landed writes
        self.refusals: list[dict] = []      # requests the stub refused (401/403)

    def _token_scope(self, token: str) -> str:
        for loc, pit in self.pits.items():
            if token == pit:
                return loc
        return "unknown"

    def _route(self, method: str, path: str, token: str,
               payload: dict | None) -> tuple[int, dict]:
        """One write attempt against the stub. Returns (status, body)."""
        payload = payload or {}
        location = payload.get("locationId")
        is_note = method == "POST" and "/notes" in path
        if location is None and is_note:
            # A note write carries no locationId; the note body is the
            # system-of-record and embeds the BOUND location — parse it so the
            # note is attributed to the right client, never the injected one.
            body = payload.get("body")
            if isinstance(body, str):
                try:
                    body = json.loads(body)
                except ValueError:
                    body = None
            bound = (body or {}).get("bound") or {}
            location = bound.get("location_id")

        record = {
            "method": method,
            "path": path,
            "location": location,
            "token_scope": self._token_scope(token),
            "payload": payload,
            "note": is_note,
        }
        self.hits.append(record)

        if location is None:
            # A write with no resolvable location scope can never be attributed
            # to a client — refuse it and record it (never a cross-client write).
            self.refusals.append(record)
            return 403, {"message": "no location scope"}
        if token != self.pits.get(location):
            # The bearer token does not belong to the target location — the
            # transport itself refuses a cross-location write (defense in depth).
            self.refusals.append(record)
            return 401, {"message": "invalid token for location"}
        self.writes.setdefault(location, []).append(payload)
        if is_note:
            return 201, {"id": "note-stub"}
        return 201, {"contact": {"id": "contact-stub"}}


class _StubTransport:
    """Wraps the stub with the post_with_retry signature the U15 write-back
    expects: post(base_url, path, token, payload, timeout) -> (status, body,
    attempts)."""

    def __init__(self, stub: _TwoClientGHLStub):
        self.stub = stub

    def post(self, base_url, path, token, payload, timeout=30):
        status, body = self.stub._route(
            "POST", path, token, payload)
        return status, body, 1

    def put(self, base_url, path, token, payload, timeout=30):
        status, body = self.stub._route(
            "PUT", path, token, payload)
        return status, body, 1


# ---------------------------------------------------------------------------
# Per-case assertion helpers
# ---------------------------------------------------------------------------

def _contact_hits(stub: _TwoClientGHLStub, location: str) -> list[dict]:
    """Every contact write (POST /contacts/ or PUT /contacts/<id>) the stub
    saw that was attributed to `location`."""
    return [h for h in stub.hits
            if h["location"] == location
            and h["method"] in ("POST", "PUT")
            and h["path"].startswith("/contacts/")
            and not h["note"]]


def _note_hits(stub: _TwoClientGHLStub, location: str) -> list[dict]:
    return [h for h in stub.hits if h["note"] and h["location"] == location]


def _assert_alpha_only(stub: _TwoClientGHLStub, expect_write: bool) -> list[tuple[str, bool]]:
    """The core isolation assertion for a client-A case: the answer must land on
    alpha and ONLY alpha. Zero hits on beta is the load-bearing negative."""
    alpha_contact = _contact_hits(stub, LOC_ALPHA)
    beta_hits = [h for h in stub.hits if h["location"] == LOC_BETA]
    notes_alpha = _note_hits(stub, LOC_ALPHA)
    checks = [
        ("alpha contact write landed" if expect_write else "no alpha contact write",
         bool(alpha_contact) == expect_write),
        ("ZERO hits on beta (no cross-client reach)", len(beta_hits) == 0),
        ("note on alpha" if expect_write else "no note on alpha",
         bool(notes_alpha) == expect_write),
    ]
    if expect_write:
        # The landed payload's locationId must be alpha — the injected/bound
        # destination was ignored at the payload level.
        for p in stub.writes[LOC_ALPHA]:
            checks.append(("landed payload locationId == alpha",
                           p.get("locationId") == LOC_ALPHA))
            break
    return checks


def _assert_beta_only(stub: _TwoClientGHLStub, expect_write: bool) -> list[tuple[str, bool]]:
    """Mirror of _assert_alpha_only for a client-B case (alpha is the foreign
    location that must see ZERO hits)."""
    beta_contact = _contact_hits(stub, LOC_BETA)
    alpha_hits = [h for h in stub.hits if h["location"] == LOC_ALPHA]
    notes_beta = _note_hits(stub, LOC_BETA)
    checks = [
        ("beta contact write landed" if expect_write else "no beta contact write",
         bool(beta_contact) == expect_write),
        ("ZERO hits on alpha (no cross-client reach)", len(alpha_hits) == 0),
        ("note on beta" if expect_write else "no note on beta",
         bool(notes_beta) == expect_write),
    ]
    if expect_write:
        for p in stub.writes[LOC_BETA]:
            checks.append(("landed payload locationId == beta",
                           p.get("locationId") == LOC_BETA))
            break
    return checks


# ---------------------------------------------------------------------------
# The battery (positive + negative merged — the full two-fake-client isolation
# proof). Every case runs the REAL U15 write-back against the stub transport.
# ---------------------------------------------------------------------------

def _run_writeback(stub: _TwoClientGHLStub, delivery: dict,
                   env: dict[str, str], ledger_root: Path) -> dict:
    """Drive the real U15 write-back with the stub transport. Returns the
    outcome dict; raises WritebackRefused on an isolation refusal."""
    return wb.run_writeback(
        delivery,
        _PHASE_CONFIG,
        ledger_root=ledger_root,
        base_url="http://stub.two-client.local",
        env=env,
        transport=_StubTransport(stub),
    )


def run_battery() -> list[tuple[str, bool, str]]:
    results: list[tuple[str, bool, str]] = []
    ledger_root = Path(tempfile.mkdtemp(prefix="ma-u17-ledger-"))

    def check(name: str, cond: bool, detail: str) -> None:
        results.append((name, cond, detail))

    def case_label(name: str, checks: list[tuple[str, bool]]) -> str:
        return "; ".join("OK %s" % lbl if good else "XX %s" % lbl
                         for lbl, good in checks)

    # ------------------------------------------------------------------
    # POSITIVE: client A's answer with A's OWN KV binding row lands on
    # location-alpha (and only alpha).
    # ------------------------------------------------------------------
    stub = _TwoClientGHLStub()
    binding_a = _kv_binding(_TOKEN_A)
    assert binding_a is not None and binding_a["location_id"] == LOC_ALPHA
    try:
        _run_writeback(stub, _delivery(binding_a,
                        _answer("first_name", "Ada Lovelace", "ans-alpha-0001")),
                       _env_for(LOC_ALPHA), ledger_root / "case1")
        checks = _assert_alpha_only(stub, expect_write=True)
    except wb.WritebackRefused as exc:
        checks = [("A write succeeded (no unexpected refusal)", False),
                  ("refusal detail", False)]
        _log_refusal("CASE-1", exc)
    check("CASE-1 POSITIVE A answer + A binding row -> lands alpha only",
          all(c[1] for c in checks), case_label("CASE-1", checks))

    # ------------------------------------------------------------------
    # POSITIVE: client B's answer with B's OWN KV binding row lands on
    # location-beta (and only beta).
    # ------------------------------------------------------------------
    stub = _TwoClientGHLStub()
    binding_b = _kv_binding(_TOKEN_B)
    assert binding_b is not None and binding_b["location_id"] == LOC_BETA
    try:
        _run_writeback(stub, _delivery(binding_b,
                        _answer("first_name", "Barbara Klein", "ans-beta-0001")),
                       _env_for(LOC_BETA), ledger_root / "case2")
        checks = _assert_beta_only(stub, expect_write=True)
    except wb.WritebackRefused as exc:
        checks = [("B write succeeded (no unexpected refusal)", False),
                  ("refusal detail", False)]
        _log_refusal("CASE-2", exc)
    check("CASE-2 POSITIVE B answer + B binding row -> lands beta only",
          all(c[1] for c in checks), case_label("CASE-2", checks))

    # ------------------------------------------------------------------
    # NEGATIVE (THE LOAD-BEARING ONE): client A's answer body INJECTS client
    # B's destination (location_id, client_id, contact_id, destination all
    # forged to BETA). The KV binding row is the SOLE authority -> the answer
    # MUST still land on alpha, with ZERO hits on beta.
    # ------------------------------------------------------------------
    stub = _TwoClientGHLStub()
    injected_b = {
        "location_id": LOC_BETA,
        "client_id": "client_fictitious_beta",
        "contact_id": "contact-beta-forged",
        "destination": {"location_id": LOC_BETA,
                        "client_id": "client_fictitious_beta"},
    }
    try:
        _run_writeback(stub,
                       _delivery(binding_a,
                                 _answer("first_name", "Ada Lovelace",
                                         "ans-alpha-inject",
                                         injected=injected_b)),
                       _env_for(LOC_ALPHA), ledger_root / "case3")
        checks = _assert_alpha_only(stub, expect_write=True)
        checks.append(("injected beta destination never reached beta",
                       len(stub.writes[LOC_BETA]) == 0))
    except wb.WritebackRefused as exc:
        checks = [("A answer with forged B destination wrote (binding wins)", False),
                  ("refusal detail", False)]
        _log_refusal("CASE-3", exc)
    check("CASE-3 NEGATIVE A answer INJECTS B destination -> still alpha, ZERO beta",
          all(c[1] for c in checks), case_label("CASE-3", checks))

    # ------------------------------------------------------------------
    # NEGATIVE: an answer with NO KV binding row (unpossessed) -> refused
    # before any call. ZERO GHL hits on EITHER location (proven negative).
    # ------------------------------------------------------------------
    stub = _TwoClientGHLStub()
    orphan_answer = _answer("first_name", "Mallory", "ans-orphan-0001")
    refused_code = None
    try:
        _run_writeback(stub, _delivery(None, orphan_answer),
                       _env_for(LOC_ALPHA), ledger_root / "case4")
        checks = [("no-binding answer refused", False),
                  ("zero GHL hits", False)]
    except wb.WritebackRefused as exc:
        refused_code = exc.code
        checks = [("no-binding answer refused (AF named)", True),
                  ("refused BEFORE any call", exc.code == wb.AF_UNBOUND),
                  ("ZERO GHL hits on both locations (proven negative)",
                   len(stub.hits) == 0)]
        if refused_code != wb.AF_UNBOUND:
            checks.append(("refusal code is AF-BW-MA-WB-UNBOUND",
                           refused_code == wb.AF_UNBOUND))
    check("CASE-4 NEGATIVE answer with NO binding row -> refused, ZERO GHL hits",
          all(c[1] for c in checks), case_label("CASE-4", checks))

    # ------------------------------------------------------------------
    # NEGATIVE: a token bound to alpha presented WITH a B-flavored body ->
    # no cross-client reach. Either it is refused or it lands alpha; it can
    # NEVER land on beta. (Binding row wins -> lands alpha; ZERO beta hits.)
    # ------------------------------------------------------------------
    stub = _TwoClientGHLStub()
    b_flavored = {
        "client_id": "client_fictitious_beta",
        "destination": {"location_id": LOC_BETA,
                        "client_id": "client_fictitious_beta"},
    }
    try:
        _run_writeback(stub,
                       _delivery(binding_a,            # alpha token / binding
                                 _answer("first_name", "Ada Lovelace",
                                         "ans-alpha-bbody",
                                         injected=b_flavored)),
                       _env_for(LOC_ALPHA),            # alpha-only whitelist+PIT
                       ledger_root / "case5")
        checks = _assert_alpha_only(stub, expect_write=True)
        checks.append(("B-flavored body never reached beta",
                       len(stub.writes[LOC_BETA]) == 0
                       and len([h for h in stub.hits
                                if h["location"] == LOC_BETA]) == 0))
    except wb.WritebackRefused:
        # "refused OR lands alpha" is both isolation-safe — the invariant that
        # matters is ZERO beta hits.
        checks = [("alpha token + B body refused or landed alpha (isolation-safe)",
                   True),
                  ("ZERO hits on beta", len(stub.hits) == 0
                   or len([h for h in stub.hits
                           if h["location"] == LOC_BETA]) == 0)]
    check("CASE-5 NEGATIVE alpha-bound token + B body -> no cross-client reach",
          all(c[1] for c in checks), case_label("CASE-5", checks))

    # ------------------------------------------------------------------
    # REGRESSION: the U15 unit's OWN six-case self-test must still pass —
    # the isolation seam this prover proves is the one U15 enforces.
    # ------------------------------------------------------------------
    try:
        proc = subprocess.run(
            [sys.executable, str(_BOX_DIR / "ghl_writeback.py"), "--self-test"],
            capture_output=True, text=True, timeout=300)
        u15_ok = proc.returncode == 0
        detail = u15_ok and "U15 six-case battery PASS" or "U15 self-test failed (rc=%s)" % proc.returncode
    except (OSError, subprocess.SubprocessError) as exc:
        u15_ok = False
        detail = "U15 self-test could not run: %s" % exc
    check("REGRESSION U15 ghl_writeback.py --self-test passes",
          u15_ok, detail)

    # ------------------------------------------------------------------
    # SOURCE LINT: this prover ships no unresolved double-brace / dollar-paren
    # template tokens, no provider ids, and no operator-key literals. (The stub
    # PITs are placeholder-shaped by design — the write-back refuses
    # placeholders.) The forbidden patterns are built with split/chr joins so a
    # bare literal of the banned token can never live in this file — the lint
    # measures the same tokens it forbids.
    # ------------------------------------------------------------------
    # 97..105 = a n t h r o p i c ; 99,108,97,117,100,101 = c l a u d e
    _forbidden_ids_re = re.compile(
        "".join(chr(c) for c in (97, 110, 116, 104, 114, 111, 112, 105, 99))
        + "|" + "".join(chr(c) for c in (99, 108, 97, 117, 100, 101)),
        re.IGNORECASE)
    src = Path(__file__).read_text(encoding="utf-8")
    no_templates = wb._TEMPLATE_RE.search(src) is None
    no_ids = _forbidden_ids_re.search(src) is None
    no_sk = re.search(r"sk-[A-Za-z0-9]{16,}", src) is None
    lint_checks = [
        ("no double-brace / dollar-paren template tokens", no_templates),
        ("no provider id in prover source", no_ids),
        ("no operator key literal (sk-...)", no_sk),
    ]
    check("LINT prover source is clean (no provider id / no templates / no keys)",
          all(g for _, g in lint_checks),
          case_label("LINT", lint_checks))

    import shutil
    shutil.rmtree(ledger_root, ignore_errors=True)
    return results


def _log_refusal(case: str, exc: wb.WritebackRefused) -> None:
    sys.stderr.write("U17 %s unexpected refusal [%s] %s\n"
                     % (case, exc.code, exc.message))


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    parser = argparse.ArgumentParser(
        prog="prove_mini_app_isolation.py",
        description="U17 two-fake-client isolation prover (hard gate).")
    parser.add_argument("--self-test", "--selftest", action="store_true",
                        help="run the full positive+negative isolation battery")
    parser.add_argument("--json", action="store_true",
                        help="emit the result as JSON")
    args = parser.parse_args(argv)

    # The battery is the prover's only action — --self-test and a bare run are
    # the same hard gate (the battery IS the self-test).
    try:
        results = run_battery()
    except Exception as exc:  # any harness failure is a usage/io exit
        print("USAGE/IO: U17 isolation prover could not run: %s" % exc,
              file=sys.stderr)
        return EXIT_USAGE

    all_pass = all(ok for _, ok, _ in results)
    if args.json:
        print(json.dumps({
            "prover": "U17-mini-app-isolation",
            "passed": all_pass,
            "cases": [{"name": n, "ok": o, "detail": d}
                      for n, o, d in results],
        }, indent=2))
    else:
        for name, ok, detail in results:
            print("%s %s  %s" % ("PASS" if ok else "FAIL", name, detail))
        print("== U17 mini-app isolation prover: %s =="
              % ("ALL CASES PASSED (no cross-client reach)" if all_pass
                 else "FAILED — see FAIL lines above (each names its exact case)"))

    if all_pass:
        return EXIT_PASS
    # Any cross-client reach, or any failed case, exits NON-ZERO. Each FAIL
    # line already names the EXACT case that failed.
    return EXIT_AUTOFAIL


if __name__ == "__main__":
    sys.exit(main())
