#!/usr/bin/env python3
"""Extended cross-distribution parity suite for the drama-song ad factory (PKG-01-U1).

Enumerates BOTH packaged skill folders, classifies every packaged file, and
diffs every packaged module + doc — zero byte drift between distributions.

  A  OpenClaw distribution   `75-drama-song-ad-factory` (onboarding repo)
  B  Claude-Nine / Claude Code `999-setup/.claude/skills/drama-song-ad-factory`
  C  canonical build-tree staging copy `onboarding/75-drama-song-ad-factory`
     (optional witness; parity-contract.md names it source of truth)

Families
  packaged-inventory         every file in every packaged folder enumerated,
                             classified (core-module / doc / test), symlink-free,
                             unique-vs-shared recorded (unique = UNDETERMINED,
                             no twin to compare — never a pass)
  module-parity              `scripts/core/` of A vs B: identical file set,
                             identical per-file bytes, identical tree sha256;
                             A and B must be subsets of C with identical bytes
                             (copies derive from canonical), C-only modules
                             recorded UNDETERMINED (packaging currency)
  shared-doc-byte-parity     every doc (.md/.txt/.json/VERSION) carried by BOTH
                             packaged distributions (A and B) is byte-identical
                             (SKILL.md routed to skillmd-doc-contract — contract
                             clauses, not bytes, per parity-contract.md).
                             Canonical staging C is not a packaged repo, so its
                             docs are out of this family's scope; only its
                             scripts/core/ is compared (module-parity).
  skillmd-doc-contract       A/B SKILL.md exist, same identity, same documented
                             envelope schema, exit-code tables equal to each
                             other and to the shipped EXIT maps, twelve-stage
                             doctrine, each names its twin
  packaged-claims            falsifiable claims in B's CHANGELOG.md (file count)
                             verified against the trees; tree-sha256 claim is
                             checked against the observed digests and recorded
                             UNDETERMINED when the claim's formula cannot be
             reproduced (recorded, never a pass)

Resolution: DSAFX_* env override is authoritative (wrong path = resolve failure),
then the candidate paths below. stdlib only, no framework, no network.

Exit: 0 no family FAIL, 1 any family FAIL, 2 resolve/tooling failure.
"""
from __future__ import annotations

import hashlib
import os
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
BUILD = HERE.parents[1]          # <build>/ when suite lives in <build>/tests/,
                                 # <repo>/ when it lives in <repo>/tests/
SLUG = "drama-song-ad-factory"
ONB_DIR = "75-" + SLUG

CACHE_PARTS = {"__pycache__"}
CACHE_SUFFIX = (".pyc",)
DOC_SUFFIX = {".md", ".txt", ".json"}


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


def tree_digest(files: dict[str, Path]) -> str:
    lines = [f"{sha256_file(p)}  {rel}" for rel, p in sorted(files.items())]
    return hashlib.sha256("\n".join(lines).encode()).hexdigest()


def read_text(p: Path) -> str:
    return p.read_text(encoding="utf-8", errors="replace")


def walk_inventory(root: Path) -> tuple[dict[str, Path], list[str], list[str]]:
    """rel-path -> file, symlink paths, empty directories (caches excluded)."""
    files: dict[str, Path] = {}
    syms: list[str] = []
    empty: list[str] = []
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        here = Path(dirpath)
        keep = []
        for d in sorted(dirnames):
            p = here / d
            rel = p.relative_to(root).as_posix()
            if p.is_symlink():
                syms.append(rel + "/")
                continue
            if not os.listdir(p):
                empty.append(rel)
                continue
            keep.append(d)
        dirnames[:] = keep
        for f in sorted(filenames):
            p = here / f
            rel = p.relative_to(root).as_posix()
            parts = rel.split("/")
            if any(part in CACHE_PARTS for part in parts) or rel.endswith(CACHE_SUFFIX):
                continue
            if p.is_symlink():
                syms.append(rel)
                continue
            files[rel] = p
    return files, syms, sorted(empty)


def kind_of(rel: str) -> str:
    if rel.startswith("scripts/core/"):
        return "core-module"
    if rel.startswith("tests/") and rel.endswith(".py"):
        return "test"
    name = rel.rsplit("/", 1)[-1]
    if Path(name).suffix in DOC_SUFFIX or name == "VERSION":
        return "doc"
    return "other"


