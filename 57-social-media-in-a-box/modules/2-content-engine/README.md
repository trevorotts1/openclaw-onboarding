# Module 2 — Content engine

**Source:** `02-content-generator` (14 nodes) + `agency-template-fixed-v3` writer/reformatter.
**Prompts:** 01–04, 15, 16 (baked, hash-pinned). **Phases:** P2 (author) + P3 (contract + bands).

## Two engines

- **(A) Single-call N-day multi-platform generator** — prompt 01: N days of platform-specific
  content (post/story/reel/video/short variants) as a JSON array from theme + CTA + link + platform
  list.
- **(B) Per-day agent loop** — Core-Concept master-hook agent (prompt 02) → per-platform "Superpower
  Strategy" injection (prompt 03) → Platform-Native Reformatter (prompt 04).

The **weekly 7-part series** mode uses **prompt 15** (7-part cliffhanger content writer, 64K chars) +
**prompt 16** (multi-platform reformatter playbook, 70K chars). See `MASTERDOC.md §1` for the SACRED
series mechanics (identical main title, no-space hashtag subtitles, 150-char hook, truth standard,
theme-seeded style randomizers).

## Provider chain (CLIENT only)

Text runs on the client's OpenRouter key with their chosen `openrouterModel` + the 2
`openrouterFallbacks` (`route:"fallback"`). Authoring-grade steps (core concept, super prompts) use
the primary; retries walk the fallback chain. **Zero Anthropic.** The run manifest records every
model used (`AF-SM-NOANTHROPIC`).

## Enforcement (P3)

Every output is dropped as JSON under the run dir and gated:

- `working/content/bands/*.json` → `prove_bands.py` (the SACRED bands; `MASTERDOC.md §2`).
- `working/content/contracts/*.json` → `validate_contract.py` (per-platform shape + em-dash ban +
  single-digit grid + JSON-safe QC; `MASTERDOC.md §3`).

Any non-zero exit BLOCKS advance to media. No "close enough": a logged client-exact override wins
and is recorded on the certificate.
