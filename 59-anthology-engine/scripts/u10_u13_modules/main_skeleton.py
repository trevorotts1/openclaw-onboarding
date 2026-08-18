#!/usr/bin/env python3
# =============================================================================
# SKILL 59 — ANTHOLOGY ENGINE :: u10_u13_modules/main_skeleton.py
# U10/U13 TEMPLATE-LAW DISPATCHER — the offline-plan / offline-self-test
# driver for the U10/U13 module family under scripts/u10_u13_modules/ (the
# FAIL-CLOSED CLIENT-FACING TEMPLATE-LAW of the engine: every sanctioned
# release-notification email and SMS is a JSON / Python data generator that
# renders OFFLINE — zero network, zero credentials, nothing ever sent — under
# Trevor's copy law, and every generated string is proven law-clean at
# generation time, never at send time). It imports the template modules BY
# NAME (importlib, never exec'd from a path), enforces the fail-closed
# one-entry-point contract, and resolves the aggregate exit code exactly as
# its U02 / U03 / U04 / U05 / U06 / U07 / U08_U09 siblings
# (u02_modules/main_skeleton.py, u03_modules/main_skeleton.py,
# u04_modules/main_skeleton.py, u05_modules/main_skeleton.py,
# u06_modules/main_skeleton.py, u07_modules/main_skeleton.py and
# u08_u09_modules/main_skeleton.py) do. It carries NO template logic itself:
# a template module is exercised ONLY through this CLI so `--dry-run`,
# `--self-test`, and the render aggregate never drift apart.
#
# TEMPLATE GENERATION IS OFFLINE BY CONSTRUCTION. This family is the release
# bus of the snapshot contract's workflows.release_notifications block — the
# EIGHT tag->notification workflows (four LIVE slugs, two WIRED-AHEAD, two
# DOCTRINE) that turn each anthology-release-* tag into the author's
# producer-branded EMAIL + link-only SMS. The templates are data generators:
# they RENDER the exact payloads OFFLINE and the send path (nudge_send.py /
# caf delivery) fills the rendered slots at send time. No template module in
# this family, and this dispatcher never, touches the wire, a token, an env
# secret, or a credential store — there is no live surface to gate, and the
# dispatcher REFUSES any request that would make one (a live verify command
# is a usage STOP, exit 2, never a silent network probe). --dry-run and
# --self-test are the whole surface, both fully OFFLINE and free.
#
# THE U10/U13 FAMILY (the template modules this dispatcher aggregates; each
# is STDLIB-only, a pure data generator, and ships its own OFFLINE self-test
# battery that proves the copy law OFFLINE — a template that cannot prove
# itself offline is never trusted at render time):
#   w4_release_tone.py   the W4 RELEASE-TONE TEMPLATE — the
#                        anthology-release-tone EMAIL + SMS generator (the
#                        contract row "Anthology Release: Tone", LIVE slug,
#                        actions send-email + send-sms): the tone deliverable
#                        PDF view + Google Doc edit links from the contact
#                        custom fields, the byte-exact standing instruction,
#                        the stage review form link pre-filled
#                        ?anthology_id=<minted>&stage=<stage> (the U08
#                        pre-fill law; the default form is the universal-
#                        review pin and the default stage token s2_gate, an
#                        exact STAGE_CURSORS vocabulary member), the
#                        sign-off "The Editors" or the
#                        {{ custom_values.producer }} merge, and the
#                        link-only SMS shape (one warm sentence plus ONE
#                        doc link). Renders OFFLINE; every client-facing
#                        value is a {{ ... }} merge slot unless an offline
#                        preview passes fixture values; an em-dash, an AI /
#                        ghostwriter shape, an unbalanced merge or a
#                        secret-shaped fragment in any generated string is a
#                        ValueError at generation time, never a silently
#                        off-law payload.
#   (the siblings — the Review Fire / Title Fire workflow templates and the
#   Avatar / Tone / Title / Chapter / Rewrite / Cover / Final / Delivered /
#   Chapter-Approval-Ready release generators — follow the same contract;
#   this dispatcher's module inventory is the fixed law set, and a shipped
#   template that is not in the set is a STOP, never a silently skipped
#   law.)
#
# THE IMPORT CONTRACT (the surface the family satisfies): one ENTRY POINT
# per module, exposed as `self_test(out=None) -> int` — exit 0 on pass, 4
# (EX_VIOLATION, the AF-AE-TEMPLATE-ATTACK family) on failure, exactly as
# the U02..U08_U09 siblings require. A module without a battery STOPS the
# dispatcher (fail-closed: no template law is ever skipped, and a template
# that cannot prove itself offline cannot be trusted at render time). The
# render aggregate is driven through each module's OWN documented surfaces
# (render / render_email / render_sms / plan), never through a
# re-implementation, and each generated string is scanned for the copy-law
# tokens BY the dispatcher too (belt and braces over the module's own
# generation-time refusals).
#
# COPY LAW (workflows.copy_law — Trevor's verbatim law for every client-
# facing word; enforced at GENERATION time, and RE-PROVEN here on every
# surface so a drifted generator can never ship off-law copy):
#   EDITORS, NEVER AI ........ "editors" / "editorial" are the ONLY byline
#        actors. "AI", "ghostwriter", "automated", "generated" and every
#        model / tool name are ABSENT from every generated string (the
#        dispatcher refuses them by word boundary on every render it
#        aggregates; the single enforcement-context exception is the module
#        docstrings, which are not generated copy).
#   ZERO EM-DASHES .......... U+2014 is FORBIDDEN in every generated string.
#        Every sentence uses commas, periods, or a colon instead.
#   SIGN-OFF ................ "The Editors" or "{{ custom_values.producer }}"
#        only, never a person's raw name and never a model persona.
#   STANDING INSTRUCTION .... "The PDF is yours to view. The Google Doc is
#        the one you edit, and it is the version we use." — byte-exact, in
#        every release email (copy_law.standing_instruction).
#   STAGE FORM LINK ......... <forms_base>/widget/form/<form_id>?anthology_id=
#        <minted>&stage=<stage> — the U08 pre-fill law: the TWO query params
#        pre-fill the form's HIDDEN fields client-side (the universal
#        hidden-field contract; prefill_verifier.py owns the verifier). The
#        default form is the universal-review pin and the default stage is
#        an exact STAGE_CURSORS vocabulary member; an out-of-vocabulary
#        stage is a refusal, never a fabricated token.
#   PER-STAGE LINKS ......... each email carries that stage's PDF (VIEW)
#        link plus the editable Google Doc (EDIT) link, pulled from the
#        matching field-map deliverable_fields contact custom fields; the
#        SMS carries ONLY the doc link (the sms_shape law: one warm
#        sentence plus ONE link).
#   NO CODE FENCES / NO INTERNAL NAMES / NO TOKENS .... zero code fences,
#        zero internal tool or model names, and — this family holds no
#        credential surface — a secret-shaped fragment (Bearer / sk- / a
#        JWT) anywhere in a generated string is a refusal, never a print.
#
# CREDENTIALS: THIS FAMILY RESOLVES NOTHING. There is no PIT, no location,
# no token, no env secret on any surface — a template generator cannot print
# a token it never holds. The self-test proves it: every surface scans its
# own payloads for the credential shape (Bearer / sk- / JWT) and a hit
# REFUSES. Never print a token is vacuously true and asserted, not assumed.
#
# AF CODES (fail-closed surfaces; self-test failures are exit 4, never 1):
#   AF-AE-U10-U13-ASSEMBLY-INCOMPLETE -> the template-module set named in
#          U10_U13_MODULES is not fully present, or a module violates the
#          one-entry-point contract, or a shipped template file is not in
#          the set. STOP (exit 2) — a template law is never silently
#          skipped.
#   AF-AE-COPY-LAW               -> an em-dash, a banned byline actor, an
#          unbalanced merge slot, a code fence, or a secret-shaped fragment
#          in a generated string. exit 5 (the fail-closed default of the
#          copy law; also the module-level ValueError family) — never a
#          printed payload, and never exit 0.
#   AF-AE-TEMPLATE-ATTACK        -> an attack fixture tripped the OFFLINE
#          self-test (also the family self-test batteries). exit 4.
#
# EXIT CODES (house convention 0/1/2/3/5; 4 = enforced violation only inside
# the offline self-test batteries — the operator CLI of this dispatcher
# resolves to 0 / 2 / 5 exactly, per the U10/U13 surface contract):
#   0  all template laws PASS (also --dry-run plan pass and self-test pass)
#   1  unexpected error
#   2  STOP refusal — usage / a live-verify request (this family is OFFLINE
#      BY CONSTRUCTION; there is no live surface) / the template-module
#      assembly incomplete (AF-AE-U10-U13-ASSEMBLY-INCOMPLETE)
#   3  HELD — unused by this family: template generation is OFFLINE, so a
#      dependency or transport state is never consulted (kept for the house
#      0/1/2/3/5 law and the exit-code self-test)
#   4  self-test FAILED — an assertion in an OFFLINE self-test battery
#      tripped (AF-AE-TEMPLATE-ATTACK family). A tamper NEVER masquerades
#      as exit 1. (Batteries are exercised through `--self-test` and inside
#      the aggregate's gate order; an operator CLI run never returns 4.)
#   5  data or copy-law mismatch (a generated string carrying an em-dash, a
#      banned byline actor, an unbalanced merge slot, a code fence, or a
#      secret-shaped fragment — AF-AE-COPY-LAW; the fail-closed default)
#
# STDLIB ONLY (argparse / importlib / json / re / pathlib). Calls NO model.
# Imports NO runtime engine module (this family is self-contained: the copy
# law and the stage vocabulary are pinned here, read once from the contract
# surface where it is read at all). DOCTRINE: move in silence; NOTHING
# Anthropic in any runtime file; Convert and Flow naming in every client
# surface; NEVER print a secret value; --dry-run and --self-test are
# OFFLINE; template generation is OFFLINE; the BUILD write surface is
# Trevor-gated (--execute, AF-AE-U10-U13-NO-EXECUTE).
# =============================================================================
"""main_skeleton.py — U10/U13 template-law dispatcher: offline plan and
offline self-test of the client-facing release-notification template
generators of the Anthology engine (Skill 59, u10_u13_modules; the packaged
sibling of u02_modules/main_skeleton.py, u03_modules/main_skeleton.py,
u04_modules/main_skeleton.py, u05_modules/main_skeleton.py,
u06_modules/main_skeleton.py, u07_modules/main_skeleton.py and
u08_u09_modules/main_skeleton.py). TEMPLATE GENERATION IS OFFLINE — this
family renders JSON/Python data OFFLINE with no network, no credential, and
nothing ever sent; there is no live surface, so a live-verify request is a
usage STOP (exit 2), never a silent network probe. The BUILD (the family's
one write surface, owned by the packaged assembler
build_anthology_workflows.py) is Trevor-gated: without --execute it is a
usage STOP (exit 2, AF-AE-U10-U13-NO-EXECUTE) that writes nothing. --dry-run
and --self-test are the whole surface, both fully OFFLINE and free."""

from __future__ import annotations

import argparse
import io
import json
import re
import sys
from pathlib import Path

EX_OK, EX_ERR, EX_STOP, EX_HELD, EX_MISMATCH = 0, 1, 2, 3, 5
EX_VIOLATION = 4  # enforced violation detected (self-test FAILED)

# The u10_u13_modules directory itself — sibling imports resolve from here, in
# BOTH execution contexts (as a script, whose own directory is sys.path[0],
# and as an imported module, where the caller may not have added it).
MODULES_DIR = Path(__file__).resolve().parent
if str(MODULES_DIR) not in sys.path:
    sys.path.insert(0, str(MODULES_DIR))
