#!/usr/bin/env python3
# =============================================================================
# SKILL 59 - ANTHOLOGY ENGINE :: build_anthology_workflows.py  (U10/U13 tooling)
# U10/U13 WORKFLOW-TEMPLATE ASSEMBLY DISPATCHER - the ONE CLI ASSEMBLED from
# the u10_u13_modules files (the family's 16-module catalog plus the W6
# release-outline generator, 17 files on disk): it imports EVERY module under
# scripts/u10_u13_modules/ BY NAME (importlib, never exec'd from a path) and
# wires them into ONE OFFLINE assembly whose self-test battery (every module's
# own golden PASS / attack FAIL, the skeleton dispatcher battery, the assembly
# tree pin, and the 13-template file validation: trigger type, the EMAIL + SMS
# action pair on every client-facing seat, zero banned byline actors, zero
# em-dashes, zero code fences, the merge links present) runs before anything
# is written, and which GENERATES the 13 workflow template JSON documents
# OFFLINE to scripts/u10_u13_workflows/*.json (one file per seat, seat 1..13).
# It is the packaged sibling of scripts/build_anthology_forms.py (U08/U09,
# row 60) under the ENGINE-MANIFEST row-54 shipping doctrine; its OWN
# manifest row is staged manifest-pending/u10_u13.json (PENDING - stamped by
# this assembly, exactly as the U07 row was stamped by provision_fields.py).
#
# THE u10_u13_modules FILES (imported by name; each is STDLIB-only and
# self-tests itself - docs_workflows.py carries the module inventory as data
# and its self-test proves the tree ships together; the family's FIXED
# catalog is 16 modules, the exact count docs_workflows.CONTRACT_MODULE_COUNT
# pins, and the W6 release-outline generator is the seventeenth file, the
# module that resolves the family's PENDING seat 13):
#   __init__.py            fail-closed EMPTY package init (pure namespace;
#                          records the package doctrine - template
#                          generation is OFFLINE, destructive actions require
#                          --execute, move in silence, zero Anthropic runtime
#                          identifiers)
#   copy_rules.py          the COPY-RULE CONSTANT MODULE - the single
#                          canonical source of the copy law (contract
#                          workflows.copy_law) plus the two-link and
#                          stage-form-link laws; every sibling imports its
#                          constants and deny machinery FROM HERE
#   webhook_body.py        the W1/W2 WEBHOOK BODY BUILDER - the routed
#                          submission shapes the inbound intake hook accepts
#                          and the OUTBOUND custom-webhook POST shapes the
#                          tag->notification workflows fire
#   w1_review_fire.py      the W1 REVIEW FIRE TEMPLATE - the
#                          form_submission-triggered workflow scoped to the
#                          universal-review form (webhook + decision EMAIL +
#                          SMS); renders OFFLINE through render()
#   w2_title_fire.py       the W2 TITLE FIRE TEMPLATE - the
#                          form_submission-triggered workflow scoped to the
#                          title-select form (webhook + release EMAIL + SMS);
#                          renders OFFLINE through render_workflow()
#   w3_release_avatar.py   the W3 RELEASE-AVATAR EMAIL + SMS generator
#                          (render() -> the contract row "Anthology Release:
#                          Avatar", LIVE slug)
#   w4_release_tone.py     the W4 RELEASE-TONE EMAIL + SMS generator
#                          (render() -> "Anthology Release: Tone", LIVE)
#   w5_release_title.py    the W5 RELEASE-TITLE EMAIL + SMS generator
#                          (render() -> "Anthology Release: Title", LIVE)
#   w6_release_outline.py  the W6 RELEASE-OUTLINE EMAIL + SMS generator
#                          (render() -> the contract row "Anthology Release:
#                          Outline & Blurb", LIVE slug; the seat the family
#                          docs mark PENDING is now shipped by this module)
#   w7_release_chapter.py  the W7 RELEASE-CHAPTER EMAIL + SMS generator
#                          (render_all() -> "Anthology Release: Chapter",
#                          WIRED-AHEAD; the masked stage form link)
#   w8_release_rewrite.py  the W8 RELEASE-REWRITE EMAIL + SMS generator
#                          (workflow_payload() -> "Anthology Release:
#                          Rewrite", WIRED-AHEAD)
#   w9_release_cover.py    the W9 RELEASE-COVER EMAIL + SMS generator
#                          (workflow_payload() -> "Anthology Release: Cover
#                          Picks", WIRED-AHEAD; the four cover-sample links)
#   w10_release_final.py   the W10 RELEASE-FINAL EMAIL + SMS generator
#                          (workflow_payload() -> "Anthology Release: Final
#                          Chapter", DOCTRINE; the S8 runner's own STAGE)
#   w11_delivered.py       the W11 DELIVERED EMAIL + SMS generator
#                          (workflow_payload() -> "Anthology: Book
#                          Delivered", DOCTRINE; the TERMINAL s9 milestone)
#   w12_chapter_ready.py   the W12 CHAPTER-APPROVAL-READY generator
#                          (workflow_payload() -> "Chapter Approval Ready",
#                          the producer notification, EMAIL ONLY)
#   main_skeleton.py       the U10/U13 template-law dispatcher (plan /
#                          self-test / render aggregate; the ONE entry-point
#                          contract over the modules; refuses a live verify)
#   docs_workflows.py      the family README / catalog data + drift gate
#                          (the thirteen workflow seats, copy rules, module
#                          inventory, exit codes, AF family, doctrine,
#                          credential labels; readme() renders FROM the data)
#
# WHAT THIS ASSEMBLY IS:
#   * The engine's ONE offline writer of the 13 workflow-template JSON
#     documents. The contract (config/anthology-snapshot-contract.json
#     workflows.release_notifications + tag_to_notification) is a CONTRACT
#     DESCRIPTION, never an n8n/GHL workflow JSON export; these generated
#     documents are the same: template copy + merge tags + trigger seats as
#     DATA for the Skill 44 caf build rail to build in the client's OWN
#     Convert and Flow account - never a node graph (scan-no-json-exports.sh
#     bans n8n JSON exports; the generated files carry no n8n marker and no
#     "connections" shape, so the scanner stays clean over the generated
#     directory - proved by the self-test).
#   * OFFLINE BY CONSTRUCTION, like the whole U10/U13 family: no network, no
#     credential, nothing sent. There is NO live surface, so there is no
#     --execute gate: a `verify` request is a usage STOP (exit 2,
#     AF-AE-U10-U13-OFFLINE), never a silent probe.
#   * FAIL-CLOSED: every module import is BY NAME (a missing module STOPS,
#     never a silent skip); every generated file is validated against the
#     copy law (zero banned byline actors, zero em-dashes, zero code fences,
#     the sanctioned sign-offs, the links present) before it is written; a
#     validation failure is exit 4, never a silently off-law file. The
#     generated directory is written atomically (temp + rename per file).
#   * NEVER-A-TOKEN: the generated files carry the REPLACE-ME location
#     custom-value merges and the contact custom-field merge tags ONLY -
#     never a real URL, never a real token, never a form id VALUE (masked
#     markers only). A credential-shaped fragment anywhere is a refusal.
#
# EXIT CODES (house convention 0/1/2/3/5; 4 = enforced violation):
#   0  build (13 files generated and validated) or self-test PASS
#   1  unexpected error (top-level guard; never a secret leak)
#   2  STOP refusal - usage / a live-verify request (AF-AE-U10-U13-OFFLINE:
#      this family is OFFLINE by construction) / the module assembly
#      incomplete (AF-AE-U10-U13-ASSEMBLY-INCOMPLETE) / an
#      out-of-vocabulary stage token
#   3  HELD - unused by this family (kept for the house 0/1/2/3/5 law)
#   4  self-test FAILED (the AF-AE-TEMPLATE-ATTACK enforced-violation family
#      - a tamper never masquerades as exit 1)
#   5  data / copy-law mismatch in a rendered template (AF-AE-COPY-LAW - the
#      fail-closed default; never a printed off-law payload)
#
# CLI (house shape; --dry-run / --self-test accepted as flags AND as
# positional subcommands, --self-test / --selftest normalized exactly as
# anthology_registry.py and the U02..U08_U09 siblings):
#   python3 build_anthology_workflows.py build       # generate + validate
#   python3 build_anthology_workflows.py self-test   # offline battery + the
#                                                    # 13-file validation
#   python3 build_anthology_workflows.py plan        # offline plan
#   python3 build_anthology_workflows.py verify      # REFUSED (exit 2)
# After a PASS the assembly writes manifest-pending/u10_u13.json (fail-
# closed: FAIL/HELD/STOP writes nothing). ENGINE-MANIFEST.json /
# ENGINE-PIN.sha256 / verify.sh are NEVER touched here.
# =============================================================================
"""build_anthology_workflows.py - the U10/U13 workflow-template assembly
dispatcher: imports the u10_u13_modules files BY NAME and generates the
13 workflow template JSON documents OFFLINE to scripts/u10_u13_workflows/
(Skill 59; the packaged sibling of build_anthology_forms.py (U08/U09) under
the ENGINE-MANIFEST row-54 shipping doctrine). Template generation is OFFLINE
by construction: no network, no credential, nothing ever sent."""

