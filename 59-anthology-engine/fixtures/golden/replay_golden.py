#!/usr/bin/env python3
# =============================================================================
# SKILL 59 — ANTHOLOGY ENGINE :: fixtures/golden/replay_golden.py
# THE GOLDEN-FIXTURE REPLAY + VERIFY HARNESS (W1.23)
# -----------------------------------------------------------------------------
# Replays each golden fixture (full-participant, two-anthology-contact,
# exception, assembly-trio) against the REAL sole ledger writer
# (scripts/anthology_state.py) in an ISOLATED, MIRROR-ONLY temp state directory,
# asserting every step's exit code and a subset of its JSON result, then the
# per-fixture final_assertions (participant cursors, anthology state, S9
# readiness, and the one-contact/two-anthology keying invariant).
#
# It is BOTH the offline smoke test for these fixtures AND the driver the Wave 5
# canary drills shell (W5.4 full participant, W5.6 two-anthology, W5.7 assembly);
# on the canary the SAME step sequence is additionally exercised from both doors
# (board card + participant token page). Here it is pure, deterministic, and
# network-free: no base id is configured, so the ledger runs mirror-only and
# exits 0 on the base path (SPEC 7.2). STDLIB ONLY. Nothing Anthropic, no
# secret values printed (labels only), Convert and Flow naming throughout.
#
#   python3 fixtures/golden/replay_golden.py --list
#   python3 fixtures/golden/replay_golden.py --all
#   python3 fixtures/golden/replay_golden.py --fixture assembly-trio [--json]
#   python3 fixtures/golden/replay_golden.py --fixture assembly-trio --explain
#
# Exit 0 iff every replayed step and every final assertion holds.
# =============================================================================
"""Replay + verify the Anthology Engine golden fixtures against the real ledger."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

GOLDEN_DIR = Path(__file__).resolve().parent
SKILL_DIR = GOLDEN_DIR.parents[1]                      # 59-anthology-engine/
STATE_SCRIPT = SKILL_DIR / "scripts" / "anthology_state.py"
MANIFEST = GOLDEN_DIR / "golden-manifest.json"

FIXTURE_FILES = {
    "full-participant": GOLDEN_DIR / "full-participant.json",
    "two-anthology-contact": GOLDEN_DIR / "two-anthology-contact.json",
    "exception": GOLDEN_DIR / "exception.json",
    "assembly-trio": GOLDEN_DIR / "assembly-trio.json",
}

# Base-store env labels that would switch the ledger to LIVE mode. We strip them
# from the child environment so every replay runs MIRROR-ONLY (a clean exit-0
# base path) and never reaches for a real Airtable base. Values are never read
# or printed; we only ensure the labels are ABSENT for isolation.
_BASE_ENV_LABELS = (
    "ANTHOLOGY_STATE_BASE_ID", "ANTHOLOGY_STATE_AIRTABLE_KEY",
    "AIRTABLE_API_KEY", "AIRTABLE_TOKEN", "AIRTABLE_PAT",
)


# ---------------------------------------------------------------------------
# The macro that expands the repeated "S0 -> approved with a frozen chapter" arc
# into the exact anthology_state.py subcommand sequence. Kept here (not in the
# fixture JSON) so the fixtures stay readable; --explain prints the expansion.
# ---------------------------------------------------------------------------
def expand_macro(step: dict) -> list:
    name = step.get("macro")
    if name != "drive_to_approved_frozen":
        raise SystemExit("unknown macro %r in step %s" % (name, step.get("n")))
    p = step["params"]
    key = p["participant_key"]
    model = p.get("model", "glm-5.2")
    slug = key.split("::", 1)[0].lower()
    doc = "https://docs.google.com/document/d/gdoc_syn_chapter_%s/edit" % slug
    pdf = "https://drive.google.com/file/d/gfile_syn_chapter_%s/view" % slug
    title_args = {"--gate": "s3_selection", "--participant-key": key,
                  "--decision": "approve", "--title": p["title"], "--door": "nudge_link"}
    if p.get("subtitle"):
        title_args["--subtitle"] = p["subtitle"]
    chap_args = {"--participant-key": key, "--type": "chapter", "--doc-url": doc,
                 "--pdf-url": pdf, "--sha256": p["sha256"], "--model-used": model,
                 "--custom-field-keys-written":
                     ["contact.anthology_chapter_doc_url", "contact.anthology_chapter_pdf_url"]}
    seq = [
        ("advance-stage", {"--participant-key": key, "--to": "s1_avatar"}, 0, {"to": "s1_avatar"}),
        ("advance-stage", {"--participant-key": key, "--to": "s1_gate"}, 0, {"to": "s1_gate"}),
        ("record-approval", {"--gate": "s1_producer", "--participant-key": key,
                             "--decision": "approve", "--door": "dashboard"}, 0,
         {"stage_cursor": "s2_tone"}),
        ("advance-stage", {"--participant-key": key, "--to": "s2_gate"}, 0, {"to": "s2_gate"}),
        ("record-approval", {"--gate": "s2_producer", "--participant-key": key,
                             "--decision": "approve", "--door": "dashboard"}, 0,
         {"stage_cursor": "s3_title"}),
        ("advance-stage", {"--participant-key": key, "--to": "s3_gate"}, 0, {"to": "s3_gate"}),
        ("record-approval", title_args, 0, {"stage_cursor": "s4_blurb_outline"}),
        ("advance-stage", {"--participant-key": key, "--to": "s4_gate_producer"}, 0,
         {"to": "s4_gate_producer"}),
        ("record-approval", {"--gate": "s4_producer", "--participant-key": key,
                             "--decision": "approve", "--door": "dashboard"}, 0,
         {"stage_cursor": "s4_gate_participant"}),
        ("record-approval", {"--gate": "s4_participant", "--participant-key": key,
                             "--decision": "approve", "--door": "nudge_link"}, 0,
         {"stage_cursor": "s5_chapter"}),
        ("record-artifact", chap_args, 0, {"type": "chapter", "version": 1}),
        ("advance-stage", {"--participant-key": key, "--to": "s5_gate"}, 0, {"to": "s5_gate"}),
        ("record-approval", {"--gate": "s5_participant", "--participant-key": key,
                             "--decision": "approve", "--door": "nudge_link"}, 0,
         {"stage_cursor": "s7_cover"}),
        ("advance-stage", {"--participant-key": key, "--to": "s8_deliver"}, 0, {"to": "s8_deliver"}),
        ("advance-stage", {"--participant-key": key, "--to": "s9_wait_assembly"}, 0,
         {"to": "s9_wait_assembly"}),
        ("advance-stage", {"--participant-key": key, "--to": "approved"}, 0, {"to": "approved"}),
    ]
    return [{"cmd": c, "args": a, "expect_exit": e, "expect": x, "_macro": name,
             "_body_file": p.get("body_file") if c == "record-artifact" else None}
            for (c, a, e, x) in seq]


# ---------------------------------------------------------------------------
# Ledger CLI invocation (mirror-only, isolated temp DB).
# ---------------------------------------------------------------------------
def _flatten(args: dict) -> list:
    out = []
    for k, v in args.items():
        if v is True:
            out.append(k)
        elif v is False or v is None:
            continue
        elif isinstance(v, (list, dict)):
            out.extend([k, json.dumps(v, ensure_ascii=False)])
        else:
            out.extend([k, str(v)])
    return out


def run_cmd(db: Path, cmd: str, args: dict):
    """Run one anthology_state.py subcommand; return (exit_code, result_dict)."""
    argv = [sys.executable, str(STATE_SCRIPT), "--db", str(db), "--json", cmd] + _flatten(args)
    env = dict(os.environ)
    for label in _BASE_ENV_LABELS:
        env.pop(label, None)
    proc = subprocess.run(argv, capture_output=True, text=True, timeout=90, env=env)
    result = {}
    out = (proc.stdout or "").strip()
    if out:
        try:
            result = json.loads(out)
        except json.JSONDecodeError:
            result = {"_unparsed_stdout": out}
    if not out and proc.stderr.strip():
        result = {"_stderr": proc.stderr.strip()}
    return proc.returncode, result


def subset_ok(expect, got) -> bool:
    if isinstance(expect, dict):
        if not isinstance(got, dict):
            return False
        return all(k in got and subset_ok(v, got[k]) for k, v in expect.items())
    if isinstance(expect, list):
        return isinstance(got, list) and len(expect) == len(got) \
            and all(subset_ok(a, b) for a, b in zip(expect, got))
    return expect == got


def verify_body_sha(body_file, sha256, checks, label):
    if not body_file or not sha256:
        return
    fp = GOLDEN_DIR / body_file
    ok = fp.is_file() and hashlib.sha256(fp.read_bytes()).hexdigest() == sha256
    checks.append(("%s: fixture sha256 matches %s bytes" % (label, body_file), ok))


# ---------------------------------------------------------------------------
# Final-assertion probes (read the persisted ledger back through the CLI).
# ---------------------------------------------------------------------------
def export_anthology(db: Path, anthology_id: str, tmp: Path):
    out = tmp / ("bundle_%s.json" % anthology_id)
    rc, _ = run_cmd(db, "export-bundle",
                    {"--anthology-id": anthology_id, "--out": str(out)})
    if rc != 0 or not out.is_file():
        return None
    return json.loads(out.read_text(encoding="utf-8"))


def readiness(db: Path, anthology_id: str):
    rc, res = run_cmd(db, "assembly-readiness-report", {"--anthology-id": anthology_id})
    return res if rc == 0 else None


def anthology_of(key: str) -> str:
    return key.split("::", 1)[1] if "::" in key else ""


def run_final_assertions(db: Path, fx: dict, tmp: Path, checks: list):
    fa = fx.get("final_assertions", {})
    # Cache export bundles per anthology.
    needed = set()
    for key in fa.get("participants", {}):
        needed.add(anthology_of(key))
    for aid in fa.get("anthology", {}):
        needed.add(aid)
    for key in fa.get("keying", {}).get("same_contact_id", []) \
            + fa.get("keying", {}).get("distinct_anthology_id", []):
        needed.add(anthology_of(key))
    bundles = {aid: export_anthology(db, aid, tmp) for aid in needed if aid}
    part_index = {}
    for b in bundles.values():
        if b:
            for p in b.get("participants", []):
                part_index[p["participant_key"]] = p

    for key, want in fa.get("participants", {}).items():
        row = part_index.get(key)
        checks.append(("final: participant %s present" % key, row is not None))
        if row is not None:
            checks.append(("final: participant %s matches %s"
                           % (key, json.dumps(want, sort_keys=True)),
                           subset_ok(want, row)))

    for aid, want in fa.get("anthology", {}).items():
        b = bundles.get(aid)
        anth = b.get("anthology") if b else None
        checks.append(("final: anthology %s present" % aid, anth is not None))
        if anth is not None:
            checks.append(("final: anthology %s matches %s"
                           % (aid, json.dumps(want, sort_keys=True)),
                           subset_ok(want, anth)))

    for aid, want in fa.get("readiness", {}).items():
        r = readiness(db, aid)
        checks.append(("final: readiness %s present" % aid, r is not None))
        if r is not None:
            checks.append(("final: readiness %s matches %s"
                           % (aid, json.dumps(want, sort_keys=True)),
                           subset_ok(want, r)))

    keying = fa.get("keying")
    if keying:
        same = keying.get("same_contact_id", [])
        cids = {part_index[k]["contact_id"] for k in same if k in part_index}
        checks.append(("final: keying same_contact_id across %d rows" % len(same),
                       len(same) >= 2 and len(cids) == 1
                       and all(k in part_index for k in same)))
        distinct = keying.get("distinct_anthology_id", [])
        aids = [part_index[k]["anthology_id"] for k in distinct if k in part_index]
        checks.append(("final: keying distinct_anthology_id across %d rows" % len(distinct),
                       len(aids) == len(distinct) and len(set(aids)) == len(aids)))


# ---------------------------------------------------------------------------
# Fixture replay.
# ---------------------------------------------------------------------------
def replay_fixture(fixture_id: str, explain: bool = False):
    fx = json.loads(FIXTURE_FILES[fixture_id].read_text(encoding="utf-8"))
    checks = []
    tmp = Path(tempfile.mkdtemp(prefix="golden_%s_" % fixture_id))
    db = tmp / "state.db"

    # Expand steps (macros inline) and count.
    flat = []
    for step in fx["steps"]:
        if step.get("macro"):
            sub = expand_macro(step)
            flat.append(("macro-head", step, None))
            for s in sub:
                flat.append(("cmd", step, s))
            flat.append(("macro-tail", step, sub))
        else:
            flat.append(("cmd", step, step))

    if explain:
        print("== %s: expanded step plan ==" % fixture_id)
        i = 0
        for kind, parent, s in flat:
            if kind != "cmd":
                continue
            i += 1
            print("  %3d  %-24s %s" % (i, s["cmd"], json.dumps(s["args"], ensure_ascii=False)))
        print("  (%d executable subcommands)\n" % i)

    last_macro_final = {}
    for kind, parent, s in flat:
        if kind == "macro-head":
            continue
        if kind == "macro-tail":
            # verify the macro's final cursor if declared
            want = parent.get("expect_final_cursor")
            if want:
                checks.append(("macro %s -> final cursor %s"
                               % (parent["params"]["participant_key"], want),
                               last_macro_final.get(parent["params"]["participant_key"]) == want))
            continue
        cmd, args = s["cmd"], s.get("args", {})
        want_exit = s.get("expect_exit", 0)
        rc, res = run_cmd(db, cmd, args)
        n = parent.get("n") if parent is s else "%s.macro" % parent.get("n")
        label = "step %s [%s] %s" % (n, cmd, s.get("desc", "")[:60])
        checks.append(("%s -> exit %d (got %d)" % (label, want_exit, rc), rc == want_exit))
        exp = s.get("expect")
        if exp is not None:
            checks.append(("%s -> result subset" % label, subset_ok(exp, res)))
        # body-file sha self-consistency (record-artifact steps that name one)
        bf = s.get("body_file") or s.get("_body_file")
        if cmd == "record-artifact" and bf:
            verify_body_sha(bf, args.get("--sha256"), checks, label)
        # track macro final cursor
        if s.get("_macro") and cmd == "advance-stage" and args.get("--to") == "approved":
            last_macro_final[args["--participant-key"]] = res.get("to") or (
                "approved" if res.get("noop") else None)

    run_final_assertions(db, fx, tmp, checks)
    return checks


def verify_chapter_manifest(checks: list):
    if not MANIFEST.is_file():
        checks.append(("golden-manifest.json present", False))
        return
    man = json.loads(MANIFEST.read_text(encoding="utf-8"))
    for ch in man.get("chapters", []):
        fp = GOLDEN_DIR / ch["path"]
        ok = fp.is_file() and hashlib.sha256(fp.read_bytes()).hexdigest() == ch["sha256"]
        checks.append(("manifest: %s sha256 matches bytes" % ch["path"], ok))


# ---------------------------------------------------------------------------
# CLI.
# ---------------------------------------------------------------------------
def main(argv=None):
    ap = argparse.ArgumentParser(description="Replay + verify the Anthology Engine "
                                             "golden fixtures against the real ledger.")
    ap.add_argument("--fixture", choices=sorted(FIXTURE_FILES), help="replay one fixture")
    ap.add_argument("--all", action="store_true", help="replay every fixture")
    ap.add_argument("--list", action="store_true", help="list fixtures and exit")
    ap.add_argument("--explain", action="store_true", help="print the expanded step plan")
    ap.add_argument("--json", action="store_true", help="emit a machine-readable summary")
    a = ap.parse_args(argv)

    if a.list:
        for fid in sorted(FIXTURE_FILES):
            fx = json.loads(FIXTURE_FILES[fid].read_text(encoding="utf-8"))
            print("%-24s drills=%s  %s" % (fid, ",".join(fx.get("drills", [])), fx.get("title", "")))
        return 0

    if not STATE_SCRIPT.is_file():
        print("FATAL: ledger writer not found at %s "
              "(run from the skill checkout so scripts/anthology_state.py resolves)"
              % STATE_SCRIPT, file=sys.stderr)
        return 2

    targets = sorted(FIXTURE_FILES) if (a.all or not a.fixture) else [a.fixture]

    all_checks = []
    per_fixture = {}
    # Global: the chapter files referenced by the fixtures are byte-consistent.
    manifest_checks = []
    verify_chapter_manifest(manifest_checks)
    all_checks.extend(manifest_checks)

    for fid in targets:
        checks = replay_fixture(fid, explain=a.explain)
        per_fixture[fid] = checks
        all_checks.extend(checks)

    passed = sum(1 for _, ok in all_checks if ok)
    total = len(all_checks)
    overall = passed == total

    if a.json:
        print(json.dumps({
            "ok": overall, "passed": passed, "total": total,
            "fixtures": {fid: {"passed": sum(1 for _, ok in c if ok), "total": len(c),
                               "failures": [lbl for lbl, ok in c if not ok]}
                         for fid, c in per_fixture.items()},
            "manifest": {"passed": sum(1 for _, ok in manifest_checks if ok),
                         "total": len(manifest_checks)},
        }, indent=2, ensure_ascii=False))
        return 0 if overall else 1

    if manifest_checks:
        print("== chapter manifest ==")
        for lbl, ok in manifest_checks:
            print("  [%s] %s" % ("OK" if ok else "XX", lbl))
    for fid in targets:
        checks = per_fixture[fid]
        fp = sum(1 for _, ok in checks if ok)
        print("== golden fixture: %s (%d/%d) ==" % (fid, fp, len(checks)))
        for lbl, ok in checks:
            if not ok:
                print("  [XX] %s" % lbl)
        if fp == len(checks):
            print("  all %d checks passed" % len(checks))
    print("== golden replay: %s (%d/%d checks) =="
          % ("ALL PASSED" if overall else "FAILED", passed, total))
    return 0 if overall else 1


if __name__ == "__main__":
    sys.exit(main())
