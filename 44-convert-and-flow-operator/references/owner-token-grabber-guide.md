# Setting Up Your Convert & Flow Automations — A Simple Walkthrough

*This is a friendly, owner-facing guide. Your AI agent can send it to you, or walk
you through it one step at a time. There is nothing technical to understand here —
just a few clicks, one time only.*

---

## What this unlocks for you

Your AI agent can now **build automation workflows for you inside Convert & Flow**
(the system some folks know as GoHighLevel). In plain terms, that means the busywork
that used to eat your day can run on its own:

- **Appointment-booking follow-ups** — someone books a call, and the right reminders
  and confirmations go out automatically.
- **Lead nurture** — a new lead comes in, and a thoughtful series of messages keeps
  them warm without you lifting a finger.
- **Tag-and-text automations** — when a contact does something (or you tag them), the
  right text or email goes out at the right time.

Here is the wild part: **you don't have to build any of it — you do it JUST BY TALKING.**
You just tell your agent, in your own words, what you want — *"When someone books a
discovery call, send them a confirmation text right away and a reminder the morning of."*
Your agent builds it for you as a **draft you can review** before anything goes live. No
clicking around, no tech setup, no watching tutorials. Nothing turns on without your okay.

And this isn't something everyone has — this is the **only system in the world that can do
this right now**, and it's installed on your setup. 🌎

There is just **one small setup step**, and you only ever do it once. After that, your
agent can build automations for you anytime, just by asking.

---

## The one-time setup: the Token Grabber

To let your agent build these automations, it needs a secure "key" from your own
Convert & Flow account. We've made a tiny helper — a free Chrome browser tool called
the **Convert & Flow Token Grabber** — that fetches that key for you in two clicks.

**Download it here:**

### 👉 https://drive.google.com/file/d/1WJYUm80PIeUy_oI82fPx65gQz7mgVVxp/view?usp=sharing

> This little tool only reads the key from your own browser and copies it for you. It
> never sends your information anywhere. You install it once, use it, and you're done.

Take your time — the steps below are written to be followed slowly. If anything feels
unclear, send your agent a message and it will walk you through that exact step.

---

## The 8 steps

**1. Download the tool.**
   Open the link above. Click the **Download** button — it's the **down-arrow (⬇)** near
   the top of the page. The file lands in your **Downloads** folder. **Double-click** the
   downloaded `.zip` file to unpack it into a folder. **Remember where that folder is** —
   you'll point to it in step 4. (If it unpacked to Downloads, it's right there.)

**2. Open Chrome's extensions page.**
   Click into Chrome's address bar at the top, type **`chrome://extensions`**, and press
   **Enter**.

**3. Turn on Developer mode.**
   Look at the **top-right** corner of that page for a switch labeled **"Developer mode."**
   Click it so it turns **ON** (it turns blue).

**4. Load the tool.**
   Now look at the **top-left** — click the **"Load unpacked"** button. A file window opens.
   Find and select the **folder you unpacked in step 1**, then click **Select** (or
   **Open**). The Token Grabber now appears in your list.

**5. Pin it so it's easy to find.**
   Up near Chrome's address bar, click the little **puzzle-piece icon (🧩)**. A small menu
   drops down — find **"Convert and Flow Token Grabber"** in the list, and click the
   **push-pin (📌)** next to it. A small **pinkish icon** now sits in your toolbar, ready
   whenever you need it.

**6. Log into Convert & Flow fresh.**
   Open **Convert & Flow** in Chrome. To make sure the key is current, **log out, then log
   back in.** Leave that tab open.

**7. Grab and copy the key.**
   Click the **pinkish icon** in your toolbar. A little box pops up — click
   **"Grab the token,"** then click **"Copy the token."** That's it — the key is now copied,
   ready to paste.

**8. Send it to your agent.**
   Message your agent and paste it in, exactly like this:

   > *Here is the Convert and Flow GHL Firebase token: (paste the key here) — please add
   > this to my environments file and confirm that it works.*

   Wait for your agent to confirm it's working. Once it does, you're fully set up. To see
   it in action, just send:

   > *Use Skill 44 and create me a test workflow.*

That's the whole thing. From now on, anytime you want an automation, just describe it to
your agent and it builds you a draft to review.

---

## A note on the key

The key (the "token") is a private credential, just like a password. Only ever paste it
to **your own agent** — never share it with anyone else. If it ever stops working down the
road (keys can expire), your agent will let you know, and you'll simply repeat steps 6 and
7 to grab a fresh one. Nothing else to redo.

---
---

## ⚙️ FOR THE AGENT — wiring + first build (not part of the owner walkthrough)

> This section is for the box agent receiving the owner's pasted token. It is deliberately
> separated from the owner-facing walkthrough above. Do not paste this section to the owner.

When the owner pastes their token with a message like *"Here is the Convert and Flow GHL
Firebase token: …"*, do the following:

### 1. Wire the token into the gateway-inherited environment

The canonical env var is **`GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN`** (the wrapper also accepts
`CAF_FIREBASE_REFRESH_TOKEN` as an alias; write the canonical name).

- **All boxes** — set it in OpenClaw's config so the gateway inherits it:
  ```bash
  openclaw config set env.vars.GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN "<pasted-token>"
  ```
- **Hostinger VPS boxes (additionally)** — the wrapper at `/hostinger/server.mjs` rebuilds
  env from `/docker/<project>/.env` on every boot, so the token must also live there.
  **Replace the empty placeholder** (do not append a duplicate):
  ```
  GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN=<pasted-token>
  ```
  then `docker compose up -d --force-recreate` so the container picks it up.

Do not invent new key paths. Use the canonical var name above exactly.

### 2. Verify on the INHERITED env with a real `caf` read

Do not trust the `config set` return value alone — confirm the *running gateway* actually
inherited the token by exercising a real workflow-write-capable read:

```bash
caf doctor        # Firebase token check should now report OK (not WARN)
```

The token is what unlocks workflow BUILD/EDIT. A green `caf doctor` Firebase line (or a
successful authenticated workflow read on the inherited env) is the ground-truth confirmation
— report success to the owner only after seeing it.

### 3. Build the test workflow — DRAFT ONLY, ZHC- prefixed

When the owner then says *"Use Skill 44 and create me a test workflow,"* build it:

- **Draft only** — `GOHIGHLEVEL_DRAFT_ONLY=true` is the default; never publish without a
  second explicit approval.
- **ZHC- prefixed name** — name the workflow (and any folder) with the `ZHC-` prefix so it
  carries standing approval (no `CAF_APPROVAL_TOKEN` prompt) per the skill 41 contract.
- Surface the resulting draft to the owner for review; nothing goes live silently.

### 4. Retry once on a transient token error

If a workflow write returns a transient **"token refresh failed"** (or similar refresh
error), **retry the operation exactly once** before telling the owner anything is wrong.
Only if the retry also fails do you surface the issue — and then nudge the owner to re-grab
a fresh token (steps 6-7 of the owner walkthrough above).

---

*Owner-facing setup link (keep prominent):*
**https://drive.google.com/file/d/1WJYUm80PIeUy_oI82fPx65gQz7mgVVxp/view?usp=sharing**
