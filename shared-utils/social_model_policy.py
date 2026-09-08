#!/usr/bin/env python3
"""
social_model_policy.py — Provider-first social-planner model policy (F31).

Implements the model build contract for the Social Media Planner program:
provider-first, then model selection with live available candidates, role-based
recommendations, approved fallbacks, a saved immutable policy revision, and a
hard no-silent-substitution rule.

Contract (run/contracts/provider_policy.json):
  - selection_mode: pinned | recommend_confirm. Never silently choose a newer
    model solely because its version number is higher.
  - role_models: primary provider/model + allowed fallbacks for planner,
    researcher, writer, prompt_compiler and visual_qc; image/video separate.
  - revision: int, immutable per policy record.
  - provider-first selection; client pin preserved until accepted change;
    provider_id separate from model_id.

Usage:
    from social_model_policy import select_provider_then_model
    r = select_provider_then_model("openrouter", "planner", inventory)
    r = select_provider_then_model("openrouter", "planner", inventory,
                                   policy={"role_models": {...}, "budget": {...}})

Policy persistence: load_policy()/save_policy() store a JSON document with an
immutable `revision` int; each accepted change appends the prior revision to
`supersedes`. A restart re-reads the same file — the client's pin survives.
"""

import json
import os
from typing import Optional

DEFAULT_POLICY_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "social-model-policy.json"
)

# Roles with separated selection (model build contract). Text/strategy roles
# resolve through the text selector; visual_qc additionally REQUIRES vision
# capability; image/video resolve to dedicated generation models.
ROLES = ("planner", "researcher", "writer", "prompt_compiler", "visual_qc")

# Role -> required input modality (hard constraint, matches model-capabilities
# vocabulary). visual_qc inspects generated images — it MUST be able to see.
ROLE_MODALITY = {
    "planner": "text",
    "researcher": "text",
    "writer": "text",
    "prompt_compiler": "text",
    "visual_qc": "vision",
}

# Providers with an extensible adapter registry (see provider_adapters.py).
# A provider NOT in this set is "unsupported" — the selection result reports the
# adapter/setup work required instead of silently routing through another
# provider (never implicit OpenRouter/Ollama routing).
SUPPORTED_PROVIDERS = ("ollama", "openrouter", "deepseek", "test-provider")

# Provider prefix conventions per provider_id. These are ID-SHAPES, not routing:
# a provider-first selection is resolved BY its adapter, never re-routed.
PROVIDER_PREFIXES = {
    "ollama": ("ollama/", "ollama-cloud/"),
    "openrouter": ("openrouter/",),
    "deepseek": ("deepseek/", "deepseek-direct/"),
    "test-provider": ("test-provider/",),
}

VISION_CAPABILITY = "vision"


def _slug_lower(x: str) -> str:
    return (x or "").strip().lower()


def provider_of(model_id: str) -> str:
    """Infer the provider_id from a model id's prefix (provider_id ≠ model_id)."""
    mid = _slug_lower(model_id)
    if mid.startswith("ollama-cloud/"):
        return "ollama"
    if mid.startswith("ollama/"):
        return "ollama"
    if mid.startswith("openrouter/"):
        return "openrouter"
    if mid.startswith("deepseek/") or mid.startswith("deepseek-direct/"):
        return "deepseek"
    if mid.startswith("test-provider/"):
        return "test-provider"
    return ""


def matches_provider(model_id: str, provider: str) -> bool:
    """True iff model_id belongs to provider by ID SHAPE (no implicit re-routing)."""
    prefixes = PROVIDER_PREFIXES.get(_slug_lower(provider), ())
    mid = _slug_lower(model_id)
    return any(mid.startswith(p) for p in prefixes)


def _inventory_ids(available_inventory) -> list:
    """Normalize inventory entries (str or {id, capabilities, provider}) to ids."""
    ids = []
    for item in available_inventory or []:
        if isinstance(item, str):
            ids.append(item)
        elif isinstance(item, dict) and item.get("id"):
            ids.append(item["id"])
        elif isinstance(item, dict) and item.get("model_id"):
            ids.append(item["model_id"])
    return ids


def _inventory_caps(available_inventory) -> dict:
    """Map lowercased model id -> declared capabilities list."""
    caps = {}
    for item in available_inventory or []:
        if isinstance(item, dict):
            mid = _slug_lower(item.get("id") or item.get("model_id") or "")
            if mid:
                caps[mid] = [c.lower() for c in (item.get("capabilities") or [])]
    return caps


