#!/usr/bin/env python3
"""Skill 45 (Design Intelligence Library), read-only consumption for the Signature Launch family.

Fix spec M4 / decision D-F: the page skills (49, 71, 78 to 83) READ Skill 45's style cards and
rules and keep a receipt of exactly what they read; nothing in Skill 45 is ever written.

Every loader refuses by name (AF-DI-ABSENT) when the file it needs is missing, so a box without
Skill 45 can never silently build a "styled" page from nothing. A requested style card that does
not resolve is never dropped.

  library_root()                     the box's Skill 45 install (``library/`` holding INDEX.md)
  resolve_style_card(card_id)        {"id", "long_tier", "sha256", "path"}: the card's LONG tier
  load_prompt_bands()                {"json", "sha256"}   _system/prompt-bands.json
  load_negative_prompting()          {"text", "sha256"}   _system/NEGATIVE-PROMPTING-SOP.md
  load_page_rules(category)          {"text", "sha256"}   <category>/_RULES.md (default funnel pages)
  build_receipt / write_receipt      the receipt Skill 71's stage gate demands
  verify_receipt                     re-hash the live library against a receipt (drift = problem)

The LONG tier is cut the way the STYLE-CARD-TEMPLATE writes it (a ``### LONG`` heading, then a
fenced block), the same cut Skill 6's rail makes, so both rails embed the same bytes.

CLI (stdlib only, no network):
  design_intelligence.py receipt --run-dir DIR [--style-card-id FN-001] [--category funnel-page-designs]
  design_intelligence.py verify  --run-dir DIR
Exit 0 ok, 1 refusal (the AF code is printed), 2 usage.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

ABSENT = "AF-DI-ABSENT"
LIBRARY_ENV = "DIU_LIBRARY_DIR"  # the same override Skill 6's rail honours
RECEIPT_REL = Path("private") / "receipts" / "design-intelligence.json"
RECEIPT_SCHEMA = "skill45-design-intelligence-receipt/1"
DEFAULT_CATEGORY = "funnel-page-designs"
_HOME_CANDIDATES = (
    "~/.openclaw/skills/45-design-intelligence-library/library",
    "~/.openclaw/onboarding/45-design-intelligence-library/library",
    "/data/.openclaw/skills/45-design-intelligence-library/library",
)
_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_CATEGORY = re.compile(r"^[a-z0-9][a-z0-9-]*$")


class DesignIntelligenceError(Exception):
    """A named refusal. ``code`` is the AF code; the text always starts with it."""

    def __init__(self, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.code = code


def _absent(message: str) -> DesignIntelligenceError:
    return DesignIntelligenceError(ABSENT, message)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def library_root(env: Optional[Dict[str, str]] = None) -> Path:
    """The Skill 45 ``library/`` folder (the one holding INDEX.md), or AF-DI-ABSENT.

    Order: the DIU_LIBRARY_DIR override (it must itself hold INDEX.md; a bad override is a
    refusal, never a silent fall-through), the sibling skill in this checkout, then the
    installed skills trees."""
    environ = os.environ if env is None else env
    override = str(environ.get(LIBRARY_ENV, "")).strip()
    if override:
        p = Path(os.path.expanduser(override))
        if (p / "INDEX.md").is_file():
            return p
        raise _absent(f"{LIBRARY_ENV} names a folder without INDEX.md; Skill 45's library is not there")
    candidates = [Path(__file__).resolve().parents[2] / "45-design-intelligence-library" / "library"]
    candidates += [Path(os.path.expanduser(c)) for c in _HOME_CANDIDATES]
    for p in candidates:
        if (p / "INDEX.md").is_file():
            return p
    raise _absent("Skill 45's design library (45-design-intelligence-library/library/INDEX.md) is not "
                  f"installed on this box (set {LIBRARY_ENV} or install the skill); no style, rule or "
                  "prompt band can be read")


def _root(root: Optional[Path]) -> Path:
    return Path(root) if root is not None else library_root()


def _read(root: Path, rel: str) -> bytes:
    """Bytes of ``rel`` under the library, refusing a missing file and any path leaving the library."""
    base = Path(root).resolve()
    path = (base / rel).resolve()
    if base != path and base not in path.parents:
        raise _absent(f"{rel} resolves outside the design library")
    try:
        return path.read_bytes()
    except OSError:
        raise _absent(f"{rel} is missing from the design library at {base.name}/") from None


def _index_card_path(index_text: str, card_id: str) -> Optional[str]:
    """The File Path cell of the INDEX.md row whose ID column equals ``card_id`` (case-insensitive)."""
    target = card_id.strip().lower()
    id_col: Optional[int] = None
    for line in index_text.splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        lowered = [c.lower() for c in cells]
        if "id" in lowered and "file path" in lowered:  # a table header row: remember where ID sits
            id_col = lowered.index("id")
            continue
        if id_col is None or id_col >= len(cells) or cells[id_col].lower() != target:
            continue
        path = next((c for c in reversed(cells) if c and c != "-"), "")
        if path.startswith("[") and "](" in path and path.endswith(")"):
            path = path.split("](", 1)[1][:-1].strip()
        return path or None
    return None


def _extract_long_tier(card_text: str) -> Optional[str]:
    """The LONG-tier prompt from a card body: ``### LONG`` heading, then the first fenced block
    (else the raw section text). A heading-looking line inside the fence does not end the section."""
    lines = card_text.splitlines()
    start = next((i + 1 for i, ln in enumerate(lines) if ln.lstrip().startswith("### LONG")), None)
    if start is None:
        return None
    body: List[str] = []
    fenced = False
    for ln in lines[start:]:
        s = ln.lstrip()
        if s.startswith("```"):
            fenced = not fenced
        elif not fenced and (s.startswith("### ") or s.startswith("## ")):
            break
        body.append(ln)
    text = "\n".join(body)
    if "```" in text:
        parts = text.split("```")
        if len(parts) >= 3 and parts[1].strip():
            return parts[1].strip()
    return text.strip() or None


def resolve_style_card(card_id: str, root: Optional[Path] = None) -> Dict[str, str]:
    """``{"id", "long_tier", "sha256", "path"}`` for a registered style card.

    ``sha256`` is the hash of the LONG-tier text itself (the slice that is embedded), ``path`` is
    relative to the library. An unregistered id, a missing card file or a card with no LONG tier is
    a named refusal: a requested style is never silently dropped."""
    cid = str(card_id or "").strip()
    if not cid:
        raise _absent("style_card_id is empty")
    base = _root(root)
    rel = _index_card_path(_read(base, "INDEX.md").decode("utf-8"), cid)
    if not rel:
        raise _absent(f"style_card_id {cid!r} is not registered in the design library INDEX.md; "
                      "register the card (Skill 45 Workflow A) before a page references it")
    rel = rel.strip().lstrip("/")
    for prefix in ("design-library/", "library/"):
        if rel.startswith(prefix):
            rel = rel[len(prefix):]
            break
    card = _read(base, rel).decode("utf-8")
    long_tier = _extract_long_tier(card)
    if not long_tier:
        raise _absent(f"style card {cid!r} ({rel}) carries no LONG tier (a '### LONG' section); a "
                      "funnel style card must ship one to feed the Brand-Style block")
    return {"id": cid, "long_tier": long_tier, "sha256": _sha256(long_tier.encode("utf-8")), "path": rel}


def load_prompt_bands(root: Optional[Path] = None) -> Dict[str, Any]:
    """``{"json", "sha256"}``: the prompt bands (_system/prompt-bands.json)."""
    raw = _read(_root(root), "_system/prompt-bands.json")
    try:
        return {"json": json.loads(raw.decode("utf-8")), "sha256": _sha256(raw)}
    except ValueError:
        raise _absent("_system/prompt-bands.json is not readable JSON") from None


def load_negative_prompting(root: Optional[Path] = None) -> Dict[str, str]:
    """``{"text", "sha256"}``: the negative-prompting rules (_system/NEGATIVE-PROMPTING-SOP.md)."""
    raw = _read(_root(root), "_system/NEGATIVE-PROMPTING-SOP.md")
    return {"text": raw.decode("utf-8"), "sha256": _sha256(raw)}


def load_page_rules(category: str = DEFAULT_CATEGORY, root: Optional[Path] = None) -> Dict[str, str]:
    """``{"text", "sha256"}``: a category's _RULES.md (funnel pages by default)."""
    if not _CATEGORY.match(str(category or "")):
        raise _absent(f"{category!r} is not a design-library category folder name")
    raw = _read(_root(root), f"{category}/_RULES.md")
    return {"text": raw.decode("utf-8"), "sha256": _sha256(raw)}


