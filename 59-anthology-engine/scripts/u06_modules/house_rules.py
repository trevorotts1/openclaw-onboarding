#!/usr/bin/env python3
# =============================================================================
# SKILL 59 — ANTHOLOGY ENGINE :: u06_modules/house_rules.py  (U06 tooling)
# HOUSE RULES CONSTANTS MODULE — the ONE canonical surface for the engine's
# fixed laws: the browser User-Agent (CF 1010), the Convert and Flow version
# header, and the complete AF autofail code table. Imported BY NAME as
# u06_modules.house_rules, per the u06_modules package contract in __init__.py
# (pure namespace container; side-effect-free at import).
#
# WHERE THIS SITS: scripts/u06_modules/ — an importable module under the U06
# package. It is NOT a manifest row and it is NOT a dispatched check module:
# it ships as the shared constant surface the U06 live verifier, its check
# modules, and the family's batteries import, so a law can NEVER drift
# between the modules that enforce it — exactly the delta_reporter.py
# single-implementation doctrine (a law read once, in one module) that the
# U03 / U05 families already practice (their house_rules.py is this module's
# packaged sibling, and the U06 table below is mirrored from
# docs_u06.AF_CODES, the family's own autofail authority, plus the manifest
# table the U05 sibling already pins byte-exact).
#
# WHAT THIS OWNS
#   1. THE BROWSER UA LAW (CF 1010). backend.leadconnectorhq.com is
#      Cloudflare-fronted and 403s urllib's default "Python-urllib/x.y"
#      User-Agent at the WAF edge (CF error 1010) BEFORE the request ever
#      reaches Convert and Flow (W0.6 / GK-09: the proven failure mode, and
#      the proven-live fix string ported byte-for-byte from the Podcast gate).
#      CAF_BROWSER_UA below is PORTED BYTE-FOR-BYTE from
#      anthology_registry.CAF_BROWSER_UA (the house pattern every adapter
#      rides through reg.InternalRailClient / reg._internal_request_headers)
#      so this module's own copy cannot drift — and the offline self-test
#      pins the two strings byte-equal.
#      The UA is NOT a secret: it is a public, per-request header string
#      carried on every request, exactly as the registry sends it. The rule
#      it enforces is absolute: ANY module in this package that talks to
#      GoHighLevel / Convert and Flow (services.leadconnectorhq.com,
#      Cloudflare-fronted) MUST send a browser User-Agent on EVERY request —
#      the U06 find/read surfaces (find_legacy, workflow_lister) ride the
#      internal rail and depend on this law.
#   2. THE VERSION HEADER LAW. The Convert and Flow (LeadConnector v2)
#      Version header is the fixed "2021-07-28" (verified at W0.5;
#      reg.CAF_VERSION_HEADER) — the same byte-exact header reg.CafClient /
#      reg.InternalRailClient send on every request. Version is also NOT a
#      secret.
#   3. THE AF CODE LAW. The complete autofail table as immutable constants:
#      the U06 family's OWN codes (mirrored byte-exact from docs_u06.AF_CODES
#      — the family's autofail authority; the U06-specific rows are PENDING
#      in ENGINE-MANIFEST.json, verified at ship time 2026-08-11, exactly as
#      docs_u06 declares) plus the SHARED house codes (the manifest table
#      this sibling pins: AF-AE-READBACK-MISMATCH and AF-AE-TEMPLATE-ATTACK
#      already live in the manifest; the U02 / U03 / U04 / U05 families ride
#      the same shared rows). A code can NEVER be misspelled or drifted
#      between a raising module and the family's authority. The self-test
#      pins the family rows byte-exact against docs_u06.AF_CODES and the
#      shared rows byte-exact against ENGINE-MANIFEST.json's autofails
#      (when the manifest is present at the module's canonical repo path) —
#      a reordered or reworded authority trips the mirror first (fail-closed:
#      the mirror never silently re-sorts).
#
# FAIL-CLOSED (the whole point): a drifted UA, a drifted version header, a
# code set that no longer matches its authority (docs_u06.AF_CODES for the
# U06 rows, the manifest for the shared rows), a non-AF-shaped code, or an
# empty table is a REFUSAL (HouseRulesError / exit 4) — never a silent pass,
# never a fabricated success.
#
# NEVER-A-TOKEN SURFACE: this module holds ZERO credential surface — it reads
# no env var and resolves no label. A constants module cannot leak what it
# never holds (the same construction the golden/attack fixture siblings
# carry: a fixture is DATA, not code). The self-test proves the point: the
# never-a-token scan refuses a credential-shaped string anywhere on the
# module's own plan surface.
#
# OFFLINE: this module makes NO network call. The self-test is fully offline
# (no token, no wire) and pins every law byte-exact.
#
# EXIT CODES (house convention 0/1/2/3/4/5; ENGINE-MANIFEST.json
# exit_code_house_convention):
#   0  self-test / plan PASS (offline)
#   1  unexpected error
#   2  STOP refusal — a law authority present but unreadable/malformed
#      (docs_u06 or ENGINE-MANIFEST.json cannot be read, so the AF code law
#      is unverifiable; the constants still import — the law is the
#      authority's, the mirror is this module's)
#   4  self-test FAILED — a law drifted or a code deviates (a tamper NEVER
#      masquerades as exit 1)
#   (3 and 5 are not applicable here: no live surface, no read-back.)
#
# USAGE (machine surface — ONE JSON object on stdout; human notes on stderr;
# --self-test is OFFLINE and needs NO token and NO network):
#   house_rules.py plan          # offline: the three laws with their sources
#   house_rules.py self-test     # offline golden + attack battery
#
# STDLIB ONLY. Calls NO model. Sibling import bootstrap identical to the
# other u06_modules: sys.path.insert to scripts/ then
# `import anthology_registry as reg` for its canonical constants.
# DOCTRINE: move in silence; NOTHING Anthropic in any runtime file; Convert
# and Flow naming in every client surface; NEVER print a secret value; the
# archive ACTION requires --execute (Trevor-gated) — this constants module
# carries no ACTION surface at all.
# =============================================================================
"""house_rules.py — the engine's canonical constant surface for the U06
family: browser UA (CF 1010), Convert and Flow version header, and the
complete AF autofail code table (the U06 family's rows + the shared house
rows)."""

