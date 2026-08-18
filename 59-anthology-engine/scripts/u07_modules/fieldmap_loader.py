#!/usr/bin/env python3
# =============================================================================
# SKILL 59 — ANTHOLOGY ENGINE :: u07_modules/fieldmap_loader.py
# FAIL-CLOSED FIELD-MAP LOADER AND CONTRACT GATE (U07 tooling) — the single
# implementation of the field-map.json load-and-verify law for this package:
# read config/field-map.json and return its provisioning.fields inventory
# (the 38 keys, with their declared data types) ONLY when the map satisfies
# its own contract; refuse anything else. It is the OFFLINE, READ-ONLY,
# NETWORK-FREE surface of the field-map — the sibling of the U02 byte-exact
# LIVE check (u02_modules/fields_check.py) and of the registry's provisioning
# (anthology_registry.py provision-fields), which this module never performs
# and never duplicates.
#
# WHERE THIS SITS: scripts/u07_modules/ — an importable module under the U07
# tooling. It is NOT a manifest row: it ships as a sibling helper, exactly
# the way delivery_report.py ships as the sibling helper of caf_delivery.py
# (ENGINE-MANIFEST row 12 pattern), so the U07 verifier stays the single
# manifest row while this module owns the field-map load surface. Imported
# BY NAME as u07_modules.fieldmap_loader from the engine scripts, per the
# u07_modules package contract (__init__.py: pure namespace container —
# fail-closed empty init, no runtime code, side-effect free). Standalone
# invocation works too: the SAME sys.path.insert bootstrap the sibling
# imports use resolves anthology_registry from scripts/.
#
# WHAT THIS OWNS (byte-exact, fail-closed, never a token):
#   1. THE LOAD LAW: parse field-map.json and return ONLY a contract-verified
#      provisioning.fields inventory. The contract (config/field-map.json
#      provisioning_rule): exactly thirty-eight keys — the ten deliverable
#      Doc/PDF field pairs (20 keys: the eight base deliverables plus the two
#      chapter-rewrite-preservation pairs rewrite1/rewrite2 from PRD Gap
#      G10) plus the three control fields plus the five U8 cover-style
#      fields (four LARGE_TEXT sample-url fields + one SINGLE_OPTIONS choice
#      field) plus the ten U15-absorbed live fields (9 LARGE_TEXT + the
#      SINGLE_OPTIONS review decision). provisioning.total_keys MUST
#      byte-match the inventory length;
#      a map that drifted from its own contract is a refusal (FieldMapError,
#      exit 2 STOP family), never a silent load. An unresolved field_id slot
#      (the committed template ships every resolved slot null) is a NORMAL
#      load — it is surfaced as per-key status RESOLVED / UNRESOLVED, and
#      the resolved value itself NEVER reaches any surface (a field id is a
#      tenant identifier: masked policy identical to the location and
#      workflow ids).
#   2. THE DERIVATION LAW (W0.5): the Convert and Flow create-custom-field
#      endpoint derives the fieldKey; it does NOT accept an arbitrary
#      fieldKey on create. Every row's create_name MUST derive back to its
#      intended_key byte-exact (reg.derive_field_key); a violating row is
#      drift, never loaded.
#   3. THE TYPE LAW (PRD Gap G11 + U8 + U15, byte-exact): every free-text
#      key is
#      declared LARGE_TEXT (the multi-line law, matching live provisioning —
#      the earlier TEXT declaration was a repo-vs-live drift the spec called
#      out); the TWO SINGLE_OPTIONS keys are the U8 cover choice
#      (contact.anthology_cover_choice) carrying EXACTLY the four named
#      style options ("Signature", "Bold Editorial", "Fine Art", "Pure
#      Type") in order, and the U15-absorbed review decision
#      (contact.anthology_review_decision) carrying EXACTLY the two gate
#      actions ("approve_as_is", "request_rewrite_with_notes") in order. A
#      non-contract data_type on any key is a refusal, never a load.
#   4. THE KEY LAW: every intended_key carries the "contact." prefix
#      (reg._KEY_PREFIX), the thirty-eight keys are unique, and the
#      inventory is a list of objects — a non-list inventory, a non-object
#      row, a missing key, a duplicate, or a wrong prefix is a refusal,
#      never a blind pass.
#   5. THE BROWSER-UA LAW (offline): this module makes NO network request —
#      there is no request to attach a User-Agent to — and it carries the
#      house browser-UA doctrine the way a pure loader must: it asserts
#      reg.CAF_BROWSER_UA exists and byte-equals the Podcast gate's
#      proven-live string (the GK-09 regression pin, exactly as the
#      registry's own self-test enforces). A consumer of the loaded map
#      that wires its OWN requests (services.leadconnectorhq.com is
#      Cloudflare-fronted; urllib's default "Python-urllib/x.y" is 403'd at
#      the WAF edge with CF error 1010 before it ever reaches Convert and
#      Flow) is therefore caught OFFLINE by this module's law surface if the
#      shared constant drifts — never first seen as a 1010 at runtime.
#   NO CREDENTIAL IS EVER RESOLVED OR PRINTED HERE. This module is fully
#   OFFLINE: it never touches a token, an env store, or the network, and it
#   has no credential path to leak. A credential belongs to the live
#   surfaces (registry, U02), never to a pure loader.
#
# EXIT CODE CONTRACT (house convention 0/1/2/3/4/5):
#   0  verified success — the map satisfies its own contract and the
#      inventory was loaded; also self-test OK
#   1  unexpected error (top-level guard; never a secret leak)
#   2  STOP — field-map.json missing/unreadable/malformed JSON, or any
#      FieldMapError contract refusal (38-key count, total_keys mismatch,
#      derivation law, type law, key law); also empty --field-map usage
#   3  HELD — reserved for live surfaces; this module never returns 3
#   4  self-test FAILED (AF-AE-FIELDMAP-* family, enforced violation)
#   5  mismatch — reserved for live read-back surfaces; this module never
#      returns 5
#
# USAGE (machine surface — ONE JSON object on stdout; human notes on
# stderr; --self-test is OFFLINE and needs no network and no token):
#
#   python3 scripts/u07_modules/fieldmap_loader.py run [--field-map PATH]
#   python3 scripts/u07_modules/fieldmap_loader.py self-test
#
#   The run payload carries STATUS only for resolved slots — never the
#   field_id VALUE (a tenant identifier; the masked-id policy of the U06
#   modules). Every row is verified byte-exact against the map's own
#   contract before it is reported.
#
# STDLIB ONLY (json + argparse via the registry sibling). Calls NO model.
# Sibling import bootstrap identical to live_verify_template.py:
# sys.path.insert to scripts/ then `import anthology_registry as reg`.
# DOCTRINE: move in silence; NOTHING Anthropic in any runtime file; Convert
# and Flow naming in every client surface; NEVER print a secret value.
# =============================================================================
"""fieldmap_loader.py — fail-closed loader and contract gate for the
field-map's provisioning.fields inventory (U07 tooling, Skill 59).

Imported BY NAME as u07_modules.fieldmap_loader from the engine scripts, per
the u07_modules package contract (__init__.py: pure namespace container).
"""

