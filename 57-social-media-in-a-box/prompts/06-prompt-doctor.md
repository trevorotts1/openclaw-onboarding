# Prompt 06 — Prompt Doctor (Image-Gen Error Recovery)

- **Source workflow:** `03-image-generator` (03-Social Media in a Box Image Generator)
- **Model at export time:** OpenRouter `google/gemini-2.0-flash-001`
- **Purpose:** On Kie.ai 422/prompt errors: rewrites the failed Midjourney prompt (shorten, remove banned words) while preserving visual intent, then retries generation.
- **Anonymization:** verified clean — no client names or secrets in this prompt text. Client-identifying data in this workflow family lives ONLY in raw-export `pinData` (see ANALYSIS.md `client_name_locations`); it is excluded here.

## System

_Source: node `Agent - Prompt Doctor` → options.systemMessage_

```
You are a Midjourney Prompt Engineer. Output ONLY the fixed prompt text.
```

## User

_Source: node `Agent - Prompt Doctor` → text_

```
ERROR RECEIVED: {{ $json.msg || $json.error.message }}
ORIGINAL PROMPT: {{ $('Agent - Visual Prompt Architect').item.json.output }}

TASK: Rewrite the prompt to fix the error (shorten it, remove banned words) while keeping the visual intent.
```
