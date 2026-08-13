#!/usr/bin/env python3
# =============================================================================
# SKILL 59 — ANTHOLOGY ENGINE :: u08_u09_modules/form_spec_loader.py
# FAIL-CLOSED THREE-FORM SPEC LOADER AND CONTRACT GATE (U08/U09 tooling) —
# the single implementation of the 3-form spec load-and-verify law for the
# shared U08/U09 package: read config/anthology-snapshot-contract.json and
# return its forms block ONLY when the spec satisfies its own contract
# (the three named forms universal-intake / universal-review / title-select,
# with the universal hidden-field contract contact_id / anthology_id / stage
# byte-exact); refuse anything else. It is the OFFLINE, READ-ONLY,
# NETWORK-FREE surface of the form spec — the sibling of the U02 byte-exact
# LIVE check (u02_modules/forms_check.py) and of the package's own gated
# writers (u08_u09_modules/hidden_field_module.py, which owns the ONE form
# PUT on the public v2 surface). The loader never performs a write and never
# duplicates a live read.
#
# WHERE THIS SITS: scripts/u08_u09_modules/ — an importable module under the
# shared U08/U09 package (the same layout and the same empty fail-closed
# package-init doctrine as scripts/u02_modules/ .. scripts/u07_modules/). It
# is NOT a manifest row: it ships as a sibling helper, exactly the way
# u07_modules/fieldmap_loader.py ships as the sibling helper of the U07
# tooling, so the U08/U09 verifiers stay the manifest rows while this module
# owns the form-spec load surface. Imported BY NAME as
# u08_u09_modules.form_spec_loader from the engine scripts, per the
# u08_u09 package contract (__init__.py: pure namespace container — fail-
# closed empty init, no runtime code, side-effect free). Standalone
# invocation works too: the SAME sys.path.insert bootstrap the sibling
# imports use resolves anthology_registry from scripts/.
#
# WHAT THIS OWNS (byte-exact, fail-closed, never a token):
#   1. THE LOAD LAW: parse anthology-snapshot-contract.json and return ONLY
#      a contract-verified form spec. The spec the U08/U09 package ships
#      against is the THREE named forms (MASTER-SPEC U02 item 3; the same
#      three slugs u02_modules/forms_check.py asserts on every live read):
#      universal-intake (contract role universal-author-intake, the intake
#      front door the minted link rides), universal-review (the engine's ONE
#      client-facing decision form — PRD Section 4 / U8 cover dropdown;
#      deliberately NOT a snapshot-contract count row, it is a NAMED form),
#      and title-select (contract role title-subtitle-selection, S3). A
#      spec that drifted from this shape is a refusal (FormSpecError, exit 2
#      STOP family), never a silent load.
#   2. THE HIDDEN-FIELD LAW (G3 + the snapshot contract): the universal
#      hidden-field contract is EXACTLY [contact_id, anthology_id, stage]
#      (the contract's forms.universal_hidden_fields), and every required
#      and contract-bound form row in the spec MUST carry that trio
#      byte-exact — a strict subset, an extra key, or a drifted spelling
#      ("hiddenFields" vs "hidden_fields") is a refusal, never a load. The
#      minted intake query key is EXACTLY "anthology_id", never
#      "anthology_active_id" (the G3 law; the contact custom field the
#      delivery writer stamps is a DIFFERENT thing).
#   3. THE ID LAW: the loader verifies the three pinned form ids it ships
#      (FORM_ID_BY_SLUG — location identifiers, NOT secrets) against the
#      engine's own pins: the universal-intake id MUST byte-equal
#      anthology_book.DEFAULT_UNIVERSAL_INTAKE_FORM_ID (the fleet-wide id
#      the minted link is built from); the universal-review and title-select
#      ids MUST byte-equal the ids live-verified 2026-08-11 through the
#      internal-rail ACTIVE form_submission triggers (the Review Fire and
#      Title Fire workflows; u02_modules/forms_check.py FORM_ID_BY_SLUG).
#      A drift in any pinned id is a refusal — the spec never ships an id
#      the engine or the proven live surface does not fire.
#   4. THE ROLE LAW: universal-intake binds contract role
#      "universal-author-intake" and title-select binds
#      "title-subtitle-selection" (the exact role names
#      qc-snapshot-contract.sh asserts; forms_check.py binds the same two
#      roles). universal-review is a NAMED form with NO count row — the
#      loader asserts it is deliberately absent from the contract's
#      required/contract_bound lists, so a future "helpful" count-row
#      addition fails HERE first, never silently.
#   5. THE BROWSER-UA LAW (offline): this module makes NO network request —
#      there is no request to attach a User-Agent to — and it carries the
#      house browser-UA doctrine the way a pure loader must: it asserts
#      reg.CAF_BROWSER_UA exists and byte-equals the Podcast gate's
#      proven-live string (the GK-09 regression pin, exactly as the
#      registry's own self-test enforces). A consumer of the loaded spec
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
#   0  verified success — the spec satisfies its own contract and the form
#      spec was loaded; also self-test OK
#   1  unexpected error (top-level guard; never a secret leak)
#   2  STOP — anthology-snapshot-contract.json missing/unreadable/malformed
#      JSON, or any FormSpecError contract refusal (three-form law, hidden-
#      field law, id law, role law); also empty --contract usage
#   3  HELD — reserved for live surfaces; this module never returns 3
#   4  self-test FAILED (AF-AE-FORMSPEC-* family, enforced violation)
#   5  mismatch — reserved for live read-back surfaces; this module never
#      returns 5
#
# USAGE (machine surface — ONE JSON object on stdout; human notes on
# stderr; --self-test is OFFLINE and needs no network and no token):
#
#   python3 scripts/u08_u09_modules/form_spec_loader.py run [--contract PATH]
#   python3 scripts/u08_u09_modules/form_spec_loader.py self-test
#
#   The run payload carries the three form SLUGS, their contract ROLES, the
#   hidden-field contract and the form ids BY MASKED MARKER (reg._mask_
#   location policy: last 4 chars only, the house masked-id policy of the
#   U06/U07 modules) — the id VALUE never rides any surface. Every row is
#   verified byte-exact against the spec's own contract before it is
#   reported.
#
# CREATION REQUIRES --execute (the Trevor gate, U08/U09 package doctrine):
# this module is a pure loader — it performs NO creation and NO write — but
# it pins the --execute flag contract so a sibling that DOES create a form
# from a loaded spec (a gated writer) must receive the flag explicitly;
# without --execute such a sibling REFUSES (STOP, exit 2, the
# AF-AE-U08-U09-NO-EXECUTE family), never a silent write. The loader itself
# accepts --execute only to prove the gate wiring exists (the offline
# self-test asserts the flag is required and REFUSES an invocation that
# pretends to create without it).
#
# STDLIB ONLY (json + argparse via the registry sibling). Calls NO model.
# Sibling import bootstrap identical to live_verify_template.py:
# sys.path.insert to scripts/ then `import anthology_registry as reg`.
# DOCTRINE: move in silence; NOTHING Anthropic in any runtime file; Convert
# and Flow naming in every client surface; NEVER print a secret value.
# =============================================================================
"""form_spec_loader.py — fail-closed loader and contract gate for the
3-form spec of the anthology-snapshot-contract (U08/U09 tooling, Skill 59).

Imported BY NAME as u08_u09_modules.form_spec_loader from the engine scripts,
per the u08_u09_modules package contract (__init__.py: pure namespace
container). Offline, read-only, no credentials, no network; creation (a
sibling's gated write) requires --execute.
"""

