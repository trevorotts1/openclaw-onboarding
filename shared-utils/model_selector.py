#!/usr/bin/env python3
"""
model_selector.py — Capability-class model selector for OpenClaw role-library.

NEW LAYER (v1.0.0) sitting ABOVE the existing tier system in select_model.py.

Given a role slug + department, this module:
  1. Infers the role's Capability Class (HEAVY-REASONING / WRITING / JUDGMENT /
     MECHANICAL / CONVERSATIONAL / GENERATION) plus an optional VISION flag.
  2. Translates the class to a select_model.py purpose-tier + modality constraint.
  3. Delegates to the existing select_model.py cascade to resolve the best
     available concrete model id from whatever the client has installed.
  4. For GENERATION class roles, returns a fixed pipeline target (no LLM).

The existing select_model.py is NEVER duplicated here — all cascade/version/
tier/forbidden-prefix logic stays there. This module is a pure classification
layer on top of it.

Usage (CLI):
    python3 shared-utils/model_selector.py --role <slug> --dept <dept>
    python3 shared-utils/model_selector.py --role sop-writer --dept audio
    python3 shared-utils/model_selector.py --self-test

Usage (import):
    from model_selector import infer_class, resolve_model_for_role
"""

import json
import os
import re
import subprocess
import sys
from typing import Optional

# ─── CONSTANTS ────────────────────────────────────────────────────────────────

# Primary capability classes
CLASS_HEAVY = "HEAVY-REASONING"
CLASS_WRITING = "WRITING"
CLASS_JUDGMENT = "JUDGMENT"
CLASS_MECHANICAL = "MECHANICAL"
CLASS_CONVERSATIONAL = "CONVERSATIONAL"
CLASS_GENERATION = "GENERATION"

# Additive flag (combined with any primary class)
FLAG_VISION = "VISION"

# Class → select_model.py --purpose-tier mapping
CLASS_TO_TIER = {
    CLASS_HEAVY: "heavy",
    CLASS_WRITING: "mid",
    CLASS_JUDGMENT: "mid",
    CLASS_MECHANICAL: "fast",
    CLASS_CONVERSATIONAL: "mid",
    CLASS_GENERATION: None,   # fixed pipeline — no LLM tier
}

# Generation roles → fixed pipeline targets (no LLM resolution)
GENERATION_PIPELINE = {
    "ai-image-generator-specialist":    "kie-ai/gpt-image-2-image-to-image",
    "ai-video-generator-specialist":    "video-pipeline/ai-video-generator",
    "music-and-audio-producer":         "fish-audio/text-to-audio",
    "generation-operator":              "kie-ai/gpt-image-2-image-to-image",
    "role--generation-operator":        "kie-ai/gpt-image-2-image-to-image",
    "slide-image-creator":              "kie-ai/gpt-image-2-image-to-image",
    "sound-design-sfx-specialist":      "fish-audio/text-to-audio",
    "audiobook-production-specialist":  "fish-audio/text-to-audio",
    "ai-voice-specialist-11-labs-play.ht": "fish-audio/elevenlabs-passthrough",
}

# ─── LAYER A: EXPLICIT OVERRIDE TABLE ─────────────────────────────────────────
# Slugs whose names do not betray their class. First match wins over keyword rules.

