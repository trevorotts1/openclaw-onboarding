#!/usr/bin/env python3
"""emergency_owner.py: the per-install EMERGENCY OWNER binding.

RECONCILED add/add (S75-T13 + S75-T27 both authored this path). One file, two
callers, one doctrine. Boss rule 2026-10-26 (D-9/D-10), quoted: "the emergency
owner is a per-install value, not a hard-coded name. On Trevor's operator box it
defaults to Trevor. On client installs it binds to that client's own on-call
operator from their config, and is never Trevor and never invented." Absent
client config => fail closed (refuse), never default, never invent.

TWO APIS OVER ONE PRECEDENCE CHAIN (the reconciliation, so neither unit's
callers or tests are rewritten):

    resolve()                  receipt shape -- outcome/owner/source/
                               reason_code/blocked/detail. S75-T13's factory
                               `owner` command and S75-T13's tests call this.
    resolve_emergency_owner()  binding shape -- state/name/code/install_kind/
                               searched, or raises EmergencyOwnerError.
                               S75-T27's callers and tests call this.

PRECEDENCE (highest first), every source already exists on the box -- this adds
no config root and no new file:

    1. OPENCLAW_EMERGENCY_OWNER      explicit per-install pin (blank is no pin)
    2. onCallOperator                this install's onboarding-identity.json
                                     (the ONE key this module adds); a value
                                     present but malformed is REFUSED, never
                                     defaulted over
    3. ownerName                     onboarding-identity.json, the identity the
                                     installer itself collects
    4. openclaw.json                 meta.ownerName, owner.name,
                                     wizard.ownerName, meta.owner.name,
                                     owner.firstName -- the installer's order
    5. operator-box default          "Trevor", ONLY on an install that proved it
                                     is the operator box
    6. else                          REFUSED (EMERGENCY_OWNER_UNCONFIGURED)

OPERATOR-BOX SIGNALS (any one, all pre-existing in the fleet):

    env IS_OPERATOR_BOX / OPERATOR_BOX / CC_OPERATOR_IS_OWNER  (truthy)
    <root>/.operator-is-owner                                  (file exists)
    <root>/secrets/.env  OPERATOR_BOX=1 or IS_OPERATOR_BOX=1

AN ABSENT MARKER IS NEVER AN OPERATOR BOX. A client config that literally names
the operator default is refused (EMERGENCY_OWNER_TREVOR_ON_CLIENT) rather than
handing a client install the operator's name.

No network, no provider call, no spend, stdlib only. The only writer here is
`record_refusal`, and it writes a refusal and nothing else.

Run: python3 -I emergency_owner.py resolve [--root DIR] [--record PATH]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone

SCHEMA_VERSION = "blackceo.emergency-owner/v1"

# ── the install's own config, and the one key this module adds ────────────────
IDENTITY_FILE = "onboarding-identity.json"
IDENTITY_KEY = "ownerName"
CONFIG_FILE = "openclaw.json"
CONFIG_NAME_PATHS = (("meta", "ownerName"), ("owner", "name"),
                     ("wizard", "ownerName"), ("meta", "owner", "name"),
                     ("owner", "firstName"))
CONFIG_KEY = "onCallOperator"
ENV_PIN = "OPENCLAW_EMERGENCY_OWNER"

# ── operator-box signals ─────────────────────────────────────────────────────
OPERATOR_MARKERS = ("IS_OPERATOR_BOX", "OPERATOR_BOX")
OPERATOR_MARKER = ".operator-is-owner"
OPERATOR_ENV = "CC_OPERATOR_IS_OWNER"
SECRETS_ENV = os.path.join("secrets", ".env")
_TRUTHY = ("1", "true", "yes", "on")

#: A default is only ever handed to an install that already proved it is the
#: operator box; see ``install_kind``.
OPERATOR_DEFAULT = "Trevor"
OPERATOR_DEFAULT_NAME = OPERATOR_DEFAULT
MAX_NAME = 200

STATE_BOUND = "bound"
STATE_REFUSED = "refused"

# ── refusal codes (never a status string; outcome/state is reported apart) ────
CODE_FROM_CONFIG = "EMERGENCY_OWNER_FROM_INSTALL_CONFIG"
CODE_OPERATOR_DEFAULT = "EMERGENCY_OWNER_OPERATOR_BOX_DEFAULT"
CODE_UNCONFIGURED = "EMERGENCY_OWNER_UNCONFIGURED"
CODE_INVALID = "EMERGENCY_OWNER_INVALID"
CODE_CONFIG_INVALID = "EMERGENCY_OWNER_CONFIG_INVALID"
EMERGENCY_OWNER_UNCONFIGURED = CODE_UNCONFIGURED
EMERGENCY_OWNER_INVALID = CODE_INVALID
EMERGENCY_OWNER_TREVOR_ON_CLIENT = "EMERGENCY_OWNER_TREVOR_ON_CLIENT"


class EmergencyOwnerError(Exception):
    """A refusal with a stable code the caller reports verbatim."""

    def __init__(self, code, message, record=None):
        super().__init__("%s: %s" % (code, message))
        self.code = code
        self.record = record or {}


# ── small helpers ────────────────────────────────────────────────────────────

def _truthy(value):
    return isinstance(value, str) and value.strip().lower() in _TRUTHY


def _clean_name(value):
    """A configured name, or '' when it is not one. Never invented, never cut."""
    if not isinstance(value, str):
        return ""
    value = value.strip()
    if not value or len(value) > MAX_NAME or any(ord(c) < 32 for c in value):
        return ""
    return value


def _strict_name(value):
    """(name, problem) -- a malformed recorded value is a refusal."""
    if not isinstance(value, str):
        return "", "the recorded value is %s, not a string" % type(value).__name__
    name = value.strip()
    if not name:
        return "", "the recorded value is blank"
    if len(name) > MAX_NAME or any(ord(c) < 32 for c in name):
        return "", ("the recorded value must be one line of at most %d "
                    "characters" % MAX_NAME)
    return name, None


def _read_json(path):
    """Tolerant read: anything unreadable is simply not a source."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


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


