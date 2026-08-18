#!/usr/bin/env python3
# =============================================================================
# SKILL 59 — ANTHOLOGY ENGINE :: u07_modules/house_rules.py  (U07 tooling)
# HOUSE RULES CONSTANTS MODULE — the ONE canonical surface for the engine's
# fixed laws: the browser User-Agent (CF 1010), the Convert and Flow version
# header, and the complete AF autofail code table. Imported BY NAME as
# u07_modules.house_rules, per the u07_modules package contract in __init__.py
# (pure namespace container; side-effect-free at import).
#
# WHERE THIS SITS: scripts/u07_modules/ — an importable module under the U07
# package. It is NOT a manifest row: it ships as the shared constant surface
# the U07 live verifier, its check modules, and the family's batteries
# import, so a law can NEVER drift between the modules that enforce it —
# exactly the delta_reporter.py single-implementation doctrine (a law read
# once, in one module) that the U03 / U05 / U06 families already practice
# (their house_rules.py is this module's packaged sibling; the U06 module
# adds its own docs_u06 authority, the U07 module's authority is the
# manifest itself, as the U03 / U05 siblings mirror).
#
# WHAT THIS OWNS
#   1. THE BROWSER UA LAW (CF 1010). backend.leadconnectorhq.com is
#      Cloudflare-fronted and 403s urllib's default "Python-urllib/x.y"
#      User-Agent at the WAF edge (CF error 1010) BEFORE the request ever
#      reaches Convert and Flow (W0.6 / GK-09: the proven failure mode, and
#      the proven-live fix string ported byte-for-byte from the Podcast
#      gate). CAF_BROWSER_UA below is PORTED BYTE-FOR-BYTE from
#      anthology_registry.CAF_BROWSER_UA (the house pattern every adapter
#      rides through reg.CafClient / reg.InternalRailClient /
#      reg._internal_request_headers) so this module's own copy cannot
#      drift — and the offline self-test pins the two strings byte-equal.
#      The UA is NOT a secret: it is a public, per-request header string
#      carried on every request, exactly as the registry sends it. The rule
#      it enforces is absolute: ANY module in this package that talks to
#      GoHighLevel / Convert and Flow (services.leadconnectorhq.com,
#      backend.leadconnectorhq.com — Cloudflare-fronted) MUST send a
#      browser User-Agent on EVERY request — the U07 live surfaces
#      (live_fields_reader) ride the proven public rail GET
#      /locations/{id}/customFields and depend on this law.
#   2. THE VERSION HEADER LAW. The Convert and Flow (LeadConnector v2)
#      Version header is the fixed "2021-07-28" (verified at W0.5;
#      reg.CAF_VERSION_HEADER) — the same byte-exact header reg.CafClient /
#      reg.InternalRailClient send on every request. Version is also NOT a
#      secret.
#   3. THE AF CODE LAW. The complete autofail table mirrored from
#      ENGINE-MANIFEST.json "autofails" (75 rows: the AF-AE-* families plus
#      AE_DEPS_MISSING) as immutable constants, so a code can NEVER be
#      misspelled or drifted between a raising module and the manifest.
#      Self-test asserts byte-equality with the manifest (when the manifest
#      is present at the module's canonical repo path) — the engine's
#      AF-AE-* families and the U03 AF-AE-TEMPLATE-* family all ride this
#      one table. The U07 family's OWN enforcement codes live in the family
#      authority docs_u07.AF_CODES (the U07 catalog module's autofail
#      table: the four exit-4 wildcard rows AF-AE-FIELDMAP-* /
#      AF-AE-GOLDENALLPRESENT-* / AF-AE-MISSINGFINDER-* / AF-AE-TEMPLATE-
#      ATTACK, the real rows AF-AE-FIELD-MISSING (stamped in the manifest)
#      and AF-AE-FIELD-KEY-MISMATCH (PENDING in the manifest, verified at
#      ship time 2026-08-11 exactly as docs_u07 declares), and the shared
#      AF-AE-READBACK-MISMATCH row) — a code can NEVER be misspelled or
#      drifted between a raising module and the family's authority.
#
# FAIL-CLOSED (the whole point): a drifted UA, a drifted version header, a
# code set that no longer matches the manifest, a non-AF-shaped code, or an
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
#   2  STOP refusal — manifest present but unreadable/malformed
#      (the AF code law would be unverifiable; the constants still import —
#      the law is the manifest's, the mirror is this module's)
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
# other u07_modules: sys.path.insert to scripts/ then
# `import anthology_registry as reg` for its canonical constants.
# DOCTRINE: move in silence; NOTHING Anthropic in any runtime file; Convert
# and Flow naming in every client surface; NEVER print a secret value; the
# U07 WRITE ACTION (provisioning a missing field) requires --execute
# (Trevor-gated, per the u07 package-init doctrine and golden_all_present's
# WRITE_ACTION law) — this constants module carries no ACTION surface at
# all.
# =============================================================================
"""house_rules.py — the engine's canonical constant surface for the U07
family: browser UA (CF 1010), Convert and Flow version header, and the full
AF autofail code table (the manifest's 75 rows, the U07 family's authority
exactly as the U03 / U05 siblings mirror; the U07 family's own codes are
carried by docs_u07.AF_CODES, with AF-AE-FIELD-KEY-MISMATCH declared
PENDING in the manifest and verified at ship time 2026-08-11)."""

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

