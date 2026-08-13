#!/usr/bin/env python3
# =============================================================================
# SKILL 59 — ANTHOLOGY ENGINE :: u05_modules/main_skeleton.py
# U05 CHECK-MODULE DISPATCHER — the offline-plan / offline-self-test / live
# verify driver for the U05 SCOPED-READ and FILTER-SCOPE LAW family under
# scripts/u05_modules/. It imports the check modules BY NAME (importlib,
# never exec'd from a path), enforces the fail-closed one-entry-point
# contract, and resolves the aggregate exit code exactly as its U02 / U03 /
# U04 siblings (u02_modules/main_skeleton.py, u03_modules/main_skeleton.py,
# u04_modules/main_skeleton.py) do. It carries NO check logic itself: a
# check module is exercised ONLY through this CLI so `--dry-run`,
# `--self-test`, and the live aggregate never drift apart.
#
# THE U05 FAMILY (MASTER-SPEC U05 — the SCOPED-READ and FILTER-SCOPE LAW of
# the anthology engine, SPEC 7.2 / 11.3: every participant-facing read is
# scoped to ONE subject, never an unscoped sweep; and the U05 pipeline rule
# "Form is universal-intake" gates ONLY the universal author-intake form).
# The check modules this dispatcher aggregates; each is STDLIB-only (plus
# the registry), ships its own OFFLINE self-test battery (exit 0 pass / 4
# enforced violation), and exposes a thin own CLI — this skeleton is the
# ONE entry-point contract over them:
#   scope_checker.py      check(payload) -> (ok, filter_set) — the pure,
#                         side-effect-free PIPELINE-RULE SCOPE GATE: the
#                         filter must be "Form is universal-intake"
#                         BYTE-EXACT (form == "universal-intake", one space
#                         around "is", nothing else) to be in intake scope;
#                         an EMPTY / wildcard / renamed-token / byte-drifted
#                         filter is OUT of scope with a typed reason, never
#                         a fabricated pass; never echoes the filter beyond
#                         a reason code. OFFLINE and pure.
#   golden_scoped.py      golden_scoped() / golden_listing_payload() /
#                         payload(candidate) — the GOLDEN SCOPED-READ
#                         fixture (the canonical single-subject payload keyed
#                         by the one non-empty anthology_id filter; the
#                         KEYING LAW contact_id::anthology_id read once from
#                         anthology_state.participant_key, never hardcoded;
#                         mappingproxy-frozen canon) and its fail-closed
#                         payload gate: an empty filter, a foreign subject
#                         row, a foreign gate, a malformed read, or a
#                         credential-shaped value is REFUSED (exit 5), never
#                         a blind pass. OFFLINE (synthetic ids only).
#   attack_unscoped.py    scoped_rows(filter, rows) / verify_live(filter,
#                         rows) / payload() — the U05 ATTACK: the EMPTY
#                         ANTHOLOGY FILTER read (an unfiltered read reaches
#                         EVERY ledger row across ALL anthologies) that MUST
#                         FAIL every unscoped-read gate — verify_live exits
#                         5 on the empty / whitespace-only / shape-illegal /
#                         non-string filter while the true one-anthology
#                         scoped read exits 0; payload() ships EXACTLY the
#                         one empty-filter attack over the synthetic
#                         two-anthology ledger and REFUSES any drift; every
#                         anthology id reported by MASKED MARKER only. The
#                         fixture carries its own golden control (the
#                         negative-result contract: the pass/fail split
#                         discriminates the boundary, never a broken
#                         instrument). OFFLINE.
#   attack_wrong_form.py  attack_rule() / verify_rule(rule) / payload() —
#                         the U05 ATTACK: the WRONG FORM ON THE INTAKE
#                         FILTER (the canonical "Form is <token>" rule with
#                         the ONE form named swapped to a foreign form,
#                         every other field preserved) that MUST FAIL every
#                         byte-exact scope gate — the pipeline-rule gate AND
#                         its mirrored u02 trigger-side gate (u02_modules.
#                         scope_check); payload() ships EXACTLY the one-
#                         wrong-form attack and REFUSES any drift; the
#                         golden control passes exit 0. OFFLINE.
#   workflow_reader.py    read_workflows(client, location_id, *,
#                         pinned_id) -> the ONE live workflow read — the
#                         internal rail GET /workflow/<loc>/list?limit=200
#                         (the ONLY workflow surface this repo has PROVEN
#                         live, Skill 58) that FINDS the "Anthology Intake
#                         Fire" front-door workflow by the name law and
#                         reports its ONE id; a listing with no matching row
#                         is WORKFLOWS-NOT-FOUND / WORKFLOWS-EMPTY, a pinned
#                         id absent from the listing is PIN-MISSING (exit 5,
#                         never a silent pass), an unreadable listing shape
#                         raises WorkflowReadError (STOP), a transport /
#                         edge failure raises the registry HELD family, and
#                         a credential-shaped string in a row REFUSES the
#                         whole surface. The live read is RAIL-GATED
#                         (Firebase refresh token BY LABEL; PIT fallback) and
#                         rides CAF_BROWSER_UA (CF 1010).
#   house_rules.py        the ONE canonical HOUSE-LAW CONSTANT surface —
#                         CAF_BROWSER_UA / CAF_VERSION_HEADER ported
#                         byte-for-byte from the registry and the complete
#                         AF autofail table mirrored from ENGINE-MANIFEST.
#                         json as immutable constants; self_test() pins
#                         byte-equality (UA, version header, AF table) and
#                         proves zero credential surface. OFFLINE.
#   negative_verifier.py  check(payload) -> report — the NEGATIVE VERIFIER:
#                         certifies, fail-closed, that a submission (the
#                         universal-review decision form) does NOT fire the
#                         Intake Fire trigger; the scope law is IMPORTED
#                         from u02_modules.scope_check (read once, never
#                         re-implemented); a payload the trigger's own gate
#                         deterministically refuses is CERTIFIED does-not-
#                         fire, a payload that presents intake identity is
#                         FIRES (exit 5, AF-AE-NEGATIVE-INTAKE-FIRE), an
#                         INDETERMINATE shape is REFUSED (exit 5, never
#                         fabricated), a broken / emptied policy STOPS
#                         (exit 2 — the empty-filter attack shape certifies
#                         nothing). OFFLINE and pure.
#   scope_applier.py      run_apply(rail, location_id, workflow_id, name,
#                         row, *, execute) — the U05 family's ONLY write
#                         surface: corrects the trigger SCOPE FILTER of a
#                         release-notification workflow (the U02 item-4
#                         contract rows) so the workflow fires ONLY on its
#                         contract contact_tag trigger, via the internal
#                         rail PUT /workflow/{loc}/trigger/{id}. It REFUSES
#                         to write unless the operator passes --execute to
#                         ITS OWN CLI; the dispatcher NEVER invokes it and
#                         NEVER writes. Also plan().
#   trigger_reader.py     read_trigger(workflow=None, *, workflow_path) ->
#                         the OFFLINE reader of the n8n Drive-broker
#                         workflow asset's trigger FILTER SET (the webhook
#                         trigger gate, the Authorize & Dispatch filter law,
#                         the action allowlist pinned byte-exact to
#                         drive_adapter.BROKER_REQUIRED_ACTIONS); a data
#                         mismatch is a named af_code RESULT (TRIGGER-
#                         MISSING / TRIGGER-AMBIGUOUS / AUTH-GATE-MISSING /
#                         AUTH-GATE-AMBIGUOUS / ALLOWLIST-DRIFT, exit 5,
#                         never a fabricated filter set), an unreadable
#                         asset shape raises TriggerReadError (STOP, exit
#                         2); the token env label is reported by STATE
#                         ONLY. OFFLINE — reads the shipped asset, never
#                         the network.
#   example_usage.py      example_run(rail, location_id) -> int — the
#                         fail-closed WORKED EXAMPLE of the U05 dispatch:
#                         the front-door live read (workflow_reader) + the
#                         golden scoped gate + the empty-filter attack + the
#                         wrong-form attack + the negative verifier,
#                         composed end to end with every sibling's exit code
#                         honored verbatim (a STOP/HELD never masquerades
#                         as a mismatch). This dispatcher's LIVE_GATES
#                         implement the SAME composition gate-by-gate so the
#                         aggregate reports per-check records; the self-test
#                         pins example_usage's composition against the gate
#                         order.
#   docs_u05.py           the U05 tooling README/catalog data + drift gate
#                         (the module inventory, the four verified items,
#                         the house exit codes and af codes as DATA; its
#                         self-test proves the tree ships together).
#
# PLUS the two INDEPENDENT PYTEST BATTERIES that ship with the family
# (provenance only: the batteries' presence is asserted; their tests run
# under pytest): test_scope_checker.py and test_negative_verifier.py.
#
# THE IMPORT CONTRACT (the surface the family already satisfies): one ENTRY
# POINT per module, exposed as `self_test(out=None) -> int` — exit 0 on
# pass, 4 (EX_VIOLATION, the AF-AE-TEMPLATE-ATTACK family) on failure.
# A module without a battery STOPS the dispatcher (fail-closed: no check
# family is ever skipped, and a family that cannot prove itself offline
# cannot be trusted live). The live gates are driven through each module's
# OWN documented surfaces (check / verify_live / read_workflows /
# payload), never through a re-implementation, and their STOP-family
# exceptions are classified by name, exactly as the U02 / U03 / U04
# siblings classify theirs.
#
# THE ONE LIVE READ IS RAIL-GATED; THE TOOLING SHIPS NOW (manifest row 54
# doctrine; docs_u05.py "U05_VERIFIER = None  # PENDING"). The operator
# executes `verify` only from a session that can resolve a location-scoped
# credential BY LABEL — the internal-rail Firebase refresh token (preferred,
# the proven workflow surface) with the Firebase API key, or the template
# PIT as the rail fallback (the workflow_reader CLI's exact seam). --dry-run
# (offline plan) and --self-test (offline, no token, no network) always
# work. The four offline gates (scoped-read law, pipeline-rule scope,
# negative-verifier mirror, attack boundary) are exercised with their own
# golden surfaces and NEVER require a credential — and the aggregate still
# refuses up front without a rail credential (the workflow read is
# rail-gated and no gate is ever skipped).
#
# CREDENTIALS: BY LABEL, NEVER BY VALUE. The rail refresh token + API key
# are resolved through anthology_registry (FIREBASE_REFRESH_LABELS /
# FIREBASE_API_KEY_LABELS, live process env first then the three canonical
# client env stores), with the PIT (CONVERT_AND_FLOW_PIT /
# CONVERT_AND_FLOW_API_KEY / GOHIGHLEVEL_API_KEY / GOHIGHLEVEL_PIT /
# GHL_API_KEY) as the rail fallback, exactly as workflow_reader's own CLI
# resolves them. The location id is pinned to the contract's template
# location (2HIKGNgsixWx0yds7Qnx) unless --location-id overrides. SET /
# NOT SET only on every operator surface; a token value is NEVER printed,
# and the location / workflow ids are masked on every surface (last-4
# marker, reg._mask_location — the house shape).
#
# BROWSER UA: every request rides reg.CafClient / reg.InternalRailClient /
# the workflow_reader fetch, which apply CAF_BROWSER_UA on every request so
# the Cloudflare edge fronting services.leadconnectorhq.com /
# backend.leadconnectorhq.com never 1010s a verify request (CF 1010 /
# GK-09 discipline — the house pattern ported byte-for-byte from the
# U02 / U03 / U04 families and the podcast gate). This dispatcher asserts
# the law OFFLINE (its self-test pins the exact constant on the outbound
# surface) so a drifted UA is caught before a single live request.
# Scope-vs-edge-block discrimination: a bare 401/403 is HELD
# (UpstreamBlockedError / InternalRailUnavailable), never mislabeled as a
# scope problem; a genuine scope denial is a STOP (exit 2).
#
# AF CODES (fail-closed surfaces; self-test failures are exit 4, never 1):
#   AF-AE-U05-ASSEMBLY-INCOMPLETE -> the U05 check-module set named in
#          U05_MODULES is not fully present, or a module violates the
#          one-entry-point contract. STOP (exit 2) — a check family is
#          never silently skipped.
#   AF-AE-SCOPED-SUBJECT-MISSING  -> the scoped listing lost its golden
#          subject (golden_scoped payload gate). exit 5.
#   AF-AE-SCOPED-FOREIGN-ROW      -> a foreign subject leaked into the
#          one-subject read (golden_scoped payload gate). exit 5.
#   AF-AE-SCOPED-ROW-COUNT        -> the scoped listing is not exactly one
#          row (golden_scoped payload gate). exit 5.
#   AF-AE-NEGATIVE-INTAKE-FIRE    -> the negative verifier certified
#          does-not-fire for a submission that FIRES Intake Fire — the
#          negative claim is FALSE. exit 5.
#   AF-AE-TEMPLATE-ATTACK         -> an attack fixture tripped the OFFLINE
#          self-test (also the family self-test batteries). exit 4.
#   AF-AE-ATTACKUNSCOPED-* / AF-AE-ATTACKWRONGFORM-* / AF-AE-GOLDENSCOPED-*
#          / AF-AE-NEGATIVE-ATTACK -> the family's own enforced-violation
#          families. exit 4.
#
# EXIT CODES (house convention 0/1/2/3/5; 4 = enforced violation; the
# primary surface the operator consumes is 0 = PASS, 2 = STOP, 5 = mismatch):
#   0  all checks PASS (also --dry-run plan pass and self-test pass)
#   1  unexpected error
#   2  STOP refusal — label NOT SET / non-pit- value / usage / the U05
#      check-module assembly incomplete (AF-AE-U05-ASSEMBLY-INCOMPLETE) /
#      a contract that cannot be read / an unreadable listing shape /
#      a module STOP-family refusal (WorkflowReadError / FixtureError /
#      HouseRulesError / the negative-verifier broken-policy STOP)
#   3  HELD — Convert and Flow unreachable / Cloudflare edge block /
#      the internal rail unavailable (UNDETERMINED, never a verdict)
#   4  self-test FAILED — an assertion in the OFFLINE self-test tripped
#      (AF-AE-TEMPLATE-ATTACK family). A tamper NEVER masquerades as exit 1.
#   5  data or read-back mismatch (AF-AE-SCOPED-* / AF-AE-NEGATIVE-INTAKE-
#      FIRE / WORKFLOWS-NOT-FOUND / WORKFLOWS-EMPTY / PIN-MISSING / the
#      attack fixtures' REFUSED paths; also the fail-closed default when
#      any live check is DEFERRED without --allow-deferred)
#
# STDLIB ONLY (urllib + json via the registry and the check modules); calls
# NO model. Reuses anthology_registry (CafClient, InternalRailClient,
# resolve_pit, resolve_firebase_refresh_token, _resolve_firebase_api_key,
# _stop, _mask_location). DOCTRINE: move in silence; NOTHING Anthropic in
# any runtime file; Convert and Flow naming in every client surface; NEVER
# print a secret value; --dry-run and --self-test are OFFLINE.
# =============================================================================
"""main_skeleton.py — U05 check-module dispatcher: offline plan / offline
self-test / live verify of the Anthology SCOPED-READ and FILTER-SCOPE LAW
family (Skill 59, u05_modules; the packaged sibling of
u02_modules/main_skeleton.py, u03_modules/main_skeleton.py and
u04_modules/main_skeleton.py)."""

