# U81 / GK-19 — Prove the Social Media Planner UNBROKEN against the graphics handoff (or capture the exact break)

**Unit:** U81 (crosswalk GK-19), P0, live (operator).

**Binary acceptance (master spec, line 1964-1968):** "drive the full fixture flow on the
operator's own box: a Graphics-department asset WITH a SOP-GIP-02 receipt ≥ 8.5 passes
`pregen_prompt_gate.py check --asset-source graphics-department` and gets posted (draft-only
rail); the SAME asset with the receipt removed is REFUSED exit 6 (`AF-SM-INPUT-QC-GATE`); a
Skill-35-authored text-overlay prompt on Nano Banana is REFUSED exit 6 and passes when
re-routed to Ideogram V3 DESIGN. ... all three legs behave exactly as specified with exit
codes + receipts archived, OR a written reproduction with the failing command, exit code, and
stderr exists and a follow-up unit is filed. No middle state."

**Deps satisfied:** GK-22/U84 (on-box content proof) run first — see `../U84-GK-22/README.md`
— confirms this box is running P3-05 content (Skill 35 v2.9.10, Skill 45 v1.3.3, all three
gate files byte-identical to `origin/main`), so this leg exercises current content, not stale
bytes.

**Live rail used:** `caf social create-post` = the actual installed `caf` CLI at
`/Users/blackceomacmini/.local/bin/caf` (Skill 44 / convert-and-flow-operator engine),
targeting the OPERATOR'S OWN GHL sub-account — `locationId=Mct54Bwi1KlNouGXQcDX`, "BlackCEO
LLC" (verified via `caf locations get`, see `leg1-gate-check.out`-adjacent evidence below —
first/last name Trevor Otts, `trevor@reply.blackceonow.com`; NOT a client location — safe for
this fixture write per operator-box-is-canary doctrine).

---

## Leg 1 — Graphics asset WITH SOP-GIP-02 receipt ≥ 8.5

### 1a. Gate check (`pregen_prompt_gate.py check --asset-source graphics-department --qc-receipt-file <receipt>`)

Fixtures: `prompt-graphics-asset.txt` (text-overlay prompt, brand-safety clause baked in,
verbatim on-image text baked in), `avoid-list.txt`, `image_qc_report_PASS.json`
(`average: 9.1, pass: true` — SOP-GIP-02 shape, ≥ 8.5 floor).

```
$ python3 pregen_prompt_gate.py check --prompt-file prompt-graphics-asset.txt \
    --model ideogram-v3-design --ratio 4:5 --pixels 1080x1350 --platform instagram \
    --text-overlay "Three Moves That Doubled Our Pipeline" \
    --brand-colors "#0B3D2E,#F5EFE0,#C9A24B" --avoid-list-file avoid-list.txt \
    --asset-source graphics-department --qc-receipt-file image_qc_report_PASS.json
exit=0
OK: prompt clears the Skill 35 pre-generation gate (model=ideogram-v3-design, ratio=4:5, platform=instagram).
```

**Result: PASS, exit 0, exactly as specified.** Archived: `leg1-gate-check.out/.err/.exitcode`.

### 1b. "gets posted (draft-only rail)" — LIVE round trip: **BROKEN, exact break captured**

Attempt 1 (no approval token — the safety gate's normal fail-closed default):
```
$ caf social create-post --account-id <Black-CEO-fb-page> --text "[GK-19/U81 QC FIXTURE ...]"
exit=1
stderr: SAFETY GATE: WRITE REFUSED: no approval token present.
Set CAF_APPROVAL_TOKEN=<token> to approve this write, OR
prefix the workflow/folder name with 'ZHC-' or 'ZHC_' for standing approval.
```
This is Skill 44's own single-chokepoint write-approval gate (`utils/safety_gate.py`,
`check_write()` Rule 3) — working as designed. Approved this ONE fixture write via the
sanctioned mechanism (`CAF_APPROVAL_TOKEN`, scoped to this single command only, never
exported globally, never left set afterward):

```
$ CAF_APPROVAL_TOKEN=<one-time-token> caf --json social create-post \
    --account-id 64faa5bff0befc6c98267746_Mct54Bwi1KlNouGXQcDX_136340370119693_page \
    --text "[GK-19/U81 QC FIXTURE - DRAFT ONLY - DO NOT PUBLISH - operator verification run 2026-07-13 - auto-deleted after read-back]"
exit=1
stderr: API Error (422): ['property locationId should not exist', 'media must be an array with media objects or an empty array', 'Post Type must be one of the following values: - post, story, reel', 'type should not be empty', 'userId must be a string', 'userId should not be empty']
```

