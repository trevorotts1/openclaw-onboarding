# Owner approval flow (one path for every skill)

Use this whenever a skill needs the owner's yes before something is built, spent, written or goes out:
the launch plan, copy, the Design Board, wireframes and mockups, a paid image budget, a Skill 44
automation write, a publish. **The owner can approve right inside the conversation they are already in
(Telegram or the OpenClaw chat app), by a Telegram button, or in Command Center. Any of the three
works and none is required.** The review material goes to the owner in the chat, not behind a link.

The helper is `shared-utils/owner_approval/owner_approval.py`. It is the ONLY place the Command
Center path lives. It needs `MISSION_CONTROL_URL` and `MC_API_TOKEN` (already on the box).
Installed path: `~/.openclaw/skills/shared-utils/owner_approval/owner_approval.py` (VPS: `/data/.openclaw/skills/shared-utils/...`).

## Kinds (one path, every kind)

| `--kind` | The approval point | Put in the chat |
|---|---|---|
| `plan_build` | the launch plan (Skill 49 / 83) | the plan in plain words, page list, prices |
| `design_board` | copy, the Design Board, wireframes, mockups, layout proofs (Skills 71 / 83) | the copy text inline; board, wireframe and mockup images or the review PDF attached |
| `paid_asset_budget` | the picture spend ceiling (Skill 83) | the cap, what it buys, the per-image price |
| `automation_write` | a GHL install or automation write (Skills 44 / 35 / 57) | what will be created and where |
| `publish` | going live (Skill 44 draft-off) | the final page or post |
| `stub_render` | placeholder wireframes (Skill 49) | what the placeholders are |
| `pin_rotation` | a key or pin rotation | what changes |

## The steps