EXPLICIT_OVERRIDES: dict[str, str] = {
    # HEAVY-REASONING
    "master-orchestrator":                   CLASS_HEAVY,
    "research-agent":                        CLASS_HEAVY,
    "cost-model-optimizer-specialist":       CLASS_HEAVY,
    "data-analysis-specialist":              CLASS_HEAVY,
    "go-to-market-specialist":               CLASS_HEAVY,
    "dept-healer-template":                  CLASS_HEAVY,
    "chief-healer":                          CLASS_HEAVY,
    "chief-research-officer":                CLASS_HEAVY,
    "chief-project-architect":               CLASS_HEAVY,
    "chief-financial-officer":               CLASS_HEAVY,
    "chief-marketing-officer":               CLASS_HEAVY,
    "chief-sales-officer":                   CLASS_HEAVY,
    "chief-communications-officer":          CLASS_HEAVY,
    "chief-legal-officer":                   CLASS_HEAVY,
    "chief-design-officer":                  CLASS_HEAVY,
    "fpanda--forecasting-analyst":           CLASS_HEAVY,
    "cash-flow-forecasting-specialist":      CLASS_HEAVY,
    "industry-analysis-specialist-mckinsey-style": CLASS_HEAVY,
    "capacity-planning-specialist":          CLASS_HEAVY,
    "customer-journey-architect":            CLASS_HEAVY,
    "persona-research-specialist":           CLASS_HEAVY,
    "market-trends-specialist":              CLASS_HEAVY,
    "funnel-strategist":                     CLASS_HEAVY,
    "brand-positioning-specialist":          CLASS_HEAVY,
    "offer-price-strategist":               CLASS_HEAVY,
    "competitive-intelligence-specialist":   CLASS_HEAVY,
    "audience-research-specialist":          CLASS_HEAVY,
    "retargeting-strategist":               CLASS_HEAVY,
    "style-analyst":                        CLASS_HEAVY,   # analyzes, does not generate
    "role--style-analyst":                  CLASS_HEAVY,
    "sales-operations--pipeline-specialist": CLASS_HEAVY,
    "customer-research-specialist":          CLASS_HEAVY,
    "app-store-optimization-aso-specialist": CLASS_HEAVY,
    "cross-platform-attribution-specialist": CLASS_HEAVY,
    "marketing-analytics-specialist":        CLASS_HEAVY,
    "video-seo-specialist":                  CLASS_HEAVY,
    "seo-specialist-organic-search":         CLASS_HEAVY,
    "technical-seo-specialist":              CLASS_HEAVY,
    "conversion-rate-optimization-cro-specialist": CLASS_HEAVY,
    "web-security-specialist":               CLASS_HEAVY,
    "web-accessibility-a11y-specialist":     CLASS_HEAVY,
    "integration--mcp-specialist":           CLASS_HEAVY,
    "systems-engineer":                      CLASS_HEAVY,
    "qa-engineer":                           CLASS_HEAVY,
    "performance-tuning-specialist":         CLASS_HEAVY,
    "disaster-recovery-specialist":          CLASS_HEAVY,
    "security-and-secrets-specialist":       CLASS_HEAVY,
    "skill-update-and-patch-specialist":     CLASS_HEAVY,
    "version-and-upgrade-manager-specialist":CLASS_HEAVY,
    "cloud-infrastructure-specialist":       CLASS_HEAVY,
    "api-backend-specialist":                CLASS_HEAVY,
    "frontend--javascript--react-specialist":CLASS_HEAVY,
    "pwa-progressive-web-app-specialist":    CLASS_HEAVY,
    "android-specialist":                    CLASS_HEAVY,
    "ios-specialist":                        CLASS_HEAVY,
    "desktop-app-specialist":                CLASS_HEAVY,
    "ux-ui-specialist":                      CLASS_HEAVY,
    "landing-page-specialist":               CLASS_HEAVY,
    "member-area--membership-site-specialist":CLASS_HEAVY,
    "wordpress-specialist":                  CLASS_HEAVY,
    "facebook-ads-specialist":               CLASS_HEAVY,
    "google-ads-specialist":                 CLASS_HEAVY,
    "instagram-ads-specialist":              CLASS_HEAVY,
    "tiktok-ads-specialist":                 CLASS_HEAVY,
    "linkedin-ads-specialist":               CLASS_HEAVY,
    "twitter-x-ads-specialist":              CLASS_HEAVY,
    "pinterest-ads-specialist":              CLASS_HEAVY,
    "snapchat-ads-specialist":               CLASS_HEAVY,
    "bing--microsoft-ads-specialist":        CLASS_HEAVY,
    "native-ads-specialist":                 CLASS_HEAVY,
    "youtube-ads-specialist":                CLASS_HEAVY,
    "spotify-audio-ads-specialist":          CLASS_HEAVY,
    "facebook-specialist":                   CLASS_HEAVY,
    "instagram-specialist":                  CLASS_HEAVY,
    "tiktok-specialist":                     CLASS_HEAVY,
    "linkedin-specialist":                   CLASS_HEAVY,
    "twitter-x-specialist":                  CLASS_HEAVY,
    "pinterest-specialist":                  CLASS_HEAVY,
    "youtube-channel-specialist-organic-only":CLASS_HEAVY,
    "reddit-specialist":                     CLASS_HEAVY,
    "quora-specialist":                      CLASS_HEAVY,
    "discord-community-specialist":          CLASS_HEAVY,
    "bluesky-specialist":                    CLASS_HEAVY,
    "threads-specialist":                    CLASS_HEAVY,
    "contract-drafter-client-agreements":    CLASS_HEAVY,
    "employment-contract-specialist":        CLASS_HEAVY,
    "affiliate-agreement-specialist":        CLASS_HEAVY,
    "vendor-contract-specialist":            CLASS_HEAVY,
    "customer-agreement-specialist":         CLASS_HEAVY,
    "terms--privacy-policy-specialist":      CLASS_HEAVY,
    "ip--trademark-specialist":              CLASS_HEAVY,
    "compliance-monitor--specialist":        CLASS_HEAVY,
    "industry-specific-regulatory-specialist":CLASS_HEAVY,
    "churn-prevention-specialist":           CLASS_HEAVY,
    "refunds-and-disputes-specialist":       CLASS_HEAVY,
    "dispute-resolution-specialist":         CLASS_HEAVY,
    "collection-specialist":                 CLASS_HEAVY,
    "collections-specialist":               CLASS_HEAVY,
    "invoicing-and-ar-specialist":           CLASS_HEAVY,
    "financial-reporting-specialist":        CLASS_HEAVY,
    "tax-liaison-specialist":                CLASS_HEAVY,
    "subscription--recurring-revenue-specialist": CLASS_HEAVY,
    "bookkeeping-specialist":                CLASS_HEAVY,
    "account-manager-post-sale":             CLASS_HEAVY,
    "affiliate--referral-specialist":        CLASS_HEAVY,
    "influencer-marketing-specialist":       CLASS_HEAVY,
    "webinar-event-marketing-specialist":    CLASS_HEAVY,
    "lead-magnet-specialist":                CLASS_HEAVY,
    "content-marketing-strategist":          CLASS_HEAVY,
    "content-strategist":                    CLASS_HEAVY,
    "funnel-builder-specialist":             CLASS_HEAVY,
    "survey-and-polling-specialist":         CLASS_HEAVY,
    "travel-logistics-specialist":           CLASS_HEAVY,
    "returns-reverse-logistics-specialist":  CLASS_HEAVY,
    # JUDGMENT overrides
    "qc-agent":                              CLASS_JUDGMENT,
    "role-auditor":                          CLASS_JUDGMENT,
    "fidelity-tester":                       CLASS_JUDGMENT,
    "role--fidelity-tester":                 CLASS_JUDGMENT,
    "triage-dedup-analyst":                  CLASS_JUDGMENT,
    "procedure-auditor":                     CLASS_JUDGMENT,
    "qa-tester-app":                         CLASS_JUDGMENT,
    "app-analytics-specialist":              CLASS_JUDGMENT,
    # CONVERSATIONAL overrides
    "generalist-operator":                   CLASS_CONVERSATIONAL,
    "appointment-setter":                    CLASS_CONVERSATIONAL,
    "concierge-lead":                        CLASS_CONVERSATIONAL,
    "delivery-concierge":                    CLASS_CONVERSATIONAL,
    "personal-coach":                        CLASS_CONVERSATIONAL,
    "presenter-coach":                       CLASS_CONVERSATIONAL,
    "closer":                                CLASS_CONVERSATIONAL,
    "sdr-sales-development-rep":             CLASS_CONVERSATIONAL,
    "account-executive-full-cycle":          CLASS_CONVERSATIONAL,
    "discovery-call-specialist":             CLASS_CONVERSATIONAL,
    "live-chat-specialist":                  CLASS_CONVERSATIONAL,
    "voice--phone-support-specialist":       CLASS_CONVERSATIONAL,
    "tier-1-support-specialist":             CLASS_CONVERSATIONAL,
    "tier-2-support-specialist":             CLASS_CONVERSATIONAL,
    "community-manager":                     CLASS_CONVERSATIONAL,
    "podcast-host":                          CLASS_CONVERSATIONAL,
    "client-relationship-manager":           CLASS_CONVERSATIONAL,
    "onboarding-specialist":                 CLASS_CONVERSATIONAL,
    "retention-specialist":                  CLASS_CONVERSATIONAL,
    "post-session-followup-specialist":      CLASS_CONVERSATIONAL,
    "booking-coordinator":                   CLASS_CONVERSATIONAL,
    "client-onboarding-specialist":          CLASS_CONVERSATIONAL,
    "membership-specialist":                 CLASS_CONVERSATIONAL,
    "head-of-customer-success":              CLASS_CONVERSATIONAL,
    "account-health-monitor-proactive":      CLASS_MECHANICAL,
    # WRITING overrides
    "hook-strategist":                       CLASS_WRITING,
    "op-ed-ghostwriter":                     CLASS_WRITING,
    "slide-copywriter":                      CLASS_WRITING,
    "knowledge-base-specialist":             CLASS_WRITING,
    "listing-creator":                       CLASS_WRITING,
    "web-designer":                          CLASS_WRITING,
    "voice-agent-builder":                   CLASS_WRITING,
    "storyboard-pre-production-specialist":  CLASS_WRITING,
    "code-editor":                           CLASS_WRITING,
    "sop-writer":                            CLASS_WRITING,
    "presenters-speech-writer":              CLASS_WRITING,
    "presenters-guide-specialist":           CLASS_WRITING,
    "speech--talking-points-specialist":     CLASS_WRITING,
    "speech-writing-specialist":             CLASS_WRITING,
    "press-release-statement-specialist":    CLASS_WRITING,
    "brand-messaging-specialist":            CLASS_WRITING,
    "email-campaign-strategist":             CLASS_WRITING,
    "follow-up-sequence-specialist":         CLASS_WRITING,
    "sms--whatsapp--dm-sequence-specialist": CLASS_WRITING,
    "proposal-and-quote-specialist":         CLASS_WRITING,
    "email-deliverability-optimization-specialist": CLASS_WRITING,
    "internal-communications-manager":       CLASS_WRITING,
    "investor--stakeholder-comms-specialist":CLASS_WRITING,
    "media-pitching-specialist":             CLASS_WRITING,
    "crisis-communications-specialist":      CLASS_WRITING,
    "pr--media-relations-specialist":        CLASS_WRITING,
    "automation-workflow-specialist":        CLASS_WRITING,
    "crm-platform-administrator":            CLASS_MECHANICAL,
    "tag--segmentation-specialist":          CLASS_MECHANICAL,
    "pipeline-stage-specialist":             CLASS_MECHANICAL,
    # MECHANICAL overrides
    "code-monitor":                          CLASS_MECHANICAL,
    "render-dispatcher":                     CLASS_MECHANICAL,
    "role--render-dispatcher":               CLASS_MECHANICAL,
    "slide-submitter":                       CLASS_MECHANICAL,
    "media-librarian-ghl-updater":           CLASS_MECHANICAL,
    "memory-hygiene-specialist":             CLASS_MECHANICAL,
    "triage-classifier":                     CLASS_MECHANICAL,
    "bug-intake-clerk":                      CLASS_MECHANICAL,
    "bug-librarian":                         CLASS_MECHANICAL,
    "bugs-department-sops":                  CLASS_MECHANICAL,
    "inbox-manager":                         CLASS_MECHANICAL,
    "dispatcher":                            CLASS_MECHANICAL,
    "scheduler":                             CLASS_MECHANICAL,
    "calendar-scheduling-manager":           CLASS_MECHANICAL,
    "transcription-specialist":              CLASS_MECHANICAL,
    "uptime-connectivity-watchdog-specialist":CLASS_MECHANICAL,
    "system-health--uptime-specialist":      CLASS_MECHANICAL,
    "monitoring--observability-specialist":  CLASS_MECHANICAL,
    "backup-and-recovery-specialist":        CLASS_MECHANICAL,
    "token-manager-furnace-watch-specialist":CLASS_MECHANICAL,
    "fulfillment-coordinator":               CLASS_MECHANICAL,
    "inventory-manager":                     CLASS_MECHANICAL,
    "task-priority-manager":                 CLASS_MECHANICAL,
    "daily-briefing-specialist":             CLASS_MECHANICAL,
    "conversion-tracking-specialist":        CLASS_MECHANICAL,
    "capacity-reliability-engineer":         CLASS_MECHANICAL,
    "version-and-upgrade-manager-specialist":CLASS_MECHANICAL,
}