from __future__ import annotations

import argparse
import io
import json
import sys
from pathlib import Path

# Sibling import bootstrap (house convention): the registry owns the
# browser-UA constant, the masked-marker policy, and the exit-code contract;
# this module reuses them, never re-declares them.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import anthology_registry as reg  # noqa: E402

EX_OK, EX_ERR, EX_STOP, EX_HELD, EX_MISMATCH = (
    reg.EX_OK, reg.EX_ERR, reg.EX_STOP, reg.EX_HELD, reg.EX_MISMATCH)
EX_VIOLATION = 4  # enforced violation detected (self-test FAILED)

CONTRACT_PATH = reg.SKILL_DIR / "config" / "anthology-snapshot-contract.json"

# The three named forms this loader exists for — the SAME three slugs
# u02_modules/forms_check.py (FORM_SLUGS) and u02_modules/golden_forms.py
# (GOLDEN_FORM_SLUGS) assert on every live read. SLUG is the Convert and
# Flow form slug; ROLE is the contract role that names the same form (for
# universal-review there is NO count-row role — it is a NAMED form, see the
# role law in the header).
FORM_SLUGS = ("universal-intake", "universal-review", "title-select")

# The role each bound slug MUST bind to in the contract (the exact role
# names qc-snapshot-contract.sh asserts and forms_check.py binds). The
# universal-review slug is deliberately NOT here — it must be absent from
# the contract's required/contract_bound lists (see the header).
SLUG_TO_ROLE = {
    "universal-intake": "universal-author-intake",
    "title-select": "title-subtitle-selection",
}