1. **Register and deliver in one go.** The agent hashes the plan it is asking about (`PLAN_SHA`, the
   same `CAF_PLAN_SHA256` the write gate checks) and runs:
   ```bash
   python3 owner_approval.py request --kind design_board --action design_board_approve \
     --object-key "landing-board" --plan-sha256 "$BOARD_SHA" --skill 71 \
     --title "Landing page design board" \
     --summary "The look of your landing page: your colors, logo and the real images." \
     --preview-file copy.md --preview-file design-board.png --preview-file mockups.pdf \
     --deliver telegram --target "$OWNER_TELEGRAM_CHAT_ID"
   ```
   `--preview-file` is repeatable. A text file (`.md .txt .json .html`) is shown INLINE in the message; an
   image (`.png .jpg .webp .gif`) or a PDF is ATTACHED. It POSTs `{MISSION_CONTROL_URL}/api/approval-requests`,
   saves the request and the owner's link under `~/.openclaw/data/owner-approvals/`, and with `--deliver
   telegram` sends the message through the gateway (`openclaw message send`, attachments as `--media`, Approve /
   Ask-for-changes buttons as a `--presentation`; if the gateway rejects buttons it resends without them). For
   the OpenClaw chat app (`--deliver webchat`) the helper prints the message and the file list and the agent posts
   them in its own reply with the files attached. Asking again about the same plan reuses the same request. A
   changed plan is a new request, because the old approval is bound to the old plan hash. Re-send later with
   `owner_approval.py deliver --request-id RID --channel telegram --target ID [--reminder]`.
2. **The message always carries** a plain summary, the preview inline, the attached files, the three ways to
   answer, and `Code: <first 6 characters of the request id>`. Never send a bare "awaiting your approval".
3. **The owner answers (any one place).**
   - *In chat.* Their reply ("approve", "yes", "looks good", or "changes: make the headline shorter"). The agent
     does NOT treat it as approval. It runs
     `owner_approval.py chat-decision --request-id RID --decision approve|changes --channel telegram|webchat --source-message-ref <channel>:<chat_or_session_id>:<message_id> [--note "..."]`
     with the reference of the owner's REAL inbound message. Command Center verifies that message really came from
     the owner and mints the record. Exit 0 and the printed id (or `--shell` exports) means approved; exit 4 means
     changes were recorded (read `note`, revise, register a NEW request); exit 7 means Command Center refused with a
     reason: relay the reason in plain words and re-send the link (the output carries a ready `owner_message`).
   - *By button.* A Telegram button tap arrives as the same kind of inbound owner message ("approve ABC123"): handle it
     exactly like a typed reply.
   - *In Command Center.* The owner taps the link. Nothing for the agent to do but wait.
   If more than one request is waiting, match the reply by `Code:` (or by the one request it is plainly about); run
   `owner_approval.py pending` to list them. If a reply is ambiguous ("maybe", "what about the price?"), answer the
   question and ask once; do not guess a decision.
4. **Poll, do not nag.** `python3 owner_approval.py wait --request-id RID --shell` (or `status` on each heartbeat) sees
   an approval from ANY of the three places. Exit 0 and `export CAF_APPROVAL_ID=...`: carry on without asking again.
   Exit 3 pending, 4 changes requested, 5 expired or revoked (register a new one), 6 Command Center unreachable
   (say so plainly; do not proceed).
5. **Reminders re-send everything.** `owner_approval.py deliver --request-id RID --channel telegram --reminder` (or
   `message --reminder`) prints the same summary, preview, three ways to answer and code.
6. **Never re-ask what is already approved.** `deliver` refuses an approved request and `chat-decision` returns the
   existing approval without a second call.

Kinds: `caf` write commands (including `caf social create-post`) are checked as `automation_write`;
use `--kind publish` only for the Skill 44 draft-off (go live) approval.

## Safety rules (unchanged)

- The agent never mints approval. The helper only asks Command Center to create a PENDING request and
  reads the answer. The write gate (`safety_gate.py`) still fetches the record from Command Center and
  checks kind, location, action, object key, plan hash, approver, expiry and revocation. An invented
  id fails. A plan that changed after the owner tapped Approve is refused.
- An env token, a `ZHC-` name, a file the agent wrote, or the agent's own sentence is not approval. The owner's chat
  message becomes approval only when Command Center verifies that real inbound message through `chat-decision` and
  mints the record. The agent only relays what the owner said and which message said it; it never decides for the owner, and a reply Command Center cannot match to the owner is refused.
- If the preview source (for example the Google Sheet) cannot be read, say so in plain words
  ("I could not open your Google Sheet because my Google sign-in expired") and put the preview
  inline in the message. The approval link is sent either way.

## Contract (Command Center `/api/approval-requests`, snake_case)

`POST /api/approval-requests` (Bearer `MC_API_TOKEN`): `{kind: plan_build|paid_asset_budget|publish|automation_write|design_board|pin_rotation|stub_render,
location_id, action, object_key, plan_sha256, title, summary, preview?: {text, links:[{label,url}], images:[https urls]},
requested_by?, expires_at? (how long the owner has to answer, default 7d), valid_until? (end of the window being approved)}`
returns `{request_id, status:"pending", path:"/approvals/<id>", approval_url (absolute, or null: path is used)}`.
`GET /api/approval-requests/<id>` returns `{status: pending|approved|changes_requested|expired, approval_id (null until
approved), decision_note, approval_url, path, short_code, approve_by}`.
`POST /api/approval-requests/<id>/chat-decision`: `{decision: "approve"|"changes", channel: "telegram"|"webchat",
source_message_ref: "<channel>:<chat_or_session_id>:<message_id>", note?}` returns `{status, approval_id}`; a refusal is
403 or 409 with `{reason}`. After a chat approval the helper re-reads the request with GET before it hands out an id.
Paths and field spellings are constants at the top of `owner_approval.py`. Use `--valid-until` for a weekly plan so the
approval outlives the week it covers.

`wait/status/chat-decision --shell` on approval prints four exports so the Skill 44 write gate binds to what was registered:
`CAF_APPROVAL_ID`, `CAF_WRITE_ACTION`, `CAF_OBJECT_KEY`, `CAF_PLAN_SHA256` (`caf social create-post` reads
them; nothing else sets them). Use `eval "$(owner_approval.py wait --request-id RID --shell)"`.
Skills 35, 49, 57, 71 and 83 all use this one helper.