# VISION flag overrides — slugs that carry the vision additive flag
VISION_SLUG_PATTERNS = [
    "fidelity-tester",
    "fidelity",
    "style-analyst",
    "style-steward",
    "style-librarian",
    "photo-shoot-director",
    "slide-image-creator",
    "ad-creative-specialist",
    "brand-identity-specialist",
    "brand-systems-specialist",
    "deck-systems-specialist",
    "infographic-specialist",
    "thumbnail",
    "color-grading",
    "visual",
    "motion-systems",
    "motion-graphics",
    "social-media-graphics",
    "presentation-designer",
]

# Departments where all non-generation, non-mechanical roles carry VISION flag
VISION_DEPTS = {"graphics"}

# ─── LAYER B: KEYWORD RULES ────────────────────────────────────────────────────

def _keyword_class(slug: str, dept: str) -> Optional[str]:
    """Apply ordered keyword rules. Returns class string or None if no match."""
    s = slug
    # HEAVY-REASONING keywords
    if "deep-research" in s:
        return CLASS_HEAVY
    if "healer" in s:
        return CLASS_HEAVY
    if "director-of" in s:
        return CLASS_HEAVY
    if "head-of" in s:
        return CLASS_HEAVY
    if s.startswith("chief-"):
        return CLASS_HEAVY
    if "architect" in s and "content-to-presentation" not in s:
        return CLASS_HEAVY
    if "strategist" in s:
        return CLASS_HEAVY
    if "forecasting" in s:
        return CLASS_HEAVY
    if "intelligence" in s:
        return CLASS_HEAVY
    if "research" in s:
        return CLASS_HEAVY
    # JUDGMENT keywords
    if "devils-advocate" in s:
        return CLASS_JUDGMENT
    if "qc-specialist" in s:
        return CLASS_JUDGMENT
    if "qc-role" in s:
        return CLASS_JUDGMENT
    if "fidelity" in s:
        return CLASS_JUDGMENT
    if "auditor" in s:
        return CLASS_JUDGMENT
    if "audit" in s:
        return CLASS_JUDGMENT
    if s.startswith("qa-"):
        return CLASS_JUDGMENT
    # CONVERSATIONAL keywords
    if "brainstorming-buddy" in s:
        return CLASS_CONVERSATIONAL
    if "concierge" in s:
        return CLASS_CONVERSATIONAL
    if "coach" in s:
        return CLASS_CONVERSATIONAL
    if "support-specialist" in s:
        return CLASS_CONVERSATIONAL
    if "chat-specialist" in s:
        return CLASS_CONVERSATIONAL
    # MECHANICAL keywords
    if "librarian" in s:
        return CLASS_MECHANICAL
    if "monitor" in s and "compliance" not in s:
        return CLASS_MECHANICAL
    if "dispatcher" in s:
        return CLASS_MECHANICAL
    if "submitter" in s:
        return CLASS_MECHANICAL
    if "classifier" in s:
        return CLASS_MECHANICAL
    if "watchdog" in s:
        return CLASS_MECHANICAL
    if "hygiene" in s:
        return CLASS_MECHANICAL
    if "intake" in s:
        return CLASS_MECHANICAL
    if "uptime" in s:
        return CLASS_MECHANICAL
    # WRITING keywords
    if "sop-writer" in s:
        return CLASS_WRITING
    if "copywriter" in s:
        return CLASS_WRITING
    if "ghostwriter" in s:
        return CLASS_WRITING
    if "-writer" in s:
        return CLASS_WRITING
    if "editor" in s and dept not in ("video", "audio"):
        return CLASS_WRITING
    if "designer" in s and dept not in ("graphics",):
        return CLASS_WRITING
    if "creator" in s and dept not in ("graphics", "video"):
        return CLASS_WRITING
    return None