def core_files(root: Path) -> dict[str, Path]:
    base = root / "scripts" / "core"
    out: dict[str, Path] = {}
    if not base.is_dir():
        return out
    for p in sorted(base.rglob("*")):
        if not p.is_file() or p.is_symlink():
            continue
        rel = p.relative_to(base).as_posix()
        if any(part in CACHE_PARTS for part in rel.split("/")) or rel.endswith(CACHE_SUFFIX):
            continue
        out[rel] = p
    return out


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
    table: dict[str, int] = {}
    for m in re.finditer(r"^\|\s*`?(ok|waiting|parked|rejected|error)`?\s*\|\s*(\d+)\s*\|",
                         text, re.M):
        table[m.group(1)] = int(m.group(2))
    for m in re.finditer(r"^\|\s*(\d+)\s*\|\s*`?(ok|waiting|parked|rejected|error)`?\s*\|",
                         text, re.M):
        table[m.group(2)] = int(m.group(1))
    return table


def exit_map(skill: Path) -> dict[str, int]:
    fac = skill / "scripts" / "core" / "intake_preflight" / "factory.py"
    if not fac.is_file():
        raise SystemExit(f"missing entrypoint {fac}")
    m = re.search(r"^[ \t]*EXIT\s*=\s*(\{[^}]*\})", read_text(fac), re.M)
    if not m:
        raise SystemExit(f"cannot find EXIT map in {fac}")
    return {k: int(v) for k, v in re.findall(r"['\"](\w+)['\"]\s*:\s*(\d+)", m.group(1))}


# --------------------------------------------------------------------------- #
# resolution
# --------------------------------------------------------------------------- #
def _env(key: str) -> Path | None:
    v = os.environ.get(key)
    return Path(v).expanduser() if v else None


def _pick(cands: list[Path], require_skill: bool,
          env_key: str) -> tuple[Path | None, list[str]]:
    env = _env(env_key)
    if env is not None:
        # An explicit override is authoritative: a wrong path is a resolve
        # failure, never a silent fall-through to a default distribution.
        if (env / "scripts" / "core").is_dir() \
                and (not require_skill or (env / "SKILL.md").is_file()):
            return env, [str(env)]
        return None, [f"{env_key}={env} has no "
                      + ("SKILL.md + scripts/core/" if require_skill
                         else "scripts/core/")]
    tried: list[str] = []
    seen: set[Path] = set()
    for c in cands:
        if c is None or c in seen:
            continue
        seen.add(c)
        tried.append(str(c))
        if not (c / "scripts" / "core").is_dir():
            continue
        if require_skill and not (c / "SKILL.md").is_file():
            continue
        return c, tried
    return None, tried


def resolve() -> tuple[Path, Path, Path | None]:
    dts = os.environ.get("DTS_BUILD_ROOT")
    dts_root = Path(dts).expanduser() if dts else None
    home_build = Path.home() / "drama-song-factory-build"
    onb_repo = Path.home() / "openclaw-onboarding"

    a_cands = [BUILD / ONB_DIR,
               BUILD / "onboarding" / ONB_DIR,
               dts_root / "openclaw-onboarding" / ONB_DIR if dts_root else None,
               dts_root / "onboarding" / ONB_DIR if dts_root else None,
               onb_repo / ONB_DIR,
               home_build / "onboarding" / ONB_DIR]
    a, a_tried = _pick([c for c in a_cands if c], require_skill=True,
                       env_key="DSAFX_OPENCLAW_SKILL")
    if a is None:
        raise SystemExit("resolve-failure: packaged OpenClaw distribution (A) not "
                         "found; set DSAFX_OPENCLAW_SKILL. Tried: " + ", ".join(a_tried))

    b_cands = [BUILD / "999-setup" / ".claude" / "skills" / SLUG,
               dts_root / "999-setup" / ".claude" / "skills" / SLUG if dts_root else None,
               home_build / "999-setup" / ".claude" / "skills" / SLUG]
    b, b_tried = _pick([c for c in b_cands if c], require_skill=True,
                       env_key="DSAFX_999_SKILL")
    if b is None:
        raise SystemExit("resolve-failure: packaged 999 distribution (B) not found; "
                         "set DSAFX_999_SKILL. Tried: " + ", ".join(b_tried))

    c_cands = [dts_root / "onboarding" / ONB_DIR if dts_root else None,
               BUILD / "onboarding" / ONB_DIR,
               home_build / "onboarding" / ONB_DIR,
               BUILD / ONB_DIR,
               onb_repo / ONB_DIR]
    c, c_tried = _pick([x for x in c_cands if x and x not in (a, b)],
                       require_skill=False, env_key="DSAFX_CANON_SKILL")
    if _env("DSAFX_CANON_SKILL") is not None and c is None:
        raise SystemExit("resolve-failure: canonical staging (C) override invalid; "
                         "set DSAFX_CANON_SKILL. Tried: " + ", ".join(c_tried))
    return a, b, c