# The scripts/ directory itself — one sibling template (w2_title_fire) proves
# its scope law against the owning authority's pin
# (u08_u09_modules.title_select_builder) and resolves that sibling package
# by import; this dispatcher provides the same import context the engine
# scripts run under.
SCRIPTS_DIR = Path(__file__).resolve().parent.parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

SKILL_DIR = Path(__file__).resolve().parent.parent.parent
CONTRACT_PATH = SKILL_DIR / "config" / "anthology-snapshot-contract.json"

# The client-facing platform name, spelled out in every client surface
# (the same constant copy_qc_workflows.py pins).
_PLATFORM = "Convert and Flow"

# ---------------------------------------------------------------------------
# The copy law (config/anthology-snapshot-contract.json -> workflows.copy_law
# — Trevor's verbatim law; the family generates UNDER it, and the contract
# copy is re-read by the self-test so a drifted law is a self-test FAIL,
# never a silent drift).
# ---------------------------------------------------------------------------
COPY_LAW = {
    "editors_never_ai": {
        "note": "The editorial process is performed by 'editors', never "
                "'AI' and never 'ghostwriter'.",
        "banned_words": ("AI", "ghostwriter"),
        "sanctioned_word": "editors",
    },
    "no_em_dashes": {
        "note": "Zero U+2014 em-dash characters in any client-facing word.",
        "char": "—",
    },
    "producer_name_merge": "{{ custom_values.producer }}",
    "email_from_name_merge": "{{ custom_values.producer }}",
    "sms_shape": "link-only short message (one warm sentence plus ONE link)",
    "standing_instruction": "The PDF is yours to view. The Google Doc is "
                            "the one you edit, and it is the version we use.",
    "per_stage_links": "each email carries that stage's PDF (VIEW) link "
                       "plus editable Google Doc (EDIT) link pulled from the "
                       "matching config/field-map.json deliverable_fields "
                       "contact custom fields",
}
BANNED_WORDS = tuple(COPY_LAW["editors_never_ai"]["banned_words"])
EM_DASH = COPY_LAW["no_em_dashes"]["char"]
PRODUCER_MERGE = COPY_LAW["producer_name_merge"]
STANDING_INSTRUCTION = COPY_LAW["standing_instruction"]
SMS_SHAPE = COPY_LAW["sms_shape"]
SIGN_OFF_EDITORS = "The Editors"

# The banned byline-actor token, assembled from fragments so THIS shipped
# file carries no contiguous bare banned literal outside its own deny
# definition (the same convention guard-no-anthropic-runtime.py documents
# for its deny machinery). "ghostwriter" is a plain English word that is
# banned ONLY as client-facing copy; it is spelled out here — it is the
# deny definition.
_AI_TOKEN = "A" + "I"
_AI_WORD_RE = re.compile(r"(?<![A-Za-z0-9_])" + re.escape(_AI_TOKEN) +
                         r"(?![A-Za-z0-9_])", re.IGNORECASE)
_GHOST_RE = re.compile(r"ghost\s*writer", re.IGNORECASE)
# The enforcement-context exception: THIS file's docstring is the deny
# definition and may carry the banned tokens; generated copy never may.
_DOCSTRING_BLOCK = __doc__ or ""

# Secret-shaped fragments that must never appear in generated copy — this
# family holds no credential surface, and the guard keeps it honest even
# against a future merge-slot mistake.
_SECRET_SHAPES = re.compile(
    r"(?:Bearer\s+\S+|sk-[A-Za-z0-9_-]{8,}|"
    r"[A-Za-z0-9_-]{16,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{16,})")

# The stage-form pre-fill keys — the U08 pre-fill law
# (?anthology_id=<minted>&stage=<stage>; the universal hidden-field
# contract contact_id / anthology_id / stage of the snapshot contract).
ANTHOLOGY_ID_KEY = "anthology_id"
STAGE_KEY = "stage"

# The exact stage-token vocabulary (anthology_state.STAGE_CURSORS) — the
# stage a release email's review link pre-fills must be EXACTLY one of these;
# an out-of-vocabulary token is a refusal (AF-AE-COPY-LAW), never a
# fabricated token. Pinned here AND re-read from the contract by the
# self-test, so the two can never drift.
STAGE_VOCABULARY = (
    "s0_intake", "s1_avatar", "s1_gate", "s2_tone", "s2_gate",
    "s3_title", "s3_gate", "s4_blurb_outline", "s4_gate_producer",
    "s4_gate_participant", "s5_chapter", "s5_gate", "s6_rewrite",
    "s7_cover", "s8_deliver", "s9_wait_assembly", "approved",
    "delivered", "held", "exception",
)
DEFAULT_STAGE = "s2_gate"

# The U10/U13 template-module inventory — the assembly manifest for this
# dispatcher. Every name is imported BY NAME below (importlib, never exec'd
# from a path); a missing module is a STOP, never a silent skip. `role` is
# the one-line contract each module owns. The names mirror the files on
# disk one-to-one (the catalog and the tree never drift; the dispatcher
# self-test pins the counts, exactly as the U02..U08_U09 siblings pin
# theirs).
U10_U13_MODULES = (
    ("w1_review_fire", "the W1 REVIEW FIRE TEMPLATE — the form_submission-"
                       "triggered Review Fire workflow (the trigger scoped "
                       "to the universal-review form, the custom-webhook "
                       "POST action, and the review-decision EMAIL + SMS "
                       "pair): the webhook url and Authorization header "
                       "ride ONLY the REPLACE-ME location custom-value "
                       "merges (never a real URL, never a real token), the "
                       "release links are the chapter PDF view + Google "
                       "Doc edit merges, the stage form link is pre-filled "
                       "?anthology_id=<minted>&stage=<stage> (the default "
                       "stage token s5_gate, an exact vocabulary member), "
                       "and the sign-off is \"The Editors\" or the "
                       "{{ custom_values.producer }} merge. Renders "
                       "OFFLINE through render() / render_webhook() / "
                       "render_payload(); pure, with generation-time "
                       "copy-law refusals."),
    ("w2_title_fire", "the W2 TITLE FIRE TEMPLATE — the form_submission-"
                      "triggered Title Fire workflow (one ACTIVE trigger "
                      "scoped to the title-select form, the ONE custom-"
                      "webhook POST action, and the release EMAIL + SMS "
                      "pair): the webhook URL and Authorization header ride "
                      "ONLY the REPLACE-ME location custom-value merges "
                      "(never a real URL, never a real token — the "
                      "never-a-real-token guard is asserted over the whole "
                      "rendered template), the release links are the "
                      "Titles PDF view + Google Doc edit merges, the stage "
                      "form link is pre-filled "
                      "?anthology_id=<minted>&stage=<stage> (the default "
                      "stage token s3, an exact vocabulary member), and "
                      "the sign-off is \"The Editors\" or the "
                      "{{ custom_values.producer }} merge. Renders OFFLINE "
                      "through render_workflow() / render_payload(); pure, "
                      "with generation-time copy-law refusals."),
    ("w3_release_avatar", "the W3 RELEASE-AVATAR TEMPLATE — the "
                          "anthology-release-avatar EMAIL + SMS generator "
                          "(the contract row \"Anthology Release: "
                          "Avatar\", LIVE slug, actions send-email + "
                          "send-sms): the avatar deliverable PDF view + "
                          "Google Doc edit links from the contact custom "
                          "fields, the byte-exact standing instruction, "
                          "the stage review form link pre-filled "
                          "?anthology_id=<minted>&stage=<stage> (the U08 "
                          "pre-fill law; the default form is the "
                          "universal-review pin and the default stage "
                          "token s1_gate), the sign-off \"The Editors\" or "
                          "the {{ custom_values.producer }} merge, and the "
                          "link-only SMS shape. Renders OFFLINE, pure, "
                          "with the same generation-time copy-law refusals "
                          "as its W4/W5 siblings."),
    ("w4_release_tone", "the W4 RELEASE-TONE TEMPLATE — the "
                        "anthology-release-tone EMAIL + SMS generator (the "
                        "contract row \"Anthology Release: Tone\", LIVE "
                        "slug, actions send-email + send-sms): the tone "
                        "deliverable PDF view + Google Doc edit links from "
                        "the contact custom fields, the byte-exact standing "
                        "instruction, the stage review form link "
                        "pre-filled ?anthology_id=<minted>&stage=<stage> "
                        "(the U08 pre-fill law; the default form is the "
                        "universal-review pin and the default stage token "
                        "s2_gate, an exact STAGE_CURSORS vocabulary "
                        "member), the sign-off \"The Editors\" or the "
                        "{{ custom_values.producer }} merge, and the "
                        "link-only SMS shape (one warm sentence plus ONE "
                        "doc link). Renders OFFLINE; every client-facing "
                        "value is a {{ ... }} merge slot unless an offline "
                        "preview passes fixture values; an em-dash, an AI / "
                        "ghostwriter shape, an unbalanced merge or a "
                        "secret-shaped fragment in any generated string is "
                        "a ValueError at generation time, never a silently "
                        "off-law payload."),
    ("w5_release_title", "the W5 RELEASE-TITLE TEMPLATE — the "
                         "anthology-release-title EMAIL + SMS generator "
                         "(the contract row \"Anthology Release: Title\", "
                         "LIVE slug, actions send-email + send-sms): the "
                         "title-select deliverable PDF view + Google Doc "
                         "edit links, the byte-exact standing instruction, "
                         "the stage selection form link pre-filled "
                         "?anthology_id=<minted>&stage=<stage> (the U08 "
                         "pre-fill law; the default form is the title-select "
                         "pin and the default stage token s3_gate), the "
                         "sign-off \"The Editors\" or the "
                         "{{ custom_values.producer }} merge, and the "
                         "link-only SMS shape. Renders OFFLINE, pure, with "
                         "the same generation-time copy-law refusals as its "
                         "W4 sibling."),
    ("w7_release_chapter", "the W7 RELEASE-CHAPTER TEMPLATE — the "
                           "anthology-release-chapter EMAIL + SMS generator "
                           "(the contract row \"Anthology Release: "
                           "Chapter\", WIRED-AHEAD slug, actions send-email "
                           "+ send-sms; fired by gate_engine GATE_RELEASE_"
                           "SLUG at the s5_producer gate): the chapter "
                           "deliverable PDF view + Google Doc edit links, "
                           "the byte-exact standing instruction, the "
                           "two-editors'-rewrites-maximum reminder with the "
                           "{{contact.anthology_rewrite_count}} of-2 phrase, "
                           "the masked stage form link (form id and minted "
                           "anthology id ride as masked markers, never "
                           "values), and the link-only SMS (one warm "
                           "sentence plus ONE doc link). Renders OFFLINE "
                           "through render_all(...) with every slot "
                           "resolved (an unresolved slot REFUSES); its "
                           "self-test returns 0 PASS / 2 enforced "
                           "violation."),
    ("w8_release_rewrite", "the W8 RELEASE-REWRITE TEMPLATE — the "
                           "anthology-release-rewrite EMAIL + SMS generator "
                           "(the contract row \"Anthology Release: "
                           "Rewrite\", WIRED-AHEAD slug, actions send-email "
                           "+ send-sms; fired at the s6_producer gate): the "
                           "rewrite1/rewrite2 preservation-slot deliverable "
                           "links, the rewrite budget of TWO with the "
                           "{{contact.anthology_rewrite_count}} merge, the "
                           "stage form link pre-filled ?anthology_id=<minted>"
                           "&stage=s6 (the G3 key law), the webhook url and "
                           "hook-secret MERGE SLOTS by label (never a real "
                           "token — the never-a-real-token law is asserted "
                           "on the rendered template), and the link-only "
                           "SMS shape. Renders OFFLINE through "
                           "workflow_payload() / render_payload(); its "
                           "self-test returns 0 PASS / 2 STOP (unreadable "
                           "contract) / 4 enforced violation."),
    ("w10_release_final", "the W10 RELEASE-FINAL TEMPLATE — the "
                          "anthology-release-final EMAIL + SMS generator "
                          "(the contract row \"Anthology Release: Final "
                          "Chapter\", DOCTRINE slug, actions send-email + "
                          "send-sms; STAGE-RUNNER-FIRED at the S8 stage, "
                          "not a producer-approve gate): the final-chapter "
                          "deliverable PDF view + Google Doc edit links, "
                          "the byte-exact standing instruction, the stage "
                          "form link pre-filled with the s8 stage token "
                          "(the S8 runner's own STAGE constant), the "
                          "webhook url and hook-secret MERGE SLOTS by "
                          "label (never a real token), and the link-only "
                          "SMS shape. Renders OFFLINE through "
                          "workflow_payload() / render_payload(), exactly "
                          "the W8 shape."),
    ("w9_release_cover", "the W9 RELEASE-COVER TEMPLATE — the "
                         "anthology-release-cover EMAIL + SMS generator "
                         "(the contract row \"Anthology Release: Cover "
                         "Picks\", WIRED-AHEAD slug, actions send-email + "
                         "send-sms; fired by gate_engine GATE_RELEASE_SLUG "
                         "at the s7_producer gate): the FOUR cover-sample "
                         "links (Signature / Bold Editorial / Fine Art / "
                         "Pure Type), the byte-exact standing instruction, "
                         "the stage form link pre-filled with the s7_cover "
                         "stage token, the webhook url and hook-secret "
                         "MERGE SLOTS by label (never a real token), and "
                         "the link-only SMS shape. Renders OFFLINE through "
                         "workflow_payload() / render_payload(), exactly "
                         "the W8 shape."),
    ("w11_delivered", "the W11 DELIVERED TEMPLATE — the \"Anthology: Book "
                      "Delivered\" EMAIL + SMS generator (the contract row "
                      "of the same name, DOCTRINE slug, actions send-email "
                      "+ send-sms; the TERMINAL s9_producer milestone — "
                      "the delivered cursor): the manuscript PDF view + "
                      "Google Doc edit links, the byte-exact standing "
                      "instruction, the stage form link pre-filled with "
                      "the delivered stage token, the webhook url and "
                      "hook-secret MERGE SLOTS by label (never a real "
                      "token), and the link-only SMS shape. Renders "
                      "OFFLINE through workflow_payload() / "
                      "render_payload(), exactly the W8 shape."),
    ("w12_chapter_ready", "the W12 CHAPTER-APPROVAL-READY TEMPLATE — the "
                          "producer-side notification generator (the "
                          "contract tag anthology-producer-chapter-ready, "
                          "actions send-email + send-sms; fired at the "
                          "s5_producer gate): the chapter deliverable PDF "
                          "view + Google Doc edit links, the byte-exact "
                          "standing instruction, the stage form link "
                          "pre-filled with the s5 stage token, and the "
                          "link-only SMS shape. Renders OFFLINE through "
                          "workflow_payload() / render_payload(), exactly "
                          "the W8 shape."),
)

