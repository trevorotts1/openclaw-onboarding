"""The look lock (section 3B.2, row N-29): one record written at intake.

At the moment the run owner picks a look, the run writes
``control/look-lock.json`` and nothing can be made before it exists (no
reference picture, no keyframe, no clip). The lock holds, copied whole from
the look's mode file:

* one look id and the mode file it resolves to;
* the style blocks (``h3_block``, ``kling_block``, ``kling_who``,
  ``keyframe_clause``) and the palette;
* the look's ``banned_words`` list;
* a fingerprint of all of it and a lock ``version`` starting at 1;
* who chose and when, and the character-bible fingerprint.

Changing the look later is allowed only by the run owner's recorded order: it
writes a new lock with the next version number, and everything made under the
old version is stale (``is_stale`` / section 3B.4).

stdlib only: no network, no runner, no spend. The only write is the lock file,
and only under the run folder the caller names.
"""
from __future__ import annotations

import hashlib
import json
import os

try:
    from prompt_templates import load as _load_mode
except ImportError as _e:                      # imported as core.style_defaults
    if "prompt_templates" not in str(_e):
        raise
    from ..prompt_templates import load as _load_mode   # type: ignore

TOOL_NAME = "style_defaults.look_lock"
TOOL_VERSION = "1.0.0"
SCHEMA_VERSION = "blackceo.look-lock/v1"

#: Where the lock lives inside a run folder.
LOOK_LOCK_RELPATH = "control/look-lock.json"

#: The blocks a lock copies. `kling_block`/`kling_who` are optional on a mode
#: (a look may never be lip-synced), so only the first and last are required.
REQUIRED_BLOCKS = ("h3_block", "keyframe_clause")
COPIED_BLOCKS = ("h3_block", "kling_block", "kling_who", "keyframe_clause")


class LookLockError(Exception):
    """A refusal this module owns. ``code`` is the stable string checks key on."""

    def __init__(self, code, message):
        super().__init__("%s: %s" % (code, message))
        self.code = code


def _canonical(payload):
    """Canonical JSON bytes: sorted keys, no whitespace. Same on every box."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False).encode("utf-8")


def fingerprint(payload):
    """SHA-256 hex over canonical JSON. The lock's own ``fingerprint`` is never
    part of the payload handed here."""
    return hashlib.sha256(_canonical(payload)).hexdigest()


def _resolve_mode(mode_id, root=None):
    """The mode file with ``extends`` folded in, so the lock is self-contained.

    ``golden-realism`` extends ``realism`` and appends an ``h3_block_suffix``;
    the effective ``h3_block`` is the base block with the suffix, exactly as
    ``prompt_templates._look_block`` renders it. A required block still missing
    after that resolution refuses the lock.
    """
    mode = _load_mode("mode", mode_id, root=root)
    return mode


def _effective_blocks(mode, root=None):
    """The four copied blocks plus palette, extends resolved."""
    text = {}
    base = None
    if mode.get("extends"):
        base = _load_mode("mode", mode["extends"], root=root)
    palette = (mode.get("palette") or mode.get("palette_default")
               or (base or {}).get("palette")
               or (base or {}).get("palette_default") or "")
    h3 = mode.get("h3_block")
    if h3:
        h3 = h3.replace("{palette}", palette)
        if mode.get("h3_block_suffix"):
            h3 = (h3 + " " + mode["h3_block_suffix"]).strip()
    elif base and base.get("h3_block"):
        base_palette = base.get("palette") or base.get("palette_default") or palette
        h3 = base["h3_block"].replace("{palette}", base_palette)
        if mode.get("h3_block_suffix"):
            h3 = (h3 + " " + mode["h3_block_suffix"]).strip()
    text["h3_block"] = h3
    text["kling_block"] = mode.get("kling_block") or (base or {}).get("kling_block")
    text["kling_who"] = mode.get("kling_who") or (base or {}).get("kling_who")
    text["keyframe_clause"] = (mode.get("keyframe_clause")
                              or (base or {}).get("keyframe_clause"))
    text["palette"] = palette
    return text


def mode_style_blocks(mode_id, root=None):
    """The effective style blocks + palette for a mode, extends resolved."""
    return _effective_blocks(_resolve_mode(mode_id, root), root=root)


def mode_banned_words(mode_id, root=None):
    """The look's banned-word list (section 3B.3 rule 3), from the mode file."""
    words = _resolve_mode(mode_id, root).get("banned_words")
    if not isinstance(words, list) or not words:
        raise LookLockError(
            "LOOK_BANNED_WORDS_MISSING",
            "mode %r carries no banned_words list; every look must define one"
            % mode_id)
    return list(words)


