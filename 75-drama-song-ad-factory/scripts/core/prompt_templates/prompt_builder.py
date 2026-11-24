#!/usr/bin/env python3
"""prompt_builder.py — the picture Prompt Builder (N-77, plan section 3H).

WHY THIS EXISTS
    Picture prompts were hand-written at about 4,000 characters and refused at
    dispatch for being under the provider floor (19,000 characters; the
    provider caps at 20,000). That cost a whole rewrite round. Code now
    assembles every picture prompt: the fixed lock blocks are copied whole and
    only the shot's own part is written by the section writer. The builder
    checks length, banned words, recorded strings and reference pictures
    before anything is dispatched, stamps the prompt, and NEVER pads.

WHAT IT ASSEMBLES (plan 3H.1)
    look, identity, place, wardrobe, expression, text rules and negatives come
    from the run's look lock and the character/location records. The shot's own
    part (action, framing, camera, light) is the ONLY text a writer supplies.

WHAT IT CHECKS (plan 3H.2)
    1. Length between the provider floor and cap. Under the floor REFUSES and
       names the thin shot fields; it never adds filler or repeats a block.
    2. Banned words for the look, only in the shot's own part (the locked block
       may contain its own words, e.g. "soft pores").
    3. Every recorded string from the text record, in quotes.
    4. Every reference picture the Shot Router listed, fingerprinted.
    5. The stamp: the lock version and each block's sha256.

REFUSAL CODES
    PICTURE_PROMPT_BELOW_FLOOR, PICTURE_PROMPT_ABOVE_CAP, STYLE_WORD_BANNED,
    PICTURE_TEXT_MISSING, PICTURE_REFERENCE_MISSING.

Stdlib only. No network, no spend.
"""
from __future__ import annotations

import hashlib
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.dirname(HERE)
for _p in (CORE, HERE):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import prompt_templates as PT  # noqa: E402

#: The fixed blocks, in assembly order. A block the lock does not carry is
#: skipped, never invented.
FIXED_BLOCK_ORDER = ("look", "identity", "place", "wardrobe", "expression",
                     "text_rules", "negatives")

#: Fallbacks only when the manifest carries no ``picture_prompt_band``: the
#: provider floor and cap from Trevor's skill 66 rule (plan 3H).
DEFAULT_FLOOR = 19000
DEFAULT_CAP = 20000


def _band(floor=None, cap=None, root=None):
    """The picture band: explicit args, then the manifest, then the defaults."""
    lo, hi = floor, cap
    if lo is None or hi is None:
        try:
            b = (PT.load("manifest", root=root).get("picture_prompt_band") or {})
        except PT.PromptTemplateError:
            b = {}
        lo = b.get("floor", DEFAULT_FLOOR) if lo is None else lo
        hi = b.get("cap", DEFAULT_CAP) if hi is None else hi
    return int(lo), int(hi)


def _blocks(lock):
    """The fixed block texts from a run look lock, in FIXED_BLOCK_ORDER."""
    src = dict(lock.get("blocks") or {})
    for k in FIXED_BLOCK_ORDER:
        if k not in src and isinstance(lock.get(k), str):
            src[k] = lock[k]
    return [(k, src[k]) for k in FIXED_BLOCK_ORDER if src.get(k)]


def _sha(text):
    return hashlib.sha256(str(text).encode("utf-8")).hexdigest()


def _banned(lock, mode=None):
    words = lock.get("banned_words")
    if not words and isinstance(mode, dict):
        words = mode.get("banned_words")
    return [str(w).strip() for w in (words or []) if str(w).strip()]