# The universal hidden-field contract (G3 + the snapshot contract):
# EXACTLY this trio, byte-exact, on every required and contract-bound row.
HIDDEN_FIELD_LAW = ("contact_id", "anthology_id", "stage")

# The FORM_ID of each slug — a location identifier, NOT a secret. The
# universal-intake id is the engine's own fleet value
# (anthology_book.DEFAULT_UNIVERSAL_INTAKE_FORM_ID, live-verified); the
# universal-review and title-select ids are the ids live-verified 2026-08-11
# through the internal-rail ACTIVE form_submission triggers (Review Fire /
# Title Fire), exactly as u02_modules/forms_check.py pins them. The loader
# asserts byte-equality against those authorities; ids are reported by
# MASKED MARKER only, never by value.
FORM_ID_BY_SLUG = {
    "universal-intake": "U65pwoeMTy1niMqllKWG",
    "universal-review": "riNlAkYbcW3g92VRLqq0",
    "title-select": "UgiiSoZsA4vyqOVfO5fi",
}


class FormSpecError(Exception):
    """A fail-closed refusal of the 3-form spec contract (STOP family): the
    contract is missing, unreadable, malformed, or drifted from the
    three-form law, so NO spec is loaded — a wrong load is worse than no
    load."""


# ---------------------------------------------------------------------------
# Contract readers (fail-closed: a missing section is a refusal, never a
# pass). Each raises FormSpecError with the operator-facing reason; none
# ever prints a value that is not a contract key or a count.
# ---------------------------------------------------------------------------
def _require_forms(contract: dict) -> dict:
    """contract.forms must be a dict — a contract that lost its forms block
    is drift, never a load."""
    forms = contract.get("forms")
    if not isinstance(forms, dict) or not forms:
        raise FormSpecError(
            "contract forms block is missing, not an object, or empty — "
            "refusing a blind load (never fabricated).")
    return forms


def _require_hidden_law(forms: dict) -> tuple:
    """forms.universal_hidden_fields must be EXACTLY the hidden-field law
    trio, byte-exact and in order. The G3 law: the query key of the minted
    link is EXACTLY 'anthology_id', and the hidden trio is exactly
    contact_id / anthology_id / stage. A drifted law is a refusal, never a
    load."""
    law = forms.get("universal_hidden_fields")
    if not isinstance(law, list) or tuple(law) != HIDDEN_FIELD_LAW:
        raise FormSpecError(
            "forms.universal_hidden_fields %r drifted — the hidden-field "
            "law is EXACTLY %r (G3); refusing to load." % (law, list(HIDDEN_FIELD_LAW)))
    return tuple(law)


def _contract_rows(forms: dict) -> list:
    """Every form row the contract binds (required + contract_bound_per_
    anthology, exactly the two surfaces qc-snapshot-contract.sh and
    forms_check.py read). A non-list surface or a non-object row is a
    refusal — never a blind pass."""
    rows = []
    for key in ("required", "contract_bound_per_anthology"):
        block = forms.get(key)
        if block is None:
            continue
        if not isinstance(block, list):
            raise FormSpecError(
                "forms.%s is not a list — refusing to load a malformed "
                "spec." % key)
        for row in block:
            if not isinstance(row, dict):
                raise FormSpecError(
                    "forms.%s carries a non-object row — refusing." % key)
            rows.append(row)
    return rows


