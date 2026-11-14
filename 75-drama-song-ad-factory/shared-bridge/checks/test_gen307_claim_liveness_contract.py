#!/usr/bin/env python3
"""U-GEN307 — the claim-liveness contract must match the code.

The defect this guards: the module shipped a Windows-safe liveness probe that
no production path called, while the claim path's real contract (OPTION A: a
claim outlives its process, so a dead holder blocks the order for the default
lease) was not stated where a reader would see it.

There are two honest endings, and this check accepts either:

  probe ending  `_holder_live` returns False for a dead pid with a live lease,
                so the claim is recoverable without waiting out the lease.
  loud ending   OPTION A stays: `_holder_live` returns True, the module states
                the one-hour cost, and no unused `pid_is_alive` probe ships —
                it is absent from the module, or a production caller outside
                `checks/` uses it.

On the pre-fix tree this FAILS: the probe exists with check-only callers and
the module docstring does not state the one-hour cost. On the fixed tree it
passes because the probe is absent and the cost is stated.

Run: python3 -I checks/test_gen307_claim_liveness_contract.py
Exit: 0 contract and code agree, 1 they do not.
"""
import ast
import importlib.util
import os
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
BRIDGE_DIR = HERE.parent
LEDGER = BRIDGE_DIR / "studio_claim.py"

NOW = 1_000_000.0
LIVE_LEASE = NOW + 3600.0
DEAD_PID = 2 ** 31 - 1


def load_ledger():
    spec = importlib.util.spec_from_file_location("sc_gen307", str(LEDGER))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def production_callers(name):
    """Files outside `checks/` that name `name` in their syntax tree."""
    hits = []
    for dp, dns, fns in os.walk(BRIDGE_DIR):
        dns[:] = [d for d in dns
                  if d not in ("checks", "__pycache__", ".git")]
        for fn in fns:
            if not fn.endswith(".py"):
                continue
            path = os.path.join(dp, fn)
            try:
                tree = ast.parse(open(path, encoding="utf-8").read())
            except (OSError, SyntaxError, UnicodeDecodeError):
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.Name) and node.id == name:
                    hits.append("%s:%d" % (path, node.lineno))
                elif isinstance(node, ast.Attribute) and node.attr == name:
                    hits.append("%s:%d" % (path, node.lineno))
    return hits


def cost_paragraph(doc):
    """The docstring paragraph that states what a dead holder costs."""
    lines = (doc or "").splitlines()
    for i, line in enumerate(lines):
        if "dead holder" in line.lower():
            j = i
            while j + 1 < len(lines) and lines[j + 1].strip():
                j += 1
            return "\n".join(ln.strip() for ln in lines[i:j + 1])
    return ""


def main():
    sc = load_ledger()
    decision = sc._holder_live("probe-host", DEAD_PID, LIVE_LEASE, NOW)
    doc = "\n".join(filter(None, (sc.__doc__, sc._holder_live.__doc__))).lower()
    states_cost = (("one hour" in doc or "3600" in doc)
                   and "dead holder" in doc and "lease" in doc)
    probe_present = hasattr(sc, "pid_is_alive")
    callers = production_callers("pid_is_alive") if probe_present else []

    if decision is False:
        ok = True
        form = "probe ending (_holder_live refuses the dead holder)"
    elif decision is True:
        ok = states_cost and (not probe_present or bool(callers))
        form = ("loud ending (_holder_live keeps OPTION A; cost stated=%s; "
                "probe present=%s; production callers=%s)"
                % (states_cost, probe_present, callers))
    else:
        ok = False
        form = "unexpected decision %r" % (decision,)

    print("%s: dead holder with a live lease -> %r; %s"
          % ("ok" if ok else "FAIL", decision, form))
    print("contract paragraph: %s" % (cost_paragraph(sc.__doc__) or "(none)"))
    print("pid_is_alive: %s" % ("absent" if not probe_present
                                else "present; production callers=%s" % callers))
    if not ok:
        if decision is True and not states_cost:
            print("FAIL: the module does not state that a dead holder's claim "
                  "stands for the default one-hour lease")
        if decision is True and probe_present and not callers:
            print("FAIL: `pid_is_alive` is shipped but no production caller "
                  "uses it")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
