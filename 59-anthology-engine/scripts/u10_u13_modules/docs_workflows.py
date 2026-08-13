#!/usr/bin/env python3
# =============================================================================
# SKILL 59 — ANTHOLOGY ENGINE :: u10_u13_modules/docs_workflows.py
# U10/U13 WORKFLOWS-FAMILY TOOLING — THE MODULE DOCSTRING / README, SHIPPED AS
# AN IMPORTABLE MODULE (the u08_u09_modules/docs_forms.py row-54-sibling
# pattern — the U10/U13 workflows family ships under the ENGINE-MANIFEST.json
# row-54 "template live verify (U02)" shipping doctrine; the family's OWN
# manifest rows are NOT yet stamped: PENDING, staged exactly under the
# manifest-pending/u02.json · u03.json · u04.json · u05.json · u06.json ·
# u07.json · u08_u09.json pattern; current skill-version 0.1.24, 2026-08-11).
# -----------------------------------------------------------------------------
# WHERE THIS SITS: scripts/u10_u13_modules/ — the U10/U13 workflows family's
# documentation module, sibling of the eleven template generators (w1_review_
# fire, w2_title_fire, w3_release_avatar, w4_release_tone, w5_release_title,
# w7_release_chapter, w8_release_rewrite, w9_release_cover, w10_release_final,
# w11_delivered, w12_chapter_ready), the canonical copy-law module
# (copy_rules.py), the webhook-body builder (webhook_body.py), and the
# dispatcher (main_skeleton.py) it documents. It is NOT a manifest row: the
# family's driver stays main_skeleton.py (the offline-plan / offline-
# self-test dispatcher under the U02 row-54 sibling-helper pattern, exactly
# as u02_modules/docs_u02.py · u03_modules/docs_u03.py · u04_modules/docs_u04
# .py · u05_modules/docs_u05.py · u06_modules/docs_u06.py ·
# u07_modules/docs_u07.py · u08_u09_modules/docs_forms.py document their
# siblings; the family's OWN manifest rows are PENDING — recorded below as
# None; a doc that claims a manifest row that does not exist is drift).
# Imported BY NAME as u10_u13_modules.docs_workflows when a consumer wants
# the family's contract surfaces as DATA (the thirteen workflows and their
# seats, the copy rules, the module inventory, the house exit codes, the
# doctrine) or its rendered README as text.
#
# WHAT THIS OWNS:
#   1. THE README. The module docstring below IS the U10/U13 workflows-family
#      README: what the tooling generates, the thirteen workflows and their
#      seats, the copy rules, the module inventory, the exit-code contract,
#      the credential / OFFLINE / fail-closed doctrine. The same content is
#      carried as STRUCTURED DATA (WORKFLOWS, COPY_RULES, MODULES,
#      EXIT_CODES, DOCTRINE, CREDENTIAL_LABELS) so a consumer can diff
#      against it instead of parsing prose — and readme() renders the README
#      FROM that data, so the two can never drift.
#   2. THE DRIFT GATE. self_test() proves the documentation still matches
#      the shipped tree: every module the README lists exists on disk next
#      to this module, every workflow seat row is present exactly once,
#      every house exit code is documented, the stage vocabulary is
#      byte-equal to the STAGE_CURSORS the dispatcher pins, and the rendered
#      README covers every inventory row. A doc that names a module that
#      does not ship FAILS the self-test (exit 4, the house
#      enforced-violation code) — documentation is data, and stale
#      documentation is drift.
#   3. PURE DATA, BY CONSTRUCTION. Nothing here reads an env var, opens a
#      file at import, touches the network, or holds a credential. A
#      documentation module cannot leak what it never holds. It performs NO
#      requests, so it defines NO User-Agent constant of its own: the
#      browser UA that defeats the Cloudflare edge (CF error 1010) is
#      CAF_BROWSER_UA, owned by anthology_registry.py and applied by its
#      clients (CafClient) — the docs record that doctrine, they do not
#      re-implement it. The form ids the docs mention are the family's
#      pinned LOCATION identifiers (the live-verified 2026-08-11 pins of
#      forms_check.py / the w1/w2/w5 siblings) — not secrets, but reported
#      BY MASKED MARKER on every surface, and the self-test proves no form
#      id VALUE rides the rendered README.
#
# THE THIRTEEN WORKFLOW SEATS (the family's contract surface — the fixed
# inventory the release-notification template family serves; the count is
# load-bearing and pinned by the self-test):
#   THE ELEVEN MODULE-OWNED WORKFLOWS — one generator module per workflow
#   seat, each an OFFLINE JSON/Python data generator, each with its own
#   battery, driven only through the main_skeleton.py dispatcher:
#     1.  W1  Anthology Review Fire          (w1_review_fire.py)
#     2.  W2  Anthology Title Fire           (w2_title_fire.py)
#     3.  W3  Anthology Release: Avatar      (w3_release_avatar.py)
#     4.  W4  Anthology Release: Tone        (w4_release_tone.py)
#     5.  W5  Anthology Release: Title       (w5_release_title.py)
#     6.  W7  Anthology Release: Chapter     (w7_release_chapter.py)
#     7.  W8  Anthology Release: Rewrite     (w8_release_rewrite.py)
#     8.  W9  Anthology Release: Cover Picks (w9_release_cover.py)
#     9.  W10 Anthology Release: Final Chapter (w10_release_final.py)
#     10. W11 Anthology: Book Delivered      (w11_delivered.py)
#     11. W12 Chapter Approval Ready         (w12_chapter_ready.py)
#   THE TWO SEATS THE FAMILY DOCUMENTS BUT DOES NOT OWN:
#     12. Anthology Intake Fire — the intake front door, the THIRD member
#         of the three-Fire family (Intake / Review / Title; forms_check.py
#         :271, the internal-rail trigger surface live-verified 2026-08-11).
#         Owned by the U02/U05 tooling (u02_modules/scope_check.py,
#         scripts/check_intake_fire_scope.py); the U10/U13 family documents
#         the seat, it does not generate its template.
#     13. Anthology Release: Outline & Blurb — the contract's LIVE-slug row
#         (config/anthology-snapshot-contract.json
#         workflows.release_notifications, trigger tag
#         anthology-release-outline; the S4 blurb-and-outline deliverable
#         pair field-map.json deliverable_fields blurb + outline). The
#         contract row is declared; a W6 generator module for the seat is
#         PENDING and does not yet ship (a doc that claims a module that
#         does not ship is drift — recorded below as pending_module: null).
#
# COPY RULES (workflows.copy_law — Trevor's verbatim law for every client-
# facing word these workflows carry; enforced at GENERATION time by every
# generator and RE-PROVEN by the dispatcher's copy-law scan on every
# surface, so a templated release can never drift from the law):
#   EDITORS, NEVER AI ........ "editors" and "editorial team" are the ONLY
#        byline actors. "AI", "ghostwriter", "automated", "generated" and
#        every model / tool name are ABSENT from every generated string
#        (the generators refuse them by word boundary; the single
#        enforcement-context exception is the module docstrings, which are
#        not generated copy — the guards allowlist the deny definitions
#        line-for-line, the guard-no-anthropic-runtime.py convention).
#   ZERO EM-DASHES .......... U+2014 is FORBIDDEN in every generated string.
#        Every sentence uses commas, periods, or a colon instead. The
#        generators refuse (ValueError) any rendered string that carries
#        one (the same law verify.sh enforces over the nudge templates).
#   SIGN-OFF ................ "The Editors" or "{{ custom_values.producer }}"
#        only, never a person's raw name and never a model persona. The
#        email sign-off is "The Editors"; SMS never carries a sign-off (the
#        SMS shape law: one warm sentence plus ONE link).
#   STANDING INSTRUCTION .... "The PDF is yours to view. The Google Doc is
#        the one you edit, and it is the version we use." — byte-exact, in
#        every release email (copy_law.standing_instruction).
#   STAGE FORM LINK ......... <forms_base>/widget/form/<form_id>?anthology_id=
#        <minted>&stage=<stage> — the U08 pre-fill law: the TWO query params
#        pre-fill the form's HIDDEN fields client-side (the universal
#        hidden-field contract contact_id / anthology_id / stage;
#        prefill_verifier.py owns the verifier). The default form is the
#        universal-review pin (riNlAkYbcW3g92VRLqq0 — the Review Fire
#        trigger AND the form the release emails link) except for the W5
#        Title release and the W2 Title Fire, which link the title-select
#        pin (UgiiSoZsA4vyqOVfO5fi), and the W7 chapter release, which
#        carries the form id and the minted anthology id AS MASKED MARKERS
#        only, never values. The default stage is always an exact
#        STAGE_CURSORS vocabulary member; an out-of-vocabulary stage is a
#        refusal, never a fabricated token. The G3 key law: the query key is
#        EXACTLY "anthology_id", never "anthology_active_id".
#   PER-STAGE LINKS ......... each email carries that stage's PDF (VIEW)
#        link plus the editable Google Doc (EDIT) link, pulled from the
#        matching config/field-map.json deliverable_fields contact custom
#        fields (the contract row's email_link_fields); the SMS carries
#        ONLY the doc link (sms_shape: one warm sentence plus ONE link).
#   WARM LANGUAGE ............ every client-facing word is warm and
#        personal: the email greets the author by name via the
#        {{ contact.first_name }} merge and closes warm ("Warm regards")
#        before the sanctioned sign-off (the warm-language law, copy_rules
#        COPY_LAW warm_language).
#   NO CODE FENCES / NO INTERNAL NAMES / NO TOKENS .... zero code fences,
#        zero internal tool or model names, and — this family holds no
#        credential surface — a secret-shaped fragment (Bearer / sk- / a
#        JWT / pit-<value>) anywhere in a generated string is a refusal at
#        generation time, never a print. The webhook URL and its
#        Authorization header ride the REPLACE-ME location custom-value
#        merges ONLY ({{ custom_values.anthology_webhook_url }} and
#        {{ custom_values.anthology_hook_secret }}, the never-a-real-token
#        rule) — never an inlined URL, never an inlined token.
#
# CREDENTIALS: BY LABEL, NEVER BY VALUE, everywhere in the engine. The
# U10/U13 workflows family itself RESOLVES NOTHING: there is no PIT, no
# location, no token, no env secret on any surface of any template
# generator — a template generator cannot print a token it never holds. The
# live surfaces elsewhere in the engine (the builders' apply, the caf
# delivery rail) resolve their credentials through the house labels (PIT
# first: CONVERT_AND_FLOW_PIT / CONVERT_AND_FLOW_API_KEY / GOHIGHLEVEL_API_KEY
# / GOHIGHLEVEL_PIT / GHL_API_KEY — live process env first, then the three
# canonical client env stores; SET / NOT SET only — a token value is NEVER
# printed). The self-test proves the never-a-real-token law on the rendered
# README too: a credential-shaped string on any surface REFUSES the whole
# surface rather than print it. Form ids and location ids are MASKED to
# their last 4 characters on every report — never printed in full.
#
# OFFLINE LAW (the heart of the family): template generation is OFFLINE by
# construction — plan / render / self-test all run with zero network and
# zero credential; rendering is PURE (same inputs -> same bytes). A
# live-verify request is a usage STOP at the dispatcher CLI (exit 2),
# never a silent network probe — this family has no live surface to gate.
#
# BROWSER UA (CF 1010 LAW): every request the ENGINE makes to GoHighLevel /
# Convert and Flow (services.leadconnectorhq.com) rides reg.CafClient, which
# applies CAF_BROWSER_UA on EVERY request — urllib's default
# "Python-urllib/x.y" is 403'd at the WAF edge (CF error 1010) before it
# ever reaches Convert and Flow (W0.6 / GK-09). This documentation module
# makes NO network call and defines NO User-Agent constant of its own — the
# self-test PINS the browser-UA doctrine constant byte-equal to
# reg.CAF_BROWSER_UA so a registry regression is caught HERE first.
#
# FAIL-CLOSED (the whole point): a missing credential STOPS (exit 2), a
# non-pit- token is refused, an out-of-vocabulary stage token or an unknown
# form slug is a refusal (exit 2 / ValueError, never a fabricated token), a
# template module the dispatcher's inventory names but that does not ship
# is a STOP (exit 2, AF-AE-U10-U13-ASSEMBLY-INCOMPLETE), an em-dash / a
# banned byline actor / an unbalanced merge slot / a code fence / a
# secret-shaped fragment in any generated string is a REFUSAL (exit 5,
# AF-AE-COPY-LAW), an attack fixture that trips an OFFLINE battery is exit
# 4 (AF-AE-TEMPLATE-ATTACK, never 1), and a drifted authority (the snapshot
# contract's copy_law, field-map.json deliverable_fields, gate_engine /
# anthology_state STAGE_CURSORS) breaks the family's self-tests FIRST —
# a tamper never masquerades as exit 1. Every deviation is NAMED with its
# code — never a bare "something failed".
#
# DOCTRINE (house, per anthology_registry.py / drive_adapter.py): move in
# silence (operator-verbose only); NOTHING Anthropic in any runtime file;
# Convert and Flow naming in every client surface; STDLIB ONLY; calls NO
# model; never a client PII; a law is read once, in one module (copy_rules
# .py is the canonical source of the copy law and the deny machinery, the
# dispatcher pins the STAGE_CURSORS vocabulary read once from
# anthology_state.py, gate_engine owns the gate / decision vocabulary, the
# snapshot contract owns the copy_law and release_notifications rows, and
# the generators derive from them, never re-implement). READ-ONLY by
# doctrine — this documentation module never writes; the family's write
# surface is the Skill 44 caf build rail at build time, never a module
# here. Self-test failures are exit 4 (the AF-AE-* families below), never
# exit 1.
#
# USAGE (this module's own machine surface — pure data, nothing to leak):
#   python3 docs_workflows.py                ONE JSON catalog of the whole tooling
#   python3 docs_workflows.py readme         the rendered README (markdown text)
#   python3 docs_workflows.py self-test      OFFLINE drift gate over the docs vs
#                                            the shipped tree; 0 clean, 4 drift
# =============================================================================
"""docs_workflows.py -- README / module docstring for the U10/U13
workflows-family tooling, as an importable fail-closed pure-data module: the
thirteen workflow seats (the eleven module-owned release-notification and
Fire template generators, the Intake Fire seat owned by the U02/U05
tooling, and the declared-but-pending Outline and Blurb contract row), the
copy rules (editors never the banned words, zero em-dashes, sign-off
"The Editors" or the producer merge, the standing instruction, the stage
form link with anthology_id and stage prefilled, the PDF view plus Doc edit
link pair, warm language), the module inventory, the house exit codes, and
the credential / OFFLINE / browser-UA / doctrine contracts — shipped under
the ENGINE-MANIFEST.json row-54 "template live verify (U02)" doctrine (the
family's OWN manifest rows PENDING). Performs no I/O at import and holds no
credential; readme() is rendered from the same structured data the
self-test asserts against, so documentation and data cannot drift."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# The fixed report contract (mirrors the golden-fixture naming discipline).
# ---------------------------------------------------------------------------
DOC_CONTRACT = "anthology-engine-u10-u13-workflows-docs"
SCHEMA_VERSION = 1

# The U10/U13 workflows family's driver is main_skeleton.py under the U02
# row-54 shipping law; the u10_u13_modules/ siblings ship as non-manifest
# helpers (the delivery_report.py row-12 pattern, exactly the docs_u02.py /
# docs_u03.py / docs_u04.py / docs_u05.py / docs_u06.py / docs_u07.py /
# docs_forms.py siblings). The family's OWN manifest rows are NOT yet
# stamped in ENGINE-MANIFEST.json (verified at ship time, 2026-08-11): they
# are PENDING, staged under the manifest-pending/u02.json · u03.json ·
# u04.json · u05.json · u06.json · u07.json · u08_u09.json pattern — this
# module records None rather than invent row numbers (a doc that claims
# rows that do not exist is drift).
U10_U13_DISPATCHER = "main_skeleton.py"  # the family's driver
U10_U13_MANIFEST_ROW = None  # PENDING — the family is not yet stamped
U10_U13_SHIPPING_VERSION = "v0.1.24 (2026-08-11)"  # skill-version at ship time

# ---------------------------------------------------------------------------
# THE THIRTEEN WORKFLOW SEATS — the family's contract surface, in the FIXED
# order the dispatcher's module inventory carries (w1 .. w12, then the two
# documented-but-not-owned seats). Each row is ONE workflow seat: the
# generator module that owns it (or None for a documented seat), the
# trigger seat (form_submission for the three Fires, contact_tag for the
# release rows), the stage token the release / review link pre-fills, the
# deliverable pair the email links, and the actions. Workflow numbers are
# load-bearing (positions 1..13, exactly thirteen — the self-test pins the
# count).
# ---------------------------------------------------------------------------
WORKFLOWS = (
    {
        "seat": 1,
        "name": "Anthology Review Fire",
        "module": "w1_review_fire",
        "trigger": "form_submission, scoped EXACTLY to the universal-review "
                   "form (the engine's ONE client-facing decision form; the "
                   "Review Fire trigger AND the form the release emails "
                   "link)",
        "actions": "custom-webhook POST (the REPLACE-ME merges "
                   "{{ custom_values.anthology_webhook_url }} and "
                   "{{ custom_values.anthology_hook_secret }}, never a real "
                   "token) + the review-decision EMAIL + SMS",
        "stage": "s5_gate",
        "deliverable": "the chapter pair — PDF view "
                       "{{contact.anthology_chapter_pdf_url}} + Google Doc "
                       "edit {{contact.anthology_chapter_doc_url}}",
        "form": "universal-review (the pinned Review Fire trigger form, "
                "BY MASKED MARKER ...Lqq0)",
    },
    {
        "seat": 2,
        "name": "Anthology Title Fire",
        "module": "w2_title_fire",
        "trigger": "form_submission, scoped EXACTLY to the title-select "
                   "form (the S3 title-and-subtitle pick; the Title Fire "
                   "trigger AND the S3 link in \"Release: Titles\")",
        "actions": "ONE custom-webhook POST (the REPLACE-ME merges, never "
                   "a real URL, never a real token) + the release EMAIL + "
                   "SMS",
        "stage": "s3_gate",
        "deliverable": "the Titles pair — PDF view "
                       "{{contact.anthology_titles_pdf_url}} + Google Doc "
                       "edit {{contact.anthology_titles_doc_url}}",
        "form": "title-select (the pinned Title Fire trigger form, BY "
                "MASKED MARKER ...O5fi)",
    },
    {
        "seat": 3,
        "name": "Anthology Release: Avatar",
        "module": "w3_release_avatar",
        "trigger": "contact_tag anthology-release-avatar (the §3 release "
                   "bus; the contract row of the same name, LIVE slug, "
                   "actions send-email + send-sms)",
        "actions": "send-email + send-sms",
        "stage": "s1_gate",
        "deliverable": "the Avatar pair — PDF view "
                       "{{contact.anthology_avatar_pdf_url}} + Google Doc "
                       "edit {{contact.anthology_avatar_doc_url}}",
        "form": "universal-review (the default release-link form)",
    },
    {
        "seat": 4,
        "name": "Anthology Release: Tone",
        "module": "w4_release_tone",
        "trigger": "contact_tag anthology-release-tone (the §3 release "
                   "bus; the contract row of the same name, LIVE slug, "
                   "actions send-email + send-sms)",
        "actions": "send-email + send-sms",
        "stage": "s2_gate",
        "deliverable": "the Tone pair — PDF view "
                       "{{contact.anthology_tone_pdf_url}} + Google Doc "
                       "edit {{contact.anthology_tone_doc_url}}",
        "form": "universal-review (the default release-link form)",
    },
    {
        "seat": 5,
        "name": "Anthology Release: Title",
        "module": "w5_release_title",
        "trigger": "contact_tag anthology-release-title (the §3 release "
                   "bus, the S3 TITLE stage's release; the SAME default "
                   "stage token the W2 Title Fire sibling uses)",
        "actions": "send-email + send-sms",
        "stage": "s3_gate",
        "deliverable": "the Titles pair — PDF view "
                       "{{contact.anthology_titles_pdf_url}} + Google Doc "
                       "edit {{contact.anthology_titles_doc_url}}",
        "form": "title-select (the pinned Title Fire trigger form, BY "
                "MASKED MARKER ...O5fi — the Title Fire trigger AND the S3 "
                "title-and-subtitle link)",
    },
    {
        "seat": 6,
        "name": "Anthology Release: Chapter",
        "module": "w7_release_chapter",
        "trigger": "contact_tag anthology-release-chapter (the §3 release "
                   "bus fired by gate_engine GATE_RELEASE_SLUG at the "
                   "s5_producer board-door gate; the contract row of the "
                   "same name, WIRED-AHEAD slug, actions send-email + "
                   "send-sms)",
        "actions": "send-email + send-sms",
        "stage": "s5_chapter",
        "deliverable": "the chapter pair — PDF view "
                       "{{contact.anthology_chapter_pdf_url}} + Google Doc "
                       "edit {{contact.anthology_chapter_doc_url}}; the "
                       "two-editors'-rewrites-maximum reminder with the "
                       "{{contact.anthology_rewrite_count}} of-2 phrase",
        "form": "the stage form link rides MASKED MARKERS only — the form "
                "id and the minted anthology id as placeholders, never "
                "values",
    },
    {
        "seat": 7,
        "name": "Anthology Release: Rewrite",
        "module": "w8_release_rewrite",
        "trigger": "contact_tag anthology-release-rewrite (the §3 release "
                   "bus fired at the s6_producer gate; the contract row of "
                   "the same name, WIRED-AHEAD slug, actions send-email + "
                   "send-sms)",
        "actions": "send-email + send-sms",
        "stage": "s6",
        "deliverable": "the rewrite1 / rewrite2 preservation-slot pair — "
                       "PDF view + Google Doc edit links; the rewrite "
                       "budget of TWO with the "
                       "{{contact.anthology_rewrite_count}} merge",
        "form": "the stage form link with the "
                "?anthology_id=<minted>&stage=s6 query pair (the G3 key "
                "law)",
    },
    {
        "seat": 8,
        "name": "Anthology Release: Cover Picks",
        "module": "w9_release_cover",
        "trigger": "contact_tag anthology-release-cover (the §3 release "
                   "bus fired by gate_engine GATE_RELEASE_SLUG at the "
                   "s7_producer gate; the contract row of the same name, "
                   "WIRED-AHEAD slug, actions send-email + send-sms)",
        "actions": "send-email + send-sms",
        "stage": "s7_cover",
        "deliverable": "the FOUR cover-sample links (Signature / Bold "
                       "Editorial / Fine Art / Pure Type — cover_render "
                       "STYLE_NAMES)",
        "form": "the stage form link pre-filled with the s7_cover stage "
                "token",
    },
    {
        "seat": 9,
        "name": "Anthology Release: Final Chapter",
        "module": "w10_release_final",
        "trigger": "contact_tag anthology-release-final (the §3 release "
                   "bus; STAGE-RUNNER-FIRED at the S8 stage, not a "
                   "producer-approve gate; the contract row of the same "
                   "name, DOCTRINE slug, actions send-email + send-sms)",
        "actions": "send-email + send-sms",
        "stage": "s8",
        "deliverable": "the final-chapter pair — PDF view "
                       "{{contact.anthology_chapter_pdf_url}} + Google Doc "
                       "edit {{contact.anthology_chapter_doc_url}} (the "
                       "S8 runner's own STAGE constant)",
        "form": "the stage form link pre-filled with the s8 stage token",
    },
    {
        "seat": 10,
        "name": "Anthology: Book Delivered",
        "module": "w11_delivered",
        "trigger": "contact_tag anthology-delivered (the TERMINAL "
                   "s9_producer milestone — the delivered cursor; the "
                   "contract row of the same name, DOCTRINE slug, actions "
                   "send-email + send-sms)",
        "actions": "send-email + send-sms",
        "stage": "delivered",
        "deliverable": "the manuscript pair — PDF view "
                       "{{contact.anthology_manuscript_pdf_url}} + Google "
                       "Doc edit {{contact.anthology_manuscript_doc_url}}",
        "form": "the stage form link pre-filled with the delivered stage "
                "token",
    },
    {
        "seat": 11,
        "name": "Chapter Approval Ready",
        "module": "w12_chapter_ready",
        "trigger": "contact_tag anthology-producer-chapter-ready (the "
                   "producer-notification seat named by the contract's "
                   "workflows.producer_notify_out_of_scope — notifies the "
                   "PRODUCER, not the author; the retrofit template under "
                   "the same copy law)",
        "actions": "EMAIL ONLY — actions exactly [\"send-email\"]; there "
                   "is no SMS action and no webhook in the producer "
                   "notification",
        "stage": "s5",
        "deliverable": "the chapter pair — PDF view "
                       "{{contact.anthology_chapter_pdf_url}} + Google Doc "
                       "edit {{contact.anthology_chapter_doc_url}}; the "
                       "rewrites-used count with the of-2 budget wording",
        "form": "the stage form link pre-filled with the s5 stage token "
                "so the router re-stamps the universal hidden-field "
                "contract on gate re-entry",
    },
    {
        "seat": 12,
        "name": "Anthology Intake Fire",
        "module": None,
        "trigger": "form_submission, scoped EXACTLY to the universal-intake "
                   "form (the intake front door; the minted link "
                   "<forms_base>/widget/form/<id>?anthology_id=<minted> "
                   "built by anthology_book.py)",
        "actions": "the webhook-to-route intake mapping "
                   "(/hooks/anthology-intake) — owned by the U02/U05 "
                   "tooling (u02_modules/scope_check.py, "
                   "scripts/check_intake_fire_scope.py), NOT by this "
                   "family; documented here as the third member of the "
                   "three-Fire family (Intake / Review / Title; "
                   "forms_check.py, live-verified 2026-08-11)",
        "owned_elsewhere": "true — the seat is owned by the U02/U05 "
                           "tooling (u02_modules/scope_check.py, "
                           "scripts/check_intake_fire_scope.py); this "
                           "family documents it, it does not generate its "
                           "template",
        "stage": "s0_intake",
        "deliverable": "none — the intake front door carries no "
                       "deliverable link pair",
        "form": "universal-intake (the pinned Intake Fire trigger form, "
                "BY MASKED MARKER ...lKWG)",
    },
    {
        "seat": 13,
        "name": "Anthology Release: Outline & Blurb",
        "module": None,
        "trigger": "contact_tag anthology-release-outline (the §3 release "
                   "bus fired by gate_engine GATE_RELEASE_SLUG at the "
                   "s4_producer gate; the contract row of the same name, "
                   "LIVE slug, actions send-email + send-sms)",
        "actions": "send-email + send-sms",
        "stage": "s4_blurb_outline",
        "deliverable": "the blurb + outline pairs — PDF view + Google Doc "
                       "edit links from field-map.json deliverable_fields "
                       "blurb and outline",
        "form": "the universal-review default form link, pending a W6 "
                "generator",
        "pending_module": "a W6 generator module for this seat is PENDING "
                          "and does not yet ship — the contract row is "
                          "declared; a doc that claims a module that does "
                          "not ship is drift, so this seat stays "
                          "module-less here",
    },
)

# The family's module-owned seats, as the dispatcher's inventory carries
# them (the on-disk template generator modules — the drift gate checks
# every row against the tree).
MODULE_OWNED_SEATS = (
    "w1_review_fire", "w2_title_fire", "w3_release_avatar",
    "w4_release_tone", "w5_release_title", "w7_release_chapter",
    "w8_release_rewrite", "w9_release_cover", "w10_release_final",
    "w11_delivered", "w12_chapter_ready",
)

# ---------------------------------------------------------------------------
# THE COPY RULES (workflows.copy_law, Trevor's verbatim) as data — the same
# law copy_rules.py owns as the single canonical source; this row records
# the law so the README renders it, and the self-test asserts it never
# drifts from the family's own canonical constants (copy_rules.py) and the
# contract (config/anthology-snapshot-contract.json workflows.copy_law).
# ---------------------------------------------------------------------------
COPY_RULES = {
    "editors_never_ai": {
        "note": "The editorial process is performed by 'editors', never "
                "the banned words (Trevor's verbatim law; MASTERDOC floor "
                "#14).",
        "sanctioned_word": "editors",
        "banned_words": ("AI", "ghostwriter"),
    },
    "no_em_dashes": {
        "note": "Zero U+2014 em-dash characters in any client-facing "
                "word (the same law verify.sh enforces over the nudge "
                "templates).",
        "banned_character": "U+2014 em-dash",
    },
    "sign_off": {
        "note": "The email sign-off is exactly one of two forms: "
                "'The Editors' or the producer-name merge "
                "{{ custom_values.producer }} — never a person's raw name "
                "and never a model persona.",
        "editors": "The Editors",
        "producer_merge": "{{ custom_values.producer }}",
    },
    "sms_shape": {
        "note": "Link-only short message: one warm sentence plus ONE "
                "link. SMS never carries a sign-off.",
        "law": "one warm sentence plus ONE link",
    },
    "standing_instruction": "The PDF is yours to view. The Google Doc is "
                            "the one you edit, and it is the version we "
                            "use.",
    "stage_form_link": {
        "note": "The U08 pre-fill law: <forms_base>/widget/form/"
                "<form_id>?anthology_id=<minted>&stage=<stage> — the TWO "
                "query params pre-fill the form's HIDDEN fields "
                "client-side (the universal hidden-field contract "
                "contact_id / anthology_id / stage). The G3 key law: the "
                "query key is EXACTLY 'anthology_id', never "
                "'anthology_active_id'. The stage token is always an "
                "exact STAGE_CURSORS vocabulary member; an "
                "out-of-vocabulary stage is a refusal, never a fabricated "
                "token.",
        "query_keys": ("anthology_id", "stage"),
    },
    "per_stage_links": {
        "note": "Each email carries that stage's PDF (VIEW) link plus "
                "the editable Google Doc (EDIT) link, pulled from the "
                "matching config/field-map.json deliverable_fields "
                "contact custom fields; the SMS carries ONLY the doc "
                "link.",
    },
    "warm_language": {
        "note": "Every client-facing word is warm and personal: the "
                "email greets the author by name via the "
                "{{ contact.first_name }} merge and closes warm "
                "('Warm regards') before the sanctioned sign-off.",
        "greeting_merge": "{{ contact.first_name }}",
        "warm_close": "Warm regards",
    },
    "no_tokens": {
        "note": "The family holds no credential surface: the webhook URL "
                "and its Authorization header ride the REPLACE-ME "
                "location custom-value merges ONLY "
                "({{ custom_values.anthology_webhook_url }} and "
                "{{ custom_values.anthology_hook_secret }}) — never an "
                "inlined URL, never an inlined token. A secret-shaped "
                "fragment (Bearer / sk- / a JWT / pit-<value>) anywhere "
                "in a generated string is a refusal at generation time, "
                "never a print.",
        "webhook_url_merge": "{{ custom_values.anthology_webhook_url }}",
        "hook_secret_merge": "{{ custom_values.anthology_hook_secret }}",
    },
}

# ---------------------------------------------------------------------------
# THE MODULE INVENTORY. `place` names the directory relative to this module
# (the u10_u13_modules package itself); self-test proves each name exists at
# that place. `role` is the one-line contract each module owns; `offline`
# names the credential-free surface; `exit_codes` follows the house
# convention (0/1/2/3/5, 4 = self-test).
# ---------------------------------------------------------------------------
MODULES = (
    {
        "name": "__init__.py",
        "place": "scripts/u10_u13_modules/",
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
        "name": "copy_rules.py",
        "place": "scripts/u10_u13_modules/",
        "manifest_row": None,
        "role": ("the COPY-RULE CONSTANT MODULE — the single canonical "
                 "source of the copy law (config/anthology-snapshot-"
                 "contract.json workflows.copy_law, Trevor's verbatim) "
                 "plus the two-link and stage-form-link laws for the "
                 "U10/U13 tag->notification template family: the "
                 "sanctioned word 'editors', the banned words, zero "
                 "em-dashes, the sign-off law ('The Editors' or the "
                 "producer merge), the warm-language law, the stage-form "
                 "link with anthology_id and stage prefilled, the PDF "
                 "view + Doc edit link pair per stage, and the "
                 "never-a-real-token deny machinery. Every sibling "
                 "imports its constants and deny machinery FROM HERE, so "
                 "the law is defined once and enforced everywhere"),
        "offline": "entirely — pure data + self-test (no network, no "
                   "credential)",
        "exit_codes": "0/1/2/4",
    },
    {
        "name": "webhook_body.py",
        "place": "scripts/u10_u13_modules/",
        "manifest_row": None,
        "role": ("the W1/W2 WEBHOOK BODY BUILDER — the routed submission "
                 "shapes the engine's inbound intake hook "
                 "(/hooks/anthology-intake) accepts and the OUTBOUND "
                 "custom-webhook POST shapes the tag->notification "
                 "workflows fire: the body key law (source, stage, "
                 "decision, notes, cover_choice, anthology_id, "
                 "contact_id, location), the source law (exactly "
                 "'anthology-intake'), the secret-header law (the route "
                 "secret rides the header, never the body; the outbound "
                 "POST rides the REPLACE-ME merge only), the decision / "
                 "notes / cover law (the two s5_gate actions, the four "
                 "cover styles), the copy law, the standing instruction, "
                 "and the stage-form pre-fill link"),
        "offline": "entirely — pure data generator, no network, no "
                   "credential",
        "exit_codes": "0/1/2/4",
    },
    {
        "name": "w1_review_fire.py",
        "place": "scripts/u10_u13_modules/",
        "manifest_row": None,
        "role": ("the W1 REVIEW FIRE TEMPLATE — the form_submission-"
                 "triggered Review Fire workflow (the trigger scoped "
                 "EXACTLY to the universal-review form, the custom-webhook "
                 "POST with the REPLACE-ME merges, and the review-decision "
                 "EMAIL + SMS pair): the chapter PDF view + Doc edit "
                 "merges, the stage form link pre-filled "
                 "?anthology_id=<minted>&stage=<stage> (default s5_gate), "
                 "and the sign-off 'The Editors' or the producer merge"),
        "offline": "entirely — pure data generator, no network, no "
                   "credential",
        "exit_codes": "0/1/2/4/5",
    },
    {
        "name": "w2_title_fire.py",
        "place": "scripts/u10_u13_modules/",
        "manifest_row": None,
        "role": ("the W2 TITLE FIRE TEMPLATE — the form_submission-"
                 "triggered Title Fire workflow (one ACTIVE trigger "
                 "scoped to the title-select form, the ONE custom-webhook "
                 "POST action, and the release EMAIL + SMS pair): the "
                 "Titles PDF view + Doc edit merges, the stage form link "
                 "pre-filled with the default stage s3_gate, and the "
                 "sign-off law"),
        "offline": "entirely — pure data generator, no network, no "
                   "credential",
        "exit_codes": "0/1/2/4/5",
    },
    {
        "name": "w3_release_avatar.py",
        "place": "scripts/u10_u13_modules/",
        "manifest_row": None,
        "role": ("the W3 RELEASE-AVATAR TEMPLATE — the "
                 "anthology-release-avatar EMAIL + SMS generator (the "
                 "contract row of the same name, LIVE slug): the Avatar "
                 "deliverable PDF view + Doc edit links, the byte-exact "
                 "standing instruction, the stage review form link "
                 "pre-filled with the default stage s1_gate, the "
                 "link-only SMS shape, and the sign-off law"),
        "offline": "entirely — pure data generator, no network, no "
                   "credential",
        "exit_codes": "0/1/2/4/5",
    },
    {
        "name": "w4_release_tone.py",
        "place": "scripts/u10_u13_modules/",
        "manifest_row": None,
        "role": ("the W4 RELEASE-TONE TEMPLATE — the "
                 "anthology-release-tone EMAIL + SMS generator (the "
                 "contract row of the same name, LIVE slug): the Tone "
                 "deliverable PDF view + Doc edit links, the byte-exact "
                 "standing instruction, the stage review form link "
                 "pre-filled with the default stage s2_gate, the "
                 "link-only SMS shape, and the sign-off law"),
        "offline": "entirely — pure data generator, no network, no "
                   "credential",
        "exit_codes": "0/1/2/4/5",
    },
    {
        "name": "w5_release_title.py",
        "place": "scripts/u10_u13_modules/",
        "manifest_row": None,
        "role": ("the W5 RELEASE-TITLE TEMPLATE — the "
                 "anthology-release-title EMAIL + SMS generator (the §3 "
                 "release bus, the S3 TITLE stage's release): the "
                 "title-select deliverable PDF view + Doc edit links, the "
                 "byte-exact standing instruction, the stage selection "
                 "form link pre-filled with the default stage s3_gate "
                 "(the SAME default the W2 Title Fire sibling uses), the "
                 "link-only SMS shape, and the sign-off law"),
        "offline": "entirely — pure data generator, no network, no "
                   "credential",
        "exit_codes": "0/1/2/4/5",
    },
    {
        "name": "w7_release_chapter.py",
        "place": "scripts/u10_u13_modules/",
        "manifest_row": None,
        "role": ("the W7 RELEASE-CHAPTER TEMPLATE — the "
                 "anthology-release-chapter EMAIL + SMS generator (the "
                 "contract row of the same name, WIRED-AHEAD slug; fired "
                 "by gate_engine GATE_RELEASE_SLUG at the s5_producer "
                 "gate): the chapter deliverable PDF view + Doc edit "
                 "links, the two-editors'-rewrites-maximum reminder with "
                 "the rewrite-count of-2 phrase, the masked stage form "
                 "link (form id and minted anthology id ride as masked "
                 "markers, never values), and the link-only SMS"),
        "offline": "entirely — pure data generator, no network, no "
                   "credential",
        "exit_codes": "0/1/2/4/5",
    },
    {
        "name": "w8_release_rewrite.py",
        "place": "scripts/u10_u13_modules/",
        "manifest_row": None,
        "role": ("the W8 RELEASE-REWRITE TEMPLATE — the "
                 "anthology-release-rewrite EMAIL + SMS generator (the "
                 "contract row of the same name, WIRED-AHEAD slug; fired "
                 "at the s6_producer gate): the rewrite1 / rewrite2 "
                 "preservation-slot deliverable links, the rewrite budget "
                 "of TWO with the rewrite-count merge, the stage form "
                 "link with the ?anthology_id=<minted>&stage=s6 query "
                 "pair, the webhook url and hook-secret MERGE SLOTS by "
                 "label, and the link-only SMS"),
        "offline": "entirely — pure data generator, no network, no "
                   "credential",
        "exit_codes": "0/1/2/4/5",
    },
    {
        "name": "w9_release_cover.py",
        "place": "scripts/u10_u13_modules/",
        "manifest_row": None,
        "role": ("the W9 RELEASE-COVER TEMPLATE — the "
                 "anthology-release-cover EMAIL + SMS generator (the "
                 "contract row of the same name, WIRED-AHEAD slug; fired "
                 "by gate_engine GATE_RELEASE_SLUG at the s7_producer "
                 "gate): the FOUR cover-sample links (Signature / Bold "
                 "Editorial / Fine Art / Pure Type), the stage form link "
                 "pre-filled with the s7_cover stage token, the webhook "
                 "merges by label, and the link-only SMS"),
        "offline": "entirely — pure data generator, no network, no "
                   "credential",
        "exit_codes": "0/1/2/4/5",
    },
    {
        "name": "w10_release_final.py",
        "place": "scripts/u10_u13_modules/",
        "manifest_row": None,
        "role": ("the W10 RELEASE-FINAL TEMPLATE — the "
                 "anthology-release-final EMAIL + SMS generator (the "
                 "contract row of the same name, DOCTRINE slug; "
                 "STAGE-RUNNER-FIRED at the S8 stage): the final-chapter "
                 "deliverable PDF view + Doc edit links, the stage form "
                 "link pre-filled with the s8 stage token (the S8 "
                 "runner's own STAGE constant), the webhook merges by "
                 "label, and the link-only SMS"),
        "offline": "entirely — pure data generator, no network, no "
                   "credential",
        "exit_codes": "0/1/2/4/5",
    },
    {
        "name": "w11_delivered.py",
        "place": "scripts/u10_u13_modules/",
        "manifest_row": None,
        "role": ("the W11 DELIVERED TEMPLATE — the 'Anthology: Book "
                 "Delivered' EMAIL + SMS generator (the contract row of "
                 "the same name, DOCTRINE slug; the TERMINAL s9_producer "
                 "milestone): the manuscript PDF view + Doc edit links, "
                 "the stage form link pre-filled with the delivered stage "
                 "token, the webhook merges by label, and the link-only "
                 "SMS"),
        "offline": "entirely — pure data generator, no network, no "
                   "credential",
        "exit_codes": "0/1/2/4/5",
    },
    {
        "name": "w12_chapter_ready.py",
        "place": "scripts/u10_u13_modules/",
        "manifest_row": None,
        "role": ("the W12 CHAPTER-APPROVAL-READY TEMPLATE — the "
                 "producer-side notification generator (the contract "
                 "seat workflows.producer_notify_out_of_scope names the "
                 "existing producer-notify workflow 'Chapter Approval "
                 "Ready', trigger tag anthology-producer-chapter-ready; "
                 "notifies the PRODUCER, not the author): the chapter "
                 "deliverable PDF view + Doc edit links, the stage form "
                 "link pre-filled with the s5 stage token, and the "
                 "EMAIL-ONLY shape — actions exactly [\"send-email\"], no "
                 "SMS action and no webhook"),
        "offline": "entirely — pure data generator, no network, no "
                   "credential",
        "exit_codes": "0/1/2/4/5",
    },
    {
        "name": "main_skeleton.py",
        "place": "scripts/u10_u13_modules/",
        "manifest_row": None,
        "role": ("the U10/U13 TEMPLATE-LAW DISPATCHER — the offline-plan / "
                 "offline-self-test driver for the family: imports the "
                 "template modules BY NAME (importlib, never exec'd from a "
                 "path), enforces the fail-closed one-entry-point contract "
                 "(self_test(out) -> int), pins the module inventory and "
                 "the STAGE_CURSORS vocabulary, runs every module's own "
                 "battery plus the aggregate copy-law scan over every "
                 "generated string, and REFUSES a live-verify request "
                 "(exit 2 — the OFFLINE law)"),
        "offline": "entirely — the whole CLI surface (plan / render "
                   "aggregate / self-test) is OFFLINE",
        "exit_codes": "0/1/2/4/5",
    },
    {
        "name": "docs_workflows.py",
        "place": "scripts/u10_u13_modules/",
        "manifest_row": None,
        "role": ("THIS module — the family's README / documentation as an "
                 "importable fail-closed pure-data module: the thirteen "
                 "workflow seats, the copy rules, the module inventory, "
                 "the house exit codes, the doctrine, and the credential "
                 "labels; readme() renders FROM the same data the "
                 "self-test asserts against, so documentation and data "
                 "cannot drift; performs no I/O at import and holds no "
                 "credential"),
        "offline": "entirely — pure data; self-test is a read-only "
                   "filesystem drift gate",
        "exit_codes": "0/1/4",
    },
)

# ---------------------------------------------------------------------------
# HOUSE EXIT CODES (0/1/2/3/5; 4 = enforced violation). The exact contract
# the U10/U13 workflows family commits to; self-test pins all six.
# ---------------------------------------------------------------------------
EXIT_CODES = {
    0: "verified success — plan / render / self-test pass (the whole "
       "surface is OFFLINE: nothing is ever sent)",
    1: "unexpected error (top-level guard; never a secret leak)",
    2: ("STOP refusal — a BUILD without --execute (the Trevor gate, "
        "AF-AE-U10-U13-NO-EXECUTE: the build reports the plan and exits "
        "without writing anything) / usage / a live-verify request (this "
        "family is OFFLINE BY CONSTRUCTION; there is no live surface to "
        "gate, AF-AE-U10-U13-OFFLINE) / the template-module assembly "
        "incomplete (AF-AE-U10-U13-ASSEMBLY-INCOMPLETE: a module the "
        "inventory names that does not ship, or a shipped template that "
        "is not in the set) / an out-of-vocabulary stage token or an "
        "unknown form slug (never a fabricated token)"),
    3: "HELD — unused by this family: template generation is OFFLINE, so "
       "a dependency or transport state is never consulted (kept for the "
       "house 0/1/2/3/5 law)",
    4: ("self-test FAILED (the AF-AE-TEMPLATE-ATTACK enforced-violation "
        "family — a tamper never masquerades as exit 1)"),
    5: ("data or copy-law mismatch — a generated string carrying an "
        "em-dash, a banned byline actor, an unbalanced merge slot, a "
        "code fence, or a secret-shaped fragment (AF-AE-COPY-LAW; the "
        "fail-closed default — never a printed payload, never exit 0)"),
}

# ---------------------------------------------------------------------------
# THE AF AUTOfail FAMILY of the U10/U13 workflows tooling — the codes the
# family's own surfaces declare. The family's own manifest rows are NOT yet
# stamped in ENGINE-MANIFEST.json (PENDING — verified at ship time,
# 2026-08-11); AF-AE-READBACK-MISMATCH and AF-AE-TEMPLATE-ATTACK already
# live in the manifest. Self-test failures are exit 4, never 1.
# ---------------------------------------------------------------------------
AF_CODES = (
    ("AF-AE-U10-U13-ASSEMBLY-INCOMPLETE", 2,
     "the template-module set named in the dispatcher's inventory is not "
     "fully present, or a module violates the one-entry-point contract, "
     "or a shipped template file is not in the set — a template law is "
     "never silently skipped (not yet stamped in ENGINE-MANIFEST.json)"),
    ("AF-AE-U10-U13-NO-EXECUTE", 2,
     "a BUILD (the family's one write surface: the 13 template documents "
     "plus the manifest-pending stage) was requested WITHOUT --execute — "
     "the Trevor gate: the build reports the plan and exits without "
     "writing anything, never a silent rewrite and never a silent no-op"),
    ("AF-AE-U10-U13-OFFLINE", 2,
     "a live-verify request on the U10/U13 family — template generation "
     "is OFFLINE by construction and there is no live surface to gate; "
     "a verify request is a usage STOP, never a silent network probe"),
    ("AF-AE-COPY-LAW", 5,
     "an em-dash, a banned byline actor, an unbalanced merge slot, a "
     "code fence, or a secret-shaped fragment in a generated string — "
     "never a printed payload, and never exit 0 (the fail-closed default "
     "of the copy law)"),
    ("AF-AE-TEMPLATE-ATTACK", 4,
     "an attack fixture tripped the OFFLINE self-test of a family module "
     "or battery (enforced violation — the house code, shared with the "
     "U02 / U03 / U04 / U05 / U06 / U07 / U08_U09 families)"),
)

# ---------------------------------------------------------------------------
# DOCTRINE — the house rules the whole U10/U13 workflows tooling commits
# to, as data so the README renders them from the same source the self-test
# asserts.
# ---------------------------------------------------------------------------
DOCTRINE = (
    ("Offline by construction", "template generation is OFFLINE: plan / "
     "render / self-test run with zero network and zero credential; "
     "rendering is PURE (same inputs -> same bytes); a live-verify "
     "request is a usage STOP (exit 2, AF-AE-U10-U13-OFFLINE), never a "
     "silent network probe; the BUILD (13 template documents + the "
     "manifest-pending stage) is the family's ONE write surface and it "
     "is Trevor-gated: without --execute it is a usage STOP (exit 2, "
     "AF-AE-U10-U13-NO-EXECUTE) that writes nothing, never a silent "
     "rewrite; nothing here ever sends a message"),
    ("Editors, never AI", "'editors' and 'editorial team' are the ONLY "
     "byline actors; the banned words and every model / tool name are "
     "ABSENT from every generated string (the single enforcement-context "
     "exception is the module docstrings, which are not generated "
     "copy)"),
    ("Zero em-dashes", "U+2014 is FORBIDDEN in every generated string; "
     "every sentence uses commas, periods, or a colon instead; a "
     "rendered string that carries one is a ValueError at generation "
     "time"),
    ("Sign-off", "the email sign-off is exactly 'The Editors' or the "
     "producer-name merge {{ custom_values.producer }} — never a "
     "person's raw name and never a model persona; SMS never carries a "
     "sign-off (the SMS shape law: one warm sentence plus ONE link)"),
    ("Secrets", "the family RESOLVES NOTHING: no PIT, no location, no "
     "token, no env secret on any surface — a template generator cannot "
     "print a token it never holds; the webhook URL and Authorization "
     "header ride the REPLACE-ME location custom-value merges ONLY "
     "(never-a-real-token); a secret-shaped fragment (Bearer / sk- / a "
     "JWT / pit-<value>) anywhere is a refusal, never a print; the "
     "engine-wide credentials resolve BY LABEL only, form and location "
     "ids are MASKED to their last 4 characters on every report"),
    ("Single authority", "a law is read once, in one module: "
     "copy_rules.py owns the copy law and the deny machinery, the "
     "dispatcher pins the STAGE_CURSORS vocabulary read once from "
     "anthology_state.py, gate_engine owns the gate / decision "
     "vocabulary, the snapshot contract owns copy_law and "
     "release_notifications, field-map.json owns the deliverable link "
     "fields, and the generators derive from them, never re-implement; "
     "a drift in an authority breaks the family's self-tests FIRST"),
    ("Fail-closed", "a missing module, a drifted vocabulary, an "
     "unreadable contract, or a law violation is a REFUSAL or a recorded "
     "FAIL — never a blind pass, never a fabricated success; a template "
     "that cannot prove itself offline is never trusted at render time; "
     "an id is NEVER guessed from memory"),
    ("Move in silence", "operator-verbose only; NOTHING Anthropic in any "
     "runtime file; Convert and Flow naming in every client surface; "
     "STDLIB ONLY; calls NO model; never a client PII; READ-ONLY by "
     "doctrine — the family's write surface is the Skill 44 caf build "
     "rail at build time, never a module here"),
)

# ---------------------------------------------------------------------------
# CREDENTIAL LABELS — BY LABEL ONLY. These are the label NAMES the engine's
# live surfaces resolve through anthology_registry (live process env first,
# then the three canonical client env stores). A label is a name, never a
# value; the values they resolve to are never held here and never printed
# anywhere. The U10/U13 workflows family itself holds NO credential surface
# at all — the labels are recorded so the README documents where the
# engine's live surfaces resolve them.
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

# The pinned form-id VALUES of the forms the family's links reference —
# location identifiers, never secrets, but they NEVER ride this
# documentation surface: the WORKFLOWS rows above carry the pin in prose
# where a row names its form, and the self-test proves no id VALUE rides
# the rendered README (the same masked-marker policy the U06/U07/U08_U09
# modules enforce). Recorded here so the self-test can assert the markers
# really are the last-4 markers of the family's live-verified pins
# (forms_check.py FORM_ID_BY_SLUG — the SAME pins the w1/w2/w5 siblings
# and title_select_builder.py ship against).
PINNED_FORM_IDS = {
    "universal-intake": "U65pwoeMTy1niMqllKWG",
    "universal-review": "riNlAkYbcW3g92VRLqq0",
    "title-select": "UgiiSoZsA4vyqOVfO5fi",
}

# The exact stage-token vocabulary (anthology_state.STAGE_CURSORS — the
# same tuple the dispatcher pins; the stage a release / review link
# pre-fills must be EXACTLY one of these; an out-of-vocabulary token is a
# refusal, never a fabricated token). The self-test asserts byte-equality
# against the dispatcher's own pin, so the two can never drift.
STAGE_VOCABULARY = (
    "s0_intake", "s1_avatar", "s1_gate", "s2_tone", "s2_gate",
    "s3_title", "s3_gate", "s4_blurb_outline", "s4_gate_producer",
    "s4_gate_participant", "s5_chapter", "s5_gate", "s6_rewrite",
    "s7_cover", "s8_deliver", "s9_wait_assembly", "approved",
    "delivered", "held", "exception",
)

# Pinned counts (the fixture-counting discipline of golden_fields.py: a
# drifted inventory is drift, never tolerated). Adding a module to the
# U10/U13 workflows tooling REQUIRES adding it here AND to the README's
# inventory.
CONTRACT_WORKFLOW_COUNT = 13
CONTRACT_MODULE_COUNT = 16
CONTRACT_MODULE_OWNED_COUNT = 11

class DocsError(Exception):
    """A fail-closed documentation refusal: the README data drifted from
    its own contract, so no catalog is shipped — wrong docs are worse than
    no docs."""

# ---------------------------------------------------------------------------
# Accessors — deep copies, so callers can never mutate the canonical data.
# ---------------------------------------------------------------------------
def workflows() -> list:
    """The thirteen workflow-seat rows as a mutable deep copy (callers may
    mutate their copy; the canonical tuple is never touched)."""
    return [dict(row) for row in WORKFLOWS]

def copy_rules() -> dict:
    """The copy rules as a plain dict copy."""
    return json.loads(json.dumps(COPY_RULES))

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

def stage_vocabulary() -> list:
    """The exact stage-token vocabulary as a mutable list."""
    return list(STAGE_VOCABULARY)

# ---------------------------------------------------------------------------
# The rendered README — built FROM the data, so prose can never drift from
# the contract. This is the machine-readable form of the module docstring.
# ---------------------------------------------------------------------------
def readme() -> str:
    """The U10/U13 workflows-family README, rendered from the structured
    data above.

    One markdown document: what the tooling is, the thirteen workflow
    seats and their laws, the copy rules, the module inventory, the house
    exit codes, the autofail family, the doctrine, and the credential
    labels. Because every section renders from the same constants the
    self-test asserts, a drift in the data FAILS the self-test before it
    can ship a stale README. Form ids ride the rendered README BY MASKED
    MARKER only — the id VALUE never surfaces (proven by the self-test)."""
    lines = [
        "# U10/U13 workflows-family tooling — the thirteen workflows, one "
        "template generator per seat, under the copy rules (README)",
        "",
        "Shipped under the ENGINE-MANIFEST.json row-54 \"template live "
        "verify (U02)\" shipping doctrine (%s; the family's OWN manifest "
        "rows are PENDING — not yet stamped, staged under the "
        "manifest-pending/u02.json · u03.json · u04.json · u05.json · "
        "u06.json · u07.json · u08_u09.json pattern) — the family's "
        "driver is `main_skeleton.py` (the offline-plan / offline-"
        "self-test dispatcher, the delivery_report.py row-12 "
        "sibling-helper pattern) plus the eleven template generators, the "
        "canonical copy-law module `copy_rules.py`, the webhook-body "
        "builder `webhook_body.py`, and this documentation module in "
        "`scripts/u10_u13_modules/` — documented machine-side by this "
        "module (`u10_u13_modules.docs_workflows`)."
        % U10_U13_SHIPPING_VERSION,
        "",
        "The family owns the FAIL-CLOSED CLIENT-FACING TEMPLATE-LAW of "
        "the engine: every sanctioned release-notification email and SMS "
        "is a JSON/Python data generator that renders OFFLINE — zero "
        "network, zero credentials, nothing ever sent — under Trevor's "
        "copy law, and every generated string is proven law-clean at "
        "generation time, never at send time. The send path (nudge_send "
        ".py / the Skill 44 caf delivery rail) fills the rendered slots "
        "at send time; no template module ever touches the wire, a "
        "token, an env secret, or a credential store.",
        "",
        "## The thirteen workflow seats (the fixed inventory; each "
        "module-owned seat is ONE template generator, one module per "
        "seat)",
        "",
    ]
    for row in WORKFLOWS:
        owner = row.get("module")
        if owner:
            seat = "module %s" % owner
        else:
            pending = row.get("pending_module")
            if pending:
                seat = "documented seat (%s)" % pending
            else:
                seat = "documented seat (not owned here)"
        lines.append("%d. **%s** — %s. Trigger: %s. Actions: %s. Stage "
                     "token: %s. Deliverable: %s. Form: %s."
                     % (row["seat"], row["name"], seat, row["trigger"],
                        row["actions"], row["stage"], row["deliverable"],
                        row["form"]))
        lines.append("")
    lines += [
        "## Copy rules (workflows.copy_law — Trevor's verbatim law for "
        "every client-facing word; enforced at GENERATION time)",
        "",
    ]
    lines.append("- Editors, never AI: the ONLY byline actors are "
                 "\"editors\" and \"editorial team\"; %s are banned."
                 % ", ".join(COPY_RULES["editors_never_ai"]["banned_words"]))
    lines.append("- Zero em-dashes: %s is forbidden in every generated "
                 "string." % COPY_RULES["no_em_dashes"]["banned_character"])
    lines.append("- Sign-off: \"%s\" or %s only, never a persona name."
                 % (COPY_RULES["sign_off"]["editors"],
                    COPY_RULES["sign_off"]["producer_merge"]))
    lines.append("- Standing instruction (byte-exact, in every release "
                 "email): \"%s\"" % COPY_RULES["standing_instruction"])
    lines.append("- Stage form link: "
                 "<forms_base>/widget/form/<form_id>?%s=<minted>&%s=<stage> "
                 "— the U08 pre-fill law (the TWO query params pre-fill "
                 "the form's HIDDEN fields client-side); the G3 key law: "
                 "the query key is EXACTLY \"anthology_id\", never "
                 "\"anthology_active_id\"; the stage token is always an "
                 "exact STAGE_CURSORS vocabulary member."
                 % (COPY_RULES["stage_form_link"]["query_keys"][0],
                    COPY_RULES["stage_form_link"]["query_keys"][1]))
    lines.append("- Per-stage links: each email carries that stage's PDF "
                 "(VIEW) link plus the editable Google Doc (EDIT) link "
                 "from the matching field-map.json deliverable_fields "
                 "contact custom fields; the SMS carries ONLY the doc "
                 "link.")
    lines.append("- Warm language: the email greets the author by name "
                 "(%s) and closes warm (\"%s\") before the sanctioned "
                 "sign-off." % (COPY_RULES["warm_language"]
                                ["greeting_merge"],
                                COPY_RULES["warm_language"]["warm_close"]))
    lines.append("- Never a token: the webhook URL and its Authorization "
                 "header ride the REPLACE-ME location custom-value merges "
                 "ONLY (%s and %s) — never an inlined URL, never an "
                 "inlined token; a secret-shaped fragment anywhere in a "
                 "generated string is a refusal, never a print."
                 % (COPY_RULES["no_tokens"]["webhook_url_merge"],
                    COPY_RULES["no_tokens"]["hook_secret_merge"]))
    lines += [
        "",
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
    """The on-disk path a README inventory row claims. Every u10_u13 row
    lives next to this module (scripts/u10_u13_modules/)."""
    base = Path(__file__).resolve().parent
    if row.get("place", "").strip("/") == "scripts":
        base = base.parent
    return base / row["name"]

def _self_test_body(dev) -> None:
    dev.write("[docs-workflows] pinning: %d workflow seats, %d modules, "
              "%d module-owned seats, exit codes 0..5\n"
              % (CONTRACT_WORKFLOW_COUNT, CONTRACT_MODULE_COUNT,
                 CONTRACT_MODULE_OWNED_COUNT))

    wrows = WORKFLOWS
    if len(wrows) != CONTRACT_WORKFLOW_COUNT:
        raise AssertionError(
            "WORKFLOWS carries %d rows, contract is %d — the U10/U13 "
            "workflow list drifted; refusing to ship a stale README."
            % (len(wrows), CONTRACT_WORKFLOW_COUNT))
    seen_seats = set()
    for row in wrows:
        seat = row.get("seat")
        if not isinstance(seat, int) or seat in seen_seats:
            raise AssertionError(
                "WORKFLOWS seat numbers must be unique integers, got %r"
                % seat)
        seen_seats.add(seat)
        for key in ("name", "module", "trigger", "actions", "stage",
                    "deliverable", "form"):
            if key == "module":
                value = row.get(key)
                if value is not None and (not isinstance(value, str)
                                          or not value):
                    raise AssertionError(
                        "WORKFLOWS row %d lost its %r field — the workflow "
                        "contract is incomplete." % (seat, key))
            elif not isinstance(row.get(key), str) or not row[key]:
                raise AssertionError(
                    "WORKFLOWS row %d lost its %r field — the workflow "
                    "contract is incomplete." % (seat, key))
        if row.get("module") is None and not row.get("pending_module") \
                and not row.get("owned_elsewhere"):
            raise AssertionError(
                "WORKFLOWS row %d has no owning module and no pending or "
                "owned-elsewhere note — a seat that neither ships nor "
                "documents its status is drift." % seat)
        if row["module"] is not None and row["module"] not in MODULE_OWNED_SEATS:
            raise AssertionError(
                "WORKFLOWS row %d names module %r which is not in the "
                "module-owned seat set." % (seat, row["module"]))
    if seen_seats != set(range(1, CONTRACT_WORKFLOW_COUNT + 1)):
        raise AssertionError(
            "WORKFLOWS seat numbers must be exactly 1..%d, got %s"
            % (CONTRACT_WORKFLOW_COUNT, sorted(seen_seats)))
    if len(MODULE_OWNED_SEATS) != CONTRACT_MODULE_OWNED_COUNT:
        raise AssertionError(
            "MODULE_OWNED_SEATS carries %d rows, contract is %d."
            % (len(MODULE_OWNED_SEATS), CONTRACT_MODULE_OWNED_COUNT))
    owned = [r["module"] for r in wrows if r["module"] is not None]
    if sorted(owned) != sorted(MODULE_OWNED_SEATS):
        raise AssertionError(
            "the module-owned seat set drifted from the WORKFLOWS rows.")

    # The stage tokens the rows claim must be EXACTLY the modules' OWN
    # STAGE / DEFAULT_STAGE constants (each generator's stage-form link
    # law) — and each must be a token the intake router accepts: either an
    # exact STAGE_CURSORS vocabulary member or a stage-runner STAGE
    # constant (the short s5 / s6 / s8 / delivered tokens the S5/S6/S8
    # runners carry, which intake_router.classify_stage accepts by name —
    # a self-describing per-stage form). An out-of-vocabulary token in a
    # doc row is the same drift the generators refuse — never a fabricated
    # token.
    vocab = set(STAGE_VOCABULARY)
    runner_tokens = {"s5", "s6", "s8", "delivered"}
    for row in wrows:
        stage = row["stage"]
        if stage not in vocab and stage not in runner_tokens:
            raise AssertionError(
                "WORKFLOWS row %d claims stage token %r which is neither "
                "an exact STAGE_CURSORS member nor a runner STAGE token — "
                "an out-of-vocabulary stage is a refusal, never a "
                "documented token." % (row["seat"], stage))

    # The stage vocabulary itself never drifts from the dispatcher's own
    # pin (main_skeleton.STAGE_VOCABULARY — the same tuple the generators
    # refuse against; a drifted vocabulary breaks the docs self-test
    # FIRST).
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import main_skeleton as ms  # noqa: E402
    except Exception as exc:  # noqa: BLE001 — importability is the law, the reason is surfaced
        raise AssertionError(
            "main_skeleton cannot be imported to pin the stage vocabulary "
            "(%s: %s) — refusing to ship a stale README."
            % (type(exc).__name__, exc))
    if tuple(ms.STAGE_VOCABULARY) != STAGE_VOCABULARY:
        raise AssertionError(
            "the docs stage vocabulary drifted from main_skeleton."
            "STAGE_VOCABULARY — the STAGE_CURSORS law is load-bearing; "
            "refusing to ship a stale README.")

    # The copy rules never drift from the family's OWN canonical source
    # (copy_rules.py — the single implementation of the law).
    try:
        import copy_rules as cr  # noqa: E402 — same directory
    except Exception as exc:  # noqa: BLE001
        raise AssertionError(
            "copy_rules cannot be imported to pin the copy rules (%s: %s) "
            "— refusing to ship a stale README." % (type(exc).__name__, exc))
    if cr.SANCTIONED_WORD != COPY_RULES["editors_never_ai"]["sanctioned_word"]:
        raise AssertionError(
            "the docs sanctioned word drifted from copy_rules.SANCTIONED_WORD")
    if tuple(cr.BANNED_WORDS) != COPY_RULES["editors_never_ai"]["banned_words"]:
        raise AssertionError(
            "the docs banned words drifted from copy_rules.BANNED_WORDS")
    if cr.SIGN_OFF != COPY_RULES["sign_off"]["editors"]:
        raise AssertionError(
            "the docs editors sign-off drifted from copy_rules.SIGN_OFF")
    if cr.STANDING_INSTRUCTION != COPY_RULES["standing_instruction"]:
        raise AssertionError(
            "the docs standing instruction drifted from copy_rules."
            "STANDING_INSTRUCTION")

    # The pinned form-id markers the WORKFLOWS prose carries are the
    # last-4 markers of the family's own live-verified pins (the SAME pins
    # forms_check.py / the w1/w2/w5 siblings ship against) — and NO full
    # id VALUE may ever ride the rendered README (masked markers only, the
    # U06/U07 policy).
    pins = PINNED_FORM_IDS
    rendered_ids = json.dumps(list(pins.values()))
    if any(fid in rendered for fid in pins.values()
           for rendered in [readme()]):
        raise AssertionError(
            "a pinned form id VALUE rides the rendered README — masked "
            "markers only, never a value (the U06/U07 policy).")

    mods = MODULES
    if len(mods) != CONTRACT_MODULE_COUNT:
        raise AssertionError(
            "MODULES carries %d rows, contract is %d — a U10/U13 module "
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

    # Every module-owned workflow seat must also be documented as a
    # shipped file (belt and braces over the WORKFLOWS rows).
    for name in MODULE_OWNED_SEATS:
        f = Path(__file__).resolve().parent / (name + ".py")
        if not f.is_file():
            raise AssertionError(
                "module-owned seat %s does not ship at %s — the workflow "
                "inventory drifted from the tree." % (name, f))

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

    if not STAGE_VOCABULARY or len(STAGE_VOCABULARY) != len(set(STAGE_VOCABULARY)):
        raise AssertionError(
            "STAGE_VOCABULARY must carry unique, non-empty stage tokens.")

    # The browser-UA doctrine is pinned byte-equal to the registry — a
    # registry regression is caught HERE first (the engine's live surfaces
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
    for row in WORKFLOWS:
        if row["name"] not in rendered:
            raise AssertionError(
                "readme() no longer renders workflow seat %r — the README "
                "drifted from WORKFLOWS." % row["name"])
    for row in MODULES:
        if row["name"] not in rendered:
            raise AssertionError(
                "readme() no longer renders module %r — the README drifted "
                "from MODULES." % row["name"])
    for code in sorted(EXIT_CODES):
        if str(code) + " —" not in rendered:
            raise AssertionError(
                "readme() no longer renders exit code %d." % code)
    # A real credential value is pit- followed by alphanumerics; the
    # doctrine's own literal template "pit-<value>" is the SHAPE
    # description, never a credential, and must not trip the scan.
    if re.search(r"pit-[A-Za-z0-9]+", rendered):
        raise AssertionError(
            "the rendered README carries a credential-shaped string — "
            "REFUSED without printing it (the never-a-real-token "
            "doctrine).")
    if any(str(v) in rendered for v in pins.values()):
        raise AssertionError(
            "a pinned form id VALUE rides the rendered README — masked "
            "markers only (the U06/U07 policy).")

    dev.write("[docs-workflows] PASS — README data and shipped tree agree "
              "(%d workflow seats, %d modules, exit 0..5, %d af codes, "
              "form id values never surfaced).\n"
              % (len(wrows), len(mods), len(codes)))

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
        sys.stderr.write("[docs-workflows] SELF-TEST FAILED "
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
        prog="docs_workflows.py",
        description="U10/U13 workflows-family documentation module — README, "
                    "the thirteen workflow seats, the copy rules, module "
                    "inventory, exit codes, doctrine, credential labels "
                    "(pure data; nothing to leak).")
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
            "dispatcher": U10_U13_DISPATCHER,
            "manifest_row": U10_U13_MANIFEST_ROW,
            "shipping": U10_U13_SHIPPING_VERSION,
            "workflows": workflows(),
            "copy_rules": copy_rules(),
            "modules": modules(),
            "exit_codes": exit_codes(),
            "af_codes": af_codes(),
            "doctrine": [{"name": n, "text": t} for n, t in DOCTRINE],
            "stage_vocabulary": stage_vocabulary(),
            "credential_labels": {k: list(v)
                                  for k, v in CREDENTIAL_LABELS.items()},
            "note": "pure data — no credential value is held or printed; "
                    "form ids by masked marker only, never by value; the "
                    "U10/U13 manifest rows are PENDING",
        }, indent=2, sort_keys=True))
        return EX_OK
    except Exception as exc:  # noqa: BLE001 — top-level guard, never leaks a secret
        sys.stderr.write("[docs-workflows] unexpected error: %s: %s\n"
                         % (type(exc).__name__, exc))
        return EX_ERR

if __name__ == "__main__":
    sys.exit(main())
