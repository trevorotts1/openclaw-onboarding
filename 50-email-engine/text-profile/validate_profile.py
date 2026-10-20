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
# USAGE:  python3 validate_profile.py            (exit 0 = pass)
# =============================================================================
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


def main():
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
