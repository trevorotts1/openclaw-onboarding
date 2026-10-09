#!/usr/bin/env python3
"""Video-model lock (manual Part F F14, Critical). Stdlib only.

Rule: the video model is locked to the card's choice (default MiniMax H3
768P, decision 5). The allowed list is exactly the models in
references/price-menu.md - anything else (seedance-1.5-pro included) is
refused even if KIE offers it. No automatic fallback: if the chosen model
is down, stop and ask the owner with the next approved option and its price.

Pieces:
- ALLOWED_VIDEO_MODELS  static fallback list mirroring price-menu.md
- parse_price_menu()    reads the men table; tests assert parse == static
- assert_allowed(m)     raises ModelLockError(MODEL_NOT_ON_MENU) off-menu
- lock_run_model(...)   writes the chosen model into run state (choice card)
- read_locked_model(..) the dispatch gate reads this; None = fail-closed
- check_video_model_delivery(receipt, locked) for the delivery gate (F16)

price-menu.md itself is a human snapshot, not a price authority: this module
reads only the MODEL IDs from its "Rates used" table, never rates.
"""
from __future__ import annotations

import os
import re
import sqlite3
from pathlib import Path

TOOL_NAME = "model_lock"
SCHEMA_VERSION = "blackceo.model-lock/v1"
LOCK_TABLE = "video_model_lock"

# Static fallback list mirroring price-menu.md "Rates used (silent, no
# audio)" rows (first column, parenthesized KIE ids, in table order). parse
# must return exactly this or the drift test fails.
ALLOWED_VIDEO_MODELS = (
    "veo3_fast",
    "veo-3-1",
    "veo3",
    "happyhorse-1-1/*",
    "minimax-h3/*",
    "kling-3.0-omni/*",
    "google/gemini-omni-flash-1-1",
    "bytedance/seedance-2-5",
    "wan/3-0-video",
    "kling-3.0/video",
    "bytedance/seedance-2-mini",
)

# Decision 5 default: MiniMax H3 768P - the id price-menu.md names for the
# family ("minimax-h3/*"); the card's per-member picks stay in the family.
DEFAULT_VIDEO_MODEL = "minimax-h3/*"

# Lip-sync is not a menu video model: Trevor locked the lip-sync model. The F14
# video lock (menu + card choice) does not apply to it; kie_dispatch lets this
# one model through F14 and then holds it to the picture gate.
LOCKED_LIPSYNC_MODEL = "kling/ai-avatar-standard"

# Walk up from this file for references/price-menu.md (kie_dispatch pattern).
_PRICE_MENU_RELS = (("references", "price-menu.md"),)
PRICE_MENU_ENV = "PRICE_MENU_MD"
_MENU_SECTION = "Rates used (silent, no audio)"


def _loud(kind, code, detail):
    """Named, visible failure/warning that reaches the receipt (loud_failure.py)."""
    import os as _os, sys as _sys
    d = _os.path.dirname(_os.path.abspath(__file__))
    while d != _os.path.dirname(d) and not _os.path.exists(_os.path.join(d, "loud_failure.py")):
        d = _os.path.dirname(d)
    if d not in _sys.path:
        _sys.path.insert(0, d)
    import loud_failure
    getattr(loud_failure, kind)(code, detail)


class ModelLockError(Exception):
    """Carries a machine reason code (e.g. MODEL_NOT_ON_MENU)."""

    def __init__(self, reason, message, model=""):
        super().__init__(message)
        self.reason = reason
        self.model = model
        self.message = message


def is_locked_lipsync(model):
    """True for the one lip-sync model Trevor locked (exact id)."""
    return (model or "").strip() == LOCKED_LIPSYNC_MODEL


def resolve_price_menu(explicit=None):
    """Path to price-menu.md: explicit -> $PRICE_MENU_MD -> walk up. Or None."""
    if explicit:
        return explicit if os.path.isfile(explicit) else None
    env = os.environ.get(PRICE_MENU_ENV)
    if env and os.path.isfile(env):
        return env
    start = Path(__file__).resolve()
    for parent in (start,) + tuple(start.parents):
        for rel in _PRICE_MENU_RELS:
            cand = parent.joinpath(*rel)
            if cand.is_file():
                return str(cand)
    return None


def parse_price_menu(path=None):
    """Model ids from the menu's 'Rates used' table, table order, deduped.

    Raises FileNotFoundError when path is None and the menu is not found
    (drift checks must not silently pass on a missing menu).
    """
    p = Path(path or resolve_price_menu())
    text = p.read_text(encoding="utf-8")
    ids, in_section = [], False
    for line in text.splitlines():
        if line.startswith("#"):
            in_section = _MENU_SECTION in line
            continue
        if not in_section:
            continue
        if not line.strip().startswith("|"):
            continue
        cell = line.strip().strip("|").split("|")[0].strip()
        m = re.search(r"\(([^)]*)\)", cell)
        if not m:
            continue
        for tok in m.group(1).split(";"):
            tok = tok.strip()
            if tok.startswith("market id "):
                tok = tok[len("market id "):].strip()
            # model ids are bare tokens: skip the header row ("KIE id") and
            # row annotations like "std=720p, pro=1080p"
            if tok and not re.search(r"[\s=,]", tok) and tok not in ids:
                ids.append(tok)
    return ids


