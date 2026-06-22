# Client-Facing Phrasebook — Skill 06 GHL Install Pages

> **Who this file is for:** The AI agent, not the client. This is the translation
> layer. Before the agent sends ANY message to a client, it checks this file and
> swaps every engineer term for the plain word listed here. Nothing in this file
> is shown verbatim to the client — the CLIENT gets only the delivery template
> at the bottom of this document.
>
> **Source:** Usability analysis in
> `~/Downloads/ghl-factory-research/02-three-builder-rubrics-usability-orgdesign.md`
> (section: `usability`, keys `plainLanguageGaps`, `improvements`, `whatGetsForgotten`).

---

## Part 1 — Phrasebook: Engineer Term to Client Word

These are the only words the agent is permitted to use when messaging a client.
Any word in the left column MUST be replaced with the right column before sending.
No exceptions.

| Engineer term (FORBIDDEN in client messages) | Plain client word (USE THIS) |
|----------------------------------------------|------------------------------|
| funnel | your page |
| website | your site |
| page builder | (say nothing — client never needs this) |
| sub-account | your account |
| step | page |
| step path | web address |
| deploy / deployment | build / put it up |
| draft | only you can see it right now |
| publish | go live |
| published / live | live — anyone can see it now |
| preview URL | a private link just for you to check |
| public URL | your real web address |
| embed | (say nothing — 100% internal, client never hears this word) |
| iframe | (say nothing — 100% internal) |
| Mode 2 | (say nothing — 100% internal) |
| CodeMirror | (say nothing — 100% internal) |
| payload | (say nothing — 100% internal) |
| render | show up / load |
| marker string | (say nothing — 100% internal) |
| X-Frame-Options: DENY | (say nothing — handle it silently) |
| CSP frame-ancestors | (say nothing — handle it silently) |
| HTTP 200 | (say nothing — report only the plain outcome) |
| 375px / 1440px / 1440x900 | on your phone / on your computer screen |
| headless | (say nothing — 100% internal) |
| Firebase token | (say nothing — use the holding message below) |
| IndexedDB | (say nothing — 100% internal) |
| 28-gate | (say nothing — 100% internal) |
| snapshot ref | (say nothing — 100% internal) |
| ZHC prefix | (say nothing — 100% internal) |
| ledger | (say nothing — 100% internal) |
| Vercel | (say nothing — handle hosting silently) |
| CDN | (say nothing — handle it silently) |
| curl returned 200 (PASS) | it loaded correctly |
| content check: 23 HTML elements | (say nothing in client message) |
| Screenshot size: 1440x900 (PASS) | (say nothing in client message) |
| Mobile scroll: no horizontal overflow at 375px (PASS) | looks good on your phone |
| two-factor / 2FA | (say nothing — use the security holding message) |
| sub-account mismatch | (say nothing — use the security holding message) |

### Terms that always stay internal (never reach the client under any circumstances)

The Deployment Report template (from INSTRUCTIONS.md) is **operator/agent log only.**
Never send it to the client. It contains curl codes, viewport dimensions, pixel sizes,
HTML element counts, and screenshot checksums — none of which the client can act on.

The following words are **permanently forbidden** in any client-facing message:

- funnel, website (as GHL product nouns)
- embed, iframe, Mode 2, Vercel
- sub-account, step, step path
- deploy, deployment
- preview URL, public URL
- draft (alone — always pair it with the plain phrase "only you can see it")
- Firebase, token, IndexedDB
- HTTP, curl, 200, 404, PASS, FAIL
- px, viewport, 1440, 375, 768
- CodeMirror, payload, marker, render
- headless, gate, ledger, snapshot, ZHC

---

## Part 2 — Client Delivery Template

Use this EXACT template the moment a build reaches the `previewed` state in the
ledger (Phase 10 / ghl_builder.py ledger state = `previewed`). Send it through
the agent's normal message channel (Telegram or whatever the client uses). Do NOT
wait for the operator to prompt you.

### Template A — Page is ready, still a draft (most common case)

```
Here is your page. Tap to see it:

[PASTE THE PREVIEW LINK HERE — one bare URL, no other text around it]

Right now it is a **DRAFT** — only you can see it. Your customers cannot see it yet.

Reply **GO LIVE** when you are happy with how it looks and want the world to see it.

---
Here is how it looks on your phone:
[ATTACH THE 375px MOBILE SCREENSHOT HERE, labeled "Your page on a phone"]
```

Rules for this template:
- One sentence. One link. One bold line about draft vs live. One screenshot.
- No IDs, no account names, no location IDs, no funnel/step IDs in the link or anywhere.
- The preview link must be the bare URL — no wrapping text like "(preview URL)" or "(draft link)."
- **Bold** the words DRAFT and GO LIVE every single time.
- Always attach the mobile screenshot. The QC step already takes it (375px viewport). Surface it. Do not skip it.
- Never include the Deployment Report in this message. That goes only in the operator log.

### Template B — Page is live (user replied GO LIVE and it published)

```
Your page is now **LIVE** — anyone can see it at:

[PASTE THE PUBLIC URL HERE]

Share that link wherever you like. If you want to make any changes, just tell me.
```

Rules for Template B:
- No IDs, no location IDs, no GHL internal paths.
- The URL must be the real public address, not the GHL preview domain.
- Do not say "published," "deployed," or "funnel." Say "live" and "your page."

### Template C — Build stopped for a security reason (token expired, two-factor, or account mismatch)

```
I hit a security checkpoint on your account and have already pinged my team to
clear it. Your page is safe and saved right where I left it — I will finish the
moment that clears. You do not need to do anything.
```

Rules for Template C:
- NEVER tell the client the technical reason (Firebase token revoked, 2FA, sub-account mismatch).
- NEVER go silent. If the build stops for any operator-side reason, send this message immediately.
- Never say "token," "two-factor," "Firebase," or "sub-account" in this message.

### Template D — Agent needs the client to confirm before building (optional pre-build check)

```
Got it. You want a page where people can [RESTATE THEIR GOAL IN THEIR WORDS].

I will build it as a draft first so you can check it before anyone else sees it.
Once you say it looks good, I will make it live. Sound right?
```

Rules for Template D:
- Use the client's own words for their goal, not internal product names.
- Only ask this one yes/no question. Do not ask about re-entry, publish decisions, or technical details.
- Default is always draft. If the client says yes (or anything that means yes), build it.

---

## How the agent must use this file

1. **Before sending any message to a client:** scan the draft for every forbidden
   term in the table above. Replace with the plain word. If a term has no plain
   substitute (embed, iframe, Firebase, etc.), cut the sentence entirely — that
   information is internal and the client does not need it.

2. **At the `previewed` ledger state:** fire Template A automatically without
   waiting for an operator prompt.

3. **If a build stops for any operator reason:** fire Template C immediately,
   then notify the operator separately through the operator log.

4. **Never expose:** location IDs, funnel IDs, step IDs, page IDs, session IDs,
   API tokens, or any internal reference number in any client-facing message.

5. **Funnel vs Website routing:** resolve this 100% internally. Default is Funnel
   (per SKILL.md A3). The client NEVER hears the words "funnel" or "website" as
   GHL product names. Use "your page" and "your site" only.
