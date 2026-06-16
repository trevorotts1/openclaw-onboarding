# Capability-Class Model-Selection Framework

**Version:** 1.0.0
**Schema targets:** role-library `_index.json` v1.x, `model_selector.py` v1.0.0+
**Audience:** Any client agent on any box — read this to understand why your model was chosen and how to override it.

---

## Why this layer exists

The existing `select_model.py` tier system (heavy / mid / fast) resolves models by *department*. That is the right default for a director-level agent routing a department. But many roles inside a department have fundamentally different computational needs:

- A `sop-writer` inside the graphics department writes text — it does not need vision.
- A `fidelity-tester` inside the same department must read images — it does need vision.
- A `render-dispatcher` sends a job to an external pipeline — a fast cheap model is correct.

The Capability-Class layer sits **above** the existing tier system. It maps each *role* to a class, each class maps to a purpose-tier + an optional hard modality requirement, and the existing cascade machinery resolves the concrete model id from whatever the client has installed.

---

## The 7 Capability Classes

| Class | One-line definition | Maps to tier | Hard modality |
|---|---|---|---|
| **HEAVY-REASONING** | Large-context multi-step reasoning, synthesis, strategy, deep research, healing, forecasting. Rare-firing; expensive. | `heavy` | `text` |
| **WRITING** | Long-form and structured-output text generation — copy, scripts, SOPs, naming, content, image-prompt authoring, code authoring. | `mid` | `text` |
| **JUDGMENT** | Scoring, critique, adversarial review, auditing, evaluation, pass/fail gating. | `mid` | `text` |
| **MECHANICAL** | Fast cheap deterministic transforms — submit, dispatch, format, upload, librarian, monitor, schedule, transcribe. | `fast` | `text` |
| **CONVERSATIONAL** | Friendly back-and-forth with a human — brainstorming, intake, onboarding, concierge, support, sales calls. | `mid` | `text` |
| **VISION** | **ADDITIVE** layer — not a standalone primary. Flags any role that must READ images; layered on top of the primary class as a hard modality requirement of `vision`. | *(inherits primary)* | `vision` |
| **GENERATION** | Image/audio/video MEDIA creation. Fixed external pipeline — KIE.ai `gpt-image-2` for images, Fish Audio for audio, dedicated video pipeline. **The LLM resolver MUST NOT assign an LLM here.** | `N/A` | `image_generation` / `audio_generation` / `video_generation` |

> **VISION is additive.** A role tagged `HEAVY-REASONING+VISION` gets the heavy tier chain but the model MUST pass the `model_has_modality(model_id, "vision")` gate. A role tagged `MECHANICAL+VISION` gets the fast chain + vision gate.

---

## Class-to-chain reference ordering

The class maps to a `select_model.py` purpose-tier argument. The existing chain order for each tier is the authoritative source of truth inside `select_model.py`; these classes are shorthand that points to those chains.

| Class | `--purpose-tier` | Chain positions (abbreviated) |
|---|---|---|
| HEAVY-REASONING | `heavy` | Ollama DeepSeek-pro → Ollama Kimi → OpenRouter DeepSeek-pro → OpenRouter Kimi → OAuth GPT |
| WRITING | `mid` | Ollama Minimax → OpenRouter Mimo-pro → OpenRouter GLM |
| JUDGMENT | `mid` | same as WRITING |
| MECHANICAL | `fast` | Ollama DeepSeek-flash → OpenRouter DeepSeek-flash → Gemini Flash Lite |
| CONVERSATIONAL | `mid` | same as WRITING |
| VISION (additive) | *(from primary)* | same chain as primary class, pre-filtered to vision-capable models |
| GENERATION | *(fixed pipeline)* | KIE.ai `gpt-image-2-image-to-image` / Fish Audio / video pipeline |

---

## Role → Class Inference Ruleset

Resolution is **ordered; first match wins.** Run against:
- the lowercased slug with any leading `ROLE--` prefix stripped
- the `dept` field
- the `role_type` field

### Layer A — Explicit override table (slugs whose names don't betray their class)

