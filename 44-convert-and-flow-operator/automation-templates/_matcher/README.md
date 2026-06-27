# Flexible Automation Matcher (Skill 44 STEP 0)

Makes Skill 44 (`44-convert-and-flow-operator`) **flexible + template-aware**. Before caf
wires a GoHighLevel workflow it classifies the request, **detects the intent mode**, scores
it against the 28 shipped automation templates, and decides a posture that NEVER dominates
the user's desire.

## CORE PRINCIPLE — FLEXIBILITY
Every template/persona/sequence is a **GUIDE and a RESOURCE, never a rule or a requirement.**
It assists; it never dominates. `imposes_on_user` is always `false`; `override_allowed` is
always `true`; the matcher **never blocks** a build.

| Intent mode | Decision (when a template fits) | Behaviour |
|---|---|---|
| `EXPLICIT_USER_SPEC` | `HONOR_USER` | Build the user's spec; template = **optional reference only**, never imposed. |
| `UNSURE_WANTS_SUGGESTION` | `SUGGEST_TEMPLATE` | Recommend the proven template + WHY; **await confirm**. |
| `HANDS_OFF_DO_IT_ALL` | `USE_TEMPLATE` | Build the whole automation from the template. |
| (nothing fits) | `CREATE_NEW` | Build net-new, then `save_new_template()` so the library grows. |

The DEFAULT mode (no strong cue) is `UNSURE` → `SUGGEST` — the least-dominating posture
(recommend, never silently impose or auto-build).

## Files
- `flex.py` — shared intent-mode detection (`detect_mode`) + decision mapping (`decide`).
  Also mirrored INLINE inside the Skill-6 `funnel_matcher.py` so that file stays self-contained.
- `automation_matcher.py` — engine (stdlib-only, deterministic, no network):
  `Catalog.load`, `classify`, `score_template`, `match_automation`, `instantiate_workflow`,
  `save_new_template`, `log_decision`, `expand_funnel_to_automations`, `step0_match`.
- `cli.py` — `--build-index | --match "<text>" [--mode MODE] | --expand <funnel_id> | --selftest`.
- `catalog-index.json` — generated index (28 templates, 5 categories).
- `WIRING.md` — the three integration surfaces (Skill-44 step 0, Skill-6→Skill-44 complete-funnel
  trigger, the v2_dispatcher handoff call-site).

## Selftest
`python3 cli.py --selftest` → **9/9** intent-mode/decision cases + **38/38** funnels expand to a
buildable plan. `python3 flex.py` → **8/8** mode-detection cases.

## Funnel → Automation link map
`../_links/funnel-to-automation.json` maps each of the 38 Skill-6 funnel templates to its
RECOMMENDED follow-up automation(s) (primary + secondary + graduation), Brunson-doctrine:
- Lead (squeeze/lead-magnet/...) → Soap Opera Sequence → graduate to daily Seinfeld.
- Buyer (book/tripwire/SLO) → post-purchase OTO + cart-abandon recovery.
- Event (webinar/...) → registration + reminders + replay + Perfect Webinar Stack close.
- Application → homework/booking nurture. Membership → stick/retention. etc.

Every link is a **RECOMMENDED DEFAULT, not mandatory** — overridable, mixable, ignorable.
`expand_funnel_to_automations(funnel_id, overrides=...)` returns the linked build-plans minus
any the user overrode (`build_now:false`).

## Honest status
- **Wired + proven:** catalog loader, classifier, lexical scorer, intent-mode detection, the
  HONOR_USER/SUGGEST/USE/CREATE_NEW decision map, workflow-plan instantiation, save-back,
  decision logging, the funnel→automation expander, and `step0_match`. All selftests pass.
- **Scaffolded (off by default):** semantic re-rank (no `embed_fn` here — lexical is the wired
  path). Vendoring into `44-.../tools/` + the INSTRUCTIONS.md Step-0.4 edit + the v2_dispatcher
  handoff call-site are the ship agent's commit (patches/anchors in `_patches/` + `WIRING.md`).
