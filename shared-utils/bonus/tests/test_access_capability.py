#!/usr/bin/env python3
"""Self-check for T-14 — bonus membership/access capability decision.

Pins every acceptance clause of the task record (R-13, C-14, C-F07) and the
refusal cases, so a future edit cannot quietly promote an unproved step to
"supported" or gate the original gift on the bonus lane.

  C-14  current official route/tenant requirements, mobile-only
        identity/token/recovery evidence or the EXACT capability block, and no
        fabricated API;
  C-F07 original gift proceeds while the bonus is unavailable.

Run: python3 -m unittest discover -s shared-utils/bonus/tests -v
     (from the repository root; the dotted path does not resolve through the
      hyphenated `shared-utils` directory, so it is not offered here)
"""

from __future__ import annotations

import json
import os
import re
import sys
import unicodedata
import unittest
from pathlib import Path

_TESTS = Path(__file__).resolve().parent
_BONUS = _TESTS.parent
_SHARED = _BONUS.parent
_REPO = _SHARED.parent
for _p in (str(_SHARED), str(_REPO)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from bonus import access_capability as ac  # noqa: E402


# --------------------------------------------------------------------------
# Fabricated-API detector
# --------------------------------------------------------------------------
# One place decides what an invented interface looks like. The route surface is
# searched for every shape; Python source is searched for the four that cannot
# be legitimate there. A dotted token is NOT searched in Python source because
# attribute access (`cap.transport.value`) is real Python — a smuggled operation
# id has to reach the returned surface to matter, and that surface is covered.

_URL = re.compile(r"https?://", re.I)
# `\s*`, not `\s+`: a verb glued to its path (`POST/memberships/grant`) is the
# same fabrication as a spaced one. `\S+`, not `\S*`: a verb with nothing behind
# the slash (`POST/`) is a verb and no operation, and must not be flagged.
_VERB_PATH = re.compile(r"\b(?:GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS)\s*/\S+", re.I)
# A bare operation path, in two forms:
#   1. slash-led, delimited by whitespace, a quote or a value separator
#      (`"/memberships/grant"`). Always flagged.
#   2. identifier-prefixed: any [A-Za-z0-9_] run glued in front of the first
#      `/` (`v1/memberships/grant`, `memberships/grant`). Shape alone cannot
#      tell it from real prose (`memberships/communities`, `assisted/operator`),
#      so the world is closed: the token passes only as file provenance, or as a
#      reviewed slash token inside the exact sentence it was reviewed in. A new
#      token, or a reviewed token outside its sentence, fails until a human
#      reviews it. An exemption no longer travels with the token alone, so a
#      reviewed token cannot excuse an `api` or `route` value.
#   3. a trailing path segment with no segment behind it (`memberships/`): the
#      operation family with its operation cut off is still operation-shaped.
# The forms cannot overlap, so form 1 flags exactly what it did before.
_BARE_PATH = re.compile(
    r"(?:^|(?<=[\s\"'=(:,]))/[A-Za-z0-9_{][A-Za-z0-9_\-{}/.]*"
    r"|(?<![A-Za-z0-9_\-.{}/])[A-Za-z0-9_{][A-Za-z0-9_\-.{}]*(?:/[A-Za-z0-9_\-.{}]*[A-Za-z0-9_}])+"
)
REVIEWED_SLASH_TOKENS = frozenset({
    "assisted/operator",
    "course/credential",
    "courses/memberships",
    "create/delete",
    "identity/grant/credential/SMS/resource",
    "login/credential",
    "Membership/course",
    "memberships/communities",
    "return/recovery",
    "shared-utils/ghl",
    # PBB-387: the padded spelling of a path separator is the same class as the
    # glued one, so a pair of segments split by spaces is an operation shape.
    # This is the one sentence in the deliverable's own prose that carries such
    # a pair -- a citation pair, not a path -- and it was reviewed in that exact
    # sentence, which is the only way prose passes.
    "R-13 / DEC-16",
})
# The SAME path-segment class, in its padded spelling: `x / y`. A whitespace run
# on both sides of a solidus is a path separator like any other, so it is one
# class with the glued form -- and it cannot be told apart from prose
# alternation by shape, so the closed world below is what keeps prose readable
# while an unpadded or padded spelling of a new operation still fails.
_SPACED_PATH = re.compile(
    r"(?<![A-Za-z0-9_/.-])[A-Za-z0-9_{][A-Za-z0-9_\-.{}]* / "
    r"[A-Za-z0-9_{][A-Za-z0-9_\-.{}]*(?![A-Za-z0-9_/.-])"
)
_SCHEMELESS_HOST = re.compile(r"\b(?:[a-z0-9][a-z0-9-]*\.)+[a-z][a-z0-9-]*(?::\d+)?/[A-Za-z0-9]")
_DOTTED_OPERATION = re.compile(r"\b[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+\b")
_FILE_SUFFIXES = (
    ".py", ".md", ".json", ".txt", ".sh", ".yml", ".yaml", ".toml", ".cfg",
    ".ini", ".html", ".js", ".ts", ".css", ".csv", ".xml", ".png", ".jpg",
)
_TRAILING_SEGMENT = re.compile(
    r"(?<![A-Za-z0-9_\-.{}/])[A-Za-z0-9_{][A-Za-z0-9_\-.{}]*/(?![A-Za-z0-9_\-.{}/])"
)
# A bare verb with a slash behind it is a verb, never an operation.
_HTTP_VERBS = frozenset({"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"})

# Role beats shape. Whatever a token names -- a real file, a reviewed sentence,
# anything -- behind one of these keys it is an operation VALUE, and no
# provenance or prose exemption survives that position. This is the class the
# PBB-260 and PBB-311 defects shared: the exemptions were keyed on what the
# token looked like and applied whatever role the token was playing.
#
# PBB-387 DESIGN CHANGE. PBB-371 charged that the "structural" role check was
# two enumerated lists -- a wrapper whitelist and a separator whitelist -- and
# that any spelling outside them walked past every rule (angle brackets,
# typographic quotes, an em dash, a doubled separator, unicode arrows,
# zero-width characters, mixed seam spellings). Character stripping cannot
# close that class, because every new spelling has to be typed into a list.
# The role is read off a TOKEN STREAM instead: the head text is scanned once
# into identifier / string / bracket / separator tokens, and the governing key
# is the key token before the value across a seam. There is no wrapper spelling
# and no separator spelling to enumerate, so there is none to miss.
#
# A seam is a run carrying at least one non-whitespace separator character
# between a key token and the value. Whitespace alone is prose, not a seam, so
# `see the path shared-utils/...` does not read `path` as a key.
# Frames are walked to their real depth -- the stack is the nesting that is
# actually in the text -- so a nested value answers to its parent key however
# deep the nesting goes.
#
# PBB-443 DEFECT 1: THE DEFAULT IS INVERTED. There is no key vocabulary here
# any more. The previous read returned a role only for nine typed spellings
# (`api`, `route`, ...), so behind any other key -- `href`, `target`, `op`,
# `apis`, `end-point` -- a real repo path kept its file-provenance exemption
# and read as an innocent citation. A hand-written list of spellings can never
# be closed: every repair that adds nine more just moves the boundary. The read
# now answers one structural question -- IS A KEY BOUND TO THIS TOKEN -- and
# whatever that key spells, the token is a value. The DEFAULT is then fail
# closed: a value carries no exemption at all, and the only way it is allowed
# is a declared legitimate prose context (REVIEWED_PROSE_CONTEXTS or
# LEGITIMATE_TEXT, both closed worlds below). So an unrecognised key carrying a
# real repo path FAILS, and only a reviewed sentence lets it through. What is
# derived is derived rather than typed: the quote characters and the path
# separators come out of Unicode names, not out of a list somebody typed.
_OPENERS = {"(": ")", "[": "]", "{": "}"}
_CLOSERS = {v: k for k, v in _OPENERS.items()}
# A string delimiter is any character Unicode calls a quotation mark, plus the
# two it calls an apostrophe and a grave accent. DERIVED from the name, like the
# path-separator table below, so a delimiter nobody typed here is in class too.
def _quote_table():
    out = []
    for codepoint in range(0x110000):
        char = chr(codepoint)
        name = unicodedata.name(char, "")
        if "QUOTATION MARK" in name or name in ("APOSTROPHE", "GRAVE ACCENT"):
            out.append(char)
    return "".join(out)


_STRING_QUOTES = _quote_table()
# A string prefix is part of the literal it opens (`f"..."`, `rb'...'`), so the
# prefix is never read as a key of its own. DERIVED, not typed: a prefix is a
# run of one or two alphabetic characters sitting on a delimiter, whatever the
# letters are. `api"..."` is three letters and stays a key; `zz'...'` is a
# literal just like `rb'...'`.
_STRING_PREFIX = re.compile(r"^[^\W\d_]{1,2}$")
_ROLE_WINDOW = 4000


def _tokens(text):
    """Identifier / string / bracket / separator tokens, with their offsets.

    Brackets and quotes are STRUCTURE, so a bracket inside a string literal is
    never mistaken for a frame boundary and the wrapper characters around a
    value cannot be stripped away before the role is read.
    """
    out = []
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        if ch.isalnum() or ch == "_":
            j = i + 1
            while j < n and (text[j].isalnum() or text[j] in "_-"):
                j += 1
            if j < n and text[j] in _STRING_QUOTES and _STRING_PREFIX.match(text[i:j]):
                quote = text[j]
                k = j + 1
                while k < n and text[k] != quote:
                    k += 2 if text[k] == "\\" else 1
                k = min(k + 1, n)
                out.append(("STR", text[j + 1:k - 1] if k - j > 2 else "", i, k))
                i = k
                continue
            out.append(("ID", text[i:j], i, j))
            i = j
        elif ch in _STRING_QUOTES:
            j = i + 1
            while j < n and text[j] != ch:
                j += 2 if text[j] == "\\" else 1
            j = min(j + 1, n)
            out.append(("STR", text[i + 1:j - 1] if j - i > 2 else "", i, j))
            i = j
        elif ch in _OPENERS or ch in _CLOSERS:
            out.append(("OPEN" if ch in _OPENERS else "CLOSE", ch, i, i + 1))
            i += 1
        else:
            j = i + 1
            while j < n and not (
                text[j].isalnum()
                or text[j] in "_-" + _STRING_QUOTES + "()[]{}"
            ):
                j += 1
            out.append(("SEP", text[i:j], i, j))
            i = j
    return out


def _match_opener(tokens, close_at):
    """Index of the opener that closes `tokens[close_at]`, or None."""
    want = _CLOSERS[tokens[close_at][1]]
    depth = 0
    for k in range(close_at - 1, -1, -1):
        kind, val, _, _ = tokens[k]
        if kind == "CLOSE":
            depth += 1
        elif kind == "OPEN":
            if depth == 0:
                return k if val == want else None
            depth -= 1
    return None


def _innermost_open_before(tokens, at):
    depth = 0
    for k in range(at - 1, -1, -1):
        kind, _, _, _ = tokens[k]
        if kind == "CLOSE":
            depth += 1
        elif kind == "OPEN":
            if depth == 0:
                return k
            depth -= 1
    return None


def _is_subscript(tokens, open_at):
    """`[` at `open_at` indexes something; it is not an array literal."""
    return (
        open_at > 0
        and tokens[open_at - 1][0] in ("ID", "STR", "CLOSE")
    )


def _bracket_key(tokens, open_at, close_at):
    """The key a bracket group carries, or "".

    `spec["api"]` carries `api` as its key. `{"api": [ ... ]}` is an array
    literal and carries no key of its own -- its key sits before the bracket,
    where the walk finds it.
    """
    if tokens[open_at][1] != "[" or not _is_subscript(tokens, open_at):
        return ""
    for tok in reversed(tokens[open_at + 1:close_at]):
        if tok[0] in ("ID", "STR") and tok[1]:
            return tok[1]
    return ""


def _seam(tokens, at):
    """(key token, separator run) ending at `at`, or (None, "").

    A seam is a separator run carrying at least one non-whitespace character.
    Whitespace alone joins words, not a key to a value. A COMMA is a member
    separator, not a binding: in `["a.md", "b.md"]` the run before `b.md` joins
    two list members and binds nothing, so the second element is not the value
    of the first. PBB-443: without this, every list element after the first
    read as a value with the previous element as its key.
    """
    i = at
    run = ""
    while i > 0 and tokens[i - 1][0] == "SEP":
        run = tokens[i - 1][1] + run
        i -= 1
    if not run or not run.strip() or "," in run:
        return None, ""
    if i == 0 or tokens[i - 1][0] not in ("ID", "STR"):
        return None, ""
    return tokens[i - 1], run


def _role_chain(tokens, truncated=False):
    """(keys governing the expression `tokens` describes, read is resolved).

    Keys come back innermost first. `resolved` is False when the walk ran out of
    window while it was still climbing a frame, so the governing key is outside
    what the read could see. That is UNRESOLVED, never "no key" -- see
    `_role_state`.

    ITERATIVE on purpose (PBB-863). The walk climbs one frame per iteration by
    moving the `end` cursor left over the SAME token list, so the depth of the
    document costs heap, not interpreter stack. 1200 nested frames used to
    exhaust the stack inside this function and take the whole scan down with
    RecursionError. The depth of the text is unbounded, so a raised recursion
    limit would only move the failure; and every fail-closed answer -- the
    `resolved` flag, the empty chain, the key order -- is unchanged.
    """
    keys = []
    end = len(tokens)
    while True:
        if end == 0:
            return keys, not truncated
        i = end
        key, _ = _seam(tokens, i)
        if key is not None:
            rest_at = i
            while rest_at > 0 and tokens[rest_at - 1][0] == "SEP":
                rest_at -= 1
            key_at = rest_at - 1
            opener = _innermost_open_before(tokens, key_at)
            keys.append(key[1])
            if opener is None:
                return keys, True
            end = opener
            continue
        # No key across the seam. A member separator (a comma) binds nothing, but
        # it does not end the expression either: the element still answers to the
        # key that binds the list it sits in. So the walk climbs the frame instead
        # of stopping -- `{"api": [1, "<token>"]}` answers to `api`, while a bare
        # `["a.md", "<token>"]` at the top of the text still answers to nothing.
        run_at = i
        while run_at > 0 and tokens[run_at - 1][0] == "SEP":
            run_at -= 1
        member_run = "".join(tok[1] for tok in tokens[run_at:i])
        if "," in member_run and run_at > 0:
            opener = _innermost_open_before(tokens, run_at)
            if opener is not None:
                end = opener
                continue
        # The expression is a bracketed group, or it is glued to whatever precedes
        # it (a name, a prefix) and carries no key of its own.
        while i > 0 and tokens[i - 1][0] == "SEP":
            i -= 1
        if i == 0:
            return keys, not truncated
        kind, val, _, _ = tokens[i - 1]
        if kind == "CLOSE":
            opener = _match_opener(tokens, i - 1)
            if opener is None:
                return keys, True
            inner_key = _bracket_key(tokens, opener, i - 1)
            if inner_key:
                keys.append(inner_key)
            end = opener
            continue
        if kind == "OPEN":
            if val == "(" and i > 1 and tokens[i - 2][0] == "ID":
                # a call name is not a key
                end = i - 2
            else:
                end = i - 1
            continue
        return keys, True  # glued: `POST/...`, `v1/...` -- a prefix, not a key


BOUND = "bound"
PROSE = "prose"
UNRESOLVED = "unresolved"


def _role_window(text, pos):
    """(base, aligned) for the head the role at `pos` is read off.

    The head starts `_ROLE_WINDOW` characters back. A start in the middle of a
    name or of a string literal DESYNCHRONISES the token stream -- the first
    quote it meets opens a literal that swallows the frames behind it -- and a
    desynchronised stream is not evidence of anything. So the start is walked
    back to the nearest whitespace that is not inside a string literal, which
    is a real token boundary. If no such point is reachable, the window is not
    aligned and the read is UNRESOLVED. Fail closed, and cheap: an unaligned
    head can only ever make the scan stricter.
    """
    base = max(0, pos - _ROLE_WINDOW)
    if base == 0:
        return 0, True
    open_delimiters = {
        quote for quote in _STRING_QUOTES if text[:base].count(quote) % 2
    }
    at = base
    limit = max(0, base - _ROLE_WINDOW)
    while at > limit:
        if text[at - 1] in _STRING_QUOTES:
            quote = text[at - 1]
            open_delimiters.discard(quote) if quote in open_delimiters \
                else open_delimiters.add(quote)
        if not open_delimiters and text[at - 1].isspace():
            return at, True
        at -= 1
    return limit, False


def _role_state(text, pos):
    """(state, key) for the token that holds `pos`.

    `BOUND` -- a key governs the token across a seam or a bracket key. Any key
    spelling: there is no vocabulary to be outside of.
    `PROSE` -- no key governs it; the token is prose or a citation.
    `UNRESOLVED` -- the governing key sits outside the 4000-character role
    window, or the window could not be aligned, so the read cannot say what the
    token is. FAIL CLOSED: an unresolved token is treated as a value and gets
    no exemption, because the empty answer the window used to return fell
    through to the file-provenance exemption and the token PASSED. A bound that
    silently means "exempt" is a hole, not honesty.

    Read off the token stream, so no wrapper spelling and no seam spelling can
    hide the role: `api: x`, a quoted `api` value, `api: **x**`, `| api | x |`,
    `api -> x`, an em-dash seam, an arrow seam, `api: | x`, a subscript with a
    seam inside it, `spec["api"]["inner"] = x` and `{"operation": {"inner": x}}`
    all resolve. The walk runs to the depth the text actually has.
    """
    base, aligned = _role_window(text, pos)
    window = text[base:pos + 1]
    tokens = _tokens(window)
    # The value is whatever token CONTAINS `pos` (a string literal swallows it).
    # Everything before that token is the head the role is read off.
    at = len(tokens)
    for index, tok in enumerate(tokens):
        if tok[3] + base > pos:
            at = index
            break
    keys, resolved = _role_chain(tokens[:at], truncated=base > 0)
    if keys:
        return BOUND, keys[0]
    if not aligned or not resolved:
        return UNRESOLVED, ""
    return PROSE, ""


def _key_before(text, pos):
    """The key whose value holds `pos`, or "" -- any spelling, no vocabulary."""
    state, key = _role_state(text, pos)
    return key if state == BOUND else ""

# The exact sentence each reviewed slash token was reviewed in. This is the
# closed world: outside one of these sentences the token is an operation shape
# like any other, so `assisted/operator` is prose in its own sentence and a
# fabrication in an `api` value. Every sentence here appears in the module, the
# evidence doc, the returned surface, or the probe's own prose control; none of
# them is a substring of any smuggle shape below.
REVIEWED_PROSE_CONTEXTS = frozenset({
    ' observed mobile-only login/credential/ return/recovery. Onl',
    '. Supported path is **assisted/operator**. **Code:** `shared-',
    'IVE-community.md`). - Membership/course surfaces are browser-',
    'The supported path is assisted/operator: the owner creates th',
    'bonus access adapter (identity/grant/credential/SMS/resource authorization, failed',
    'est passed both with `shared-utils/ghl` present and with it ',
    'ive probe proving the course/credential create operations are',
    'mberships tools whose create/delete " "entries are docume',
    'mberships tools whose create/delete entries are documente',
    'mmunity-MCP list (~15 courses/memberships tools whose create/de',
    'nly login/credential/ return/recovery. Only then does `SUPP',
    'rships tools) and its create/delete entries are documente',
    'sing": ["a documented memberships/communities operation in the froz',
    'ssing:** a documented memberships/communities operation in the froz',
    'ssing=( "a documented memberships/communities operation in the froz',
    'the assisted/operator path and the R-13 / D',
    'the assisted/operator path and the R-13 / DEC-16 authority',
    'tity": ["a documented memberships/communities operation in the froz',
    # PBB-443. The reviewed ROWS the deliverable itself emits. With the default
    # inverted, a real repo path sitting in a VALUE -- behind any key at all --
    # has no shape-based way out, so the module's own citation rows have to be
    # reviewed like any other sentence. These are the five `provenance` rows of
    # the returned decision document and the decision line of the evidence doc,
    # captured verbatim from what the module hands back and from the delivered
    # text. Change either one and the scan stops passing until a human reviews
    # the new row -- which is the point.
    '"provenance": ["36-ghl-mcp-setup/ghl-mcp-setup-full.md", '
    '"06-ghl-install-pages/tools/SELECTORS-LIVE-course.md", '
    '"06-ghl-install-pages/tools/SELECTORS-LIVE-community.md"]',
    '"provenance": ["44-convert-and-flow-operator/tools/engine/cli_anything/'
    'gohighlevel/utils/workflow_builder.py", '
    '"36-ghl-mcp-setup/ghl-mcp-setup-full.md", '
    '"44-convert-and-flow-operator/automation-templates/launch-ghl-probe/'
    'GHL-CAPABILITY-NOTE.md"]',
    '"provenance": ["44-convert-and-flow-operator/tools/engine/cli_anything/'
    'gohighlevel/public/operations.py", '
    '"shared-utils/ghl/capability_inventory.py", '
    '"06-ghl-install-pages/references/form-click-map.md"]',
    '"provenance": ["44-convert-and-flow-operator/tools/engine/cli_anything/'
    'gohighlevel/public/operations.py"]',
    '"provenance": ["shared-utils/ghl/capability_inventory.py", '
    '"05-ghl-setup/INSTRUCTIONS.md"]',
    "**Decision:** **BLOCKED** for every automated route. Supported path is "
    "**assisted/operator**. **Code:** `shared-utils/bonus/access_capability.py` "
    "· `shared-utils/bonus/tests/test_access_capability.py`",
    "The shared inventory answers this from its own data: "
    "`select_route(EXECUTE, resource=\"memberships\")` returns `[]` "
    "(`shared-utils/ghl/capability_inventory.py`).",
    "The retired Tier-2 community MCP had the membership tool family "
    "(~15 courses and memberships tools) and its create/delete entries are "
    "documented as **possibly unverified shells** "
    "(`36-ghl-mcp-setup/ghl-mcp-setup-full.md`).",
    "send (`shared-utils/ghl/capability_inventory.py`, "
    "`conversations.send_message`; `05-ghl-setup/INSTRUCTIONS.md`).",
    "claims evidence levels 1–2 only; levels 3–4 (account grant, observed "
    "on the box) are explicitly **not held** "
    "(`shared-utils/ghl/capability_inventory.py`, `TRANSPORT_STATUS`).",
    "all** (`44-convert-and-flow-operator/tools/engine/cli_anything/"
    "gohighlevel/public/operations.py",
    "code | |---|---|---| | \"Is there a membership route?\" | "
    "`shared-utils/ghl/capability_inventory.py",
    "wording: `38-conversational-ai-system/CHANGELOG.md",
    "green: `38-conversational-ai-system/scripts/qc-pb-contracts.sh",
})

# The delivered prose may not promise more than the scan delivers. Each pattern
# is a whole CLASS of absolute claim, not one frozen literal, so the guard can
# see an overstatement it has not seen before.
OVERSTATED_GUARANTEES = (
    r"cannot\s+(?:slip|reach|enter|appear|get|creep|sneak)",
    r"\b(?:no|any)\s+fabricat\w+\s+(?:can|could|will|would|shall)\b",
    r"\bfabricat\w+\s+(?:can(?:not)?\s+)?never\s+(?:reach|enter|appear)",
    r"\b(?:always|invariably|unfailingly)\s+(?:caught|flagged|rejected|fails)",
    r"\bguarantee[sd]?\s+(?:that\s+)?(?:no|nothing|none)\b",
    r"\bimpossible\s+to\s+(?:slip|add|introduce|sneak|smuggle)",
    r"\b(?:100|101)\s*%\s*(?:coverage|detection)",
    r"\bnothing\s+can\s+(?:slip|pass|reach|enter)",
    r"\bcatch(?:es)?\s+every\s+(?:possible|shape|fabrication|case|form)",
    r"\bevery\s+fabricat\w+\s+(?:is|are|will\s+be)\s+(?:caught|flagged|rejected)",
    # PBB-311 B2: the patterns above could not see the very sentence the prior
    # verdict falsified, nor the common rephrasings of the same promise. These
    # are the CLASSES those phrasings share -- "the scan is total" and "an edit
    # of an enumerated shape is guaranteed to fail" -- not one frozen literal.
    r"\bedit\s+that\s+adds\b[^.]{0,80}\bfails?\s+the\s+suite\b",
    r"\bcatches?\s+(?:everything|anything|all)\b",
    r"\bcatch(?:es)?\s+every\s+(?:edit|version|revision)\b",
    r"\b(?:the\s+)?scan\s+(?:is\s+)?airtight\b",
    r"\bcannot\s+be\s+bypassed\b",
    r"\bnothing\s+(?:slips?|passes?|gets?|escapes?)\s+(?:past|through|by)\b",
    r"\b(?:no|zero)\s+fabricat\w+\s+(?:gets?|passes?|slips?|reaches?|escapes?)\b",
    r"\bevery\s+(?:fabricat\w+|shape|smuggle\w*|token)\s+(?:is|are|will\s+be|gets?)\b"
    r"[^.]{0,40}\b(?:caught|flagged|rejected|stopped|blocked)\b",
    # PBB-387 defect 3: the guard could not see the overstatements the previous
    # commit shipped -- three sentences that were all true of nothing. Each
    # pattern below is the CLASS those phrasings belong to, not one frozen
    # literal, so a fresh phrasing of the same promise still fails here.
    # (a) a traversal that is claimed without its bound.
    r"\b(?:walk|reach)\w*\s+out\s+(?:through|past|into)\b[^.]{0,60}\b(?:frames?|nesting|levels?)\b",
    r"\bhowever\s+deep\b",
    r"\bno\s+matter\s+how\s+(?:deep|far|many)\b",
    r"\b(?:all|any|every)\s+(?:depth|nesting|frames?)\b[^.]{0,40}\b(?:walk|reach|read)\w*\b",
    # (b) a wrapper claimed to be invisible to the read.
    r"\bcannot\s+hide\s+(?:the\s+)?role\b",
    r"\b(?:wrappers?|formatting|quoting|quotes?|punctuation)\s+cannot\s+hide\b",
    r"\b(?:wrappers?|formatting)\s+(?:are|is)\s+removed\b[^.]{0,60}\brole\b",
    # (c) a claim that no spelling can be chosen past the rules.
    r"\bcannot\s+(?:choose|pick|find|select|use)\s+(?:a|any|the)\b[^.]{0,40}\bspelling\b",
    r"\bspellings?\s+(?:the\s+rules?|the\s+scan)\s+(?:miss|misses|could\s+miss|would\s+miss)\b",
    r"\b(?:rules?|scan)\s+(?:never\s+)?miss(?:es)?\b[^.]{0,40}\bspelling\b",
    r"\bno\s+spellings?\s+(?:can|could|will|would)\s+be\s+(?:chosen|picked|found|used)\b",
    r"\bspellings?\b[^.]{0,40}\b(?:the\s+rules?|the\s+scan)\s+(?:miss|misses)\b",
    # PBB-443 DEFECT 3: the guard could not see its own false sentence. The
    # module claimed every separator look-alike -- any character whose Unicode
    # name calls it a solidus or a slash -- reaches the same rule as `/`, while
    # 16 of the 46 named look-alikes never reached it at all. These are the
    # CLASS: a spelling-universality promise about named characters, stated
    # without the shapes it excludes. The scoped sentence this round ships
    # names those shapes ("outside the two literal shapes ..."), and the
    # negative lookahead is what keeps the guard quiet on it.
    r"\bevery\s+separator\s+look-alike\b"
    r"(?![^.]{0,200}\b(?:outside|except|excepting|save|but\s+for)\b)",
    r"\bany\s+character\s+whose\s+(?:unicode\s+)?name\b[^.]{0,80}"
    r"\b(?:reaches|arrives?\s+at|hits)\b[^.]{0,60}\bsame\s+rule\b"
    r"(?![^.]{0,200}\b(?:outside|except|excepting|save|but\s+for)\b)",
    r"\b(?:no|not\s+one|nary\s+a)\s+(?:separator|slash|solidus|look-alike|"
    r"character)\b[^.]{0,60}\b(?:escapes?|misses?|gets?\s+past)\b",
    r"\bevery\s+(?:character|code\s*point|codepoint|spelling)\b[^.]{0,60}"
    r"\b(?:reaches|arrives?\s+at|is\s+mapped|is\s+read)\b"
    r"(?![^.]{0,200}\b(?:outside|except|excepting|save|but\s+for)\b)",
    r"\bhowever\s+(?:it\s+is\s+|it\s+is\s+)?spelled\b",
    r"\bwhatever\s+(?:the\s+)?spelling\b",
    r"\bevery\s+(?:spelling|named?\s+character)\b[^.]{0,40}\b(?:is|are)\s+"
    r"(?:in\s+class|covered|mapped|read)\b",
)
_OVERSTATED_RE = tuple(re.compile(p, re.I) for p in OVERSTATED_GUARANTEES)
# What the prose must state so a reader knows what the scan does not cover.
REQUIRED_GUARANTEE_SCOPE = (
    "pattern scan, not a proof",
    "is not caught",
    "closed world",
    "fails until a human reviews",
    "normalises",
)


def _overstated_guarantee_hits(text):
    """Absolute detection claims in delivered prose.

    A scan entry point like the shape scanners, so it takes the same input and
    refuses a non-string with the same domain error (PBB-311 defect C: this one
    leaked a bare `TypeError` out of a regex).
    """
    text = _scan_text(text)
    return [m.group(0) for rx in _OVERSTATED_RE for m in rx.finditer(text)]


_REPO_FILES = None


def _repo_files():
    """Every regular file in this tree, repo-relative. The tree is fixed here."""
    global _REPO_FILES
    if _REPO_FILES is None:
        _REPO_FILES = frozenset(
            str(p.relative_to(_REPO))
            for p in _REPO.rglob("*")
            if p.is_file() and ".git" not in p.parts
        )
    return _REPO_FILES


def _is_real_file_name(name):
    """`name` is a real path in this tree, or a path-SEGMENT run that ends one.

    PBB-311 A4: `p.endswith(name)` with no boundary admitted any tail, so a
    fabricated `.../s/bonus/access_capability.py` was "a real file". The
    boundary is required now: a name may be the whole path or start at a
    segment boundary, never mid-segment.
    """
    return any(p == name or p.endswith("/" + name) for p in _repo_files())


_TEMPLATE_BINDING = re.compile(
    r"(?:^|[\s;({,])([_A-Za-z][_A-Za-z0-9]*)\s*=\s*[\"']([^\"'\n]{1,200})[\"']"
)


def _bound_constants(text):
    """String constants bound in this text, so an f-string head can be RESOLVED.

    PBB-311 A4: the previous rule accepted any fabricated variable head plus a
    real path tail, so `f"{TOTALLY_FAKE}/bonus/access_capability.py"` was
    provenance even though no variable was ever bound. A template is provenance
    only when its head is bound here AND the whole expansion is a real file.
    """
    return {m.group(1): m.group(2) for m in _TEMPLATE_BINDING.finditer(text)}


def _in_value_position(text, start):
    """True when the token at `start` is a VALUE, not prose.

    A key governs it (BOUND), or the role read cannot reach far enough back to
    say (UNRESOLVED). PROSE is the only state an exemption may attach to. This
    is the inversion: the question is no longer "is this key API-ish", it is
    "is this a value at all", and a value carries no exemption by default.
    """
    return _role_state(text, start)[0] in (BOUND, UNRESOLVED)


def _resolves_to_real_file(token, text=""):
    """File provenance, closed world.

    A literal path must be a real file in this tree. A path built from an
    f-string variable is provenance only when that variable is bound in the same
    text AND the expansion is a real file -- resolution, not tail-matching. A
    name with no path behind it (`shared-utils/ghl`) is a directory at best and
    never file provenance.
    """
    if token in _repo_files():
        return True
    match = re.fullmatch(r"\{([_A-Za-z][_A-Za-z0-9]*)\}/(.+)", token)
    if not match:
        return False
    head, rest = match.group(1), match.group(2)
    bound = _bound_constants(text).get(head)
    if not bound:
        return False
    return f"{bound.rstrip('/')}/{rest}" in _repo_files()


def _is_file_provenance(token, text=""):
    # A suffix alone proves nothing: `memberships/grant.py` ends in `.py` and is
    # still a fabricated operation. The suffix only says where to look.
    return token.lower().endswith(_FILE_SUFFIXES) and _resolves_to_real_file(token, text)


def _starts_value_run(text, at):
    """True when a reviewed window begins on the far side of a seam.

    PBB-311 A5: a reviewed window pasted behind `target: ` exempted its token
    whatever role the window was playing. The window is the unit of review, so
    it must start outside a value run. The seam is read off the token stream,
    so a label spelled with any separator counts and prose spacing does not.
    """
    window_start, aligned = _role_window(text, at)
    if not aligned:
        return True  # an unaligned head proves nothing; refuse the exemption
    # A window that begins ON the separator run of a binding is still on the
    # far side of that seam, so the run is read as part of the head. Without
    # this, `wording: <path>` is excused by a phrase starting at the colon.
    end = at
    while end < len(text) and not (
        text[end].isalnum()
        or text[end] in "_-" + _STRING_QUOTES + "()[]{}"
    ):
        end += 1
    tokens = _tokens(text[window_start:end])
    key, _ = _seam(tokens, len(tokens))
    return key is not None


def _value_token_start(text, pos):
    """Left edge of the token that holds `pos` -- a string literal swallows it.

    A value wrapped in quotes or brackets -- api: then a quoted path, api: then
    a bracketed path -- has its binding further left than the first byte of the
    path. A window that starts at the path starts INSIDE the value, whatever
    wrapper is around it.
    """
    for tok in _tokens(text[:pos + 1]):
        if tok[2] <= pos < tok[3]:
            return tok[2]
    return pos


def _starts_on_a_name(text, at):
    """`at` falls INSIDE a name or a string literal.

    A row may begin in the middle of a separator run -- `**Decision:**` starts
    on the asterisks -- but never in the middle of a name: `wording: <path>` is
    excused by a phrase starting at `g` of `wording` otherwise, which is the
    value talking about itself.
    """
    for tok in _tokens(text[:at + 1]):
        if tok[2] < at < tok[3]:
            return tok[0] in ("ID", "STR")
    return False


def _begins_a_row(text, at):
    """`at` starts a ROW, not the inside of a bracket someone opened on it.

    A reviewed row is reviewed as a row -- the `"provenance": [...]` rows of the
    returned document, the decision line of the evidence doc. What may NOT open
    a row is a bracket: `api: {` and `api: (` are a key holding a frame, and a
    window that starts inside that frame is the value talking about itself.
    """
    if at <= 0:
        return True
    head = _tokens(text[:at])
    i = len(head)
    while i > 0 and head[i - 1][0] == "SEP":
        i -= 1
    return i == 0 or head[i - 1][0] != "OPEN"


def _in_reviewed_prose(text, start, end, phrases=None):
    """The token sits inside one of the declared windows, verbatim.

    The window is the unit of review, so it must not itself begin inside a
    value run -- a reviewed sentence pasted behind `target: ` is a value, not
    prose. `phrases` defaults to the reviewed prose contexts; the declared
    legitimate windows below widen it to the other closed world.
    """
    token = text[start:end]
    for phrase in (REVIEWED_PROSE_CONTEXTS if phrases is None else phrases):
        offset = phrase.find(token)
        while offset != -1:
            at = start - offset
            if (
                at >= 0
                and text[at: at + len(phrase)] == phrase
                and not _starts_value_run(text, at)
            ):
                return True
            offset = phrase.find(token, offset + 1)
    return False

# Every smuggle shape a fabricated interface has been seen to take. The scan
# must catch all of them; the table below is the proof it does.
#
# FIXTURES, NOT DELIVERABLE: these literals are attack inputs, and this test
# file is the only file in shared-utils/bonus/ allowed to carry an API-shaped
# string. `test_the_evidence_doc_carries_no_api_shape` and
# `test_module_source_carries_no_api_shape` keep the other files at zero.
SMUGGLE_SHAPES = (
    ("scheme url", "https://api.leadconnectorhq.com/v1/memberships/grant"),
    ("uppercase verb+path", "GET  /memberships/grant"),
    ("lowercase verb+path", "post /memberships/grant"),
    ("bare operation path", '"api": "/memberships/grant"'),
    ("schemeless host+path", "api.leadconnectorhq.com/v1/memberships/grant"),
    ("dotted operation id", '"api": "memberships.grant"'),
    # PBB-132 QC: an identifier glued in front of the `/` defeated every rule.
    ("glued uppercase verb+path", "POST/memberships/grant"),
    ("glued lowercase verb+path", "post/memberships/grant"),
    ("glued mixed-case verb+path", "Get/memberships/grant"),
    ("glued delete verb+path", "DELETE/memberships/grant"),
    ("version-prefixed path", "v1/memberships/grant"),
    ("api-prefixed path", "api/memberships/grant"),
    ("unprefixed operation path", "memberships/grant"),
    ("identifier-prefixed path", "x/memberships/grant"),
    # PBB-260 QC: an exemption keyed on the token's shape alone laundered a
    # fabricated API past the scan. These are the shapes it admitted, plus the
    # operation family with its operation cut off.
    ("file-suffix laundering .py", "memberships/grant.py"),
    ("file-suffix laundering .json", "memberships/grant.json"),
    ("file-suffix laundering .md", "v1/memberships/grant.md"),
    ("file-suffix laundering .sh", "x/memberships/grant.sh"),
    ("file-suffix laundering .yml", "api/tools/memberships_grant.yml"),
    ("file-suffix laundering .txt", "identity/grant/credential.txt"),
    ("file-suffix laundering .html", "courses/memberships.html"),
    ("dotted-id file-suffix laundering", "memberships.grant.py"),
    ("reviewed token as a bare api value", "assisted/operator"),
    ("reviewed token as a bare api value 2", "memberships/communities"),
    ("reviewed token as a bare api value 3", "return/recovery"),
    ("reviewed token as a bare api value 4", "identity/grant/credential/SMS/resource"),
    ("reviewed token as a bare api value 5", "shared-utils/ghl"),
    ("reviewed token behind an api key", "api: courses/memberships"),
    ("reviewed token behind a route key", '"route": "login/credential"'),
    ("file-suffix behind an api key", "api: memberships/grant.py"),
    ("real file behind an api key", "api: shared-utils/bonus/access_capability.py"),
    ("trailing path segment", "memberships/"),
    # PBB-311 A1: a wrapper character between the key and the value hid the
    # role from a seam regex. Role is read structurally now, so every wrapper
    # spelling resolves to the same key.
    ("backtick value position", "api: `shared-utils/bonus/access_capability.py`"),
    ("asterisk value position", "api: **shared-utils/bonus/access_capability.py**"),
    ("paren value position", "api: (shared-utils/bonus/access_capability.py)"),
    ("bracket value position", "api: [shared-utils/bonus/access_capability.py](x)"),
    ("markdown cell value position", "| api | `shared-utils/ghl/capability_inventory.py` |"),
    ("nested object parent key", '{"operation": {"inner": "shared-utils/ghl/capability_inventory.py"}}'),
    ("arrow value position", "api -> shared-utils/bonus/access_capability.py"),
    ("subscript value position", 'spec["api"] = "shared-utils/bonus/access_capability.py"'),
    # PBB-311 A2/A3: separator spellings.
    ("doubled separator", "memberships//grant"),
    ("doubled separator behind a verb", "POST//memberships/grant"),
    ("fullwidth slash U+FF0F", "memberships／grant"),
    ("division slash U+2215", "memberships∕grant"),
    ("fraction slash U+2044", "memberships⁄grant"),
    ("big solidus U+29F8", "memberships⧸grant"),
    ("fullwidth slash behind a verb", "POST／memberships／grant"),
    ("backslash separator", "memberships\\grant"),
    # PBB-311 A4: a fabricated f-string head was admitted as provenance because
    # only the tail was checked. The head must be bound now.
    ("unbound template head", 'f"{TOTALLY_FAKE}/bonus/access_capability.py"'),
    ("unbound template head, nested tail", 'f"{X}/s/bonus/access_capability.py"'),
    # PBB-311 A5: a reviewed window pasted behind a label exempted its token
    # whatever role the window was playing.
    (
        "reviewed window behind a label",
        "target: The supported path is assisted/operator: the owner creates th",
    ),
    # PBB-387: the class PBB-371 measured still open, and the spellings this
    # round invented. PBB-371 charged that the role read was two enumerated
    # lists and that every spelling outside them walked past the rule; these are
    # the spellings nobody had typed when that commit shipped. They are pinned
    # as FAMILIES (wrapper / seam / subscript / frame / invisible / padded
    # separator), not as eight more rows of the same family.
    ("angle wrapper value position", "api: <shared-utils/bonus/access_capability.py>"),
    ("typographic quote value position",
     "api: \u201cshared-utils/bonus/access_capability.py\u201d"),
    ("em-dash seam", "api \u2014 shared-utils/bonus/access_capability.py"),
    ("double separator seam", "api: | shared-utils/bonus/access_capability.py"),
    ("long double arrow seam", "api \u27f9 shared-utils/bonus/access_capability.py"),
    ("long rightwards arrow seam", "api \u27f6 shared-utils/bonus/access_capability.py"),
    ("rightwards double arrow seam", "api \u21d2 shared-utils/bonus/access_capability.py"),
    ("right-left harpoon seam", "api \u21cc shared-utils/bonus/access_capability.py"),
    ("long left-right arrow seam", "api \u27f7 shared-utils/bonus/access_capability.py"),
    ("arrowhead seam", "api \u2934 shared-utils/bonus/access_capability.py"),
    ("colon then pipe seam", "api : | shared-utils/bonus/access_capability.py"),
    ("arrow then colon seam", "api ->: shared-utils/bonus/access_capability.py"),
    ("colon then em-dash seam", "api :\u2014 shared-utils/bonus/access_capability.py"),
    ("colon-equals then pipe seam", "api := | shared-utils/bonus/access_capability.py"),
    ("pipe then equals seam", "api |= shared-utils/bonus/access_capability.py"),
    ("triple colon seam", "api ::: shared-utils/bonus/access_capability.py"),
    ("equals then arrow seam", "api ==> shared-utils/bonus/access_capability.py"),
    ("slash seam", "api / shared-utils/bonus/access_capability.py"),
    ("arrow wrapper around the value",
     "api: ->shared-utils/bonus/access_capability.py->"),
    ("equals wrapper around the value",
     "api: =shared-utils/bonus/access_capability.py="),
    ("colon wrapper around the value",
     "api: :shared-utils/bonus/access_capability.py:"),
    ("pipe wrapper around the value",
     "api: |shared-utils/bonus/access_capability.py|"),
    ("arrow wrapper inside a markdown cell",
     "| api | ->shared-utils/ghl/capability_inventory.py-> |"),
    ("zero-width space before the value",
     "api: \u200bshared-utils/bonus/access_capability.py"),
    ("zero-width space inside the key",
     "a\u200bpi: shared-utils/bonus/access_capability.py"),
    ("zero-width joiner after the key",
     "api\u200d: shared-utils/bonus/access_capability.py"),
    ("byte-order mark before the key",
     "\ufeffapi: shared-utils/bonus/access_capability.py"),
    ("right-to-left mark before the key",
     "\u200fapi: shared-utils/bonus/access_capability.py"),
    ("zero-width non-joiner at the seam",
     "api\u200c: shared-utils/bonus/access_capability.py"),
    ("zero-width space inside the value path",
     "api: shared-utils/bonus/access\u200b_capability.py"),
    ("arrow inside a subscript",
     'spec["api" -> "shared-utils/bonus/access_capability.py"]'),
    ("colon inside a subscript",
     'spec["api": "shared-utils/bonus/access_capability.py"]'),
    ("pipe inside a subscript",
     'spec["route" | "shared-utils/bonus/access_capability.py"]'),
    ("seam inside a subscript holding a nested object",
     'spec["operation" := {"inner": "shared-utils/bonus/access_capability.py"}]'),
    ("subscript chain, parent is the api key",
     'spec["operation"]["inner"] = "shared-utils/bonus/access_capability.py"'),
    ("three-deep subscript chain",
     'spec["api"]["inner"]["deep"] = "shared-utils/bonus/access_capability.py"'),
    ("subscript then brace",
     'spec["route"]["inner"] = {"deep": "shared-utils/bonus/access_capability.py"}'),
    ("fullwidth reverse solidus U+FF3C", "memberships\uff3cgrant"),
    ("padded solidus", "memberships / grant"),
    ("padded fullwidth solidus", "memberships \uff0f grant"),
    ("padded division slash", "memberships \u2215 grant"),
    ("padded reverse solidus", "memberships \uff3c grant"),
)

# Text that must NOT be flagged: real repo provenance and plain prose.
LEGITIMATE_TEXT = (
    "#!/usr/bin/env python3",
    # PBB-311 A4: a template is legitimate only with its binding present. This
    # is the module's own two lines, which is what real provenance looks like.
    '    _GHL = "44-convert-and-flow-operator"\n'
    '    _REGISTRY = f"{_GHL}/tools/engine/cli_anything/gohighlevel/public/operations.py"',
    "44-convert-and-flow-operator/tools/engine/cli_anything/gohighlevel/public/operations.py",
    "shared-utils/ghl/capability_inventory.py",
    "05-ghl-setup/INSTRUCTIONS.md",
    "06-ghl-install-pages/tools/SELECTORS-LIVE-course.md",
    "36-ghl-mcp-setup/ghl-mcp-setup-full.md",
    "the assisted/operator path and the R-13 / DEC-16 authority",
    "select_route(OpClass.EXECUTE, resource=\"memberships\") returns []",
    "in the frozen v3 production spec, contact enrollment against an existing "
    "workflow is not authoring",
    # PBB-387: the read must not UNWRAP a legitimate expression. Stripping the
    # brackets out of `a[b]/c[d]` would manufacture `ab/cd`, an operation path
    # that is not in the text. The token stream keeps the brackets where they
    # are, so the expression reads as itself.
    "ratio = a[b]/c[d]",
    "res = compute(a[0], b[1])",
    "value = table[key]",
    'cfg = {"note": "plain", "other": 1}',
    # PBB-371 defect 5: the normaliser used to rewrite legitimate filesystem
    # literals into bare paths. A local-file URL, a drive-rooted path and a UNC
    # path keep their own separators now.
    "file:///Users/me/project/file.py",
    "C:\\Users\\me\\project\\file.py",
    "\\\\server\\share\\doc.md",
)

# PBB-443. THE ALLOW-PATH, DECLARED. A value -- behind any key, or beyond the
# role window -- has no shape-based way out any more. The only thing that lets
# it through is a sentence a human reviewed and that is listed here. Both
# tables above are closed worlds; this set is their union, and nothing enters
# it by looking like anything. That is what "an unrecognised key carrying a real
# repo path must FAIL CLOSED, and only a declared legitimate prose context may
# allow it" means in code.
DECLARED_LEGITIMATE_WINDOWS = frozenset(
    re.sub(r"\s+", " ", phrase).strip()
    for phrase in set(REVIEWED_PROSE_CONTEXTS) | set(LEGITIMATE_TEXT)
)


def _in_declared_window(text, start, end):
    """The one exemption a value may carry: a reviewed ROW, verbatim.

    Three things have to hold, and each one is structural:
      * the row begins a row -- the head of the text, or just after a group
        close, which is where a reviewed row sits;
      * the row begins BEFORE the value token it excuses, so `api: \\`<token>\\``
        and `api: (<token>)` are the value talking about itself and are
        refused;
      * the row does not itself begin on the far side of a seam.

    Reproducing a whole reviewed row verbatim is the closed world's documented
    limit -- the same one the reviewed prose sentences have always had. A new
    row, or a reviewed row reworded, fails until a human reviews it.
    """
    edge = _value_token_start(text, start)
    token = text[start:end]
    for phrase in DECLARED_LEGITIMATE_WINDOWS:
        offset = phrase.find(token)
        while offset != -1:
            at = start - offset
            if (
                at >= 0
                and at < edge
                and not _starts_on_a_name(text, at)      # never inside a name
                and _begins_a_row(text, at)              # never inside a frame
                and text[at: at + len(phrase)] == phrase
                and not _starts_value_run(text, at)
            ):
                return True
            offset = phrase.find(token, offset + 1)
    return False


# PBB-311 A2/A3: a path split by a doubled separator or by a look-alike slash
# walked past every rule. Normalising the separators means one rule decides one
# class: the glued form, the doubled form and the look-alike form cannot be told
# apart because they arrive identical.
#
# PBB-387: the map is DERIVED, not typed. Any character whose Unicode name
# calls it a solidus or a slash is a path separator, so a spelling nobody
# anticipated (U+FF3C FULLWIDTH REVERSE SOLIDUS, U+FE68 SMALL REVERSE SOLIDUS,
# U+29F5 REVERSE SOLIDUS OPERATOR) arrives at the same rule as `/`. A typed
# list of five characters is exactly the device PBB-371 charged.
#
# PBB-443 DEFECT 3: the derivation used to stop at U+10FFF, so eleven named
# separators above it (U+1D194, U+1D195, U+1D199, U+1D1A9, U+1F10D, U+1F10F,
# U+1F16E, U+1F67C VERY HEAVY SOLIDUS, U+1F67D, U+E002F TAG SOLIDUS,
# U+E005C TAG REVERSE SOLIDUS) were never mapped, and five more were mapped but
# deleted first because they are combining marks. 16 of the 46 named look-alikes
# did not reach the rule while the delivered prose claimed all of them did. The
# derivation now covers the WHOLE code space, and `_drop_invisible` keeps a
# named separator instead of deleting it. See the docstring for the two literal
# shapes that still keep their own separators.
def _slash_like_table():
    table = {}
    for codepoint in range(0x110000):
        char = chr(codepoint)
        if char == "/":
            continue
        name = unicodedata.name(char, "")
        if "SOLIDUS" in name or "SLASH" in name:
            table[codepoint] = ord("/")
    return str.maketrans(table)
_SLASH_TRANSLATE = _slash_like_table()
# The same derived set, as a character class for the path rules below.
_SLASH_LIKE = "".join(chr(c) for c in range(0x110000) if c in _SLASH_TRANSLATE)
_SEPARATOR_LOOKALIKES = _SLASH_TRANSLATE
# A backslash is a path separator like any other. The one shape it may not be
# mapped inside is a real Windows path -- a drive root (`C:\...`) or a UNC
# (`\\server\...`) -- where it is the separator OF that path and mapping it to
# `/` manufactures bare-path hits out of legitimate literals (PBB-371 defect 5).
# The shape is defined structurally: a drive root, or a doubled leading
# separator. No product is named.
_PROTECTED_BACKSLASH = "\x00"
_WINDOWS_PATH = re.compile(r"(?<![A-Za-z0-9_])(?:[A-Za-z]:\\|\\\\)[^\s\"'`|*<>]*")
# A scheme with an EMPTY authority (`file:///x`, `data:///x`) names a local
# object and not a host, so it is not an operation path. Structural again: the
# authority slot is empty, which no host name ever is.
_EMPTY_AUTHORITY_URL = re.compile(r"\b[A-Za-z][A-Za-z0-9+.\-]*:///[^\s\"'`|*<>]*")
# Characters with no visible glyph carry no role of their own: a zero-width
# space inside `api` is not a different spelling of `api`. Structural -- the
# Unicode categories for format, control, surrogate, unassigned and combining
# marks, not a list of characters. ONE exception, also derived rather than
# typed: a character Unicode names a solidus or a slash is a SEPARATOR whatever
# its category, so it is kept long enough to be mapped onto `/`. Deleting it
# first is what used to hide U+0337, U+0338, U+20E0, U+20E5, U+20EB, U+E002F
# and U+E005C from the rule the prose said they reached.
def _drop_invisible(text):
    return "".join(
        char for char in text
        if not unicodedata.category(char).startswith(("C", "M"))
        or char in _SLASH_LIKE
    )

def _scan_text(text):
    """The text the scan runs over.

    Whitespace is normalised first: the same sentence wraps across lines in the
    module and sits on one line in the evidence doc and in the returned surface,
    and the reviewed prose contexts below are captured from the normalised form.
    Invisible characters are then dropped (they carry no role), separator
    look-alikes are mapped to `/` by Unicode name, and a doubled separator is
    collapsed -- except where the run is a scheme delimiter (`file://`, `x://`),
    which is not a path and must survive byte for byte. A non-string is refused
    with the domain error, never a bare `TypeError` out of a regex.
    """
    if not isinstance(text, str):
        raise ac.BonusCapabilityError(
            f"api shape scan takes text, got {type(text).__name__}"
        )
    flat = re.sub(r"\s+", " ", text)
    flat = _drop_invisible(flat)
    flat = _WINDOWS_PATH.sub(
        lambda m: m.group(0).replace("\\", _PROTECTED_BACKSLASH), flat
    )
    flat = flat.translate(_SEPARATOR_LOOKALIKES)
    flat = re.sub(r"(?<![:/])/{2,}", "/", flat)
    return flat.replace(_PROTECTED_BACKSLASH, "\\")


def _path_literal_spans(text):
    """Spans of filesystem literals the path rules leave alone.

    A real Windows path and a local-file URL each carry their own separator
    syntax; mapping them onto `/` manufactured bare-path hits out of
    legitimate literals. The ROLE rule is unaffected: a literal behind an
    `api` key is an operation value like any other.
    """
    spans = [m.span() for m in _WINDOWS_PATH.finditer(text)]
    return spans + [m.span() for m in _EMPTY_AUTHORITY_URL.finditer(text)]


def _dotted_operation_hits(text):
    text = _scan_text(text)
    local = _path_literal_spans(text)
    # A dotted run inside a bare path is that path's OWN TAIL, not a second
    # token with a key of its own. `shared-utils/ghl/capability_inventory.py`
    # must not read `ghl` as a key bound to `capability_inventory.py` -- the
    # key has to sit outside the token it governs, which is the same rule that
    # keeps the bare-path read honest at its own left edge.
    inside_path = [m.span() for m in _BARE_PATH.finditer(text)]
    hits = []
    for match in _DOTTED_OPERATION.finditer(text):
        if any(l < match.end() and match.start() < r for l, r in local):
            continue
        if any(l <= match.start() and match.end() <= r for l, r in inside_path):
            continue
        token = match.group(0)
        if match.start() > 0 and text[match.start() - 1] == "-":
            # PBB-311: a dot-token glued behind a hyphen is part of a real
            # hyphenated file name (`SELECTORS-LIVE-course.md`), not an
            # operation id. The segment-boundary rule below is what makes this
            # distinction necessary.
            continue
        if _in_value_position(text, match.start()):
            if (
                token in REVIEWED_SLASH_TOKENS
                and _in_reviewed_prose(text, match.start(), match.end())
            ) or _in_declared_window(text, match.start(), match.end()):
                continue
            hits.append(token)  # a value is never filename provenance
            continue
        # Provenance, closed world: only a name that is the tail of a real path
        # in this tree is a filename fragment of a cited file. The greedy match
        # above is the defence -- `memberships.grant.py` is ONE token and no real
        # path ends with it, while `operations.py` is the tail of the provenance
        # file the surface actually cites.
        if token.lower().endswith(_FILE_SUFFIXES) and _is_real_file_name(token):
            continue
        hits.append(token)
    return hits


def _api_shape_hits(text):
    """API shapes that cannot be legitimate in this module's source or surface."""
    text = _scan_text(text)
    local = _path_literal_spans(text)
    hits = [f"url:{m.group(0)}" for m in _URL.finditer(text)]
    hits += [f"verb+path:{m.group(0)}" for m in _VERB_PATH.finditer(text)]
    for match in _BARE_PATH.finditer(text):
        if any(l < match.end() and match.start() < r for l, r in local):
            continue
        token = match.group(0)
        if _in_value_position(text, match.start()):
            # A value gets no FILE-PROVENANCE exemption. Whatever the key
            # spells -- `api`, `href`, `note`, `_REGISTRY`, `deeper` -- a real
            # repo path sitting in a value is an operation value until a human
            # has reviewed the row it appears in. A reviewed SLASH token keeps
            # its own closed world: it passes only inside the exact sentence it
            # was reviewed in, which is a declaration too.
            if (
                token in REVIEWED_SLASH_TOKENS
                and _in_reviewed_prose(text, match.start(), match.end())
            ) or _in_declared_window(text, match.start(), match.end()):
                continue
            hits.append(f"bare-path:{token}")
            continue
        if not token.startswith("/") and (
            _is_file_provenance(token, text)
            or (
                token in REVIEWED_SLASH_TOKENS
                and _in_reviewed_prose(text, match.start(), match.end())
            )
        ):
            continue  # file provenance or reviewed prose, not an operation
        hits.append(f"bare-path:{token}")
    for match in _SPACED_PATH.finditer(text):
        token = match.group(0)
        if _in_value_position(text, match.start()):
            if (
                token in REVIEWED_SLASH_TOKENS
                and _in_reviewed_prose(text, match.start(), match.end())
            ) or _in_declared_window(text, match.start(), match.end()):
                continue
            hits.append(f"bare-path:{token}")
            continue
        if _is_file_provenance(token, text) or (
            token in REVIEWED_SLASH_TOKENS
            and _in_reviewed_prose(text, match.start(), match.end())
        ):
            continue  # file provenance or reviewed prose, not an operation
        hits.append(f"bare-path:{token}")
    for match in _TRAILING_SEGMENT.finditer(text):
        token = match.group(0)
        if token.rstrip("/").upper() in _HTTP_VERBS:
            continue  # `POST/` is a verb with no path behind it, not an operation
        hits.append(f"partial-path:{token}")
    hits += [f"host+path:{m.group(0)}" for m in _SCHEMELESS_HOST.finditer(text)]
    return hits


def _fabricated_api_hits(text):
    return _api_shape_hits(text) + [
        f"operation-id:{t}" for t in _dotted_operation_hits(text)
    ]


class _BlockImport:
    """meta_path finder that makes `import ghl...` genuinely raise ImportError."""

    def find_spec(self, fullname, path=None, target=None):
        if fullname == "ghl" or fullname.startswith("ghl."):
            raise ImportError(f"blocked for this test: {fullname}")
        return None


class TestCapabilityBlock(unittest.TestCase):
    """C-14: the exact block, announced rather than an invented interface."""

    def test_every_step_is_declared_exactly_once_in_order(self):
        self.assertEqual(list(ac.STEP_ORDER), ["identity", "grant", "credential", "return", "recovery"])
        self.assertEqual([e.step for e in ac.EVIDENCE], list(ac.STEP_ORDER))

    def test_all_five_steps_are_blocked_today(self):
        self.assertEqual(ac.blocked_steps(), list(ac.STEP_ORDER))

    def test_every_step_names_the_exact_missing_evidence(self):
        for step, row in ac.capability_evidence().items():
            self.assertFalse(row["routable"], f"{step} was promoted to routable")
            self.assertTrue(row["missing"], f"{step} names no missing evidence")
            for clause in row["missing"]:
                self.assertTrue(str(clause).strip(), f"{step} carries a blank missing clause")
            self.assertTrue(row["authority"], f"{step} cites no authority")
            self.assertTrue(row["claim"].strip(), f"{step} carries no claim")

    def test_every_provenance_file_exists_in_this_tree(self):
        for step, row in ac.capability_evidence().items():
            self.assertTrue(row["provenance"], f"{step} cites no provenance")
            for rel in row["provenance"]:
                self.assertFalse(os.path.isabs(rel), f"{step} provenance must be repo-relative: {rel}")
                self.assertTrue(
                    (_REPO / rel).is_file(), f"{step} provenance does not exist: {rel}"
                )

    def test_no_step_is_proved_or_claims_a_tenant_observation(self):
        for step, row in ac.capability_evidence().items():
            self.assertNotEqual(row["state"], ac.PROVED, step)
            self.assertNotIn("verified on this box", row["claim"].lower(), step)


class TestNoFabricatedApi(unittest.TestCase):
    """C-14: no fabricated API anywhere in the route surface."""

    def test_supported_route_exposes_no_api(self):
        route = ac.supported_route()
        self.assertIsNone(route["api"])
        self.assertTrue(route["no_invented_api"])
        self.assertNotIn("endpoint", route["supported_path"].lower())

    def test_route_values_contain_no_url_or_verb_path(self):
        blob = json.dumps(ac.supported_route(), sort_keys=True)
        self.assertIsNone(re.search(r"https?://", blob))
        self.assertIsNone(re.search(r"\b(?:GET|POST|PUT|PATCH|DELETE)\s+/[A-Za-z0-9{]", blob))

    def test_module_source_carries_no_url_or_verb_path(self):
        source = Path(ac.__file__).read_text(encoding="utf-8")
        self.assertIsNone(re.search(r"https?://", source), "module carries a URL")
        self.assertIsNone(
            re.search(r"\b(?:GET|POST|PUT|PATCH|DELETE)\s+/[A-Za-z0-9{]", source),
            "module carries a verb+path operation",
        )

    def test_membership_family_has_no_route_in_the_shared_inventory(self):
        # Reuse of the upstream inventory, not a second local table.
        self.assertEqual(ac.membership_inventory_routes(), [])
        # Instrument control on the negative: the SAME call path answers
        # non-empty for a family the inventory does document, so the zero above
        # is discriminating and not a broken instrument reported as a block.
        from ghl import capability_inventory as inventory

        control = inventory.select_route(
            inventory.OpClass.EXECUTE, resource="workflows", dynamic_confirmed=False
        )
        self.assertTrue(
            control,
            "shared inventory answered nothing for a documented family — "
            "the memberships zero is a broken instrument, not a capability block",
        )

    def test_a_broken_reuse_path_fails_closed_and_is_never_a_capability_block(self):
        # A missing inventory is an instrument failure. Returning [] for it would
        # make a broken reuse path indistinguishable from a proven "no route".
        # The cached modules are dropped first so the import genuinely re-runs
        # and the blocker is what fails it, not a stale sys.modules entry.
        saved = {k: v for k, v in sys.modules.items() if k == "ghl" or k.startswith("ghl.")}
        for name in saved:
            del sys.modules[name]
        sys.meta_path.insert(0, _BlockImport())
        try:
            with self.assertRaises(ac.BonusCapabilityError):
                ac.membership_inventory_routes()
        finally:
            sys.meta_path.pop(0)
            sys.modules.update(saved)
        # Inverse: with the inventory reachable again, the honest answer is
        # still the empty list — the block is real, not an import artifact.
        self.assertEqual(ac.membership_inventory_routes(), [])

    def test_route_surface_carries_no_api_shape_at_all(self):
        # `api` is None, so any API-shaped token anywhere in what the module
        # hands back is a fabrication. Zero tolerance for every enumerated shape.
        for name, blob in (
            ("supported_route", json.dumps(ac.supported_route(), sort_keys=True)),
            ("decision_document", json.dumps(ac.decision_document(), sort_keys=True)),
        ):
            self.assertEqual(_fabricated_api_hits(blob), [], name)

    def test_module_source_carries_no_api_shape(self):
        source = Path(ac.__file__).read_text(encoding="utf-8")
        self.assertEqual(_api_shape_hits(source), [], "module source carries an API shape")

    def test_the_evidence_doc_carries_no_api_shape(self):
        doc = (_BONUS / "BONUS-ACCESS-CAPABILITY-DECISION.md").read_text(encoding="utf-8")
        self.assertEqual(_api_shape_hits(doc), [], "evidence doc carries an API shape")

    def test_no_other_bonus_file_carries_an_api_shape(self):
        # The whole deliverable is scanned, so nothing can hide beside the
        # module. The attack fixtures above are the single sanctioned exception.
        for path in sorted(_BONUS.rglob("*")):
            if not path.is_file() or path.name == "test_access_capability.py":
                continue
            if path.suffix not in (".py", ".md", ".json", ".txt"):
                continue
            text = path.read_text(encoding="utf-8")
            self.assertEqual(_api_shape_hits(text), [], str(path.relative_to(_REPO)))

    def test_the_scan_catches_every_known_smuggle_shape(self):
        for name, shape in SMUGGLE_SHAPES:
            self.assertTrue(
                _fabricated_api_hits(shape), f"{name} passes the scan uncaught"
            )

    def test_the_scan_leaves_legitimate_text_alone(self):
        # The inverse: a stricter scan must not become a blanket refusal. Real
        # provenance paths, filenames and plain prose carry no fabricated API.
        for text in LEGITIMATE_TEXT:
            self.assertEqual(_fabricated_api_hits(text), [], text[:60])

    def test_the_scan_guarantee_is_not_overstated(self):
        # A pattern scan catches the enumerated shapes; it is not a proof that
        # nothing can slip in, and the delivered prose may not promise more.
        for name, path in (
            ("module", Path(ac.__file__)),
            ("evidence doc", _BONUS / "BONUS-ACCESS-CAPABILITY-DECISION.md"),
        ):
            flat = " ".join(path.read_text(encoding="utf-8").split())
            self.assertNotIn("cannot slip a fabricated", flat, name)
            self.assertIn("pattern scan, not a proof", flat, name)
            # PBB-260: two fixed literals cannot see an overstatement they have
            # not met before. The guard classifies absolute detection claims by
            # class instead, so a fresh one fails here.
            self.assertEqual(_overstated_guarantee_hits(flat), [], name)
            for clause in REQUIRED_GUARANTEE_SCOPE:
                self.assertIn(clause, flat, f"{name} stopped stating: {clause}")

    def test_supported_route_reports_the_block_reason(self):
        route = ac.supported_route()
        self.assertFalse(route["available"])
        self.assertFalse(route["advertised_bonus_ready"])
        self.assertEqual(route["reason_code"], ac.BLOCK_REASON)
        self.assertEqual(route["route"], "assisted_operator")


class TestRequestRefusal(unittest.TestCase):
    """C-14: an unattended grant is refused, never silently downgraded."""

    def test_unattended_request_is_refused_with_the_exact_block(self):
        result = ac.request_bonus_access(unattended=True)
        self.assertFalse(result["granted"])
        self.assertTrue(result["refused"])
        self.assertEqual(result["route"], "refused")
        self.assertEqual(result["reason_code"], ac.BLOCK_REASON)
        self.assertEqual(result["blocked_steps"], list(ac.STEP_ORDER))
        self.assertTrue(result["no_silent_downgrade"])
        for step in ac.STEP_ORDER:
            self.assertIn(step, result["reason"])

    def test_refusal_offers_exactly_the_assisted_route(self):
        offer = ac.request_bonus_access(unattended=True)["offer"]
        self.assertEqual(offer["route"], "assisted_operator")
        self.assertEqual(offer["next"], "prepare_operator_instruction")

    def test_assisted_request_awaits_the_operator_and_has_no_receipt(self):
        result = ac.request_bonus_access(unattended=False)
        self.assertFalse(result["granted"])
        self.assertFalse(result["refused"])
        self.assertEqual(result["route"], "assisted_operator")
        self.assertEqual(result["status"], "awaiting-operator")
        self.assertIsNone(result["receipt"])
        self.assertFalse(result["system_claimed_grant"])
        self.assertEqual(result["blocked_steps"], list(ac.STEP_ORDER))

    def test_non_bool_unattended_is_refused(self):
        for value in ("yes", 1, None):
            with self.assertRaises(ac.BonusCapabilityError):
                ac.request_bonus_access(unattended=value)  # type: ignore[arg-type]


class TestOriginalGiftIndependence(unittest.TestCase):
    """C-F07: the original gift proceeds while the bonus is unavailable."""

    def test_original_is_ready_while_bonus_is_unavailable(self):
        plan = ac.plan_fulfillment(original_ready=True)
        self.assertTrue(plan["original"]["ready"])
        self.assertEqual(plan["original"]["route"], "direct_chat")
        self.assertFalse(plan["original"]["blocked_by_bonus"])
        self.assertFalse(plan["original"]["depends_on_bonus"])
        self.assertFalse(plan["bonus"]["available"])
        self.assertFalse(plan["advertised_bonus_ready"])
        self.assertEqual(plan["continuation"], "original_only")

    def test_a_not_ready_original_names_its_own_reason_never_the_bonus(self):
        plan = ac.plan_fulfillment(
            original_ready=False, original_reason="asset not yet approved for release"
        )
        self.assertFalse(plan["original"]["ready"])
        self.assertEqual(plan["original"]["reason"], "asset not yet approved for release")
        self.assertFalse(plan["original"]["blocked_by_bonus"])
        self.assertEqual(plan["continuation"], "original_repair")
        self.assertNotIn("bonus", plan["original"]["reason"].lower())

    def test_a_not_ready_original_must_name_its_reason(self):
        for reason in ("", "   "):
            with self.assertRaises(ac.BonusCapabilityError):
                ac.plan_fulfillment(original_ready=False, original_reason=reason)

    def test_original_lane_is_identical_when_the_bonus_lane_changes(self):
        # Prove no coupling: even a hypothetical proved bonus cannot move the
        # original lane. Same inputs must yield the same original dict.
        before = ac.plan_fulfillment(original_ready=True)["original"]
        proved = {
            "available": True,
            "route": "unattended",
            "blocked_steps": [],
            "missing_evidence": {},
            "api": None,
            "no_invented_api": True,
            "advertised_bonus_ready": True,
        }
        with _patched_route(proved):
            after_plan = ac.plan_fulfillment(original_ready=True)
        self.assertEqual(before, after_plan["original"])
        self.assertEqual(after_plan["continuation"], "original_and_bonus")

    def test_the_guard_rejects_a_hand_built_coupled_plan(self):
        coupled = ac.plan_fulfillment(original_ready=True)
        coupled["original"]["blocked_by_bonus"] = True
        with self.assertRaises(ac.BonusCouplingError):
            ac.assert_original_not_gated_by_bonus(coupled)
        coupled = ac.plan_fulfillment(original_ready=True)
        coupled["original"]["depends_on_bonus"] = True
        with self.assertRaises(ac.BonusCouplingError):
            ac.assert_original_not_gated_by_bonus(coupled)
        with self.assertRaises(ac.BonusCouplingError):
            ac.assert_original_not_gated_by_bonus({"bonus": {}})

    def test_non_bool_plan_inputs_are_refused(self):
        for kwargs in (
            {"original_ready": "true"},
            {"original_ready": True, "bonus_requested": "no"},
        ):
            with self.assertRaises(ac.BonusCapabilityError):
                ac.plan_fulfillment(**kwargs)  # type: ignore[arg-type]

    def test_the_guard_refuses_a_malformed_plan_with_the_domain_error(self):
        # The guard's job is to reject a bad plan. It must not answer a bad plan
        # with a bare AttributeError from duck-typed attribute access.
        for bad in (None, [], "plan", 1, object()):
            with self.assertRaises(ac.BonusCapabilityError):
                ac.assert_original_not_gated_by_bonus(bad)  # type: ignore[arg-type]
        # Inverse: a well-formed plan still passes the guard.
        self.assertTrue(
            ac.assert_original_not_gated_by_bonus(ac.plan_fulfillment(original_ready=True))
        )

    def test_a_not_ready_original_reason_must_be_a_real_string(self):
        # No silent coercion: str(None) would store the literal "None" as the
        # member-facing reason a not-ready lane is required to name.
        for reason in (None, 12345, [], {}, True):
            with self.assertRaises(ac.BonusCapabilityError):
                ac.plan_fulfillment(
                    original_ready=False, original_reason=reason
                )  # type: ignore[arg-type]
        # Inverse: a real reason still plans, and is stored verbatim minus padding.
        plan = ac.plan_fulfillment(
            original_ready=False, original_reason="  asset pending release  "
        )
        self.assertEqual(plan["original"]["reason"], "asset pending release")


class TestCredentialVersusResource(unittest.TestCase):
    """R-13: an expired credential is not expired guides."""

    def test_expired_credential_does_not_close_authorized_guides(self):
        state = ac.resolve_member_state(credential_state="expired", resource_authorized=True)
        self.assertFalse(state["credential_valid"])
        self.assertTrue(state["resource_available"])
        self.assertFalse(state["conflated"])
        self.assertIn("nothing about the guides", state["statement"])

    def test_valid_credential_does_not_authorize_guides(self):
        state = ac.resolve_member_state(credential_state="valid", resource_authorized=False)
        self.assertTrue(state["credential_valid"])
        self.assertFalse(state["resource_available"])

    def test_resource_availability_ignores_the_credential_on_every_state(self):
        for cred in ac.CREDENTIAL_STATES:
            self.assertTrue(
                ac.resolve_member_state(credential_state=cred, resource_authorized=True)[
                    "resource_available"
                ],
                cred,
            )
            self.assertFalse(
                ac.resolve_member_state(credential_state=cred, resource_authorized=False)[
                    "resource_available"
                ],
                cred,
            )

    def test_unknown_credential_state_is_refused(self):
        for value in ("good", "", None, "expir'd"):
            with self.assertRaises(ac.BonusCapabilityError):
                ac.resolve_member_state(credential_state=value, resource_authorized=True)  # type: ignore[arg-type]

    def test_uppercase_and_padded_credential_state_is_normalised(self):
        state = ac.resolve_member_state(credential_state=" EXPIRED ", resource_authorized=True)
        self.assertEqual(state["credential_state"], "expired")

    def test_non_bool_authorization_is_refused(self):
        for value in ("true", 1, None):
            with self.assertRaises(ac.BonusCapabilityError):
                ac.resolve_member_state(credential_state="valid", resource_authorized=value)  # type: ignore[arg-type]


class TestDecisionDocument(unittest.TestCase):
    def test_document_is_serialisable_and_self_consistent(self):
        doc = ac.decision_document()
        blob = json.dumps(doc, sort_keys=True)
        round_trip = json.loads(blob)
        self.assertEqual(round_trip["verdict"], "BLOCKED")
        self.assertEqual(round_trip["blocked_steps"], list(ac.STEP_ORDER))
        self.assertEqual(round_trip["steps"], list(ac.STEP_ORDER))
        self.assertEqual(round_trip["check_ids"], ["C-14", "C-F07"])
        self.assertTrue(round_trip["original_gift_independent"])
        self.assertIsNone(round_trip["route"]["api"])
        self.assertEqual(set(round_trip["evidence"]), set(ac.STEP_ORDER))


class TestEvidenceWording(unittest.TestCase):
    """The workflow ceiling is scoped, not stated as an absolute.

    The frozen registry carries v3 workflow rows that are NOT read-only (contact
    enrollment and unenrollment against an existing workflow), and the
    definition-authoring rows sit at staging-doc level. An absolute "read-only"
    claim overstates the registry it cites as authority. The ceiling that is
    true is the authoring ceiling in the frozen v3 production spec.
    """

    UNQUALIFIED_CLAIMS = (
        "cannot build or edit a workflow at all",
        "its only workflow operation is the read-only list",
        "workflows are read-only there",
        "workflows read-only on the public API",
    )
    QUALIFIERS = ("frozen v3 production spec", "not authoring", "staging")

    def _doc(self):
        raw = (_BONUS / "BONUS-ACCESS-CAPABILITY-DECISION.md").read_text(encoding="utf-8")
        return re.sub(r"\s+", " ", raw)  # prose wraps across lines

    def test_the_evidence_doc_does_not_overstate_the_workflow_ceiling(self):
        doc = self._doc()
        for phrase in self.UNQUALIFIED_CLAIMS:
            self.assertNotIn(phrase, doc, f"unqualified claim left in the doc: {phrase}")
        for qualifier in self.QUALIFIERS:
            self.assertIn(qualifier, doc, f"scope qualifier missing from the doc: {qualifier}")

    def test_the_module_claim_is_scoped_the_same_way(self):
        source = Path(ac.__file__).read_text(encoding="utf-8")
        for phrase in self.UNQUALIFIED_CLAIMS:
            self.assertNotIn(phrase, source, f"unqualified claim left in the module: {phrase}")
        claim = ac.capability_evidence()["grant"]["claim"]
        self.assertIn("frozen v3 production spec", claim)
        self.assertIn("not authoring", claim)

    def test_the_scoped_ceiling_does_not_change_the_block(self):
        # Scoping the wording is not softening the decision: the enrollment rows
        # are not a membership grant, so the grant step stays blocked.
        evidence = ac.capability_evidence()
        self.assertEqual(evidence["grant"]["state"], ac.RETIRED_RAIL_ONLY)
        self.assertFalse(evidence["grant"]["routable"])
        self.assertEqual(ac.decision_document()["verdict"], "BLOCKED")


class _patched_route:
    """Context manager: replace supported_route with a hypothetical proved one."""

    def __init__(self, value):
        self.value = value
        self._orig = None

    def __enter__(self):
        self._orig = ac.supported_route
        ac.supported_route = lambda: dict(self.value)
        return self

    def __exit__(self, *exc):
        ac.supported_route = self._orig
        return False


class TestTheExemptionsAreClosedWorld(unittest.TestCase):
    """PBB-260: an exemption may not travel with the token alone.

    Both defects in that verdict were the same mistake twice -- file provenance
    and the reviewed prose list were keyed on what a token LOOKED like and then
    applied whatever role the token was playing. A fabricated API played the
    role of a filename, or of reviewed prose, and reached the returned surface,
    the module source and the whole-deliverable scan uncaught. These tests are
    the proof for each one: they fail on the reviewed bytes and pass here.
    """

    FILE_SUFFIX_LAUNDERING = (
        "memberships/grant.py",
        "memberships/grant.json",
        "v1/memberships/grant.md",
        "x/memberships/grant.sh",
        "api/tools/memberships_grant.yml",
        "identity/grant/credential.txt",
        "courses/memberships.html",
        "memberships.grant.py",
    )
    REVIEWED_TOKEN_LAUNDERING = (
        "assisted/operator",
        "memberships/communities",
        "return/recovery",
        "identity/grant/credential/SMS/resource",
        "shared-utils/ghl",
    )
    VALUE_TEMPLATES = (
        '"operation": "{}"',
        'api: {}',
        '"api": "{}"',
        'route={} ',
        '| api | {} |',
    )

    def test_a_file_suffix_alone_is_never_provenance(self):
        # A1. `.py` says where to look, not what the token is.
        for token in self.FILE_SUFFIX_LAUNDERING:
            self.assertTrue(_fabricated_api_hits(token), token)

    def test_a_reviewed_token_alone_is_never_prose(self):
        # A2. A bare token is a value, not the sentence it was reviewed in.
        for token in self.REVIEWED_TOKEN_LAUNDERING:
            self.assertTrue(_fabricated_api_hits(token), token)

    def test_no_exemption_survives_an_api_value_position(self):
        # The class both defects share. Whatever the token names -- a real file,
        # a reviewed sentence, anything -- behind an api-shaped key it is an
        # operation value and is flagged.
        for token in (
            "courses/memberships",
            "memberships/grant.py",
            "shared-utils/ghl",
            "assisted/operator",
            "shared-utils/bonus/access_capability.py",
            "05-ghl-setup/INSTRUCTIONS.md",
        ):
            for template in self.VALUE_TEMPLATES:
                text = template.format(token)
                self.assertTrue(_fabricated_api_hits(text), text)

    def test_the_file_exemption_needs_a_file_that_exists(self):
        # Provenance is a real path in this tree and nothing else.
        self.assertFalse(_fabricated_api_hits("shared-utils/ghl/capability_inventory.py"))
        self.assertFalse(_fabricated_api_hits("05-ghl-setup/INSTRUCTIONS.md"))
        self.assertTrue(_fabricated_api_hits("memberships/grant.py"))
        self.assertTrue(_fabricated_api_hits("v1/tools/engine/memberships_grant.py"))
        # PBB-311 A4: an f-string variable is provenance only when the variable
        # is BOUND in the same text and the whole expansion is a real file. The
        # previously-shipped pin called the unbound line clean; it is not.
        self.assertFalse(_fabricated_api_hits(
            '_GHL = "44-convert-and-flow-operator"\n'
            '_REGISTRY = f"{_GHL}/tools/engine/cli_anything/gohighlevel/public/operations.py"'
        ))
        self.assertTrue(_fabricated_api_hits(
            '_REGISTRY = f"{_GHL}/tools/engine/cli_anything/gohighlevel/public/operations.py"'
        ))
        self.assertTrue(_fabricated_api_hits(
            '_GHL = "44-convert-and-flow-operator"\n'
            '_REGISTRY = f"{_GHL}/tools/engine/cli_anything/memberships_grant.py"'
        ))

    def test_the_reviewed_exemption_does_not_travel_outside_its_sentence(self):
        # Closed world: the list names the exact sentence each token was
        # reviewed in. A reworded sentence is not that sentence, so the token
        # is an operation shape again until a human reviews the new wording.
        for token in self.REVIEWED_TOKEN_LAUNDERING:
            self.assertTrue(_fabricated_api_hits(token), token)
            self.assertTrue(_fabricated_api_hits(f"see the {token} wording here"), token)
        self.assertFalse(_fabricated_api_hits(
            "the assisted/operator path and the R-13 / DEC-16 authority"
        ))

    def test_a_trailing_path_segment_is_caught_but_a_bare_verb_is_not(self):
        # Same class, one step wider: `memberships/` is the operation family with
        # its operation cut off and is still operation-shaped. `POST/` is a verb
        # with nothing behind it and is not an operation -- the inverse keeps the
        # stricter scan from becoming a blanket refusal.
        self.assertTrue(_fabricated_api_hits("memberships/"))
        self.assertTrue(_fabricated_api_hits("v1/memberships/"))
        self.assertFalse(_fabricated_api_hits("POST/"))
        self.assertFalse(_fabricated_api_hits("get/"))
        self.assertFalse(_fabricated_api_hits("DELETE/"))
        self.assertFalse(_fabricated_api_hits(""))
        self.assertFalse(_fabricated_api_hits("//"))
        # every verb plus a real path is still caught
        for verb in ("GET", "post", "Put", "PATCH", "DELETE", "Head", "OPTIONS"):
            self.assertTrue(_fabricated_api_hits(f"{verb}/memberships/grant"), verb)

    # PBB-311: each defect below is pinned by CLASS, so the same mistake in a
    # spelling nobody typed here still fails.
    WRAPPER_SEAMS = (
        "api: `{token}`",
        "api: **{token}**",
        "api: ({token})",
        "api: [{token}](x)",
        "| api | `{token}` |",
        '{{"operation": {{"inner": "{token}"}}}}',
        "api -> {token}",
        'spec["api"] = "{token}"',
    )
    def test_a_wrapper_cannot_hide_an_operation_value(self):
        # A1. Every wrapper spelling resolves to the same key, so an exemption
        # never survives the position.
        for token in (
            "shared-utils/bonus/access_capability.py",
            "shared-utils/ghl/capability_inventory.py",
            "assisted/operator",
        ):
            for seam in self.WRAPPER_SEAMS:
                text = seam.format(token=token)
                self.assertTrue(_fabricated_api_hits(text), text)

    def test_a_separator_spelling_cannot_hide_an_operation_path(self):
        # A2/A3. Doubled, backslash and look-alike slashes are one class.
        for sep in ("/", "//", "\\\\", "／", "∕", "⁄", "⧸"):
            text = f"memberships{sep}grant"
            self.assertTrue(_fabricated_api_hits(text), repr(text))
            verb = f"POST{sep}memberships{sep}grant"
            self.assertTrue(_fabricated_api_hits(verb), repr(verb))
        # the scheme slashes are not collapsed away
        self.assertTrue(_fabricated_api_hits("https://api.leadconnectorhq.com/v1/x"))

    def test_a_template_needs_its_variable_bound(self):
        # A4. Resolution, not tail-matching: an unbound head is not provenance.
        bound = (
            '_GHL = "44-convert-and-flow-operator"\n'
            '_REGISTRY = f"{_GHL}/tools/engine/cli_anything/gohighlevel/public/operations.py"'
        )
        self.assertFalse(_fabricated_api_hits(bound))
        for unbound in (
            'f"{TOTALLY_FAKE}/bonus/access_capability.py"',
            'f"{X}/s/bonus/access_capability.py"',
            'f"{X}/tools/engine/cli_anything/gohighlevel/public/operations.py"',
        ):
            self.assertTrue(_fabricated_api_hits(unbound), unbound)
        # A4's other half: a provenance name must begin at a segment boundary,
        # so a tail cut out of the middle of a real path is not the real path.
        self.assertTrue(_is_real_file_name("bonus/access_capability.py"))
        self.assertFalse(_is_real_file_name("s/bonus/access_capability.py"))
        self.assertFalse(_is_real_file_name("{_GHL}/tools/engine/cli_anything/gohighlevel/public/operations.py"))
        # a bound head that expands to a file that does not exist is not either
        self.assertTrue(_fabricated_api_hits(
            '_GHL = "44-convert-and-flow-operator"\n'
            '_REGISTRY = f"{_GHL}/tools/engine/cli_anything/memberships_grant.py"'
        ))

    def test_a_reviewed_window_is_not_reviewed_inside_a_value(self):
        # A5. The window is the unit of review, so it must start outside a value.
        window = "The supported path is assisted/operator: the owner creates th"
        self.assertFalse(_fabricated_api_hits(window))
        for label in ("target: ", "route: ", "url: ", "endpoint -> "):
            self.assertTrue(_fabricated_api_hits(label + window), label + window)

    def test_the_role_walk_reaches_the_depth_the_text_has(self):
        # Defect 3's bound. The previous read was `for _ in range(4)` while both
        # delivered documents claimed the walk went out through nested frames.
        # The read is off a token stack now, so the depth it reaches is the
        # depth the text has; five frames and ten frames both answer to the key
        # that owns them. Pinned at two depths past the old bound so a
        # reintroduced ceiling fails here.
        for depth in (5, 10):
            keys = ["api"] + [f"k{i}" for i in range(depth - 1)]
            text = (
                "".join(f'{{"{key}":' for key in keys)
                + '"shared-utils/bonus/access_capability.py"'
                + "}" * depth
            )
            self.assertTrue(_fabricated_api_hits(text), f"{depth} frames")
        # The key must be the one that OWNS the value, not the nearest one.
        self.assertTrue(_fabricated_api_hits(
            '{"api": {"note": "shared-utils/bonus/access_capability.py"}}'
        ))
        self.assertTrue(_fabricated_api_hits(
            '{"note": {"api": {"deep": "shared-utils/bonus/access_capability.py"}}}'
        ))
        # PBB-443 RULING, ON THE RECORD. The two lines below used to assert
        # that a real repo path nested under keys like `note` / `deep` /
        # `deeper` reads CLEAN. That is exactly the hole PBB-429 charged:
        # "behind any of those, a real repo path keeps its file-provenance
        # exemption and reads as an innocent citation", and the brief's ruling
        # is that "an unrecognised key that carries a real repo path must FAIL
        # CLOSED, and only a declared legitimate prose context may allow it".
        # `deeper` is an unrecognised key carrying a real repo path, so it
        # FAILS. The over-refusal control moved to where the brief puts it: a
        # declared legitimate prose context, and a citation with no key bound
        # to it at all.
        self.assertTrue(_fabricated_api_hits(
            '{"note": {"deep": {"deeper": "shared-utils/ghl/capability_inventory.py"}}}'
        ))
        self.assertTrue(_fabricated_api_hits(
            'f(a[{"b": ({"c": [{"d": "shared-utils/ghl/capability_inventory.py"}]})}])'
        ))
        # Shallow legitimate nesting still passes: no key binds the citation,
        # so it is prose and its file provenance is real.
        self.assertEqual(_fabricated_api_hits(
            '["shared-utils/ghl/capability_inventory.py", "05-ghl-setup/INSTRUCTIONS.md"]'
        ), [])
        self.assertEqual(_fabricated_api_hits(
            '{"note": "plain", "other": 1}'
        ), [])
        self.assertEqual(_fabricated_api_hits(
            "the assisted/operator path and the R-13 / DEC-16 authority"
        ), [])

    def test_the_three_falsified_sentences_are_gone_and_the_guard_sees_them(self):
        # Defect 3. PBB-371 measured three shipped sentences the guard could not
        # see: an unbounded walk claim over code bounded at four, a claim that
        # wrappers are removed before the role is read, and a claim that no
        # spelling can be chosen past the rules. All three are gone from the
        # delivered prose, and the guard fires on each as a CLASS.
        falsified = (
            "including a key reached by walking out through nested frames",
            "Wrappers cannot hide the role because they are removed before the "
            "role is read.",
            "so a smuggling shape cannot choose a spelling the rules miss",
            "a key reached by walking out through nested frames",
            "Wrappers cannot hide the role",
            "walks out through nested frames however deep they go",
            "wrappers are removed before the role is read",
            "a smuggling shape cannot choose a spelling the rules miss",
        )
        for claim in falsified:
            self.assertTrue(_overstated_guarantee_hits(claim), claim)
        for name, path in (
            ("module", Path(ac.__file__)),
            ("evidence doc", _BONUS / "BONUS-ACCESS-CAPABILITY-DECISION.md"),
        ):
            flat = " ".join(path.read_text(encoding="utf-8").split())
            for claim in falsified[:3]:
                self.assertNotIn(claim, flat, f"{name} still ships: {claim}")
        # The scope is stated instead: the walk's window is named, and the
        # bound of the read is the depth of the text rather than a claim about
        # every nesting.
        for name, path in (
            ("module", Path(ac.__file__)),
            ("evidence doc", _BONUS / "BONUS-ACCESS-CAPABILITY-DECISION.md"),
        ):
            flat = " ".join(path.read_text(encoding="utf-8").split())
            self.assertIn("4000-character role window", flat, name)
            self.assertIn("the depth the text actually has", flat, name)

    def test_the_prose_guard_sees_the_class_it_names(self):
        # B2. The guard must flag the falsified sentence itself and the common
        # rephrasings, and must stay silent on honest scoping prose.
        for claim in (
            "so an edit that adds one of those shapes fails the suite",
            "an edit that adds one of those shapes fails the suite",
            "nothing slips past the scan",
            "the scan catches everything",
            "no fabrication gets through",
            "the scan cannot be bypassed",
            "the scan is airtight",
            "every fabrication is stopped",
            "a later edit cannot slip one in",
            # PBB-387 defect 3: the three sentences the shipped guard could not
            # see, and two rephrasings of each.
            "including a key reached by walking out through nested frames",
            "a key reached by walking out through nested frames",
            "walks out through nested frames however deep they go",
            "the read walks out through any frames",
            "Wrappers cannot hide the role because they are removed before the "
            "role is read.",
            "Wrappers cannot hide the role",
            "wrappers are removed before the role is read",
            "so a smuggling shape cannot choose a spelling the rules miss",
            "a smuggling shape cannot choose a spelling the rules miss",
            "no spelling can be chosen that the rules miss",
            # PBB-443 defect 3: the false sentence the shipped guard could not
            # see, and the rephrasings of the same promise.
            "every separator look-alike -- any character whose Unicode name "
            "calls it a solidus or a slash -- reaches the same rule as `/`.",
            "every separator look-alike reaches the same rule",
            "any character whose Unicode name calls it a solidus or a slash "
            "arrives at the same rule as `/`",
            "no separator escapes the rule",
            "every character whose name calls it a slash is mapped",
            "however it is spelled, the token is read",
        ):
            self.assertTrue(_overstated_guarantee_hits(claim), claim)
        for honest in (
            "It is a pattern scan, not a proof: a fabrication in a shape the scan does not enumerate is not caught.",
            "coverage is not hollow",
            "the scan does not enumerate every shape",
            "the reviewer's table scores 46 of 46",
            # PBB-387: the honest scope statements this round ships, which must
            # stay silent under the wider guard.
            "The read walks out to the depth the text actually has, inside a "
            "4000-character role window.",
            "no wrapper spelling has to be listed to be read",
            "a bracket inside a string literal is never a frame boundary",
            "A seam is any run carrying a non-whitespace separator character "
            "between a key token and the value",
            # PBB-443: the scoped separator sentence, which names the shapes
            # it excludes and therefore is not the guarded class.
            "every separator look-alike -- any character whose Unicode name "
            "calls it a solidus or a slash, anywhere in the code space -- "
            "reaches the same rule as `/`, outside the two literal shapes that "
            "keep their own separators: a real Windows path and a scheme with "
            "an empty authority.",
        ):
            self.assertEqual(_overstated_guarantee_hits(honest), [], honest)

    def test_the_named_falsified_sentence_is_gone_from_every_delivered_document(self):
        # B1/B3/B4/B5. The exact claim the prior verdict falsified, and the two
        # absolute claims about provenance and reviewed prose, may not ship.
        falsified = "an edit that adds one of those shapes fails the suite"
        forbidden = (
            falsified,
            "resolves to a real file in this tree; a",
            "passes only inside the exact sentence it was reviewed in",
        )
        for name, path in (
            ("module", Path(ac.__file__)),
            ("evidence doc", _BONUS / "BONUS-ACCESS-CAPABILITY-DECISION.md"),
        ):
            flat = " ".join(path.read_text(encoding="utf-8").split())
            for claim in forbidden:
                self.assertNotIn(claim, flat, f"{name} still ships: {claim}")

    def test_the_changelog_entries_this_task_touched_claim_only_what_holds(self):
        # B1/B5: the CHANGELOG shipped the same falsified sentence and an
        # absolute about value positions. Both are gone, and the entries that
        # remain carry no absolute detection claim of the guarded class.
        flat = " ".join(
            (_REPO / "38-conversational-ai-system/CHANGELOG.md")
            .read_text(encoding="utf-8")
            .split()
        )
        self.assertNotIn("an edit that adds one of those shapes fails the suite", flat)
        self.assertNotIn("whatever a token names", flat)
        head = flat.split("## [2.0.34]")[0]
        self.assertEqual(_overstated_guarantee_hits(head), [], "changelog head")

    def test_the_scan_refuses_non_text_with_the_domain_error(self):
        # Defect C: a wrong type answers with the domain error, not a bare
        # TypeError thrown from inside a regex.
        for bad in (None, 123, 0.5, ["a/b"], {"a": "b/c"}, b"bytes", (1, 2)):
            for fn in (
                _api_shape_hits,
                _fabricated_api_hits,
                _dotted_operation_hits,
                _overstated_guarantee_hits,
            ):
                with self.assertRaises(ac.BonusCapabilityError):
                    fn(bad)

    def test_a_legitimate_expression_is_not_unwrapped_into_a_shape(self):
        # Defect 1's inverse. The read is over a token stream, so brackets stay
        # where the text put them: stripping the wrappers out of `a[b]/c[d]`
        # would manufacture `ab/cd`, an operation path that no sentence in the
        # text contains. The normaliser must not rewrite a filesystem literal
        # into a bare path either.
        for text in (
            "ratio = a[b]/c[d]",
            "res = compute(a[0], b[1])",
            "value = table[key]",
            'cfg = {"note": "plain", "other": 1}',
        ):
            self.assertEqual(_fabricated_api_hits(text), [], text)
        for text in (
            "file:///Users/me/project/file.py",
            "C:\\Users\\me\\project\\file.py",
            "\\\\server\\share\\doc.md",
        ):
            self.assertEqual(_fabricated_api_hits(text), [], text)
            self.assertEqual(_scan_text(text), text, text)

    def test_a_python_attribute_access_is_a_source_shape_not_a_surface_one(self):
        # The documented scope, pinned both ways. `cap.transport.value` is real
        # Python, so the SOURCE scan leaves it alone; on the returned surface a
        # dotted token is an operation id, and that is where the dotted rule
        # runs. One instrument answering twice would be a scope claim the code
        # does not make.
        self.assertEqual(_api_shape_hits("value = cap.transport.value"), [])
        self.assertTrue(_fabricated_api_hits("value = cap.transport.value"))

    def test_the_harness_controls_are_not_stuck_in_one_polarity(self):
        # Both polarities, on purpose. A probe that only ever passes proves
        # nothing, and a probe that only ever fails is a broken instrument.
        self.assertTrue(
            _fabricated_api_hits("api: shared-utils/bonus/access_capability.py"),
            "expected-FAIL control came back clean",
        )
        self.assertEqual(
            _fabricated_api_hits("shared-utils/ghl/capability_inventory.py"), [],
            "expected-PASS control came back flagged",
        )

    def test_the_scan_still_takes_text_of_every_shape(self):
        # Inverse for the type guard: real text still scans, and the shapes the
        # guard claims to catch are still caught.
        self.assertEqual(_api_shape_hits(""), [])
        self.assertEqual(_api_shape_hits("   \n\t "), [])
        self.assertTrue(_fabricated_api_hits("memberships/grant"))
        self.assertTrue(_fabricated_api_hits('"api": "/memberships/grant"'))

class TestPbb443Closures(unittest.TestCase):
    """The three defects PBB-429 charged, pinned, each with its inverse."""

    REAL = "shared-utils/bonus/access_capability.py"

    # The 27 key spellings PBB-429 measured. The 16 that used to read CLEAN
    # are the reason the vocabulary is gone.
    KEY_SPELLINGS = (
        "api", "route", "operation", "endpoint", "method", "path", "url",
        "uri", "action", "API", "Path", "href", "target", "link", "resource",
        "op", "call", "endpoints", "api_url", "apiPath", "theApi", "uri_",
        "operation_id", "fetch", "request", "end-point", "apis",
    )

    def test_no_key_vocabulary_decides_which_spellings_are_in_class(self):
        # DEFECT 1. Every key spelling carries the real repo path as its value
        # and every one of them is an operation value now. There is no list to
        # be outside of.
        for key in self.KEY_SPELLINGS:
            text = "%s: %s" % (key, self.REAL)
            self.assertTrue(_fabricated_api_hits(text), text)
            self.assertEqual(_role_state(text, text.index(self.REAL))[0], BOUND,
                             text)
        # Over-refusal control, where the brief puts it: a declared legitimate
        # prose context still passes.
        for text in (
            "the assisted/operator path and the R-13 / DEC-16 authority",
            "shared-utils/ghl/capability_inventory.py",
            "05-ghl-setup/INSTRUCTIONS.md",
            "see shared-utils/ghl/capability_inventory.py for the inventory",
            '    _GHL = "44-convert-and-flow-operator"\n'
            '    _REGISTRY = f"{_GHL}/tools/engine/cli_anything/'
            'gohighlevel/public/operations.py"',
        ):
            self.assertEqual(_fabricated_api_hits(text), [], text)

    def test_a_reviewed_row_is_the_only_way_through_a_value(self):
        # The allow-path, and the wall around it. A reviewed row reproduced
        # verbatim at a row boundary passes; the same text behind a key, or
        # opened inside a frame, does not.
        row = ('"provenance": ["shared-utils/ghl/capability_inventory.py", '
               '"05-ghl-setup/INSTRUCTIONS.md"]')
        self.assertEqual(_fabricated_api_hits("x, " + row), [])
        self.assertTrue(_fabricated_api_hits("api: {" + row + "}"))
        self.assertTrue(_fabricated_api_hits("api: `" + self.REAL + "`"))
        self.assertTrue(_fabricated_api_hits("api: (" + self.REAL + ")"))
        self.assertTrue(_fabricated_api_hits('api: "' + self.REAL + '"'))
        self.assertTrue(_fabricated_api_hits(
            '{"note": {"deep": {"deeper": "%s"}}}' % self.REAL
        ))

    def test_every_named_separator_reaches_the_rule(self):
        # DEFECT 3, EXTENDED. The derivation covers the whole code space and
        # `_drop_invisible` keeps a named separator instead of deleting it, so
        # the 11 above U+10FFF and the 5 combining overlays reach the rule.
        named = [
            cp for cp in range(0x110000)
            if cp != ord("/")
            and ("SOLIDUS" in (unicodedata.name(chr(cp), "") or "")
                 or "SLASH" in (unicodedata.name(chr(cp), "") or ""))
        ]
        self.assertEqual(len(named), 46, "the named look-alike class changed")
        for cp in named:
            text = "memberships%sgrant" % chr(cp)
            self.assertTrue(
                _fabricated_api_hits(text),
                "U+%04X %s does not reach the rule"
                % (cp, unicodedata.name(chr(cp))),
            )
        # Two representatives the old derivation could not see, named so a
        # regression to `range(0x11000)` or to dropping combining marks fails
        # here by name.
        for cp, name in (
            (0x1F67C, "VERY HEAVY SOLIDUS"),
            (0x0337, "COMBINING SHORT SOLIDUS OVERLAY"),
            (0xE002F, "TAG SOLIDUS"),
        ):
            self.assertIn(name, unicodedata.name(chr(cp)))
            self.assertTrue(_fabricated_api_hits("memberships%sgrant" % chr(cp)))
        # Inverse: the scoped sentence the prose now ships is true, and the
        # unscoped one is guarded.
        self.assertEqual(_overstated_guarantee_hits(
            "every separator look-alike -- any character whose Unicode name "
            "calls it a solidus or a slash, anywhere in the code space -- "
            "reaches the same rule as `/`, outside the two literal shapes that "
            "keep their own separators: a real Windows path and a scheme with "
            "an empty authority."
        ), [])
        self.assertTrue(_overstated_guarantee_hits(
            "every separator look-alike -- any character whose Unicode name "
            "calls it a solidus or a slash -- reaches the same rule as `/`."
        ))

    def test_a_token_past_the_role_window_is_refused_not_exempt(self):
        # THE WINDOW BYPASS. A real repo path nested past the window used to
        # read as empty and then fall through to the file-provenance exemption
        # and PASS. It is unresolved now, and unresolved flags.
        for depth in (2, 100, 300, 400, 460, 500, 570, 800, 1200):
            keys = ["api"] + ["k%d" % i for i in range(depth - 1)]
            text = (
                "".join('{"%s":' % key for key in keys)
                + '"%s"' % self.REAL + "}" * depth
            )
            self.assertTrue(_fabricated_api_hits(text), f"{depth} frames")
            self.assertNotEqual(
                _role_state(text, text.index(self.REAL))[0], PROSE,
                f"{depth} frames read as prose",
            )
        # The same shape with no exemption to fall through to is flagged at
        # every depth too -- so the difference above was the exemption, not
        # the shape.
        for depth in (2, 460, 1200):
            keys = ["api"] + ["k%d" % i for i in range(depth - 1)]
            text = (
                "".join('{"%s":' % key for key in keys)
                + '"memberships/grant"' + "}" * depth
            )
            self.assertTrue(_fabricated_api_hits(text), f"{depth} frames")
        # Shallow legitimate nesting still passes: no key binds the citation.
        self.assertEqual(_fabricated_api_hits(
            '["shared-utils/ghl/capability_inventory.py", '
            '"05-ghl-setup/INSTRUCTIONS.md"]'
        ), [])
        self.assertEqual(_fabricated_api_hits(
            '{"note": "plain", "other": 1}'
        ), [])
        # And the window states its own consequence: a head the read cannot
        # align to a token boundary is unresolved, never "no key". A 6000
        # character run with no whitespace has no boundary to align to.
        run = "a" * 6000 + " " + self.REAL
        self.assertFalse(_role_window(run, run.index(self.REAL))[1])
        self.assertEqual(
            _role_state(run, run.index(self.REAL))[0], UNRESOLVED
        )
        self.assertTrue(_fabricated_api_hits(run))
        # A list element answers to the key that binds the LIST, so a
        # fabrication cannot hide behind a comma either.
        self.assertTrue(_fabricated_api_hits(
            '{"api": [1, "%s"]}' % self.REAL
        ))

    def test_the_rules_that_had_no_pin_are_pinned(self):
        # PBB-429's mutation survivors M10, M11, M19, M20, M29. A rule with no
        # pin that can fail is decoration.
        # M10: `[` indexes something only when something precedes it.
        self.assertTrue(_is_subscript(_tokens('spec["api"]'), 1))
        self.assertFalse(_is_subscript(_tokens("a = [1]"), 2))
        # M11: the string delimiters are DERIVED from Unicode names, so the
        # single quote, the backtick and the typographic quotes are all in
        # class. Shrinking the set to `"` alone fails here.
        for quote in "\"'`“”‘’«»":
            self.assertIn(quote, _STRING_QUOTES, repr(quote))
        self.assertIn(
            ("STR", "[x]"),
            [(kind, val) for kind, val, _, _ in _tokens("a '[x]'")],
        )
        # M29: a string prefix is derived -- one or two letters, whatever they
        # are -- and three letters is still a key.
        self.assertTrue(_STRING_PREFIX.match("f"))
        self.assertTrue(_STRING_PREFIX.match("rb"))
        self.assertTrue(_STRING_PREFIX.match("zz"))
        self.assertIsNone(_STRING_PREFIX.match("api"))
        self.assertEqual(_tokens('f"[x]"')[0], ("STR", "[x]", 0, 6))
        # M19: a call name is not a key, so `api: compute(x)` answers to `api`.
        self.assertTrue(_fabricated_api_hits(
            "api: compute(%s)" % self.REAL
        ))
        # M20: the required scope is pinned by its own contents.
        self.assertEqual(len(REQUIRED_GUARANTEE_SCOPE), 5)
        for clause in REQUIRED_GUARANTEE_SCOPE:
            self.assertGreater(len(clause), 8, clause)
        # And the comma rule the row read needs: a list element does not read
        # the element before it as its key.
        text = '["a.md", "shared-utils/ghl/capability_inventory.py"]'
        self.assertEqual(
            _role_state(text, text.index("shared-utils"))[0], PROSE
        )
        self.assertIsNone(
            _seam(_tokens('["a.md", "b.md"]'), 2)[0]
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
