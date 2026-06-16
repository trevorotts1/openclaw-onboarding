## [v12.19.0] — 2026-06-16 — fix(presentations): un-bypassable pipeline + canonical renderer + stronger research/QC

- build_deck.py reconciled to ONE canonical renderer (was diverged): demographic-default guard + prompt char-count gates + HOME-relative env paths (from main) UNION 420s poll ceiling + grace window + the PROCESS PREFLIGHT gate (from live). Preflight REFUSES to render/assemble (exit 3) unless the upstream artifacts exist: intake.json (presentation_mode), research brief (research_complete:true), copy_qc_report (Phase 1Q pass). --adhoc-no-process is the only, loudly-bannered override. Closes the shortcut that bypassed the whole pipeline.
- Deep Research Specialist SOP: Categories G–L added (attributable quotes, fact-validation ledger, objection research, social-proof, persuasion-framework, compliance); AF-RESEARCH-GATE required categories extended.
- media-librarian-ghl-updater SOP: GHL folder-creation + slide-PNG upload + final-PPTX upload is now a REQUIRED, GATED step (AF-PIPELINE-COMPLETE), naming build_deck.py as the bypass it catches.