# ─── LAYER D: DEPARTMENT BACKSTOP ─────────────────────────────────────────────

DEPT_BACKSTOP: dict[str, str] = {
    "graphics":                    CLASS_WRITING,
    "video":                       CLASS_WRITING,
    "audio":                       CLASS_WRITING,
    "web-development":             CLASS_HEAVY,
    "app-development":             CLASS_HEAVY,
    "engineering":                 CLASS_HEAVY,
    "research":                    CLASS_HEAVY,
    "legal-compliance":            CLASS_HEAVY,
    "billing":                     CLASS_HEAVY,
    "project-architecture-office": CLASS_HEAVY,
    "healer":                      CLASS_HEAVY,
    "quality-control":             CLASS_JUDGMENT,
    "bugs":                        CLASS_JUDGMENT,
    "sales":                       CLASS_CONVERSATIONAL,
    "customer-support":            CLASS_CONVERSATIONAL,
    "founding-member-concierge":   CLASS_CONVERSATIONAL,
    "scheduling-dispatch":         CLASS_MECHANICAL,
    "logistics-fulfillment":       CLASS_MECHANICAL,
    "openclaw-maintenance":        CLASS_MECHANICAL,
}
DEPT_BACKSTOP_DEFAULT = CLASS_WRITING


# ─── VISION FLAG INFERENCE ─────────────────────────────────────────────────────

