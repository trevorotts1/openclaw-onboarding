# Ledger / Session-Log Reconciler — Recovery Snapshot

AUTHORITATIVE, machine-derived-from-git-truth recovery source for the Skill 6 (blended persona kanban v2) and Skill 62 (cinematic web funnel engine) builds. Every fact below was independently re-derived from `git` (fetch + ancestry + direct-parent merge-commit match + annotated-tag lookup), never copied from a prior run or from ledger prose. If a build session is lost to a context/session limit, this file is the fastest path back to real state.

**FRESHNESS CONTRACT — verify liveness LIVE, never from this prose.** The reconciler runs on a 10-minute cron on the operator box, but the git-committed copy of this file is only rewritten (and committed) when its SUBSTANTIVE content changes — so an old `Generated` timestamp here does NOT by itself prove the reconciler is alive OR dead. Liveness proof lives on the operator box: `~/ledger-reconciler/recovery-state.md` gets a fresh `Generated` on EVERY pass, and `~/ledger-reconciler/logs/reconcile.log` gets a `run start`/`run end` pair per pass. If the newest `run start` there is older than ~20 minutes, the reconciler is DEAD (check `crontab -l` for the reconcile.sh entry) and every claim below — including the Integrity Alarms — is frozen at the `Generated` time: the alarms were true AT GENERATION but may have been resolved since. (This exact failure happened 2026-07-16: the cron was paused for a defect fix, never re-enabled, and 5 then-true alarms were presented as current for 3 days after every one of them had been resolved by merge.)

Generated: 2026-07-20T03:00:04Z
openclaw-onboarding `origin/main` HEAD: `3f57363a07aa98121043b35870168b40fd2603f3`
blackceo-command-center `origin/main` HEAD: `7d1a247e7f499b99cf43a6e2049ef223bc7143e4`

## INTEGRITY ALARMS — fail-closed (verified-but-unmerged leg mismatches)

No mismatches found this run.

## INTEGRITY FINDINGS — informational (NOT fail-closed mismatches)

**3 finding(s) this run.** Two kinds land here, neither a contradiction: (1) `compound-tag-unconfirmed` -- a compound/modified leg tag row (e.g. "CC (+ONB)", "ONB (+CC endpoint)") has no exact or disambiguated-suffix `skill6-v2/<unit>` branch in the repo its primary leg needs. **This does NOT mean the leg is missing** -- a genuinely complete leg can ship under a branch name with zero discoverable relationship to its own unit id (proven twice: U15's ONB leg inside `skill6-v2/chainA`, U79's CC leg as `u79-gk17-cc-anthology-selfheal-banner`); there is no safe, general way to mechanically discover a non-namespaced branch name. Before resolving such a finding either way, read the unit's own CHANGELOG.md entry AND any OTHER cross-referenced unit's CHANGELOG/spec dependency line. (2) `cross-shipped-leg-verified` -- a both-leg row with no own-named branch in a repo, whose row text cites a carrier branch git PROVES merged into that repo's main (the resolved-U108 shape: its CC leg shipped inside `skill6-v2/U110` by explicit, self-documented design). The merge proof is machine-re-derived; the carrier's content coverage is the human judgment already recorded in the row.

| unit | repo | branch (own name, not found) | kind | shared ledger status |
|---|---|---|---|---|
| U15 | openclaw-onboarding | `skill6-v2/U15` | compound-tag-unconfirmed | verified |
| U79 | blackceo-command-center | `skill6-v2/U79` | compound-tag-unconfirmed | verified (test-proof confirmed) |
| U108 | blackceo-command-center | `skill6-v2/U108` | cross-shipped-leg-verified | verified |

## Skill 6 — openclaw-onboarding (`skill6-v2/*` branches)