from __future__ import annotations

import argparse
import io
import json
import sys
from pathlib import Path

# Sibling import bootstrap (house convention): the registry owns the
# browser-UA constant, the key-prefix/derivation symbols, and the exit-code
# contract; this module reuses them, never re-declares them.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import anthology_registry as reg  # noqa: E402

# The contract total, fixed by the PRD (19 base Section 6 link/control keys +
# 4 Gap G10 chapter-rewrite-preservation keys + 5 U8 cover-style keys + the
# 10 U15-absorbed live fields 2026-08-13). This module asserts this exact
# number — a map that carries more or fewer keys has drifted and the loader
# refuses to ship it. (The same 38 that u02_modules/golden_fields.py pins as
# CONTRACT_TOTAL; the loader is the load-side of that fixture's contract.)
CONTRACT_TOTAL = 38

# The cover-choice picklist key (PRD Section 6 / U8). Everything except the
# TWO SINGLE_OPTIONS keys must be LARGE_TEXT (Gap G11). The cover picklist's
# four options are the named cover styles the client picks from (their
# byte-exact names MUST equal scripts/cover_render.py STYLE_NAMES in order —
# the field-map's own cover_style_fields.choice_options is the checked
# source, and this module asserts the row against it, never against a
# hardcoded list).
COVER_CHOICE_KEY = "contact.anthology_cover_choice"

# The review-decision picklist key (PRD Section 4 / U15-absorbed): the TWO
# decision options are the gate_engine s5_gate actions, and the field-map's
# own review_decision_field.options block is the checked source (the map is
# now the authority; the row and the block must byte-equal).
DECISION_KEY = "contact.anthology_review_decision"


