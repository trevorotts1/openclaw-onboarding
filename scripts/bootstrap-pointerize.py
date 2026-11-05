#!/usr/bin/env python3
"""bootstrap-pointerize.py — write MANAGED bootstrap blocks as compact POINTERS.

WHY THIS EXISTS
---------------
Every fleet roll stamps managed blocks into each box's bootstrap files
(AGENTS.md / TOOLS.md / MEMORY.md / SOUL.md / IDENTITY.md / USER.md). Those
files are re-billed to the model on EVERY turn, so full rule text stamped
there is paid for forever. Measured on one live box, 2026-09-18:

    AGENTS.md total                                     92,068 chars
      skill CORE_UPDATES blocks (7 x <!-- BEGIN skill:NN:agents -->)  13,171
      apply-fleet-standards.sh stamped sections (6)                    9,726
      "## UPDATE PENDING ..." notice                                   3,140
      "## Managed skill blocks (do not remove)"                        3,039

Moving a managed block OUT of a bootstrap file BY HAND does not hold: the next
roll's idempotency guard sees the marker gone and re-appends the full text.
The fix therefore has to live in the WRITER, which is what this module is.

THE CONTRACT
------------
For each managed block the roll would stamp, the bootstrap file receives a
compact POINTER:

    <!-- BEGIN <marker> -->
    ## <heading>
    <one-line summary>
    **Triggers:** <exact trigger phrases that must bind inline>
    **Full text:** <ONE absolute path>
    <!-- END <marker> -->

and the VERBATIM full text is written to that absolute path, fenced by its own
`<!-- BEGIN REF <marker> -->` / `<!-- END REF <marker> -->` pair so the
reference file is itself idempotently rewritable.

The marker names are UNCHANGED, so every existing idempotency guard, pair
balance check, dedup script and validator keeps working untouched.

MIGRATION (the part that makes already-fat boxes converge)
----------------------------------------------------------
When a bootstrap file already carries the FULL text under a marker, this module
lifts that text verbatim into the reference file BEFORE replacing the block with
the pointer. Nothing is lost and nothing needs a hand edit. A box that was
cleaned by hand takes the same code path with no special case.

IDEMPOTENCY
-----------
The result is computed, then compared to what is on disk. Identical means NO
write, NO backup, exit "unchanged". So the second run of a roll is a true no-op,
which is the property the old `grep -q MARKER && skip` guard only pretended to
have (it skipped on the marker, so an EDIT to a block never reached a wired box,
and a marker RENAME appended a second copy forever).

FAIL-CLOSED
-----------
If the reference file cannot be written, the pointer is NOT stamped and the
bootstrap file is left exactly as it was — a pointer to a file that does not
exist is worse than the bloat it replaces. Exit code 3 says so explicitly.

Exit codes: 0 = written, 10 = unchanged (already correct), 3 = refused
(reference unwritable), 4 = bad usage.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

POINTER_MODE_DEFAULT = "pointer"

# A pointer block carries this sentinel so a validator (and a human) can tell a
# pointer from a hand-written stub at a glance, and so `--mode full` can detect
# a block it previously pointerized and restore it from the reference file.
POINTER_SENTINEL = "**Full text:**"


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except FileNotFoundError:
        return ""
    except OSError:
        return ""


def _markers(marker: str) -> tuple[str, str]:
    return f"<!-- BEGIN {marker} -->", f"<!-- END {marker} -->"


def _ref_markers(marker: str) -> tuple[str, str]:
    return f"<!-- BEGIN REF {marker} -->", f"<!-- END REF {marker} -->"


def extract_block(text: str, marker: str) -> str | None:
    """Return the body between a marker pair, or None when the pair is absent.

    An UNMATCHED BEGIN (no closing END) returns None rather than swallowing the
    rest of the file — the same safety rule the skill-38 writer already uses.
    """
    begin, end = _markers(marker)
    i = text.find(begin)
    if i < 0:
        return None
    j = text.find(end, i + len(begin))
    if j < 0:
        return None
    return text[i + len(begin):j].strip("\n")


def replace_block(text: str, marker: str, body: str) -> str:
    """Replace a marker pair's body, or append a fresh pair when absent."""
    begin, end = _markers(marker)
    new = f"{begin}\n{body}\n{end}"
    i = text.find(begin)
    if i >= 0:
        j = text.find(end, i + len(begin))
        if j >= 0:
            return text[:i] + new + text[j + len(end):]
    # Absent (or an orphan BEGIN we refuse to span): append a clean pair.
    sep = "" if text.endswith("\n\n") or not text else ("\n" if text.endswith("\n") else "\n\n")
    return text + sep + "\n" + new + "\n"