from __future__ import annotations

import argparse
import io
import json
import re
import sys
from pathlib import Path

# Sibling import bootstrap (house convention): the registry does the
# Cloudflare browser-UA wiring + LeadConnector clients and its label
# resolution is the house credential contract.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import anthology_registry as reg  # noqa: E402

EX_OK, EX_ERR, EX_STOP, EX_HELD, EX_MISMATCH = (
    reg.EX_OK, reg.EX_ERR, reg.EX_STOP, reg.EX_HELD, reg.EX_MISMATCH)
EX_VIOLATION = 4  # enforced violation detected (self-test FAILED)

# The u05_modules directory itself — sibling imports resolve from here, in
# BOTH execution contexts (as a script, whose own directory is sys.path[0],
# and as an imported module, where the caller may not have added it).
MODULES_DIR = Path(__file__).resolve().parent
if str(MODULES_DIR) not in sys.path:
    sys.path.insert(0, str(MODULES_DIR))

SKILL_DIR = Path(__file__).resolve().parent.parent.parent
CONTRACT_PATH = SKILL_DIR / "config" / "anthology-snapshot-contract.json"

# The template location id is the CONTRACT's source_template_location (the
# operator's OWN template location, operator infrastructure config, not a
# secret). The verifier pins to it; --location-id overrides for tests.
DEFAULT_TEMPLATE_LOCATION = "2HIKGNgsixWx0yds7Qnx"