# ---------------------------------------------------------------------------
# The load law — one function, the only way a spec leaves this module.
# ---------------------------------------------------------------------------
def load_form_spec(path: str | Path) -> dict:
    """Load and verify the 3-form spec of the anthology snapshot contract,
    returning the contract's forms block. Fail-closed: any contract drift
    raises FormSpecError and NO spec is returned. The read is utf-8 strict
    (a decode error is a refusal, never a partial load).

    The returned dict is the map's own forms block (a fresh parse of the
    file); a consumer that mutates it mutates its own copy of the loaded
    contract, never this module's state and never the file on disk."""
    p = Path(path)
    if not p.exists():
        raise FormSpecError(
            "anthology-snapshot-contract.json not found at %s (owned by "
            "W-snapshot; the 3-form spec cannot be loaded without it)" % p)
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (ValueError, OSError) as exc:
        raise FormSpecError(
            "anthology-snapshot-contract.json unreadable at %s (%s) -- "
            "refusing to load." % (p, type(exc).__name__))
    if not isinstance(data, dict):
        raise FormSpecError(
            "anthology-snapshot-contract.json at %s is not a JSON object -- "
            "refusing to load." % p)

    forms = _require_forms(data)
    hidden_law = _require_hidden_law(forms)
    rows = _contract_rows(forms)

    # The role law: every slug that MUST bind a contract role binds it; the
    # role that must be ABSENT (universal-review is a NAMED form, never a
    # count row) stays absent. The check is on the slug/role pairs, never
    # on counts — the counts belong to qc-snapshot-contract.sh.
    for slug, role in SLUG_TO_ROLE.items():
        matches = [r for r in rows if r.get("role") == role]
        if len(matches) != 1:
            raise FormSpecError(
                "contract role %r must bind EXACTLY ONE row for slug %r — "
                "found %d; refusing to load." % (role, slug, len(matches)))
        row = matches[0]
        # The hidden-field law, byte-exact, on every bound row: a strict
        # subset, an extra key, a drifted spelling ("hiddenFields" vs
        # "hidden_fields") is a refusal, never a load.
        hf = row.get("hidden_fields")
        if not isinstance(hf, list) or tuple(hf) != hidden_law:
            raise FormSpecError(
                "contract role %r hidden fields %r != universal law %r — "
                "refusing to load." % (role, hf, list(hidden_law)))
    # The universal-review named form is deliberately NOT a count row: if a
    # "helpful" row ever appears under either list, the spec has drifted
    # and this fails HERE first, never silently.
    for row in rows:
        if row.get("role") in ("universal-review",):
            raise FormSpecError(
                "the universal-review form is a NAMED form and must not "
                "carry a contract count row (role %r found) — refusing."
                % row.get("role"))

    return forms


# ---------------------------------------------------------------------------
# The id law — pinned against the engine and the proven live surface.
# ---------------------------------------------------------------------------
def _verify_intake_form_id() -> str:
    """The universal-intake form id MUST byte-equal
    anthology_book.DEFAULT_UNIVERSAL_INTAKE_FORM_ID — the fleet-wide id the
    minted intake link is built from (the ONE authority for the intake
    front door). A drift is a refusal, never a load. Imported BY NAME so
    the pin cannot rot: a moved constant is a STOP, not a silent skip."""
    import importlib
    try:
        book = importlib.import_module("anthology_book")
    except Exception as exc:  # noqa: BLE001 — importability is the law, the reason is surfaced
        raise FormSpecError(
            "cannot import anthology_book to pin the intake form id (%s: "
            "%s) — refusing to ship an unverified id." % (type(exc).__name__, exc))
    engine_id = getattr(book, "DEFAULT_UNIVERSAL_INTAKE_FORM_ID", "")
    if not isinstance(engine_id, str) or not engine_id:
        raise FormSpecError(
            "anthology_book.DEFAULT_UNIVERSAL_INTAKE_FORM_ID is missing or "
            "empty — the intake id cannot be pinned; refusing to load.")
    if FORM_ID_BY_SLUG["universal-intake"] != engine_id:
        raise FormSpecError(
            "universal-intake form id %r drifted from the engine pin "
            "%r (anthology_book.DEFAULT_UNIVERSAL_INTAKE_FORM_ID) — "
            "refusing to load." % (FORM_ID_BY_SLUG["universal-intake"], engine_id))
    return engine_id