def mode_client_wording(mode_id, root=None):
    """The one client-facing line the guide must match (row N-36)."""
    line = _resolve_mode(mode_id, root).get("client_wording")
    if not isinstance(line, str) or not line.strip():
        raise LookLockError(
            "LOOK_CLIENT_WORDING_MISSING",
            "mode %r carries no client_wording line" % mode_id)
    return line.strip()


def resolve_look_modes(look_id, root=None):
    """Every mode file a card look renders with, in look-file order.

    A pure look (``lifelike-3d``) is its own mode. A hybrid card look
    (``canvas-to-3d``) has no mode file of its own: its ``looks/<id>.json``
    ``modes`` list names the modes it switches between. Unknown looks refuse
    by name (``LOOK_UNKNOWN``), never guessed.
    """
    if not isinstance(look_id, str) or not look_id.strip():
        raise LookLockError("LOOK_UNKNOWN",
                            "look id must be a non-empty string, got %r"
                            % (look_id,))
    try:
        _load_mode("mode", look_id, root=root)
        return [look_id]
    except Exception:                                   # noqa: BLE001
        pass
    try:
        look = _load_mode("look", look_id, root=root)
    except Exception as exc:                            # noqa: BLE001
        raise LookLockError(
            "LOOK_UNKNOWN",
            "%r is neither a mode file nor a card look: %s" % (look_id, exc)
        ) from exc
    modes = look.get("modes")
    if not isinstance(modes, list) or not modes:
        raise LookLockError("LOOK_UNKNOWN",
                            "look %r names no modes" % look_id)
    return list(modes)


def _union(lists):
    """Order-preserving union of word lists (first list's order first)."""
    out = []
    for words in lists:
        for w in words:
            if w not in out:
                out.append(w)
    return out


def build_lock(look_id, chosen_by, chosen_at, mode_id=None,
               character_bible_fingerprint=None, version=1, root=None):
    """A new lock record for one look, blocks copied whole from its mode file.

    ``look_id`` is the card look id; the mode files it renders with come from
    ``resolve_look_modes`` unless ``mode_id`` names one. A hybrid look records
    every mode's blocks and banned words (``style_blocks_by_mode`` /
    ``banned_words_by_mode``), and its flat ``style_blocks``/``banned_words``
    are the primary mode's blocks and the union of the modes' words. Missing
    style blocks or banned words refuse (``LOOK_BLOCK_MISSING`` / the two
    ``*_MISSING`` codes), so a look can never be half-defined.
    """
    if not isinstance(chosen_by, str) or not chosen_by.strip():
        raise LookLockError("LOOK_CHOSEN_BY_REQUIRED",
                            "the lock records who chose the look")
    if not isinstance(chosen_at, str) or not chosen_at.strip():
        raise LookLockError("LOOK_CHOSEN_AT_REQUIRED",
                            "the lock records when the look was chosen")
    if not isinstance(version, int) or version < 1:
        raise LookLockError("LOOK_VERSION_INVALID",
                            "lock version must be an integer >= 1, got %r" % (version,))
    modes = resolve_look_modes(look_id, root=root)
    if mode_id:
        if mode_id not in modes:
            raise LookLockError(
                "LOOK_MODE_NOT_IN_LOOK",
                "mode %r is not one of look %r's modes (%s)"
                % (mode_id, look_id, ", ".join(modes)))
        modes = [mode_id] + [m for m in modes if m != mode_id]
    per_mode = {}
    words_by_mode = {}
    for mid in modes:
        blocks = mode_style_blocks(mid, root=root)
        for key in REQUIRED_BLOCKS:
            if not blocks.get(key):
                raise LookLockError(
                    "LOOK_BLOCK_MISSING",
                    "mode %r has no %s; every look must define all its blocks"
                    % (mid, key))
        per_mode[mid] = {k: blocks.get(k) for k in COPIED_BLOCKS}
        words_by_mode[mid] = mode_banned_words(mid, root=root)
    primary = modes[0]
    blocks = mode_style_blocks(primary, root=root)
    body = {
        "schema_version": SCHEMA_VERSION,
        "look_id": look_id,
        "mode_id": primary,
        "modes": modes,
        "version": version,
        "chosen_by": chosen_by.strip(),
        "chosen_at": chosen_at.strip(),
        "character_bible_fingerprint": character_bible_fingerprint,
        "style_blocks": per_mode[primary],
        "palette": blocks.get("palette", ""),
        "banned_words": _union(words_by_mode[m] for m in modes),
    }
    if len(modes) > 1:
        body["style_blocks_by_mode"] = per_mode
        body["banned_words_by_mode"] = words_by_mode
    lock = dict(body)
    lock["fingerprint"] = fingerprint(body)
    return lock


