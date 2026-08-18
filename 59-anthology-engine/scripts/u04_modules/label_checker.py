#!/usr/bin/env python3
# =============================================================================
# SKILL 59 — ANTHOLOGY ENGINE :: u04_modules/label_checker.py  (U04 tooling)
# RAW-KEY LABEL CHECKER — the fail-closed gate that the engine's raw-key
# labels (ideal_avatar, niche, primary_goal, ...) are the SAME canonical
# field the warm client language map carries, and that NO client-facing
# surface ever speaks the raw key instead of the warm label.
# -----------------------------------------------------------------------------
# WHAT THIS OWNS — THE RAW-KEY LAW, OFFLINE
#   The engine's ledger stores participant answers under machine keys
#   (participants.ideal_avatar / niche / primary_goal / chapter_about /
#   personal_stories / tone_inputs, per scripts/anthology_state.py), and the
#   universal author-intake form carries them under the same raw keys (the
#   intake_router.py field_candidates law: ideal_avatar / idealAvatar / q1 /
#   Q1 / customData.ideal_avatar are the SAME field, never a second column).
#   The warm client language map is the human-facing vocabulary: the same
#   concept spoken to the client as "My Ideal Avatar / Dream Customer"
#   (Skill 52 intake-schema shared_required), "My Niche / category",
#   "My Ideal Avatar's Primary Goal", and in the sanctioned nudge templates
#   as the client-clean deliverable labels ("author profile", "tone profile",
#   "title options", "blurb and outline", "outline", "chapter draft",
#   "anthology readiness", "manuscript") with the "Warmly," sign-off and
#   zero em dashes. A client-facing surface that says "ideal_avatar" instead
#   of the warm label ships a plumbing key into the client's brand — the
#   same class of defect the G3 query-key gate refuses.
#
#   THIS module is the OFFLINE, fail-closed tripwire over the committed
#   engine assets and prompts: it proves the raw-key set and the warm-label
#   set are a coherent map (every raw key has a warm label; the two
#   vocabularies never collide), and it scans the client-facing template
#   family (config/nudge-templates/*.md) for any raw key that leaked into a
#   {{slot}} or a literal. It NEVER fetches, NEVER resolves a credential,
#   and NEVER reads a secret: it is pure local shape analysis, so it runs
#   with zero network and zero tokens.
#
# FAIL-CLOSED, BOTH DIRECTIONS:
#   - a raw key with NO warm label in the map               -> FAIL (the map
#     is incomplete; a client surface would have no warm word to use),
#   - a warm label that IS a raw key (the vocabularies collide, e.g. a
#     label that says "ideal_avatar" instead of "My Ideal Avatar /
#     Dream Customer")                                       -> FAIL,
#   - a raw key that appears as a {{slot}} or a literal in a sanctioned
#     client-facing template                               -> FAIL (the raw
#     key leaked onto a client surface; never a silent pass),
#   - a template whose slots are not all in the map         -> FAIL (an
#     unmapped slot cannot be spoken warmly — AF-AE-SLOT-UNRESOLVED
#     family),
#   - the map or a template cannot be read (missing / malformed) -> STOP
#     (a check that cannot see its law never fabricates a pass).
#
# THE LAW IS READ ONCE: the canonical raw-key set is mirrored from
# scripts/anthology_state.py (participants columns) and
# scripts/intake_router.py (field_candidates keys + upsert_scalar_fields)
# exactly as required_checker.py mirrors the required-flags law — the
# delta_reporter single-implementation doctrine. The warm-label map is the
# committed engine surface: the Skill 52 shared_required wording
# (intake/intake-schema.json), the Skill 54 intake wording
# (intake/aw-intake-schema.json), and nudge_send.py GATE_META
# (client-clean deliverable labels, never a stage code). The self-test pins
# the mirror byte-equal against those sources, so a drift between the raw
# keys and the warm language trips the battery before it can ship.
#
# CREDENTIALS: this module holds ZERO credential surface — it reads no env
# var and resolves no label (the required_checker.py construction). A raw
# key is a field NAME, never a value; this module never prints a value.
#
# BROWSER UA: no network surface exists here, so no User-Agent rides this
# module. The rule it ENFORCES for its siblings: any module in the u04
# package that talks to GoHighLevel / Convert and Flow
# (services.leadconnectorhq.com, Cloudflare-fronted) MUST send a browser
# User-Agent on every request (reg.CafClient applies CAF_BROWSER_UA — CF
# error 1010 403s urllib's default "Python-urllib/x.y" UA at the WAF edge
# before the request ever reaches the API; W0.6 / GK-09 discipline, the
# house pattern ported byte-for-byte from the Podcast gate).
#
# EXIT CODES (house convention 0/1/2/3/4/5; ENGINE-MANIFEST.json
# exit_code_house_convention):
#   0  PASS — the raw-key set and the warm-label map are coherent and no
#      raw key leaks onto a client-facing surface (also plan and self-test
#      PASS)
#   1  unexpected error (top-level guard; never a secret leak)
#   2  STOP refusal — a source of truth cannot be read (anthology_state /
#      intake_router / nudge_send unreadable, the map or a template
#      missing/malformed): the law is unverifiable — a check that cannot
#      see its law never fabricates a pass
#   4  self-test FAILED (an offline assertion tripped; a tamper NEVER
#      masquerades as exit 1)
#   5  FAIL — a raw key has no warm label, the vocabularies collide, a raw
#      key leaks into a sanctioned client-facing template, or a template
#      slot is unmapped (AF-AE-LABEL family; the fail-closed verdict for a
#      drifted label map)
#   (3 is not applicable here: no live surface, nothing to hold)
#
# USAGE (machine surface — ONE JSON object on stdout; human notes on stderr;
# --self-test is OFFLINE and needs NO token and NO network):
#   label_checker.py check            # offline: the raw-key law + the warm
#                                     # label map applied to the committed
#                                     # templates
#   label_checker.py plan             # offline; the raw-key / warm-label
#                                     # map with its sources of truth
#   label_checker.py self-test        # offline golden + attack fixtures
#
# STDLIB ONLY. Calls NO model. Sibling import bootstrap identical to the
# other u04 modules: sys.path.insert to scripts/ then
# `import anthology_registry as reg` for its canonical constants. DOCTRINE:
# move in silence; NOTHING Anthropic in any runtime file; Convert and Flow
# naming in every client surface; NEVER print a secret value.
# =============================================================================
"""label_checker.py — the engine's raw-key / warm-client-language map gate:
every raw ledger key (ideal_avatar etc.) has a warm human label, and no raw
key ever leaks onto a client-facing surface."""