def _allowed():
    """Menu list when readable, else the static fallback. Never empty."""
    menu = resolve_price_menu()
    if menu:
        try:
            parsed = parse_price_menu(menu)
            if parsed:
                return list(parsed)
        except (OSError, ValueError) as exc:
            _loud("warn", "PRICE_MENU_UNPARSEABLE",
                  "falling back to the built-in video model list: %r" % (exc,))
    return list(ALLOWED_VIDEO_MODELS)


def matches_family(model, pattern):
    """True when model fits a menu pattern: exact, or 'fam/*' family member."""
    model, pattern = (model or "").strip(), (pattern or "").strip()
    if pattern.endswith("/*"):
        base = pattern[:-2]
        return model == pattern or model == base or \
            model.startswith(base + "/")
    return model == pattern


def _hit(model):
    """The menu pattern that covers model, or None."""
    for pat in _allowed():
        if matches_family(model, pat):
            return pat
    return None


def assert_allowed(model):
    """Refuse anything not on price-menu.md (seedance-1.5-pro included).

    Raises ModelLockError(reason='MODEL_NOT_ON_MENU'); returns model on pass.
    """
    if model and _hit(model):
        return model
    raise ModelLockError(
        "MODEL_NOT_ON_MENU",
        "video model %r is not on price-menu.md; the allowed list is exactly "
        "the menu (seedance-1.5-pro included). Never call KIE directly; take "
        "the refusal to the owner." % (model,),
        model=model or "")


# -- run state ---------------------------------------------------------------

_LOCK_DDL = (
    "CREATE TABLE IF NOT EXISTS %s("
    " run_id TEXT PRIMARY KEY, model TEXT NOT NULL,"
    " locked_at TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 0)"
    % LOCK_TABLE)


def _db(state_store):
    """sqlite3.connect path for a path str or a state_store.Store."""
    p = getattr(state_store, "path", None)
    return str(p) if p is not None else str(state_store)


def lock_run_model(state_store, run_id, model=None):
    """Write the chosen video model into run state (choice card step).

    model None -> DEFAULT_VIDEO_MODEL. Refuses off-menu models with
    MODEL_NOT_ON_MENU (the card only ever offers menu models). Re-locking
    the same run replaces the choice (the card is the single writer).
    """
    chosen = model or DEFAULT_VIDEO_MODEL
    assert_allowed(chosen)                      # never lock an off-menu id
    con = sqlite3.connect(_db(state_store), timeout=30)
    try:
        con.execute(_LOCK_DDL)
        con.execute(
            "INSERT INTO %s(run_id, model, locked_at, version)"
            " VALUES(?,?,datetime('now'),1)"
            " ON CONFLICT(run_id) DO UPDATE SET model=excluded.model,"
            " locked_at=excluded.locked_at, version=version+1"
            % LOCK_TABLE, (run_id, chosen))
        con.commit()
        row = con.execute(
            "SELECT run_id, model, locked_at, version FROM %s"
            " WHERE run_id=?" % LOCK_TABLE, (run_id,)).fetchone()
        return {"run_id": row[0], "model": row[1], "locked_at": row[2],
                "version": row[3], "schema_version": SCHEMA_VERSION}
    finally:
        con.close()


def read_locked_model(state_store, run_id):
    """The locked video model, or None (no lock recorded / unreadable store).

    None is fail-closed at the dispatcher: never dispatch un-locked videos.
    """
    if not state_store or not run_id:
        return None
    try:
        con = sqlite3.connect(_db(state_store), timeout=10)
        try:
            row = con.execute(
                "SELECT model FROM %s WHERE run_id=?" % LOCK_TABLE,
                (run_id,)).fetchone()
            return row[0] if row else None
        finally:
            con.close()
    except sqlite3.Error:
        return None


# -- delivery gate (wired by the F16 unit) -----------------------------------

def _clips(receipt):
    """Best-effort clip list from a receipt: the shapes the gate allows."""
    if isinstance(receipt, list):
        return receipt
    if isinstance(receipt, dict):
        for key in ("clips", "video_clips", "shots"):
            v = receipt.get(key)
            if isinstance(v, list):
                return v
    return []


def _clip_model(clip):
    if not isinstance(clip, dict):
        return None
    for key in ("model", "video_model", "model_id"):
        v = clip.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return None


def check_video_model_delivery(receipt, locked_model):
    """[] when every clip's model equals the locked one, else mismatch list.

    Manual F14: any mismatch fails the ad.
    """
    locked = locked_model or DEFAULT_VIDEO_MODEL
    out = []
    for i, clip in enumerate(_clips(receipt)):
        m = _clip_model(clip)
        if m is None:
            out.append(
                "VIDEO_MODEL_MISMATCH: clip %s records no model; locked "
                "model is %s" % (i, locked))
        elif not matches_family(m, locked):
            out.append(
                "VIDEO_MODEL_MISMATCH: clip %s used %r but the locked video "
                "model is %r" % (i, m, locked))
    return out


if __name__ == "__main__":                    # self-check, run from this dir
    _menu = resolve_price_menu()
    print("menu:", _menu)
    _parsed = parse_price_menu(_menu) if _menu else []
    print("parsed:", _parsed)
    print("drift:", "NONE" if _parsed == list(ALLOWED_VIDEO_MODELS)
          else _parsed)
    try:
        assert_allowed("bytedance/seedance-1.5-pro")
        print("seedance-1.5-pro: NOT REFUSED (bug)")
    except ModelLockError as e:
        print("seedance-1.5-pro: refused %s" % e.reason)
    print("default:", DEFAULT_VIDEO_MODEL, "allowed:",
          assert_allowed(DEFAULT_VIDEO_MODEL))