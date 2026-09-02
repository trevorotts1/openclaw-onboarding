"""presentation_job/oc_paths.py -- FIX 68: platform-aware openclaw paths.

THE ONE-SENTENCE PROBLEM THIS FIXES: every engine module hard-coded
``Path.home() / ".openclaw" / ...``. On the Docker VPS the openclaw root is
``/data/.openclaw`` (HOME is often /tmp or the node user's home), so with
``HOME=/tmp/x`` the engine looked for secrets in /tmp/x/.openclaw/ -- found
nothing -- and failed closed on a box whose credentials were present the
whole time.

FIX 68 (MASTER-ASSESSMENT-AND-FIX-PLAN.md, SOURCE [R11 §G4]):

  * One module owns openclaw root resolution: ``root()``, ``workspace()``,
    ``skills()``, ``secrets_env_candidates()``, ``state_dir()``.
  * Resolution order: the ``OPENCLAW_PLATFORM`` env var first (explicit
    operator override: "mac" | "vps"), then filesystem detection (does
    ``/data/.openclaw`` exist? -> vps layout), then the Mac default
    (``~/.openclaw``).
  * ``secrets_env_candidates()`` returns the ordered secrets-file candidate
    list for the RESOLVED platform first -- so on the VPS
    ``/data/.openclaw/secrets/.env`` is FIRST, on a Mac ``~/.openclaw/...``
    is -- and the other platform's standard locations follow as fallbacks
    (a file that exists is read; a path that does not is skipped, exactly
    the posture every caller already had).

NO SECRET VALUE ever passes through this module -- only PATHS. Callers keep
their own parsing/parse-order semantics; they only stop hard-coding the
platform prefix.

Rollback: ``PRESENTATION_OC_PATHS=0`` makes every helper return the legacy
Mac path (``~/.openclaw/...``) unchanged -- the pre-FIX-68 behavior,
explicitly documented, never a silent no-op.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import List

FLAG_ENV = "PRESENTATION_OC_PATHS"       # =0 -> legacy Mac-only behavior
PLATFORM_ENV = "OPENCLAW_PLATFORM"       # "mac" | "vps"
VPS_ROOT = Path("/data/.openclaw")

#: The per-platform env-store inventory, resolved HOME-relative at call time.
#: Mac order mirrors the stores the engine already read (secrets/.env, then
#: secrets/secrets.env, then the flat .env, then the workspace store); VPS
#: mirrors the /data/.openclaw layout the docker gateway writes.
_MAC_SECRETS = (
    "~/.openclaw/secrets/.env",
    "~/.openclaw/secrets/secrets.env",
    "~/.openclaw/.env",
    "~/.openclaw/workspace/.env",
    "~/clawd/secrets/.env",
)
_VPS_SECRETS = (
    "/data/.openclaw/secrets/.env",
    "/data/.openclaw/secrets/secrets.env",
    "/data/.openclaw/.env",
)


def _platform() -> str:
    """Resolve the platform: explicit OPENCLAW_PLATFORM, else filesystem
    detection (a /data/.openclaw root means the docker VPS layout), else the
    Mac default. Always one of "mac" / "vps" -- unknown values fall through
    to detection rather than guessing."""
    raw = (os.environ.get(PLATFORM_ENV) or "").strip().lower()
    if raw in ("mac", "vps"):
        return raw
    if VPS_ROOT.is_dir():
        return "vps"
    return "mac"


def _legacy() -> bool:
    """True iff the operator disabled FIX 68 via PRESENTATION_OC_PATHS=0 --
    the documented rollback: every helper answers the pre-fix Mac path."""
    return (os.environ.get(FLAG_ENV) or "").strip() == "0"


def root() -> Path:
    """The openclaw root for the resolved platform: /data/.openclaw on the
    VPS, ~/.openclaw on a Mac."""
    if _legacy() or _platform() == "mac":
        return Path.home() / ".openclaw"
    return VPS_ROOT


def workspace() -> Path:
    """The openclaw workspace root (departments/... live under it)."""
    return root() / "workspace"


def skills() -> Path:
    """The canonical skills dir ($OC_SKILLS_DIR override still wins for
    callers that already honor it -- this is the DEFAULT, not a gate)."""
    override = (os.environ.get("OC_SKILLS_DIR") or "").strip()
    if override:
        return Path(override).expanduser()
    return root() / "skills"


def state_dir() -> Path:
    """The presentations state dir -- secrets-ADJACENT (sibling of secrets/,
    the same ownership boundary resource_profile.py documents)."""
    return root() / "state" / "presentation"


def secrets_env_candidates() -> List[Path]:
    """Ordered secrets-file candidates: an explicit $OPENCLAW_SECRETS
    pointer FIRST when set (the HIGH-3 posture kie_generate.py ships --
    it is unset in every standard environment, so the platform ordering
    the FIX 68 proof checks is untouched), then the resolved platform's
    standard stores (the proof contract: on the docker VPS
    ``/data/.openclaw/secrets/.env`` is first, on a Mac the ~/.openclaw
    stores are), then the OTHER platform's locations as cross-platform
    fallbacks. Paths are expanded at call time; existence is NOT checked
    here (callers already skip missing files, and the proof contract
    requires a stable, checkable ORDER)."""
    candidates: List[Path] = []
    override = (os.environ.get("OPENCLAW_SECRETS") or "").strip()
    if override:
        candidates.append(Path(override).expanduser())
    if _legacy():
        plat = "mac"
    else:
        plat = _platform()
    primary, secondary = (
        (_MAC_SECRETS, _VPS_SECRETS) if plat == "mac" else (_VPS_SECRETS, _MAC_SECRETS)
    )
    for spec in primary + secondary:
        candidates.append(Path(os.path.expanduser(spec)))
    return candidates
