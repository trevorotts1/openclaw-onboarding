# Android SMS System — Operating Instructions

This is the day-to-day procedure for answering myCRMSIM questions from the offline support documentation. Every answer comes from the saved articles, in their own order — never from memory.

The documentation set is installed on this machine at:

```
$HOME/Downloads/openclaw-master-files/mycrmsim/
```

| Path | What it is |
|---|---|
| `00-INDEX.md` | Master index: all 156 articles, Doc IDs, titles, one-line summaries, grouped by category |
| `articles/` | All 156 articles as Markdown, inside 7 category folders |
| `categories/` | The 36 category index pages |
| `_manifest.json` | Machine-readable list of every doc: `doc_id`, `title`, `file`, `category`, `updated`, `path_cat` |
| `_labels.json`, `_labels-parts/` | Label data |
| `_assets/<Doc ID>/` | Screenshots and GIFs, linked relatively so the set reads offline |
| `_source-html/` | Original saved pages — removed in cleanup; never the answer source |

Covered: Android SMS, MMS, iMessage, WhatsApp, RCS, voice calling, devices and SIMs, HighLevel / HubSpot / Zapier / Make / Salesforce / Zoho integrations, automations and AI agents, the myCRMSIM dashboard, snapshot workflows, and troubleshooting.

---

# The Six-Step Loop

Follow these in order. Do not skip to an answer.

## Step 1 — Identify the channel and the symptom

Pin down two things before opening a file: **which channel** the person is on, and **what they actually see**. A channel answer and a symptom answer are different lookups, and confusing them sends you to the wrong folder.

**Channels:**

| Channel | Typical wording |
|---|---|
| Android SMS | "texts", "SMS", "smsgateway app", "SIM", "Android phone" |
| MMS | "picture message", "send an image", "attachment too large" |
| iMessage | "blue bubble", "iMessage", "Apple", "Mac" |
| WhatsApp | "WhatsApp", "WhatsApp Business", "warm-up", "QR" |
| RCS | "RCS", "Google Messages", "chat features", "Connected" |
| Voice calling | "calls", "caller ID", "landline", "call routing", "voice agent" |

**Symptoms** (these route on their own — see the Symptom Routing table below): messages Pending or Queued, nothing sends after an Android OS update, an error code, the phone warns about a large number of messages, MMS fails, RCS shows disconnected, a campaign went out by accident, calls do not ring, a device or SIM is stuck or duplicated, delivery status is unclear.

If the person names a tool instead of a channel — HighLevel, HubSpot, Zapier, Make, Salesforce, Zoho, Google Sheets — the channel is still whatever carries the message; the tool decides the folder, which is `04-Integrations`.

## Step 2 — Open `00-INDEX.md` and pick the category folder

Read the index first. It is the fastest map of all 156 articles, and every entry carries the Doc ID, the title, a one-line summary and the article path. Use it to choose one folder, then go into that folder.

### Channel-to-folder routing table

Folder names below are exact, including spaces and numbering. All are directly under `articles/`.