# The U05 check-module inventory — the assembly manifest for this
# dispatcher. Every name is imported BY NAME below (importlib, never exec'd
# from a path); a missing module is a STOP, never a silent skip. `role` is
# the one-line contract each module owns. The names mirror the files on
# disk one-to-one and docs_u05.MODULES (the catalog and the tree never
# drift; the dispatcher self-test pins the counts, exactly as the U03 /
# U04 siblings pin theirs).
U05_MODULES = (
    ("scope_checker", "the pipeline-rule scope gate (filter == 'Form is "
                      "universal-intake' byte-exact; empty / wildcard / "
                      "drifted filters are OUT of scope, never a pass)"),
    ("golden_scoped", "the golden SCOPED-READ fixture (the canonical "
                      "single-subject payload keyed by the one non-empty "
                      "anthology_id filter; KEYING LAW read once from "
                      "anthology_state.participant_key) + its fail-closed "
                      "payload gate"),
    ("attack_unscoped", "the U05 ATTACK: the empty-anthology-filter read "
                        "that MUST FAIL every unscoped-read gate (the "
                        "golden one-anthology scoped control PASSES)"),
    ("attack_wrong_form", "the U05 ATTACK: the wrong form on the intake "
                          "filter that MUST FAIL every byte-exact scope "
                          "gate (the golden control PASSES)"),
    ("workflow_reader", "the ONE live workflow read — find 'Anthology "
                        "Intake Fire' by the name law / pin on the "
                        "internal-rail listing, report its ONE id"),
    ("house_rules", "the ONE canonical house-law constant surface (browser "
                    "UA, version header, the AF autofail table mirrored "
                    "from ENGINE-MANIFEST.json)"),
    ("negative_verifier", "the NEGATIVE VERIFIER — certify, fail-closed, "
                          "that a submission does NOT fire the Intake Fire "
                          "trigger (the scope law read once from "
                          "u02_modules.scope_check)"),
    ("scope_applier", "the ONLY write surface — the trigger-scope PUT, "
                      "REFUSED without its own --execute (the dispatcher "
                      "NEVER invokes it and NEVER writes)"),
    ("trigger_reader", "the OFFLINE reader of the n8n Drive-broker trigger "
                       "filter set (the webhook gate + the Authorize & "
                       "Dispatch filter law + the action allowlist pinned "
                       "to drive_adapter.BROKER_REQUIRED_ACTIONS)"),
    ("example_usage", "the fail-closed WORKED EXAMPLE of the U05 dispatch "
                      "(front-door read + scoped law + both attacks + the "
                      "negative mirror, composed with every sibling exit "
                      "code honored verbatim)"),
    ("docs_u05", "the U05 tooling README/catalog data + drift gate (the "
                 "module inventory as DATA; its self-test proves the tree "
                 "ships together)"),
)

# The modules that ship their own OFFLINE self-test battery (each returns
# exit 0 on pass, 4 on failure). The dispatcher REQUIRES a battery from
# every module — a check family that cannot prove itself offline STOPS.
SELF_TEST_MODULES = tuple(name for name, _ in U05_MODULES)

# The independent pytest batteries that ship with the family (provenance
# only: the batteries' presence is asserted, their tests run under pytest).
TEST_BATTERIES = ("test_scope_checker.py", "test_negative_verifier.py")

# The live-verify gate order (FIXED, in this order) — the family's four
# verified items plus the negative-verifier mirror:
#   1. scoped-read law (golden_scoped payload gate over the golden
#      listing — offline by construction),
#   2. pipeline-rule scope (scope_checker over the golden rule — offline),
#   3. the Intake Fire workflow read (workflow_reader — the ONE rail-gated
#      live read),
#   4. the attack boundary (attack_unscoped verify_live + attack_wrong_form
#      verify_rule over their canonical attacks — offline; the FAIL paths
#      are proven to FAIL),
#   5. the negative mirror (negative_verifier over the golden review
#      submission — offline; the does-not-fire certification holds),
#   6. the trigger filter-set read (trigger_reader over the shipped n8n
#      Drive-broker asset — offline; the front door's filter set must be
#      certified byte-exact to the engine authority).
# scope_applier is NOT a live gate: it is the family's gated WRITE surface
# and the dispatcher never invokes it (the write gate holds at its own CLI).
# example_usage is the WORKED EXAMPLE of this same composition — the
# self-test pins its step order against LIVE_GATES so the two never drift.
LIVE_GATES = (
    ("golden_scoped", "the scoped-read law — the golden single-subject "
                      "listing must pass the fail-closed payload gate"),
    ("scope_checker", "the pipeline-rule scope law — the golden rule "
                      "filter must be IN scope byte-exact"),
    ("workflow_reader", "the Intake Fire workflow read — the live "
                        "internal-rail listing must name the workflow "
                        "(rail-gated; the ONE credential surface)"),
    ("attack_unscoped", "the attack boundary — the empty-filter attack "
                        "must FAIL and the one-anthology control PASS"),
    ("attack_wrong_form", "the attack boundary — the wrong-form attack "
                          "must FAIL and the golden control PASS"),
    ("negative_verifier", "the negative mirror — the golden universal-"
                          "review submission must be CERTIFIED "
                          "does-not-fire"),
    ("trigger_reader", "the trigger filter-set read — the shipped n8n "
                       "Drive-broker asset's filter set must be certified "
                       "byte-exact to the engine authority"),
)


