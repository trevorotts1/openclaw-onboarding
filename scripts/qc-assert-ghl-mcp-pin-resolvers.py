#!/usr/bin/env python3
"""qc-assert-ghl-mcp-pin-resolvers.py -- keep the pin-file search paths in sync.

WHY THIS EXISTS
---------------
Four different files each carry their own hardcoded list of places to look for
``config/ghl-mcp-pin.env``: the autostart script, the liveness probe, the VPS
overlay, and the digest checker that judges the record.

If the checker's list is ever NARROWER than a consumer's, the gate and the box
can read DIFFERENT FILES. The gate then passes on a record the box will never
see, while the box quietly runs whatever the file it *did* find says. A gate
that validates a different file from the one that gets executed is not a gate.

So the invariant is one-directional and deliberate:

    every path any CONSUMER searches must also be searched by the CHECKER

The checker is allowed to search MORE paths than a consumer (it does today, and
it should -- it is the thing that has to be able to find whatever the box found).
It is never allowed to search fewer.

This is a static, structural check. It parses the literal candidate paths out of
each file; it does not source anything.

Exit codes: 0 = in sync, 1 = drift found, 2 = a file or its resolver is missing.
"""

import os
import re
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

CHECKER = "scripts/ghl-mcp-check-pin-digest.sh"
CONSUMERS = [
    "scripts/ghl-mcp-autostart.sh",
    "scripts/ghl-mcp-probe.sh",
    "platform/vps/36-ghl-mcp-setup-scripts/start-ghl-mcp-server.sh",
]

# Matches the quoted candidate paths in the `for _c in "..." \` resolver loops.
CANDIDATE_RE = re.compile(r'"([^"]*ghl-mcp-pin\.env)"')


def normalise(path):
    """Collapse the repo-relative spellings to one canonical token.

    The three consumers sit at different depths, so the same repo-root config
    directory is spelled "$SELF_DIR/../config/...", "$SELF_DIR/../../../config/..."
    and so on. Those are the SAME location and must not read as drift. Everything
    else is compared literally, because "$HOME/.openclaw/config" and
    "$HOME/.openclaw/onboarding/config" really are different directories and the
    difference is exactly what this check is for.
    """
    if path.startswith("$SELF_DIR/"):
        rest = path[len("$SELF_DIR/"):]
        rest = re.sub(r"^(\.\./)+", "", rest)
        return "<repo>/" + rest
    return path


def extract(rel_path):
    full = os.path.join(REPO_ROOT, rel_path)
    if not os.path.isfile(full):
        return None
    with open(full, "r", encoding="utf-8", errors="replace") as fh:
        text = fh.read()
    found = []
    for line in text.splitlines():
        stripped = line.lstrip()
        if stripped.startswith("#"):
            continue  # a path named in prose is documentation, not a resolver
        for hit in CANDIDATE_RE.findall(line):
            found.append(normalise(hit))
    return found


def main():
    checker_paths = extract(CHECKER)
    if checker_paths is None:
        print("FAIL: %s is missing -- it owns the digest gate's resolver." % CHECKER)
        return 2
    if not checker_paths:
        print("FAIL: %s declares no pin-file candidate paths." % CHECKER)
        return 2

    checker_set = set(checker_paths)
    failures = 0
    missing_consumers = 0

    print("checker %s searches %d path(s):" % (CHECKER, len(checker_set)))
    for p in checker_paths:
        print("    %s" % p)

    for consumer in CONSUMERS:
        paths = extract(consumer)
        if paths is None:
            print("FAIL: consumer %s is missing." % consumer)
            missing_consumers += 1
            continue
        if not paths:
            print("FAIL: consumer %s declares no pin-file candidate paths -- it "
                  "cannot be reading the pin at all." % consumer)
            failures += 1
            continue
        gaps = [p for p in paths if p not in checker_set]
        if gaps:
            failures += 1
            print("FAIL: %s searches path(s) the digest checker does NOT:" % consumer)
            for g in gaps:
                print("        %s" % g)
            print("      The box could read that file while the gate judges a "
                  "different one. Add it to %s." % CHECKER)
        else:
            print("PASS: %s (%d path(s), all covered by the checker)" % (consumer, len(paths)))

    if missing_consumers:
        return 2
    if failures:
        print("\nRESULT: pin-file resolver drift -- %d consumer(s) out of sync." % failures)
        return 1
    print("\nRESULT: every consumer's pin-file resolver is covered by the digest checker.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