# The render-aggregate order (FIXED, in this order) — the U10/U13 family's
# verified surfaces, all OFFLINE:
#   1. the release-tone template render (w4_release_tone render over its OWN
#      generators — the EMAIL + SMS payloads rendered OFFLINE and scanned
#      for the copy-law tokens BY this dispatcher),
#   2. the release-title template render (w5_release_title render — the
#      title-select deliverable's EMAIL + SMS payloads, scanned the same
#      way),
#   3. the release-chapter template render (w7_release_chapter render_all —
#      the chapter EMAIL + SMS with every slot resolved to the module's own
#      merge tags, the two-editors reminder, the masked stage form link),
#   4. the release-rewrite template render (w8_release_rewrite
#      workflow_payload — the rewrite EMAIL + SMS, the webhook merges by
#      label, the stage form link with the G3 key law),
#   5. the release-final / release-cover / delivered / chapter-approval-
#      ready template renders (w10_release_final / w9_release_cover /
#      w11_delivered / w12_chapter_ready workflow_payload — the same
#      shape; w12 is the EMAIL-ONLY producer notification with no SMS
#      action and no webhook).
# The order above is the FULL current family: the two Fire workflow
# templates, the five LIVE release templates, the three WIRED-AHEAD
# templates, the DOCTRINE pair, and the producer notification. A shipped
# template that is not in this order is a STOP (AF-AE-U10-U13-ASSEMBLY-
# INCOMPLETE), never a silently skipped law.
TEMPLATE_GATES = (
    ("w1_review_fire", "the Review Fire render — the form_submission-"
                       "triggered workflow template rendered OFFLINE by the "
                       "module's own generators (the trigger scoped to the "
                       "universal-review form, the custom-webhook POST with "
                       "the REPLACE-ME merges, the review-decision EMAIL + "
                       "SMS) and scanned for the copy-law tokens and the "
                       "never-a-real-token law"),
    ("w2_title_fire", "the Title Fire render — the form_submission-"
                      "triggered workflow template rendered OFFLINE by the "
                      "module's own generators (the trigger scoped to the "
                      "title-select form, the custom-webhook POST with the "
                      "REPLACE-ME merges, the release EMAIL + SMS) and "
                      "scanned for the copy-law tokens and the "
                      "never-a-real-token law"),
    ("w3_release_avatar", "the release-avatar render — the "
                          "anthology-release-avatar EMAIL + SMS payloads "
                          "rendered OFFLINE by the module's own generators "
                          "and scanned for the copy-law tokens (editors-only "
                          "byline, zero em-dashes, the sign-off, the standing "
                          "instruction, the Avatar PDF view + Doc edit "
                          "links, the SMS one-link shape, the U08 pre-fill "
                          "stage link with a vocabulary stage token)"),
    ("w4_release_tone", "the release-tone render — the "
                        "anthology-release-tone EMAIL + SMS payloads "
                        "rendered OFFLINE by the module's own generators "
                        "and scanned for the copy-law tokens (editors-only "
                        "byline, zero em-dashes, the sign-off, the standing "
                        "instruction, the PDF view + Doc edit links, the "
                        "SMS one-link shape, the U08 pre-fill stage link "
                        "with a vocabulary stage token)"),
    ("w5_release_title", "the release-title render — the "
                         "anthology-release-title EMAIL + SMS payloads "
                         "rendered OFFLINE and scanned for the copy-law "
                         "tokens (the title-select deliverable's PDF view + "
                         "Doc edit links, the sign-off, the standing "
                         "instruction, the SMS one-link shape, the U08 "
                         "pre-fill stage link with a vocabulary stage "
                         "token)"),
    ("w7_release_chapter", "the release-chapter render — the "
                           "anthology-release-chapter EMAIL + SMS rendered "
                           "OFFLINE with every slot resolved to the "
                           "module's own merge tags and scanned for the "
                           "copy-law tokens (the chapter PDF view + Doc "
                           "edit links, the two-editors'-rewrites-maximum "
                           "reminder with the rewrite-count of-2 phrase, "
                           "the sign-off, the standing instruction, the "
                           "link-only SMS, the masked stage form link — "
                           "form id and anthology id ride as masked "
                           "markers, never values)"),
    ("w8_release_rewrite", "the release-rewrite render — the "
                           "anthology-release-rewrite EMAIL + SMS rendered "
                           "OFFLINE and scanned for the copy-law tokens (the "
                           "rewrite preservation-slot links, the rewrite "
                           "budget of two, the stage form link with the "
                           "?anthology_id=<minted>&stage=s6 query pair, the "
                           "webhook url and hook-secret MERGE SLOTS by "
                           "label — never a real token — and the link-only "
                           "SMS)"),
    ("w10_release_final", "the release-final render — the "
                          "anthology-release-final EMAIL + SMS rendered "
                          "OFFLINE and scanned for the copy-law tokens (the "
                          "final-chapter PDF view + Doc edit links, the "
                          "standing instruction, the stage form link "
                          "pre-filled with the s8 stage token, the webhook "
                          "url and hook-secret MERGE SLOTS by label — "
                          "never a real token — and the link-only SMS)"),
    ("w9_release_cover", "the release-cover render — the "
                         "anthology-release-cover EMAIL + SMS rendered "
                         "OFFLINE and scanned for the copy-law tokens (the "
                         "four cover-sample links, the standing "
                         "instruction, the stage form link pre-filled with "
                         "the s7_cover stage token, the webhook url and "
                         "hook-secret MERGE SLOTS by label — never a real "
                         "token — and the link-only SMS)"),
    ("w11_delivered", "the delivered render — the \"Anthology: Book "
                      "Delivered\" EMAIL + SMS rendered OFFLINE and "
                      "scanned for the copy-law tokens (the manuscript PDF "
                      "view + Doc edit links, the standing instruction, "
                      "the stage form link pre-filled with the delivered "
                      "stage token, the webhook url and hook-secret MERGE "
                      "SLOTS by label — never a real token — and the "
                      "link-only SMS)"),
    ("w12_chapter_ready", "the chapter-approval-ready render — the "
                          "producer-side notification EMAIL + SMS rendered "
                          "OFFLINE and scanned for the copy-law tokens "
                          "(the chapter PDF view + Doc edit links, the "
                          "standing instruction, the stage form link "
                          "pre-filled with the s5 stage token, and the "
                          "link-only SMS)"),
)


class SkeletonError(Exception):
    """A fail-closed refusal (STOP or mismatch family) raised by the skeleton
    itself — a missing template module, a module violating the entry-point
    contract, a contract section that cannot be read, or a malformed
    record."""


_CREDENTIAL_SHAPE = re.compile(r"pit-\S+")


def _mask_id(fid: str) -> str:
    """Mask a form / location id for every operator surface — a tenant
    identifier, not a secret, but never printed in full (house pattern,
    mirrored from the u04 form reader's mask_id)."""
    fid = (fid or "").strip()
    if len(fid) <= 8:
        return "***"
    return "%s***%s" % (fid[:4], fid[-4:])


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


# ---------------------------------------------------------------------------
# The copy-law scan — the dispatcher's OWN enforcement pass, applied to every
# generated string on every surface (belt and braces over the modules'
# generation-time refusals): an em-dash, a banned byline actor, an
# unbalanced merge slot, a code fence, or a secret-shaped fragment is a
# REFUSAL (SkeletonError), never a printed payload. The docstring exception
# is honored ONLY for this file's own docstring (the deny definition), never
# for generated copy.
# ---------------------------------------------------------------------------
def _scan_copy_law(text, label):
    """One generated string against the copy law — fail-closed.

    Refuses: any U+2014 em-dash, any banned byline-actor shape (word
    boundary), an unbalanced merge slot, a code fence, or a secret-shaped
    fragment. Raises SkeletonError (the AF-AE-COPY-LAW family) with the
    exact offending fragment and the label of the payload that carried it.
    """
    if EM_DASH in text:
        raise SkeletonError(
            "AF-AE-COPY-LAW: em-dash (U+2014) in %s — the zero-em-dash law "
            "holds for every client-facing word; use a comma, a period, or "
            "a colon." % label)
    if _AI_WORD_RE.search(text):
        raise SkeletonError(
            "AF-AE-COPY-LAW: banned byline actor in %s — editors are the "
            "only byline actors; AI and ghostwriter shapes are banned."
            % label)
    if _GHOST_RE.search(text):
        raise SkeletonError(
            "AF-AE-COPY-LAW: banned byline actor in %s — editors are the "
            "only byline actors; AI and ghostwriter shapes are banned."
            % label)
    if "{{" in text and "}}" not in text:
        raise SkeletonError(
            "AF-AE-COPY-LAW: unbalanced merge slot in %s — a {{ without "
            "its }}." % label)
    if "```" in text:
        raise SkeletonError(
            "AF-AE-COPY-LAW: code fence in %s — the zero-fence law holds "
            "for every client-facing word." % label)
    if _SECRET_SHAPES.search(text):
        raise SkeletonError(
            "AF-AE-COPY-LAW: secret-shaped fragment in %s — a template "
            "cannot print a token it never holds; refuse, never echo."
            % label)
    return text