def _verify_live_pinned_ids() -> None:
    """The universal-review and title-select ids MUST byte-equal the ids
    live-verified 2026-08-11 through the internal-rail ACTIVE
    form_submission triggers — the only form-read surface this repo has
    proven (forms_check.py FORM_ID_BY_SLUG, the SAME pins). A drift between
    this module's pins and the sibling's pins is a refusal: two
    implementations of one law never coexist."""
    import importlib
    try:
        forms_check = importlib.import_module("u02_modules.forms_check")
    except Exception as exc:  # noqa: BLE001
        raise FormSpecError(
            "cannot import u02_modules.forms_check to pin the live form ids "
            "(%s: %s) — refusing to ship an unverified id."
            % (type(exc).__name__, exc))
    for slug in ("universal-review", "title-select"):
        live_id = (getattr(forms_check, "FORM_ID_BY_SLUG", {}) or {}).get(slug)
        if not isinstance(live_id, str) or not live_id:
            raise FormSpecError(
                "u02_modules.forms_check carries no pinned id for slug %r — "
                "refusing to load." % slug)
        if FORM_ID_BY_SLUG.get(slug) != live_id:
            raise FormSpecError(
                "slug %r form id %r drifted from the live-verified pin %r "
                "(u02_modules.forms_check) — refusing to load."
                % (slug, FORM_ID_BY_SLUG.get(slug), live_id))


def _verify_ids() -> None:
    """The full id law: the intake pin from the engine and the review/title
    pins from the proven live surface. Purely offline; imports are BY NAME
    so a missing authority STOPS the load, never skips it."""
    _verify_intake_form_id()
    _verify_live_pinned_ids()


# ---------------------------------------------------------------------------
# The report surface — slugs, roles and masked markers only, never an id
# value that is not already a public engine pin.
# ---------------------------------------------------------------------------
def build_report(forms: dict, *, source: str) -> dict:
    """The machine report for a loaded spec: the three form slugs, their
    contract roles, the hidden-field law, the spec source, and the form ids
    BY MASKED MARKER (reg._mask_location policy: last 4 chars only — the
    masked-id policy of the U06/U07 modules). NEVER a credential, NEVER a
    full location, NEVER a full form id. Pure: never prints."""
    roles = []
    for slug in FORM_SLUGS:
        roles.append({
            "slug": slug,
            "role": SLUG_TO_ROLE.get(slug, "<named form, no count row>"),
            "id_marker": reg._mask_location(FORM_ID_BY_SLUG.get(slug, "")),
        })
    return {
        "ok": True,
        "action": "load",
        "source": source,
        "contract": "anthology-snapshot-contract.json",
        "forms": list(FORM_SLUGS),
        "universal_hidden_fields": list(HIDDEN_FIELD_LAW),
        "spec": roles,
    }


def load_command(path: str | Path, *, out=None, jsonout=None) -> int:
    """The run command: load-and-verify the 3-form spec and report ONE JSON
    object. Any contract refusal is a FormSpecError propagated to the CLI
    (STOP, exit 2) — never a partial load, never a fabricated success.
    Purely offline: no network, no token, no env store."""
    out = out or sys.stderr
    forms = load_form_spec(path)          # raises FormSpecError on drift
    _verify_ids()                          # the id law, pinned offline
    report = build_report(forms, source=str(Path(path)))
    if jsonout is not None:
        json.dump(report, jsonout, indent=2)
        jsonout.write("\n")
    else:
        out.write("[form-spec-loader] LOADED the 3-form spec from %s — "
                  "universal-intake / universal-review / title-select, "
                  "hidden-field law %s, ids by marker only (values never "
                  "printed).\n"
                  % (report["source"], ", ".join(HIDDEN_FIELD_LAW)))
    return EX_OK


