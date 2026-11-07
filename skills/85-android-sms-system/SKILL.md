---
name: android-sms-system
description: Answer myCRMSIM (CRM SIM) questions from its complete offline support documentation — Android SMS gateway app install and device setup, SIM assignment and sub-account assignment, Android SMS, iMessage, WhatsApp, RCS, voice calling, HighLevel / HubSpot / Zapier / Make / Salesforce / Zoho integration, sub-account connection and sync, message pending or queued failures, deliverability and error codes, WhatsApp warm-up, and snapshot workflows. Use whenever the agent must answer a how-to, configuration or troubleshooting question about myCRMSIM, CRM SIM, the myCRMSIM smsgateway Android app, or CRM-connected SMS / WhatsApp / iMessage / RCS sending.
---

# Android SMS System

Answer myCRMSIM support questions from the shipped documentation set. This file is a map. The answers live in the articles, not here.

## What This Skill Is

myCRMSIM is a CRM-connected messaging platform that sends SMS, WhatsApp, iMessage and RCS through real Android phones and Macs rather than through a carrier API. The Android device is the gateway: the myCRMSIM smsgateway app pairs a phone to the platform, the phone's SIM actually sends the message, and HighLevel (or HubSpot, Salesforce, Zoho, Zapier, Make) drives the campaign.

This skill gives the agent a route into the 156-article offline documentation set so it can quote the real steps instead of inventing them. It is a pointer, not a copy. No article text is duplicated here.

## When It Triggers

Trigger on any of these, in help-desk or client-support phrasing:

- **Platform** — "myCRMSIM", "CRM SIM", "myCRMSIM dashboard", "myCRMSIM snapshot", "MCS-###" article numbers.
- **Android SMS gateway** — install the APK, Play Protect warning, QR pairing, Firebase token, permissions, keep-alive, battery optimization, "SMS gateway is sending a large number of messages" alert, `increase-sms-limit.bat`, ADB.
- **SIM assignment** — adding multiple SIMs, multi-SIM load spreading, assigning a SIM or device to a sub-account user, replying from the correct SIM.
- **Channels** — Android SMS, MMS (800 KB limit), iMessage setup, WhatsApp install and device setup, WhatsApp warm-up, RCS install and phone requirements, RCS off / SMS fallback, voice calling, verified caller ID, call routing, landline for calling, voice agent.
- **Integrations** — HighLevel / Lead Connector marketplace app install, HubSpot, Zapier, Make, Salesforce, Zoho CRM, Google Sheets, custom workspace and webhook.
- **Sub-account** — connecting and syncing sub-accounts, automatic contact creation from inbound SMS, multiple devices on one sub-account, per-user sending.
- **Symptom language** — "message pending", "stuck in queued", "messages not sending", "messages failing", deliverability, error codes (`NO_SERVICE`, `RADIO_OFF`, `LIMIT_EXCEEDED`, `GENERIC_FAILURE`), drip mode, SIM ban, message routing and fallback order, stopping an accidental campaign.
- **Automations and AI** — workflows, database reactivation, drip campaign template, Google Reviews workflow, Message Buddy / Conversation Buddy, AI agents, lead capture forms, surveys (CSAT/NPS), pipeline.

If the question is about myCRMSIM at all, this skill applies. Route it through the docs.

## Where The Documents Live

Resolve the docs root in this order and use the first one that exists —
`$HOME` is the home directory of the user running the agent:

1. `$ASMS_DOCS_DIR`, when that environment variable is set
2. `docs/` beside this `SKILL.md`
3. `$HOME/Downloads/openclaw-master-files/mycrmsim` (the usual location)

```
$HOME/Downloads/openclaw-master-files/mycrmsim
```

The entry point — always the first file opened — is:

```
$HOME/Downloads/openclaw-master-files/mycrmsim/00-INDEX.md
```

What sits inside the set:

| Path | Contents |
|---|---|
| `00-INDEX.md` | All 156 articles grouped under 7 top-level categories, each with Doc ID, title, relative link and a one-line summary |
| `articles/` | The 156 articles themselves, in the same category tree the site uses |
| `categories/` | 36 category index pages |
| `_assets/` | Not installed by design — the 660 images were deleted to keep the repo small |
| `_source-html/` | Raw pages for provenance — removed in cleanup; not needed to answer |
| `_manifest.json` | Machine-readable index of every document |
| `_labels.json` | Article labels and metadata |