# Canonical repo layout for the manifest mirror-check (Skill 59 root ->
# ENGINE-MANIFEST.json, exactly where the pinned install ships it).
SKILL_DIR = Path(__file__).resolve().parent.parent.parent
MANIFEST_PATH = SKILL_DIR / "ENGINE-MANIFEST.json"
U07_DIR = Path(__file__).resolve().parent
if str(U07_DIR) not in sys.path:
    sys.path.insert(0, str(U07_DIR))
import docs_u07 as _u07docs  # noqa: E402  (the U07 family autofail authority)

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
# LAW 3 — THE AF CODE TABLE. The complete autofail table mirrored from
# ENGINE-MANIFEST.json "autofails": every AF-AE-* code (and the lone
# AE_DEPS_MISSING row) as immutable constants — a raising module names the
# constant, never a hand-typed literal, so a code can never drift from the
# manifest. The engine's AF-AE-* families and the U03 AF-AE-TEMPLATE-*
# family (the fail-closed codes the U03 verifier and check modules raise)
# all ride this one table. self_test() proves byte-equality with the
# manifest — SAME set AND SAME order — and REFUSES any deviation (exit 4,
# AF-AE-HASH-PIN family in the manifest's own audit language: a drifted
# enforcement set is a tamper).
# ---------------------------------------------------------------------------
#      Cloudflare-fronted and 403s urllib's default "Python-urllib/x.y"
#      User-Agent at the WAF edge (CF error 1010) BEFORE the request ever
#      reaches Convert and Flow (W0.6 / GK-09: the proven failure mode, and
#      the proven-live fix string ported byte-for-byte from the Podcast
#      gate). CAF_BROWSER_UA below is PORTED BYTE-FOR-BYTE from
#      anthology_registry.CAF_BROWSER_UA (the house pattern every adapter
#      rides through reg.CafClient / reg.InternalRailClient /
#      reg._internal_request_headers) so this module's own copy cannot
#      drift — and the offline self-test pins the two strings byte-equal.
#      The UA is NOT a secret: it is a public, per-request header string
#      carried on every request, exactly as the registry sends it. The rule
#      it enforces is absolute: ANY module in this package that talks to
#      GoHighLevel / Convert and Flow (services.leadconnectorhq.com,
#      backend.leadconnectorhq.com — Cloudflare-fronted) MUST send a
#      browser User-Agent on EVERY request — the U07 live surfaces
#      (live_fields_reader) ride the proven public rail GET
#      /locations/{id}/customFields and depend on this law.
#   2. THE VERSION HEADER LAW. The Convert and Flow (LeadConnector v2)
#      Version header is the fixed "2021-07-28" (verified at W0.5;
#      reg.CAF_VERSION_HEADER) — the same byte-exact header reg.CafClient /
#      reg.InternalRailClient send on every request. Version is also NOT a
#      secret.
#   3. THE AF CODE LAW. The complete autofail table mirrored from
#      ENGINE-MANIFEST.json "autofails" (75 rows: the AF-AE-* families plus
#      AE_DEPS_MISSING) as immutable constants, so a code can NEVER be
#      misspelled or drifted between a raising module and the manifest.
#      Self-test asserts byte-equality with the manifest (when the manifest
#      is present at the module's canonical repo path) — the engine's
#      AF-AE-* families and the U03 AF-AE-TEMPLATE-* family all ride this
#      one table. The U07 family's OWN enforcement codes live in the family
#      surfaces: AF-AE-FIELD-KEY-MISMATCH (missing_finder's name-squat
#      drift), AF-AE-FIELD-MISSING (the missing-field census family),
#      AF-AE-FIELDMAP-* (fieldmap_loader's self-test family),
#      AF-AE-GOLDENALLPRESENT-* (golden_all_present's self-test family),
#      AF-AE-MISSINGFINDER-* (missing_finder's self-test family) — the
#      enforced-violation families are declared by the U06 sibling's
#      convention and the manifest's own exit-code language (family
#      wildcards under exit 4), exactly as the U05 rows were before they
#      were stamped. A code can NEVER be misspelled or drifted between a
#      raising module and the family's authority.
#
# FAIL-CLOSED (the whole point): a drifted UA, a drifted version header, a
# code set that no longer matches the manifest, a non-AF-shaped code, or an
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
#   2  STOP refusal — manifest present but unreadable/malformed
#      (the AF code law would be unverifiable; the constants still import —
#      the law is the manifest's, the mirror is this module's)
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
# other u07_modules: sys.path.insert to scripts/ then
# `import anthology_registry as reg` for its canonical constants.
# DOCTRINE: move in silence; NOTHING Anthropic in any runtime file; Convert
# and Flow naming in every client surface; NEVER print a secret value; the
# U07 WRITE ACTION (provisioning a missing field) requires --execute
# (Trevor-gated, per the u07 package-init doctrine and golden_all_present's
# WRITE_ACTION law) — this constants module carries no ACTION surface at
# all.
# =============================================================================
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
# LAW 3 — THE AF CODE TABLE. The complete autofail table mirrored from
# ENGINE-MANIFEST.json "autofails": every AF-AE-* code (and the lone
# AE_DEPS_MISSING row) as immutable constants — a raising module names the
# constant, never a hand-typed literal, so a code can never drift from the
# manifest. The engine's AF-AE-* families and the U03 AF-AE-TEMPLATE-*
# family (the fail-closed codes the U03 verifier and check modules raise)
# all ride this one table. self_test() proves byte-equality with the
# manifest — SAME set AND SAME order — and REFUSES any deviation (exit 4,
# AF-AE-HASH-PIN family in the manifest's own audit language: a drifted
# enforcement set is a tamper).
# ---------------------------------------------------------------------------
# Constants are declared in the manifest's EXACT autofails order, so the
# table below is a literal mirror and a reordered manifest trips the
# self-test first (fail-closed: the mirror never silently re-sorts).
AF_SLOT_UNRESOLVED = "AF-AE-SLOT-UNRESOLVED"
AF_ANTHROPIC = "AF-AE-ANTHROPIC"
AF_PROMPT_PIN = "AF-AE-PROMPT-PIN"
AF_FONT_FLOOR = "AF-AE-FONT-FLOOR"
AF_TENANT_MISMATCH = "AF-AE-TENANT-MISMATCH"
AF_UNROUTABLE = "AF-AE-UNROUTABLE"
AF_STAGE_MISMATCH = "AF-AE-STAGE-MISMATCH"
AF_ILLEGAL_TRANSITION = "AF-AE-ILLEGAL-TRANSITION"
AF_READBACK_MISMATCH = "AF-AE-READBACK-MISMATCH"
AF_BROKER_ACTIONS_MISSING = "AF-AE-BROKER-ACTIONS-MISSING"
AF_TITLE_LOCK = "AF-AE-TITLE-LOCK"
AF_CHAP_BAND = "AF-AE-CHAP-BAND"
AF_REWRITE_BUDGET = "AF-AE-REWRITE-BUDGET"
AF_QC_STRIKEOUT = "AF-AE-QC-STRIKEOUT"
AF_JUDGE_INDEPENDENCE = "AF-AE-JUDGE-INDEPENDENCE"
AF_CREDIT_HOLD = "AF-AE-CREDIT-HOLD"
AF_S9_GUARD = "AF-AE-S9-GUARD"
AF_S9_FROZEN = "AF-AE-S9-FROZEN"
AF_FIELD_MISSING = "AF-AE-FIELD-MISSING"
AF_PIT_SCOPE = "AF-AE-PIT-SCOPE"
AF_PIPELINE_UI_CREATE = "AF-AE-PIPELINE-UI-CREATE"
AF_EXPORT_LEAK = "AF-AE-EXPORT-LEAK"
AF_CRON_DRIFT = "AF-AE-CRON-DRIFT"
AF_COMMINGLE = "AF-AE-COMMINGLE"
AF_AUTH_FAIL = "AF-AE-TOKEN-REFUSED"
AF_BYPASS = "AF-AE-BYPASS"
AF_HASH_PIN = "AF-AE-HASH-PIN"
AF_UNRESOLVED_MODELMAP = "AF-AE-UNRESOLVED-MODELMAP"
AE_DEPS_MISSING = "AE_DEPS_MISSING"
AF_SNAPSHOT_KEY_MISMATCH = "AF-AE-SNAPSHOT-KEY-MISMATCH"
AF_SNAPSHOT_EMPTY = "AF-AE-SNAPSHOT-EMPTY"
AF_TEMPLATE_PIPELINE_MISSING = "AF-AE-TEMPLATE-PIPELINE-MISSING"
AF_TEMPLATE_STAGE_DRIFT = "AF-AE-TEMPLATE-STAGE-DRIFT"
AF_TEMPLATE_FIELD_MISSING = "AF-AE-TEMPLATE-FIELD-MISSING"
AF_TEMPLATE_KEY_MISMATCH = "AF-AE-TEMPLATE-KEY-MISMATCH"
AF_TEMPLATE_CUSTOM_VALUE_REAL = "AF-AE-TEMPLATE-CUSTOM-VALUE-REAL"
AF_TEMPLATE_INTAKE_FIRE = "AF-AE-TEMPLATE-INTAKE-FIRE"
AF_U07_CREATE_NO_EXECUTE = "AF-AE-U07-CREATE-NO-EXECUTE"
AF_FIELD_KEY_MISMATCH = "AF-AE-FIELD-KEY-MISMATCH"
AF_U08_U09_NO_EXECUTE = "AF-AE-U08-U09-NO-EXECUTE"
AF_U10_U13_ASSEMBLY_INCOMPLETE = "AF-AE-U10-U13-ASSEMBLY-INCOMPLETE"
AF_U10_U13_NO_EXECUTE = "AF-AE-U10-U13-NO-EXECUTE"
AF_U10_U13_OFFLINE = "AF-AE-U10-U13-OFFLINE"
AF_COPY_LAW = "AF-AE-COPY-LAW"
AF_TEMPLATE_ATTACK = "AF-AE-TEMPLATE-ATTACK"
AF_U20_ASSEMBLY_INCOMPLETE = "AF-AE-U20-ASSEMBLY-INCOMPLETE"
AF_WELCOME_NO_EXECUTE = "AF-AE-WELCOME-NO-EXECUTE"
AF_WELCOME_DB_MISSING = "AF-AE-WELCOME-DB-MISSING"
AF_WELCOME_READ_REFUSED = "AF-AE-WELCOME-READ-REFUSED"
AF_WELCOME_CARD_REFUSED = "AF-AE-WELCOME-CARD-REFUSED"
AF_WELCOME_READBACK_MISMATCH = "AF-AE-WELCOME-READBACK-MISMATCH"
AF_WELCOME_SOURCE_UNREADABLE = "AF-AE-WELCOME-SOURCE-UNREADABLE"
AF_WELCOME_SOURCE_DRIFT = "AF-AE-WELCOME-SOURCE-DRIFT"
AF_WELCOME_CONTENT_VIOLATION = "AF-AE-WELCOME-CONTENT-VIOLATION"
AF_WELCOME_DB_UNREADABLE = "AF-AE-WELCOME-DB-UNREADABLE"
AF_WELCOME_DB_MISMATCH = "AF-AE-WELCOME-DB-MISMATCH"
AF_WELCOME_INSERT_REFUSED = "AF-AE-WELCOME-INSERT-REFUSED"
AF_WELCOME_CARDS_PRESENT = "AF-AE-WELCOME-CARDS-PRESENT"
AF_WELCOME_MALFORMED = "AF-AE-WELCOME-MALFORMED"
AF_WELCOME_ATTACK = "AF-AE-WELCOME-ATTACK"
AF_DBC_NO_DB = "AF-AE-DBC-NO-DB"
AF_DBC_NO_EXECUTE = "AF-AE-DBC-NO-EXECUTE"
AF_DBC_NO_WELCOME = "AF-AE-DBC-NO-WELCOME"
AF_DBC_SEED_EXISTS = "AF-AE-DBC-SEED-EXISTS"
AF_DBC_ATTACK = "AF-AE-DBC-ATTACK"
AF_VRBOARD_NO_DB = "AF-AE-VRBOARD-NO-DB"
AF_VRBOARD_NO_EXECUTE = "AF-AE-VRBOARD-NO-EXECUTE"
AF_VRBOARD_TASKS_MISSING = "AF-AE-VRBOARD-TASKS-MISSING"
AF_VRBOARD_DRILLS_LIVE = "AF-AE-VRBOARD-DRILLS-LIVE"
AF_VRBOARD_NO_WELCOME = "AF-AE-VRBOARD-NO-WELCOME"
AF_VRBOARD_ATTACK = "AF-AE-VRBOARD-ATTACK"
AF_U20ARCHIVE_NO_EXECUTE = "AF-AE-U20ARCHIVE-NO-EXECUTE"
AF_U20ARCHIVE_READBACK_MISMATCH = "AF-AE-U20ARCHIVE-READBACK-MISMATCH"
AF_ARCHSTMT_NO_EXECUTE = "AF-AE-ARCHSTMT-NO-EXECUTE"
AF_ARCHSTMT_READBACK = "AF-AE-ARCHSTMT-READBACK"

