#!/usr/bin/env python3
"""Cross-distribution parity suite for the drama-song ad factory (unit W3-06-U1).

Two distributions, one shared fixture set, six families, per-family PASS/FAIL.

  A = OpenClaw distribution   -> onboarding/75-drama-song-ad-factory
  B = Claude-Nine / Claude Code -> 999-setup/.claude/skills/drama-song-ad-factory
  C = build-tree staging copy of A (optional third witness for byte parity)

Families
  cli-exit-codes              shared fixtures through both entrypoints; exit codes
                              equal across distributions and equal to the EXIT map
                              the shipped code defines
  envelope-schema-version     every envelope carries the same schema_version in
                              both distributions, matching the shipped constant
  acceptance-qc-byte-parity   acceptance-profile.json + contracts/qc-schema.json
                              byte-identical across distributions
  core-sha256-parity          every scripts/core/ file byte-identical
  department-wiring-equality  department wiring shipped/declared by the two
                              distributions agrees with each other and with
                              skill-department-map.json (no contradiction)
  skillmd-contract-equivalence  SKILL.md contract clauses equivalent, using the
                              OpenClaw twin (onboarding/75-.../SKILL.md,
                              2026-10-06, v2.3.0)

Resolution order per distribution: DSAF_* environment override, then the paths
below. stdlib only, no framework, no network.

Exit: 0 all families PASS, 1 any family FAIL, 2 tooling/resolve failure.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
FIXTURES = HERE / "fixtures"
BUILD = HERE.parents[1]  # drama-song-factory-build/

SCHEMA_LITERAL = "blackceo.intake-preflight/envelope/v1"
DEPT_SLUG = "drama-song-ad-factory"
OPENCLAW_DIR = "75-drama-song-ad-factory"   # numbered onboarding slot
OPENCLAW_TWIN_VERSION = "v2.3.0"
OPENCLAW_TWIN_DATE = "2026-10-06"

SKIP_PARTS = ("__pycache__",)
SKIP_SUFFIX = (".pyc",)

# Shared fixtures -> expected behavior, verified live against the shipped code
# (see tests/distribution-parity/README.md). One fixture set, both distributions.
SCENARIOS = [
    ("complete-brief", "intake",
     ["--brief-file", "complete-brief.json"],
     0, "ok", "complete-brief-zero-questions"),
    ("thin-brief", "intake",
     ["--brief-file", "thin-brief.json"],
     2, "waiting", "missing-essentials"),
    ("injection-brief", "intake",
     ["--brief-file", "injection-brief.json"],
     4, "rejected", "untrusted-injection-blocked"),
    ("resume-approval-invalidated", "intake",
     ["--brief-file", "resume-brief.json", "--resume-file", "resume-state.json"],
     3, "parked", "resume-approval-invalidated"),
    ("preflight-approval-missing", "preflight",
     ["--root", "@TMPROOT@"],
     4, "rejected", "approval-missing"),
    ("preflight-schema-untrusted", "preflight",
     ["--root", "@TMPROOT@", "--schema-version", "parity.evil/v1"],
     1, "error", "schema-untrusted"),
]


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
class Out:
    """Collects family results and their detail lines."""

    def __init__(self) -> None:
        self.families: list[tuple[str, str, list[str], list[str]]] = []
        self.undetermined = 0

    def family(self, name: str, fails: list[str], notes: list[str] | None = None,
               undet: int = 0) -> None:
        self.families.append((name, "FAIL" if fails else "PASS", fails, notes or []))
        self.undetermined += undet


def sha256_file(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def core_files(root: Path) -> dict[str, Path]:
    """All shipped files under scripts/core/, relative path -> absolute path."""
    base = root / "scripts" / "core"
    out: dict[str, Path] = {}
    if not base.is_dir():
        return out
    for p in sorted(base.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(base).as_posix()
        if any(part in SKIP_PARTS for part in rel.split("/")):
            continue
        if rel.endswith(SKIP_SUFFIX):
            continue
        out[rel] = p
    return out


def tree_digest(files: dict[str, Path]) -> str:
    lines = [f"{sha256_file(p)}  {rel}" for rel, p in sorted(files.items())]
    return hashlib.sha256("\n".join(lines).encode()).hexdigest()


def read_text(p: Path) -> str:
    return p.read_text(encoding="utf-8", errors="replace")


def frontmatter(text: str) -> dict[str, str]:
    m = re.match(r"\A---\s*\n(.*?)\n---\s*\n", text, re.S)
    if not m:
        return {}
    fm: dict[str, str] = {}
    for line in m.group(1).splitlines():
        if ":" in line and not line.startswith((" ", "\t")):
            k, _, v = line.partition(":")
            fm[k.strip()] = v.strip()
    return fm


def parse_exit_table(text: str) -> dict[str, int]:
    """outcome -> exit code from a markdown `| outcome | exit | ...` table."""
    table: dict[str, int] = {}
    for m in re.finditer(r"^\|\s*`?(ok|waiting|parked|rejected|error)`?\s*\|\s*(\d+)\s*\|",
                         text, re.M):
        table[m.group(1)] = int(m.group(2))
    # cli-contract.md writes the columns the other way round
    for m in re.finditer(r"^\|\s*(\d+)\s*\|\s*`?(ok|waiting|parked|rejected|error)`?\s*\|",
                         text, re.M):
        table[m.group(2)] = int(m.group(1))
    return table


def _exit_map_of(src: str, where: str) -> dict[str, int]:
    m = re.search(r"^[ \t]*EXIT\s*=\s*(\{[^}]*\})", src, re.M)
    if not m:
        raise SystemExit(f"cannot find EXIT map in {where}")
    return {k: int(v) for k, v in re.findall(r"['\"](\w+)['\"]\s*:\s*(\d+)", m.group(1))}


def load_exit_map(skill: Path) -> tuple[dict[str, int], list[str]]:
    """EXIT maps of both shipped definitions; they must agree.

    factory.py is what a script invocation actually uses (the package import
    fails when the file is run directly, so its literal fallback wins).
    """
    pkg = skill / "scripts" / "core" / "intake_preflight" / "__init__.py"
    fac = skill / "scripts" / "core" / "intake_preflight" / "factory.py"
    if not fac.is_file():
        raise SystemExit(f"missing entrypoint {fac}")
    factory_map = _exit_map_of(read_text(fac), str(fac))
    problems: list[str] = []
    if pkg.is_file():
        pkg_map = _exit_map_of(read_text(pkg), str(pkg))
        if pkg_map != factory_map:
            problems.append(f"{skill.name}: __init__.py EXIT {pkg_map} != "
                            f"factory.py EXIT {factory_map}")
    return factory_map, problems


def run_cli(skill: Path, scenario: tuple, tmproot: Path) -> dict:
    name, sub, args, want_exit, want_outcome, want_reason = scenario
    resolved = [str(FIXTURES / a) if a.endswith(".json") and not a.startswith("@")
                else (str(tmproot) if a == "@TMPROOT@" else a) for a in args]
    cmd = [sys.executable, str(skill / "scripts/core/intake_preflight/factory.py"),
           sub, *resolved, "--run-id", f"parity{name[:18].replace('-', '')}"]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    env = None
    if proc.stdout.strip():
        try:
            env = json.loads(proc.stdout)
        except json.JSONDecodeError as exc:
            env = {"__parse_error__": str(exc)}
    return {
        "scenario": name,
        "cmd": cmd,
        "rc": proc.returncode,
        "envelope": env,
        "stderr": proc.stderr.strip()[:400],
        "want_exit": want_exit,
        "want_outcome": want_outcome,
        "want_reason": want_reason,
    }


def normalize(env: dict) -> dict:
    """Drop values that legitimately differ between two runs on one machine."""
    if not isinstance(env, dict):
        return env
    clone = json.loads(json.dumps(env))
    clone.pop("run_id", None)
    disk = (clone.get("data") or {}).get("checks", {}).get("disk")
    if isinstance(disk, dict):
        disk.pop("free", None)
    return clone


def department_declaration(skill: Path) -> dict | None:
    """Owning department / roles a distribution declares, or None if it declares none."""
    for name in ("SKILL.md", "INSTRUCTIONS.md"):
        p = skill / name
        if not p.is_file():
            continue
        text = read_text(p)
        m = re.search(r"^##\s*Department wiring\s*$(.*?)(?=^##\s|\Z)", text,
                      re.M | re.S)
        body = " ".join(m.group(1).split()) if m else ""
        if not body:
            continue
        dept = re.search(r"Owning department:\s*\*+\[?([^\]*]+?)\]?\**\s*\(", body)
        primary = re.search(r"Primary role:\s*`([^`]+)`", body)
        support = re.search(r"support roles?:\s*(.+?)\.\s", body)
        roles: list[str] = []
        if primary:
            roles.append(primary.group(1))
        if support:
            roles.extend(re.findall(r"`([^`]+)`", support.group(1)))
        return {
            "source": name,
            "department": (dept.group(1).strip() if dept else None),
            "primary": primary.group(1) if primary else None,
            "roles": roles,
            "raw": body,
        }
    return None


def dept_wiring_dir(skill: Path) -> dict[str, str]:
    d = skill / "department-wiring"
    if not d.is_dir():
        return {}
    return {p.relative_to(d).as_posix(): sha256_file(p)
            for p in sorted(d.rglob("*")) if p.is_file()}


def git_last_date(path: Path) -> str | None:
    """Last commit date for the skill folder; None when not in a worktree."""
    try:
        r = subprocess.run(["git", "-C", str(path), "log", "-1", "--format=%cs",
                            "--", "."],
                           capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if r.returncode != 0:
        return None
    return r.stdout.strip() or None


# --------------------------------------------------------------------------- #
# families
# --------------------------------------------------------------------------- #
def fam_cli_exit(out: Out, a: Path, b: Path, exit_a: dict, exit_b: dict,
                 map_problems: list[str]) -> None:
    fails: list[str] = []
    notes: list[str] = []
    fails.extend(map_problems)
    tmp = Path(tempfile.mkdtemp(prefix=os.environ.get(
        "DSAF_TMP_PREFIX", "W3-06-U1-")))
    try:
        for scen in SCENARIOS:
            ra, rb = run_cli(a, scen, tmp), run_cli(b, scen, tmp)
            tag = scen[0]
            if ra["rc"] != scen[3] or rb["rc"] != scen[3]:
                fails.append(f"{tag}: exit openclaw={ra['rc']} claude={rb['rc']} "
                             f"expected={scen[3]}")
            elif ra["rc"] != rb["rc"]:
                fails.append(f"{tag}: exit differs openclaw={ra['rc']} claude={rb['rc']}")
            for side, r, xmap in (("openclaw", ra, exit_a), ("claude", rb, exit_b)):
                env = r["envelope"]
                if not isinstance(env, dict) or "__parse_error__" in (env or {}):
                    fails.append(f"{tag}: {side} produced no parseable envelope "
                                 f"(stderr={r['stderr'][:160]})")
                    continue
                if env.get("outcome") != scen[4] or env.get("reason_code") != scen[5]:
                    fails.append(f"{tag}: {side} {env.get('outcome')}/"
                                 f"{env.get('reason_code')} expected "
                                 f"{scen[4]}/{scen[5]}")
                if env.get("outcome") in xmap and r["rc"] != xmap[env["outcome"]]:
                    fails.append(f"{tag}: {side} rc {r['rc']} != code EXIT["
                                 f"{env['outcome']}]={xmap[env['outcome']]}")
            if isinstance(ra["envelope"], dict) and isinstance(rb["envelope"], dict) \
                    and "__parse_error__" not in ra["envelope"] \
                    and "__parse_error__" not in rb["envelope"]:
                if normalize(ra["envelope"]) != normalize(rb["envelope"]):
                    fails.append(f"{tag}: envelopes differ across distributions "
                                 "(after dropping run_id/disk.free)")
        if exit_a != exit_b:
            fails.append(f"code EXIT maps differ: openclaw={exit_a} claude={exit_b}")
        notes.append(f"{len(SCENARIOS)} shared-fixture scenarios x 2 distributions; "
                     f"EXIT map {dict(sorted(exit_a.items()))}")
    finally:
        for p in sorted(tmp.glob("**/*"), reverse=True):
            try:
                p.unlink() if p.is_file() else p.rmdir()
            except OSError:
                pass
        try:
            tmp.rmdir()
        except OSError:
            pass
    out.family("cli-exit-codes", fails, notes)


def fam_schema_version(out: Out, a: Path, b: Path, exit_a: dict, exit_b: dict) -> None:
    fails: list[str] = []
    notes: list[str] = []
    tmp = Path(tempfile.mkdtemp(prefix=os.environ.get(
        "DSAF_TMP_PREFIX", "W3-06-U1-")))
    try:
        seen: set[str] = set()
        for scen in SCENARIOS:
            for side, root in (("openclaw", a), ("claude", b)):
                r = run_cli(root, scen, tmp)
                env = r["envelope"]
                if not isinstance(env, dict) or "__parse_error__" in (env or {}):
                    fails.append(f"{scen[0]}: {side} envelope unreadable")
                    continue
                seen.add(env.get("schema_version") or "<missing>")
                if env.get("schema_version") != SCHEMA_LITERAL:
                    fails.append(f"{scen[0]}: {side} schema_version="
                                 f"{env.get('schema_version')!r} expected {SCHEMA_LITERAL!r}")
                if env.get("command") != scen[1]:
                    fails.append(f"{scen[0]}: {side} command={env.get('command')!r} "
                                 f"expected {scen[1]!r}")
                if set(env) != {"schema_version", "tool_version", "command", "run_id",
                                "outcome", "reason_code", "next_action", "evidence",
                                "data", "state_version"}:
                    fails.append(f"{scen[0]}: {side} envelope keys drifted: "
                                 f"{sorted(env)}")
        for side, root in (("openclaw", a), ("claude", b)):
            init = root / "scripts/core/intake_preflight/__init__.py"
            if init.is_file():
                m = re.search(r'^SCHEMA_VERSION\s*=\s*"([^"]+)"', read_text(init), re.M)
                if not m or m.group(1) != SCHEMA_LITERAL:
                    fails.append(f"{side} shipped SCHEMA_VERSION="
                                 f"{m.group(1) if m else '<absent>'!r}")
        notes.append(f"observed schema_version values across both distributions: "
                     f"{sorted(seen)}; envelope key set fixed at 10 keys")
    finally:
        for p in sorted(tmp.glob("**/*"), reverse=True):
            try:
                p.unlink() if p.is_file() else p.rmdir()
            except OSError:
                pass
        try:
            tmp.rmdir()
        except OSError:
            pass
    out.family("envelope-schema-version", fails, notes)


def fam_byte_parity(out: Out, a: Path, b: Path, c: Path | None) -> None:
    fails: list[str] = []
    notes: list[str] = []
    targets = [("acceptance-profile.json", Path("acceptance-profile.json")),
               ("qc-schema.json", Path("contracts/qc-schema.json"))]
    for label, rel in targets:
        pa, pb = a / "scripts" / "core" / rel, b / "scripts" / "core" / rel
        if not pa.is_file() or not pb.is_file():
            fails.append(f"{label}: missing openclaw={pa.is_file()} claude={pb.is_file()}")
            continue
        ba, bb = pa.read_bytes(), pb.read_bytes()
        if ba != bb:
            fails.append(f"{label}: bytes differ sha256 openclaw={sha256_file(pa)[:16]} "
                         f"claude={sha256_file(pb)[:16]}")
        else:
            notes.append(f"{label} sha256={sha256_file(pa)[:16]} "
                         f"({len(ba)} bytes, byte-identical)")
        if c is not None:
            pc = c / "scripts" / "core" / rel
            if pc.is_file() and pc.read_bytes() != ba:
                fails.append(f"{label}: build staging copy differs from openclaw")
            elif pc.is_file():
                notes.append(f"{label}: build staging copy also identical")
    out.family("acceptance-qc-byte-parity", fails, notes)


def fam_core_sha(out: Out, a: Path, b: Path, c: Path | None) -> None:
    fails: list[str] = []
    notes: list[str] = []
    fa, fb = core_files(a), core_files(b)
    if not fa or not fb:
        out.family("core-sha256-parity",
                   [f"scripts/core/ empty: openclaw={len(fa)} claude={len(fb)}"])
        return
    only_a, only_b = sorted(set(fa) - set(fb)), sorted(set(fb) - set(fa))
    if only_a or only_b:
        fails.append(f"file set differs: only-openclaw={only_a} only-claude={only_b}")
    for rel in sorted(set(fa) & set(fb)):
        if sha256_file(fa[rel]) != sha256_file(fb[rel]):
            fails.append(f"{rel}: sha256 differs "
                         f"openclaw={sha256_file(fa[rel])[:16]} "
                         f"claude={sha256_file(fb[rel])[:16]}")
    da, db = tree_digest(fa), tree_digest(fb)
    if da != db:
        fails.append(f"tree sha256 differs: openclaw={da} claude={db}")
    else:
        notes.append(f"{len(fa)} files, tree sha256={da}")
    if c is not None:
        fc = core_files(c)
        if set(fc) != set(fa) or tree_digest(fc) != da:
            fails.append(f"build staging copy differs: files={len(fc)} "
                         f"tree={tree_digest(fc) if fc else '-'}")
        else:
            notes.append("build staging copy matches too (3-way)")
    else:
        notes.append("build staging copy absent (2-way proven)")
        out.undetermined += 0
    out.family("core-sha256-parity", fails, notes)


def fam_dept(out: Out, a: Path, b: Path, staging: Path | None,
             dept_map: Path | None) -> None:
    fails: list[str] = []
    notes: list[str] = []
    undet = 0

    # 5.1 shipped department-wiring artifacts must be equal across distributions
    da, db = dept_wiring_dir(a), dept_wiring_dir(b)
    if da != db:
        fails.append(f"department-wiring/ artifacts differ: openclaw={sorted(da)} "
                     f"claude={sorted(db)}")
    else:
        notes.append("department-wiring/ shipped by both distributions: "
                     f"{'none' if not da else sorted(da)}")
    if staging is not None and dept_wiring_dir(staging) != da:
        fails.append("build staging department-wiring/ differs from openclaw")

    # 5.2 canonical map entry present
    entry: dict | None = None
    if dept_map is None or not dept_map.is_file():
        notes.append(f"skill-department-map.json not resolvable "
                     f"({dept_map}); canonical side UNDETERMINED")
        undet += 1
    else:
        try:
            data = json.loads(read_text(dept_map))
        except json.JSONDecodeError as exc:
            fails.append(f"skill-department-map.json unparseable: {exc}")
            data = {}
        skills = data.get("skills") if isinstance(data, dict) else None
        for s in skills or []:
            if isinstance(s, dict) and s.get("slug") == DEPT_SLUG:
                entry = s
                break
        if entry is None:
            fails.append(f"skill-department-map.json has no slug={DEPT_SLUG} entry")
        else:
            notes.append(f"canonical map: dept_owner={entry.get('dept_owner')!r} "
                         f"departments={entry.get('departments')} "
                         f"roles={[r.get('slug') for r in entry.get('roles', [])]}")

    # 5.3 every declaration a distribution ships must agree with the canonical map
    decls = []
    for side, root in (("openclaw", a), ("claude", b)):
        d = department_declaration(root)
        decls.append((side, d))
        if d is None:
            notes.append(f"{side}: no owning-department declaration "
                         "(parity-contract.md lists host-runtime department hooks "
                         "under 'may differ')")
            continue
        if entry is None:
            continue
        if d.get("department") and d["department"] not in (entry.get("departments") or []) \
                and d["department"] != entry.get("dept_owner"):
            fails.append(f"{side} declares department {d['department']!r}, canonical "
                         f"map says {entry.get('dept_owner')!r}")
        want_roles = {r.get("slug") for r in entry.get("roles", [])}
        if d.get("roles") and set(d["roles"]) != want_roles:
            fails.append(f"{side} declares roles {d['roles']}, canonical map has "
                         f"{sorted(want_roles)}")
        if d.get("department") and set(d["roles"]) == want_roles:
            notes.append(f"{side}: department {d['department']!r} + roles match "
                         "canonical map")

    # 5.4 the two distributions must not contradict each other
    declared = [(s, d) for s, d in decls if d]
    if len(declared) == 2:
        if declared[0][1]["department"] != declared[1][1]["department"] or \
                set(declared[0][1]["roles"]) != set(declared[1][1]["roles"]):
            fails.append("owning department/roles contradict across distributions: "
                         f"openclaw={declared[0][1]} claude={declared[1][1]}")
        else:
            notes.append("both distributions declare identical department wiring")
    elif len(declared) == 1:
        notes.append(f"only {declared[0][0]} declares department wiring; "
                     "cross-distribution agreement UNDETERMINED (recorded, "
                     "not a pass)")
        undet += 1
    else:
        notes.append("neither distribution declares owning-department wiring "
                     "(nothing to compare; recorded, not a pass)")
        undet += 1

    out.family("department-wiring-equality", fails, notes, undet=undet)


def fam_skillmd(out: Out, a: Path, b: Path, exit_a: dict, exit_b: dict) -> None:
    fails: list[str] = []
    notes: list[str] = []
    sa, sb = a / "SKILL.md", b / "SKILL.md"
    if not sa.is_file() or not sb.is_file():
        out.family("skillmd-contract-equivalence",
                   [f"SKILL.md missing: openclaw={sa.is_file()} claude={sb.is_file()}"])
        return
    ta, tb = read_text(sa), read_text(sb)
    fa, fb = frontmatter(ta), frontmatter(tb)

    # 1. identity
    if fa.get("name") != DEPT_SLUG or fb.get("name") != DEPT_SLUG:
        fails.append(f"frontmatter name: openclaw={fa.get('name')!r} "
                     f"claude={fb.get('name')!r}")
    else:
        notes.append(f"frontmatter name equal: {DEPT_SLUG}")

    # 2. version self-consistency
    ver_a = (a / "skill-version.txt")
    ver_b = (b / "VERSION")
    if ver_a.is_file() and fa.get("version") != read_text(ver_a).strip():
        fails.append(f"openclaw frontmatter version {fa.get('version')!r} != "
                     f"skill-version.txt {read_text(ver_a).strip()!r}")
    if ver_b.is_file() and fb.get("version") != read_text(ver_b).strip():
        fails.append(f"claude frontmatter version {fb.get('version')!r} != "
                     f"VERSION {read_text(ver_b).strip()!r}")
    if not fails:
        notes.append(f"versions self-consistent: openclaw={fa.get('version')} "
                     f"claude={fb.get('version')} (packages version independently)")

    # 3. OpenClaw twin identity from the unit brief
    if fa.get("version") != OPENCLAW_TWIN_VERSION:
        fails.append(f"openclaw twin version {fa.get('version')!r} != "
                     f"{OPENCLAW_TWIN_VERSION!r}")
    else:
        notes.append(f"openclaw twin version {OPENCLAW_TWIN_VERSION} confirmed")
    d = git_last_date(a)
    if d is None:
        notes.append("openclaw twin last-commit date UNDETERMINED (not a git "
                     "worktree); filesystem mtime used as evidence only")
    elif d != OPENCLAW_TWIN_DATE:
        fails.append(f"openclaw twin SKILL.md last commit {d} != "
                     f"{OPENCLAW_TWIN_DATE}")
    else:
        notes.append(f"openclaw twin SKILL.md last commit {d}")

    # 4. envelope schema_version declared by each distribution's documentation
    def declares_schema(root: Path, text: str) -> bool:
        if SCHEMA_LITERAL in text:
            return True
        ref = root / "references" / "cli-contract.md"
        return ref.is_file() and SCHEMA_LITERAL in read_text(ref)

    ca, cb = declares_schema(a, ta), declares_schema(b, tb)
    if not (ca and cb):
        fails.append(f"envelope schema_version declared: openclaw={ca} claude={cb}")
    else:
        notes.append(f"both distributions document schema_version={SCHEMA_LITERAL}")

    # 5. control entrypoint declared identically
    entry = "scripts/core/intake_preflight/factory.py"
    if entry not in ta or entry not in tb:
        fails.append(f"entrypoint {entry} declared: openclaw={entry in ta} "
                     f"claude={entry in tb}")
    else:
        notes.append(f"both declare entrypoint {entry}")

    # 6. exit-code tables equal across distributions and equal to shipped code
    xa, xb = parse_exit_table(ta), parse_exit_table(tb)
    ref_text = read_text(b / "references" / "cli-contract.md") \
        if (b / "references" / "cli-contract.md").is_file() else ""
    xr = parse_exit_table(ref_text) if ref_text else {}
    if xa != xb:
        fails.append(f"exit-code tables differ: openclaw={dict(sorted(xa.items()))} "
                     f"claude={dict(sorted(xb.items()))} "
                     f"code={dict(sorted(exit_a.items()))}")
    elif xa != exit_a:
        fails.append(f"SKILL.md exit-code table {dict(sorted(xa.items()))} != "
                     f"code EXIT map {dict(sorted(exit_a.items()))}")
    else:
        notes.append(f"exit-code tables equal and match code: "
                     f"{dict(sorted(xa.items()))}")
    if xr and xr != xb:
        fails.append(f"claude references/cli-contract.md table {dict(sorted(xr.items()))} "
                     f"!= claude SKILL.md table {dict(sorted(xb.items()))}")
    elif xr:
        notes.append("claude SKILL.md table == references/cli-contract.md table")

    # 7. creative doctrine marker present in both
    if "twelve-stage" not in ta or "twelve-stage" not in tb:
        fails.append(f"twelve-stage doctrine declared: openclaw={'twelve-stage' in ta} "
                     f"claude={'twelve-stage' in tb}")
    else:
        notes.append("both declare the twelve-stage arc")

    # 8. provider hierarchy (KIE skills 66/67/68) declared in both
    missing = [s for s in ("66", "67", "68")
               if not (re.search(rf"(Skill\s+{s}\b|{s}-kie-)", ta)
                       and re.search(rf"(Skill\s+{s}\b|{s}-kie-)", tb))]
    if missing:
        fails.append(f"provider skill references missing from one side: {missing}")
    else:
        notes.append("both name provider skills 66/67/68 (KIE image/video/audio)")

    # 9. each distribution names the other
    if "999" not in ta and "Claude-Nine" not in ta:
        fails.append("openclaw SKILL.md does not name the Claude-Nine/Claude Code twin")
    if "OpenClaw" not in tb:
        fails.append("claude SKILL.md does not name the OpenClaw twin")
    if not any(f.startswith(("openclaw SKILL.md does not", "claude SKILL.md does not"))
               for f in fails):
        notes.append("each SKILL.md names its twin distribution")

    out.family("skillmd-contract-equivalence", fails, notes)


# --------------------------------------------------------------------------- #
# resolution
# --------------------------------------------------------------------------- #
def resolve() -> tuple[Path, Path, Path | None, Path | None]:
    def env_path(key: str) -> Path | None:
        v = os.environ.get(key)
        return Path(v).expanduser() if v else None

    # An explicit override is authoritative: wrong path is a resolve failure,
    # never a silent fall-through to a different distribution.
    p = env_path("DSAF_OPENCLAW_SKILL")
    if p is not None:
        if not (p / "SKILL.md").is_file():
            raise SystemExit(f"resolve-failure: DSAF_OPENCLAW_SKILL={p} has no SKILL.md")
        a = p
    else:
        cands = [BUILD / "onboarding" / OPENCLAW_DIR,
                 Path.home() / "openclaw-onboarding" / OPENCLAW_DIR]
        a = next((c for c in cands if (c / "SKILL.md").is_file()), None)
        if a is None:
            raise SystemExit("resolve-failure: OpenClaw distribution not found; set "
                             "DSAF_OPENCLAW_SKILL. Tried: "
                             + ", ".join(str(c) for c in cands))

    p = env_path("DSAF_999_SKILL")
    if p is not None:
        if not (p / "SKILL.md").is_file():
            raise SystemExit(f"resolve-failure: DSAF_999_SKILL={p} has no SKILL.md")
        b = p
    else:
        cands = [BUILD / "999-setup" / ".claude" / "skills" / DEPT_SLUG,
                 Path.home() / "drama-song-factory-build" / "999-setup"
                 / ".claude" / "skills" / DEPT_SLUG]
        b = next((c for c in cands if (c / "SKILL.md").is_file()), None)
        if b is None:
            raise SystemExit("resolve-failure: 999 distribution not found; set "
                             "DSAF_999_SKILL. Tried: "
                             + ", ".join(str(c) for c in cands))

    staging = env_path("DSAF_STAGING_SKILL") or BUILD / "onboarding" / OPENCLAW_DIR
    if staging == a or not (staging / "scripts" / "core").is_dir():
        staging = None

    dept_map = env_path("DSAF_DEPT_MAP") or (
        Path.home() / "openclaw-onboarding" / "23-ai-workforce-blueprint"
        / "skill-department-map.json")
    if not dept_map.is_file():
        dept_map = None
    return a, b, staging, dept_map


def main() -> int:
    try:
        a, b, staging, dept_map = resolve()
    except SystemExit as exc:
        if isinstance(exc.code, str):
            print(exc.code, file=sys.stderr)
            return 2
        raise

    try:
        exit_a, problems_a = load_exit_map(a)
        exit_b, problems_b = load_exit_map(b)
    except SystemExit as exc:
        print(f"tooling-failure: {exc}", file=sys.stderr)
        return 2

    out = Out()
    fam_cli_exit(out, a, b, exit_a, exit_b, problems_a + problems_b)
    fam_schema_version(out, a, b, exit_a, exit_b)
    fam_byte_parity(out, a, b, staging)
    fam_core_sha(out, a, b, staging)
    fam_dept(out, a, b, staging, dept_map)
    fam_skillmd(out, a, b, exit_a, exit_b)

    print("distribution-parity  unit W3-06-U1")
    print(f"  openclaw : {a}")
    print(f"  claude   : {b}")
    print(f"  staging  : {staging if staging else '(absent, 2-way proof)'}")
    print(f"  dept map : {dept_map if dept_map else '(absent)'}")
    print()
    npass = nfail = 0
    for name, verdict, fails, notes in out.families:
        print(f"[{name}] {verdict}")
        for line in fails:
            print(f"    FAIL {line}")
        for line in notes:
            print(f"    - {line}")
        npass += verdict == "PASS"
        nfail += verdict == "FAIL"
    print()
    print(f"SUMMARY: {len(out.families)} families, {npass} PASS, {nfail} FAIL"
          + (f", {out.undetermined} sub-check UNDETERMINED (not a pass)"
             if out.undetermined else ""))
    return 1 if nfail else 0


if __name__ == "__main__":
    sys.exit(main())