from __future__ import annotations

import argparse
import io
import json
import re
import sys
from pathlib import Path

# Sibling import bootstrap (house convention): the registry owns the
# canonical CAF_BROWSER_UA / CAF_VERSION_HEADER constants and the fail-closed
# helper surfaces; this module mirrors them byte-exact and pins the mirror.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import anthology_registry as reg  # noqa: E402

EX_OK, EX_ERR, EX_STOP = reg.EX_OK, reg.EX_ERR, reg.EX_STOP
EX_VIOLATION = 4  # enforced violation detected (self-test FAILED)

# Canonical repo layout for the mirror-checks (Skill 59 root ->
# ENGINE-MANIFEST.json, exactly where the pinned install ships it; and the
# u06_modules package dir for docs_u06, the U06 family's autofail
# authority).
SKILL_DIR = Path(__file__).resolve().parent.parent.parent
MANIFEST_PATH = SKILL_DIR / "ENGINE-MANIFEST.json"
U06_DIR = Path(__file__).resolve().parent
if str(U06_DIR) not in sys.path:
    sys.path.insert(0, str(U06_DIR))
import docs_u06 as _u06docs  # noqa: E402  (the U06 autofail authority)

# ---------------------------------------------------------------------------
# LAW 1 — THE BROWSER UA (CF 1010). Ported BYTE-FOR-BYTE from
# anthology_registry.CAF_BROWSER_UA (the proven-live Podcast-gate string the
# registry carries; the well-formed four-segment Chrome build that passes the
# Cloudflare edge fronting backend.leadconnectorhq.com / the internal rail).
# Enforced: every request to that host carries a browser UA on EVERY request
# — urllib's default is 403'd (CF error 1010) before it reaches Convert and
# Flow. A header, never a secret.
# ---------------------------------------------------------------------------
CAF_BROWSER_UA = reg.CAF_BROWSER_UA

# ---------------------------------------------------------------------------
# LAW 2 — THE VERSION HEADER. Convert and Flow (LeadConnector v2) pins the
# API Version header at "2021-07-28" (verified at W0.5; reg.CAF_VERSION_HEADER
# is what reg.CafClient / reg.InternalRailClient send on every request). Also
# a header, never a secret.
# ---------------------------------------------------------------------------
CAF_VERSION_HEADER = reg.CAF_VERSION_HEADER

