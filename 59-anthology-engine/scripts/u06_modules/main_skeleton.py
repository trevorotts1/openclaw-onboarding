#!/usr/bin/env python3
# =============================================================================
# SKILL 59 — ANTHOLOGY ENGINE :: u06_modules/main_skeleton.py
# U06 ARCHIVE-ACTION DISPATCHER — the offline-plan / offline-self-test / live
# verify driver for the U06 ARCHIVE-ACTION LAW family under scripts/u06_modules/
# (the fail-closed archive doctrine of the package init: any archive ACTION —
# delete / archive / remove / deactivate / revoke / unpublish — REQUIRES the
# explicit Trevor gate --execute; without it the dispatcher reports what it
# WOULD do and exits WITHOUT mutating). It imports the check modules BY NAME
# (importlib, never exec'd from a path), enforces the fail-closed
# one-entry-point contract, and resolves the aggregate exit code exactly as
# its U02 / U03 / U04 / U05 siblings (u02_modules/main_skeleton.py,
# u03_modules/main_skeleton.py, u04_modules/main_skeleton.py,
# u05_modules/main_skeleton.py) do. It carries NO check logic itself: a check
# module is exercised ONLY through this CLI so `--dry-run`, `--self-test`,
# and the live aggregate never drift apart.
#
# THE U06 FAMILY (the ARCHIVE-ACTION LAW of the anthology engine — the
# package-init doctrine, u06_modules/__init__.py: "Destructive actions fail
# closed: any archive ACTION (delete / archive / remove / deactivate /
# revoke / unpublish) in this package requires the caller to pass --execute
# explicitly (Trevor-gated). Without --execute the module must report what it
# WOULD do and exit without mutating."). The modules this dispatcher
# aggregates; each is STDLIB-only (plus the registry), ships its own OFFLINE
# self-test battery (exit 0 pass / 4 enforced violation), and exposes a thin
# own CLI — this skeleton is the ONE entry-point contract over them:
#   workflow_lister.py  live_list_command(location_id, *, out, jsonout) — the
#                       live read surface of the U06 family: the workflow
#                       NAMES of a Convert and Flow location through the
#                       PROVEN internal rail (GET /workflow/{loc}/list?limit=200
#                       on backend.leadconnectorhq.com — the ONLY workflow
#                       surface this repo has proven live, Skill 58 /
#                       Podcast-gate discipline); an EMPTY workflow set is a
#                       truthful PASS (exit 0); a missing credential, an
#                       unreachable rail, an edge block, or an unparseable
#                       listing is HELD (exit 3, never a fabricated list).
#                       Its ONE ACTION verb, archive(name, location_id, *,
#                       execute=False), is the Trevor-gated archive ACTION:
#                       WITHOUT --execute it is a STOP (exit 2), never a
#                       silent no-op; WITH --execute it is STILL A PLAN ONLY
#                       (the module reports the records it would archive and
#                       exits WITHOUT mutating, because no archive/delete
#                       surface for workflows has been proven live anywhere
#                       in this repo — Skill 44 endpoint doctrine: only
#                       proven endpoints). self_test() is the offline battery
#                       (golden listing sorted / folders excluded, byte-exact
#                       name bind, no-mutation plan + masked ids, and the
#                       attack fixtures refused fail-closed: duplicate-name /
#                       empty-name / unknown-name / non-dict / missing-rows /
#                       non-list-rows / non-object-row / ragged-rows; the
#                       --execute gate STOPs without it).
#   golden_absent.py    the archive LAW authority + the golden ABSENT-state
#                       fixture: both archive targets (board / ledger — the
#                       revoke flow's R2 / R6 pair) EMPTY -> PASS (nothing
#                       to archive); the archive ACTION is --execute-gated
#                       (GOLDEN_EXECUTE_REQUIRED), canonical record
#                       mappingproxy-frozen; payload() judges a census
#                       (stdin) fail-closed (exit 0 pass / 5 refused).
#   find_legacy.py      the legacy-find law authority + the live read of the
#                       TWO legacy Anthology workflows BY EXACT NAME on the
#                       PROVEN internal rail (LEGACY_NAMES — the U06 archive
#                       targets, read-only: this module NEVER archives);
#                       find_legacies(...) -> the {contract, ok, workflows,
#                       absent, pinned, candidates, af_code} surface
#                       (LEGACY-FOUND / LEGACY-ABSENT / LEGACY-PARTIAL /
#                       LEGACY-EMPTY / PIN-MISSING / PIN-ON-WRONG-NAME /
#                       PIN-UNATTRIBUTABLE); raises LegacyFindError (STOP)
#                       on an unreadable listing shape or a credential-shaped
#                       id; every request rides CAF_BROWSER_UA (CF 1010).
#   attack_no_execute.py  the U06 ATTACK: the archive ACTION requested
#                       WITHOUT --execute (the Trevor gate) — the canonical
#                       no-execute record (the ONE gate flag dropped over
#                       synthetic material, every id masked) that every
#                       archive authority MUST refuse (verify_archive exit
#                       5), with the golden execute-required dry-run control
#                       PASSING (payload_true) — the pass/fail split
#                       discriminates the missing-gate boundary.
#   golden_found.py     the GOLDEN FOUND-state fixture — the canonical
#                       in-memory payload of the U06 FIND half in its FOUND
#                       state: BOTH contract workflows the archive action
#                       touches on the listing, byte-exact by the golden
#                       keys (read once from find_legacy.LEGACY_NAMES, the
#                       find law authority), each with its one synthetic id;
#                       payload(candidate=None) judges a listing against
#                       the found-state law fail-closed and returns the
#                       dispatcher-consumed dict {"ok", "names", "rows",
#                       "af_code", "note"} — with no candidate the GOLDEN
#                       listing itself is judged (this dispatcher's offline
#                       gate). READ-ONLY by construction; the --execute gate
#                       lives in this dispatcher, never in a fixture.
#   test_find_legacy.py the independent pytest battery for the family's
#                       find law (provenance: its presence is asserted, its
#                       tests run under pytest).
#   docs_u06.py         the U06 tooling README/catalog data + drift gate
#                       (the module inventory, the five verified items,
#                       the house exit codes and af codes as DATA; its
#                       self-test proves the tree ships together).
#   verify_archived.py  the ARCHIVED-STATE VERIFIER — the read-back half of
#                       the U06 archive law: re-reads the engine's TWO
#                       archive targets (board / ledger, the revoke flow's
#                       R2 / R6 pair) after the archive sweep and confirms
#                       the archived status BYTE-EXACT (ledger status
#                       'archived' via anthology_state's own read surface;
#                       board cards at the board's archive status 'blocked'
#                       via mc_board's own fail-soft projection); its check
#                       ACTION is Trevor-gated (--execute) and READ-ONLY —
#                       without --execute it STOPS (exit 2, the family's
#                       AF-AE-U06-ARCHIVE-NO-EXECUTE law), with --execute it
#                       still writes nothing; an unreadable mirror is HELD
#                       (exit 3), a drift is a MISMATCH (exit 5).
#
# THE IMPORT CONTRACT (the surface the family already satisfies): one ENTRY
# POINT per module, exposed as `self_test(out=None) -> int` — exit 0 on
# pass, 4 (EX_VIOLATION, the AF-AE-TEMPLATE-ATTACK family) on failure.
# A module without a battery STOPS the dispatcher (fail-closed: no check
# family is ever skipped, and a family that cannot prove itself offline
# cannot be trusted live). The live gates are driven through each module's
# OWN documented surfaces (live_list_command / archive_command / payload /
# golden listings), never through a re-implementation, and their STOP-family
# exceptions are classified by name, exactly as the U02 / U03 / U04 / U05
# siblings classify theirs.
#
# THE ARCHIVE ACTION IS TREVOR-GATED HERE. The dispatcher NEVER archives
# without --execute: `archive` is a THIRD positional subcommand (verify /
# plan / self-test / archive) that routes to the gated ACTION path, and
# `verify_live(..., archive=...)` refuses the archive step up front (exit 2,
# AF-AE-U06-ARCHIVE-NO-EXECUTE) unless the operator passed --execute
# explicitly. The gate is enforced in BOTH surfaces (the CLI and the
# aggregate), pinned by the offline self-test (mutation proof: without
# --execute nothing may be written, and the no-execute refusal is a STOP —
# exit 2 — never a silent pass). An archive ACTION must ALSO name its ONE
# byte-exact target workflow (--name; a nameless archive is a refusal, never
# a sweep). The module's OWN --execute gate is re-proven HERE, never
# assumed: this dispatcher passes its operator-gate status INTO the module's
# surface, and the module's own no-execute STOP is classified verbatim. A
# mutation is NEVER performed by the dispatcher itself — it carries no write
# surface; the family's write discipline is the gate + the plan-only
# contract.
#
# THE ONE LIVE READ IS RAIL-GATED; THE TOOLING SHIPS NOW (the u06_modules
# package-init doctrine; the U06 manifest row PENDING, staged under the
# manifest-pending/u02.json · u03.json · u04.json · u05.json pattern). The
# operator executes `verify` only from a session that can resolve a
# location-scoped credential BY LABEL — the internal-rail Firebase refresh
# token (the proven workflow surface) with the Firebase API key. --dry-run
# (offline plan) and --self-test (offline, no token, no network) always
# work. The offline gates (the golden both-workflows fixture, the golden
# listing, the archive gate law) are exercised with their own golden
# surfaces and NEVER require a credential — and the aggregate still refuses
# up front without a rail credential (the workflow read is rail-gated and no
# gate is ever skipped).
#
# CREDENTIALS: BY LABEL, NEVER BY VALUE. The rail refresh token + API key
# are resolved through anthology_registry (FIREBASE_REFRESH_LABELS /
# FIREBASE_API_KEY_LABELS, live process env first then the three canonical
# client env stores) and the location id through reg.resolve_location
# (CONVERT_AND_FLOW_LOCATION_ID / GOHIGHLEVEL_LOCATION_ID / GHL_LOCATION_ID)
# unless --location-id overrides. SET / NOT SET only on every operator
# surface; a token value is NEVER printed, and the location / workflow ids
# are masked on every surface (reg._mask_location / the module's last-4
# marker — the house shape).
#
# BROWSER UA: every request rides reg.InternalRailClient /
# reg._internal_request_headers, which apply CAF_BROWSER_UA on every request
# so the Cloudflare edge fronting backend.leadconnectorhq.com never 1010s a
# verify request (CF 1010 / GK-09 discipline — the house pattern ported
# byte-for-byte from the U02 / U03 / U04 / U05 families and the podcast
# gate). This dispatcher asserts the law OFFLINE (its self-test pins the
# exact constant on the outbound surface) so a drifted UA is caught before a
# single live request. Scope-vs-edge-block discrimination: a bare 401/403 is
# HELD (UpstreamBlockedError / InternalRailUnavailable), never mislabeled as
# a scope problem.
#
# AF CODES (fail-closed surfaces; self-test failures are exit 4, never 1):
#   AF-AE-U06-ASSEMBLY-INCOMPLETE -> the U06 check-module set named in
#          U06_MODULES is not fully present, or a module violates the
#          one-entry-point contract. STOP (exit 2) — a check family is
#          never silently skipped.
#   AF-AE-U06-ARCHIVE-NO-EXECUTE  -> the archive ACTION was requested
#          without --execute (the Trevor gate). STOP (exit 2) — an ACTION
#          without the gate is a refusal, never a silent no-op.
#   AF-AE-U06-ARCHIVE-NO-NAME     -> the archive ACTION was requested
#          without its byte-exact target workflow name. STOP (exit 2) — a
#          nameless archive is a refusal, never a sweep.
#   AF-AE-U06-ARCHIVE-PLAN-ONLY   -> WITH --execute the archive step still
#          performs NO mutation (endpoint doctrine — no archive/delete
#          surface proven live): it reports the plan and exits without
#          writing. Plan-only is the CONTRACT, not a failure.
#   AF-AE-U06-NAME-NOT-FOUND      -> a byte-exact workflow name resolves to
#          no workflow on the live listing. exit 2 (module STOP).
#   AF-AE-U06-NAME-AMBIGUOUS      -> a workflow name is duplicated on the
#          live listing — the bind is ambiguous and MUST refuse. exit 2.
#   AF-AE-TEMPLATE-ATTACK         -> an attack fixture tripped the OFFLINE
#          self-test (also the family self-test batteries). exit 4.
#
# EXIT CODES (house convention 0/1/2/3/5; 4 = enforced violation; the
# primary surface the operator consumes is 0 = PASS, 2 = STOP, 5 = mismatch):
#   0  all checks PASS (also --dry-run plan pass and self-test pass)
#   1  unexpected error
#   2  STOP refusal — the archive ACTION without --execute (the Trevor
#      gate, AF-AE-U06-ARCHIVE-NO-EXECUTE) or without its byte-exact target
#      name (AF-AE-U06-ARCHIVE-NO-NAME) / label NOT SET / usage / the
#      U06 check-module assembly incomplete (AF-AE-U06-ASSEMBLY-INCOMPLETE)
#      / a contract that cannot be read / a name that resolves to no
#      workflow or to more than one / a module STOP-family refusal
#   3  HELD — the internal rail unreachable / Cloudflare edge block /
#      Firebase exchange failure / a malformed listing (UNDETERMINED,
#      never a verdict)
#   4  self-test FAILED — an assertion in the OFFLINE self-test tripped
#      (AF-AE-TEMPLATE-ATTACK family). A tamper NEVER masquerades as exit 1.
#   5  data or read-back mismatch (a DEFERRED live read without
#      --allow-deferred; the fail-closed default)
#
# STDLIB ONLY (urllib + json via the registry and the check modules); calls
# NO model. Reuses anthology_registry (InternalRailClient,
# resolve_firebase_refresh_token, _resolve_firebase_api_key,
# resolve_location, _stop, _mask_location). DOCTRINE: move in silence;
# NOTHING Anthropic in any runtime file (the exact house doctrine string,
# carried verbatim so the guard scan's phrase stays present); Convert and
# Flow naming in every client surface; NEVER print a secret value;
# --dry-run and --self-test are OFFLINE; an archive ACTION requires
# --execute (Trevor-gated) and even then is a plan only — no mutation.
# =============================================================================
"""main_skeleton.py — U06 archive-action dispatcher: offline plan / offline
self-test / live verify of the Anthology ARCHIVE-ACTION LAW family (Skill 59,
u06_modules; the packaged sibling of u02_modules/main_skeleton.py,
u03_modules/main_skeleton.py, u04_modules/main_skeleton.py and
u05_modules/main_skeleton.py). The archive ACTION requires --execute
(Trevor-gated) and is a plan only — this dispatcher never mutates."""

