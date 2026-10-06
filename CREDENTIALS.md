# Credential Alias Mapping
# Version 1.0 | March 22, 2026
#
# This file maps credential names across skills. When checking if a credential
# exists, the agent must check ALL aliases, not just the primary name.
# A credential is PRESENT if ANY alias is found in ANY env file.

## Google API Key
**Required by:** Skill 22, Skill 31
**Check ALL of these names:**
- GOOGLE_API_KEY
- GEMINI_API_KEY
- GOOGLE_CLOUD_API_KEY
If ANY of these exist, the credential is satisfied.

## OpenRouter API Key
**Required by:** Skill 22 (fallback), Skill 28 (fallback)
**Check ALL of these names:**
- OPENROUTER_API_KEY
If this exists, models routed via OpenRouter are available. This can substitute for MOONSHOT_API_KEY since Kimi K2.5 is available via OpenRouter.

## Moonshot API Key
**OPTIONAL for:** Skill 22
**Check ALL of these names:**
- MOONSHOT_API_KEY
**Note:** This is NOT required if OPENROUTER_API_KEY exists, because Kimi K2.5 is available via openrouter/moonshot/kimi-k2.6. Only flag as missing if NEITHER Moonshot NOR OpenRouter keys exist.

## GoHighLevel / Convert and Flow
**Required by:** Skill 5, Skill 6, Skill 29
**Check ALL of these names:**
- PRIVATE_INTEGRATION_TOKEN
- GHL_API_KEY
- GOHIGHLEVEL_API_KEY
- GHL_TOKEN
- GHL_PIT
- PIT_TOKEN
If ANY of these exist, the credential is satisfied. GoHighLevel, GHL, and Convert and Flow are the same system. The correct modern term is Private Integration Token (PIT).

## KIE.ai API Key
**Required by (KIE is the media provider these skills call):**
- Skill 7 (KIE setup and HTTP structure) and the KIE family: Skill 46 (callback relay), Skill 66 (image), Skill 67 (video), Skill 68 (audio), Skill 74 (live adapter: live model discovery, live schema read, submit and poll; ships separately)
- Video and image producers: Skill 25, Skill 28, Skill 47 (movie producer; Skills 49 and 56 reach KIE through Skill 47's image adapter)
- Content skills: Skill 37 (closeout infographics and celebration video), Skill 45 (design library, requires Skill 7 and the key), Skill 48 (Facebook ads), Skill 49 (signature funnel), Skill 56 (sales page assets), Skill 57 (social media in a box), Skill 58 (podcast cover art), Skill 59 (anthology covers), Skill 62 (cinematic web funnel)
- Skill 6 (GHL install pages): its image step generates page images through KIE
- The Presentations, Graphics, and Video departments (they generate slides, graphics, and video through KIE)
- Skill 38 only records a KIE model id for its optional workflow hero visual (a stub; it makes no KIE call yet) and checks that the key is present
**Whose key:** on a client box the KIE key is the client's own. Operator keys are never used for client work.
**Check ALL of these names:** the alias list lives in `shared-utils/secret_names.json` under `KIE_API_KEY` (the one secret-name canon). Check every name listed there; do not copy the list into other files. If ANY alias exists, the credential is satisfied.
**Shared KIE rules:** `07-kie-setup/references/kie-common-rules.md`.

## Vercel Token
**Required by:** Skill 8
**Check ALL of these names:**
- VERCEL_TOKEN
- VERCEL_API_KEY
If ANY of these exist, the credential is satisfied.

## GitHub Token
**Required by:** Skill 10
**OPTIONAL for:** Skill 6 (non-blocking archival of VERCEL_EMBED page source to
GitHub — `06-ghl-install-pages/tools/ghl_github_archive.py`). If absent, Skill
6's Vercel-embed pages still deploy and go live normally; only the GitHub
archive step is skipped (recorded as an honest failed receipt, never a build
blocker). Flag it for the operator so the page's source ends up in GitHub per
the standing "source always also lives in GitHub" rule, but do NOT halt the
build over it.
**Check ALL of these names:**
- GH_TOKEN
- GITHUB_TOKEN
If ANY of these exist, the credential is satisfied.

## Fish Audio API Key
**Required by:** Skill 30
**Check ALL of these names:**
- FISH_AUDIO_API_KEY

## LLM API Key (at least one)
**Required by:** Skill 11 (optional), Skill 28 (at least one)
**Check ALL of these names:**
- GEMINI_API_KEY
- GOOGLE_API_KEY
- OPENAI_API_KEY
- OPENROUTER_API_KEY
- ANTHROPIC_API_KEY
If ANY of these exist, the LLM credential is satisfied. The agent does NOT need all of them. One is enough.

## OPTIONAL Credentials (do NOT flag as missing)
These are nice-to-have but NOT required. Do not block installation if missing:
- PIKA_API_KEY (Skill 25 - optional provider, KIE.ai is primary)
- RUNWAY_API_KEY (Skill 25 - optional provider, KIE.ai is primary)
- ANTHROPIC_API_KEY (Skill 11 - optional, can use OpenRouter or OpenAI instead)
- APIFY_API_TOKEN (Skill 28 - optional YouTube transcript fallback)
- MOONSHOT_API_KEY (Skill 22 - optional if OpenRouter key exists)

## Where to Look
Check ALL of these locations for every credential:
1. ~/.openclaw/.env
2. ~/.openclaw/secrets/.env
3. ~/.openclaw/workspace/secrets/.env
4. ~/clawd/secrets/.env (legacy path, some clients still use this)
5. System environment variables (printenv | grep KEY_NAME)

Do NOT stop after checking one file. A credential might be in any of them.
Do NOT report a credential as missing if it exists under a different alias name.