from __future__ import annotations

import argparse
import io
import json
import re
import sys
from pathlib import Path

# Sibling import bootstrap (house convention): the registry owns the
# canonical constants (CAF_BROWSER_UA / CAF_VERSION_HEADER) and the
# fail-closed helper surfaces; this module mirrors the constants it needs and
# pins the mirror in its offline self-test.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import anthology_registry as reg  # noqa: E402

EX_OK, EX_ERR, EX_STOP = reg.EX_OK, reg.EX_ERR, reg.EX_STOP
EX_MISMATCH = reg.EX_MISMATCH
EX_VIOLATION = 4  # enforced violation detected (self-test FAILED)

SKILL_DIR = Path(__file__).resolve().parent.parent.parent
STATE_PATH = SKILL_DIR / "scripts" / "anthology_state.py"
ROUTER_PATH = SKILL_DIR / "scripts" / "intake_router.py"
NUDGE_PATH = SKILL_DIR / "scripts" / "nudge_send.py"
TEMPLATES_DIR = SKILL_DIR / "config" / "nudge-templates"

# The client-facing template family this gate scans. The sanctioned set is
# nudge_send.py SANCTIONED (the ONLY three templates the engine may send —
# SPEC 3.4 row 8 / 10.5); the scan covers exactly those files.
SANCTIONED_TEMPLATES = ("gate-open.md", "completion.md", "stuck-renudge.md")

# The slot shape in the templates ({{slot}}), the same shape nudge_send.py
# SLOT_RE / RESIDUAL_RE resolve (fail-closed on any residual).
_SLOT_RE = re.compile(r"\{\{\s*([A-Za-z0-9_]+)\s*\}\}")
_RESIDUAL_RE = re.compile(r"\{\{.*?\}\}", re.DOTALL)

# The em-dash family the client surfaces must never carry (nudge_send.py
# EM_DASH / the qc-tier1 _EMDASH_CHARS law; U+2014 em dash, U+2015 bar).
_EMDASH_CHARS = ("—", "―")

