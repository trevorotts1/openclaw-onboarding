"""A seeded, per-test live-price cache, so no test reads the machine's own Skill 74 price cache.

Skill 74's adapter reads KIE_LIVE_CACHE_DIR/catalog.json before it asks the network. Pointing the
cache at a temp folder with a fresh per-picture catalog makes a paid-run test
depend on nothing but this file, whatever the machine has cached (the machine's cache prices
gpt-image-2-6 per million tokens, which issue 60 correctly refuses).
"""

from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path
from unittest import mock

DEFAULT_MODEL = "gpt-image-2-6/sunburst-text-to-image"
PER_PICTURE_TEXT = ("GPT Image 2.6 — now just 6 credits ($0.03) for 1 K, 10 credits ($0.05) for 2 K, "
                    "and 16 credits ($0.08) for 4 K.")


def seed_price_cache(testcase, entries=None):
    """Point KIE_LIVE_CACHE_DIR at a fresh temp folder holding a seeded catalog."""
    tmp = tempfile.TemporaryDirectory()
    testcase.addCleanup(tmp.cleanup)
    root = Path(tmp.name)
    models = [{"model": m, "pricingDesc": d} for m, d in (entries or [(DEFAULT_MODEL, PER_PICTURE_TEXT)])]
    (root / "cache").mkdir()
    (root / "cache" / "catalog.json").write_text(
        json.dumps({"fetched_at": time.time(), "models": models}), encoding="utf-8")
    patcher = mock.patch.dict(os.environ, {"KIE_LIVE_CACHE_DIR": str(root / "cache")})
    patcher.start()
    testcase.addCleanup(patcher.stop)
    return root
