#!/usr/bin/env python3
# =============================================================================
# SKILL 59 — ANTHOLOGY ENGINE :: u02_modules/golden_forms
# GOLDEN FORMS FIXTURE — the canonical three-form payload for the U02 tooling
# self-tests (MASTER-SPEC U02 item 3; the sibling module forms_check.py).
# -----------------------------------------------------------------------------
# WHAT THIS OWNS
#   ONE golden forms payload: the three named Convert and Flow forms —
#   universal-intake / universal-review / title-select — exactly as the
#   internal-rail /workflow/{loc}/list rows of type != "workflow" read them
#   back, with the universal hidden-field contract (contact_id / anthology_id
#   / stage) on every row. Imported BY NAME (u02_modules.golden_forms) by the
#   sibling self-tests so the golden state stays a single, diffable source of
#   truth instead of being re-typed inside each test body.
#
#   The SAME three-slug contract is asserted on every successful read by
#   forms_check.py (FORM_SLUGS) and by live_verify_template.py check_forms
#   (item 3: forms are counted from the rail listing rows of type !=
#   "workflow"). This fixture is the payload BOTH consumers pass on — the
#   golden live state that must never drift into a FAIL. "forms" in the name
#   means the FORMS payload only: the pipeline / fields / custom-values /
#   workflows golden states each live inside their own sibling module's
#   self-test body (pipeline_check._golden_pipeline etc.), where they belong.
#
# FAIL-CLOSED / SECRETS / BROWSER-UA DOCTRINE (house, per anthology_registry.py
#   / drive_adapter.py / forms_check.py):
#   - A fixture is DATA, not code: it performs no I/O, holds no credential,
#     and can never leak a token by construction. Nothing here reads an env
#     var, opens a file, or touches the network.
#   - Every row in the golden payload is a fixture row that any live read can
#     reproduce with the rail; it never carries a value that could be a
#     credential. The location marker is the fixed operator-template marker
#     from the sibling checks (reg._mask_location of the template location),
#     never a real location id.
#   - This module itself performs NO requests, so it defines NO User-Agent
#     constant of its own — the browser UA that defeats the Cloudflare edge
#     (CF 1010) on services.leadconnectorhq.com is CAF_BROWSER_UA, owned by
#     anthology_registry.py and applied by its clients (CafClient /
#     InternalRailClient), which is exactly what the live forms read rides.
#     Importing golden_forms never imports anthology_registry, so a fixture
#     cannot drag the credential-resolution code into a test process that
#     needs none.
#   - Move in silence; NOTHING Anthropic in any runtime file; Convert and
#     Flow naming in every client surface; never print a secret value.
#
# SHAPE (byte-exact contract the fixture commits to — a drift here is caught
#   by the offline self-test in forms_check.py, never silently):
#   GOLDEN_FORM_SLUGS        ("universal-intake", "universal-review", "title-select")
#   GOLDEN_UNIVERSAL_HIDDEN  ["contact_id", "anthology_id", "stage"]
#   GOLDEN_FORMS             the three rows, slug / name / type / hiddenFields
#   GOLDEN_FORM_NAMES        the display names, for the name-match law
#   GOLDEN_TEMPLATE_LOCATION the fixed template-location marker of the golden
#                            state (the operator's OWN template location)
#   golden_form_rows()       a deep-copied list of the rows (callers may
#                            mutate their copy; the module constant is never
#                            touched)
#   golden_form_name_matches()  rows matched by the display-name law (a row
#                            whose name is the slug with dashes -> spaces)
#   golden_rail_payload()    the full {"rows": [...]} listing object the rail
#                            serves, with the three form rows on it
# =============================================================================
"""golden_forms.py -- the golden three-form payload for the U02 self-tests.

Pure data + tiny pure builders. Imported BY NAME as u02_modules.golden_forms
from the sibling self-tests (forms_check.py, live_verify_template.py). No I/O,
no credentials, no network — a fixture cannot leak what it never holds.
"""

from __future__ import annotations

import copy

# ---------------------------------------------------------------------------
# The golden payload (canonical, diffable, never mutated in place).
# ---------------------------------------------------------------------------
# The three named forms this fixture exists for — the same three slugs
# forms_check.FORM_SLUGS asserts on every successful read. universal-review
# is the engine's own name for the PRD Section 4 decision form (deliberately
# NOT a snapshot-contract count row; see forms_check.py's header).
GOLDEN_FORM_SLUGS = ("universal-intake", "universal-review", "title-select")

