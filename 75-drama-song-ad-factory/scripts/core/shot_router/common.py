"""Shared types, constants and small helpers for the Shot Router. Stdlib only.

The Shot Router gives every storyboard shot one route and an exact picture
list (section 3E), and its Clip Sizer chooses each clip's length (section 3I).
Nothing in this package reaches the network, spends credits or writes outside
the paths its callers hand it.
"""
from __future__ import annotations

SCHEMA_VERSION = "1.0.0"
TOOL_VERSION = "1.0.0"


class ShotRouterError(Exception):
    """A refusal carries a machine code and a human message.

    Codes are the plan's own (SHOT_OFF_BEAT, PRICE_MISSING,
    PROVIDER_CANNOT_HOLD_CHARACTER and the rest); callers branch on .code,
    never on the message text.
    """

    def __init__(self, code, message):
        super().__init__("%s: %s" % (code, message))
        self.code = code
        self.message = message


def is_num(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def as_number(value, name, code="VALUE_INVALID"):
    if not is_num(value):
        raise ShotRouterError(code, "%s must be a number, got %r" % (name, value))
    return float(value)


def as_int(value, name, code="VALUE_INVALID"):
    if not isinstance(value, int) or isinstance(value, bool):
        raise ShotRouterError(code, "%s must be an integer, got %r" % (name, value))
    return value


def ceil_seconds(value):
    """Whole seconds, rounded up: OmniHuman bills by whole seconds."""
    n = int(value)
    return n if n == value else n + 1


def clamp(value, low, high):
    return max(low, min(high, value))
