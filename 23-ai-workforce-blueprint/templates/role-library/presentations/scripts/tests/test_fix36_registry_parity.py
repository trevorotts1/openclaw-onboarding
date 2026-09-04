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
  4. (FIX 82) No registry row marked DOCTRINE-ONLY may name a code the
     manifest enforces with a py_symbol — a wired gate understated as
     doctrine fails here (R6 J10-11).
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


# ---------------------------------------------------------------------------
# 2. FIX 82 leg: a DOCTRINE-ONLY row may never carry a py_symbol.
# ---------------------------------------------------------------------------
#
# A DOCTRINE-ONLY registration means "no mechanical enforcement exists" (the
# registry's own definition, section 2). The moment the manifest assigns that
# code a py_symbol — a real `_chk_*` callable in build_deck.py — the row is a
# LIE: it understates live enforcement and lets a wired gate be read as
# doctrine. That drift is exactly what FIX 82 (R6 J10-11) closed: the six
# North-Star rows in section 3.2 had sat at DOCTRINE-ONLY for months while the
# manifest v54 already enforced every one of them. This leg makes any such
# regression fail the parity test: either flip the row to REGISTERED or remove
# the py_symbol from the manifest — one of the two, never both true at once.

def _manifest_py_symbol_map() -> dict:
    """code -> py_symbol for every manifest autofail that declares one."""
    m = load_manifest()
    return {
        a["code"]: a["py_symbol"]
        for a in m["autofails"]
        if isinstance(a, dict) and a.get("code") and a.get("py_symbol")
    }


def _doctrine_only_rows() -> list:
    """(af_code, py_symbols_found_in_the_row, line_number) for every registry
    table row whose Registration cell says DOCTRINE-ONLY."""
    text = REGISTRY_DOC.read_text(encoding="utf-8", errors="replace")
    rows = []
    for lineno, ln in enumerate(text.splitlines(), 1):
        s = ln.strip()
        if not s.startswith("|"):
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        if len(cells) < 4:
            continue
        if not any("DOCTRINE-ONLY" == c for c in cells):
            continue
        row_text = "| " + " | ".join(cells) + " |"
        rows.append((AF_RE.findall(cells[0]), AF_RE.findall(row_text), lineno))
    return rows


def test_no_doctrine_only_row_has_a_py_symbol():
    """FIX 82: any code whose manifest autofail entry carries a py_symbol is
    machine-enforced; a registry row marking it DOCTRINE-ONLY contradicts the
    manifest and must fail."""
    py_symbol_codes = _manifest_py_symbol_map()
    stale = []
    for first_col_codes, row_codes, lineno in _doctrine_only_rows():
        for code in first_col_codes:
            if code in py_symbol_codes:
                stale.append(
                    f"{code} (row line {lineno}, py_symbol "
                    f"{py_symbol_codes[code]})")
    assert not stale, (
        f"{len(stale)} registry row(s) still marked DOCTRINE-ONLY while the "
        f"manifest enforces them with a py_symbol (FIX 82): {stale}. Flip the "
        f"row to REGISTERED (see registry section 4) — the gate is wired, the "
        f"ledger must not say otherwise.")


def test_fix82_flipped_rows_are_registered_in_doc():
    """The six North-Star codes flipped by FIX 82 must now read REGISTERED in
    their section-3.2 rows (the row text must not match DOCTRINE-ONLY) and
    must each carry a py_symbol in the manifest."""
    text = REGISTRY_DOC.read_text(encoding="utf-8", errors="replace")
    py_symbol_codes = _manifest_py_symbol_map()
    for code in ("AF-PRIORITY-SHIFT", "AF-PEAK-END", "AF-NO-SALIENCE-APEX",
                 "AF-MODE-UNSET", "AF-NO-SHIFT", "AF-PROCLAMATION-HEDGE"):
        row = next((ln for ln in text.splitlines()
                    if ln.strip().startswith(f"| {code} |")), None)
        assert row is not None, f"{code} lost from the registry entirely"
        assert "DOCTRINE-ONLY" not in row, (
            f"{code} is manifest-enforced with py_symbol "
            f"{py_symbol_codes.get(code)} but its registry row still says "
            f"DOCTRINE-ONLY (FIX 82 flip incomplete)")
        assert code in py_symbol_codes, (
            f"{code} flipped to REGISTERED by FIX 82 but the manifest no "
            f"longer declares a py_symbol for it — re-verify the manifest")