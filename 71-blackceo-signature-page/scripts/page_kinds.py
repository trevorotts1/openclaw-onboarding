#!/usr/bin/env python3
"""Skill 71 page kinds: the signature sales page and the signature landing
(opt-in) page, both of page role `landing`.

Everything is data in references/page-kinds.json. This module reads it and
answers five questions for the rest of the pipeline:

  declared(run_dir, request)   the run's page kind (request, request metadata,
                               then intake.json), or None when undeclared
  check(kind, copy_version)    refuse a kind that may not use that copy form
  sequence(kind, copy_version) the canonical section sequence: the copy spec's
                               own `sequence` for that form, never a copy of it
  wireframe_lines(kind, form, index, total)
                               the wireframe build-spec lines for one slice
  mockup_line(kind) / board(kind)
                               the mockup stages' one line, the Design Board's
                               page label and emphasis

Never calls a provider and never reads a secret.

  python3 scripts/page_kinds.py            # list the kinds and their sequences
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[1]
KINDS_FILE = SKILL_ROOT / "references" / "page-kinds.json"
SPEC_DIR = SKILL_ROOT / "references" / "copy-specs"


class KindError(Exception):
    """A named refusal; callers re-raise it as their own error type."""


_DATA = None


def data() -> dict:
    global _DATA
    if _DATA is None:
        try:
            _DATA = json.loads(KINDS_FILE.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise KindError(f"cannot read {KINDS_FILE.name}: {exc}")
    return _DATA


def kind_ids() -> list:
    return list(data()["kinds"])


def normalize(value) -> str:
    """"opt-in", "Opt In" -> "opt_in"; anything else is returned lowered."""
    return re.sub(r"[\s-]+", "_", str(value or "").strip().lower())


def entry(kind: str) -> dict:
    found = data()["kinds"].get(normalize(kind))
    if found is None:
        raise KindError(f"page_kind {kind!r} is not one of {', '.join(kind_ids())}")
    return found


def declared(run_dir, request: dict):
    """The run's page kind: request page_kind, request metadata, intake.json.
    Returns the normalised id, or None when nothing declares one."""
    metadata = request.get("metadata") if isinstance(request.get("metadata"), dict) else {}
    values = [request.get("page_kind"), metadata.get("page_kind")]
    try:
        intake = json.loads((Path(run_dir) / "intake.json").read_text(encoding="utf-8"))
        values.append(intake.get("page_kind"))
    except (OSError, ValueError, AttributeError):
        pass
    for value in values:
        if value:
            entry(value)  # an unknown kind is a refusal, never a silent skip
            return normalize(value)
    return None


def check(kind, copy_version) -> None:
    if not kind:
        raise KindError(f"no page_kind is recorded (one of {', '.join(kind_ids())})")
    allowed = entry(kind)["copy_versions"]
    if copy_version not in allowed:
        raise KindError(
            f"page_kind {normalize(kind)!r} uses the {' or '.join(allowed)} copy; the run "
            f"declares copy_version {copy_version!r} (references/page-kinds.json)")


def sequence(kind: str, copy_version: str) -> list:
    check(kind, copy_version)
    spec = json.loads((SPEC_DIR / f"{copy_version}-v6.json").read_text(encoding="utf-8"))
    return list(spec["sequence"])


def wireframe_lines(kind: str, form_label: str, index: int, total: int) -> list:
    """The page-kind head, and on the last slice the closing band."""
    e = entry(kind)
    lines = [e["wireframe_head"].format(form_label=form_label, total=total)]
    if index == total:
        lines.append(e["closing_band"])
    return lines


def mockup_line(kind: str) -> str:
    return entry(kind)["mockup_line"]


def board(kind: str) -> tuple:
    b = entry(kind)["design_board"]
    return b["label"], b["emphasis"]


if __name__ == "__main__":
    for k in kind_ids():
        e = entry(k)
        print(f"{k}: {e['tag']} page_role={data()['page_role']} action={e['action']}")
        for form in e["copy_versions"]:
            seq = sequence(k, form)
            print(f"  {form}: {len(seq)} sections {','.join(seq)}")
    sys.exit(0)