```
# HEAVY-REASONING overrides
master-orchestrator               -> HEAVY-REASONING
research-agent                    -> HEAVY-REASONING
cost-model-optimizer-specialist   -> HEAVY-REASONING
data-analysis-specialist          -> HEAVY-REASONING
go-to-market-specialist           -> HEAVY-REASONING
dept-healer-template              -> HEAVY-REASONING
chief-healer                      -> HEAVY-REASONING
chief-research-officer            -> HEAVY-REASONING
chief-project-architect           -> HEAVY-REASONING
chief-financial-officer           -> HEAVY-REASONING
chief-marketing-officer           -> HEAVY-REASONING
chief-sales-officer               -> HEAVY-REASONING
chief-communications-officer      -> HEAVY-REASONING
chief-legal-officer               -> HEAVY-REASONING
chief-design-officer              -> HEAVY-REASONING
fpanda--forecasting-analyst       -> HEAVY-REASONING
cash-flow-forecasting-specialist  -> HEAVY-REASONING
industry-analysis-specialist-mckinsey-style -> HEAVY-REASONING
capacity-planning-specialist      -> HEAVY-REASONING
customer-journey-architect        -> HEAVY-REASONING
persona-research-specialist       -> HEAVY-REASONING
market-trends-specialist          -> HEAVY-REASONING
go-to-market-specialist           -> HEAVY-REASONING
funnel-strategist                 -> HEAVY-REASONING
brand-positioning-specialist      -> HEAVY-REASONING
offer-price-strategist            -> HEAVY-REASONING

# JUDGMENT overrides
qc-agent                          -> JUDGMENT
role-auditor                      -> JUDGMENT
fidelity-tester                   -> JUDGMENT
triage-dedup-analyst              -> JUDGMENT
procedure-auditor                 -> JUDGMENT

# CONVERSATIONAL overrides
generalist-operator               -> CONVERSATIONAL
appointment-setter                -> CONVERSATIONAL
concierge-lead                    -> CONVERSATIONAL
delivery-concierge                -> CONVERSATIONAL
personal-coach                    -> CONVERSATIONAL
presenter-coach                   -> CONVERSATIONAL
closer                            -> CONVERSATIONAL
sdr-sales-development-rep         -> CONVERSATIONAL
account-executive-full-cycle      -> CONVERSATIONAL
discovery-call-specialist         -> CONVERSATIONAL
live-chat-specialist              -> CONVERSATIONAL
voice--phone-support-specialist   -> CONVERSATIONAL
tier-1-support-specialist         -> CONVERSATIONAL
tier-2-support-specialist         -> CONVERSATIONAL
community-manager                 -> CONVERSATIONAL
podcast-host                      -> CONVERSATIONAL
client-relationship-manager       -> CONVERSATIONAL
onboarding-specialist             -> CONVERSATIONAL
retention-specialist              -> CONVERSATIONAL
post-session-followup-specialist  -> CONVERSATIONAL

# WRITING overrides (strategist/specialist names that mean "writes copy")
hook-strategist                   -> WRITING
op-ed-ghostwriter                 -> WRITING
slide-copywriter                  -> WRITING
knowledge-base-specialist         -> WRITING
listing-creator                   -> WRITING
web-designer                      -> WRITING
voice-agent-builder               -> WRITING
storyboard-pre-production-specialist -> WRITING
code-editor                       -> WRITING
sop-writer                        -> WRITING
presenters-speech-writer          -> WRITING
presenters-guide-specialist       -> WRITING
speech--talking-points-specialist -> WRITING
speech-writing-specialist         -> WRITING
press-release-statement-specialist -> WRITING
brand-messaging-specialist        -> WRITING
email-campaign-strategist         -> WRITING
follow-up-sequence-specialist     -> WRITING
sms--whatsapp--dm-sequence-specialist -> WRITING
proposal-and-quote-specialist     -> WRITING

# MECHANICAL overrides
code-monitor                      -> MECHANICAL
render-dispatcher                 -> MECHANICAL
slide-submitter                   -> MECHANICAL
media-librarian-ghl-updater       -> MECHANICAL
memory-hygiene-specialist         -> MECHANICAL
triage-classifier                 -> MECHANICAL
bug-intake-clerk                  -> MECHANICAL
bug-librarian                     -> MECHANICAL
bugs-department-sops              -> MECHANICAL
inbox-manager                     -> MECHANICAL
dispatcher                        -> MECHANICAL
scheduler                         -> MECHANICAL
calendar-scheduling-manager       -> MECHANICAL
tag--segmentation-specialist      -> MECHANICAL
crm-platform-administrator        -> MECHANICAL
pipeline-stage-specialist         -> MECHANICAL
transcription-specialist          -> MECHANICAL
uptime-connectivity-watchdog-specialist -> MECHANICAL
system-health--uptime-specialist  -> MECHANICAL
monitoring--observability-specialist -> MECHANICAL
backup-and-recovery-specialist    -> MECHANICAL
token-manager-furnace-watch-specialist -> MECHANICAL
account-health-monitor-proactive  -> MECHANICAL
fulfillment-coordinator           -> MECHANICAL
inventory-manager                 -> MECHANICAL
task-priority-manager             -> MECHANICAL
daily-briefing-specialist         -> MECHANICAL
conversion-tracking-specialist    -> MECHANICAL
```

### Layer B — Ordered keyword rules (applied after Layer A; first match wins)

