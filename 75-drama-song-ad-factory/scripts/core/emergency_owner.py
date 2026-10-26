#!/usr/bin/env python3
"""emergency_owner.py: the per-install EMERGENCY OWNER binding (S75-T13 / S75-A13).

Boss rule 2026-10-26 (D-9/D-10 answer, quoted): "the emergency owner is a
per-install value, not a hard-coded name. On Trevor's operator box it defaults
to Trevor. On client installs it binds to that client's own on-call operator
from their config, and is never Trevor and never invented." Absent client
config => fail closed (refuse), never default, never invent.

Install config discovery -- the installer's own mechanism, reused, not a second
config root:

    home      $OPENCLAW_HOME, else ~/.openclaw
    config    <home>/onboarding-identity.json   (written by scripts/onboarding-identity.py)
    key       onCallOperator                     (the ONE named key this adds)
    operator  <home>/.operator-is-owner marker, or CC_OPERATOR_IS_OWNER=1

Resolution order:

    1. onCallOperator recorded       -> that value, on any box
    2. no value + operator-box install -> "Trevor" (source operator_box_default)
    3. no value + client install     -> REFUSED, EMERGENCY_OWNER_UNCONFIGURED

A value that is present but malformed (not a string, blank, over 200 characters,
control characters) and an unreadable config are REFUSED on every box: a
handoff gate never guesses and never defaults over a broken record.

No network, no spend, stdlib only.
"""
import json
import os
import time
from datetime import datetime, timezone

SCHEMA_VERSION = "blackceo.emergency-owner/v1"
CONFIG_KEY = "onCallOperator"
IDENTITY_FILE = "onboarding-identity.json"
OPERATOR_MARKER = ".operator-is-owner"
OPERATOR_ENV = "CC_OPERATOR_IS_OWNER"
OPERATOR_DEFAULT = "Trevor"
MAX_NAME = 200

#: reason codes (never a status string; the outcome is ok/refused separately).
CODE_FROM_CONFIG = "EMERGENCY_OWNER_FROM_INSTALL_CONFIG"
CODE_OPERATOR_DEFAULT = "EMERGENCY_OWNER_OPERATOR_BOX_DEFAULT"
CODE_UNCONFIGURED = "EMERGENCY_OWNER_UNCONFIGURED"
CODE_INVALID = "EMERGENCY_OWNER_INVALID"
CODE_CONFIG_INVALID = "EMERGENCY_OWNER_CONFIG_INVALID"


def default_home():
    """The install's existing config root (never a new one)."""
    return os.environ.get("OPENCLAW_HOME") or os.path.expanduser("~/.openclaw")


def is_operator_box(home):
    """True only on the operator's own machine: the durable marker, or the env
    var that the marker was created to replace. The marker's own text says it
    must never exist on a client box."""
    if os.path.isfile(os.path.join(home, OPERATOR_MARKER)):
        return True
    return str(os.environ.get(OPERATOR_ENV) or "").strip().lower() in (
        "1", "true", "yes")


def _read_config(path):
    """(doc, problem). No file == no configured value, not an error."""
    try:
        with open(path, encoding="utf-8") as f:
            doc = json.load(f)
    except FileNotFoundError:
        return {}, None
    except (OSError, ValueError) as e:
        return None, "%s: %s" % (type(e).__name__, str(e)[:200])
    if not isinstance(doc, dict):
        return None, "expected a JSON object, got %s" % type(doc).__name__
    return doc, None


def _name(value):
    """(name, problem). A malformed recorded value is a refusal, never a default."""
    if not isinstance(value, str):
        return "", "onCallOperator is %s, not a string" % type(value).__name__
    name = value.strip()
    if not name:
        return "", "onCallOperator is blank"
    if len(name) > MAX_NAME or any(ord(c) < 32 for c in name):
        return "", "onCallOperator must be one line of at most %d characters" % MAX_NAME
    return name, None


def resolve(install_home=None, config_path=None):
    """Resolve this install's emergency owner. Returns a receipt dict:

        outcome       "ok" or "refused"
        owner         the resolved name, or None on a refusal
        source        "install_config" / "operator_box_default" / None
        reason_code   one of the CODE_* constants
        blocked       True on a refusal (callers must not proceed)
        detail        plain-language reason
        install_home, config_path, operator_box   the exact inputs read
    """
    home = os.path.abspath(os.path.expanduser(install_home or default_home()))
    path = os.path.abspath(os.path.expanduser(config_path)) if config_path \
        else os.path.join(home, IDENTITY_FILE)
    operator = is_operator_box(home)
    receipt = {"schema_version": SCHEMA_VERSION, "install_home": home,
               "config_path": path, "operator_box": operator,
               "owner": None, "source": None, "blocked": False,
               "outcome": "refused", "reason_code": CODE_UNCONFIGURED,
               "detail": ""}
    doc, problem = _read_config(path)
    if problem:
        receipt.update(reason_code=CODE_CONFIG_INVALID, blocked=True,
                       detail="install config is unreadable (%s); refusing to "
                              "guess an emergency owner" % problem)
        return receipt
    if CONFIG_KEY in doc:
        name, bad = _name(doc[CONFIG_KEY])
        if bad:
            receipt.update(reason_code=CODE_INVALID, blocked=True,
                           detail="install config records %s; refusing to "
                                  "proceed with a broken owner record" % bad)
            return receipt
        receipt.update(outcome="ok", owner=name, source="install_config",
                       reason_code=CODE_FROM_CONFIG,
                       detail="onCallOperator recorded in this install's config")
        return receipt
    if operator:
        receipt.update(outcome="ok", owner=OPERATOR_DEFAULT,
                       source="operator_box_default",
                       reason_code=CODE_OPERATOR_DEFAULT,
                       detail="operator-box install with no configured value "
                              "defaults to %s" % OPERATOR_DEFAULT)
        return receipt
    receipt.update(blocked=True, reason_code=CODE_UNCONFIGURED,
                   detail="client install with no on-call operator recorded; "
                          "refusing to proceed (never defaults to %s and never "
                          "invents a name)" % OPERATOR_DEFAULT)
    return receipt


def refusal_record(receipt, at=None):
    """The durable refusal, written only when resolution refused."""
    rec = dict(receipt)
    rec.update(outcome="refused", blocked=True, owner=None,
               recorded_at=at or datetime.now(timezone.utc).isoformat(),
               recorded_unix=int(time.time()))
    return rec


if __name__ == "__main__":
    import sys
    result = resolve()
    json.dump(result, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    sys.exit(0 if result["outcome"] == "ok" else 4)
