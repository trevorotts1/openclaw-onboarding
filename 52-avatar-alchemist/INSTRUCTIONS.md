# INSTRUCTIONS — the canonical Avatar-Alchemist run procedure

This is the operating procedure (no separate `universal-sops/` entry needed). A department
specialist invokes it via its Section-8 "Tools You Use" reference; intake goes ONLY through Gate 0.

## 0. Preflight (once per box)

```
bash 52-avatar-alchemist/preflight.sh        # probes the client's providers → model-map.json
bash 52-avatar-alchemist/verify-deps.sh      # proves python3 stdlib only; zero external services
```

`preflight.sh` writes `model-map.json` (TIER-A deep authoring / TIER-B structured / SEARCH for
stage `02`) + `provider_caps` (local Ollama capped at ≤3 concurrent). **Client providers only —
never Anthropic, never operator keys.**

## 1. Intake (Gate 0)

Two entry modes land on the same normalized `intake.json`:
1. **Conversational** — interview the user against `intake/INTAKE-TEMPLATE.md` (version selector
   FIRST), write `intake.json`.
2. **File drop** — a filled `intake.json` from the user or an upstream skill (must carry `version`).

Validate:
```
python3 scripts/aa_intake_gate.py --intake <RUN_DIR>/intake.json [--book-skill-present]
```
- `version=brand` → continue below.
- `version=book` → the gate routes to the Book skill (53) or parks `book-skill-not-available`.
  This skill does **ZERO** generation for a book run.

## 2. Front door + foreman

```
bash 52-avatar-alchemist/entry.sh <RUN_DIR>          # deps → bypass-scan (Anthropic ids + egress) →
                                                      # env-credential-name scan → hash-pin → nonce + foreman-key
cp <intake.json> <RUN_DIR>/intake.json               # required for a real dispatch (version gate reads it)
python3 scripts/aa_director.py --run-dir <RUN_DIR> --nonce <RUN_DIR>/.entry-nonce --plan
python3 scripts/aa_director.py --run-dir <RUN_DIR> --nonce <RUN_DIR>/.entry-nonce
```

The foreman schedules 20 dependency waves (peak 5 authors), throttled to
`min(slots, provider_cap)`, dispatching one sub-agent per stage with ONLY its 3 prompt files +
resolved dependency artifacts. It refuses to dispatch any stage whose `depends_on` receipts are
missing. `--fast-ads` collapses the ad tail (documented fidelity trade-off, OFF by default);
`--resume` re-enters at the exact incomplete stage. **Source repairs R1–R6 are OFF by default
(faithful to the live workflow); `--apply-repairs` opts into them and turns on the R4 ad-set-category
gate — see `REPAIRS.md`. R7 (the Anthropic ban) is always on.**

A real dispatch does NOT trust that `entry.sh` actually ran or that the nonce is genuine: it
RE-VERIFIES deps + bypass-scan + egress-scan + hash-pin in-process, unconditionally, before
anything is scheduled — a hand-forged nonce cannot skip these. It also loads
`<RUN_DIR>/intake.json` and REFUSES in code to run the 40-stage brand pipeline for
`version=book` (exit 4, `route.json` written) — the version gate is code-coupled, not procedural.

## 3. Content gate

```
python3 scripts/aa_build_check.py --run <RUN_DIR>
```
Enforces stripped-word floors, exact counts, the 5,000–19,000-char image-prompt band, the 13
restored ad-set categories (R4 — enforced only under `--apply-repairs`), bot-doc structure, the
12-section hero page, zero placeholders, and zero Anthropic model ids. Any violation is fail-closed.
Stage 02 links are checked separately by the fail-soft `aa_links_gate.py` (verify or `degraded:search`).

## 4. QC (independent, BINDING)

An independent verifier agent (≠ any author) scores the 10-category OpenClaw QC Protocol on the
client's TIER-A model. `≥ 8.5`, zero autofails. Below the line → redo ONLY the failing artifact
within `max_fix_attempts`, then park.

## 5. Delivery gate + certificate

```
python3 scripts/aa_package.py --run-dir <RUN_DIR> --first <First> --last <Last> \
        --out "$HOME/Downloads/<First>_<Last>-Brand-Intelligence/Avatar_Alchemist_<YYYY-MM-DD_HHMM>"
python3 scripts/aa_qc_cert.py --run-dir <RUN_DIR> --key-file <RUN_DIR>/.foreman-key \
        --out <RUN_DIR>/QC-CERTIFICATE.json
python3 scripts/aa_delivery_gate.py --run-dir <RUN_DIR> \
        --deliver-dir "$HOME/Downloads/<First>_<Last>-Brand-Intelligence/Avatar_Alchemist_<YYYY-MM-DD_HHMM>" \
        --cert-out <deliver-dir>/PROCESS-CERTIFICATE.json
# ANY "done" claim MUST re-verify, not just check field presence:
python3 scripts/aa_delivery_gate.py --verify-cert <deliver-dir>/PROCESS-CERTIFICATE.json \
        --key-file <RUN_DIR>/.foreman-key --run-dir <RUN_DIR> --deep
```
The delivery gate refuses `~/Downloads` below 40/40 receipts+artifacts loaded FROM DISK (never a
caller-supplied dict), re-runs the content prover itself against the on-disk run, requires a
detached QC certificate (`aa_qc_cert.py` — a separate program, `verifier != author`) scoring
`≥ 8.5`, requires + consumes the one-time front-door nonce, and re-checks gate-integrity live at
issuance. The signature is HMAC-SHA256 keyed by the per-run foreman key (`<RUN_DIR>/.foreman-key`,
minted only by `entry.sh`, never embedded in the certificate). **"Done" is claimed only with a
certificate that PASSES `aa_delivery_gate.py --verify-cert`** (no-false-done rule; presence of the
`signature` field alone is NOT sufficient — it must independently re-verify).

## Delivery contract (we move in silence)

The skill's final answer = the deliverable folder path + the `00-INDEX.md` doc list + the
certificate status. No client-facing sends mid-run. Optional owner notification only if the
department how-to wires the box's own OpenClaw gateway channel — never raw Slack/Gmail, never
operator credentials.

## Downstream handoffs

- 3 bot docs → **Skill 38** (conversational-ai-system) playbook input.
- `Top_39_Suggested_Ad_Angles` + `Facebook_Headline_…` + `Facebook_Targeting_Intelligence` →
  **Skill 48** (facebook-ad-generator).
- Image generation from the two image-prompt docs → **Skill 47** (movie-producer).
- GHL page/delivery → **Skill 6** (the one GHL rail).
- `version=book` intake → **Skill 53** (the Book skill).