# ---------------------------------------------------------------------------
# The WARM CLIENT LANGUAGE MAP — the canonical human labels for every raw
# key. This is the ONE committed map this module owns and pins: a raw key
# without a warm label, or a warm label that is itself a raw key, is a FAIL.
# The wording is mirrored from the committed sources named per entry
# (Skill 52 intake-schema shared_required, Skill 54 aw-intake-schema,
# nudge_send.py GATE_META deliverable labels, the snapshot contract copy
# law). Each label is a human, client-clean phrase — never a stage code,
# never an internal name (the nudge_send.py GATE_META doctrine).
# ---------------------------------------------------------------------------
WARM_LABELS = {
    # -- the universal author-intake answers (Skill 52 shared_required /
    #    intake-schema.json wording, mirrored byte-for-byte) ----------------
    "first_name": "First name",
    "last_name": "Last name",
    "email": "Email",
    "phone": "Phone",
    "ideal_avatar": "My Ideal Avatar / Dream Customer",
    "niche": "My Niche / category",
    "primary_goal": "My Ideal Avatar's Primary Goal",
    "chapter_about": "What your chapter is about",
    "personal_stories": "Personal stories, facts, or quotes",
    "tone_inputs": "Writing tone",
    "title_locked": "Your locked title",
    "subtitle_locked": "Your locked subtitle",
    "chapter_updates": "Your requested chapter changes",
    # -- the Skill 52 / 53 / 54 shared intake fields ------------------------
    "tone": "My Writing Tone",
    "tone_style_1": "First well-known figure whose style to incorporate",
    "tone_style_2": "Optional second figure (N/A allowed)",
    "tone_style_3": "Optional third figure (N/A allowed)",
    "tone_style_4": "Optional fourth figure (N/A allowed)",
    "target_market": "Target market",
    "offer_name": "Offer name",
    "offer_type": "Offer type",
    "offer_benefit": "Offer benefit",
    "product_info": "Product info",
    "brand_info": "Brand info",
    "brand_start_date": "Brand start date",
    "brand_why": "Why you started this brand",
    "brand_colors": "Brand colors",
    "book_about": "What you want your book to be about",
    "book_stories": "Personal stories, facts, or quotes for the book",
    "cover_description": "Book cover description",
    # -- the Skill 54 (anthology writer) intake fields -----------------------
    "anthology_title": "The book this chapter belongs to",
    "chapter_premise": "The spine of your chapter",
    "subtitle_hint": "Optional subtitle steer",
    "target_reader": "The reader this is written for",
    "tone_influences": "Tone influences",
    "client_folder_name": "Deliverable folder label",
    # -- the hidden / routing fields (never typed, never displayed) ---------
    "contact_id": "Contact id",
    "anthology_id": "Book id",
    "stage": "Current step",
    "location": "Location",
    # -- the nudge_send.py GATE_META client-clean deliverable labels --------
    "author profile": "author profile",
    "tone profile": "tone profile",
    "title options": "title options",
    "blurb and outline": "blurb and outline",
    "outline": "outline",
    "chapter draft": "chapter draft",
    "anthology readiness": "anthology readiness",
    "manuscript": "manuscript",
    # -- the nudge template slots (resolved by the client-clean serializer) --
    "deliverable_label": "your deliverable",
    "gate_link": "your link",
    "deliverable_link": "your document link",
    "producer_display_name": "the editorial team",
    "anthology_name": "the anthology",
}

# The raw-key vocabulary that must NEVER ride a client surface as a literal
# (the machine keys this gate refuses in a template). Everything else is
# permitted: a template may speak any human word, but never a plumbing key.
# The keys are matched as snake_case IDENTIFIER shapes only — a bare English
# word inside a warm label ("My Niche / category") can never trip this, and
# a camelCase alias (idealAvatar) is the same field and equally refused.
_RAW_KEY_RE = re.compile(
    r"(?i)\b("
    r"ideal_avatar|idealavatar|primary_goal|primarygoal|chapter_about|"
    r"chapterabout|personal_stories|tone_inputs|tone_style_[1-4]|"
    r"tone_influences|chapter_premise|chapterpremise|anthology_title|"
    r"subtitle_hint|target_reader|target_market|offer_name|offer_type|"
    r"offer_benefit|product_info|brand_info|brand_start_date|brand_why|"
    r"brand_colors|book_about|book_stories|cover_description|"
    r"client_folder_name|contact_id|anthology_id|stage_cursor|"
    r"title_locked|subtitle_locked|chapter_updates|rewrite_count|"
    r"bio_source|contributor_name|one_line_summary|word_count|subtheme|"
    r"strength_signal|chapter_title"
    r")\b")