def build_pointer(heading: str, summary: str, triggers: list[str], ref_path: str,
                  anchor: str) -> str:
    """The compact pointer: heading + one line + triggers + ONE absolute path."""
    lines = []
    head = heading.strip()
    if head:
        if not head.startswith("#"):
            head = "## " + head
        lines.append(head)
    s = " ".join(summary.split())
    if s:
        lines.append(s)
    trig = [t.strip() for t in triggers if t and t.strip()]
    if trig:
        # Short single-line declarations stay on one compact "Triggers:" line.
        # Anything that is a numbered rule, a bulleted prohibition, or a
        # multi-line unit is emitted VERBATIM on its own lines: joining those
        # with " · " is what produced the 2026-11-04 gibberish.
        simple = [
            t for t in trig
            if _RULE_LINE_RE.match(t) is None
            and _BULLET_GATE_RE.match(t) is None
            and _TRIGGER_DECL_RE.match(t) is not None
            and len(t) <= 200
        ]
        structured = [t for t in trig if t not in simple]
        if simple:
            lines.append("**Triggers:** " + " · ".join(simple))
        if structured:
            lines.append("**Binding rules (kept verbatim — these are in force):**")
            lines.extend(structured)
    target = ref_path if not anchor else f"{ref_path} §{anchor}"
    lines.append(f"{POINTER_SENTINEL} {target} — read it BEFORE acting on this "
                 f"surface; never work from memory.")
    return "\n".join(lines)


def write_reference(ref_file: Path, marker: str, full_text: str) -> bool:
    """Idempotently place `full_text` under its REF marker pair. True if changed.

    Raises OSError on an unwritable destination; the caller turns that into a
    REFUSAL rather than stamping a pointer that would dangle.
    """
    rbegin, rend = _ref_markers(marker)
    existing = _read(ref_file)
    body = f"## {marker}\n\n{full_text.strip()}"
    block = f"{rbegin}\n{body}\n{rend}"

    i = existing.find(rbegin)
    if i >= 0:
        j = existing.find(rend, i + len(rbegin))
        if j >= 0:
            updated = existing[:i] + block + existing[j + len(rend):]
        else:
            updated = existing.rstrip("\n") + "\n\n" + block + "\n"
    elif existing.strip():
        updated = existing.rstrip("\n") + "\n\n" + block + "\n"
    else:
        header = (
            "# Bootstrap reference — full text of managed blocks\n\n"
            "Written by the fleet roll. The box's bootstrap files carry a compact\n"
            "POINTER to each section here; this file carries the VERBATIM text.\n"
            "Do not hand-edit: the next roll rewrites every REF block below.\n"
        )
        updated = header + "\n" + block + "\n"

    if updated == existing:
        return False
    ref_file.parent.mkdir(parents=True, exist_ok=True)
    tmp = ref_file.with_suffix(ref_file.suffix + ".tmp")
    tmp.write_text(updated, encoding="utf-8")
    os.replace(tmp, ref_file)
    return True