# The complete, immutable AF table (frozen; one canonical order — the
# manifest's own autofails order, never re-sorted). Built from the constants
# above so a code can never be entered twice or misspelled.
_AF_TABLE = (
    AF_SLOT_UNRESOLVED,
    AF_ANTHROPIC,
    AF_PROMPT_PIN,
    AF_FONT_FLOOR,
    AF_TENANT_MISMATCH,
    AF_UNROUTABLE,
    AF_STAGE_MISMATCH,
    AF_ILLEGAL_TRANSITION,
    AF_READBACK_MISMATCH,
    AF_BROKER_ACTIONS_MISSING,
    AF_TITLE_LOCK,
    AF_CHAP_BAND,
    AF_REWRITE_BUDGET,
    AF_QC_STRIKEOUT,
    AF_JUDGE_INDEPENDENCE,
    AF_CREDIT_HOLD,
    AF_S9_GUARD,
    AF_S9_FROZEN,
    AF_FIELD_MISSING,
    AF_PIT_SCOPE,
    AF_PIPELINE_UI_CREATE,
    AF_EXPORT_LEAK,
    AF_CRON_DRIFT,
    AF_COMMINGLE,
    AF_AUTH_FAIL,
    AF_BYPASS,
    AF_HASH_PIN,
    AF_UNRESOLVED_MODELMAP,
    AE_DEPS_MISSING,
    AF_SNAPSHOT_KEY_MISMATCH,
    AF_SNAPSHOT_EMPTY,
    AF_TEMPLATE_PIPELINE_MISSING,
    AF_TEMPLATE_STAGE_DRIFT,
    AF_TEMPLATE_FIELD_MISSING,
    AF_TEMPLATE_KEY_MISMATCH,
    AF_TEMPLATE_CUSTOM_VALUE_REAL,
    AF_TEMPLATE_INTAKE_FIRE,
    AF_U07_CREATE_NO_EXECUTE,
    AF_FIELD_KEY_MISMATCH,
    AF_U08_U09_NO_EXECUTE,
    AF_U10_U13_ASSEMBLY_INCOMPLETE,
    AF_U10_U13_NO_EXECUTE,
    AF_U10_U13_OFFLINE,
    AF_COPY_LAW,
    AF_TEMPLATE_ATTACK,
    AF_U20_ASSEMBLY_INCOMPLETE,
    AF_WELCOME_NO_EXECUTE,
    AF_WELCOME_DB_MISSING,
    AF_WELCOME_READ_REFUSED,
    AF_WELCOME_CARD_REFUSED,
    AF_WELCOME_READBACK_MISMATCH,
    AF_WELCOME_SOURCE_UNREADABLE,
    AF_WELCOME_SOURCE_DRIFT,
    AF_WELCOME_CONTENT_VIOLATION,
    AF_WELCOME_DB_UNREADABLE,
    AF_WELCOME_DB_MISMATCH,
    AF_WELCOME_INSERT_REFUSED,
    AF_WELCOME_CARDS_PRESENT,
    AF_WELCOME_MALFORMED,
    AF_WELCOME_ATTACK,
    AF_DBC_NO_DB,
    AF_DBC_NO_EXECUTE,
    AF_DBC_NO_WELCOME,
    AF_DBC_SEED_EXISTS,
    AF_DBC_ATTACK,
    AF_VRBOARD_NO_DB,
    AF_VRBOARD_NO_EXECUTE,
    AF_VRBOARD_TASKS_MISSING,
    AF_VRBOARD_DRILLS_LIVE,
    AF_VRBOARD_NO_WELCOME,
    AF_VRBOARD_ATTACK,
    AF_U20ARCHIVE_NO_EXECUTE,
    AF_U20ARCHIVE_READBACK_MISMATCH,
    AF_ARCHSTMT_NO_EXECUTE,
    AF_ARCHSTMT_READBACK,
)
AF_CODES = tuple(_AF_TABLE)  # public immutable surface; also a set below
AF_CODES_SET = frozenset(_AF_TABLE)

