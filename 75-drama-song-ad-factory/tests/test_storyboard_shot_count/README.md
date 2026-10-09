# test_storyboard_shot_count — DEL-15 proof (PKG-06-U3)

Storyboard picture counts, their configuration cap, their separation from
the video shot count, and agreement across every price surface.

## What is asserted

| File | Contract |
|---|---|
| `test_count_anchors.py` | 60 s -> 8 pictures, 120 s -> 24 pictures, monotone, bad lengths fail closed |
| `test_five_second_cadence.py` | past 2 minutes every +5 s adds exactly one picture (walk 121..600), 180 -> 36, 300 -> 60, 600 -> 120 |
| `test_cap_from_configuration.py` | `storyboard-config.json` holds 120, `storyboard_cap()` reads it, >120 lengths clamp to it, a different config file moves the clamp, missing/malformed config fails closed |
| `test_picture_vs_video_shot_count.py` | `video_shot_count` is ceil(length / model max); `shot_count` takes no model argument; card carries `storyboard_pictures` and `shots_per_shape` as separate fields, never their sum; pictures >= shots for every approved model and every offered length |
| `test_price_surfaces.py` | `references/price-menu.md`, `references/choice-card-spec.md` 3.12, `references/CLIENT-GUIDE.md` and the rendered card line all state the calculator's own counts and the configured cap; no dollar amount reaches the client guide or the card's storyboard line |

Every expected number is taken from the live calculator at run time
(`shot_count`, `video_shot_count`, `storyboard_cap`) except the two owner-
pinned anchors (8 at 60 s, 24 at 2 min), which are asserted literally on
both sides so neither side can drift alone.

## Run

```bash
python3 -m pytest 75-drama-song-ad-factory/tests/test_storyboard_shot_count -q
python3 75-drama-song-ad-factory/tests/test_storyboard_shot_count/test_count_anchors.py
```

stdlib only, no network, no provider calls. Never writes a verdict file.

## Base and negative controls

`lanes/PKG-06-U3-lane/pkg-06-u3-negative-controls.sh` runs the suite
against origin/main (must FAIL: the calculator rule does not exist there)
and against a handful of one-line mutations of the merged tree (each must
FAIL). A suite that passes everywhere proves nothing.