def stamp(bootstrap: Path, marker: str, ref_file: Path, heading: str, summary: str,
          triggers: list[str], full_text: str | None, mode: str,
          anchor: str = "") -> dict:
    """Stamp one managed block as a pointer (or as full text when mode=full)."""
    current_doc = _read(bootstrap)
    current_block = extract_block(current_doc, marker)

    # Source of truth for the full text, in priority order:
    #   1. what the caller shipped this run (--full-text-file)
    #   2. what the bootstrap file already holds (MIGRATION of a fat box)
    #   3. what the reference file already holds (re-stamp after a hand edit)
    text = full_text
    if text is None and current_block is not None and POINTER_SENTINEL not in current_block:
        text = current_block
    if text is None:
        prior = extract_block(_read(ref_file).replace("BEGIN REF ", "BEGIN ")
                              .replace("END REF ", "END "), marker)
        if prior is not None:
            # Strip the "## <marker>" heading write_reference added.
            text = re.sub(r"^##\s+" + re.escape(marker) + r"\s*\n+", "", prior).strip()
    if text is None or not text.strip():
        return {"marker": marker, "status": "skipped",
                "reason": "no full text available from caller, bootstrap or reference"}

    if mode == "full":
        new_block = text.strip()
        ref_changed = False
    else:
        try:
            ref_changed = write_reference(ref_file, marker, text)
        except OSError as exc:
            return {"marker": marker, "status": "refused",
                    "reason": f"reference file unwritable: {exc.__class__.__name__}",
                    "reference": str(ref_file)}
        new_block = build_pointer(heading, summary, triggers, str(ref_file),
                                  anchor or marker)

    updated_doc = replace_block(current_doc, marker, new_block)
    if updated_doc == current_doc:
        return {"marker": marker, "status": "unchanged",
                "reference": str(ref_file), "reference_written": ref_changed,
                "bootstrap_chars": len(current_doc)}

    try:
        bootstrap.parent.mkdir(parents=True, exist_ok=True)
        tmp = bootstrap.with_suffix(bootstrap.suffix + ".tmp")
        tmp.write_text(updated_doc, encoding="utf-8")
        os.replace(tmp, bootstrap)
    except OSError as exc:
        return {"marker": marker, "status": "refused",
                "reason": f"bootstrap file unwritable: {exc.__class__.__name__}",
                "bootstrap": str(bootstrap)}

    return {
        "marker": marker,
        "status": "written",
        "reference": str(ref_file),
        "reference_written": ref_changed,
        "before_chars": len(current_doc),
        "after_chars": len(updated_doc),
        "saved_chars": len(current_doc) - len(updated_doc),
    }


# ───────────────────────────── the migration sweep ──────────────────────────
#
# WHY A SWEEP AND NOT JUST A BETTER WRITER
#   Fixing each stamper only helps a box that has not been wired yet. Every
#   stamper in this repo skips when its idempotency guard matches, so on an
#   ALREADY-wired box the writer never runs again and the fat block sits there
#   forever. The sweep is the migration path: it walks the managed blocks that
#   are already on the box and pointerizes the ones that are still full text.
#
# WHAT STAYS INLINE
#   A pointer that hides a prohibition is a downgrade. So the sweep keeps inline,
#   verbatim, every line carrying a hard-gate signal — the same rule the skill-38
#   pointer writer states in its own header ("the prohibitions/trigger phrases
#   that MUST bind inline"). Everything else moves to the reference file.

# A line is kept inline only when it DECLARES a gate or a trigger at its START.
# Matching a bare "NEVER" ANYWHERE in a line was tried first and was worse than
# useless: prose wraps mid-sentence, so it harvested fragments like
# `that in?"). NEVER post an audience you inferred` and joined them into a
# "Triggers:" line that read as gibberish. A pointer that garbles the rule it
# points at is a downgrade over the bloat it replaces, so the test is anchored.
_GATE_LINE_RE = re.compile(
    r"""^\s*(?:
          [⛔🚫❌]                                   # a gate glyph opens the line
        | \*{0,2}(?:TRIGGERS?|TRIGGER\ PHRASES?)\*{0,2}\s*:   # a trigger declaration
        | \*{0,2}(?:NEVER|ALWAYS|MUST\ NOT|DO\ NOT|REFUSE|HARD\ GATE)\b
        | [-*]\s+\*{0,2}(?:NEVER|ALWAYS|MUST\ NOT|DO\ NOT|REFUSE)\b
    )""",
    re.IGNORECASE | re.VERBOSE,
)
HARD_GATE_MAX_LINES = 6

# A managed block whose NAME or HEADING declares binding rules is never reduced
# to a pointer. Pointerizing one is how SKILL38_RUNTIME_INVARIANTS lost its six
# safety rules on 2026-11-04 while still claiming they were in force.
PROTECTED_BLOCK_RE = re.compile(
    r"(INVARIANTS|SAFETY|HARD[\s_-]*RULE|NEVER[\s_-]*DO|PROHIBIT|GATE\b)",
    re.IGNORECASE,
)

