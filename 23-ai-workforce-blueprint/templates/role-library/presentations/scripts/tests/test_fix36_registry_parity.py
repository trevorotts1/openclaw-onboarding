"""FIX 36(4) — enforcement-registry exact parity.

Spec (PRESENTATION-DEPT-FIX-SPEC.md, FIX 36 change 4): "bring the runtime
enforcement registry into exact parity with every documented enforced checker,
including FIX 15/18, and make missing entries fail the registry parity test".

The registry doc (universal-sops/presentation-slide-craft/
SOP-MECHANICAL-ENFORCEMENT-REGISTRY.md) is the human-facing ledger of every
declared auto-fail code. This test is the machine check §5 used to say could
not exist. Three legs, all failing LOUDLY on drift:

  1. EVERY manifest-enforced code (PIPELINE-MANIFEST.json autofails[]) must be
     named in the registry — the machine truth may never contain a code the
     ledger does not know about (FIX 15/18's loader codes
     AF-SLIDE-CRAFT-LOADER / AF-CRAFT-JUDGEMENT-LOADER included).
  2. The registry's §6 machine-checked appendix (generated from the manifest
     by scripts/gen_registry_parity.py) must be FRESH: re-derive the table
     from the manifest and compare — a manifest change without regenerating
     the appendix fails the parity test.
  3. Codes the registry lists as machine-checked that the manifest does NOT
     enforce must be reconciled: they are doctrine aliases/parents, and each
     must appear in the doc's documented alias table naming its manifest
     successor(s) — a silent mismatch is exactly the pre-FIX-36 disease.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))

from sync_check import AF_RE, load_manifest  # noqa: E402


def _repo_root() -> Path:
    cur = SCRIPTS
    for _ in range(12):
        if (cur / "universal-sops" / "presentation-slide-craft"
                / "PIPELINE-MANIFEST.json").is_file():
            return cur
        if cur.parent == cur:
            break
        cur = cur.parent
    raise AssertionError("repo root with the cluster manifest not found")


ROOT = _repo_root()
REGISTRY_DOC = (ROOT / "universal-sops" / "presentation-slide-craft"
                / "SOP-MECHANICAL-ENFORCEMENT-REGISTRY.md")
MANIFEST = ROOT / "universal-sops" / "presentation-slide-craft" / "PIPELINE-MANIFEST.json"


def _manifest_af_codes() -> set:
    m = load_manifest()
    return {a["code"] for a in m["autofails"] if isinstance(a, dict) and a.get("code")}


def _registry_codes() -> set:
    """Every AF code the registry names in a table row's first column."""
    text = REGISTRY_DOC.read_text(encoding="utf-8", errors="replace")
    codes = set()
    for ln in text.splitlines():
        s = ln.strip()
        if not s.startswith("|"):
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        if len(cells) >= 2 and cells[0] and cells[0].lower() != "af code":
            for code in AF_RE.findall(cells[0]):
                codes.add(code)
    return codes


def _doc_alias_table() -> set:
    """The parent/alias codes the doc explicitly declares as doctrine names
    whose enforcement lives under manifest successor codes (section 3.4)."""
    text = REGISTRY_DOC.read_text(encoding="utf-8", errors="replace")
    m = re.search(r"### 3\.4 Doctrine aliases(.*?)(?=\n## |\Z)", text, re.S)
    if not m:
        return set()
    aliases = set()
    for ln in m.group(1).splitlines():
        s = ln.strip()
        if not s.startswith("|"):
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        if len(cells) >= 2 and cells[0] and cells[0].lower() != "af code":
            for code in AF_RE.findall(cells[0]):
                aliases.add(code)
    return aliases


def _generated_parity_table() -> str:
    """Extract the §6 machine-checked appendix table verbatim from the doc."""
    text = REGISTRY_DOC.read_text(encoding="utf-8", errors="replace")
    m = re.search(r"<!-- BEGIN MACHINE-CHECKED PARITY TABLE -->\n(.*?)\n"
                  r"<!-- END MACHINE-CHECKED PARITY TABLE -->", text, re.S)
    assert m, (
        "SOP-MECHANICAL-ENFORCEMENT-REGISTRY.md lost its machine-checked "
        "parity appendix (the BEGIN/END markers). Regenerate it with "
        "23-ai-workforce-blueprint/scripts/gen_registry_parity.py."
    )
    return m.group(1)


