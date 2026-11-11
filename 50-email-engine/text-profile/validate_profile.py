#!/usr/bin/env python3
# =============================================================================
# 50-email-engine/text-profile/validate_profile.py
# -----------------------------------------------------------------------------
# Fail-closed self-check for the launch-text copy profile. Stdlib only.
# Proves the profile itself keeps the rules the spec sets (3.2):
#   * every text point is classified promotional or operational;
#   * required endings are reply invitation + literal STOP;
#   * send window is 08:00-21:00 recipient local;
#   * promotional cap is 3-5 and the point catalog does not exceed it;
#   * every example carries a reply invitation and STOP, <= max chars, <= 1 link;
#   * draft_only / a2p gate / no-send posture is declared.
#
# It also judges the per-set SMS copy Skill 50 hands to Skill 44 (issue 3):
#   * check_message / check_sms_set hold every approved body to the same rules;
#   * `python3 validate_profile.py --check-sms working/text/<set_id>.sms.json`.
#
# USAGE:  python3 validate_profile.py            (exit 0 = pass)
# =============================================================================
import hashlib
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PROFILE = os.path.join(HERE, "launch-text.profile.json")
LINK = re.compile(r"\{(?:link|url)\}|https?://\S+")
REPLY = re.compile(r"\breply\b", re.IGNORECASE)


def check(profile):
    fails = []
    rules = profile.get("rules", {})

    if rules.get("kind") != "text-profile":
        fails.append("rules.kind must be text-profile")
    if rules.get("draft_only") is not True or rules.get("never_sends") is not True:
        fails.append("profile must be draft_only and never_sends")
    if rules.get("a2p_required") is not True or not rules.get("a2p_gate"):
        fails.append("a2p_required + a2p_gate required")

    endings = rules.get("required_endings") or []
    for need in ("reply_invitation", "opt_out_stop"):
        if need not in endings:
            fails.append("required_endings missing %s" % need)
    if rules.get("opt_out_keyword") != "STOP":
        fails.append("opt_out_keyword must be STOP")

    window = rules.get("send_window") or {}
    if (window.get("start"), window.get("end")) != ("08:00", "21:00"):
        fails.append("send_window must be 08:00-21:00")
    if window.get("timezone") != "recipient_local":
        fails.append("send_window.timezone must be recipient_local")
    if not window.get("outside_window_policy"):
        fails.append("send_window.outside_window_policy required")

    cap = rules.get("promotional_cap_per_launch")
    if not isinstance(cap, int) or not 3 <= cap <= 5:
        fails.append("promotional_cap_per_launch must be 3-5")

    points = rules.get("points") or {}
    promo = rules.get("promotional_points") or []
    ops = rules.get("operational_points") or []
    if set(promo) & set(ops):
        fails.append("a point cannot be both promotional and operational")
    if set(promo) | set(ops) != set(points):
        fails.append("points and promotional/operational lists must match")
    if len(promo) > cap:
        fails.append("promotional points exceed the cap")
    for pid, p in points.items():
        if p.get("kind") not in ("promotional", "operational"):
            fails.append("%s: kind must be promotional or operational" % pid)
        if not p.get("voice_intent"):
            fails.append("%s: voice_intent required" % pid)
        if (pid in promo) != (p.get("kind") == "promotional"):
            fails.append("%s: kind disagrees with the point list" % pid)

    max_chars = rules.get("max_characters")
    if not isinstance(max_chars, int) or max_chars <= 0:
        fails.append("max_characters required")
    for i, ex in enumerate(profile.get("examples") or []):
        text = ex.get("text", "")
        label = "example[%d] (%s)" % (i, ex.get("point"))
        if ex.get("point") not in points:
            fails.append("%s: unknown point" % label)
        if not REPLY.search(text):
            fails.append("%s: no reply invitation" % label)
        if "STOP" not in text:
            fails.append("%s: no literal STOP" % label)
        if len(text) > max_chars:
            fails.append("%s: %d chars > %d" % (label, len(text), max_chars))
        if len(LINK.findall(text)) > 1:
            fails.append("%s: more than one link" % label)
        if "unsubscribe" in text.lower():
            fails.append("%s: use STOP, not unsubscribe" % label)
    return fails


CATEGORIES = ("marketing", "operational")


def profile_sha256(path=PROFILE):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def check_message(body, category, rules):
    """Why one approved SMS body breaks the profile's copy contract (empty list = it holds)."""
    fails = []
    if not isinstance(body, str) or not body.strip():
        return ["body is empty"]
    if category not in CATEGORIES:
        fails.append("category %r is not marketing|operational" % (category,))
    if not REPLY.search(body):
        fails.append("no reply invitation")
    if "STOP" not in body:
        fails.append("no literal STOP")
    if len(body) > rules.get("max_characters", 320):
        fails.append("%d chars > %d" % (len(body), rules.get("max_characters", 320)))
    if len(LINK.findall(body)) > rules.get("max_links", 1):
        fails.append("more than one link")
    if "unsubscribe" in body.lower():
        fails.append("use STOP, not unsubscribe")
    return fails


def check_sms_set(doc, profile=None, path=PROFILE):
    """Failures for a working/text/<set_id>.sms.json document (empty list = valid)."""
    if profile is None:
        with open(path, encoding="utf-8") as f:
            profile = json.load(f)
    rules = profile.get("rules", {})
    if not isinstance(doc, dict):
        return ["sms set is not a JSON object"]
    fails = []
    if not (isinstance(doc.get("set_id"), str) and doc["set_id"].strip()):
        fails.append("set_id required")
    if doc.get("profile_sha256") != profile_sha256(path):
        fails.append("profile_sha256 is not the sha256 of launch-text.profile.json")
    messages = doc.get("messages")
    if not isinstance(messages, list) or not messages:
        return fails + ["messages must be a non-empty list"]
    seen = set()
    for i, m in enumerate(messages):
        label = "messages[%d]" % i
        if not isinstance(m, dict) or not isinstance(m.get("step_id"), str) or not m["step_id"].strip():
            fails.append("%s: step_id required" % label)
            continue
        if m["step_id"] in seen:
            fails.append("%s: step_id %r repeated" % (label, m["step_id"]))
        seen.add(m["step_id"])
        fails += ["%s: %s" % (label, f) for f in check_message(m.get("body"), m.get("category"), rules)]
    return fails


def main():
    if len(sys.argv) == 3 and sys.argv[1] == "--check-sms":
        try:
            with open(sys.argv[2], encoding="utf-8") as f:
                doc = json.load(f)
        except (OSError, ValueError) as exc:
            print("FAIL: %s unreadable: %s" % (sys.argv[2], exc))
            return 1
        fails = check_sms_set(doc)
        for f in fails:
            print("FAIL: %s" % f)
        if not fails:
            print("PASS: %s honours the launch-text profile" % sys.argv[2])
        return 1 if fails else 0
    if not os.path.isfile(PROFILE):
        print("FAIL: %s not found" % PROFILE)
        return 1
    with open(PROFILE, encoding="utf-8") as f:
        profile = json.load(f)
    fails = check(profile)
    if fails:
        for f in fails:
            print("FAIL: %s" % f)
        return 1
    print("PASS: launch-text profile honours reply+STOP, 08:00-21:00 local, promo cap %d"
          % profile["rules"]["promotional_cap_per_launch"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