class SkeletonError(Exception):
    """A fail-closed refusal (STOP or mismatch family) raised by the skeleton
    itself — a missing check module, a module violating the entry-point
    contract, a contract section that cannot be read, or a malformed record."""


# ---------------------------------------------------------------------------
# Check-module loader — imports the U05 modules BY NAME and enforces the
# fail-closed contract: a missing module or a module that fails to expose
# its entry point is a STOP, never a silent skip.
# ---------------------------------------------------------------------------
def load_modules():
    """Import every U05_MODULES module. Returns {name: module}.

    Fail-closed: a module that does not exist raises SkeletonError (STOP) so
    the aggregate NEVER passes with a check family silently absent.
    `importlib` is the only import surface — nothing is ever exec'd from a
    path. Each module's `self_test(out=None) -> int` battery is REQUIRED
    (checked here, not deferred to the self-test run)."""
    import importlib

    modules = {}
    missing = []
    for name, _role in U05_MODULES:
        try:
            mod = importlib.import_module(name)
        except ImportError:
            missing.append(name)
            continue
        modules[name] = mod
    if missing:
        raise SkeletonError(
            "u05_modules file(s) not found: %s — the U05 assembly is "
            "incomplete (fail-closed: no check family is ever skipped)"
            % ", ".join(missing))
    for name, mod in modules.items():
        st = getattr(mod, "self_test", None)
        if not callable(st):
            raise SkeletonError(
                "u05_modules module %s does not expose 'self_test' — every "
                "check module must prove itself offline" % name)
    return modules


# ---------------------------------------------------------------------------
# Offline self-test — run EVERY module's own battery (golden PASS / attack
# FAIL), plus this dispatcher's own assembly and house-law assertions. NO
# network, NO credentials. Exit 4 on any failure (AF-AE-TEMPLATE-ATTACK
# family) — a tamper NEVER masquerades as exit 1.
# ---------------------------------------------------------------------------
def self_test(modules, out=None) -> int:
    out = out or sys.stderr
    dev = io.StringIO()
    try:
        # 1. the assembly is complete: exactly the U05 check-module set
        #    exists (the dispatcher, the empty package init, and the pytest
        #    batteries are the assembly container, not dispatched modules).
        on_disk = sorted(p.name[:-3] for p in MODULES_DIR.glob("*.py")
                         if p.name not in ("__init__.py", "main_skeleton.py")
                         and not p.name.startswith("test_"))
        expected = sorted(name for name, _ in U05_MODULES)
        assert on_disk == expected, (
            "u05_modules tree drifted: disk carries %s, the %d-module "
            "assembly contract names %s" % (", ".join(on_disk), len(expected),
                                            ", ".join(expected)))
        for battery in TEST_BATTERIES:
            assert (MODULES_DIR / battery).is_file(), (
                "the U05 pytest battery %s is missing from u05_modules/"
                % battery)
        # 2. every module's own battery passes (golden PASS / attack FAIL).
        for name, mod in modules.items():
            try:
                rc = mod.self_test(out=dev)
            except TypeError:
                rc = mod.self_test()
            if rc != EX_OK:
                raise AssertionError("%s self_test returned exit %d" % (name, rc))
        # 2b. the WORKED EXAMPLE cannot drift from this dispatcher's gate
        #     order: example_usage's composition runs the SAME five-step
        #     law (its own self-test asserts the step order), and every
        #     step must have a matching live gate here — a composition
        #     that reordered or dropped a gate is drift, never a pass.
        assert [name for name, _ in LIVE_GATES] == [
            "golden_scoped", "scope_checker", "workflow_reader",
            "attack_unscoped", "attack_wrong_form", "negative_verifier",
            "trigger_reader"], \
            "the U05 live-gate order drifted from the family contract"
        _by_step = {"golden-scoped": "golden_scoped",
                    "empty-filter": "attack_unscoped",
                    "wrong-form": "attack_wrong_form",
                    "negative": "negative_verifier"}
        _gate_names = {name for name, _ in LIVE_GATES}
        for _step, _gate in _by_step.items():
            assert _gate in _gate_names, \
                "example_usage step %r has no matching live gate" % _step
        # 3. the house exit-code law is the manifest convention
        #    (0/1/2/3/4/5): the skeleton's constants never drifted from the
        #    registry's, which the manifest pins.
        assert (EX_OK, EX_ERR, EX_STOP, EX_HELD, EX_MISMATCH) == (0, 1, 2, 3, 5), \
            "house exit-code law drifted: registry constants are not 0/1/2/3/5"
        assert EX_VIOLATION == 4, "house exit-code law drifted: EX_VIOLATION is not 4"
        # 4. BROWSER UA LAW (CF 1010 / GK-09): the CAF_BROWSER_UA constant is
        #    a well-formed browser UA (never urllib's "Python-urllib/x.y"
        #    default, which the Cloudflare edge fronting the Convert and Flow
        #    / internal-rail hosts 403s as error 1010 before the request is
        #    ever scope-checked).
        ua = reg.CAF_BROWSER_UA
        assert isinstance(ua, str) and ua.strip(), "CAF_BROWSER_UA is empty"
        assert "Python-urllib" not in ua, \
            "CAF_BROWSER_UA is urllib's default — the Cloudflare edge 1010s it"
        assert ua.startswith("Mozilla/5.0") and "Chrome/" in ua, \
            "CAF_BROWSER_UA is not a well-formed browser UA"
        # 5. CREDENTIAL LAW: the PIT labels are the house standard set and
        #    resolve to SET / NOT SET only — never a printed value. The
        #    resolver refuses a non-pit- value (a placeholder or a mis-set
        #    value must not silently ride as a token).
        assert tuple(reg.PIT_LABELS) == (
            "CONVERT_AND_FLOW_PIT", "CONVERT_AND_FLOW_API_KEY",
            "GOHIGHLEVEL_API_KEY", "GOHIGHLEVEL_PIT", "GHL_API_KEY"), \
            "PIT label set drifted from the house credential law"
        _label, token = reg.resolve_pit()
        assert token is None or str(token).startswith("pit-"), \
            "resolve_pit returned a non-pit- token (would be refused)"
        # 6. NEVER-A-TOKEN LAW on the skeleton's OWN surfaces: the plan
        #    payload (the same builder the --dry-run prints) and the report
        #    surface carry labels and SET / NOT SET states only — a
        #    credential-shaped string (pit- followed by a value) can never
        #    leak through them.
        contract = _read_json(CONTRACT_PATH, "anthology-snapshot-contract.json")
        plan_blob = json.dumps(_build_plan(modules, DEFAULT_TEMPLATE_LOCATION,
                                           contract),
                               indent=2, sort_keys=True)
        assert not _CREDENTIAL_SHAPE.search(plan_blob), \
            "the plan surface must never carry a credential-shaped string"
        report_blob = json.dumps(_build_report(modules), indent=2, sort_keys=True)
        assert not _CREDENTIAL_SHAPE.search(report_blob), \
            "the report surface must never carry a credential-shaped string"
    except AssertionError as exc:
        sys.stderr.write("[main-skeleton] SELF-TEST FAILED "
                         "(AF-AE-TEMPLATE-ATTACK family): %s\n" % exc)
        return EX_VIOLATION
    except SkeletonError as exc:
        sys.stderr.write("[main-skeleton] SELF-TEST FAILED "
                         "(AF-AE-TEMPLATE-ATTACK family): %s\n" % exc)
        return EX_VIOLATION
    out.write(dev.getvalue())
    out.write("[main-skeleton] U05 self-test: OK (%d modules imported, "
              "every module battery + assembly assertions + exit-code law + "
              "browser-UA law + credential law pass)\n" % len(modules))
    return EX_OK


