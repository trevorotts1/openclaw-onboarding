# GK-01 / U63 — Cover art, third pass (2026-07-16)

## Unblock condition met this pass

The prior two passes (see `README.md` in this directory) declined to fabricate
episode cover art or guess `client_email` without primary-source, non-relayed
operator authorization, because this podcast is a real, live, full-management
client account — a one-way-door action on that account's public feed is not a
decision an agent makes unilaterally.

This pass's dispatch carries a direct, verbatim quote of the operator's own
words, explicitly authorizing exactly this action in his capacity as the
full-management operator of this account (no client approval required for that
reason): *"Just create some dummy content, create some cover art, use my email
address. I don't care… Make some cover art up… Verify email:
trevor@blackceo.com. Stop stalling. Get it done."* That satisfies the
"real client-approved cover art... AND a verified client email" unblock branch
recorded in the ledger's prior OPERATOR DECISION (the operator IS the approving
party for this full-management account).

## What was generated

- File: `episode-cover-u63.jpg` (this directory), 1500x1500px, JPEG, RGB, 72dpi,
  ~90KB (well under Podbean's 512KB cap; within the 1400-3000px square window;
  filename uses only letters/numbers/underscore/dash — all per Podbean's
  published episode-image spec, confirmed this pass:
  https://help.podbean.com/support/solutions/articles/25000005083-adding-the-episode-logo-to-my-episode ,
  https://help.podbean.com/support/solutions/articles/25000005097-podbean-supported-file-formats-and-single-file-size-limit ).
- Content: a generic, wordless, abstract design — soundwave rings and a
  stylized microphone silhouette on a navy-to-teal gradient with minimal
  geometric corner framing. No client or human name, no invented business
  name/logo, nothing that represents or misrepresents any real person or
  business — a neutral placeholder mark, exactly as the operator authorized
  ("make some cover art up").
- Verified email for the publish payload's `client_email` field: `trevor@blackceo.com`
  (the operator's own address, per his explicit instruction).

## Hosting for the live n8n fetch

The live workflow's `Download Image — Fetch From GHL URL` node does a plain
HTTP GET on whatever `image_url` string is in the payload — it is not actually
GHL-specific despite the node's name/notes (confirmed by reading the node's
`httpRequest` parameters live: `url = {{ ...image_url }}`, `authentication:
none`). This repo (`trevorotts1/openclaw-onboarding`) is a **public** GitHub
repo (confirmed `gh repo view --json visibility` → `PUBLIC`), so a
`raw.githubusercontent.com` URL to the file on this branch is a valid,
anonymously-fetchable `http(s)://` URL satisfying the entry guard's URL-shape
check, without needing any client GHL Media Library access (which stays
out of scope per standing doctrine — operator and client credential lanes
never cross).

Raw URL used for this pass's `image_url`:
`https://raw.githubusercontent.com/trevorotts1/openclaw-onboarding/proof/u63-live-publish/ledgers/evidence/GK-01-U63/episode-cover-u63.jpg`

This branch is pushed, NOT merged, per dispatch instruction. The live retry
execution (below, appended after the publish attempt) depends on this file
being reachable at that raw URL on this branch — do not delete/rename this
file or force-push this branch until GK-01/U63 is fully closed out and any
follow-on unit no longer needs the evidence trail.