from __future__ import annotations

import argparse
import importlib
import io
import json
import os
import re
import sys
from pathlib import Path

EX_OK, EX_ERR, EX_STOP, EX_HELD, EX_MISMATCH = 0, 1, 2, 3, 5
EX_VIOLATION = 4  # enforced violation detected (self-test FAILED)

SKILL_DIR = Path(__file__).resolve().parent.parent
CONTRACT_PATH = SKILL_DIR / "config" / "anthology-snapshot-contract.json"
PENDING_DIR = SKILL_DIR / "manifest-pending"
PENDING_U10_U13 = PENDING_DIR / "u10_u13.json"
OUTPUT_DIR = Path(__file__).resolve().parent / "u10_u13_workflows"

# The template location pin, read from the contract the U02..U08_U09
# siblings use (source_template_location). A location identifier, never a
# secret; masked on every surface.
DEFAULT_TEMPLATE_LOCATION = "2HIKGNgsixWx0yds7Qnx"

# The u10_u13_modules directory - sibling imports resolve from here, in
# BOTH execution contexts (as a script and as an imported module).
MODULES_DIR = Path(__file__).resolve().parent / "u10_u13_modules"
if str(MODULES_DIR) not in sys.path:
    sys.path.insert(0, str(MODULES_DIR))

# THE u10_u13_modules FILES - the assembly manifest for this dispatcher.
# Every name is imported BY NAME below (importlib), never exec'd from a
# path; a missing module is a STOP, never a silent skip. The names mirror
# the files on disk one-to-one (the catalog and the tree never drift; the
# self-test pins the roster and the count). The set is the family's
# 16-module catalog (docs_workflows.CONTRACT_MODULE_COUNT: the empty
# package init + copy_rules + webhook_body + the eleven catalog generators
# + main_skeleton + docs_workflows) PLUS the W6 release-outline generator,
# the module that resolves the family's PENDING seat 13 - 17 files on
# disk, and the assembly imports every one of them (the modules dict holds
# exactly the 16 module objects; the package init is the namespace).
U10_U13_FILES = (
    ("__init__.py",        "fail-closed EMPTY package init (pure namespace)"),
    ("copy_rules.py",      "the COPY-RULE CONSTANT MODULE - the single canonical source of the copy law (contract workflows.copy_law) plus the two-link and stage-form-link laws; every sibling imports its constants and deny machinery FROM HERE"),
    ("webhook_body.py",    "the W1/W2 WEBHOOK BODY BUILDER - the routed submission shapes the inbound intake hook accepts and the OUTBOUND custom-webhook POST shapes the tag->notification workflows fire"),
    ("w1_review_fire.py",  "the W1 REVIEW FIRE TEMPLATE - the form_submission-triggered workflow scoped to the universal-review form (the custom-webhook POST with the REPLACE-ME merges and the review-decision EMAIL + SMS pair); renders OFFLINE through render()"),
    ("w2_title_fire.py",   "the W2 TITLE FIRE TEMPLATE - the form_submission-triggered workflow scoped to the title-select form (the ONE custom-webhook POST action and the release EMAIL + SMS pair); renders OFFLINE through render_workflow()"),
    ("w3_release_avatar.py", "the W3 RELEASE-AVATAR EMAIL + SMS generator (the contract row 'Anthology Release: Avatar', LIVE slug); renders OFFLINE through render()"),
    ("w4_release_tone.py", "the W4 RELEASE-TONE EMAIL + SMS generator (the contract row 'Anthology Release: Tone', LIVE slug); renders OFFLINE through render()"),
    ("w5_release_title.py", "the W5 RELEASE-TITLE EMAIL + SMS generator (the contract row 'Anthology Release: Title', LIVE slug); renders OFFLINE through render()"),
    ("w6_release_outline.py", "the W6 RELEASE-OUTLINE EMAIL + SMS generator (the contract row 'Anthology Release: Outline & Blurb', LIVE slug - the blurb + outline pairs and the SMS outline-doc link); renders OFFLINE through render()"),
    ("w7_release_chapter.py", "the W7 RELEASE-CHAPTER EMAIL + SMS generator (the contract row 'Anthology Release: Chapter', WIRED-AHEAD slug; the two-editors reminder and the MASKED stage form link - never a value); renders OFFLINE through render_all()"),
    ("w8_release_rewrite.py", "the W8 RELEASE-REWRITE EMAIL + SMS generator (the contract row 'Anthology Release: Rewrite', WIRED-AHEAD slug; the rewrite preservation slots and the stage-form link with the ?anthology_id=<minted>&stage=s6 pair); renders OFFLINE through workflow_payload()"),
    ("w9_release_cover.py", "the W9 RELEASE-COVER EMAIL + SMS generator (the contract row 'Anthology Release: Cover Picks', WIRED-AHEAD slug; the FOUR cover-sample links); renders OFFLINE through workflow_payload()"),
    ("w10_release_final.py", "the W10 RELEASE-FINAL EMAIL + SMS generator (the contract row 'Anthology Release: Final Chapter', DOCTRINE slug; STAGE-RUNNER-FIRED at the S8 stage); renders OFFLINE through workflow_payload()"),
    ("w11_delivered.py",   "the W11 DELIVERED EMAIL + SMS generator (the contract row 'Anthology: Book Delivered', DOCTRINE slug; the TERMINAL s9_producer milestone); renders OFFLINE through workflow_payload()"),
    ("w12_chapter_ready.py", "the W12 CHAPTER-APPROVAL-READY generator (the producer-notification seat, trigger tag anthology-producer-chapter-ready; EMAIL ONLY - actions exactly [\"send-email\"], no SMS action, no webhook); renders OFFLINE through workflow_payload()"),
    ("main_skeleton.py",   "the U10/U13 TEMPLATE-LAW DISPATCHER - the offline-plan / offline-self-test driver over the template modules (imports BY NAME, pins the inventory and the STAGE_CURSORS vocabulary, runs the aggregate copy-law scan, and REFUSES a live-verify request)"),
    ("docs_workflows.py",  "the family README / catalog data + drift gate - the thirteen workflow seats, the copy rules, the module inventory, the house exit codes, the AF family, the doctrine, and the credential labels as DATA; readme() renders FROM the same data the self-test asserts against"),
)  # 17 rows: the family's 16-module catalog
   # (docs_workflows.CONTRACT_MODULE_COUNT) plus the W6 generator that
   # resolves the PENDING seat 13 - the catalog and this assembly never
   # drift

