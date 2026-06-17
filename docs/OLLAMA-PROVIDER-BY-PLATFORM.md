# Ollama Provider — Mac vs VPS (CLIENT ONBOARDING STANDARD)

> This is the canonical standard for how the `ollama` model provider is wired on a
> client box, **branched by box type**. It is machine-enforced by
> `scripts/qc-assert-ollama-provider-platform.sh` (CHECK X.9 in
> `scripts/qc-system-integrity.sh`). If you change the standard here, change the
> enforcer too — the QC gate FAILs any box whose `ollama` provider does not match
> its platform.
>
> Verified against **docs.openclaw.ai/providers/ollama** (the "Cloud + Local"
> hybrid flow) on 2026-06-17, OpenClaw 2026.6.x, onboarding v12.21.0.

---

## TL;DR

| | 🍎 Mac client (Mac mini / laptop / any macOS) | 🟦 VPS client (Hostinger Docker / any Linux container) |
|---|---|---|
| Local Ollama daemon | **YES** — signed in via `ollama signin` (client's own ollama.com account) | **NO** — no daemon in the container |
| `ollama` provider `baseUrl` | `http://127.0.0.1:11434` | `https://ollama.com` |
| `ollama` provider `api` | `ollama` | `ollama` |
| `ollama` provider `apiKey` | `ollama-local` (sentinel) | `{{OLLAMA_API_KEY}}` — the client's OWN Ollama Cloud key |
| Serves local models? | **YES** | No |
| Serves `:cloud` models? | **YES — through the same local endpoint** | YES — direct to cloud |
| `:cloud` model `maxTokens` | **≤ 64000** | **≤ 64000** |

There is exactly **ONE** `ollama` provider on every box. Do not split into
`ollama-local` + `ollama-cloud`.

---

## 🍎 Mac client — signed-in LOCAL daemon (hybrid Cloud + Local)

A Mac client runs the Ollama daemon locally. We **sign it in** to the client's own
ollama.com account, and then a single provider points at the local daemon. A
signed-in daemon brokers BOTH local models AND `:cloud` models through that one
loopback endpoint — this is the documented "Cloud + Local" hybrid flow.

### Setup

1. **Install + sign in the local daemon** (client's OWN ollama.com account):
   ```bash
   ollama signin
   ```
   This writes `~/.ollama/id_ed25519`; the daemon now authenticates `:cloud` calls
   on the client's behalf. No `OLLAMA_API_KEY` env var is needed for routing — the
   daemon holds the credential.

2. **One `ollama` provider** in `openclaw.json` pointing at the local daemon:
   ```json
   {
     "models": {
       "providers": {
         "ollama": {
           "baseUrl": "http://127.0.0.1:11434",
           "api": "ollama",
           "apiKey": "ollama-local",
           "models": [
             { "id": "kimi-k2.6:cloud",       "maxTokens": 64000 },
             { "id": "deepseek-v4-pro:cloud", "maxTokens": 64000 },
             { "id": "gemma4",                "maxTokens": 64000 }
           ]
         }
       }
     }
   }
   ```
   Mix local model ids (e.g. `gemma4`) and `:cloud` model ids (e.g.
   `kimi-k2.6:cloud`) in this ONE provider. Both route through `127.0.0.1:11434`.

3. **Verify the daemon actually replies** (config-valid is NOT enough — see "Live
   PONG" below).

### Why loopback is correct on Mac

The legacy rule treated `127.0.0.1:11434` as a hard violation for inference. That
was true *when no box ran a local daemon*. On a Mac with a **signed-in** daemon,
the daemon is the control point for both local and cloud inference — forcing the
Mac onto `https://ollama.com` discards the local-model path and the free local
route. So the loopback rule is platform-branched: **REQUIRED on Mac, FORBIDDEN on
VPS.**

---

## 🟦 VPS client — CLOUD-DIRECT (no local daemon)

A Hostinger Docker VPS (or any Linux container) has **no local Ollama daemon**.
Pointing the provider at a loopback address → immediate `ECONNREFUSED` on every
call (a silent model failure, not a retried error). The provider talks straight to
Ollama Cloud with the client's own key.

### Setup

1. **Client's own `OLLAMA_API_KEY`** lives in the box's env store (Hostinger:
   host `/docker/<project>/.env`; container `/data/.openclaw/secrets/.env`).

2. **One `ollama` provider**, cloud-direct:
   ```json
   {
     "models": {
       "providers": {
         "ollama": {
           "baseUrl": "https://ollama.com",
           "api": "ollama",
           "apiKey": "{{OLLAMA_API_KEY}}",
           "models": [
             { "id": "kimi-k2.6:cloud",       "maxTokens": 64000 },
             { "id": "deepseek-v4-pro:cloud", "maxTokens": 64000 }
           ]
         }
       }
     }
   }
   ```
   VPS provider serves `:cloud` models only — no local model ids.

---

## All boxes — `:cloud` maxTokens ≤ 64000

Ollama Cloud caps output at **65536** tokens. A `maxTokens` of 384000 (the spec
window) returns **HTTP 400 on every call** and silently breaks the primary model.
Ship `maxTokens: 64000` on every `:cloud` model entry (headroom under 65536). The
enforcer hard-fails any `:cloud` model whose `maxTokens` exceeds 64000.

---

## Live PONG — never trust config-valid alone

`openclaw config validate` only proves the JSON is well-formed. It does NOT prove
the model replies. Always confirm a real round-trip after wiring:

```bash
# Mac (local daemon must be up and signed in):
curl -s http://127.0.0.1:11434/api/version           # daemon alive
openclaw run --model ollama/kimi-k2.6:cloud "Reply with exactly: PONG"

# VPS (cloud-direct):
openclaw run --model ollama/kimi-k2.6:cloud "Reply with exactly: PONG"
```

A box is only "done" when the model returns a live PONG — both a local model and a
`:cloud` model on Mac, the `:cloud` model on VPS.

---

## Enforcement

- **Doc (this file):** the standard, branched by platform.
- **Enforcer:** `scripts/qc-assert-ollama-provider-platform.sh` — single-source-of-truth
  invariant check. Detects platform (`/data/.openclaw` → VPS, else Mac;
  overridable via `OPENCLAW_PLATFORM`). Asserts:
  - **P1** baseUrl matches platform (Mac=loopback REQUIRED, VPS=loopback FORBIDDEN).
  - **P2** `api: "ollama"`.
  - **P3** apiKey shape per platform (Mac=`ollama-local`; VPS=real key, not the
    local sentinel).
  - **P4** no `:cloud` model with `maxTokens > 64000`.
- **QC gate:** `scripts/qc-system-integrity.sh` CHECK **X.9** delegates to the
  enforcer; hard-fail blocks the build/QC. Runs during `install.sh` and every
  `update-skills.sh` pass.

---

## ⚠️ Existing Mac clients wired cloud-direct need MIGRATION

Some Mac clients were onboarded under the old VPS-only assumption and are currently
on `baseUrl: "https://ollama.com"` with **no local daemon**. Under this new
standard, the enforcer will FAIL those boxes (P1 MAC mismatch) with an explicit
migration message. Migration steps (operator-run; do NOT auto-migrate a live
client):

1. Install Ollama on the Mac and `ollama signin` to the client's OWN ollama.com
   account.
2. Repoint the `ollama` provider: `baseUrl` → `http://127.0.0.1:11434`, `apiKey` →
   `ollama-local`.
3. Pull any local models the client wants; keep the `:cloud` ids.
4. Restart the gateway and confirm a live PONG from both a local and a `:cloud`
   model.

Until migrated, those boxes keep working cloud-direct — the enforcer flags the
drift; it does not break the running client.
