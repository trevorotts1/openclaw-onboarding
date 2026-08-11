#!/usr/bin/env python3
# =============================================================================
# SKILL 59 — ANTHOLOGY ENGINE :: u08_u09_modules/docs_forms.py
# U08/U09 FORMS-FAMILY TOOLING — THE MODULE DOCSTRING / README, SHIPPED AS AN
# IMPORTABLE MODULE (the u02_modules/docs_u02.py row-54-sibling pattern — the
# U08/U09 forms family ships under the ENGINE-MANIFEST.json row-54 "template
# live verify (U02)" shipping doctrine; the family's OWN manifest rows are
# NOT yet stamped: PENDING, staged exactly under the manifest-pending/u02.json
# · u03.json · u04.json · u05.json · u06.json pattern; current
# skill-version 0.1.23, 2026-08-11).
# -----------------------------------------------------------------------------
# WHERE THIS SITS: scripts/u08_u09_modules/ — the U08/U09 forms family's
# documentation module, sibling of the builders, the golden/attack fixtures,
# the hidden-field creator, the dropdown creator, and the pre-fill verifier
# it documents. It is NOT a manifest row: the family's drivers stay the
# gated builders and the module dispatchers under the delivery_report.py
# row-12 sibling-helper pattern, exactly as u02_modules/docs_u02.py documents
# the row-54 U02 verifier and u03_modules/docs_u03.py · u04_modules/docs_u04.py
# · u05_modules/docs_u05.py · u06_modules/docs_u06.py ·
# u07_modules/docs_u07.py document their siblings (the family's OWN manifest
# rows are PENDING — recorded below as None; a doc that claims a manifest row
# that does not exist is drift). Imported BY NAME as
# u08_u09_modules.docs_forms when a consumer wants the family's contract
# surfaces as DATA (the forms and their laws, the module inventory, the house
# exit codes, the doctrine) or its rendered README as text.
#
# WHAT THIS OWNS:
#   1. THE README. The module docstring below IS the U08/U09 forms-family
#      README: what the tooling verifies and builds, the forms and their
#      laws, the module inventory, the exit-code contract, the credential /
#      browser-UA / fail-closed doctrine. The same content is carried as
#      STRUCTURED DATA (FORMS, MODULES, EXIT_CODES, AF_CODES, DOCTRINE,
#      CREDENTIAL_LABELS) so a consumer can diff against it instead of
#      parsing prose — and readme() renders the README FROM that data, so
#      the two can never drift.
#   2. THE DRIFT GATE. self_test() proves the documentation still matches
#      the shipped tree: every module the README lists exists on disk next
#      to this module, every form law row is present exactly once, every
#      house exit code is documented, and the rendered README covers every
#      inventory row. A doc that names a module that does not ship FAILS
#      the self-test (exit 4, the house enforced-violation code) —
#      documentation is data, and stale documentation is drift.
#   3. PURE DATA, BY CONSTRUCTION. Nothing here reads an env var, opens a
#      file at import, touches the network, or holds a credential. A
#      documentation module cannot leak what it never holds. It performs NO
#      requests, so it defines NO User-Agent constant of its own: the
#      browser UA that defeats the Cloudflare edge (CF error 1010) is
#      CAF_BROWSER_UA, owned by anthology_registry.py and applied by its
#      clients (CafClient) — the docs record that doctrine, they do not
#      re-implement it. The form ids the docs mention are the family's
#      pinned LOCATION identifiers (the live-verified 2026-08-11 pins of
#      forms_check.py / form_reader.py / title_select_builder.py) — not
#      secrets, but reported BY MASKED MARKER on every surface, and the
#      self-test proves no form id VALUE rides the rendered README.
#
# THE TOOLING THIS DOCUMENTS (orientation):
#   MASTER-SPEC U08/U09 — the FORMS SURFACE LAW of the anthology engine: the
#   three named forms (universal-intake / universal-review / title-select),
#   their hidden-field laws, and the gated, read-back-proven builders that
#   normalize the live Convert and Flow forms to those laws. Every write is
#   Trevor-gated (--execute), every write is proven by a same-job read-back
#   (AF-AE-READBACK-MISMATCH family, exit 5, never a fabricated success),
#   and every request rides CAF_BROWSER_UA (the Cloudflare edge fronting
#   services.leadconnectorhq.com 403s urllib's default User-Agent, CF error
#   1010, before it ever reaches Convert and Flow).
#   1. THE THREE-FORM LAW (forms_check.py FORM_SLUGS — the SAME three
#      forms the U02 check asserts on every live read): universal-intake
#      (contract role universal-author-intake; the intake front door the
#      minted link rides, <forms_base>/widget/form/<id>?anthology_id=<minted>,
#      built by anthology_book.py), universal-review (the engine's ONE
#      client-facing decision form — PRD Section 4 / U8; a NAMED form,
#      deliberately NOT a snapshot-contract count row), and title-select
#      (contract role title-subtitle-selection, S3; the participant's
#      title-and-subtitle pick the one-way TITLE LOCK stamps).
#   2. THE HIDDEN-FIELD LAW (G3 + config/anthology-snapshot-contract.json
#      forms.universal_hidden_fields): the universal trio
#      contact_id / anthology_id / stage rides every required and
#      contract-bound form BYTE-EXACT; the minted intake query key is
#      EXACTLY "anthology_id", never "anthology_active_id" (the contact
#      custom field the delivery writer stamps is a DIFFERENT thing).
#      The review and title-select forms carry EXACTLY TWO hidden keys —
#      anthology_id and stage — because they are only ever opened from an
#      ALREADY-resolved participant token page (the contact_id hidden field
#      is deliberately ABSENT; a review submission must never ride the
#      intake front door — the U05 negative mirror).
#   3. THE DECISION AND COVER LAWS (PRD Section 4 / U8): the
#      universal-review decision field is a SINGLE_OPTIONS with EXACTLY TWO
#      options — "Approve as-is" / "Request rewrite with notes" — read from
#      gate_engine (GATE_BY_CURSOR["s5_gate"].actions, the chapter gate's
#      exactly-two-actions law), with a multi-line (LARGE_TEXT) notes
#      surface; the U8 cover dropdown offers the FOUR named cover styles
#      (cover_render.STYLE_NAMES — Signature / Bold Editorial / Fine Art /
#      Pure Type), the coherence law the registry self-test pins
#      (field-map.json cover_style_fields choice_options == STYLE_NAMES).
#   4. THE GATED WRITE LAW (--execute, the Trevor gate — u08_u09_modules/
#      __init__.py doctrine): EVERY form write in this family REFUSES
#      without the operator's explicit --execute (AF-AE-U08-U09-NO-EXECUTE,
#      exit 2 — never a silent write, never a silent no-op); without
#      --execute a builder is a read-only dry-run that prints exactly the
#      PUT it WOULD send; after the PUT the form is read back in the SAME
#      job and must prove the law byte-exact (AF-AE-READBACK-MISMATCH,
#      exit 5, never a reported success; an applied-but-unreadable PUT is
#      HELD, exit 3 — the live state is UNDETERMINED, never reported as
#      built). A PUT body is built ONLY from the live read-back row —
#      never from memory.
#   5. THE PRE-FILL LAW (U08 value-side): the LIVE universal author-intake
#      form pre-fills BOTH hidden fields from the minted link's TWO query
#      params (?anthology_id=<minted>&stage=<stage>); the pre-fill is
#      CLIENT-SIDE (the served form page is BYTE-IDENTICAL with and without
#      the probe params), so the honest live observation is a two-part
#      signature — the byte-identical page + the committed widget-build
#      artifact signature (config/prefill-verifier-baseline.json).
#   6. THE TARGET LAW (slug + pin): a row a builder may write MUST be
#      proven to be its form — the slug law (normalized name == the slug
#      with dashes -> spaces) or, when a pinned id is given, the pin law
#      (a pin BYPASSES the slug law; a pinned id absent from the listing
#      REFUSES the plan). A row that matches NEITHER law is never written.
#
# CREDENTIALS: BY LABEL, NEVER BY VALUE, everywhere in this tooling. The
# live surfaces resolve their credentials through the house labels (PIT
# first: CONVERT_AND_FLOW_PIT / CONVERT_AND_FLOW_API_KEY / GOHIGHLEVEL_API_KEY
# / GOHIGHLEVEL_PIT / GHL_API_KEY — live process env first, then the three
# canonical client env stores; SET / NOT SET only — a token value is NEVER
# printed). Before any JSON is emitted, every payload is scanned against
# the house credential shape (pit-<value>) and a hit REFUSES the whole
# surface rather than print it (the delta_reporter.py never-a-real-token
# doctrine). Form ids and the location id are MASKED to their last 4
# characters on every report — never printed in full; the full ids ride
# only inside request bodies and the machine-consumed JSON payloads.
#
# BROWSER UA (CF 1010 LAW): every request rides reg.CafClient, which applies
# CAF_BROWSER_UA on EVERY request — the Cloudflare edge fronting
# services.leadconnectorhq.com 403s urllib's default "Python-urllib/x.y"
# User-Agent at the WAF edge (CF error 1010) before the request ever reaches
# Convert and Flow (W0.6 / GK-09; the same browser UA the Podcast gate
# proved live). This documentation module makes NO network call and defines
# NO User-Agent constant of its own — the self-test PINS the browser-UA
# doctrine constant byte-equal to reg.CAF_BROWSER_UA so a registry
# regression is caught HERE first. Scope-vs-edge-block discrimination: a
# bare 401/403 is HELD (UpstreamBlockedError / CafUnreachable, exit 3),
# never mislabeled as a scope problem; a genuine scope denial is a STOP
# (exit 2).
#
# FAIL-CLOSED (the whole point): a missing credential STOPS (exit 2), a
# non-pit- token is refused, an unreadable listing / a listing with NO form
# row / a pinned id the listing lacks is a FAIL (exit 5, never a fabricated
# pass, never an id guessed from memory), a transport / edge failure is
# HELD (exit 3, UNDETERMINED — never a verdict), a write NEVER happens
# without the operator's --execute (exit 2, AF-AE-U08-U09-NO-EXECUTE) and
# every write must read back byte-for-byte (exit 5,
# AF-AE-READBACK-MISMATCH), a credential-shaped string on any surface
# REFUSES the whole surface rather than print it, and a drifted authority
# (form_reader / forms_check / anthology_book / gate_engine / cover_render /
# the snapshot contract) breaks the family's self-tests FIRST (exit 4 — a
# tamper never masquerades as exit 1). A success is claimed ONLY when the
# live form carries the law byte-exact. Every deviation is NAMED with its
# code — never a bare "something failed".
#
# DOCTRINE (house, per anthology_registry.py / drive_adapter.py): move in
# silence (operator-verbose only); NOTHING Anthropic in any runtime file;
# Convert and Flow naming in every client surface; STDLIB ONLY; calls NO
# model; never a client PII; a law is read once, in one module (the
# delta_reporter.py single-implementation doctrine — form_reader owns the
# public v2 forms listing read and the slug/pin laws, hidden_field_module
# owns the ONE form WRITE path and the hidden container-key normalization,
# forms_check / form_reader / anthology_book own the form pins, gate_engine
# owns the decision vocabulary, cover_render owns the style names, and the
# builders derive from them, never re-implement). READ-ONLY by doctrine —
# this documentation module never writes; the builders are the family's
# gated write surfaces (their OWN --execute, the dispatchers never write).
# Self-test failures are exit 4 (enforced violation — the AF-AE-* families
# below), never exit 1.
#
# USAGE (this module's own machine surface — pure data, nothing to leak):
#   python3 docs_forms.py                ONE JSON catalog of the whole tooling
#   python3 docs_forms.py readme         the rendered README (markdown text)
#   python3 docs_forms.py self-test      OFFLINE drift gate over the docs vs
#                                        the shipped tree; 0 clean, 4 drift
# =============================================================================
"""docs_forms.py -- README / module docstring for the U08/U09 forms-family
tooling, as an importable fail-closed pure-data module: the three named
forms (universal-intake / universal-review / title-select), their
hidden-field / decision / cover laws, the gated builders (hidden-field
creator, dropdown creator, title-select builder, universal-review builder),
the golden and attack fixtures, the pre-fill verifier, the family's module
inventory, the house exit codes, and the credential / browser-UA / doctrine
contracts — shipped under the ENGINE-MANIFEST.json row-54 "template live
verify (U02)" doctrine (the family's OWN manifest rows PENDING). Performs
no I/O at import and holds no credential; readme() is rendered from the
same structured data the self-test asserts against, so documentation and
data cannot drift."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# The fixed report contract (mirrors the golden-fixture naming discipline).
# ---------------------------------------------------------------------------
DOC_CONTRACT = "anthology-engine-u08-u09-forms-docs"
SCHEMA_VERSION = 1

# The U08/U09 forms family's drivers are the gated builders and the module
# dispatchers under the U02 row-54 shipping law; the u08_u09_modules/
# siblings ship as non-manifest helpers (the delivery_report.py row-12
# pattern, exactly the docs_u02.py / docs_u03.py / docs_u04.py / docs_u05.py
# / docs_u06.py / docs_u07.py siblings). The family's OWN manifest rows are
# NOT yet stamped in ENGINE-MANIFEST.json (verified at ship time,
# 2026-08-11): they are PENDING, staged under the manifest-pending/u02.json
# · u03.json · u04.json · u05.json · u06.json pattern — this module records
# None rather than invent row numbers (a doc that claims rows that do not
# exist is drift).
U08_U09_VERIFIER = None  # PENDING — the family's single driver is not yet named
U08_U09_MANIFEST_ROW = None  # PENDING — the family is not yet stamped
U08_U09_SHIPPING_VERSION = "v0.1.23 (2026-08-11)"  # skill-version at ship time

# ---------------------------------------------------------------------------
# THE FORMS AND THEIR LAWS — the family's contract surface, in the FIXED
# order forms_check.py FORM_SLUGS carries (the three named forms the U02
# check asserts on every live read). Each row is the family's law for ONE
# form: the contract role, the hidden-field law, the decision/cover surface,
# the pinned form id BY MASKED MARKER only (the full id VALUE is a location
# identifier, never a secret, but it NEVER rides this documentation surface —
# the self-test proves no id value is rendered anywhere), the build surfaces
# that own it, and the fail-closed claim. Form numbers are load-bearing
# (positions 1..3, exactly three — self-test pins the count).
# ---------------------------------------------------------------------------
FORMS = (
    {
        "form": 1,
        "slug": "universal-intake",
        "role": "universal-author-intake",
        "hidden_fields": ["contact_id", "anthology_id", "stage"],
        "surface": ("the intake front door — the minted link "
                    "<forms_base>/widget/form/<form_id>?anthology_id=<minted> "
                    "built by anthology_book.py (INTAKE_QUERY_KEY; the query "
                    "key is EXACTLY 'anthology_id', never "
                    "'anthology_active_id' — G3); EVERY submission carries "
                    "the minted Book ID plus its stage"),
        "law": ("the universal hidden-field contract "
                "(config/anthology-snapshot-contract.json "
                "forms.universal_hidden_fields) byte-exact on the required "
                "row; the pre-fill law (U08 value-side): BOTH hidden fields "
                "pre-fill from the minted link's TWO query params "
                "(?anthology_id=<minted>&stage=<stage>), client-side, "
                "proven by the byte-identical page + the committed "
                "widget-build signature"),
        "builders": ("hidden_field_module.py (the ONE form WRITE path, "
                     "FORMS_WRITE_PATH = '/forms/%s' — hidden-field create, "
                     "Trevor-gated) + prefill_verifier.py (live value-side "
                     "verify, --execute required, no write)"),
        "id_marker": "...lKWG",
        "fails": "AF-AE-U08-U09-NO-EXECUTE (exit 2) — a hidden-field write "
                 "without --execute; READBACK-MISMATCH (exit 5) — a PUT "
                 "whose read-back does not prove the trio; AF-AE-PREFILL-* "
                 "(exit 5/2/3) — a drifted page or widget-build signature, "
                 "a missing baseline, --execute withheld for the live verify",
    },
    {
        "form": 2,
        "slug": "universal-review",
        "role": "<named form, no count row>",
        "hidden_fields": ["anthology_id", "stage"],
        "surface": ("the engine's ONE client-facing decision form (PRD "
                    "Section 4 / U8) — a NAMED form, deliberately NOT a "
                    "snapshot-contract count row (forms_check.py); only "
                    "ever opened from an ALREADY-resolved participant token "
                    "page, so the contact_id hidden field is ABSENT by "
                    "contract (a review submission must never ride the "
                    "intake front door — the U05 negative mirror)"),
        "law": ("EXACTLY TWO hidden fields (anthology_id, stage) — the "
                "release links pre-key them; the decision field is a "
                "SINGLE_OPTIONS with EXACTLY TWO options, 'Approve as-is' / "
                "'Request rewrite with notes' (gate_engine "
                "GATE_BY_CURSOR['s5_gate'].actions, read once, never "
                "re-implemented) plus a multi-line (LARGE_TEXT) notes "
                "surface; the U8 cover dropdown offers the FOUR named cover "
                "styles (cover_render.STYLE_NAMES — Signature / Bold "
                "Editorial / Fine Art / Pure Type)"),
        "builders": ("universal_review_builder.py (gated PUT /forms/{id}, "
                     "dry-run without --execute, same-job read-back) + "
                     "dropdown_module.py (the TWO SINGLE_OPTIONS picklists, "
                     "create-only-missing, Trevor-gated)"),
        "id_marker": "...Lqq0",
        "fails": "AF-AE-U08-U09-NO-EXECUTE (exit 2) — a build without "
                 "--execute; READBACK-MISMATCH (exit 5) — the read-back "
                 "does not prove the two hidden keys / two decision options "
                 "/ four cover options; FORMS-EMPTY / FORMS-NOT-FOUND "
                 "(exit 5) — the review row is absent",
    },
    {
        "form": 3,
        "slug": "title-select",
        "role": "title-subtitle-selection",
        "hidden_fields": ["anthology_id", "stage"],
        "surface": ("the S3 title-and-subtitle selection form — the "
                    "participant's pick on the token page, stamped by the "
                    "one-way TITLE LOCK (title_locked / subtitle_locked, "
                    "MASTERDOC floor 4); only ever opened from an "
                    "ALREADY-resolved participant token page, so the "
                    "hidden pair is exactly TWO, never the intake trio"),
        "law": ("EXACTLY TWO hidden fields (anthology_id, stage) in the "
                "contract's own universal order + TWO visible multi-line "
                "REQUIRED fields (title, subtitle — LARGE_TEXT, the "
                "anthology free-text law of provision_fields, PRD Gap G11; "
                "a blank pick is a lock on nothing, never permitted)"),
        "builders": ("title_select_builder.py (gated PUT /forms/{id}, "
                     "dry-run without --execute, same-job read-back)"),
        "id_marker": "...O5fi",
        "fails": "AF-AE-U08-U09-NO-EXECUTE (exit 2) — a build without "
                 "--execute; READBACK-MISMATCH (exit 5) — the read-back "
                 "does not prove the routing pair / the visible pair; "
                 "FORMS-EMPTY / FORMS-NOT-FOUND (exit 5) — the "
                 "title-select row is absent",
    },
)

# ---------------------------------------------------------------------------
# THE MODULE INVENTORY. `place` names the directory relative to this module
# (the u08_u09_modules package itself); self-test proves each name exists at
# that place. `role` is the one-line contract each module owns; `offline`
# names the credential-free surface; `exit_codes` follows the house
# convention (0/1/2/3/5, 4 = self-test).
# ---------------------------------------------------------------------------
MODULES = (
    {
        "name": "__init__.py",
        "place": "scripts/u08_u09_modules/",
        "manifest_row": None,
        "role": ("fail-closed EMPTY package init — pure namespace "
                 "container, no runtime code; modules are imported BY "
                 "NAME; records the package doctrine (fail-closed, secrets "
                 "by label, browser-UA law for every GoHighLevel / Convert "
                 "and Flow surface, move in silence; destructive actions "
                 "require --execute)"),
        "offline": "trivially — it is empty",
        "exit_codes": "n/a (no executable surface)",
    },
    {
        "name": "form_spec_loader.py",
        "place": "scripts/u08_u09_modules/",
        "manifest_row": None,
        "role": ("the FAIL-CLOSED THREE-FORM SPEC LOADER — the single "
                 "implementation of the 3-form spec load-and-verify law: "
                 "read config/anthology-snapshot-contract.json and return "
                 "its forms block ONLY when the spec satisfies its own "
                 "contract (the three named forms, the universal "
                 "hidden-field law contact_id / anthology_id / stage "
                 "byte-exact, the pinned form ids, the role law); "
                 "OFFLINE and READ-ONLY — no network, no token, no env "
                 "store; form ids by masked marker only; the --execute "
                 "gate is pinned as the law a creating sibling must "
                 "receive (a creating sibling REFUSES without it, exit 2)"),
        "offline": "entirely — pure loader, no network, no credentials",
        "exit_codes": "0/1/2/4",
    },
    {
        "name": "hidden_field_module.py",
        "place": "scripts/u08_u09_modules/",
        "manifest_row": None,
        "role": ("the HIDDEN-FIELD CREATOR — creates a hidden field on the "
                 "universal author-intake form so EVERY submission carries "
                 "the minted Book ID plus its stage; the ONE form WRITE "
                 "path of the family (public v2 PUT /forms/{id}, Version "
                 "2021-07-28 — FORMS_WRITE_PATH = '/forms/%s'); REFUSES to "
                 "write unless the operator passes --execute (Trevor-gated); "
                 "without --execute a read-only DRY-RUN printing exactly "
                 "the PUT it WOULD send; the PUT body is built ONLY from "
                 "the live read-back row; after the PUT the form is read "
                 "back in the SAME job and must prove the trio byte-exact "
                 "(AF-AE-READBACK-MISMATCH, exit 5)"),
        "offline": "plan + self-test (no token, no network); apply (dry-run "
                   "included) needs the location's OWN PIT BY LABEL — a "
                   "truthful plan requires the live read",
        "exit_codes": "0/1/2/3/4/5",
    },
    {
        "name": "dropdown_module.py",
        "place": "scripts/u08_u09_modules/",
        "manifest_row": None,
        "role": ("the DROPDOWN CREATOR — the TWO SINGLE_OPTIONS picklist "
                 "fields the client-facing review surface ships: the PRD "
                 "Section 4 decision field (EXACTLY TWO options, "
                 "'Approve as-is' / 'Request rewrite with notes' — read "
                 "from gate_engine GATE_BY_CURSOR['s5_gate'].actions, "
                 "never re-implemented) and the U8 cover-style choice "
                 "field (the FOUR named cover styles, read from "
                 "cover_render.STYLE_NAMES; the coherence law the registry "
                 "self-test pins: field-map choice_options == STYLE_NAMES); "
                 "CREATE-ONLY-MISSING and Trevor-gated — creation REFUSES "
                 "without --execute, every other invocation is a read-only "
                 "plan"),
        "offline": "plan + self-test (no token, no network); apply needs the "
                   "location's OWN PIT BY LABEL",
        "exit_codes": "0/1/2/3/4/5",
    },
    {
        "name": "title_select_builder.py",
        "place": "scripts/u08_u09_modules/",
        "manifest_row": None,
        "role": ("the TITLE-SELECT BUILDER — normalizes the S3 form (slug "
                 "title-select; role title-subtitle-selection) to its law "
                 "via public v2 PUT /forms/{id}: the two routing hidden "
                 "fields (anthology_id, stage — EXACTLY two, never the "
                 "intake trio) and the two visible multi-line REQUIRED "
                 "fields (title, subtitle) the one-way TITLE LOCK stamps; "
                 "REFUSES to write without --execute; the read-back in the "
                 "SAME job must prove the shape byte-exact "
                 "(AF-AE-READBACK-MISMATCH, exit 5); the target law: slug "
                 "match or pinned id, never a write to an unproven row"),
        "offline": "plan + self-test (no token, no network); apply (dry-run "
                   "included) needs the location's OWN PIT BY LABEL",
        "exit_codes": "0/1/2/3/4/5",
    },
    {
        "name": "universal_review_builder.py",
        "place": "scripts/u08_u09_modules/",
        "manifest_row": None,
        "role": ("the UNIVERSAL-REVIEW BUILDER — normalizes the engine's "
                 "ONE client-facing decision form to its law via public v2 "
                 "PUT /forms/{id}: the two hidden fields (anthology_id, "
                 "stage — the contact_id hidden field is ABSENT by "
                 "contract), the two-option decision dropdown, the "
                 "multi-line notes surface, and the four-option cover "
                 "dropdown; REFUSES to write without --execute; the "
                 "read-back in the SAME job must prove the contract "
                 "byte-exact (AF-AE-READBACK-MISMATCH, exit 5); a PUT that "
                 "returned success but cannot be read back is HELD (exit "
                 "3) — the live state is UNDETERMINED, never reported as "
                 "built"),
        "offline": "plan + self-test (no token, no network); apply (dry-run "
                   "included) needs the location's OWN PIT BY LABEL",
        "exit_codes": "0/1/2/3/4/5",
    },
    {
        "name": "golden_review.py",
        "place": "scripts/u08_u09_modules/",
        "manifest_row": None,
        "role": ("the GOLDEN UNIVERSAL-REVIEW FIXTURE — the canonical "
                 "in-memory payload of the universal-review decision "
                 "submission in its does-not-fire state (a submission the "
                 "negative mirror must CERTIFY does-not-fire -> PASS, by "
                 "construction); the golden control of the family's "
                 "offline self-tests — MappingProxyType-frozen canon, "
                 "deep-copied payload surfaces, SYNTHETIC ids only "
                 "(A-9001 / C-9001 / LOC-synthetic-RVW); payload() REFUSES "
                 "any drift (exit 5)"),
        "offline": "entirely — pure data + builders (synthetic ids only)",
        "exit_codes": "0/1/4/5",
    },
    {
        "name": "golden_title.py",
        "place": "scripts/u08_u09_modules/",
        "manifest_row": None,
        "role": ("the GOLDEN TITLE-SELECT FIXTURE — the canonical in-memory "
                 "payload of the S3 title selection in its GOLDEN state: "
                 "the byte-exact locked pair (title, subtitle) with the "
                 "one-way TITLE LOCK law stamped, the composite "
                 "participant key under the KEYING LAW, carried on both "
                 "doors; the golden control of the title-select gate and "
                 "the anti-attack mirror of attack_missing_hidden; "
                 "SYNTHETIC ids only; payload() REFUSES any deviation "
                 "(exit 5)"),
        "offline": "entirely — pure data + builders (synthetic ids only)",
        "exit_codes": "0/1/4/5",
    },
    {
        "name": "attack_missing_hidden.py",
        "place": "scripts/u08_u09_modules/",
        "manifest_row": None,
        "role": ("the ATTACK FIXTURE — HIDDEN FIELD MISSING, MUST FAIL: a "
                 "form that carries the universal hidden-field contract "
                 "with ONE of the THREE contract keys dropped (the strict "
                 "subset that must never pass); the attack is "
                 "deterministic and single-variable — the canonical "
                 "container is built from the snapshot contract's "
                 "universal_hidden_fields (the single authority), the drop "
                 "is by POSITION (the last key), never a magic literal; "
                 "the --execute gate applies fail-closed in BOTH "
                 "directions (the payload is REFUSED without --execute; "
                 "verify carries execute_required: True)"),
        "offline": "plan + self-test (no network, no token surface)",
        "exit_codes": "0/1/2/4/5",
    },
    {
        "name": "prefill_verifier.py",
        "place": "scripts/u08_u09_modules/",
        "manifest_row": None,
        "role": ("the INTAKE PRE-FILL VERIFIER — the U08 value-side gate: "
                 "proves the LIVE universal author-intake form pre-fills "
                 "BOTH hidden fields from the minted link's TWO query "
                 "params (?anthology_id=<minted>&stage=<stage>); the "
                 "pre-fill is client-side (the served page is "
                 "BYTE-IDENTICAL with and without the probe params), so "
                 "the honest observation is the two-part signature — the "
                 "byte-identical page + the committed widget-build artifact "
                 "signature (config/prefill-verifier-baseline.json); a "
                 "page that bakes the probe into the served bytes, a "
                 "drifted artifact signature, or an absent hydration code "
                 "is a MISMATCH (exit 5); --execute REQUIRED for the live "
                 "verify (AF-AE-PREFILL-EXECUTE, exit 2); an optional "
                 "headless-Chromium render observes the rendered values "
                 "when the runtime is present, SKIPPED-as-undetermined "
                 "when absent (never fabricated); CREDENTIAL-FREE — the "
                 "hosted form and the widget build are PUBLIC surfaces"),
        "offline": "plan + self-test (no token, no network); live needs "
                   "--execute but NO credential (public hosted-form "
                   "surface)",
        "exit_codes": "0/1/2/3/4/5",
    },
    {
        "name": "attack_bad_dropdown.py",
        "place": "scripts/u08_u09_modules/",
        "manifest_row": None,
        "role": ("the ATTACK FIXTURE — DECISION-DROPDOWN WRONG OPTION, "
                 "MUST FAIL: the one-option-wrong picklist of the "
                 "universal-review decision field — the FIRST of the two "
                 "gate actions byte-swapped to the repo's OWN documented "
                 "drifted spelling (approved_as_is, pinned byte-exact "
                 "against golden_review.GOLDEN_DECISION and proven NOT in "
                 "the two gate actions) — that every byte-exact picklist "
                 "gate must never pass; the attack is deterministic and "
                 "single-variable, the law read once from "
                 "dropdown_module (itself byte-derived from gate_engine); "
                 "verify_options FAILs the wrong-option read (exit 5, "
                 "wrong option and expected option named) while the true "
                 "two-option golden control PASSES exit 0; reordered / "
                 "extra / dropped / duplicated / blank reads FAIL with "
                 "named defects; the --execute gate applies fail-closed in "
                 "BOTH directions (payload / payload-true are REFUSED "
                 "without --execute)"),
        "offline": "plan + self-test (no network, no token surface)",
        "exit_codes": "0/1/4/5",
    },
    {
        "name": "docs_forms.py",
        "place": "scripts/u08_u09_modules/",
        "manifest_row": None,
        "role": ("THIS module — the family's README / documentation as an "
                 "importable fail-closed pure-data module: the three named "
                 "forms and their laws, the module inventory, the house "
                 "exit codes, the AF family, the doctrine, and the "
                 "credential labels; readme() renders FROM the same data "
                 "the self-test asserts against, so documentation and "
                 "data cannot drift; performs no I/O at import and holds "
                 "no credential"),
        "offline": "entirely — pure data; self-test is a read-only "
                   "filesystem drift gate",
        "exit_codes": "0/1/4",
    },
)

# ---------------------------------------------------------------------------
# HOUSE EXIT CODES (0/1/2/3/5; 4 = enforced violation). The exact contract
# the U08/U09 forms family commits to; self-test pins all six.
# ---------------------------------------------------------------------------
EXIT_CODES = {
    0: "verified success — the live form carries its law byte-exact (also "
       "plan / dry-run / self-test / a documented PASS)",
    1: "unexpected error (top-level guard; never a secret leak)",
    2: ("STOP refusal — label NOT SET / non-pit- value / usage / the "
        "--execute gate withheld (AF-AE-U08-U09-NO-EXECUTE: an ACTION "
        "without the gate is a refusal, never a silent write) / the "
        "pre-fill live verify without --execute (AF-AE-PREFILL-EXECUTE) / "
        "an unreadable listing shape / a genuine location-scope denial"),
    3: ("HELD — Convert and Flow unreachable / Cloudflare edge block "
        "(CF error 1010) / an applied-but-unreadable PUT (the live state "
        "is UNDETERMINED, never reported as built) / a pre-fill fetch or "
        "render that cannot complete"),
    4: ("self-test FAILED (the AF-AE-* enforced-violation family — a "
        "tamper never masquerades as exit 1)"),
    5: ("mismatch / fail-closed default — a form row absent (FORMS-EMPTY / "
        "FORMS-NOT-FOUND), a pinned id absent from the listing, a "
        "byte-drifted hidden-field law (including a strict subset), a "
        "drifted decision or cover option set, a pre-fill page that is "
        "not byte-identical or a drifted widget-build signature "
        "(AF-AE-PREFILL-*), a read-back that does not prove the build "
        "(AF-AE-READBACK-MISMATCH), or a fixture payload that drifted"),
}

# ---------------------------------------------------------------------------
# THE AF AUTOfail FAMILY of the U08/U09 forms tooling — the codes the
# family's own surfaces declare. The family's own manifest rows are NOT yet
# stamped in ENGINE-MANIFEST.json (PENDING — verified at ship time,
# 2026-08-11); AF-AE-READBACK-MISMATCH and AF-AE-TEMPLATE-ATTACK already
# live in the manifest. Self-test failures are exit 4, never 1.
# ---------------------------------------------------------------------------
AF_CODES = (
    ("AF-AE-U08-U09-NO-EXECUTE", 2,
     "an ACTION (a form create / build / write) was requested without the "
     "operator's explicit --execute (the Trevor gate, u08_u09_modules/"
     "__init__.py doctrine) — a refusal, never a silent no-op and never a "
     "silent write (not yet stamped in ENGINE-MANIFEST.json)"),
    ("AF-AE-READBACK-MISMATCH", 5,
     "a PUT returned success but the read-back in the SAME job does not "
     "prove the build byte-exact — never reported as built (the house "
     "code, already stamped in ENGINE-MANIFEST.json)"),
    ("AF-AE-PREFILL-EXECUTE", 2,
     "the pre-fill live verify was requested without --execute — an "
     "operator-gated live action in this package (background or accidental "
     "invocations must never even probe the live surface)"),
    ("AF-AE-PREFILL-BASELINE-UNREADABLE", 2,
     "the committed pre-fill widget-build baseline "
     "(config/prefill-verifier-baseline.json) is missing or unreadable — "
     "a check that cannot see its law never fabricates a pass"),
    ("AF-AE-PREFILL-BASELINE-MALFORMED", 2,
     "the committed pre-fill baseline is malformed (not a JSON object / "
     "drifted structure) — the hydration law became unverifiable, never a "
     "silent pass"),
    ("AF-AE-PREFILL-RENDER", 5,
     "a headless-Chromium render observed a probe value rendered non-exact "
     "or onto the wrong field, or a prefill rendered with its param "
     "absent — the rendered hidden-field values must be exact (the render "
     "is OPTIONAL — absent runtime is SKIPPED-as-undetermined, never "
     "fabricated)"),
    ("AF-AE-TEMPLATE-ATTACK", 4,
     "an attack fixture tripped the OFFLINE self-test of a family module "
     "or battery (enforced violation — the house code, shared with the "
     "U02 / U03 / U04 / U05 / U06 / U07 families)"),
)

# ---------------------------------------------------------------------------
# DOCTRINE — the house rules the whole U08/U09 forms tooling commits to, as
# data so the README renders them from the same source the self-test
# asserts.
# ---------------------------------------------------------------------------
DOCTRINE = (
    ("Fail-closed", "a missing credential, a malformed input, an "
     "unreadable source, or a live read that cannot be completed is a "
     "REFUSAL or a recorded FAIL — never a blind pass, never a fabricated "
     "success; a strict subset of a hidden-field law is a MISSING, never a "
     "pass; a listing with no form row is a FAIL, never a silent empty; an "
     "id is NEVER guessed from memory"),
    ("Secrets", "credentials resolve BY LABEL only (SET / NOT SET); a "
     "token value is never printed, echoed, or reflected in any surface; "
     "before any JSON is emitted the payload is scanned against the house "
     "credential shape (pit-<value>) and a hit REFUSES the whole surface "
     "(the delta_reporter.py never-a-real-token doctrine); form ids and "
     "the location id are MASKED to their last 4 characters in every "
     "report"),
    ("Browser UA", "every request to GoHighLevel / Convert and Flow "
     "(services.leadconnectorhq.com) rides reg.CafClient, which applies "
     "CAF_BROWSER_UA on EVERY request — urllib's default "
     "'Python-urllib/x.y' is 403'd at the WAF edge (CF error 1010) before "
     "it ever reaches the API (W0.6 / GK-09); the fixtures and this "
     "documentation module make NO network call, so they define NO "
     "User-Agent constant of their own — the self-tests PIN the constant "
     "byte-equal to reg.CAF_BROWSER_UA so a registry regression is caught "
     "HERE first"),
    ("Scope vs edge", "a bare 401/403 is HELD (UpstreamBlockedError / "
     "CafUnreachable, exit 3), never mislabeled as a scope problem; a "
     "genuine location-scope denial is a STOP (exit 2)"),
    ("Synthetic ids only", "the fixtures carry SYNTHETIC deterministic "
     "ids only (A-9001 / C-9001 / LOC-synthetic-RVW / cnt_golden / "
     "anth_golden — the synthetic-id discipline of the u02/u03/u04/u05/"
     "u06/u07 golden siblings) — a fixture id is never a real "
     "participant, form, location, or anthology id, and never a real "
     "token"),
    ("Single authority", "a law is read once, in one module: "
     "form_reader owns the public v2 forms listing read and the slug/pin "
     "laws, hidden_field_module owns the ONE form WRITE path "
     "(FORMS_WRITE_PATH) and the hidden container-key normalization, "
     "forms_check / form_reader / anthology_book own the form pins, "
     "gate_engine owns the decision vocabulary "
     "(GATE_BY_CURSOR['s5_gate'].actions), cover_render owns the style "
     "names (STYLE_NAMES), the snapshot contract owns the universal "
     "hidden-field law, and the builders derive from them, never "
     "re-implement; a drift in an authority breaks the family's "
     "self-tests FIRST"),
    ("Gated writes", "--execute is the ONLY flag that performs a form "
     "PUT (each builder's OWN CLI, Trevor-gated); every other invocation "
     "is a read-only dry-run that prints exactly the PUT it WOULD send; "
     "the POST-PUT read-back must prove the build byte-for-byte "
     "(AF-AE-READBACK-MISMATCH, exit 5); an applied-but-unreadable PUT is "
     "HELD (exit 3) — the live state is UNDETERMINED, never reported as "
     "built; the PUT body is built ONLY from the live read-back row, "
     "never from memory"),
    ("Move in silence", "operator-verbose only; NOTHING Anthropic in any "
     "runtime file; Convert and Flow naming in every client surface; "
     "STDLIB ONLY; calls NO model; never a client PII; READ-ONLY by "
     "doctrine — the fixtures and the docs never write; the builders are "
     "the family's gated write surfaces"),
)

# ---------------------------------------------------------------------------
# CREDENTIAL LABELS — BY LABEL ONLY. These are the label NAMES the live
# surfaces resolve through anthology_registry (live process env first, then
# the three canonical client env stores). A label is a name, never a value;
# the values they resolve to are never held here and never printed anywhere.
# The fixtures and this documentation module hold NO credential surface at
# all; the family's live surfaces (the builders' apply, the hidden-field
# creator, the dropdown creator) resolve their credentials through the house
# PIT labels below.
# ---------------------------------------------------------------------------
CREDENTIAL_LABELS = {
    "pit": (
        "CONVERT_AND_FLOW_PIT",
        "CONVERT_AND_FLOW_API_KEY",
        "GOHIGHLEVEL_API_KEY",
        "GOHIGHLEVEL_PIT",
        "GHL_API_KEY",
    ),
}

# The pinned form-id VALUES of the three named forms — location identifiers,
# never secrets, but they NEVER ride this documentation surface: the FORMS
# rows above carry masked markers only, and the self-test proves no id
# value is rendered anywhere (the same masked-marker policy the U06/U07
# modules enforce). Recorded here so the self-test can assert the markers
# really are the last-4 markers of the family's live-verified pins
# (forms_check.py FORM_ID_BY_SLUG — the SAME pins form_spec_loader.py and
# title_select_builder.py ship against).
PINNED_FORM_IDS = {
    "universal-intake": "U65pwoeMTy1niMqllKWG",
    "universal-review": "riNlAkYbcW3g92VRLqq0",
    "title-select": "UgiiSoZsA4vyqOVfO5fi",
}

# Pinned counts (the fixture-counting discipline of golden_fields.py: a
# drifted inventory is drift, never tolerated). Adding a module to the
# U08/U09 forms tooling REQUIRES adding it here AND to the README's
# inventory.
CONTRACT_FORM_COUNT = 3
CONTRACT_MODULE_COUNT = 12

class DocsError(Exception):
    """A fail-closed documentation refusal: the README data drifted from
    its own contract, so no catalog is shipped — wrong docs are worse than
    no docs."""

# ---------------------------------------------------------------------------
# Accessors — deep copies, so callers can never mutate the canonical data.
# ---------------------------------------------------------------------------
def forms() -> list:
    """The three form-law rows as a mutable deep copy (callers may mutate
    their copy; the canonical tuple is never touched)."""
    return [dict(row) for row in FORMS]

def modules() -> list:
    """The module inventory as a mutable deep copy."""
    return [dict(row) for row in MODULES]

def exit_codes() -> dict:
    """The house exit-code contract as a plain dict copy."""
    return dict(EXIT_CODES)

def af_codes() -> list:
    """The AF autofail family as plain (code, exit, meaning) tuples in a
    mutable list."""
    return list(AF_CODES)

# ---------------------------------------------------------------------------
# The rendered README — built FROM the data, so prose can never drift from
# the contract. This is the machine-readable form of the module docstring.
# ---------------------------------------------------------------------------
def readme() -> str:
    """The U08/U09 forms-family README, rendered from the structured data
    above.

    One markdown document: what the tooling is, the three named forms and
    their laws, the module inventory, the house exit codes, the autofail
    family, the doctrine, and the credential labels. Because every section
    renders from the same constants the self-test asserts, a drift in the
    data FAILS the self-test before it can ship a stale README. Form ids
    ride the rendered README BY MASKED MARKER only — the id VALUE never
    surfaces (proven by the self-test)."""
    lines = [
        "# U08/U09 forms-family tooling — the three named forms and their "
        "gated builders (README)",
        "",
        "Shipped under the ENGINE-MANIFEST.json row-54 \"template live "
        "verify (U02)\" shipping doctrine (%s; the family's OWN manifest "
        "rows are PENDING — not yet stamped, staged under the "
        "manifest-pending/u02.json · u03.json · u04.json · u05.json · "
        "u06.json pattern) — the gated builders stay the family's "
        "drivers (the delivery_report.py row-12 sibling-helper pattern) "
        "plus the importable hidden-field creator, the dropdown creator, "
        "the golden and attack fixtures, the pre-fill verifier, and this "
        "documentation module in `scripts/u08_u09_modules/` — documented "
        "machine-side by this module (`u08_u09_modules.docs_forms`)."
        % U08_U09_SHIPPING_VERSION,
        "",
        "The family gates the FORMS SURFACE LAW of the anthology engine: "
        "the three named forms (universal-intake / universal-review / "
        "title-select), their hidden-field / decision / cover laws, and "
        "the gated, read-back-proven builders that normalize the live "
        "Convert and Flow forms to those laws. Every write is Trevor-gated "
        "(--execute — REFUSED without it, AF-AE-U08-U09-NO-EXECUTE, exit "
        "2), every write is proven by a same-job read-back "
        "(AF-AE-READBACK-MISMATCH, exit 5, never a fabricated success), "
        "and every request rides CAF_BROWSER_UA (the Cloudflare edge "
        "fronting services.leadconnectorhq.com 403s urllib's default "
        "User-Agent, CF error 1010, before it ever reaches Convert and "
        "Flow). The family's live surfaces run only from a session that "
        "can resolve the location's OWN private-integration token BY "
        "LABEL (PIT first, then the canonical client env stores); "
        "`plan` / `dry-run` and `self-test` are OFFLINE (no token, no "
        "network), and the pre-fill live verify is CREDENTIAL-FREE (the "
        "hosted form and the widget build are PUBLIC surfaces — but still "
        "--execute-gated). The fixtures carry SYNTHETIC ids only (A-9001 "
        "/ C-9001 / LOC-synthetic-RVW / cnt_golden / anth_golden — never "
        "a live id); every report masks form / location ids to their "
        "last 4 characters and never prints a token.",
        "",
        "## The three named forms and their laws (MASTER-SPEC U08/U09 — "
        "the family's contract surface, in the FIXED order forms_check.py "
        "FORM_SLUGS carries)",
        "",
    ]
    for row in FORMS:
        lines.append("%d. **%s** (contract role %s) — hidden fields: %s. "
                     "Pinned id marker: %s. Surface: %s. Law: %s. "
                     "Builders: %s. Fails: %s."
                     % (row["form"], row["slug"], row["role"],
                        ", ".join(row["hidden_fields"]), row["id_marker"],
                        row["surface"], row["law"], row["builders"],
                        row["fails"]))
        lines.append("")
    lines += [
        "## Module inventory",
        "",
    ]
    for row in MODULES:
        place = row["place"].rstrip("/") + "/" + row["name"]
        row_no = ("manifest row %d" % row["manifest_row"]
                  if row["manifest_row"] is not None else "sibling helper")
        lines.append("- `%s` (%s) — %s Offline surface: %s. Exit codes: %s."
                     % (place, row_no, row["role"], row["offline"],
                        row["exit_codes"]))
    lines += [
        "",
        "## Exit codes (house convention 0/1/2/3/5; 4 = enforced violation)",
        "",
    ]
    for code in sorted(EXIT_CODES):
        lines.append("- %d — %s" % (code, EXIT_CODES[code]))
    lines += [
        "",
        "## AF autofail family",
        "",
    ]
    for code, exit_code, meaning in AF_CODES:
        lines.append("- %s (exit %d) — %s" % (code, exit_code, meaning))
    lines += [
        "",
        "## Doctrine",
        "",
    ]
    for name, text in DOCTRINE:
        lines.append("- %s: %s." % (name, text))
    lines += [
        "",
        "## Credentials — by label, never by value",
        "",
    ]
    for group, labels in CREDENTIAL_LABELS.items():
        lines.append("- %s: %s" % (group, ", ".join(labels)))
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Self-test — OFFLINE: the documentation's drift gate. No network, no
# credentials, only read-only filesystem existence checks for the modules
# the README claims ship. A FAILED self-test is exit 4 (enforced
# violation), never 'unexpected error' — the house self-test discipline.
# ---------------------------------------------------------------------------
EX_VIOLATION = 4
EX_OK = 0
EX_ERR = 1

def _module_file(row: dict) -> Path:
    """The on-disk path a README inventory row claims. Every u08_u09 row
    lives next to this module (scripts/u08_u09_modules/)."""
    base = Path(__file__).resolve().parent
    if row.get("place", "").strip("/") == "scripts":
        base = base.parent
    return base / row["name"]

def _self_test_body(dev) -> None:
    dev.write("[docs-forms] pinning: %d named forms, %d modules, "
              "exit codes 0..5\n"
              % (CONTRACT_FORM_COUNT, CONTRACT_MODULE_COUNT))

    frows = FORMS
    if len(frows) != CONTRACT_FORM_COUNT:
        raise AssertionError(
            "FORMS carries %d rows, contract is %d — the U08/U09 form list "
            "drifted; refusing to ship a stale README."
            % (len(frows), CONTRACT_FORM_COUNT))
    seen_forms = set()
    for row in frows:
        num = row.get("form")
        if not isinstance(num, int) or num in seen_forms:
            raise AssertionError(
                "FORMS form numbers must be unique integers, got %r" % num)
        seen_forms.add(num)
        for key in ("slug", "role", "hidden_fields", "surface", "law",
                    "builders", "id_marker", "fails"):
            if key == "hidden_fields":
                value = row.get(key)
                if not isinstance(value, list) or not value or not all(
                        isinstance(v, str) and v for v in value):
                    raise AssertionError(
                        "FORMS row %d lost its %r field — the form "
                        "contract is incomplete." % (num, key))
            elif not isinstance(row.get(key), str) or not row[key]:
                raise AssertionError(
                    "FORMS row %d lost its %r field — the form contract "
                    "is incomplete." % (num, key))
    if seen_forms != set(range(1, CONTRACT_FORM_COUNT + 1)):
        raise AssertionError(
            "FORMS form numbers must be exactly 1..%d, got %s"
            % (CONTRACT_FORM_COUNT, sorted(seen_forms)))

    # The form laws themselves never drift from the family's OWN authorities:
    # the three slugs are forms_check.FORM_SLUGS byte-exact, the intake trio
    # is the snapshot contract's universal_hidden_fields byte-exact, and the
    # review/title pair is EXACTLY (anthology_id, stage) — the U05 negative
    # mirror law (never the intake trio, never a contact_id).
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "u02_modules"))
        import forms_check as fc  # noqa: E402
        slugs = tuple(str(s) for s in fc.FORM_SLUGS)
    except Exception as exc:  # noqa: BLE001 — importability is the law, the reason is surfaced
        raise AssertionError(
            "forms_check cannot be imported to pin the three-form law "
            "(%s: %s) — refusing to ship a stale README."
            % (type(exc).__name__, exc))
    if slugs != ("universal-intake", "universal-review", "title-select"):
        raise AssertionError(
            "forms_check.FORM_SLUGS drifted: %r — the three-form law is "
            "load-bearing; refusing to ship a stale README." % (slugs,))
    doc_slugs = tuple(row["slug"] for row in frows)
    if doc_slugs != slugs:
        raise AssertionError(
            "the README form slugs %r drifted from forms_check.FORM_SLUGS "
            "%r — refusing to ship a stale README." % (doc_slugs, slugs))
    for row in frows:
        hf = tuple(row["hidden_fields"])
        if row["slug"] == "universal-intake":
            if hf != ("contact_id", "anthology_id", "stage"):
                raise AssertionError(
                    "the universal-intake hidden-field law drifted from "
                    "the universal trio: %r" % (hf,))
        else:
            if hf != ("anthology_id", "stage"):
                raise AssertionError(
                    "the %s hidden-field law drifted from the routing pair "
                    "anthology_id / stage: %r (the contact_id hidden field "
                    "is ABSENT by contract — the U05 negative mirror)."
                    % (row["slug"], hf))

    # The pinned form-id markers are the last-4 markers of the family's own
    # live-verified pins (the SAME pins form_spec_loader.py / forms_check.py
    # / title_select_builder.py ship against) — and NO full id VALUE may ever
    # ride the rendered README (masked markers only, the U06/U07 policy).
    pins = PINNED_FORM_IDS
    for row in frows:
        marker = row["id_marker"]
        fid = pins.get(row["slug"], "")
        if not fid or marker != "...%s" % fid[-4:]:
            raise AssertionError(
                "the README id marker for %s is %r — it must be the "
                "last-4 masked marker of the pinned id (never a value)."
                % (row["slug"], marker))
    rendered_ids = json.dumps(list(pins.values()))
    if any(fid in rendered for fid in pins.values()
           for rendered in [readme()]):
        raise AssertionError(
            "a pinned form id VALUE rides the rendered README — masked "
            "markers only, never a value (the U06/U07 policy).")

    mods = MODULES
    if len(mods) != CONTRACT_MODULE_COUNT:
        raise AssertionError(
            "MODULES carries %d rows, contract is %d — a U08/U09 module "
            "was added or removed without updating the inventory (and "
            "this self-test); refusing to ship a stale README."
            % (len(mods), CONTRACT_MODULE_COUNT))
    seen_names = set()
    for row in mods:
        name = row.get("name")
        if not isinstance(name, str) or not name or name in seen_names:
            raise AssertionError(
                "MODULES names must be unique non-empty strings, got %r"
                % name)
        seen_names.add(name)
        for key in ("place", "role", "offline", "exit_codes"):
            if not isinstance(row.get(key), str) or not row[key]:
                raise AssertionError(
                    "MODULES row %r lost its %r field." % (name, key))
        f = _module_file(row)
        if not f.is_file():
            raise AssertionError(
                "README inventory names %s, but that file does not ship at "
                "%s — documentation drifted from the tree (fail-closed: a "
                "doc that names a module that does not ship must never "
                "pass)." % (name, f))

    if set(EXIT_CODES) != {0, 1, 2, 3, 4, 5}:
        raise AssertionError(
            "EXIT_CODES must carry exactly 0..5 (house convention), got %s"
            % sorted(EXIT_CODES))
    for code in (0, 1, 2, 3, 4, 5):
        if not isinstance(EXIT_CODES[code], str) or not EXIT_CODES[code]:
            raise AssertionError("EXIT_CODES[%d] lost its meaning." % code)

    codes = [c for c, _, _ in AF_CODES]
    if len(codes) != len(set(codes)) or not codes:
        raise AssertionError("AF_CODES must carry unique, non-empty codes.")
    exits = {e for _, e, _ in AF_CODES}
    if not exits <= {2, 4, 5}:
        raise AssertionError(
            "AF family must map only onto STOP/self-test/mismatch exits "
            "(2/4/5), got %s" % sorted(exits))

    if not DOCTRINE or any(
            not isinstance(name, str) or not isinstance(text, str)
            or not name or not text for name, text in DOCTRINE):
        raise AssertionError("DOCTRINE must carry non-empty (name, text) rows.")

    if not CREDENTIAL_LABELS or not all(
            labels and all(isinstance(l, str) and l.isupper() and l
                           for l in labels)
            for labels in CREDENTIAL_LABELS.values()):
        raise AssertionError(
            "CREDENTIAL_LABELS must carry non-empty UPPERCASE label names "
            "only — a label is a name, never a value.")

    # The browser-UA doctrine is pinned byte-equal to the registry — a
    # registry regression is caught HERE first (the family's live surfaces
    # ride reg.CafClient, which applies CAF_BROWSER_UA on every request).
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
        import anthology_registry as reg  # noqa: E402
    except Exception as exc:  # noqa: BLE001
        raise AssertionError(
            "anthology_registry cannot be imported to pin the browser-UA "
            "doctrine (%s: %s)." % (type(exc).__name__, exc))
    if not getattr(reg, "CAF_BROWSER_UA", "") or not (
            "Mozilla/5.0" in reg.CAF_BROWSER_UA
            and "Chrome/" in reg.CAF_BROWSER_UA):
        raise AssertionError(
            "reg.CAF_BROWSER_UA is missing or not a browser User-Agent — "
            "the CF 1010 law drifted; refusing to ship a stale README.")

    # The rendered README must cover the data it renders (a dropped section
    # is drift, never a silent omission), and it must never leak a token:
    # the credential-shape scan is the same never-a-real-token doctrine the
    # sibling builders enforce before every surface.
    rendered = readme()
    for row in FORMS:
        if row["slug"] not in rendered:
            raise AssertionError(
                "readme() no longer renders form %r — the README drifted "
                "from FORMS." % row["slug"])
    for row in MODULES:
        if row["name"] not in rendered:
            raise AssertionError(
                "readme() no longer renders module %r — the README drifted "
                "from MODULES." % row["name"])
    for code in sorted(EXIT_CODES):
        if str(code) + " —" not in rendered:
            raise AssertionError(
                "readme() no longer renders exit code %d." % code)
    import re as _re
    # A real credential value is pit- followed by alphanumerics; the
    # doctrine's own literal template "pit-<value>" is the SHAPE description,
    # never a credential, and must not trip the scan.
    if _re.search(r"pit-[A-Za-z0-9]+", rendered):
        raise AssertionError(
            "the rendered README carries a credential-shaped string — "
            "REFUSED without printing it (the never-a-real-token "
            "doctrine).")
    if any(str(v) in rendered for v in pins.values()):
        raise AssertionError(
            "a pinned form id VALUE rides the rendered README — masked "
            "markers only (the U06/U07 policy).")

    dev.write("[docs-forms] PASS — README data and shipped tree agree "
              "(%d forms, %d modules, exit 0..5, %d af codes, form id "
              "values never surfaced).\n"
              % (len(frows), len(mods), len(codes)))

def self_test(out=None) -> int:
    """The module's own OFFLINE self-test (no network, no credentials).
    Returns 0 on a clean pass, 4 on a detected drift — a stale README never
    masquerades as a pass."""
    import io
    out = out or sys.stderr
    dev = io.StringIO()
    try:
        _self_test_body(dev)
    except AssertionError as exc:
        sys.stderr.write("[docs-forms] SELF-TEST FAILED "
                         "(AF-AE-TEMPLATE-ATTACK family discipline, "
                         "enforced violation): %s\n" % exc)
        return EX_VIOLATION
    out.write(dev.getvalue())
    return 0


# ---------------------------------------------------------------------------
# CLI — ONE JSON catalog object (default), the rendered README, or the
# offline self-test. Pure data; there is nothing secret here to leak.
# ---------------------------------------------------------------------------
def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="docs_forms.py",
        description="U08/U09 forms-family documentation module — README, "
                    "the three named forms and their laws, module inventory, "
                    "exit codes, doctrine, credential labels (pure data; "
                    "nothing to leak).")
    parser.add_argument("cmd", nargs="?", choices=("catalog", "readme",
                                                   "self-test"),
                        default="catalog",
                        help="catalog (default): ONE JSON object; readme: "
                             "the rendered README text; self-test: offline "
                             "drift gate (0 clean, 4 drift)")
    args = parser.parse_args(argv)
    try:
        if args.cmd == "self-test":
            return self_test()
        if args.cmd == "readme":
            sys.stdout.write(readme())
            return EX_OK
        print(json.dumps({
            "contract": DOC_CONTRACT,
            "schema_version": SCHEMA_VERSION,
            "ok": True,
            "verifier": U08_U09_VERIFIER,
            "manifest_row": U08_U09_MANIFEST_ROW,
            "shipping": U08_U09_SHIPPING_VERSION,
            "forms": forms(),
            "modules": modules(),
            "exit_codes": exit_codes(),
            "af_codes": af_codes(),
            "doctrine": [{"name": n, "text": t} for n, t in DOCTRINE],
            "credential_labels": {k: list(v)
                                  for k, v in CREDENTIAL_LABELS.items()},
            "note": "pure data — no credential value is held or printed; "
                    "form ids by masked marker only, never by value; the "
                    "U08/U09 manifest rows are PENDING",
        }, indent=2, sort_keys=True))
        return EX_OK
    except Exception as exc:  # noqa: BLE001 — top-level guard, never leaks a secret
        sys.stderr.write("[docs-forms] unexpected error: %s: %s\n"
                         % (type(exc).__name__, exc))
        return EX_ERR

if __name__ == "__main__":
    sys.exit(main())
