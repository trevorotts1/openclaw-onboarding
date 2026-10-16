# Authority Map: Skill 72

Read in this order. Load only the stage you are working on.

1. `SKILL.md`: what this skill is, the four delivery modes
   (`powerpoint_graphic`, `vsl_desktop`, `vsl_mobile`,
   `standalone_video`), the one canonical pipeline, route
   boundaries, and the decisions index.
2. `INSTRUCTIONS.md`: the stage-by-stage runbook you follow on every run.
3. `references/intake-and-modes.md`: the intake authority. The mode is resolved before any job setup; this document holds the mode table, the intake record, and the VSL parent handoff.
4. `references/contracts-v2.schema.json`: the canonical V2 contracts. The manifest entrypoint is `references/manifest-schema.json`. Validated worked examples, one job per mode: `assets/examples/`.
5. `references/brand-bible-template.md`: copy per brand, fill in, load on every run.
6. `references/renderer-routing.md` and `references/renderer-capabilities.json`: which adapter renders a scene, and what each adapter is proven able to do on this machine. Readiness is proven by the shared runtime's capability and launch records, not by classification.
7. `references/component-catalog.md`: the typed component registry. C04 through C09 are available for production dispatch; C01, C02, C03, C10, C11, and C12 are registered identities with explicit unavailable reasons, refused by name until their bundles register. The same reference records the shipped seam that the canonical package validators still admit C05 scenes only.
8. `references/approvals-and-gates.md`: the approval gates (design, render, delivery), issuer trust, and the content revisions every approval binds.
9. `references/preview-and-review.md`: the preview model. Previews preserve the composition aspect at full fps; reduced-fps artifacts are labeled `rough_layout_only` and never satisfy the motion gate.
10. `references/review-evidence.md`: the MG-031 review bundle. Coverage is complete-runtime: covered plus omitted accounts for exactly 100 percent of the runtime, and the bundle tool never prints PASS.
11. `references/critique-protocol.md`: the evidence-bound creative rubric (MG-033). Self-approval is refused, there is no minimum round count, correction is capped at five rounds, and a claimed 10 is refused against an uncalibrated reference. Records are validated on write with `scripts/review_rubric.py`; the dashboard renders from the records.
12. `references/technical-qc.md`: the MG-034 technical QC contract. Every check is named PASS, FAIL, SKIPPED_WITH_REASON, or NOT_RUN against the compiled plan; the report at `qc/final-qc.json` is what the delivery gate consumes.
13. `references/audio-policy.md`: the MG-023 audio policy. The resolved plan is computed once at plan load; narration is measured, never assumed; silent and inherited modes produce no narration and need no TTS credential. Provider rules for the Fish Audio narration tooling are in `references/fish-audio-tts.md`.
14. `references/status-and-delivery.md`: status, recovery, and delivery. One task identity from intake to delivery, the status ledger in the job directory, the delivery receipt built from measured facts, and the Skill 47 bridge (`47-movie-producer/scripts/motion_status.py`).
15. Mode producers: `references/powerpoint-packaging.md` for `powerpoint_graphic` (playback inside Microsoft PowerPoint is UNVERIFIED on every platform; the package proves embed structure and hashes), `references/vsl-desktop-handoff.md` and `references/vsl-mobile-handoff.md` for the VSL modes (mobile is genuinely recomposed, never cropped), and `scripts/build_standalone.py` for `standalone_video`.
16. `references/integration-contracts.md`: how presentation decks consume motion components through the existing presentation pipeline (election, authentication, embed, phase, webinar reuse).
17. `references/design-intelligence-bridge.md`: the one legal crossing with Skill 45. A reference goes to a Style Analyst; a style card comes back as analysis only.
18. `references/install-and-migration.md` with `INSTALL.md`: installation, the guarded upgrade transaction, and migration of V1 jobs.
19. `references/untested-alternatives.md`: renderer status reference. Hyperframes and Remotion are the two production adapters of Skill 72 V2. Items still untested (Diffusion Studio, fleet rendering) are listed there with their specific gaps.
20. `references/animation-contract.md` and `references/fish-audio-tts.md`: the legacy compatibility path's scene contract and the Fish Audio provider rules, reached only by explicit choice through migration (`scripts/migrate_manifest.py`). The V1 manifest shape is preserved as `references/legacy-manifest-schema.json` with its example at `assets/example-manifest.json`.
21. `MASTERDOC.md`: integration contract, department ownership, boundaries, and the engine-boundary rules.
22. `QC.md`: the QC checklist behind `scripts/qc.sh` and `bash verify.sh`.
