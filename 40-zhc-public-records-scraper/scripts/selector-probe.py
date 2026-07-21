#!/usr/bin/env python3
"""selector-probe.py — Skill 40 result-selector evaluator (SK1-30 / T0-53).

05-validate-target.sh used to pass a target as "safe to use live" on the COUNT
of keys in the config's `selectors` object. The shipped Tier-3 template fills
that object with four `<css-selector-...>` placeholders, so an unedited template
counted four selectors and passed. A target whose selectors match nothing was
certified live-safe, and the live run then produced records extracted by
selectors that were never evaluated against a page.

This evaluates each selector against a REAL document (an operator-supplied
saved results page) and reports, per selector, one of:

    MATCHED <n>   the selector matched n elements in the document
    NO_MATCH      the selector is valid but matched nothing
    UNSUPPORTED   the selector uses a construct this probe cannot evaluate

UNSUPPORTED is a FAILURE, never a skip: a selector this probe cannot evaluate
has not been proven to work, and an unevaluated selector is exactly the state
the finding is about.

Supported subset (deliberately small and exact):
    tag, .class, #id, [attr], [attr=value], [attr*=value], [attr^=value],
    [attr$=value], and compounds of those (e.g. tr.result-row[data-id]),
    combined with the descendant (space) and child (>) combinators.

Usage:
    selector-probe.py <document.html> <selector> [<selector> ...]

Exit: 0 = every selector matched at least one element
      1 = at least one selector did not match or is unsupported
      2 = bad invocation / unreadable document
"""

from __future__ import annotations

import re
import sys
from html.parser import HTMLParser

VOID = {
    "area", "base", "br", "col", "embed", "hr", "img", "input", "link",
    "meta", "param", "source", "track", "wbr",
}


class Node:
    __slots__ = ("tag", "attrs", "children", "parent")

    def __init__(self, tag, attrs=None, parent=None):
        self.tag = tag
        self.attrs = attrs or {}
        self.children = []
        self.parent = parent


class TreeBuilder(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = Node("#document")
        self.cursor = self.root

    def handle_starttag(self, tag, attrs):
        node = Node(tag.lower(), {k.lower(): (v or "") for k, v in attrs}, self.cursor)
        self.cursor.children.append(node)
        if tag.lower() not in VOID:
            self.cursor = node

    def handle_startendtag(self, tag, attrs):
        node = Node(tag.lower(), {k.lower(): (v or "") for k, v in attrs}, self.cursor)
        self.cursor.children.append(node)

    def handle_endtag(self, tag):
        tag = tag.lower()
        walk = self.cursor
        while walk is not None and walk.tag != tag:
            walk = walk.parent
        if walk is not None and walk.parent is not None:
            self.cursor = walk.parent


class Unsupported(Exception):
    pass


_COMPOUND = re.compile(
    r"""
    (?P<tag>^[A-Za-z][A-Za-z0-9-]*)
  | \.(?P<cls>[A-Za-z_][\w-]*)
  | \#(?P<id>[A-Za-z_][\w-]*)
  | \[\s*(?P<attr>[A-Za-z_:][\w:.-]*)\s*
        (?:(?P<op>[*^$|~]?=)\s*(?P<val>"[^"]*"|'[^']*'|[^\]\s]+)\s*)?\]
    """,
    re.VERBOSE,
)


def parse_compound(text: str):
    """Parse one compound selector into a list of predicate tuples."""
    text = text.strip()
    if not text:
        raise Unsupported("empty compound")
    preds = []
    pos = 0
    while pos < len(text):
        m = _COMPOUND.match(text, pos)
        if not m or m.end() == pos:
            raise Unsupported("unsupported construct at %r" % text[pos:])
        if m.group("tag"):
            preds.append(("tag", m.group("tag").lower()))
        elif m.group("cls"):
            preds.append(("class", m.group("cls")))
        elif m.group("id"):
            preds.append(("id", m.group("id")))
        elif m.group("attr"):
            val = m.group("val")
            if val and val[0] in "\"'":
                val = val[1:-1]
            preds.append(("attr", m.group("attr").lower(), m.group("op"), val))
        pos = m.end()
    return preds


def compound_matches(node: Node, preds) -> bool:
    for p in preds:
        kind = p[0]
        if kind == "tag":
            if node.tag != p[1]:
                return False
        elif kind == "class":
            if p[1] not in (node.attrs.get("class") or "").split():
                return False
        elif kind == "id":
            if (node.attrs.get("id") or "") != p[1]:
                return False
        elif kind == "attr":
            _, name, op, val = p
            if name not in node.attrs:
                return False
            actual = node.attrs.get(name) or ""
            if op is None:
                continue
            if op == "=":
                if actual != val:
                    return False
            elif op == "*=":
                if val not in actual:
                    return False
            elif op == "^=":
                if not actual.startswith(val):
                    return False
            elif op == "$=":
                if not actual.endswith(val):
                    return False
            else:
                raise Unsupported("attribute operator %r" % op)
    return True


def tokenize(selector: str):
    """Split a selector into [(combinator, compound), ...]."""
    if "," in selector:
        raise Unsupported("selector lists (comma) are not evaluated by this probe")
    if any(ch in selector for ch in ("~", "+", ":")):
        raise Unsupported("sibling/pseudo selectors are not evaluated by this probe")
    parts = []
    for chunk in re.split(r"\s*>\s*|\s+", selector.strip()):
        if chunk:
            parts.append(chunk)
    combinators = re.findall(r"\s*(>)\s*|\s+", selector.strip())
    # Re-derive combinators positionally: default descendant, '>' when present.
    combos = []
    idx = 0
    rest = selector.strip()
    for part in parts[1:]:
        idx = rest.find(part, idx)
        between = rest[:idx]
        combos.append(">" if between.rstrip().endswith(">") else " ")
        rest = rest[idx:]
        idx = len(part)
    del combinators
    return parts, combos


def walk(node: Node):
    for child in node.children:
        yield child
        yield from walk(child)


def select(root: Node, selector: str):
    parts, combos = tokenize(selector)
    compounds = [parse_compound(p) for p in parts]
    current = [n for n in walk(root) if compound_matches(n, compounds[0])]
    for i, comp in enumerate(compounds[1:]):
        combo = combos[i]
        nxt = []
        for base in current:
            pool = base.children if combo == ">" else list(walk(base))
            for cand in pool:
                if compound_matches(cand, comp) and cand not in nxt:
                    nxt.append(cand)
        current = nxt
    return current


def main(argv):
    if len(argv) < 3:
        sys.stderr.write("usage: selector-probe.py <document.html> <selector> [...]\n")
        return 2
    doc_path = argv[1]
    try:
        with open(doc_path, "r", encoding="utf-8", errors="replace") as fh:
            html = fh.read()
    except OSError as exc:
        sys.stderr.write("selector-probe: cannot read document %s: %s\n" % (doc_path, exc))
        return 2
    if not html.strip():
        sys.stderr.write("selector-probe: document %s is empty\n" % doc_path)
        return 2

    builder = TreeBuilder()
    builder.feed(html)
    builder.close()

    failed = False
    for selector in argv[2:]:
        try:
            hits = select(builder.root, selector)
        except Unsupported as exc:
            print("%s\tUNSUPPORTED %s" % (selector, exc))
            failed = True
            continue
        if hits:
            print("%s\tMATCHED %d" % (selector, len(hits)))
        else:
            print("%s\tNO_MATCH" % selector)
            failed = True
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
