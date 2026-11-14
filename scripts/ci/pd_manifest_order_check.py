#!/usr/bin/env python3
"""pd_manifest_order_check.py - prove no phase can be stranded by a declined branch.

Reads PIPELINE-MANIFEST.json as JSON (never prose) and, for each of the four
upsell election sets, asks whether every artifact a phase CONSUMES can exist
when that phase runs.

Finding kinds
  DEFER_TRAP         FAILING. A phase with no `defers_unless` of its own
                     consumes a file whose every producer declares one: the
                     producer is DEFERRED for a client who declined that
                     branch, the edge INTO this phase is still REQUIRED
                     (`build_edge_records`: optional is decided by the
                     CONSUMER's defers_unless, not the producer's), and the
                     engine's admission gate therefore withholds the consumer
                     forever. This is finding PD-038.
  NO_PRODUCER        FAILING. No phase produces the file and it is not a
                     declared input (see EXTERNAL_INPUTS).
  SELF_CONSUME       informational. A phase consumes its own product.
  INACTIVE_PRODUCER  informational. Every producer of the file is deferred
                     under these elections.
  LATE_PRODUCER      informational only (the engine schedules by the artifact
                     DAG, never by `order`, so a producer ordered later is not
                     a defect).
  UNPARSED           informational. A defers_unless predicate outside the
                     `intake.<key> == "yes"` grammar; treated as active.

Exit codes: 0 clean (no DEFER_TRAP / NO_PRODUCER), 1 a failing kind fired,
2 cannot run (manifest missing or unparseable).
Usage: python3 -I pd_manifest_order_check.py --manifest PATH [--json]
STDLIB ONLY. Read-only.
"""
import argparse
import fnmatch
import json
import sys
from pathlib import Path

# Inputs no manifest phase produces. Extend ONLY with a comment naming the writer.
EXTERNAL_INPUTS = {
    "raw/*",                             # client upload (raw/source-brief.*)
    "working/copy/slides.json",          # engine-owned, manifest.py _ROOT_INPUTS
                                         # (presentation_job/slides_assembly.py writes it)
    "working/copy/intake.json",          # deck-intake-driver.py --complete
    "working/interview/intake_transcript.json",  # deck-intake-driver.py
    "working/copy/sp_intake.json",       # deck-intake-driver.py --signature
    "working/prompts/infographic-prompt.txt",    # agent-authored: role
                                         # slide-image-creator under SOP 9.10
                                         # (INFOGRAPHIC-PROMPT-TEMPLATE.md);
                                         # build_infographic.py reads it VERBATIM
                                         # and never authors its own prompt
}

# Only these two kinds fail the check. LATE_PRODUCER is information (the engine
# schedules by the artifact DAG, not by `order`), and SELF_CONSUME /
# INACTIVE_PRODUCER / UNPARSED are reported without blocking.
FAILING_KINDS = ("DEFER_TRAP", "NO_PRODUCER")

ELECTION_SETS = {
    "default (sales_checkout=yes, vsl=no)": {"want_sales_checkout": "yes", "want_vsl_page": "no"},
    "both upsells": {"want_sales_checkout": "yes", "want_vsl_page": "yes"},
    "deck only": {"want_sales_checkout": "no", "want_vsl_page": "no"},
    "vsl only": {"want_sales_checkout": "no", "want_vsl_page": "yes"},
}


def as_list(value):
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    return [str(v) for v in value]


def active(phase, elections):
    """True when the phase's defers_unless predicate holds (or it has none).

    The manifest predicate grammar seen in v75 is only:
        intake.<key> == "yes" [or intake.<key> == "yes"]
    Anything else is reported as UNPARSED and treated as active (never hidden).
    """
    pred = phase.get("defers_unless")
    if not pred:
        return True, None
    clauses = [c.strip() for c in pred.split(" or ")]
    verdicts = []
    for clause in clauses:
        parts = clause.split("==")
        if len(parts) != 2 or not parts[0].strip().startswith("intake."):
            return True, "UNPARSED defers_unless: %r" % pred
        key = parts[0].strip()[len("intake."):]
        want = parts[1].strip().strip('"').strip("'")
        verdicts.append(elections.get(key) == want)
    return any(verdicts), None