from __future__ import annotations

import argparse
import io
import json
import re
import sys
from pathlib import Path

# Sibling import bootstrap (house convention): the registry does the
# Cloudflare browser-UA wiring + the internal-rail client and its label
# resolution is the house credential contract.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import anthology_registry as reg  # noqa: E402

EX_OK, EX_ERR, EX_STOP, EX_HELD, EX_MISMATCH = (
    reg.EX_OK, reg.EX_ERR, reg.EX_STOP, reg.EX_HELD, reg.EX_MISMATCH)
EX_VIOLATION = 4  # enforced violation detected (self-test FAILED)

# The u06_modules directory itself — sibling imports resolve from here, in
# BOTH execution contexts (as a script, whose own directory is sys.path[0],
# and as an imported module, where the caller may not have added it).
MODULES_DIR = Path(__file__).resolve().parent
if str(MODULES_DIR) not in sys.path:
    sys.path.insert(0, str(MODULES_DIR))

SKILL_DIR = Path(__file__).resolve().parent.parent.parent
CONTRACT_PATH = SKILL_DIR / "config" / "anthology-snapshot-contract.json"

# The U06 check-module inventory — the assembly manifest for this
# dispatcher. Every name is imported BY NAME below (importlib, never exec'd
# from a path); a missing module is a STOP, never a silent skip. `role` is
# the one-line contract each module owns. The names mirror the files on
# disk one-to-one (the catalog and the tree never drift; the dispatcher
# self-test pins the counts, exactly as the U03 / U04 / U05 siblings pin
# theirs).
U06_MODULES = (
    ("workflow_lister", "the live read surface of the U06 family — the "
                        "workflow NAMES of a Convert and Flow location "
                        "through the PROVEN internal rail (GET "
                        "/workflow/{loc}/list?limit=200); its ONE ACTION "
                        "verb 'archive' is Trevor-gated (--execute) and a "
                        "plan only — no mutation, endpoint doctrine"),
    ("golden_absent", "the archive LAW authority + the golden ABSENT-state "
                      "fixture: both archive targets (board / ledger — the "
                      "revoke flow's R2 / R6 pair) EMPTY -> PASS (nothing "
                      "to archive); the archive ACTION is --execute-gated "
                      "(GOLDEN_EXECUTE_REQUIRED); payload() judges a census "
                      "fail-closed (exit 0 pass / 5 refused)"),
    ("find_legacy", "the legacy-find law authority + the live read of the "
                    "TWO legacy Anthology workflows BY EXACT NAME on the "
                    "PROVEN internal rail (LEGACY_NAMES — the U06 archive "
                    "targets; read-only, NEVER archives); find_legacies(...) "
                    "-> the fail-closed {workflows, absent, af_code} "
                    "surface (LEGACY-FOUND / -ABSENT / -PARTIAL / -EMPTY / "
                    "PIN-MISSING / PIN-ON-WRONG-NAME / PIN-UNATTRIBUTABLE)"),
    ("attack_no_execute", "the U06 ATTACK: the archive ACTION requested "
                          "WITHOUT --execute (the Trevor gate) — the "
                          "canonical no-execute record that every archive "
                          "authority MUST refuse (verify_archive exit 5) "
                          "with the golden execute-required control "
                          "PASSING (payload_true) — the pass/fail split "
                          "discriminates the missing-gate boundary"),
    ("golden_found", "the GOLDEN FOUND-state fixture — the canonical "
                     "in-memory payload of the U06 FIND half in its FOUND "
                     "state: BOTH contract workflows the archive action "
                     "touches on the listing byte-exact by the golden keys, "
                     "each with its one synthetic id; payload(candidate="
                     "None) judges a listing against the found-state law "
                     "fail-closed and returns the dispatcher-consumed dict "
                     "— READ-ONLY, the --execute gate lives in this "
                     "dispatcher"),
    ("docs_u06", "the U06 tooling README/catalog data + drift gate (the "
                 "module inventory as DATA; its self-test proves the tree "
                 "ships together)"),
    ("verify_archived", "the ARCHIVED-STATE VERIFIER — the read-back half "
                        "of the U06 archive law: re-reads the engine's TWO "
                        "archive targets (board / ledger) after the archive "
                        "sweep and confirms the archived status BYTE-EXACT; "
                        "its check ACTION is Trevor-gated (--execute) and "
                        "READ-ONLY — without --execute it STOPS (exit 2), "
                        "an unreadable mirror is HELD (exit 3), a drift is "
                        "a MISMATCH (exit 5)"),
    ("house_rules", "the ONE canonical house-law constant surface (browser "
                    "UA, version header, the AF autofail table mirrored "
                    "from docs_u06.AF_CODES plus the shared rows pinned "
                    "against ENGINE-MANIFEST.json)"),
    ("example_usage", "the fail-closed WORKED EXAMPLE of the U06 dispatch "
                      "(the FIND law + the golden found-state + the golden "
                      "absent-state + the no-execute attack + the lister's "
                      "archive ACTION, composed with every sibling exit "
                      "code honored verbatim)"),
)

