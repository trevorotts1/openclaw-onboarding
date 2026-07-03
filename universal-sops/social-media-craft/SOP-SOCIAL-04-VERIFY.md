# SOP-SOCIAL-04: VERIFY — THE CERTIFICATE PLUS A LIVE GHL LISTING IS THE ONLY `done`

**Cluster:** Social-Media-Craft Rules (`universal-sops/social-media-craft/`)
**Master authority:** `MASTER-SOCIAL-QC-AUTOFAIL-RULESET.md` + `57-social-media-in-a-box/scripts/build_manifest.py` + `57-social-media-in-a-box/scripts/scrub_gate.py`
**Owning role:** QC Role -- Social Media (verifier != author)
**Stage:** P5-SCRUB -> P6-MANIFEST -> P7-PUBLISH (independent verify)
**Produces:** `working/qc/scrub_report.json`, `delivery/PROCESS-CERTIFICATE.json`, `working/publish/publish_results.json`
**Gates this stage satisfies:** AF-SM-PROCESS-INTEGRITY, AF-SM-NOANTHROPIC, AF-SM-PROVENANCE-MISSING, AF-SM-PROMPT-HASH, AF-SM-PUBLISH-RESULT, AF-SM-PUBLISH-UNPROVEN, AF-SM-DOUBLE-POST

---

## 0. WHY THIS SOP EXISTS

QC is a deterministic MEASURER, not an agent self-score, and the verifier is never the author. The publisher physically cannot run without a complete signed manifest, and `done` is claimed ONLY from the certificate PLUS a live GHL post-listing verify — never the poster's own return value.

## 1. THE SIGNED PROCESS CERTIFICATE (P6)

`build_manifest.py` mints `delivery/PROCESS-CERTIFICATE.json` only when: every gate PASS is recorded, a per-call provenance record exists (a zero-Anthropic proof is a lie without it), every model/provider used shows ZERO Anthropic (`AF-SM-NOANTHROPIC`), shipped prompt hashes match the canonical pin (`AF-SM-PROMPT-HASH`), and — in agency mode — no two roster entries share a PIT/locationId (`AF-SM-AGENCY-SHARED-PIT`). A deploy/publish requested without the signed certificate, or after a skipped phase, is `AF-SM-PROCESS-INTEGRITY`. The certificate SHA is deterministic (computed over the ordered phases + identity, not the clock).

## 2. INDEPENDENT `done` — CERT + LIVE GHL LISTING (P7)

Each publisher sub-mode posts via `services.leadconnectorhq.com/social-media-posting/{locationId}/posts` with the CLIENT's own PIT and returns the normalized `{platform, success, totalPosts, processedAccounts, errors}` contract (`AF-SM-PUBLISH-RESULT`). `done` is proven by reconciling the certificate against a LIVE GHL post-listing (`AF-SM-PUBLISH-UNPROVEN` if the publisher ran without a complete upstream manifest). The reviewer that stamps QC is not the agent that authored the run.

## 3. THE ADVISORY VOICE REPORT (WARN, NEVER BLOCK)

Triage `working/qc/voice_report.json` (emoji count, generic-CTA phrases, comment-similarity) as ADVISORY: it warns and NEVER blocks a publish. You read the provers' verdicts; you never re-judge content — the provers are the QC of record (C12). Exact comment duplication is blocked by the fingerprint (a safety gate), not by taste.

## 4. DE-DUP BLOCK HANDLING — THE RE-POST TOKEN (§4.4)

A P7 `AF-SM-DOUBLE-POST` block means the same `(platform, content_sha256)` is already posted/scheduled in the lookback window, or the `(platform, scheduled_slot)` is occupied — reconciled against the live GHL listing. It clears ONLY by a logged owner-approved re-post token recorded on the certificate: the client CAN re-post identically by saying so; the engine never does it by accident. `clean` remains the rollback (date-range + status scoped, department-lead authority).

## 5. THE SCRUB SCREEN (P5, DEFENSE-IN-DEPTH)

Before the certificate, `scrub_gate.py` screens generated content AND shipped bytes for ZERO client-name tokens, ZERO secret patterns, ZERO n8n `pinData`, and ZERO Anthropic identifiers. The same zero-Anthropic detector is re-run at P6, so a rogue id is refused twice. Never print a matched secret value — confirm the finding and BLOCK.