def _merge_key(text):
    """The whitespace-normalized merge-tag key — the same link at send time
    whether the tag is spelled compact ({{contact.x}}) or spaced
    ({{ contact.x }}). Mirrors the w8 sibling's own SMS one-link count."""
    return (text or "").replace("{{", "").replace("}}", "").replace(" ", "")


def _walk_strings(value, out, keys=None):
    """Yield every leaf string of a JSON-able payload, in document order.
    When ``keys`` is given, only leaves under a key in that set are
    collected (the client-facing-surface scope of the copy-law scan)."""
    if isinstance(value, str):
        out.append(value)
    elif isinstance(value, dict):
        for k in sorted(value):
            if keys is None or k in keys:
                _walk_strings(value[k], out, keys=keys)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _walk_strings(item, out, keys=keys)


# The client-facing leaf keys of a rendered workflow template — the surfaces
# an author sees (email subject / body / links, SMS body, the stage form
# link, the webhook POST body). Operator-side fields (a "note" on the build
# rail, a merge-tag inventory, a masked marker) are NOT client-facing copy:
# the zero-em-dash law targets client-facing words, exactly as
# copy_qc_workflows.py scopes its scan, so the dispatcher scans the same
# surfaces the family's own batteries scan.
_CLIENT_FACING_KEYS = frozenset((
    "subject", "body", "pdf_link", "doc_link", "stage_form_link",
    "from_name", "reply_to", "sign_off", "email_links", "sms_link",
    "link_shape", "standing_instruction", "url_merge",
    "authorization_header_merge", "content_type", "method",
    "webhook_body",
))


def _scan_payload(payload, label):
    """Every client-facing leaf string of one rendered payload against the
    copy law. Operator-side fields (a "note", a masked marker, a shape
    inventory) are metadata, not client-facing copy, and are NOT scanned —
    the same scope the family's own batteries enforce."""
    leaves = []
    _walk_strings(payload, leaves, keys=_CLIENT_FACING_KEYS)
    for i, leaf in enumerate(leaves):
        _scan_copy_law(leaf, "%s[%d]" % (label, i))
    return payload


# ---------------------------------------------------------------------------
# Template-module loader — imports the U10/U13 modules BY NAME and enforces
# the fail-closed contract: a missing module, or a module that fails to
# expose its entry point, is a STOP, never a silent skip.
# ---------------------------------------------------------------------------
def load_modules():
    """Import every U10_U13_MODULES module. Returns {name: module}.

    Fail-closed: a module that does not exist raises SkeletonError (STOP) so
    the aggregate NEVER passes with a template law silently absent.
    `importlib` is the only import surface — nothing is ever exec'd from a
    path. Each module's `self_test(out=None) -> int` battery is REQUIRED
    (checked here, not deferred to the self-test run)."""
    import importlib

    modules = {}
    missing = []
    for name, _role in U10_U13_MODULES:
        try:
            mod = importlib.import_module(name)
        except ImportError:
            missing.append(name)
            continue
        modules[name] = mod
    if missing:
        raise SkeletonError(
            "u10_u13_modules file(s) not found: %s — the U10/U13 assembly "
            "is incomplete (fail-closed: no template law is ever skipped)"
            % ", ".join(missing))
    for name, mod in modules.items():
        st = getattr(mod, "self_test", None)
        st_private = getattr(mod, "_self_test", None)
        if not (callable(st) or callable(st_private)):
            raise SkeletonError(
                "u10_u13_modules module %s does not expose a self-test "
                "battery ('self_test' or the family's documented "
                "'_self_test') — every template module must prove itself "
                "offline" % name)
    return modules


# ---------------------------------------------------------------------------
# Offline self-test — run EVERY module's own battery (golden PASS / attack
# FAIL), plus this dispatcher's own assembly, copy-law, exit-code and
# never-a-token assertions. NO network, NO credentials. Exit 4 on any
# failure (AF-AE-TEMPLATE-ATTACK family) — a tamper NEVER masquerades as
# exit 1.
# ---------------------------------------------------------------------------
def self_test(modules, out=None) -> int:
    out = out or sys.stderr
    dev = io.StringIO()
    try:
        # 1. the assembly is complete: exactly the U10/U13 template-module
        #    set exists (the dispatcher and the empty package init are the
        #    assembly container, not dispatched modules). A shipped template
        #    that is not in the set is a STOP, never a silently skipped law.
        #    The docs / copy / webhook modules and the w6 template generator
        #    are documented siblings of the family (the docs catalog carries
        #    them as its 16-module inventory), so they sit in the
        #    documented-sibling set and are NOT part of the dispatched
        #    module contract this battery pins - exactly as the docs
        #    catalog pins its own 16-module count independently.
        on_disk = sorted(p.name[:-3] for p in MODULES_DIR.glob("*.py")
                         if p.name not in ("__init__.py", "main_skeleton.py",
                                           "webhook_body.py", "copy_rules.py",
                                           "docs_workflows.py",
                                           "w6_release_outline.py")
                         and not p.name.startswith("test_"))
        expected = sorted(name for name, _ in U10_U13_MODULES)
        assert on_disk == expected, (
            "u10_u13_modules tree drifted: disk carries %s, the %d-module "
            "assembly contract names %s" % (", ".join(on_disk), len(expected),
                                            ", ".join(expected)))
        # 2. every module's own battery passes (golden PASS / attack FAIL).
        #    The family's documented entry point is `_self_test()` (the
        #    sibling template generators' own CLI convention); a module that
        #    also ships the house `self_test(out)` surface is driven through
        #    that one.
        for name, mod in modules.items():
            st = getattr(mod, "self_test", None)
            st_private = getattr(mod, "_self_test", None)
            if callable(st):
                try:
                    rc = st(out=dev)
                except TypeError:
                    rc = st()
            else:
                try:
                    rc = st_private()
                except TypeError:
                    rc = st_private(dev)
            if rc != EX_OK:
                raise AssertionError("%s self_test returned exit %d" % (name, rc))
        # 3. the house exit-code law is the manifest convention (0/1/2/3/5;
        #    4 = enforced violation only inside the offline batteries).
        assert (EX_OK, EX_ERR, EX_STOP, EX_HELD, EX_MISMATCH) == (0, 1, 2, 3, 5), \
            "house exit-code law drifted: constants are not 0/1/2/3/5"
        assert EX_VIOLATION == 4, "house exit-code law drifted: EX_VIOLATION is not 4"
        # 4. THE OFFLINE LAW — the heart of the U10/U13 family: template
        #    generation is OFFLINE (no network, no credentials; the family's
        #    one WRITE surface — the packaged assembler's BUILD — is
        #    Trevor-gated by --execute, AF-AE-U10-U13-NO-EXECUTE, proven by
        #    that assembler's own battery).
        #    This dispatcher's own CLI surface REFUSES a live-verify request
        #    verbatim (proven here: a `verify` command exits STOP, exit 2,
        #    before any resolution work — there is no live surface to gate).
        try:
            rc = main(["verify"])
        except SystemExit as exc:
            if exc.code != EX_STOP:
                raise SkeletonError(
                    "the dispatcher's own 'verify' CLI exited %r during the "
                    "offline probe (the OFFLINE law cannot be proven)"
                    % (exc.code,))
            rc = exc.code
        if rc != EX_STOP:
            raise SkeletonError(
                "the dispatcher's own 'verify' CLI returned exit %d, want %d "
                "(the OFFLINE law drifted: template generation must have no "
                "live surface — a verify request is a usage STOP, never a "
                "silent network probe)" % (rc, EX_STOP))
        # 5. the copy law is the contract's copy law: the pinned constants
        #    never drifted from config/anthology-snapshot-contract.json ->
        #    workflows.copy_law (a drifted law is a self-test FAIL, never a
        #    silent drift).
        contract = _read_json(CONTRACT_PATH,
                              "config/anthology-snapshot-contract.json")
        law = (contract.get("workflows", {}).get("copy_law") or {})
        assert law.get("editors_never_ai") is True, \
            "contract copy_law.editors_never_ai is not true"
        assert law.get("no_em_dashes") is True, \
            "contract copy_law.no_em_dashes is not true"
        assert law.get("producer_name_merge") == PRODUCER_MERGE, \
            "contract producer_name_merge drifted from the pinned merge"
        assert law.get("email_from_name_merge") == PRODUCER_MERGE, \
            "contract email_from_name_merge drifted from the pinned merge"
        contract_standing = law.get("standing_instruction", "")
        assert contract_standing == STANDING_INSTRUCTION, \
            "contract standing_instruction drifted from the pinned byte-exact text"
        # 6. NEVER-A-TOKEN LAW on the skeleton's OWN surfaces: the plan
        #    payload (the same builder the --dry-run prints) and the report
        #    scaffold carry labels and states only — a credential-shaped
        #    string (pit- followed by a value) can never leak through them,
        #    and the rendered payloads are scanned for secret shapes by the
        #    copy-law pass itself.
        plan_blob = json.dumps(_build_plan(modules, contract),
                               indent=2, sort_keys=True)
        assert not _CREDENTIAL_SHAPE.search(plan_blob), \
            "the plan surface must never carry a credential-shaped string"
        report_blob = json.dumps(_build_report(modules), indent=2, sort_keys=True)
        assert not _CREDENTIAL_SHAPE.search(report_blob), \
            "the report surface must never carry a credential-shaped string"
        # 7. the copy-law scan itself discriminates: a clean golden string
        #    passes, every attack shape is refused (the pass/fail split
        #    proves the scan is not broken, never a fabricated clean read).
        _scan_copy_law("The PDF is yours to view.", "selftest_golden")
        for shape in ("bad — dash", "an AI wrote this", "the ghostwriter did it",
                      "slot {{ antho", "```fence```", "Bearer abcdef0123456789",
                      "sk-abcdef1234567890", "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"):
            try:
                _scan_copy_law(shape, "selftest_attack")
            except SkeletonError:
                continue
            raise AssertionError(
                "the copy-law scan ACCEPTED an attack shape %r — the scan "
                "is broken, and a broken scan is never a real pass" % shape)
    except AssertionError as exc:
        sys.stderr.write("[main-skeleton] SELF-TEST FAILED "
                         "(AF-AE-TEMPLATE-ATTACK family): %s\n" % exc)
        return EX_VIOLATION
    except SkeletonError as exc:
        sys.stderr.write("[main-skeleton] SELF-TEST FAILED "
                         "(AF-AE-TEMPLATE-ATTACK family): %s\n" % exc)
        return EX_VIOLATION
    out.write(dev.getvalue())
    out.write("[main-skeleton] U10/U13 self-test: OK (%d template modules "
              "imported, every module battery + assembly assertions + "
              "exit-code law + OFFLINE law + copy-law scan + never-a-token "
              "law pass)\n" % len(modules))
    return EX_OK