# A numbered rule: "1. ", "2) " ... kept WHOLE (item + continuation lines).
_RULE_LINE_RE = re.compile(r"^\s*\d+[.)]\s+\S")
# A bulleted prohibition.
_BULLET_GATE_RE = re.compile(
    r"^\s*[-*]\s+\*{0,2}(?:NEVER|ALWAYS|MUST\s+NOT|DO\s+NOT|REFUSE|HARD\s+GATE)\b",
    re.IGNORECASE,
)


# A line that DECLARES a trigger at the top of a block. This is stricter than
# _GATE_LINE_RE on purpose: _GATE_LINE_RE exists to catch a prohibition that
# starts a paragraph, while this one only accepts an actual declaration.
_TRIGGER_DECL_RE = re.compile(
    r"""^\s*(?:
          [⛔🚫❌]
        | \*{0,2}(?:TRIGGERS?|TRIGGER\ PHRASES?)\*{0,2}\s*:
    )""",
    re.IGNORECASE | re.VERBOSE,
)


_BOLD_GATE_RE = re.compile(
    r"\*\*\s*(?:NEVER|ALWAYS|MUST\s+NOT|DO\s+NOT|REFUSE|HARD\s+GATE)\b",
    re.IGNORECASE,
)


def _binding_units(body: str) -> list[list[str]]:
    """Every binding unit in a block, as the list of its raw lines.

    A binding unit is:
      * a numbered rule, kept WHOLE with its continuation lines;
      * a bulleted prohibition;
      * a trigger declaration;
      * a prohibition that OPENS a paragraph (previous line blank).

    The paragraph-start requirement is what stops hard-wrapped prose from being
    chopped into fragments. A line reading "never to a parallel sequence.**" is
    the middle of a sentence, not a rule, and treating it as one is exactly how
    the 2026-11-04 pointer garbled six safety rules.
    """
    units, cur = [], []
    prev_blank = True
    for line in body.splitlines():
        if not line.strip():
            if cur:
                units.append(cur)
                cur = []
            prev_blank = True
            continue
        starts_new = (
            _RULE_LINE_RE.match(line)
            or _BULLET_GATE_RE.match(line)
            or _TRIGGER_DECL_RE.match(line)
            or (prev_blank and _GATE_LINE_RE.match(line))
            # A BOLDED prohibition is a declaration wherever it sits. The whole
            # line (and its continuation) is kept -- never a slice of it.
            or _BOLD_GATE_RE.search(line)
        )
        if starts_new:
            if cur:
                units.append(cur)
            cur = [line]
        elif cur:
            cur.append(line)
        prev_blank = False
    if cur:
        units.append(cur)
    return units


def _pointer_gate(body: str, ptr: str) -> str:
    """Empty string when the pointer is safe; otherwise the reason it is not.

    A pointer may only be stamped if every binding unit that was in the block
    is still legible in the pointer. This is the check that did not exist when
    the sweep mangled SKILL38_RUNTIME_INVARIANTS: the block was replaced by
    harvested fragments and nothing validated that the rules survived.
    """
    units = _binding_units(body)
    if not units:
        return ""
    if ptr.count("**") % 2:
        return "pointer would carry an unbalanced bold marker"
    # Every LINE of every unit must survive, not just the opening 80 characters:
    # a gate that only checks a prefix cannot notice continuation lines being
    # dropped, which is how the original damage stayed invisible.
    flat = re.sub(r"\s+", " ", ptr)
    missing = []
    for unit in units:
        # The unit must survive as an ORDERED BLOCK. Checking lines one by one
        # lets a shared line satisfy two different rules while one of them has
        # actually lost it.
        block = re.sub(r"\s+", " ", " ".join(l.strip() for l in unit)).strip()
        if block and block not in flat:
            missing.append(block[:80])
    if missing:
        return ("would drop %d binding rule(s) — left verbatim (first: %s)"
                % (len(missing), missing[0][:60]))
    # A pointer that keeps nearly everything saves nothing and only adds a
    # second place for the rules to drift. Leave such a block alone.
    if len(ptr) >= len(body) * 0.9:
        return ("pointer would not save space (%d -> %d chars) — left verbatim"
                % (len(body), len(ptr)))
    return ""

