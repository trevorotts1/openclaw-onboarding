# Skill 06 — GHL Install Pages: Day-0 Install Card

**What this skill is:** browser-control skill that builds and verifies GHL (Convert and Flow) funnels/websites/forms/surveys/courses/pipelines through the Skill 03 agent-browser gateway (Playwright = fallback only).

**Prerequisites — in this exact order (hard rule):** 01 TYP → 02 Backup → **03 agent-browser → 06**, and **05 GHL Setup → 06**. Skill 06 MUST NOT start until 03 and 05 are complete.

**Step 1 — agent-browser:** install/verify Skill 03 and pin `0.27.0` (`agent-browser --version` must print `0.27.0`; anything else stops Day-0).

**Step 2 — capability probe + browser_manager:** run the capability probe (writes `working/skill6-capability.json`, see `tools/README.md` capability group), then `source tools/browser_manager.sh` + `bm_ensure` — start only the selected lane.

**Step 3 — Firebase token (Tier-1 only):** `GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN` must resolve; no login form, no 2FA path. Pointer only — see SKILL.md Prerequisites (auth bullet) and `tools/seed-ghl-auth.py --check`.

**Full procedure:** `INSTALL.md` (v3) is the canonical install; `ENV-MATRIX.md` is the binding Mac-vs-VPS environment contract.

**Lite vs full:** this card is the LITE (operator-driven) mode; the FULL autonomous variant — the dept agent building board-driven, no operator at the keyboard — lives in `v2-autonomous-build-sop.md`. Both share the same `tools/gates.json` gates, token-only auth, and the capability probe.

**DAY-0 acceptance:** the capability probe returns `selectedLane != null`. No lane selected → fail closed — do not proceed to any build.