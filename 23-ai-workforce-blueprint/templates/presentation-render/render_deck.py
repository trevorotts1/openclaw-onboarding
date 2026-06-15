"""
CANONICAL RENDER MODULE — all client presentation decks MUST call this module.
Per-deck renderers are FORBIDDEN. See AF-RENDERER auto-fail in QC gate.

Usage:
    from render_deck import render_deck

    results = render_deck(
        slides=[
            {
                "slide_id": "slide-01",
                "prompt": "<full 1500-15000 char prompt>",
                "target_path": "/abs/path/to/slide-01.png"
            },
            ...
        ],
        config={
            "model": "gpt-image-2-text-to-image",   # pinned in client's intake.json
            "client_slug": "operator-test",
            "kie_api_key": "...",
            "workspace_dir": "/abs/path/to/workspace"
        }
    )

    # results is a list of dicts: { slide_id, target_path, status, task_id, model_used, fallback }
    # render_manifest.json is written to workspace_dir

Version: 1.0
Last updated: 2026-06-14

PROHIBITION: This module is FORBIDDEN from doing any Pillow text overlay or black scrim compositing.
Typography is baked INTO the image by the model (prompt elements 3 and 4). There is no Pillow overlay
path. There is no black scrim. See AF-BAKED auto-fail in QC gate.
"""

import json
import os
import time
import threading
import urllib.request
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

# ---------------------------------------------------------------------------
# CONSTANTS
# ---------------------------------------------------------------------------

APPROVED_MODELS = [
    "gpt-image-2-text-to-image",
    "gpt-image-2-image-to-image",
]

# FALLBACK_MODEL fires ONLY on a hard API failure of the primary.
# It is NEVER the silent primary. Every invocation is MANDATORY-LOGGED to render_manifest.json.
FALLBACK_MODEL = "nano-banana-2"

PROMPT_CHAR_FLOOR = 1500
PROMPT_CHAR_CEILING = 15000

# Required structural blocks -- checked case-insensitively
REQUIRED_STRUCTURAL_BLOCKS = [
    "[ARCHETYPE",
    "NEGATIVE BLOCK",
    "Do not ",
]

KIE_CREATE_TASK_URL = "https://api.kie.ai/api/v1/jobs/createTask"
KIE_RECORD_INFO_URL = "https://api.kie.ai/api/v1/jobs/recordInfo"

MAX_POLLS_PER_TASK = 100
POLL_SLEEP_SECONDS = 5

# Rate limit: 20 requests per 10 seconds (source: https://docs.kie.ai/, verified 2026-06-14)
RATE_LIMIT_MAX = 20
RATE_LIMIT_WINDOW = 10.0  # seconds


# ---------------------------------------------------------------------------
# RATE LIMITER (token bucket)
# ---------------------------------------------------------------------------

class _TokenBucket:
    def __init__(self, max_tokens: int, window_seconds: float):
        self._max = max_tokens
        self._window = window_seconds
        self._tokens = max_tokens
        self._last_refill = time.monotonic()
        self._lock = threading.Lock()

    def acquire(self):
        """Block until a token is available."""
        while True:
            with self._lock:
                now = time.monotonic()
                elapsed = now - self._last_refill
                if elapsed >= self._window:
                    self._tokens = self._max
                    self._last_refill = now
                if self._tokens > 0:
                    self._tokens -= 1
                    return
                wait = self._window - elapsed
            time.sleep(wait + 0.05)


_bucket = _TokenBucket(RATE_LIMIT_MAX, RATE_LIMIT_WINDOW)


# ---------------------------------------------------------------------------
# VALIDATION HELPERS
# ---------------------------------------------------------------------------

def _validate_model(model: str) -> None:
    """Hard check: model must be in the approved list."""
    if model not in APPROVED_MODELS:
        raise ValueError(
            f"AF-MODEL-SOVEREIGNTY: model '{model}' is not approved for client presentations. "
            f"Approved: gpt-image-2-text-to-image, gpt-image-2-image-to-image. "
            f"A fallback may fire ONLY on a hard API failure and MUST be logged."
        )


def _validate_prompt(slide_id: str, prompt: str) -> None:
    """Hard check: prompt must be within char range and have required structural blocks."""
    length = len(prompt)
    if length < PROMPT_CHAR_FLOOR or length > PROMPT_CHAR_CEILING:
        raise ValueError(
            f"AF-PROMPT-FLOOR: slide {slide_id} prompt is {length} chars "
            f"(required: {PROMPT_CHAR_FLOOR}-{PROMPT_CHAR_CEILING}). HARD BLOCK."
        )

    prompt_lower = prompt.lower()
    for block in REQUIRED_STRUCTURAL_BLOCKS:
        if block.lower() not in prompt_lower:
            raise ValueError(
                f"AF-PROMPT-FLOOR: slide {slide_id} prompt missing required structural blocks "
                f"(archetype declaration, negative block, or Do-not imperative sentences). HARD BLOCK."
            )


