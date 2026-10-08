Batch release v26.4.8 (one onboarding bump from v26.4.7, one skill 75 bump v2.8.0 to v2.8.1, one combined CHANGELOG entry, README updated).

Units included (merged in PR-number order, no force):
- #1654 LPC001 lip-sync close-up in every reference set
- #1655 BND001 sung share judged only by the 5/10 point band, no 55 percent floor
- #1656 W-G-003 (G3) calibrated sung detector
- #1657 W3-B-U1 Social Media Planner v3.7.0
- #1658 INF002 installers install with a note instead of failing (skills 05/29/32/36/47/48/59/70/74)
- #1659 SPK001 spoken share cut to 20-25 percent, singing judged against voice time

Excluded: #1639 (conflicting; cc-compat pin is not yet v7.6.112), #1637 (superseded by #1655), #1623 (old v26.4.6 mint PR), drafts, #1653 (no batch-train label).

Conflict notes: skill 75 CHANGELOG sections kept side by side; skill 35 kept v3.7.0 from #1657 (older 3.6.16 from #1658 dropped); README top banners collapsed to one v26.4.8 banner.

Local checks (empty HOME): skill 75 scripts/core 66 test files all pass; operator-path-leak clean; qc-assert-repo-consistency PASS; bump-version --check 10 markers agree; qc-skill35-installed-layout 6 passed; tests/social-planner 527 passed, 7 failed (5 test_f38_video_evidence fail identically on origin/main, 2 test_n8n_compat need node_modules, same as #1657 note).

🤖 Generated with [Claude Code](https://claude.com/claude-code)