```
slug contains "deep-research"         -> HEAVY-REASONING
slug contains "healer"                -> HEAVY-REASONING
slug contains "director-of"           -> HEAVY-REASONING
slug contains "head-of"               -> HEAVY-REASONING
slug contains "chief-"                -> HEAVY-REASONING
slug contains "architect"             -> HEAVY-REASONING
slug contains "strategist"            -> HEAVY-REASONING  (unless overridden in A)
slug contains "forecasting"           -> HEAVY-REASONING
slug contains "intelligence"          -> HEAVY-REASONING
slug contains "research"              -> HEAVY-REASONING

slug contains "devils-advocate"       -> JUDGMENT
slug contains "qc-specialist"         -> JUDGMENT
slug contains "qc-role"               -> JUDGMENT
slug contains "qc-agent"              -> JUDGMENT
slug contains "fidelity"              -> JUDGMENT
slug contains "auditor"               -> JUDGMENT
slug contains "audit"                 -> JUDGMENT
slug contains "qa-"                   -> JUDGMENT

slug contains "brainstorming-buddy"   -> CONVERSATIONAL
slug contains "concierge"             -> CONVERSATIONAL
slug contains "coach"                 -> CONVERSATIONAL
slug contains "support-specialist"    -> CONVERSATIONAL
slug contains "chat-specialist"       -> CONVERSATIONAL
slug contains "onboarding"            -> CONVERSATIONAL  (unless mechanical override)

slug contains "sop-writer"            -> WRITING
slug contains "copywriter"            -> WRITING
slug contains "ghostwriter"           -> WRITING
slug contains "content-"              -> WRITING
slug contains "copy"                  -> WRITING
slug contains "-writer"               -> WRITING
slug contains "editor" AND dept != "video"  -> WRITING
slug contains "designer" AND dept != "graphics"  -> WRITING
slug contains "creator"               -> WRITING  (unless generation dept)

slug contains "librarian"             -> MECHANICAL
slug contains "monitor"               -> MECHANICAL
slug contains "dispatcher"            -> MECHANICAL
slug contains "submitter"             -> MECHANICAL
slug contains "classifier"            -> MECHANICAL
slug contains "scheduler"             -> MECHANICAL
slug contains "watchdog"              -> MECHANICAL
slug contains "uptime"                -> MECHANICAL
slug contains "hygiene"               -> MECHANICAL
slug contains "intake"                -> MECHANICAL
slug contains "versioning"            -> MECHANICAL
```

### Layer C — VISION additive flag rules (applied AFTER primary class is set)

A role receives the VISION flag in addition to its primary class when any of these are true:
- `dept` is `graphics` AND role is not a pure GENERATION or MECHANICAL role
- `dept` is `video` AND role touches frames/thumbnails/storyboards (slug contains `storyboard`, `color-grading`, `thumbnail`, `fidelity`)
- slug contains `fidelity-tester`, `style-analyst`, `style-steward`, `photo-shoot-director`, `visual`, `slide-image-creator`
- slug contains `ad-creative` (visual QC)
- `dept` is `presentations` AND slug contains `slide-image`, `brand-steward`, `design-producer`, `deck-systems`

### Layer D — Department-tier backstop (100% coverage fallback)

Any role not matched by A, B, or C resolves via its department's canonical tier from `dept-model-suitability.json`. This is NOT a blind MECHANICAL default — it is a *sensible domain default* derived from the department's nature.

| Department | Backstop class |
|---|---|
| `graphics` | WRITING (text prompt authoring) + VISION flag |
| `video` | WRITING |
| `audio` | WRITING |
| `web-development`, `app-development`, `engineering` | HEAVY-REASONING |
| `research` | HEAVY-REASONING |
| `legal-compliance` | HEAVY-REASONING |
| `billing` | HEAVY-REASONING |
| `project-architecture-office` | HEAVY-REASONING |
| `healer` | HEAVY-REASONING |
| `quality-control` | JUDGMENT |
| `sales` | CONVERSATIONAL |
| `customer-support` | CONVERSATIONAL |
| `founding-member-concierge` | CONVERSATIONAL |
| `scheduling-dispatch` | MECHANICAL |
| `logistics-fulfillment` | MECHANICAL |
| `openclaw-maintenance` | MECHANICAL |
| all others | WRITING |

---

## GENERATION roles — fixed pipeline, no LLM

The following role slugs map to GENERATION class. The resolver returns a fixed pipeline target, not an LLM:

- `ai-image-generator-specialist` → KIE.ai `gpt-image-2-image-to-image`
- `ai-video-generator-specialist` → video pipeline
- `music-and-audio-producer` → Fish Audio
- `generation-operator` / `ROLE--generation-operator` → KIE.ai `gpt-image-2-image-to-image`
- `slide-image-creator` → KIE.ai `gpt-image-2-image-to-image`
- `sound-design-sfx-specialist` → Fish Audio
- `audiobook-production-specialist` → Fish Audio
- `ai-voice-specialist-11-labs-play.ht` → Fish Audio / ElevenLabs (external)

---

## How a client agent self-selects

```
1. Read this file to understand the classes.
2. Call: python3 shared-utils/model_selector.py --role <slug> --dept <dept>
   Output: JSON with { capability_class, vision_flag, model_id, tier, pipeline }
3. Honor explicit role-level override in openclaw.json agents.list[].model if present.
4. Honor the resolved model_id otherwise.
```

---

## Backward compatibility

- All existing `_resolve_dept_default_model` calls in `build-workforce.py` continue to work unchanged.
- The new per-role resolution is additive: if a role has an explicit `model` in openclaw.json, that wins (Layer 0 override). The class-based resolution is Layer 1.
- The `capability_class` field is added to each role entry in `_index.json` by the tagging script at build time.

---

*Generated by the MSF build — do not hand-edit the capability_class fields; regenerate via `python3 23-ai-workforce-blueprint/scripts/tag_role_classes.py`.*
