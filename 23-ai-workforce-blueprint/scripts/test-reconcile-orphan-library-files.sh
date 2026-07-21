#!/usr/bin/env bash
# test-reconcile-orphan-library-files.sh — hermetic proof that canonical
# DELETIONS can be reconciled on a box WITHOUT it ever being possible to remove
# client-authored content.
#
# T0  REPRODUCTION — emulates install.sh:3165 (`cp -r archive/* staging/`) and
#     asserts a retired file SURVIVES the merge-copy. That is the defect: the
#     staging tree is additive and never pruned. This test FAILS on a tree
#     where the copy prunes, so the reproduction can never become theater.
# T1  DRY-RUN (the default) reports every orphan, rc 10, and moves NOTHING.
# T2  CLIENT-AUTHORED files are NEVER touched — dry-run or --apply. This is the
#     most important assertion in this file.
# T3  --apply QUARANTINES (moves, never unlinks): originals gone, quarantine
#     copies byte-identical, manifest.json written.
# T4  --restore puts a batch back byte-identical.
# T5  A retired path with LOCALLY MODIFIED bytes is a CONFLICT: reported, rc 4,
#     NEVER removed — dry-run or --apply.
# T6  A healthy tree (only live canonical files) is rc 0 with zero orphans.
# T7  IDEMPOTENT: a second --apply is a no-op, rc 0.
# T8  COLD BACKUPS (backups/, updater-src-*, *.bak-*) are never even walked.
# T9  A client's MATERIALIZED workforce (workspace/departments/**) is
#     structurally unreachable even when handed in as a scan root.
# T10 FAIL LOUD: missing / corrupt / schema-wrong / provenance-less ledger and
#     an empty manifest are each rc 2 with ZERO deletions.
# T11 A symlink at a retired path is UNREADABLE: rc 4, never followed, never
#     removed.
# T12 A ledger/manifest contradiction (same path listed live AND retired) is
#     rc 2 with zero deletions.
#
# Hermetic: builds its own mktemp sandbox, pins the manifest/ledger/roots via
# CLI flags, and touches nothing under ~/.openclaw or the repo.
# Exit 0 = all pass; 1 = at least one failed.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

python3 - "$SKILL_DIR" <<'PY'
import importlib.util, json, os, shutil, subprocess, sys, tempfile
from pathlib import Path

SKILL = Path(sys.argv[1])
TOOL = SKILL / "scripts" / "reconcile-orphan-library-files.py"
HCM = SKILL / "scripts" / "hash-content-manifest.py"

PASS = 0
FAIL = 0


def ok(m):
    global PASS
    PASS += 1
    print(f"  PASS: {m}")


def bad(m):
    global FAIL
    FAIL += 1
    print(f"  FAIL: {m}")


def chk(cond, m):
    ok(m) if cond else bad(m)


for p in (TOOL, HCM):
    if not p.is_file():
        print(f"  FAIL: required script missing: {p}")
        print("RESULT: FAIL (1 failed)")
        sys.exit(1)

spec = importlib.util.spec_from_file_location("hcm", HCM)
hcm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hcm)

LIB = "templates/role-library"
SK = "23-ai-workforce-blueprint"

DEAD_REL = f"{LIB}/graphics/sops/chief-design-officer-sops.md"
DEAD2_REL = f"{LIB}/presentations/sops/deck-discovery-strategist-sops.md"
LIVE_REL = f"{LIB}/graphics/sops/SOP--chief-design-officer-sops.md"
CLIENT_REL = f"{LIB}/graphics/sops/client-custom-sop.md"
# Same BASENAME as a retired file but a different department: the cheap
# basename prefilter must never be mistaken for the match.
DECOY_REL = f"{LIB}/sales/sops/chief-design-officer-sops.md"

DEAD_BODY = ("# Chief Design Officer SOPs\n\n**Last updated:** 2026-06-01\n"
             "**Version:** 1.0.0\n\nSUPERSEDED content that must not be read.\n")
DEAD2_BODY = "# Deck Discovery Strategist SOPs\n\nretired at the rename.\n"
LIVE_BODY = "# SOP-- Chief Design Officer\n\nthe CURRENT enhanced version.\n"
CLIENT_BODY = "# Our own SOP\n\nwritten by the client. Must never be removed.\n"
MODIFIED_BODY = DEAD2_BODY + "\nthe client added this paragraph.\n"