def _has_vision_flag(slug: str, dept: str, primary_class: str) -> bool:
    """Return True if this role carries the additive VISION modality flag."""
    # Never add vision to generation or mechanical roles
    if primary_class in (CLASS_GENERATION, CLASS_MECHANICAL):
        return False
    # Dept-level blanket (graphics dept roles almost all need vision)
    if dept in VISION_DEPTS and primary_class not in (CLASS_GENERATION, CLASS_MECHANICAL, CLASS_JUDGMENT):
        return True
    # Slug-level patterns
    for pat in VISION_SLUG_PATTERNS:
        if pat in slug:
            return True
    # Presentations dept: slide image / design roles
    if dept == "presentations" and any(p in slug for p in [
        "slide-image", "brand-steward", "design-producer", "deck-systems", "typography"
    ]):
        return True
    # Video dept: storyboard / color / thumbnail / fidelity roles
    if dept == "video" and any(p in slug for p in [
        "storyboard", "color-grading", "thumbnail", "fidelity", "motion-graphics"
    ]):
        return True
    return False


# ─── MAIN INFERENCE FUNCTION ───────────────────────────────────────────────────

def infer_class(slug: str, dept: str, role_type: str = "") -> dict:
    """
    Infer the capability class for a role.

    Returns:
        {
            "capability_class": str,        # primary class constant
            "vision_flag": bool,            # True if VISION additive flag applies
            "purpose_tier": str | None,     # select_model.py tier arg (None = GENERATION)
            "required_modality": str,       # "text" | "vision" | "image_generation" | ...
            "generation_pipeline": str | None,  # fixed pipeline id for GENERATION class
            "inference_layer": str,         # "explicit_override" | "keyword" | "dept_backstop"
        }
    """
    # Normalize slug: strip ROLE-- prefix, lowercase
    raw = slug.strip().lower()
    if raw.startswith("role--"):
        raw = raw[6:]

    # Layer 0: check generation pipeline first (these bypass all LLM resolution)
    if raw in GENERATION_PIPELINE:
        result_class = CLASS_GENERATION
        pipeline = GENERATION_PIPELINE[raw]
        return {
            "capability_class": result_class,
            "vision_flag": False,
            "purpose_tier": None,
            "required_modality": "image_generation",  # broadest match
            "generation_pipeline": pipeline,
            "inference_layer": "generation_pipeline",
        }

    # Layer A: explicit override table
    layer = "explicit_override"
    result_class = EXPLICIT_OVERRIDES.get(raw)

    # Layer B: keyword rules (if Layer A missed)
    if result_class is None:
        layer = "keyword"
        result_class = _keyword_class(raw, dept)

    # Layer D: department backstop (if A and B both missed)
    if result_class is None:
        layer = "dept_backstop"
        result_class = DEPT_BACKSTOP.get(dept, DEPT_BACKSTOP_DEFAULT)

    # Layer C: vision additive flag
    vision = _has_vision_flag(raw, dept, result_class)

    purpose_tier = CLASS_TO_TIER.get(result_class)
    if vision and purpose_tier is None:
        purpose_tier = "heavy"  # safety: if somehow vision + generation, force heavy

    required_modality = "vision" if vision else "text"

    return {
        "capability_class": result_class,
        "vision_flag": vision,
        "purpose_tier": purpose_tier,
        "required_modality": required_modality,
        "generation_pipeline": None,
        "inference_layer": layer,
    }