# The U07 family's OWN rows, in docs_u07.AF_CODES' order (the family
# authority's table: the four exit-4 enforced-violation wildcard rows, the
# real rows AF-AE-FIELD-MISSING (stamped in the manifest) and
# AF-AE-FIELD-KEY-MISMATCH (PENDING in the manifest, verified at ship time
# 2026-08-11), plus the shared AF-AE-READBACK-MISMATCH row docs_u07 itself
# declares — the subset whose membership is the family's, so the family
# subset never absorbs a manifest-only row and the real rows are pinned
# against the manifest separately).
AF_U07_CODES = tuple(
    c[0] for c in _u07docs.af_codes()
    if isinstance(c, tuple) and c and isinstance(c[0], str) and c[0])

# The REAL (non-wildcard) family rows — the ones whose manifest status the
# self-test pins: every real row must be EITHER stamped in
# ENGINE-MANIFEST.json's autofails (AF-AE-FIELD-MISSING,
# AF-AE-READBACK-MISMATCH) OR declared PENDING below. A malformed docs_u07
# row is filtered out of the derived subsets and then caught by
# _u07_family_codes() (the strict per-row gate, defined below) and by the
# self-test's byte-exact mirror — never a silent pass.
AF_U07_REAL_CODES = tuple(
    c for c in AF_U07_CODES
    if c.startswith("AF-AE-") and "*" not in c
    and c != "AF-AE-TEMPLATE-ATTACK")