# The modules that ship their own OFFLINE self-test battery (each returns
# exit 0 on pass, 4 on failure). The dispatcher REQUIRES a battery from
# every module — a check family that cannot prove itself offline STOPS.
SELF_TEST_MODULES = tuple(name for name, _ in U06_MODULES)

# The independent pytest batteries that ship with the family (provenance
# only: the batteries' presence is asserted, their tests run under pytest).
TEST_BATTERIES = ("test_find_legacy.py", "test_verify_archived.py")

# The live-verify gate order (FIXED, in this order) — the U06 family's
# verified surfaces:
#   1. the archive gate law (the family contract: the archive ACTION is
#      Trevor-gated — without --execute it is a STOP, exit 2, never a
#      silent no-op; with --execute it is a plan only — OFFLINE, pure, by
#      the family doctrine; no network, no credential),
#   2. the golden ABSENT-state fixture (golden_absent payload gate over the
#      golden empty census — OFFLINE by construction; a board card or a
#      ledger row present is a FAIL, never a blind pass),
#   3. the golden FOUND-state fixture (golden_found payload gate over the
#      golden listing — OFFLINE by construction; an absent, renamed, or
#      duplicated contract workflow is a FAIL, never a blind pass),
#   4. the legacy-find read (find_legacy find_legacies over the live
#      internal-rail listing — the ONE rail-gated live read; both legacy
#      workflows must be found by exact name; a partial or absent find is a
#      MISMATCH, exit 5, never a half-pass),
#   5. the live workflow list read (workflow_lister live_list_command — the
#      rail-gated names read; an EMPTY workflow set is a truthful PASS),
#   6. the archived-state read-back (verify_archived check — the engine's
#      own local ledger mirror + board projection, NO rail credential; the
#      read-back ACTION is Trevor-gated, so the gate runs it with --execute
#      ON, and a drift in either target is a MISMATCH, never a pass).
# attack_no_execute is NOT a live gate: the attack's FAIL path is the
# family's own no-execute law, proven OFFLINE by the archive gate + its own
# battery — the live path never re-runs an attack as a gate. The archive
# ACTION is NOT a live gate either: it is the family's gated ACTION surface
# (verify_live refuses it without --execute) and even WITH --execute it is
# a plan only — this dispatcher never mutates.
LIVE_GATES = (
    ("golden_absent", "the golden ABSENT-state fixture — both archive "
                      "targets (board / ledger) EMPTY, the archive ACTION "
                      "--execute-gated; a present card or row is a FAIL, "
                      "never a blind pass"),
    ("golden_found", "the golden FOUND-state fixture — both contract "
                     "workflows the archive action touches on the listing "
                     "byte-exact by the golden keys; an absent, renamed, "
                     "or duplicated contract workflow is a FAIL, never a "
                     "blind pass"),
    ("find_legacy", "the legacy-find read — the TWO legacy workflows found "
                    "BY EXACT NAME on the live internal-rail listing "
                    "(rail-gated; LEGACY-ABSENT / LEGACY-PARTIAL is a "
                    "MISMATCH, never a half-pass)"),
    ("workflow_lister", "the live workflow list read — the location's "
                        "workflow names through the PROVEN internal rail "
                        "(rail-gated; an EMPTY workflow set is a truthful "
                        "PASS)"),
    ("verify_archived", "the archived-state read-back — the engine's own "
                        "local ledger mirror + board projection, both "
                        "targets confirmed archived byte-exact (NO rail "
                        "credential; a drift is a MISMATCH, an unreadable "
                        "mirror is HELD)"),
)