Screenshots are not bundled: answers come from the article text, and the 660 image reference lines in the articles (`![alt](../../../_assets/MCS-0NN/file.gif)`) are expected and harmless — the files are absent on purpose.

The 7 top-level categories under `articles/`:

1. `01-Devices and Installation` (71 articles)
2. `02-Frequently Asked Questions` (47)
3. `03-Getting Started` (1)
4. `04-Integrations` (14)
5. `05-Automations and AI Agents` (5)
6. `06-myCRMSIM Dashboard` (17)
7. `07-Talk To The Team` (1)

Article filenames keep their Doc ID, so a path is predictable:
`articles/<category folder>/<subfolder>/MCS-131 - Setting Up Your Android Device with myCRMSIM SMS Gateway.md`

## How To Answer A Question

Follow this order every time. Do not skip to memory.

1. **Open `00-INDEX.md`.** It is the only entry point. Never guess a path from memory.
2. **Find the category.** Match the question to one of the 7 top-level categories, then the sub-heading inside it (for example Devices and Installation → myCRMSIM SMS Installation and Setup → SMS Trouble Shooting).
3. **Read the matching article in full.** The article is complete and never truncated — read the whole file, including its labelled header (Doc ID, category path, site update age, source URL, download date). Do not summarise from the index's one-line blurb alone.
4. **Quote the steps.** Give the real numbered steps, real menu names, real button labels, real error codes, real file sizes and real time limits exactly as the article states them. Name the Doc ID and the article title so the user can open it themselves.
5. **Never invent.** No plausible-sounding menu path, no guessed setting name, no fabricated error code, no imagined screenshot. If the set does not answer it, say so plainly and name what you checked — then point to `07-Talk To The Team` or myCRMSIM support.
6. **Check a related article before declaring a gap.** Troubleshooting questions usually span two: the setup article and a troubleshooting article. Read both before answering.
7. **Do not promise a screenshot.** The image files are not bundled. Where an article leans on an illustration, describe the step in words from the surrounding text instead.

Common routing shortcuts:

| Question shape | Start here |
|---|---|
| Will not send / pending / queued | `articles/01-Devices and Installation/01-myCRMSIM SMS Installation and Setup/01-SMS Trouble Shooting/` — MCS-138, MCS-015, MCS-134 |
| Install or reinstall the Android app | `01-SMS Device Setup/` — MCS-131, MCS-132, MCS-126 |
| RCS | `01-myCRMSIM RCS Installation and Setup/` — MCS-088, MCS-089, MCS-085, MCS-086; RCS off / SMS fallback is MCS-049, under `01-How to install and Setup myCRMSIM/` |
| WhatsApp | `myCRMSIM WhatsApp Installation and Setup/`, `WhatsApp Device Setup/`, `WhatsApp Warm-Up Guide/` |
| iMessage | `myCRMSIM iMessage Installation and Setup/`, `iMessage/` |
| Calls | `01-Integrating Twilio-Lead Connector for calls/` — MCS-010, MCS-058; dashboard MCS-074, MCS-151 |
| CRM integrations | `articles/04-Integrations/` — HighLevel, HubSpot, Zapier, Make, Salesforce, Zoho |
| Snapshot templates | `01-myCRMSIM Snapshot/` — MCS-091, MCS-092, MCS-093 |
| Dashboard, contacts, conversations, pipelines | `articles/06-myCRMSIM Dashboard/` |

## What It Does Not Cover

- It does not configure, install, or mutate a live myCRMSIM account, HighLevel agency, or Android device. It answers questions from documentation.
- It does not cover GoHighLevel / Convert and Flow API and credential setup — that is skill `05-ghl-setup` (and skill 36 for GHL MCP).
- It does not cover general fleet operations, SSH access, OpenClaw gateway management, or other client boxes.
- It does not cover carrier-side porting. Articles MCS-050 and the porting category state plainly that porting out of Twilio or Lead Connector is handled by those providers and myCRMSIM does not assist.
- It does not cover areas myCRMSIM support explicitly declines to help with — check `Before You Get Started` (MCS-047) for the current list before promising anything.
- It does not guarantee the documentation is current. Each article carries a site update age; when the age looks stale or the UI has clearly moved, say so and defer to live support.

## Next

Point-in-time execution steps, defaults and file-by-file reading order for this skill folder live in `$HOME/Downloads/openclaw-master-files/85-android-sms-system/INSTRUCTIONS.md`.
