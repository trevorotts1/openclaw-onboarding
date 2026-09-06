#!/usr/bin/env python3
"""Regenerate (and CI-check) every phase table / version marker that restates
PIPELINE-MANIFEST.json.

WHY THIS EXISTS
---------------
`23-ai-workforce-blueprint/templates/role-library/presentations/00-START-HERE.md` is
the entry document for the Presentations department -- `dept-presentations` and its
role agents read it to learn the phase graph, and director-of-presentations SOP 9.6
(parallelization) plus the capacity engineer's Step 0.5 both plan fan-out from it.
It was found stating `manifest_version 55, 55 phases` while the live SSOT was
manifest_version 67 with 62 phases: SEVEN revisions of drift, four duplicated list
numbers ("14." four times), fifteen phases parked in a side list outside the
sequence, and 22 dead "Full contract: look it up in the manifest." stubs.

GATE 4 of scripts/ci/presentations-drift-gates.sh did not catch it because GATE 4
only asserts that every `phases[].id` is NAMED somewhere in the doc. Every id WAS
named. What drifted was the stated version, the stated count, and the ORDER --
none of which GATE 4 reads.

The cure is that no human hand-transcribes a phase table again. This script owns
those regions: `--write` regenerates them from the manifest, `--check` fails CI
when they disagree. GATE 7 of presentations-drift-gates.sh runs `--check`.

WHAT IT OWNS (and nothing else)
-------------------------------
1. 00-START-HERE.md -- the "Pipeline Sequence" generated region (the full ordered
   list of every phase) and its `(manifest_version V, N phases)` marker.
   PER-PHASE PROSE IS PRESERVED across regeneration: the generator reads the
   existing entry for each id and carries its description forward verbatim. Only
   the numbering, the ordering, the `(order ...)` metadata and the missing/stub
   entries are machine-authored. Department doctrine is the operator's; this
   script never rewrites it.
2. SOP-SLIDE-05-PROCESS-MANIFEST.md -- the "current full registry" sentence
   (version, count, and the id list in `order`).
3. DEPARTMENT-COUNTS-CANONICAL.md -- the declared-phase two-column table, its
   version/count sentence, and the PHASE_VERIFIERS registry-parity numbers.
4. The `(manifest_version V, N phases)` markers in the role files that restate
   them (director-of-presentations.md, pptx-assembly-specialist.md,
   slide-image-creator.md) and the equivalent marker in
   qc-specialist-prompt-presentations.md.

CANONICAL ORDER: `sorted(phases, key=lambda p: p["order"])` -- the exact
expression run_signature_deck.py's declare_plan() sorts on. Python's sort is
stable, so phases sharing an `order` (P-U-DESIGN-SALES and P1Q-COPY-QC are both
4.2) keep their manifest file order, matching the runner.

USAGE
    python3 scripts/ci/phase_doc_sync.py --check     # CI; exit 1 on drift
    python3 scripts/ci/phase_doc_sync.py --write     # regenerate in place

AFTER --write CHANGES SOP-SLIDE-05: that file lives under universal-sops/, whose
bytes are hashed into universal-sops/_content-manifest.json. Re-run
`python3 scripts/hash-universal-sops-manifest.py` and commit the restamp with the
content change, or `hash-universal-sops-manifest.py --check` (pre-commit hook +
embedding-integrity-guard.yml) fails. --write prints this reminder when it applies.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import subprocess
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]

MANIFEST_REL = "universal-sops/presentation-slide-craft/PIPELINE-MANIFEST.json"
DEPT_REL = "23-ai-workforce-blueprint/templates/role-library/presentations"
START_HERE_REL = f"{DEPT_REL}/00-START-HERE.md"
SOP05_REL = "universal-sops/presentation-slide-craft/SOP-SLIDE-05-PROCESS-MANIFEST.md"
COUNTS_REL = f"{DEPT_REL}/DEPARTMENT-COUNTS-CANONICAL.md"
VERIFIERS_REL = f"{DEPT_REL}/scripts/phase_verifiers.py"
DIRECTOR_REL = f"{DEPT_REL}/director-of-presentations.md"

# Files that restate "(manifest_version V, N phases)" verbatim.
VERSION_MARKER_FILES = [
    START_HERE_REL,
    DIRECTOR_REL,
    f"{DEPT_REL}/pptx-assembly-specialist.md",
    f"{DEPT_REL}/slide-image-creator.md",
]

BEGIN_MARK = "<!-- BEGIN GENERATED: pipeline-sequence -- regenerate with: python3 scripts/ci/phase_doc_sync.py --write -->"
END_MARK = "<!-- END GENERATED: pipeline-sequence -->"

VERSION_MARKER_RE = re.compile(r"manifest_version (\d+), (\d+) phases")
# qc-specialist-prompt-presentations.md carries the same assertion in prose form.
PROSE_MARKER_RE = re.compile(r"The canonical pipeline \(manifest_version (\d+), (\d+) phases\) is in")
PROSE_MARKER_FILE = f"{DEPT_REL}/qc-specialist-prompt-presentations.md"

SOP05_RE = re.compile(
    r"The current full registry \(manifest_version (\d+), (\d+) phases, in `order`\): (.+?)\. Kept in lockstep",
    re.S,
)
COUNTS_SENTENCE_RE = re.compile(
    r"the live read was\nmanifest_version (\d+), declared count (\d+)\."
)
COUNTS_TABLE_RE = re.compile(
    r"\| # \| order \| id \| # \| order \| id \|\n\|---\|---\|---\|---\|---\|---\|\n(?:\|.*\n)+"
)
COUNTS_PARITY_RE = re.compile(
    r"\(read live: registry parity (\d+)/(\d+), regenerated by scripts/ci/phase_doc_sync\.py\)"
)
COUNTS_PARITY_N_RE = re.compile(r"total registered in PHASE_VERIFIERS: len\(PHASE_VERIFIERS\)     \((\d+), same read\)")
# §1 headline summary table -- the five rows that restate the declared count and
# the executed-count matrix. Same numbers as §2, printed one screen higher.
COUNTS_DECLARED_ROW_RE = re.compile(
    r"\| \*\*(\d+)\*\* \| Declared and machine-enforced phase count \| "
    r"\*\*Changed by Wave C: 36 -> 40\*\* \(manifest_version 50 -> 51\), then by later waves to "
    r"\*\*(\d+)\*\* \(manifest_version (\d+); count is read from `len\(manifest\.phases\)`, never hardcoded\) \|"
)
COUNTS_EXEC_ROW_RE = re.compile(
    r"\| \*\*(\d+) / (\d+) / (\d+) / (\d+)\*\* \((standard|signature|content-conversion)\) \|"
)
COUNTS_STEPS_ROW_RE = re.compile(
    r"\| \*\*~(\d+)\*\* \| Honest end-to-end mechanical step count \(declared phase count, read from "
    r"the manifest, \+ ~12 outside-manifest gates\) \| Descriptive, not a manifest number — the "
    r"\"~12 gates\" arithmetic is unchanged; the base phase count under it moved ([0-9 ->]+) \|"
)
OUTSIDE_MANIFEST_GATES = 12  # the "~12 outside-manifest gates" the row's arithmetic adds

COUNTS_MATRIX_RE = re.compile(
    r"```\n {26}both {8}sales-only {6}VSL-only {7}both\n"
    r" {26}declined {4}\(VSL no\) {8}\(sales no\) {5}elected\n"
    r"(?:\S[^\n]*\n)+?```"
)
COUNTS_UNSET_RE = re.compile(
    r"```\nstandard-from-scratch, deck known, upsell flags unset  -> \d+   \(test_standard_from_scratch_is_31\)\n"
    r"signature, deck known, upsell flags unset              -> \d+   \(test_signature_is_35\)\n"
    r"content-conversion, deck known, upsell flags unset     -> \d+   \(test_content_conversion_is_32\)\n"
    r"fully unknown deck \(no intake.json / empty object\)     -> \d+   \(test_unknown_intake_fails_safe_to_full_36\)\n```"
)
# 00-START-HERE.md restates the both-declined column of that same matrix.
START_HERE_COUNTS_RE = re.compile(
    r"\*\*Executed counts \(out of \d+ declared\):\*\* the count now depends on BOTH deck type AND the two "
    r"upsell elections — see `DEPARTMENT-COUNTS-CANONICAL\.md` for the full mechanically-derived table "
    r"\(deck type x sales/checkout x VSL\)\. With both upsells declined and no signature/content-conversion "
    r"signals: \*\*(\d+) on a standard from-scratch deck, (\d+) on a signature deck, (\d+) on a "
    r"content-conversion deck\*\*\."
)

# The three deck-type rows and four upsell-election columns of the executed-count
# matrix, in the order DEPARTMENT-COUNTS-CANONICAL.md prints them.
MATRIX_ROWS = [
    ("standard-from-scratch", {"deck_type": "webinar", "creation_mode": "from_scratch"}),
    ("signature", {"deck_type": "signature_presentation", "creation_mode": "from_scratch"}),
    ("content-conversion", {"deck_type": "webinar", "creation_mode": "content_personal"}),
]
MATRIX_COLS = [
    {"want_sales_checkout": "no", "want_vsl_page": "no"},
    {"want_sales_checkout": "yes", "want_vsl_page": "no"},
    {"want_sales_checkout": "no", "want_vsl_page": "yes"},
    {"want_sales_checkout": "yes", "want_vsl_page": "yes"},
]

DIRECTOR_UPSELL_ROW_RE = re.compile(r"^\| Upsell waves \| .*? \| (.*?) \|$", re.M)
DIRECTOR_LEFTOVER_ROW_RE = re.compile(
    r"^\| Phases with no legacy short code \| .*? \| (.*?) \|$", re.M)
DIRECTOR_TABLE_END_RE = re.compile(
    r"^\| Signature \+ converter branches \| .*? \| .*? \|$", re.M)

# A description that is one of these carries no contract at all -- it is the
# "look it up yourself" stub this script exists to delete.
STUB_MARKERS = (
    "Full contract: look it up in the manifest",
    "See manifest for the full contract",
)


# --------------------------------------------------------------------------- #
# manifest
# --------------------------------------------------------------------------- #
def load_manifest():
    path = REPO_ROOT / MANIFEST_REL
    manifest = json.loads(path.read_text(encoding="utf-8"))
    version = manifest["manifest_version"]
    phases = sorted(manifest["phases"], key=lambda p: p["order"])
    return version, phases


def fmt_order(order) -> str:
    """Render an order the way the manifest stores it (4 not 4.0, -0.5 not -0.50)."""
    if isinstance(order, float) and order.is_integer():
        return str(int(order))
    return str(order)


def rel_link(from_rel: str, to_rel: str) -> str:
    """POSIX relative path from one repo file to another, for a markdown link."""
    return os.path.relpath(REPO_ROOT / to_rel, (REPO_ROOT / from_rel).parent)


# --------------------------------------------------------------------------- #
# 00-START-HERE.md -- pipeline sequence
# --------------------------------------------------------------------------- #
ENTRY_RE = re.compile(r"^(?:\d+\.|-)\s+\*\*`([^`]+)`\*\*\s*\([^)]*\)\s*(?:--|—)\s*(.*)$")


def harvest_descriptions(text: str) -> dict[str, str]:
    """Pull the human-written description out of every existing phase entry.

    Returns {phase_id: description}. Stub descriptions are dropped so the
    generator replaces them with a real contract line.
    """
    found: dict[str, str] = {}
    for line in text.splitlines():
        m = ENTRY_RE.match(line.strip())
        if not m:
            continue
        pid, desc = m.group(1), m.group(2).strip()
        for stub in STUB_MARKERS:
            if stub in desc:
                desc = ""
                break
        if desc:
            found[pid] = desc
    return found


def generated_description(phase: dict) -> str:
    """A real contract line for a phase nobody has written prose for yet.

    Every field here is read from the manifest row, and the line ends in a real
    link -- the owning SOP when the row declares one, and the manifest itself
    always. It never says 'look it up'.
    """
    bits = [phase["name"].rstrip(".") + "."]
    bits.append(f"Owned by `{phase['owning_role']}`.")

    artifact = phase.get("produces_artifact")
    if isinstance(artifact, list):
        bits.append("Produces " + ", ".join(f"`{a}`" for a in artifact) + ".")
    elif artifact:
        bits.append(f"Produces `{artifact}`.")

    gates = phase.get("gate_codes") or []
    if gates:
        bits.append("Gates: " + ", ".join(gates) + ".")

    links = []
    for ref in phase.get("sop_refs") or []:
        links.append(f"[`sops/{ref}`](sops/{ref})")
    manifest_link = rel_link(START_HERE_REL, MANIFEST_REL)
    links.append(f"the `{phase['id']}` row in [`PIPELINE-MANIFEST.json`]({manifest_link})")
    bits.append("Full contract: " + " and ".join(links) + ".")
    return " ".join(bits)


def entry_meta(phase: dict) -> str:
    """The parenthetical after the phase id: order, executor kind, conditionality."""
    parts = [f"order {fmt_order(phase['order'])}"]
    executor = phase.get("executor") or {}
    if executor.get("kind") == "script":
        cmd = executor.get("cmd", "")
        m = re.search(r"(\S+\.py)", cmd)
        parts.append(f"script: `{m.group(1)}`" if m else "kind: script")
    if phase.get("fanout"):
        fan = phase["fanout"]
        parts.append(f"fanout by {fan.get('by')}, max {fan.get('max_units')} units")
    if phase.get("defers_unless"):
        parts.append(f"CONDITIONAL -- defers unless `{phase['defers_unless']}`")
    return ", ".join(parts)


def render_sequence(version: int, phases: list[dict], descriptions: dict[str, str]) -> str:
    pu = [p for p in phases if p["id"].startswith("P-U-")]
    conditional = [p for p in phases if p.get("defers_unless")]
    lines = [
        BEGIN_MARK,
        "",
        "### Upsell (P-U) and other conditional phases",
        "",
        f"All {len(phases)} declared phases are listed once, in the sequence below, in the manifest's "
        f"own `order`. {len(pu)} of them are P-U upsell phases. {len(conditional)} phases declare a "
        "`defers_unless` predicate in the manifest; each is marked CONDITIONAL below with that exact "
        "predicate, and defers (returns empty, no-op) when it is not met. A decline is a logged "
        "client waiver, never silence. The phases that defer through the runner's own filters rather "
        "than a `defers_unless` predicate -- `P-CONVERTER`, the four `P-SP-*` signature phases and "
        "`P-SPEECH-QC` -- are named in the note above. The sales/checkout and VSL upsell contracts "
        "are in [`sops/SALES-CHECKOUT-BUILDER-SOP.md`](sops/SALES-CHECKOUT-BUILDER-SOP.md) and "
        "[`sops/VSL-BUILDER-SOP.md`](sops/VSL-BUILDER-SOP.md).",
        "",
    ]
    for n, phase in enumerate(phases, 1):
        desc = descriptions.get(phase["id"]) or generated_description(phase)
        lines.append(f"{n}. **`{phase['id']}`** ({entry_meta(phase)}) -- {desc}")
    lines += ["", END_MARK]
    return "\n".join(lines)


def build_start_here(text: str, version: int, phases: list[dict]) -> str:
    """Return the new 00-START-HERE.md body."""
    descriptions = harvest_descriptions(text)
    block = render_sequence(version, phases, descriptions)

    if BEGIN_MARK in text and END_MARK in text:
        head, rest = text.split(BEGIN_MARK, 1)
        _, tail = rest.split(END_MARK, 1)
        return head + block + tail

    # First run: carve the region out of the legacy layout. The legacy layout is
    # the "### Upsell (P-U) phases" heading through the end of the numbered list,
    # with the conditional/executed-counts blockquote sitting in the middle of it.
    lines = text.splitlines()
    try:
        start = next(i for i, l in enumerate(lines) if l.startswith("### Upsell (P-U) phases"))
    except StopIteration:  # pragma: no cover -- layout already migrated
        raise SystemExit("phase_doc_sync: cannot find the legacy '### Upsell (P-U) phases' heading")
    end = next(
        i
        for i in range(len(lines) - 1, start, -1)
        if re.match(r"^\d+\. \*\*`", lines[i])
    )
    # The blockquote that explains conditionality and executed counts is the
    # operator's prose; it moves ahead of the generated list verbatim.
    keep = [l for l in lines[start : end + 1] if l.startswith(">")]
    new = lines[:start] + keep + [""] + block.splitlines() + lines[end + 1 :]
    return "\n".join(new) + ("\n" if text.endswith("\n") else "")


# --------------------------------------------------------------------------- #
# SOP-SLIDE-05 + DEPARTMENT-COUNTS
# --------------------------------------------------------------------------- #
def build_sop05(text: str, version: int, phases: list[dict]) -> str:
    ids = ", ".join(f"`{p['id']}`" for p in phases)
    replacement = (
        f"The current full registry (manifest_version {version}, {len(phases)} phases, "
        f"in `order`): {ids}. Kept in lockstep"
    )
    new, n = SOP05_RE.subn(lambda _m: replacement, text, count=1)
    if n != 1:
        raise SystemExit("phase_doc_sync: SOP-SLIDE-05 registry sentence not found")
    return new


def build_counts_table(phases: list[dict]) -> str:
    half = (len(phases) + 1) // 2
    left, right = phases[:half], phases[half:]
    out = ["| # | order | id | # | order | id |", "|---|---|---|---|---|---|"]
    for i in range(half):
        lp = left[i]
        cells = [str(i + 1), fmt_order(lp["order"]), f"`{lp['id']}`"]
        if i < len(right):
            rp = right[i]
            cells += [str(half + i + 1), fmt_order(rp["order"]), f"`{rp['id']}`"]
        else:
            cells += ["", "", ""]
        out.append("| " + " | ".join(cells) + " |")
    return "\n".join(out) + "\n"


def registered_verifier_count() -> int:
    """len(PHASE_VERIFIERS), read by importing the module the runner imports.

    Imported in a subprocess: this is the same live read DEPARTMENT-COUNTS-CANONICAL
    documents, and a source-scrape would miss entries the module builds
    programmatically -- exactly the way a hand-count goes stale.
    """
    scripts_dir = (REPO_ROOT / VERIFIERS_REL).parent
    proc = subprocess.run(
        [sys.executable, "-c",
         "import sys; sys.path.insert(0, '.'); "
         "import phase_verifiers; print(len(phase_verifiers.PHASE_VERIFIERS))"],
        cwd=scripts_dir, capture_output=True, text=True,
    )
    if proc.returncode != 0:
        raise SystemExit(
            "phase_doc_sync: could not import phase_verifiers to count PHASE_VERIFIERS "
            f"(rc={proc.returncode}):\n{proc.stderr}"
        )
    return int(proc.stdout.strip())


def executed_counts() -> tuple[list[list[int]], list[int]]:
    """Run the real client-visible-phase filter and return the executed-count matrix.

    DEPARTMENT-COUNTS-CANONICAL.md documents these numbers as "mechanical
    derivation actually run in this worktree" against
    run_signature_deck._client_visible_phases(). They were hand-copied and went
    stale by every cell; this function IS that derivation, so the doc can no
    longer disagree with the runner.

    Returns (matrix, unset) where matrix[row][col] follows MATRIX_ROWS x
    MATRIX_COLS and unset is [standard, signature, content-conversion,
    fully-unknown] with the upsell flags absent.
    """
    scripts_dir = (REPO_ROOT / VERIFIERS_REL).parent
    driver = r"""