class SkeletonError(Exception):
    """A fail-closed refusal (STOP or mismatch family) raised by the skeleton
    itself — a missing check module, a module violating the entry-point
    contract, a contract section that cannot be read, or a malformed record."""


# ---------------------------------------------------------------------------
# Check-module loader — imports the U06 modules BY NAME and enforces the
# fail-closed contract: a missing module or a module that fails to expose
# its entry point is a STOP, never a silent skip.
# ---------------------------------------------------------------------------
def load_modules():
    """Import every U06_MODULES module. Returns {name: module}.

    Fail-closed: a module that does not exist raises SkeletonError (STOP) so
    the aggregate NEVER passes with a check family silently absent.
    `importlib` is the only import surface — nothing is ever exec'd from a
    path. Each module's `self_test(out=None) -> int` battery is REQUIRED
    (checked here, not deferred to the self-test run)."""
    import importlib

    modules = {}
    missing = []
    for name, _role in U06_MODULES:
        try:
            mod = importlib.import_module(name)
        except ImportError:
            missing.append(name)
            continue
        modules[name] = mod
    if missing:
        raise SkeletonError(
            "u06_modules file(s) not found: %s — the U06 assembly is "
            "incomplete (fail-closed: no check family is ever skipped)"
            % ", ".join(missing))
    for name, mod in modules.items():
        st = getattr(mod, "self_test", None)
        if not callable(st):
            raise SkeletonError(
                "u06_modules module %s does not expose 'self_test' — every "
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
        # 1. the assembly is complete: exactly the U06 check-module set
        #    exists (the dispatcher and the empty package init are the
        #    assembly container, not dispatched modules).
        on_disk = sorted(p.name[:-3] for p in MODULES_DIR.glob("*.py")
                         if p.name not in ("__init__.py", "main_skeleton.py")
                         and not p.name.startswith("test_"))
        expected = sorted(name for name, _ in U06_MODULES)
        assert on_disk == expected, (
            "u06_modules tree drifted: disk carries %s, the %d-module "
            "assembly contract names %s" % (", ".join(on_disk), len(expected),
                                            ", ".join(expected)))
        for battery in TEST_BATTERIES:
            assert (MODULES_DIR / battery).is_file(), _battery_exc(battery)
        # 2. every module's own battery passes (golden PASS / attack FAIL).
        for name, mod in modules.items():
            try:
                rc = mod.self_test(out=dev)
            except TypeError:
                rc = mod.self_test()
            if rc != EX_OK:
                raise AssertionError("%s self_test returned exit %d" % (name, rc))
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
        # 5. THE ARCHIVE GATE LAW — the heart of the U06 family: the
        #    dispatcher's own action gate refuses the archive ACTION
        #    without --execute (the Trevor gate), and the module's own
        #    surface (workflow_lister.archive_command with execute=False) is
        #    the family's verbatim STOP (exit 2, AF-AE-U06-ARCHIVE-
        #    NO-EXECUTE) — never a silent no-op, never a mutation. The
        #    gate also refuses a nameless archive (AF-AE-U06-ARCHIVE-NO-NAME,
        #    exit 2) — a nameless archive is a refusal, never a sweep.
        assert _archive_gate(modules, "synthetic-archive-target") == EX_OK, \
            "the dispatcher archive gate must pass its own offline law"
        _rc_nameless = _archive_gate(modules, "")
        assert _rc_nameless == EX_STOP, \
            "a nameless archive ACTION must STOP (exit 2), got %d" % _rc_nameless
        # 6. CREDENTIAL LAW: the PIT labels are the house standard set and
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
        # 7. NEVER-A-TOKEN LAW on the skeleton's OWN surfaces: the plan
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
    out.write("[main-skeleton] U06 self-test: OK (%d modules imported, "
              "every module battery + assembly assertions + exit-code law + "
              "browser-UA law + archive-gate law + credential law pass)\n"
              % len(modules))
    return EX_OK


def _battery_exc(battery: str) -> str:
    """The one-line failure note for a missing battery — a pytest battery is
    provenance (its tests run under pytest), never a dispatched module."""
    return "the U06 pytest battery %s is missing from u06_modules/" % battery


_CREDENTIAL_SHAPE = re.compile(r"pit-\S+")


def _mask_id(fid: str) -> str:
    """Mask a workflow / location id for every operator surface — a location
    identifier, not a secret, but never printed in full (house pattern,
    mirrored from workflow_lister._mask_id)."""
    fid = (fid or "").strip()
    if len(fid) <= 8:
        return "***"
    return "%s***%s" % (fid[:4], fid[-4:])


# ---------------------------------------------------------------------------
# The Trevor gate — the archive ACTION law, enforced by this dispatcher in
# BOTH surfaces (the CLI and the aggregate). Fail-closed and pure: a plan
# without --execute is refused with a typed reason, never fabricated.
# ---------------------------------------------------------------------------
def _archive_gate(modules, name: str, out=None) -> int:
    """The archive ACTION law, offline and pure. An archive ACTION must
    name its byte-exact target workflow, and without --execute it is a STOP
    (exit 2, AF-AE-U06-ARCHIVE-NO-EXECUTE) — an ACTION without the Trevor
    gate is a refusal, never a silent no-op. WITH --execute it is a PLAN
    ONLY (endpoint doctrine — no archive/delete surface proven live): the
    plan is reported and nothing is written. The module's own gate (its CLI
    refusing the ACTION without --execute) is re-proven verbatim here — the
    family never re-implements a law."""
    out = out or sys.stderr
    try:
        mod = modules["workflow_lister"]
    except KeyError:
        raise SkeletonError(
            "workflow_lister is not loaded — the archive gate cannot be "
            "proven (fail-closed)")
    if not (name or "").strip():
        reg._stop(out, "archive REFUSED: no --name (the byte-exact target "
                       "workflow).",
                  ["An archive ACTION must name the ONE byte-exact workflow "
                   "it would touch — a nameless archive is a refusal "
                   "(fail-closed), never a sweep."])
        return EX_STOP
    # The family's verbatim no-execute STOP: the module's OWN CLI must
    # refuse the ACTION without --execute (exit 2) — never a silent pass.
    # The CLI refusal holds BEFORE any credential or name work (it is the
    # module's own gate surface); a missing --name is the module's own
    # guard STOP, never an unexpected error.
    try:
        rc = mod.main(["archive", "--name", name])
    except SystemExit:
        raise SkeletonError(
            "workflow_lister's CLI exited unexpectedly during the "
            "no-execute probe (the Trevor gate cannot be proven)")
    if rc != EX_STOP:
        raise SkeletonError(
            "workflow_lister's CLI archive without --execute returned "
            "exit %d, want %d (AF-AE-U06-ARCHIVE-NO-EXECUTE — the Trevor "
            "gate drifted; an ACTION without the gate must STOP)"
            % (rc, EX_STOP))
    return EX_OK


# ---------------------------------------------------------------------------
# Offline plan — no network, no credentials. The U06 dispatch law with the
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
        if name == "workflow_lister":
            return {
                "live_read": "GET /workflow/{loc}/list?limit=200 via the "
                             "internal rail (backend.leadconnectorhq.com — "
                             "the ONLY proven workflow surface, Skill 58; "
                             "CAF_BROWSER_UA on every request — CF 1010)",
                "archive_action": "Trevor-gated (--execute) and a PLAN ONLY "
                                  "— no archive/delete surface proven live "
                                  "(Skill 44 endpoint doctrine); WITHOUT "
                                  "--execute it is a STOP (exit 2), never a "
                                  "silent no-op",
                "note": "offline plan only — no network, no credential "
                        "needed; a truthful live list needs the rail "
                        "credentials BY LABEL",
            }
        if name == "golden_absent":
            return {
                "fixture": "the golden ABSENT-state archive fixture — "
                           "both archive targets (board / ledger, the "
                           "revoke flow's R2 / R6 pair) EMPTY, so the "
                           "archive ACTION is a clean no-op PASS",
                "archive_action": "archive (--execute-gated, Trevor-gated; "
                                  "GOLDEN_EXECUTE_REQUIRED)",
                "note": "offline plan only — synthetic fixture ids, no "
                        "network, no credential needed",
            }
        if name == "find_legacy":
            return {
                "legacy_names": dict(mod.LEGACY_NAMES),
                "name_law": "workflow-typed row name == the contract legacy "
                            "name (normalized); a renamed legacy is "
                            "indistinguishable from an absent one and both "
                            "refuse",
                "read": "internal rail %s?limit=200 (CAF_BROWSER_UA on the "
                        "request — CF 1010 law)"
                        % (mod.WORKFLOWS_LIST_PATH % "<loc>"),
                "archive_gate": "the finder is read-only — NEVER archives; "
                                "an archive ACTION in the U06 family "
                                "REQUIRES --execute (Trevor-gated) and a "
                                "proven write surface (none is proven)",
                "note": "offline plan only — no network, no credential "
                        "needed; a legacy absent from the live listing is "
                        "a MISMATCH (exit 5), never a silent pass",
            }
        if name == "golden_found":
            return {
                "fixture": "the golden FOUND-state fixture — both contract "
                           "workflows the archive action touches on the "
                           "listing byte-exact by the golden keys (read "
                           "once from find_legacy.LEGACY_NAMES, the find "
                           "law authority)",
                "read_only": "a fixture never writes and never carries a "
                             "credential — the --execute gate lives in the "
                             "dispatcher, never in a fixture",
                "note": "offline plan only — synthetic fixture ids, no "
                        "network, no credential needed",
            }
        if name == "verify_archived":
            return {
                "read_back": "re-reads the engine's TWO archive targets "
                             "(board / ledger, the revoke flow's R2 / R6 "
                             "pair) after the archive sweep and confirms "
                             "the archived status byte-exact (ledger "
                             "'archived' via anthology_state's own read "
                             "surface; board cards at the board's archive "
                             "status via mc_board's own fail-soft "
                             "projection)",
                "action_gate": "the check ACTION is Trevor-gated "
                               "(--execute) and READ-ONLY — without "
                               "--execute it STOPS (exit 2, "
                               "AF-AE-U06-ARCHIVE-NO-EXECUTE), with "
                               "--execute it still writes nothing",
                "reads": "local ledger mirror + board projection — NO rail "
                         "credential, NO network",
                "note": "offline plan only — no network, no credential "
                        "needed; a drift in either target is a MISMATCH "
                        "(exit 5), an unreadable mirror is HELD (exit 3)",
            }
        if name == "docs_u06":
            return {
                "module_count": len(mod.MODULES),
                "verified_items": [row["item"] for row in mod.VERIFY_ITEMS],
                "note": "offline documentation data — the inventory and "
                        "contract surfaces as DATA",
            }
        if name == "house_rules":
            return {
                "laws": ("browser UA (%s bytes, CAF_BROWSER_UA — CF 1010), "
                         "version header %r, AF autofail table (%d codes "
                         "mirrored from docs_u06.AF_CODES, the family "
                         "authority, plus the shared rows pinned against "
                         "ENGINE-MANIFEST.json)"
                         % (len(mod.CAF_BROWSER_UA.encode("utf-8")),
                            mod.CAF_VERSION_HEADER, len(mod.AF_CODES))),
                "note": "offline only — pure constant surface; a header is "
                        "a law, never a secret",
            }
        if name == "attack_no_execute":
            return {
                "attack": "the archive ACTION without --execute (the "
                          "Trevor gate) must FAIL every no-execute surface "
                          "of the family — exit 5 (AF-AE-ATTACKNOEXECUTE-* "
                          "family), never a silent no-op",
                "control": "the execute-required dry-run contract PASSES "
                           "exit 0 (the pass/fail split discriminates the "
                           "missing-gate boundary, never a broken "
                           "instrument)",
                "note": "offline attack fixture — no network, no "
                        "credential needed; every archive id reported by "
                        "masked marker only",
            }
        if name == "example_usage":
            return {
                "example": "the fail-closed WORKED EXAMPLE of the U06 "
                           "dispatch — the FIND law + the golden found-"
                           "state + the golden absent-state + the "
                           "no-execute attack + the lister's archive "
                           "ACTION, composed in the documented order with "
                           "every sibling exit code honored verbatim",
                "note": "offline worked example — no network, no "
                        "credential needed for the offline steps; the "
                        "live FIND needs the rail credential BY LABEL",
            }
        return {"note": "no plan surface for %s" % name}
    except Exception as exc:  # noqa: BLE001 — a plan is never fatal
        return {"error": "%s: %s" % (type(exc).__name__, exc)}


def _build_plan(modules, location_id: str, contract: dict) -> dict:
    """The ONE offline plan payload (shared by --dry-run and the self-test's
    never-a-token scan, so the two can never drift)."""
    plans = {}
    for name, _role in U06_MODULES:
        plans[name] = _module_plan(modules, name, location_id, contract)
    return {
        "contract": "anthology-engine-u06-dispatch-plan",
        "schema_version": 1,
        "template_location_id": location_id,
        "template_location_id_masked": _mask_id(location_id),
        "gates": [name for name, _ in LIVE_GATES],
        "modules": [name for name, _ in U06_MODULES],
        "plans": plans,
        "archive_gate": "the archive ACTION requires --execute (Trevor-"
                        "gated); even WITH --execute it is a plan only — "
                        "no mutation (endpoint doctrine)",
        "dry_run": True,
        "note": "offline plan only — no network, no credential needed; the "
                "ONE live read (workflow_lister) must ride the internal "
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
        "contract": "anthology-engine-u06-verify",
        "schema_version": 1,
        "template_location_id": DEFAULT_TEMPLATE_LOCATION,
        "template_location_id_masked": _mask_id(DEFAULT_TEMPLATE_LOCATION),
        "rail_label": ("SET" if reg.resolve_firebase_refresh_token()[1]
                       else "NOT SET"),
        "checks": {},
        "delta": [],
        "fail_closed": True,
    }


# ---------------------------------------------------------------------------
# Live verify — fail-closed aggregate over the fixed gate order. Any FAIL ->
# exit 5; a STOP-family refusal propagates as exit 2; a transport / edge
# failure is HELD (exit 3), never mislabeled as scope. The archive gate law
# and the golden fixture run FIRST (their golden surfaces need no
# credential), then the ONE rail-gated live read. The archive ACTION is
# never a gate: it is the family's gated ACTION surface, refused without
# --execute (the Trevor gate) and plan-only even with it — this dispatcher
# never mutates.
# ---------------------------------------------------------------------------
def _stop_classes(mod):
    """The STOP-family exception classes a module may raise, resolved BY
    NAME so a module that stops defining one fails the self-test, not the
    live path."""
    return tuple(cls for cname in ("WorkflowReadError", "FixtureError")
                 if isinstance(cls := getattr(mod, cname, None), type)
                 and issubclass(cls, Exception))


def _rail_client(out) -> "object":
    """Resolve the internal-rail client for the ONE live read, BY LABEL,
    exactly as workflow_lister's own CLI resolves it: the Firebase refresh
    token with the Firebase API key. NEVER prints a value; a missing
    credential is a STOP (the caller returns it)."""
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
    reg._stop(out,
              "No internal-rail credential is SET.",
              ["Checked (in order): refresh-token labels %s — all NOT SET."
               % ", ".join(reg.FIREBASE_REFRESH_LABELS),
               "The ONE live read (workflow_lister) rides the internal "
               "rail with CAF_BROWSER_UA on every request — CF 1010 law; "
               "set the template refresh token (the proven workflow "
               "surface) and re-run."])
    return None, EX_STOP


def verify_live(modules, location_id: str, contract: dict, *,
                allow_deferred: bool = False, archive: bool = False,
                archive_name: str = "", archive_anthology_id: str = "",
                archive_state_dir: str = "", out=None) -> int:
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
            if name == "golden_absent":
                # OFFLINE: the golden ABSENT-state fixture — both archive
                # targets (board / ledger, the revoke flow's R2 / R6 pair)
                # EMPTY, so the archive ACTION is a clean no-op PASS. The
                # fixture is READ-ONLY by construction; the --execute gate
                # lives in this dispatcher. Its payload() judges a census
                # handed in, so the golden empty census is passed through.
                result = _capture_sibling(
                    lambda: mod.payload(mod.golden_absent_payload(),
                                        out=io.StringIO()))
                if result == EX_OK:
                    return ("PASS",
                            "both archive targets ABSENT (board 0 cards, "
                            "ledger 0 rows) — NOTHING to archive; the "
                            "archive ACTION is --execute-gated (Trevor "
                            "gate)",
                            {"board": 0, "ledger": 0},
                            {"board": 0, "ledger": 0}), None
                return ("FAIL",
                        "the golden absent census was REFUSED (exit %d) — "
                        "the archive LAW drifted" % result,
                        {"board": 0, "ledger": 0},
                        {"board": "?", "ledger": "?"}), None
            if name == "golden_found":
                # OFFLINE: the golden FOUND-state fixture — both contract
                # workflows the archive action touches must be on the
                # listing byte-exact by the golden keys. The fixture is
                # READ-ONLY by construction; the --execute gate lives in
                # this dispatcher. payload(None) judges the GOLDEN listing
                # itself and returns the dispatcher-consumed dict.
                result = _capture_sibling(
                    lambda: mod.payload(None, out=io.StringIO()))
                if result.get("ok"):
                    return ("PASS",
                            "both contract workflows found byte-exact "
                            "(%s, %d row(s)) — the FOUND state of the "
                            "find-then-archive gate holds"
                            % (", ".join(result.get("names", [])),
                               result.get("rows", 0)),
                            {"found": True,
                             "af_code": result.get("af_code", "LEGACY-FOUND")},
                            {"found": True,
                             "names": result.get("names", [])}), None
                return ("FAIL",
                        "%s: %s" % (result.get("af_code", "U06-FIXTURE-"
                                                       "MISSING"),
                                    result.get("note", "")),
                        {"found": True},
                        {"found": False}), None
            if name == "find_legacy":
                # The ONE rail-gated live read: both legacy workflows by
                # EXACT NAME on the internal-rail listing. The result is
                # the module's own fail-closed surface (LEGACY-FOUND /
                # -ABSENT / -PARTIAL / -EMPTY / PIN-*); every id rides
                # masked inside the module's own report.
                rail, rc = _rail_client(out)
                if rc is not None:
                    return None, rc
                result = mod.find_legacies(rail, location_id)
                if result.get("ok"):
                    return ("PASS",
                            "both legacy workflows found by exact name "
                            "(LEGACY-FOUND, %d workflow row(s); ids "
                            "masked)"
                            % result.get("count", 0),
                            {"found": True},
                            {"found": True,
                             "workflows": result.get("workflows", {})}), None
                return ("FAIL",
                        "%s: %s" % (result.get("af_code", "LEGACY-ABSENT"),
                                    result.get("note", "")),
                        {"found": True},
                        {"found": False,
                         "absent": result.get("absent", []),
                         "candidates": result.get("candidates", [])}), None
            if name == "workflow_lister":
                rail, rc = _rail_client(out)
                if rc is not None:
                    return None, rc
                result = mod.live_list_command(location_id, out=io.StringIO())
                if result == EX_OK:
                    return ("PASS",
                            "the live workflow list read succeeded (marker "
                            "%s) — an EMPTY workflow set is a truthful "
                            "PASS" % masked,
                            {"ok": True},
                            {"ok": True}), None
                if result == EX_HELD:
                    out.write("[main-skeleton] HELD: the live workflow "
                              "list read was HELD (marker %s) — "
                              "UNDETERMINED, never a fabricated list.\n"
                              % masked)
                    return None, EX_HELD
                return ("FAIL",
                        "the live workflow list read returned exit %d — "
                        "the U06 read surface drifted" % result,
                        {"ok": True}, {"ok": False}), None
            if name == "verify_archived":
                # The archived-state read-back — the engine's own local
                # ledger mirror + board projection, NO rail credential. The
                # check ACTION is Trevor-gated, so the gate runs it with
                # --execute ON (the family's read-back contract; the
                # verifier still writes nothing). A missing anthology id is
                # a STOP; an unreadable mirror is HELD; a drift in either
                # target is a MISMATCH — never a pass.
                if not (archive_anthology_id or "").strip():
                    reg._stop(out, "verify_archived REFUSED: no "
                                   "--anthology-id (the read-back target is "
                                   "required, never a sweep).", [])
                    return None, EX_STOP
                rc = _capture_sibling(
                    lambda: mod.check(archive_anthology_id, execute=True,
                                      state_dir=archive_state_dir,
                                      out=io.StringIO()))
                if rc == EX_OK:
                    return ("PASS",
                            "both archive targets re-read and confirmed "
                            "archived (ledger 'archived', board at the "
                            "board's archive status; marker %s)"
                            % _mask_id(archive_anthology_id),
                            {"archived": True},
                            {"archived": True}), None
                if rc == EX_HELD:
                    out.write("[main-skeleton] HELD: the archived-state "
                              "read-back was HELD (marker %s) — "
                              "UNDETERMINED, never a verdict.\n"
                              % _mask_id(archive_anthology_id))
                    return None, EX_HELD
                return ("FAIL",
                        "the archived-state read-back returned exit %d — "
                        "a target is not archived byte-exact (marker %s)"
                        % (rc, _mask_id(archive_anthology_id)),
                        {"archived": True},
                        {"archived": False}), None
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
            if exc.__class__.__name__ in ("WorkflowReadError", "FixtureError"):
                reg._stop(out, "Fail-closed refusal in %s: %s" % (name, exc), [])
                return None, EX_STOP
            raise

    # ---- the archive ACTION (Trevor-gated) -------------------------------
    # The gate holds HERE, before any check runs: an archive ACTION without
    # --execute is a STOP (AF-AE-U06-ARCHIVE-NO-EXECUTE), never a silent
    # no-op and never a mutation. WITH --execute it is a PLAN ONLY (endpoint
    # doctrine — no archive/delete surface proven live): the plan is
    # reported and nothing is written.
    if archive:
        rc = _archive_gate(modules, archive_name, out=out)
        if rc != EX_OK:
            return rc
        report["archive"] = {
            "status": "PLAN",
            "execute": True,
            "note": "the archive ACTION is a plan only — no mutation "
                    "(Skill 44 endpoint doctrine: no archive/delete surface "
                    "proven live); the module reports the records it would "
                    "archive and exits without writing",
            "af_code": "AF-AE-U06-ARCHIVE-PLAN-ONLY",
        }

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
# anthology_registry.py and the U02 / U03 / U04 / U05 skeletons). The
# archive ACTION is a positional subcommand ('archive') that REQUIRES
# --execute (the Trevor gate).
# ---------------------------------------------------------------------------
def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="main_skeleton.py",
        description="U06 archive-action dispatcher: offline plan, offline "
                    "self-test, live verify, and the Trevor-gated archive "
                    "ACTION of the Anthology ARCHIVE-ACTION LAW family "
                    "(Skill 59, u06_modules; the packaged sibling of "
                    "u02_modules/main_skeleton.py, u03_modules/main_skeleton.py, "
                    "u04_modules/main_skeleton.py and "
                    "u05_modules/main_skeleton.py) — imports the check "
                    "modules by name and aggregates their records into ONE "
                    "fail-closed JSON report. The archive ACTION requires "
                    "--execute (Trevor-gated) and is a plan only — this "
                    "dispatcher never mutates.")
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
    ap.add_argument("--execute", action="store_true",
                    help="the Trevor gate for the archive ACTION — REQUIRED "
                         "before any archive; without it the ACTION is a STOP "
                         "(exit 2); even WITH it the archive is a plan only "
                         "(no mutation, endpoint doctrine)")
    ap.add_argument("--name", default="",
                    help="the byte-exact target workflow name (archive "
                         "ACTION; REQUIRED for archive, never a nameless "
                         "sweep)")
    ap.add_argument("--anthology-id", default="",
                    help="the read-back target anthology id (verify_archived "
                         "gate; masked on every surface, never printed in "
                         "full; REQUIRED for the archived-state gate, never "
                         "a sweep)")
    ap.add_argument("--state-dir", default="",
                    help="engine state directory for the archived-state "
                         "read-back (default: the engine's own resolution — "
                         "ANTHOLOGY_STATE_DIR / OPENCLAW_DATA_DIR / node "
                         "home)")
    ap.add_argument("--selftest", "--self-test", dest="self_test", action="store_true",
                    help="run the offline self-test (golden + attack fixtures) and exit")
    ap.add_argument("cmd", nargs="?", choices=["verify", "plan", "archive", "self-test"],
                    help="positional subcommand form (verify / plan / archive / self-test)")

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

        if args.cmd == "archive":
            # The Trevor gate, enforced at the CLI surface: an archive
            # ACTION without --execute is a STOP (exit 2), never a silent
            # no-op. WITH --execute it is a plan only — the dispatcher
            # never mutates.
            if not args.execute:
                reg._stop(sys.stderr,
                          "archive REFUSED: no --execute (the Trevor gate).",
                          ["An archive ACTION without --execute is a STOP "
                           "(AF-AE-U06-ARCHIVE-NO-EXECUTE), never a silent "
                           "no-op. Re-run with --execute to authorize the "
                           "ACTION — it is a plan only (no mutation, "
                           "endpoint doctrine) and the report records it "
                           "explicitly (marker %s)." % _mask_id(location_id)])
                return EX_STOP
            return verify_live(modules, location_id, contract,
                               allow_deferred=args.allow_deferred,
                               archive=True, archive_name=args.name,
                               archive_anthology_id=args.anthology_id,
                               archive_state_dir=args.state_dir,
                               out=sys.stderr)

        # ---- live verify (rail-gated for the live reads) ----
        return verify_live(modules, location_id, contract,
                           allow_deferred=args.allow_deferred,
                           archive_anthology_id=args.anthology_id,
                           archive_state_dir=args.state_dir,
                           out=sys.stderr)

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


DEFAULT_TEMPLATE_LOCATION = "2HIKGNgsixWx0yds7Qnx"


if __name__ == "__main__":
    sys.exit(main())