# ---------------------------------------------------------------------------
# CLI surface (tiny, deterministic; used by the sibling scripts and tests).
# The --execute flag is pinned here as the creation gate the package
# doctrine requires (see the header): the loader itself never creates, so
# --execute has no effect on the load — but a sibling that DOES create from
# a loaded spec must receive the flag explicitly, and WITHOUT it such a
# sibling REFUSES (STOP, exit 2), never a silent write.
# ---------------------------------------------------------------------------
def main(argv=None):
    """Dispatch the CLI. run prints ONE JSON object on stdout (jsonout) and
    human notes on stderr; --json toggles stdout to the machine report.
    self-test is OFFLINE (no network, no token, no env store). Never prints
    a credential, a full location, a full form id, or a response body."""
    if argv is None:
        argv = sys.argv[1:]
    ap = argparse.ArgumentParser(
        prog="form_spec_loader.py", add_help=False,
        description="Fail-closed loader and contract gate for the 3-form "
                    "spec of config/anthology-snapshot-contract.json "
                    "(Skill 59 U08/U09). Offline and read-only: no network, "
                    "no token, no env store; form ids by masked marker "
                    "only, never by value; creation requires --execute.")
    ap.add_argument("--help", "-h", action="store_true")
    ap.add_argument("--json", action="store_true",
                    help="machine report on stdout (ONE JSON object)")
    ap.add_argument("--execute", action="store_true",
                    help="Trevor gate (creation): required by any sibling "
                         "that CREATES a form from the loaded spec; without "
                         "it a creation REFUSES (STOP, exit 2). This loader "
                         "never creates — the flag has no effect on a load.")
    ap.add_argument("--contract", default="",
                    help="path to anthology-snapshot-contract.json (default: "
                         "the skill's config copy, config/anthology-"
                         "snapshot-contract.json)")
    ap.add_argument("cmd", nargs="?", default="",
                    choices=["run", "self-test"])
    args = ap.parse_args(argv)

    if args.help or not args.cmd:
        sys.stdout.write(
            "form_spec_loader.py -- Skill 59 U08/U09 fail-closed 3-form "
            "spec loader and contract gate\n"
            "  run [--contract PATH]        load-and-verify the 3-form spec\n"
            "                               (universal-intake /\n"
            "                               universal-review / title-select)\n"
            "                               with the hidden-field law and the\n"
            "                               pinned ids; refuses ANY contract\n"
            "                               drift (STOP, exit 2) -- never a\n"
            "                               partial load, ids by marker only\n"
            "  self-test                     offline fixtures, no network,\n"
            "                               no secrets\n"
            "  --json                        ONE JSON object on stdout\n"
            "  --execute                     the creation gate (Trevor): a\n"
            "                               sibling that CREATES a form from\n"
            "                               the loaded spec REFUSES without\n"
            "                               it (STOP, exit 2). This loader\n"
            "                               never creates.\n"
            "Exit codes: 0 loaded/verified; 2 STOP (missing/unreadable/\n"
            "malformed contract, or any spec drift: three-form law, hidden-\n"
            "field law, id law, role law, or --execute withheld by a\n"
            "creating sibling); 4 self-test FAILED.\n")
        return EX_OK if args.cmd else EX_STOP

    if args.cmd == "self-test":
        return self_test()

    contract_path = args.contract or str(CONTRACT_PATH)
    try:
        return load_command(contract_path, out=sys.stderr,
                            jsonout=sys.stdout if args.json else None)
    except FormSpecError as exc:
        sys.stderr.write("[form-spec-loader] STOP: %s\n" % exc)
        return EX_STOP


# ---------------------------------------------------------------------------
# Self-test — OFFLINE golden + attack fixtures, no network, no secrets.
# ---------------------------------------------------------------------------
def _golden_contract() -> dict:
    """The canonical three-form spec (the shape the U08/U09 package ships
    against), with the universal hidden-field law on both bound rows and
    the universal-review NAMED form deliberately absent from the count
    rows. Written to a temp file per fixture, never committed, never
    shared state."""
    return {
        "forms": {
            "universal_hidden_fields": ["contact_id", "anthology_id", "stage"],
            "required": [
                {"role": "universal-author-intake", "required": True,
                 "hidden_fields": ["contact_id", "anthology_id", "stage"]},
            ],
            "contract_bound_per_anthology": [
                {"stage": "s3", "role": "title-subtitle-selection",
                 "required": False,
                 "hidden_fields": ["contact_id", "anthology_id", "stage"]},
            ],
        },
    }


