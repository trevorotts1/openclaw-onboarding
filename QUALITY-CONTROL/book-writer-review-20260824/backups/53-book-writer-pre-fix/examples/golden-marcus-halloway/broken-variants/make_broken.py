#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""make_broken.py — the fail-closed proof for the golden-marcus-halloway sample.

Takes the PASSING golden BOOK run (mode=full) and applies ONE single-defect
mutation per AF-BK-* code, each crafted to trip a DISTINCT auto-fail across the
twelve fail-closed provers, and asserts every one is REJECTED (never silently
served). Read-only w.r.t. the checked-in golden run (mutations are applied to
in-memory copies). Writes ONLY REJECTION-RESULTS.json.

AUTHORING STATUS (Agent A): the mutation logic + the AF-BK map are FINAL and
reference the pinned GOLDEN-BOOK-BIBLE layout. Variants whose source is a DATA
anchor already shipped by Agent A (intake.json, stories.json, 433_Deck_Data.json,
RUN-LEDGER) run NOW. Variants that mutate Wave-2 PROSE (chapters / tone / outline /
challenge / blurb / cover) report {"blocked_on_prose": true} until that prose
exists; Agent D re-runs this AFTER Wave-2 authors the prose to light every variant.

Usage:
  python3 make_broken.py               # verify every present variant rejects; refresh REJECTION-RESULTS.json
  python3 make_broken.py --results <p> # write the results ledger to <p> (read-only tree; used by verify.sh)

