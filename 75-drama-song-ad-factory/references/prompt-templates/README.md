# 20-prompt-templates (DRAFT)

Draft data files for the template system in `../20-OPUS-PROMPT-TEMPLATE-SYSTEM.md`. The build lanes port this folder to `references/prompt-templates/` in both repos, with the same bytes in each, and port the three draft scripts into one module, `scripts/core/prompt_templates/prompt_templates.py`.

| Path | Layer |
|---|---|
| `manifest.json` | caps (with source and status), bands, layer order, quality rules |
| `models/` | one block per model: `minimax-h3`, `kling-video`, `kling-ai-avatar-standard`, `suno-v6` |
| `modes/` | the five render modes that the five looks are built from: `lifelike-3d`, `painted-2d`, `sketch-ink`, `realism`, `golden-realism` |
| `looks/` | the five card looks: which modes each uses, the beat-to-mode map, switch rules and lip-sync modes |
| `shot-types/` | six shot types: talking close-up, motion b-roll, struggle beat, product/book, style switch, end card |
| `length-classes.json` | 60/90/120/180/300/600 s: shots, H3 clips, lip-sync, lanes, hooks, spoken share, product seconds |
| `music/` | Soul Ballad, R&B Flow, Soul Rise: style parts, negative tags, cue overrides, skeleton rules |
| `h3/specs/` | six SAMPLE shot specs, the facts the shot planner writes for each shot (fictional campaign) |
| `h3/examples/` | the six assembled H3 prompts, each with a receipt |
| `suno/examples/` | one Suno payload per length class, with measured counts |
| `kling/` | three Kling avatar prompts, with measured counts |

Run (stdlib only, no network, no spend):

```bash
python3 assemble_draft.py --selftest   # H3: assemble 6, check band and structure, then 6 mutants per prompt must fail
python3 suno_draft.py --core <clone>/75-drama-song-ad-factory/scripts/core
python3 kling_draft.py
```

The sample campaign is fictional ("Renee", *The Unhurried Year* by Dana Wells). It exists only to fill the templates. It is not client content.