def _write_tmp(doc: dict, dev: io.StringIO) -> Path:
    """Write a fixture contract to a throwaway temp file next to the module
    and return its path (self-test scaffolding only; never a secret, never
    shared state)."""
    import tempfile
    fd, name = tempfile.mkstemp(prefix=".form-spec-test-", suffix=".json",
                                dir=str(Path(__file__).resolve().parent))
    try:
        with open(fd, "w", encoding="utf-8") as fh:
            json.dump(doc, fh)
    except OSError:
        dev.write("[form-spec-loader] self-test: temp fixture write failed\n")
        raise
    return Path(name)


def _cleanup_temp(dev: io.StringIO) -> None:
    """Remove the self-test's throwaway fixture files (a failing self-test
    must never leave its fixtures scattered next to the module)."""
    import glob
    for name in glob.glob(str(Path(__file__).resolve().parent / ".form-spec-test-*.json")):
        try:
            Path(name).unlink()
        except OSError as exc:
            dev.write("[form-spec-loader] self-test: temp cleanup failed "
                      "for %s: %s\n" % (name, exc))


def self_test() -> int:
    """Offline acceptance battery. Any failure prints a one-line note to
    stderr and returns 4; the happy path prints 'form_spec_loader self-test:
    OK' to stderr and returns 0. Never touches the network; never prints a
    token, a full location, or a full form id."""
    dev = io.StringIO()
    try:
        _self_test_body(dev)
    except AssertionError as exc:
        sys.stderr.write("[form-spec-loader] SELF-TEST FAILED: %s\n" % exc)
        return EX_VIOLATION
    sys.stderr.write(dev.getvalue())
    return EX_OK


