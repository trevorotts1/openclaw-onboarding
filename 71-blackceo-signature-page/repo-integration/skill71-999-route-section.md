# Skill 71 in the 999 repo: route section for SKILL.md

This file is the adapter-class source for the 999 edition's SKILL.md
route text (Item 28 step 3). It is authored here, in the onboarding
repo, and applied to the 999 copy of SKILL.md when the sync runs. The
999 SKILL.md is adapter-class in the parity allowlist precisely
because this section differs: the two harnesses resolve the same
routes through different native machinery, and no route in the 999
edition may borrow from the OpenClaw skills tree.

## Replacement for the "Images and video" ownership bullet

- **Images and video:** in this harness (Claude Code, claude-nine),
  every generation request resolves inside this repo: policy from the
  native `kie` skill and its vendored helpers (66-kie-image policy,
  67-kie-video, 68-kie-audio, 46-kie-callback-relay, 07-kie-setup
  under `installer-registration/helpers/`), copied into this skill as
  data in `references/kie-policy-999.json`; transport through the same
  native adapter (74-kie-live-adapter) for everything it implements,
  with `scripts/kie_transport.py` in this skill supplying only the two
  pieces the capability audit proved absent (the credits before/after
  pair and the per-task receipt files the gate reads). Video routes to
  the native `motion-video-plus` skill (Item 28 Row 4). Agnes requests
  route through `scripts/agnes_route.py` in this skill. Do not
  hand-roll provider calls anywhere in this harness either.

## Replacement for the "Image and video engine routing" section

Ask whether the owner/client has an explicit image-engine preference
when generation is in scope, and record it at intake. The intake in
this edition records `runtime: "claude-nine"`; `scripts/write_intake.py`
refuses `image_engine agnes` in writing when no Agnes key is
configured in the environment (Item 28 Row 5).

- The gate's transport vocabulary maps onto this harness as follows
  (Item 28 step 3): a receipt whose transport skill is `kie` is the
  native kie skill performing both the policy and transport roles.
  The generated policy names the pin a **user pin** where the
  onboarding law says department pin; the gate maps the value at
  validation time and the stored receipt keeps `user-pin`.
- Model choice follows the standing rule: the client selects their
  model, or their configured default applies (in this harness, the
  install's 9Router configuration); the system may recommend with
  reasons. No model is prescribed here.
- The N43 ratio rules, the preflight rule (balance covers price x
  1.30), the prompt budget check, and the per-task receipt fields the
  gate requires are unchanged; they are the law copied into
  `references/kie-policy-999.json`, not a second invention.

## Harness dependency declarations (Item 28 sub-dispositions)

- **Skill 5 (setup and provisioning): DECLARE.** Provisioning of the
  harness itself is a prerequisite owned by the 999 install, not by
  this skill. This skill declares the dependency and does not copy it.
- **Skill 29 (GHL Convert and Flow API): MAP by reference.** Its role
  in this harness is served by the GHL pack that ships with this
  edition (`.claude/skills/ghl-install-pages/`,
  `.claude/skills/convert-and-flow-operator/`,
  `.claude/skills/conversational-ai-system/`), whose Tier 0 caf CLI
  rail and API rail are the routes Item 32 names. No separate copy of
  Skill 29 is vendored.
- **Skill 36 (GHL MCP setup doctrine): VENDOR as data.** The tier
  doctrine (Tier 0 caf CLI first, browser as the Tier 4 backstop) is
  carried as data in the GHL pack's adapter contract
  (`.claude/skills/ghl-install-pages/ADAPTER.md`), not as a skill
  copy.
- **The caf CLI is an external prerequisite in this harness.** The
  step-zero audit proved the 999 installer does not provision it
  (zero hits across the install corpus, where the same corpus
  provisions the Vercel CLI). Until the install provisions it, the
  pack's API rail is unavailable and funnel and workflow work falls
  to the Tier 4 agent-browser backstop, recorded as such in receipts.