# The universal hidden-field contract, asserted byte-exact on every form row
# by forms_check.check_forms and live_verify_template.check_forms. The three
# fixed field names only — nothing else may ever ride a golden row.
GOLDEN_UNIVERSAL_HIDDEN = ["contact_id", "anthology_id", "stage"]

# The fixed operator-template location marker of the golden state. This is
# the SAME operator infrastructure config the sibling checks pin to
# (forms_check.DEFAULT_TEMPLATE_LOCATION / the contract's
# source_template_location.template_location_id). Not a secret — but a
# fixture must never carry a live client location, so the golden marker is
# the template location, not a client one.
GOLDEN_TEMPLATE_LOCATION = "2HIKGNgsixWx0yds7Qnx"

# The three display names — the name-match law (a row whose name is the slug
# with dashes -> spaces) resolves each slug to exactly one of these. Kept in
# slug order; index i pairs with GOLDEN_FORM_SLUGS[i].
GOLDEN_FORM_NAMES = ("Universal Author Intake", "Universal Review", "Title Select")


def golden_form_rows():
    """The golden form rows, deep-copied so callers may mutate their copy
    without ever touching the canonical constant. One row per slug, each
    carrying the universal hidden-field contract — the exact shape the
    internal-rail listing serves for rows of type != "workflow"."""
    return [
        {"slug": "universal-intake", "name": "Universal Author Intake",
         "type": "form", "hiddenFields": ["contact_id", "anthology_id", "stage"]},
        {"slug": "universal-review", "name": "Universal Review",
         "type": "form", "hiddenFields": ["contact_id", "anthology_id", "stage"]},
        {"slug": "title-select", "name": "Title Select",
         "type": "form", "hiddenFields": ["contact_id", "anthology_id", "stage"]},
    ]


def golden_form_name_matches():
    """Rows that pass the name-match law without a slug key: the display form
    of the slug (a space where the slug has a dash) under 'name'. Same three
    rows, matched by name only — proves the match law, not the slug key."""
    return [
        {"name": "universal intake", "type": "form",
         "hiddenFields": ["contact_id", "anthology_id", "stage"]},
        {"name": "universal review", "type": "form",
         "hiddenFields": ["contact_id", "anthology_id", "stage"]},
        {"name": "title select", "type": "form",
         "hiddenFields": ["contact_id", "anthology_id", "stage"]},
    ]


def golden_rail_payload():
    """The full listing object the internal rail serves for the golden state:
    the three form rows on the same /workflow/{loc}/list shape both consumers
    read (rows of type != "workflow" ARE the forms; the count is len(rows))."""
    return {"rows": golden_form_rows()}


# ---------------------------------------------------------------------------
# Coherence gate — a drift in the golden payload itself must be caught by the
# self-tests that import it, never silently. This one check runs on import
# and REFUSES (raises) if the three named rows are not exactly what the
# contract expects. The constant below stays a plain tuple so no import-time
# failure ever depends on anthology_registry (a fixture must be importable in
# any process, credential-free).
# ---------------------------------------------------------------------------
_GOLDEN_SLUGS_TUPLE = tuple(GOLDEN_FORM_SLUGS)
_GOLDEN_NAMES_TUPLE = tuple(GOLDEN_FORM_NAMES)
_GOLDEN_HIDDEN_TUPLE = tuple(GOLDEN_UNIVERSAL_HIDDEN)


def validate_golden_forms() -> None:
    """Fail-closed coherence check over the canonical golden payload. Raises
    ValueError (never returns False) on drift, so a fixture corruption can
    never silently masquerade as a passing self-test.

    Asserts the invariant forms_check.py depends on: the three slugs, the
    three byte-exact display names in slug order, the three universal hidden
    fields on every row, and a row count of exactly three — no more, no less.
    """
    rows = golden_form_rows()
    if len(rows) != 3:
        raise ValueError("golden forms fixture must carry exactly 3 rows, got %d" % len(rows))
    if len(_GOLDEN_SLUGS_TUPLE) != 3 or len(_GOLDEN_NAMES_TUPLE) != 3:
        raise ValueError("golden slugs/names must each carry exactly 3 entries")
    if tuple(_GOLDEN_HIDDEN_TUPLE) != ("contact_id", "anthology_id", "stage"):
        raise ValueError("golden universal hidden fields drifted from the contract")
    for i, row in enumerate(rows):
        if not isinstance(row, dict):
            raise ValueError("golden row %d is not an object" % i)
        if row.get("slug") != _GOLDEN_SLUGS_TUPLE[i]:
            raise ValueError("golden row %d slug drifted: %r" % (i, row.get("slug")))
        if row.get("name") != _GOLDEN_NAMES_TUPLE[i]:
            raise ValueError("golden row %d name drifted: %r" % (i, row.get("name")))
        if tuple(row.get("hiddenFields") or ()) != _GOLDEN_HIDDEN_TUPLE:
            raise ValueError("golden row %d hidden fields drifted: %r"
                             % (i, row.get("hiddenFields")))


