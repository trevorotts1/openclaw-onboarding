#!/usr/bin/env python3
"""client_rules.py - compile a CLIENT'S measurable absolute rules into the
production validation path, and sweep the declared client-facing output tree
(F19 items 7-10).

WHAT THIS IS
------------
A review that only inspects "design quality" cannot catch a banned phrase, a
wrong price, an unapproved font claim, or a business name the client never
used. This module is the ONE client-rule sweep: it loads a per-client rule
document, checks rendered/visible text recursively, and reports violations.
It never rewrites files, never guesses a default, and never installs one
client's preferences as another client's rules.

SCOPE AND PRECEDENCE (F19 item 10)
----------------------------------
Leanne's palette, business name, fonts and personal punctuation are examples
of a CLIENT-SCOPED rule file. This module carries NO default rule set:
``DEFAULT_RULES`` is None. A rules document must name its client. A document
without a client identity is refused, because a global default is exactly the
defect this module exists to prevent.

WHAT IT CHECKS (F19 item 7)
---------------------------
Measurable absolute rules only. Subjective design quality stays with the
independent review in review_record.py.
  * banned_phrase        - case-insensitive visible-text phrases
  * banned_punctuation   - exact characters (em dash, exclamation, etc.)
  * required_content     - phrases that must appear
  * approved_price      - every currency token must be an approved price
  * brand_name          - the canonical business name; forbidden aliases
  * truthful_scarcity   - unapproved scarcity claims ("only 3 left", "guaranteed")
  * truthful_proof      - unapproved proof claims ("100%", "#1", "proven")
  * presentation        - report/response-template rules (no em dash, no
                          exclamation, no ALL CAPS, required business name)

WHERE IT CHECKS (F19 item 8)
----------------------------
``sweep_tree`` walks the declared output tree recursively, including newly
added nested files. For rendered artifacts it checks visible text; it does not
blindly replace characters in code, URLs, signed evidence, hashes or legal
source quotations. Those regions are excluded, not "fixed".

WHAT A FILESYSTEM SWEEPER CANNOT DO (F19 item 9)
------------------------------------------------
It can apply presentation rules to generated client reports and response
templates. It cannot mechanically control arbitrary chat outside the reporting
integration; ``chat_enforcement()`` states that limitation so no report claims
otherwise.

Stdlib only. Deterministic.
"""
from __future__ import annotations

import html
import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

SCHEMA = "signature-launch-client-rules/v1"

#: Deliberately empty. A rule set is the CLIENT'S, never this module's default.
DEFAULT_RULES = None

#: Characters treated as punctuation rules.
PUNCTUATION_NAMES = {
    "—": "em dash",
    "–": "en dash",
    "!": "exclamation mark",
    ";": "semicolon",
}

_VISIBLE_EXTENSIONS = {
    ".html", ".htm", ".md", ".txt", ".svg", ".json", ".csv", ".xml",
    ".yml", ".yaml",
}
_SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__",
              ".mypy_cache", ".pytest_cache", ".next", ".cache"}
_REPORT_KEYS = {
    "headline", "title", "subtitle", "body", "copy", "summary", "message",
    "cta", "description", "text", "label", "caption", "offer", "price",
    "bullets", "paragraph", "note", "disclaimer",
}
_NON_TEXT_KEYS = {
    "sha256", "hash", "url", "uri", "path", "file", "file_id", "evidence",
    "code", "snippet", "signature", "approval_ref", "plan_hash", "id",
}
_URL_RE = re.compile(r"(?:https?://|data:|mailto:)\S+", re.IGNORECASE)
_HASH_RE = re.compile(r"\b(?:sha256:)?[a-f0-9]{40,64}\b", re.IGNORECASE)
_PRICE_RE = re.compile(r"(?:\$\s?\d[\d,]*(?:\.\d{1,2})?|\b\d[\d,]*\s?(?:USD|dollars?)\b)",
                       re.IGNORECASE)
_CODE_FENCE_RE = re.compile(r"```.*?```", re.DOTALL)
_INLINE_CODE_RE = re.compile(r"`[^`\n]+`")
_HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
_SCRIPT_RE = re.compile(r"<(script|style|pre|code)\b.*?</\1>", re.DOTALL | re.IGNORECASE)
_LEGAL_BLOCK_RE = re.compile(
    r"<(blockquote|div|p)[^>]*(?:class|data-[a-z-]+)=[\"'][^\"']*"
    r"(?:legal|quote|quotation)[^\"']*[\"'][^>]*>.*?</\1>",
    re.DOTALL | re.IGNORECASE)
_TAG_RE = re.compile(r"<[^>]+>")


class ClientRulesError(ValueError):
    """The rule document is unusable; the caller must fail closed."""


def _norm(text: Any) -> str:
    return str(text if text is not None else "").lower()