class LabelError(Exception):
    """A fail-closed refusal: the label law is unverifiable (a source of
    truth cannot be read) or a violation was detected (AF-AE-LABEL family)."""


class LabelContractError(LabelError):
    """STOP family: a source of truth (anthology_state / intake_router /
    nudge_send) cannot be read, so the raw-key law is unverifiable."""


# ---------------------------------------------------------------------------
# Sources of truth — read ONCE, from the owning modules, never hardcoded
# (the required_checker.py _required_fields construction; SPEC M8: a law is
# read once, from the module that owns it).
# ---------------------------------------------------------------------------
def _read_source(path: Path, what: str) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        raise LabelContractError(
            "AF-AE-LABEL-CONTRACT-UNREADABLE: %s (%s) cannot be read — the "
            "raw-key law is unverifiable" % (what, type(exc).__name__)) from exc


def _state_raw_keys() -> list:
    """The canonical participant ANSWER keys from anthology_state.py's
    participants schema, in table order, EXCLUDING the ledger plumbing
    columns (participant_key / stage_cursor / qc_attempts_current /
    hold_reason / stage_timestamps / drive_folder_id / created_at /
    updated_at / rewrite_count — machine state, never an intake answer, so
    they carry no warm client label). Mirrored by regex over the committed
    source — never hardcoded here."""
    text = _read_source(STATE_PATH, "scripts/anthology_state.py")
    m = re.search(r"CREATE TABLE IF NOT EXISTS participants\s*\((.*?)\);",
                  text, re.S)
    if not m:
        raise LabelContractError(
            "AF-AE-LABEL-CONTRACT-UNREADABLE: the participants schema is not "
            "readable in anthology_state.py — the raw-key law is "
            "unverifiable")
    _PLUMBING = {
        "participant_key", "stage_cursor", "rewrite_count",
        "qc_attempts_current", "hold_reason", "stage_timestamps",
        "drive_folder_id", "created_at", "updated_at",
    }
    keys = []
    for line in m.group(1).splitlines():
        mm = re.match(r"\s*([A-Za-z_][A-Za-z0-9_]*)\s+(TEXT|INTEGER)", line)
        if mm and mm.group(1) not in _PLUMBING:
            keys.append(mm.group(1))
    return keys


def _router_raw_keys() -> list:
    """The intake field_candidates keys (the alias families the router
    extracts by) plus the upsert scalar fields, from intake_router.py —
    the exact raw keys the universal intake form submits."""
    text = _read_source(ROUTER_PATH, "scripts/intake_router.py")
    keys = []
    for m in re.finditer(r'"([A-Za-z_][A-Za-z0-9_]*)":\s*\[', text):
        if m.group(1) not in keys:
            keys.append(m.group(1))
    return keys


def _template_paths() -> list:
    """The sanctioned client-facing template files, in SANCTIONED order.
    Fail-closed: a missing template is a STOP (the scan cannot see one of
    its inputs)."""
    out = []
    for name in SANCTIONED_TEMPLATES:
        p = TEMPLATES_DIR / name
        if not p.is_file():
            raise LabelContractError(
                "AF-AE-LABEL-CONTRACT-UNREADABLE: sanctioned client-facing "
                "template %s is missing — the raw-key leak scan cannot see "
                "one of its inputs" % p)
        out.append(p)
    return out


# ---------------------------------------------------------------------------
# The checks — pure, OFFLINE, fail-closed.
# ---------------------------------------------------------------------------
def _check_map(raw_keys: list) -> list:
    """The map coherence check over the raw-key set and WARM_LABELS.
    Returns a list of violation dicts (empty == PASS). Fail-closed:
      - a raw key with NO warm label is a FAIL (the map is incomplete),
      - a warm label that IS a raw key is a FAIL (the vocabularies collide —
        the label speaks the plumbing key instead of the warm word)."""
    violations = []
    for key in raw_keys:
        if not key:
            continue
        if key not in WARM_LABELS:
            violations.append({
                "kind": "RAW-KEY-UNLABELED",
                "raw_key": key,
                "detail": ("raw key %r has no warm client label — the "
                           "warm-client language map is incomplete" % key),
            })
            continue
        label = WARM_LABELS[key]
        if _RAW_KEY_RE.search(label):
            violations.append({
                "kind": "LABEL-COLLIDES-WITH-RAW-KEY",
                "raw_key": key,
                "label": label,
                "detail": ("the warm label for %r (%r) is itself a raw key — "
                           "a client surface would speak the plumbing key"
                           % (key, label)),
            })
    return violations