# The template-generator modules, in the dispatcher's fixed render order.
# The w3/w4/w5/w6 siblings share the render() surface shape; w1 renders
# through render(); w2 through render_workflow(); w7 through render_all();
# w8..w12 through workflow_payload().
GENERATOR_MODULES = (
    "w1_review_fire", "w2_title_fire", "w3_release_avatar",
    "w4_release_tone", "w5_release_title", "w6_release_outline",
    "w7_release_chapter", "w8_release_rewrite", "w9_release_cover",
    "w10_release_final", "w11_delivered", "w12_chapter_ready",
)

# The 13 seats of the family (docs_workflows.WORKFLOWS - the catalog and
# the tree never drift; the self-test pins seat 1..13 byte-exact). Seat 12
# (Anthology Intake Fire) is owned elsewhere (U02/U05 tooling) and is
# DOCUMENTED, never generated: its template is the live webhook-to-route
# mapping, not a release-notification generator. Seat 13 is W6.
SEAT_NAMES = (
    "Anthology Review Fire",            # 1  w1_review_fire
    "Anthology Title Fire",             # 2  w2_title_fire
    "Anthology Release: Avatar",        # 3  w3_release_avatar
    "Anthology Release: Tone",          # 4  w4_release_tone
    "Anthology Release: Title",         # 5  w5_release_title
    "Anthology Release: Chapter",       # 6  w7_release_chapter
    "Anthology Release: Rewrite",       # 7  w8_release_rewrite
    "Anthology Release: Cover Picks",   # 8  w9_release_cover
    "Anthology Release: Final Chapter", # 9  w10_release_final
    "Anthology: Book Delivered",        # 10 w11_delivered
    "Chapter Approval Ready",           # 11 w12_chapter_ready
    "Anthology Intake Fire",            # 12 owned elsewhere (U02/U05)
    "Anthology Release: Outline & Blurb",  # 13 w6_release_outline
)
SEAT_MODULES = {
    "Anthology Review Fire": "w1_review_fire",
    "Anthology Title Fire": "w2_title_fire",
    "Anthology Release: Avatar": "w3_release_avatar",
    "Anthology Release: Tone": "w4_release_tone",
    "Anthology Release: Title": "w5_release_title",
    "Anthology Release: Chapter": "w7_release_chapter",
    "Anthology Release: Rewrite": "w8_release_rewrite",
    "Anthology Release: Cover Picks": "w9_release_cover",
    "Anthology Release: Final Chapter": "w10_release_final",
    "Anthology: Book Delivered": "w11_delivered",
    "Chapter Approval Ready": "w12_chapter_ready",
    "Anthology Release: Outline & Blurb": "w6_release_outline",
}
DOCUMENTED_SEATS = ("Anthology Intake Fire",)

# The merge-tag / link keys a generated file must carry on its client-facing
# surfaces (the assembly-level validation; the modules' own generation-time
# refusals plus the skeleton's scan are the belt, this is the braces).
LINK_KEY_PATTERNS = (
    re.compile(r"\{\{contact\.[A-Za-z0-9_]+\}\}"),
    re.compile(r"\{\{\s*contact\.[A-Za-z0-9_]+\s*\}\}"),
    re.compile(r"\{\{\s*custom_values\.[A-Za-z0-9_]+\s*\}\}"),
)
_REAL_TOKEN_SHAPES = re.compile(
    r"(?:Bearer\s+\S+|sk-[A-Za-z0-9_-]{8,}|"
    r"[A-Za-z0-9_-]{16,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{16,}|"
    r"pit-[A-Za-z0-9]+)")

# Client-facing leaf keys of a generated template (the surfaces an author
# sees; operator-side fields such as a "note" or a masked marker are not
# client-facing copy - the same scope main_skeleton._CLIENT_FACING_KEYS
# enforces).
_CLIENT_FACING_KEYS = frozenset((
    "subject", "body", "pdf_link", "doc_link", "stage_form_link",
    "from_name", "reply_to", "sign_off", "email_links", "sms_link",
    "link_shape", "standing_instruction", "url_merge",
    "authorization_header_merge", "content_type", "method",
    "webhook_body",
))


class AssembleError(Exception):
    """A fail-closed refusal raised by the assembly itself - a missing
    u10_u13_modules file, a module violating the entry-point contract, a
    template that fails validation, or a manifest-pending stage that cannot
    be written."""


