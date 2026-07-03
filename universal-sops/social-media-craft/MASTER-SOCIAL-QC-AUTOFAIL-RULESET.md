# MASTER SOCIAL QC AUTO-FAIL RULESET

**Cluster:** Social-Media-Craft Rules (`universal-sops/social-media-craft/`)
**Enforced by:** `57-social-media-in-a-box/scripts/prove_bands.py` + `validate_contract.py` + `preflight_gate.py` + `scrub_gate.py` + `build_manifest.py` + `ledger.py` (all fail-closed, model-free, stdlib-only) + `run_social_media.py` (phase integrity) + `social-media-entry.sh` (front-door nonce, BYPASS-SCAN, engine hash-pin)
**Master authority:** `57-social-media-in-a-box/SOCIAL-MANIFEST.json` (this table is its SOP-facing mirror)

Every run and every asset is measured against the table below. A violation is a HARD auto-fail: the prover `sys.exit(2)` with the named code, and the publisher is NOT unlocked. The provers are MEASURERS, not an agent self-score. Bands are SACRED (`config/bands.json`); a logged client-exact override wins over a default band and is recorded on the process certificate (the client gets EXACTLY what they ask for — never floored/capped). A SILENT deviation is the only forbidden deviation.

## Section 1 — The auto-fail table

