# Changelog — Skill 52 (Avatar Alchemist)

## 1.3.0 — 2026-07-05 — F4.3 deterministic N/A tone-slot auto-pick (train DEP-7)

Train **DEP-7**. Fix IDs: F4.3.

### Changed
- The shared **tone-writing-core** N/A tone-slot auto-pick is now **deterministic**: the shared
  `shared-utils/tone-writing-core/tone_persona_autopick.py` routes each **N/A** tone slot through
  the ONE shared entry point `shared-utils/persona_for_job.py` (canonical 5-layer selector), so the
  pick is avatar/task-aware, deterministic, and **LOGGED** — replacing the ad-hoc prompt-level
  "choose a well-known person" guess. The persona's Section-4 governance excerpt seeds the tone
  analysis.

### Invariants preserved
- **CLIENT-NAMED tone slots are NEVER touched** (client sovereignty) — the selector is consulted
  for N/A slots only.
- The **4-slot blend** at stage 08 is unchanged; slots are resolved independently.
- The lockstep-synced tone prompt `.md` assets are unchanged (no sync drift); the resolver is an
  additive helper. Skill 53's fictional palette is an explicit fallback tier.

## 1.2.0

Wave-0 merge-train **T-52-avatar-alchemist** — semantic QC leg, real dispatch
loop, entry/token/golden fixes.

- **FIX-XC-05b** — implemented the real foreman **dispatch loop** in
  `aa_director.py` (`--execute`): per-wave/stage it refuses on a missing dep
  receipt, loads + token-resolves the three prompt files, prepends the repairs
  banner, dispatches to the client model via one documented adapter seam
  (`--dispatch-cmd` / `openclaw agent --json`), and writes `artifacts/<sid>.md`
  + an **HMAC-signed** `receipts/G-STAGE-<sid>.json` (foreman key) + a ledger row
  carrying the REAL returned model id. `--resume` skips verified stages; per-stage
  `recovery`/`max_fix_attempts` drive a redo-then-`PARKED.json` loop; stage-02
  completion runs the links gate (`--online-links` on client boxes). A returned
  Anthropic model id parks the run (AF-AV-NOANTHROPIC). Fully self-tested offline
  with a mock adapter.
- **FIX-XC-03d** — added the **semantic QC leg**: a second detached certificate
  `QC-SEMANTIC.json` (`aa_qc_cert.py --semantic`) from an independent verifier
  sub-agent (!= any author) on the client TIER-A model, 10-category OpenClaw QC
  Protocol per artifact, verifier model id G-NOANTHROPIC-checked, transcript
  sha256 embedded, HMAC-signed. `aa_delivery_gate._load_qc_semantic()` now
  requires BOTH certs with semantic ≥ 8.5 (new code `AF-AV-CERT-SEMANTIC`).
- **FIX-AVATAR-01** — `entry.sh` book-skill detection is now a dynamic
  `53-*book*` glob (case-insensitive, mirroring `aa_director`); a `version=book`
  intake on a box WITH `53-book-writer` now routes instead of dying exit 2.
  Added the `verify.sh` regression case.
- **FIX-AVATAR-03** — renamed every generic `{{artifact.upstream}}` token to a
  named `{{artifact.<stage_id>}}` across the 34 large prompts (bots, ad sets,
  top-39, headline copy, landing) and synced `depends_on` for stages 02/20/21/38/39
  so prompt and DAG agree; added the fail-closed `aa_token_lockstep.py` prover
  (membership + coverage) wired into `qc-avatar-alchemist.sh` + `verify.sh`. The
  four shared tone-core prompts (04-07) keep the canonical `{{artifact.upstream}}`
  (byte-for-byte IP shared with skills 53/54) as a SANCTIONED, positionally-
  resolvable token — count must equal `depends_on`.
- **FIX-AVATAR-04** — added `examples/golden-lumen-rise-live/`, the DEFAULT-mode
  (repairs OFF, faithful-to-live) reference run: regression-covered (clears the
  content prover + both QC certs) and visibly graded (semantic below the
  repairs-ON flagship, still ≥ 8.5). RULING R3 (default-flip to `--apply-repairs`)
  is left as a separate Trevor decision.
- Re-pinned `AA-GATE-HASHES.json` (now 11 gates, incl. `aa_token_lockstep.py`).
