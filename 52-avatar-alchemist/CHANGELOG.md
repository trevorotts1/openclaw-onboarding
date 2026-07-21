# Changelog — Skill 52 (Avatar Alchemist)

## 1.5.3 — 2026-07-21 — T0-28: book routing is acknowledgement-based, not directory-based

### Fixed
- **`book-routed` was written because a DIRECTORY existed.** `scripts/aa_director.py::_version_gate`
  decided `route = "book-routed" if "AF-AV-BOOK-SKILL-MISSING" not in codes else "book-parked"`,
  and that code came from `aa_intake_gate.verify(intake, book_present)` where `book_present`
  was a glob for a sibling `53-*book*` folder. **No target was ever invoked.** Skill 53
  never saw the intake. The durable `<run-dir>/route.json` that downstream automation reads
  recorded a completed handoff for a book run that had never begun — and the forwarded
  intake would not have satisfied the target's own entry gate anyway.
- `aa_director.py` now forwards the intake to the target's own intake-accept command
  (`53-*book*/scripts/bw_intake_accept.py`), reads the receipt from **that process's
  stdout** rather than from a file that could be pre-planted, and honours it only when the
  digest the target signed equals the sha256 of the bytes this process forwarded.
- `route.json` now records the truth in four states, with an explicit `accepted` boolean:
  `book-routed` (target accepted, receipt attached), `book-rejected` (target refused,
  its own `AF-BK-*` reasons carried through), `book-pending` (target present but not
  consultable — no accept command, launch failure, timeout, unparseable answer, or a
  receipt bound to different bytes), `book-parked` (no Book skill on this box).
- The exit code is unchanged: every `version=book` outcome remains the hard stop, exit 4.
  What changed is that the durable route no longer claims a handoff that did not happen.
- `AA-GATE-HASHES.json` re-pinned for the changed `scripts/aa_director.py`.

### Proof
`tests/unit/book-routing-requires-a-receipt.test.py`, hermetic (staged skill trees in a
tempdir). Measured on the branch:

    aa_director.py at origin/main  ->   3 passed,  9 failed
        an incomplete intake was recorded "book-routed"
        a Skill 53 with NO accept command was recorded "book-routed"
        a fake target claiming acceptance for other bytes was recorded "book-routed"
    aa_director.py fixed           ->  12 passed,  0 failed


## 1.5.0 — 2026-07-05 — Wave-2 floor alignment + repairs default flip (train W2-52-avatar)

Train **W2-52-avatar**. Fix IDs: **FIX-XC-04g** (R2), **FIX-AVATAR-04** (R3), **FIX-AVATAR-05**.
Ratified rulings R2/R3 (Trevor, 2026-07-05; SACRED-IP sign-off granted for R2).

### Changed — the avatar floor schism is closed (FIX-XC-04g / R2)
- **MASTERDOC.md is the single numeric source** for the per-stage floors; `AA-PIPELINE-MANIFEST.json`
  `stages[].floors` is the machine mirror aligned to it. `aa_build_check.py`'s docstring no longer
  restates a third, conflicting floor set — it points at the manifest with no numbers.
- **Word floors raised to the SACRED bands:** `01` ≥3,000 · `08` ≥3,000 · `09/11/13` ≥1,500 ·
  `19` ≥5,000 (were 1,800 / 1,500 / 900 / 2,600).
- **Floors added for every previously-floorless non-`_internal` stage:** `03` ≥600 · `15` ≥500 ·
  `16` ≥600 · `17` ≥600 · `10/12/14` ≥400.
- **New `≤550 stripped-char bot-message cap` (`AF-AV-BOTMSG-CAP`)** on stages `19/20/21`
  (manifest `floors.bot_msg_char_cap`): every quoted, single-line sendable bot message must stay
  within the cap. Enforced in `aa_build_check._botdoc_defects` (reused by `aa_qc_cert.py`), declared
  in `AVATAR-MANIFEST.json`, and covered by a new rejecting fixture in the build-check self-test.
- **Both goldens re-authored** to genuinely clear the aligned spec (real, non-repeating authored
  copy, not padding): `examples/golden-lumen-rise/` (repairs ON) and `-live/` (repairs OFF).
- **`AA-GATE-HASHES.json` re-pinned** over the changed manifests/provers/entry.sh.

