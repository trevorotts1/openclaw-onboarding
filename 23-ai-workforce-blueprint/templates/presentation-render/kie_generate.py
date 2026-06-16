#!/usr/bin/env python3
"""
kie_generate.py — canonical KIE.ai image generation helper for the Presentations pipeline.

This is the image-to-image / text-to-image submit+poll+download helper used by the full
webinar pipeline when references (logo, founder portrait, style frame) must be passed.
For the single-command deterministic text-to-image deck, use build_deck.py in this same
directory instead — it composes the prompt mechanically and assembles the .pptx for you.

USAGE:
    python3 kie_generate.py <prompts.json> <renders_dir>

    prompts.json shape:
    [
      {
        "slide": "slide-01",
        "prompt": "...",
        "mode": "i2i",          // "i2i" = gpt-image-2-image-to-image (DEFAULT), "t2i" = gpt-image-2-text-to-image
        "input_urls": ["https://..."]   // required when mode == "i2i"
      },
      ...
    ]

    renders_dir: path where slide-NN.png files are written (created if absent).

ENVIRONMENT:
    KIE_API_KEY — the CLIENT's own KIE.ai key (never the operator's, never shared).
    Read from env, else from one of the client's standard env stores:
        ~/.openclaw/workspace/.env
        ~/clawd/secrets/.env
        ~/.openclaw/secrets/.env
    (paths expanded against the current user's HOME).

ENGLISH/LATIN-ONLY PIN: every prompt that renders copy MUST carry the mandatory pin
    verbatim (the caller embeds it in `prompt`):
      "All text rendered in the image MUST be in English, Latin alphabet ONLY. NO
       Chinese/CJK or non-Latin characters anywhere. Render the copy spelled correctly,
       letter-for-letter. No garbled, misspelled, or invented text."

RATE CAP: 20 requests / 10 seconds per KIE.ai docs. This script submits in waves of 20
          with a 10-second sleep between waves.

ENDPOINTS (VERIFIED 2026-06-16, live 200):
    Submit:  POST https://api.kie.ai/api/v1/jobs/createTask
    Poll:    GET  https://api.kie.ai/api/v1/jobs/recordInfo?taskId=<id>

DEAD ENDPOINT (NEVER USE): /api/v1/image/gpt-image — returns HTTP 404.

EXIT CODES:
    0 — all slides downloaded successfully
    1 — one or more slides failed (details printed to stderr)
    2 — fatal configuration error (no API key, bad prompts.json, etc.)
"""

import json
import os
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CREATE_URL = "https://api.kie.ai/api/v1/jobs/createTask"
POLL_URL   = "https://api.kie.ai/api/v1/jobs/recordInfo"

MODEL_I2I  = "gpt-image-2-image-to-image"
MODEL_T2I  = "gpt-image-2-text-to-image"

ASPECT_RATIO = "16:9"
RESOLUTION   = "2K"

RATE_CAP_REQUESTS = 20
RATE_CAP_WINDOW_S = 10

INITIAL_POLL_WAIT_S = 300   # 5 minutes after final submit
POLL_INTERVAL_S     = 60
MAX_POLL_PASSES     = 100

# Client's own env stores (HOME-relative — works on any client box).
SECRETS_CANDIDATES = [
    os.path.expanduser("~/.openclaw/workspace/.env"),
    os.path.expanduser("~/clawd/secrets/.env"),
    os.path.expanduser("~/.openclaw/secrets/.env"),
]

# ---------------------------------------------------------------------------
# Guardrail: REFUSE to run if caller somehow wired the dead endpoint
# ---------------------------------------------------------------------------

DEAD_ENDPOINT_FRAGMENT = "/api/v1/image/gpt-image"


def _load_api_key() -> str:
    """Read KIE_API_KEY from environment, falling back to the client's env stores."""
    key = os.environ.get("KIE_API_KEY", "").strip()
    if key:
        return key.strip("'\"")
    for path in SECRETS_CANDIDATES:
        env_path = Path(path)
        if not env_path.exists():
            continue
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line.startswith("KIE_API_KEY="):
                value = line[len("KIE_API_KEY="):].strip().strip("'\"")
                if value:
                    return value
    print("FATAL: KIE_API_KEY not found in environment or any of:", file=sys.stderr)
    for path in SECRETS_CANDIDATES:
        print("   ", path, file=sys.stderr)
    sys.exit(2)