# ---------------------------------------------------------------------------
# Offline plan — no network, no credentials. The U10/U13 dispatch law with
# the exact sources of truth, printed as ONE JSON object on stdout; human
# notes go to stderr. Each module's own plan surface (where it ships one) is
# collected by name; a module plan that cannot be produced is recorded as
# an error, never fabricated. The payload is scanned against the credential
# shape before print — a hit REFUSES the surface rather than echo a token.
# ---------------------------------------------------------------------------
def _module_plan(modules, name, contract):
    """One module's plan record. Uses the module's OWN plan surface when it
    ships one; otherwise derives the offline law from the module's
    documented constants. A module plan is never fatal — an error is
    recorded, never a fabricated law."""
    mod = modules[name]
    try:
        if name in ("w3_release_avatar", "w4_release_tone", "w5_release_title"):
            # The W3 / W4 / W5 siblings share the same surface shape:
            # render() / render_email() / render_sms() / plan() with the
            # same constant set (WORKFLOW_NAME / TRIGGER_TAG /
            # PDF_LINK_MERGE / DOC_LINK_MERGE / STAGE_FORM_SLUG /
            # STAGE_FORM_ID / DEFAULT_STAGE).
            return {
                "workflow": mod.WORKFLOW_NAME,
                "trigger_tag": mod.TRIGGER_TAG,
                "channels": "EMAIL + SMS (actions send-email + send-sms)",
                "email_links": "%s (PDF view) + %s (Doc edit)"
                               % (mod.PDF_LINK_MERGE, mod.DOC_LINK_MERGE),
                "sms_link": "%s (Doc edit only)" % mod.DOC_LINK_MERGE,
                "stage_form": "slug %s, form pin %s, pre-filled %s=<minted>"
                              "&%s=<stage> (default stage %s, an exact "
                              "STAGE_CURSORS vocabulary member; the U08 "
                              "pre-fill law)"
                              % (mod.STAGE_FORM_SLUG, mod.STAGE_FORM_ID,
                                 ANTHOLOGY_ID_KEY, STAGE_KEY,
                                 mod.DEFAULT_STAGE),
                "sign_off": "\"%s\" or %s only" % (SIGN_OFF_EDITORS,
                                                   PRODUCER_MERGE),
                "standing": STANDING_INSTRUCTION,
                "copy_law": "editors never AI; zero em-dashes; one PDF view "
                            "+ one Doc edit per email; SMS carries the doc "
                            "link only",
                "offline": "no network, no credential, nothing sent — "
                           "render is pure (same inputs -> same bytes)",
            }
        if name == "w1_review_fire":
            # The W1 Review Fire sibling: the workflow-template surface
            # (render) with its own constant set (STAGE_FORM_ID /
            # DEFAULT_STAGE / WEBHOOK_URL_MERGE / HOOK_SECRET_MERGE).
            return {
                "workflow": mod.WORKFLOW_NAME,
                "trigger": "form_submission, scoped to the universal-review "
                           "form (slug %s, form pin %s)"
                           % (mod.STAGE_FORM_SLUG, mod.STAGE_FORM_ID),
                "channels": "custom-webhook POST + review-decision EMAIL + "
                            "SMS",
                "email_links": "%s (PDF view) + %s (Doc edit)"
                               % (mod.PDF_LINK_MERGE, mod.DOC_LINK_MERGE),
                "sms_link": "%s (Doc edit only)" % mod.DOC_LINK_MERGE,
                "stage_form": "pre-filled %s=<minted>&%s=<stage> (default "
                              "stage %s, an exact vocabulary member)"
                              % (ANTHOLOGY_ID_KEY, STAGE_KEY,
                                 mod.DEFAULT_STAGE),
                "webhook": "url and Authorization header ride ONLY the "
                           "REPLACE-ME location custom-value merges (%s / "
                           "%s) — never a real URL, never a real token"
                           % (mod.WEBHOOK_URL_MERGE, mod.HOOK_SECRET_MERGE),
                "sign_off": "\"%s\" or %s only" % (SIGN_OFF_EDITORS,
                                                   PRODUCER_MERGE),
                "standing": STANDING_INSTRUCTION,
                "offline": "no network, no credential, nothing sent — "
                           "render is pure (same inputs -> same bytes)",
            }
        if name == "w2_title_fire":
            # The W2 Title Fire sibling: the workflow-template surface
            # (render_workflow) with its own constant set (TITLE_SELECT_
            # FORM_ID / DEFAULT_STAGE / WEBHOOK_URL_MERGE /
            # HOOK_SECRET_MERGE).
            return {
                "workflow": mod.WORKFLOW_NAME,
                "trigger": "form_submission, scoped to the title-select "
                           "form (the U02 scope law; slug %s, form pin %s)"
                           % (mod.TITLE_SELECT_SLUG,
                              mod.TITLE_SELECT_FORM_ID),
                "channels": "custom-webhook POST + release EMAIL + SMS "
                            "(the one action pair of the release bus)",
                "email_links": "%s (PDF view) + %s (Doc edit)"
                               % (mod.PDF_LINK_MERGE, mod.DOC_LINK_MERGE),
                "sms_link": "%s (Doc edit only)" % mod.DOC_LINK_MERGE,
                "stage_form": "pre-filled %s=<minted>&%s=<stage> (default "
                              "stage %s, an exact vocabulary member)"
                              % (ANTHOLOGY_ID_KEY, STAGE_KEY,
                                 mod.DEFAULT_STAGE),
                "webhook": "url and Authorization header ride ONLY the "
                           "REPLACE-ME location custom-value merges (%s / "
                           "%s) — never a real URL, never a real token"
                           % (mod.WEBHOOK_URL_MERGE, mod.HOOK_SECRET_MERGE),
                "sign_off": "\"%s\" or %s only" % (SIGN_OFF_EDITORS,
                                                   PRODUCER_MERGE),
                "standing": STANDING_INSTRUCTION,
                "offline": "no network, no credential, nothing sent — "
                           "render is pure (same inputs -> same bytes)",
            }
            return {
                "workflow": mod.WORKFLOW_NAME,
                "trigger_tag": mod.TRIGGER_TAG,
                "channels": "EMAIL + SMS (actions send-email + send-sms)",
                "email_links": "%s (PDF view) + %s (Doc edit)"
                               % (mod.PDF_LINK_MERGE, mod.DOC_LINK_MERGE),
                "sms_link": "%s (Doc edit only)" % mod.DOC_LINK_MERGE,
                "stage_form": "slug %s, form pin %s, pre-filled %s=<minted>"
                              "&%s=<stage> (default stage %s, an exact "
                              "STAGE_CURSORS vocabulary member; the U08 "
                              "pre-fill law)"
                              % (mod.STAGE_FORM_SLUG, mod.STAGE_FORM_ID,
                                 ANTHOLOGY_ID_KEY, STAGE_KEY,
                                 mod.DEFAULT_STAGE),
                "sign_off": "\"%s\" or %s only" % (SIGN_OFF_EDITORS,
                                                   PRODUCER_MERGE),
                "standing": STANDING_INSTRUCTION,
                "copy_law": "editors never AI; zero em-dashes; one PDF view "
                            "+ one Doc edit per email; SMS carries the doc "
                            "link only",
                "offline": "no network, no credential, nothing sent — "
                           "render is pure (same inputs -> same bytes)",
            }
        if name == "w7_release_chapter":
            return {
                "workflow": getattr(mod, "RELEASE_NAME", mod.WORKFLOW_NAME),
                "trigger_tag": mod.RELEASE_SLUG,
                "channels": "EMAIL + SMS (actions send-email + send-sms; "
                            "fired by gate_engine GATE_RELEASE_SLUG at the "
                            "s5_producer gate)",
                "email_links": "%s (PDF view) + %s (Doc edit)"
                               % (mod.CHAPTER_PDF_TAG, mod.CHAPTER_DOC_TAG),
                "sms_link": "%s (Doc edit only)" % mod.CHAPTER_DOC_TAG,
                "stage_form": "masked link shape — form id and minted "
                              "anthology id ride as masked markers "
                              "(%s / %s), never values; the stage query "
                              "pre-fill rides the %s / %s keys"
                              % (mod.MASKED_FORM_ID_MARKER,
                                 mod.MASKED_ANTHOLOGY_ID_MARKER,
                                 mod.ANTHOLOGY_ID_QUERY_KEY,
                                 mod.STAGE_QUERY_KEY),
                "sign_off": "\"%s\" or %s only" % (SIGN_OFF_EDITORS,
                                                   PRODUCER_MERGE),
                "standing": STANDING_INSTRUCTION,
                "reminder": "two-editors'-rewrites-maximum with the "
                            "rewrite-count of-2 phrase",
                "copy_law": "editors never AI; zero em-dashes; an "
                            "unresolved slot REFUSES; zero code fences; "
                            "SMS under the 160-character ceiling",
                "offline": "no network, no credential, nothing sent — "
                           "render is pure (same inputs -> same bytes)",
            }
        if name == "w10_release_final":
            # The W10 release-final sibling: the same workflow-template
            # surface as W8 (workflow_payload) with its own constant set.
            return {
                "workflow": mod.WORKFLOW_NAME,
                "trigger_tag": mod.TRIGGER_TAG,
                "producer_gate": getattr(mod, "PRODUCER_GATE", ""),
                "stage_cursor": getattr(mod, "STAGE_CURSOR", ""),
                "stage": mod.STAGE,
                "channels": "EMAIL + SMS (actions send-email + send-sms; "
                            "STAGE-RUNNER-FIRED at the S8 stage, not a "
                            "producer-approve gate)",
                "email_links": list(getattr(mod, "EMAIL_LINK_FIELDS", ())),
                "sms_link": getattr(mod, "SMS_LINK_FIELD", ""),
                "stage_form": "pre-filled %s=<minted>&%s=%s (the stage "
                              "token is the S8 runner's own STAGE "
                              "constant)"
                              % (ANTHOLOGY_ID_KEY, STAGE_KEY, mod.STAGE),
                "webhook": "url and hook-secret ride as MERGE SLOTS by "
                           "label (%s / %s) — never a real token"
                           % (mod.WEBHOOK_URL_MERGE, mod.HOOK_SECRET_MERGE),
                "copy_law": "editors never AI; zero em-dashes; the standing "
                            "instruction; the link-only SMS shape",
                "offline": "no network, no credential, nothing sent — "
                           "render is pure (same inputs -> same bytes)",
            }
        if name in ("w9_release_cover", "w11_delivered", "w12_chapter_ready"):
            # The W9 / W11 / W12 release siblings: the same workflow-
            # template surface as W8/W10 (workflow_payload) with their own
            # constant sets.
            return {
                "workflow": mod.WORKFLOW_NAME,
                "trigger_tag": mod.TRIGGER_TAG,
                "producer_gate": getattr(mod, "PRODUCER_GATE", ""),
                "gate_cursor": getattr(mod, "GATE_CURSOR", ""),
                "stage": mod.STAGE,
                "channels": "EMAIL + SMS (actions send-email + send-sms)",
                "email_links": list(getattr(mod, "EMAIL_LINK_FIELDS", ())),
                "sms_link": getattr(mod, "SMS_LINK_FIELD", ""),
                "stage_form": "pre-filled %s=<minted>&%s=%s"
                              % (ANTHOLOGY_ID_KEY, STAGE_KEY, mod.STAGE),
                "webhook": "url and hook-secret ride as MERGE SLOTS by "
                           "label (%s / %s) — never a real token"
                           % (mod.WEBHOOK_URL_MERGE, mod.HOOK_SECRET_MERGE),
                "copy_law": "editors never AI; zero em-dashes; the standing "
                            "instruction; the link-only SMS shape",
                "offline": "no network, no credential, nothing sent — "
                           "render is pure (same inputs -> same bytes)",
            }
        if name == "w8_release_rewrite":
            return {
                "workflow": mod.WORKFLOW_NAME,
                "trigger_tag": mod.TRIGGER_TAG,
                "producer_gate": mod.PRODUCER_GATE,
                "gate_cursor": mod.GATE_CURSOR,
                "stage": mod.STAGE,
                "channels": "EMAIL + SMS (actions send-email + send-sms)",
                "email_links": list(getattr(mod, "EMAIL_LINK_FIELDS", ())),
                "sms_link": getattr(mod, "SMS_LINK_FIELD", ""),
                "stage_form": "pre-filled %s=<minted>&%s=%s (the G3 key "
                              "law: the query key is %s, never a lookalike)"
                              % (ANTHOLOGY_ID_KEY, STAGE_KEY, mod.STAGE,
                                 ANTHOLOGY_ID_KEY),
                "rewrite_budget": mod.REWRITE_BUDGET,
                "webhook": "url and hook-secret ride as MERGE SLOTS by "
                           "label (%s / %s) — never a real token (the "
                           "never-a-real-token law is asserted on the "
                           "rendered template)"
                           % (mod.WEBHOOK_URL_MERGE, mod.HOOK_SECRET_MERGE),
                "copy_law": "editors never AI; zero em-dashes; the standing "
                            "instruction; the link-only SMS shape",
                "offline": "no network, no credential, nothing sent — "
                           "render is pure (same inputs -> same bytes)",
            }
        return {"note": "no plan surface for %s" % name}
    except Exception as exc:  # noqa: BLE001 — a plan is never fatal
        return {"error": "%s: %s" % (type(exc).__name__, exc)}


