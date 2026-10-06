# Storyboard Writer - Instructions

## What this skill does

Storyboard Writer plans a video before you generate any clips.

It:
1. takes a target runtime (in seconds)
2. uses the chosen model's clip duration
3. calculates how many clips you need
4. generates a prompt for each segment
5. exports JSON and Markdown files

## Where pricing and durations come from

Durations and indicative prices are read from `scripts/model-database.json`. That file is a dated snapshot (last verified 2024-01-15) and is NOT authoritative:
- Which model to use: Skill 67 (`67-kie-video`, `scripts/select_video_model.py`). Run it when the user names no model.
- Live prices: `python3 74-kie-live-adapter/scripts/kie_live_adapter.py price --model <id>` (Skill 74, live `pricingDesc`). The price numbers in the JSON are fallback constants read by the cost estimate only.
- Sora is prohibited by the Video department and is never a default. The Sora rows in the snapshot are historical data only.

If estimates look wrong, do not hand-edit prices to "fix" them. Quote the price from the Skill 74 command above instead.

## How to run

### 1) Create a storyboard

```bash
python3 scripts/create_storyboard.py \
  --duration 300 \
  --model kling-3 \
  --topic "Product Tutorial" \
  --output my_storyboard
```

You should see:
- a confirmation message
- the number of segments
- the estimated cost
- files written: `my_storyboard.json` and `my_storyboard.md`

### 2) List available model IDs

```bash
python3 -c "from scripts.model_database import list_models; print('\n'.join(list_models()))"
```

### 3) Get a cost estimate in Python

```python
from scripts.model_database import calculate_cost

cost = calculate_cost("kling-3", 300)
print(cost)
```

## Allowed core file updates

This skill is only allowed to add pointers to:
- `TOOLS.md`
- `MEMORY.md`

Follow `CORE_UPDATES.md` for the exact text to add.

## Troubleshooting

### "Unknown model"
- Run the "List available model IDs" command above.
- Use one of the IDs it prints.

### No output files created
- Make sure you have permission to write to the current folder.
- Try running with a different `--output` name.