def _as_list(value: Any) -> List[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, (list, tuple)):
        return [str(item) for item in value if str(item).strip()]
    return []


def load_client_rules(source: Any, *, require_client: bool = True) -> Dict[str, Any]:
    """Load and validate a per-client rule document.

    ``source`` may be a path to JSON or the already-parsed dict. Raises
    ClientRulesError (fail closed) on a missing schema, a missing client
    identity, an unknown rule kind, or an explicit global-default claim.
    """
    if isinstance(source, (str, Path)):
        path = Path(source)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise ClientRulesError(f"client rules unreadable: {path} ({exc})") from exc
    else:
        data = source
    if not isinstance(data, dict):
        raise ClientRulesError("client rules document is not an object")
    if data.get("schema") != SCHEMA:
        raise ClientRulesError(f"client rules schema is not {SCHEMA}")
    client_id = data.get("client_id") or (data.get("scope") or {}).get("client_id")
    if require_client and not (isinstance(client_id, str) and client_id.strip()):
        raise ClientRulesError(
            "client rules name no client_id: a global default rule set is refused")
    if data.get("global_default") is True:
        raise ClientRulesError(
            "global_default is refused: client rules are client-scoped, never fleet-wide")
    rules = data.get("rules")
    if not isinstance(rules, list) or not rules:
        raise ClientRulesError("client rules document carries no rules")
    known = {"banned_phrase", "banned_punctuation", "required_content",
             "approved_price", "brand_name", "truthful_scarcity",
             "truthful_proof", "presentation"}
    seen = set()
    cleaned = []
    for index, rule in enumerate(rules):
        if not isinstance(rule, dict) or not str(rule.get("id") or "").strip():
            raise ClientRulesError(f"rule #{index} names no id")
        if rule["id"] in seen:
            raise ClientRulesError(f"duplicate rule id {rule['id']!r}")
        seen.add(rule["id"])
        if rule.get("kind") not in known:
            raise ClientRulesError(
                f"rule {rule['id']!r} has unknown kind {rule.get('kind')!r}")
        cleaned.append(dict(rule))
    out = dict(data)
    out["client_id"] = client_id
    out["rules"] = cleaned
    return out


def chat_enforcement() -> Dict[str, str]:
    """F19 item 9: state the limit instead of claiming chat control."""
    return {
        "filesystem_sweep": "checked client-facing files and generated reports",
        "chat": "not_mechanically_enforceable_by_filesystem_sweeper",
        "note": ("presentation rules are applied to generated client reports and "
                 "response templates; arbitrary chat outside the reporting "
                 "integration is not mechanically controlled by a file sweep"),
    }


def _strip_non_visible(text: str, *, suffix: str) -> str:
    """Remove regions the rule sweep must not rewrite or misread."""
    if suffix in (".html", ".htm", ".svg"):
        text = _HTML_COMMENT_RE.sub(" ", text)
        text = _LEGAL_BLOCK_RE.sub(" ", text)
        text = _SCRIPT_RE.sub(" ", text)
        text = _TAG_RE.sub(" ", text)
        text = html.unescape(text)
    if suffix in (".md", ".markdown"):
        text = _CODE_FENCE_RE.sub(" ", text)
        text = _INLINE_CODE_RE.sub(" ", text)
        text = "\n".join(line for line in text.splitlines()
                         if not line.lstrip().startswith(">"))
    # URLs, hashes and signed evidence are never rewritten or treated as prose.
    text = _URL_RE.sub(" ", text)
    text = _HASH_RE.sub(" ", text)
    return text


def visible_text(raw: str, *, file_name: str = "") -> str:
    """Extract the text a reader sees, excluding code, URLs, hashes and quotes."""
    return _strip_non_visible(raw, suffix=Path(file_name).suffix.lower())


def _presentation_fails(text: str, rule: dict) -> List[str]:
    fails: List[str] = []
    lower = _norm(text)
    for value in _as_list(rule.get("banned_phrases")):
        if value.lower() in lower:
            fails.append(f"banned phrase {value!r}")
    for value in _as_list(rule.get("banned_punctuation")):
        if value and value in text:
            fails.append(f"banned punctuation {PUNCTUATION_NAMES.get(value, value)!r}")
    if rule.get("no_exclamation") is True and "!" in text:
        fails.append("exclamation mark")
    if rule.get("no_all_caps") is True:
        allowed = {str(a).upper() for a in _as_list(rule.get("allowed_caps"))}
        for word in re.findall(r"\b[A-Z]{2,}\b", text):
            if word not in allowed:
                fails.append(f"all-caps word {word!r}")
                break
    required_name = rule.get("require_business_name")
    if isinstance(required_name, str) and required_name.strip() \
            and required_name.lower() not in lower:
        fails.append(f"required business name {required_name!r} is absent")
    return fails