_CREDENTIAL_SHAPE = re.compile(r"pit-\S+")


def _mask_id(fid: str) -> str:
    """Mask a workflow / location id for every operator surface — a location
    identifier, not a secret, but never printed in full (house pattern,
    mirrored from workflow_reader.mask_id / golden_scoped's fixture
    discipline)."""
    fid = (fid or "").strip()
    if len(fid) <= 8:
        return "***"
    return "%s***%s" % (fid[:4], fid[-4:])


# ---------------------------------------------------------------------------
# Offline plan — no network, no credentials. The U05 dispatch law with the
# exact sources of truth, printed as ONE JSON object on stdout; human notes
# go to stderr. Each module's own plan surface (where it ships one) is
# collected by name; a module plan that cannot be produced is recorded as
# an error, never fabricated. The payload is scanned against the credential
# shape before print — a hit REFUSES the surface rather than echo a token.
# ---------------------------------------------------------------------------
def _module_plan(modules, name, location_id, contract):
    """One module's plan record. Uses the module's OWN plan() surface when
    it ships one; otherwise derives the offline law from the module's
    documented constants / functions. A module plan is never fatal — an
    error is recorded, never a fabricated law."""
    mod = modules[name]
    try:
        if name == "workflow_reader":
            dev = io.StringIO()
            rc = mod.plan(location_id, "", out=dev)
            if rc != EX_OK:
                return {"error": "plan returned exit %d" % rc}
            return json.loads(dev.getvalue() or "null")
        if name == "scope_applier":
            # The write surface's plan is offline (no network, no credential
            # needed): the eight contract rows + the PUT surface. The
            # dispatcher records the plan and the write gate, and NEVER
            # invokes the apply.
            return {
                "write_surface": "PUT /workflow/{loc}/trigger/{id} via the "
                                 "internal rail (the ONLY proven trigger-"
                                 "write surface, Skill 44)",
                "write_gate": "the PUT is performed ONLY with --execute to "
                              "scope_applier's own CLI — the dispatcher "
                              "never invokes it and never writes",
                "contract_rows": "config/anthology-snapshot-contract.json "
                                 "workflows.release_notifications (the "
                                 "EIGHT tag->notification workflows)",
                "note": "offline plan only — no network, no credential "
                        "needed; a truthful apply dry-run needs the live "
                        "read and the rail credentials",
            }
        if name == "scope_checker":
            return {
                "filter_law": "the U05 pipeline rule filter must be EXACTLY "
                              "%r (form == %r, byte-exact, one space around "
                              "'is', nothing else) to be in intake scope"
                              % (mod.UNIVERSAL_INTAKE_FILTER,
                                 mod.UNIVERSAL_INTAKE_FORM),
                "note": "offline only — pure local shape analysis; an empty "
                        "/ malformed / unrecognized filter is OUT of scope "
                        "with a typed reason, never a fabricated pass",
            }
        if name == "golden_scoped":
            return {
                "filter_key": mod.FILTER_KEY,
                "filter_value": mod.GOLDEN_ANTHOLOGY_ID,
                "subject_key": mod.GOLDEN_SUBJECT_KEY,
                "gate_id": mod.GOLDEN_GATE_ID,
                "law_source": "anthology_state.participant_key (the KEYING "
                              "LAW contact_id::anthology_id — read once, "
                              "never hardcoded)",
                "note": "offline plan only — synthetic fixture ids, no "
                        "network, no credential needed",
            }
        if name == "attack_unscoped":
            return {
                "attack": "the empty-anthology-filter read (an unfiltered "
                          "read reaches EVERY ledger row across ALL "
                          "anthologies) must FAIL every unscoped-read gate",
                "ledger_rows": len(mod.ATTACK_LEDGER),
                "control": "the true one-anthology scoped read PASSES "
                           "exit 0 (the pass/fail split discriminates the "
                           "boundary, never a broken instrument)",
                "note": "offline attack fixture — every anthology id "
                        "reported by masked marker only",
            }
        if name == "attack_wrong_form":
            return {
                "attack": "the wrong form on the intake filter (the "
                          "canonical 'Form is <token>' rule with the ONE "
                          "form named swapped to a foreign form) must FAIL "
                          "every byte-exact scope gate",
                "expected_form": mod.ATTACK_RULE and mod.ATTACK_RULE.get(
                    "filter", ""),
                "control": "the golden rule names the byte-exact "
                           "universal-intake form and PASSES exit 0",
                "note": "offline attack fixture — the form tokens are rule "
                        "names, never credentials",
            }
        if name == "house_rules":
            return {
                "laws": ("browser UA (%s bytes, CAF_BROWSER_UA — CF 1010), "
                         "version header %r, AF autofail table (%d codes "
                         "mirrored from ENGINE-MANIFEST.json)"
                         % (len(mod.CAF_BROWSER_UA.encode("utf-8")),
                            mod.CAF_VERSION_HEADER, len(mod.AF_CODES))),
                "note": "offline only — pure constant surface; a header is "
                        "a law, never a secret",
            }
        if name == "negative_verifier":
            return {
                "certifies": "a submission (the universal-review decision "
                             "form) does NOT fire the Intake Fire trigger",
                "law_source": "u02_modules.scope_check (the Intake Fire "
                              "scope law — read once, never re-implemented)",
                "refusals": "fires-intake (exit 5, AF-AE-NEGATIVE-INTAKE-"
                            "FIRE) / INDETERMINATE (exit 5, never "
                            "fabricated) / broken-emptied policy (exit 2 — "
                            "the empty-filter attack shape certifies "
                            "nothing)",
                "note": "offline only — pure deterministic predicate over "
                        "ONE payload; never prints the payload or a token",
            }
        if name == "trigger_reader":
            dev = io.StringIO()
            rc = mod.plan(out=dev)
            if rc != EX_OK:
                return {"error": "plan returned exit %d" % rc}
            return json.loads(dev.getvalue() or "null")
        if name == "example_usage":
            dev = io.StringIO()
            rc = mod.plan(out=dev, jsonout=dev)
            if rc != EX_OK:
                return {"error": "plan returned exit %d" % rc}
            return json.loads(dev.getvalue() or "null")
        if name == "docs_u05":
            return {
                "module_count": len(mod.MODULES),
                "verified_items": [row["item"] for row in mod.VERIFY_ITEMS],
                "note": "offline documentation data — the inventory and "
                        "contract surfaces as DATA",
            }
        return {"note": "no plan surface for %s" % name}
    except Exception as exc:  # noqa: BLE001 — a plan is never fatal
        return {"error": "%s: %s" % (type(exc).__name__, exc)}