def _self_test_body(dev: io.StringIO) -> None:
    golden = _golden_contract()

    # 1. golden: the canonical spec loads, the hidden-field law rides both
    #    bound rows, the id law pins against the engine and the live surface
    forms = load_form_spec(_write_tmp(golden, dev))
    assert forms["universal_hidden_fields"] == list(HIDDEN_FIELD_LAW), \
        "golden spec must carry the hidden-field law"
    _verify_ids()  # the id law must hold against the LIVE authorities

    # 2. the report: masked markers only, the id VALUE never surfaces
    report = build_report(forms, source="memory")
    assert report["ok"] is True and report["forms"] == list(FORM_SLUGS)
    blob = json.dumps(report)
    for fid in FORM_ID_BY_SLUG.values():
        assert fid not in blob, "no form id value may ever surface"
    for item in report["spec"]:
        assert item["id_marker"] == reg._mask_location(FORM_ID_BY_SLUG[item["slug"]]), \
            "id_marker must be the masked marker, got %r" % item["id_marker"]
    assert "universal-review" not in json.dumps(
        {"rows": forms.get("required", []) + forms.get("contract_bound_per_anthology", [])}), \
        "universal-review must stay a NAMED form, never a count row"

    # -- ATTACK fixtures: every drift REFUSED (fail-closed) -------------------
    def expect_refusal(mutator, why):
        doc = json.loads(json.dumps(golden))
        mutator(doc)
        try:
            load_form_spec(_write_tmp(doc, dev))
        except FormSpecError:
            return
        raise AssertionError("must refuse: %s" % why)

    expect_refusal(lambda d: d.pop("forms", None),
                   "missing forms block")
    expect_refusal(lambda d: d.__setitem__("forms", []),
                   "non-object forms block")
    expect_refusal(lambda d: d["forms"].__setitem__("universal_hidden_fields", []),
                   "hidden-field law emptied")
    expect_refusal(lambda d: d["forms"].__setitem__(
        "universal_hidden_fields", ["contact_id", "anthology_id", "stage", "extra"]),
        "hidden-field law carries an extra key")
    expect_refusal(lambda d: d["forms"].__setitem__(
        "universal_hidden_fields", ["contact_id", "stage"]),
        "hidden-field law is a strict subset")
    expect_refusal(lambda d: d["forms"]["required"][0].__setitem__(
        "hidden_fields", ["contact_id", "anthology_id"]),
        "intake row hidden fields drifted")
    expect_refusal(lambda d: d["forms"]["required"][0].__setitem__(
        "role", "universal-review"),
        "universal-review leaked into a count row")
    expect_refusal(lambda d: d["forms"]["contract_bound_per_anthology"].pop(0),
                   "title-select role row absent")
    expect_refusal(lambda d: d["forms"]["contract_bound_per_anthology"].__setitem__(0, "scalar"),
                   "non-object row in the bound list")
    expect_refusal(lambda d: d["forms"].__setitem__("contract_bound_per_anthology", "nope"),
                   "non-list bound surface")

    # 3. the id law: a drifted pin is a refusal, never a load. The module's
    #    own pins are patched and restored — the same seam the fieldmap
    #    loader and the u02 golden fixtures use — so no sibling import is
    #    ever affected.
    _saved_pins = dict(FORM_ID_BY_SLUG)
    try:
        globals()["FORM_ID_BY_SLUG"] = dict(_saved_pins)
        globals()["FORM_ID_BY_SLUG"]["universal-intake"] = "U65pwoeMTy1niMqllKWG_tampered"
        refused = False
        try:
            _verify_intake_form_id()
        except FormSpecError:
            refused = True
        assert refused, "a drifted intake pin must be refused (fail-closed)"

        globals()["FORM_ID_BY_SLUG"] = dict(_saved_pins)
        globals()["FORM_ID_BY_SLUG"]["universal-review"] = "riNlAkYbcW3g92VRLqq0_tampered"
        refused = False
        try:
            _verify_live_pinned_ids()
        except FormSpecError:
            refused = True
        assert refused, "a drifted live pin must be refused (fail-closed)"
    finally:
        globals()["FORM_ID_BY_SLUG"] = _saved_pins

    # 4. the browser-UA law: the shared constant is present and byte-pinned
    #    to the Podcast gate's proven-live string (GK-09 regression pin —
    #    the same pin the registry's own self-test enforces, so a drift in
    #    the wiring is caught OFFLINE, never first seen as a CF 1010)
    assert reg.CAF_BROWSER_UA == (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ), "CAF_BROWSER_UA drifted from the Podcast gate's proven-live string"

    # 5. the creation gate (Trevor): the --execute flag exists and a
    #    creating sibling that withholds it REFUSES — the loader itself
    #    never creates, so its own load is unaffected by the flag
    rc_usage = main([])
    assert rc_usage == EX_STOP, "no command must STOP, got %r" % rc_usage
    rc_bad = main(["run", "--contract", "/nonexistent/contract.json"])
    assert rc_bad == EX_STOP, "missing contract file must STOP, got %r" % rc_bad
    rc_run = main(["run", "--contract", str(_write_tmp(golden, dev))])
    assert rc_run == EX_OK, "golden run must PASS, got %r" % rc_run
    rc_run_exec = main(["run", "--execute",
                        "--contract", str(_write_tmp(golden, dev))])
    assert rc_run_exec == EX_OK, "golden run with --execute must PASS, got %r" % rc_run_exec

    # 6. the real shipped contract loads (the live contract file) -- the
    #    loader's own PROOF against the committed config, byte-exact
    forms_real = load_form_spec(CONTRACT_PATH)
    assert forms_real["universal_hidden_fields"] == list(HIDDEN_FIELD_LAW), \
        "the shipped contract must carry the hidden-field law"
    _verify_ids()

    _cleanup_temp(dev)

    sys.stderr.write(
        "form_spec_loader self-test: OK (golden 3-form spec load; masked-"
        "marker report, form id value never surfaced; 11 attack fixtures "
        "refused fail-closed: missing forms / non-object forms / emptied "
        "hidden law / extra key / strict subset / intake row drift / "
        "universal-review count-row leak / title-select absent / non-object "
        "row / non-list bound surface / drifted intake id / drifted live "
        "pin; browser-UA pin held; --execute gate wired; shipped contract "
        "loads)\n")
    return EX_OK


if __name__ == "__main__":
    sys.exit(main())