### Changed — client-run repairs default flipped ON (FIX-AVATAR-04 / R3, RATIFIED)
- A **CLIENT brand run now defaults to source repairs R1–R6 ON** so a delivered package does NOT
  ship the live workflow's known content bugs. Driven by `intake/INTAKE-TEMPLATE.md` `apply_repairs`
  (default `true`) + `aa_intake_gate.py` (`resolve_apply_repairs`, absent ⇒ ON) + `aa_director.py`
  (honors `intake.apply_repairs`; new **`--no-repairs`** forces OFF for fidelity/regression runs).
  `--no-repairs` and `intake.apply_repairs=false` are the two opt-outs; the golden-live is still
  built `--no-repairs`. **R7 (Anthropic ban) is unconditional, never a repair.**

### Fixed — P3 bundle (FIX-AVATAR-05)
- **Nonce consumption is no longer best-effort** (`aa_delivery_gate.py`): if the single-use
  front-door nonce cannot be consumed (read-only run dir / racing consumer / FS error), the
  certificate is **WITHHELD** with `AF-AV-CERT-NO-FRONT-DOOR` instead of the OSError being swallowed
  — a nonce that cannot be retired could otherwise be replayed to mint a second cert. New
  read-only-run-dir self-test proves the withhold.
- **`entry.sh` Anthropic scan tightened** (`:29–31`): dropped the `grep -v '/anthropic|claude/i'`
  doc-literal exclusion (which could hide a real baked id sharing a line with the doc string) and
  scoped the positive pattern to real usable ids (the `qc-avatar-alchemist.sh` pattern). Re-pinned.
- **`HOW-TO-USE.md` truth pass:** the preflight-probe and foreman-dispatch descriptions now match the
  landed behavior (FIX-XC-09f resolve-or-hard-fail; FIX-XC-05b `--execute` + `--dispatch-cmd` seam)
  and the repairs-default statement reflects the R3 flip.

## 1.4.0 — 2026-07-05 — F4.3 deterministic N/A tone-slot auto-pick (train DEP-7)

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

## 1.3.0

Wave-1 merge-train **T-w1-52-avatar** — model-map is finally consumed, preflight
resolves real box providers, and the zero-egress runs gain a mission-control
carding contract.

- **FIX-XC-09f** — `model-map.json` is now **actually consumed** at dispatch time.
  `aa_director.py` loads the box's `model-map.json` (search order `$AA_MODEL_MAP`
  → `<run-dir>/model-map.json` → `<skill-root>/model-map.json`), resolves each
  stage's declared tier (A/B/SEARCH) to the box's **concrete model id** (passed to
  the adapter as the model hint), defaults `--provider-cap` from
  `provider_caps.concurrent` (the fleet Ollama-only ≤3 rule — **never the old
  hardcoded 10**), and records the resolved tier ids + the cap source into
  `RUN-LEDGER.json`. A model-map carrying an Anthropic-shaped tier id is refused by
  the consumer (defense-in-depth, `AF-AV-NOANTHROPIC`). Absent a map, the cap falls
  back to the conservative fleet default (3) and tiers resolve to the abstract
  hint (legacy seam intact). Three new offline self-test legs prove all of this.
- **FIX-XC-09f (preflight)** — `preflight.sh` no longer bakes hardcoded env
  DEFAULTS. It resolves each tier from THIS box's OpenClaw config (explicit
  `AA_TIER_A/B` / `AA_SEARCH` box-derived overrides or an `AA_PROVIDER_PROBE_CMD`
  hook), **hard-fails** when a tier is unresolved (writes no guessed map), validates
  every resolved id against the box's discoverable OpenClaw config, and keeps the
  Anthropic ban. `AA-GATE-HASHES.json` re-pinned after the `aa_director.py` change.
- **FIX-AVATAR-02** — the `scripts/` stay deliberately **zero-egress**, but the
  driving role + SOP now carry a **3-step mission-control carding contract** so a
  multi-hour, 40-stage deliverable is neither board-invisible nor able to skip the
  QC `review` column: (1) intake → `scripts/mc-route.sh marketing "Brand
  Intelligence — <First> <Last>"`; (2) signed QC certificate issued → advance the
  card to `review` (never straight to `done`); (3) `aa_delivery_gate.py
  --verify-cert` PASS → `done`. Card state is always verified by querying the
  Command Center tasks **rows** via `find_dashboard_db()`, never file mtime (WAL
  lag). Added to `brand-positioning-specialist.md §8.1` and
  `universal-sops/avatar-craft/SOP-AVATAR-01 §6`; role-library `_index.json`
  content-hash re-stamped for the edited role + marketing dept.

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