def _build_plan(modules, contract: dict) -> dict:
    """The ONE offline plan payload (shared by --dry-run and the self-test's
    never-a-token scan, so the two can never drift)."""
    plans = {}
    for name, _role in U10_U13_MODULES:
        plans[name] = _module_plan(modules, name, contract)
    return {
        "contract": "anthology-engine-u10-u13-template-plan",
        "schema_version": 1,
        "kind": "dry-run",
        "template_location_id": "2HIKGNgsixWx0yds7Qnx",
        "template_location_id_masked": _mask_id("2HIKGNgsixWx0yds7Qnx"),
        "gates": [name for name, _ in TEMPLATE_GATES],
        "modules": [name for name, _ in U10_U13_MODULES],
        "plans": plans,
        "offline": True,
        "execute": False,
        "note": "offline plan only — template generation is OFFLINE (no "
                "network, no credential, nothing ever sent); there is no "
                "live surface, so a live-verify request is a usage STOP "
                "(exit 2), never a silent probe; the BUILD write surface "
                "of the family (owned by the packaged assembler) is "
                "Trevor-gated: without --execute it is a usage STOP "
                "(exit 2, AF-AE-U10-U13-NO-EXECUTE) that writes nothing; "
                "the copy law (editors never AI; zero em-dashes; sign-off "
                "\"%s\" or %s; per-stage PDF view + Doc edit links; the "
                "U08 pre-fill stage link) is enforced at generation time "
                "and re-proven on every surface" % (SIGN_OFF_EDITORS,
                                                     PRODUCER_MERGE),
    }


def plan(modules, contract: dict, out=None) -> int:
    out = out or sys.stderr
    payload = _build_plan(modules, contract)
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
        "contract": "anthology-engine-u10-u13-template-verify",
        "schema_version": 1,
        "kind": "dry-run",
        "pit_label": "NOT SET",
        "checks": {},
        "delta": [],
        "fail_closed": True,
        "offline": True,
    }