def build_receipt(card_id: Optional[str] = None, category: str = DEFAULT_CATEGORY,
                  root: Optional[Path] = None) -> Dict[str, Any]:
    """What a stage read, as hashes. ``card_id``/``card_sha256`` are null when no card was requested."""
    base = _root(root)
    card = resolve_style_card(card_id, base) if card_id else None
    return {
        "schema": RECEIPT_SCHEMA,
        "card_id": card["id"] if card else None,
        "card_sha256": card["sha256"] if card else None,
        "prompt_bands_sha256": load_prompt_bands(base)["sha256"],
        "negative_prompting_sha256": load_negative_prompting(base)["sha256"],
        "page_rules_category": category,
        "page_rules_sha256": load_page_rules(category, base)["sha256"],
    }


def write_receipt(run_dir: Path, card_id: Optional[str] = None, category: str = DEFAULT_CATEGORY,
                  root: Optional[Path] = None) -> Path:
    """Write ``<run_dir>/private/receipts/design-intelligence.json`` and return its path."""
    receipt = build_receipt(card_id, category, root)
    path = Path(run_dir) / RECEIPT_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def run_style_card_id(run_dir: Path) -> Optional[str]:
    """The ``style_card_id`` a run's intake.json carries, else None (blank counts as unset)."""
    try:
        doc = json.loads((Path(run_dir) / "intake.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    value = doc.get("style_card_id") if isinstance(doc, dict) else None
    return (str(value).strip() or None) if value is not None else None


def verify_receipt(receipt: Any, root: Optional[Path] = None) -> List[str]:
    """Problems with a receipt, empty when it is well formed AND matches the live library.

    A receipt whose hashes no longer match was built against rules that have since changed (or
    never existed): the stage must be redone, not waved through."""
    if not isinstance(receipt, dict):
        return [f"{ABSENT}: the design-intelligence receipt is not a JSON object"]
    problems: List[str] = []
    for key in ("prompt_bands_sha256", "negative_prompting_sha256", "page_rules_sha256"):
        if not _HEX64.match(str(receipt.get(key) or "")):
            problems.append(f"{ABSENT}: receipt field {key} is missing or not a sha256")
    card_id, card_sha = receipt.get("card_id"), receipt.get("card_sha256")
    if bool(card_id) != bool(card_sha) or (card_sha and not _HEX64.match(str(card_sha))):
        problems.append(f"{ABSENT}: receipt card_id and card_sha256 must both be set or both be null")
    if problems:
        return problems
    try:
        live = build_receipt(card_id or None, str(receipt.get("page_rules_category") or DEFAULT_CATEGORY), root)
    except DesignIntelligenceError as exc:
        return [str(exc)]
    for key in ("card_sha256", "prompt_bands_sha256", "negative_prompting_sha256", "page_rules_sha256"):
        if live[key] != receipt.get(key):
            problems.append(f"{ABSENT}: receipt {key} does not match the design library now "
                            f"(receipt {str(receipt.get(key))[:12]}, library {str(live[key])[:12]}); "
                            "the prompts were built against different rules, so redo them")
    return problems


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Skill 45 read-only receipt for a Signature Launch run.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    rc = sub.add_parser("receipt", help="write private/receipts/design-intelligence.json for a run")
    rc.add_argument("--run-dir", required=True, type=Path)
    rc.add_argument("--style-card-id", default=None, help="default: the run's intake.json style_card_id")
    rc.add_argument("--category", default=DEFAULT_CATEGORY)
    vf = sub.add_parser("verify", help="re-hash the live library against the run's receipt")
    vf.add_argument("--run-dir", required=True, type=Path)
    a = ap.parse_args(argv)
    try:
        if a.cmd == "receipt":
            card = a.style_card_id if a.style_card_id is not None else run_style_card_id(a.run_dir)
            print(f"WROTE {write_receipt(a.run_dir, card, a.category)}")
            return 0
        path = a.run_dir / RECEIPT_REL
        try:
            receipt = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            print(f"{ABSENT}: no readable design-intelligence receipt at {RECEIPT_REL.as_posix()}")
            return 1
        problems = verify_receipt(receipt)
        for line in problems:
            print(line)
        print("OK: receipt matches the design library" if not problems else f"FAIL: {len(problems)} problem(s)")
        return 0 if not problems else 1
    except DesignIntelligenceError as exc:
        print(exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