def _http_json(method: str, url: str, api_key: str, body: Optional[dict] = None) -> dict:
    """Minimal HTTP helper; returns parsed JSON response. Raises on non-200."""
    if DEAD_ENDPOINT_FRAGMENT in url:
        raise RuntimeError(
            f"REFUSED: attempted to call the dead endpoint {DEAD_ENDPOINT_FRAGMENT}. "
            "This script only uses /api/v1/jobs/createTask and /api/v1/jobs/recordInfo."
        )
    data = json.dumps(body).encode() if body is not None else None
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode()
            return json.loads(raw)
    except urllib.error.HTTPError as exc:
        body_text = exc.read().decode(errors="replace")
        raise RuntimeError(
            f"HTTP {exc.code} {method} {url}\n"
            f"Response: {body_text}\n"
            "If this is a 404 and you see /api/v1/image/gpt-image in the URL above,\n"
            "you have wired the DEAD endpoint. This script only uses /api/v1/jobs/createTask.\n"
            "Check your call site."
        ) from exc


def _submit_slide(slide: dict, api_key: str) -> str:
    """Submit one slide to createTask; return taskId."""
    mode = slide.get("mode", "i2i").lower()
    if mode == "i2i":
        model = MODEL_I2I
    elif mode == "t2i":
        model = MODEL_T2I
    else:
        raise ValueError(f"Slide {slide['slide']}: unknown mode '{mode}'. Use 'i2i' or 't2i'.")

    input_block: dict = {
        "prompt": slide["prompt"],
        "aspect_ratio": ASPECT_RATIO,
        "resolution": RESOLUTION,
    }

    if mode == "i2i":
        urls = slide.get("input_urls", [])
        if not urls:
            raise ValueError(
                f"Slide {slide['slide']}: mode=i2i requires at least one input_urls entry "
                "(first entry must be the logo URL). If there truly is no logo, set mode=t2i."
            )
        input_block["input_urls"] = urls

    payload = {"model": model, "input": input_block}

    resp = _http_json("POST", CREATE_URL, api_key, body=payload)

    if resp.get("code") != 200:
        raise RuntimeError(
            f"Slide {slide['slide']}: createTask returned non-200 code.\n"
            f"Full response: {json.dumps(resp)}"
        )

    task_id = resp.get("data", {}).get("taskId")
    if not task_id:
        raise RuntimeError(
            f"Slide {slide['slide']}: createTask 200 but no taskId in response.\n"
            f"Full response: {json.dumps(resp)}"
        )

    return task_id


def _poll_task(task_id: str, api_key: str) -> str:
    """Poll recordInfo until success/fail. Returns resultUrls[0] on success."""
    url = f"{POLL_URL}?taskId={task_id}"
    for attempt in range(MAX_POLL_PASSES):
        resp = _http_json("GET", url, api_key)
        data = resp.get("data", {})
        state = data.get("state", "").lower()

        if state == "success":
            result_json_str = data.get("resultJson")
            if not result_json_str:
                raise RuntimeError(
                    f"taskId {task_id}: state=success but resultJson is missing.\n"
                    f"Full response: {json.dumps(resp)}"
                )
            result_obj = json.loads(result_json_str)
            urls = result_obj.get("resultUrls", [])
            if not urls:
                raise RuntimeError(
                    f"taskId {task_id}: resultJson parsed but resultUrls is empty.\n"
                    f"Parsed resultJson: {json.dumps(result_obj)}"
                )
            return urls[0]

        if state in ("fail", "failed", "error", "cancelled"):
            fail_code = data.get("failCode", "unknown")
            fail_msg  = data.get("failMsg", "no message")
            raise RuntimeError(
                f"taskId {task_id}: terminal state '{state}'. "
                f"failCode={fail_code} failMsg={fail_msg}"
            )

        # still waiting
        print(f"  [{attempt+1}/{MAX_POLL_PASSES}] taskId {task_id}: state={state!r}, sleeping {POLL_INTERVAL_S}s...")
        time.sleep(POLL_INTERVAL_S)

    raise RuntimeError(
        f"taskId {task_id}: exceeded {MAX_POLL_PASSES} poll passes still in 'waiting'. "
        "Checkpoint task ID and escalate."
    )