def _secrets_marker(root):
    """OPERATOR_BOX=1 from the install's own secrets env file.

    Read, never printed: the file also holds credentials, so only the marker's
    presence is returned as a boolean.
    """
    path = os.path.join(root, SECRETS_ENV)
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.read().splitlines()
    except OSError:
        return False
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):].strip()
        name, _, value = line.partition("=")
        if name.strip() in OPERATOR_MARKERS and _truthy(value.strip().strip("\"'")):
            return True
    return False


def _openclaw_name(root):
    """(name, source) from openclaw.json, in the installer's own key order."""
    config = _read_json(os.path.join(root, CONFIG_FILE))
    if not isinstance(config, dict):
        return "", ""
    for path in CONFIG_NAME_PATHS:
        cur = config
        for key in path:
            cur = cur.get(key) if isinstance(cur, dict) else None
        name = _clean_name(cur)
        if name:
            return name, CONFIG_FILE + ":" + ".".join(path)
    return "", ""


def _searched(root):
    return [os.path.join(root, IDENTITY_FILE),
            os.path.join(root, CONFIG_FILE),
            os.path.join(root, SECRETS_ENV),
            "env:" + ENV_PIN]


# ── install identity ─────────────────────────────────────────────────────────

def config_root(explicit=None, env=None):
    """The install's own config root: explicit, then the installers' own vars."""
    if explicit:
        return os.path.expanduser(explicit)
    env = os.environ if env is None else env
    for key in ("OPENCLAW_HOME", "OPENCLAW_ROOT", "OC_ROOT", "OC_CONFIG"):
        value = (env.get(key) or "").strip()
        if value:
            return os.path.expanduser(value)
    # ponytail: one home default. A VPS that keeps its install at /data sets
    # OPENCLAW_ROOT (platform/common.sh does exactly that), so no second probe.
    return os.path.join(os.path.expanduser("~"), ".openclaw")


def default_home():
    """The install's existing config root (never a new one)."""
    return config_root()


def install_kind(root=None, env=None):
    """'operator' or 'client'. AN ABSENT MARKER IS NEVER AN OPERATOR BOX."""
    env = os.environ if env is None else env
    root = root or config_root(env=env)
    for key in OPERATOR_MARKERS:
        if _truthy(env.get(key)):
            return "operator"
    if _truthy(env.get(OPERATOR_ENV)):
        return "operator"
    if os.path.isfile(os.path.join(root, OPERATOR_MARKER)):
        return "operator"
    if _secrets_marker(root):
        return "operator"
    return "client"