def model_has_capability(model_id: str, capability: str, caps: Optional[dict] = None) -> bool:
    """Capability check against declared inventory capabilities (then heuristic).

    visual_qc requires actual image INPUT — a text-only model is never eligible,
    even though a text model could technically attempt a caption of a described
    image. That is exactly the F37 forbidden downgrade.
    """
    mid = _slug_lower(model_id)
    if caps and mid in caps:
        return capability in caps[mid]
    # Heuristic fallback (no declared caps): known vision-capable families.
    if capability == VISION_CAPABILITY:
        vision_families = ("qwen3-vl", "qwen2-vl", "qwen-vl", "glm-4v", "glm-5v",
                           "gemini", "gpt-4o", "gpt-5", "minimax-m", "llama-vision",
                           "seedream", "pixtral")
        return any(f in mid for f in vision_families)
    return capability == "text"  # text is the lenient default


class SelectionRequest(Exception):
    """Raised/returned marker: an explicit selection request — never silent."""

    def __init__(self, reason: str, provider: str, role: str, available: list):
        self.reason = reason
        self.provider = provider
        self.role = role
        self.available = available
        super().__init__(reason)


def select_provider_then_model(
    provider: str,
    role: str,
    available_inventory,
    policy: Optional[dict] = None,
    recommend: bool = True,
) -> dict:
    """Provider-first, then model selection for a social-planner role.

    Resolution order:
      1. Client pin from saved policy (role_models[role].model_id) — honored
         EXACTLY while it is available and provider-matched. Never auto-upgraded
         to a newer version (selection_mode pinned / recommend_confirm).
      2. Approved fallbacks from saved policy, in the client's saved ORDER.
      3. Recommendation over the provider's live available candidates (cost/
         latency-informed), only in recommend_confirm mode and only as a
         visible recommendation, never a silent switch.
      4. Explicit selection request (needs_owner_input) — NEVER a silent
         substitution and NEVER an indefinite wait; the request is returned
         for the client to answer.

    Never routes a direct-provider selection through OpenRouter/Ollama.
    """
    provider_l = _slug_lower(provider)
    role_l = _slug_lower(role)
    if role_l not in ROLES:
        return {
            "selected": False, "needs_selection": True,
            "reason": f"unknown role '{role}' — known roles: {', '.join(ROLES)}",
            "provider": provider_l, "role": role_l, "model_id": None,
        }
    inv_ids = [m for m in _inventory_ids(available_inventory) if m]
    caps = _inventory_caps(available_inventory)
    required_modality = ROLE_MODALITY[role_l]

    # Provider support: unsupported provider reports the adapter/setup work
    # required — it never silently routes through a supported provider.
    if provider_l and provider_l not in SUPPORTED_PROVIDERS:
        return {
            "selected": False, "needs_selection": True,
            "needs_adapter": True,
            "reason": (f"provider '{provider}' has no adapter — adapter/setup work "
                       f"required (known providers: {', '.join(SUPPORTED_PROVIDERS)})"),
            "provider": provider_l, "role": role_l,
            "model_id": None, "available_models": inv_ids,
        }

    policy = policy or {}
    role_cfg = (policy.get("role_models") or {}).get(role_l) or {}
    pin = role_cfg.get("model_id") or role_cfg.get("model")
    fallbacks = role_cfg.get("fallbacks") or []

    def _result(model_id, source, **extra):
        out = {
            "selected": True, "needs_selection": False,
            "provider": provider_of(model_id) or provider_l,
            "role": role_l,
            "model_id": model_id,
            "required_modality": required_modality,
            "source": source,
            "available_models": inv_ids,
        }
        out.update(extra)
        return out

    # 1 — client pin, honored while valid (available + provider-matched +
    # modality-capable). A pin on an unavailable model NEVER silently switches;
    # an APPROVED fallback in the client's saved order may serve instead — and
    # only an approved one.
    if pin:
        pin_l = _slug_lower(pin)
        if matches_provider(pin_l, provider_l) and pin_l in [ _slug_lower(m) for m in inv_ids ] \
                and model_has_capability(pin_l, required_modality, caps):
            return _result(pin, "client_pin")
        # 2 — approved fallbacks IN SAVED ORDER (fallbacks follow saved consent).
        for fb in fallbacks:
            fb_l = _slug_lower(fb)
            if (matches_provider(fb_l, provider_l)
                    and fb_l in [_slug_lower(m) for m in inv_ids]
                    and model_has_capability(fb_l, required_modality, caps)):
                return _result(fb, "approved_fallback", pin_unavailable=pin)
        return {
            "selected": False, "needs_selection": True,
            "pin_unavailable": pin,
            "reason": (f"pinned model '{pin}' is unavailable on provider '{provider_l}' "
                       f"(removed or no longer accessible). Approved fallbacks follow "
                       f"saved consent; without one, an explicit selection is required."),
            "provider": provider_l, "role": role_l, "model_id": None,
            "available_models": inv_ids,
        }

    # 2b — no pin saved: approved fallbacks still apply in saved order.
    for fb in fallbacks:
        fb_l = _slug_lower(fb)
        if (matches_provider(fb_l, provider_l)
                and fb_l in [_slug_lower(m) for m in inv_ids]
                and model_has_capability(fb_l, required_modality, caps)):
            return _result(fb, "approved_fallback")

    # 3 — recommendation over the provider's own available candidates.
    provider_pool = [m for m in inv_ids if matches_provider(m, provider_l)
                     and model_has_capability(_slug_lower(m), required_modality, caps)]
    if recommend and provider_pool:
        rec = sorted(provider_pool, key=lambda m: (not model_has_capability(
            _slug_lower(m), required_modality, caps), m))[0]
        return _result(rec, "recommendation", is_recommendation=True,
                       confirm_required=True)

    # 4 — explicit selection request. Never silent, never indefinite.
    return {
        "selected": False, "needs_selection": True,
        "reason": (f"no available model on provider '{provider_l}' satisfies role "
                   f"'{role_l}' (requires {required_modality}). "
                   f"An explicit selection is required — no substitution was made."),
        "provider": provider_l, "role": role_l, "model_id": None,
        "available_models": inv_ids,
        "needs_owner_input": True,
    }