| unit | branch | headSha | mergedIntoMain | mergeSha | tag | ledgerStatus | qcScore(prose) |
|---|---|---|---|---|---|---|---|
| U1 | `skill6-v2/U1` | `6a31a7fe` | True | `292f4ee4` | v20.0.17 | verified | 9.35 |
| U10 | `skill6-v2/U10` | `d2c26e1f` | True | `51559d32` | v20.0.60 | verified (auto-reconciled, needs test-proof confirmation) | - |
| U100 | `skill6-v2/U100` | `07031a47` | True | `785dd532` | v20.0.63 | verified (auto-reconciled, needs test-proof confirmation) | - |
| U106 | `skill6-v2/U106` | `c28f75b8` | True | `b5f24e62` | v20.0.61 | verified (test-proof confirmed) | - |
| U107 | `skill6-v2/U107` | `4e43ff80` | True | `d69f4cc7` | v20.0.60 | verified (auto-reconciled, needs test-proof confirmation) | - |
| U108 | `skill6-v2/U108` | `eac10193` | True | `2bb9cbe4` | v20.0.61 | verified | - |
| U109 | `skill6-v2/U109` | `2c4fff68` | True | `09d8140f` | v20.0.67 | verified (auto-reconciled, needs test-proof confirmation) | - |
| U11 | `skill6-v2/U11` | `f3d751f5` | True | `93e4c1ed` | v20.0.61 | verified (auto-reconciled, needs test-proof confirmation) | - |
| U110 | `skill6-v2/U110` | `0d4f2763` | True | `667058ae` | v20.0.66 | verified | 8.7 |
| U111 | `skill6-v2/U111` | `6b24b2b8` | True | `f2be7dcd` | v20.0.24 | verified | 8.9 |
| U112 | `skill6-v2/U112` | `4fcfa01c` | True | `4b4e3afa` | v20.0.60 | verified (test-proof confirmed) | - |
| U113 | `skill6-v2/U113` | `87125b24` | True | `7ae6ab3f` | v20.0.63 | verified (auto-reconciled, needs test-proof confirmation) | - |
| U114 | `skill6-v2/U114` | `69899ae7` | True | `2daa54fc` | v20.0.63 | verified (auto-reconciled, needs test-proof confirmation) | - |
| U115 | `skill6-v2/U115` | `670043c5` | True | `f5506853` | v20.0.60 | verified (auto-reconciled, needs test-proof confirmation) | - |
| U116 | `skill6-v2/U116` | `cef6c474` | True | `48359b40` | v20.0.60 | verified (hand-verified, both legs, test + mutation proof) | - |
| U116-verify | `skill6-v2/U116-verify` | `eaf3ae58` | True | `88b62711` | v20.0.70 | (no row) | - |
| U117 | `skill6-v2/U117` | `252d6cce` | True | `ab6344c6` | v20.0.61 | verified (auto-reconciled, needs test-proof confirmation) | - |
| U12 | `skill6-v2/U12` | `5f3c7321` | True | `1e04f9e4` | v20.0.60 | verified (test-proof confirmed) | - |
| U13 | `skill6-v2/U13` | `5fec8cf9` | True | `59c472b9` | v20.0.38 | verified | 9.3 |
| U14 | `skill6-v2/U14` | `ab4b5aff` | True | `c6f865fe` | v20.0.51 | verified | - |
| U18 | `skill6-v2/U18` | `0b72ee80` | True | `706aff5d` | v20.0.27 | verified | 9.3 |
| U2 | `skill6-v2/U2` | `1cb2c874` | True | `86420ff7` | v20.0.18 | verified | 8.9 |
| U20 | `skill6-v2/U20` | `1bbfe0f0` | True | `ea371000` | v20.0.23 | verified | 9.1 |
| U21 | `skill6-v2/U21` | `ad92145d` | True | `0d3f31a0` | v20.0.33 | verified (ONB half) | - |
| U22 | `skill6-v2/U22` | `50ff2e79` | True | `b64c8166` | v20.0.35 | verified (LIVE-PROOF tier PAID 2026-07-19 — fixture-funnel 23/23 + producer→CC ingest handshake, re-proven live, evidence 06-ghl-install-pages/evidence/u22-live-tier-proof-2026-07-19/; A-U7/B-U10 GHL→Vercel live legs remain operator-gated on a named sandbox GHL location, owed, not claimed) | - |
| U22-offline | `skill6-v2/U22-offline` | `694c341d` | True | `37431f41` | v20.0.71 | (no row) | - |
| U23 | `skill6-v2/U23` | `2ff57796` | True | `f350cc9d` | v20.0.39 | verified | - |
| U24 | `skill6-v2/U24` | `fc9e636e` | True | `1de2099a` | v20.0.30 | verified | 9.0 |
| U25 | `skill6-v2/U25` | `f95e3fe3` | True | `d177e7e7` | v20.0.21 | verified | - |
| U27 | `skill6-v2/U27` | `cba9065a` | True | `6234014b` | v20.0.25 | verified | 9.0 |
| U28 | `skill6-v2/U28` | `46ed631d` | True | `78f73b1a` | v20.0.52 | verified | - |
| U29 | `skill6-v2/U29` | `cffa32b7` | True | `a2f4dc67` | v20.0.53 | verified | - |
| U3 | `skill6-v2/U3` | `033d223d` | True | `ba89a65d` | v20.0.22 | verified | 9.3 |
| U30 | `skill6-v2/U30` | `d3b4d0de` | True | `7e1a07e4` | v20.0.61 | verified (test-proof confirmed) | - |
| U31 | `skill6-v2/U31` | `e7c3cbb5` | True | `ebef2f72` | v20.0.54 | verified | - |
| U39 | `skill6-v2/U39` | `3ca7edae` | True | `1eb670d9` | v20.0.61 | verified (auto-reconciled, needs test-proof confirmation) | - |
| U4 | `skill6-v2/U4` | `ee42a22a` | True | `7dfbad1a` | v20.0.31 | verified (ONB half) | - |
| U44 | `skill6-v2/U44` | `c6aca95f` | True | `0ecbcebe` | v20.0.60 | verified | - |
| U5 | `skill6-v2/U5` | `616084f2` | True | `e979d09d` | v20.0.32 | verified (ONB half) | - |
| U53 | `skill6-v2/U53` | `1afb5690` | True | `7b0e3a1b` | v20.0.57 | verified (both-repo code legs merged — CC v6.0.36 + ONB v20.0.57; D12/D-HL-3 crown-DECISION ratification + live "prove the loop" run still waiting on Trevor / operator) | - |
| U59 | `skill6-v2/U59` | `985935c4` | True | `5c51fb96` | v20.0.60 | verified (test-proof confirmed) | - |
| U6 | `skill6-v2/U6` | `da5dd284` | True | `ada71006` | v20.0.27 | verified | 9.0 |
| U63 | `skill6-v2/U63` | `c3d13ec5` | True | `5a55f459` | v20.0.60 | DONE (operator-closed) — legs (a)/(c) PROVEN live; leg (b)/the authorization question below is SUPERSEDED by the 2026-07-19 operator closure (see lead sentence) | - |
| U64 | `skill6-v2/U64` | `a1f52194` | True | `4736b19b` | v20.0.60 | verified | - |
| U65 | `skill6-v2/U65` | `8a7a213a` | True | `8e556638` | v20.0.60 | deferred (operator-gated) | - |
| U67 | `skill6-v2/U67` | `c35bec2e` | True | `f24713a3` | v20.0.43 | verified | - |
| U68 | `skill6-v2/U68` | `10f88c01` | True | `ee20f234` | v20.0.44 | verified | - |
| U7 | `skill6-v2/U7` | `f06ce74c` | True | `8004d0b2` | v20.0.34 | verified | - |
| U70 | `skill6-v2/U70` | `5fdbe35d` | True | `c7475499` | v20.0.45 | verified (repo leg; live provisioning owed) | - |
| U71 | `skill6-v2/U71` | `16a6441c` | True | `144d2e88` | v20.0.59 | verified (repo leg; live snapshot-chain run owed) | - |
| U74 | `skill6-v2/U74` | `c2772c0c` | True | `92d106a3` | v20.0.67 | verified (repo-half; n8n-half owed) | - |
| U78 | `skill6-v2/U78` | `3bb3b2e5` | True | `8c631959` | v20.0.65 | verified (live record on file; not re-executed this pass) | - |
| U79 | `skill6-v2/U79` | `3be48c21` | True | `b62455b1` | v20.0.63 | verified (test-proof confirmed) | - |
| U8 | `skill6-v2/U8` | `2034ad79` | True | `3abbafe5` | v20.0.29 | verified | 8.9 |
| U80 | `skill6-v2/U80` | `bb5cf95c` | True | `84cfbf88` | v20.0.63 | verified (auto-reconciled, needs test-proof confirmation) | - |
| U82 | `skill6-v2/U82` | `2e349833` | True | `f7b0d9be` | v20.0.46 | verified | - |
| U83 | `skill6-v2/U83` | `cd6e51b0` | True | `fcd029ac` | v20.0.47 | verified | - |
| U85 | `skill6-v2/U85` | `fe21fdb6` | True | `07fcf247` | v20.0.48 | verified | - |
| U86 | `skill6-v2/U86` | `919b195d` | True | `411f9b34` | v20.0.60 | verified (test-proof confirmed) | - |
| U88 | `skill6-v2/U88` | `21ebb5bc` | True | `a3a42e1d` | v20.0.49 | verified (OFFLINE/FIXTURE tier verified unchanged; LIVE operator-box tier RUN 2026-07-19 across 2 passes — 5/5 legs PASS, HONEST not fabricated; pass 1 found+fixed leg 2's real defects but its corrected call published live+public with an unresolved revert, disclosed not buried; pass 2 sourced the real API's own `status` field, shipped `--status draft`, and re-ran leg 2 correctly — genuine draft created, independently read back twice [draft confirmed, then deletion confirmed], zero new live/public side effect; pass 1's live-publish incident remains disclosed+unresolved and still requires the operator's own manual removal, NOT claimed fixed by pass 2) | - |
| U88-live-proof | `skill6-v2/U88-live-proof` | `481be42a` | True | `03f592e8` | v20.0.70 | (no row) | - |
| U89 | `skill6-v2/U89` | `1acd1769` | True | `0fae9ee7` | v20.0.61 | verified (auto-reconciled, needs test-proof confirmation) | - |
| U9 | `skill6-v2/U9` | `b4b58f1e` | True | `ceaac642` | v20.0.50 | verified | - |
| U9-sonnet5-b | `skill6-v2/U9-sonnet5-b` | `89345db2` | False | - | - | (no row) | - |
| U90 | `skill6-v2/U90` | `2057aefd` | True | `c7359410` | v20.0.37 | verified | 9.2 |
| U91 | `skill6-v2/U91` | `4ba11988` | True | `2f23e2e0` | v20.0.60 | verified | - |
| U92 | `skill6-v2/U92` | `1bed45fa` | True | `73e73846` | v20.0.40 | verified | 9.4 |
| U93 | `skill6-v2/U93` | `f1e245d8` | True | `60fa01eb` | v20.0.63 | verified (auto-reconciled, needs test-proof confirmation) | - |
| U96 | `skill6-v2/U96` | `889b13ab` | True | `381b5093` | v20.0.60 | verified (test-proof confirmed) | - |
| U97 | `skill6-v2/U97` | `fa1cdba7` | True | `2a5855f5` | v20.0.60 | verified (test-proof confirmed) | - |
| U98 | `skill6-v2/U98` | `d980209f` | True | `0510c6b5` | v20.0.61 | verified (auto-reconciled, needs test-proof confirmation) | - |
| chainA | `skill6-v2/chainA` | `3161e8fa` | True | `f6636fc0` | v20.0.19 | (no row) | - |
| chainB | `skill6-v2/chainB` | `2e9907d7` | True | `7de4a73e` | v20.0.20 | (no row) | - |
| fix-agent-browser-guard-red | `skill6-v2/fix-agent-browser-guard-red` | `f947b12d` | True | `980e8a9b` | v20.0.55 | (no row) | - |
| fix-reconciler-failclosed | `skill6-v2/fix-reconciler-failclosed` | `0a2127bd` | True | `c26ddfe7` | v20.0.56 | (no row) | - |