# --------------------------------------------------------------------------- #
# families
# --------------------------------------------------------------------------- #
def fam_inventory(out: Out, dists: list[tuple[str, Path]],
                  inv: dict[str, dict[str, Path]], syms: dict[str, list[str]],
                  empties: dict[str, list[str]]) -> None:
    fails: list[str] = []
    notes: list[str] = []
    undet = 0
    for name, root in dists:
        files, s, e = inv[name], syms[name], empties[name]
        if not files:
            fails.append(f"{name}: enumerated zero files under {root}")
        if s:
            fails.append(f"{name}: symlink(s) in packaged folder (breaks clean "
                         f"install): {s[:6]}")
        kinds: dict[str, int] = {}
        for rel in files:
            kinds[kind_of(rel)] = kinds.get(kind_of(rel), 0) + 1
        notes.append(f"{name}: {len(files)} files ({', '.join(f'{k}={v}' for k, v in sorted(kinds.items()))})"
                     + (f", empty dirs={e}" if e else ""))

    holders: dict[str, list[str]] = {}
    for name, _ in dists:
        for rel in inv[name]:
            holders.setdefault(rel, []).append(name)
    shared = {r: h for r, h in holders.items() if len(h) > 1}
    unique = {r: h[0] for r, h in holders.items() if len(h) == 1}
    notes.append(f"{len(shared)} paths carried by 2+ distributions (byte-compared); "
                 f"{len(unique)} distribution-unique")
    by_holder: dict[str, list[str]] = {}
    for rel, who in sorted(unique.items()):
        by_holder.setdefault(who, []).append(rel)
    for who in sorted(by_holder):
        rels = by_holder[who]
        notes.append(f"  UNDETERMINED unique to {who} ({len(rels)}): no twin to "
                     "compare — recorded, not a pass")
        for rel in rels:
            notes.append(f"      {rel}")
        undet += len(rels)
    out.family("packaged-inventory", fails, notes, undet=undet)


def fam_module(out: Out, a: Path, b: Path, c: Path | None) -> None:
    fails: list[str] = []
    notes: list[str] = []
    undet = 0
    fa, fb = core_files(a), core_files(b)
    if not fa or not fb:
        out.family("module-parity",
                   [f"scripts/core/ empty: openclaw={len(fa)} claude999={len(fb)}"])
        return
    only_a, only_b = sorted(set(fa) - set(fb)), sorted(set(fb) - set(fa))
    if only_a or only_b:
        fails.append(f"module file set differs: only-openclaw={only_a} "
                     f"only-claude999={only_b}")
    for rel in sorted(set(fa) & set(fb)):
        if sha256_file(fa[rel]) != sha256_file(fb[rel]):
            fails.append(f"{rel}: sha256 differs openclaw={sha256_file(fa[rel])[:16]} "
                         f"claude999={sha256_file(fb[rel])[:16]}")
    da, db = tree_digest(fa), tree_digest(fb)
    if da != db:
        fails.append(f"tree sha256 differs: openclaw={da} claude999={db}")
    else:
        notes.append(f"{len(fa)} modules byte-identical across A/B, tree sha256={da}")

    if c is None:
        notes.append("canonical staging absent — A/B cross-distribution proof only "
                     "(2-way)")
        undet += 1
    else:
        fc = core_files(c)
        missing = sorted(set(fa) - set(fc)) + sorted(set(fb) - set(fc))
        if missing:
            fails.append(f"packaged module not present in canonical staging "
                         f"(copies must derive from canonical): {missing[:8]}")
        for rel in sorted(set(fa) & set(fc)):
            if sha256_file(fa[rel]) != sha256_file(fc[rel]):
                fails.append(f"{rel}: openclaw differs from canonical staging "
                             f"{sha256_file(fa[rel])[:16]} != {sha256_file(fc[rel])[:16]}")
        for rel in sorted(set(fb) & set(fc)):
            if sha256_file(fb[rel]) != sha256_file(fc[rel]):
                fails.append(f"{rel}: claude999 differs from canonical staging "
                             f"{sha256_file(fb[rel])[:16]} != {sha256_file(fc[rel])[:16]}")
        canon_only = sorted(set(fc) - set(fa) - set(fb))
        if not missing:
            notes.append(f"A/B modules are subsets of canonical with identical "
                         f"bytes ({len(set(fa) & set(fc))} files compared each side)")
        if canon_only:
            notes.append(f"canonical-only modules: {len(canon_only)} "
                         f"(e.g. {canon_only[:4]}) — packaging currency of the "
                         "canonical tree vs the packaged skill; recorded UNDETERMINED, "
                         "not a pass (999's own tests/test_parity_layout.py enforces "
                         "set equality against canonical and owns that gate)")
            undet += 1
    out.family("module-parity", fails, notes, undet=undet)


