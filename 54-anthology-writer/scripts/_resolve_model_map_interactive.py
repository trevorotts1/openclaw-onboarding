#!/usr/bin/env python3
"""Interactive model-map resolver for Skill 54 (Anthology Writer).

Reads the placeholder model-map.json that preflight.sh just scaffolded, prompts
the operator for a provider + model per capability tier, and rewrites the map
resolved.

WHY THIS IS A REAL FILE AND NOT A preflight.sh HEREDOC:
    `python3 - <<'PY'` feeds the program text to python3 ON STDIN. When the
    program then calls input(), stdin is already at EOF (the heredoc was fully
    consumed as the source), so every prompt dies with EOFError. A script file
    is read from disk, so python3's stdin stays connected to the operator's
    terminal / piped answers and input() actually works.

Usage:
    _resolve_model_map_interactive.py <path/to/model-map.json>

Guarantees: NEVER writes an Anthropic id; NEVER writes an operator key.
"""
import json
import os
import re
import sys

BANNED = re.compile(r"claude-|anthropic/|us\.anthropic\.")


def main(argv):
    if len(argv) != 2:
        print("usage: _resolve_model_map_interactive.py <model-map.json>", file=sys.stderr)
        return 3
    path = argv[1]
    try:
        current = json.load(open(path, "r", encoding="utf-8"))
    except Exception as exc:
        print("AF-AW-UNRESOLVED-MODELMAP: cannot read %s: %s" % (path, exc), file=sys.stderr)
        return 2
    tiers = current.get("tiers", {}) or {}
    if not tiers:
        print("AF-AW-UNRESOLVED-MODELMAP: no tiers found in %s" % path, file=sys.stderr)
        return 2

    print("\n  === Interactive Model-Map Configuration ===", file=sys.stderr)
    print("  For each tier, enter the provider ID and model ID for your box.", file=sys.stderr)
    print("  Press Enter to accept the default shown in [brackets].", file=sys.stderr)
    print("  No provider/model may start with 'claude-', 'anthropic/', or 'us.anthropic.'.",
          file=sys.stderr)

    resolved = {}
    for name in sorted(tiers):
        t = tiers[name] or {}
        print("\n  --- Tier: %s (%s) ---" % (name, t.get("role", "")), file=sys.stderr)
        def_provider = os.environ.get("AW_PROVIDER_" + name, "")
        def_model = os.environ.get("AW_MODEL_" + name, "")
        suffix_p = " [%s]" % def_provider if def_provider else ""
        suffix_m = " [%s]" % def_model if def_model else ""
        try:
            provider = input("  Provider for %s:%s " % (name, suffix_p)).strip()
            model = input("  Model for %s:%s " % (name, suffix_m)).strip()
        except EOFError:
            print("AF-AW-UNRESOLVED-MODELMAP: input ended before every tier was resolved "
                  "(expected a provider and a model for each tier)", file=sys.stderr)
            return 2
        provider = provider or def_provider
        model = model or def_model
        for k, v in (("provider", provider), ("model", model)):
            if BANNED.search(v):
                print("AF-AW-ANTHROPIC: tier %s.%s carries a banned id %r" % (name, k, v),
                      file=sys.stderr)
                return 2
        entry = {"role": t.get("role", ""), "provider": provider, "model": model}
        if t.get("maxTokens") is not None:
            entry["maxTokens"] = t.get("maxTokens")
        resolved[name] = entry

    current["tiers"] = resolved
    current["resolved_per_box"] = True
    current["note"] = ("Resolved interactively — provider/model values entered by operator. "
                       "NEVER Anthropic, NEVER operator keys.")
    json.dump(current, open(path, "w", encoding="utf-8"), indent=2)
    print("  resolved model-map.json ->", path)
    for name in sorted(resolved):
        print("   tier %-13s provider=%s model=%s"
              % (name, resolved[name]["provider"], resolved[name]["model"]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