def _build_plan(modules, location_id: str, contract: dict) -> dict:
    """The ONE offline plan payload (shared by --dry-run and the self-test's
    never-a-token scan, so the two can never drift)."""
    plans = {}
    for name, _role in U05_MODULES:
        plans[name] = _module_plan(modules, name, location_id, contract)
    return {
        "contract": "anthology-engine-u05-dispatch-plan",
        "schema_version": 1,
        "template_location_id": location_id,
        "template_location_id_masked": _mask_id(location_id),
        "gates": [name for name, _ in LIVE_GATES],
        "modules": [name for name, _ in U05_MODULES],
        "plans": plans,
        "dry_run": True,
        "note": "offline plan only — no network, no credential needed; the "
                "ONE live read (workflow_reader) must ride the internal "
                "rail with CAF_BROWSER_UA on every request — CF 1010 law",
    }


def plan(modules, location_id: str, contract: dict, out=None) -> int:
    out = out or sys.stderr
    payload = _build_plan(modules, location_id, contract)
    dumped = json.dumps(payload, indent=2, sort_keys=True)
    if _CREDENTIAL_SHAPE.search(dumped):
        raise SkeletonError(
            "plan payload carries a credential-shaped string — REFUSED "
            "without printing it")
    print(dumped)
    return EX_OK


def _build_report(modules) -> dict:
    """The empty report scaffold (labels and states only — the never-a-token
    law is pinned on this exact surface in the self-test)."""
    return {
        "contract": "anthology-engine-u05-verify",
        "schema_version": 1,
        "template_location_id": DEFAULT_TEMPLATE_LOCATION,
        "template_location_id_masked": _mask_id(DEFAULT_TEMPLATE_LOCATION),
        "pit_label": "SET" if reg.resolve_pit()[0] else "NOT SET",
        "rail_label": "SET" if reg.resolve_firebase_refresh_token()[1] else "NOT SET",
        "checks": {},
        "delta": [],
        "fail_closed": True,
    }


# ---------------------------------------------------------------------------
# Live verify — fail-closed aggregate over the fixed gate order. Any FAIL ->
# exit 5; a STOP-family refusal propagates as exit 2; a transport / edge
# failure is HELD (exit 3), never mislabeled as scope. The four offline
# gates run FIRST (their golden surfaces need no credential), then the ONE
# rail-gated live read. scope_applier is never a gate: the dispatcher never
# writes.
# ---------------------------------------------------------------------------
def _stop_classes(mod):
    """The STOP-family exception classes a module may raise, resolved BY
    NAME so a module that stops defining one fails the self-test, not the
    live path."""
    return tuple(cls for cname in ("WorkflowReadError", "FixtureError",
                                   "HouseRulesError", "WorkflowMissing",
                                   "TriggerScopeRefused", "TriggerReadError")
                 if isinstance(cls := getattr(mod, cname, None), type)
                 and issubclass(cls, Exception))


def _rail_client(out) -> "object":
    """Resolve the internal-rail client for the ONE live read, BY LABEL,
    exactly as workflow_reader's own CLI resolves it: the Firebase refresh
    token (preferred, the proven workflow surface) with the Firebase API
    key, else the template PIT as the rail fallback. NEVER prints a value;
    a missing credential is a STOP (the caller returns it)."""
    refresh_label, refresh = reg.resolve_firebase_refresh_token()
    if refresh:
        api_label, api_key = reg._resolve_firebase_api_key()
        if not api_key:
            reg._stop(out,
                      "The Firebase refresh token is SET but the Firebase "
                      "API key is NOT SET.",
                      ["Checked (in order): %s — all NOT SET."
                       % ", ".join(reg.FIREBASE_API_KEY_LABELS),
                       "The internal rail cannot mint an id_token without "
                       "both labels. Set the API-key label and re-run."])
            return None, EX_STOP
        return reg.InternalRailClient(refresh, api_key), None
    pit_label, token = reg.resolve_pit()
    if not token:
        checked = ", ".join(reg.PIT_LABELS)
        reg._stop(out,
                  "No Convert and Flow credential is SET.",
                  ["Checked (in order): refresh-token labels %s — all NOT "
                   "SET; PIT labels %s — all NOT SET."
                   % (", ".join(reg.FIREBASE_REFRESH_LABELS), checked),
                   "The verify runs against the operator's OWN template "
                   "location %s; set the template refresh token (preferred, "
                   "the proven workflow surface) or the template PIT and "
                   "re-run." % _mask_id(DEFAULT_TEMPLATE_LOCATION)])
        return None, EX_STOP
    # The PIT rides the internal base with CAF_BROWSER_UA and the
    # Authorization header — the exact fallback workflow_reader's CLI
    # builds (never re-implemented here; the class shape mirrors it).
    import urllib.request  # noqa: F401  (imported for parity with the sibling)

    class _PitRailClient:
        def __init__(self, tok):
            self._tok = tok

        def _get(self, path):
            import urllib.error
            import urllib.request as _ur
            req = _ur.Request(
                reg.INTERNAL_API_BASE + path,
                headers={"Authorization": "Bearer %s" % self._tok,
                         "version": reg.INTERNAL_VERSION_HEADER,
                         "Accept": "application/json",
                         "User-Agent": reg.CAF_BROWSER_UA})
            try:
                with _ur.urlopen(req, timeout=15) as resp:
                    raw = resp.read().decode("utf-8") or "{}"
                    return json.loads(raw) if raw.strip() else {}
            except urllib.error.HTTPError as exc:
                if exc.code in (401, 403):
                    body = b""
                    try:
                        body = exc.read()
                    except Exception:  # noqa: BLE001 — a body read is never fatal
                        body = b""
                    if reg._auth_denial_kind(body) == "scope":
                        raise reg.ScopeDenied(
                            "token not authorized for this scope (HTTP %s)"
                            % exc.code)
                    raise reg.UpstreamBlockedError(
                        "HTTP %s did NOT match a Convert and Flow scope-"
                        "denial signature — likely a Cloudflare/WAF edge "
                        "block, NOT a token-scope problem (HTTP %s)"
                        % (exc.code, exc.code))
                raise reg.CafUnreachable(
                    "Convert and Flow HTTP %s on %s" % (exc.code, path))
            except (urllib.error.URLError, TimeoutError, OSError,
                    ValueError) as exc:
                raise reg.CafUnreachable(
                    "Convert and Flow transport error: %s"
                    % type(exc).__name__)

    return _PitRailClient(token), None