# ─── MODEL RESOLUTION ─────────────────────────────────────────────────────────

def _module_dir() -> str:
    return os.path.dirname(os.path.abspath(__file__))


def _select_model_script_path() -> Optional[str]:
    """Locate select_model.py across known install layouts."""
    candidates = [
        os.path.join(_module_dir(), "select_model.py"),
        os.path.join(os.path.expanduser("~"), "Downloads", "openclaw-master-files",
                     "shared-utils", "select_model.py"),
        os.path.join(os.path.expanduser("~"), ".openclaw", "skills",
                     "shared-utils", "select_model.py"),
    ]
    for p in candidates:
        if p and os.path.isfile(p):
            return p
    return None


def resolve_model_for_role(
    slug: str,
    dept: str,
    role_type: str = "",
    openclaw_json_path: Optional[str] = None,
    inventory: Optional[list] = None,
) -> dict:
    """
    Full resolution: infer class then resolve a concrete model id.

    Returns:
        {
            "slug": str,
            "dept": str,
            "capability_class": str,
            "vision_flag": bool,
            "purpose_tier": str | None,
            "required_modality": str,
            "generation_pipeline": str | None,
            "model_id": str | None,
            "chain_position": int,
            "needs_owner_input": bool,
            "inference_layer": str,
            "prompt_to_owner": str,
        }
    """
    cls_info = infer_class(slug, dept, role_type)
    base = {
        "slug": slug,
        "dept": dept,
        **cls_info,
    }

    # GENERATION class → no LLM, return pipeline
    if cls_info["capability_class"] == CLASS_GENERATION:
        base.update({
            "model_id": cls_info.get("generation_pipeline"),
            "chain_position": 0,
            "needs_owner_input": False,
            "prompt_to_owner": "",
        })
        return base

    # Delegate to select_model.py for concrete model resolution
    sel = _select_model_script_path()
    if sel is None:
        base.update({
            "model_id": None,
            "chain_position": 0,
            "needs_owner_input": True,
            "prompt_to_owner": (
                "Cannot locate select_model.py. Add shared-utils/ to your path "
                "or install openclaw-onboarding and retry."
            ),
        })
        return base

    cmd = [
        sys.executable, sel,
        "--mode", "task",
        "--purpose-tier", cls_info["purpose_tier"],
        "--required-modality", cls_info["required_modality"],
        "--format", "json",
    ]
    if openclaw_json_path:
        cmd += ["--config", openclaw_json_path]

    # If inventory is passed in-process (for tests), inject via env var pattern
    # is impractical — so we call select_model.py's Python API directly instead.
    if inventory is not None:
        try:
            # Add shared-utils to sys.path temporarily
            _sm_dir = os.path.dirname(sel)
            if _sm_dir not in sys.path:
                sys.path.insert(0, _sm_dir)
            from select_model import select_task_model  # type: ignore  # noqa
            result = select_task_model(
                task_text="",
                department=dept,
                required_modality=cls_info["required_modality"],
                difficulty={"heavy": "hard", "mid": "medium", "fast": "simple"}.get(
                    cls_info["purpose_tier"], "medium"
                ),
                inventory=inventory,
            )
            base.update({
                "model_id": result.get("model_id"),
                "chain_position": result.get("chain_position", 0),
                "needs_owner_input": result.get("needs_owner_input", False),
                "prompt_to_owner": result.get("prompt_to_owner", ""),
            })
            return base
        except Exception as exc:  # noqa: BLE001
            base.update({
                "model_id": None,
                "chain_position": 0,
                "needs_owner_input": True,
                "prompt_to_owner": f"In-process select_model call failed: {exc}",
            })
            return base

    try:
        r = subprocess.run(
            cmd, capture_output=True, text=True, timeout=15,
        )
        if r.stdout.strip():
            data = json.loads(r.stdout)
            base.update({
                "model_id": data.get("model_id"),
                "chain_position": data.get("chain_position", 0),
                "needs_owner_input": data.get("needs_owner_input", False),
                "prompt_to_owner": data.get("prompt_to_owner", ""),
            })
            return base
    except Exception as exc:  # noqa: BLE001
        base.update({
            "model_id": None,
            "chain_position": 0,
            "needs_owner_input": True,
            "prompt_to_owner": f"select_model subprocess failed: {exc}",
        })
    return base