import json, pathlib, sys, tempfile
sys.path.insert(0, ".")
import run_signature_deck as rsd
phases = json.loads(pathlib.Path(sys.argv[1]).read_text())["phases"]

def n(intake):
    with tempfile.TemporaryDirectory() as tmp:
        d = pathlib.Path(tmp)
        (d / "working" / "copy").mkdir(parents=True)
        if intake is not None:
            (d / "working" / "copy" / "intake.json").write_text(json.dumps(intake))
        return len(rsd._client_visible_phases(d, phases))

rows = json.loads(sys.argv[2])
cols = json.loads(sys.argv[3])
matrix = [[n({**r, **c}) for c in cols] for r in rows]
unset = [n(dict(r)) for r in rows] + [n(None)]
print(json.dumps({"matrix": matrix, "unset": unset}))
"""
    proc = subprocess.run(
        [sys.executable, "-c", driver, str(REPO_ROOT / MANIFEST_REL),
         json.dumps([r for _, r in MATRIX_ROWS]), json.dumps(MATRIX_COLS)],
        cwd=scripts_dir, capture_output=True, text=True,
    )
    if proc.returncode != 0:
        raise SystemExit(
            "phase_doc_sync: could not derive executed counts from "
            f"run_signature_deck._client_visible_phases (rc={proc.returncode}):\n{proc.stderr}"
        )
    data = json.loads(proc.stdout.strip().splitlines()[-1])
    return data["matrix"], data["unset"]


def render_matrix(matrix: list[list[int]]) -> str:
    lines = [
        "```",
        " " * 26 + "both        sales-only      VSL-only       both",
        " " * 26 + "declined    (VSL no)        (sales no)     elected",
    ]
    for (label, _), row in zip(MATRIX_ROWS, matrix):
        cells = f"{row[0]:>5}{row[1]:>14}{row[2]:>16}{row[3]:>15}"
        lines.append(f"{label:<22} ->{cells}")
    lines.append("```")
    return "\n".join(lines)


def render_unset(unset: list[int]) -> str:
    return "\n".join([
        "```",
        f"standard-from-scratch, deck known, upsell flags unset  -> {unset[0]}   (test_standard_from_scratch_is_31)",
        f"signature, deck known, upsell flags unset              -> {unset[1]}   (test_signature_is_35)",
        f"content-conversion, deck known, upsell flags unset     -> {unset[2]}   (test_content_conversion_is_32)",
        f"fully unknown deck (no intake.json / empty object)     -> {unset[3]}   (test_unknown_intake_fails_safe_to_full_36)",
        "```",
    ])


def build_start_here_counts(text: str, count: int, matrix: list[list[int]]) -> str:
    """Keep 00-START-HERE's restatement of the both-declined column honest."""
    declined = [row[0] for row in matrix]
    replacement = (
        f"**Executed counts (out of {count} declared):** the count now depends on BOTH deck type AND "
        "the two upsell elections — see `DEPARTMENT-COUNTS-CANONICAL.md` for the full "
        "mechanically-derived table (deck type x sales/checkout x VSL). With both upsells declined and "
        f"no signature/content-conversion signals: **{declined[0]} on a standard from-scratch deck, "
        f"{declined[1]} on a signature deck, {declined[2]} on a content-conversion deck**."
    )
    new, n = START_HERE_COUNTS_RE.subn(lambda _m: replacement, text, count=1)
    if n == 1:
        return new
    # First run: migrate the legacy sentence, whose numbers conflated "declined"
    # with "unknown" (they are no longer the same number) and whose "out of 40
    # enforced" predates the current declared count.
    legacy = re.compile(
        r"\*\*Executed counts \(out of \d+ enforced\):\*\*.*?`DEPARTMENT-COUNTS-CANONICAL\.md` is the "
        r"single source; link to it\.",
        re.S,
    )
    new, n = legacy.subn(
        lambda _m: replacement + " Do not restate the full matrix here — "
        "`DEPARTMENT-COUNTS-CANONICAL.md` is the single source; link to it.",
        text, count=1,
    )
    if n != 1:
        raise SystemExit("phase_doc_sync: 00-START-HERE executed-counts sentence not found")
    return new


