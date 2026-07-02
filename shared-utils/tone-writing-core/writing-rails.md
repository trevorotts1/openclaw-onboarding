# Shared Writing Rails (canonical)

The writing rails every BlackCEO writing skill (52 brand / 53 book / 54 anthology) enforces on
tone-governed output. Extracted verbatim-in-spirit from the source generator methodology; the
machine floors are enforced by each skill's content prover (`aa_build_check.py` for 52).

## R1 — Tone fidelity
- Author ONLY in the resolved tone (`Tone_Doc` / "The {First} {Last} Tone"). No other style.
- The blended tone is quoted **verbatim, untruncated** into the bios and every bot document.

## R2 — Grade-level analysis first
- Every tone-style analysis opens with the communicator's grade level ("communicates at the
  10th-grade level" / "PhD level"), then the `[TONE]` explanation, then mimic-not-plagiarize
  writing instructions, then one short example paragraph.

## R3 — N/A auto-pick (never a dead field)
- If a tone-style input is `N/A`/`na`/blank, the stage MUST auto-pick a real, well-known figure in
  harmony with the avatar's 32 answers — the style field is never left empty.

## R4 — Markdown-only, no bracketed scaffolding
- Output is pure Markdown. No `[bracketed]` template text may survive into the artifact.
- Lists put each item on its own line; questions render as H3 headers followed by the answer.
- No commentary before or after the requested output.

## R5 — Cultural / gender / intersectional relevance
- Analyze the brand/avatar for cultural group, gender, or intersection and tailor references,
  history, and language accordingly; avoid stereotyping; err toward inclusivity and respect.
- African-American audiences: "African American" (never "black"); concrete, respectful skin-tone /
  hairstyle description standards where imagery is described.

## R6 — Per-platform usage guidance
- The blended tone doc explains how to use the tone for: email + subject lines, SMS, Facebook,
  TikTok, Instagram, Twitter, webinar scripts, 90-second reels, and YouTube shorts — mindful of the
  shorter-text platforms.

## R7 — Stripped-word floors (machine-enforced)
| Artifact | Floor |
|---|---|
| Blended tone (`08`) | ≥ 3,000 stripped words |
| Avatar Questions 1–30 (`01`) | ≥ 3,000 stripped words |
| Each awareness pt1 (`09/11/13`) | ≥ 1,500 stripped words |
| Booking bot (`19`) | ≥ 5,000 stripped words |

Floors are measured on **markdown/whitespace-stripped** text so padding can never fake a floor.
Self-reported counts are ignored.

## R8 — Provider sovereignty (binding)
- Resolved by the **client's own** TIER-A (deep authoring) / TIER-B (structured) models. Zero
  Anthropic/`claude-*` ids at runtime; client keys only, never the operator's.