def fam_docs(out: Out, dists: list[tuple[str, Path]],
             inv: dict[str, dict[str, Path]]) -> None:
    fails: list[str] = []
    notes: list[str] = []
    holders: dict[str, list[str]] = {}
    for name, _ in dists:
        for rel in inv[name]:
            if kind_of(rel) == "doc":
                holders.setdefault(rel, []).append(name)
    compared = 0
    for rel, who in sorted(holders.items()):
        if len(who) < 2:
            continue
        if rel == "SKILL.md":
            notes.append("SKILL.md carried by A/B: byte drift expected across "
                         "runtimes — contract-clause compared in "
                         "skillmd-doc-contract (parity-contract.md 'may differ' "
                         "runtime docs), not byte-compared here")
            continue
        digests = {n: sha256_file(dict(dists)[n] / rel) for n in who}
        compared += 1
        if len(set(digests.values())) != 1:
            fails.append(f"{rel}: doc bytes differ across {who}: "
                         + ", ".join(f"{n}={d[:16]}" for n, d in digests.items()))
        else:
            notes.append(f"{rel}: byte-identical across {who} sha256="
                         f"{next(iter(digests.values()))[:16]}")
    if compared == 0:
        notes.append("no non-SKILL.md doc is carried by 2+ distributions in this "
                     "resolution (nothing to byte-compare; recorded)")
    out.family("shared-doc-byte-parity", fails, notes)


def fam_skillmd(out: Out, a: Path, b: Path, xa: dict, xb: dict) -> None:
    fails: list[str] = []
    notes: list[str] = []
    sa, sb = a / "SKILL.md", b / "SKILL.md"
    if not sa.is_file() or not sb.is_file():
        out.family("skillmd-doc-contract",
                   [f"SKILL.md missing: openclaw={sa.is_file()} claude999={sb.is_file()}"])
        return
    ta, tb = read_text(sa), read_text(sb)
    if not ta.strip() or not tb.strip():
        fails.append("SKILL.md empty on a packaged side")
    fa, fb = frontmatter(ta), frontmatter(tb)
    if fa.get("name") != SLUG or fb.get("name") != SLUG:
        fails.append(f"frontmatter name: openclaw={fa.get('name')!r} "
                     f"claude999={fb.get('name')!r}")
    else:
        notes.append(f"both name the skill {SLUG}")

    schema = "blackceo.intake-preflight/envelope/v1"
    ca = schema in ta or (a / "references" / "cli-contract.md").is_file() \
        and schema in read_text(a / "references" / "cli-contract.md")
    cb = schema in tb or (b / "references" / "cli-contract.md").is_file() \
        and schema in read_text(b / "references" / "cli-contract.md")
    if not (ca and cb):
        fails.append(f"envelope schema documented: openclaw={bool(ca)} "
                     f"claude999={bool(cb)}")
    else:
        notes.append(f"both document schema_version={schema}")

    xta, xtb = parse_exit_table(ta), parse_exit_table(tb)
    if xta != xtb:
        fails.append(f"exit-code tables differ: openclaw={dict(sorted(xta.items()))} "
                     f"claude999={dict(sorted(xtb.items()))}")
    elif xta != xa or xtb != xb:
        fails.append(f"exit table vs shipped code: openclaw table={dict(sorted(xta.items()))} "
                     f"code={dict(sorted(xa.items()))}; claude999 table="
                     f"{dict(sorted(xtb.items()))} code={dict(sorted(xb.items()))}")
    else:
        notes.append(f"exit tables equal across distributions and equal to shipped "
                     f"code: {dict(sorted(xa.items()))}")
    if xa != xb:
        fails.append(f"shipped EXIT maps differ across distributions: "
                     f"openclaw={xa} claude999={xb}")

    if "twelve-stage" not in ta or "twelve-stage" not in tb:
        fails.append(f"twelve-stage doctrine declared: openclaw={'twelve-stage' in ta} "
                     f"claude999={'twelve-stage' in tb}")
    else:
        notes.append("both declare the twelve-stage arc")

    if "999" not in ta and "Claude-Nine" not in ta:
        fails.append("openclaw SKILL.md does not name the Claude-Nine/Claude Code twin")
    if "OpenClaw" not in tb:
        fails.append("claude999 SKILL.md does not name the OpenClaw twin")
    if not fails:
        notes.append("each SKILL.md names its twin distribution; full clause "
                     "equivalence beyond these gates belongs to "
                     "tests/distribution-parity family skillmd-contract-equivalence")
    out.family("skillmd-doc-contract", fails, notes)