def lock_fingerprint(lock):
    """Recompute the fingerprint over everything but ``fingerprint`` itself."""
    body = {k: v for k, v in lock.items() if k != "fingerprint"}
    return fingerprint(body)


def verify_fingerprint(lock):
    """True when the stored fingerprint still matches the lock's own content."""
    return lock.get("fingerprint") == lock_fingerprint(lock)


def rotate(lock, chosen_by, chosen_at, mode_id=None,
           character_bible_fingerprint=None, root=None):
    """The next lock after a recorded change of look, bible or route.

    The version goes up by one, so every picture and take made under the old
    version is stale (section 3B.4). A bible fingerprint left unset keeps the
    previous one.
    """
    if not isinstance(lock, dict) or "version" not in lock:
        raise LookLockError("LOOK_LOCK_INVALID", "rotate needs a lock record")
    if character_bible_fingerprint is None:
        character_bible_fingerprint = lock.get("character_bible_fingerprint")
    return build_lock(
        look_id=lock["look_id"],
        chosen_by=chosen_by,
        chosen_at=chosen_at,
        mode_id=mode_id or lock.get("mode_id"),
        character_bible_fingerprint=character_bible_fingerprint,
        version=int(lock["version"]) + 1,
        root=root,
    )


def look_lock_path(run_root):
    """Absolute path of the lock inside a run folder."""
    return os.path.join(os.path.abspath(run_root), *LOOK_LOCK_RELPATH.split("/"))


def read_lock(path):
    """The lock at ``path`` as a dict, or None when no lock exists yet."""
    try:
        with open(path, "r", encoding="utf-8") as fh:
            doc = json.load(fh)
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as exc:
        raise LookLockError("LOOK_LOCK_UNREADABLE",
                            "%s (%s)" % (path, exc)) from exc
    if not isinstance(doc, dict):
        raise LookLockError("LOOK_LOCK_NOT_AN_OBJECT", "%s holds %s"
                            % (path, type(doc).__name__))
    return doc


def read_lock_for_run(run_root):
    """The run's lock, or None before intake has written one."""
    return read_lock(look_lock_path(run_root))


