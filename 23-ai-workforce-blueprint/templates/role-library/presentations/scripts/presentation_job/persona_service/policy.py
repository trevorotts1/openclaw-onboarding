"""Per-phase persona policy — execution specialist vs client voice (PRES-053).

Two independent dimensions, never conflated:

  * execution_persona — the craft specialist that OWNS the work process
    (the manifest owning_role; a Skill23 task persona for the phase job).
  * client_voice — the audience-facing blended voice governing WRITTEN
    output (Skill23 voice/topic blend; Skill51 governed_phase_voice for
    the four narrative phases).

Policy kinds:
  * "governed-blend" — client-facing copy: resolve the full blend bundle
    and attach the relevant sections to the work unit.
  * "execution-only" — research/render/ops phases: execution specialist
    only, no audience voice (mirrors the blender's non-content branch).
  * "qc-independent" — QC phases: an independent reviewer persona that
    MUST differ from the producing phase's voice.
  * "human-gate" — owner-gateway phases: no persona resolution; the owner
    decides (style pick, intake confirm).
"""
from __future__ import annotations

from typing import Dict, List, Optional

# The four Skill51 narrative phases (blend_voice_governance.PHASES) mapped
# from pipeline phase ids (presentation_job.persona.BLEND_PHASE_FOR).
NARRATIVE_PHASE_FOR = {
    "P-SP-STRUCTURE": "avatar-section",
    "P4-COPY": "signature-story",
    "P-SP-P3-HYGIENE": "transformational-teaching",
    "P4-PROMPT": "purpose-pitch",
}

NARRATIVE_PHASES = ("avatar-section", "signature-story",
                    "transformational-teaching", "purpose-pitch")

# Phases whose artifact is client-facing written copy/speech/page/VSL and
# therefore needs the governed blend voice (beyond the four narrative
# phases, which always resolve).
GOVERNED_BLEND_PHASES = frozenset({
    "P-SP-STRUCTURE",
    "P4-COPY",
    "P-SP-P3-HYGIENE",
    "P4-PROMPT",
    "P-U-SALES-COPY",
    "P-U-CHECKOUT-COPY",
    "P-U-VSL-COPY",
    "P-U-VSL-RESEARCH",
    "P9-SPEECH",
    "P9.1-SPEECH-PDF",
    "P7-TELEPROMPTER",
    "P9-SPEECH-WEBINAR-INTRO",
    "P8.2-GUIDE",
    "P8.25-WORKBOOK",
    "P-U-HTML-SALES",
    "P-U-HTML-CHECKOUT",
    "P-U-HTML-VSL",
    "P8.4-FISH-TAG",
    "P-CONVERTER",
})

# QC phases: independent reviewer, must differ from the producer voice.
QC_PHASES = frozenset({
    "P1Q-COPY-QC",
    "P-TYPO-QC",
    "P-PROMPT-QC",
    "P-IMAGE-QC",
    "P-SPEECH-QC",
    "P-SHIFT-QC",
    "P-QC-AGGREGATE",
    "P-U-QC",
    "P-BUNDLE-GATE",
})

# Owner-gateway phases: a human decides; no persona resolution.
HUMAN_GATE_PHASES = frozenset({
    "P-STYLE-PICK",
    "P0A-INTAKE",
})

