"""PersonaService context — explicit client-scoped input (PRES-053).

Replaces every implicit discovery seam (operator SOUL.md / USER.md, global
company-config, global Command Center DB, monorepo path search) with one
explicit, hashable, serializable dataclass. A PersonaService call carries
everything the resolution needs; nothing is read from the operator box.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class PersonaContext:
    """All inputs persona resolution may use. No live-path discovery."""

    company_id: str
    presentation_id: str
    run_id: str = ""
    audience: str = ""
    topic: str = ""
    offer: str = ""
    role: str = ""          # department execution role, e.g. slide-copywriter
    phase: str = ""         # pipeline phase id, e.g. P4-COPY
    context_revision: str = "1"
    audience_override: str = ""   # approved, operator-visible audience answer
    conversion_goal: str = ""
    goal_source: str = ""
    # Explicit per-client company config (ICP descriptors, default/
    # governance persona overrides). NEVER read from a global file.
    company_config: Dict[str, Any] = field(default_factory=dict)
    # Approved user preferences (voice picks, locked personas). NEVER
    # operator USER.md / SOUL.md.
    user_preferences: Dict[str, Any] = field(default_factory=dict)
    # Client-named voice: honored verbatim (client sovereignty), never judged.
    client_persona_id: str = ""
    client_persona_source: str = ""
    # Declared task parts (U115 scope_hint list). NEVER invented here.
    parts: tuple = ()
    # Deterministic hermetic mode for tests: heuristic scoring, no LLM,
    # no subprocess, no record writes.
    hermetic: bool = False

    def task_text(self) -> str:
        bits = [
            f"Presentation phase '{self.phase}'" if self.phase else "Presentation task",
            f"role {self.role}" if self.role else "",
            f"topic {self.topic}" if self.topic else "",
            f"audience {self.audience}" if self.audience else "",
            f"offer {self.offer}" if self.offer else "",
        ]
        return ". ".join(b for b in bits if b).strip() + "."

    def canonical(self) -> Dict[str, Any]:
        """Stable JSON-able form used for hashing and cache keys."""
        d = asdict(self)
        d["parts"] = list(self.parts)
        return d

    def context_hash(self) -> str:
        """Immutable context hash — cache key half 1 (who/what this is for)."""
        raw = json.dumps(self.canonical(), sort_keys=True, separators=(",", ":"),
                         default=str)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def content_hash(payload: Dict[str, Any]) -> str:
    """Cache key half 2 (what the packaged content was when resolved)."""
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"),
                     default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def scopes_for_context(ctx: PersonaContext) -> Dict[str, str]:
    """Storage scoping — company first, then presentation/run."""
    return {
        "company_id": ctx.company_id,
        "presentation_id": ctx.presentation_id,
        "run_id": ctx.run_id,
        "context_hash": ctx.context_hash(),
    }
