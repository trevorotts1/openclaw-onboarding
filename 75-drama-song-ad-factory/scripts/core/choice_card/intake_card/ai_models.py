"""AI MODELS question: which AI builds the video and which AI checks the work.

OpenRouter is the recommended build route; Ollama is allowed. Free-text replies
are checked against ai_models.json; unknown names are refused politely.
Honest scope: skill 75 runs on the model the session already uses (SKILL.md, the
user's choice wins), so the answer is a recorded preference (`ai_models` in the
approved intake summary) for the operator, not a per-run model switch.
`build != check` is enforced so the checker stays independent.
"""
import json
import os
import re

with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "ai_models.json"), encoding="utf-8") as _f:
    _T = json.load(_f)
MODELS = {m["id"]: m for m in _T["models"]}
REC_BUILD, REC_CHECK = _T["recommended"]["build"], _T["recommended"]["check"]
_PAT = re.compile(r"^\s*(.+?)\s+builds?\s*[,;]?\s*(?:and\s+)?(.+?)\s+checks?\s*\.?\s*$", re.I)
_BY_NAME = {}


def _key(s):
    return re.sub(r"[^a-z0-9.]+", " ", str(s).lower()).strip()


for _m in _T["models"]:
    for _n in [_m["id"], _m["label"]] + _m["aliases"]:
        _BY_NAME[_key(_n)] = _m["id"]


def label(mid):
    return MODELS[mid]["label"]


def recommended():
    return {"build": REC_BUILD, "check": REC_CHECK, "route": MODELS[REC_BUILD]["route"]}


def recommended_text():
    return "%s builds, %s checks" % (label(REC_BUILD), label(REC_CHECK))


def check(build, checker):
    """Names or ids -> ({"build","check","route"}, None) or (None, polite refusal)."""
    ids = []
    for who, name in (("build", build), ("check", checker)):
        mid = _BY_NAME.get(_key(name))
        if not mid:
            return None, 'Sorry, I cannot use "%s" as the %s model. I can use: %s.' % (
                str(name).strip(), who, ", ".join(m["label"] for m in _T["models"]))
        ids.append(mid)
    if ids[0] == ids[1]:
        return None, "The model that checks the work must be a different model from the one that builds it."
    return {"build": ids[0], "check": ids[1], "route": MODELS[ids[0]]["route"]}, None


def parse(reply):
    """A card reply -> check()'s result. "1"/"recommended" takes the recommended setup."""
    t = (reply or "").strip()
    if t.lower() in ("recommended", "recommend", "rec", "1"):
        return recommended(), None
    m = _PAT.match(t)
    if not m:
        return None, 'Please reply 1, or name both models like "DeepSeek builds, Claude Sonnet checks".'
    return check(*m.groups())
