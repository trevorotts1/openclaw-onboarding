#!/usr/bin/env python3
"""attempt_ceiling.py: stop after N consecutive IDENTICAL structural failures
(L4.4, v2.9.73 reliability; live proof: the Voyage To Virtue run made 65
lip-sync attempts, every one FAIL FACE_COUNT "0 faces found", with no early
abort — ~8 h of paid retries on stills where no lip-sync attempt could ever
pass).

A structural failure is one whose receipt names the SAME failure code and the
same structural key (the stills' measured face_count for image gates) — the
shape of the input, not its content: re-trying an unchanged shape can only
produce the same verdict. After CEILING (3) consecutive identical structural
failures the run STOPS with the cause named — e.g. "no face in these stills —
choose a face-visible format" — and reports; it never retries again until a
HUMAN changes the plan.

Two call shapes:
  * consecutive_identical(receipts) -> (count, sample) for the trailing run of
    receipts sharing one structural key;
  * ceiling_check(receipts, ceiling=CEILING) -> {"stop": bool, "count": n,
    "cause": code, "message": str, "structural": <key>} — stop=True when
    n >= ceiling. Empty or missing history never stops; a structural KEY the
    caller cannot derive (face_count missing) is NOT counted as identical.

stdlib only, no network, no spend. Test:
scripts/core/lip_sync/lip_gate/test_attempt_ceiling_v2973.py
"""
from __future__ import annotations

CEILING = 3                            # 3 consecutive identical structural failures
LIP_CEILING_CODE = "ATTEMPT_CEILING_REACHED"
NO_FACE_IN_STILLS = "no face in these stills — choose a face-visible format"

#: structural failure families this gate names, keyed by the measured field
#: that decides them. A code NOT in this table is not structural (e.g. a
#: transient provider error) and never counts toward the ceiling.
STRUCTURAL_CODES = frozenset({
    "FACE_COUNT",          # picture_gate: the stills' face count decided it
    "LIPSYNC_IMAGE_UNMEASURED",   # image_gate: the source could not be measured
    "LIPSYNC_COVERAGE_SHORT",     # final edit: coverage cannot change on retry
    "LIPSYNC_LINES_TOO_FEW",
})

def structural_key(receipt):
    """The failure's structural identity: (code, value) of the deciding
    measured field (face_count when named), else None (not structural)."""
    if not isinstance(receipt, dict):
        return None
    reasons = receipt.get("reasons") or receipt.get("fails") or []
    if not isinstance(reasons, list):
        return None
    face = (receipt.get("numbers") or {}).get("face_count") \
        if isinstance(receipt.get("numbers"), dict) else None
    for item in reasons:
        code = item[0] if isinstance(item, (list, tuple)) and item else item
        text = item[1] if isinstance(item, (list, tuple)) and len(item) > 1 else ""
        if code in STRUCTURAL_CODES:
            # FACE_COUNT carries its measured count in the reason text
            # ("0 faces found; exactly 1 is required"); the count IS the key.
            if code == "FACE_COUNT":
                return ("FACE_COUNT", None if face is None else str(face))
            return (str(code), "")
    return None

def consecutive_identical(receipts):
    """[receipt...] -> (count, sample_key). Trailing run of receipts sharing
    one structural key; non-structural or missing-key receipts break the run."""
    if not isinstance(receipts, list):
        return 0, None
    count, tail = 0, None
    for rec in reversed(receipts or []):
        k = structural_key(rec)
        if k is None:
            break
        if tail is not None and k != tail:
            break
        tail = k
        count += 1
    return count, tail

def ceiling_check(receipts, ceiling=CEILING):
    """Stop when the last `ceiling` attempts are the SAME structural failure.
    Returns a dict; never raises on bad history (unusable history = no stop)."""
    try:
        n, key = consecutive_identical(list(receipts or []))
    except Exception:                                # noqa: BLE001
        return {"stop": False, "count": 0}
    out = {"stop": bool(n and key and n >= int(ceiling) and ceiling >= 1),
           "count": n, "structural_code": (key[0] if key else None),
           "structural_value": (key[1] if key else None),
           "ceiling": int(ceiling)}
    if out["stop"]:
        if key[0] == "FACE_COUNT":
            v = key[1]
            out["cause"] = LIP_CEILING_CODE
            found = ("%s face(s)" % v) if v is not None else "no measured face count"
            out["message"] = ("no face in these stills — choose a face-visible "
                              "format: the last %d attempts all measured %s; "
                              "stopped before another paid attempt" % (n, found))
        else:
            out["cause"] = LIP_CEILING_CODE
            out["message"] = ("the same structural failure (%s) on %d consecutive "
                              "attempts; stopped before another paid attempt"
                              % (key[0], n))
    return out