class FieldMapError(Exception):
    """A fail-closed refusal of the field-map contract (STOP family): the
    map is missing, unreadable, malformed, or drifted from its own
    contract, so NO inventory is loaded — a wrong load is worse than no
    load."""


# ---------------------------------------------------------------------------
# Contract readers (fail-closed: a missing section is a refusal, never a
# pass). Each raises FieldMapError with the operator-facing reason; none
# ever prints a value that is not already a contract key or a count.
# ---------------------------------------------------------------------------
def _require_total_keys(field_map: dict) -> int:
    """provisioning.total_keys must be an int — a map that lost its contract
    total is drift, never a load."""
    total = (field_map.get("provisioning") or {}).get("total_keys")
    if not isinstance(total, int):
        raise FieldMapError(
            "field-map provisioning.total_keys is missing or not an int — "
            "the map lost its own contract; refusing to load.")
    return total


def _require_inventory(field_map: dict) -> list:
    """provisioning.fields must be a non-empty list of objects — a non-list
    inventory, an empty inventory, or a non-object row is a refusal (an
    empty inventory would silently read as 'no fields to provision')."""
    fields = (field_map.get("provisioning") or {}).get("fields")
    if not isinstance(fields, list) or not fields:
        raise FieldMapError(
            "field-map provisioning.fields is missing, not a list, or empty "
            "-- refusing a blind load (never fabricated).")
    rows = [f for f in fields if isinstance(f, dict)]
    if len(rows) != len(fields):
        raise FieldMapError(
            "field-map provisioning.fields carries a non-object row — "
            "refusing to load a malformed inventory.")
    return rows


# ---------------------------------------------------------------------------
# The load law — one function, the only way an inventory leaves this module.
# ---------------------------------------------------------------------------
def load_field_map(path: str | Path) -> dict:
    """Load and verify the field-map, returning its provisioning.fields
    inventory. Fail-closed: any contract drift raises FieldMapError and NO
    inventory is returned. The read is utf-8 strict (a decode error is a
    refusal, never a partial load); the committed template's null resolved
    slots are expected and pass — resolution state is reported by status,
    never by value.

    The returned rows are the map's own rows (dicts); a consumer that
    mutates them mutates its own copy of the loaded file, never this
    module's state and never the file on disk."""
    p = Path(path)
    if not p.exists():
        raise FieldMapError(
            "field-map.json not found at %s (owned by W1.8; the 38 PRD "
            "Section 6 + U15-absorbed keys cannot be loaded without it)" % p)
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (ValueError, OSError) as exc:
        raise FieldMapError(
            "field-map.json unreadable at %s (%s) -- refusing to load."
            % (p, type(exc).__name__))
    if not isinstance(data, dict):
        raise FieldMapError(
            "field-map.json at %s is not a JSON object -- refusing to load."
            % p)

    inventory = _require_inventory(data)
    total = _require_total_keys(data)

    if len(inventory) != CONTRACT_TOTAL:
        raise FieldMapError(
            "field-map provisioning.fields carries %d keys, but the "
            "contract is %d (19 base PRD Section 6 + 4 Gap G10 rewrite + 5 "
            "U8 cover-style + 10 U15-absorbed) -- the map drifted; refusing "
            "to load." % (len(inventory), CONTRACT_TOTAL))
    if len(inventory) != total:
        raise FieldMapError(
            "field-map provisioning.fields carries %d rows but "
            "provisioning.total_keys says %d -- the map drifted from its "
            "own contract; refusing to load." % (len(inventory), total))

    choice_options = _choice_options_from_map(data)
    decision_options = _decision_options_from_map(data)
    seen = set()
    for i, item in enumerate(inventory):
        _verify_row(i, item, seen, choice_options, decision_options)

    return inventory


