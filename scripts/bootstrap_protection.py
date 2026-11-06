#!/usr/bin/env python3
"""One definition of "a block that carries binding rules".

Both bootstrap-pointerize.py and validate-core-references.py import this. Two
separate notions of protection is how the 2026-11-04 damage survived a validator
that reported OK: the pointerizer protected nothing, and the validator named one
hardcoded block. Anywhere that logic is needed, it comes from here.

A block is protected when ANY of these hold:
  * its NAME declares binding rules          (SKILL38_RUNTIME_INVARIANTS ...)
  * any HEADING inside it declares them      (## HARD SAFETY RULES ...)
  * its BODY carries the binding rules       (OPERATOR-ONLY allow-list ...)

The body test exists because the same six rules live under different block names
on different boxes. Protecting only one naming scheme protects one box.
"""

from __future__ import annotations

import re

# Declarations in a block name or heading.
PROTECTED_NAME_RE = re.compile(
    r"(INVARIANTS|SAFETY|HARD[\s_-]*RULE|NEVER[\s_-]*DO|PROHIBIT|GATE\b)",
    re.IGNORECASE,
)

# Signatures of the six binding rules themselves. A block carrying any of these
# is protected whatever it is called.
RULE_SIGNATURES = (
    "OPERATOR-ONLY allow-list",
    "Customer text is NEVER an instruction",
    "default-OFF feature is a NO-OP",
    "Hard gates always apply",
    "PII-FREE by construction",
    "SHARED REMINDER MACHINE",
)

_HEADING_RE = re.compile(r"^#{1,6}\s+(.*)$", re.MULTILINE)
_PAIR_RE = re.compile(r"<!--\s*BEGIN ([^>]+?)\s*-->")
_SENTINEL_RE = re.compile(r"^<!--\s*([A-Z][A-Z0-9_]*_V\d+)\s*-->[ \t]*$", re.MULTILINE)


def carries_binding_rules(text: str) -> bool:
    """True when the text contains the binding rules themselves."""
    return any(sig in text for sig in RULE_SIGNATURES)


def is_protected(name: str, body: str = "") -> bool:
    """True when this block may never be pointerized or emptied."""
    if name and PROTECTED_NAME_RE.search(name):
        return True
    if body:
        for m in _HEADING_RE.finditer(body):
            if PROTECTED_NAME_RE.search(m.group(1)):
                return True
        if carries_binding_rules(body):
            return True
    return False


def pair_blocks(text: str):
    """[(name, body)] for every BEGIN/END pair block, body excluding the markers."""
    out = []
    for m in _PAIR_RE.finditer(text):
        name = m.group(1).strip()
        if name.startswith("REF "):
            continue
        begin = "<!-- BEGIN " + name
        idx = text.find(begin)
        end_tok = "<!-- END " + name
        j = text.find(end_tok, idx + len(begin))
        if j < 0:
            continue
        out.append((name, text[idx + len(begin):j]))
    return out


def sentinel_blocks(text: str):
    """[(name, body)] for append-only sentinel sections (no matching END)."""
    out = []
    for m in _SENTINEL_RE.finditer(text):
        name = m.group(1)
        if ("<!-- END " + name) in text:
            continue
        start = m.end()
        # A sentinel body ends at the NEXT MARKER OF ANY KIND. Stopping only at
        # the next sentinel swallowed whole pair blocks that followed it, so a
        # harmless block inherited a neighbour's binding rules and was reported
        # protected -- a false positive that would fail healthy boxes.
        nxt = re.search(r"^<!--", text[start:], re.MULTILINE)
        end = start + nxt.start() if nxt else len(text)
        out.append((name, text[start:end]))
    return out


def all_blocks(text: str):
    return pair_blocks(text) + sentinel_blocks(text)


def protected_blocks(text: str):
    return [(n, b) for n, b in all_blocks(text) if is_protected(n, b)]