def is_operator_box(home=None, env=None):
    """True only on the operator's own machine (see the marker list above)."""
    return install_kind(home, env=env) == "operator"


# ── the one precedence chain both APIs sit on ────────────────────────────────

def _first_configured(root, env=None):
    """(name, source, problem) over the whole precedence chain.

    ``problem`` is set only for a value that is PRESENT and malformed: that is
    a refusal on every box, never a reason to fall through to the default.
    Malformed values in the tolerant sources (ownerName, openclaw.json) are
    simply not a source, matching the installer's own reading of them.
    """
    env = os.environ if env is None else env

    pinned = _clean_name(env.get(ENV_PIN))
    if pinned:
        return pinned, "env:" + ENV_PIN, None

    identity = _read_json(os.path.join(root, IDENTITY_FILE))
    if isinstance(identity, dict) and CONFIG_KEY in identity:
        name, problem = _strict_name(identity.get(CONFIG_KEY))
        if problem:
            return "", "", "%s in %s: %s" % (CONFIG_KEY, IDENTITY_FILE, problem)
        return name, IDENTITY_FILE + ":" + CONFIG_KEY, None

    if isinstance(identity, dict):
        name = _clean_name(identity.get(IDENTITY_KEY))
        if name:
            return name, IDENTITY_FILE + ":" + IDENTITY_KEY, None

    name, source = _openclaw_name(root)
    if name:
        return name, source, None
    return "", "", None


def configured_owner(root=None, env=None):
    """(name, source) from the install config, or ('', '') when unconfigured."""
    root = root or config_root(env=env)
    name, source, _problem = _first_configured(root, env=env)
    return (name, source) if name else ("", "")


# ── API 1 (S75-T27): the binding, or a raised refusal ────────────────────────

def _refusal(root, kind, code, reason):
    return {
        "schema_version": SCHEMA_VERSION,
        "state": STATE_REFUSED,
        "name": None,
        "code": code,
        "reason": reason,
        "install_kind": kind,
        "root": root,
        "searched": _searched(root),
        "defaulted": False,
        "invented": False,
    }


def resolve_emergency_owner(root=None, env=None):
    """The binding for this install. Raises EmergencyOwnerError when refused.

    The bound result is handoff-ready and deterministic: the same config and
    environment always produce the same record.
    """
    env = os.environ if env is None else env
    root = root or config_root(env=env)
    kind = install_kind(root, env=env)

    name, source, problem = _first_configured(root, env=env)
    if problem:
        record = _refusal(root, kind, CODE_INVALID,
                          "install config records a malformed value (%s); "
                          "refusing to proceed with a broken owner record"
                          % problem)
        raise EmergencyOwnerError(CODE_INVALID, record["reason"], record)

    if name and kind == "client" and name.casefold() == \
            OPERATOR_DEFAULT_NAME.casefold():
        record = _refusal(
            root, kind, EMERGENCY_OWNER_TREVOR_ON_CLIENT,
            "client install config names the operator-box owner; a client "
            "install never binds to %s" % OPERATOR_DEFAULT_NAME)
        record["configured_source"] = source
        raise EmergencyOwnerError(EMERGENCY_OWNER_TREVOR_ON_CLIENT,
                                  record["reason"], record)

    if name:
        return {
            "schema_version": SCHEMA_VERSION,
            "state": STATE_BOUND,
            "name": name,
            "code": None,
            "reason": "configured on this install",
            "install_kind": kind,
            "source": source,
            "root": root,
            "searched": _searched(root),
            "defaulted": False,
            "invented": False,
        }

    if kind == "operator":
        return {
            "schema_version": SCHEMA_VERSION,
            "state": STATE_BOUND,
            "name": OPERATOR_DEFAULT_NAME,
            "code": None,
            "reason": "OPERATOR box with no configured value; operator default",
            "install_kind": kind,
            "source": "operator-default",
            "root": root,
            "searched": _searched(root),
            "defaulted": True,
            "invented": False,
        }

    record = _refusal(
        root, kind, EMERGENCY_OWNER_UNCONFIGURED,
        "client install has no configured on-call operator; refusing instead "
        "of defaulting to %s or inventing a name" % OPERATOR_DEFAULT_NAME)
    raise EmergencyOwnerError(EMERGENCY_OWNER_UNCONFIGURED, record["reason"],
                              record)


