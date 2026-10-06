#!/usr/bin/env python3
"""loop_identity.py - the ONE place skill 61 decides what this box is called.

RR plan F17 (2026-10-03). The installer used to default the box name to
`hostname`, and loop_escalate sent only that as `box`. A hostname is not a join
key: Rescue Rangers matches on the canonical fleet slug, so hostname-named
escalations matched no client, could not be coached, paged the operator, and
two clients' boxes could fold into one ticket (970 of ~2,600 pre-clear tickets
came from this skill).

Order: FLEET_STANDING_BOX_SLUG env, RR_BOX_SLUG env, then openclaw.json
env.vars.FLEET_STANDING_BOX_SLUG (read only; the secrets file is deliberately
never read). A name that looks like a hostname or a container id is REFUSED, not
guessed. Stdlib only. Never prints a secret.

CLI:  loop_identity.py resolve        print the slug, exit 0; exit 4 + reason on stderr
      loop_identity.py check NAME     exit 0 if NAME is a usable slug; exit 4 + reason
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

SLUG_ENVS = ("FLEET_STANDING_BOX_SLUG", "RR_BOX_SLUG")
CLIENT_ENV = "FLEET_STANDING_CLIENT_LABEL"
_PLACEHOLDERS = {"", "tbd", "unknown", "n/a", "na", "none", "null", "box",
                 "localhost", "host", "hostname"}
_HOST_SUFFIXES = (".local", ".lan", ".home", ".localdomain", ".internal", ".fritz.box")
_CONTAINER_ID = re.compile(r"^(?:[0-9a-f]{12}|[0-9a-f]{64})$")


def problem(name):
    """Why `name` cannot be a canonical slug, or None when it is usable."""
    n = (name or "").strip()
    low = n.lower()
    if low in _PLACEHOLDERS:
        return "empty or placeholder name %r" % n
    if low.endswith(_HOST_SUFFIXES) or "." in n:
        return "%r looks like a hostname (contains a dot or ends .local/.lan/.home)" % n
    if _CONTAINER_ID.match(low):
        return "%r looks like a docker container id" % n
    return None


def _from_openclaw_json():
    try:
        from loop_ledger import openclaw_root
        d = json.loads((openclaw_root() / "openclaw.json").read_text(encoding="utf-8"))
        return str((((d.get("env") or {}).get("vars") or {}).get("FLEET_STANDING_BOX_SLUG") or "")).strip()
    except Exception:
        return ""


def resolve_slug():
    """(slug, why_not). slug is a usable canonical slug or None."""
    for key in SLUG_ENVS:
        v = os.environ.get(key, "").strip()
        if v:
            p = problem(v)
            return (None, "%s: %s" % (key, p)) if p else (v, None)
    v = _from_openclaw_json()
    if v:
        p = problem(v)
        return (None, "openclaw.json env.vars.FLEET_STANDING_BOX_SLUG: %s" % p) if p else (v, None)
    return None, "FLEET_STANDING_BOX_SLUG / RR_BOX_SLUG not set in the environment or openclaw.json"


def _sync_ledger_box(slug):
    """Keep Skill 61's OWN ledger meta `box` equal to the canonical slug.

    Fix 7 (October update spec): installs made before the fleet-slug fix keep a
    hostname in meta `box`, and the run reads that stored name. Once a slug
    resolves, the ledger is corrected here so the box converges on its slug.
    Touches only an EXISTING ledger (never creates one as a side effect),
    never runs as root (state writes are the box user's),
    and never raises: identity housekeeping must not break an escalation.
    """
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import loop_ledger as _ll
        if _ll.is_root() or not _ll.db_path().exists():
            return
        with _ll.Ledger() as led:
            if led.get_meta("box") != slug:
                led.set_meta("box", slug)
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write("WARN [loop_identity]: could not sync ledger box meta (%s)\n"
                         % type(exc).__name__)


def canonical_box(box):
    """The name to put on the wire. The canonical slug is resolved FIRST and
    wins over any stored/explicit name (a dotless hostname such as
    `TrevelynsMini2` passes problem(), so the stored name must never beat a
    resolvable slug). On a hit the ledger meta `box` is corrected too. Only when
    NO slug resolves does the stored name fall back (see identity_state())."""
    slug, _why = resolve_slug()
    if slug:
        _sync_ledger_box(slug)
        return slug
    if box and problem(box) is None:
        return box.strip()
    return box or ""


def identity_state():
    """Return 'resolved' when a canonical slug is known, else 'unresolved'
    (the wire name is then the stored fallback). Rescue Rangers tells the two
    apart through the escalation payload's `identity` field."""
    return "resolved" if resolve_slug()[0] else "unresolved"


def client_label(box_name):
    """FLEET_STANDING_CLIENT_LABEL when set, else the slug (same default the
    escalation template stamper uses), so clientName is never blank."""
    return os.environ.get(CLIENT_ENV, "").strip() or box_name


def _cli(argv):
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    if len(argv) >= 1 and argv[0] == "resolve":
        slug, why = resolve_slug()
        if slug:
            print(slug)
            return 0
        sys.stderr.write("[loop-identity] REFUSED: %s\n" % why)
        return 4
    if len(argv) == 2 and argv[0] == "check":
        p = problem(argv[1])
        if p is None:
            return 0
        sys.stderr.write("[loop-identity] REFUSED: %s\n" % p)
        return 4
    sys.stderr.write("usage: loop_identity.py resolve | check NAME\n")
    return 2


if __name__ == "__main__":
    sys.exit(_cli(sys.argv[1:]))