DEAD_SHA = hcm.content_sha_of_text(DEAD_BODY)
DEAD2_SHA = hcm.content_sha_of_text(DEAD2_BODY)


def write(path, body):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


def make_ledger(tmp, *, schema="openclaw/retired-artifacts@2", shas=True, shallow=False):
    arts = [
        {"lib_path": "templates/role-library/x.md" if shallow else DEAD_REL,
         "repo_path": f"{SK}/{DEAD_REL}", "dept": "graphics",
         "file": "chief-design-officer-sops.md", "kind": "sop",
         "content_shas": [DEAD_SHA] if shas else [],
         "retired_in": "34e4b6a3", "retired_at": "2026-07-05T11:33:49-04:00"},
        {"lib_path": DEAD2_REL, "repo_path": f"{SK}/{DEAD2_REL}", "dept": "presentations",
         "file": "deck-discovery-strategist-sops.md", "kind": "sop",
         "content_shas": [DEAD2_SHA], "retired_in": "f5942a68",
         "retired_at": "2026-06-12T14:00:15-04:00"},
    ]
    p = Path(tmp) / "_retired.json"
    p.write_text(json.dumps({
        "schema": schema, "generated_at": "x", "source_ref": "x",
        "tracked_trees": [f"{SK}/{LIB}"], "algo": {"content_sha": "sha256"},
        "counts": {"artifacts": len(arts)}, "artifacts": arts,
    }, indent=1), encoding="utf-8")
    return p


def make_manifest(tmp, *, empty=False, clash=False):
    sops = [] if empty else [
        {"slug": "SOP--chief-design-officer-sops", "dept": "graphics",
         "path": LIVE_REL, "content_sha": "sha256:live"},
    ]
    if clash:
        sops.append({"slug": "x", "dept": "graphics", "path": DEAD_REL,
                     "content_sha": "sha256:clash"})
    p = Path(tmp) / "_index.json"
    p.write_text(json.dumps({"version": "test", "roles": [], "sops": sops,
                             "personas": []}, indent=1), encoding="utf-8")
    return p


def build_box(tmp):
    """A box carrying orphans in every measured surface, plus content that must
    survive: client-authored, live canonical, a same-basename decoy, cold
    backups, and a materialized workforce."""
    box = Path(tmp) / "box"
    # --- agent-reachable orphans (the 4 measured surfaces) ---
    orphans = [
        write(box / "skills" / SK / DEAD_REL, DEAD_BODY),                 # lagging live tree
        write(box / "skills" / "onboarding" / SK / DEAD_REL, DEAD_BODY),  # stray in skill path
        write(box / "skills" / DEAD_REL, DEAD_BODY),                      # skills/templates/... stray
        write(box / "onboarding" / SK / DEAD_REL, DEAD_BODY),             # staging checkout
    ]
    # --- must survive ---
    keep = [
        write(box / "skills" / SK / LIVE_REL, LIVE_BODY),        # live canonical
        write(box / "skills" / SK / CLIENT_REL, CLIENT_BODY),    # CLIENT-AUTHORED
        write(box / "onboarding" / SK / CLIENT_REL, CLIENT_BODY),
        write(box / "skills" / SK / DECOY_REL, DEAD_BODY),       # same basename, other dept
        write(box / "skills" / "backups" / SK / DEAD_REL, DEAD_BODY),          # cold backup
        write(box / "skills" / "skills-backup-20260701" / SK / DEAD_REL, DEAD_BODY),
        write(box / "onboarding" / "updater-src-20260701" / SK / DEAD_REL, DEAD_BODY),
        write(box / "skills" / "23-ai-workforce-blueprint.bak-20260701" / DEAD_REL, DEAD_BODY),
        write(box / "workspace" / "departments" / "graphics" / "sops"
              / "chief-design-officer-sops.md", DEAD_BODY),      # materialized workforce
    ]
    return box, orphans, keep


def run(box, manifest, ledger, *extra, roots=None):
    roots = roots if roots is not None else [box / "skills", box / "onboarding"]
    cmd = [sys.executable, str(TOOL), "--manifest", str(manifest), "--ledger", str(ledger),
           "--quarantine-root", str(box)]
    for r in roots:
        cmd += ["--root", str(r)]
    cmd += list(extra)
    p = subprocess.run(cmd, capture_output=True, text=True)
    return p.returncode, p.stdout + p.stderr


