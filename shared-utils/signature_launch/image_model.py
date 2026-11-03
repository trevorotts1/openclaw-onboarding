#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The one place the Signature Launch wrappers get their paid image-to-image model id (IMG-19).

Skill 71 says never hard-code a model id. The id comes from Skill 66's own selector
(66-kie-image/scripts/select_image_model.py, gpt_default_routes): the newest GPT Image generation per
Skill 74 `latest-family` when that adapter answers, else Skill 66's models.json default. Nothing here
falls back to a literal id: if Skill 66 cannot answer, resolve() raises and the caller stops before
anything is drawn or paid for.

Loaded by path (the shared-utils convention); stdlib only; reads no secret. Nothing is cached, so a
changed Skill 66 default is picked up by the next call.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Optional


def _skill66_root() -> Path:
    """Skill 66 beside shared-utils: <repo>/66-kie-image (onboarding) or <repo>/.claude/skills/66-kie-image
    (deployed). The first that holds the selector wins; neither means the onboarding path, so resolve()
    refuses by name."""
    repo = Path(__file__).resolve().parents[2]
    cands = [repo / "66-kie-image", repo / ".claude" / "skills" / "66-kie-image"]
    return next((c for c in cands if (c / "scripts" / "select_image_model.py").is_file()), cands[0])


SKILL66_ROOT = _skill66_root()


class ImageModelError(RuntimeError):
    pass


def resolve(root: Optional[Path] = None, task: str = "i2i") -> str:
    """The Skill 66 default model id for `task` ("i2i" image-to-image, or "t2i" text-to-image)."""
    selector = Path(root or SKILL66_ROOT) / "scripts" / "select_image_model.py"
    if not selector.is_file():
        raise ImageModelError(f"Skill 66 selector not found at {selector}")
    saved = sys.modules.pop("adapter_bridge", None)  # the selector imports its own sibling by this name
    try:
        spec = importlib.util.spec_from_file_location("skill66_select_image_model", selector)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        model = mod.gpt_default_routes().get(task)
    except Exception as exc:
        raise ImageModelError(f"Skill 66 could not resolve the {task} model: {exc}") from exc
    finally:
        sys.modules.pop("adapter_bridge", None)
        if saved is not None:
            sys.modules["adapter_bridge"] = saved
    if not isinstance(model, str) or not model.strip():
        raise ImageModelError(f"Skill 66 returned no {task} model id")
    return model


if __name__ == "__main__":
    print(resolve())