def same_artifact(a, b):
    return a == b or fnmatch.fnmatch(a, b) or fnmatch.fnmatch(b, a)


def check(manifest, elections):
    findings = []
    phases = sorted(manifest["phases"], key=lambda p: p.get("order", 0))
    state = []
    for p in phases:
        is_active, note = active(p, elections)
        if note:
            findings.append(("UNPARSED", p["id"], note))
        state.append((p, is_active))
    for consumer, c_active in state:
        if not c_active:
            continue
        c_order = consumer.get("order", 0)
        own = as_list(consumer.get("produces_artifact"))
        gated_consumer = bool(consumer.get("defers_unless"))
        for need in as_list(consumer.get("consumes")):
            if any(same_artifact(need, ext) for ext in EXTERNAL_INPUTS):
                continue
            if any(same_artifact(need, o) for o in own):
                findings.append(("SELF_CONSUME", consumer["id"],
                                 "%s (order %s) consumes its own product %s" % (consumer["id"], c_order, need)))
                continue
            producers = [(p, a) for p, a in state
                         if p["id"] != consumer["id"]
                         and any(same_artifact(need, o) for o in as_list(p.get("produces_artifact")))]
            if not producers:
                findings.append(("NO_PRODUCER", consumer["id"],
                                 "%s (order %s) consumes %s; no phase produces it" % (consumer["id"], c_order, need)))
                continue
            if not gated_consumer and all(p.get("defers_unless") for p, _ in producers):
                findings.append(("DEFER_TRAP", consumer["id"],
                                 "%s (order %s) has no defers_unless but consumes %s, whose every producer "
                                 "defers (%s) -- a declined branch strands this phase"
                                 % (consumer["id"], c_order, need,
                                    ", ".join(p["id"] for p, _ in producers))))
            live = [p for p, a in producers if a]
            if not live:
                findings.append(("INACTIVE_PRODUCER", consumer["id"],
                                 "%s (order %s) consumes %s; producer(s) %s are deferred under these elections"
                                 % (consumer["id"], c_order, need, [p["id"] for p, _ in producers])))
                continue
            earlier = [p for p in live if p.get("order", 0) < c_order]
            if not earlier:
                findings.append(("LATE_PRODUCER", consumer["id"],
                                 "%s (order %s) consumes %s; earliest active producer is %s (order %s)"
                                 % (consumer["id"], c_order, need, live[0]["id"], live[0].get("order"))))
    return findings


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    path = Path(args.manifest)
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
        assert isinstance(manifest.get("phases"), list) and manifest["phases"]
    except Exception as exc:  # noqa: BLE001 - cannot run is exit 2, never a pass
        print("CANNOT RUN: %s (%s)" % (path, exc), file=sys.stderr)
        return 2
    report = {}
    failing = []
    for label, elections in ELECTION_SETS.items():
        found = check(manifest, elections)
        report[label] = [{"kind": k, "phase": pid, "detail": d} for k, pid, d in found]
        failing.extend((label, k, pid) for k, pid, _ in found if k in FAILING_KINDS)
    if args.json:
        print(json.dumps({"manifest_version": manifest.get("manifest_version"),
                          "phases": len(manifest["phases"]),
                          "failing_kinds": list(FAILING_KINDS),
                          "fail": bool(failing),
                          "findings": report}, indent=2))
    else:
        print("manifest_version=%s phases=%d" % (manifest.get("manifest_version"), len(manifest["phases"])))
        for label, rows in report.items():
            print("\n[%s] %d finding(s)" % (label, len(rows)))
            for row in rows:
                tag = "FAIL" if row["kind"] in FAILING_KINDS else "INFO"
                print("  %-4s %-18s %s" % (tag, row["kind"], row["detail"]))
        if failing:
            print("\nFAILED: %d %s row(s) across the election sets." % (len(failing), "/".join(FAILING_KINDS)))
        else:
            print("\nPASS: no %s row in any election set." % " or ".join(FAILING_KINDS))
    return 1 if failing else 0


if __name__ == "__main__":
    sys.exit(main())