# ---------------------------------------------------------------------------
# LAW 3 — THE AF CODE TABLE. The complete autofail table as immutable
# constants, in TWO blocks:
#   (a) THE FULL TABLE — mirrored byte-exact from docs_u06.AF_CODES, the
#       family's autofail authority (the codes the family's own surfaces
#       declare): the U06-specific rows (AF-AE-U06-*, PENDING in
#       ENGINE-MANIFEST.json, verified at ship time 2026-08-11, exactly as
#       docs_u06 declares), the AF-AE-ATTACKNOEXECUTE-* wildcard row, and
#       the two shared rows docs_u06 itself declares — AF-AE-READBACK-
#       MISMATCH (the post-write read-back law, already stamped in
#       ENGINE-MANIFEST.json's autofails) and AF-AE-TEMPLATE-ATTACK (the
#       enforced-violation code every family battery raises; the manifest's
#       own exit-code language names it verbatim).
# A raising module names the constant, never a hand-typed literal, so a
# code can never drift from the family authority.
# self_test() proves byte-equality with docs_u06.AF_CODES — SAME set, SAME
# order, SAME exit mapping — and proves the shared rows that live in the
# manifest (AF-AE-READBACK-MISMATCH) against ENGINE-MANIFEST.json's
# autofails; any deviation is a REFUSAL (exit 4, the AF-AE-HASH-PIN
# family's audit language: a drifted enforcement set is a tamper).
# ---------------------------------------------------------------------------
# The FULL AF table — constants declared in docs_u06.AF_CODES' EXACT order
# (the family authority's 14 rows: the U06-specific rows, the no-execute
# wildcard row, and the two shared rows the authority itself declares), so
# the table below is a literal mirror and a reordered authority trips the
# self-test first (fail-closed: the mirror never silently re-sorts).
AF_U06_ASSEMBLY_INCOMPLETE = "AF-AE-U06-ASSEMBLY-INCOMPLETE"
AF_U06_ARCHIVE_NO_EXECUTE = "AF-AE-U06-ARCHIVE-NO-EXECUTE"
AF_U06_ARCHIVE_NO_NAME = "AF-AE-U06-ARCHIVE-NO-NAME"
AF_U06_ARCHIVE_PLAN_ONLY = "AF-AE-U06-ARCHIVE-PLAN-ONLY"
AF_U06_NAME_NOT_FOUND = "AF-AE-U06-NAME-NOT-FOUND"
AF_U06_NAME_AMBIGUOUS = "AF-AE-U06-NAME-AMBIGUOUS"
AF_U06_LEGACY_ABSENT = "AF-AE-U06-LEGACY-ABSENT"
AF_U06_LEGACY_PARTIAL = "AF-AE-U06-LEGACY-PARTIAL"
AF_U06_LEGACY_EMPTY = "AF-AE-U06-LEGACY-EMPTY"
AF_U06_PIN_MISSING = "AF-AE-U06-PIN-MISSING"
AF_U06_PIN_ON_WRONG_NAME = "AF-AE-U06-PIN-ON-WRONG-NAME"
AF_ATTACK_NO_EXECUTE = "AF-AE-ATTACKNOEXECUTE-*"
AF_READBACK_MISMATCH = "AF-AE-READBACK-MISMATCH"
AF_TEMPLATE_ATTACK = "AF-AE-TEMPLATE-ATTACK"

# The complete, immutable AF table (frozen; one canonical order — the U06
# authority's own order, never re-sorted). Built from the constants above
# so a code can never be entered twice or misspelled.
_AF_TABLE = (
    AF_U06_ASSEMBLY_INCOMPLETE,
    AF_U06_ARCHIVE_NO_EXECUTE,
    AF_U06_ARCHIVE_NO_NAME,
    AF_U06_ARCHIVE_PLAN_ONLY,
    AF_U06_NAME_NOT_FOUND,
    AF_U06_NAME_AMBIGUOUS,
    AF_U06_LEGACY_ABSENT,
    AF_U06_LEGACY_PARTIAL,
    AF_U06_LEGACY_EMPTY,
    AF_U06_PIN_MISSING,
    AF_U06_PIN_ON_WRONG_NAME,
    AF_ATTACK_NO_EXECUTE,
    AF_READBACK_MISMATCH,
    AF_TEMPLATE_ATTACK,
)
AF_CODES = tuple(_AF_TABLE)  # public immutable surface; also a set below
AF_CODES_SET = frozenset(_AF_TABLE)

