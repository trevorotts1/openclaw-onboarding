#!/usr/bin/env python3
"""answer_duty.py - Skill 38 reads the `- duty:` a handoff carries and decides
which outbound channel may answer it.

WHY (T-26 clause (d), "distinct public/private duty"): Skill 35's comment reader
stamps every synthetic handoff with `- duty: public_answer`. That stamp is only a
capability if the OWNER of the reply - this skill - reads it and refuses what the
duty forbids. Nothing here is a label: the two duties are two different
permissions, and the difference is observable at the send boundary.

  public_answer   the answer belongs in the PUBLIC COMMENT THREAD. A DM or an
                  SMS is refused - that is the unsolicited private send the
                  clause exists to prevent.
  private_answer  opened by a real GHL Conversations inbound event; the DM is the
                  expected channel. The public thread is not.

An absent, unrecognised or typo'd duty fails CLOSED: no channel is allowed. A
turn whose duty cannot be read is never treated as permissive.

Python 3 standard library only. Assert-based self-check:
    python3 -I answer_duty.py
"""
from __future__ import annotations

import re

PUBLIC_ANSWER_DUTY = "public_answer"
PRIVATE_ANSWER_DUTY = "private_answer"

CHANNEL_PUBLIC_COMMENT = "public_comment"
CHANNEL_DM = "dm"
CHANNEL_SMS = "sms"

# duty -> the channels that may answer it. Anything not listed here is refused.
ALLOWED_CHANNELS = {
    PUBLIC_ANSWER_DUTY: frozenset({CHANNEL_PUBLIC_COMMENT}),
    PRIVATE_ANSWER_DUTY: frozenset({CHANNEL_DM}),
}

# `- duty: <token>` on its own line. Deliberately unanchored at the end so a
# trailing annotation (the pre-T-26 line carried a parenthetical) still parses.
_DUTY_LINE_RE = re.compile(r"^[ \t]*- duty:[ \t]*([A-Za-z0-9_.-]+)", re.MULTILINE)


def duty_from_log_text(text) -> str | None:
    """The duty of the LAST turn in a conversational log, or None.

    A log is append-only, so the last `- duty:` line is the current turn's.
    Returns None when no turn carries a duty - the caller must fail closed.
    """
    found = _DUTY_LINE_RE.findall(text or "")
    return found[-1] if found else None


def outbound_channel_allowed(duty, channel) -> bool:
    """May a turn carrying `duty` be answered on `channel`?

    Unknown/absent duty -> False (fail closed). Unknown channel -> False.
    """
    token = (duty or "").strip()
    return str(channel or "").strip() in ALLOWED_CHANNELS.get(token, frozenset())


# ── assert-based self-check (stdlib only) ───────────────────────────────────

def _selfcheck() -> int:
    checks = 0

    def ok(cond: bool, label: str) -> None:
        nonlocal checks
        if not cond:
            raise AssertionError("FAIL: " + label)
        checks += 1

    log = (
        "# Conversation log - author_555\n"
        "### Inbound - public comment (facebook) - t1\n"
        "- duty: public_answer\n"
        "- text: how do I book?\n"
    )
    ok(duty_from_log_text(log) == PUBLIC_ANSWER_DUTY, "reads the stamped duty")
    ok(duty_from_log_text("- duty: public_answer (answer publicly)\n")
       == PUBLIC_ANSWER_DUTY, "tolerates a trailing annotation")
    ok(duty_from_log_text("- text: no duty here\n") is None, "no duty -> None")
    ok(outbound_channel_allowed(duty_from_log_text(log), CHANNEL_PUBLIC_COMMENT),
       "public duty may be answered publicly")
    ok(not outbound_channel_allowed(duty_from_log_text(log), CHANNEL_DM),
       "public duty may not be answered in DM")
    ok(not outbound_channel_allowed(duty_from_log_text(log), CHANNEL_SMS),
       "public duty may not be answered by SMS")
    ok(outbound_channel_allowed(PRIVATE_ANSWER_DUTY, CHANNEL_DM),
       "private duty may be answered in DM")
    ok(not outbound_channel_allowed(PRIVATE_ANSWER_DUTY, CHANNEL_PUBLIC_COMMENT),
       "private duty is not a public-thread answer")
    ok(not outbound_channel_allowed("zzz-not-a-duty", CHANNEL_PUBLIC_COMMENT),
       "unknown duty fails closed")
    ok(not outbound_channel_allowed(None, CHANNEL_PUBLIC_COMMENT),
       "absent duty fails closed")

    # The last turn wins: an earlier public turn must not license a later one.
    two_turns = ("- duty: private_answer\n- text: a\n"
                 "- duty: public_answer\n- text: b\n")
    ok(duty_from_log_text(two_turns) == PUBLIC_ANSWER_DUTY, "last turn wins")

    print(f"OK {checks} PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(_selfcheck())
