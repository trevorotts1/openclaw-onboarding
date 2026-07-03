# SOP-SOCIAL-02: RUN THROUGH THE ONE FRONT DOOR

**Cluster:** Social-Media-Craft Rules (`universal-sops/social-media-craft/`)
**Master authority:** `SOCIAL-PIPELINE-MANIFEST.json` + `57-social-media-in-a-box/SOCIAL-MANIFEST.json` + `57-social-media-in-a-box/modes.md`
**Owning role:** Director of Social Media (department-lead authority for `clean` rollback)
**Stage:** P0-PREFLIGHT -> P8-PLANNER-WRITEBACK (mode-selected phase subset, walked IN ORDER)
**Produces:** `delivery/PROCESS-CERTIFICATE.json` (+ the mode's working artifacts)
**Gates this stage satisfies:** AF-SM-PREFLIGHT-*, AF-SM-DISCOVERY-DRIFT, AF-SM-ENGINE-HASH-PIN, AF-SM-POST-BYPASS, AF-SM-CONTENT-MISSING, AF-SM-PROCESS-INTEGRITY

---

## 0. WHY THIS SOP EXISTS

There is exactly ONE way to run the engine, and it is the ONE sanctioned entry. Every mode — the weekly run, a single day, a carousel, a fold (podcast/newsletter/blog/engage), a creative lane (brief/campaign/client-copy/reactive) — goes through the same door with the same DEPS / BYPASS-SCAN / HASH-PIN gates, the same run-scoped nonce, the same fail-closed phase machine, and the same signed certificate. A direct orchestrator call (bypassing the door) exits 4.

## 1. THE ONE FRONT DOOR

```
bash 57-social-media-in-a-box/social-media-entry.sh --run-dir DIR --mode MODE
bash 57-social-media-in-a-box/social-media-entry.sh --mode MODE --plan     # print the phase plan (gates still run)
```

Never call `run_social_media.py` directly (front-door-nonce mismatch -> exit 4). Never hand-roll a poster in the run directory (`AF-SM-POST-BYPASS` via BYPASS-SCAN). The engine hash must match `ENGINE-PIN.sha256` (`AF-SM-ENGINE-HASH-PIN`).

## 2. THE MODE-SELECTION TABLE (§3)

| Mode | Owner role | What it does |
|---|---|---|
| `week` | director-of-social-media | Full P0->P8 weekly run; config-enabled folds fan out (P9 newsletter / P10 blog / P11 podcast / P12 engage) as their own certified runs. |
| `day` | director-of-social-media | Single-day regenerate + publish. |
| `carousel` | social-media-graphics-specialist | 10-slide FB/IG or 9-slide LinkedIn-PDF (`postAsPdf:true`). |
| `video` | director-of-social-media | Sora 25.0s lane (`--narrated` -> DEFERRED v0.3.0). |
| `podcast` | director-of-podcast | Script -> Fish-Audio S2 -> ffprobe bands -> Podbean + 1400x1400 cover. |
| `newsletter` | email-campaign-strategist | Weekly social-week digest via GHL Campaigns (subject <=60 / preview <=120). |
| `blog` | content-marketing-strategist | Day-7 long-form via GHL blog (LeadConnector `blogs.write`). |
| `engage` | community-manager | Read-only 7-day metrics poll -> anomaly report (SOP-05). |
| `plan` | content-marketing-strategist | Planner create / theme-sync / append only. |
| `clean` | director-of-social-media | GHL post rollback (date-range + status scoped) — department-lead authority. |
| `brief` / `campaign` / `client-copy` / `reactive` | see SOP-03 | The M1-M4 creative lanes. |
| `twitter` (publisher sub-mode) | twitter-x-specialist | X/Twitter via the client's GHL PIT (C1); inside `week`/`day`. |
| `syndicate` | director-of-social-media | DEFERRED v0.4.0; fails closed (`AF-SM-DEFERRED`). |

## 3. PREFLIGHT IS FAIL-CLOSED (P0)

The run does not begin until `preflight_gate.py` PASSES: Kie.ai credits >= 200, OpenRouter balance >= $5, GHL PIT valid, all required config fields present, status == Paid, AND the C2 live connected-accounts reconcile (config platforms enum vs the live GHL accounts — both drift directions BLOCK; a deliberate exclusion is honored only via the logged `platformsExcluded` list). A FAIL emits a labeled failure report + the configured notification and blocks the run (`sys.exit 2`). Owner Q&A about publish scope is answered from this live reconcile, never a memorized list.

## 4. GRACEFUL SKIPS ARE NOT FAILURES

A fold whose dependency is unconfigured degrades to a LABELED skip, never a band failure — e.g. unconfigured Fish-Audio/Podbean emits `{"deferred": true}` recorded as `PODCAST_DEFERRED`. A capability deferred to a named later version (`syndicate`, `--narrated`, persona/memory adapters) fails CLOSED with a clear "deferred to vX.Y.Z" message, never a silent no-op; baseline config-carried behavior is never blocked meanwhile.

## 5. HAND OFF TO VERIFY

A mode that mints a certificate hands to SOP-04: `done` is claimed ONLY from the certificate PLUS a live GHL post-listing. The read-only `engage` mode mints no certificate — it hands to SOP-05.