# Two shapes of managed block exist in this repo, and both must survive a sweep
# with their idempotency guard still matching:
#   PAIR     <!-- BEGIN name --> ... <!-- END name -->   (skill:*, SKILL38:*)
#   SENTINEL <!-- NAME_V1 -->\n## Heading\n...           (apply-fleet-standards.sh)
# For SENTINEL blocks the guard is `grep -qF "<!-- NAME_V1 -->"`, so the sentinel
# AND its heading are preserved and only the body below them is replaced.
_PAIR_RE = re.compile(r"<!--\s*BEGIN ([^>]+?)\s*-->")
_SENTINEL_RE = re.compile(r"^<!--\s*([A-Z][A-Z0-9_]*_V\d+)\s*-->[ \t]*$", re.MULTILINE)
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$", re.MULTILINE)


def _derive(body: str) -> tuple[str, str, list[str]]:
    """Heading, one-line summary, and the binding text that must stay inline.

    Binding text is kept VERBATIM AND WHOLE. The previous version sliced
    individual lines that happened to begin with "NEVER"/"Never" out of
    hard-wrapped prose and joined them with " · ", which turned a block of six
    numbered safety rules into `**Triggers:** NEVER open a gate. · never to a
    parallel sequence.** Never enter the ...` -- a pointer that garbled the
    rules it replaced while still promising they bound.
    """
    heading, summary, keep = "", "", []
    lines = body.splitlines()
    seen: set[str] = set()

    def _add(unit_lines: list[str]) -> None:
        # No cross-unit dedupe. Two rules may legitimately share an identical
        # continuation line; dropping the second copy silently weakens rule two
        # while the gate still passes because the line exists once.
        for raw in unit_lines:
            s = raw.rstrip()
            if s.strip():
                keep.append(s)

    i = 0
    while i < len(lines):
        line = lines[i]
        s = line.strip()
        if not s:
            i += 1
            continue
        m = _HEADING_RE.match(line)
        if m and not heading and not keep:
            heading = m.group(2).strip()
            i += 1
            continue
        if _RULE_LINE_RE.match(line) or _BULLET_GATE_RE.match(line) or _GATE_LINE_RE.match(line):
            unit = [line]
            j = i + 1
            while j < len(lines):
                nxt = lines[j]
                if not nxt.strip():
                    break
                if (_HEADING_RE.match(nxt) or _RULE_LINE_RE.match(nxt)
                        or _BULLET_GATE_RE.match(nxt) or _GATE_LINE_RE.match(nxt)):
                    break
                unit.append(nxt)
                j += 1
            _add(unit)
            i = j
            continue
        if not summary and not s.startswith(("<!--", ">", "```", "|", "-", "*", "#")):
            summary = s
        i += 1
    if not summary:
        summary = "Managed block — full text moved out of the bootstrap file."
    if len(summary) > 240:
        summary = summary[:237].rstrip() + "..."
    return heading, summary, keep


def _sentinel_blocks(text: str) -> list[tuple[str, int, int, int]]:
    """(name, sentinel_start, body_start, body_end) for each sentinel section.

    A sentinel that OWNS a matching `<!-- END NAME -->` is deliberately excluded.
    Those blocks (PRESENTATION_ROUTING_REFLEX_*, SKILL_INTENT_ROUTING_REFLEX_*,
    CEO_ROUTING_NO_LOOPHOLES_*) are rewritten WHOLESALE on every roll by
    apply-fleet-standards.sh's own strip/upgrade branches, which regex on the
    START/END pair. Pointerizing one is pointless (the next roll re-expands it)
    and dangerous: the first cut of this sweep ran the body to the next `##`
    heading and SWALLOWED the END marker, orphaning the pair and breaking the
    upgrade branch that keys on it. Only append-only sentinels — the ones with
    no END, which is exactly the set apply-fleet-standards.sh guards with a bare
    `grep -qF "<!-- NAME -->"` — are swept.
    """
    out = []
    for m in _SENTINEL_RE.finditer(text):
        name = m.group(1)
        if f"<!-- END {name} -->" in text:
            continue
        # Body starts after the sentinel line and after its heading line if present.
        pos = m.end()
        rest = text[pos:]
        lead = re.match(r"\n*(#{1,6}[^\n]*\n)", rest)
        body_start = pos + (lead.end() if lead else 0)
        # Section ends at the next heading, the next sentinel, or ANY marker
        # comment — never past a boundary another writer owns.
        end = len(text)
        for pat in (r"^#{1,6}\s", r"^<!--"):
            nxt = re.search(pat, text[body_start:], re.MULTILINE)
            if nxt:
                end = min(end, body_start + nxt.start())
        out.append((name, m.start(), body_start, end))
    return out