def sandbox():
    tmp = tempfile.mkdtemp(prefix="reconcile-orphan-test-")
    box, orphans, keep = build_box(tmp)
    return tmp, box, orphans, keep, make_manifest(tmp), make_ledger(tmp)


print("=" * 74)
print("T0 — REPRODUCTION: install.sh:3165 merge-copy leaves the retired file behind")
print("=" * 74)
_t = tempfile.mkdtemp(prefix="reconcile-orphan-repro-")
archive = Path(_t) / "openclaw-onboarding-main"
staging = Path(_t) / "onboarding"
write(archive / SK / LIVE_REL, LIVE_BODY)
write(staging / SK / DEAD_REL, DEAD_BODY)      # what a PRIOR release left behind
write(staging / SK / LIVE_REL, "older")
subprocess.run(f'cp -r "{archive}/"* "{staging}/"', shell=True, check=True)
chk((staging / SK / DEAD_REL).is_file(),
    "retired file SURVIVES the additive merge-copy (the defect is real)")
chk((staging / SK / LIVE_REL).read_text() == LIVE_BODY,
    "the merge-copy does overwrite files that still exist canonically")
shutil.rmtree(_t, ignore_errors=True)

print("=" * 74)
print("T1 — DRY-RUN is the default: reports, rc 10, moves nothing")
print("=" * 74)
tmp, box, orphans, keep, man, led = sandbox()
rc, out = run(box, man, led)
chk(rc == 10, f"dry-run rc == 10 (actionable orphans found) [got {rc}]")
chk(out.count("WOULD QUARANTINE") == 4, f"all 4 orphan surfaces reported "
    f"[got {out.count('WOULD QUARANTINE')}]")
chk("orphan=4" in out, "summary reports orphan=4")
chk(all(p.is_file() for p in orphans), "dry-run moved NO orphan")
chk(all(p.is_file() for p in keep), "dry-run moved NO protected file")
chk("QUARANTINED:" not in out, "dry-run never claims to have quarantined")

print("=" * 74)
print("T2 — CLIENT-AUTHORED content is NEVER touched (dry-run AND --apply)")
print("=" * 74)
client_files = [p for p in keep if p.name in ("client-custom-sop.md",)]
decoy = [p for p in keep if "sales" in p.parts][0]
chk(len(client_files) == 2, "fixture carries client-authored files in both roots")
chk(all(p.is_file() and p.read_text() == CLIENT_BODY for p in client_files),
    "client-authored files intact after dry-run")
chk(decoy.is_file(), "same-basename different-dept decoy intact after dry-run")
rc, out = run(box, man, led, "--apply")
chk(rc == 0, f"--apply rc == 0 (clean) [got {rc}]")
chk(all(p.is_file() and p.read_text() == CLIENT_BODY for p in client_files),
    "client-authored files intact after --apply  <<< PRIMARY SAFETY ASSERTION")
chk(decoy.is_file() and decoy.read_text() == DEAD_BODY,
    "same-basename different-dept decoy intact after --apply")
chk(not any(str(p) in out for p in client_files),
    "client-authored files are not even named as candidates")
live = [p for p in keep if p.name.startswith("SOP--")][0]
chk(live.is_file(), "live canonical file untouched")

print("=" * 74)
print("T3 — --apply QUARANTINES (moves, never unlinks)")
print("=" * 74)
chk(not any(p.exists() for p in orphans), "all 4 orphans removed from their trees")
batches = sorted((box / ".orphan-quarantine").iterdir())
chk(len(batches) == 1, f"exactly one quarantine batch created [got {len(batches)}]")
batch = batches[0]
manifest_json = batch / "manifest.json"
chk(manifest_json.is_file(), "quarantine manifest.json written")
qman = json.loads(manifest_json.read_text())
chk(len(qman["items"]) == 4, f"manifest records all 4 items [got {len(qman['items'])}]")
quarantined = [Path(i["quarantined_to"]) for i in qman["items"]]
chk(all(p.is_file() for p in quarantined), "every quarantined file exists on disk")
chk(all(p.read_text() == DEAD_BODY for p in quarantined),
    "quarantined bytes are identical to the originals (moved, not truncated)")
chk(qman["failures"] == [], "no move failures recorded")