# The U06 family's OWN rows, in docs_u06.AF_CODES' order (the family
# authority's table EXCLUDING the two shared rows — the subset whose
# membership is the family's, so the family subset never absorbs a shared
# row and the shared rows are pinned against the manifest separately).
AF_U06_CODES = tuple(
    c for c in _AF_TABLE
    if c.startswith("AF-AE-U06-") or c == AF_ATTACK_NO_EXECUTE)

# Every AF row must carry the house AF shape: "AF-<family>-<NAME>", with the
# two sanctioned exceptions this table mirrors because the authorities say
# so: "AF-AE-ATTACKNOEXECUTE-*" (docs_u06's wildcard row for the no-execute
# attack family — a pattern the enforcement family raises by convention, not
# a single code) and "AF-AE-TEMPLATE-ATTACK" (the enforced-violation code
# the manifest's own exit-code language names).
_AF_SHAPE_RE = re.compile(r"^AF-[A-Z0-9]+-[A-Z0-9-]+$")
_AF_PATTERN_SHAPE_RE = re.compile(r"^AF-[A-Z0-9]+-[A-Z0-9-]+-\*$")


def _af_shape_ok(code: str) -> bool:
    """The AF shape gate, with the table's two sanctioned exception shapes:
    the wildcard pattern row (AF-AE-ATTACKNOEXECUTE-*) and the manifest's
    enforced-violation code (AF-AE-TEMPLATE-ATTACK). ANY other deviation
    from the AF shape is refused. A well-formed-lookalike code (correct
    shape, wrong value) is NOT a shape violation — it is refused by
    membership instead (the pinned table is the membership authority)."""
    if code == AF_TEMPLATE_ATTACK:
        return bool(_AF_SHAPE_RE.match(code))
    if code == AF_ATTACK_NO_EXECUTE:
        return bool(_AF_PATTERN_SHAPE_RE.match(code))
    return bool(_AF_SHAPE_RE.match(code) or _AF_PATTERN_SHAPE_RE.match(code))


class HouseRulesError(Exception):
    """A fail-closed refusal: a house law drifted (UA / version header /
    AF table no longer byte-equal to its canonical source)."""


# ---------------------------------------------------------------------------
# The law surfaces.
# ---------------------------------------------------------------------------
def af_code(name: str) -> str:
    """Resolve an AF code by constant name, fail-closed: an unknown name or a
    value that is not in the pinned table is a REFUSAL, never a guess."""
    value = globals().get(name)
    if not isinstance(value, str):
        raise HouseRulesError(
            "AF code constant %r is not a string" % name)
    if value not in AF_CODES_SET:
        raise HouseRulesError(
            "AF code constant %r resolved to %r, which is NOT in the pinned "
            "AF table -- the table must be re-mirrored from docs_u06.AF_CODES "
            "and ENGINE-MANIFEST.json" % (name, value))
    return value


def _check_laws(out) -> None:
    """Pins the mirror against the registry byte-exact; raises
    HouseRulesError on any drift."""
    if CAF_BROWSER_UA != reg.CAF_BROWSER_UA:
        raise HouseRulesError(
            "CAF_BROWSER_UA drifted from the registry's proven-live string")
    if CAF_VERSION_HEADER != reg.CAF_VERSION_HEADER:
        raise HouseRulesError(
            "CAF_VERSION_HEADER drifted from the registry's W0.5-verified "
            "header")
    if len(AF_CODES) != len(AF_CODES_SET):
        raise HouseRulesError("the AF table carries a duplicate code")
    for code in AF_CODES:
        if not _af_shape_ok(code):
            raise HouseRulesError(
                "AF code %r does not carry the house AF shape -- the table "
                "is polluted" % code)


