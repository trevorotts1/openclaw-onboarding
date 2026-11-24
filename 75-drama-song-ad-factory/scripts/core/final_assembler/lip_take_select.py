"""G-LIP-01: the lip decider prefers the clean lip take on disk.

Old failure: a stale failed-letter list made the decider run H3 base on shots
that already had a letter-clean lip take on disk. The 1:02 window shipped with
no mouth match although clean lip takes sat on disk.

Rule (G-LIP-01):
  * a shot with ``lip_sync: true`` whose take options include a take the letter
    pass marked ``LETTERS_CLEAN`` MUST use that lip take; choosing an H3/base
    take while a clean lip take exists is refused ``CLEAN_LIP_TAKE_EXISTS``;
  * an H3/base take on a ``lip_sync: true`` shot is admitted ONLY with a
    receipt proving zero clean lip takes on disk AND the run owner's recorded
    written order (``h3_admit``); otherwise ``H3_BASE_NEEDS_ORDER``.

Data shape (per plan segment, written by the planning step):
    take_options: [{"take_id", "model", "letters", "path"}, ...]
    chosen_take:  {"take_id", "model", ...} or the take_id string
    h3_admit:     {"no_clean_lip_proof": <path/str>, "order": {"who","at"}}

Stdlib only. Pure functions; no disk, no ffmpeg, no network.
"""
from __future__ import annotations

#: The letter pass's clean marker (lipsync-fix ledger-v4.json spelling).
LETTERS_CLEAN = "LETTERS_CLEAN"

#: A clean lip take sits on disk but a base take was chosen.
CLEAN_LIP_TAKE_EXISTS = "CLEAN_LIP_TAKE_EXISTS"
#: An H3/base take on a lip-sync shot without proof + the owner's order.
H3_BASE_NEEDS_ORDER = "H3_BASE_NEEDS_ORDER"

#: Models that ARE a lip-sync take. Anything else is a base/story take.
_LIP_MODELS = ("omnihuman", "kling", "ai-avatar", "ai_avatar", "infinitalk")
#: Models that name an H3 / base (non-lip-sync) take.
_BASE_MODELS = ("h3", "hailuo", "minimax", "base")


def _model_name(take):
    if isinstance(take, dict):
        return str(take.get("model") or "").lower()
    return ""


def _letters(take):
    if isinstance(take, dict):
        return take.get("letters")
    return None


def is_lip_model(model):
    """True when the model name is a lip-sync take (not an H3/base take)."""
    m = str(model or "").lower()
    return any(k in m for k in _LIP_MODELS)


def is_base_model(model):
    """True when the model name is an H3/base (non-lip-sync) take."""
    m = str(model or "").lower()
    return any(k in m for k in _BASE_MODELS) and not is_lip_model(m)


def is_clean_lip_take(take):
    """A lip take the letter pass marked LETTERS_CLEAN."""
    if not isinstance(take, dict):
        return False
    if _letters(take) != LETTERS_CLEAN:
        return False
    return is_lip_model(_model_name(take))


def _chosen_take(chosen):
    return chosen.get("take_id") if isinstance(chosen, dict) else chosen


def check_shot(take_options=None, chosen_take=None, *, lip_sync=False,
               h3_admit=None):
    """One lip-sync shot's selection, as a refusal dict or None.

    ``take_options`` is the shot's candidate takes; ``chosen_take`` is the take
    the plan will use (a dict with ``take_id`` or the bare id).
    """
    if not lip_sync:
        return None
    options = [t for t in (take_options or []) if isinstance(t, dict)]
    clean = [t for t in options if is_clean_lip_take(t)]
    chosen_id = _chosen_take(chosen_take)
    chosen = next((t for t in options if t.get("take_id") == chosen_id), None)
    if chosen is None and isinstance(chosen_take, dict):
        chosen = chosen_take
    chosen_model = _model_name(chosen) if chosen else ""

    if clean and not is_clean_lip_take(chosen):
        return {
            "reason_code": CLEAN_LIP_TAKE_EXISTS,
            "next_action": (
                "a letter-clean lip take is on disk for this shot (%s); use "
                "it instead of an H3/base take -- the clean take wins "
                "(G-LIP-01)" % [t.get("take_id") for t in clean]),
            "clean_takes": [t.get("take_id") for t in clean],
            "chosen": chosen_id,
        }

    if chosen is not None and is_base_model(chosen_model):
        order = (h3_admit or {}).get("order") if isinstance(h3_admit, dict) else None
        proof = ((h3_admit or {}).get("no_clean_lip_proof")
                 if isinstance(h3_admit, dict) else None)
        if not (isinstance(order, dict) and order.get("who") and order.get("at")
                and proof):
            return {
                "reason_code": H3_BASE_NEEDS_ORDER,
                "next_action": (
                    "an H3/base take on a lip-sync shot needs a receipt "
                    "proving zero clean lip takes on disk plus the run "
                    "owner's written order (G-LIP-01)"),
                "chosen": chosen_id,
            }
    return None


def refusals(plan):
    """Every lip-sync shot's G-LIP-01 refusal, in plan order."""
    out = []
    for seg in (plan or {}).get("segments") or []:
        if not isinstance(seg, dict):
            continue
        bad = check_shot(
            seg.get("take_options"), seg.get("chosen_take"),
            lip_sync=bool(seg.get("lip_sync") or seg.get("lip_sync_line_ids")),
            h3_admit=seg.get("h3_admit"))
        if bad is not None:
            bad = dict(bad, segments=[seg.get("src")])
            out.append(bad)
    return out


if __name__ == "__main__":
    # Self-check: a clean lip take beats an H3 base; an H3 base without proof
    # plus the owner's order refuses; a non-lip-sync shot is never judged.
    _clean = {"take_id": "T12", "model": "omnihuman-2-0",
              "letters": LETTERS_CLEAN}
    _h3 = {"take_id": "H3", "model": "minimax-h3"}
    assert is_clean_lip_take(_clean) and not is_clean_lip_take(_h3)
    # 1) clean lip take on disk + H3 chosen -> CLEAN_LIP_TAKE_EXISTS
    r = check_shot([_clean, _h3], _h3, lip_sync=True)
    assert r and r["reason_code"] == CLEAN_LIP_TAKE_EXISTS, r
    # 2) H3 chosen, no clean take, no order -> H3_BASE_NEEDS_ORDER
    r = check_shot([_h3], _h3, lip_sync=True)
    assert r and r["reason_code"] == H3_BASE_NEEDS_ORDER, r
    # 3) H3 chosen, no clean take, proof + owner order -> admitted
    ok = check_shot([_h3], _h3, lip_sync=True,
                    h3_admit={"no_clean_lip_proof": "lipsync-fix/ledger.json",
                              "order": {"who": "owner", "at": "recorded"}})
    assert ok is None, ok
    # 4) a non-lip-sync shot is never judged
    assert check_shot([_h3], _h3, lip_sync=False) is None
    print("lip_take_select self-check OK")

