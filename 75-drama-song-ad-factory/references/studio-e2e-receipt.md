# Drama Studio — live end-to-end proof on the operator Mac (DSF W4-e2e-proof-U1)

Unit **DSF-411** · plan row `W4-e2e-proof-U1` · proves **SPEC §8** line by line.
Receipt only: no code change, no version bump, no CHANGELOG edit.

| | |
|---|---|
| Date | 2026-10-13 (times below are UTC unless marked) |
| Repo / branch | `trevorotts1/openclaw-onboarding`, worktree `/Users/<operator>/dsf-wt/DSF-411`, branch `unit/DSF-411`, base `origin/main` = `56a22f226` |
| Machine | operator Mac Mini only — never a client or fleet box |
| Live service | `https://studio.zerohumanworkforce.com` |
| Box key | `~/.drama-studio/machine.key`, folder `700`, file `600` — read **by code only**, never printed, never written into this receipt or any file |
| Link key | read from `~/.drama-studio/client.url` **by code**; every shape below shows `#k=` + hex **length**, REDACTED |
| Operator test client | `c-7315a3aed6dc11a179c4ab3f77d37791` |
| Lane (raw captures) | `/Users/<operator>/Downloads/DRAMA FIXES OCT 13/run/lanes/DSF-411-lane/out/` |
| Runs root | `/tmp/operator-mac-DSF-411-tmp/drama-runs/` |

Skill refresh first, as briefed:

```
$ git -C ~/999-setup pull
Already up to date.
$ ~/.local/bin/sync-nine-skills.sh
sync-nine-skills: already in sync (74 skills).
```

The drama-studio skill on this machine is **not** older than its repo — `md5`
of `studio.py`, `studio_bridge.py`, `studio_check.py`, `SKILL.md` are identical
between `~/.claude/skills/drama-studio/` and `~/999-setup/.claude/skills/drama-studio/`.

---

## Path notes (why the commands below use these paths)

1. **`<worktree>/.claude/skills/…` cannot exist in this repo.** `.claude/` is
   gitignored (`.gitignore:6:.claude/`) and untracked on `origin/main`:
   `git ls-tree -r --name-only origin/main | grep -c '^\.claude/'` → `0`.
   The drama-studio skill lives in the **999-setup** repo, not this one.
2. **`studio.py link --new` does not exist on any merged ref.** Ran it verbatim
   from the installed skill root:

   ```
   $ cd ~/999-setup && python3 .claude/skills/drama-studio/studio.py link --new --print
   usage: studio.py [-h] {pair,link} ...
   studio.py: error: unrecognized arguments: --new
   EXIT=2
   ```

   `git show origin/main:.claude/skills/drama-studio/studio.py | grep -c -- "--new"` → `0`.
   The branch that adds it (`unit/DSF-W1-claude-skill-U2`, commit `60ef6feef`)
   is **not merged**: `git merge-base --is-ancestor origin/unit/DSF-W1-claude-skill-U2 origin/main` → `NO`.
   Same for the bridge: 999 `origin/main` has no `link`, `poll`,
   `publish-approval` or `approval-answer` subcommand; the branch that carries
   them (`unit/DSF-W3-twin-sync-U2`, `fc16ef9fb`) is also **not merged**.