def assemble(shot, lock, mode=None, floor=None, cap=None, root=None):
    """Assemble one picture prompt. Returns {prompt, chars, stamp}.

    Raises ``PT.PromptTemplateError`` with one of the refusal codes above.
    Nothing is ever padded: a short prompt is refused, not filled.
    """
    lo, hi = _band(floor, cap, root)
    blocks = _blocks(lock)
    if not blocks:
        raise PT.PromptTemplateError(
            "PROMPT_LOCK_EMPTY",
            "the look lock carries no fixed blocks; nothing may be pasted by hand")
    shot_part = str(shot.get("shot_part") or "").strip()
    if not shot_part:
        raise PT.PromptTemplateError(
            "PICTURE_PROMPT_BELOW_FLOOR",
            "%d < %d and the shot's own part is empty; the writer must supply "
            "the action, framing, camera and light" % (0, lo))

    prompt = "\n\n".join("%s: %s" % (k.replace("_", " ").title(), v)
                         for k, v in blocks)
    prompt = prompt + "\n\nShot: " + shot_part

    # 2. Banned words, in the shot's own part only (the locked block may hold
    #    its own words by design).
    low_shot = shot_part.lower()
    for w in _banned(lock, mode):
        if w.lower() in low_shot:
            raise PT.PromptTemplateError(
                "STYLE_WORD_BANNED",
                "%r is not this look's word; it may appear only inside the "
                "locked block" % w)

    # 3. Every recorded string, in quotes.
    for entry in shot.get("text_on_screen") or []:
        for line in (entry.get("lines") if isinstance(entry, dict) else []) or []:
            s = str(line).strip()
            if s and '"%s"' % s not in prompt:
                raise PT.PromptTemplateError(
                    "PICTURE_TEXT_MISSING",
                    "the text record's %r must appear in the prompt in quotes" % s)

    # 4. Every reference picture, by fingerprint in the lock.
    known = set(str(x) for x in (lock.get("fingerprints") or [])
                if isinstance(x, str))
    for ref in shot.get("reference_pictures") or []:
        fp = ref.get("sha256") if isinstance(ref, dict) else None
        if not fp or str(fp) not in known:
            raise PT.PromptTemplateError(
                "PICTURE_REFERENCE_MISSING",
                "reference %r is not in the lock file"
                % (ref.get("path") if isinstance(ref, dict) else ref))

    # 1. Length. Over the cap trims the shot's own part (background first,
    #    action last); a locked block is never trimmed.
    prompt, shot_part = _fit_cap(shot, blocks, shot_part, hi)
    n = len(prompt)
    if n < lo:
        thin = shot.get("thin_fields") or []
        raise PT.PromptTemplateError(
            "PICTURE_PROMPT_BELOW_FLOOR",
            "%d < %d; the spec is thin in: %s. Supply those facts; never pad."
            % (n, lo, ", ".join(thin) if thin else "(fields not named)"))
    if n > hi:
        raise PT.PromptTemplateError(
            "PICTURE_PROMPT_ABOVE_CAP",
            "%d > %d after trimming the shot's own part" % (n, hi))

    # N-34: the stamp's shape matches prompt_templates.style_stamp (a single
    # block_sha256), so the dispatcher reads one shape on both prompt paths.
    # The picture lock's look block is the stamped block; the per-block hashes
    # ride along for the builder's own accounting.
    version = lock.get("version") or lock.get("lock_version")
    block_sha = {k: _sha(v) for k, v in blocks}
    look_block = dict(blocks).get("look") or ""
    stamp = {"lock_version": version,
             "block_sha256": _sha(look_block) if look_block else "",
             "block_sha256_by_block": block_sha,
             "prompt_sha256": _sha(prompt)}
    return {"prompt": prompt, "chars": n, "stamp": stamp}


def _fit_cap(shot, blocks, shot_part, cap):
    """Trim the shot's own part, background detail first and action last."""
    fixed = "\n\n".join("%s: %s" % (k.replace("_", " ").title(), v)
                        for k, v in blocks)
    optional = [str(x).strip() for x in (shot.get("trim_order") or [])
                if str(x).strip()]
    cur = shot_part
    prompt = fixed + "\n\nShot: " + cur
    for piece in optional:            # caller order: background detail first
        if len(prompt) <= cap:
            break
        if piece and piece in cur:
            cur = cur.replace(piece, "", 1).strip()
            cur = " ".join(cur.split())
            prompt = fixed + "\n\nShot: " + cur
    return prompt, cur


def build(shot, lock, mode=None, root=None):
    """Convenience wrapper: the result, or the refusal dict (never raised).

    Mirrors make_h3_request.build's ``(value, refusal)`` shape so a caller can
    branch without try/except.
    """
    try:
        return assemble(shot, lock, mode=mode, root=root), None
    except PT.PromptTemplateError as exc:
        return None, {"reason_code": getattr(exc, "code", "PICTURE_PROMPT"),
                      "detail": str(exc)}


if __name__ == "__main__":
    # One runnable check: a padded prompt refuses, a full one stamps clean.
    lock = {"version": 3,
            "blocks": {"look": "clearly animated 3D, soft light",
                       "identity": "same face as the reference pictures"},
            "fingerprints": ["abc123"],
            "banned_words": ["photoreal"]}
    thin = {"shot_part": "She turns toward the window.",
            "thin_fields": ["composition", "lens_light"]}
    out, refusal = build(thin, lock)
    assert out is None and refusal["reason_code"] == "PICTURE_PROMPT_BELOW_FLOOR", refusal
    full = {"shot_part": "She turns toward the window. " + "The kitchen is still. " * 900,
            "reference_pictures": [{"path": "key.png", "sha256": "abc123"}],
            "text_on_screen": [{"object": "diploma", "lines": ["Bachelor of Science"]}]}
    full["shot_part"] += 'The diploma reads exactly "Bachelor of Science".'
    res, refusal = build(full, lock)
    assert refusal is None and res["chars"] >= 19000, (refusal, res and res["chars"])
    assert res["stamp"]["lock_version"] == 3 and "look" in res["stamp"]["block_sha256_by_block"]
    bad = dict(full, shot_part=full["shot_part"] + " a photoreal frame")
    _, refusal = build(bad, lock)
    assert refusal and refusal["reason_code"] == "STYLE_WORD_BANNED", refusal
    print("prompt_builder self-check: OK")