# The U07 family rows PENDING in ENGINE-MANIFEST.json — the U06 sibling
# pattern: a family row the family authority declares but the manifest has
# not yet stamped. As of 2026-08-11 every real U07 family row is STAMPED in
# ENGINE-MANIFEST.json's autofails (AF-AE-FIELD-MISSING,
# AF-AE-FIELD-KEY-MISMATCH — row 59 — and the shared
# AF-AE-READBACK-MISMATCH), so the PENDING set is EMPTY. The self-test
# refuses a real row that is NEITHER stamped NOR declared PENDING (drift),
# and refuses a declared-PENDING row that the manifest has since stamped (a
# stale mirror is a tamper, never silent).
AF_U07_PENDING = ()

# Every AF row must carry the house AF shape: "AF-<family>-<NAME>", with the
# one sanctioned exception AE_DEPS_MISSING (the manifest's own lone non-AF
# row, which this module mirrors exactly because the manifest says so).
_AF_SHAPE_RE = re.compile(r"^AF-[A-Z0-9]+-[A-Z0-9-]+$")


def _af_shape_ok(code: str) -> bool:
    """The AF shape gate, with the manifest's one sanctioned exception:
    AE_DEPS_MISSING is a non-AF row that ENGINE-MANIFEST.json itself
    declares in the autofails table, so it is mirrored byte-exact — any
    OTHER deviation from the AF shape is refused."""
    if code == AE_DEPS_MISSING:
        return True
    return bool(_AF_SHAPE_RE.match(code))


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
            "AF table -- the table must be re-mirrored from "
            "ENGINE-MANIFEST.json" % (name, value))
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