print("=" * 74)
print("T4 — --restore returns a batch byte-identical")
print("=" * 74)
p = subprocess.run([sys.executable, str(TOOL), "--restore", str(batch)],
                   capture_output=True, text=True)
chk(p.returncode == 0, f"restore rc == 0 [got {p.returncode}]")
chk("RESTORE_STATUS ok=1 restored=4" in p.stdout, "restore reports 4 restored")
chk(all(o.is_file() and o.read_text() == DEAD_BODY for o in orphans),
    "every orphan is back at its original path with identical bytes")

print("=" * 74)
print("T5 — locally MODIFIED retired file is a CONFLICT, never an orphan")
print("=" * 74)
tmp5 = tempfile.mkdtemp(prefix="reconcile-orphan-conflict-")
box5 = Path(tmp5) / "box"
conflict = write(box5 / "skills" / SK / DEAD2_REL, MODIFIED_BODY)
man5, led5 = make_manifest(tmp5), make_ledger(tmp5)
rc, out = run(box5, man5, led5, roots=[box5 / "skills"])
chk(rc == 4, f"dry-run rc == 4 for a conflict [got {rc}]")
chk("CONFLICT (KEPT)" in out, "conflict is reported LOUDLY")
chk(conflict.is_file() and conflict.read_text() == MODIFIED_BODY,
    "conflicting file untouched in dry-run")
rc, out = run(box5, man5, led5, "--apply", roots=[box5 / "skills"])
chk(rc == 4, f"--apply rc == 4 for a conflict [got {rc}]")
chk(conflict.is_file() and conflict.read_text() == MODIFIED_BODY,
    "conflicting file NOT removed under --apply")
chk(not (box5 / ".orphan-quarantine").exists(), "no quarantine batch for a conflict")

print("=" * 74)
print("T6 — healthy tree: no-op, zero false positives")
print("=" * 74)
tmp6 = tempfile.mkdtemp(prefix="reconcile-orphan-healthy-")
box6 = Path(tmp6) / "box"
write(box6 / "skills" / SK / LIVE_REL, LIVE_BODY)
write(box6 / "skills" / SK / CLIENT_REL, CLIENT_BODY)
write(box6 / "onboarding" / SK / LIVE_REL, LIVE_BODY)
man6, led6 = make_manifest(tmp6), make_ledger(tmp6)
rc, out = run(box6, man6, led6, roots=[box6 / "skills", box6 / "onboarding"])
chk(rc == 0, f"healthy tree rc == 0 [got {rc}]")
chk("orphan=0 quarantined=0 conflict=0 problems=0" in out,
    "healthy tree reports zero of everything")

print("=" * 74)
print("T7 — idempotent: the second --apply is a no-op")
print("=" * 74)
rc1, _ = run(box, man, led, "--apply")           # box was restored in T4
before = len(sorted((box / ".orphan-quarantine").iterdir()))
rc2, out2 = run(box, man, led, "--apply")
after = len(sorted((box / ".orphan-quarantine").iterdir()))
chk(rc1 == 0, f"first --apply rc == 0 [got {rc1}]")
chk(rc2 == 0, f"second --apply rc == 0 [got {rc2}]")
chk("orphan=0 quarantined=0" in out2, "second run finds nothing to do")
chk(after == before, f"the no-op run creates no empty batch [{before} -> {after}]")

print("=" * 74)
print("T8 — cold backups are never walked")
print("=" * 74)
backups = [p for p in keep if any(
    c in ("backups", "skills-backup-20260701", "updater-src-20260701",
          "23-ai-workforce-blueprint.bak-20260701") for c in p.parts)]
chk(len(backups) == 4, f"fixture carries 4 cold-backup copies [got {len(backups)}]")
chk(all(p.is_file() and p.read_text() == DEAD_BODY for p in backups),
    "every cold-backup copy survived --apply  <<< rollback material preserved")

print("=" * 74)
print("T9 — a materialized workforce is structurally unreachable")
print("=" * 74)
mat = [p for p in keep if "departments" in p.parts][0]
rc, out = run(box, man, led, "--apply",
              roots=[box / "skills", box / "onboarding", box / "workspace"])
chk(mat.is_file() and mat.read_text() == DEAD_BODY,
    "workspace/departments/**/sops file untouched even when handed in as a root")