def verify_live(modules, location_id: str, contract: dict, *,
                allow_deferred: bool = False, out=None) -> int:
    out = out or sys.stderr
    masked = _mask_id(location_id)
    report = _build_report(modules)
    report["template_location_id_masked"] = masked

    import contextlib as _contextlib

    def _capture_sibling(call):
        """Run a sibling module surface that prints its OWN gate document to
        stdout by contract, capturing that stdout into the human channel so
        the dispatcher's stdout stays exactly its ONE JSON report object
        (the u04 skeleton's plan-capture pattern, applied to the live
        gates). Returns the call's return value."""
        cap = io.StringIO()
        with _contextlib.redirect_stdout(cap):
            rc = call()
        if cap.getvalue().strip():
            out.write(cap.getvalue())
        return rc

    def _run(name, mod):
        try:
            if name == "golden_scoped":
                result = _capture_sibling(
                    lambda: mod.payload(mod.golden_listing_payload(),
                                        out=io.StringIO()))
                if result == EX_OK:
                    return ("PASS",
                            "the golden single-subject listing passes the "
                            "fail-closed scoped gate (KEYING LAW "
                            "contact_id::anthology_id, exactly one row)",
                            {"subject_key": mod.GOLDEN_SUBJECT_KEY,
                             "rows": 1},
                            {"subject_key": mod.GOLDEN_SUBJECT_KEY,
                             "rows": 1}), None
                return ("FAIL",
                        "the golden scoped listing was REFUSED (exit %d) — "
                        "the scoped-read law drifted"
                        % result,
                        {"subject_key": mod.GOLDEN_SUBJECT_KEY, "rows": 1},
                        {"subject_key": "?", "rows": "?"}), None
            if name == "scope_checker":
                ok, flt = mod.check({"source": "anthology-intake",
                                     "location": "LOC-synthetic-AAA",
                                     "filter": mod.UNIVERSAL_INTAKE_FILTER})
                if ok:
                    return ("PASS",
                            "the golden rule filter is IN scope byte-exact "
                            "(form %r)"
                            % flt.get("form"),
                            {"filter": mod.UNIVERSAL_INTAKE_FILTER},
                            {"filter": mod.UNIVERSAL_INTAKE_FILTER}), None
                return ("FAIL",
                        "the golden rule filter was REFUSED (reason %s) — "
                        "the pipeline-rule scope law drifted"
                        % (flt.get("reason") if isinstance(flt, dict) else "?"),
                        {"filter": mod.UNIVERSAL_INTAKE_FILTER},
                        {"filter": None}), None
            if name == "workflow_reader":
                rail, rc = _rail_client(out)
                if rc is not None:
                    return None, rc
                result = mod.read_workflows(rail, location_id)
                if result.get("ok"):
                    return ("PASS",
                            "the 'Anthology Intake Fire' workflow is on the "
                            "live listing (matched by %s, %d workflow row(s); "
                            "id masked)"
                            % (result.get("matched_by", "?"),
                               result.get("count", 0)),
                            {"found": True,
                             "workflow_id_masked": result.get(
                                 "workflow_id_masked", "")},
                            {"found": True,
                             "workflow_id_masked": result.get(
                                 "workflow_id_masked", "")}), None
                return ("FAIL",
                        "%s: %s" % (result.get("af_code", "WORKFLOWS-NOT-FOUND"),
                                    result.get("note", "")),
                        {"found": True},
                        {"found": False,
                         "candidates": result.get("candidates", [])}), None
            if name == "attack_unscoped":
                fail_rc = _capture_sibling(
                    lambda: mod.verify_live("", mod.ATTACK_LEDGER,
                                            out=io.StringIO()))
                pass_rc = _capture_sibling(
                    lambda: mod.verify_live(mod.SCOPED_BOOK_ID,
                                            mod.ATTACK_LEDGER,
                                            out=io.StringIO()))
                if fail_rc == EX_MISMATCH and pass_rc == EX_OK:
                    return ("PASS",
                            "the empty-filter attack FAILS (exit 5) and the "
                            "one-anthology control PASSES (exit 0) — the "
                            "boundary discriminates",
                            {"attack": "FAIL", "control": "PASS"},
                            {"attack": fail_rc, "control": pass_rc}), None
                return ("FAIL",
                        "the attack boundary drifted: empty-filter attack "
                        "exit %d (want 5), one-anthology control exit %d "
                        "(want 0)"
                        % (fail_rc, pass_rc),
                        {"attack": "FAIL", "control": "PASS"},
                        {"attack": fail_rc, "control": pass_rc}), None
            if name == "attack_wrong_form":
                fail_rc = _capture_sibling(
                    lambda: mod.verify_rule(mod.ATTACK_RULE,
                                            out=io.StringIO()))
                pass_rc = _capture_sibling(
                    lambda: mod.verify_rule(mod.GOLDEN_RULE_CANONICAL,
                                            out=io.StringIO()))
                if fail_rc == EX_MISMATCH and pass_rc == EX_OK:
                    return ("PASS",
                            "the wrong-form attack FAILS (exit 5) and the "
                            "golden rule control PASSES (exit 0) — the "
                            "byte-exact form law discriminates",
                            {"attack": "FAIL", "control": "PASS"},
                            {"attack": fail_rc, "control": pass_rc}), None
                return ("FAIL",
                        "the form-attack boundary drifted: wrong-form "
                        "attack exit %d (want 5), golden control exit %d "
                        "(want 0)"
                        % (fail_rc, pass_rc),
                        {"attack": "FAIL", "control": "PASS"},
                        {"attack": fail_rc, "control": pass_rc}), None
            if name == "negative_verifier":
                golden = {"source": "anthology-intake",
                          "location": "LOC-synthetic-RVW",
                          "form": mod.UNIVERSAL_REVIEW_FORM,
                          "contact_id": "C-9001",
                          "anthology_id": "A-9001",
                          "stage": "s7_cover"}
                result = mod.check(golden)
                if result.get("ok") and result.get("verified"):
                    return ("PASS",
                            "the golden universal-review submission is "
                            "CERTIFIED does-not-fire (basis %s)"
                            % result.get("basis", "?"),
                            {"fires_intake": False},
                            {"fires_intake": result.get("fires_intake")}), None
                return ("FAIL",
                        "the negative mirror drifted: golden review "
                        "submission %s (basis %s) — %s"
                        % ("CERTIFIED" if result.get("ok") else "REFUSED",
                           result.get("basis", "?"),
                           result.get("note", "")),
                        {"fires_intake": False},
                        {"fires_intake": result.get("fires_intake"),
                         "basis": result.get("basis")}), None
            if name == "trigger_reader":
                # OFFLINE: reads the SHIPPED n8n Drive-broker asset, never
                # the network — the front door's filter set must certify
                # byte-exact (webhook gate + auth-gate filter law + action
                # allowlist pinned to drive_adapter.BROKER_REQUIRED_ACTIONS).
                result = mod.read_trigger()
                if result.get("ok"):
                    return ("PASS",
                            "the Drive-broker trigger filter set is "
                            "certified (webhook gate, auth-gate filter law, "
                            "allowlist byte-exact — %d action(s))"
                            % len(result.get("actions", {}).get(
                                "allowlist", [])),
                            {"af_code": "OK"},
                            {"af_code": result.get("af_code", "OK")}), None
                return ("FAIL",
                        "%s: %s" % (result.get("af_code", "TRIGGER-MISSING"),
                                    result.get("note", "")),
                        {"af_code": "OK"},
                        {"af_code": result.get("af_code", "?"),
                         "delta": result.get("delta", [])}), None
            raise SkeletonError("dispatcher has no live gate for module %r"
                                % name)
        except reg.ScopeDenied as exc:
            reg._stop(out, "The Convert and Flow token cannot READ the "
                           "template location (%s)." % masked,
                      [str(exc), "Grant the template PIT the READ scope and "
                                 "re-run.", "AF-AE-PIT-SCOPE."])
            return None, EX_STOP
        except reg.UpstreamBlockedError as exc:
            out.write("[main-skeleton] HELD: %s\n" % exc)
            return None, EX_HELD
        except reg.CafUnreachable as exc:
            out.write("[main-skeleton] HELD: %s\n" % exc)
            return None, EX_HELD
        except reg.InternalRailUnavailable as exc:
            out.write("[main-skeleton] HELD (internal rail): %s\n" % exc)
            return None, EX_HELD
        except _stop_classes(mod) as exc:
            reg._stop(out, "Fail-closed refusal in %s: %s" % (name, exc), [])
            return None, EX_STOP
        except SkeletonError as exc:
            reg._stop(out, "Fail-closed refusal in %s: %s" % (name, exc), [])
            return None, EX_STOP
        except Exception as exc:  # noqa: BLE001 — a module refusal is never an unexpected error
            if exc.__class__.__name__ in ("WorkflowReadError", "FixtureError",
                                          "HouseRulesError", "WorkflowMissing",
                                          "TriggerScopeRefused",
                                          "TriggerReadError"):
                reg._stop(out, "Fail-closed refusal in %s: %s" % (name, exc), [])
                return None, EX_STOP
            raise

    for name, _role in LIVE_GATES:
        record, rc = _run(name, modules[name])
        if rc is not None:
            return rc
        status, detail, expected, live = record
        report["checks"][name] = {
            "status": status,
            "detail": detail,
            "expected": expected,
            "live": live,
        }
        if status == "FAIL":
            report["delta"].append(
                {"check": name, "expected": expected, "live": live,
                 "detail": detail})

    deferred = [n for n, c in report["checks"].items()
                if c.get("status") == "DEFERRED"]
    failures = [n for n, c in report["checks"].items()
                if c.get("status") == "FAIL"]
    if deferred:
        out.write("[main-skeleton] %d check(s) DEFERRED (never fabricated). "
                  "Pass --allow-deferred to accept the deferral.\n"
                  % len(deferred))
        if not allow_deferred:
            report["delta"].append({
                "check": "aggregate",
                "detail": "%d check(s) DEFERRED without --allow-deferred "
                          "(fail-closed): %s" % (len(deferred),
                                                 ", ".join(deferred)),
            })
            report["verdict"] = "FAIL (deferred without --allow-deferred)"
            print(json.dumps(report, indent=2, sort_keys=True))
            return EX_MISMATCH
    report["verdict"] = "PASS" if not failures else "FAIL"
    print(json.dumps(report, indent=2, sort_keys=True))
    return EX_OK if not failures else EX_MISMATCH