def _u07_family_codes() -> list:
    """The U07 family's OWN autofail rows from docs_u07.AF_CODES (the
    family's autofail authority, exactly as the U06 sibling mirrors its
    docs_u06): every (code, exit, meaning) row, in the authority's exact
    order — the four enforced-violation wildcard rows (AF-AE-FIELDMAP-* /
    AF-AE-GOLDENALLPRESENT-* / AF-AE-MISSINGFINDER-* / AF-AE-TEMPLATE-
    ATTACK) plus the two real rows the manifest already stamps
    (AF-AE-FIELD-MISSING / AF-AE-FIELD-KEY-MISMATCH) and the shared
    AF-AE-READBACK-MISMATCH row the authority itself declares. Fail-closed:
    a docs_u07 that cannot be read, or an authority whose rows lost their
    code field, is a REFUSAL (HouseRulesError) — a family law that cannot
    be verified is never a blind skip."""
    rows = _u07docs.af_codes()
    codes = []
    for row in rows:
        code = row[0] if isinstance(row, tuple) and row else None
        if not isinstance(code, str) or not code:
            raise HouseRulesError(
                "docs_u07.AF_CODES carries a row with no code string -- the "
                "family AF law is unverifiable")
        codes.append(code)
    if not codes:
        raise HouseRulesError(
            "docs_u07.AF_CODES carries no autofail row -- the family AF "
            "law is unverifiable")
    return codes