**Root cause (located, not guessed):** `gohighlevel_cli.py::social_create_post()` builds the
POST body as `{"locationId": ..., "accountIds": [...], "summary": text}`. GHL's real
`/social-media-posting/{locationId}/posts` endpoint (a) does NOT want `locationId` duplicated
in the body (it's already the URL path segment), and (b) REQUIRES `type` (one of
`post`/`story`/`reel`) and `userId` (the posting GHL user id) — neither of which the CLI's
`social create-post` command exposes as a flag or supplies in the body at all. This is
independently corroborated by `caf doctor`'s own disclosed caveat: "golden fixture was built
from source-code shapes and has NOT been validated against a live GHL backend" — this run is
the first live validation, and it surfaces exactly the predicted class of defect.

Archived verbatim: `leg1a-create-post.err` (first attempt), `leg1a-create-post.json` +
its `.err` (second, token-approved attempt — the 422 above).

**No resource was created** (GHL rejected both attempts before persisting anything) — confirmed
by a full read-back of the location's post list immediately after (`leg1-posts-list-full.json`,
20 most-recent posts, zero hits for the fixture marker text `"GK-19/U81 QC FIXTURE"`). Zero
cleanup required; zero client-visible or operator-visible artifact left behind.

**Secondary, independently-confirmed defect** in the SAME command family: `caf social posts`
(the read-back/list command) is ALSO broken against the live API — same `locationId`-in-body
defect plus a type mismatch (`skip`/`limit` must be number-strings, the CLI sends ints):
```
$ caf --json social posts --limit 10
exit=1
stderr: API Error (422): ['property locationId should not exist', 'skip must be a number string', 'limit must be a number string']
```
Archived: `leg1-posts-list-confirm-no-orphan.err`.

**Read-back mechanics independently proven sound** once the payload is correctly shaped (bypass
only the CLI's malformed body construction, same authenticated client/session,
`ghl_client.post()` called directly with `{"limit": "20", "skip": "0"}` and no `locationId` key):
```
$ python -c '... api.post(f"/social-media-posting/{loc}/posts/list", data={"limit":"20","skip":"0"}) ...'
exit=0 — 20 real posts returned, zero fixture-marker hits (no orphan).
```
Archived: `leg1-posts-list-diagnostic-corrected-shape.out/.err`, `leg1-posts-list-full.json`.
This confirms the break is precisely and only in `gohighlevel_cli.py`'s two `social`
subcommand body-builders — not a deeper account/permission/connectivity problem.

**Leg 1 verdict:** gate-check half PASSES exactly as spec'd (§1a). Live-post half FAILS —
written reproduction (exact failing commands, exit codes, stderr) archived per the BINARY
acceptance's OR-branch. **Follow-up unit filed: U81-F1** (below) — fix
`social_create_post`/`social_posts` body construction in
`44-convert-and-flow-operator/tools/engine/cli_anything/gohighlevel/gohighlevel_cli.py`
(add `--post-type`/`--user-id` flags, drop `locationId` from both bodies, stringify
`skip`/`limit`). Not fixed here — out of scope for a P0 VERIFICATION unit; root cause is
located and reproducible, not a blind guess.

---

## Leg 2 — SAME asset, receipt REMOVED → must REFUSE exit 6 `AF-SM-INPUT-QC-GATE`

```
$ python3 pregen_prompt_gate.py check --prompt-file prompt-graphics-asset.txt \
    --model ideogram-v3-design --ratio 4:5 --pixels 1080x1350 --platform instagram \
    --text-overlay "Three Moves That Doubled Our Pipeline" \
    --brand-colors "#0B3D2E,#F5EFE0,#C9A24B" --avoid-list-file avoid-list.txt \
    --asset-source graphics-department          # (no --qc-receipt-file)
exit=6
stderr: FATAL: prompt cleared FORM but has 1 quality/routing defect(s):
  - AF-SM-INPUT-QC-GATE: --asset-source graphics-department but no --qc-receipt-file supplied.
    The planner REJECTS graphics-department assets lacking a SOP-GIP-02 QC receipt (P3-05 step
    4i) instead of posting them.
```

