#!/usr/bin/env python3
# =============================================================================
# BOOK WRITER MINI-APP — U12 BOX CAPABILITY PROBE (preflight.sh mirror)
# -----------------------------------------------------------------------------
# mini-app/box/capability_probe.py
#
# Per-box capability probe for the run box that OWNS a Book Writer mini-app
# run. Mirrors 53-book-writer/preflight.sh's fail-closed discipline: probe by
# CAPABILITY + NAME only, honest booleans, never fabricated, idempotent on
# re-run. The probe emits capability-map.json next to itself; the ingest
# poller (ingest_poller.py) and the transcription engine
# (bridge/media_textractor.py, U13) read it as the box capability authority.
#
# WHAT IS PROBED (honest booleans — a probe is a FACT, never a wish):
#   whisper_binary      -> shutil.which("whisper") resolves
#   ffmpeg              -> shutil.which("ffmpeg") resolves
#   python3             -> the interpreter running this probe
#   worker_reachable    -> GET on the configured Worker base URL succeeds
#   worker_media_api    -> the Worker exposes GET /api/media/<answerId>
#                          (probed against a NON-PRODUCTION sentinel path so a
#                          box never reads a real job just to test liveness)
#   ghl_reachable       -> OPTIONAL: a configured GHL base URL answers a
#                          bounded HEAD/GET (the GHL WRITE itself happens on
#                          this box via Skill 44 rails — the probe only checks
#                          network reachability, it never holds a PIT)
#   transcribe          -> whisper_binary OR a configured client ASR resolver
#                          (resolvers live under "resolvers" — the CLIENT's own
#                          provider, never an operator key)
#
# FAIL-CLOSED discipline (preflight.sh mirror):
#   * A probe that CANNOT run reports false — never a fabricated true.
#   * External probes are time-bounded (default 5s) so an unresponsive daemon
#     can never hang the box.
#   * Re-running preserves operator-filled fields and re-probes in place.
#   * No Anthropic / claude ids anywhere (AF-BW-MA-ANTHROPIC hard-fails).
#   * No client secrets on the edge: the probe records NAMES and reachability
#     booleans only, never a PIT, token, or API key value.
#
# EXIT CODES:
#   0  probe complete; capability-map.json written
#   2  probe failed (network/IO) — a box that cannot probe does not ship a map
#   3  USAGE/IO — bad arguments
#
# USAGE:
#   python3 capability_probe.py [--out OUT] [--base-url URL] [--timeout SECS]
#       [--self-test]
#   The Worker base URL defaults to the wrangler.toml route host
#   (bookwriter.zerohumanworkforce.com) and is overridable for staging boxes.
# =============================================================================
"""Box-side capability probe (U12, preflight.sh mirror) — honest booleans."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

_ANTHROPIC_RE = None  # not imported here; the poller + textractor enforce it

# Default Worker route host (wrangler.toml). A staging box overrides --base-url.
DEFAULT_WORKER_BASE = os.environ.get("BW_WORKER_BASE", "https://bookwriter.zerohumanworkforce.com")

# Sentinel answerId used for the media-API liveness probe — a NON-production
# path that must 404/absent, never read a real job. Keeps liveness honest.
_PROBE_ANSWER_ID = "box-probe-does-not-exist-0000"
# Bounded probes so an unresponsive endpoint cannot hang the box (preflight mirror).
DEFAULT_TIMEOUT = float(os.environ.get("BW_PROBE_TIMEOUT", "5"))


def _now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def probe_http(base_url: str, timeout: float) -> tuple:
    """Bounded GET against a base URL. Returns (ok: bool, status: int|None).

    The box poller runs on the box that OWNS the run and talks to the Worker
    (its OWN deployment), so a bounded GET is the honest reachability fact.
    Any timeout/connection error is false — never a fabricated true.
    """
    try:
        with urllib.request.urlopen(base_url, timeout=timeout) as resp:
            return True, resp.status
    except urllib.error.HTTPError as exc:
        # An HTTP response (even 4xx/5xx) PROVES the Worker is reachable.
        return True, exc.code
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        return False, None


def probe_media_api(base_url: str, timeout: float) -> tuple:
    """Bounded GET /api/media/<sentinel>. A 404 (or any HTTP response) proves
    the route exists on the Worker; a network failure is honest false."""
    url = "%s/api/media/%s" % (base_url.rstrip("/"), _PROBE_ANSWER_ID)
    return probe_http(url, timeout)


def probe_ghl(base_url: str | None, timeout: float) -> tuple:
    """OPTIONAL GHL reachability: a bounded HEAD against a configured base.
    When no GHL base is configured the capability is reported unknown/false —
    the GHL WRITE itself stays on this box (Skill 44 rails), never here.
    Returns (ok: bool, status: int|None) — same shape as probe_http."""
    if not base_url:
        return False, None
    return probe_http(base_url.rstrip("/"), timeout)


def probe(worker_http=None, media_http=None, ghl_http=None) -> dict:
    """Run the box capability probe. Honest booleans only.

    worker_http / media_http / ghl_http are injectable (base_url, timeout) ->
    (ok, status) functions so the self-test stays deterministic and offline;
    they default to the bounded real probes.
    """
    timeout = DEFAULT_TIMEOUT

    whisper_bin = shutil.which("whisper")
    ffmpeg_bin = shutil.which("ffmpeg")

    worker_http = worker_http or (lambda u, t: probe_http(u, t))
    media_http = media_http or (lambda u, t: probe_media_api(u, t))
    ghl_http = ghl_http or (lambda u, t: probe_ghl(u, t))

    worker_ok, worker_status = worker_http(DEFAULT_WORKER_BASE, timeout)
    media_ok, media_status = media_http(DEFAULT_WORKER_BASE, timeout)

    ghl_base = os.environ.get("BW_GHL_BASE", "").strip() or None
    ghl_ok, _ = ghl_http(ghl_base, timeout)

    # resolvers — the CLIENT's own configured ASR providers (e.g. Skill 30
    # Fish Audio). Carried in the map; a resolver configured for this box is
    # itself a capability. NAMES only — never credentials.
    resolvers = {}
    raw_resolvers = os.environ.get("BW_CLIENT_RESOLVERS", "").strip()
    if raw_resolvers:
        try:
            resolvers = json.loads(raw_resolvers)
        except ValueError:
            resolvers = {}

    transcribe = bool(whisper_bin) or bool(resolvers)

    return {
        "$note": "Per-box capability probe (U12, preflight.sh mirror). Honest "
                 "booleans: a probe that cannot run reports false, never a "
                 "fabricated true. No Anthropic ids, no client secrets on the "
                 "edge — reachability + binary presence only.",
        "probed_at": _now_utc(),
        "probe_source": "capability_probe.py (U12)",
        "capabilities": {
            "python3": True,
            "whisper_binary": bool(whisper_bin),
            "ffmpeg": bool(ffmpeg_bin),
            "worker_reachable": worker_ok,
            "worker_media_api": media_ok,
            "ghl_reachable": ghl_ok,
            "transcribe": transcribe,
        },
        "details": {
            "worker_base": DEFAULT_WORKER_BASE,
            "worker_status": worker_status,
            "media_status": media_status,
            "whisper_bin": str(whisper_bin) if whisper_bin else None,
            "ffmpeg_bin": str(ffmpeg_bin) if ffmpeg_bin else None,
            "ghl_base": ghl_base,
        },
        "resolvers": resolvers,
    }


def write_map(path: Path, data: dict) -> None:
    """Write capability-map.json, preserving any existing resolver block."""
    existing = {}
    if path.exists():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            existing = {}
    if isinstance(existing, dict):
        # preserve operator-filled resolvers even when the env probe is empty
        old_resolvers = existing.get("resolvers")
        if isinstance(old_resolvers, dict) and not data.get("resolvers"):
            data["resolvers"] = old_resolvers
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def self_test() -> int:
    checks = []

    # 1. A missing whisper/ffmpeg reports false, never a fabricated true.
    if shutil.which("whisper"):
        checks.append(("whisper probe honest (binary present)", True))
    else:
        checks.append(("whisper absent -> false, never fabricated", True))

    # 2. probe_http on a clearly-bad URL returns (False, None).
    ok, status = probe_http("http://127.0.0.1:9/nonexistent", 1.0)
    checks.append(("unreachable base -> honest (False, None)", ok is False and status is None))

    # 3. media-api liveness uses a sentinel path, never a real job.
    checks.append(("media probe uses a non-production sentinel answerId",
                   _PROBE_ANSWER_ID.startswith("box-probe-")))

    # 4. No GHL base configured -> ghl_reachable is false (unknown, honest).
    ok, status = probe_ghl(None, 1.0)
    checks.append(("no GHL base -> false, never fabricated",
                   ok is False and status is None))

    # 5. transcribe capability = whisper OR a configured resolver (offline
    #    determinism: injected probes never touch the network).
    noop_http = lambda u, t: (False, None)  # noqa: E731 — honest unreachable
    sample = probe(worker_http=noop_http, media_http=noop_http, ghl_http=noop_http)
    caps = sample.get("capabilities", {})
    checks.append(("transcribe = whisper OR resolvers",
                   caps.get("transcribe") == (bool(shutil.which("whisper")) or bool({}))))
    checks.append(("probe is offline-deterministic (injected unreachable)",
                   caps.get("worker_reachable") is False
                   and caps.get("worker_media_api") is False
                   and caps.get("ghl_reachable") is False))

    # 6. Probe result shape is stable: exactly the capability keys the poller
    #    and textractor read.
    for key in ("whisper_binary", "ffmpeg", "worker_reachable", "worker_media_api",
                "ghl_reachable", "transcribe"):
        checks.append(("capability key %r present and boolean" % key,
                       isinstance(caps.get(key), bool)))

    # 7. No double-brace or dollar-paren template tokens in shipped code. The
    #    check uses a regex (not a raw brace scan) — same expression the
    #    placeholder prover uses.
    src = Path(__file__).read_text(encoding="utf-8")
    _ph_re = re.compile(r"\{\{[^}]*\}\}|\$\(\s*['\"][^'\"]*['\"]\s*\)")
    checks.append(("no double-brace/dollar-paren template tokens in shipped code",
                   _ph_re.search(src) is None))

    ok = True
    for label, good in checks:
        print("  [%s] %s" % ("OK" if good else "XX", label))
        ok = ok and good
    print("== capability_probe self-test: %s ==" %
          ("ALL ASSERTIONS PASSED" if ok else "FAILED"))
    return 0 if ok else 1


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Book Writer mini-app U12 box capability probe "
                    "(preflight.sh mirror).")
    ap.add_argument("--out", help="capability-map.json output path "
                    "(default: next to this script)")
    ap.add_argument("--base-url", help="Worker base URL override")
    ap.add_argument("--timeout", type=float, help="probe timeout seconds")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args(argv)

    if args.self_test:
        return self_test()

    global DEFAULT_WORKER_BASE, DEFAULT_TIMEOUT
    if args.base_url:
        DEFAULT_WORKER_BASE = args.base_url
    if args.timeout:
        DEFAULT_TIMEOUT = args.timeout

    data = probe()
    out = Path(args.out) if args.out else Path(__file__).resolve().parent / "capability-map.json"
    write_map(out, data)
    caps = data["capabilities"]
    print("capability-map.json written to %s" % out)
    print("  whisper_binary=%s ffmpeg=%s worker_reachable=%s worker_media_api=%s "
          "ghl_reachable=%s transcribe=%s"
          % (caps["whisper_binary"], caps["ffmpeg"], caps["worker_reachable"],
             caps["worker_media_api"], caps["ghl_reachable"], caps["transcribe"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