| Channel / topic | Primary folder under `articles/` | Subfolders and files inside it |
|---|---|---|
| Android SMS install & setup | `01-Devices and Installation` → `01-myCRMSIM SMS Installation and Setup` | `01-SMS Device Setup`, `01-SMS Trouble Shooting`, `01-myCRMSIM Snapshot`, `01-Integrating Twilio-Lead Connector for calls`, `01-How to create conversation SMS with Message Buddy`, `01-How To Port Numbers Out Of Twilio or Lead Connector`, `01-myCRMSIM White Label Install Instructions` |
| iMessage | `01-Devices and Installation` → `01-myCRMSIM iMessage Installation and Setup` | `01-Before You Get Started`; troubleshooting article `MCS-081 - iMessage Trouble Shooting.md` at folder level |
| WhatsApp | `01-Devices and Installation` → `01-myCRMSIM WhatsApp Installation and Setup` | `01-WhatsApp Device Setup`, `01-WhatsApp Warm-Up Guide`, `01-How To Disconnect Your WhatsApp Account From myCRMSIM`; `MCS-107 - WhatsApp Troubleshooting Guide.md` at folder level |
| RCS | `01-Devices and Installation` → `01-myCRMSIM RCS Installation and Setup` | RCS install, phone specifications, multiple RCS devices, disconnect; plus `MCS-148 - RCS Troubleshooting Guide.md` at the `01-Devices and Installation` level and `MCS-049 - RCS Setting.md` under `01-How to install and Setup myCRMSIM` |
| Voice calling | `01-Devices and Installation` (folder level) | `MCS-147 - Android Calling Setup – myCRMSIM.md`; caller ID and landline articles under `01-myCRMSIM SMS Installation and Setup/01-Integrating Twilio-Lead Connector for calls`; also `06-myCRMSIM Dashboard/MCS-074 - 📞 Call Routing.md` |
| Devices, SIMs, assignment, disconnects | `01-Devices and Installation` (folder level) | `MCS-016` (assign / transfer / change / remove SIMs and devices), `MCS-149 - Connect your OpenVox box`, `MCS-017 - myCRMSIM Twilio Integration and Setup Guide`; `MCS-152 - How to Disconnect or Remove a Device from myCRMSIM` sits in `06-myCRMSIM Dashboard` |
| CRM and app integrations | `04-Integrations` | `04-HighLevel Setup`, `04-HubSpot Integration`, `04-Make Integration`, `04-Salesforce Integration`, `04-Zapier Integration`, `04-Zoho CRM Integration`; `MCS-059 - Google Sheets Integration with myCRMSIM.md` at folder level |
| Automations, triggers, AI agents | `05-Automations and AI Agents` | Automations guide, AI agents with HighLevel, link-clicked trigger, missed-call text-back (two articles), advanced missed-call automation |
| Dashboard, contacts, conversations, pipelines, forms, widget, DBR, MCP, voice agent, delivery status, surveys | `06-myCRMSIM Dashboard` | Includes `06-Custom Workspace and Webhook Integration Guide`, `MCS-034` Quick Start, `MCS-063` API, `MCS-065` chat widget, `MCS-066` DBR campaign, `MCS-067` lead capture forms, `MCS-068` delete bulk queued, `MCS-070` contacts, `MCS-071` conversations, `MCS-072` pipeline, `MCS-150` MCP, `MCS-151` voice agent, `MCS-154` message status, `MCS-155` Tailscale screen sharing, `MCS-156` surveys |
| First-time setup / reactivation basics | `03-Getting Started` | `MCS-033 - Getting Started with myCRMSIM and Database Reactivations.md` |
| Short answers and FAQs | `02-Frequently Asked Questions` | `02-Calls`, `02-Dashboard`, `02-General`, `02-iMessage`, `02-Phone`, `02-SMS` |
| Reaching a human | `07-Talk To The Team` | `MCS-139 - Book A Call With Us.md` |

### Symptom routing table

| Symptom | Go here first |
|---|---|
| Messages stuck in Pending or Queued | `01-Devices and Installation/01-myCRMSIM SMS Installation and Setup/01-SMS Trouble Shooting/MCS-015` then `MCS-138 - SMS Troubleshooting.md` |
| Nothing sends after an Android OS update | `…/01-SMS Trouble Shooting/MCS-126` |
| Specific failure, error code shown | `…/01-SMS Trouble Shooting/MCS-134 - Error Codes.md` |
| Phone warns it is sending a large number of messages | `…/01-SMS Trouble Shooting/MCS-133 - Bypassing the SMS Gateway is Sending a Large Number of Messages Alert on Android.md` |
| MMS or image fails | `…/01-SMS Trouble Shooting/MCS-118 - Can I Send MMS Messages.md` |
| RCS disconnected, or incoming RCS never arrives | `01-Devices and Installation/01-How to install and Setup myCRMSIM/MCS-049 - RCS Setting.md`, then `01-Devices and Installation/MCS-148 - RCS Troubleshooting Guide.md` |
| Campaign went out by accident, need to stop it | `…/01-SMS Trouble Shooting/MCS-136` |
| Calls do not connect, caller ID wrong, landline | `01-Devices and Installation/MCS-147`, `06-myCRMSIM Dashboard/MCS-074`, `02-Frequently Asked Questions/02-Calls` |
| Device duplicated, wrong SIM replying, device removal | `MCS-016`, `MCS-152`, `02-Frequently Asked Questions/02-Phone` |
| Delivered / not delivered, status unclear | `06-myCRMSIM Dashboard/MCS-154 - Message Status and Delivery Troubleshooting.md` |
| Integration missing fields, mirroring, sync | `04-Integrations/<the exact CRM folder>` |

## Step 3 — Read the specific article

Open the file named in the index. Every article starts with a labeled header you can trust:

```
> **Doc ID:** MCS-131
> **Category:** SMS Device Setup
> **Site updated:** 4 days ago
> **Source:** https://support.mycrmsim.com/article/...
> **Downloaded:** 2026-11-05 from myCRMSIM Support Center
```

Read the whole article before replying. If it cites another article or an outbound support link, that reference is part of the answer. Screenshots live at `_assets/<Doc ID>/` and are already linked relatively — if a step depends on seeing a screen, name the image the article uses instead of guessing what it shows.

Do not answer from a title alone, and do not answer from the one-line summary in `00-INDEX.md`. The summary tells you which article to open, never what it says.

## Step 4 — Answer using the article's own steps, in order

Rules for the reply:

1. Keep the article's step order. Do not reorder, merge, compress or "improve" it.
2. Keep the article's own labels and names — button names, menu names, field names, app names — exactly as written.
3. Surface the warnings. Where the article marks something with ⚠️ or "Important", put that before the step it guards, not after.
4. Answer the question asked first, then the steps.
5. Cite what you used: Doc ID, article title, and absolute file path.

**Reply shape:**

