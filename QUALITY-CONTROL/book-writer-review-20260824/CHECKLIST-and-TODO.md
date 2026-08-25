# CHECKLIST + TODO — Book Writer (Skill 53) end-to-end fix — 2026-08-24

Spec: SPEC-book-writer-fixes.md · Ledger: LEDGER.md · Backup: backups/53-book-writer-pre-fix/

## TODO — in flight now

- [ ] fix-engine: orchestrator + entry fixes (11 items + evidence_root ×3)
- [ ] fix-provers: prover suite + verify.sh fixes (12 items + mc_board pin + webhook pattern)
- [ ] fix-docs-board: docs/manifest/board/CC fixes (9 items + deep-checks docstring)
- [ ] Central verification of every agent edit
- [ ] ENGINE-PIN re-mint
- [ ] Full green battery (verify.sh, 18 broken variants, all self-tests, golden idempotency)
- [ ] Sonnet QC pass; residual loop until clean
- [ ] Release stamping: 1.3.0 bump, README, CHANGELOG, annotated tag
- [ ] Batch merge scoped to book-writer paths + 2 CC files

## FLAGGED — need TREVOR's GO (byte-locked shared tone-core, touches Skills 52/53/54)

- [ ] Remove forbidden "pick a well-known person" instruction from prompts/04-tone-style-1/user.md:12 + wire na_autopick resolver (coordinated 3-skill re-pin)
- [ ] Typo "to modeo" → "to model" (same coordinated edit)

## UNDETERMINED — operator follow-up

- [ ] Live n8n factories 4d50PNmVOyE9GJWz / KF6PCxzSzKWeOwN6: still firing on main.blackceoautomations.com? Not provable from this repo.

## FIXED (updated as verified)

- [x] QC catch (lead, 2026-08-25): middleware.ts `/^\/api\/tasks\/[^/]+$/` entry REVERTED — it excluded the route from the same-origin CSRF passthrough (middleware.ts:523), breaking board UI PATCHes (MissionQueue.tsx:572 status moves, TaskModal.tsx:446 SOP attach → 401 everywhere) and 503ing boxes with no WEBHOOK_SECRET via Gate A. Route has no route-level HMAC (unlike /status), so DATA-09-family membership was wrong anyway. External mc_board PATCH authenticates fine via its Bearer at Gate B (:595). Proof: middleware-same-origin-board 27/27 PASS post-revert; bypass-replay 4 fails pre-exist at HEAD (stash round-trip). Residual stays documented U052/MR-23 OPEN posture.
- [x] All fix-wave items from LEDGER.md (fix-engine 10+2, fix-provers 12+11b/11c, fix-docs-board 9+8b) applied + green battery (verify.sh rc=0, 18/18 broken rejected, self-tests exit 0, tsc clean)
- [x] Golden PROCESS-CERTIFICATE re-stamped under corrected measurement (781e41c9…); ENGINE-PIN re-minted v2 framing (71608e63…); model-map.json tiers filled; anon-tokens.txt shipped in golden run/checkpoints
