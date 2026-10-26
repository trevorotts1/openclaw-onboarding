#!/usr/bin/env python3
"""emergency_owner.py: the per-install emergency owner (S75-T27 / D-9 / D-10).

The emergency owner is a PER-INSTALL VALUE, never a hard-coded name:

* on the OPERATOR box (install marker ``IS_OPERATOR_BOX=1`` / ``OPERATOR_BOX=1``)
  an unconfigured install binds to the operator default, ``Trevor``;
* on a CLIENT install it binds to that client's own on-call operator, read from
  the install's own config. It is never Trevor and never invented;
* a client install with no configured on-call operator FAILS CLOSED: the
  refusal is named (``EMERGENCY_OWNER_UNCONFIGURED``) and can be recorded, and
  no name is minted. A client config that literally names Trevor is refused for
  the same reason (``EMERGENCY_OWNER_TREVOR_ON_CLIENT``).

SOURCES, in the order this module reads them -- all of them already exist in
this repository, so no new config key is introduced:

1. ``OPENCLAW_EMERGENCY_OWNER`` -- explicit per-install pin, the same shape as
   the installer's ``OPENCLAW_OWNER_CHAT_ID`` override. Optional; a pin that is
   blank is not a pin.
2. ``$ROOT/onboarding-identity.json`` ``ownerName`` -- the identity the
   installer itself collects (``scripts/onboarding-identity.py``).
3. ``$ROOT/openclaw.json`` -- the same key order the installer's
   ``resolve_owner_name`` reads: ``meta.ownerName``, ``owner.name``,
   ``wizard.ownerName``, ``meta.owner.name``, ``owner.firstName``.
4. Operator default ``Trevor`` -- OPERATOR box only.

The ready-to-handoff record (``evidence/emergency-owner-handoff.json`` in the
build authority root) names ``owner: UNKNOWN`` because no artifact on that disk
names a person. This module is how a box answers that question for itself: the
binding is resolved from THIS install's config, and an unresolvable install
refuses instead of guessing. The name is kept verbatim as configured (stripped,
single line, at most 200 characters), never truncated to a first token.

Stdlib only, no network, no provider call, no spend. Nothing here writes on the
bound path; ``record_refusal`` is the one writer and it only ever writes a
refusal.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

SCHEMA_VERSION = "blackceo.emergency-owner/v1"

#: The operator box's default. A default is only ever handed to an install that
#: has already proved it is the operator box; see ``install_kind``.
OPERATOR_DEFAULT_NAME = "Trevor"

STATE_BOUND = "bound"
STATE_REFUSED = "refused"

EMERGENCY_OWNER_UNCONFIGURED = "EMERGENCY_OWNER_UNCONFIGURED"
EMERGENCY_OWNER_TREVOR_ON_CLIENT = "EMERGENCY_OWNER_TREVOR_ON_CLIENT"

#: Install marker names, in the order the existing repo already uses them.
OPERATOR_MARKERS = ("IS_OPERATOR_BOX", "OPERATOR_BOX")

#: The identity-file key, and the openclaw.json key order the installer reads.
IDENTITY_FILE = "onboarding-identity.json"
IDENTITY_KEY = "ownerName"
CONFIG_FILE = "openclaw.json"
CONFIG_NAME_PATHS = (("meta", "ownerName"), ("owner", "name"),
                     ("wizard", "ownerName"), ("meta", "owner", "name"),
                     ("owner", "firstName"))

_TRUTHY = ("1", "true", "yes", "on")


class EmergencyOwnerError(Exception):
    """A refusal with a stable code the caller reports verbatim."""

    def __init__(self, code, message, record=None):
        super().__init__("%s: %s" % (code, message))
        self.code = code
        self.record = record or {}


def _truthy(value):
    return isinstance(value, str) and value.strip().lower() in _TRUTHY


def _clean_name(value):
    """A configured name, or '' when it is not one. Never invented, never cut."""
    if not isinstance(value, str):
        return ""
    value = value.strip()
    if not value or len(value) > 200 or any(ord(c) < 32 for c in value):
        return ""
    return value


def config_root(explicit=None, env=None):
    """The install's own config root: explicit, then the installers' own vars."""
    if explicit:
        return os.path.expanduser(explicit)
    env = os.environ if env is None else env
    for key in ("OPENCLAW_ROOT", "OC_ROOT", "OC_CONFIG"):
        value = (env.get(key) or "").strip()
        if value:
            return os.path.expanduser(value)
    # ponytail: one home default. A VPS that keeps its install at /data sets
    # OPENCLAW_ROOT (platform/common.sh does exactly that), so no second probe.
    return os.path.join(os.path.expanduser("~"), ".openclaw")


def _read_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _secrets_marker(root):
    """OPERATOR_BOX=1 from the install's own secrets env file.

    Read, never printed: the file also holds credentials, so only the marker's
    presence is returned as a boolean.
    """
    path = os.path.join(root, "secrets", ".env")
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


def install_kind(root=None, env=None):
    """'operator' or 'client'. AN ABSENT MARKER IS NEVER AN OPERATOR BOX.

    The marker is the one the fleet already sets: ``IS_OPERATOR_BOX`` /
    ``OPERATOR_BOX`` in the environment, or ``OPERATOR_BOX=1`` in the install's
    secrets env file (the same variable ``scripts/configure-operator-telegram.sh``
    requires before it will touch operator routing).
    """
    env = os.environ if env is None else env
    root = root or config_root(env=env)
    for key in OPERATOR_MARKERS:
        if _truthy(env.get(key)):
            return "operator"
    if _secrets_marker(root):
        return "operator"
    return "client"


def configured_owner(root=None):
    """(name, source) from the install config, or ('', '') when unconfigured.

    ``onboarding-identity.json`` is the identity the installer collects, so it
    wins; ``openclaw.json`` is read in the installer's own key order.
    """
    root = root or config_root()
    identity = _read_json(os.path.join(root, IDENTITY_FILE))
    if isinstance(identity, dict):
        name = _clean_name(identity.get(IDENTITY_KEY))
        if name:
            return name, IDENTITY_FILE + ":" + IDENTITY_KEY
    config = _read_json(os.path.join(root, CONFIG_FILE))
    if isinstance(config, dict):
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
            os.path.join(root, "secrets", ".env"),
            "env:OPENCLAW_EMERGENCY_OWNER"]


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

    pinned = _clean_name(env.get("OPENCLAW_EMERGENCY_OWNER"))
    if pinned:
        name, source = pinned, "env:OPENCLAW_EMERGENCY_OWNER"
    else:
        name, source = configured_owner(root)

    if name and kind == "client" and name.strip().casefold() == \
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