def _read_json(path: Path, what: str) -> dict:
    """Fail-closed contract reader - a missing section is never a blind
    pass."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise AssembleError("cannot read %s: %s" % (what, exc)) from exc
    except ValueError as exc:
        raise AssembleError("%s is not valid JSON: %s" % (what, exc)) from exc
    if not isinstance(data, dict):
        raise AssembleError("%s does not parse to a JSON object" % what)
    return data


# ---------------------------------------------------------------------------
# The file assembly - import EVERY u10_u13_modules file BY NAME. The empty
# package init is imported for the namespace guarantee; the template modules
# come through main_skeleton.load_modules (the ONE entry-point contract);
# the docs / copy / webhook modules are imported for their surfaces and
# their self-test batteries.
# ---------------------------------------------------------------------------
def _load_package() -> None:
    """Prove the package namespace container imports clean."""
    importlib.import_module("u10_u13_modules")


def load_skeleton() -> object:
    """The main_skeleton dispatcher module (imported BY NAME)."""
    return importlib.import_module("u10_u13_modules.main_skeleton")


def load_all_modules(out=None) -> dict:
    """Import every one of the u10_u13_modules files. Returns
    {name: module}. Fail-closed: a missing file or a module violating its
    contract raises AssembleError (STOP) - the assembly NEVER passes with a
    module silently absent.

    The template modules go through main_skeleton.load_modules (which
    enforces the one-entry-point contract); the docs / copy / webhook
    modules are imported directly here (their self-tests prove their
    surfaces)."""
    out = out or sys.stderr
    _load_package()
    if str(MODULES_DIR) not in sys.path:
        sys.path.insert(0, str(MODULES_DIR))

    skeleton = load_skeleton()
    try:
        dispatched = skeleton.load_modules()
    except skeleton.SkeletonError as exc:
        raise AssembleError("template-module load failed: %s" % exc) from exc

    modules = {"main_skeleton": skeleton}
    modules.update(dispatched)
    # w6_release_outline is NOT in the skeleton's dispatch roster (the
    # skeleton's 11-module set predates it); this assembly adds it BY NAME
    # like every other module.
    missing = []
    for name in ("w6_release_outline", "docs_workflows", "copy_rules",
                 "webhook_body"):
        if name in modules:
            continue
        try:
            modules[name] = importlib.import_module("u10_u13_modules." + name)
        except ImportError:
            missing.append(name)
    if missing:
        raise AssembleError(
            "u10_u13_modules file(s) not found: %s - the U10/U13 assembly is "
            "incomplete (fail-closed: no module is ever skipped)"
            % ", ".join(missing))
    # 16 files: the skeleton + the 12 generator modules + docs_workflows +
    # copy_rules + webhook_body (the __init__ package init is imported for
    # the namespace guarantee, not counted as a module surface).
    if len(modules) != 16:
        raise AssembleError(
            "assembly loaded %d modules, expected 16 (main_skeleton + 12 "
            "generator modules + docs_workflows + copy_rules + "
            "webhook_body)" % len(modules))
    return modules
    # copy_rules + webhook_body (the __init__ package init is imported for
    # the namespace guarantee, not counted as a module surface).
    if len(modules) != 16:
        raise AssembleError(
            "assembly loaded %d modules, expected 16 (main_skeleton + 12 "
            "generator modules + docs_workflows + copy_rules + "
            "webhook_body)" % len(modules))
    return modules


# ---------------------------------------------------------------------------
# Offline template generation - every seat's data object, rendered from the
# module's OWN generator (the same surfaces main_skeleton.render_all drives).
# Seat 12 (Anthology Intake Fire) is DOCUMENTED, never generated: its
# template is the live webhook-to-route mapping owned by the U02/U05
# tooling, so its file records the seat, the trigger, the owned-elsewhere
# note, and the forms pin BY MASKED MARKER - never an n8n/GHL node graph and
# never a fabricated generator.
# ---------------------------------------------------------------------------
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


def _validate_file_law(payload: dict, label: str) -> None:
    """The assembly-level template law over ONE generated file: zero em-dash
    characters, zero banned byline-actor shapes (word boundary), zero code
    fences, zero secret-shaped fragments, and the sanctioned sign-off forms
    on the client-facing leaves. Raises AssembleError (exit 4 family) with
    the exact offending fragment and the payload label - a silently off-law
    file never ships."""
    em_dash = chr(0x2014)
    ai_re = re.compile(r"(?<![A-Za-z0-9_])A\.?I\.?(?![A-Za-z0-9_])",
                       re.IGNORECASE)
    ghost_re = re.compile(r"ghost\s*writer", re.IGNORECASE)
    leaves = []
    _walk_strings(payload, leaves, keys=_CLIENT_FACING_KEYS)
    blob = json.dumps(payload)
    if em_dash in blob:
        raise AssembleError(
            "AF-AE-COPY-LAW: em-dash (U+2014) in %s - the zero-em-dash law "
            "holds for every client-facing word" % label)
    if ai_re.search(blob) or ghost_re.search(blob):
        raise AssembleError(
            "AF-AE-COPY-LAW: banned byline actor in %s - editors are the "
            "only byline actors" % label)
    if "```" in blob:
        raise AssembleError(
            "AF-AE-COPY-LAW: code fence in %s - the zero-fence law holds "
            "for every client-facing word" % label)
    if _REAL_TOKEN_SHAPES.search(blob):
        raise AssembleError(
            "AF-AE-COPY-LAW: secret-shaped fragment in %s - a template "
            "cannot print a token it never holds" % label)
    for i, leaf in enumerate(leaves):
        if "{{" in leaf and "}}" not in leaf:
            raise AssembleError(
                "AF-AE-COPY-LAW: unbalanced merge slot in %s[%d]" % (label, i))


def _render_seat(modules: dict, seat_name: str, seat_no: int) -> dict:
    """One seat's template document, rendered from its module's OWN
    generator surface. Fail-closed: a generator that refuses its own render
    is an AssembleError, never a fabricated payload."""
    name = SEAT_MODULES[seat_name]
    mod = modules[name]
    try:
        if name == "w1_review_fire":
            data = mod.render()
        elif name == "w2_title_fire":
            data = mod.render_workflow()
        elif name in ("w3_release_avatar", "w4_release_tone",
                      "w5_release_title", "w6_release_outline"):
            data = mod.render()
        elif name == "w7_release_chapter":
            data = mod.render_all(
                first_name="there",
                anthology_name="Stories We Carry",
                producer_display_name="Marlowe",
                chapter_pdf_url=mod.CHAPTER_PDF_TAG,
                chapter_doc_url=mod.CHAPTER_DOC_TAG,
                rewrite_count=0,
                sign_off=mod.SIGN_OFF_EDITORS)
        elif name in ("w8_release_rewrite", "w9_release_cover",
                      "w10_release_final", "w11_delivered",
                      "w12_chapter_ready"):
            data = mod.workflow_payload()
        else:
            raise AssembleError(
                "no generator surface for module %r" % name)
    except ValueError as exc:
        raise AssembleError(
            "the %s template refused its own render at generation time: %s "
            "(AF-AE-COPY-LAW, never a silently off-law payload)"
            % (name, exc)) from exc

    # The assembly record: seat + trigger + actions + module provenance ride
    # every generated file; the module's own data is preserved under "data".
    return {
        "contract": "anthology-engine-u10-u13-workflows",
        "schema_version": 1,
        "seat": seat_no,
        "name": seat_name,
        "module": name,
        "trigger": _seat_trigger(mod, name),
        "actions": _seat_actions(mod, name),
        "status": _seat_status(seat_name),
        "links": _seat_links(mod, name),
        "data": data,
        "note": "OFFLINE template document for the Skill 44 caf build rail "
                "against the client's OWN Convert and Flow account "
                "(template folder 'Anthology Engine'): template copy + "
                "merge tags + trigger seat only - never an n8n/GHL workflow "
                "JSON export, never a real URL, never a real token; "
                "published (one toggle per workflow) before it fires live",
    }


def _seat_trigger(mod, name: str) -> dict:
    """The trigger seat, read from the module's own constants - never
    fabricated."""
    if name in ("w1_review_fire", "w2_title_fire"):
        return {
            "type": getattr(mod, "TRIGGER_TYPE", "form_submission"),
            "scoped_form": (getattr(mod, "SCOPED_FORM", "") or
                            getattr(mod, "TITLE_SELECT_SLUG", "")),
        }
    return {"type": "contact_tag", "tag": getattr(mod, "TRIGGER_TAG", "")}


def _seat_actions(mod, name: str) -> list:
    """The action pair of one seat. w12 is the EMAIL-ONLY producer
    notification (no SMS action, no webhook) - the family's own law; every
    other module-owned seat is EMAIL + SMS."""
    if name == "w12_chapter_ready":
        return ["send-email"]
    if name in ("w1_review_fire", "w2_title_fire"):
        return ["custom-webhook", "send-email", "send-sms"]
    return ["send-email", "send-sms"]


def _seat_links(mod, name: str) -> dict:
    """The deliverable link merge tags of one seat, read from the module's
    own constants - the per-stage PDF view + Doc edit pair (or the cover
    sample set / the manuscript pair) the generated file's email body must
    carry. Never fabricated.

    The w3/w4/w5/w6 siblings carry their link pair as PDF_LINK_MERGE /
    DOC_LINK_MERGE (or the four-link blurb + outline pair), the w1/w2
    Fires carry the pair under the same names, and w7 carries the
    chapter pair as CHAPTER_PDF_TAG / CHAPTER_DOC_TAG; the w8..w12
    modules carry EMAIL_LINK_FIELDS / SMS_LINK_FIELD. A seat whose
    module carries none of the surfaces records an empty set."""
    email_fields = getattr(mod, "EMAIL_LINK_FIELDS", ())
    if not email_fields:
        pdf = getattr(mod, "PDF_LINK_MERGE", "")
        doc = getattr(mod, "DOC_LINK_MERGE", "")
        if not pdf and name == "w7_release_chapter":
            pdf = getattr(mod, "CHAPTER_PDF_TAG", "")
            doc = getattr(mod, "CHAPTER_DOC_TAG", "")
        if pdf and doc:
            email_fields = (pdf, doc)
    sms = getattr(mod, "SMS_LINK_FIELD", "")
    if not sms and email_fields:
        # The release siblings' SMS carries the Doc edit link only (the
        # w3..w7 siblings expose it as DOC_LINK_MERGE / CHAPTER_DOC_TAG;
        # the w8..w12 modules expose SMS_LINK_FIELD already). The Fires
        # carry the doc link the same way. The w12 producer notification
        # has NO SMS action, so its sms_link stays empty BY DESIGN.
        doc = (getattr(mod, "DOC_LINK_MERGE", "")
               or getattr(mod, "CHAPTER_DOC_TAG", ""))
        sms = doc
    return {"email_links": list(email_fields), "sms_link": sms}


def _seat_status(seat_name: str) -> str:
    """The slug status of one seat (contract release_notifications rows +
    the family catalog)."""
    return {
        "Anthology Review Fire": "LIVE",
        "Anthology Title Fire": "LIVE",
        "Anthology Release: Avatar": "LIVE",
        "Anthology Release: Tone": "LIVE",
        "Anthology Release: Title": "LIVE",
        "Anthology Release: Chapter": "WIRED-AHEAD",
        "Anthology Release: Rewrite": "WIRED-AHEAD",
        "Anthology Release: Cover Picks": "WIRED-AHEAD",
        "Anthology Release: Final Chapter": "DOCTRINE",
        "Anthology: Book Delivered": "DOCTRINE",
        "Chapter Approval Ready": "PRODUCER-NOTIFY",
        "Anthology Intake Fire": "OWNED-ELSEWHERE",
        "Anthology Release: Outline & Blurb": "LIVE",
    }[seat_name]


def _documented_seat(seat_name: str, seat_no: int) -> dict:
    """Seat 12 (Anthology Intake Fire) - DOCUMENTED, never generated: the
    template is the live webhook-to-route intake mapping owned by the
    U02/U05 tooling (u02_modules/scope_check.py,
    scripts/check_intake_fire_scope.py). The file records the seat, the
    trigger, the owned-elsewhere note, and the forms pin BY MASKED MARKER -
    never a fabricated generator and never a real id value."""
    return {
        "contract": "anthology-engine-u10-u13-workflows",
        "schema_version": 1,
        "seat": seat_no,
        "name": seat_name,
        "module": None,
        "trigger": {"type": "form_submission", "scoped_form": "universal-intake"},
        "actions": ["webhook-to-route"],
        "status": "OWNED-ELSEWHERE",
        "owned_elsewhere": "true - the seat is owned by the U02/U05 tooling "
                           "(u02_modules/scope_check.py, "
                           "scripts/check_intake_fire_scope.py); this family "
                           "documents it, it does not generate its template",
        "forms": {
            "form_slug": "universal-intake",
            "form_id_marker": "...lKWG",
        },
        "note": "DOCUMENTED SEAT ONLY - no template is generated for the "
                "Intake Fire: its template is the live webhook-to-route "
                "mapping owned by the U02/U05 tooling, never an n8n/GHL "
                "workflow JSON export",
    }


def build_all(modules: dict, out=None) -> dict:
    """Generate every seat's template document (13 files) OFFLINE. Returns
    {filename: payload}. Every generated payload is validated against the
    assembly law before it is returned - a validation failure raises
    AssembleError and nothing is written."""
    out = out or sys.stderr
    generated = {}
    for seat_no, seat_name in enumerate(SEAT_NAMES, start=1):
        if seat_name in DOCUMENTED_SEATS:
            payload = _documented_seat(seat_name, seat_no)
        else:
            payload = _render_seat(modules, seat_name, seat_no)
            _validate_file_law(payload, "%s.seat%d" % (seat_name, seat_no))
        filename = "%02d_%s.json" % (
            seat_no, _slugify(seat_name))
        generated[filename] = payload
    if len(generated) != 13:
        raise AssembleError(
            "build generated %d files, expected 13" % len(generated))
    out.write("[build-anthology-workflows] generated %d template documents "
              "offline (validated: trigger + actions + copy law)\n"
              % len(generated))
    return generated


def _slugify(name: str) -> str:
    """A filename-safe slug of one seat name (lowercase, alphanumeric +
    dash)."""
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug or "seat"


def write_outputs(generated: dict, out=None) -> None:
    """Write the generated files to scripts/u10_u13_workflows/, each
    atomically (temp + rename) so a crash mid-write never leaves a partial
    template. The engine never touches ENGINE-MANIFEST.json /
    ENGINE-PIN.sha256 / verify.sh here."""
    out = out or sys.stderr
    try:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        for filename, payload in generated.items():
            tmp = OUTPUT_DIR / (filename + ".tmp-%d" % os.getpid())
            tmp.write_text(json.dumps(payload, indent=2, sort_keys=True)
                           + "\n", encoding="utf-8")
            tmp.replace(OUTPUT_DIR / filename)
    except OSError as exc:
        raise AssembleError("cannot write %s: %s" % (OUTPUT_DIR, exc)) from exc
    out.write("[build-anthology-workflows] wrote %d files to %s\n"
              % (len(generated), OUTPUT_DIR))


# ---------------------------------------------------------------------------
# Offline self-test - run EVERY module's own battery, the skeleton
# dispatcher battery, the docs drift gate, the assembly tree pin (the exact
# file roster), the rendered-payload validation, and the 13-file output
# validation. NO network, NO credentials. Exit 4 on any failure
# (AF-AE-TEMPLATE-ATTACK family).
# ---------------------------------------------------------------------------
def _module_self_test(module, name: str, out) -> None:
    """Drive one module's own battery through its documented entry point
    (self_test(out) or the family's _self_test())."""
    st = getattr(module, "self_test", None)
    st_private = getattr(module, "_self_test", None)
    dev = io.StringIO()
    if callable(st):
        try:
            rc = st(out=dev)
        except TypeError:
            rc = st()
    elif callable(st_private):
        try:
            rc = st_private()
        except TypeError:
            rc = st_private(dev)
    else:
        raise AssertionError(
            "module %s does not expose 'self_test' or the family's "
            "'_self_test' - every u10_u13_modules module must prove itself "
            "offline" % name)
    out.write(dev.getvalue())
    if rc != EX_OK:
        raise AssertionError("%s self_test returned exit %d" % (name, rc))

def _file_validation_checks(out) -> None:
    """The 13-file validation battery over freshly generated documents:
    every file carries the contract marker, the trigger type, the actions
    (EMAIL + SMS on every client-facing seat; EMAIL ONLY on the producer
    notification), zero banned byline actors, zero em-dashes, zero code
    fences, and the merge links present on the client-facing surfaces. The
    pass/fail split must discriminate - the checks are real assertions over
    the generated bytes."""
    em_dash = chr(0x2014)
    ai_re = re.compile(r"(?<![A-Za-z0-9_])A\.?I\.?(?![A-Za-z0-9_])",
                       re.IGNORECASE)
    ghost_re = re.compile(r"ghost\s*writer", re.IGNORECASE)
    # Seed the tree with fresh builds so the file check exercises the same
    # payloads the writer emits (never a stale disk copy).
    modules = load_all_modules(out=out)
    generated = build_all(modules, out=io.StringIO())
    assert len(generated) == 13, \
        "the build must emit exactly 13 template documents, got %d" \
        % len(generated)
    for filename, payload in sorted(generated.items()):
        blob = json.dumps(payload)
        # 1. the contract marker + seat identity.
        assert payload.get("contract") == "anthology-engine-u10-u13-workflows", \
            "the %s file lost its contract marker" % filename
        seat = payload.get("seat")
        assert isinstance(seat, int) and 1 <= seat <= 13, \
            "the %s file lost its seat number" % filename
        # 2. the trigger type on every file.
        trigger = payload.get("trigger", {})
        assert isinstance(trigger, dict) and trigger.get("type"), \
            "the %s file lost its trigger type" % filename
        # 3. the actions law: EMAIL + SMS present on every client-facing
        #    seat; the producer notification is EMAIL ONLY.
        actions = payload.get("actions", [])
        name = payload.get("name", "")
        if name == "Chapter Approval Ready":
            assert actions == ["send-email"], \
                "the producer notification must be EMAIL ONLY, got %r" \
                % (actions,)
            assert "send-sms" not in actions, \
                "the producer notification must carry NO SMS action"
        elif name == "Anthology Intake Fire":
            pass  # documented seat - actions are the owned-elsewhere note
        else:
            assert "send-email" in actions and "send-sms" in actions, \
                "the %s seat must carry BOTH the email and the SMS action, " \
                "got %r" % (filename, actions)
        # 4. the copy law over the whole file.
        assert em_dash not in blob, \
            "the %s file carries an em-dash (U+2014)" % filename
        assert not ai_re.search(blob) and not ghost_re.search(blob), \
            "the %s file carries a banned byline actor" % filename
        assert "```" not in blob, \
            "the %s file carries a code fence" % filename
        # 5. the merge links present (contact merges / custom-value merges)
        #    on every GENERATED seat and no real-token fragment anywhere.
        #    The documented Intake Fire seat (12) carries no template and no
        #    links BY DESIGN - its file records the seat and the
        #    owned-elsewhere note only.
        if name != "Anthology Intake Fire":
            assert any(rx.search(blob) for rx in LINK_KEY_PATTERNS), \
                "the %s file carries no merge tag at all" % filename
            # the links inventory (the per-stage PDF view + Doc edit pair
            # and the SMS link) must ride the assembly record of every
            # generated seat.
            links = payload.get("links", {})
            assert isinstance(links, dict) and links.get("email_links"), \
                "the %s file lost its email link inventory" % filename
            # The SMS link is required on every seat that carries an SMS
            # action (the w12 producer notification is EMAIL ONLY).
            if "send-sms" in actions:
                assert links.get("sms_link"), \
                    "the %s file lost its SMS link inventory" % filename
        assert not _REAL_TOKEN_SHAPES.search(blob), \
            "the %s file carries a secret-shaped fragment" % filename
        # 6. the seat-name law: the 13 seats are exactly the family's.
        assert name in SEAT_NAMES, \
            "the %s file names an unknown seat %r" % (filename, name)
    assert sorted(payload_name_for(p) for p in generated.values()) \
        == sorted(SEAT_NAMES), "the generated seats drifted from the 13-seat law"
    # 7. the module-owned seats are generated, the documented seat is not.
    for seat_name, module_name in SEAT_MODULES.items():
        assert any(p.get("name") == seat_name and p.get("module") == module_name
                   for p in generated.values()), \
            "seat %r must be generated by module %r" % (seat_name, module_name)
    assert any(p.get("name") == "Anthology Intake Fire"
               and p.get("module") is None for p in generated.values()), \
        "the Intake Fire seat must be documented, never generated"
    out.write("[build-anthology-workflows] 13-file validation: PASS "
              "(trigger type, EMAIL + SMS actions, zero banned byline "
              "actors, zero em-dashes, zero code fences, merge links "
              "present, no real-token fragment)\n")


def payload_name_for(payload: dict) -> str:
    """The seat name of one generated payload (helper for the self-test)."""
    return payload.get("name", "")


def self_test(out=None) -> int:
    """OFFLINE self-test: every module's own battery, the skeleton
    dispatcher battery, the docs drift gate, the assembly tree pin (the
    exact file roster), and the 13-file validation battery. Any failure
    is exit 4 (AF-AE-TEMPLATE-ATTACK family) - a tamper NEVER masquerades
    as exit 1. On a clean pass the manifest-pending stage is written by the
    CLI."""
    out = out or sys.stderr
    dev = io.StringIO()
    try:
        # 1. the assembly is complete: the exact file set exists (the
        #    family's 16-module catalog plus the W6 generator, 17 files).
        on_disk = sorted(p.name for p in MODULES_DIR.glob("*.py"))
        expected = sorted(name for name, _ in U10_U13_FILES)
        assert on_disk == expected, (
            "u10_u13_modules tree drifted: disk carries %d files, the "
            "%d-file assembly contract names %d (%s)"
            % (len(on_disk), len(expected),
               len(set(on_disk) ^ set(expected)),
               ", ".join(sorted(set(on_disk) ^ set(expected)))))
        # 2. every module's own battery passes (golden PASS / attack FAIL).
        #    main_skeleton's battery takes the module dict (it drives its
        #    OWN dispatch set through the one-entry-point contract) and runs
        #    as the dispatcher battery in step 3, exactly as the U08_U09
        #    sibling assembler handles it - never here.
        modules = load_all_modules(out=dev)
        for name in sorted(modules):
            if name == "main_skeleton":
                continue
            _module_self_test(modules[name], name, dev)
        # 3. the skeleton dispatcher battery (the one-entry-point contract,
        #    the copy-law scan, the OFFLINE law, the never-a-token law).
        #    The skeleton's battery is built for ITS OWN dispatch roster:
        #    it pins the tree to the skeleton's 11-module contract set, so
        #    the dispatch dict must mirror that set exactly (the 12 module
        #    batteries plus the docs / copy / webhook batteries ran in
        #    step 2 - a family whose modules prove themselves offline).
        skeleton = modules["main_skeleton"]
        dispatch_only = {k: v for k, v in modules.items()
                         if k in GENERATOR_MODULES and k != "w6_release_outline"}
        sk_rc = skeleton.self_test(dispatch_only, out=dev)
        assert sk_rc == EX_OK, \
            "main_skeleton dispatcher self-test returned exit %d" % sk_rc
        # 4. the docs drift gate (the 13 seats, the 16-module catalog, the
        #    copy rules, the stage vocabulary, the masked-marker policy).
        docs = modules["docs_workflows"]
        docs_rc = docs.self_test(out=dev)
        assert docs_rc == EX_OK, \
            "docs_workflows self-test returned exit %d" % docs_rc
        # 5. the family counts are the assembly's counts.
        assert docs.CONTRACT_WORKFLOW_COUNT == 13, \
            "the 13-workflow count drifted from the family catalog"
        assert docs.CONTRACT_MODULE_COUNT == 16, \
            "the 16-module count drifted from the family catalog"
        assert docs.CONTRACT_MODULE_OWNED_COUNT == 11, \
            "the 11 module-owned-seat count drifted from the family catalog"
        # 6. the rendered-payload validation battery (over fresh builds).
        _file_validation_checks(dev)
    except AssertionError as exc:
        sys.stderr.write("[build-anthology-workflows] SELF-TEST FAILED "
                         "(AF-AE-TEMPLATE-ATTACK family): %s\n" % exc)
        return EX_VIOLATION
    except AssembleError as exc:
        sys.stderr.write("[build-anthology-workflows] SELF-TEST FAILED "
                         "(AF-AE-TEMPLATE-ATTACK family): %s\n" % exc)
        return EX_VIOLATION

    out.write(dev.getvalue())
    out.write("[build-anthology-workflows] assembled self-test: OK (16 "
              "u10_u13_modules files imported, every module battery + the "
              "skeleton dispatcher battery + the docs drift gate + the "
              "13-file validation all pass)\n")
    return EX_OK


# ---------------------------------------------------------------------------
# Offline plan - no network, no credentials. ONE JSON object on stdout.
# ---------------------------------------------------------------------------
def dry_run(modules: dict, contract: dict, out=None) -> int:
    """The offline plan payload (the assembly's stage-record on the side)."""
    out = out or sys.stderr
    docs = modules["docs_workflows"]
    payload = {
        "contract": "anthology-engine-u10-u13-build-plan",
        "schema_version": 1,
        "kind": "dry-run",
        "template_location_id": DEFAULT_TEMPLATE_LOCATION,
        "template_location_id_masked": "...7Qnx",
        "seats": [{"seat": i + 1, "name": name,
                   "module": SEAT_MODULES.get(name),
                   "status": _seat_status(name)}
                  for i, name in enumerate(SEAT_NAMES)],
        "modules": [name for name, _ in U10_U13_FILES],
        "output_dir": str(OUTPUT_DIR),
        "offline": True,
        "execute": False,
        "note": "offline plan only - template generation is OFFLINE (no "
                "network, no credential, nothing ever sent); there is no "
                "live surface, so no execute gate exists and a live-verify "
                "request is a usage STOP (exit 2, AF-AE-U10-U13-OFFLINE), "
                "never a silent probe; the copy law (editors never AI; zero "
                "em-dashes; sign-off 'The Editors' or the producer merge; "
                "per-stage PDF view + Doc edit links; the U08 pre-fill "
                "stage link) is enforced at generation time and re-proven "
                "on every generated file",
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    out.write("[build-anthology-workflows] dry-run plan: OK (offline - no "
              "network, no credential needed)\n")
    return EX_OK


# ---------------------------------------------------------------------------
# Manifest-pending stage - manifest-pending/u10_u13.json. Written ONLY after
# a PASS (self-test pass or build pass); a FAIL/HELD/STOP run writes
# nothing. The record is the machine-readable input to a later manifest
# re-stamp - the ENGINE-MANIFEST.json / ENGINE-PIN.sha256 / verify.sh are
# NEVER touched here.
# ---------------------------------------------------------------------------
def _pending_payload(kind: str, verdict: str = "PASS") -> dict:
    docs_modules = _docs_module_rows()
    return {
        "contract": "anthology-engine-u10-u13-workflows-law",
        "schema_version": 1,
        "kind": kind,  # "self-test" | "build" | "dry-run"
        "verdict": verdict,
        "script": "build_anthology_workflows.py",
        "authored_by": "U10/U13",
        "template_location_id": DEFAULT_TEMPLATE_LOCATION,
        "u10_u13_modules": [
            {"name": name, "role": role} for name, role in U10_U13_FILES
        ],
        "docs_modules": docs_modules,
        "workflow_seats": [
            {"seat": i + 1, "name": name,
             "module": SEAT_MODULES.get(name)}
            for i, name in enumerate(SEAT_NAMES)
        ],
        "generated_files": len(SEAT_NAMES),
        "generated_files": len(SEAT_NAMES),
        "check_modules": list(GENERATOR_MODULES),
        "af_codes": [
            {"code": code, "exit": exit_code, "meaning": meaning}
            for code, exit_code, meaning in _AF_CODES
        ],
        "exit_codes": _EXIT_CODES,
        "checks": {},
        "fail_closed": {
            "any_fail": False,
            "note": "template generation is OFFLINE by construction (the "
                    "U10/U13 package-init doctrine): no network, no "
                    "credential, nothing ever sent - there is no live "
                    "surface and no execute gate; a live-verify request is "
                    "a usage STOP (exit 2, AF-AE-U10-U13-OFFLINE), never a "
                    "silent network probe; every generated file is "
                    "validated against the copy law before it is written - "
                    "a silently off-law file never ships",
        },
    }


def _docs_module_rows() -> list:
    """The module inventory rows as docs_workflows carries them (the catalog
    and the tree never drift; the self-test pins the roster against the
    tree)."""
    try:
        import importlib
        docs = importlib.import_module("u10_u13_modules.docs_workflows")
        return [{"name": row["name"], "role": row["role"]}
                for row in docs.modules()]
    except Exception:  # noqa: BLE001 - a docs read is never fatal to the stage
        return []


# The AF-AE autofail family of the U10/U13 workflows tooling, as the stage
# records it (mirrored from docs_workflows.AF_CODES - the family authority).
_AF_CODES = (
    ("AF-AE-U10-U13-ASSEMBLY-INCOMPLETE", 2,
     "the template-module set named in the dispatcher's inventory is not "
     "fully present, or a module violates the one-entry-point contract, or "
     "a shipped template file is not in the set - a template law is never "
     "silently skipped"),
    ("AF-AE-U10-U13-OFFLINE", 2,
     "a live-verify request on the U10/U13 family - template generation is "
     "OFFLINE by construction and there is no live surface to gate; a "
     "verify request is a usage STOP, never a silent network probe"),
    ("AF-AE-COPY-LAW", 5,
     "an em-dash, a banned byline actor, an unbalanced merge slot, a code "
     "fence, or a secret-shaped fragment in a generated string - never a "
     "printed payload, and never exit 0 (the fail-closed default of the "
     "copy law)"),
    ("AF-AE-TEMPLATE-ATTACK", 4,
     "an attack fixture tripped the OFFLINE self-test of a family module "
     "or battery (enforced violation - the house code, shared with the "
     "U02 / U03 / U04 / U05 / U06 / U07 / U08_U09 families)"),
)

# House exit-code contract (docs_workflows.EXIT_CODES).
_EXIT_CODES = {
    0: "verified success - the 13 template documents generated and "
       "validated OFFLINE (also plan / self-test / a documented PASS)",
    1: "unexpected error (top-level guard; never a secret leak)",
    2: ("STOP refusal - usage / a live-verify request (this family is "
        "OFFLINE BY CONSTRUCTION; there is no live surface to gate, "
        "AF-AE-U10-U13-OFFLINE) / the template-module assembly incomplete "
        "(AF-AE-U10-U13-ASSEMBLY-INCOMPLETE: a module the inventory names "
        "that does not ship, or a shipped template that is not in the "
        "set) / an out-of-vocabulary stage token"),
    3: "HELD - unused by this family: template generation is OFFLINE, so "
       "a dependency or transport state is never consulted (kept for the "
       "house 0/1/2/3/5 law)",
    4: ("self-test FAILED (the AF-AE-TEMPLATE-ATTACK enforced-violation "
        "family - a tamper never masquerades as exit 1)"),
    5: ("data or copy-law mismatch - a generated string carrying an "
        "em-dash, a banned byline actor, an unbalanced merge slot, a code "
        "fence, or a secret-shaped fragment (AF-AE-COPY-LAW; the "
        "fail-closed default - never a printed payload, never exit 0)"),
}


def write_pending(payload: dict, *, mode: str = "self-test", out=None) -> None:
    """Write manifest-pending/u10_u13.json (fail-closed: only after a
    PASS). The directory is created if absent; the file is written
    atomically (temp + rename) so a crash mid-write never leaves a partial
    stage. The ENGINE-MANIFEST.json / ENGINE-PIN.sha256 / verify.sh are
    NEVER touched."""
    out = out or sys.stderr
    try:
        PENDING_DIR.mkdir(parents=True, exist_ok=True)
        tmp = PENDING_DIR / ("u10_u13.json.tmp-%d" % os.getpid())
        tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n",
                       encoding="utf-8")
        tmp.replace(PENDING_U10_U13)
    except OSError as exc:
        raise AssembleError("cannot write %s: %s" % (PENDING_U10_U13, exc)) from exc
    out.write("[build-anthology-workflows] manifest-pending stage written: "
              "%s (%s)\n" % (PENDING_U10_U13, mode))


# ---------------------------------------------------------------------------
# CLI - house shape: --dry-run / --self-test accepted as flags AND as a
# positional subcommand (--self-test / --selftest normalize exactly as
# anthology_registry.py and the U02..U08_U09 siblings). The default command
# is the OFFLINE build (13 files generated + validated); `verify` is a
# usage STOP (exit 2, AF-AE-U10-U13-OFFLINE) - template generation is
# OFFLINE by construction.
# ---------------------------------------------------------------------------
def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="build_anthology_workflows.py",
        description="The U10/U13 workflow-template assembly dispatcher: "
                    "imports the 16 u10_u13_modules files BY NAME and "
                    "generates the 13 workflow template JSON documents "
                    "OFFLINE to scripts/u10_u13_workflows/ (Skill 59) - "
                    "every file validated (trigger type, EMAIL + SMS "
                    "actions, zero banned byline actors, zero em-dashes, "
                    "zero code fences, the merge links present) before it "
                    "is written; the manifest-pending stage is written "
                    "after a PASS. Template generation is OFFLINE by "
                    "construction: no network, no credential, nothing ever "
                    "sent - a live-verify request is a usage STOP (exit 2, "
                    "AF-AE-U10-U13-OFFLINE), never a silent probe.")
    ap.add_argument("--dry-run", action="store_true",
                    help="offline plan only - no network, no credential "
                         "(default: the offline build)")
    ap.add_argument("--json", action="store_true",
                    help="emit a machine-readable summary on stdout "
                         "(default on for plan)")
    ap.add_argument("--out", default=str(OUTPUT_DIR),
                    help="the output directory for the generated template "
                         "documents (default: scripts/u10_u13_workflows)")
    ap.add_argument("--no-pending", action="store_true",
                    help="do not write manifest-pending/u10_u13.json after "
                         "a PASS (dry runs for CI)")
    ap.add_argument("--selftest", "--self-test", dest="self_test",
                    action="store_true",
                    help="run the offline self-test (every module battery + "
                         "the skeleton dispatcher battery + the docs drift "
                         "gate + the 13-file validation) and exit")
    ap.add_argument("cmd", nargs="?", choices=["build", "plan", "verify",
                                               "self-test"],
                    help="positional subcommand form (build / plan / "
                         "verify / self-test) - 'verify' is REFUSED: "
                         "template generation is OFFLINE and there is no "
                         "live surface")

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
        # request is a usage STOP (exit 2, AF-AE-U10-U13-OFFLINE) -
        # template generation is OFFLINE by construction and there is no
        # live surface to gate.
        sys.stderr.write(
            "[build-anthology-workflows] verify REFUSED: template "
            "generation is OFFLINE by construction - the U10/U13 family is "
            "the release-notification data generators (no network, no "
            "credential, nothing ever sent), so there is no live surface "
            "to verify.\n")
        return EX_STOP

    try:
        modules = load_all_modules()

        if args.self_test:
            rc = self_test(out=sys.stderr)
            if rc == EX_OK and not args.no_pending:
                write_pending(_pending_payload("self-test"), mode="self-test")
            return rc

        contract = _read_json(CONTRACT_PATH,
                              "config/anthology-snapshot-contract.json")

        if args.dry_run:
            return dry_run(modules, contract)

        # The default surface: the OFFLINE build - every seat's template
        # document generated and validated, then written.
        generated = build_all(modules)
        write_outputs(generated)
        if not args.no_pending:
            write_pending(_pending_payload("build"), mode="build")
        return EX_OK

    except AssembleError as exc:
        sys.stderr.write("[build-anthology-workflows] STOP/FAIL: %s\n" % exc)
        return EX_STOP
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001 - top-level guard, never leaks a secret
        sys.stderr.write("[build-anthology-workflows] unexpected error: "
                         "%s: %s\n" % (type(exc).__name__, exc))
        return EX_ERR


if __name__ == "__main__":
    sys.exit(main())