def _u06_family_codes() -> list:
    """The FULL autofail table from docs_u06.AF_CODES (the family
    authority): every (code, exit, meaning) row, in the authority's exact
    order — the U06-specific rows, the AF-AE-ATTACKNOEXECUTE-* wildcard
    row, and the two shared rows the authority itself declares. Fail-
    closed: a docs_u06 that cannot be read, or an authority whose rows
    lost their code field, is a REFUSAL (HouseRulesError) -- a family law
    that cannot be verified is never a blind skip."""
    rows = _u06docs.af_codes()
    codes = []
    for row in rows:
        code = row[0] if isinstance(row, tuple) and row else None
        if not isinstance(code, str) or not code:
            raise HouseRulesError(
                "docs_u06.AF_CODES carries a row with no code string -- the "
                "family AF law is unverifiable")
        codes.append(code)
    if not codes:
        raise HouseRulesError(
            "docs_u06.AF_CODES carries no autofail row -- the family AF "
            "law is unverifiable")
    return codes


def _manifest_codes(manifest_path: Path) -> list:
    """Reads the manifest's autofail codes, fail-closed: an unreadable or
    malformed manifest at the canonical path is a REFUSAL (HouseRulesError),
    never a blind skip -- a manifest that cannot be read means the shared
    AF code law is unverifiable."""
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise HouseRulesError(
            "ENGINE-MANIFEST.json missing at %s -- the shared AF code law "
            "is unverifiable" % manifest_path)
    except (OSError, IOError, ValueError) as exc:
        raise HouseRulesError(
            "ENGINE-MANIFEST.json unreadable/malformed at %s: %s -- the "
            "shared AF code law is unverifiable" % (manifest_path, exc))
    rows = data.get("autofails")
    if not isinstance(rows, list) or not rows:
        raise HouseRulesError(
            "ENGINE-MANIFEST.json autofails is empty or not a list -- the "
            "shared AF code law is unverifiable")
    codes = []
    for row in rows:
        code = row.get("code") if isinstance(row, dict) else None
        if not isinstance(code, str) or not code:
            raise HouseRulesError(
                "ENGINE-MANIFEST.json autofail row carries no code string")
        codes.append(code)
    return codes


def plan(*, out=None) -> int:
    """Prints the ONE JSON plan object (machine surface, indent 2,
    sort_keys): the three laws with their sources and byte counts."""
    out = out or sys.stdout
    _check_laws(out=out)
    payload = {
        "contract": "anthology-engine-house-rules",
        "laws": {
            "browser_ua": {
                "constant": "CAF_BROWSER_UA",
                "bytes": len(CAF_BROWSER_UA.encode("utf-8")),
                "source": "anthology_registry.CAF_BROWSER_UA (ported "
                          "byte-for-byte from the Podcast gate's "
                          "proven-live string; W0.6 / GK-09)",
                "law": "every request to services.leadconnectorhq.com / "
                       "backend.leadconnectorhq.com (Cloudflare-fronted) "
                       "MUST carry a browser User-Agent on EVERY request -- "
                       "urllib's default 'Python-urllib/x.y' is 403'd at "
                       "the WAF edge (CF error 1010) before it reaches "
                       "Convert and Flow",
                "value": CAF_BROWSER_UA,
            },
            "version_header": {
                "constant": "CAF_VERSION_HEADER",
                "value": CAF_VERSION_HEADER,
                "source": "anthology_registry.CAF_VERSION_HEADER "
                          "(LeadConnector v2, verified at W0.5)",
            },
            "af_codes": {
                "constant": "AF_CODES",
                "count": len(AF_CODES),
                "codes": list(AF_CODES),
                "source": "docs_u06.AF_CODES (the family authority: the "
                          "U06 rows PENDING in the manifest, verified at "
                          "ship time 2026-08-11, plus the shared rows the "
                          "authority declares; the shared "
                          "AF-AE-READBACK-MISMATCH row is also pinned "
                          "against ENGINE-MANIFEST.json autofails)",
            },
        },
    }
    json.dump(payload, out, indent=2, sort_keys=True)
    out.write("\n")
    return EX_OK