def _manifest_codes(manifest_path: Path) -> list:
    """Reads the manifest's autofail codes, fail-closed: an unreadable or
    malformed manifest at the canonical path is a REFUSAL (HouseRulesError),
    never a blind skip -- a manifest that cannot be read means the AF code
    law is unverifiable."""
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise HouseRulesError(
            "ENGINE-MANIFEST.json missing at %s -- the AF code law is "
            "unverifiable" % manifest_path)
    except (OSError, IOError, ValueError) as exc:
        raise HouseRulesError(
            "ENGINE-MANIFEST.json unreadable/malformed at %s: %s -- the AF "
            "code law is unverifiable" % (manifest_path, exc))
    rows = data.get("autofails")
    if not isinstance(rows, list) or not rows:
        raise HouseRulesError(
            "ENGINE-MANIFEST.json autofails is empty or not a list -- the AF "
            "code law is unverifiable")
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
        "u07_family_codes": list(_u07_family_codes()),
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
                "source": "ENGINE-MANIFEST.json autofails (75 rows)",
            },
        },
    }
    json.dump(payload, out, indent=2, sort_keys=True)
    out.write("\n")
    return EX_OK


def self_test(*, out=None) -> int:
    """OFFLINE self-test (no network, no credential): pins the UA and the
    version header byte-exact against the registry, pins the AF table
    byte-exact against ENGINE-MANIFEST.json's autofails, and proves every
    attack fixture is REFUSED. A tamper NEVER masquerades as exit 1 -- it is
    exit 4 (AF-AE-HASH-PIN family: a drifted enforcement set)."""
    out = out or sys.stdout
    failures = []

    # ---- the golden laws: registry mirror, byte-exact ---------------------
    try:
        _check_laws(out=out)
    except HouseRulesError as exc:
        failures.append("golden laws: %s" % exc)

    # ---- the golden AF table: manifest mirror, byte-exact ------------------
    try:
        manifest_codes = _manifest_codes(MANIFEST_PATH)
    except HouseRulesError as exc:
        failures.append("manifest read: %s" % exc)
        manifest_codes = None
    if manifest_codes is not None:
        if sorted(AF_CODES) != sorted(manifest_codes):
            missing = sorted(set(manifest_codes) - set(AF_CODES))
            extra = sorted(set(AF_CODES) - set(manifest_codes))
            failures.append(
                "AF table drifted from ENGINE-MANIFEST.json: missing=%s "
                "extra=%s" % (missing, extra))
        if list(AF_CODES) != list(manifest_codes):
            failures.append(
                "AF table order drifted from ENGINE-MANIFEST.json")

    # ---- the golden U07 family rows: docs_u07 mirror, byte-exact ----------
    # The family's OWN rows are pinned against docs_u07.AF_CODES (the
    # family authority) — SAME set AND SAME order — and every row that the
    # manifest stamps must be present in the manifest's autofails, so a
    # family code is certified against BOTH authorities.
    try:
        u07_codes = _u07_family_codes()
    except HouseRulesError as exc:
        failures.append("docs_u07 read: %s" % exc)
        u07_codes = None
    if u07_codes is not None:
        docs_codes = [r[0] if isinstance(r, tuple) and r else None
                      for r in _u07docs.af_codes()]
        if None in docs_codes:
            failures.append("docs_u07.AF_CODES carries a row with no code "
                            "string -- the family AF law is unverifiable")
        elif list(AF_U07_CODES) != list(docs_codes):
            failures.append(
                "the family subset AF_U07_CODES drifted from "
                "docs_u07.AF_CODES: missing=%s extra=%s"
                % (sorted(set(docs_codes) - set(AF_U07_CODES)),
                   sorted(set(AF_U07_CODES) - set(docs_codes))))
        if set(AF_U07_CODES) & {AE_DEPS_MISSING}:
            failures.append(
                "the family subset AF_U07_CODES absorbed a manifest-only "
                "row")
    if u07_codes is not None and manifest_codes is not None:
        # The family's REAL rows (the ones that must already live in the
        # manifest) are pinned against the manifest; the wildcard rows and
        # the shared AF-AE-TEMPLATE-ATTACK row are the family's own
        # enforcement language (the docs_u07 / manifest exit-code
        # convention), NEVER manifest rows.
        for code in u07_codes:
            if (code.startswith("AF-AE-") and "*" not in code
                    and code != "AF-AE-TEMPLATE-ATTACK"):
                if code in manifest_codes:
                    if code in AF_U07_PENDING:
                        failures.append(
                            "the U07 family row %s was stamped in "
                            "ENGINE-MANIFEST.json but is still declared "
                            "PENDING in AF_U07_PENDING -- a stale mirror "
                            "is a tamper, never silent" % code)
                elif code not in AF_U07_PENDING:
                    failures.append(
                        "the U07 family row %s is not in ENGINE-MANIFEST"
                        ".json's autofails and is not declared PENDING "
                        "-- the row drifted from its authority" % code)

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
    for bad in ("AF-AE-", "", "af-ae-x", "AE-DEPS-MISSING",
                "AE_DEPS_MISSING-EXTRA"):
        if _af_shape_ok(bad):
            failures.append("attack not refused: malformed code %r passed "
                            "the AF shape gate" % bad)
    for name, value in (("AF_CODES", AF_CODES),
                        ("AF_CODES_SET", AF_CODES_SET),
                        ("AF_U07_CODES", AF_U07_CODES),
                        ("AF_U07_REAL_CODES", AF_U07_REAL_CODES),
                        ("CAF_BROWSER_UA", CAF_BROWSER_UA),
                        ("CAF_VERSION_HEADER", CAF_VERSION_HEADER)):
        if not isinstance(value, (tuple, frozenset, str)) or not value:
            failures.append("attack not refused: %s is empty" % name)
    for lookalike in ("AF-AE-FIELDMAP", "AF-AE-MISSINGFINDER",
                      "AF-AE-GOLDENALLPRESENT", "AF-AE-FIELD-MISSING-EXTRA",
                      "AF-AE-FIELD-KEY-MISMATCH-EXTRA"):
        if lookalike in AF_U07_CODES:
            failures.append("attack not refused: family lookalike %r "
                            "polluted the U07 family rows" % lookalike)
        if _af_shape_ok(lookalike) and lookalike in AF_CODES_SET:
            failures.append("attack not refused: family lookalike %r "
                            "polluted the pinned AF table" % lookalike)
    for wildcard in ("AF-AE-FIELDMAP-*", "AF-AE-GOLDENALLPRESENT-*",
                     "AF-AE-MISSINGFINDER-*"):
        if wildcard in AF_CODES_SET:
            failures.append("attack not refused: the family wildcard row %r "
                            "leaked into the manifest-mirror AF table "
                            "(family rows belong in AF_U07_CODES only)"
                            % wildcard)
        if wildcard not in AF_U07_CODES:
            failures.append("attack not refused: the family wildcard row %r "
                            "is missing from AF_U07_CODES" % wildcard)
    for real in AF_U07_REAL_CODES:
        if "*" in real:
            failures.append("attack not refused: a wildcard row %r leaked "
                            "into AF_U07_REAL_CODES" % real)
    try:
        af_code("AF_TEMPLATE_PIPELINE_MISSING")
    except HouseRulesError as exc:
        failures.append("attack not refused: pinned AF resolution failed: "
                        "%s" % exc)
    try:
        af_code("NOT_A_CONSTANT")
        failures.append("attack not refused: unknown AF constant name")
    except HouseRulesError:
        pass

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
              "byte-exact against the registry; AF table matches "
              "ENGINE-MANIFEST.json (%s codes); the U07 family rows match "
              "docs_u07.AF_CODES (%s rows, same set AND same order) and "
              "the real rows are stamped in the manifest; every attack "
              "fixture refused; zero credential surface\n"
              % (len(AF_CODES), len(AF_U07_CODES)))
    return EX_OK


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="house_rules.py",
        description="The U07 family's canonical constant surface: browser "
                    "UA (CF 1010), Convert and Flow version header, the "
                    "complete AF autofail code table (the manifest's 75 "
                    "rows), and the U07 family's own rows (docs_u07.AF_CODES)"
                    " -- fail-closed, offline, never prints a token "
                    "(Skill 59). One JSON object on stdout.")
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