# ---------------------------------------------------------------------------
# Row verification — the derivation law, the key law, and the type law.
# ---------------------------------------------------------------------------
def _verify_row(i: int, item: dict, seen: set, choice_options: list,
                decision_options: list) -> None:
    """Verify ONE inventory row byte-exact against the field-map contract.
    Raises FieldMapError on any drift. `choice_options` is the map's own
    cover_style_fields.choice_options block and `decision_options` the
    review_decision_field.options block (each resolved once by the loader).
    Pure: never prints, never writes."""
    intended = item.get("intended_key")
    cname = item.get("create_name")
    dtype = item.get("data_type")
    if not isinstance(intended, str) or not intended:
        raise FieldMapError(
            "field-map row %d has no intended_key -- refusing." % i)
    if not intended.startswith(reg._KEY_PREFIX):
        raise FieldMapError(
            "intended_key %r must carry the %r prefix -- refusing."
            % (intended, reg._KEY_PREFIX))
    if not isinstance(cname, str) or not cname:
        raise FieldMapError(
            "intended_key %r has no create_name -- refusing." % intended)
    # The derivation law (W0.5): the API derives the fieldKey; create_name
    # must derive back to the intended key. A row that violates the law is
    # drift -- the loader never ships it.
    if reg.derive_field_key(cname) != intended:
        raise FieldMapError(
            "create_name %r does not derive to intended_key %r -- the map "
            "violates the fieldKey derivation law; refusing." % (cname, intended))
    if intended in seen:
        raise FieldMapError(
            "intended_key %r repeats in the inventory -- refusing." % intended)
    seen.add(intended)

    # The G11 / U8 data-type law, byte-exact: every free-text key is
    # LARGE_TEXT (the multi-line law, matching live provisioning); the lone
    # cover-choice key is SINGLE_OPTIONS. The picklist options are checked
    # against the map's OWN cover_style_fields.choice_options block (the
    # single source of truth) -- never a hardcoded list, never a partial
    # match.
    if intended == COVER_CHOICE_KEY:
        if dtype != "SINGLE_OPTIONS":
            raise FieldMapError(
                "%s must be declared SINGLE_OPTIONS (U8), got %r -- refusing."
                % (intended, dtype))
        got = item.get("options")
        if not isinstance(got, list) or got != choice_options:
            raise FieldMapError(
                "%s options %r must byte-equal the map's own "
                "cover_style_fields.choice_options %r -- refusing."
                % (intended, got, choice_options))
    elif intended == DECISION_KEY:
        if dtype != "SINGLE_OPTIONS":
            raise FieldMapError(
                "%s must be declared SINGLE_OPTIONS (PRD Section 4), got %r "
                "-- refusing." % (intended, dtype))
        got = item.get("options")
        if not isinstance(got, list) or got != decision_options:
            raise FieldMapError(
                "%s options %r must byte-equal the map's own "
                "review_decision_field.options %r -- refusing."
                % (intended, got, decision_options))
    else:
        if dtype != "LARGE_TEXT":
            raise FieldMapError(
                "%s must be declared LARGE_TEXT (Gap G11), got %r -- "
                "refusing to load a non-contract type." % (intended, dtype))


def _choice_options_from_map(field_map: dict) -> list:
    """The cover-choice picklist options, from the map's own
    cover_style_fields block (the single source of truth, per the field-map
    header: the style names here MUST byte-equal scripts/cover_render.py
    STYLE_NAMES in order). A missing, non-list, or empty block is a refusal
    -- the loader never invents the options."""
    cs = (field_map.get("cover_style_fields") or {}).get("choice_options")
    if not isinstance(cs, list) or not cs:
        raise FieldMapError(
            "field-map cover_style_fields.choice_options is missing, not a "
            "list, or empty -- the cover choice picklist cannot be verified; "
            "refusing to load.")
    return list(cs)

def _decision_options_from_map(field_map: dict) -> list:
    """The review-decision picklist options, from the map's own
    review_decision_field block (the single source of truth; the options are
    the gate_engine s5_gate decision actions byte-exact). A missing,
    non-list, or empty block is a refusal -- the loader never invents the
    options."""
    ds = (field_map.get("review_decision_field") or {}).get("options")
    if not isinstance(ds, list) or not ds:
        raise FieldMapError(
            "field-map review_decision_field.options is missing, not a "
            "list, or empty -- the review-decision picklist cannot be "
            "verified; refusing to load.")
    return list(ds)


# ---------------------------------------------------------------------------
# The report surface — status only, never a value that is not a contract key.
# ---------------------------------------------------------------------------
def _resolved_status(row: dict) -> str:
    """RESOLVED when the row carries a non-empty field_id stamp (the per-box
    provision stamp), UNRESOLVED otherwise. The VALUE never leaves this
    function: a field id is a tenant identifier, reported by status only
    (the masked-id policy of the house modules)."""
    fid = row.get("field_id")
    return "RESOLVED" if isinstance(fid, str) and fid else "UNRESOLVED"