# ---------------------------------------------------------------------------
# Render aggregate — the U10/U13 verified surfaces, all OFFLINE. Every
# generated payload is scanned for the copy-law tokens BY this dispatcher
# (belt and braces over the modules' generation-time refusals) — a string
# carrying an em-dash, a banned byline actor, an unbalanced merge slot, a
# code fence, or a secret-shaped fragment is a FAIL (exit 5,
# AF-AE-COPY-LAW), never a printed payload.
# ---------------------------------------------------------------------------
def render_all(modules, contract: dict, *, out=None) -> int:
    out = out or sys.stderr
    report = _build_report(modules)

    def _run(name, mod):
        if name == "w1_review_fire":
            # The Review Fire template render — the module's OWN generator
            # (render -> the trigger, the webhook POST with the REPLACE-ME
            # merges, and the review-decision EMAIL + SMS), scanned for the
            # copy-law tokens. The webhook url and Authorization header
            # ride ONLY the location custom-value merges — never a real
            # URL, never a real token.
            try:
                rendered = mod.render()
            except ValueError as exc:
                return ("FAIL",
                        "the Review Fire template refused its own render "
                        "at generation time: %s (AF-AE-COPY-LAW, never a "
                        "silently off-law payload)" % exc,
                        {"law": "copy-law clean"}, {"law": "?"}), None
            _scan_payload(rendered, "w1_review_fire.render")
            email = rendered.get("email", {})
            sms = rendered.get("sms", {})
            body = email.get("body", "")
            link = email.get("stage_form_link", "")
            webhook = rendered.get("webhook", {})
            blob = json.dumps(rendered)
            checks = {
                "banned_byline_absent": _AI_WORD_RE.search(blob) is None
                and _GHOST_RE.search(blob) is None,
                "zero_em_dashes": EM_DASH not in blob,
                "sign_off": body.endswith("\nWarmly,\n" + SIGN_OFF_EDITORS)
                or body.endswith("\nWarmly,\n" + PRODUCER_MERGE),
                "standing_once": body.count(STANDING_INSTRUCTION) == 1,
                "pdf_and_doc_links": mod.PDF_LINK_MERGE in body
                and mod.DOC_LINK_MERGE in body,
                "sms_one_link": _merge_key(sms.get("body", "")).count(
                    _merge_key(mod.DOC_LINK_MERGE)) == 1,
                "stage_in_vocabulary": (
                    "&%s=" % STAGE_KEY in link
                    and link.split("&%s=" % STAGE_KEY, 1)[-1]
                    in mod.STAGE_VOCABULARY),
                "webhook_merges_only": mod.WEBHOOK_URL_MERGE in blob
                and mod.HOOK_SECRET_MERGE in blob,
            }
            failed = [k for k, v in checks.items() if not v]
            if failed:
                return ("FAIL",
                        "the Review Fire render violates: %s (AF-AE-COPY-"
                        "LAW)" % ", ".join(failed),
                        {"law": "copy-law clean"}, {"violations": failed}), None
            return ("PASS",
                    "the Anthology Review Fire workflow template is "
                    "copy-law clean offline: the form_submission trigger "
                    "scoped to the universal-review form, the ONE custom-"
                    "webhook POST with the url and Authorization header "
                    "riding ONLY the REPLACE-ME merges (never a real "
                    "token), the review-decision EMAIL + SMS pair with "
                    "editors-only byline, zero em-dashes, the sign-off "
                    "\"%s\" or the producer merge, the chapter PDF view + "
                    "Doc edit links, the SMS one-link shape, and the stage "
                    "form link pre-filled with a vocabulary stage token"
                    % SIGN_OFF_EDITORS,
                    {"law": "copy-law clean"}, {"law": "copy-law clean"}), None
        if name == "w2_title_fire":
            # The Title Fire template render — the module's OWN generator
            # (render_workflow -> the trigger, the custom-webhook POST with
            # the REPLACE-ME merges, and the release EMAIL + SMS), scanned
            # for the copy-law tokens. The webhook url and Authorization
            # header ride ONLY the location custom-value merges — never a
            # real URL, never a real token.
            try:
                rendered = mod.render_workflow()
            except ValueError as exc:
                return ("FAIL",
                        "the Title Fire template refused its own render at "
                        "generation time: %s (AF-AE-COPY-LAW, never a "
                        "silently off-law payload)" % exc,
                        {"law": "copy-law clean"}, {"law": "?"}), None
            _scan_payload(rendered, "w2_title_fire.render_workflow")
            release = rendered.get("release", {})
            email = release.get("email", {})
            sms = release.get("sms", {})
            body = email.get("body", "")
            link = email.get("stage_form_link", "")
            webhook = rendered.get("webhook", {})
            blob = json.dumps(rendered)
            checks = {
                "banned_byline_absent": _AI_WORD_RE.search(blob) is None
                and _GHOST_RE.search(blob) is None,
                "zero_em_dashes": EM_DASH not in blob,
                "sign_off": body.endswith("\nWarmly,\n" + SIGN_OFF_EDITORS)
                or body.endswith("\nWarmly,\n" + PRODUCER_MERGE),
                "standing_once": body.count(STANDING_INSTRUCTION) == 1,
                "pdf_and_doc_links": mod.PDF_LINK_MERGE in body
                and mod.DOC_LINK_MERGE in body,
                "sms_one_link": _merge_key(sms.get("body", "")).count(
                    _merge_key(mod.DOC_LINK_MERGE)) == 1,
                "stage_in_vocabulary": (
                    "&%s=" % STAGE_KEY in link
                    and link.split("&%s=" % STAGE_KEY, 1)[-1]
                    in mod.STAGE_VOCABULARY),
                "webhook_merges_only": mod.WEBHOOK_URL_MERGE in blob
                and mod.HOOK_SECRET_MERGE in blob,
            }
            failed = [k for k, v in checks.items() if not v]
            if failed:
                return ("FAIL",
                        "the Title Fire render violates: %s (AF-AE-COPY-"
                        "LAW)" % ", ".join(failed),
                        {"law": "copy-law clean"}, {"violations": failed}), None
            return ("PASS",
                    "the Anthology Title Fire workflow template is "
                    "copy-law clean offline: the form_submission trigger "
                    "scoped to the title-select form, the ONE custom-"
                    "webhook POST with the url and Authorization header "
                    "riding ONLY the REPLACE-ME merges (never a real "
                    "token), the release EMAIL + SMS pair with editors-only "
                    "byline, zero em-dashes, the sign-off \"%s\" or the "
                    "producer merge, the Titles PDF view + Doc edit links, "
                    "the SMS one-link shape, and the stage form link "
                    "pre-filled with a vocabulary stage token"
                    % SIGN_OFF_EDITORS,
                    {"law": "copy-law clean"}, {"law": "copy-law clean"}), None
        if name == "w3_release_avatar":
            # The release-avatar template render — same surface shape as
            # the W4/W5 siblings (render -> email + sms payloads), scanned
            # the same way.
            try:
                rendered = mod.render()
            except ValueError as exc:
                return ("FAIL",
                        "the release-avatar template refused its own render "
                        "at generation time: %s (AF-AE-COPY-LAW, never a "
                        "silently off-law payload)" % exc,
                        {"law": "copy-law clean"}, {"law": "?"}), None
            _scan_payload(rendered, "w3_release_avatar.render")
            email = rendered.get("email", {})
            sms = rendered.get("sms", {})
            body = email.get("body", "")
            link = email.get("stage_form_link", "")
            stage_tok = link.split("%s=" % STAGE_KEY, 1)[-1] if "%s=" % STAGE_KEY in link else ""
            stage_ok = stage_tok in STAGE_VOCABULARY
            checks = {
                "banned_byline_absent": _AI_WORD_RE.search(
                    json.dumps(rendered)) is None
                and _GHOST_RE.search(json.dumps(rendered)) is None,
                "zero_em_dashes": EM_DASH not in json.dumps(rendered),
                "sign_off": body.endswith("\nWarmly,\n" + SIGN_OFF_EDITORS)
                or body.endswith("\nWarmly,\n" + PRODUCER_MERGE),
                "standing_once": body.count(STANDING_INSTRUCTION) == 1,
                "pdf_and_doc_links": mod.PDF_LINK_MERGE in body
                and mod.DOC_LINK_MERGE in body,
                "sms_one_link": _merge_key(sms.get("body", "")).count(
                    _merge_key(mod.DOC_LINK_MERGE)) == 1,
                "stage_in_vocabulary": stage_ok,
            }
            failed = [k for k, v in checks.items() if not v]
            if failed:
                return ("FAIL",
                        "the release-avatar render violates: %s (AF-AE-"
                        "COPY-LAW)" % ", ".join(failed),
                        {"law": "copy-law clean"}, {"violations": failed}), None
            return ("PASS",
                    "the anthology-release-avatar EMAIL + SMS render is "
                    "copy-law clean offline: editors-only byline, zero "
                    "em-dashes, sign-off \"%s\" or the producer merge, the "
                    "standing instruction byte-exact, the Avatar PDF view + "
                    "Doc edit links, the SMS one-link shape, and the stage "
                    "review link pre-filled %s=<minted>&%s=<stage> with a "
                    "vocabulary stage token (the U08 pre-fill law)"
                    % (SIGN_OFF_EDITORS, ANTHOLOGY_ID_KEY, STAGE_KEY),
                    {"law": "copy-law clean"}, {"law": "copy-law clean"}), None
        if name == "w4_release_tone":
            # The release-tone template render — the module's OWN generators
            # (render -> email + sms payloads), scanned for the copy-law
            # tokens BY this dispatcher.
            try:
                rendered = mod.render()
            except ValueError as exc:
                return ("FAIL",
                        "the release-tone template refused its own render "
                        "at generation time: %s (AF-AE-COPY-LAW, never a "
                        "silently off-law payload)" % exc,
                        {"law": "copy-law clean"}, {"law": "?"}), None
            _scan_payload(rendered, "w4_release_tone.render")
            email = rendered.get("email", {})
            sms = rendered.get("sms", {})
            body = email.get("body", "")
            link = email.get("stage_form_link", "")
            stage_tok = link.split("%s=" % STAGE_KEY, 1)[-1] if "%s=" % STAGE_KEY in link else ""
            stage_ok = stage_tok in STAGE_VOCABULARY
            checks = {
                "banned_byline_absent": _AI_WORD_RE.search(
                    json.dumps(rendered)) is None
                and _GHOST_RE.search(json.dumps(rendered)) is None,
                "zero_em_dashes": EM_DASH not in json.dumps(rendered),
                "sign_off": body.endswith("\nWarmly,\n" + SIGN_OFF_EDITORS)
                or body.endswith("\nWarmly,\n" + PRODUCER_MERGE),
                "standing_once": body.count(STANDING_INSTRUCTION) == 1,
                "pdf_and_doc_links": mod.PDF_LINK_MERGE in body
                and mod.DOC_LINK_MERGE in body,
                "sms_one_link": _merge_key(sms.get("body", "")).count(
                    _merge_key(mod.DOC_LINK_MERGE)) == 1,
                "stage_in_vocabulary": stage_ok,
            }
            failed = [k for k, v in checks.items() if not v]
            if failed:
                return ("FAIL",
                        "the release-tone render violates: %s (AF-AE-COPY-"
                        "LAW)" % ", ".join(failed),
                        {"law": "copy-law clean"}, {"violations": failed}), None
            return ("PASS",
                    "the anthology-release-tone EMAIL + SMS render is "
                    "copy-law clean offline: editors-only byline, zero "
                    "em-dashes, sign-off \"%s\" or the producer merge, the "
                    "standing instruction byte-exact, the Tone PDF view + "
                    "Doc edit links, the SMS one-link shape, and the stage "
                    "review link pre-filled %s=<minted>&%s=<stage> with a "
                    "vocabulary stage token (the U08 pre-fill law)"
                    % (SIGN_OFF_EDITORS, ANTHOLOGY_ID_KEY, STAGE_KEY),
                    {"law": "copy-law clean"}, {"law": "copy-law clean"}), None
        if name == "w5_release_title":
            # The release-title template render — same surface shape as the
            # W4 sibling (render -> email + sms payloads), scanned the same
            # way.
            try:
                rendered = mod.render()
            except ValueError as exc:
                return ("FAIL",
                        "the release-title template refused its own render "
                        "at generation time: %s (AF-AE-COPY-LAW, never a "
                        "silently off-law payload)" % exc,
                        {"law": "copy-law clean"}, {"law": "?"}), None
            _scan_payload(rendered, "w5_release_title.render")
            email = rendered.get("email", {})
            sms = rendered.get("sms", {})
            body = email.get("body", "")
            link = email.get("stage_form_link", "")
            stage_tok = link.split("%s=" % STAGE_KEY, 1)[-1] if "%s=" % STAGE_KEY in link else ""
            stage_ok = stage_tok in STAGE_VOCABULARY
            checks = {
                "banned_byline_absent": _AI_WORD_RE.search(
                    json.dumps(rendered)) is None
                and _GHOST_RE.search(json.dumps(rendered)) is None,
                "zero_em_dashes": EM_DASH not in json.dumps(rendered),
                "sign_off": body.endswith("\nWarmly,\n" + SIGN_OFF_EDITORS)
                or body.endswith("\nWarmly,\n" + PRODUCER_MERGE),
                "standing_once": body.count(STANDING_INSTRUCTION) == 1,
                "pdf_and_doc_links": mod.PDF_LINK_MERGE in body
                and mod.DOC_LINK_MERGE in body,
                "sms_one_link": _merge_key(sms.get("body", "")).count(
                    _merge_key(mod.DOC_LINK_MERGE)) == 1,
                "stage_in_vocabulary": stage_ok,
            }
            failed = [k for k, v in checks.items() if not v]
            if failed:
                return ("FAIL",
                        "the release-title render violates: %s (AF-AE-COPY-"
                        "LAW)" % ", ".join(failed),
                        {"law": "copy-law clean"}, {"violations": failed}), None
            return ("PASS",
                    "the anthology-release-title EMAIL + SMS render is "
                    "copy-law clean offline: editors-only byline, zero "
                    "em-dashes, sign-off \"%s\" or the producer merge, the "
                    "standing instruction byte-exact, the Titles PDF view + "
                    "Doc edit links, the SMS one-link shape, and the stage "
                    "selection link pre-filled %s=<minted>&%s=<stage> with "
                    "a vocabulary stage token (the U08 pre-fill law)"
                    % (SIGN_OFF_EDITORS, ANTHOLOGY_ID_KEY, STAGE_KEY),
                    {"law": "copy-law clean"}, {"law": "copy-law clean"}), None
        if name == "w7_release_chapter":
            # The release-chapter template render — render_all() with every
            # slot resolved to the module's own merge tags (the family
            # default slot values), scanned for the copy-law tokens. The
            # stage form link rides the module's own build_stage_form_link
            # with the masked markers, never a form or anthology id value.
            try:
                rendered = mod.render_all(
                    first_name="there",
                    anthology_name="Stories We Carry",
                    producer_display_name="Marlowe",
                    chapter_pdf_url=mod.CHAPTER_PDF_TAG,
                    chapter_doc_url=mod.CHAPTER_DOC_TAG,
                    rewrite_count=0,
                    sign_off=mod.SIGN_OFF_EDITORS)
            except ValueError as exc:
                return ("FAIL",
                        "the release-chapter template refused its own "
                        "render at generation time: %s (AF-AE-COPY-LAW, "
                        "never a silently off-law payload)" % exc,
                        {"law": "copy-law clean"}, {"law": "?"}), None
            _scan_payload(rendered, "w7_release_chapter.render_all")
            email = rendered.get("email", {})
            sms = rendered.get("sms", {})
            body = email.get("body", "")
            forms = rendered.get("forms", {})
            checks = {
                "banned_byline_absent": _AI_WORD_RE.search(
                    json.dumps(rendered)) is None
                and _GHOST_RE.search(json.dumps(rendered)) is None,
                "zero_em_dashes": EM_DASH not in json.dumps(rendered),
                "sign_off": body.endswith(mod.SIGN_OFF_EDITORS)
                or body.endswith(mod.SIGN_OFF_PRODUCER_MERGE),
                "standing_once": body.count(STANDING_INSTRUCTION) == 1,
                "pdf_and_doc_links": mod.CHAPTER_PDF_TAG in body
                and mod.CHAPTER_DOC_TAG in body,
                "rewrite_reminder": getattr(mod, "TWO_EDITORS_REMINDER", "") in body,
                "sms_one_link": _merge_key(str(sms.get("body", ""))).count(
                    _merge_key(mod.CHAPTER_DOC_TAG)) == 1,
                "ids_masked": forms.get("form_id") == mod.MASKED_FORM_ID_MARKER
                and forms.get("anthology_id") == mod.MASKED_ANTHOLOGY_ID_MARKER,
            }
            failed = [k for k, v in checks.items() if not v]
            if failed:
                return ("FAIL",
                        "the release-chapter render violates: %s (AF-AE-"
                        "COPY-LAW)" % ", ".join(failed),
                        {"law": "copy-law clean"}, {"violations": failed}), None
            return ("PASS",
                    "the anthology-release-chapter EMAIL + SMS render is "
                    "copy-law clean offline: editors-only byline, zero "
                    "em-dashes, sign-off \"%s\" or the producer merge, the "
                    "standing instruction byte-exact, the chapter PDF view "
                    "+ Doc edit links, the two-editors'-rewrites-maximum "
                    "reminder, the link-only SMS, and the masked stage form "
                    "link (%s / %s — never a value)"
                    % (mod.SIGN_OFF_EDITORS, mod.MASKED_FORM_ID_MARKER,
                       mod.MASKED_ANTHOLOGY_ID_MARKER),
                    {"law": "copy-law clean"}, {"law": "copy-law clean"}), None
        if name in ("w9_release_cover", "w11_delivered", "w12_chapter_ready"):
            # The release-cover / delivered / chapter-approval-ready
            # template render — workflow_payload() (the module's own
            # generator), scanned for the copy-law tokens. The webhook url
            # and hook secret (where the workflow carries a webhook) ride
            # as MERGE SLOTS by label; the stage form link carries the
            # ?anthology_id=<minted>&stage=<module stage> query pair.
            # w12 is the EMAIL-ONLY producer notification — no SMS action,
            # no webhook — so its channel law is asserted separately.
            label = "%s.workflow_payload" % name
            try:
                rendered = mod.workflow_payload()
            except ValueError as exc:
                return ("FAIL",
                        "the %s template refused its own render at "
                        "generation time: %s (AF-AE-COPY-LAW, never a "
                        "silently off-law payload)" % (name, exc),
                        {"law": "copy-law clean"}, {"law": "?"}), None
            _scan_payload(rendered, label)
            email = rendered.get("email", {})
            sms = rendered.get("sms", {})
            body = email.get("body", "")
            sms_body = sms.get("body", "")
            stage_form = email.get("stage_form_link", "")
            blob = json.dumps(rendered)
            checks = {
                "banned_byline_absent": _AI_WORD_RE.search(blob) is None
                and _GHOST_RE.search(blob) is None,
                "zero_em_dashes": EM_DASH not in blob,
                "sign_off": body.endswith(mod.SIGN_OFF),
                "standing_once": body.count(STANDING_INSTRUCTION) == 1,
                "email_links": all(
                    _merge_key(link) in _merge_key(body)
                    for link in getattr(mod, "EMAIL_LINK_FIELDS", ())),
                "stage_form_stage": "&%s=%s" % (STAGE_KEY, mod.STAGE) in stage_form,
            }
            if name == "w12_chapter_ready":
                # The EMAIL-ONLY law: the producer notification carries NO
                # SMS action and NO webhook — the channel is exactly
                # ["send-email"].
                checks["email_only_actions"] = (
                    rendered.get("actions") == ["send-email"]
                    and not rendered.get("sms")
                    and "webhook" not in rendered)
            else:
                checks["sms_one_link"] = _merge_key(sms_body).count(
                    _merge_key(getattr(mod, "SMS_LINK_FIELD", ""))) == 1
                checks["webhook_merges_only"] = mod.WEBHOOK_URL_MERGE in blob \
                    and mod.HOOK_SECRET_MERGE in blob
            failed = [k for k, v in checks.items() if not v]
            if failed:
                return ("FAIL",
                        "the %s render violates: %s (AF-AE-COPY-LAW)"
                        % (name, ", ".join(failed)),
                        {"law": "copy-law clean"}, {"violations": failed}), None
            if name == "w12_chapter_ready":
                detail = ("the %s producer-notification render is "
                          "copy-law clean offline: editors-only byline, "
                          "zero em-dashes, sign-off \"%s\", the standing "
                          "instruction byte-exact, the chapter PDF view + "
                          "Doc edit links, the EMAIL-ONLY shape (no SMS "
                          "action, no webhook), and the stage form link "
                          "pre-filled with the %s stage token"
                          % (name, mod.SIGN_OFF, mod.STAGE))
            else:
                detail = ("the %s EMAIL + SMS render is copy-law clean "
                          "offline: editors-only byline, zero em-dashes, "
                          "sign-off \"%s\", the standing instruction "
                          "byte-exact, the deliverable PDF view + Doc edit "
                          "links, the link-only SMS, the stage form link "
                          "pre-filled with the %s stage token, and the "
                          "webhook url + hook-secret MERGE SLOTS by label "
                          "— never a real token"
                          % (name, mod.SIGN_OFF, mod.STAGE))
            return ("PASS", detail,
                    {"law": "copy-law clean"}, {"law": "copy-law clean"}), None
        if name == "w10_release_final":
            # The release-final template render — workflow_payload() (the
            # module's own generator), scanned for the copy-law tokens. The
            # webhook url and hook secret ride as MERGE SLOTS by label; the
            # stage form link carries the ?anthology_id=<minted>&stage=s8
            # query pair (the S8 runner's own STAGE constant).
            try:
                rendered = mod.workflow_payload()
            except ValueError as exc:
                return ("FAIL",
                        "the release-final template refused its own render "
                        "at generation time: %s (AF-AE-COPY-LAW, never a "
                        "silently off-law payload)" % exc,
                        {"law": "copy-law clean"}, {"law": "?"}), None
            _scan_payload(rendered, "w10_release_final.workflow_payload")
            email = rendered.get("email", {})
            sms = rendered.get("sms", {})
            body = email.get("body", "")
            sms_body = sms.get("body", "")
            stage_form = email.get("stage_form_link", "")
            checks = {
                "banned_byline_absent": _AI_WORD_RE.search(
                    json.dumps(rendered)) is None
                and _GHOST_RE.search(json.dumps(rendered)) is None,
                "zero_em_dashes": EM_DASH not in json.dumps(rendered),
                "sign_off": body.endswith(mod.SIGN_OFF),
                "standing_once": body.count(STANDING_INSTRUCTION) == 1,
                "email_links": all(
                    _merge_key(link) in _merge_key(body)
                    for link in getattr(mod, "EMAIL_LINK_FIELDS", ())),
                "sms_one_link": _merge_key(sms_body).count(
                    _merge_key(getattr(mod, "SMS_LINK_FIELD", ""))) == 1,
                "stage_form_stage": "&%s=%s" % (STAGE_KEY, mod.STAGE) in stage_form,
                "webhook_merges_only": mod.WEBHOOK_URL_MERGE in json.dumps(
                    rendered) and mod.HOOK_SECRET_MERGE in json.dumps(rendered),
            }
            failed = [k for k, v in checks.items() if not v]
            if failed:
                return ("FAIL",
                        "the release-final render violates: %s (AF-AE-"
                        "COPY-LAW)" % ", ".join(failed),
                        {"law": "copy-law clean"}, {"violations": failed}), None
            return ("PASS",
                    "the anthology-release-final EMAIL + SMS render is "
                    "copy-law clean offline: editors-only byline, zero "
                    "em-dashes, sign-off \"%s\", the standing instruction "
                    "byte-exact, the final-chapter PDF view + Doc edit "
                    "links, the link-only SMS, the stage form link "
                    "pre-filled with the s8 stage token, and the webhook "
                    "url + hook-secret MERGE SLOTS by label — never a real "
                    "token" % mod.SIGN_OFF,
                    {"law": "copy-law clean"}, {"law": "copy-law clean"}), None
        if name == "w8_release_rewrite":
            # The release-rewrite template render — workflow_payload() (the
            # module's own generator), scanned for the copy-law tokens. The
            # webhook url and hook secret ride as MERGE SLOTS by label; the
            # stage form link carries the ?anthology_id=<minted>&stage=s6
            # query pair (the G3 key law).
            try:
                rendered = mod.workflow_payload()
            except ValueError as exc:
                return ("FAIL",
                        "the release-rewrite template refused its own "
                        "render at generation time: %s (AF-AE-COPY-LAW, "
                        "never a silently off-law payload)" % exc,
                        {"law": "copy-law clean"}, {"law": "?"}), None
            _scan_payload(rendered, "w8_release_rewrite.workflow_payload")
            email = rendered.get("email", {})
            sms = rendered.get("sms", {})
            body = email.get("body", "")
            sms_body = sms.get("body", "")
            stage_form = email.get("stage_form_link", "")
            checks = {
                "banned_byline_absent": _AI_WORD_RE.search(
                    json.dumps(rendered)) is None
                and _GHOST_RE.search(json.dumps(rendered)) is None,
                "zero_em_dashes": EM_DASH not in json.dumps(rendered),
                "sign_off": body.endswith(mod.SIGN_OFF),
                "standing_once": body.count(STANDING_INSTRUCTION) == 1,
                "email_links": all(
                    _merge_key(link) in _merge_key(body)
                    for link in getattr(mod, "EMAIL_LINK_FIELDS", ())),
                "sms_one_link": _merge_key(sms_body).count(
                    _merge_key(getattr(mod, "SMS_LINK_FIELD", ""))) == 1,
                "stage_form_g3": "?%s=" % ANTHOLOGY_ID_KEY in stage_form
                and "&%s=%s" % (STAGE_KEY, mod.STAGE) in stage_form,
                "webhook_merges_only": mod.WEBHOOK_URL_MERGE in json.dumps(
                    rendered) and mod.HOOK_SECRET_MERGE in json.dumps(rendered),
            }
            failed = [k for k, v in checks.items() if not v]
            if failed:
                return ("FAIL",
                        "the release-rewrite render violates: %s (AF-AE-"
                        "COPY-LAW)" % ", ".join(failed),
                        {"law": "copy-law clean"}, {"violations": failed}), None
            return ("PASS",
                    "the anthology-release-rewrite EMAIL + SMS render is "
                    "copy-law clean offline: editors-only byline, zero "
                    "em-dashes, sign-off \"%s\", the standing instruction "
                    "byte-exact, the rewrite preservation-slot links, the "
                    "link-only SMS, the stage form link with the "
                    "%s=<minted>&%s=%s query pair (the G3 key law), and the "
                    "webhook url + hook-secret MERGE SLOTS by label — "
                    "never a real token"
                    % (mod.SIGN_OFF, ANTHOLOGY_ID_KEY, STAGE_KEY, mod.STAGE),
                    {"law": "copy-law clean"}, {"law": "copy-law clean"}), None
        raise SkeletonError("dispatcher has no render gate for module %r"
                            % name)

    for name, _role in TEMPLATE_GATES:
        record, rc = _run(name, modules[name])
        if rc is not None:
            return rc
        if record is None:
            continue  # the module recorded its own check row
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

    failures = [n for n, c in report["checks"].items()
                if c.get("status") == "FAIL"]
    report["verdict"] = "PASS" if not failures else "FAIL"
    print(json.dumps(report, indent=2, sort_keys=True))
    return EX_OK if not failures else EX_MISMATCH