**Result: PASS — exactly as specified** (exit 6, `AF-SM-INPUT-QC-GATE` cited verbatim).
Archived: `leg2-gate-check-no-receipt.out/.err/.exitcode`.

---

## Leg 3 — Skill-35-authored text-overlay prompt: Nano Banana REFUSED, Ideogram V3 DESIGN PASSES

### 3a. Routed to `nano-banana-2` (NON_TEXT_MODELS)

```
$ python3 pregen_prompt_gate.py check --prompt-file prompt-skill35-text-overlay.txt \
    --model nano-banana-2 --ratio 1:1 --pixels 1080x1080 --platform instagram \
    --text-overlay "5 Ways To Book More Discovery Calls This Week" \
    --brand-colors "#0B3D2E,#F5EFE0,#C9A24B" --avoid-list-file avoid-list.txt
exit=6
stderr: FATAL: ... AF-SM-MODEL-ROUTING: this prompt carries baked on-image text but is routed
  to 'nano-banana-2', which is NOT a text-rendering specialist ... MUST route to Ideogram V3
  DESIGN per Skill 45's own routing rule (45-design-intelligence-library/library/
  social-media-designs/_RULES.md). Nano Banana 2/Pro is reserved for non-text imagery only.
```

**Result: PASS — exactly as specified** (exit 6, `AF-SM-MODEL-ROUTING` cited verbatim).
Archived: `leg3a-nanobanana-refuse.out/.err/.exitcode`.

### 3b. SAME prompt, re-routed to `ideogram-v3-design`

```
$ python3 pregen_prompt_gate.py check --prompt-file prompt-skill35-text-overlay.txt \
    --model ideogram-v3-design --ratio 1:1 --pixels 1080x1080 --platform instagram \
    --text-overlay "5 Ways To Book More Discovery Calls This Week" \
    --brand-colors "#0B3D2E,#F5EFE0,#C9A24B" --avoid-list-file avoid-list.txt
exit=0
OK: prompt clears the Skill 35 pre-generation gate (model=ideogram-v3-design, ratio=1:1, platform=instagram).
```

**Result: PASS — exactly as specified** (exit 0 after re-route).
Archived: `leg3b-ideogram-pass.out/.err/.exitcode`.

---

## VERDICT — U81 / GK-19

- **Leg 2: PASS, exact match to spec.**
- **Leg 3: PASS, exact match to spec (both sub-legs).**
- **Leg 1: gate-check half PASSES; live-post half genuinely BROKEN** — written reproduction
  (failing command + exit code + stderr) archived per the BINARY acceptance's own OR-branch;
  root cause located (not guessed) and a follow-up unit filed (U81-F1). No orphaned resources;
  nothing client-visible was ever created.

Per the master spec's own words for this exact unit — "If any leg fails, the failure trace IS
the deliverable — the exact reproduction of the operator's 'it breaks the planner' report,
filed as its own fix unit" — **this satisfies GK-19's acceptance criteria as a "capture the
exact break" outcome for the live-posting half of Leg 1**, with Legs 2 and 3 fully proven
UNBROKEN.

## Follow-up unit filed: U81-F1

**What:** fix `44-convert-and-flow-operator/tools/engine/cli_anything/gohighlevel/gohighlevel_cli.py`
`social_create_post()` and `social_posts()`: (a) remove `locationId` from both request bodies
(already in the URL path); (b) add `--post-type {post,story,reel}` (required by GHL) and
`--user-id` flags to `create-post`, wired into the body as `type`/`userId`; (c) stringify
`skip`/`limit` in `social_posts()`'s body. Re-run `caf doctor`'s live-validation procedure
(`internal/fixtures/README.md`) against a real backend afterward so the SYNTHETIC_FIXTURE
warning can be retired for this command family.
**Why:** located here, live, with a real 422 + exact GHL validation messages (not
reproduced from a synthetic fixture) — see Leg 1 above.
**Deps:** none.
**BINARY acceptance:** `caf social create-post` on the operator's own "BlackCEO LLC" location
creates a real draft post (verified via read-back showing the post with `deleted:false` and no
`publishedAt`), which is then deleted and the deletion verified by a second read-back showing
it absent/`deleted:true`. `caf social posts` lists posts without a 422.
**Revert:** the CLI body-builder edit is additive/corrective only — revert the commit; no data
migration.