## Skill 6 — blackceo-command-center (`skill6-v2/*` branches)

| unit | branch | headSha | mergedIntoMain | mergeSha | tag | ledgerStatus | qcScore(prose) |
|---|---|---|---|---|---|---|---|
| U100 | `skill6-v2/U100` | `9eb12a45` | True | `1813234d` | v6.0.41 | verified (auto-reconciled, needs test-proof confirmation) | - |
| U101 | `skill6-v2/U101` | `3a69a3e6` | True | `42751a16` | v6.0.29 | verified | 9.4 |
| U102 | `skill6-v2/U102` | `77e5643e` | True | `cdd03617` | v6.0.40 | verified (auto-reconciled, needs test-proof confirmation) | - |
| U103 | `skill6-v2/U103` | `7831aeb8` | True | `20935e91` | v6.0.32 | verified (auto-reconciled, needs test-proof confirmation) | - |
| U104 | `skill6-v2/U104` | `38c59b5f` | True | `1bbbd26f` | v6.0.27 | verified | 9.2 |
| U105 | `skill6-v2/U105` | `0711f092` | True | `737eb62c` | v6.0.33 | verified (auto-reconciled, needs test-proof confirmation) | - |
| U107 | `skill6-v2/U107` | `fb6d7520` | True | `b930b042` | v6.0.50 | verified (auto-reconciled, needs test-proof confirmation) | - |
| U109 | `skill6-v2/U109` | `b1f8f99f` | True | `ffbd8d95` | v6.0.43 | verified (auto-reconciled, needs test-proof confirmation) | - |
| U11 | `skill6-v2/U11` | `d618f332` | True | `2e07f87e` | v6.0.47 | verified (auto-reconciled, needs test-proof confirmation) | - |
| U110 | `skill6-v2/U110` | `25ba6c6c` | True | `b11c45b3` | v6.0.55 | verified | 8.7 |
| U115 | `skill6-v2/U115` | `64ccd7ab` | True | `0ff78368` | v6.0.51 | verified (auto-reconciled, needs test-proof confirmation) | - |
| U116-cc-leg | `skill6-v2/U116-cc-leg` | `1e65a94e` | True | `3a509230` | v6.0.54 | (no row) | - |
| U117-cc | `skill6-v2/U117-cc` | `518792cb` | True | `f8ce5176` | v6.0.56 | (no row) | - |
| U12 | `skill6-v2/U12` | `d9649e50` | True | `05971bda` | v6.0.53 | verified (test-proof confirmed) | - |
| U15-cc | `skill6-v2/U15-cc` | `f273e5a1` | True | `99da561c` | v6.0.57 | (no row) | - |
| U20 | `skill6-v2/U20` | `5e5c3bb9` | True | `ae80043b` | v6.0.4 | verified | 9.1 |
| U21 | `skill6-v2/U21` | `5374c4fd` | True | `4759561a` | v6.0.18 | verified (ONB half) | - |
| U22 | `skill6-v2/U22` | `f4f933ff` | True | `ae972738` | v6.0.20 | verified (LIVE-PROOF tier PAID 2026-07-19 — fixture-funnel 23/23 + producer→CC ingest handshake, re-proven live, evidence 06-ghl-install-pages/evidence/u22-live-tier-proof-2026-07-19/; A-U7/B-U10 GHL→Vercel live legs remain operator-gated on a named sandbox GHL location, owed, not claimed) | - |
| U22-offline | `skill6-v2/U22-offline` | `6034e881` | True | `fe66e378` | v6.0.60 | (no row) | - |
| U26 | `skill6-v2/U26` | `5e26d8d8` | True | `b3c585c1` | v6.0.3 | verified | 8.8 |
| U27 | `skill6-v2/U27` | `92beccab` | True | `6dfb8bf7` | v6.0.11 | verified | 9.0 |
| U32 | `skill6-v2/U32` | `6c442dfd` | True | `2da17734` | v6.0.5 | verified | 8.9 |
| U33 | `skill6-v2/U33` | `57c8305c` | True | `20773b64` | v6.0.38 | verified (auto-reconciled, needs test-proof confirmation) | - |
| U34-U35 | `skill6-v2/U34-U35` | `ccfe9847` | True | `8a5369e0` | v6.0.26 | (no row) | - |
| U37 | `skill6-v2/U37` | `88db8a74` | True | `d80eea2d` | v6.0.34 | verified | - |
| U38 | `skill6-v2/U38` | `6971f6ab` | True | `b9b20b9e` | v6.0.40 | verified (auto-reconciled, needs test-proof confirmation) | - |
| U39 | `skill6-v2/U39` | `163e75eb` | True | `3da3271e` | v6.0.45 | verified (auto-reconciled, needs test-proof confirmation) | - |
| U4 | `skill6-v2/U4` | `ca647283` | True | `98e55842` | v6.0.17 | verified (ONB half) | - |
| U40 | `skill6-v2/U40` | `1e9a57ce` | True | `36674061` | v6.0.6 | verified | 8.9 |
| U41 | `skill6-v2/U41` | `64863d52` | True | `619b9eca` | v6.0.7 | verified | 8.9 |
| U42 | `skill6-v2/U42` | `b50987cb` | True | `4b983a13` | v6.0.21 | verified | 9.2 |
| U43 | `skill6-v2/U43` | `4a4e7680` | True | `751fa8ad` | v6.0.35 | verified | - |
| U44 | `skill6-v2/U44` | `eb30a3b1` | True | `a301a181` | v6.0.58 | verified | - |
| U45 | `skill6-v2/U45` | `9dfc8fe9` | True | `c69996cd` | v6.0.39 | verified (auto-reconciled, needs test-proof confirmation) | - |
| U46 | `skill6-v2/U46` | `e28ea4b4` | True | `fd064907` | v6.0.8 | verified | 8.9 |
| U47 | `skill6-v2/U47` | `2944303f` | True | `169355ef` | v6.0.22 | verified | 9.0 |
| U48 | `skill6-v2/U48` | `1dc10292` | True | `7f1c6620` | v6.0.9 | verified | 9.2 |
| U49 | `skill6-v2/U49` | `0f8d63a2` | True | `bbfdb997` | v6.0.28 | verified | 9.0 |
| U5 | `skill6-v2/U5` | `89229982` | True | `eb00420d` | v6.0.16 | verified (ONB half) | - |
| U50 | `skill6-v2/U50` | `8d0c480a` | True | `28e91598` | v6.0.37 | verified (auto-reconciled, needs test-proof confirmation) | - |
| U53 | `skill6-v2/U53` | `c8086c73` | True | `481ff9a2` | v6.0.36 | verified (both-repo code legs merged — CC v6.0.36 + ONB v20.0.57; D12/D-HL-3 crown-DECISION ratification + live "prove the loop" run still waiting on Trevor / operator) | - |
| U54 | `skill6-v2/U54` | `806b98c8` | True | `7b6642ac` | v6.0.39 | verified (auto-reconciled, needs test-proof confirmation) | - |
| U55 | `skill6-v2/U55` | `a4c54669` | True | `917ea8f0` | v6.0.12 | verified | 8.9 |
| U56 | `skill6-v2/U56` | `ce1fb032` | True | `a69f0da4` | v6.0.13 | verified | 9.0 |
| U57 | `skill6-v2/U57` | `eeb61852` | True | `2d2f90f4` | v6.0.23 | verified | 9.0 |
| U58 | `skill6-v2/U58` | `b2d272c1` | True | `0e40db1c` | v6.0.30 | verified (auto-reconciled, needs test-proof confirmation) | - |
| U59-cc-d15 | `skill6-v2/U59-cc-d15` | `d0f3558c` | False | - | - | (no row) | - |
| U6 | `skill6-v2/U6` | `d6fc0509` | True | `2d82fd6a` | v6.0.15 | verified | 9.0 |
| U60 | `skill6-v2/U60` | `803a8807` | True | `5e2f8b9a` | v6.0.10 | verified | 9.7 |
| U62 | `skill6-v2/U62` | `d4e0c7ee` | True | `cd987ce9` | v6.0.59 | verified | - |
| U7 | `skill6-v2/U7` | `ece5ae36` | True | `e96d745b` | v6.0.19 | verified | - |
| U77 | `skill6-v2/U77` | `033c0641` | True | `d9758456` | v6.0.39 | verified | - |
| U93 | `skill6-v2/U93` | `c063dd9b` | True | `94a617b5` | v6.0.41 | verified (auto-reconciled, needs test-proof confirmation) | - |
| U94 | `skill6-v2/U94` | `02cb757f` | True | `1eceeca2` | v6.0.39 | verified (auto-reconciled, needs test-proof confirmation) | - |
| U95 | `skill6-v2/U95` | `86004117` | True | `d8f46fb4` | v6.0.31 | verified (auto-reconciled, needs test-proof confirmation) | - |
| U99 | `skill6-v2/U99` | `21898e7d` | True | `ad297f3d` | v6.0.39 | verified (auto-reconciled, needs test-proof confirmation) | - |

## Skill 62 — cinematic-web-funnel-engine (`skill62/cinematic-engine`)

- branch tip: `ce6aab7a`
- merge-base with `origin/main`: `fa479da6`
- commits ahead of that merge-base (cinematic-specific work so far): 1
  - `ce6aab7a` fix(skill-62): robust JSON extraction in prove_conversion via raw_decode + test
- merged into `origin/main`: False

## Merge queue snapshot (`onboarding-merge-queue/`)

- writer lock held at gather time: False
- ready tickets in `tickets/`: 0
- completed in `done/`: 0

## This run

- ledger-edit permitted this run (merge-queue lock was free): True
- units auto-reconciled (git showed merged/tagged, ledger still said pending) this run: none
- fail-closed integrity alarms this run (verified-but-unmerged leg mismatches): 0 (none)
- informational leg-unconfirmed findings this run (NOT fail-closed; kinds in the findings table): 3 (U15-openclaw-onboarding, U79-blackceo-command-center, U108-blackceo-command-center)
- journal corroboration hits scanned: 25 (informational only, never authoritative)