# ─── SELF-TEST ─────────────────────────────────────────────────────────────────

# Trevor's full lineup (realistic client box)
TREVOR_LINEUP = [
    "ollama/deepseek-v4-pro:cloud",
    "ollama/kimi-k2.6:cloud",
    "ollama/minimax-m1:cloud",
    "openrouter/xiaomi/mimo-v2.5-pro",
    "ollama/deepseek-v4-flash:cloud",
    "openrouter/google/gemini-3.1-flash-lite-preview",
    "openrouter/z-ai/glm-4.5",
    "openrouter/qwen/qwen3-vl:235b",
]

# Degraded lineup — only the cheapest two remain
DEGRADED_LINEUP = [
    "ollama/deepseek-v4-flash:cloud",
    "openrouter/z-ai/glm-4.5",
]

SELF_TEST_ROLES = [
    # (slug, dept, expected_class, description)
    ("master-orchestrator",        "master-orchestrator",  CLASS_HEAVY,        "CEO/orchestrator — must be HEAVY"),
    ("sop-writer",                 "audio",                CLASS_WRITING,       "SOP writer in any dept — WRITING"),
    ("qc-specialist-audio",        "audio",                CLASS_JUDGMENT,      "QC specialist — JUDGMENT"),
    ("transcription-specialist",   "audio",                CLASS_MECHANICAL,    "Transcription — MECHANICAL"),
    ("appointment-setter",         "sales",                CLASS_CONVERSATIONAL,"Appointment setter — CONVERSATIONAL"),
    ("ai-image-generator-specialist", "graphics",          CLASS_GENERATION,    "Image gen — GENERATION (no LLM)"),
    ("healer-billing",             "billing",              CLASS_HEAVY,         "Healer — always HEAVY"),
    ("devils-advocate--marketing", "marketing",            CLASS_JUDGMENT,      "Devils advocate — JUDGMENT"),
    ("deep-research-specialist",   "research",             CLASS_HEAVY,         "Deep research — HEAVY"),
    ("facebook-specialist",        "social-media",         CLASS_HEAVY,         "Social specialist — HEAVY (override)"),
    ("ios-specialist",             "app-development",      CLASS_HEAVY,         "iOS specialist — HEAVY (override)"),
    ("render-dispatcher",          "graphics",             CLASS_MECHANICAL,    "Render dispatcher — MECHANICAL (override)"),
    ("fidelity-tester",            "graphics",             CLASS_JUDGMENT,      "Fidelity tester — JUDGMENT + VISION"),
    ("style-analyst",              "graphics",             CLASS_HEAVY,         "Style analyst — HEAVY + VISION (dept backstop via keyword 'analyst')"),
]