def build_counts(text: str, version: int, phases: list[dict]) -> str:
    new, n = COUNTS_SENTENCE_RE.subn(
        f"the live read was\nmanifest_version {version}, declared count {len(phases)}.", text, count=1
    )
    if n != 1:
        raise SystemExit("phase_doc_sync: DEPARTMENT-COUNTS version sentence not found")

    new, n = COUNTS_TABLE_RE.subn(lambda _m: build_counts_table(phases), new, count=1)
    if n != 1:
        raise SystemExit("phase_doc_sync: DEPARTMENT-COUNTS declared-phase table not found")

    registered = registered_verifier_count()
    # First run: migrate the date-stamped legacy markers. A date stamp on a
    # generated number is a claim that rots on its own; these say who regenerates
    # them instead.
    new = re.sub(
        r"\(read live: registry parity \d+/\d+ at the \d{4}-\d{2}-\d{2} re-check\)",
        "(read live: registry parity 0/0, regenerated by scripts/ci/phase_doc_sync.py)", new)
    new = re.sub(
        r"total registered in PHASE_VERIFIERS: len\(PHASE_VERIFIERS\)     \(\d+ at the same re-check\)",
        "total registered in PHASE_VERIFIERS: len(PHASE_VERIFIERS)     (0, same read)", new)
    new = re.sub(
        r"\(see §2\.40 for the mechanical read; parity = \d+/\d+ at the \d{4}-\d{2}-\d{2} re-check\)\.",
        "(see §2.40 for the mechanical read; the live parity is regenerated there by\n"
        "scripts/ci/phase_doc_sync.py and CI-enforced by GATE 7 of scripts/ci/presentations-drift-gates.sh).",
        new)
    new, n = COUNTS_PARITY_RE.subn(
        f"(read live: registry parity {registered}/{len(phases)}, "
        "regenerated by scripts/ci/phase_doc_sync.py)", new, count=1
    )
    if n != 1:
        raise SystemExit("phase_doc_sync: DEPARTMENT-COUNTS parity marker not found")
    new, n = COUNTS_PARITY_N_RE.subn(
        "total registered in PHASE_VERIFIERS: len(PHASE_VERIFIERS)     "
        f"({registered}, same read)",
        new,
        count=1,
    )
    if n != 1:
        raise SystemExit("phase_doc_sync: DEPARTMENT-COUNTS PHASE_VERIFIERS count not found")

    matrix, unset = executed_counts()

    # §1 headline summary rows -- the same numbers, one screen higher up.
    new, n = COUNTS_DECLARED_ROW_RE.subn(
        lambda _m: (f"| **{len(phases)}** | Declared and machine-enforced phase count | "
                    "**Changed by Wave C: 36 -> 40** (manifest_version 50 -> 51), then by later "
                    f"waves to **{len(phases)}** (manifest_version {version}; count is read from "
                    "`len(manifest.phases)`, never hardcoded) |"),
        new, count=1)
    if n != 1:
        raise SystemExit("phase_doc_sync: DEPARTMENT-COUNTS §1 declared-count row not found")

    by_label = dict(zip([lbl for lbl, _ in MATRIX_ROWS], matrix))
    label_map = {"standard": "standard-from-scratch", "signature": "signature",
                 "content-conversion": "content-conversion"}

    def _exec_row(m):
        row = by_label[label_map[m.group(5)]]
        return f"| **{row[0]} / {row[1]} / {row[2]} / {row[3]}** ({m.group(5)}) |"

    new, n = COUNTS_EXEC_ROW_RE.subn(_exec_row, new)
    if n != 3:
        raise SystemExit(f"phase_doc_sync: expected 3 DEPARTMENT-COUNTS §1 executed-count rows, found {n}")

    def _steps_row(m):
        chain = [c.strip() for c in m.group(2).split("->")]
        if chain[-1] != str(len(phases)):
            chain.append(str(len(phases)))
        return (f"| **~{len(phases) + OUTSIDE_MANIFEST_GATES}** | Honest end-to-end mechanical step "
                "count (declared phase count, read from the manifest, + ~12 outside-manifest gates) | "
                'Descriptive, not a manifest number — the "~12 gates" arithmetic is unchanged; the '
                f"base phase count under it moved {' -> '.join(chain)} |")

    new, n = COUNTS_STEPS_ROW_RE.subn(_steps_row, new, count=1)
    if n != 1:
        raise SystemExit("phase_doc_sync: DEPARTMENT-COUNTS §1 mechanical-step-count row not found")

    new, n = COUNTS_MATRIX_RE.subn(lambda _m: render_matrix(matrix), new, count=1)
    if n != 1:
        raise SystemExit("phase_doc_sync: DEPARTMENT-COUNTS executed-count matrix not found")
    new, n = COUNTS_UNSET_RE.subn(lambda _m: render_unset(unset), new, count=1)
    if n != 1:
        raise SystemExit("phase_doc_sync: DEPARTMENT-COUNTS flags-unset block not found")
    return new