def rule_fails(text: str, rules: Dict[str, Any], *,
               surface: str = "visible_text") -> List[Dict[str, str]]:
    """Return findings for one text surface. Never mutates ``text``."""
    findings: List[Dict[str, str]] = []
    for rule in rules.get("rules", []):
        applies = _as_list(rule.get("applies_to")) or ["visible_text"]
        if surface not in [item.lower() for item in applies]:
            continue
        kind = rule.get("kind")
        rid = str(rule.get("id"))
        lower = _norm(text)

        def add(detail: str) -> None:
            findings.append({"rule_id": rid, "kind": str(kind),
                             "surface": surface, "detail": detail,
                             "severity": str(rule.get("severity") or "fail")})

        if kind == "banned_phrase":
            for value in _as_list(rule.get("values") or rule.get("value")):
                if value and value.lower() in lower:
                    add(f"banned phrase {value!r} present")
        elif kind == "banned_punctuation":
            for value in _as_list(rule.get("values") or rule.get("value")):
                if value and value in text:
                    add(f"banned punctuation {PUNCTUATION_NAMES.get(value, value)!r} present")
        elif kind == "required_content":
            for value in _as_list(rule.get("values") or rule.get("value")):
                if value and value.lower() not in lower:
                    add(f"required content {value!r} is absent")
        elif kind == "approved_price":
            approved = {item.replace(" ", "").lower()
                        for item in _as_list(rule.get("values") or rule.get("value"))}
            for token in _PRICE_RE.findall(text):
                if token.replace(" ", "").lower() not in approved:
                    add(f"unapproved price {token!r}")
        elif kind == "brand_name":
            canonical = rule.get("value") or rule.get("values")
            canonical = canonical[0] if isinstance(canonical, list) and canonical else canonical
            if isinstance(canonical, str) and canonical.strip() \
                    and canonical.lower() not in lower:
                add(f"canonical business name {canonical!r} is absent")
            for forbidden in _as_list(rule.get("forbidden")):
                if forbidden and forbidden.lower() in lower:
                    add(f"forbidden business name/alias {forbidden!r} present")
        elif kind in ("truthful_scarcity", "truthful_proof"):
            allowed = {value.lower() for value in _as_list(rule.get("allowed"))}
            for claim in _as_list(rule.get("values") or rule.get("value")):
                if claim and claim.lower() in lower and claim.lower() not in allowed:
                    add(f"unapproved {kind.replace('_', ' ')} claim {claim!r}")
        elif kind == "presentation":
            for detail in _presentation_fails(text, rule):
                add(detail)
    return findings


def _json_texts(value: Any, *, key: str = "") -> Iterable[str]:
    """Yield client-facing strings from a generated report, never hashes/URLs."""
    if isinstance(value, dict):
        for child_key, child in value.items():
            name = str(child_key)
            if name.lower() in _NON_TEXT_KEYS:
                continue
            yield from _json_texts(child, key=name)
    elif isinstance(value, list):
        for item in value:
            yield from _json_texts(item, key=key)
    elif isinstance(value, str):
        if key.lower() in _REPORT_KEYS or not key:
            yield value


def check_report(text: str, rules: Dict[str, Any]) -> List[Dict[str, str]]:
    """Presentation rules for a generated client report."""
    return rule_fails(text, rules, surface="reports")


def check_response_template(text: str, rules: Dict[str, Any]) -> List[Dict[str, str]]:
    """Presentation rules for an outbound response template."""
    return rule_fails(text, rules, surface="response_templates")


def sweep_tree(root: Any, rules: Dict[str, Any], *, max_files: int = 5000,
               exclude: Iterable[Any] = ()) -> Dict[str, Any]:
    """Recursively sweep the declared client-facing output tree.

    Returns a report, never a mutation. A missing root or an unusable rule
    document fails closed (``ok: False``). ``exclude`` names files (the rule
    document itself, for example) that are not client-facing output.
    """
    excluded = {Path(item).resolve() for item in exclude}
    report: Dict[str, Any] = {
        "ok": False, "root": str(root), "files_checked": 0, "files_skipped": 0,
        "findings": [], "reasons": [], "chat_enforcement": chat_enforcement(),
    }
    try:
        rules = load_client_rules(rules)
    except ClientRulesError as exc:
        report["reasons"].append(str(exc))
        return report
    base = Path(root)
    if not base.is_dir():
        report["reasons"].append(f"declared output tree does not exist: {base}")
        return report
    checked = 0
    for path in sorted(base.rglob("*")):
        if checked >= max_files:
            report["reasons"].append(f"file budget {max_files} exhausted; sweep incomplete")
            break
        if path.is_symlink() or not path.is_file():
            continue
        if excluded and path.resolve() in excluded:
            report["files_skipped"] += 1
            continue
        if any(part in _SKIP_DIRS for part in path.relative_to(base).parts[:-1]):
            report["files_skipped"] += 1
            continue
        suffix = path.suffix.lower()
        if suffix not in _VISIBLE_EXTENSIONS:
            report["files_skipped"] += 1
            continue
        try:
            if path.stat().st_size > 5_000_000:
                report["files_skipped"] += 1
                continue
            raw = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            report["files_skipped"] += 1
            continue
        checked += 1
        surface = "visible_text"
        texts: List[str] = []
        if suffix == ".json":
            try:
                texts = list(_json_texts(json.loads(raw)))
            except ValueError:
                texts = [raw]
            surface = "reports"
        else:
            texts = [visible_text(raw, file_name=path.name)]
        for text in texts:
            for finding in rule_fails(text, rules, surface=surface):
                finding["file"] = str(path.relative_to(base))
                report["findings"].append(finding)
    report["files_checked"] = checked
    report["ok"] = not report["findings"] and not report["reasons"]
    return report


