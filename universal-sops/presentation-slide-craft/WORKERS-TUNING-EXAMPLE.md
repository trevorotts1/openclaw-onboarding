# `workers` field tuning example (NOT wired into PIPELINE-MANIFEST.json)

Reference: `PARALLEL-PIPELINE-SPEC.md` (PARALLEL-PIPELINE-ARCHITECT, 2026-08-27),
section 3.4, "Recommended per-phase starting values."

## Status: documentation only, not live

**As of manifest v62, `PIPELINE-MANIFEST.json` declares a `workers` field on
exactly one phase — `P4-PROMPT` (`workers: 12`, the Ticket-4-wired fan-out) —
and none on the rest. The phase count itself is never restated as a literal
here; read it mechanically: `len(PIPELINE_MANIFEST["phases"])` (the count at
this snapshot was 62, per §2.40's generated line in
`23-ai-workforce-blueprint/templates/role-library/presentations/DEPARTMENT-COUNTS-CANONICAL.md`,
which GATE 4 of `scripts/ci/presentations-drift-gates.sh` keeps honest).**
Every phase without an explicit `workers` key resolves to the default (`1`),
which is the literal, unchanged, currently-shipping serial dispatch path
(`presentation_job/dispatcher.py`'s `_dispatch_prompt_phase_serial`, and the
generic single-target dispatch for every other phase). Fleet-wide behavior on
upgrade day is byte-for-byte identical to v22.0.80.

This file is the spec's §3.4 table, kept here as a *reference for Trevor to
opt into by hand, per phase, when he chooses to* — never applied automatically
by any script, roll, or update. Turning a phase's fan-out on means editing
`PIPELINE-MANIFEST.json` directly (adding a `"workers": N` key to that one
phase entry) and restamping `MANIFEST-SOURCE.txt` +
`universal-sops/_content-manifest.json` (`scripts/hash-universal-sops-manifest.py`),
exactly like any other manifest edit.

Only `P4-PROMPT` has the dispatcher-side wiring implemented and tested as of
this writing (Ticket 4). Every other row below fans out to a phase whose
dispatcher-side pool wiring (Tickets 6/7) has **not** shipped yet — setting
`workers` on those phases today would have no effect (the generic dispatch
path does not yet consult `phase.workers` for anything but P4-PROMPT).

## The values (spec Table, §3.4)

| Phase | `workers` | Why | Wired? |
|---|---|---|---|
| `P4-PROMPT` | 50 | min'd to slide count; independent per-slide files, existing `ordinals` hook, biggest single wall-clock win | **Yes (Ticket 4)** |
| `P-IMAGE-QC` | 50 | min'd to slide count; **requires a vision-capable model pin** before enabling (§1 row 20) | No (Ticket 6) |
| `P-PROMPT-QC` | 25 | per-file grading, floor/ceiling already per-file | No (Ticket 6) |
| `P-0.5-RESEARCH` | 20 | needs an explicit topic-partition list authored first | No (Ticket 11-adjacent) |
| `P4-COPY` | 25 | **Wave D only** — requires the harmonize pass (§4.2) to exist first; do not enable before then | No (Ticket 11) |
| `P9.5-NOTES-SYNC` | 25 | text generation only; the PPTX write stays serial | No |
| `P1Q-COPY-QC` | 10 | QC provenance requirement applies (§4.4) | No (Ticket 6) |
| `P-TYPO-QC` | 10 | same provenance requirement | No (Ticket 6) |
| `P9.6-WEBINAR-VIDEO` | 6 (`cpu_count()//2`, cap 8 — **not 50**) | CPU-bound ffmpeg clip loop; box/thermal ceiling, not a provider ceiling (§7.2) | No (Ticket 7 — measure first) |
| `P9-DELIVER` | 8 | Fish Audio concurrency limit is UNVERIFIED — start conservative | No |
| `P9-SPEECH-WEBINAR-INTRO` | 8 | same unverified limit | No |
| `P9.2-GHL-UPLOAD` | 6 | GHL rate limit UNVERIFIED; known Cloudflare-1010-block history on bare `urllib` calls | No |
| `P-SPEECH-QC` | 5 | conditional phase, modest unit count | No |
| everything else | absent (`1`) | not parallelizable — human-paced, single coherent artifact, or already-batched (see spec §1 full table) | N/A |

## Before enabling any row above

1. Confirm the phase's dispatcher-side pool wiring actually exists (only
   `P4-PROMPT` does, as of v22.0.81). Setting `workers` on an unwired phase
   is a silent no-op, not an error — the generic dispatch path does not read
   `phase.workers` at all.
2. For `P-IMAGE-QC`: pin a vision-capable model explicitly for that phase
   before enabling fan-out (see spec §1 row 20 — a text-only model stalls
   silently rather than erroring).
3. For `P9.6-WEBINAR-VIDEO`: run the Ticket 7a measurement pass on the real
   operator box before picking a number. `6`/`cap 8` is a starting estimate,
   not a measured result.
4. For `P9-DELIVER`, `P9-SPEECH-WEBINAR-INTRO`, `P9.2-GHL-UPLOAD`: these
   providers' real concurrency ceilings were **not verified** by the spec
   author (Fish Audio, GHL). Do not raise these numbers without measuring
   against the real API first.
5. Run the Ticket 8 proof test (same E2E deck, once at `workers` absent,
   once at the tuned values) on the operator box only — never a client feed
   — before rolling any of this to the fleet.