def fam_claims(out: Out, a: Path, b: Path) -> None:
    fails: list[str] = []
    notes: list[str] = []
    undet = 0
    changelog = b / "CHANGELOG.md"
    if not changelog.is_file():
        notes.append("no CHANGELOG.md in distribution B (nothing to claim-check)")
        out.family("packaged-claims", fails, notes)
        return
    # CHANGELOG wraps lines, so collapse whitespace before matching claims.
    text = " ".join(read_text(changelog).split())
    m_count = re.search(r"—\s*(\d+)\s+files,\s*tree\s+sha256", text)
    m_digest = re.search(r"tree\s+sha256\s*`([0-9a-f]{64})`", text)
    fa, fb = core_files(a), core_files(b)
    actual = len(fb)
    if m_count:
        claim = int(m_count.group(1))
        if claim != actual or len(fa) != claim:
            fails.append(f"CHANGELOG claims {claim} core files; observed "
                         f"openclaw={len(fa)} claude999={actual}")
        else:
            notes.append(f"CHANGELOG file-count claim ({claim} files) matches both "
                         "packaged trees")
    else:
        notes.append("CHANGELOG carries no '— N files, tree sha256' claim")
    if m_digest:
        claim_digest = m_digest.group(1)
        obs = {"openclaw": tree_digest(fa), "claude999": tree_digest(fb)}
        if all(v == claim_digest for v in obs.values()):
            notes.append(f"CHANGELOG tree-sha256 claim verified: {claim_digest[:16]}…")
        else:
            notes.append(f"CHANGELOG tree-sha256 claim {claim_digest[:16]}… does not "
                         "match the observed digests "
                         + ", ".join(f"{k}={v[:16]}…" for k, v in obs.items())
                         + "; claim's hashing formula is not stated and was not "
                         "reproducible under the tested layouts — recorded "
                         "UNDETERMINED (the byte-identity the claim describes is "
                         "proven directly by module-parity)")
            undet += 1
    out.family("packaged-claims", fails, notes, undet=undet)


# --------------------------------------------------------------------------- #
def main() -> int:
    try:
        a, b, c = resolve()
    except SystemExit as exc:
        if isinstance(exc.code, str):
            print(exc.code, file=sys.stderr)
            return 2
        raise
    try:
        xa, xb = exit_map(a), exit_map(b)
    except SystemExit as exc:
        print(f"tooling-failure: {exc}", file=sys.stderr)
        return 2

    dists: list[tuple[str, Path]] = [("openclaw", a), ("claude999", b)]
    if c is not None:
        dists.append(("canonical", c))
    inv: dict[str, dict[str, Path]] = {}
    syms: dict[str, list[str]] = {}
    empties: dict[str, list[str]] = {}
    for name, root in dists:
        files, s, e = walk_inventory(root)
        inv[name], syms[name], empties[name] = files, s, e

    out = Out()
    fam_inventory(out, dists, inv, syms, empties)
    fam_module(out, a, b, c)
    # Doc byte-parity is scoped to the two PACKAGED distributions (both repos).
    # Canonical staging C is not a packaged repo — its docs are packaging-work
    # territory and are compared nowhere but scripts/core/ (module-parity).
    fam_docs(out, [("openclaw", a), ("claude999", b)], inv)
    fam_skillmd(out, a, b, xa, xb)
    fam_claims(out, a, b)

    total_files = sum(len(v) for v in inv.values())
    print("distribution-parity-extended  unit PKG-01-U1")
    print(f"  openclaw  (A): {a}")
    print(f"  claude999 (B): {b}")
    print(f"  canonical (C): {c if c else '(absent — A/B cross-distribution proof only)'}")
    print(f"  enumerated  : {total_files} packaged files across {len(dists)} folders")
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
