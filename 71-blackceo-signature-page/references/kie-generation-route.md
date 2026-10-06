# Skill 71 image and video generation route (KIE)

Authority: `07-kie-setup/references/kie-common-rules.md` (the KIE common rules, merged by PR #1497).
Where this file and that file disagree, that file wins. This file only says how Skill 71 uses it.

Skill 71 never calls KIE itself. Every generated image or video follows one path:

```
Skill 71 stage -> policy owner (Skill 66 image, Skill 67 video) -> transport (Skill 74) -> save -> receipt
```

## 1. Policy: which model (Skill 66 or 67)

- Skill 71 never writes a model id from memory (rule 10). It hands the final prompt, the ratio and the
  reference files to Skill 66 (image) or Skill 67 (video), which select the model from their registry.
- Authority order (rule 1): owner rulings, department pins, Skills 66/67/68, Skill 74 (mechanics), static tables.
  An explicit client request for a model or a department pin wins over the default.
- The GPT Image default is the newest GPT Image generation in KIE's live catalog (rule 13). Skill 66
  resolves it with `python3 74-kie-live-adapter/scripts/kie_live_adapter.py latest-family --family gpt-image`.
  Today that is GPT Image 2.5 Sunburst. If it changes, the adapter writes a receipt and the operator is told.
- Ratio rules from AGENTS.md N43 (rule 11), applied by Skill 66 before dispatch and recorded on the receipt:
  3:1, 1:3 and 9:21 go to the legacy `gpt-image-2-*` route only; on the default route 5:4 becomes 4:3,
  4:5 becomes 3:4, 2:1 becomes 16:9 and 1:2 becomes 9:16; every other ratio is used as asked.
  The page slot ratio comes from the wireframe image inventory. When a substitution happens, write the
  prompt's composition for the ratio that will be generated, and record both ratios in the receipt.
- Constraint sets are per generation and never merged (rule 11).

## 2. Transport: how (Skill 74 only)

Run these from the Skill 74 folder, once per image or clip. `--mode active` is required on every
dispatching call; the default mode is `shadow`, which never spends. Rule-Zero approval (USD announce plus
budget cap) and the per-job image cap still apply before the first paid call.

1. Validate the payload against the live schema:
   `python3 scripts/kie_live_adapter.py validate --model <id> --payload input.json`
2. Preflight credits, price times 1.30 (rules 6 and 7); stop on a shortfall:
   `python3 scripts/kie_live_adapter.py preflight --model <id> [--units N]`
3. Prompt budget (rule 12): 95 to 100 percent of the model's character maximum, never below 80 percent:
   `python3 scripts/kie_live_adapter.py prompt-budget --model <id> --check --prompt-file <prompt.txt>`
   Exit 3 prints the exact characters to add; exit 4 prints the exact characters to cut. Fix and re-run.
   Descriptive prompt fields only; spoken text and lyrics have their own rule.
4. Submit: `python3 scripts/kie_live_adapter.py submit --request req.json --mode active`
   (or `run --request req.json --save-dir DIR --mode active`, which submits, waits and saves in one call).
5. Wait and save immediately (rule 8; result links can expire within 24 hours):
   `python3 scripts/kie_live_adapter.py wait --task-id <id>` then `save --task-id <id> --save-dir DIR`.

The adapter never retries createTask after a network error, makes one attempt on a 401 or 403 (stop and
report), and never prints the key (rules 6 and 9). The key is the client's own. Prices are never typed
into a Skill 71 file: ask `price`. Endpoints are never typed either (rule 2).

Never copy `kie_live_adapter.py` into a run folder, and never write a `curl`, `requests` or `urllib`
createTask or recordInfo call. A hand-rolled call is outside the single approved path.

Account limit (rule 3): 20 createTask requests per 10 seconds, shared by every agent on the account.

## 3. Receipt (stage `image-generation-qc`)

`scripts/stage_gate.py` closes `image-generation-qc` only when the stage receipt carries a `transport`
block that matches this route. Example (values are placeholders):

```json
"transport": {
  "skill": "74-kie-live-adapter",
  "policy": "66-kie-image",
  "mode": "active",
  "tasks": [
    {"file": "image-generation-qc/Image-001.png", "task_id": "<KIE task id>",
     "model_id": "<id returned by Skill 66>", "model_source": "latest-family",
     "requested_ratio": "16:9", "generated_ratio": "16:9",
     "preflight_ok": true, "budget_exit": 0}
  ]
},
"cost": {"provider": "kie", "credits_before": 0, "credits_after": 0}
```

`model_id` and `model_source` are per task because one page can use the legacy route for a 3:1 slot and
the default for the rest. `model_source` is one of `latest-family`, `explicit-request`, `department-pin`,
`legacy-ratio-route`. The gate checks the N43 ratio rule on every task: a requested 3:1, 1:3 or 9:21 must be
generated as asked on the legacy route; on the default route 5:4, 4:5, 2:1 and 1:2 must be generated as
4:3, 3:4, 16:9 and 9:16; every other ratio must be generated as requested. An explicit request or a pin may
override the substitution.
Every `task_id` must also exist as its own file `<run>/receipts/kie74/<task_id>.json` (a successful active Skill 74 result, recorded with the Skill 49/56 `kie74_receipt.py` pattern or written by the run's own recorder) and be unique across tasks and files. A task whose `model_source` is `explicit-request` or `department-pin` carries `evidence` (the request text or the pin id); without it the N43 substitution cannot be skipped. The Agnes route is accepted only when `intake.json` has `image_engine: "agnes"`.
`credits_before` and `credits_after` come from `kie_live_adapter.py credits`, never from an estimate.
When the client selected Agnes, `skill` and `policy` are both `63-agnes-image` and `cost.provider` is `agnes`.

## 4. Video

Skill 71 has no video stage today. If an approved page plan includes a hero or background clip, the same
path applies with Skill 67 as the policy owner and the same Skill 74 commands; use `price --units` for
duration based prices and pass the total seconds when input and output duration are billed.