def self_test(*, out=None) -> int:
    """OFFLINE self-test (no network, no credential): pins the UA and the
    version header byte-exact against the registry, pins the FULL AF table
    byte-exact against docs_u06.AF_CODES (the family authority — SAME set
    AND SAME order), pins the shared row that lives in the manifest
    (AF-AE-READBACK-MISMATCH) against ENGINE-MANIFEST.json's autofails, and
    proves every attack fixture is REFUSED. A tamper NEVER masquerades as
    exit 1 -- it is exit 4 (AF-AE-HASH-PIN family: a drifted enforcement
    set)."""
    out = out or sys.stdout
    failures = []

    # ---- the golden laws: registry mirror, byte-exact ---------------------
    try:
        _check_laws(out=out)
    except HouseRulesError as exc:
        failures.append("golden laws: %s" % exc)

    # ---- the golden AF table: docs_u06 mirror, byte-exact ------------------
    try:
        u06_codes = _u06_family_codes()
    except HouseRulesError as exc:
        failures.append("docs_u06 read: %s" % exc)
        u06_codes = None
    if u06_codes is not None:
        # The FULL table (14 rows, including the two shared rows) is pinned
        # against the authority's FULL row set — the family subset alone is
        # never mistaken for the whole table. The shared rows are then
        # pinned against the manifest separately below.
        docs_codes = [r[0] if isinstance(r, tuple) and r else None
                      for r in _u06docs.af_codes()]
        if None in docs_codes:
            failures.append("docs_u06.AF_CODES carries a row with no code "
                            "string -- the family AF law is unverifiable")
        elif list(AF_CODES) != list(docs_codes):
            failures.append(
                "AF table drifted from docs_u06.AF_CODES: missing=%s "
                "extra=%s" % (sorted(set(docs_codes) - set(AF_CODES)),
                              sorted(set(AF_CODES) - set(docs_codes))))
        # The family-OWN subset (the U06 rows + the wildcard row) is pinned
        # against the same rows extracted from the authority — a subset that
        # absorbed a shared row, or lost a family row, is a drift.
        family_owned = [c for c in docs_codes
                        if c.startswith("AF-AE-U06-")
                        or c == AF_ATTACK_NO_EXECUTE]
        if list(AF_U06_CODES) != list(family_owned):
            failures.append(
                "the family subset AF_U06_CODES drifted from "
                "docs_u06.AF_CODES: missing=%s extra=%s"
                % (sorted(set(family_owned) - set(AF_U06_CODES)),
                   sorted(set(AF_U06_CODES) - set(family_owned))))
        if set(AF_U06_CODES) & {AF_READBACK_MISMATCH, AF_TEMPLATE_ATTACK}:
            failures.append(
                "the family subset AF_U06_CODES absorbed a shared row")

    # ---- the golden shared rows: manifest mirror, byte-exact --------------
    try:
        manifest_codes = _manifest_codes(MANIFEST_PATH)
    except HouseRulesError as exc:
        failures.append("manifest read: %s" % exc)
        manifest_codes = None
    if manifest_codes is not None:
        if AF_READBACK_MISMATCH not in manifest_codes:
            failures.append(
                "the shared AF row AF-AE-READBACK-MISMATCH is not in "
                "ENGINE-MANIFEST.json's autofails")

    # ---- attack fixtures: every deviation REFUSED --------------------------
    if CAF_BROWSER_UA == "Python-urllib/3.12":
        failures.append("attack not refused: urllib default UA")
    if CAF_BROWSER_UA != (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 "
            "Safari/537.36"):
        failures.append("attack not refused: UA deviates from the "
                        "proven-live four-segment Chrome string")
    if CAF_VERSION_HEADER != "2021-07-28":
        failures.append("attack not refused: version header deviates from "
                        "the W0.5-verified header")
    if not AF_CODES:
        failures.append("attack not refused: empty AF table")
    if len(AF_CODES) != len(AF_CODES_SET):
        failures.append("attack not refused: duplicate AF codes")
    for bad in ("AF-AE-", "", "af-ae-x", "AE-DEPS-MISSING", "AF--X",
                "AF-AE-U06-ARCHIVE/NO"):
        if _af_shape_ok(bad):
            failures.append("attack not refused: malformed code %r passed "
                            "the AF shape gate" % bad)
    # Well-formed lookalikes are refused by MEMBERSHIP, never by shape: a
    # correctly-shaped code that is not in the pinned table must not
    # resolve, and a pinned table polluted with a lookalike is a tamper.
    for lookalike in ("AF-AE-ARCHIVE-NO-EXECUTE", "AF-AE-U06-ARCHIVE-NOEXECUTE",
                      "AF-AE-ATTACKNOEXECUTE-X", "AF-AE-TEMPLATE-ATTACK-EXTRA"):
        if not _af_shape_ok(lookalike):
            failures.append("attack not refused: the shape gate refused a "
                            "well-formed lookalike %r (membership must "
                            "refuse it, never the shape gate)" % lookalike)
        if lookalike in AF_CODES_SET:
            failures.append("attack not refused: well-formed lookalike %r "
                            "polluted the pinned AF table" % lookalike)
    for cname in ("AF_U06_ARCHIVE_NO_EXECUTE", "AF_U06_LEGACY_ABSENT",
                  "AF_READBACK_MISMATCH"):
        try:
            af_code(cname)
        except HouseRulesError as exc:
            failures.append("attack not refused: pinned AF resolution "
                            "failed: %s" % exc)
    try:
        af_code("NOT_A_CONSTANT")
        failures.append("attack not refused: unknown AF constant name")
    except HouseRulesError:
        pass
    try:
        af_code("AF_U06_ARCHIVE_NO_EXECUTED")  # a lookalike constant name
        failures.append("attack not refused: lookalike AF constant name "
                        "resolved")
    except HouseRulesError:
        pass
    for name, value in (("AF_CODES", AF_CODES),
                        ("AF_CODES_SET", AF_CODES_SET),
                        ("AF_U06_CODES", AF_U06_CODES),
                        ("CAF_BROWSER_UA", CAF_BROWSER_UA),
                        ("CAF_VERSION_HEADER", CAF_VERSION_HEADER)):
        if not isinstance(value, (tuple, frozenset, str)) or not value:
            failures.append("attack not refused: %s is empty" % name)

    # ---- the never-a-token proof ------------------------------------------
    # The plan surface (the same builder the CLI prints) must never carry a
    # credential-shaped string — a constants module holds zero credential
    # surface, and the plan proves it on the wire.
    try:
        cap = io.StringIO()
        plan(out=cap)
    except HouseRulesError as exc:
        failures.append("plan surface: %s" % exc)
    else:
        if re.search(r"pit-\S+|Bearer [A-Za-z0-9]", cap.getvalue()):
            failures.append("never-a-token violation: the plan surface "
                            "carries a credential-shaped string")
    import os as _os
    if _os.environ.get("CONVERT_AND_FLOW_PIT") is not None:
        failures.append("env surface present: this module must hold ZERO "
                        "credential surface (CONVERT_AND_FLOW_PIT label "
                        "detected in the environment)")

    if failures:
        out.write("[house-rules] self-test FAILED (%s violations):\n"
                  % len(failures))
        for item in failures:
            out.write("  - %s\n" % item)
        return EX_VIOLATION
    out.write("[house-rules] self-test PASS: UA and version header pinned "
              "byte-exact against the registry; the AF table matches "
              "docs_u06.AF_CODES (%s codes, same set AND same order); the "
              "shared AF-AE-READBACK-MISMATCH row matches "
              "ENGINE-MANIFEST.json; every attack fixture refused; zero "
              "credential surface\n" % len(AF_CODES))
    return EX_OK


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="house_rules.py",
        description="The U06 family's canonical constant surface: browser "
                    "UA (CF 1010), Convert and Flow version header, and the "
                    "complete AF autofail code table -- fail-closed, "
                    "offline, never prints a token (Skill 59). One JSON "
                    "object on stdout.")
    ap.add_argument("cmd", nargs="?", choices=["plan", "self-test"],
                    default="plan")
    if argv is None:
        argv = sys.argv[1:]
    argv = list(argv)
    # Normalize --self-test / --selftest -> positional self-test subcommand
    if "--self-test" in argv:
        argv = ["self-test" if a == "--self-test" else a for a in argv]
    if "--selftest" in argv:
        argv = ["self-test" if a == "--selftest" else a for a in argv]
    args = ap.parse_args(argv)
    try:
        if args.cmd == "self-test":
            return self_test()
        return plan()
    except HouseRulesError as exc:
        sys.stderr.write("[house-rules] STOP: %s\n" % exc)
        return EX_STOP
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write("[house-rules] unexpected error: %s: %s\n"
                         % (type(exc).__name__, exc))
        return EX_ERR


if __name__ == "__main__":
    sys.exit(main())