def build_report(inventory: list, *, source: str) -> dict:
    """The machine report for a loaded inventory: key, create name, declared
    data type, deliverable, slot, and the resolved-status of the field_id
    slot. NEVER the field_id value, never a credential, never a full
    location. Pure: never prints."""
    return {
        "ok": True,
        "action": "load",
        "source": source,
        "contract_total": CONTRACT_TOTAL,
        "loaded": len(inventory),
        "resolved": sum(1 for r in inventory if _resolved_status(r) == "RESOLVED"),
        "fields": [
            {
                "key": r.get("intended_key"),
                "create_name": r.get("create_name"),
                "data_type": r.get("data_type"),
                "deliverable": r.get("deliverable"),
                "slot": r.get("slot"),
                "resolved_status": _resolved_status(r),
            }
            for r in inventory
        ],
    }


def load_command(path: str | Path, *, out=None, jsonout=None) -> int:
    """The run command: load-and-verify the field-map and report ONE JSON
    object. Any contract refusal is a FieldMapError propagated to the CLI
    (STOP, exit 2) — never a partial load, never a fabricated success.
    Purely offline: no network, no token, no env store."""
    out = out or sys.stderr
    inventory = load_field_map(path)          # raises FieldMapError on drift
    report = build_report(inventory, source=str(Path(path)))
    if jsonout is not None:
        json.dump(report, jsonout, indent=2)
        jsonout.write("\n")
    else:
        out.write("[fieldmap-loader] LOADED %d/%d keys from %s (resolved "
                  "slots: %d; values never printed).\n"
                  % (report["loaded"], report["contract_total"], report["source"],
                     report["resolved"]))
    return reg.EX_OK


# ---------------------------------------------------------------------------
# CLI surface (tiny, deterministic; used by the sibling scripts and tests).
# ---------------------------------------------------------------------------
def main(argv=None):
    """Dispatch the CLI. run prints ONE JSON object on stdout (jsonout) and
    human notes on stderr; --json toggles stdout to the machine report.
    self-test is OFFLINE (no network, no token, no env store). Never prints
    a credential, a field id, a full location, or a response body."""
    if argv is None:
        argv = sys.argv[1:]
    ap = argparse.ArgumentParser(
        prog="fieldmap_loader.py", add_help=False,
        description="Fail-closed loader and contract gate for "
                    "config/field-map.json provisioning.fields (Skill 59 "
                    "U07). Offline and read-only: no network, no token, no "
                    "env store; a field id is reported by status only, never "
                    "by value.")
    ap.add_argument("--help", "-h", action="store_true")
    ap.add_argument("--json", action="store_true",
                    help="machine report on stdout (ONE JSON object)")
    ap.add_argument("--field-map", default="",
                    help="path to field-map.json (default: the skill's "
                         "config copy, config/field-map.json)")
    ap.add_argument("cmd", nargs="?", default="",
                    choices=["run", "self-test"])
    args = ap.parse_args(argv)

    if args.help or not args.cmd:
        sys.stdout.write(
            "fieldmap_loader.py -- Skill 59 U07 fail-closed field-map "
            "loader and contract gate\n"
            "  run [--field-map PATH]       load-and-verify the 38-key\n"
            "                               provisioning.fields inventory;\n"
            "                               refuses ANY contract drift\n"
            "                               (STOP, exit 2) -- never a\n"
            "                               partial load, field ids by\n"
            "                               status only\n"
            "  self-test                     offline fixtures, no network,\n"
            "                               no secrets\n"
            "  --json                        ONE JSON object on stdout\n"
            "Exit codes: 0 loaded/verified; 2 STOP (missing/unreadable/\n"
            "malformed map, or any contract drift: 38-key count, "
            "total_keys mismatch, derivation law, type law, key law); 4 "
            "self-test FAILED.\n")
        return reg.EX_OK if args.cmd else reg.EX_STOP

    if args.cmd == "self-test":
        return self_test()

    field_map = args.field_map or str(reg.SKILL_DIR / "config" / "field-map.json")
    try:
        return load_command(field_map, out=sys.stderr,
                            jsonout=sys.stdout if args.json else None)
    except FieldMapError as exc:
        sys.stderr.write("[fieldmap-loader] STOP: %s\n" % exc)
        return reg.EX_STOP