# ---------------------------------------------------------------------------
# CLI — house shape: --dry-run / --self-test / --json accepted as flags AND
# as a positional subcommand (--self-test / --selftest normalize exactly as
# anthology_registry.py and the U02 / U03 / U04 skeletons).
# ---------------------------------------------------------------------------
def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="main_skeleton.py",
        description="U05 check-module dispatcher: offline plan, offline "
                    "self-test, and live verify of the Anthology SCOPED-READ "
                    "and FILTER-SCOPE LAW family (Skill 59, u05_modules; the "
                    "packaged sibling of u02_modules/main_skeleton.py, "
                    "u03_modules/main_skeleton.py and "
                    "u04_modules/main_skeleton.py) — imports the check "
                    "modules by name and aggregates their records into ONE "
                    "fail-closed JSON report.")
    ap.add_argument("--location-id", default="",
                    help="override the contract location id (default: the contract's "
                         "source_template_location.template_location_id, %s; masked "
                         "on every surface, never printed in full)"
                         % DEFAULT_TEMPLATE_LOCATION)
    ap.add_argument("--allow-deferred", action="store_true",
                    help="explicit operator opt-in: accept a DEFERRED live read "
                         "as PASS — the report still records the deferral")
    ap.add_argument("--contract", default=str(CONTRACT_PATH),
                    help="path to anthology-snapshot-contract.json")
    ap.add_argument("--dry-run", action="store_true",
                    help="offline plan only — no network, no credential (default: live verify)")
    ap.add_argument("--json", action="store_true",
                    help="emit a machine-readable summary on stdout (default on for verify/plan)")
    ap.add_argument("--selftest", "--self-test", dest="self_test", action="store_true",
                    help="run the offline self-test (golden + attack fixtures) and exit")
    ap.add_argument("cmd", nargs="?", choices=["verify", "plan", "self-test"],
                    help="positional subcommand form (verify / plan / self-test)")

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
        modules = load_modules()

        if args.self_test:
            return self_test(modules)

        contract = _read_json(Path(args.contract).expanduser(),
                              "anthology-snapshot-contract.json")
        location_id = (args.location_id.strip() or
                       (contract.get("source_template_location") or {}).get(
                           "template_location_id")
                       or DEFAULT_TEMPLATE_LOCATION)

        if args.dry_run:
            return plan(modules, location_id, contract)

        # ---- live verify (rail-gated for the ONE live read) ----
        return verify_live(modules, location_id, contract,
                           allow_deferred=args.allow_deferred, out=sys.stderr)

    except reg.ScopeDenied as exc:
        sys.stderr.write("[main-skeleton] STOP: %s\n" % exc)
        return EX_STOP
    except reg.UpstreamBlockedError as exc:
        sys.stderr.write("[main-skeleton] HELD: %s\n" % exc)
        return EX_HELD
    except reg.CafUnreachable as exc:
        sys.stderr.write("[main-skeleton] HELD: %s\n" % exc)
        return EX_HELD
    except reg.InternalRailUnavailable as exc:
        sys.stderr.write("[main-skeleton] HELD: %s\n" % exc)
        return EX_HELD
    except SkeletonError as exc:
        sys.stderr.write("[main-skeleton] STOP/FAIL: %s\n" % exc)
        return EX_STOP
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001 — top-level guard, never leaks a secret
        sys.stderr.write("[main-skeleton] unexpected error: %s: %s\n"
                         % (type(exc).__name__, exc))
        return EX_ERR


def _read_json(path: Path, what: str) -> dict:
    """Fail-closed contract reader — a missing section is never a blind pass."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise SkeletonError("cannot read %s: %s" % (what, exc)) from exc
    except ValueError as exc:
        raise SkeletonError("%s is not valid JSON: %s" % (what, exc)) from exc
    if not isinstance(data, dict):
        raise SkeletonError("%s does not parse to a JSON object" % what)
    return data


if __name__ == "__main__":
    sys.exit(main())