def sweep(bootstrap: Path, ref_file: Path, mode: str, min_chars: int,
          skip: list[str], dry_run: bool) -> dict:
    """Pointerize every managed block on this box that is still full text."""
    original = _read(bootstrap)
    if not original:
        return {"status": "skipped", "reason": "bootstrap file empty or unreadable",
                "bootstrap": str(bootstrap)}
    text = original
    acted, skipped = [], []
    skip_res = [re.compile(s) for s in skip]

    def _skipped(name: str, body: str = "") -> bool:
        if PROTECTED_BLOCK_RE.search(name):
            return True
        if body:
            # EVERY heading, not just the first: a block can open with an
            # innocuous heading and declare "## Safety" further down.
            for m in _HEADING_RE.finditer(body):
                if PROTECTED_BLOCK_RE.search(m.group(2)):
                    return True
        return any(r.search(name) for r in skip_res)

    # ── PAIR blocks ──────────────────────────────────────────────────────────
    for name in [m.group(1).strip() for m in _PAIR_RE.finditer(original)]:
        if name.startswith("REF "):
            continue
        body = extract_block(text, name)
        if body is None:
            continue
        if POINTER_SENTINEL in body:
            skipped.append({"marker": name, "why": "already a pointer"}); continue
        if _skipped(name, body):
            skipped.append({"marker": name, "why": "excluded by --skip"}); continue
        if len(body) < min_chars:
            skipped.append({"marker": name, "why": f"under {min_chars} chars"}); continue
        heading, summary, keep = _derive(body)
        if mode == "full":
            continue
        ptr = build_pointer(heading, summary, keep, str(ref_file), name)
        gate = _pointer_gate(body, ptr)
        if gate:
            skipped.append({"marker": name, "why": gate}); continue
        if not dry_run:
            try:
                write_reference(ref_file, name, body)
            except OSError as exc:
                skipped.append({"marker": name,
                                "why": f"reference unwritable: {exc.__class__.__name__}"})
                continue
        text = replace_block(text, name, ptr)
        acted.append({"marker": name, "kind": "pair",
                      "from_chars": len(body), "to_chars": len(ptr)})

    # ── SENTINEL sections ────────────────────────────────────────────────────
    # Rebuilt each pass because every edit shifts later offsets.
    while True:
        changed = False
        for name, _s, bstart, bend in _sentinel_blocks(text):
            body = text[bstart:bend].strip("\n")
            if not body or POINTER_SENTINEL in body:
                continue
            if _skipped(name, body):
                continue
            if len(body) < min_chars:
                continue
            heading, summary, keep = _derive(body)
            if mode == "full":
                continue
            gate = _pointer_gate(body, build_pointer("", summary, keep, str(ref_file), name))
            if gate:
                skipped.append({"marker": name, "why": gate})
                continue
            if not dry_run:
                try:
                    write_reference(ref_file, name, body)
                except OSError as exc:
                    skipped.append({"marker": name,
                                    "why": f"reference unwritable: {exc.__class__.__name__}"})
                    continue
            # Heading stays with the sentinel above the body, so only the body
            # is replaced — the `grep -qF "<!-- NAME_V1 -->"` guard still matches.
            ptr = build_pointer("", summary, keep, str(ref_file), name)
            text = text[:bstart] + ptr + "\n\n" + text[bend:]
            acted.append({"marker": name, "kind": "sentinel",
                          "from_chars": len(body), "to_chars": len(ptr)})
            changed = True
            break
        if not changed:
            break

    for e in skipped:
        e.setdefault("kind", "skip")

    result = {
        "bootstrap": str(bootstrap),
        "reference": str(ref_file),
        "mode": mode,
        "before_chars": len(original),
        "after_chars": len(text),
        "saved_chars": len(original) - len(text),
        "pointerized": acted,
        "skipped": skipped,
        "dry_run": dry_run,
    }
    if text == original:
        result["status"] = "unchanged"
        return result
    if dry_run:
        result["status"] = "would-change"
        return result
    try:
        tmp = bootstrap.with_suffix(bootstrap.suffix + ".tmp")
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, bootstrap)
    except OSError as exc:
        result["status"] = "refused"
        result["reason"] = f"bootstrap unwritable: {exc.__class__.__name__}"
        return result
    result["status"] = "written"
    return result


