# Storyboard Writer - Examples

## Example 1: 5-minute tutorial with Veo 3.1

```bash
python3 scripts/create_storyboard.py \
  --duration 300 \
  --model veo-3-1 \
  --topic "How to Bake Sourdough" \
  --output sourdough_tutorial
```

What you get:
- a segment-by-segment plan sized to the model's clip duration
- a cost estimate based on `scripts/model-database.json`
- files: `sourdough_tutorial.json`, `sourdough_tutorial.md`

## Example 2: 3-minute promo with Kling 3.0 (10s clips)

```bash
python3 scripts/create_storyboard.py \
  --duration 180 \
  --model kling-3 \
  --topic "Summer Sale Promotion" \
  --output summer_sale
```

What you get:
- a storyboard with prompts for each segment
- files: `summer_sale.json`, `summer_sale.md`

## Example 3: compare models for the same runtime

```python
from scripts.model_database import calculate_cost

for model_id in ["veo-3-1", "kling-3", "seed-dance", "wan-2-6"]:
    cost = calculate_cost(model_id, 300)
    print(model_id, cost)
```

Notes:
- The snapshot prices are indicative only (dated 2024-01-15). Live prices come from `python3 74-kie-live-adapter/scripts/kie_live_adapter.py price --model <id>` (Skill 74); which model to use comes from Skill 67. The script's estimate uses fallback constants only.
- Sora is prohibited by the Video department and is not used in any example.