validate_golden_forms()


# ---------------------------------------------------------------------------
# Self-test — OFFLINE, no network, no secrets: the coherence gate above plus
# the mutation-proof guarantees the sibling self-tests rely on.
# ---------------------------------------------------------------------------
def self_test(out=None) -> int:
    """The module's own offline self-test. Returns 0 on a clean pass, 4 on a
    detected violation (the house self-test convention: a tamper NEVER
    masquerades as exit 1)."""
    import io
    import sys as _sys
    out = out or _sys.stderr
    dev = io.StringIO()
    try:
        _self_test_body(dev)
    except AssertionError as exc:
        out.write("[golden-forms] SELF-TEST FAILED: %s\n" % exc)
        return 4
    out.write(dev.getvalue())
    return 0


def _self_test_body(dev) -> None:
    # 1. the payload itself: three rows, contract-hidden fields, slug order
    rows = golden_form_rows()
    assert len(rows) == 3, "golden rows count must be 3"
    assert [r["slug"] for r in rows] == list(GOLDEN_FORM_SLUGS), \
        "golden slugs must keep contract order"
    for row in rows:
        assert row["hiddenFields"] == ["contact_id", "anthology_id", "stage"], \
            "every golden row must carry the universal hidden-field contract"
    # 2. the name-match law: display names resolve in slug order
    assert tuple(GOLDEN_FORM_NAMES) == ("Universal Author Intake", "Universal Review",
                                        "Title Select"), "golden display names drifted"
    for i, row in enumerate(golden_form_name_matches()):
        assert row["name"] == GOLDEN_FORM_SLUGS[i].replace("-", " "), \
            "name-match rows must be the slug with dashes -> spaces"
        assert row["hiddenFields"] == ["contact_id", "anthology_id", "stage"]
    # 3. the rail payload serves exactly the three rows
    payload = golden_rail_payload()
    assert isinstance(payload.get("rows"), list) and len(payload["rows"]) == 3
    # 4. mutation-proof: a caller's mutation never leaks back into the fixture
    mutated = golden_form_rows()
    mutated[0]["slug"] = "universal-intake-tampered"
    mutated[0]["hiddenFields"] = ["contact_id", "stage"]
    assert rows[0]["slug"] == "universal-intake", \
        "golden_form_rows must return fresh copies (mutation leaked)"
    assert rows[0]["hiddenFields"] == ["contact_id", "anthology_id", "stage"]
    # 5. the coherence gate refuses drift (never a silent pass). The module's
    #    own globals are patched and restored — the same seam drive_adapter.py's
    #    self-test uses — so this needs no package-name import and cannot touch
    #    any process that imported the fixture.
    _saved = globals().get("golden_form_rows")
    try:
        globals()["golden_form_rows"] = lambda: [
            {"slug": "universal-intake", "name": "Universal Author Intake",
             "type": "form", "hiddenFields": ["contact_id", "stage"]},
            {"slug": "universal-review", "name": "Universal Review",
             "type": "form", "hiddenFields": ["contact_id", "anthology_id", "stage"]},
            {"slug": "title-select", "name": "Title Select",
             "type": "form", "hiddenFields": ["contact_id", "anthology_id", "stage"]},
        ]
        refused = False
        try:
            validate_golden_forms()
        except ValueError:
            refused = True
        assert refused, "a drifted golden payload must be refused (fail-closed)"
    finally:
        if _saved is not None:
            globals()["golden_form_rows"] = _saved

    dev.write("golden_forms self-test: OK (three golden rows + display names + "
              "rail payload, universal hidden-field contract on every row, "
              "mutation-proof copies, drift-refusing coherence gate)\n")


if __name__ == "__main__":
    import sys as _s
    _s.exit(self_test())