# ---------------------------------------------------------------------------
# KIE.AI API HELPERS
# ---------------------------------------------------------------------------

def _kie_post(url: str, body: dict, api_key: str) -> dict:
    """POST JSON to Kie.ai and return parsed response dict."""
    payload = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _kie_get(url: str, api_key: str) -> dict:
    """GET from Kie.ai and return parsed response dict."""
    req = urllib.request.Request(
        url,
        headers={"Authorization": f"Bearer {api_key}"},
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _submit_task(slide_id: str, prompt: str, model: str, api_key: str) -> Optional[str]:
    """Submit a createTask call to Kie.ai. Returns taskId or None on failure."""
    _bucket.acquire()
    body = {
        "model": model,
        "input": {
            "prompt": prompt,
            "aspect_ratio": "16:9",
            "resolution": "2K",
            "output_format": "png",
        },
    }
    try:
        resp = _kie_post(KIE_CREATE_TASK_URL, body, api_key)
        if resp.get("code") == 200 and resp.get("data", {}).get("taskId"):
            return resp["data"]["taskId"]
        print(f"[RENDER MODULE v1.0] createTask non-200 for slide {slide_id}: {resp}")
        return None
    except Exception as exc:
        print(f"[RENDER MODULE v1.0] createTask error for slide {slide_id}: {exc}")
        return None


def _poll_task(task_id: str, api_key: str) -> Optional[List[str]]:
    """
    Poll recordInfo up to MAX_POLLS_PER_TASK times.
    Returns a list of result URLs on success, or None on failure/timeout.
    """
    for poll_num in range(MAX_POLLS_PER_TASK):
        time.sleep(POLL_SLEEP_SECONDS)
        try:
            url = f"{KIE_RECORD_INFO_URL}?taskId={task_id}"
            resp = _kie_get(url, api_key)
            state = resp.get("data", {}).get("state", "")
            if state == "success":
                result_json_raw = resp["data"].get("resultJson", "{}")
                result_json = (
                    json.loads(result_json_raw)
                    if isinstance(result_json_raw, str)
                    else result_json_raw
                )
                urls = result_json.get("resultUrls", [])
                if urls:
                    return urls
                print(f"[RENDER MODULE v1.0] task {task_id} succeeded but no resultUrls")
                return None
            elif state == "fail":
                print(
                    f"[RENDER MODULE v1.0] task {task_id} reported state=fail "
                    f"at poll {poll_num + 1}"
                )
                return None
            # else: waiting/queuing/generating -- continue polling
        except Exception as exc:
            print(
                f"[RENDER MODULE v1.0] poll error for task {task_id} "
                f"at poll {poll_num + 1}: {exc}"
            )

    print(f"[RENDER MODULE v1.0] task {task_id} timed out after {MAX_POLLS_PER_TASK} polls")
    return None


def _download_image(url: str, target_path: str) -> bool:
    """Download a URL to target_path. Returns True on success."""
    try:
        os.makedirs(os.path.dirname(target_path), exist_ok=True)
        req = urllib.request.Request(url, headers={"User-Agent": "render-deck/1.0"})
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = resp.read()
        with open(target_path, "wb") as f:
            f.write(data)
        return True
    except Exception as exc:
        print(f"[RENDER MODULE v1.0] download failed for {url}: {exc}")
        return False


# ---------------------------------------------------------------------------
# PUBLIC API
# ---------------------------------------------------------------------------

def render_deck(slides: List[Dict[str, Any]], config: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Render a list of slides via Kie.ai using the canonical render module.

    Parameters
    ----------
    slides : list of dicts, each with:
        - slide_id   : str  (e.g. "slide-01")
        - prompt     : str  (1500-15000 chars; must contain [ARCHETYPE, NEGATIVE BLOCK, "Do not ")
        - target_path: str  (absolute path where the rendered PNG will be saved)

    config : dict with:
        - model         : str (REQUIRED -- pinned in client's intake.json;
                               must be gpt-image-2-text-to-image or gpt-image-2-image-to-image)
        - client_slug   : str
        - kie_api_key   : str
        - workspace_dir : str (render_manifest.json is written here)

    Returns
    -------
    list of dicts, one per slide:
        slide_id, target_path, status, task_id, model_used, fallback (bool), fallback_reason

    Raises
    ------
    ValueError
        If any model or prompt validation fails. These are hard blocks -- no slides are
        submitted until ALL validations pass.
    """
    # Resolve config
    model = config.get("model", "gpt-image-2-text-to-image")
    client_slug = config.get("client_slug", "unknown")
    api_key = config.get("kie_api_key", "")
    workspace_dir = config.get("workspace_dir", ".")

    print(
        f"[RENDER MODULE v1.0] Starting render for client={client_slug}, "
        f"model={model}, slides={len(slides)}"
    )

    # -------------------------------------------------------------------------
    # VALIDATION PHASE -- all slides validated before any API call
    # -------------------------------------------------------------------------
    _validate_model(model)

    for slide in slides:
        _validate_prompt(slide["slide_id"], slide["prompt"])

    print(
        f"[RENDER MODULE v1.0] All validations passed. "
        f"Submitting {len(slides)} slides to Kie.ai."
    )

    # -------------------------------------------------------------------------
    # RENDER PHASE
    # -------------------------------------------------------------------------
    manifest_slides = []
    results = []

    for slide in slides:
        slide_id = slide["slide_id"]
        prompt = slide["prompt"]
        target_path = slide["target_path"]

        manifest_entry = {
            "slide_id": slide_id,
            "target_path": target_path,
            "prompt_char_count": len(prompt),
            "model_requested": model,
            "model_used": None,
            "task_id": None,
            "fallback": False,
            "fallback_reason": None,
            "status": "pending",
            "submitted_at": datetime.now(timezone.utc).isoformat(),
        }

        # Attempt primary model
        task_id = _submit_task(slide_id, prompt, model, api_key)
        if task_id is not None:
            manifest_entry["task_id"] = task_id
            manifest_entry["model_used"] = model
            result_urls = _poll_task(task_id, api_key)
        else:
            result_urls = None

        # Fallback path -- ONLY on hard API failure of primary
        if result_urls is None:
            fallback_reason = (
                f"Primary model {model} returned no task_id or failed polling."
            )
            print(
                f"[FALLBACK EVENT] Primary model {model} failed for slide {slide_id}. "
                f"Engaging fallback: {FALLBACK_MODEL}. "
                f"This event is MANDATORY-LOGGED."
            )
            manifest_entry["fallback"] = True
            manifest_entry["fallback_reason"] = fallback_reason
            manifest_entry["fallback_model"] = FALLBACK_MODEL
            manifest_entry["fallback_at"] = datetime.now(timezone.utc).isoformat()

            fallback_task_id = _submit_task(slide_id, prompt, FALLBACK_MODEL, api_key)
            if fallback_task_id is not None:
                manifest_entry["fallback_task_id"] = fallback_task_id
                result_urls = _poll_task(fallback_task_id, api_key)
                if result_urls is not None:
                    manifest_entry["model_used"] = FALLBACK_MODEL
                    manifest_entry["task_id"] = fallback_task_id

        # Download result
        if result_urls:
            first_url = result_urls[0]
            success = _download_image(first_url, target_path)
            manifest_entry["status"] = "done" if success else "download-failed"
        else:
            manifest_entry["status"] = "failed"

        manifest_slides.append(manifest_entry)
        results.append({
            "slide_id": slide_id,
            "target_path": target_path,
            "status": manifest_entry["status"],
            "task_id": manifest_entry.get("task_id"),
            "model_used": manifest_entry.get("model_used"),
            "fallback": manifest_entry["fallback"],
            "fallback_reason": manifest_entry.get("fallback_reason"),
        })

    # -------------------------------------------------------------------------
    # WRITE MANIFEST
    # -------------------------------------------------------------------------
    os.makedirs(workspace_dir, exist_ok=True)
    manifest = {
        "module_version": "1.0",
        "rendered_at": datetime.now(timezone.utc).isoformat(),
        "client_slug": client_slug,
        "model_pin": model,
        "slide_count": len(slides),
        "slides": manifest_slides,
        "fallback_events": [s for s in manifest_slides if s.get("fallback")],
    }
    manifest_path = os.path.join(workspace_dir, "render_manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    done_count = sum(1 for r in results if r["status"] == "done")
    fail_count = len(results) - done_count
    fallback_count = sum(1 for r in results if r["fallback"])
    print(
        f"[RENDER MODULE v1.0] Complete: {done_count} done, {fail_count} failed, "
        f"{fallback_count} fallback events. Manifest: {manifest_path}"
    )

    return results