Exit 0 = every PRESENT variant rejected with its expected code (blocked-on-prose
variants are not counted as failures); 1 = a present variant leaked.
"""
from __future__ import annotations
import argparse
import copy
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

HERE = Path(__file__).resolve().parent
GOLDEN = HERE.parent                         # examples/golden-marcus-halloway/
RUN = GOLDEN / "run"
SKILL_ROOT = GOLDEN.parents[1]               # 53-book-writer/
sys.path.insert(0, str(SKILL_ROOT / "scripts"))
import _bw_common as c                        # noqa: E402
import prove_bw_intake as p_intake            # noqa: E402
import prove_bw_titlelock as p_title          # noqa: E402
import prove_bw_stories as p_story            # noqa: E402
import prove_bw_chapters as p_chap            # noqa: E402
import prove_bw_continuity as p_cont          # noqa: E402
import prove_bw_tone as p_tone                # noqa: E402
import prove_bw_challenge as p_chal           # noqa: E402
import prove_bw_433 as p_433                  # noqa: E402
import prove_bw_placeholder as p_ph           # noqa: E402
import prove_bw_noanthropic as p_anth         # noqa: E402
import prove_bw_anon as p_anon                # noqa: E402
import prove_bw_process as p_proc             # noqa: E402


def _text(rel: str):
    p = RUN / rel
    return p.read_text(encoding="utf-8") if p.is_file() else None


def _json(rel: str):
    p = RUN / rel
    return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else None


def _chapters() -> Dict[int, str]:
    d = RUN / "chapters"
    out = {}
    if d.is_dir():
        for p in sorted(d.glob("ch*.md")):
            digits = "".join(ch for ch in p.stem if ch.isdigit())
            if digits:
                out[int(digits)] = p.read_text(encoding="utf-8")
    return out


def _manuscript(chaps: Dict[int, str], title: str, subtitle: str) -> str:
    parts = ["# %s\n## %s\n" % (title, subtitle)]
    for i in sorted(chaps):
        parts.append("\n\n# Chapter %d\n\n%s" % (i, chaps[i]))
    return "\n".join(parts)


def _fmt(vio):
    return "\n".join("VIOLATION [%s] %s" % (cd, m) for cd, m in vio) if vio else "(no violation)"


def _res(vio):
    return (2 if vio else 0), sorted({cd for cd, _ in vio}), _fmt(vio)


BLOCKED = ("__blocked__", [], "blocked_on_prose")


# ---- data-anchor variants (run NOW) -----------------------------------------
def v_intake_missing():
    i = copy.deepcopy(_json("intake.json"))
    i.pop("ideal_avatar", None)
    return _res(p_intake.evaluate(i).violations)


def v_version():
    i = copy.deepcopy(_json("intake.json"))
    i["version"] = ""
    return _res(p_intake.evaluate(i).violations)


def v_433_counts():
    titles = "\n".join("%d. t%d" % (n, n) for n in range(1, 30))   # 29, one short
    outcomes = "\n".join("%d. o%d" % (n, n) for n in range(1, 5))
    deck = _json("433/433_Deck_Data.json")
    return _res(p_433.evaluate(titles, outcomes, deck).violations)


def v_433_map():
    titles = "\n".join("%d. t%d" % (n, n) for n in range(1, 31))
    outcomes = "\n".join("%d. o%d" % (n, n) for n in range(1, 5))
    deck = copy.deepcopy(_json("433/433_Deck_Data.json"))
    deck["phases"][0]["chapters"] = deck["phases"][0]["chapters"][:2]  # 2 chapters
    return _res(p_433.evaluate(titles, outcomes, deck).violations)


def v_anthropic():
    led = _json("RUN-LEDGER.json") or {"stages": [{"stage": "13-create-outline", "model": "ollama-cloud/x"}]}
    led = copy.deepcopy(led)
    if led.get("stages"):
        led["stages"][0]["model"] = "anthropic/claude-opus-4"
    else:
        led = {"stages": [{"stage": "x", "model": "anthropic/claude-opus-4"}]}
    return _res(p_anth.evaluate(led, env={}).violations)


def v_anon():
    files = {"deliverable-meta.json": '{"client": "Northwind Retail Group"}'}
    return _res(p_anon.evaluate(files, ["Northwind Retail Group"]).violations)


def v_stage_skipped():
    steps = [{"phase_id": p, "ok": True} for p in
             ["P0-INTAKE", "P2-TONE", "P1-AVATAR", "P3-TITLES-GATE", "P4-OUTLINE-GATE",
              "P5-CHAPTERS", "P6-PACKAGE", "P7-QC", "P8-DELIVER"]]
    return _res(p_proc.check_stage_chain(steps).violations)


def v_process_integrity():
    steps = [{"phase_id": p, "ok": (p != "P5-CHAPTERS")} for p in p_proc.PHASE_ORDER]
    return _res(p_proc.check_stage_chain(steps).violations)


def v_hash_pin():
    files = [("a", b"x"), ("b", b"y")]
    return _res(p_proc.version_hash_pin(files, "deadbeef").violations)


def v_entry_bypass():
    src = {"upload.py": "requests.post('https://www.googleapis.com/drive/v3/files')"}
    return _res(p_proc.bypass_scan(src).violations)


# ---- prose-dependent variants (blocked until Wave-2 authors prose) ----------
def v_title_lock():
    chaps = _chapters()
    title, subtitle = p_title.parse_approved_title(_text("artifacts/APPROVED-TITLE.txt") or "")
    if not chaps:
        return BLOCKED
    bad = copy.deepcopy(chaps)
    k = min(bad)
    bad[k] = bad[k].replace(subtitle, subtitle.replace("Trust", "Power")) if subtitle in bad[k] \
        else bad[k] + "\n(subtitle intentionally dropped)"
    targets = {"chapter/%d" % n: bad[n] for n in bad}
    return _res(p_title.evaluate(title, subtitle, targets).violations)


def v_stories():
    chaps = _chapters()
    outline = _text("artifacts/13-outline.md")
    stories = _json("stories.json")
    if not chaps or outline is None:
        return BLOCKED
    title, subtitle = p_title.parse_approved_title(_text("artifacts/APPROVED-TITLE.txt") or "")
    manu = _manuscript(chaps, title, subtitle)
    key = stories[0]["key_phrase"]
    manu_bad = manu.replace(key, "did some routine work")
    return _res(p_story.evaluate(stories, outline, manu_bad).violations)


def v_chap_count():
    chaps = _chapters()
    if not chaps:
        return BLOCKED
    bad = dict(sorted(chaps.items())[:-1])   # drop chapter 12
    return _res(p_chap.evaluate(bad).violations)


def v_chap_len():
    chaps = _chapters()
    if not chaps:
        return BLOCKED
    bad = copy.deepcopy(chaps)
    k = sorted(bad)[6] if len(bad) >= 7 else min(bad)
    bad[k] = "# short chapter\n\nfar too short to be a real chapter."
    return _res(p_chap.evaluate(bad).violations)


def v_continuity():
    chaps = _chapters()
    receipts = {}
    for stage, bnum, _ in p_cont.BATCHES:
        r = _json("receipts/G-STAGE-%s.json" % stage)
        if r is not None:
            receipts[bnum] = r
    if not chaps or len(receipts) < 4:
        return BLOCKED
    csha = {n: hashlib.sha256(chaps[n].encode("utf-8")).hexdigest() for n in chaps}
    bad = copy.deepcopy(receipts)
    if 3 in bad:
        bad[3].get("prior_chapters_embedded", {}).pop("2", None)
    return _res(p_cont.evaluate(bad, csha).violations)


def v_tone_len():
    tone = _text("artifacts/08-blended-tone.md")
    if tone is None:
        return BLOCKED
    bad = "# The Marcus Halloway Tone\n" + " ".join(tone.split()[:400])   # truncate under floor
    return _res(p_tone.evaluate(bad).violations)


def v_challenge():
    ch = _text("artifacts/21-30day-challenge.md")
    if ch is None:
        return BLOCKED
    # drop one 'Day N —' heading -> 29
    lines, dropped = [], False
    for line in ch.splitlines():
        if not dropped and c._DAY_HEAD_RE.match(line):
            dropped = True
            continue
        lines.append(line)
    return _res(p_chal.evaluate("\n".join(lines)).violations)


def v_placeholder():
    chaps = _chapters()
    if not chaps:
        return BLOCKED
    bad = {"chapter/ch01.md": chaps[min(chaps)] + "\n\nDear {{intake.first_name}}, welcome."}
    return _res(p_ph.evaluate(bad).violations)


VARIANTS: List[Tuple[str, str, str, Any]] = [
    ("01_intake_missing", "AF-BK-INTAKE-MISSING", "prove_bw_intake.py", v_intake_missing),
    ("02_version_unset", "AF-BK-VERSION", "prove_bw_intake.py", v_version),
    ("03_title_lock", "AF-BK-TITLE-LOCK", "prove_bw_titlelock.py", v_title_lock),
    ("04_stories_dropped", "AF-BK-STORIES", "prove_bw_stories.py", v_stories),
    ("05_chap_count", "AF-BK-CHAP-COUNT", "prove_bw_chapters.py", v_chap_count),
    ("06_chap_len", "AF-BK-CHAP-LEN", "prove_bw_chapters.py", v_chap_len),
    ("07_continuity", "AF-BK-CONTINUITY", "prove_bw_continuity.py", v_continuity),
    ("08_tone_len", "AF-BK-TONE-LEN", "prove_bw_tone.py", v_tone_len),
    ("09_challenge", "AF-BK-CHALLENGE", "prove_bw_challenge.py", v_challenge),
    ("10_433_counts", "AF-BK-433-COUNTS", "prove_bw_433.py", v_433_counts),
    ("11_433_map", "AF-BK-433-MAP", "prove_bw_433.py", v_433_map),
    ("12_placeholder", "AF-BK-PLACEHOLDER", "prove_bw_placeholder.py", v_placeholder),
    ("13_anthropic", "AF-BK-ANTHROPIC", "prove_bw_noanthropic.py", v_anthropic),
    ("14_anon", "AF-BK-ANON", "prove_bw_anon.py", v_anon),
    ("15_stage_skipped", "AF-BK-STAGE-SKIPPED", "prove_bw_process.py", v_stage_skipped),
    ("16_process_integrity", "AF-BK-PROCESS-INTEGRITY", "prove_bw_process.py", v_process_integrity),
    ("17_hash_pin", "AF-BK-HASH-PIN", "prove_bw_process.py", v_hash_pin),
    ("18_entry_bypass", "AF-BK-ENTRY-BYPASS", "prove_bw_process.py", v_entry_bypass),
]


def main(argv):
    ap = argparse.ArgumentParser(description="Fail-closed proof for the golden Book Writer sample.")
    ap.add_argument("--results", help="path to write REJECTION-RESULTS.json (default: alongside this script)")
    args = ap.parse_args(argv)

    results: Dict[str, Any] = {}
    ok = True
    print("== golden-marcus-halloway :: broken-variant fail-closed proof ==")
    for name, expected, prover, fn in VARIANTS:
        out = fn()
        if out == BLOCKED:
            results[name] = {"prover": prover, "expected_code": expected, "blocked_on_prose": True,
                             "note": "awaiting Wave-2 golden prose; Agent D re-runs to light this variant"}
            print("  [BLOCKED] %-22s %-24s -> %s (awaiting Wave-2 prose)" % (name, prover, expected))
            continue
        rc, codes, text = out
        rejected = rc != 0 and expected in codes
        results[name] = {"prover": prover, "expected_code": expected, "rc": rc,
                         "rejected": bool(rejected), "got_codes": codes, "out": text}
        if rejected:
            print("  [REJECTED] %-22s %-24s -> %s (rc=%s)" % (name, prover, expected, rc))
        else:
            ok = False
            print("  [LEAK!]    %-22s %-24s expected %s, got %s (rc=%s)" % (name, prover, expected, codes, rc))

    out_path = Path(args.results) if args.results else (HERE / "REJECTION-RESULTS.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    print("  wrote %s" % out_path)
    present = [n for n, r in results.items() if not r.get("blocked_on_prose")]
    blocked = [n for n, r in results.items() if r.get("blocked_on_prose")]
    print("RESULT: %s — %d present variant(s) checked, %d blocked-on-prose"
          % ("PASS" if ok else "FAIL", len(present), len(blocked)))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