```
[Direct answer to the question in one or two sentences.]

From MCS-131 — Setting Up Your Android Device with myCRMSIM SMS Gateway
($HOME/Downloads/openclaw-master-files/mycrmsim/articles/01-Devices and Installation/01-myCRMSIM SMS Installation and Setup/01-SMS Device Setup/MCS-131 - Setting Up Your Android Device with myCRMSIM SMS Gateway.md)

1. [the article's step 1, in its words]
2. [the article's step 2]
...

Note: the article also warns that [the warning it carries, and where in the sequence it belongs].
```

If the person is troubleshooting and the article is long — `MCS-138 - SMS Troubleshooting` has thirteen steps — still give the steps in order. You may say which steps match their symptom, but the answer body stays in the article's sequence.

## Step 5 — When two articles conflict, say so

The set was saved on 2026-11-05 and articles were updated at different times, so a few pairs will disagree — most often a setup article against a troubleshooting article, or a channel article against an FAQ answer.

When that happens:

1. **State the conflict plainly, first.** "The docs conflict on this." Never silently pick one and present it as settled.
2. **Name both.** Doc ID, title and path for each.
3. **Say which one you are following and why.** Prefer the article that is specific to the exact channel and product in the question over a general or FAQ article; where two articles cover the identical task, prefer the one with the newer `Site updated` line. Two equally specific articles with different sequences is a real tie — say it is a tie and give both sequences.
4. **Tell the person the other version exists**, so they are not surprised when the screen does not match.

Do not merge two conflicting sets of steps into one invented sequence.

## Step 6 — When nothing matches, say so plainly

If searching the folder and the index turns up nothing that covers the question:

> "The offline myCRMSIM docs do not cover this. I searched the 156 articles and the index and found no article on [topic]."

Then point to support, and only then:

- **support.mycrmsim.com** — the live support center the set was downloaded from, which may have newer articles.
- **Simi** — the AI assistant built into myCRMSIM, which answers questions and fixes most setup issues on the spot. The docs recommend trying Simi before booking a call.
- **`MCS-139 - Book A Call With Us`** (`articles/07-Talk To The Team/`) — group demo, group onboarding call, open office hours, and 1-1 support calls, plus the Demo On Demand link.

Never fill the gap with general Android or CRM advice presented as myCRMSIM guidance. If you offer outside knowledge, label it as outside the docs.

---

# Searching by Keyword Across the Folder

Use these from a terminal. Quote every path — folder and file names contain spaces. Start from the docs root so the paths stay short:

```bash
cd "$HOME/Downloads/openclaw-master-files/mycrmsim"
```

**Find every article that mentions a word or phrase (filenames only):**

```bash
grep -ril --include='*.md' "pending" articles
```

**Same search, with the matching line so you can judge relevance:**

```bash
grep -rin --include='*.md' "pending" articles
```

**Search one channel's folder instead of all 156:**

```bash
grep -ril --include='*.md' "RCS" "articles/01-Devices and Installation"
```

**Phrase search — several words, in order:**

```bash
grep -ril --include='*.md' "missed call text back" articles
```

**Several terms at once (either word):**

```bash
grep -rilE --include='*.md' "play protect|firebase token|unpair" articles
```

**Search by title or category through the manifest** (fastest when you know the topic, not the wording):

```bash
jq -r '.[] | select(.title | test("warm.?up"; "i")) | "\(.doc_id)\t\(.title)\t\(.file)"' _manifest.json
```

**Browse titles by category:**

```bash
jq -r '.[] | select(.category | test("Integrations"; "i")) | "\(.doc_id)\t\(.title)"' _manifest.json
```

If `jq` is not available, the same title lookup works with grep:

```bash
grep -i "warm" _manifest.json
```

**Reading the result:** `grep` exits 1 when there are no matches — that is an empty result, not a broken search. Exit 2 or higher means a real error (missing path, unreadable file); fix the path before concluding the docs are silent on the topic. Search results give you the file; open it and read the whole article before answering (Step 3). A keyword hit is a pointer, never the answer.

**Search order to follow:** `00-INDEX.md` first (it is curated and summarized), then the manifest for titles, then `grep` across `articles/` for exact wording inside the bodies. The index and manifest can miss body phrasing; the body grep can miss nothing but costs you the reading.

---

# Hard Rules

- **Docs outrank memory.** If the set covers it, the article is the answer, in the article's sequence. Never substitute a remembered procedure.
- **Never invent a Doc ID, a title, a path, a step or a support link.** Every citation must be a file you actually opened.
- **Never claim an article says something it does not.** If the article is thinner than the question, say what it does cover and where it stops.
- **One folder at a time.** If a second folder is genuinely needed — a setup article plus a troubleshooting article — say which two you used and in what order.
- **Read-only.** Do not edit, rename, move, re-tag or re-download anything in the documentation set. It is the source of record.
- **No truncation.** These are deep files: quote the steps the person needs in full rather than summarizing them away.