def _download(url: str, dest: Path) -> None:
    """
    Download the KIE result image URL to dest path.
    The result URL is a CDN link (tempfile.aiquickdraw.com or similar) that does NOT
    require the KIE Bearer token — sending it causes HTTP 403. Plain unauthenticated GET.
    """
    req = urllib.request.Request(url, headers={"User-Agent": "kie_generate/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=120) as resp, open(dest, "wb") as f:
            f.write(resp.read())
    except Exception as exc:
        raise RuntimeError(f"Download failed for {url}: {exc}") from exc


def _guardrail_scan_prompts(slides: list) -> None:
    """
    Guardrail: scan the incoming prompts JSON for any usage of the dead endpoint fragment.
    This catches agents that embed raw HTTP calls in their prompts or pass dead-endpoint URLs
    as input_urls by mistake. The fragment appearing in plain prompt TEXT is not a problem;
    the fragment appearing as a URL value in input_urls is.
    """
    for slide in slides:
        for url in slide.get("input_urls", []):
            if DEAD_ENDPOINT_FRAGMENT in str(url):
                print(
                    f"GUARDRAIL FAIL (slide {slide.get('slide', '?')}): "
                    f"The dead KIE endpoint '{DEAD_ENDPOINT_FRAGMENT}' was found in input_urls. "
                    f"input_urls must contain image reference URLs, not API endpoints. "
                    f"Offending value: {url}",
                    file=sys.stderr,
                )
                sys.exit(2)


def main():

    if len(sys.argv) != 3:
        print(
            "Usage: python3 kie_generate.py <prompts.json> <renders_dir>",
            file=sys.stderr,
        )
        sys.exit(2)

    prompts_path = Path(sys.argv[1])
    renders_dir  = Path(sys.argv[2])

    if not prompts_path.exists():
        print(f"FATAL: prompts file not found: {prompts_path}", file=sys.stderr)
        sys.exit(2)

    renders_dir.mkdir(parents=True, exist_ok=True)

    api_key = _load_api_key()
    slides  = json.loads(prompts_path.read_text())

    if not isinstance(slides, list) or not slides:
        print("FATAL: prompts.json must be a non-empty JSON array.", file=sys.stderr)
        sys.exit(2)

    _guardrail_scan_prompts(slides)

    # ------------------------------------------------------------------
    # Phase 1: Submit in waves of RATE_CAP_REQUESTS
    # ------------------------------------------------------------------
    task_map: dict[str, dict] = {}   # taskId -> slide dict

    print(f"\n=== KIE.ai generate — {len(slides)} slides ===")
    print(f"Submit endpoint: {CREATE_URL}")
    print(f"Rate cap: {RATE_CAP_REQUESTS} per {RATE_CAP_WINDOW_S}s\n")

    for wave_start in range(0, len(slides), RATE_CAP_REQUESTS):
        wave = slides[wave_start : wave_start + RATE_CAP_REQUESTS]
        print(f"--- Submitting wave: slides {wave_start+1}–{wave_start+len(wave)} ---")

        for slide in wave:
            slide_name = slide.get("slide", f"slide-{wave_start+1:02d}")
            try:
                task_id = _submit_slide(slide, api_key)
                task_map[task_id] = slide
                print(f"  SUBMITTED {slide_name} -> taskId={task_id}")
            except Exception as exc:
                print(f"  SUBMIT ERROR {slide_name}: {exc}", file=sys.stderr)
                # record as failed with sentinel
                slide["_submit_error"] = str(exc)

        if wave_start + RATE_CAP_REQUESTS < len(slides):
            print(f"  Sleeping {RATE_CAP_WINDOW_S}s (rate cap window)...")
            time.sleep(RATE_CAP_WINDOW_S)

    # ------------------------------------------------------------------
    # Phase 2: Initial wait before polling
    # ------------------------------------------------------------------
    if not task_map:
        print("FATAL: no tasks submitted successfully.", file=sys.stderr)
        sys.exit(1)

    print(f"\nAll waves submitted. Waiting {INITIAL_POLL_WAIT_S}s before first poll...")
    time.sleep(INITIAL_POLL_WAIT_S)

    # ------------------------------------------------------------------
    # Phase 3: Poll and download
    # ------------------------------------------------------------------
    failed: list[str] = []
    succeeded: list[str] = []

    for task_id, slide in task_map.items():
        slide_name = slide.get("slide", task_id)
        out_path   = renders_dir / f"{slide_name}.png"
        print(f"\nPolling {slide_name} (taskId={task_id})...")

        try:
            result_url = _poll_task(task_id, api_key)
            print(f"  SUCCESS state=success, resultUrls[0]={result_url}")
            _download(result_url, out_path)

            # Verify the file is a real PNG (check magic bytes)
            with open(out_path, "rb") as f:
                magic = f.read(8)
            if magic[:4] != b"\x89PNG":
                raise RuntimeError(
                    f"Downloaded file does not appear to be a PNG "
                    f"(magic bytes: {magic[:8].hex()}). "
                    f"Check KIE resultUrls[0] is a direct image URL."
                )

            file_size = out_path.stat().st_size
            print(f"  DOWNLOADED -> {out_path} ({file_size:,} bytes, PNG verified)")
            succeeded.append(slide_name)

        except Exception as exc:
            print(f"  FAIL {slide_name}: {exc}", file=sys.stderr)
            failed.append(slide_name)

    # Also mark any that failed at submit time
    for slide in slides:
        if "_submit_error" in slide:
            failed.append(slide.get("slide", "unknown"))

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    print(f"\n=== SUMMARY ===")
    print(f"Succeeded: {len(succeeded)}")
    print(f"Failed:    {len(failed)}")
    if succeeded:
        print("  OK: " + ", ".join(succeeded))
    if failed:
        print("  FAILED: " + ", ".join(failed), file=sys.stderr)
        sys.exit(1)

    sys.exit(0)


if __name__ == "__main__":
    main()
