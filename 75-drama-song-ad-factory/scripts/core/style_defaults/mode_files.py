"""Look mode-file loader and banned-word validator (N-35, section 3B.3; unit U-LOOK).

One place that reads a mode file and refuses a half-defined look. The blocks a
mode must carry are ``h3_block``, ``keyframe_clause`` and ``banned_words``
(section 3B.3 item 4); a file missing any of them fails at load. ``client_wording``
is required too, so the guide and the mode file can never drift (N-36).
``kling_block`` and ``kling_who`` are optional: the lip-sync model takes no
prompt, so a mode file without them still loads.

A mode may ``extend`` another by id; missing blocks are inherited before the
required-block check runs, so a derived look (golden-realism) needs only its own
differences.

Banned words are refused anywhere in a prompt that lies OUTSIDE the locked
block: the locked block is stripped before the scan, so a block's own negations
("never photoreal live-action") never trip it. The refusal code is
``STYLE_WORD_BANNED``.

stdlib only: no network, no runner, no paid call, no file writes.
"""
from __future__ import annotations

import json
from pathlib import Path

from .defaults import StyleDefaultsError

#: Blocks a resolved mode must carry. ``kling_block`` / ``kling_who`` are not
#: here on purpose (section 3B.3 item 4).
REQUIRED_BLOCKS = ("h3_block", "keyframe_clause", "banned_words", "client_wording")

#: The blocks a lock copies whole (section 3B.2), so the scan can strip them.
COPIED_BLOCKS = ("h3_block", "kling_block", "kling_who", "keyframe_clause")

#: <skill>/references/prompt-templates/modes, from this file's own location.
MODES_DIR = (Path(__file__).resolve().parents[3]
             / "references" / "prompt-templates" / "modes")


def modes_dir(root=None):
    """Directory holding the mode files; ``root`` overrides it for tests."""
    return Path(root) if root else MODES_DIR


def _read(path):
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise StyleDefaultsError("MODE_FILE_MISSING",
                                 "no mode file at %s" % path) from None
    except (ValueError, OSError) as exc:
        raise StyleDefaultsError("MODE_FILE_INVALID",
                                 "%s is not readable JSON: %s" % (path, exc)) from exc
    if not isinstance(doc, dict):
        raise StyleDefaultsError("MODE_FILE_INVALID",
                                 "%s must be a JSON object" % path)
    return doc


def _resolve(mode_id, root, seen):
    """Load ``mode_id`` and merge any ``extends`` parent in underneath."""
    if mode_id in seen:
        raise StyleDefaultsError("MODE_EXTENDS_CYCLE",
                                 "mode %r extends itself: %s"
                                 % (mode_id, " -> ".join(seen + [mode_id])))
    path = modes_dir(root) / ("%s.json" % mode_id)
    doc = _read(path)
    parent_id = doc.get("extends")
    if parent_id:
        parent = _resolve(parent_id, root, seen + [mode_id])
        merged = dict(parent)
        merged.update(doc)          # the child's own keys win
        doc = merged
    return doc


def load_mode(mode_id, root=None):
    """The resolved mode dict for ``mode_id``; every required block present.

    Raises ``StyleDefaultsError`` with code ``MODE_BLOCK_MISSING`` when a
    required block is absent after ``extends`` is applied.
    """
    mode = _resolve(mode_id, root, [])
    missing = [k for k in REQUIRED_BLOCKS if not mode.get(k)]
    if missing:
        raise StyleDefaultsError(
            "MODE_BLOCK_MISSING",
            "mode %r is missing %s (section 3B.3: every look has all its blocks)"
            % (mode_id, ", ".join(missing)))
    if not isinstance(mode["banned_words"], list):
        raise StyleDefaultsError(
            "MODE_BLOCK_MISSING",
            "mode %r banned_words must be a list" % mode_id)
    mode.setdefault("mode_id", mode_id)
    return mode


def load_all_modes(root=None):
    """``{mode_id: resolved mode}`` for every ``*.json`` mode file."""
    out = {}
    for path in sorted(modes_dir(root).glob("*.json")):
        mid = path.stem
        out[mid] = load_mode(mid, root=root)
    return out


def check_banned_words(prompt, banned_words, locked_block):
    """Refuse a prompt that carries a banned word outside the locked block.

    ``locked_block`` is the exact block text already placed in ``prompt`` (the
    style section); it is removed before scanning so the block's own negations
    are not refused. Raises ``STYLE_WORD_BANNED`` naming every hit.
    """
    if not isinstance(prompt, str):
        raise StyleDefaultsError("PROMPT_INVALID",
                                 "prompt must be a string, got %s"
                                 % type(prompt).__name__)
    remainder = prompt
    if locked_block:
        remainder = remainder.replace(locked_block, " ")
    low = remainder.lower()
    hits = [w for w in banned_words if w and w.lower() in low]
    if hits:
        raise StyleDefaultsError(
            "STYLE_WORD_BANNED",
            "prompt uses %s outside the locked style block"
            % ", ".join(repr(h) for h in hits))
    return prompt


def check_prompt(prompt, lock):
    """Lock-based convenience: scan ``prompt`` for ``lock``'s banned words.

    Strips **every** locked block first -- H3 and Kling alike, and each mode's
    blocks when the lock is a hybrid -- so a prompt built from the lock never
    trips on the lock's own negations (section 3B.1: "soft pores" in the
    Lifelike block, "no 3D render look" in the Realism Kling block). Then
    delegates to ``check_banned_words``.
    """
    if not isinstance(prompt, str):
        raise StyleDefaultsError("PROMPT_INVALID",
                                 "prompt must be a string, got %s"
                                 % type(prompt).__name__)
    pal = lock.get("palette") or ""
    block_sets = [lock.get("style_blocks") or lock]
    block_sets.extend((lock.get("style_blocks_by_mode") or {}).values())
    variants = set()
    for blocks in block_sets:
        for key in COPIED_BLOCKS:
            text = blocks.get(key)
            if not text:
                continue
            variants.add(text)
            if "{palette}" in text:
                variants.add(text.replace("{palette}", pal))
                variants.add(text.replace("{palette}", ""))
    remainder = prompt
    for v in sorted(variants, key=len, reverse=True):
        remainder = remainder.replace(v, " ")
    return check_banned_words(remainder, lock.get("banned_words") or [], "")


__all__ = [
    "MODES_DIR",
    "REQUIRED_BLOCKS",
    "check_banned_words",
    "check_prompt",
    "load_all_modes",
    "load_mode",
    "modes_dir",
]