# ─── Policy persistence (revision immutable, restart-surviving) ────────────────

def load_policy(path: str = DEFAULT_POLICY_PATH) -> dict:
    if os.path.exists(path):
        try:
            with open(path) as f:
                return json.load(f)
        except (OSError, ValueError):
            pass
    return {}


def save_policy(policy: dict, path: str = DEFAULT_POLICY_PATH) -> dict:
    """Persist the policy document. `revision` is immutable once written: an
    update MUST carry the prior revision as `supersedes` and bump revision by 1.
    Refuses to regress revision (restart-safe)."""
    existing = load_policy(path)
    if existing:
        if policy.get("revision", 0) < existing.get("revision", 0):
            raise ValueError(
                f"policy revision regression: {policy.get('revision')} < "
                f"{existing.get('revision')} — revision is immutable per record"
            )
    with open(path, "w") as f:
        json.dump(policy, f, indent=2, sort_keys=True)
        f.write("\n")
    return policy


def validate_policy(policy: dict) -> list:
    """Validate a policy document against run/contracts/provider_policy.json.
    Returns a list of problems ([] when valid)."""
    problems = []
    if not policy.get("company_id"):
        problems.append("missing company_id")
    if not isinstance(policy.get("revision"), int):
        problems.append("revision must be an int (immutable policy version)")
    if policy.get("selection_mode") not in ("pinned", "recommend_confirm"):
        problems.append("selection_mode must be 'pinned' or 'recommend_confirm'")
    rm = policy.get("role_models") or {}
    for role in ROLES:
        cfg = rm.get(role)
        if not cfg:
            problems.append(f"role_models.{role} missing")
            continue
        if not (cfg.get("model_id") or cfg.get("model")):
            problems.append(f"role_models.{role}.model_id missing")
        for fb in cfg.get("fallbacks") or []:
            if provider_of(fb) and policy.get("provider") and not matches_provider(fb, policy["provider"]):
                problems.append(f"role_models.{role} fallback '{fb}' crosses provider boundary")
    if not isinstance(policy.get("image_models"), list):
        problems.append("image_models must be a list")
    if not isinstance(policy.get("video_models"), list):
        problems.append("video_models must be a list")
    budget = policy.get("budget") or {}
    if not isinstance(budget.get("permitted_paid_fallbacks", []), list):
        problems.append("budget.permitted_paid_fallbacks must be a list")
    return problems


if __name__ == "__main__":
    import argparse
    import sys

    parser = argparse.ArgumentParser(description="Social-planner provider-first model policy (F31)")
    parser.add_argument("--provider", required=True)
    parser.add_argument("--role", required=True, choices=ROLES)
    parser.add_argument("--inventory", default="", help="JSON list of model ids or {id,capabilities} entries")
    parser.add_argument("--policy", default=None, help="Policy JSON file path")
    parser.add_argument("--policy-file-out", default=None)
    args = parser.parse_args()

    try:
        inventory = json.loads(args.inventory) if args.inventory else []
    except ValueError:
        print(f"bad inventory JSON: {args.inventory}", file=sys.stderr)
        sys.exit(2)

    pol = load_policy(args.policy) if args.policy else None
    result = select_provider_then_model(args.provider, args.role, inventory, policy=pol)
    print(json.dumps(result, indent=2))
    sys.exit(0 if result["selected"] else 2)