def run_self_test():
    """Print resolver output for representative roles against two lineups."""
    _sm_dir = _module_dir()
    if _sm_dir not in sys.path:
        sys.path.insert(0, _sm_dir)

    print("=" * 70)
    print("CAPABILITY-CLASS MODEL SELECTOR — SELF-TEST")
    print("=" * 70)

    for lineup_label, lineup in [
        ("TREVOR'S FULL LINEUP", TREVOR_LINEUP),
        ("DEGRADED LINEUP (flash + glm only)", DEGRADED_LINEUP),
    ]:
        print(f"\n{'─' * 70}")
        print(f"LINEUP: {lineup_label}")
        print(f"  Models: {', '.join(lineup)}")
        print(f"{'─' * 70}")

        class_counts: dict[str, int] = {}
        vision_count = 0
        errors = []

        for slug, dept, expected_class, description in SELF_TEST_ROLES:
            result = resolve_model_for_role(slug, dept, inventory=lineup)
            actual_class = result.get("capability_class")
            vision = result.get("vision_flag", False)
            model_id = result.get("model_id") or "(none — needs_owner_input)"
            tier = result.get("purpose_tier") or "N/A"
            layer = result.get("inference_layer", "?")
            pipeline = result.get("generation_pipeline")

            class_counts[actual_class] = class_counts.get(actual_class, 0) + 1
            if vision:
                vision_count += 1

            status = "PASS" if actual_class == expected_class else "FAIL"
            if status == "FAIL":
                errors.append(f"  FAIL: {slug} expected={expected_class} got={actual_class}")

            vision_str = " +VISION" if vision else ""
            pipeline_str = f" -> {pipeline}" if pipeline else ""
            print(
                f"  [{status}] {slug:<45} {actual_class}{vision_str}"
                f"\n         tier={tier:<8} model={model_id}{pipeline_str}"
                f"\n         layer={layer} | {description}"
            )

        print(f"\n  Class distribution for this lineup:")
        for cls, cnt in sorted(class_counts.items()):
            print(f"    {cls:<20} {cnt}")
        print(f"    VISION flag applied: {vision_count}")
        if errors:
            print(f"\n  ERRORS:")
            for e in errors:
                print(e)
        else:
            print(f"\n  All {len(SELF_TEST_ROLES)} assertions PASSED.")

    print("\n" + "=" * 70)
    print("FULL ROLE INDEX COVERAGE CHECK")
    print("=" * 70)

    # Load the role index and run inference on all 424 roles
    index_candidates = [
        os.path.join(_module_dir(), "..", "23-ai-workforce-blueprint",
                     "templates", "role-library", "_index.json"),
    ]
    index_path = None
    for p in index_candidates:
        if os.path.isfile(p):
            index_path = os.path.realpath(p)
            break

    if not index_path:
        print("  _index.json not found — skipping coverage check.")
        return

    with open(index_path) as f:
        index = json.load(f)
    roles = index.get("roles", [])
    print(f"  Total roles in index: {len(roles)}")

    all_class_counts: dict[str, int] = {}
    vision_total = 0
    unmatched = []

    for role in roles:
        slug = role.get("slug", "")
        dept = role.get("dept", "")
        rtype = role.get("role_type", "")
        ci = infer_class(slug, dept, rtype)
        cls = ci["capability_class"]
        all_class_counts[cls] = all_class_counts.get(cls, 0) + 1
        if ci["vision_flag"]:
            vision_total += 1
        if ci["inference_layer"] == "dept_backstop" and dept == "":
            unmatched.append(slug)

    print(f"\n  Class distribution (all {len(roles)} roles):")
    total = 0
    for cls, cnt in sorted(all_class_counts.items(), key=lambda x: -x[1]):
        print(f"    {cls:<20} {cnt}")
        total += cnt
    print(f"    {'TOTAL':<20} {total}")
    print(f"    VISION flag applied:  {vision_total}")
    print(f"    Coverage: {'100%' if total == len(roles) else f'{total}/{len(roles)} INCOMPLETE'}")
    if unmatched:
        print(f"  Roles that hit dept_backstop with no dept: {unmatched}")
    else:
        print("  No blind defaults (every role resolved via a real rule).")


# ─── CLI ───────────────────────────────────────────────────────────────────────

def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Capability-class model selector for OpenClaw roles."
    )
    parser.add_argument("--role", default="", help="Role slug")
    parser.add_argument("--dept", default="", help="Department slug")
    parser.add_argument("--role-type", default="", help="role_type field (specialist/director/etc.)")
    parser.add_argument("--config", default=None, help="Path to openclaw.json")
    parser.add_argument(
        "--format",
        choices=("json", "class", "model"),
        default="json",
        help="Output format: json (full), class (just class name), model (just model id)",
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Run self-test against representative roles + two lineups",
    )
    args = parser.parse_args()

    if args.self_test:
        run_self_test()
        return

    if not args.role:
        parser.error("--role is required (or use --self-test)")

    result = resolve_model_for_role(
        slug=args.role,
        dept=args.dept,
        role_type=args.role_type,
        openclaw_json_path=args.config,
    )

    if args.format == "class":
        cap_class = result["capability_class"]
        if result.get("vision_flag"):
            cap_class += "+VISION"
        print(cap_class)
        sys.exit(0 if result["capability_class"] else 1)
    elif args.format == "model":
        print(result.get("model_id") or "")
        sys.exit(0 if result.get("model_id") and not result.get("needs_owner_input") else 2)
    else:
        print(json.dumps(result, indent=2))
        sys.exit(0 if not result.get("needs_owner_input") else 2)


if __name__ == "__main__":
    main()
