"""shared-utils/skills — delivery-skill discovery, aliases, package integration.

Importable package marker (W10B package integration). Public surface:

    from skills.discovery_aliases import (
        canon_skill_id, discover_delivery_skills, resolve_skill,
        skill_package, default_roots, SkillRecord,
    )
"""

from .discovery_aliases import (  # noqa: F401
    ALIAS_MAP,
    CANONICAL_IDS,
    SkillRecord,
    canon_skill_id,
    default_roots,
    discover_delivery_skills,
    resolve_skill,
    skill_package,
)

__all__ = [
    "ALIAS_MAP",
    "CANONICAL_IDS",
    "SkillRecord",
    "canon_skill_id",
    "default_roots",
    "discover_delivery_skills",
    "resolve_skill",
    "skill_package",
]