# --------------------------------------------------------------------------- #
# version markers
# --------------------------------------------------------------------------- #
def build_director_map(text: str, phases: list[dict]) -> str:
    """Keep director-of-presentations.md's Phase-Code Map naming every manifest id.

    The map is the department's short-code -> manifest-id dictionary and the file
    itself asserts every current id resolves through it. It had fallen 7 ids
    behind (the three P-U DESIGN-RENDER phases, P-STYLE-SPEC, P-STYLE-PICK,
    P8.3-INFOGRAPHIC, P-BUNDLE-GATE). Two cells are machine-authored: the "Upsell
    waves" row, which is exactly the P-U family in `order`, and a completeness row
    naming any id the file does not otherwise mention. The semantic rows above
    them are the operator's and are never touched.
    """
    pu = ", ".join(f"`{p['id']}` ({fmt_order(p['order'])})"
                   for p in phases if p["id"].startswith("P-U-"))
    new, n = DIRECTOR_UPSELL_ROW_RE.subn(
        lambda m: f"| Upsell waves | {pu} | {m.group(1)} |", text, count=1)
    if n != 1:
        raise SystemExit("phase_doc_sync: director-of-presentations.md 'Upsell waves' row not found")

    # Anything still unnamed after that gets its own row, so the map is complete.
    leftover_note = ("added after the numeric short-code era; the manifest row is the only key")
    stripped = DIRECTOR_LEFTOVER_ROW_RE.sub("", new)
    missing = [p for p in phases if f"`{p['id']}`" not in stripped]
    row = ("| Phases with no legacy short code | "
           + ", ".join(f"`{p['id']}` ({fmt_order(p['order'])})" for p in missing)
           + f" | {leftover_note} |") if missing else ""

    if DIRECTOR_LEFTOVER_ROW_RE.search(new):
        new = DIRECTOR_LEFTOVER_ROW_RE.sub(lambda _m: row, new, count=1) if row \
            else DIRECTOR_LEFTOVER_ROW_RE.sub("", new, count=1)
        return re.sub(r"\n\n+(?=\nThe authoritative machine-readable list)", "\n", new)
    if not row:
        return new
    anchor = DIRECTOR_TABLE_END_RE.search(new)
    if not anchor:
        raise SystemExit("phase_doc_sync: director-of-presentations.md Phase-Code Map end row not found")
    return new[: anchor.end()] + "\n" + row + new[anchor.end():]