# Execution specialist per pipeline phase (manifest owning_role verbatim).
# Source: universal-sops/presentation-slide-craft/PIPELINE-MANIFEST.json
# (62 phases). Kept as data so drift is a diff, not a mystery.
EXECUTION_SPECIALIST_FOR: Dict[str, str] = {
    "P-CONVERTER": "content-to-presentation-architect",
    "P-0.5-RESEARCH": "deep-research-specialist-presentations",
    "P0A-INTAKE": "director-of-presentations",
    "P-SP-CLAIM": "signature-presentation-architect",
    "P-SP-INTAKE": "signature-presentation-architect",
    "P-SP-INTAKE-TRACE": "signature-presentation-architect",
    "P0B-PRIORITY": "attention-content-strategist",
    "P3-ARC": "offer-price-strategist",
    "P-3.5-RESEARCH-MAP": "deep-research-specialist-presentations",
    "P-U-SALES-COPY": "slide-copywriter",
    "P-U-CHECKOUT-COPY": "slide-copywriter",
    "P-U-VSL-RESEARCH": "deep-research-specialist-presentations",
    "P-U-VSL-COPY": "slide-copywriter",
    "P4-COPY": "slide-copywriter",
    "P-SP-STRUCTURE": "signature-presentation-architect",
    "P-SP-P3-HYGIENE": "qc-specialist-signature-presentations",
    "P-U-DESIGN-SALES": "slide-image-creator",
    "P-U-DESIGN-RENDER-SALES": "slide-image-creator",
    "P1Q-COPY-QC": "qc-specialist-presentations",
    "P-U-DESIGN-CHECKOUT": "slide-image-creator",
    "P-U-DESIGN-RENDER-CHECKOUT": "slide-image-creator",
    "P-U-DESIGN-VSL": "slide-image-creator",
    "P-U-DESIGN-RENDER-VSL": "slide-image-creator",
    "PF-DESIGN": "typography-architect",
    "P-TYPO-QC": "qc-specialist-typography-presentations",
    "P4-PROMPT": "prompt-author-presentations",
    "P-PROMPT-QC": "qc-specialist-prompt-presentations",
    "P-STYLE-PREVIEW": "slide-image-creator",
    "P-STYLE-SPEC": "brand-steward",
    "P-STYLE-PICK": "brand-steward",
    "P4-RENDER": "slide-image-creator",
    "P-IMAGE-QC": "qc-specialist-image-presentations",
    "P-U-HTML-SALES": "pptx-assembly-specialist",
    "P-U-HTML-CHECKOUT": "pptx-assembly-specialist",
    "P-U-HTML-VSL": "pptx-assembly-specialist",
    "P-U-FORM-GATE": "media-librarian-ghl-updater",
    "P-U-GHL-SALES": "media-librarian-ghl-updater",
    "P-U-GHL-VSL": "media-librarian-ghl-updater",
    "P-SHIFT-QC": "qc-specialist-presentations",
    "P8-ASSEMBLE": "pptx-assembly-specialist",
    "P8.1-PDF-EXPORT": "pptx-assembly-specialist",
    "P8.2-GUIDE": "presenters-guide-specialist",
    "P8.25-WORKBOOK": "pptx-assembly-specialist",
    "P8.3-INFOGRAPHIC": "slide-image-creator",
    "P9-SPEECH": "presenters-speech-writer",
    "P8.4-FISH-TAG": "fish-audio-expression-specialist",
    "P9-SPEECH-WEBINAR-INTRO": "audio-demonstration-specialist",
    "P9.1-SPEECH-PDF": "presenters-speech-writer",
    "P-SPEECH-QC": "qc-specialist-speech-presentations",
    "P-QC-AGGREGATE": "qc-specialist-presentations",
    "P9.5-NOTES-SYNC": "pptx-assembly-specialist",
    "P-U-SALES-BUILD": "media-librarian-ghl-updater",
    "P-U-CHECKOUT-BUILD": "media-librarian-ghl-updater",
    "P-U-FORM-CHECKOUT": "media-librarian-ghl-updater",
    "P-U-COLLATERAL": "delivery-concierge",
    "P9.2-GHL-UPLOAD": "media-librarian-ghl-updater",
    "P9.6-WEBINAR-VIDEO": "media-librarian-ghl-updater",
    "P-U-VSL-BUILD": "media-librarian-ghl-updater",
    "P7-TELEPROMPTER": "presenters-speech-writer",
    "P9-DELIVER": "delivery-concierge",
    "P-U-QC": "qc-specialist-presentations",
    "P-BUNDLE-GATE": "pptx-assembly-specialist",
}

# Producer phase per QC phase — the QC voice must differ from this voice.
QC_PRODUCER_FOR: Dict[str, str] = {
    "P1Q-COPY-QC": "P4-COPY",
    "P-TYPO-QC": "PF-DESIGN",
    "P-PROMPT-QC": "P4-PROMPT",
    "P-IMAGE-QC": "P4-RENDER",
    "P-SPEECH-QC": "P9-SPEECH",
    "P-SHIFT-QC": "P0B-PRIORITY",
    "P-QC-AGGREGATE": "",
    "P-U-QC": "P-U-SALES-BUILD",
    "P-BUNDLE-GATE": "P9-DELIVER",
}


def policy_for_phase(phase_id: str) -> dict:
    """Return the persona policy for any pipeline phase.

    Never raises on unknown phases: an unlisted phase gets execution-only
    with no pinned specialist (honest, never fabricated).
    """
    if phase_id in HUMAN_GATE_PHASES:
        return {
            "phase": phase_id,
            "kind": "human-gate",
            "execution_specialist": EXECUTION_SPECIALIST_FOR.get(phase_id, ""),
            "client_voice": False,
            "narrative_phase": NARRATIVE_PHASE_FOR.get(phase_id, ""),
            "note": "owner gateway decides; no persona resolution",
        }
    if phase_id in QC_PHASES:
        return {
            "phase": phase_id,
            "kind": "qc-independent",
            "execution_specialist": EXECUTION_SPECIALIST_FOR.get(phase_id, ""),
            "client_voice": False,
            "independent_of": QC_PRODUCER_FOR.get(phase_id, ""),
            "narrative_phase": "",
            "note": "independent reviewer; must differ from producer voice",
        }
    if phase_id in GOVERNED_BLEND_PHASES:
        return {
            "phase": phase_id,
            "kind": "governed-blend",
            "execution_specialist": EXECUTION_SPECIALIST_FOR.get(phase_id, ""),
            "client_voice": True,
            "narrative_phase": NARRATIVE_PHASE_FOR.get(phase_id, ""),
            "note": "execution specialist does the work; blended client voice governs the words",
        }
    return {
        "phase": phase_id,
        "kind": "execution-only",
        "execution_specialist": EXECUTION_SPECIALIST_FOR.get(phase_id, ""),
        "client_voice": False,
        "narrative_phase": "",
        "note": "craft/ops phase; no audience voice (blend non-content branch)",
    }


def all_policy_phases() -> List[str]:
    return sorted(set(EXECUTION_SPECIALIST_FOR)
                  | set(GOVERNED_BLEND_PHASES)
                  | set(QC_PHASES)
                  | set(HUMAN_GATE_PHASES))


def unresolved_phases(phase_ids: List[str]) -> List[str]:
    """Phases with no pinned execution specialist — packaging drift signal."""
    return [p for p in phase_ids if p not in EXECUTION_SPECIALIST_FOR]
