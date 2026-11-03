#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build_production_request_with_layouts.py - Skill 71's request builder with the declared upsell band layouts applied.

Skill 71 declares the eight upsell bands in references/page-structures.json `layouts` and the stage executor refuses a
request whose sections lack the declared layout_tag, but the builder tags none of a MANUSCRIPT-fed upsell. The legacy
ledger has no Skill 80 copy JSON or price terms to feed the --copy-json path with (that would invent them), so
legacy_downsell_images.py builds through this wrapper: 71's own entry point, each band tagged from the declared
layout, section for section. A role with no declared layout (every page but the upsells) is untouched.

    build_production_request_with_layouts.py <71 scripts dir> <build_production_request.py arguments...>

# ponytail: wraps 71's sections_from_manuscript; drop once 71 tags manuscript-fed upsell bands itself.
"""
import json
import sys
from pathlib import Path


def main(argv):
    sys.path.insert(0, argv[1])
    import build_production_request as b  # noqa: E402
    args = argv[2:]
    role = args[args.index("--page-role") + 1] if "--page-role" in args else "landing"
    declared = json.loads(Path(b.exe.STRUCTURES_FILE).read_text(encoding="utf-8")).get("layouts") or {}
    real = b.sections_from_manuscript

    def tagged(text, spec, slots, style_id=None, *rest):  # rest: 71's order_bump, passed through untouched
        out = real(text, spec, slots, style_id, *rest)
        if isinstance(declared.get(role), dict):
            bands = b.upsell_layouts({"instance": role})
            for section in out:
                section["layout_tag"] = bands[section["section_id"]]["layout_tag"]
        return out
    b.sections_from_manuscript = tagged
    return b.main(args)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