def _check_templates(violations: list) -> None:
    """The client-facing template scan: no raw key as a literal, no raw key
    as a {{slot}}, every slot mapped to a warm label, no em dashes.
    Mutates `violations` in place (a violation is a result, never raised)."""
    for path in _template_paths():
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise LabelContractError(
                "AF-AE-LABEL-CONTRACT-UNREADABLE: cannot read %s (%s)"
                % (path, type(exc).__name__)) from exc
        # strip the authoring comment block (the nudge_send COMMENT_RE rule)
        body = re.sub(r"^\s*<!--.*?-->\s*", "", text, count=1, flags=re.DOTALL)
        name = path.name
        # 1. a raw key as a literal — a plumbing key on a client surface
        m = _RAW_KEY_RE.search(body)
        if m:
            violations.append({
                "kind": "RAW-KEY-ON-CLIENT-SURFACE",
                "template": name,
                "raw_key": m.group(1).lower(),
                "detail": ("the client-facing template %s carries the raw "
                           "key %r as a literal — never a silent pass"
                           % (name, m.group(1))),
            })
        # 2. a {{slot}} that is itself a raw key — the serializer would
        #    substitute a machine key into the client's message
        for slot in _SLOT_RE.findall(body):
            if _RAW_KEY_RE.search(slot):
                violations.append({
                    "kind": "RAW-KEY-SLOT-ON-CLIENT-SURFACE",
                    "template": name,
                    "raw_key": slot.lower(),
                    "detail": ("the client-facing template %s names the raw "
                               "key %r as a {{slot}}" % (name, slot)),
                })
            if slot not in WARM_LABELS:
                violations.append({
                    "kind": "UNMAPPED-SLOT",
                    "template": name,
                    "slot": slot,
                    "detail": ("the client-facing template %s carries the "
                               "unmapped slot {{%s}} — it cannot be spoken "
                               "warmly (AF-AE-SLOT-UNRESOLVED family)"
                               % (name, slot)),
                })
        # 3. a MALFORMED {{...}} token — an unclosed brace or an empty slot.
        #    A well-formed {{slot}} is the template's intended syntax (the
        #    serializer fills every slot fail-closed); only a broken token is
        #    a defect here (the residual check on the RENDERED message is
        #    nudge_send.py's own RESIDUAL_RE surface).
        for m in re.finditer(r"\{\{.*?(?=\}\}|\{\{)", body):
            tok = m.group(0)
            if tok.strip() == "{{" or re.search(r"\{\{\s*\}\}", tok):
                violations.append({
                    "kind": "MALFORMED-SLOT",
                    "template": name,
                    "detail": ("the client-facing template %s carries a "
                               "malformed {{...}} token: %r" % (name, tok)),
                })
                break
        if "{{" in body and body.count("{{") != body.count("}}"):
            # an unbalanced brace count is a broken template, never a pass
            violations.append({
                "kind": "MALFORMED-SLOT",
                "template": name,
                "detail": ("the client-facing template %s has unbalanced "
                           "{{...}} braces (%d opens, %d closes)"
                           % (name, body.count("{{"), body.count("}}"))),
            })
        # 4. the em-dash family — zero em dashes on a client surface
        for ch in _EMDASH_CHARS:
            if ch in body:
                violations.append({
                    "kind": "EM-DASH-ON-CLIENT-SURFACE",
                    "template": name,
                    "detail": ("the client-facing template %s carries an "
                               "em dash (U+%04X) — zero em dashes is a hard "
                               "rule" % (name, ord(ch))),
                })
                break


def check_all(*, raw_keys=None) -> dict:
    """The aggregate check. Returns {"ok", "raw_keys", "warm_labels",
    "violations"} — fail-closed: any violation -> ok False; an unreadable
    source raises LabelContractError (STOP), never a fabricated pass."""
    keys = list(raw_keys) if raw_keys is not None else _state_raw_keys()
    violations = _check_map(keys)
    _check_templates(violations)
    return {
        "ok": not violations,
        "raw_keys": keys,
        "warm_labels": sorted(WARM_LABELS),
        "violations": violations,
    }