def build_version_markers(text: str, version: int, count: int, prose: bool) -> str:
    rx = PROSE_MARKER_RE if prose else VERSION_MARKER_RE
    if prose:
        return rx.sub(
            f"The canonical pipeline (manifest_version {version}, {count} phases) is in", text
        )
    return rx.sub(f"manifest_version {version}, {count} phases", text)


# --------------------------------------------------------------------------- #
# driver
# --------------------------------------------------------------------------- #
def targets(version: int, phases: list[dict]):
    """[(rel_path, new_text_builder)] for every region this script owns."""
    count = len(phases)
    out = [
        (START_HERE_REL, lambda t: build_start_here_counts(
            build_version_markers(build_start_here(t, version, phases), version, count, prose=False),
            count, executed_counts()[0])),
        (SOP05_REL, lambda t: build_sop05(t, version, phases)),
        (COUNTS_REL, lambda t: build_counts(t, version, phases)),
        (PROSE_MARKER_FILE, lambda t: build_version_markers(t, version, count, prose=True)),
    ]
    for rel in VERSION_MARKER_FILES:
        if rel == START_HERE_REL:
            continue
        if rel == DIRECTOR_REL:
            out.append((rel, lambda t: build_director_map(
                build_version_markers(t, version, count, prose=False), phases)))
            continue
        out.append((rel, lambda t: build_version_markers(t, version, count, prose=False)))
    return out


