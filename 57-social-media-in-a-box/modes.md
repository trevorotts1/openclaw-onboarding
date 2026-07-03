# Modes — Social Media in a Box (Skill 57) — v0.2.0

Sixteen user-facing verbs. Each maps to a phase subset of `SOCIAL-MANIFEST.json` (`modes`), walked
IN ORDER by `run_social_media.py` with **no phase skips**. Always invoke through the ONE sanctioned
entry (same DEPS / BYPASS-SCAN / HASH-PIN gates, same run-scoped nonce, same signed certificate):

```
bash social-media-entry.sh --run-dir DIR --mode MODE          # run
bash social-media-entry.sh --mode MODE --plan                 # print the phase plan (gates still run)
```

## Engine modes (v0.1.0 — unchanged)

| Mode | Phases | What it does |
|---|---|---|
| `week` | P0→P8 | Full weekly run: preflight → theme/plan → content → contract+bands → media → scrub → certificate → publish → planner write-back. |
| `day` | P0,P2,P3,P4,P5,P6,P7 | Single-day regeneration + publish (no planner sheet create). |
| `carousel` | P0,P3,P4,P5,P6,P7 | Standalone 10-slide FB/IG or 9-slide LinkedIn-PDF carousel engine. |
| `video` | P0,P3,P4,P5,P6,P7 | Standalone Sora 25.0s video lane. (`--narrated` → DEFERRED to v0.3.0.) |
| `podcast-cover` | P0,P4,P5,P6 | Podcast **cover** art only (1:1). |
| `plan` | P0,P1,P8 | Planner only: create sheet / sync theme-of-week / append the 20-column row. |
| `clean` | P0,P7 | Bulk rollback: delete the date-range + status-filtered posts in the client's GHL location. |

## Fold modes (v0.2.0 — merge plan C3–C6)

Each fold is a first-class standalone mode AND runs as part of the weekly cadence when its config
toggle (`podcast`/`newsletter`/`blog`/`engage`) is set — each minting its own signed certificate.

| Mode | Phases | What it does |
|---|---|---|
| `podcast` | P0,P11,P5,P6 | C3: prompt 17 → 1,500–2,000-word `[emotion]`-tagged script → Fish-Audio S2 → ffprobe 600–900 s / ≥128 kbps → Podbean + 1400×1400 cover. Unconfigured → `PODCAST_DEFERRED` labeled skip, never a failure. |
| `newsletter` | P0,P9,P5,P6 | C4: prompt 18 → subject ≤60 / preview ≤120 / table-based inline-CSS HTML → GHL Campaigns, Tue 9 AM client-timezone. |
| `blog` | P0,P10,P5,P6 | C5: prompt 19 → title ≤80 / meta ≤160 / body 700+ words → GHL blog (LeadConnector `blogs.write`). |
| `engage` | P0,P12 | C6: read-only 7-day likes/views poll → anomaly report to `notifyChannel`. NO posting → never blocks a publish run. |

## Creative modes (v0.2.0 — the client steers, the engine still certifies; M1–M4)

| Mode | Phases | What the client controls / what stays enforced |
|---|---|---|
| `brief` | P0,P1,P2-BRIEF,P3–P8 | M1: "Do it THIS way this week." The brief (theme/angle/hooks/format/voice/arc/visuals) enters through the un-hashed CREATIVE BRIEF user-message slots and overrides every default. Bands (with logged overrides), scrub, certificate, de-dup, GHL-only posting all stay enforced. |
| `campaign` | P0,P2-BRIEF,P3–P8 | M2: one-off / off-template push (flash sale, launch takeover) with its own asset list + schedule + planner row. Off-**template**, never off-**spine**. |
| `client-copy` | P0,P2-INGEST,P3–P7 | M3: the engine posts the client's finished copy **VERBATIM** — `AF-SM-CLIENT-COPY-MUTATED` hash-guarantees the published bytes match the supplied copy (modulo a programmatic ctaLink append). It packages/de-dupes/certifies but NEVER authors. |
| `reactive` | P0,P2-BRIEF,P3–P7 | M4: trend / newsjack single post — a fast lane, not a loose lane. Full form+safety chain incl. de-dup against the scheduled week. |

Flags on `week`/`day`: `--brief FILE` (tilt the default engine) / `--override FILE` (client-exact band
numbers — logged or the run fails via `AF-SM-OVERRIDE-UNLOGGED`).

## Deferred (fail-closed; merge plan C8/C9/C10/C11)

| Request | Deferred to | Stub |
|---|---|---|
| `--mode syndicate` (WordPress/Medium/Substack/YouTube-direct) | v0.4.0 | phase `P-SYNDICATE-DEFER` → `AF-SM-DEFERRED` |
| `video --narrated` (or config `narratedVideo:true`) | v0.3.0 | `defer_stub.py --capability narrated-video` |
| config `personaSource: adapter` | v0.5.0 | persona-adapter (config baseline works today) |
| config `memoryFeed: true` | v0.5.0 | memory-adapter (theme-of-week log half already folded) |

Each fails CLOSED with a clear "deferred to vX.Y.Z" message — never a silent no-op; baseline
config-carried behavior is never blocked meanwhile.

## The 12 injection points (creative layer)

I1 theme of week · I2 wildcard/queued themes · I3 brand voice/tone/avatar · I4 custom hooks/angles ·
I5 one-off campaigns · I6 client-supplied copy · I7 seasonal/reactive · I8 per-platform voice ·
I9 visual art direction · I10 persona layer · I11 narrative-arc controls · I12 CTA/comment mechanics.
The client interjects in natural language on any channel; intake normalizes into the right slot,
never floors/caps a stated number (the client gets EXACTLY what they ask for), never requires field
names. "Just this week or from now on?" is asked once (run-level auto-reverts / config-level persists).

## Gate order within a full `week`

```
P0 preflight_gate.py  →  P1 planner  →  P2 content engine
  →  P3 validate_contract.py + prove_bands.py  →  P4 media core + ledger.py QC loop
  →  P5 scrub_gate.py  →  P6 build_manifest.py (signed certificate; ZERO-Anthropic proof + creative block)
  →  P7 publisher (GHL-direct + no-double-post de-dup)  →  P8 planner write-back
```

Any phase's non-zero exit BLOCKS everything downstream (fail-closed). The publisher (P7) physically
cannot run without the P6 certificate. `done` is claimed only from the certificate **plus a live GHL
post-listing verify** — never the poster's own return value.