# ---------------------------------------------------------------------------
# Offline self-test — golden PASS / attack FAIL, no network, no credentials.
# ---------------------------------------------------------------------------
def self_test(out=None) -> int:
    out = out or sys.stderr
    dev = io.StringIO()
    try:
        _self_test_body(dev)
    except AssertionError as exc:
        sys.stderr.write("[label-checker] SELF-TEST FAILED "
                         "(AF-AE-LABEL family): %s\n" % exc)
        return EX_VIOLATION
    out.write(dev.getvalue())
    return EX_OK


def _self_test_body(dev) -> None:
    # ---- the law is readable: every source of truth exists ----------------
    raw = _state_raw_keys()
    assert raw, "the raw-key law must not be empty"
    assert "first_name" in raw and "last_name" in raw and "email" in raw, (
        "the participants schema must carry the required identity keys")
    assert "ideal_avatar" in raw and "niche" in raw and "primary_goal" in raw, (
        "the participants schema must carry the avatar answer keys")
    assert "personal_stories" in raw and "tone_inputs" in raw, (
        "the participants schema must carry the JSON-typed answer keys")
    assert "chapter_about" in raw, (
        "the participants schema must carry chapter_about")
    router = _router_raw_keys()
    assert "ideal_avatar" in router and "niche" in router and \
        "primary_goal" in router, (
            "intake_router field_candidates must carry the avatar answer keys")
    assert "first_name" in router and "last_name" in router and \
        "email" in router and "phone" in router, (
            "intake_router field_candidates must carry the identity keys")
    assert len(_template_paths()) == len(SANCTIONED_TEMPLATES), (
        "the sanctioned template set drifted from the scan")

    # ---- golden: the committed map is coherent ----------------------------
    report = check_all(raw_keys=raw)
    assert report["ok"] is True, (
        "the committed label map must pass: %r" % report["violations"][:4])
    assert report["violations"] == [], report["violations"]

    # ---- the map covers the avatar answers with the warm wording ----------
    for key, want in (
            ("ideal_avatar", "My Ideal Avatar / Dream Customer"),
            ("niche", "My Niche / category"),
            ("primary_goal", "My Ideal Avatar's Primary Goal")):
        assert WARM_LABELS.get(key) == want, (
            "the warm label for %r drifted from the Skill 52 shared_required "
            "wording: %r" % (key, WARM_LABELS.get(key)))

    # ---- attack fixtures: every deviation FAILS (never a silent pass) -----
    # 1. a raw key with no warm label -> FAIL
    a1 = _check_map(["ideal_avatar", "niche", "no_such_raw_key"])
    assert a1, "an unlabeled raw key was NOT failed"
    assert a1[0]["kind"] == "RAW-KEY-UNLABELED", a1
    # 2. a warm label that is itself a raw key -> FAIL
    a2 = _check_map(["ideal_avatar"])
    _saved = WARM_LABELS["ideal_avatar"]
    WARM_LABELS["ideal_avatar"] = "ideal_avatar"
    try:
        a2 = _check_map(["ideal_avatar"])
        assert a2 and a2[0]["kind"] == "LABEL-COLLIDES-WITH-RAW-KEY", a2
    finally:
        WARM_LABELS["ideal_avatar"] = _saved
    # 3. the templates are clean: no raw key, all slots mapped, no em dash.
    #    The authoring comment block (with its documentation-only {{slots}}
    #    mention) is stripped exactly as _check_templates strips it, so the
    #    scan sees only the client-visible body.
    text = (TEMPLATES_DIR / "completion.md").read_text(encoding="utf-8")
    body = re.sub(r"^\s*<!--.*?-->\s*", "", text, count=1, flags=re.DOTALL)
    assert _RAW_KEY_RE.search(body) is None, (
        "the golden completion template carries a raw key")
    slots = set(_SLOT_RE.findall(body))
    assert slots and all(s in WARM_LABELS for s in slots), (
        "the golden completion template carries an unmapped slot: %s"
        % sorted(s for s in slots if s not in WARM_LABELS))
    for ch in _EMDASH_CHARS:
        assert ch not in body, "the golden completion template carries an em dash"
    assert "Warmly," in body, (
        "the golden completion template must carry the 'Warmly,' sign-off")

    dev.write("[label-checker] golden PASS: the committed raw-key set "
              "(%d keys: identity + avatar answers + tone/stories + "
              "chapter + locked titles) is fully covered by warm labels "
              "pinned byte-exact to the Skill 52 / Skill 54 / nudge_send "
              "sources; all %d sanctioned client-facing templates carry "
              "only mapped slots, zero raw keys, zero em dashes.\n"
              % (len(raw), len(_template_paths())))
    dev.write("[label-checker] attack fixtures: unlabeled raw key / "
              "label-collides-with-raw-key both FAIL; the golden "
              "completion template is clean.\n")
    dev.write("[label-checker] self-test: PASS\n")


