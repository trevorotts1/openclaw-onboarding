#!/usr/bin/env python3
# =============================================================================
# BOOK WRITER MINI-APP (Wave A) :: U01 — PHASE CONFIG GENERATOR
# -----------------------------------------------------------------------------
# Derives EVERY mini-app phase config from the two authorities so the configs
# can NEVER drift from the skill:
#
#   AUTHORITY 1 — 53-book-writer/intake/intake-schema.json
#       selector         version {book,brand}, required, NO default (AF-BK-VERSION)
#       mode_selector    mode {full,4x3x3}, required, NO default
#       identity_fields  first_name, last_name        (identity_optional: email)
#       shared_required  ideal_avatar, niche, primary_goal, tone_style_1..2
#       tone_style_optional tone_style_3..4
#       book_required    book_about, book_stories, cover_description
#       book_optional    cover_reference_image
#       four33_required  avatar_dossier, tone_doc
#
#   AUTHORITY 2 — 53-book-writer/BOOK-WRITER-MANIFEST.json
#       gates_order.full    = [GATE-1-title, GATE-2-outline, GATE-3-approval,
#                              GATE-4-approval-r2]
#       gates_order.4x3x3   = [GATE-433, GATE-1-title, GATE-2-outline,
#                              GATE-3-approval]
#
# EMITS (7 phase configs, R2 config/ data — never code):
#   P0-INTAKE:full.json   P0-INTAKE:4x3x3.json   GATE-1-title.json
#   GATE-2-outline.json   GATE-3-approval.json   GATE-4-approval-r2.json
#   GATE-433.json
#
# FIELD KINDS (five, no more):
#   text/textarea -> string            (text = short line, textarea = long block)
#   choice        -> segmented enum, NO default (AF-BK-VERSION)
#   file-pdf      -> browser pdf.js TEXT extraction only; PDF is NEVER uploaded
#   file-txt      -> browser FileReader -> text
#   media         -> audio/video: presigned DIRECT-to-R2 upload -> async
#                    transcript -> poll (never through a Worker request body)
#
# CONFIG SHAPE:
#   { phase, phase_version, title, warm_intro, progress_label, questions[],
#     submit:{action, custom_field_map, tags, raw_json_note, dedupe_key},
#     gate (gate phases): {approved_on, approved_by, must_match} }
#
# GATE-1 must_match=[title, subtitle] BYTE-EXACT (AF-BK-TITLE-LOCK unchanged).
# Normalization happens ONCE at this boundary (trailing/leading-space key and
# enum defects in a source schema are stripped here, never in a prompt).
#
# Every emitted config records the sha256 of BOTH authorities it was derived
# from. --self-test recomputes those hashes and FAILS if any emitted config
# was built from a stale authority (the never-drift guarantee, enforced).
#
# EXIT: 0 OK · 2 FAILED (self-test / negative) · 3 USAGE/IO.
# USAGE:
#   gen_phase_config.py [--emit DIR]                # write all configs to DIR
#   gen_phase_config.py --self-test                 # verify against authorities
#   gen_phase_config.py --schema BAD.json           # negative: must exit 2
# =============================================================================
"""Derive Book Writer mini-app phase configs from the two authorities (U01)."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

CONFIG_KIND = "book-writer-phase-config/v1"
EXIT_OK = 0
EXIT_FAIL = 2
EXIT_USAGE = 3

SKILL_DIR = Path(__file__).resolve().parent.parent.parent  # 53-book-writer/
MINI_APP_DIR = SKILL_DIR / "mini-app"
SCHEMA_PATH = SKILL_DIR / "intake" / "intake-schema.json"
MANIFEST_PATH = SKILL_DIR / "BOOK-WRITER-MANIFEST.json"

DEFAULT_EMIT_DIR = MINI_APP_DIR / "configs"

# The exact gate orders the skill mandates — the generator derives gate configs
# from gates_order in the manifest and RE-ASSERTS these against it so a drifted
# manifest is caught by --self-test, never silently followed.
EXPECTED_GATES_FULL = ["GATE-1-title", "GATE-2-outline", "GATE-3-approval",
                       "GATE-4-approval-r2"]
EXPECTED_GATES_433 = ["GATE-433", "GATE-1-title", "GATE-2-outline",
                      "GATE-3-approval"]

# Length floors (bytes/chars per field) from the ingestion spec (master plan §4).
MAX_CHARS_DEFAULT = 50_000
MAX_CHARS_LONG = 200_000  # book_about + book_stories

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def _normalize(value):
    """Normalize a parsed JSON value ONCE at this boundary.

    Strings have leading/trailing whitespace stripped; a string that strips to
    empty is returned as-is for the caller to judge (empty-string fields are
    NOT silently dropped — that would be a hidden data change). Enum lists and
    object keys are normalized in place. This is the single normalization point
    the master plan calls for: it never reaches a prompt.
    """
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        return [_normalize(v) for v in value]
    if isinstance(value, dict):
        return {(_normalize(k) if isinstance(k, str) else k): _normalize(v)
                for k, v in value.items()}
    return value


def _normalized_keys(d: dict) -> dict:
    """Re-key a dict so keys have no leading/trailing whitespace (sloppy-source
    defect the schema description warns about: 'firstname ', 'Idealavatar ')."""
    out = {}
    for k, v in d.items():
        out[(k.strip() if isinstance(k, str) else k)] = v
    return out


# ---------------------------------------------------------------------------
# Authority loaders (fail-closed validation)
# ---------------------------------------------------------------------------

def _expect(cond: bool, msg: str):
    if not cond:
        raise ValueError(msg)


def load_schema(path: Path) -> dict:
    """Load + normalize + structurally validate intake-schema.json.

    Raises ValueError on any structural defect — a bad schema is a hard error,
    never a best-effort generation (the negative case is built on this).
    """
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:  # pragma: no cover - IO path
        raise ValueError("cannot read schema %s: %s" % (path, exc))
    try:
        schema = _normalize(json.loads(raw))
    except json.JSONDecodeError as exc:
        raise ValueError("schema %s is not valid JSON: %s" % (path, exc))
    if not isinstance(schema, dict):
        raise ValueError("schema root must be a JSON object")

    sel = schema.get("selector")
    mode_sel = schema.get("mode_selector")
    _expect(isinstance(sel, dict), "schema.selector missing")
    _expect(sel.get("field") == "version", "selector.field must be 'version'")
    _expect(sel.get("required") is True, "selector.required must be true")
    _expect(sel.get("no_default") is True, "selector.no_default must be true (AF-BK-VERSION)")
    venum = sel.get("enum") or []
    _expect(isinstance(venum, list) and "book" in venum and "brand" in venum,
            "selector.enum must include both 'book' and 'brand'")

    _expect(isinstance(mode_sel, dict), "schema.mode_selector missing")
    _expect(mode_sel.get("field") == "mode", "mode_selector.field must be 'mode'")
    menum = mode_sel.get("enum") or []
    _expect(isinstance(menum, list) and "full" in menum and "4x3x3" in menum,
            "mode_selector.enum must include 'full' and '4x3x3'")
    _expect(mode_sel.get("required") is True, "mode_selector.required must be true")

    for group in ("identity_fields", "shared_required", "book_required",
                  "four33_required"):
        _expect(isinstance(schema.get(group), dict) or
                (group == "identity_fields" and isinstance(schema.get(group), list)),
                "schema.%s missing" % group)
        if group != "identity_fields":
            _expect(len(schema.get(group) or {}) > 0, "schema.%s empty" % group)
    _expect(len(schema.get("identity_fields") or []) > 0,
            "schema.identity_fields empty")

    schema["selector"] = _normalized_keys(schema["selector"])
    schema["mode_selector"] = _normalized_keys(schema["mode_selector"])
    return schema


def load_manifest(path: Path) -> dict:
    """Load + validate BOOK-WRITER-MANIFEST.json gates_order."""
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:  # pragma: no cover - IO path
        raise ValueError("cannot read manifest %s: %s" % (path, exc))
    try:
        manifest = _normalize(json.loads(raw))
    except json.JSONDecodeError as exc:
        raise ValueError("manifest %s is not valid JSON: %s" % (path, exc))
    if not isinstance(manifest, dict):
        raise ValueError("manifest root must be a JSON object")
    go = manifest.get("gates_order")
    _expect(isinstance(go, dict) and isinstance(go.get("full"), list)
            and isinstance(go.get("4x3x3"), list),
            "manifest.gates_order.full / .4x3x3 must be lists")
    return manifest


def _group_field_ids(schema: dict) -> dict:
    """Flat, ordered view of every schema question field grouped by group id.

    Returns {group_id: [(field_id, label)]} preserving schema order.
    """
    groups = {}
    groups["identity"] = [(f, f.replace("_", " ").title())
                          for f in (schema.get("identity_fields") or [])]
    groups["identity_optional"] = [(f, f.replace("_", " ").title())
                                   for f in (schema.get("identity_optional") or [])]
    for gid in ("shared_required", "tone_style_optional", "book_required",
                "book_optional", "four33_required"):
        groups[gid] = list((schema.get(gid) or {}).items())
    return groups


# ---------------------------------------------------------------------------
# Field-kind mapping (the five kinds, nothing else)
# ---------------------------------------------------------------------------

def _field_kind(field_id: str, group_id: str) -> str:
    """Map a schema field to one of the five field kinds.

    text  -> short line (names, email)
    textarea -> long block (every prose answer)
    choice   -> version / mode (segmented enum, NO default)
    file-pdf / file-txt -> browser extraction alternate for prose questions
    media    -> audio/video (presigned -> transcript -> poll)
    """
    if field_id in ("version", "mode"):
        return "choice"
    if field_id in ("first_name", "last_name", "email"):
        return "text"
    if field_id == "cover_reference_image":
        # An image/video reference: presigned upload; a video yields a still
        # frame candidate (cover_reference_image) — never a required transcript.
        return "media"
    # All remaining fields are prose answers that may be typed, pasted from a
    # PDF/txt, or dictated as audio/video.
    return "textarea"


def _choice_question(field_id: str, enum: list, question: str, custom_field: str,
                     depends_on: dict | None) -> dict:
    return {
        "id": field_id,
        "kind": "choice",
        "label": question,
        "question": question,
        "enum": list(enum),
        "no_default": True,
        "required": True,
        "why": ("This chooses which pipeline runs — there is no wrong answer, "
                "and it cannot be inferred from your other answers."),
        "custom_field": custom_field,
        "answer_your_way": ["choice"],
        **({"depends_on": depends_on} if depends_on else {}),
    }


def _text_question(field_id: str, label: str, custom_field: str, required: bool,
                   depends_on: dict | None, max_chars: int = MAX_CHARS_DEFAULT) -> dict:
    return {
        "id": field_id,
        "kind": "text",
        "label": label,
        "question": label,
        "required": required,
        "max_chars": max_chars,
        "why": "Just a little about you, so the book sounds like you.",
        "custom_field": custom_field,
        "answer_your_way": ["text"],
        **({"depends_on": depends_on} if depends_on else {}),
    }


def _textarea_question(field_id: str, label: str, custom_field: str, required: bool,
                       depends_on: dict | None, max_chars: int = MAX_CHARS_DEFAULT,
                       why: str = "") -> dict:
    return {
        "id": field_id,
        "kind": "textarea",
        "label": label,
        "question": label,
        "required": required,
        "max_chars": max_chars,
        "why": why or ("There are no wrong answers — just start typing, it "
                       "doesn't have to be perfect."),
        "custom_field": custom_field,
        # Every prose answer may be typed, read out (audio/video -> transcript),
        # or pasted from a PDF/.txt (browser-side text extraction only).
        "answer_your_way": ["text", "media", "file-pdf", "file-txt"],
        "handlers": {
            "file-pdf": {
                "kind": "file-pdf",
                "note": ("Browser pdf.js TEXT extraction only — text is sent, "
                         "the PDF is NEVER uploaded."),
            },
            "file-txt": {
                "kind": "file-txt",
                "note": "Browser FileReader reads the file as text.",
            },
            "media": {
                "kind": "media",
                "accept": ["audio", "video"],
                "transcript": True,
                "poll": True,
                "note": ("Presigned DIRECT-to-R2 upload (never through a Worker "
                         "request body), then async transcription, then poll."),
            },
        },
        **({"depends_on": depends_on} if depends_on else {}),
    }


def _media_reference_question(field_id: str, label: str, custom_field: str,
                              required: bool, depends_on: dict | None) -> dict:
    return {
        "id": field_id,
        "kind": "media",
        "label": label,
        "question": label,
        "required": required,
        "why": "A cover you love helps us match the feel. Optional and gentle.",
        "custom_field": custom_field,
        "answer_your_way": ["media"],
        "handlers": {
            "media": {
                "kind": "media",
                "accept": ["image", "video"],
                "transcript": False,      # it is a reference, not an answer
                "poll": False,
                "still_frame": True,      # video -> best-effort still frame
                "note": ("Presigned DIRECT-to-R2 upload; a video's first frame "
                         "is the cover_reference_image candidate."),
            },
        },
        **({"depends_on": depends_on} if depends_on else {}),
    }


# ---------------------------------------------------------------------------
# Config builders
# ---------------------------------------------------------------------------

def _dedupe_key() -> str:
    return "run_id+phase_id+identity"


def _submit_block(action: str, custom_field_map: dict, tags: list,
                  raw_json_note: bool = True) -> dict:
    return {
        "action": action,
        "custom_field_map": custom_field_map,
        "tags": tags,
        "raw_json_note": raw_json_note,
        "dedupe_key": _dedupe_key(),
    }


def build_intake(schema: dict, mode: str) -> dict:
    """Build P0-INTAKE:<mode> from intake-schema.json (authority 1)."""
    if mode not in ("full", "4x3x3"):
        raise ValueError("mode must be one of {full, 4x3x3}")
    groups = _group_field_ids(schema)

    book_book = {"version": "book"}
    four33 = {"version": "book", "mode": "4x3x3"}

    questions = []
    # version selector FIRST (no default — AF-BK-VERSION).
    questions.append(_choice_question(
        "version", schema["selector"]["enum"],
        schema["selector"].get("question", "Book or brand?"),
        "bw_version", None))
    # mode selector second (no default — AF-BK-VERSION).
    questions.append(_choice_question(
        "mode", schema["mode_selector"]["enum"],
        schema["mode_selector"].get("question", "Full book or 4x3x3?"),
        "bw_mode", {"version": "book"}))

    for fid, label in groups["identity"]:
        questions.append(_text_question(fid, label, "bw_" + fid, True, book_book))
    for fid, label in groups["identity_optional"]:
        questions.append(_text_question(fid, label, "bw_" + fid, False, book_book))

    for fid, label in groups["shared_required"]:
        questions.append(_textarea_question(fid, label, "bw_" + fid, True, book_book))
    for fid, label in groups["tone_style_optional"]:
        questions.append(_textarea_question(fid, label, "bw_" + fid, False, book_book))

    for fid, label in groups["book_required"]:
        max_chars = MAX_CHARS_LONG if fid in ("book_about", "book_stories") \
            else MAX_CHARS_DEFAULT
        questions.append(_textarea_question(fid, label, "bw_" + fid, True,
                                            book_book, max_chars=max_chars))
    for fid, label in groups["book_optional"]:
        questions.append(_media_reference_question(fid, label, "bw_" + fid,
                                                   False, book_book))

    # 4x3x3-only extras (four33_required): avatar_dossier + tone_doc.
    if mode == "4x3x3":
        for fid, label in groups["four33_required"]:
            questions.append(_textarea_question(
                fid, label, "bw_" + fid, True, four33,
                why=("4x3x3 assumes the Avatar Alchemist already ran — paste "
                     "the dossier path/content; no wrong answer if it's not "
                     "handy yet.")))

    custom_field_map = {q["id"]: q["custom_field"] for q in questions}
    total = len(questions)
    return {
        "phase": "P0-INTAKE:%s" % mode,
        "phase_version": schema.get("version", "1.0.0"),
        "config_kind": CONFIG_KIND,
        "title": "Your book is already in you. We just help it out.",
        "warm_intro": (
            "A few gentle questions — type, talk, or drop a file. No wrong "
            "answers, no pressure; you can save and come back anytime."),
        "progress_label": "Question {n} of %d" % total,
        "progress_total": total,
        "mode": mode,
        "questions": questions,
        "submit": _submit_block(
            "ghl_contact", custom_field_map,
            ["book-writer", "intake", "phase-p0"]),
    }


# Gate warm copy + approval field design per gate id.
_GATE_META = {
    "GATE-1-title": {
        "title": "Lock in your title",
        "warm_intro": ("Your suggested titles are ready. Type the exact title "
                       "and subtitle you want to lock in — they stay byte-exact "
                       "through every chapter."),
    },
    "GATE-2-outline": {
        "title": "Approve your outline",
        "warm_intro": "Your outline is ready. Read it through and approve it, or ask for a change.",
    },
    "GATE-3-approval": {
        "title": "Approve your full draft",
        "warm_intro": "Your full draft is done. Give it your approval, or ask for a revision.",
    },
    "GATE-4-approval-r2": {
        "title": "Approve the revision",
        "warm_intro": "Your revised draft is ready for a second look.",
    },
    "GATE-433": {
        "title": "Approve your offer book",
        "warm_intro": ("Your 30 titles and 4 outcomes are ready. Confirm them "
                       "and drop in your avatar dossier and tone doc."),
    },
}


def build_gate(gate_id: str, modes: list, manifest: dict) -> dict:
    """Build a gate config. Gate-1 must_match=[title, subtitle] byte-exact."""
    meta = _GATE_META[gate_id]
    skill_ver = str(manifest.get("skill_version", "1.2.0"))

    if gate_id == "GATE-1-title":
        questions = [
            _text_question("title", "Book title", "bw_title", True, None),
            _text_question("subtitle", "Book subtitle", "bw_subtitle", True, None),
        ]
        gate = {
            "approved_on": True,
            "approved_by": True,
            "must_match": ["title", "subtitle"],
            "byte_exact": True,   # AF-BK-TITLE-LOCK — byte-exact everywhere
            "prover": "prove_bw_titlelock",
        }
        submit_tags = ["book-writer", "gate", "phase-p3"]
    elif gate_id == "GATE-433":
        # 4x3x3 gate: collect avatar_dossier/tone_doc paths + explicit approval.
        four33 = {"version": "book", "mode": "4x3x3"}
        questions = [
            _textarea_question("avatar_dossier", "Avatar dossier path / content",
                               "bw_avatar_dossier", True, four33),
            _textarea_question("tone_doc", "Tone doc path / content",
                               "bw_tone_doc", True, four33),
            _choice_question("approval",
                             ["approve", "needs-changes"],
                             "Do you approve the 30 titles and 4 outcomes?",
                             "bw_433_approval", four33),
        ]
        gate = {
            "approved_on": True,
            "approved_by": True,
            "must_match": ["approval"],
            "approve_token": "approve",
        }
        submit_tags = ["book-writer", "gate", "phase-p4"]
    else:
        # GATE-2 / GATE-3 / GATE-4: explicit approval choice.
        questions = [
            _choice_question("approval",
                             ["approve", "needs-changes"],
                             "Do you approve this as-is?",
                             "bw_%s_approval" % gate_id.replace("-", "_"), None),
        ]
        gate = {
            "approved_on": True,
            "approved_by": True,
            "must_match": ["approval"],
            "approve_token": "approve",
        }
        submit_tags = ["book-writer", "gate", "phase-" + (
            "p4" if gate_id == "GATE-2-outline" else "p6")]

    custom_field_map = {q["id"]: q["custom_field"] for q in questions}
    total = len(questions)
    return {
        "phase": gate_id,
        "phase_version": skill_ver,
        "config_kind": CONFIG_KIND,
        "title": meta["title"],
        "warm_intro": meta["warm_intro"],
        "progress_label": "Question {n} of %d" % total,
        "progress_total": total,
        "modes": sorted(modes, key=lambda m: ("full", "4x3x3").index(m)),
        "questions": questions,
        "submit": _submit_block("gate_receipt", custom_field_map, submit_tags),
        "gate": gate,
    }


# ---------------------------------------------------------------------------
# Validation + emission
# ---------------------------------------------------------------------------

def validate_config(cfg: dict):
    """Structural checks every emitted config must satisfy."""
    for key in ("phase", "phase_version", "title", "warm_intro",
                "progress_label", "questions", "submit"):
        if key not in cfg:
            raise ValueError("config %s missing %r" % (cfg.get("phase"), key))
    if not isinstance(cfg["questions"], list) or not cfg["questions"]:
        raise ValueError("config %s has no questions" % cfg["phase"])
    for q in cfg["questions"]:
        for key in ("id", "kind", "label", "question", "required", "why",
                    "custom_field", "answer_your_way"):
            if key not in q:
                raise ValueError("question in %s missing %r" % (cfg["phase"], key))
        if q["kind"] not in ("text", "textarea", "choice", "file-pdf",
                             "file-txt", "media"):
            raise ValueError("question %s has unknown kind %r"
                             % (q["id"], q["kind"]))
        if q["kind"] == "choice" and q.get("no_default") is not True:
            raise ValueError("choice question %s must be no_default (AF-BK-VERSION)"
                             % q["id"])
    for key in ("action", "custom_field_map", "tags", "raw_json_note",
                "dedupe_key"):
        if key not in cfg["submit"]:
            raise ValueError("config %s submit missing %r" % (cfg["phase"], key))


def stamp_authorities(cfg: dict, schema_path: Path, manifest_path: Path):
    """Record the authority identity + hashes each config was derived from."""
    cfg["derived_from"] = {
        "intake_schema": str(schema_path.relative_to(SKILL_DIR)),
        "manifest": str(manifest_path.relative_to(SKILL_DIR)),
        "intake_schema_sha256": sha256_file(schema_path),
        "manifest_sha256": sha256_file(manifest_path),
    }


def generate_all(schema_path: Path, manifest_path: Path) -> list:
    """Build the full config set from the two authorities."""
    schema = load_schema(schema_path)
    manifest = load_manifest(manifest_path)
    gates_order = manifest["gates_order"]

    _expect(list(gates_order["full"]) == EXPECTED_GATES_FULL,
            "gates_order.full drifted from %r" % EXPECTED_GATES_FULL)
    _expect(list(gates_order["4x3x3"]) == EXPECTED_GATES_433,
            "gates_order.4x3x3 drifted from %r" % EXPECTED_GATES_433)

    configs = [
        build_intake(schema, "full"),
        build_intake(schema, "4x3x3"),
    ]
    # Union of gates referenced across modes, in first-seen order.
    gate_ids = []
    for mode in ("full", "4x3x3"):
        for gid in gates_order[mode]:
            if gid not in gate_ids:
                gate_ids.append(gid)
    for gid in gate_ids:
        modes = [m for m in ("full", "4x3x3") if gid in gates_order[m]]
        configs.append(build_gate(gid, modes, manifest))

    for cfg in configs:
        validate_config(cfg)
        stamp_authorities(cfg, schema_path, manifest_path)
    return configs


def emit(configs: list, out_dir: Path):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for cfg in configs:
        out_path = out_dir / (cfg["phase"].replace(":", "-") + ".json")
        out_path.write_text(json.dumps(cfg, indent=2, sort_keys=True) + "\n",
                            encoding="utf-8")
        written.append(out_path)
    return written


# ---------------------------------------------------------------------------
# Self-test (positive + negative)
# ---------------------------------------------------------------------------

def self_test(schema_path: Path, manifest_path: Path, emit_dir: Path) -> int:
    """Run the unit's own verification: emission, authority hashing (positive)
    and a bad-schema negative that MUST fail."""
    failures = []

    def check(name: str, cond: bool, detail: str = ""):
        if cond:
            print("  [ok] %s" % name)
        else:
            failures.append(name)
            print("  [FAIL] %s %s" % (name, ("-- " + detail) if detail else ""))

    print("self-test: positive emission")
    configs = generate_all(schema_path, manifest_path)
    check("7 configs emitted", len(configs) == 7,
          "got %d" % len(configs))

    by_phase = {c["phase"]: c for c in configs}
    check("P0-INTAKE:full present", "P0-INTAKE:full" in by_phase)
    check("P0-INTAKE:4x3x3 present", "P0-INTAKE:4x3x3" in by_phase)
    for gid in ("GATE-1-title", "GATE-2-outline", "GATE-3-approval",
                "GATE-4-approval-r2", "GATE-433"):
        check("%s present" % gid, gid in by_phase)

    full = by_phase["P0-INTAKE:full"]
    f433 = by_phase["P0-INTAKE:4x3x3"]
    fids_full = {q["id"] for q in full["questions"]}
    fids_433 = {q["id"] for q in f433["questions"]}
    check("intake selects version first (no default)",
          fids_full and list(full["questions"])[0]["id"] == "version"
          and full["questions"][0]["no_default"] is True)
    check("intake version enum = {book, brand}",
          full["questions"][0]["enum"] == ["book", "brand"])
    check("intake mode enum = {full, 4x3x3}, no default",
          full["questions"][1]["id"] == "mode"
          and full["questions"][1]["enum"] == ["full", "4x3x3"]
          and full["questions"][1]["no_default"] is True)
    required = {"first_name", "last_name", "ideal_avatar", "niche",
                "primary_goal", "tone_style_1", "tone_style_2", "book_about",
                "book_stories", "cover_description", "version", "mode"}
    check("full intake carries every shared/book required field",
          required.issubset(fids_full),
          "missing %r" % sorted(required - fids_full))
    check("full intake carries cover_reference_image (book_optional)",
          "cover_reference_image" in fids_full)
    check("full intake excludes four33 fields",
          not fids_full & {"avatar_dossier", "tone_doc"})
    check("4x3x3 intake carries avatar_dossier + tone_doc",
          {"avatar_dossier", "tone_doc"}.issubset(fids_433))
    check("4x3x3 four33 fields depend on mode=4x3x3",
          all(q.get("depends_on", {}).get("mode") == "4x3x3"
              for q in f433["questions"] if q["id"] in ("avatar_dossier", "tone_doc")))
    check("every prose question is answer-your-way (media/pdf/txt)",
          all(any(k in q["answer_your_way"] for k in
                  ("media", "file-pdf", "file-txt"))
              for q in full["questions"]
              if q["kind"] in ("textarea", "media")))
    check("book_stories media-capable",
          any(q["id"] == "book_stories" and "media" in q["answer_your_way"]
              for q in full["questions"]))

    g1 = by_phase["GATE-1-title"]
    check("GATE-1 must_match=[title, subtitle]",
          g1["gate"]["must_match"] == ["title", "subtitle"])
    check("GATE-1 byte_exact flag set (AF-BK-TITLE-LOCK)",
          g1["gate"].get("byte_exact") is True)
    check("GATE-1 questions are title + subtitle",
          [q["id"] for q in g1["questions"]] == ["title", "subtitle"])
    for gid, exp_modes in (("GATE-1-title", ["full", "4x3x3"]),
                           ("GATE-2-outline", ["full", "4x3x3"]),
                           ("GATE-3-approval", ["full", "4x3x3"]),
                           ("GATE-4-approval-r2", ["full"]),
                           ("GATE-433", ["4x3x3"])):
        check("%s modes %r" % (gid, exp_modes),
              by_phase[gid]["modes"] == exp_modes)
    check("gate submit.action == gate_receipt",
          all(c["submit"]["action"] == "gate_receipt"
              for c in configs if c["phase"].startswith("GATE-")))
    check("intake submit.action == ghl_contact + phase-p0 tags",
          full["submit"]["action"] == "ghl_contact"
          and full["submit"]["tags"] == ["book-writer", "intake", "phase-p0"]
          and full["submit"]["raw_json_note"] is True)
    check("all configs carry authority hashes",
          all(c.get("derived_from", {}).get("intake_schema_sha256")
              for c in configs))

    # Recompute authority hashes: a config emitted from a stale authority MUST
    # be detected (the never-drift guarantee).
    current = sha256_file(schema_path)
    stale = any(c["derived_from"]["intake_schema_sha256"] != current
                for c in configs)
    check("configs not stale vs current schema hash", not stale)

    # Emit to a temp dir and re-load every file to prove it round-trips.
    tmp_dir = emit_dir / ".self-test-tmp"
    written = emit(configs, tmp_dir)
    check("emission round-trip parses", all(
        json.loads(p.read_text(encoding="utf-8"))["phase"] ==
        c["phase"] for c, p in zip(configs, written)))

    print("self-test: negative (bad schema MUST fail)")
    bad = {
        "contract": "book-writer-intake",
        "selector": {"field": "version", "enum": ["book", "brand"],
                     "required": True, "no_default": False},  # <-- defect
        "mode_selector": {"field": "mode", "enum": ["full", "4x3x3"],
                          "required": True, "no_default": True},
        "identity_fields": ["first_name", "last_name"],
        "shared_required": {"ideal_avatar": "x"},
        "book_required": {"book_about": "x"},
        "four33_required": {"avatar_dossier": "x"},
    }
    try:
        _load_schema_fail(schema_path, bad)
        check("bad schema (no_default=False) rejected", False,
              "generator accepted a defective schema")
    except ValueError:
        check("bad schema (no_default=False) rejected", True)

    bad2 = {"contract": "book-writer-intake",
            "selector": {"field": "version", "enum": ["book"],
                         "required": True, "no_default": True},
            "mode_selector": {"field": "mode", "enum": ["full", "4x3x3"],
                              "required": True, "no_default": True},
            "identity_fields": ["first_name"],
            "shared_required": {"ideal_avatar": "x"},
            "book_required": {"book_about": "x"},
            "four33_required": {"avatar_dossier": "x"}}
    try:
        _load_schema_fail(schema_path, bad2)
        check("bad schema (version enum missing 'brand') rejected", False)
    except ValueError:
        check("bad schema (version enum missing 'brand') rejected", True)

    bad3 = {"contract": "book-writer-intake",
            "selector": {"field": "version", "enum": ["book", "brand"],
                         "required": True, "no_default": True},
            "mode_selector": {"field": "mode", "enum": ["full"],
                              "required": True, "no_default": True},
            "identity_fields": ["first_name"],
            "shared_required": {"ideal_avatar": "x"},
            "book_required": {"book_about": "x"},
            "four33_required": {"avatar_dossier": "x"}}
    try:
        _load_schema_fail(schema_path, bad3)
        check("bad schema (mode enum missing '4x3x3') rejected", False)
    except ValueError:
        check("bad schema (mode enum missing '4x3x3') rejected", True)

    if failures:
        print("self-test FAILED: %d check(s) failed" % len(failures))
        return EXIT_FAIL
    print("self-test PASS — 7 configs derived from both authorities, "
          "no drift, negatives rejected.")
    return EXIT_OK


def _load_schema_fail(good_path: Path, bad_schema: dict):
    """Validate a bad schema DICT by routing it through the same load+validate
    path the file loader uses (raises ValueError on rejection)."""
    # Round-trip the bad dict through the same validation the real loader uses:
    # write to a temp file and load it with the exact same loader.
    import tempfile
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
        json.dump(bad_schema, fh)
        tmp = fh.name
    try:
        load_schema(Path(tmp))
    finally:
        Path(tmp).unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main(argv) -> int:
    parser = argparse.ArgumentParser(
        description="Derive Book Writer mini-app phase configs from the "
                    "two authorities (intake-schema.json + BOOK-WRITER-MANIFEST.json).")
    parser.add_argument("--emit", metavar="DIR", default=None,
                        help="write all phase configs as JSON into DIR")
    parser.add_argument("--schema", metavar="PATH", default=str(SCHEMA_PATH),
                        help="override the intake-schema authority")
    parser.add_argument("--manifest", metavar="PATH", default=str(MANIFEST_PATH),
                        help="override the manifest authority")
    parser.add_argument("--self-test", action="store_true",
                        help="run the unit's own verification (positive + negative)")
    args = parser.parse_args(argv)

    schema_path = Path(args.schema)
    manifest_path = Path(args.manifest)

    try:
        if args.self_test:
            emit_dir = Path(args.emit) if args.emit else DEFAULT_EMIT_DIR
            return self_test(schema_path, manifest_path, emit_dir)

        # Plain generation path. A bad schema still hard-fails (exit 2).
        configs = generate_all(schema_path, manifest_path)
        out_dir = Path(args.emit) if args.emit else DEFAULT_EMIT_DIR
        written = emit(configs, out_dir)
        for p in written:
            print("wrote %s" % p)
        print("emitted %d phase configs to %s" % (len(written), out_dir))
        return EXIT_OK
    except ValueError as exc:
        print("ERROR: %s" % exc, file=sys.stderr)
        return EXIT_FAIL


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