chk(str(mat) not in out, "materialized file is never even considered a candidate")

print("=" * 74)
print("T10 — fail loud: unusable ledger/manifest is rc 2 with zero deletions")
print("=" * 74)
tmpA, boxA, orphansA, keepA, manA, ledA = sandbox()
cases = []
missing = Path(tmpA) / "nope.json"
cases.append(("missing ledger", manA, missing))
corrupt = Path(tmpA) / "corrupt.json"
corrupt.write_text("{ not json", encoding="utf-8")
cases.append(("corrupt ledger", manA, corrupt))
cases.append(("wrong ledger schema", manA, make_ledger(tempfile.mkdtemp(), schema="v0")))
cases.append(("ledger entry with no content_shas", manA,
              make_ledger(tempfile.mkdtemp(), shas=False)))
cases.append(("ledger anchor too shallow", manA, make_ledger(tempfile.mkdtemp(), shallow=True)))
cases.append(("empty manifest", make_manifest(tempfile.mkdtemp(), empty=True), ledA))
for name, m, l in cases:
    rc, out = run(boxA, m, l, "--apply")
    chk(rc == 2, f"{name}: rc == 2 [got {rc}]")
    chk("FATAL:" in out, f"{name}: prints FATAL")
    chk("RECONCILE_STATUS ok=0 fatal=1" in out, f"{name}: status line says ok=0")
chk(all(p.is_file() for p in orphansA), "no file was deleted by any fatal run")
chk(all(p.is_file() for p in keepA), "no protected file was deleted by any fatal run")

print("=" * 74)
print("T11 — a symlink at a retired path is UNREADABLE, never followed")
print("=" * 74)
tmpB = tempfile.mkdtemp(prefix="reconcile-orphan-symlink-")
boxB = Path(tmpB) / "box"
real = write(Path(tmpB) / "outside" / "secret.md", CLIENT_BODY)
linkp = boxB / "skills" / SK / DEAD_REL
linkp.parent.mkdir(parents=True, exist_ok=True)
os.symlink(real, linkp)
manB, ledB = make_manifest(tmpB), make_ledger(tmpB)
rc, out = run(boxB, manB, ledB, "--apply", roots=[boxB / "skills"])
chk(rc == 4, f"symlink rc == 4 [got {rc}]")
chk("UNREADABLE (KEPT)" in out, "symlink reported as UNREADABLE")
chk(linkp.is_symlink(), "symlink not removed")
chk(real.is_file() and real.read_text() == CLIENT_BODY, "symlink target untouched")

print("=" * 74)
print("T12 — ledger/manifest contradiction is fatal")
print("=" * 74)
tmpC, boxC, orphansC, keepC, _, ledC = sandbox()
manC = make_manifest(tmpC, clash=True)
rc, out = run(boxC, manC, ledC, "--apply")
chk(rc == 2, f"contradiction rc == 2 [got {rc}]")
chk("listed as BOTH live and retired" in out, "contradiction named explicitly")
chk(all(p.is_file() for p in orphansC), "contradiction deleted nothing")

print("=" * 74)
print("T13 — the tool is WIRED, and dry-run is the default at both call sites")
print("=" * 74)
repo = SKILL.parent
for caller in ("update-skills.sh", "install.sh"):
    src = repo / caller
    if not src.is_file():
        bad(f"{caller}: not found at {src}")
        continue
    body = src.read_text(encoding="utf-8")
    chk("reconcile-orphan-library-files.py" in body,
        f"{caller}: invokes reconcile-orphan-library-files.py")
    chk("OPENCLAW_RECONCILE_ORPHANS" in body,
        f"{caller}: removal is gated behind OPENCLAW_RECONCILE_ORPHANS")
    apply_lines = [ln for ln in body.split("\n")
                   if "--apply" in ln and "reconcile-orphan" not in ln
                   and "RECONCILE_ORPHANS" in ln]
    chk(not apply_lines,
        f"{caller}: no unconditional --apply on the reconcile call")

for d in (tmp, tmp5, tmp6, tmpA, tmpB, tmpC):
    shutil.rmtree(d, ignore_errors=True)

print("=" * 74)
print(f"RESULT: {'PASS' if FAIL == 0 else 'FAIL'}  ({PASS} passed, {FAIL} failed)")
print("=" * 74)
sys.exit(1 if FAIL else 0)
PY
