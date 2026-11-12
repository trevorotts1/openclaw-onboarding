# PD-093 — BUILD REPORT

**Unit:** PD-093 · "An assembly procedure that can be followed" · Severe · logic
**Lane:** FL24 · **Branch:** `pd/fl24-role-procedures-c`
**Worktree:** `/Volumes/mac mini m4/swarm-contract/pd-fix/worktrees/onboarding/FL24`
**Base:** `579c937ae` (PD-094's accepted head; branch was reset to it before any edit)
**Build commit:** `66bf69c97eb655f2a9bcac2f4893d2141401821c`
**Report commit:** see the commit that carries this file (parent is the build commit)
**Acceptance row built:** A1

---

## 1. Reading of the engine (the row's first instruction)

| Question | Answer found in the repo |
|---|---|
| How is P8-ASSEMBLE dispatched? | `universal-sops/presentation-slide-craft/PIPELINE-MANIFEST.json:1337-1367` — `P8-ASSEMBLE`, order 8, `owning_role: pptx-assembly-specialist`, `produces_artifact: "*-FINAL.pptx"`, `executor.kind: "agent"`, `consumes: ["renders/slide-*.png", "working/deliverables/PRESENTERS-SPEECH.md"]`. |
| Is it still an agent step (decision D-12 unanswered)? | **Yes.** `executor.kind` is `"agent"`; there is no `cmd`. This is the branch the consolidation amendment tells me to write for. |
| What does the runner do on `--phase P8-ASSEMBLE`? | `scripts/run_signature_deck.py:2740` — runs `pre_assembly_harmony_checkpoint(run_dir)`, then falls through to the generic non-render branch (`run_signature_deck.py:3106-3155`): verifier `phase_verifiers.verify("P8-ASSEMBLE")` (`phase_verifiers.py:3998` → `_verify_assemble`, `phase_verifiers.py:1496`), then `attest_phase(...)` once `*-FINAL.pptx` is present. |
| Who actually assembles? | `build_deck.py:14749` calls `assemble_pptx(...)` (defined `build_deck.py:3682`) inside the **render** subprocess dispatch (`run_signature_deck.py:3339`). The deck is copied to `bundle_dir / f"{deck_slug}-FINAL.pptx"` (`build_deck.py:14800`). |
| Where does the deck land? | `bundle_dir` = the `--out <dir>` argument (`build_deck._resolve_bundle_dir`, `build_deck.py:12677`). The manifest's P4-RENDER cmd passes `--out {run_dir}/working/deliverables` (`PIPELINE-MANIFEST.json:1161`); the bundle-gate phase consumes `working/deliverables/{deck_slug}-FINAL.pptx` / `.pdf` (`PIPELINE-MANIFEST.json:2036-2037`). |
| What command does the engine accept for a phase? | `scripts/presentation-canonical-entry.sh` — usage block lines 99-127 (`--run-dir`, `--slides`, `--out`, `--phase`); direct `python3 run_signature_deck.py` is structurally denied by the front-door nonce (`run_signature_deck.py:2659-2676`). |
| Rendered PNGs live where? | `build_deck._gather_rendered_pngs` (`build_deck.py:8571`) → `run_dir / "renders"`, glob `slide-*.png`. |
| Presenter speech lives where? | `build_deck.discover_speech_chunks` (`build_deck.py:2843`) → first candidate `working/deliverables/PRESENTERS-SPEECH.md`. |

## 2. Files changed (both inside the unit's owned paths)

| File | Δ |
|---|---|
| `23-ai-workforce-blueprint/templates/role-library/presentations/pptx-assembly-specialist.md` | +45 −36 |
| `23-ai-workforce-blueprint/templates/role-library/presentations/sops/pptx-assembly-specialist-sops.md` (mirror, regenerated) | +40 −31 |

Every row of the unit is implemented in both files except the header row (blocked — §6).

### Row-by-row

| Row | Before | After |
|---|---|---|
| start condition | `**When to run:** Phase 6 -- after delivery_verified: true in media_library.json.` | `**When to run:** when the engine dispatches P8-ASSEMBLE (its inputs are renders/slide-*.png and working/deliverables/PRESENTERS-SPEECH.md).` |
| the three inputs | `working/media-library/slide-NN.png`, `working/copy/presenter_notes.json`, `working/copy/mission_prd.json` | `renders/slide-*.png`, `working/deliverables/PRESENTERS-SPEECH.md`, `working/copy/slides.json` |
| step 1 | `ls working/media-library/*.png \| wc -l` vs `slide_count_final` | Python one-liner listing `renders/` and comparing to rows in `slides.json` (tested — §5) |
| steps 3 / 3a | `HALT: delete it and route …` | `HALT and report it to the Director; do not delete it. Route …` |
| step 5 | ``Run `python3 scripts/run_signature_deck.py …` (P8-ASSEMBLE).`` | `bash scripts/presentation-canonical-entry.sh --run-dir <run-dir> --slides working/copy/slides.json --out out.pptx --phase P8-ASSEMBLE` + the mandated sentence `When the engine runs this step by script, this phase runs no command of yours.` |
| deck paths | `output/[DECK_SLUG].pptx` / `.pdf` (12 + 10 occurrences in the role file, 8 + 6 in the mirror) | `working/deliverables/{deck_slug}-FINAL.pptx` / `-FINAL.pdf` — **every** occurrence, including the SOP 9.2 commands, the Outputs lists, Gate 6 and the Good-Output example |
| SOP 9.2 step 3.b | two sentences on native overlays | deleted (sentence 1: "Native text overlays added in SOP 9.1 …"; sentence 2: "when overlays were applied natively (SOP 9.3 / 9.4) …") |
| header | `(manifest_version 75, 56 phases)` | **NOT changed — BLOCKED, see §6** |

Deliberate in-file coherence edits, all forced by the row above (named here so QC sees them as
intentional, not as tidying):

1. `output/` **directory** references that the deck used to sit in were retargeted to
   `working/deliverables/` so the commands that write next to the deck still do:
   `--outdir output/` ×2, `pdftoppm … output/pdf-pages/slide` (×3 refs),
   `output/render_log.json` (×2), `os.makedirs("output", …)` ×1,
   "exist at `output/`", "`output/` files are ready", and the Good-Output `render_log.json`
   example (which named `output/enrollment-on-autopilot.pptx|pdf`).
2. Two further prose sites carried the same "delete the overlay file" instruction as steps 3/3a
   and would have contradicted them: the archival bullet (role line 139) and the Garbled-text
   remedy paragraph (role line 242). Both now say "HALT and report it to the Director; do not
   delete it".
3. The reference python snippet's `raise SystemExit(...)` message (role line ~182) said
   "Delete it and re-prompt/re-seed"; changed to the same report-don't-delete wording for the
   same reason. **Note:** the shipped gate's own message still says delete — see §7 finding F1.
4. Mirror header marker `(manifest_version 70, 53 phases)` → `(manifest_version 75, 56 phases)`
   (the mirror was two revisions stale; it is not covered by GATE 7's `VERSION_MARKER_FILES`,
   and leaving it stale would have made the mirror disagree with its source on a line I touched).

## 3. Mirror regenerated (A1)

Role Section 9 extracted and diffed against the mirror's Section 9 (both files post-edit):

```
hunks: 1   removed: 0   added: 60
218a219,278
```

The **only** remaining difference is the mirror's extra `### SOP 9.5 -- Governed Motion Audit
(P8.15-MOTION, Skill 72 MG-036)` block (60 lines). That section is **pre-existing drift** — it
was in the mirror before this unit and is **not in the role file**. No row of PD-093 authorises
deleting it, so it is preserved and reported, not removed.

## 4. Walk-through table (A1: every step maps to a real file or command)

| SOP step | Maps to | Verified how |
|---|---|---|
| 9.1 start condition | `PIPELINE-MANIFEST.json:1337` (`P8-ASSEMBLE`, `executor.kind=agent`), consumes `renders/slide-*.png` + `working/deliverables/PRESENTERS-SPEECH.md` | read manifest |
| 9.1 step 1 | command: the one-liner as printed; files `working/copy/slides.json`, `renders/slide-*.png` | executed on a fixture, 3 cases (§5) |
| 9.1 step 2 | `working/copy/presenter_notes.json` — **RESIDUAL, see §7 F2** | — |
| 9.1 step 3 | gate `build_deck._chk_no_overlay` (`build_deck.py:8161`) | read code |
| 9.1 step 3a | `build_deck.assemble_pptx` (`build_deck.py:3682`), sole call site `build_deck.py:14749` | read code |
| 9.1 step 3b | `working/deliverables/` per `PIPELINE-MANIFEST.json:2036-2037` and `build_deck.py:14800` | read manifest + code |
| 9.1 step 5 | command: `scripts/presentation-canonical-entry.sh` (usage lines 99-127; flag parse 141-170; dispatch `cmd+=(--slides "$SLIDES" --out "$OUT" --phase "$PHASE")` line 1425); phase branch `run_signature_deck.py:2740`; attestation `run_signature_deck.py:3149` | read code |
| 9.1 step 6 | `working/deliverables/{deck_slug}-FINAL.pptx` (`build_deck.py:14800`) | read code |
| 9.1 step 7 | python-pptx readback of that pptx; AF-OVERLAY-DELIVERED structural guard in `assemble_pptx` | read code |
| 9.1 step 8 | notify only; `delivery/` untouched (Delivery Concierge SOP 9.0) | doctrine unchanged |
| 9.2 step 1-7 | `soffice --headless --convert-to pdf --outdir working/deliverables/ …`; `pdftoppm`; `working/deliverables/render_log.json`; Gate 6 | **RESIDUAL, see §7 F3** |

## 5. Exact commands run and results

All temp files under `/Volumes/mac mini m4/swarm-contract/pd-fix/tmp`; all fixtures made with
`mktemp -d -p "$TMPDIR"`. Scratch: `…/pd-fix/scratchpads/fl24-role-procedures-c/`.

```
# base
git -C <worktree> fetch origin pd/fl24-role-procedures-c      -> 579c937ae present
git -C <worktree> reset --hard 579c937ae                      -> HEAD is now at 579c937ae

# edit (asserting the occurrence count of every replacement)
python3 -I …/scratchpads/fl24-role-procedures-c/apply_pd093.py <role>.md          -> WRITTEN
python3 -I …/scratchpads/fl24-role-procedures-c/apply_pd093.py <sops>.md          -> WRITTEN
  role:  12x output/[DECK_SLUG].pptx, 10x .pdf, 8 semantic edits
  mirror: 8x output/[DECK_SLUG].pptx,  6x .pdf, 8 semantic edits

# narrow gate for the file GATE 7 grades
python3 -I scripts/ci/phase_doc_sync.py --check
  -> PHASE_DOC_SYNC_PASS: every phase table and version marker matches
     manifest_version 75 (56 phases).   rc=0     (run before and after the edits)

# the rewritten step-1 one-liner, executed verbatim on a fixture
slides.json = 3 rows, renders/slide-01..03.png   -> "rows=3 renders=3" rc=0
one render removed                               -> "rows=3 renders=2" rc=1
{"slides":[2 rows]} + 3 renders                  -> "rows=2 renders=3" rc=1

# four post-apply one-off patches (each asserted its single occurrence)
mirror step 8  "`output/` files are ready"            -> "`working/deliverables/` files are ready"
role Good-Output example output/enrollment-on-autopilot.pptx|pdf
                                                      -> working/deliverables/enrollment-on-autopilot-FINAL.pptx|pdf
mirror marker  "(manifest_version 70, 53 phases)"     -> "(manifest_version 75, 56 phases)"
snippet message "Delete it and re-prompt/re-seed"      -> "HALT and report it to the Director; do not delete it.
                                                          Re-prompt/re-seed …"   (role + mirror)

# mirror parity
diff role-Section-9 mirror-Section-9             -> 1 hunk, 0 removed, 60 added (SOP 9.5 only)

# residue scan
grep -n "Delete it|delete it," <both files>      -> no matches (rc=1)
grep -n "output/" <role>                         -> only the Common-Mistakes row 3 and
                                                    the retargeted working/deliverables/ lines
```

No full suite, no server, no browser was run (per the room's testing rule).

## 6. BLOCKED row — the header

The row says: *"fix the header to `manifest version: read it from the file`"*.

**Not implemented. Doing so breaks a live CI gate and the repair is outside this unit's owned
paths.**

- Marker site: `23-ai-workforce-blueprint/templates/role-library/presentations/pptx-assembly-specialist.md:123`
  (`(manifest_version 75, 56 phases)`).
- Gate that owns it: `scripts/ci/phase_doc_sync.py`
  - `VERSION_MARKER_FILES` includes `…/pptx-assembly-specialist.md` — **line 83**
  - `VERSION_MARKER_RE = r"manifest_version (\d+), (\d+) phases"` — **line 90**
  - `parsed_report()` — **lines 653-662**: if the regex finds nothing it appends
    `"<file>: no '(manifest_version V, N phases)' marker found at all"` and the gate FAILS.
- It runs in CI as GATE 7 via `scripts/ci/presentations-drift-gates.sh`, fired by
  `.github/workflows/presentations-drift-gates.yml:135` (which lists this exact file as a trigger).

So the required companion change is to remove this file from `VERSION_MARKER_FILES` (and from the
workflow's GATE-7 target list) in `scripts/ci/phase_doc_sync.py` — **both outside PD-093's
`owned_paths`**. Not edited. The marker is left exactly as it is, and GATE 7 stays green.

## 7. Findings outside this unit (not edited — reported)

- **F1 — the engine still tells the operator to delete the evidence.**
  `23-ai-workforce-blueprint/templates/role-library/presentations/scripts/build_deck.py:8176`
  (`_chk_no_overlay`) returns: *"… Delete this file and re-render the affected slide as a single
  composed gpt-image-2-6 image."* The role/SOP now say report-don't-delete. The row only governs
  the role file; the code message is outside `owned_paths`, so it still disagrees with the
  amended procedure. Needs a unit that owns `build_deck.py`.
- **F2 — SOP 9.1 step 2 still checks `working/copy/presenter_notes.json`.**
  The row replaced the three inputs, which drops that file, so step 2 ("Verify
  presenter_notes.json has exactly slide_count_final entries … Do not assemble with missing
  notes") now names something the engine does not read: the notes actually come from
  `working/deliverables/PRESENTERS-SPEECH.md` via `build_deck.discover_speech_chunks`
  (`build_deck.py:2843`) and are best-effort, never a render gate (`build_deck.py:241-251`
  of the role doc). Not a row of PD-093; left verbatim and flagged.
- **F3 — SOP 9.2 still describes a manual `soffice`/`pdftoppm` chain, while the manifest runs it
  as a script phase.** `P8.1-PDF-EXPORT` (`PIPELINE-MANIFEST.json:1371-1390`) is
  `executor.kind: "script"`, `cmd: python3 scripts/pdf_export.py --run-dir {run_dir}`. Not a row
  of PD-093 (only the two overlay sentences in 9.2 step 3.b were in scope).
- **F4 — `{deck_slug}` resolves to `out` on the manifest's own invocation.** P4-RENDER passes
  `{run_dir}/out.pptx` as the positional out-path, and `build_deck.py:14451` takes
  `deck_slug = out_path.stem`, so today's literal artefact is `working/deliverables/out-FINAL.pptx`.
  The doc now matches the manifest's declared path form (`{deck_slug}-FINAL.pptx`,
  `PIPELINE-MANIFEST.json:2036`), which is what the row specified. Reported, not "fixed" here.
- **F5 — the reference python snippet still reads `MEDIA_DIR = "working/media-library"`** while
  the new step 1 counts `renders/` and step 3a says the assembler reads the rendered set. Not a
  row of PD-093; left as-is. This is the last self-contradiction in SOP 9.1 and the next unit
  should take it.

## 8. Hunk attribution

- **PD-094's hunks (do not disturb):** `slide-image-creator.md`, `sops/slide-image-creator-sops.md`,
  `typography-architect.md`, `sops/typography-architect-sops.md` —
  commits `baf3f5dbb`, `bce9febf5`, `e649f7f57`, `579c937ae`. This unit touches **none** of them.
  PD-094's flat-solid / no-gradient / no-glow craft mandates appear nowhere in this diff, and no
  gradient or glow mandate was reintroduced. The word "gradient" still appears only inside the
  RETIRED-appendices and the "decommissioned overlay subsystem" archival text, exactly as PD-094
  left it.
- **This unit's hunks:** the two files in §2 only.
- No hunk belonging to another unit is present in this diff.
