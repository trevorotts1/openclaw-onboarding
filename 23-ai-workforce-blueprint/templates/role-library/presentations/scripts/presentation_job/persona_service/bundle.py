"""Typed persona receipt + integrity + consumption verify (PRES-053)."""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

GUARDRAIL_MARK = "STYLE-INSPIRED, NEVER IMPERSONATION"


@dataclass
class PersonaReceipt:
    company_id: str
    presentation_id: str
    run_id: str
    phase: str
    role: str
    context_hash: str
    content_version: str
    execution_id: str
    voice_persona_id: str = ""
    topic_persona_id: str = ""
    governing_persona_id: str = ""
    scoring_method: str = ""
    scoring_detail: str = ""
    semantic_claimed: bool = False
    semantic_evidence: str = ""
    source_hashes: Dict[str, str] = field(default_factory=dict)
    per_part: List[dict] = field(default_factory=list)
    rationale: Dict[str, Any] = field(default_factory=dict)
    policy: Dict[str, Any] = field(default_factory=dict)
    blend_directive: str = ""
    no_persona_required: bool = False
    confirm_required: bool = False
    warnings: List[str] = field(default_factory=list)
    bundle: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)

    def receipt_hash(self) -> str:
        raw = json.dumps(self.to_dict(), sort_keys=True,
                         separators=(",", ":"), default=str)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def verify_bundle_integrity(receipt: PersonaReceipt) -> List[str]:
    """Fail-closed integrity problems. Empty = PASS."""
    problems: List[str] = []
    b = receipt.bundle or {}
    if receipt.no_persona_required:
        if not receipt.governing_persona_id:
            problems.append("mechanical task lacks governing persona pointer")
        return problems
    directive = receipt.blend_directive or b.get("blend_directive", "")
    if not directive:
        problems.append("missing blend_directive")
    elif GUARDRAIL_MARK not in directive:
        problems.append("blend_directive lacks mandatory guardrail clause")
    if not receipt.voice_persona_id and not (b.get("persona_id")):
        problems.append("no voice persona resolved")
    if not receipt.topic_persona_id:
        problems.append("no topic persona resolved")
    if receipt.semantic_claimed and not receipt.semantic_evidence:
        # Fake-semantic QC-fail: claimed semantic retrieval without evidence.
        problems.append("semantic success claimed without evidence "
                        "(funnel semantic count / method tag missing)")
    return problems


_VERIFY_STOP = frozenset(
    "that with from have this will your they them then than those these "
    "their there about into through during before after other which while "
    "also your voice their them then than these those their there about".split())

_RARE_TOKEN_RE = re.compile(r"[^a-z0-9]+")


def _norm_tokens(text: str) -> List[str]:
    toks = _RARE_TOKEN_RE.split(str(text or "").lower())
    return [t for t in toks if len(t) >= 6 and t not in _VERIFY_STOP]


def _distinctive_tokens(ref_text: str, sample_cap: int = 120) -> List[str]:
    """Rarest-first sample: long tokens first (length, then alpha). Long
    domain tokens (framework names, method terms) carry the signal; short
    glue words match everything and prove nothing."""
    uniq = sorted(set(_norm_tokens(ref_text)), key=lambda t: (-len(t), t))
    return uniq[:sample_cap]


def governance_excerpt(catalog: Any, persona_id: str,
                         max_chars: int = 1400) -> str:
    """Governance excerpt = the dispatch contract's Section-4(A-D) load
    target: the persona's Agent Governance Framework section resolved via
    the packaged section map (Template A -> its governance section,
    Template B -> Section 4), literal Section 4 when unmapped. Mirrors
    persona_for_job.section4_excerpt semantics over PACKAGED bytes."""
    import re as _re
    if catalog is None or not persona_id:
        return ""
    text = catalog.blueprint_text(persona_id)
    if not text:
        return ""
    lines = text.splitlines()
    target = catalog.governance_section_number(persona_id)
    excerpt = _extract_section(lines, target) if target else ""
    if not excerpt:
        excerpt = _extract_section(lines, 4)
    if len(excerpt) > max_chars:
        excerpt = excerpt[:max_chars].rstrip() + " …"
    return excerpt


def _extract_section(lines, section_num: int) -> str:
    head = re.compile(r"^##\s+Section\s+(\d+)\b", re.IGNORECASE)
    start = None
    for i, ln in enumerate(lines):
        m = head.match(ln.strip())
        if m and m.group(1) == str(section_num):
            start = i
            break
    if start is None:
        return ""
    body = [lines[start]]
    for ln in lines[start + 1:]:
        if head.match(ln.strip()):
            break
        body.append(ln)
    return "\n".join(body).strip()


def required_texts_for_receipt(receipt: PersonaReceipt,
                               catalog: Any = None) -> Dict[str, str]:
    """Map slot -> required reference text that MUST be consumed downstream.

    Voice/topic/task texts are the GOVERNANCE excerpts (the exact bytes
    the dispatcher loads as section4_excerpt for the worker) from the
    PACKAGED blueprints — never whole 50KB blueprints, never live roots.
    """
    out: Dict[str, str] = {}
    if catalog is not None:
        if receipt.voice_persona_id:
            out["voice"] = governance_excerpt(catalog, receipt.voice_persona_id)
        if receipt.topic_persona_id and receipt.topic_persona_id != receipt.voice_persona_id:
            out["topic"] = governance_excerpt(catalog, receipt.topic_persona_id)
        for part in receipt.per_part:
            pid = part.get("persona_id")
            if pid and pid not in (receipt.voice_persona_id, receipt.topic_persona_id):
                key = f"task-{part.get('seq', '?')}-{pid}"
                if key not in out:
                    out[key] = governance_excerpt(catalog, pid)
    # The directive itself is always required text.
    if receipt.blend_directive:
        out["blend_directive"] = receipt.blend_directive
    return out


def verify_consumption(receipt: PersonaReceipt, rendered_text: str,
                       catalog: Any = None,
                       min_token_hit_ratio: float = 0.3) -> List[str]:
    """Prove downstream copy actually consumed the bundle.

    For each required reference text: normalize to content tokens and
    require at least min_token_hit_ratio of its distinctive tokens to
    appear in the rendered text. Omitted required text = QC FAIL.
    Empty reference text (missing blueprint) is itself a problem.
    """
    problems: List[str] = []
    problems.extend(verify_bundle_integrity(receipt))
    required = required_texts_for_receipt(receipt, catalog)
    if catalog is not None and not required:
        problems.append("no required reference texts resolvable from package")
        return problems
    rendered = set(_norm_tokens(rendered_text))
    if not rendered:
        problems.append("rendered text empty — nothing consumed the bundle")
        return problems
    for slot, ref_text in required.items():
        if slot == "blend_directive":
            continue  # directive presence checked via voice/topic substance
        if not ref_text or not ref_text.strip():
            problems.append(f"required text for slot '{slot}' empty "
                            f"(blueprint missing from package?)")
            continue
        sample = _distinctive_tokens(ref_text)
        if not sample:
            problems.append(f"required text for slot '{slot}' has no tokens")
            continue
        hits = sum(1 for t in sample if t in rendered)
        ratio = hits / max(1, len(sample))
        if ratio < min_token_hit_ratio:
            problems.append(
                f"slot '{slot}': only {hits}/{len(sample)} distinctive "
                f"reference tokens ({ratio:.2f} < {min_token_hit_ratio:.2f}) "
                f"appear in rendered text — bundle not consumed")
    return problems
