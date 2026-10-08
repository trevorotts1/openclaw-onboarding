# core/smp/length_routing — the Skill 35 length rules and routing table

Wave unit **SMP-W1-U4**. Source: Owner D27 / D35, plan section 6.15,
decision log 35 (2026-10-07). Pure data, stdlib only, zero paid calls.

## 1. The 59.0 second hard cap

The **planner version** of the weekly drama song must **end by 59.0
seconds**. GoHighLevel publishes YouTube Shorts and the Instagram feed at
**60 seconds**, so the render is held one tenth under that line.

**Approved ads run 62-63 seconds** — over the cap and over the 60 second
Shorts/feed limit. A planner version in that range is refused by name:

```python
validate_duration(59.0, 60)   # (True, "")
validate_duration(58.9, 60)   # (True, "")
validate_duration(59.1, 60)   # (False, "...must end by 59.0 seconds...")
validate_duration(62.5, 60)   # (False, "...approved ads run 62-63 seconds...")
validate_duration(90.0, 90)   # (True, "")   90-option window is 88.0-95.0
validate_duration(80.0, 90)   # (False, "...between 88.0 and 95.0 seconds...")
```

Only 60 and 90 are offered; any other option is refused by name.

## 2. The 90-second option route

The 90-second option posts **ONLY** to:

| Facebook Reels | Instagram Reels | TikTok | LinkedIn |
|---|---|---|---|

It **never** posts to YouTube Shorts or the Instagram feed. Threads is
deliberately outside the 90-second option even though its own limit is
5 minutes: the option list is an explicit allow-list from the owner plan,
not the output of a limit calculation. The table below still governs every
other duration, so a 120 second clip still reaches Threads.

## 3. Per-channel length routing table

GoHighLevel, checked 2026-10-07:

| channel | min seconds | max seconds |
|---|---|---|
| YouTube Shorts | 0 | 60 |
| Instagram feed | 0 | 60 |
| Facebook Reels | 3 | 90 |
| TikTok | 3 | 180 |
| Instagram Reels | 0 | 900 (15 minutes) |
| LinkedIn | 0 | 1800 (30 minutes) |
| Threads | 0 | 300 (5 minutes) |

Outside the table:

- **Google Business Profile** — never, until its limit is verified in the
  GoHighLevel documentation.
- **`* Stories`** — never; Stories carry the 15-second teaser only
  (SMP-W1-U5).
- **Any other destination name** — refused by name ("not a Skill 35
  destination in this routing table"). Fail-closed: never a silent drop of
  the channel row, never a block on the channels that do accept the length.

Every row carries a reason, allowed or not, so the planner schedule can show
the client exactly why a surface was skipped.

## Interface

```python
from core.smp.length_routing import (
    validate_duration, route_channels, channels_for_option,
    HARD_CAP_S, CHANNEL_LIMITS, OPTION_90_CHANNELS,
)

plan = route_channels(90, ["YouTube Shorts", "Threads", "TikTok"])
# [{'channel': 'YouTube Shorts', 'allowed': False, 'reason': '...'},
#  {'channel': 'Threads',         'allowed': False, 'reason': '...'},
#  {'channel': 'TikTok',          'allowed': True,  'reason': '...'}]
```

`route_channels` is also exported as `channel_acceptance` and `route` — the
three names the wave's router interface (`core/smp/weekly_step`, SMP-W1-U1)
looks for. This unit is the authority on the table; U1's inline fallback
table is the standalone fallback used only while this directory is absent.

## KIE path

**Skill 74 only.** This package never reaches KIE at all: no key, no host,
no second client, no transport of any kind, nothing dispatched
(`KIE_PATH = "skill-74"`, `KIE_DISPATCH = "not_required"`).

## Tests

```bash
python3 core/smp/length_routing/test_length_routing.py
python3 -m unittest discover -s core/smp/length_routing -p 'test_*.py'
```

Both green, exit 0. Offline, no network, no media files, no operator paths.

## Known seams (left to their owning units)

- **Threads at 90.** `core/smp/weekly_step` (SMP-W1-U1) ships a standalone
  fallback table whose 90-second row includes Threads. This unit's owner
  allow-list does not, and this unit wins when present, so U1's
  Threads-at-90 expectation needs to follow the owner list at integration.
- **Facebook Reels ceiling vs the 90-option window.** The option must land
  in 88.0-95.0 s but Facebook Reels tops out at 90 s, so a render above 90
  seconds loses Facebook Reels on the platform limit alone. The limit wins;
  `route_channels` reports it that way.
- **Destinations outside the owner's table** (Pinterest, X, Bluesky, …) are
  refused by name until the owner plan supplies a limit for them.