def parsed_report(version: int, phases: list[dict]) -> list[str]:
    """Parsed-value assertions -- ints and id sequences, never literal-string greps.

    A literal-string grep is how the existing gates got broken by an unrelated
    edit; every assertion below compares a PARSED value to the manifest.
    """
    count = len(phases)
    canon_ids = [p["id"] for p in phases]
    problems: list[str] = []

    for rel in VERSION_MARKER_FILES:
        text = (REPO_ROOT / rel).read_text(encoding="utf-8")
        marks = [(int(a), int(b)) for a, b in VERSION_MARKER_RE.findall(text)]
        if not marks:
            problems.append(f"{rel}: no '(manifest_version V, N phases)' marker found at all")
        for v, n in marks:
            if (v, n) != (version, count):
                problems.append(
                    f"{rel}: states manifest_version {v}, {n} phases -- manifest is {version}, {count}"
                )

    text = (REPO_ROOT / PROSE_MARKER_FILE).read_text(encoding="utf-8")
    marks = [(int(a), int(b)) for a, b in PROSE_MARKER_RE.findall(text)]
    if not marks:
        problems.append(f"{PROSE_MARKER_FILE}: no canonical-pipeline version marker found")
    for v, n in marks:
        if (v, n) != (version, count):
            problems.append(
                f"{PROSE_MARKER_FILE}: states manifest_version {v}, {n} phases -- manifest is {version}, {count}"
            )

    # START-HERE: the generated sequence, parsed back into an ordered id list.
    text = (REPO_ROOT / START_HERE_REL).read_text(encoding="utf-8")
    seq = re.findall(r"^(\d+)\. \*\*`([^`]+)`\*\*", text, re.M)
    doc_ids = [pid for _, pid in seq]
    numbers = [int(n) for n, _ in seq]
    if doc_ids != canon_ids:
        problems.append(
            f"{START_HERE_REL}: pipeline sequence is not the manifest's `order` "
            f"({len(doc_ids)} entries vs {count}); "
            f"missing={sorted(set(canon_ids) - set(doc_ids))} "
            f"extra={sorted(set(doc_ids) - set(canon_ids))}"
        )
    if numbers != list(range(1, len(numbers) + 1)):
        dupes = sorted({n for n in numbers if numbers.count(n) > 1})
        problems.append(f"{START_HERE_REL}: list numbering is not 1..N (duplicated: {dupes})")
    for stub in STUB_MARKERS:
        hits = text.count(stub)
        if hits:
            problems.append(f"{START_HERE_REL}: {hits} dead '{stub}' stub(s) remain")

    # SOP-SLIDE-05: version, count and the id sequence.
    text = (REPO_ROOT / SOP05_REL).read_text(encoding="utf-8")
    m = SOP05_RE.search(text)
    if not m:
        problems.append(f"{SOP05_REL}: 'current full registry' sentence not found")
    else:
        v, n = int(m.group(1)), int(m.group(2))
        doc_ids = re.findall(r"`([^`]+)`", m.group(3))
        if (v, n) != (version, count):
            problems.append(
                f"{SOP05_REL}: states manifest_version {v}, {n} phases -- manifest is {version}, {count}"
            )
        if doc_ids != canon_ids:
            problems.append(f"{SOP05_REL}: registry list is not the manifest's `order`")

    # DEPARTMENT-COUNTS: version sentence + the declared two-column table.
    text = (REPO_ROOT / COUNTS_REL).read_text(encoding="utf-8")
    m = COUNTS_SENTENCE_RE.search(text)
    if not m:
        problems.append(f"{COUNTS_REL}: declared-count sentence not found")
    elif (int(m.group(1)), int(m.group(2))) != (version, count):
        problems.append(
            f"{COUNTS_REL}: states manifest_version {m.group(1)}, declared count {m.group(2)} "
            f"-- manifest is {version}, {count}"
        )
    m = COUNTS_TABLE_RE.search(text)
    if not m:
        problems.append(f"{COUNTS_REL}: declared-phase table not found")
    else:
        cells = []
        for row in m.group(0).splitlines()[2:]:
            parts = [c.strip() for c in row.strip().strip("|").split("|")]
            for k in range(0, len(parts), 3):
                trio = parts[k : k + 3]
                if len(trio) == 3 and trio[0].isdigit():
                    cells.append((int(trio[0]), trio[1], trio[2].strip("`")))
        table_ids = [pid for _, _, pid in sorted(cells, key=lambda c: c[0])]
        if table_ids != canon_ids:
            problems.append(
                f"{COUNTS_REL}: declared-phase table is not the manifest's `order` "
                f"({len(table_ids)} rows vs {count}); "
                f"missing={sorted(set(canon_ids) - set(table_ids))}"
            )
    matrix, unset = executed_counts()
    mm = COUNTS_MATRIX_RE.search(text)
    if not mm:
        problems.append(f"{COUNTS_REL}: executed-count matrix not found")
    else:
        # Each data row is "<label> -> a  b  c  d"; parse the four ints back out.
        stated = [int(x) for line in mm.group(0).splitlines()[3:-1]
                  for x in re.findall(r"\b(\d+)\b", line.split("->", 1)[-1])]
        live = [c for row in matrix for c in row]
        if stated != live:
            problems.append(
                f"{COUNTS_REL}: executed-count matrix states {stated} -- the live "
                f"_client_visible_phases() derivation is {live}"
            )
    mm = COUNTS_DECLARED_ROW_RE.search(text)
    if not mm:
        problems.append(f"{COUNTS_REL}: §1 declared-count row not found")
    elif (int(mm.group(1)), int(mm.group(2)), int(mm.group(3))) != (count, count, version):
        problems.append(
            f"{COUNTS_REL}: §1 declared-count row states {mm.group(1)}/{mm.group(2)} phases at "
            f"manifest_version {mm.group(3)} -- manifest is {count} at {version}")
    exec_rows = COUNTS_EXEC_ROW_RE.findall(text)
    if len(exec_rows) != 3:
        problems.append(f"{COUNTS_REL}: expected 3 §1 executed-count rows, found {len(exec_rows)}")
    else:
        by_label = dict(zip([lbl for lbl, _ in MATRIX_ROWS], matrix))
        label_map = {"standard": "standard-from-scratch", "signature": "signature",
                     "content-conversion": "content-conversion"}
        for row in exec_rows:
            stated = [int(x) for x in row[:4]]
            live = by_label[label_map[row[4]]]
            if stated != live:
                problems.append(
                    f"{COUNTS_REL}: §1 executed-count row ({row[4]}) states {stated} -- "
                    f"the live derivation is {live}")
    mm = COUNTS_STEPS_ROW_RE.search(text)
    if not mm:
        problems.append(f"{COUNTS_REL}: §1 mechanical-step-count row not found")
    elif int(mm.group(1)) != count + OUTSIDE_MANIFEST_GATES:
        problems.append(
            f"{COUNTS_REL}: §1 mechanical-step-count row states ~{mm.group(1)} -- "
            f"{count} declared phases + ~{OUTSIDE_MANIFEST_GATES} outside-manifest gates is "
            f"~{count + OUTSIDE_MANIFEST_GATES}")

    mm = COUNTS_UNSET_RE.search(text)
    if not mm:
        problems.append(f"{COUNTS_REL}: flags-unset block not found")
    else:
        stated = [int(x) for x in re.findall(r"-> (\d+) ", mm.group(0))]
        if stated != unset:
            problems.append(
                f"{COUNTS_REL}: flags-unset block states {stated} -- the live "
                f"_client_visible_phases() derivation is {unset}"
            )
    sh = (REPO_ROOT / START_HERE_REL).read_text(encoding="utf-8")
    mm = START_HERE_COUNTS_RE.search(sh)
    if not mm:
        problems.append(f"{START_HERE_REL}: executed-counts sentence not in its generated form")
    else:
        stated = [int(g) for g in mm.groups()]
        live = [row[0] for row in matrix]
        if stated != live:
            problems.append(
                f"{START_HERE_REL}: executed counts state {stated} for the both-declined column "
                f"-- the live derivation is {live}"
            )

    director = (REPO_ROOT / DIRECTOR_REL).read_text(encoding="utf-8")
    unnamed = [p["id"] for p in phases if f"`{p['id']}`" not in director]
    if unnamed:
        problems.append(
            f"{DIRECTOR_REL}: Phase-Code Map does not name {len(unnamed)} of {count} manifest "
            f"phase id(s): {unnamed}")

    m = COUNTS_PARITY_RE.search(text)
    registered = registered_verifier_count()
    if not m:
        problems.append(f"{COUNTS_REL}: registry-parity marker not found")
    elif (int(m.group(1)), int(m.group(2))) != (registered, count):
        problems.append(
            f"{COUNTS_REL}: states registry parity {m.group(1)}/{m.group(2)} "
            f"-- live is {registered}/{count}"
        )
    return problems