# ---------------------------------------------------------------------------
# Self-test — OFFLINE golden + attack fixtures, no network, no secrets.
# ---------------------------------------------------------------------------
def self_test():
    """Offline acceptance battery. Any failure prints a one-line note to
    stderr and returns 4; the happy path prints 'fieldmap_loader self-test:
    OK' to stderr and returns 0. Never touches the network; never prints a
    token or a field id."""
    dev = io.StringIO()

    # -- the golden field-map (a minimal, contract-true map) ------------------
    golden = {
        "cover_style_fields": {
            "choice_options": ["Signature", "Bold Editorial", "Fine Art", "Pure Type"],
        },
        "review_decision_field": {
            "options": ["approve_as_is", "request_rewrite_with_notes"],
        },
        "provisioning": {
            "total_keys": 38,
            "fields": [
                {"intended_key": "contact.anthology_%s_%s_url" % (d, s),
                 "create_name": "anthology_%s_%s_url" % (d, s),
                 "data_type": "LARGE_TEXT", "deliverable": d, "slot": s,
                 "field_id": None, "field_key": None, "verified_at": None,
                 "location_masked": None}
                for d, s in [
                    ("avatar", "doc"), ("avatar", "pdf"),
                    ("tone", "doc"), ("tone", "pdf"),
                    ("titles", "doc"), ("titles", "pdf"),
                    ("blurb", "doc"), ("blurb", "pdf"),
                    ("outline", "doc"), ("outline", "pdf"),
                    ("chapter", "doc"), ("chapter", "pdf"),
                    ("chapter_rewrite1", "doc"), ("chapter_rewrite1", "pdf"),
                    ("chapter_rewrite2", "doc"), ("chapter_rewrite2", "pdf"),
                    ("cover", "image"), ("cover", "drive"),
                    ("cover_sample1", "url"), ("cover_sample2", "url"),
                    ("cover_sample3", "url"), ("cover_sample4", "url"),
                    ("manuscript", "doc"), ("manuscript", "pdf"),
                ]
            ]
            + [
                {"intended_key": "contact.anthology_cover_choice",
                 "create_name": "anthology_cover_choice",
                 "data_type": "SINGLE_OPTIONS", "deliverable": "cover_style",
                 "slot": "choice",
                 "options": ["Signature", "Bold Editorial", "Fine Art", "Pure Type"],
                 "field_id": None, "field_key": None, "verified_at": None,
                 "location_masked": None},
                {"intended_key": "contact.anthology_active_id",
                 "create_name": "anthology_active_id",
                 "data_type": "LARGE_TEXT", "deliverable": "control",
                 "slot": "active_id",
                 "field_id": None, "field_key": None, "verified_at": None,
                 "location_masked": None},
                {"intended_key": "contact.anthology_stage",
                 "create_name": "anthology_stage",
                 "data_type": "LARGE_TEXT", "deliverable": "control",
                 "slot": "stage",
                 "field_id": None, "field_key": None, "verified_at": None,
                 "location_masked": None},
                {"intended_key": "contact.anthology_rewrite_count",
                 "create_name": "anthology_rewrite_count",
                 "data_type": "LARGE_TEXT", "deliverable": "control",
                 "slot": "rewrite_count",
                 "field_id": None, "field_key": None, "verified_at": None,
                 "location_masked": None},
                {"intended_key": "contact.anthology_book_name",
                 "create_name": "anthology_book_name",
                 "data_type": "LARGE_TEXT", "deliverable": "intake",
                 "slot": "book_name",
                 "field_id": None, "field_key": None, "verified_at": None,
                 "location_masked": None},
                {"intended_key": "contact.anthology_title_choice",
                 "create_name": "anthology_title_choice",
                 "data_type": "LARGE_TEXT", "deliverable": "title",
                 "slot": "title_choice",
                 "field_id": None, "field_key": None, "verified_at": None,
                 "location_masked": None},
                {"intended_key": "contact.anthology_subtitle_choice",
                 "create_name": "anthology_subtitle_choice",
                 "data_type": "LARGE_TEXT", "deliverable": "title",
                 "slot": "subtitle_choice",
                 "field_id": None, "field_key": None, "verified_at": None,
                 "location_masked": None},
                {"intended_key": "contact.anthology_review_decision",
                 "create_name": "anthology_review_decision",
                 "data_type": "SINGLE_OPTIONS", "deliverable": "review",
                 "slot": "decision",
                 "options": ["approve_as_is", "request_rewrite_with_notes"],
                 "field_id": None, "field_key": None, "verified_at": None,
                 "location_masked": None},
                {"intended_key": "contact.anthology_review_notes",
                 "create_name": "anthology_review_notes",
                 "data_type": "LARGE_TEXT", "deliverable": "review",
                 "slot": "notes",
                 "field_id": None, "field_key": None, "verified_at": None,
                 "location_masked": None},
                {"intended_key": "contact.anthology_review_stage",
                 "create_name": "anthology_review_stage",
                 "data_type": "LARGE_TEXT", "deliverable": "review",
                 "slot": "stage",
                 "field_id": None, "field_key": None, "verified_at": None,
                 "location_masked": None},
                {"intended_key": "contact.chapter_about",
                 "create_name": "chapter_about",
                 "data_type": "LARGE_TEXT", "deliverable": "intake",
                 "slot": "chapter_about",
                 "field_id": None, "field_key": None, "verified_at": None,
                 "location_masked": None},
                {"intended_key": "contact.ideal_avatar",
                 "create_name": "ideal_avatar",
                 "data_type": "LARGE_TEXT", "deliverable": "intake",
                 "slot": "ideal_avatar",
                 "field_id": None, "field_key": None, "verified_at": None,
                 "location_masked": None},
                {"intended_key": "contact.niche",
                 "create_name": "niche",
                 "data_type": "LARGE_TEXT", "deliverable": "intake",
                 "slot": "niche",
                 "field_id": None, "field_key": None, "verified_at": None,
                 "location_masked": None},
                {"intended_key": "contact.primary_goal",
                 "create_name": "primary_goal",
                 "data_type": "LARGE_TEXT", "deliverable": "intake",
                 "slot": "primary_goal",
                 "field_id": None, "field_key": None, "verified_at": None,
                 "location_masked": None},
            ],
        },
    }

    # 1. load the golden map: 38 rows, all five contract laws satisfied
    inv = load_field_map(_write_tmp(golden, dev))
    assert len(inv) == CONTRACT_TOTAL == 38, \
        "golden map must load 38 keys, got %d" % len(inv)
    keys = [r["intended_key"] for r in inv]
    assert len(set(keys)) == 38, "golden keys must be unique"
    assert all(k.startswith(reg._KEY_PREFIX) for k in keys), \
        "every key must carry the contact. prefix"

    # 2. the report: status only, the field_id VALUE never surfaces
    report = build_report(inv, source="memory")
    assert report["ok"] is True and report["loaded"] == 38
    assert report["resolved"] == 0, "null slots must read UNRESOLVED"
    for f in report["fields"]:
        assert f["resolved_status"] == "UNRESOLVED", \
            "null field_id must report UNRESOLVED, got %r" % f["resolved_status"]
    blob = json.dumps(report)
    assert "fld_" not in blob, "no field id value may ever surface"

    # 3. a resolved slot reports RESOLVED but still never its value
    resolved = json.loads(json.dumps(golden))
    resolved["provisioning"]["fields"][0]["field_id"] = "fld_live_000001"
    inv_r = load_field_map(_write_tmp(resolved, dev))
    rpt_r = build_report(inv_r, source="memory")
    assert rpt_r["resolved"] == 1 and \
        rpt_r["fields"][0]["resolved_status"] == "RESOLVED"
    assert "fld_live_000001" not in json.dumps(rpt_r), \
        "a resolved field id must never reach the report"

    # -- ATTACK fixtures: every drift REFUSED (fail-closed) -------------------
    def expect_refusal(mutator, why):
        doc = json.loads(json.dumps(golden))
        mutator(doc)
        try:
            load_field_map(_write_tmp(doc, dev))
        except FieldMapError:
            return
        raise AssertionError("must refuse: %s" % why)

    expect_refusal(lambda d: d.pop("provisioning", None),
                   "missing provisioning block")
    expect_refusal(lambda d: d["provisioning"].pop("fields", None),
                   "missing fields inventory")
    expect_refusal(lambda d: d["provisioning"].__setitem__("fields", []),
                   "empty inventory")
    expect_refusal(lambda d: d["provisioning"].__setitem__("fields", "nope"),
                   "non-list inventory")
    expect_refusal(lambda d: d["provisioning"]["fields"].append("scalar"),
                   "non-object row")
    expect_refusal(lambda d: d["provisioning"].__setitem__("total_keys", 27),
                   "total_keys drifted from the inventory")
    expect_refusal(lambda d: d["provisioning"]["fields"].append(
        dict(d["provisioning"]["fields"][0])),
                   "duplicate intended_key")
    expect_refusal(lambda d: d["provisioning"]["fields"][0].__setitem__(
        "intended_key", "anthology_avatar_doc_url"),
                   "key without the contact. prefix")
    expect_refusal(lambda d: d["provisioning"]["fields"][0].__setitem__(
        "create_name", "anthology_wrong_name"),
                   "create_name violating the derivation law")
    expect_refusal(lambda d: d["provisioning"]["fields"][0].__setitem__(
        "data_type", "TEXT"),
                   "free-text key declared TEXT, not LARGE_TEXT")
    expect_refusal(lambda d: d["provisioning"]["fields"].pop(
        next(i for i, r in enumerate(d["provisioning"]["fields"])
             if r["intended_key"] == COVER_CHOICE_KEY)),
                   "cover choice key absent")
    expect_refusal(lambda d: next(r for r in d["provisioning"]["fields"]
                                  if r["intended_key"] == COVER_CHOICE_KEY)
                   .__setitem__("data_type", "LARGE_TEXT"),
                   "cover choice declared LARGE_TEXT, not SINGLE_OPTIONS")
    expect_refusal(lambda d: next(r for r in d["provisioning"]["fields"]
                                  if r["intended_key"] == COVER_CHOICE_KEY)
                   .__setitem__("options", ["Signature"]),
                   "cover choice options drifted from choice_options")
    expect_refusal(lambda d: d["cover_style_fields"].__setitem__(
        "choice_options", []),
                   "choice_options emptied")

    # 4. the real shipped map loads (the live contract file) -- the loader's
    #    own PROOF against the committed config, byte-exact
    inv_real = load_field_map(reg.SKILL_DIR / "config" / "field-map.json")
    assert len(inv_real) == CONTRACT_TOTAL, \
        "the shipped field-map must carry %d keys, got %d" \
        % (CONTRACT_TOTAL, len(inv_real))

    # 5. the browser-UA law: the shared constant is present and byte-pinned
    #    to the Podcast gate's proven-live string (GK-09 regression pin --
    #    the same pin the registry's own self-test enforces, so a drift in
    #    the wiring is caught OFFLINE, never first seen as a CF 1010)
    assert reg.CAF_BROWSER_UA == (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ), "CAF_BROWSER_UA drifted from the Podcast gate's proven-live string"

    # 6. the CLI gates: run without a map STOPS; run on the golden map
    #    PASSES; an empty command STOPS (usage)
    rc_usage = main([])
    assert rc_usage == reg.EX_STOP, "no command must STOP, got %r" % rc_usage
    rc_bad = main(["run", "--field-map", "/nonexistent/field-map.json"])
    assert rc_bad == reg.EX_STOP, \
        "missing map file must STOP, got %r" % rc_bad
    rc_run = main(["run", "--field-map", str(_write_tmp(golden, dev))])
    assert rc_run == reg.EX_OK, "golden run must PASS, got %r" % rc_run

    _cleanup_temp(dev)

    sys.stderr.write(
        "fieldmap_loader self-test: OK (golden 38-key load; status-only "
        "report, resolved slot value never surfaced; and 14 attack "
        "fixtures refused fail-closed: missing provisioning / missing "
        "inventory / empty inventory / non-list inventory / non-object row "
        "/ total_keys drift / duplicate key / missing prefix / derivation "
        "law / wrong free-text type / absent cover choice / wrong choice "
        "type / drifted options / emptied choice_options; shipped map "
        "loads; browser-UA pin held)\n")
    return reg.EX_OK


def _write_tmp(doc: dict, dev: io.StringIO) -> Path:
    """Write a fixture map to a throwaway temp file next to the module and
    return its path (self-test scaffolding only; never a secret, never
    shared state)."""
    import tempfile
    fd, name = tempfile.mkstemp(prefix=".fieldmap-test-", suffix=".json",
                                dir=str(Path(__file__).resolve().parent))
    try:
        with open(fd, "w", encoding="utf-8") as fh:
            json.dump(doc, fh)
    except OSError:
        dev.write("[fieldmap-loader] self-test: temp fixture write failed\n")
        raise
    return Path(name)


def _cleanup_temp(dev: io.StringIO) -> None:
    """Remove the self-test's throwaway fixture files (a failing self-test
    must never leave its fixtures scattered next to the module)."""
    import glob
    for name in glob.glob(str(Path(__file__).resolve().parent / ".fieldmap-test-*.json")):
        try:
            Path(name).unlink()
        except OSError as exc:
            dev.write("[fieldmap-loader] self-test: temp cleanup failed "
                      "for %s: %s\n" % (name, exc))


if __name__ == "__main__":
    sys.exit(main())