3. **So the proof runs the merged onboarding bridge**, which is the file SPEC §6
   names as canonical ("`shared-bridge/studio_bridge.py`, copied byte-identical
   to 999") and which `INSTRUCTIONS.md:245` documents for the link:

   ```
   75-drama-song-ad-factory/shared-bridge/studio_bridge.py  link [--new]
   ```
   `--skill-root` is `<worktree>/75-drama-song-ad-factory` (the merged skill
   core, holds `scripts/core/intake_preflight/factory.py`).

**Driver note (SPEC §5, free text).** Question 6 (`spend`) has **no** recommended
option — it is the free-text question ("Reply with a dollar amount, like $25").
A first order built from "recommended option for every question" sent `"1"` there
and the replay stopped at question 6, so the later orders send `"$25"`. The page
sends the client's own words for that question exactly as SPEC §5 says.

---

## SPEC §8 line 1 — "a fresh personal link opens the page on the phone"

**Mint (fresh link, rotate on):**

```
$ python3 75-drama-song-ad-factory/shared-bridge/studio_bridge.py link --new   # exit 0
shape: https://studio.zerohumanworkforce.com/#k=<64 lowercase hex, REDACTED>
$ stat -f "%Sp %z %N" ~/.drama-studio/client.url
-rw------- 106 /Users/<operator>/.drama-studio/client.url
```

Link shape is `https://` + host + `/#k=` + hex, key never leaves the file or this
machine's own state folder.

**The page itself serves (no key needed):**

```
GET /                -> HTTP 200  bytes=2120  title='Your drama song video — the studio'
GET /studio.js       -> HTTP 200  bytes=28904
GET /questions.json  -> HTTP 200  bytes=8226  json-ish
```

**The link key opens the session the way the page does (`x-ds-key` header):**

```
$ python3 <lane>/ds_api.py session
GET /api/studio/session -> HTTP 200
{
  "client_id": "c-7315a3aed6dc11a179c4ab3f77d37791",
  "draft": null,
  "key_kind": "link",
  "ok": true,
  "option": 1,
  "option_line": "Your crew starts when you open Claude Code on your computer. Last check-in: 4 minutes ago.",
  "orders": []
}
```

**Answered: YES** (mint + page + link-key session all 200; opening it on a phone
is the human step — the link shape and every route the phone calls are proved here).

*Spec drift, not a §8 line:* the key is **64** lowercase hex, SPEC §3 says "32
lowercase hex (128-bit)"; `mini-app/service/src/keys.js:25` sets
`KEY_BYTES = 32` (bytes) for every key kind.

---

## SPEC §8 line 2 — "the 9 questions show one per screen with examples"

Live `GET /questions.json` (the page's own copy, SPEC §5):

```
GET /questions.json -> HTTP 200
{
  "format": "studio-json",
  "version": 0,
  "question_count": 9,
  "len(questions)": 9
}
1. id=models     example='"1. Recommended setup." Short, clear, done.'          options=2 recommended=[1]
2. id=length     example='"60 seconds. It\'s for Instagram." …'                options=5 recommended=[1]
3. id=music      example='"Soul Rise. It starts with the problem…'             options=3 recommended=[1]
4. id=look       example='"Lifelike 3D. I want it to look real." …'            options=5 recommended=[1]
5. id=model      example='"Hailuo 02 Standard. Good quality at a fair price."'         options=4 recommended=[1]
6. id=spend      example='"1. The recommended price." Clear, and it includes…' options=1 recommended=[]
7. id=storyboard example='"Approved. Change shot 4 to show the storefront."'   options=2 recommended=[1]
8. id=song       example='"Version B. I can\'t stop humming the chorus."'      options=2 recommended=[1]
9. id=script     example='"Approved. Change \'free class\'…"'                  options=2 recommended=[1]
```

9 questions, **every one carries an example**, served by the same Worker that
serves the page (`/questions.json` → 200, 8226 bytes).

**Answered: YES** (data level — one question per screen is the page's rendering
of this array; the array and its per-question examples are proved live).

---

## SPEC §8 line 3 — "the draft survives a page reload"

```
$ python3 <lane>/ds_api.py draft "1" "2"
PUT /api/studio/draft -> HTTP 200
{
  "ok": true,
  "updated_at": 1791926733057
}

### first GET after PUT
GET /api/studio/session -> HTTP 200
{
  "client_id": "c-7315a3aed6dc11a179c4ab3f77d37791",
  "draft": { "replies": [ "1", "2" ], "updated_at": 1791926733057 },
  "key_kind": "link",
  "ok": true,
  ...
}

### second GET (page reload)
GET /api/studio/session -> HTTP 200
{
  "client_id": "c-7315a3aed6dc11a179c4ab3f77d37791",
  "draft": { "replies": [ "1", "2" ], "updated_at": 1791926733057 },
  "key_kind": "link",
  "ok": true,
  ...
}
```

Same `replies`, same `updated_at`, on a fresh read. The stored object is R2
`clients/c-7315a3aed6dc11a179c4ab3f77d37791/draft.json` (ListObjectsV2
`Size=2`, `LastModified=2026-10-13T21:26:12.000Z` — the `{}` left behind when
Lock it in deleted it: `page-api.js:42 const DRAFT_NONE = '{}'`, see line 4).

**Answered: YES**

---

## SPEC §8 line 4 — "Lock it in creates an order with replies"

```
$ python3 <lane>/ds_api.py order-create "DSF-411 e2e test order"
replies built: 9 questions + yes = 10 (values are option numbers, not secrets)
["1", "1", "1", "1", "1", "$25", "1", "1", "1", "yes"]
POST /api/studio/orders -> HTTP 201
{
  "ok": true,
  "option_line": "Your crew starts when you open Claude Code on your computer. Last check-in: 5 minutes ago.",
  "order": {
    "availability": "not-delivered",
    "client_id": "c-7315a3aed6dc11a179c4ab3f77d37791",
    "created_at": 1791927879859,
    "order_id": "r_32ae9427",
    "paid_started": false,
    "replies": [ "1", "1", "1", "1", "1", "$25", "1", "1", "1", "yes" ],
    "state": "waiting",
    "state_reason": "state",
    "title": "DSF-411 e2e test order",
    "updated_at": 1791927879859,
    "upload_ids": []
  }
}
```

All 10 replies stored on the order, state `waiting`.

**The draft is deleted by Lock it in** (SPEC §4: "the draft is deleted"):

```
### session right after the order
GET /api/studio/session -> HTTP 200
{
  "client_id": "c-7315a3aed6dc11a179c4ab3f77d37791",
  "draft": null,
  "key_kind": "link",
  "ok": true,
  "orders": [ { "order_id": "r_32ae9427", "state": "waiting", "title": "DSF-411 e2e test order", ... } ]
}
```

**Answered: YES**

---

## SPEC §8 line 5 — "poll claims it within 2 minutes and the replay writes `card-answers.json` in the run dir"

### 5a. The replay wrote `card-answers.json` — YES

```
$ python3 75-drama-song-ad-factory/shared-bridge/studio_bridge.py poll \
    --skill-root /Users/<operator>/dsf-wt/DSF-411/75-drama-song-ad-factory \
    --runs /tmp/operator-mac-DSF-411-tmp/drama-runs                                    # exit 0
{"next": "/opt/homebrew/opt/python@3.14/bin/python3.14 /Users/<operator>/dsf-wt/DSF-411/75-drama-song-ad-factory/scripts/core/intake_preflight/factory.py next --run-dir /tmp/operator-mac-DSF-411-tmp/drama-runs/r_32ae9427", "order_id": "r_32ae9427", "run_dir": "/tmp/operator-mac-DSF-411-tmp/drama-runs/r_32ae9427"}
```

Run dir listing:

```
/tmp/operator-mac-DSF-411-tmp/drama-runs/r_32ae9427
/tmp/operator-mac-DSF-411-tmp/drama-runs/r_32ae9427/card-answers.json
/tmp/operator-mac-DSF-411-tmp/drama-runs/r_32ae9427/control
/tmp/operator-mac-DSF-411-tmp/drama-runs/r_32ae9427/control/card-receipt.json
/tmp/operator-mac-DSF-411-tmp/drama-runs/r_32ae9427/control/studio-order.json
/tmp/operator-mac-DSF-411-tmp/drama-runs/r_32ae9427/song-choices
/tmp/operator-mac-DSF-411-tmp/drama-runs/r_32ae9427/song-choices/state.json
```

`card-answers.json` contents (option numbers and labels, no secrets):

```json
[
  { "n": 1, "value": { "build": "openrouter/z-ai/glm-5.3-flash", "check": "sonnet-chain", "route": "openrouter" },
    "text": "GLM 5.3 Flash (OpenRouter) builds, Claude Sonnet checks", "id": "models" },
  { "n": 1, "text": "60 seconds",       "value": null, "id": "length" },
  { "n": 1, "text": "Soul Ballad",      "value": null, "id": "music" },
  { "n": 1, "text": "Lifelike 3D",      "value": null, "id": "look" },
  { "n": 1, "text": "Hailuo 02 Standard", "value": null, "id": "model" },
  { "n": 1, "text": "up to $25.00",     "value": "25", "id": "spend" },
  { "n": 1, "text": "Yes, show me first", "value": null, "id": "storyboard" },
  { "n": 1, "text": "Yes, send me 3 versions to choose from", "value": null, "id": "song" },
  { "n": 1, "text": "Yes, show me first", "value": null, "id": "script" }
]
```

### 5b. "Within 2 minutes" — NO, measured twice, and the reason is below

| order | created (UTC) | claimed (UTC, `control/studio-order.json` mtime) | elapsed |
|---|---|---|---|
| `r_886571c3` | 21:26:11.637 | 21:38:00 | **11 min 49 s** |
| `r_32ae9427` | 21:44:39.859 | 21:46:13 | 1 min 33 s |

The first poll after `r_886571c3` was created printed **nothing**:

```
$ python3 …/studio_bridge.py poll … > poll.txt ; echo $?
0
$ wc -c poll.txt
       0 /…/out/poll.txt
$ ls -A /tmp/operator-mac-DSF-411-tmp/drama-runs/ | wc -l
       0
```

A direct check-in 4 minutes after the order existed still had no line:

```
POST /api/studio/checkin -> HTTP 200
{
  "checked_in_at": 1791927010069,     # 2026-10-13T21:30:10.069Z
  "line": null,
  "ok": true
}
```

**Cause, measured not guessed.** The box's line comes from the R2 object
`clients/<id>/inbox.json`, which `POST /api/studio/orders` writes itself
(`index.js:317`). That object, at `Size=89`, `LastModified=2026-10-13T21:26:12.245Z`
— i.e. **written by order `r_886571c3`'s own creation** — held an **empty**
waiting list:

```
R2 ListObjectsV2 prefix='clients/'
   clients/c-7315…/draft.json  2026-10-13T21:26:12.000Z
   clients/c-7315…/inbox.json  2026-10-13T21:26:12.245Z   Size=89
                               ETag "0e850a6f0430e7980bd5d4f1a6c3108c"

candidate content:
{"client_id":"c-7315a3aed6dc11a179c4ab3f77d37791","updated_at":1791926771637,"orders":[]}
len(candidate) = 89
md5(candidate) = 0e850a6f0430e7980bd5d4f1a6c3108c   == the object's ETag
```

(The R2 object body itself reads `403 AccessDenied` for this token — only list is
permitted — so the content is proved by size **and** MD5-of-content == ETag.)

`writeInbox` is fed by `waitingList()`, which is `kvList(store, "order:<id>:")`
(`index.js:484-491`) — a Cloudflare KV **list**, taken in the same request as the
`kvPut` of that very order. KV list is eventually consistent, so the brand-new
order key is not in the list yet and `orders: []` is stored. Nothing refreshes it:
`writeInbox` has exactly four call sites — `index.js:284` (check-in with an
orders array), `:317` (order created), `:364` (state event), `:372` (cancel) —
and a box's check-in sends no orders array, so it only *reads* the inbox.

`r_886571c3` became claimable only at 21:36:52, when an unrelated event (the
throwaway order `r_28cd5454` being cancelled) rewrote the inbox; `r_32ae9427` was
claimed on the first poll because an earlier cancel had already rewritten it.

**Answered: PARTIAL — the replay writes `card-answers.json` (YES); "claims it
within 2 minutes" does NOT hold (measured 11 min 49 s, inbox proven empty).**

---

## SPEC §8 line 6 — "`factory.py next` names the next stage"

**First, exactly what the `poll` line says to run — it fails on a fresh studio run:**

```
$ python3 scripts/core/intake_preflight/factory.py next --run-dir /tmp/operator-mac-DSF-411-tmp/drama-runs/r_32ae9427   # exit 1
{
  "command": "next",
  "data": {
    "missing_path": "/private/tmp/operator-mac-DSF-411-tmp/drama-runs/r_32ae9427/control/state.sqlite3"
  },
  "next_action": "Create the run first (factory.py intake, then preflight); missing state file: …/control/state.sqlite3",
  "outcome": "error",
  "reason_code": "state-file-missing",
  "run_id": "r_32ae9427",
  ...
}
```

`poll` creates `<runs>/<order>/` and replays the card into it; it does **not**
create the run state authority. `INSTRUCTIONS.md` step 5 does ("create the canonical
project structure from section 21: `project.json`, `config.json`, `control/`
(`state.sqlite3`, …)"). So the run folder is completed first, with the skill's own
single writer `state_store.Store` (no second state authority):

```
$ python3 <lane>/create_run_state.py /tmp/operator-mac-DSF-411-tmp/drama-runs/r_32ae9427
created /tmp/operator-mac-DSF-411-tmp/drama-runs/r_32ae9427/control/state.sqlite3
run_id=r_32ae9427 stages=12
   research             NOT_STARTED
   creative-strategy    NOT_STARTED
   script-lyrics        NOT_STARTED
   music                NOT_STARTED
   continuity-bible     NOT_STARTED
   storyboard           NOT_STARTED
   image-keyframes      NOT_STARTED
   video-generation     NOT_STARTED
   qc-retakes           NOT_STARTED
   assembly             NOT_STARTED
   final-qc             NOT_STARTED
   delivery             NOT_STARTED
```

**Then the same command names the stage:**

```
$ python3 scripts/core/intake_preflight/factory.py next --run-dir …/r_32ae9427   # exit 0
{
  "command": "next",
  "data": {
    "command": "python3 scripts/core/research_engine/research.py --brief \"$RUN/brief.json\" --outdir \"$RUN\"",
    "lane_size": { "agents": 1, "ffmpeg_jobs": 3, "ffmpeg_threads": 3, "kie_inflight": 8, "source": "lane_size.module" },
    "produces": "`research/{market,audience,competitors}.md` + `evidence.json` with every claim source-cited.",
    "stage": "research",
    "stages_source": "batch_mode STAGES (batch_mode/batch.py:112-125)"
  },
  "evidence": [ "…/control/state.sqlite3", "…/references/stage-runbook.md" ],
  "next_action": "Run this command for stage 'research'; after it passes its QC gate, run `next` again.",
  "outcome": "ok",
  "reason_code": "next-stage",
  "run_id": "r_32ae9427",
  ...
}
```

**Answered: YES** — with the run folder's state store created first (step 5 above);
on the folder exactly as `poll` left it, `next` answers `state-file-missing`.

---

## SPEC §8 line 7 — "a published script approval shows on the page and a tap on **Looks great** is read back by `approval-answer`"

**Publish (one-line text file in the lane):**

```
$ printf '%s\n' 'DSF-411 e2e script v1: she tries the old way, fails, and the offer saves her the afternoon.' > <lane>/script-v1.txt
$ python3 75-drama-song-ad-factory/shared-bridge/studio_bridge.py publish-approval \
    --order r_32ae9427 --stage script --version 1 --text-file <lane>/script-v1.txt        # exit 0
{
  "answer": null,
  "choices": [],
  "created_at": 1791928378908,
  "files": [],
  "stage": "script",
  "text": "DSF-411 e2e script v1: she tries the old way, fails, and the offer saves her the afternoon.\n",
  "version": 1
}
```

**It shows on the page (the link key reads it, exactly as the phone does):**

```
$ python3 <lane>/ds_api.py approvals r_32ae9427
GET /api/studio/orders/r_32ae9427/approvals -> HTTP 200
{
  "items": [
    { "answer": null, "choices": [], "created_at": 1791928378908, "files": [],
      "stage": "script",
      "text": "DSF-411 e2e script v1: …\n", "version": 1 }
  ],
  "ok": true
}
```

**The tap (link key POSTs the answer):**

```
$ python3 <lane>/ds_api.py answer r_32ae9427 script 1 approve
POST /api/studio/orders/r_32ae9427/approvals/script/answer -> HTTP 200
{
  "answer": { "at": 1791928406602, "by": "link", "value": "approve" },
  "ok": true
}
```

**Read back by the bridge:**

```
$ python3 75-drama-song-ad-factory/shared-bridge/studio_bridge.py approval-answer \
    --order r_32ae9427 --stage script --version 1                                              # exit 0
approve
```

**Answered: YES**

---

## SPEC §8 line 7b — first answer wins (SPEC §4: a second answer is `409 APPROVAL_ANSWER_TAKEN`)

```
$ python3 <lane>/ds_api.py answer r_32ae9427 script 1 "change shot 4"
POST /api/studio/orders/r_32ae9427/approvals/script/answer -> HTTP 409
{
  "code": "APPROVAL_ANSWER_TAKEN",
  "message": "The first answer for this approval is already recorded.",
  "ok": false
}
```

**Answered: YES**

---

## SPEC §8 line 8 — "the old link stops working after `link --new`"

```
OLD link shape: https://studio.zerohumanworkforce.com/#k=<64 lowercase hex, REDACTED>
OLD link BEFORE rotation: GET /api/studio/session -> HTTP 200 (ok=True client_id=c-7315a3aed6dc11a179c4ab3f77d37791)
`studio_bridge.py link --new` -> exit 0
NEW link shape: https://studio.zerohumanworkforce.com/#k=<64 lowercase hex, REDACTED>
client.url written: mode=600 size=105
OLD link AFTER rotation: GET /api/studio/session -> HTTP 401 code=AF-DS-KEY-REVOKED message=That key cannot open this.
NEW link: GET /api/studio/session -> HTTP 200 ok=True key_kind=link client_id=c-7315a3aed6dc11a179c4ab3f77d37791
```

Old link: `200` → `401 AF-DS-KEY-REVOKED`. New link: `200`, same client,
`key_kind=link`. `client.url` stays `0600`.

**Answered: YES**

---

## SPEC §8 line 9 — "KV writes stay low (check-in still writes nothing to KV)"

Measurement is read-only against the live Worker's own KV namespace, using the
operator's own token (value never printed):

```
GET /accounts/13f808b72eb78027a8046357c6cf1afa/storage/kv/namespaces →
   DS_STUDIO  2b543ffb85f546f0a016efd77660ffba
```

**BEFORE one poll:**

```
KV list prefix='checkin:' -> HTTP 200 success=True keys=2
   key: checkin:c-7315a3aed6dc11a179c4ab3f77d37791
   key: checkin:operator-mac-<probe>   # the operator Mac's own check-in key; its literal name carries the retired term, so it is not reproduced here
KV read 'checkin:c-7315a3aed6dc11a179c4ab3f77d37791' -> HTTP 200 value=1791891388093
   (= 2026-10-13T11:36:28.093Z)
R2 ListObjectsV2 prefix='checkin:' -> HTTP 200
   checkin:c-7315…  2026-10-13T21:18:49.064Z
```

**AFTER the poll** (the poll's own check-in ran, then the box claimed the order):

```
KV list prefix='checkin:' -> HTTP 200 success=True keys=2
   key: checkin:c-7315a3aed6dc11a179c4ab3f77d37791
   key: checkin:operator-mac-<probe>   # the operator Mac's own check-in key; its literal name carries the retired term, so it is not reproduced here
KV read 'checkin:c-7315a3aed6dc11a179c4ab3f77d37791' -> HTTP 200 value=1791891388093   # UNCHANGED
R2 ListObjectsV2 prefix='checkin:' -> HTTP 200
   checkin:c-7315…  2026-10-13T21:18:49.064Z
```

Same 2 keys, same value — **zero KV writes from check-in**.

**Positive control (the check-in really runs, and its write lands in R2).**
The check-in record only re-saves every `CHECKIN_SAVE_EVERY_MS` = 20 min, so the
next in-window check-in moved the **R2** object while the **KV** value stayed put:

```
R2 last-write before this call:
   checkin:c-7315…  2026-10-13T21:38:52.169Z          # a check-in at 21:38:52 wrote R2
direct check-in at 2026-10-13T21:40:07.467 -> HTTP 200 {"checked_in_at": 1791927607525, "line": null, "ok": true}
returned at 2026-10-13T21:40:07.672
R2 last-write after this call:  2026-10-13T21:38:52.169Z   (inside the 20-min window: no re-save)
KV after this call:
   keys=2, value=1791891388093                             # unchanged again
```

Across the whole run the page kept reporting fresh check-ins — three separate
`GET /api/studio/session` reads returned `"Last check-in: 4 minutes ago"`,
`"Last check-in: 7 minutes ago"` and `"Last check-in: 5 minutes ago"` — while
the KV record sat at **11:36:28Z**, 10 hours stale and untouched.

Code matches the measurement: `index.js:283` calls
`checkIn(objects, { clientId, nowMs, orders: body.orders })` where
`objects = r2Store(env.DRAMA_STUDIO)`, and `options.js` documents the move
("Stored in R2, not KV: R2's free tier takes the fleet's check-ins, KV's 1,000
writes/day does not").

*Residue, not a write:* two stale `checkin:` keys still sit in KV from before the
fix. Check-in no longer touches them.

**Answered: YES — check-in wrote nothing to KV (0 writes; value byte-identical
before and after), with a live R2 control proving the check-in itself ran.**

---

## The test orders are cancelled by the end

```
$ python3 <lane>/ds_api.py cancel r_32ae9427
POST /api/studio/orders/r_32ae9427/state -> HTTP 200
{ "ok": true, "order": { "order_id": "r_32ae9427", "state": "cancelled",
  "state_reason": "terminal", "cancelled_at": 1791928568121, "last_actor": "link",
  "paid_started": false, "title": "DSF-411 e2e test order", … } }
```

Final session, same link key:

```
GET /api/studio/session -> HTTP 200
draft: None
  order r_32ae9427 state=cancelled title='DSF-411 e2e test order' replies=10
  order r_28cd5454 state=cancelled title='DSF-411 inbox refresh order' replies=10
  order r_886571c3 state=cancelled title='DSF-411 e2e test order' replies=10
waiting: []
```

All three test orders `cancelled` (terminal), **nothing waiting** for any box.
(The cancel was posted with the **link** key — the only state event a link key may
post, SPEC §3.)

---

## Not done here (as the plan says)

**No video was produced** — no KIE credits spent. The proof stops at the first
approval stop: the script approval was published, answered, read back, and the
test order was then cancelled.

---

## Findings carried out of this proof

1. **A fresh order can be invisible to `poll` for many minutes** — SPEC §8 line 5
   measured 11 min 49 s, and the box's inbox object was proven (`md5 == ETag`,
   `Size=89`) to have been written with `orders: []` by that order's own creation.
   Mechanism: `index.js:317` builds the inbox from a KV **list** in the same
   request that `kvPut`s the order (KV list is eventually consistent), and nothing
   rewrites the inbox until a later order event. Evidence: `poll.txt` (0 bytes,
   exit 0), `checkin-direct.txt` (`line: null` at +4 min), R2 `inbox.json`
   `md5 == 0e850a6f0430e7980bd5d4f1a6c3108c` for `orders:[]`.
2. **`factory.py next` cannot run on a folder exactly as `poll` left it** —
   `state-file-missing` for `control/state.sqlite3`. The run folder's step 5
   (state store) has to happen before the command `poll` prints will work.
3. **`studio.py link --new` is documented but not on any merged ref** — it lives
   in 999 branch `unit/DSF-W1-claude-skill-U2`, unmerged; the working command is
   `shared-bridge/studio_bridge.py link --new` (`INSTRUCTIONS.md:245`).
   Likewise 999 `origin/main`'s `studio_bridge.py` still lacks `link`/`poll`/
   `publish-approval`/`approval-answer` (branch `unit/DSF-W3-twin-sync-U2`,
   unmerged), so SPEC §6's "copied byte-identical to 999" is not yet true.
4. **SPEC §3 says a link key is 32 hex; the service mints 64** —
   `keys.js: KEY_BYTES = 32` (bytes).

---

## SPEC §8 line → proven?

| # | SPEC §8 line | Proven | Where above |
|---|---|---|---|
| 1 | a fresh personal link opens the page on the phone | **YES** | line 1 (mint `#k=`+hex, page 200, link-key session 200) |
| 2 | the 9 questions show one per screen with examples | **YES** | line 2 (`/questions.json`, 9/9 with examples) |
| 3 | the draft survives a page reload | **YES** | line 3 (two sessions, same `replies` + `updated_at`) |
| 4 | Lock it in creates an order with replies | **YES** | line 4 (201, 10 replies stored, draft deleted) |
| 5a | …the replay writes `card-answers.json` in the run dir | **YES** | line 5a (file + contents) |
| 5b | …poll claims it within 2 minutes | **NO** | line 5b (11 min 49 s measured; inbox proven empty) |
| 6 | `factory.py next` names the next stage | **YES** | line 6 (stage `research`, after run-folder step 5) |
| 7 | published script approval shows on the page and is read back | **YES** | line 7 (+ 7b: second answer `409`) |
| 8 | the old link stops working after `link --new` | **YES** | line 8 (`401 AF-DS-KEY-REVOKED`, new link 200) |
| 9 | KV writes stay low (check-in writes nothing to KV) | **YES** | line 9 (value unchanged before/after, R2 control) |
| 10 | Hostinger and Contabo `run-timer.sh` + `poll` in a container | **not this unit** | `W4-e2e-proof-U2` |
| — | the test order is cancelled by the end | **YES** | final section (3/3 cancelled, 0 waiting) |
