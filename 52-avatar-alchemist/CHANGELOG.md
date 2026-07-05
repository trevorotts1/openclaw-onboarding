# Changelog — Skill 52 (Avatar Alchemist)

## 1.2.1

DEP-9 doctrine (F4.5) — terminology only, no pipeline/behavior change.

- **Avatar ≠ coaching persona.** Added a terminology callout to `SKILL.md` clarifying that the
  **avatar** this skill builds (subsystem (a) Avatar Intelligence Core) is a **buyer/customer
  persona** — the target-market profile the copy is written *for* — and is NOT the
  **coaching/leadership persona** (the 81-persona `coaching-personas` library matched per task at
  runtime by the persona selector, governed by
  `23-ai-workforce-blueprint/persona-matching-protocol.md`). The tone-style slots are likewise
  distinct. Points to `TERMINOLOGY.md` → "Persona — three distinct meanings". Version bumped to
  keep `SKILL.md` frontmatter and `skill-version.txt` in lockstep.

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