def record_refusal(path, record):
    """Write a refusal record. Never called on a bound result."""
    if not isinstance(record, dict) or record.get("state") != STATE_REFUSED:
        raise ValueError("record_refusal: not a refusal record")
    parent = os.path.dirname(os.path.abspath(path))
    if parent and not os.path.isdir(parent):
        os.makedirs(parent)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(record, f, indent=2, sort_keys=True)
        f.write("\n")
    return path


# ── API 2 (S75-T13): the receipt, never raises ──────────────────────────────

def _receipt(home, path, operator):
    return {"schema_version": SCHEMA_VERSION, "install_home": home,
            "config_path": path, "operator_box": operator,
            "owner": None, "source": None, "blocked": False,
            "outcome": "refused", "reason_code": CODE_UNCONFIGURED,
            "detail": ""}


def resolve(install_home=None, config_path=None):
    """Resolve this install's emergency owner. Returns a receipt dict:

        outcome       "ok" or "refused"
        owner         the resolved name, or None on a refusal
        source        "install_config" / "install_pin" / "operator_box_default"
        reason_code   one of the CODE_* constants
        blocked       True on a refusal (callers must not proceed)
        detail        plain-language reason
        install_home, config_path, operator_box   the exact inputs read
    """
    home = os.path.abspath(os.path.expanduser(install_home or default_home()))
    path = os.path.abspath(os.path.expanduser(config_path)) if config_path \
        else os.path.join(home, IDENTITY_FILE)
    operator = is_operator_box(home)
    receipt = _receipt(home, path, operator)

    pinned = _clean_name(os.environ.get(ENV_PIN))
    if pinned:
        receipt.update(outcome="ok", owner=pinned, source="install_pin",
                       reason_code=CODE_FROM_CONFIG,
                       detail="%s pinned for this install" % ENV_PIN)
        return receipt

    doc, problem = _read_config(path)
    if problem:
        receipt.update(reason_code=CODE_CONFIG_INVALID, blocked=True,
                       detail="install config is unreadable (%s); refusing to "
                              "guess an emergency owner" % problem)
        return receipt

    if CONFIG_KEY in doc:
        name, bad = _strict_name(doc[CONFIG_KEY])
        if bad:
            receipt.update(reason_code=CODE_INVALID, blocked=True,
                           detail="install config records %s; refusing to "
                                  "proceed with a broken owner record" % bad)
            return receipt
        receipt.update(outcome="ok", owner=name, source="install_config",
                       reason_code=CODE_FROM_CONFIG,
                       detail="%s recorded in this install's config" % CONFIG_KEY)
        return receipt

    if isinstance(doc.get(IDENTITY_KEY), str):
        name = _clean_name(doc.get(IDENTITY_KEY))
        if name:
            receipt.update(outcome="ok", owner=name, source="install_config",
                           reason_code=CODE_FROM_CONFIG,
                           detail="installer-collected %s in this install's "
                                  "config" % IDENTITY_KEY)
            return receipt

    name, _source = _openclaw_name(home)
    if name:
        receipt.update(outcome="ok", owner=name, source="install_config",
                       reason_code=CODE_FROM_CONFIG,
                       detail="%s recorded in this install's %s"
                              % (IDENTITY_KEY, CONFIG_FILE))
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


# ── CLI ─────────────────────────────────────────────────────────────────────

def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="action", required=True)
    r = sub.add_parser("resolve", help="resolve this install's emergency owner")
    r.add_argument("--root", default=None, help="install config root")
    r.add_argument("--record", default=None,
                   help="write the refusal record here when the install refuses")
    ns = ap.parse_args(argv)
    if ns.action != "resolve":  # pragma: no cover - argparse rejects others
        return 2
    try:
        binding = resolve_emergency_owner(ns.root)
    except EmergencyOwnerError as e:
        if ns.record:
            record_refusal(ns.record, e.record)
        print(json.dumps(e.record, indent=1, sort_keys=True), file=sys.stderr)
        return 2
    print(json.dumps(binding, indent=1, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