def write_lock(run_root, lock):
    """Write ``control/look-lock.json`` under ``run_root``; atomic, one writer.

    Refuses to replace a lock with an older version number
    (``LOOK_LOCK_VERSION_REGRESS``). Returns the path written.
    """
    body = {k: v for k, v in lock.items() if k != "fingerprint"}
    if lock.get("fingerprint") != fingerprint(body):
        raise LookLockError("LOOK_FINGERPRINT_MISMATCH",
                            "refusing to write a lock whose fingerprint does "
                            "not match its content")
    path = look_lock_path(run_root)
    current = read_lock(path)
    if current is not None and int(lock.get("version", 0)) < int(current.get("version", 0)):
        raise LookLockError(
            "LOOK_LOCK_VERSION_REGRESS",
            "lock version %r is older than the recorded %r"
            % (lock.get("version"), current.get("version")))
    folder = os.path.dirname(path)
    os.makedirs(folder, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(lock, fh, indent=2, sort_keys=True, ensure_ascii=False)
        fh.write("\n")
    os.replace(tmp, path)
    return path


def require_lock(run_root):
    """The run's lock, or ``LOOK_LOCK_MISSING`` -- nothing is made before it."""
    lock = read_lock_for_run(run_root)
    if lock is None:
        raise LookLockError(
            "LOOK_LOCK_MISSING",
            "no control/look-lock.json under %s; nothing may be made before the "
            "look is locked" % run_root)
    return lock


def is_stale(made_under_version, lock):
    """A record made under an older lock version is stale (section 3B.4)."""
    return int(made_under_version) < int(lock["version"])


def is_current(made_under_version, lock):
    """A record is current only at the lock's own version."""
    return int(made_under_version) == int(lock["version"])


def verify_still_matches(lock, root=None):
    """True when the lock's blocks and banned words still equal its mode file.

    A mode file edited after intake without a fresh lock is drift
    (``LOOK_LOCK_DRIFT``); the run must rotate the lock rather than render
    against a stale block.
    """
    mode_id = lock.get("mode_id") or lock.get("look_id")
    modes = lock.get("modes") or [mode_id]
    per_mode = lock.get("style_blocks_by_mode") or {}
    words_by_mode = lock.get("banned_words_by_mode") or {}
    for mid in modes:
        blocks = mode_style_blocks(mid, root=root)
        locked = per_mode.get(mid) or (lock.get("style_blocks") or {})
        for key in COPIED_BLOCKS:
            if locked.get(key) != blocks.get(key):
                raise LookLockError(
                    "LOOK_LOCK_DRIFT",
                    "lock %r block %r no longer matches mode %r; rotate the lock"
                    % (lock.get("look_id"), key, mid))
        words = words_by_mode.get(mid)
        if words is None:
            words = lock.get("banned_words") or []
        if list(words) != mode_banned_words(mid, root=root):
            raise LookLockError(
                "LOOK_LOCK_DRIFT",
                "lock %r banned words no longer match mode %r; rotate the lock"
                % (lock.get("look_id"), mid))
    return True


def banned_word_hits(text, banned_words, exempt=""):
    """Banned words found in ``text`` outside the locked block.

    ``exempt`` is the lock's own ``h3_block`` (palette-substituted); it is
    removed before the scan, so a look whose block legitimately says
    "no photoreal" never trips on its own text (section 3B.1). Matching is
    case-insensitive on whole phrases, longest first, so "photo" never fires
    inside "photograph" it already matched.
    """
    haystack = text or ""
    if exempt:
        haystack = haystack.replace(exempt, " ")
    low = haystack.lower()
    hits = []
    for word in sorted((w for w in banned_words if w), key=len, reverse=True):
        if word.lower() in low:
            hits.append(word)
            low = low.replace(word.lower(), " ")
    return hits


__all__ = [
    "COPIED_BLOCKS",
    "LOOK_LOCK_RELPATH",
    "REQUIRED_BLOCKS",
    "SCHEMA_VERSION",
    "LookLockError",
    "banned_word_hits",
    "build_lock",
    "fingerprint",
    "is_current",
    "is_stale",
    "lock_fingerprint",
    "look_lock_path",
    "mode_banned_words",
    "mode_client_wording",
    "mode_style_blocks",
    "read_lock",
    "read_lock_for_run",
    "require_lock",
    "resolve_look_modes",
    "rotate",
    "verify_fingerprint",
    "verify_still_matches",
    "write_lock",
]
