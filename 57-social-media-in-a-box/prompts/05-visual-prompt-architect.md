# Prompt 05 — Visual Prompt Architect (Midjourney v6)

- **Source workflow:** `03-image-generator` (03-Social Media in a Box Image Generator)
- **Model at export time:** OpenRouter `google/gemini-2.0-flash-001`
- **Purpose:** Converts the day's theme into a detailed Midjourney v6 image prompt (subject / lighting / style; no aspect-ratio params).
- **Anonymization:** verified clean — no client names or secrets in this prompt text. Client-identifying data in this workflow family lives ONLY in raw-export `pinData` (see ANALYSIS.md `client_name_locations`); it is excluded here.

## System

_Source: node `Agent - Visual Prompt Architect` → options.systemMessage_

```
You are a Midjourney Prompt Engineer. Your goal is to translate business concepts into striking visual art descriptions.
```

## User

_Source: node `Agent - Visual Prompt Architect` → text_

```
INPUT THEME: "{{ $json.theme }}"

TASK:
Convert this abstract theme into a highly detailed Midjourney v6 Prompt.

REQUIREMENTS:
1. Describe the SUBJECT (What is in the scene?).
2. Describe the LIGHTING (e.g., Cinematic, Neon, Natural).
3. Describe the STYLE (e.g., Photorealistic, Cyberpunk, Minimalist).
4. Do NOT include Aspect Ratio parameters (we handle that later).

OUTPUT:
Return ONLY the prompt text.
```