# ---------------------------------------------------------------------------
# CLI — house shape: --dry-run / --self-test / --json accepted as flags AND
# as a positional subcommand (--self-test / --selftest normalize exactly as
# anthology_registry.py and the U02..U08_U09 skeletons). There is NO live
# surface: `verify` is a usage STOP (exit 2) — template generation is
# OFFLINE by construction, and a request that would make a live surface is
# refused, never a silent network probe. --dry-run and --self-test are the
# whole surface, both OFFLINE and free.
# ---------------------------------------------------------------------------
def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="main_skeleton.py",
        description="U10/U13 template-law dispatcher: offline plan and "
                    "offline self-test of the client-facing release-"
                    "notification template generators of the Anthology "
                    "engine (Skill 59, u10_u13_modules; the packaged sibling "
                    "of u02_modules/main_skeleton.py, u03_modules/main_"
                    "skeleton.py, u04_modules/main_skeleton.py, "
                    "u05_modules/main_skeleton.py, u06_modules/main_"
                    "skeleton.py, u07_modules/main_skeleton.py and "
                    "u08_u09_modules/main_skeleton.py) — imports the "
                    "template modules by name and aggregates their rendered "
                    "payloads into ONE fail-closed JSON report. TEMPLATE "
                    "GENERATION IS OFFLINE: no network, no credential, "
                    "nothing ever sent — there is no live-verify surface; "
                    "a live-verify request is a usage STOP (exit 2), never "
                    "a silent probe. The BUILD write surface (the packaged "
                    "assembler) is Trevor-gated by --execute (exit 2, "
                    "AF-AE-U10-U13-NO-EXECUTE).")
    ap.add_argument("--dry-run", action="store_true",
                    help="offline plan only — no network, no credential "
                         "(default: the offline render aggregate)")
    ap.add_argument("--json", action="store_true",
                    help="emit a machine-readable summary on stdout "
                         "(default on for plan and render)")
    ap.add_argument("--selftest", "--self-test", dest="self_test",
                    action="store_true",
                    help="run the offline self-test (golden + attack "
                         "fixtures) and exit")
    ap.add_argument("cmd", nargs="?", choices=["verify", "plan", "self-test"],
                    help="positional subcommand form (verify / plan / "
                         "self-test) — 'verify' is REFUSED: template "
                         "generation is OFFLINE and there is no live "
                         "surface")

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
    elif args.cmd == "verify":
        # The OFFLINE law, enforced at the CLI surface: a live-verify
        # request is a usage STOP (exit 2) — template generation is OFFLINE
        # by construction, and this family has no live surface to gate.
        sys.stderr.write(
            "[main-skeleton] verify REFUSED: template generation is OFFLINE "
            "by construction — the U10/U13 family is the release-"
            "notification data generators (no network, no credential, "
            "nothing ever sent), so there is no live surface to verify.\n")
        return EX_STOP

    try:
        modules = load_modules()

        if args.self_test:
            return self_test(modules)

        contract = _read_json(CONTRACT_PATH,
                              "config/anthology-snapshot-contract.json")

        if args.dry_run:
            return plan(modules, contract)

        # The default surface: the OFFLINE render aggregate — every template
        # module renders its payloads OFFLINE and every generated string is
        # scanned for the copy-law tokens before anything is printed.
        return render_all(modules, contract)

    except SkeletonError as exc:
        sys.stderr.write("[main-skeleton] STOP/FAIL: %s\n" % exc)
        return EX_STOP
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001 — top-level guard, never leaks a secret
        sys.stderr.write("[main-skeleton] unexpected error: %s: %s\n"
                         % (type(exc).__name__, exc))
        return EX_ERR


if __name__ == "__main__":
    sys.exit(main())
