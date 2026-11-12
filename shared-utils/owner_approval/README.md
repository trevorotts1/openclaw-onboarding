# Owner approval flow (one path for every skill)

Use this whenever a skill needs the owner's yes before something goes out or gets written
(weekly social posts, a Black Friday launch step, a Skill 44 automation write). Never tell
the owner to "approve it in the Command Center" without a link. The owner gets the link.

The helper is `shared-utils/owner_approval/owner_approval.py`. It is the ONLY place the
Command Center path lives. It needs `MISSION_CONTROL_URL` and `MC_API_TOKEN` (already on the box).
Installed path: `~/.openclaw/skills/shared-utils/owner_approval/owner_approval.py` (VPS: `/data/.openclaw/skills/shared-utils/...`).

## The five steps

1. **Register the request.** The agent hashes the plan it is asking about (`PLAN_SHA`, the same
   `CAF_PLAN_SHA256` the write gate will check) and runs:
   ```bash
   python3 owner_approval.py request --kind publish --action social_publish \
     --object-key "weekly-2026-11-09" --plan-sha256 "$PLAN_SHA" --skill 35 \
     --summary "Nine posts across Facebook, Instagram and LinkedIn, Nov 9-15, Black Friday theme." \
     --preview-file week-preview.txt --preview-url "$SHEET_OR_PDF_URL"
   ```
   It POSTs `{MISSION_CONTROL_URL}/api/approval-requests` with the bearer `MC_API_TOKEN`, saves
   `request_id` and the owner's link under `~/.openclaw/data/owner-approvals/`, and prints JSON with
   `owner_message`. Asking again about the same plan reuses the same request (no duplicates). A
   changed plan is a new request, because the old approval is bound to the old plan hash.
2. **Message the owner (Telegram or chat)** with the printed `owner_message`: a plain-English
   summary, the preview (the actual posts, or a link to the sheet or PDF), and the direct link to
   approve. Send it in the same message. Never send a bare "awaiting your approval".
3. **Poll, do not nag.** `python3 owner_approval.py wait --request-id RID --shell` (or `status`
   on each heartbeat of the run). Exit 0 and `export CAF_APPROVAL_ID=...` means Command Center
   minted the approval; the agent exports it and proceeds without asking again. Exit 3 pending,
   4 owner asked for changes (read `note`, revise, register a NEW request), 5 expired or revoked
   (register a new one), 6 Command Center unreachable (say so plainly; do not proceed).
4. **Owner says "approved" in chat.** Chat text is never approval. Answer immediately with the
   one-tap link: `python3 owner_approval.py message --request-id RID --chat-said-approved` and send
   it. Do not stall, do not ask the owner to repeat themselves, and do not proceed on the chat text.
5. **Reminders re-send the link.** `python3 owner_approval.py message --request-id RID --reminder`
   prints the same summary, preview and link. Every reminder carries the link.

## Safety rules (unchanged)

- The agent never mints approval. The helper only asks Command Center to create a PENDING request and
  reads the answer. The write gate (`safety_gate.py`) still fetches the record from Command Center and
  checks kind, location, action, object key, plan hash, approver, expiry and revocation. An invented
  id fails. A plan that changed after the owner tapped Approve is refused.
- An env token, a `ZHC-` name, a file the agent wrote, or the owner's chat message is not approval.
- If the preview source (for example the Google Sheet) cannot be read, say so in plain words
  ("I could not open your Google Sheet because my Google sign-in expired") and put the preview
  inline in the message. The approval link is sent either way.

## Contract assumed by the helper

`POST /api/approval-requests` returns `{requestId, approvalUrl}` (a relative `approvalUrl` is joined
to `MISSION_CONTROL_URL`). `GET /api/approval-requests/{requestId}` returns
`{status: pending|approved|changes_requested|expired, approvalId (approved only), approvalUrl, note}`.
Field spellings and paths are constants at the top of `owner_approval.py`.
