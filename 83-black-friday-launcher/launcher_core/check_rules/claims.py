"""AF-LAUNCH-CLAIM: no discount or scarcity claim in any page's copy.

A check_rules module (see check_rules/__init__.py). The launch record carries no promotion facts in
this release (no compare-at price, bonus, seat limit or deadline), so a page that says "40% off",
"only 50 left" or "limited time" has nothing to be checked against and is refused, whatever claim
evidence it names. The phrase list is Skill 78's own claim scanner (selection_core
UNPROVEN_CLAIM_PATTERNS) plus the discount and scarcity wording below; one list, so the selection
page's own gate and this package gate cannot drift apart.

Every copy file a piece lists is scanned: text, markdown and html files, and any json file named
copy or manuscript, plus a piece's inline "copy". Design images and prompts are not copy.
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path
from typing import Any, Dict, Iterator, List, Tuple

CODE = "AF-LAUNCH-CLAIM"
COPY_SUFFIXES = (".md", ".txt", ".html", ".htm")
EXTRA_PATTERNS = (
    r"\b\d+\s?%\s?(?:off|discount|savings?)\b",
    r"\b(?:half|\d+ percent) off\b",
    r"\b(?:save|saving|savings of) (?:up to )?(?:[$€£]\s?)?\d",
    r"\b(?:was|regularly|normally|originally|compare at) (?:priced at )?[$€£]\s?\d",
    r"\bprice (?:goes|is going) up\b",
    r"\b(?:last chance|final hours?|selling fast|while supplies last|hurry|doors? (?:close|closing)|cart closes?)\b",
    r"\b(?:ends?|expires?) (?:tonight|today|tomorrow|soon|at midnight|monday|sunday)\b",
    r"\blimited (?:spots?|seats?|availability|quantity|supply|stock)\b",
    r"\b(?:spots?|seats?|licenses?) (?:are )?(?:limited|running out)\b",
    r"\b(?:only )?(?:a )?(?:few|limited number of) (?:spots?|seats?|places?|copies)\b",
)
_CORE = None


def _s78_patterns(skill_root: Path) -> Tuple[str, ...]:
    """Skill 78's claim patterns, read from its own selection_core."""
    global _CORE
    if _CORE is None:
        from launcher_core.constants import skill_path
        path = skill_path("signature-product-selection", "scripts", "selection_core.py",
                          root=Path(skill_root).parent)
        spec = importlib.util.spec_from_file_location("s78_selection_core_for_claims", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _CORE = tuple(module.UNPROVEN_CLAIM_PATTERNS)
    return _CORE


def found_claims(text: str, skill_root: Path) -> List[str]:
    low = text.lower()
    hits: List[str] = []
    for pattern in _s78_patterns(skill_root) + EXTRA_PATTERNS:
        for match in re.finditer(pattern, low):
            if match.group(0) not in hits:
                hits.append(match.group(0))
    return hits


def _inline(node: Any) -> Iterator[str]:
    if isinstance(node, str):
        yield node
    elif isinstance(node, dict):
        for value in node.values():
            yield from _inline(value)
    elif isinstance(node, (list, tuple)):
        for value in node:
            yield from _inline(value)


def _is_copy(name: str) -> bool:
    low = name.lower()
    return low.endswith(COPY_SUFFIXES) or (low.endswith(".json") and ("copy" in low or "manuscript" in low))


def violations(manifest: Dict[str, Any], root: Path, skill_root: Path) -> List[str]:
    fails: List[str] = []
    for piece in manifest.get("pieces") or []:
        label = str(piece.get("slot") or piece.get("role") or "page")
        texts: List[Tuple[str, str]] = [("inline copy", s) for s in _inline(piece.get("copy"))]
        for art in piece.get("artifacts") or []:
            path = str(art.get("path") or "")
            target = (Path(root) / path).resolve()
            if _is_copy(Path(path).name) and target.is_file():
                texts.append((Path(path).name, target.read_text(encoding="utf-8", errors="replace")))
        for source, text in texts:
            for phrase in found_claims(text, skill_root):
                fails.append(f"{CODE}: {label} copy {source!r} carries the claim {phrase!r}; discount and "
                             "scarcity claims are not supported in this release (the launch record holds "
                             "no promotion facts to prove one)")
    return fails