| AF code | Stage | Level | Trigger |
|---|---|---|---|
| `AF-SM-PREFLIGHT-CREDITS` | P0 | run | Kie.ai credits < 200. |
| `AF-SM-PREFLIGHT-BALANCE` | P0 | run | OpenRouter balance < $5. |
| `AF-SM-PREFLIGHT-TOKEN` | P0 | run | GHL Private Integration Token invalid against `GET /locations/{locationId}`. |
| `AF-SM-PREFLIGHT-CONFIG` | P0 | run | a required client-config field is missing/empty. |
| `AF-SM-PREFLIGHT-STATUS` | P0 | run | client status != Paid. |
| `AF-SM-DISCOVERY-DRIFT` | P0 | run | C2 live connected-accounts reconcile drift: a configured platform has no live GHL account, OR a live-connected platform is missing from the config enum without a logged `platformsExcluded` entry (the BANNED silent-miss), OR the live listing is unconfirmable in `--live` mode. |
| `AF-SM-PLAN-INCOMPLETE` | P1 | run | `plan.json` missing `themeOfWeek` or `plannerSheetId`. |
| `AF-SM-CONTENT-MISSING` | P2 | run | `content.json` not authored. |
| `AF-SM-CONTRACT-JSON` | P3 | asset | an LLM output is not valid JSON / not the declared object. |
| `AF-SM-CONTRACT-SCHEMA` | P3 | asset | a per-platform required key is missing (e.g. LinkedIn PDF carousel needs `pdfTitle` + `postAsPdf:true`; carousel needs `slides[]`). |
| `AF-SM-CONTRACT-EMDASH` | P3 | asset | an em-dash (or other banned smart character) is present in JSON-safe output (QC/caption). |
| `AF-SM-GRID-DIGIT` | P3 | asset | the Gemini 4-grid selector output is not a single digit 0-3. |
| `AF-SM-QC-JSON` | P3 | asset | the QC bot output is neither the literal `Good` nor the exact fix field set, or is not JSON-safe for SeedDream re-injection. |
| `AF-SM-CAPTION-BAND` | P3 | asset | `carouselCaption` outside 1500-1800 (FB/IG) or 1500-1900 (LinkedIn) chars. |
| `AF-SM-IMGPROMPT-BAND` | P3 | asset | a carousel slide image prompt outside 1000-1700 chars, or a 7-part series image prompt under 1800 chars. |
| `AF-SM-FOLLOWUP-BAND` | P3 | asset | `followUpComment` over 600 chars (series) / over 500 chars (reformatter). |
| `AF-SM-PDFTITLE-BAND` | P3 | asset | LinkedIn `pdfTitle` over 100 chars. |
| `AF-SM-HEADLINE-WORDS` | P3 | asset | a slide `textOnImage` headline over 8 words. |
| `AF-SM-HASHTAG-COUNT` | P3 | asset | hashtags outside 5-7 (FB/IG) / not exactly 3 (LinkedIn) / outside 5-15 (IG reformat). |
| `AF-SM-POSTBODY-WORDS` | P3 | asset | a main post body under 300 words. |
| `AF-SM-STORYBOARD` | P3 | asset | storyboard not 3-7 scenes, or scene durations do not sum to EXACTLY 25.0s (default lane). |
| `AF-SM-CAROUSEL-SLIDES` | P3 | asset | carousel not exactly 10 slides (FB/IG) / 9 slides (LinkedIn). |
| `AF-SM-CAROUSEL-FLOOR` | P3/P4 | asset | carousel assembly attempted with fewer than 2 completed images (also caps a slide-count override below the assembly floor). |
| `AF-SM-STORIES-CAPTION` | P3 | asset | FB/IG Stories caption over 250 chars (C7 content-completeness fold; client-overridable, logged). |
| `AF-SM-MEDIA-LEDGER` | P4 | run | `media_ledger.json` absent/incomplete, or an unhandled fail/timeout branch did not alert. |
| `AF-SM-CLIENT-NAME` | P5/build | bytes | a client-name token from the build-private scrub list is present (list env-supplied, NEVER shipped). |
| `AF-SM-SECRET` | P5/build | bytes | a secret pattern is present (`sk-or-v1-`, `pit-`, Kie key, bearer/JWT, webhook accessToken). |
| `AF-SM-PINDATA` | P5/build | bytes | an n8n `pinData` block is present in a shipped/generated artifact. |
| `AF-SM-NOANTHROPIC` | P5/P6/build | bytes | an anthropic/claude-* model identifier is present in any client-path file or run manifest (G-NOANTHROPIC). |
| `AF-SM-PROCESS-INTEGRITY` | P6 | run | deploy/publish requested without a signed process certificate, or a phase was skipped. |
| `AF-SM-PROMPT-HASH` | P6/build | bytes | a shipped prompt file hash does not match the canonical pin. |
| `AF-SM-PROVENANCE-MISSING` | P6 | run | the certificate is requested with no per-call provenance record (a zero-Anthropic proof cannot be made without it). |
| `AF-SM-AGENCY-SHARED-PIT` | P6 | run | agency mode: two roster entries share a `pit` or `locationId` (co-mingled credentials). |
| `AF-SM-PUBLISH-RESULT` | P7 | run | a sub-mode result does not carry the normalized `{platform, success, totalPosts, processedAccounts, errors}` contract. |
| `AF-SM-PUBLISH-UNPROVEN` | P7 | run | the publisher was invoked without a complete upstream manifest/certificate. |
| `AF-SM-DOUBLE-POST` | P7 | run | same `(platform, content_sha256)` posted/scheduled within the lookback window, or `(platform, scheduled_slot)` occupied — reconciled against the LIVE GHL post-listing; cleared ONLY by a logged owner re-post token. |
| `AF-SM-WRITEBACK-COLUMNS` | P8 | run | the planner write-back row is not the normalized 20-column shape. |
| `AF-SM-POST-BYPASS` | entry | run | a hand-rolled social poster exists in the run directory outside the sanctioned GHL-direct handoff. |
| `AF-SM-ENGINE-HASH-PIN` | entry | run | the sha256 of `run_social_media.py` + the provers does not match `ENGINE-PIN.sha256`. |
| `AF-SM-OVERRIDE-UNLOGGED` | P6 | run | a band override was APPLIED during proving with no matching logged entry (who asked / verbatim ask / scope). Deviation is free; a SILENT deviation is forbidden. |
| `AF-SM-CLIENT-COPY-MUTATED` | P6/P7 | bytes | in client-copy mode the published bytes do not match the client's supplied copy (modulo a programmatic ctaLink append). |
| `AF-SM-ENGAGE-REPORT` | P12 | run | engage mode ran but the read-only anomaly report artifact is absent/malformed. |
| `AF-SM-EMAIL-SUBJECT` | P9 | asset | newsletter subject outside 1-60 chars (client-overridable, logged). |
| `AF-SM-EMAIL-PREVIEW` | P9 | asset | newsletter preview over 120 chars (client-overridable, logged). |
| `AF-SM-EMAIL-HTML` | P9 | asset | newsletter missing the table-based inline-CSS html body. |
| `AF-SM-BLOG-TITLE` | P10 | asset | blog title outside 1-80 chars (client-overridable, logged). |
| `AF-SM-BLOG-META` | P10 | asset | blog metaDescription over 160 chars (client-overridable, logged). |
| `AF-SM-BLOG-BODY` | P10 | asset | blog body under 700 words (client-overridable, logged). |
| `AF-SM-PODCAST-SCRIPT` | P11 | asset | podcast script outside 1,500-2,000 words or < 1 `[emotion]` tag per paragraph. |
| `AF-SM-PODCAST-DURATION` | P11 | asset | podcast audio outside 600-900 s or under 128 kbps (ffprobe). |
| `AF-SM-PODCAST-COVER` | P11 | asset | podcast cover not 1400x1400 JPEG. |
| `AF-SM-DEFERRED` | defer | run | a capability deferred to a named later version was requested (syndicate C9 v0.4.0 / narrated-video C8 v0.3.0 / persona-adapter C10 v0.5.0 / memory-adapter C11 v0.5.0). The stub fails CLOSED with a clear "deferred to vX.Y.Z" message. |

## Section 2 — How to run it

```
bash 57-social-media-in-a-box/social-media-entry.sh --run-dir DIR --mode MODE      # the ONE front door
python3 57-social-media-in-a-box/scripts/prove_bands.py <asset.json> [--json] [--kind K]
python3 57-social-media-in-a-box/scripts/prove_bands.py --self-test
bash 57-social-media-in-a-box/verify.sh                                            # the full read-only self-verify gate
```

Exit 0 = PASS. Exit 2 = one or more auto-fails (fail-closed). Exit 3 = usage/IO (still fail-closed). Exit 4 = front-door-nonce mismatch (a direct orchestrator call).

## Section 3 — Independence + client-runtime

Every QC stamp is written by a reviewer who is not the author (verifier != author). The provers themselves are provider-neutral Python and call no model and no social provider — they run identically on the operator box and on a client box. The shipped engine on a client box NEVER uses Anthropic / `claude-*` models or operator keys; generation + adversarial verify run on the client's own strongest configured provider chain, posting GHL-direct through the client's own Private Integration Token. There is NO n8n and NO Airtable at runtime.
