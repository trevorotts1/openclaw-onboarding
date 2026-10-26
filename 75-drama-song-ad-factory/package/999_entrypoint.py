#!/usr/bin/env python3
"""999 normal entrypoint (S75-T30 / S75-A30). Stdlib only.

This is the 999 flavour's own front door, not the package checker. Running it
routes the story-first product carriers into the process: the imports below are
real, static, module-level imports, so a static walker sees them and the running
process really loads them before any command is answered.

The 999 package ships this adapter instead of the primary flavour's
`scripts/openclaw_adapter.py` (the seam records `skill_root_anchor` =
`.claude/skills/drama-song-ad-factory` and the primary wrapper as forbidden on
this flavour). The primary control CLI `scripts/core/intake_preflight/factory.py`
is a held file owned by another unit; this entrypoint relays `factory <args>`
to it and never edits it.

Commands:

  carriers   print the routed carriers and which of them this process loaded
  status     print the measured product status read from the loaded carriers
  factory    relay every remaining argument to the control CLI and exit with
             its exit code

Run: python3 package/999_entrypoint.py carriers
     python3 package/999_entrypoint.py status
     python3 package/999_entrypoint.py factory preflight --root DIR
"""
from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL_ROOT = os.path.dirname(HERE)
CORE = os.path.join(SKILL_ROOT, "scripts", "core")
FACTORY = os.path.join(CORE, "intake_preflight", "factory.py")

if CORE not in sys.path:
    sys.path.insert(0, CORE)

# Real routing to the product carriers. These are module-level imports on
# purpose: the 999 entrypoint must reach the story-first behaviour itself, not
# have a checker import it on the entrypoint's behalf.
import story_first_contracts  # noqa: E402
import package_flavor_adapter  # noqa: E402
from music_styles import catalog  # noqa: E402
from character_bible import identity  # noqa: E402
from character_library import notion_adapter  # noqa: E402
from character_library import sync_protocol  # noqa: E402
from method_plan import method_plan  # noqa: E402

#: Every module this entrypoint is declared to route into. `carriers` reports
#: the intersection of this tuple with sys.modules, so a dropped import is
#: visible in the running process, not only in the source.
ROUTED_CARRIERS = (
    "story_first_contracts",
    "package_flavor_adapter",
    "music_styles.catalog",
    "character_bible.identity",
    "character_library.notion_adapter",
    "character_library.sync_protocol",
    "method_plan.method_plan",
)


def loaded_carriers():
    return [name for name in ROUTED_CARRIERS if name in sys.modules]


def product_status():
    """Measure the loaded carriers. Read-only; no write, no network."""
    order = list(getattr(story_first_contracts, "STAGE_ORDER", ()))

    library_refused = False
    try:
        identity.validate_library({})
    except identity.IdentityDefect:
        library_refused = True

    notion_offline_refused = False
    try:
        notion_adapter.resolve_client_library({}, "probe")
    except notion_adapter.ConnectionUnavailable:
        notion_offline_refused = True

    sync_digest = sync_protocol.payload_digest({"probe": 1})

    plan = method_plan.validate({}, {})
    gates = method_plan.gates({})

    return {
        "skill_root": SKILL_ROOT,
        "flavour": package_flavor_adapter.resolve(package_flavor_adapter.N999)[
            "flavor"],
        "stage_count": len(order),
        "stage_order_head": order[:3],
        "identity_library_refused": library_refused,
        "notion_ops": list(getattr(notion_adapter, "OPS", ())),
        "notion_offline_refused": notion_offline_refused,
        "sync_digest_prefix": sync_digest.split(":", 1)[0],
        "style_count": len(getattr(catalog, "STYLE_IDS", ())),
        "method_gates": sorted(gates),
        "method_plan_outcome": plan.get("outcome"),
        "method_teaching_rows": len(method_plan.teaching_map("campaign")),
    }


def relay(argv):
    """Relay a control-CLI invocation to factory.py; return its exit code."""
    import subprocess
    proc = subprocess.run([sys.executable, FACTORY, *argv], cwd=SKILL_ROOT)
    return proc.returncode


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] in ("-h", "--help"):
        print(__doc__.strip())
        return 0 if args else 2
    cmd, rest = args[0], args[1:]
    if cmd == "carriers":
        print(json.dumps({"routed": list(ROUTED_CARRIERS),
                          "loaded": loaded_carriers()},
                         indent=2, sort_keys=True))
        return 0
    if cmd == "status":
        print(json.dumps(product_status(), indent=2, sort_keys=True))
        return 0
    if cmd == "factory":
        return relay(rest)
    sys.stderr.write("unknown command %r\n" % (cmd,))
    return 2


if __name__ == "__main__":
    sys.exit(main())
