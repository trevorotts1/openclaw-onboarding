#!/usr/bin/env python3
"""
kie_generate.py - the SKILL 06 COPY of the KIE.ai image generation helper (presentation-render twin).

WHICH COPY IS THIS: this file is the self-contained twin that 06-ghl-install-pages/tools/ghl_media.py
runs (it shells `python3 <this file> <prompts.json> <renders_dir>` from generate_images()).
The Presentations department does NOT run this copy. It runs the canonical copy at
23-ai-workforce-blueprint/templates/role-library/presentations/scripts/kie_generate.py,
which sits behind the front-door nonce and submits and polls through kie_tasks.py.
For a deck, use build_deck.py (role-library/presentations/scripts/): it does not compose
prompts, it renders the authored per-slide prompt verbatim and assembles the .pptx.

INTENTIONAL DIVERGENCE FROM THE CANONICAL COPY (declared 2026-10-05, recorded in
scripts/shared-script-authority.json; both headers say the same thing):
  * SAME, ported here (FIX 67): the secret-name canon (shared-utils/secret_helper aliases
    KIE_AI_API_KEY, KIE_KEY, KIE_VIDEO_API_KEY, KIE_API_KEY_IAFS all resolve to the one
    credential) and placeholder-value rejection, in _load_api_key, _import_secret_helper,
    _kie_alias_names and _is_placeholder_value. These four are byte-for-byte the canonical
    functions; keep them identical.
  * DIFFERENT ON PURPOSE - no front-door nonce gate. The canonical copy refuses to run
    unless presentation-canonical-entry.sh minted the per-run nonce, and it verifies the
    nonce by importing build_deck.py from its own directory. This twin sits beside
    render_deck.py, not build_deck.py, and Skill 06 (ghl_media.py, ghl_image_stage.py)
    calls it for non-deck page images with no Presentations run directory and no nonce.
    Porting the gate would make every Skill 06 call exit 2, so it is not ported.
  * DIFFERENT ON PURPOSE - no kie_tasks.py lifecycle. This twin keeps its own wave submit
    (20 per 10 seconds), waits 5 minutes after the last submit, then polls one task at a
    time every 60 seconds for up to 100 passes. The canonical copy has no initial wait and
    polls every pending task round-robin every 60 seconds with a 6,000 second deadline.
    This twin has no kie_tasks.py beside it, so it stays self-contained.
  * SAME as build_deck.py (declared 2026-10-05): the result download is an authenticated GET
    (Bearer + browser User-Agent), because an unauthenticated GET returned HTTP 403 live.
    The canonical role-library kie_generate.py does the same (identical _download).
Limits and rates shared by every KIE skill: 07-kie-setup/references/kie-common-rules.md.

USAGE:
    python3 kie_generate.py <prompts.json> <renders_dir>

    prompts.json shape:
    [
      {
        "slide": "slide-01",
        "prompt": "...",
        "mode": "i2i",          // "i2i" = gpt-image-2-5-sunburst-image-to-image (DEFAULT), "t2i" = gpt-image-2-5-sunburst-text-to-image
        "input_urls": ["https://..."]   // required when mode == "i2i"
      },
      ...
    ]

    renders_dir: path where slide-NN.png files are written (created if absent).

ENVIRONMENT:
    KIE_API_KEY — the CLIENT's own KIE.ai key (never the operator's, never shared).
    Read from env, else from the selected client's secrets stores resolved by
    presentation_job.oc_paths ($OPENCLAW_SECRETS must stay inside that client boundary;
    no hardcoded path; HIGH-3). Any KIE family alias name is accepted and a placeholder
    value is rejected (FIX 67, see above).

LOCKSTEP NOTE: this helper ships in TWO repo locations —
    23-ai-workforce-blueprint/templates/presentation-render/kie_generate.py
    23-ai-workforce-blueprint/templates/role-library/presentations/scripts/kie_generate.py
Keep the logic they SHARE identical when editing either (v17.0.42 re-unified a drift where
each copy carried a fix the other lacked: HIGH-3 secrets override vs FIX-IMG-03
per-entry aspect_ratio/resolution + the runtime dead-endpoint guard). The two intentional
differences (no nonce gate, no kie_tasks.py lifecycle) are listed at the top of this header.
Both copies are hash-locked by scripts/shared-script-authority.json (checked by
scripts/check-shared-script-drift.py); after any edit re-record with --record.

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

import importlib.util
import json
import os
import sys
import time
import urllib.parse
import urllib.request
import urllib.error
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CREATE_URL = "https://api.kie.ai/api/v1/jobs/createTask"
POLL_URL   = "https://api.kie.ai/api/v1/jobs/recordInfo"

# ---------------------------------------------------------------------------
# FIX 13 — no literal image model IDs in this helper. They resolve from the
# central versioned catalog (presentation_job/model_catalog.py beside the
# canonical renderer). PRESENTATION_MODEL_CATALOG=0 restores the exact
# pre-FIX-13 gpt-image-2-* literals via the catalog's rollback table; an
# unloadable catalog FAILS CLOSED rather than guessing an id on a paid call.
# ---------------------------------------------------------------------------
def _load_model_catalog():
    import importlib
    here = Path(__file__).resolve().parent
    candidates = [
        here,                                                          # role-library copy (same dir)
        here.parent / "role-library" / "presentations" / "scripts",    # presentation-render copy
        here.parent.parent / "role-library" / "presentations" / "scripts",
    ]
    for cand in candidates:
        if (cand / "presentation_job" / "model_catalog.py").is_file():
            if str(cand) not in sys.path:
                sys.path.insert(0, str(cand))
            return importlib.import_module("presentation_job.model_catalog")
    raise RuntimeError(
        "FIX 13: presentation_job/model_catalog.py not reachable from "
        f"{Path(__file__).resolve()} — refusing to guess model ids.")


_model_catalog = _load_model_catalog()


def _image_models() -> "tuple":
    """(MODEL_T2I, MODEL_I2I) re-resolved from the LIVE catalog on every call,
    so an operator bump changes the next submit without editing code."""
    t = _model_catalog.image_mode_table()
    return t["MODEL_T2I"], t["MODEL_I2I"]

MODEL_T2I, MODEL_I2I = _image_models()  # catalog-resolved import-time snapshot

ASPECT_RATIO = "16:9"
RESOLUTION   = "2K"

RATE_CAP_REQUESTS = 20
RATE_CAP_WINDOW_S = 10

INITIAL_POLL_WAIT_S = 300   # 5 minutes after final submit
POLL_INTERVAL_S     = 60
MAX_POLL_PASSES     = 100

# ---------------------------------------------------------------------------
# Secrets-file resolution (HIGH-3 fix)
# ---------------------------------------------------------------------------
# This is a FLEET template that ships to every client box, so it must NEVER embed
# an operator's literal absolute home path (such a path points at one specific
# machine and would never exist on a client box). The secrets file is resolved at
# RUNTIME:
#   1. $OPENCLAW_SECRETS, validated inside the selected client boundary, then
#   2. that client's standard root/workspace stores via presentation_job.oc_paths.
# Missing authority or invalid pins fail closed, without cross-client fallback.
def _secrets_candidates() -> list:
    """Use the selected-client authority, including its checked explicit override.

    Missing deployment or invalid pins fail closed; no HOME/clawd fallback may
    turn a configuration error into credentials borrowed from another client.
    """
    import importlib
    here = Path(__file__).resolve().parent
    for candidate in (
        here,
        here.parent / "role-library" / "presentations" / "scripts",
        here.parent.parent / "role-library" / "presentations" / "scripts",
    ):
        if (candidate / "presentation_job" / "oc_paths.py").is_file():
            if str(candidate) not in sys.path:
                sys.path.insert(0, str(candidate))
            return [str(path) for path in importlib.import_module(
                "presentation_job.oc_paths").secrets_env_candidates()]
    raise RuntimeError("Selected-client credential path module is missing; no stores loaded")

# ---------------------------------------------------------------------------
# Guardrail: REFUSE to run if caller somehow wired the dead endpoint
# ---------------------------------------------------------------------------

DEAD_ENDPOINT_FRAGMENT = "/api/v1/image/gpt-image"


# ---------------------------------------------------------------------------
# SHARED IMAGE-PROMPT GATE (prompt_gate.py) — the ONE gate every image-API path runs
# ---------------------------------------------------------------------------
# Before this, kie_generate.py submitted any `prompt` to the paid kie.ai API with ZERO
# quality checks — a sanctioned side-door around build_deck.py's 9,000–18,000-char floor.
# It now imports the SAME shared prompt_gate every canonical path uses. Because this helper
# is REUSED by non-presentations skills (06 GHL, 49 funnel, ...), the FULL presentations
# rich gate is OPT-IN via KIE_PROMPT_GATE=presentations; every caller ALWAYS gets the
# universal-safe floor (dead-endpoint + empty-prompt refusal).
#
# The import is NON-FATAL (returns None if the module is not yet deployed beside this file)
# so a shared caller on a partially-updated box is never hard-broken; the per-slide gate
# then degrades to an inline universal-safe check — UNLESS KIE_PROMPT_GATE=presentations was
# explicitly requested, in which case a missing gate FAILS CLOSED (a presentation run must
# never submit ungated).
def _import_prompt_gate():
    import importlib
    here = Path(__file__).resolve().parent
    candidates = [
        here,                                                         # role-library copy (same dir)
        here.parent / "role-library" / "presentations" / "scripts",  # presentation-render copy
        here.parent.parent / "role-library" / "presentations" / "scripts",
    ]
    for cand in candidates:
        if (cand / "prompt_gate.py").is_file():
            if str(cand) not in sys.path:
                sys.path.insert(0, str(cand))
            try:
                return importlib.import_module("prompt_gate")
            except Exception:  # noqa: BLE001 — a broken module degrades to the inline check
                return None
    return None


def _presentations_gate_requested() -> bool:
    """True iff KIE_PROMPT_GATE opts into the FULL presentations gate. Read directly from
    the environment so it works even when the shared prompt_gate module could not be
    imported (in which case a requested presentations gate FAILS CLOSED)."""
    return os.environ.get("KIE_PROMPT_GATE", "").strip().lower() in (
        "presentations", "full", "1", "on", "true")


prompt_gate = _import_prompt_gate()


def _load_api_key() -> str:
    """Read KIE_API_KEY from environment, falling back to the client's standard
    secrets stores (resolved at runtime - no hardcoded operator home path; HIGH-3).
    FIX 67: the NAME is resolved through the one secret-name canon
    (shared-utils/secret_helper: any KIE family alias - KIE_AI_API_KEY,
    KIE_KEY, KIE_VIDEO_API_KEY, KIE_API_KEY_IAFS - resolves to the same
    credential), and a placeholder value (PASTE_REAL_TOKEN / CHANGE_ME / ...)
    is REJECTED wherever it sits. The canon helper is path-imported from the
    repo checkout, the installed skills dir, or /data/.openclaw/skills - the
    same seam _import_prompt_gate/_load_model_catalog use; without it the
    pre-canon direct-name behavior holds, never a hard break."""
    _key_from_env = os.environ.get("KIE_API_KEY", "").strip()
    if _key_from_env:
        value = _key_from_env.strip("'\"")
        if value and not _is_placeholder_value(value):
            return value
    candidates = _secrets_candidates()
    # FIX 67 canon: accept every alias in the KIE key family.
    accepted_names = _kie_alias_names()
    # Try each candidate secrets file in priority order.
    for path in candidates:
        env_path = Path(path)
        if not env_path.exists():
            continue
        for line in env_path.read_text().splitlines():
            line = line.strip()
            for name in accepted_names:
                if line.startswith(f"{name}="):
                    value = line[len(f"{name}="):].strip().strip("'\"")
                    if value and not _is_placeholder_value(value):
                        return value
    print("FATAL: KIE_API_KEY not found in environment or in any of:", file=sys.stderr)
    for path in candidates:
        print("   ", path, file=sys.stderr)
    print("   (set KIE_API_KEY in env, or point $OPENCLAW_SECRETS at the client's .env)",
          file=sys.stderr)
    sys.exit(2)


def _import_secret_helper():
    """Path-import shared-utils/secret_helper.py (the FIX 67 canon helper).
    Returns the module or None when no candidate location has it."""
    import importlib
    here = Path(__file__).resolve().parent
    repo_root = None
    for anc in here.parents:
        if (anc / "shared-utils" / "secret_helper.py").is_file():
            repo_root = anc
            break
    from presentation_job.oc_paths import skills as client_skills
    for d in (os.environ.get("SHARED_UTILS_DIR", "").strip(),
              str(repo_root / "shared-utils") if repo_root else "",
              str(client_skills() / "shared-utils")):
        if d and (Path(d) / "secret_helper.py").is_file():
            try:
                spec = importlib.util.spec_from_file_location(
                    "secret_helper_s51", str(Path(d) / "secret_helper.py"))
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)  # type: ignore
                return mod
            except Exception:  # noqa: BLE001 -- a broken helper is the no-canon path
                return None
    return None


def _kie_alias_names() -> list:
    """The accepted names for the KIE_API_KEY credential: the canonical name
    plus every canon alias; falls back to the pre-canon direct name."""
    helper = _import_secret_helper()
    if helper is None:
        return ["KIE_API_KEY"]
    try:
        return list(helper.alias_list(helper.canonical_for("KIE_API_KEY")))
    except Exception:  # noqa: BLE001 -- canon failure degrades to the direct name
        return ["KIE_API_KEY"]


def _is_placeholder_value(value: str) -> bool:
    """FIX 67: a placeholder value is rejected by every reader. Uses the
    canon's is_placeholder when the helper is reachable; otherwise the same
    minimal inline gate so a partial deploy still refuses."""
    helper = _import_secret_helper()
    if helper is not None:
        try:
            return bool(helper.is_placeholder(value))
        except Exception:  # noqa: BLE001
            pass
    if not value:
        return True
    low = value.strip().lower()
    if len(low) < 10:
        return True
    for sub in ("paste_real_token", "your_key_here", "change_me", "changeme",
                "<todo>", "[replace]", "{{", "placeholder", "example_key",
                "todo:", "xxx"):
        if sub in low:
            return True
    if low.startswith("<") and low.endswith(">"):
        return True
    if low.startswith("[") and low.endswith("]"):
        return True
    return False


class AuthError(Exception):
    """Permanent authentication failure (HTTP 401/403) — the request is identical
    and will fail forever: the key is wrong, the Authorization header format is
    wrong, or the account is locked/rate-locked by the provider. Retrying the same
    request is a guaranteed token furnace. Fail loud, NEVER back off, NEVER
    re-submit. FIX-6: a 401/403 raised as AuthError is never treated as transient."""


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
        if exc.code in (401, 403):
            # PERMANENT auth failure (FIX-6): never transient, never retried.
            body_text = exc.read().decode(errors="replace")
            raise AuthError(
                f"HTTP {exc.code} {method} {url}\n"
                f"Response: {body_text}\n"
                "Permanent auth failure — do NOT re-submit. Check the KIE_API_KEY, "
                "the Authorization: Bearer header format, and that the key is not "
                "locked/rate-blocked by the provider."
            ) from exc
        body_text = exc.read().decode(errors="replace")
        raise RuntimeError(
            f"HTTP {exc.code} {method} {url}\n"
            f"Response: {body_text}\n"
            "If this is a 404 and you see /api/v1/image/gpt-image in the URL above,\n"
            "you have wired the DEAD endpoint. This script only uses /api/v1/jobs/createTask.\n"
            "Check your call site."
        ) from exc


def _expected_ratio_and_minwidth(slide: dict):
    """Return (expected_ratio, min_width) for post-download aspect verification of this
    slide. The ratio is parsed from the slide's declared 'W:H' aspect_ratio (default 16:9).
    The 2K width floor is applied ONLY for the default 16:9 pin; a slide that deliberately
    requests a different ratio (FIX-IMG-03, e.g. 3:4) is shape-checked against that ratio
    without the 16:9-specific 2K floor (min_width=1 = off)."""
    ar = str(slide.get("aspect_ratio", ASPECT_RATIO)).strip()
    try:
        w_s, h_s = ar.split(":")
        ratio = float(w_s) / float(h_s)
    except Exception:  # noqa: BLE001 — malformed ratio falls back to the 16:9 pin
        ratio = 16.0 / 9.0
    is_default_169 = abs(ratio - (16.0 / 9.0)) <= prompt_gate.ASPECT_RATIO_TOLERANCE
    min_width = prompt_gate.MIN_2K_WIDTH if is_default_169 else 1
    return ratio, min_width


def _submit_slide(slide: dict, api_key: str) -> str:
    """Submit one slide to createTask; return taskId."""
    mode = slide.get("mode", "i2i").lower()
    _model_t2i, _model_i2i = _image_models()  # catalog-live, per submit
    if mode == "i2i":
        model = _model_i2i
    elif mode == "t2i":
        model = _model_t2i
    else:
        raise ValueError(f"Slide {slide['slide']}: unknown mode '{mode}'. Use 'i2i' or 't2i'.")

    # SHARED PROMPT GATE (prompt_gate.py). This helper is REUSED by non-presentations
    # skills (06 GHL, 49 funnel, and others), so the FULL presentations rich gate
    # (9,000–18,000-char floor + structural / 8-class negative / spelling-lock / density /
    # demographic teeth + English pin + gpt-image-2.5 mode-pin) is OPT-IN via
    # KIE_PROMPT_GATE=presentations. Every caller ALWAYS gets the universal-safe floor
    # (dead-endpoint + empty-prompt refusal) so no path submits a literally-empty prompt.
    raw_prompt = slide["prompt"]
    if prompt_gate is None:
        # Shared prompt_gate module unavailable (not-yet-deployed / partial update).
        if _presentations_gate_requested():
            raise RuntimeError(
                f"Slide {slide['slide']}: KIE_PROMPT_GATE=presentations is set but the shared "
                "prompt_gate.py was not found beside kie_generate.py — refusing to submit "
                "ungated presentation prompts to the paid kie.ai API.")
        # Inline universal-safe check for shared callers (degraded, module absent).
        if DEAD_ENDPOINT_FRAGMENT in raw_prompt:
            raise ValueError(f"Slide {slide['slide']}: dead endpoint fragment in prompt — refusing.")
        if not raw_prompt.strip():
            raise ValueError(f"Slide {slide['slide']}: empty / whitespace-only prompt — refusing.")
        _pres_gate = False
    else:
        _pres_gate = prompt_gate.presentations_gate_enabled()
        if _pres_gate:
            prompt_gate.verify_prompt(raw_prompt, copy_val=slide.get("copy"),
                                      slide_id=slide.get("slide"))
        else:
            prompt_gate.verify_prompt_minimal(raw_prompt, slide_id=slide.get("slide"))

    urls = slide.get("input_urls", []) if mode == "i2i" else []
    if _pres_gate:
        # Mode consistency (transport-layer kill for the invented-logo defect): references
        # present => model MUST be gpt-image-2-5-sunburst-image-to-image; a logo-bearing slide with
        # empty input_urls hard-fails. Presentations-only (other skills use other models).
        prompt_gate.check_mode_consistency(model, urls,
                                           logo_bearing=bool(slide.get("logo_bearing")),
                                           slide_id=slide.get("slide"))
    if mode == "i2i" and not urls:
        raise ValueError(
            f"Slide {slide['slide']}: mode=i2i requires at least one input_urls entry "
            "(first entry must be the logo URL). If there truly is no logo, set mode=t2i."
        )

    # Make the English/Latin anti-garble pin REAL: append it if the author omitted it
    # (belt-and-braces). Presentations-only — other skills may legitimately render
    # non-Latin text, so the pin is scoped to the presentations gate.
    prompt = prompt_gate.ensure_english_pin(raw_prompt) if _pres_gate else raw_prompt

    # FIX-IMG-03: honor an OPTIONAL per-entry aspect_ratio / resolution when the
    # prompts.json entry carries one, else fall back to the module defaults. This
    # is purely additive — a slide without these keys renders exactly as before
    # (16:9 / 2K). It lets the Skill 6 rail respect a section's mandated ratio
    # (e.g. 49 Section 12 -> 3:4) instead of silently forcing 16:9.
    input_block: dict = {
        "prompt": prompt,
        "aspect_ratio": slide.get("aspect_ratio", ASPECT_RATIO),
        "resolution": slide.get("resolution", RESOLUTION),
    }

    if mode == "i2i":
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


def _download(url: str, dest: Path, api_key: str) -> None:
    """
    Download the KIE result image URL to dest path.
    AUTHENTICATED GET, identical to build_deck.download_image (FIX-4): the result URL
    needs `Authorization: Bearer <key>` plus a browser User-Agent; a plain GET with
    neither returned HTTP 403 in the live run (see tests/test_fix4_authenticated_download.py
    in the role-library presentations scripts, and test_kie_generate_authenticated_download.py
    beside this file). Only http(s) URLs are opened (SSRF / local-file-read guard).
    """
    scheme = (urllib.parse.urlparse(str(url)).scheme or "").lower()
    if scheme not in ("http", "https"):
        raise ValueError(
            f"REFUSED: KIE result URL {url!r} has scheme {scheme!r}; only http(s) may be opened.")
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {api_key}",
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
    })
    try:
        with urllib.request.urlopen(req, timeout=180) as resp, open(dest, "wb") as f:
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
            except AuthError as exc:
                # FIX-6 — fail-fast on auth errors: a 401/403 is PERMANENT, so EVERY
                # remaining slide would fail identically. Abort the run now (one clear
                # diagnosis) instead of burning the whole wave budget on guaranteed
                # failures. No backoff, no re-submit.
                print(f"FATAL: {exc}", file=sys.stderr)
                print("A 401/403 is a permanent auth failure — no slide can submit. "
                      "Fix the KIE_API_KEY / Authorization header, do NOT retry.",
                      file=sys.stderr)
                sys.exit(2)
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
            _download(result_url, out_path, api_key)

            # Verify the file is a real PNG (check magic bytes)
            with open(out_path, "rb") as f:
                magic = f.read(8)
            if magic[:4] != b"\x89PNG":
                raise RuntimeError(
                    f"Downloaded file does not appear to be a PNG "
                    f"(magic bytes: {magic[:8].hex()}). "
                    f"Check KIE resultUrls[0] is a direct image URL."
                )

            # POST-DOWNLOAD ASPECT/2K + OCR verification (prompt_gate) — PRESENTATIONS-ONLY
            # (opt-in via KIE_PROMPT_GATE=presentations). Skipped for shared callers (GHL,
            # funnel, etc.) whose renders are not English-only 16:9 2K, so their behavior is
            # unchanged. When enabled: a non-16:9 / sub-2K response, or rendered text that
            # does not match the approved copy, fails the slide instead of shipping distorted
            # or garbled.
            extra = ""
            if prompt_gate is not None and prompt_gate.presentations_gate_enabled():
                exp_ratio, min_w = _expected_ratio_and_minwidth(slide)
                dims = prompt_gate.verify_aspect_ratio(
                    out_path, expected_ratio=exp_ratio, min_width=min_w, slide_id=slide_name)
                readback = prompt_gate.ocr_readback(out_path, slide.get("copy"), slide_id=slide_name)
                if readback.get("checked") and readback.get("matched") is False:
                    raise RuntimeError(
                        f"OCR readback: rendered text does not match approved copy "
                        f"(unreadable/garbled: {readback.get('misses')}). Re-render this slide."
                    )
                ocr_note = ("ocr=match" if readback.get("matched")
                            else ("ocr=engine-absent" if not readback.get("available")
                                  else "ocr=recorded"))
                extra = f", {dims['width']}x{dims['height']}, {ocr_note}"

            file_size = out_path.stat().st_size
            print(f"  DOWNLOADED -> {out_path} ({file_size:,} bytes, PNG verified{extra})")
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