def selftest() -> int:
    """Prove this checker DISCRIMINATES before anyone trusts a green run.

    GATE 5 proves its drift detector the same way: a real change must trip it and
    a no-op must not. A gate that cannot fail is a no-op wearing a gate's label --
    which is exactly what GATE 3 was before U05, and what GATE 4 effectively was
    for the version/count/order class this gate covers.
    """
    version, phases = load_manifest()
    failures = []

    # 1. The sequence renderer tracks the manifest, not a constant.
    seq = render_sequence(version, phases, {})
    numbered = re.findall(r"^(\d+)\. \*\*`([^`]+)`\*\*", seq, re.M)
    if [int(n) for n, _ in numbered] != list(range(1, len(phases) + 1)):
        failures.append("render_sequence did not number 1..N")
    if [pid for _, pid in numbered] != [p["id"] for p in phases]:
        failures.append("render_sequence did not follow the manifest's `order`")
    short = render_sequence(version, phases[:-1], {})
    if len(re.findall(r"^\d+\. \*\*`", short, re.M)) != len(phases) - 1:
        failures.append("render_sequence ignored a removed phase -- it is not reading the manifest")
    if "look it up" in seq.lower():
        failures.append("render_sequence still emits a dead 'look it up' stub")

    # 2. A bumped version in a doc must be caught; an unrelated edit must not.
    text = (REPO_ROOT / START_HERE_REL).read_text(encoding="utf-8")
    live = [(int(a), int(b)) for a, b in VERSION_MARKER_RE.findall(text)]
    if not live:
        failures.append("no version marker in 00-START-HERE.md to self-test against")
    elif any(m != (version, len(phases)) for m in live):
        failures.append("00-START-HERE.md is already drifted -- run --write before --selftest")
    else:
        mutated = text.replace(
            f"manifest_version {version}, {len(phases)} phases",
            f"manifest_version {version - 1}, {len(phases)} phases", 1)
        if all(m == (version, len(phases))
               for m in [(int(a), int(b)) for a, b in VERSION_MARKER_RE.findall(mutated)]):
            failures.append("a bumped manifest_version did NOT trip the marker check")
        noop = text.replace("Pipeline Sequence (phase order)", "Pipeline Sequence (phase order) ", 1)
        if any(m != (version, len(phases))
               for m in [(int(a), int(b)) for a, b in VERSION_MARKER_RE.findall(noop)]):
            failures.append("an unrelated whitespace edit tripped the marker check (false positive)")

    # 3. The executed-count derivation runs the real filter, not a stored number.
    matrix, unset = executed_counts()
    if unset[-1] != len(phases):
        failures.append(
            f"fully-unknown intake should fail safe to all {len(phases)} phases, derived {unset[-1]}")
    if not all(len(row) == len(MATRIX_COLS) for row in matrix):
        failures.append("executed-count matrix shape does not match MATRIX_COLS")

    if failures:
        print("PHASE_DOC_SYNC_SELFTEST_FAIL:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("PHASE_DOC_SYNC_SELFTEST_PASS: the checker trips on a real change and not on a no-op.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="fail if any owned region has drifted")
    mode.add_argument("--write", action="store_true", help="regenerate every owned region in place")
    mode.add_argument("--selftest", action="store_true",
                      help="prove the checker trips on a real change and not on a no-op")
    args = ap.parse_args()
    if not (args.write or args.selftest):
        args.check = True

    version, phases = load_manifest()
    print(f"phase_doc_sync: manifest {MANIFEST_REL} -> manifest_version {version}, {len(phases)} phases")

    if args.selftest:
        return selftest()

    if args.write:
        for rel, build in targets(version, phases):
            path = REPO_ROOT / rel
            old = path.read_text(encoding="utf-8")
            new = build(old)
            if new != old:
                path.write_text(new, encoding="utf-8")
                print(f"  REWROTE {rel}")
                if rel == SOP05_REL:
                    print("  NOTE: that file is hashed into universal-sops/_content-manifest.json --"
                          " re-run scripts/hash-universal-sops-manifest.py and commit the restamp.")
            else:
                print(f"  unchanged {rel}")
        return 0

    problems = parsed_report(version, phases)
    # Round-trip proof: regenerating must be a no-op. Catches an owned region a
    # human edited by hand rather than by re-running the generator.
    for rel, build in targets(version, phases):
        old = (REPO_ROOT / rel).read_text(encoding="utf-8")
        try:
            regenerated = build(old)
        except SystemExit as exc:  # a region the generator can no longer locate
            problems.append(f"{rel}: {exc}")
            continue
        if regenerated != old:
            problems.append(f"{rel}: generated region is not what the manifest produces "
                            f"(run: python3 scripts/ci/phase_doc_sync.py --write)")

    if problems:
        print("PHASE_DOC_SYNC_FAIL: a doc that restates the pipeline manifest has drifted:")
        for p in problems:
            print(f"  - {p}")
        print("Fix: python3 scripts/ci/phase_doc_sync.py --write")
        return 1

    print(f"PHASE_DOC_SYNC_PASS: every phase table and version marker matches "
          f"manifest_version {version} ({len(phases)} phases).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