def main(argv: list[str] | None = None) -> int:
    if argv is None:
        argv = sys.argv[1:]
    if argv and argv[0] == "sweep":
        return _main_sweep(argv[1:])
    if argv and argv[0] == "stamp":
        argv = argv[1:]
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--bootstrap", type=Path, required=True,
                   help="bootstrap file to stamp (AGENTS.md, TOOLS.md, ...)")
    p.add_argument("--marker", required=True,
                   help="marker NAME without the comment syntax, e.g. 'skill:36-x:agents'")
    p.add_argument("--ref-file", type=Path, required=True,
                   help="absolute path of the reference file the pointer names")
    p.add_argument("--heading", default="", help="pointer heading")
    p.add_argument("--summary", default="", help="one-line summary")
    p.add_argument("--trigger", action="append", default=[],
                   help="an exact trigger phrase that must bind inline (repeatable)")
    p.add_argument("--anchor", default="", help="section anchor inside the reference file")
    p.add_argument("--full-text-file", type=Path,
                   help="file holding this run's full text; omit to migrate what is on the box")
    p.add_argument("--mode", choices=("pointer", "full"),
                   default=os.environ.get("OPENCLAW_BOOTSTRAP_POINTER_MODE",
                                          POINTER_MODE_DEFAULT),
                   help="pointer (default) writes a pointer; full restores verbatim text")
    a = p.parse_args(argv)

    if not a.ref_file.is_absolute():
        print(json.dumps({"status": "refused",
                          "reason": "--ref-file must be ABSOLUTE (a pointer is read by an "
                                    "agent whose cwd is unknown)"}))
        return 4

    full_text = None
    if a.full_text_file is not None:
        full_text = _read(a.full_text_file)
        if not full_text.strip():
            print(json.dumps({"status": "refused",
                              "reason": "--full-text-file is empty or unreadable",
                              "path": str(a.full_text_file)}))
            return 4

    result = stamp(a.bootstrap, a.marker, a.ref_file, a.heading, a.summary,
                   a.trigger, full_text, a.mode, a.anchor)
    print(json.dumps(result, indent=2))
    return {"written": 0, "unchanged": 10, "skipped": 10, "refused": 3}.get(
        result["status"], 3)


def _main_sweep(argv: list[str]) -> int:
    p = argparse.ArgumentParser(prog="bootstrap-pointerize.py sweep",
                                description="Pointerize managed blocks already on this box.")
    p.add_argument("--bootstrap", type=Path, required=True)
    p.add_argument("--ref-file", type=Path, required=True)
    p.add_argument("--min-chars", type=int,
                   default=int(os.environ.get("OPENCLAW_BOOTSTRAP_POINTER_MIN_CHARS", "800")),
                   help="leave blocks smaller than this inline (default 800)")
    p.add_argument("--skip", action="append", default=[],
                   help="regex of marker names to leave alone (repeatable)")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--mode", choices=("pointer", "full"),
                   default=os.environ.get("OPENCLAW_BOOTSTRAP_POINTER_MODE",
                                          POINTER_MODE_DEFAULT))
    a = p.parse_args(argv)
    if not a.ref_file.is_absolute():
        print(json.dumps({"status": "refused", "reason": "--ref-file must be ABSOLUTE"}))
        return 4
    r = sweep(a.bootstrap, a.ref_file, a.mode, a.min_chars, a.skip, a.dry_run)
    print(json.dumps(r, indent=2))
    return {"written": 0, "would-change": 0, "unchanged": 10,
            "skipped": 10, "refused": 3}.get(r["status"], 3)


if __name__ == "__main__":
    sys.exit(main())