def _rederive_parity_table() -> str:
    """Run the generator in dry-run mode and return the table it would write."""
    gen = ROOT / "23-ai-workforce-blueprint" / "scripts" / "gen_registry_parity.py"
    import subprocess
    r = subprocess.run(
        [sys.executable, str(gen), "--manifest", str(MANIFEST), "--dry-run"],
        capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, (
        f"gen_registry_parity.py --dry-run failed rc={r.returncode}\n"
        f"stdout: {r.stdout}\nstderr: {r.stderr}")
    return r.stdout.strip()


# ---------------------------------------------------------------------------
# 1. Every manifest-enforced code is named in the registry.
# ---------------------------------------------------------------------------

def test_every_manifest_code_is_in_the_registry():
    manifest_codes = _manifest_af_codes()
    registry = _registry_codes()
    missing = sorted(manifest_codes - registry)
    assert not missing, (
        f"{len(missing)} manifest-enforced AF code(s) absent from "
        f"SOP-MECHANICAL-ENFORCEMENT-REGISTRY.md (FIX 36(4) parity): "
        f"{missing}. Add them (or regenerate the appendix with "
        f"23-ai-workforce-blueprint/scripts/gen_registry_parity.py).")


def test_fix15_18_loader_codes_registered():
    """FIX 15/18's loader codes must be named by the registry explicitly."""
    registry = _registry_codes()
    for code in ("AF-SLIDE-CRAFT-LOADER", "AF-CRAFT-JUDGEMENT-LOADER"):
        assert code in registry, (
            f"{code} (FIX 15/18 loader gate) is enforced in the manifest but "
            "absent from the enforcement registry")


def test_machine_checked_codes_all_exist_in_manifest():
    """The §6 appendix is machine truth FROM the manifest; a code listed
    there that the manifest no longer declares means the doc is stale."""
    table = _generated_parity_table()
    in_table = set(AF_RE.findall(table))
    manifest_codes = _manifest_af_codes()
    stale = sorted(in_table - manifest_codes)
    assert not stale, (
        f"{len(stale)} code(s) in the machine-checked appendix are no longer "
        f"declared in PIPELINE-MANIFEST.json: {stale}. Regenerate with "
        f"23-ai-workforce-blueprint/scripts/gen_registry_parity.py.")


def test_appendix_matches_manifest_exactly():
    """The core parity leg: regenerate the appendix from the live manifest
    and require a byte-for-byte match. Any manifest autofail change without
    regenerating the registry fails here — missing entries can never pass."""
    expected = _rederive_parity_table()
    actual = _generated_parity_table()
    assert expected == actual, (
        "the machine-checked parity appendix is STALE vs "
        "PIPELINE-MANIFEST.json. Regenerate with: python3 23-ai-workforce-"
        "blueprint/scripts/gen_registry_parity.py\n"
        f"--- diff head (expected vs actual) ---\n"
        + "\n".join(
            f"- {e}" for e in expected.splitlines()[:8]
            if e not in actual.splitlines())
        + "\n" + "\n".join(
            f"+ {a}" for a in actual.splitlines()[:8]
            if a not in expected.splitlines()))


def test_doctrine_alias_codes_are_declared_not_silent():
    """Registry codes that the manifest does NOT enforce must be declared in
    the doc's 3.4 alias table with their manifest successors — never left
    sitting in an old table as if they were still machine-enforced."""
    registry = _registry_codes()
    manifest_codes = _manifest_af_codes()
    alias_declared = _doc_alias_table()
    undocumented = sorted((registry - manifest_codes) - alias_declared)
    assert not undocumented, (
        f"{len(undocumented)} registry code(s) are not manifest-enforced and "
        f"are not declared as doctrine aliases in section 3.4: "
        f"{undocumented}. Either register their manifest successor or add "
        f"them to 3.4 with the successor mapping.")