def _selftest() -> int:
    """Runnable check: client-scoped rules, recursive sweep, exclusions."""
    import tempfile
    fails: List[str] = []

    try:
        load_client_rules({"schema": SCHEMA, "rules": [
            {"id": "r1", "kind": "banned_phrase", "value": "x"}]})
        fails.append("unscoped rules were accepted (global default leak)")
    except ClientRulesError:
        pass

    rules = load_client_rules({
        "schema": SCHEMA, "client_id": "leanne-example",
        "rules": [
            {"id": "p1", "kind": "banned_phrase", "values": ["world-class"],
             "applies_to": ["visible_text", "reports"]},
            {"id": "p2", "kind": "banned_punctuation", "values": ["—", "!"]},
            {"id": "p3", "kind": "required_content", "values": ["Leanne's Bakery"]},
            {"id": "p4", "kind": "approved_price", "values": ["$97"]},
            {"id": "p5", "kind": "truthful_proof", "values": ["guaranteed"]},
            {"id": "t1", "kind": "presentation", "no_exclamation": True,
             "require_business_name": "Leanne's Bakery",
             "applies_to": ["reports", "response_templates"]},
        ]})
    bad = ("Leanne's Bakery is world-class! Only $47, guaranteed. "
           "See https://example.test/world-class and sha256:" + "a" * 64)
    found = rule_fails(visible_text(bad, file_name="x.html"), rules)
    kinds = {f["rule_id"] for f in found}
    for expected in ("p1", "p2", "p4", "p5"):
        if expected not in kinds:
            fails.append(f"rule {expected} did not fire; got {sorted(kinds)}")
    if any(f["rule_id"] == "p3" for f in found):
        fails.append("required content fired despite the business name being present")

    # Exclusions: code/URL/hash/legal quote text is never treated as prose.
    excluded = ('<p>Leanne\'s Bakery</p><code>world-class!</code>'
                '<script>world-class!</script>'
                '<blockquote class="legal">world-class!</blockquote>')
    if rule_fails(visible_text(excluded, file_name="p.html"), rules):
        fails.append("code/script/legal-quote text leaked into the visible sweep")
    md = "Leanne's Bakery\n\n```\nworld-class!\n```\n\n> world-class!\n"
    if rule_fails(visible_text(md, file_name="p.md"), rules):
        fails.append("fenced code or a quoted line leaked into the markdown sweep")

    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        (base / "nested" / "deep").mkdir(parents=True)
        (base / "nested" / "deep" / "new.html").write_text(
            "<p>Leanne's Bakery offers a world-class result</p>", encoding="utf-8")
        (base / "report.json").write_text(json.dumps(
            {"headline": "Leanne's Bakery!", "sha256": "b" * 64,
             "url": "https://example.test/world-class"}), encoding="utf-8")
        report = sweep_tree(base, rules)
        files = {f["file"] for f in report["findings"]}
        if "nested/deep/new.html" not in files:
            fails.append(f"recursive sweep missed a new nested file: {files}")
        if not any(f["file"] == "report.json" and f["rule_id"] == "t1"
                   for f in report["findings"]):
            fails.append("generated report presentation rule did not fire")
        if any("world-class" in f.get("detail", "") and f["file"] == "report.json"
               for f in report["findings"] if f["rule_id"] == "p1"):
            fails.append("a URL value in JSON was mistaken for visible prose")
    chat = chat_enforcement()
    if "not_mechanically_enforceable" not in chat["chat"]:
        fails.append("chat limitation is not stated")

    if fails:
        print("client_rules selftest -> FAIL")
        for item in fails:
            print("  -", item)
        return 1
    print("client_rules selftest -> PASS (client-scoped, recursive, exclusions, report rules)")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(_selftest() if "--selftest" in sys.argv else _selftest())
