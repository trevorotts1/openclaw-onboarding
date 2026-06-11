# Skill 44 — Standardized Fleet Announcement Template + Send Runbook

*This is the ONE canonical owner-facing announcement for Skill 44 (Convert & Flow
Operator). It is the standard that goes out fleet-wide once a box has been given Skill 44.
Send it verbatim, substituting only the two placeholders. Do not improvise the wording —
this is the version sent to the first owners (Cassandra, Aurelia) and it IS the standard.*

There are two parts to this file:

1. **THE CANONICAL 3-MESSAGE TEMPLATE** — owner-facing; send to the owner.
2. **THE FLEET-SEND RUNBOOK** — operator-facing; the gate, send mechanics, and receipts.
   Do NOT paste the runbook to an owner.

---

## Placeholders

| Placeholder | Replace with | Source |
|---|---|---|
| `[OWNER_NAME]` | The owner's first name | fleet roster |
| `[AGENT_NAME]` | The box's AI agent name (e.g. Candace, Sir Jordan, Neil) | fleet roster |

Substitute both everywhere they appear, in all three messages, before sending.

---
---

# PART 1 — THE CANONICAL 3-MESSAGE TEMPLATE (owner-facing)

Send these as **three separate messages, in order**, through the client's own OpenClaw
gateway. Verify each send before the next.

---

## MESSAGE 1 — The congratulations + what it unlocks

> 🎉 Congratulations, [OWNER_NAME]! Your AI agent just leveled up.
>
> The Rescue Rangers just installed **Skill 44 — the Convert & Flow Operator** on your
> setup. In plain English: [AGENT_NAME] can now **BUILD automation workflows for you
> inside Convert & Flow** (the system some folks know as GoHighLevel) — appointment-booking
> follow-ups, lead-nurture sequences, tag-and-text automations. You just describe it in a
> message, and [AGENT_NAME] builds it as a **draft for you to review** before anything goes
> live.
>
> There's just **ONE final 5-minute, one-time token setup** to switch this on. The next
> two messages walk you through it, step by step.
>
> If you'd rather have help, just reach out to Trevor and he'll handle it with you. 💪

---

## MESSAGE 2 — 🔑 FINAL SETUP (Part 1 of 2)

> 🔑 **FINAL SETUP — Part 1 of 2** (about 5 minutes total)
>
> To let [AGENT_NAME] build these automations, it needs a secure "key" (a token) from your
> own Convert & Flow account — just like handing over a spare key, one time only. We've made
> a tiny, free Chrome helper called the **Convert & Flow Token Grabber** that fetches that
> key for you in two clicks. It only reads the key from your own browser and copies it — it
> never sends your information anywhere.
>
> **1️⃣ Download the tool.**
> Open this link:
> https://drive.google.com/file/d/1WJYUm80PIeUy_oI82fPx65gQz7mgVVxp/view?usp=sharing
> Click the **Download** button — it's the **down-arrow (⬇)** near the top of the page. The
> file lands in your **Downloads** folder. **Double-click** the downloaded `.zip` to unpack
> it into a folder, and **remember where that folder is** — you'll point to it in step 4️⃣.
>
> **2️⃣ Open Chrome's extensions page.**
> Click into Chrome's address bar at the top, type **`chrome://extensions`**, and press
> **Enter**.
>
> **3️⃣ Turn on Developer mode.**
> Look at the **top-right** corner of that page for a switch labeled **"Developer mode."**
> Click it so it turns **ON** (it turns blue).
>
> **4️⃣ Load the tool.**
> Now look at the **top-left** — click the **"Load unpacked"** button. A file window opens.
> Find and select the **folder you unpacked in step 1️⃣**, then click **Select** (or
> **Open**).
>
> **5️⃣ Pin it so it's easy to find.**
> Up near Chrome's address bar, click the little **puzzle-piece icon (🧩)**. In the menu that
> drops down, find **"Convert and Flow Token Grabber"** and click the **push-pin (📌)** next
> to it. A small **pinkish icon** now sits in your toolbar.
>
> *(Part 2 coming next…)*

---

## MESSAGE 3 — 🔑 FINAL SETUP (Part 2 of 2)

> 🔑 **FINAL SETUP — Part 2 of 2**
>
> **6️⃣ Log into Convert & Flow fresh.**
> Open **Convert & Flow** in Chrome. To make sure the key is current, **log out, then log
> back in.** Leave that tab open.
>
> **7️⃣ Grab and copy the key.**
> Click the **pinkish icon** in your toolbar. A little box pops up — click
> **"Grab the token,"** then click **"Copy the token."** The key is now copied, ready to
> paste.
>
> **8️⃣ Send it to me here.**
> Come back to **THIS chat** and send me the key, exactly like this:
>
> *Here is the Convert and Flow GHL Firebase token: (paste the token here) — please add this
> to my environments file and confirm that it works.*
>
> Once I confirm it's working, you're fully set up. To see it in action, just send:
>
> *Use Skill 44 and create me a test workflow.*
>
> …and [AGENT_NAME] will build you a small **draft** test workflow so you can see it work.
>
> Stuck on any step, or something looks different on your screen? Message Trevor — he's got
> you. 💪

---
---

# PART 2 — FLEET-SEND RUNBOOK (operator-facing — do NOT paste to the owner)

This is how the operator (or a client agent under operator command) sends the announcement
fleet-wide. One client at a time, verified each step.

## GATE — who may receive the announcement

A box may receive this announcement **ONLY** when its ledger shows **skill44 remediation
complete**, defined as either:

- **Fully live** — caf engine **≥ 2.1.1** AND the GHL credentials are wired into the
  **gateway-inherited** env such that **a live `caf` read actually works** (ground-truth, not
  a `config set` return value). In this state, all three messages go out as written.
- **Token-pending** — engine ≥ 2.1.1 and the PIT/location creds are wired (standard caf reads
  work), but the Firebase token is not yet present. In this state **the announcement IS the
  token ask** — that is exactly what Messages 2 and 3 walk the owner through, so it is correct
  to send.

**NEVER announce a capability that is not live on that box.** If the box fails the gate
(engine < 2.1.1, or caf reads do not work on the inherited env), do not send — finish the
skill44 remediation first, update the ledger, then announce.

## SEND MECHANICS

- **Always via the client's OWN OpenClaw gateway** — never the direct Telegram API:
  ```bash
  openclaw message send --channel telegram -t <owner_chat_id> "<message text>"
  ```
- **One client at a time.** Do not batch-blast the fleet.
- **Substitute `[OWNER_NAME]` / `[AGENT_NAME]`** from the fleet roster before sending.
- **Verify each send** — check the **exit code** AND that a **message id** came back — before
  sending the next message. All **three messages, in order** (1 → 2 → 3).

## RECEIPTS

After a client's three messages are confirmed sent, append one line per client to the
operator ledger:

```json
{"box":"<name>","item":"skill44-owner-announcement","sent":3,"messageIds":[<id1>,<id2>,<id3>],"ts":"<utc iso>"}
```

The ledger is the source of truth for who has been announced — read it before sending so you
never double-announce.

## ALREADY ANNOUNCED — do NOT duplicate

| Box | Message ids | Date |
|---|---|---|
| `cassandra` | 12524, 12525, 12526 | 2026-06-11 |
| `aurelia` | (sent) | 2026-06-11 |

Skip any box already present in this list / the operator ledger.

---

*Owner-facing download link (keep prominent in Message 2):*
**https://drive.google.com/file/d/1WJYUm80PIeUy_oI82fPx65gQz7mgVVxp/view?usp=sharing**
