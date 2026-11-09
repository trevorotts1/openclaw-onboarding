#!/usr/bin/env python3
"""E02: an exchange passes only when it CHANGES a recorded decision.

``character_bible.check_cast`` is structural: a villain speaks and another
declared character answers. A decorative-praise scene satisfies that exactly as
a consequential one does. This gate adds the missing question -- did the reply
change what the decider will do -- by requiring a recorded decision, not by
counting names or words.

exchange = {"decider": name, "before": str, "after": str, "evidence_line": str}
PASS needs: the decider is a declared character who answers an opposing speaker,
``before`` and ``after`` are both stated and differ, and ``evidence_line`` is a
verbatim line the decider speaks in the sheet.

# ponytail: the record is author-declared and checked for grounding (verbatim
# line, answering turn, a real before/after difference), not understood. A
# semantic reviewer (dossier P03/P04) still owns "is this change real"; wire it
# in at ``_changed`` when that authority exists.
"""
from __future__ import annotations

import os
import sys

_CORE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _CORE not in sys.path:
    sys.path.insert(0, _CORE)

from character_bible import character_bible as CB  # noqa: E402

CODE_NO_DECISION = "EXCHANGE_NO_DECISION_RECORD"
CODE_UNCHANGED = "EXCHANGE_DECISION_UNCHANGED"
CODE_DECIDER = "EXCHANGE_DECIDER_NOT_ANSWERING"
CODE_EVIDENCE = "EXCHANGE_EVIDENCE_NOT_SPOKEN"


def _words(s):
    return " ".join(str(s or "").lower().split())


def _changed(before, after):
    return _words(before) != _words(after)


def exchange_reasons(cast, sheet_text, exchange):
    """[] = the exchange changed a decision. Each reason names the decision."""
    ex = exchange if isinstance(exchange, dict) else {}
    who, before, after, line = (ex.get(k) for k in
                                ("decider", "before", "after", "evidence_line"))
    if not all(_words(v) for v in (who, before, after, line)):
        return ["%s: no decider/before/after/evidence_line is recorded; two names "
                "or enough words are not a decision" % CODE_NO_DECISION]
    if not _changed(before, after):
        return ["%s: %s's decision is unchanged (%r -> %r); the exchange is "
                "decorative" % (CODE_UNCHANGED, who, before, after)]
    turns = CB.speaker_turns(sheet_text)
    opp = [c["name"] for c in CB.resolve_cast(cast)["characters"]
           if c["role"] in CB.OPPOSING_ROLES]
    norm = CB._norm_name
    for i, t in enumerate(turns):
        if norm(t["speaker"]) != norm(who):
            continue
        if not any(norm(p["speaker"]) in {norm(o) for o in opp} for p in turns[:i]):
            continue
        if any(_words(line) == _words(ln) for ln in t["lines"]):
            return []
    if not any(norm(t["speaker"]) == norm(who) for t in turns):
        return ["%s: %s never answers an opposing speaker in the sheet"
                % (CODE_DECIDER, who)]
    return ["%s: %r is not a line %s speaks in answer to the opposing voice; "
            "the recorded change %r -> %r is ungrounded"
            % (CODE_EVIDENCE, line, who, before, after)]


def check_exchange(cast, sheet_text, exchange):
    reasons = exchange_reasons(cast, sheet_text, exchange)
    return {"verdict": "PASS" if not reasons else "FAIL",
            "reason_code": reasons[0].split(":")[0] if reasons else "DECISION_CHANGED",
            "reasons": reasons, "detail": "; ".join(reasons) or "decision changed"}