# ---------------------------------------------------------------------------
# Offline plan — the law with its sources, ONE JSON object on stdout.
# ---------------------------------------------------------------------------
def plan(*, out=None) -> int:
    out = out or sys.stderr
    raw = _state_raw_keys()
    payload = {
        "contract": "anthology-engine-label-check-plan",
        "schema_version": 1,
        "raw_keys": raw,
        "warm_labels": {k: WARM_LABELS.get(k, "") for k in raw},
        "sources": {
            "raw_keys": "scripts/anthology_state.py participants schema + "
                        "scripts/intake_router.py field_candidates",
            "warm_labels": "Skill 52 intake/intake-schema.json "
                           "shared_required + Skill 54 "
                           "intake/aw-intake-schema.json + "
                           "scripts/nudge_send.py GATE_META",
            "templates": "config/nudge-templates/*.md (the SANCTIONED set)",
        },
        "fail_closed": True,
        "note": "offline plan only — no network, no credential needed",
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    return EX_OK


# ---------------------------------------------------------------------------
# CLI — house shape: positional subcommand (check / plan / self-test) plus
# the --self-test / --selftest flag spellings, normalized exactly as the
# other u04 modules normalize them.
# ---------------------------------------------------------------------------
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="label_checker.py",
        description="Fail-closed gate: the engine's raw-key labels "
                    "(ideal_avatar etc.) match the warm client language map, "
                    "and no raw key leaks onto a client-facing surface "
                    "(Skill 59, u04_modules). OFFLINE — no network, no "
                    "credentials.")
    ap.add_argument("cmd", nargs="?", choices=["check", "plan", "self-test"],
                    default="check",
                    help="subcommand: check (default) / plan / self-test")
    ap.add_argument("--selftest", "--self-test", dest="self_test",
                    action="store_true",
                    help="run the offline self-test (golden + attack fixtures) and exit")

    if argv is None:
        argv = sys.argv[1:]
    argv = list(argv)
    # Normalize --self-test / --selftest -> the positional self-test form.
    if "--self-test" in argv:
        argv = ["self-test" if a == "--self-test" else a for a in argv]
    if "--selftest" in argv:
        argv = ["self-test" if a == "--selftest" else a for a in argv]
    args = ap.parse_args(argv)
    try:
        if args.self_test or args.cmd == "self-test":
            return self_test()
        if args.cmd == "plan":
            return plan()
        report = check_all()
        if report["ok"]:
            sys.stderr.write("[label-checker] PASS: %d raw keys fully covered "
                             "by warm labels; all sanctioned client-facing "
                             "templates clean (zero raw keys, all slots "
                             "mapped, zero em dashes).\n"
                             % len(report["raw_keys"]))
            print(json.dumps(report, indent=2, sort_keys=True))
            return EX_OK
        sys.stderr.write("[label-checker] FAIL (AF-AE-LABEL family): "
                         "%d violation(s).\n" % len(report["violations"]))
        for v in report["violations"][:50]:
            sys.stderr.write("  %s %s: %s\n"
                             % (v.get("kind", "?"),
                                v.get("raw_key") or v.get("template") or "",
                                v.get("detail", "")))
        print(json.dumps(report, indent=2, sort_keys=True))
        return EX_MISMATCH
    except LabelContractError as exc:
        sys.stderr.write("[label-checker] STOP: %s\n" % exc)
        return EX_STOP
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001 — top-level guard, never leaks a secret
        sys.stderr.write("[label-checker] unexpected error: %s: %s\n"
                         % (type(exc).__name__, exc))
        return EX_ERR


if __name__ == "__main__":
    sys.exit(main())
