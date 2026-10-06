---
name: kie-setup
description: >
  Complete setup, credential management, and API router reference for KIE.ai, a
  unified API platform for generating images, videos, and audio through one API
  key and consistent async job conventions.
version: v7.1.0
metadata:
  version: "7.1.0"
  priority: CRITICAL
---

# KIE.ai Setup, Router, and Common API Reference

KIE.ai is a unified API platform that connects you to AI models for creating
images, videos, and audio using a single API key (`KIE_API_KEY`) and consistent
endpoints.

Think of KIE.ai as a universal remote control and gateway for AI media generation.

## When to Use This Skill

- Setting up or verifying the `KIE_API_KEY` credential in the workspace environment
- Verifying KIE account balance, health, rate limits, or error diagnostics
- Understanding generic Market API rules (`createTask`, `recordInfo`, async lifecycle)
- Production callback configuration via Skill 46 (`callBackUrl` vs polling policy)
- High-level routing across modality skills:
  - **KIE Image** (Skill 66) — dedicated image generation, models, limits, and validation
  - **KIE Video** (Skill 67) — dedicated video generation, models, limits, and validation
  - **KIE Audio** (Skill 68) — dedicated audio, music (Suno), TTS, and STT
  - **Agnes Image** (Skill 63) / **Agnes Video** (Skill 64) — Agnes AI media pipelines

## Prerequisites

- Teach Yourself Protocol (TYP) must be learned first (Skill 01)
- Backup Protocol must be learned first (Skill 02)
- A KIE.ai account with an API key (from https://kie.ai/api-key)
- Credits loaded on the KIE.ai account (pay as you go)

## Media Generation Routing

When dispatching media generation requests, use this routing architecture:
- **Generic image** -> provider router -> Agnes Image (Skill 63) or KIE Image (Skill 66)
- **Generic video** -> provider router -> Agnes Video (Skill 64) or KIE Video (Skill 67)
- **KIE audio / music / TTS** -> KIE Audio (Skill 68)
- **Explicit model/provider wins**; department manifest wins; chosen provider remembered for the task
- **Validators run before API dispatch** (validation scripts live in the respective modality skills)
- **Detailed model tables and registries** live in modality skill references, not here

## What This Skill Covers

1. **API key setup** — How to configure `KIE_API_KEY` in `~/.openclaw/secrets/.env` (and legacy paths), and verify it works with a credit/health check.
2. **Generic Market API pattern** — Standard two-step async job flow:
   - Create task: `POST https://api.kie.ai/api/v1/jobs/createTask`
   - Query task: `GET https://api.kie.ai/api/v1/jobs/recordInfo?taskId=<TASK_ID>`
   - States: `waiting`, `queuing`, `generating`, `success`, `fail` (HTTP 200 means accepted, not complete).
3. **Dedicated API families** — Dedicated endpoints that bypass generic `createTask`:
   - Runway: `POST /api/v1/runway/generate`, `GET /api/v1/runway/record-detail`
   - Veo: `POST /api/v1/veo/generate`, `GET /api/v1/veo/record-info?taskId=XXX`
   - Suno / Music: `POST /api/v1/generate`, `GET /api/v1/generate/record-info`
4. **Callback vs polling policy** — Prefer Skill 46 (`callBackUrl`) in production; stepped/exponential backoff for polling (initial 2-3s delay, respect 429, never hammer).
5. **Rate limits and retention** — 20 new requests per 10s per account; 100+ concurrent running tasks. KIE documents 14 days for generated media but its task-detail page says result URLs typically expire after 24 hours; download/persist immediately.
6. **Error codes** — Handling 401 (unauthorized), 402 (insufficient credits), 429 (rate limited), 422 (validation error), 500/501 (server/generation failed).
7. **Modality dispatch** — Detailed model selection, schemas, prompt expansion bands, and payload validators are owned by Skills 66 (Image), 67 (Video), and 68 (Audio).

## Common Rules and Skill 74

- **`references/kie-common-rules.md` is the single source of truth** for KIE authority order, endpoints, rate limits, polling, prompt caps, credit preflight, prices, retention, keys, model ids, the image pin and the prompt budget. Read it before this skill's other files; where another file disagrees with it, the common rules win.
- **Skill 74 (`74-kie-live-adapter`) is the mechanics layer**, a dependency declared in `PREREQS.json` (optional: Skill 74 itself requires this skill first, and the modality skills fall back to static tables and curl when it is absent). Skills 66, 67 and 68 keep the policy (which model, which limits); they run `kie_live_adapter.py validate` (live schema, registry fallback) and `preflight` (balance must cover price x 1.30) before `submit --mode active`, then their own QC. Production batches pass `--callback-url` of the Skill 46 relay.
- Adapter health is part of this skill's QC: `qc-kie-setup.sh` checks the adapter is present and that `health --json` runs, hermetically (no network, placeholder key); set `KIE_QC_OFFLINE=1` to skip the live credit probe too.

## Files in This Folder (Reading Order)

1. **SKILL.md** — You are here. Overview, credentials, router, and common API rules. Then `references/kie-common-rules.md` (canonical rules).
2. **INSTRUCTIONS.md** — Operational instructions for credential setup and common API usage.
3. **INSTALL.md** — Steps to install and verify `KIE_API_KEY`.
4. **CORE_UPDATES.md** — Core file updates performed by `wire.sh`.
5. **EXAMPLES.md** — Example API calls for common generic and account tasks.
6. **kie-setup-full.md** — Comprehensive reference document.

## Critical Things to Know

- **NEVER use OpenAI's endpoint format** (`/v1/images/generations`) for KIE. KIE has its own endpoint structure.
- **All tasks are asynchronous.** A 200 response on task creation means the job was queued/accepted, NOT that it is finished.
- **Rate limits:** Maximum 20 new tasks per 10 seconds per account. Maximum 10 status queries per second per API key. Obey HTTP 429 with backoff.
- **Generated files expire:** KIE documents 14 days for generated media but its task-detail page says result URLs typically expire after 24 hours; download/persist immediately.
- **For production batch jobs and decks:** Use Skill 46 (kie-callback-relay) callback architecture rather than polling sequentially.
- **Department pipelines OVERRIDE defaults:** Never override a model pinned by Presentations (GPT-Image-2.5 only), Movie Producer, or department manifests.
- **The API key convention is `KIE_API_KEY`:** Stored in `~/.openclaw/secrets/.env` (and `~/.openclaw/.env`). Reference only; NEVER print or log the key.

## Skill 46 Companion (Callback Architecture)

Skill 46 (`46-kie-callback-relay`) provides centralized callback handling:
- Reduces API query budget consumption.
- Crash-safe task resume for large batch jobs.
- Secure HMAC validation with public HTTPS callback worker.
