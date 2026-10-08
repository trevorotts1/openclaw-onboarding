#!/usr/bin/env python3
"""weekly_step.py — the Skill 35 weekly drama-song step (Owner D27 / plan 6.15
/ decision 35, 2026-10-07).

What it does once a week:
  1. Reads the client's saved style (look, music, voice, length, CTA text and
     link) from the planner's drama-song style JSON.
  2. Gates on Skill 74 (`74-kie-live-adapter`) ACTIVE mode. Anything else
     writes `drama-song-skipped.json` with a plain-English client-facing
     reason and exits 0 — the weekly run continues without the video, and
     there is never a fallback to a private KIE client.
  3. Calls the Drama Song Ad Factory (Skill 75) for ONE 9:16 ad from the
     Theme of the Week, on the client's own key through Skill 74.
  4. Enforces the planner hard cap (59.0 s for the 60-second option; the
     90-second option must land in 88-95 s) and records which connected
     channels accept that length, so the planner schedule can post it.

KIE path: Skill 74 only. This module resolves Skill 74's mode store (env
`KIE_LIVE_ADAPTER_MODE`, then `$OC_CONFIG/kie-live-adapter-mode.conf`, then
the `shadow` default — the adapter's own precedence) and dispatches to Skill
75. It carries no API host, no key handling and no second KIE client.

stdlib only. Mocked tests: test_weekly_step.py (no network, no paid calls,
no media files).
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

SCHEMA_VERSION = "blackceo.smp-weekly-step/v1"
TOOL_VERSION = "0.1.0"

EXIT = {"ok": 0, "error": 1, "waiting": 2, "rejected": 4}
# Exit map is code-owned, same shape as Skill 75's control entrypoint.

# --- shape and length (plan 6.15, owner D27) -------------------------------

SHAPE = "9:16"
HARD_CAP_S = 59.0                      # planner version must END by 59.0 s
NINETY_WINDOW_S = (88.0, 95.0)         # 90-second option acceptance window
LENGTHS = (60, 90)

DEFAULTS = {
    "look": "Lifelike 3D",
    "music": "Soul Ballad",
    "voice": "All Suno",
    "length": 60,
    "cta_text": "",
    "cta_link": "",
}
#: M8: Docker boxes keep OpenClaw at /data/.openclaw (wire.sh's two-line rule),
#: so the weekly step reads the same style file the setup block and the
#: Saturday prompt write, on both kinds of box.
_OC_ROOT = ("/data/.openclaw" if os.path.isdir("/data/.openclaw")
            else os.path.expanduser("~/.openclaw"))
DEFAULT_STYLE_PATH = os.path.join(
    _OC_ROOT, "workspace", "social-media-planner", "drama-song-style.json"
)

# Connected surface -> route for each weekly option. Source: the shared wave
# interface (SMP-BRIEF) built from plan 6.15's GoHighLevel limit table
# (checked 2026-10-07): YouTube Shorts 60 s, Instagram feed 60 s, Facebook
# Reels 3-90 s, TikTok 3-180 s, Instagram Reels 15 min, LinkedIn 30 min,
# Threads 5 min.
ROUTE = {
    60: (
        "Instagram Reels",
        "Facebook Reels",
        "TikTok",
        "YouTube Shorts",
        "LinkedIn",
        "Instagram feed",
        "Threads",
    ),
    90: (
        "Facebook Reels",
        "Instagram Reels",
        "TikTok",
        "LinkedIn",
        "Threads",
    ),
}

# Channels that never take the ad, with the client-facing reason.
NEVER = {
    "Google Business Profile": (
        "Google Business Profile video limit is not verified in the "
        "GoHighLevel documentation; do not post until a limit is verified"
    ),
}
STORIES_SUFFIX = " Stories"
TEASER_REASON = (
    "Stories carry the 15-second teaser only, never the full weekly ad"
)


# --- envelopes -------------------------------------------------------------

def envelope(command, status, **payload):
    """One JSON shape for every CLI answer (directive 24.4 style)."""
    out = {
        "schema_version": SCHEMA_VERSION,
        "tool_version": TOOL_VERSION,
        "command": command,
        "status": status,
    }
    out.update(payload)
    return out


def exit_code_for(status):
    return {
        "ok": EXIT["ok"],
        "dry-run": EXIT["ok"],
        "skipped": EXIT["ok"],       # skip is a normal weekly outcome
        "error": EXIT["error"],
        "failed": EXIT["rejected"],
        "rejected": EXIT["rejected"],
    }.get(status, EXIT["error"])


def _write_json(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)
    return path


# --- Skill 74 mode gate (active only) -------------------------------------

def resolve_kie_mode(env=None, oc_config=None):
    """Skill 74's own precedence: env, then the mode conf, then `shadow`.

    Read-only: this never writes the adapter's mode store.
    """
    env = dict(os.environ if env is None else env)
    mode = (env.get("KIE_LIVE_ADAPTER_MODE") or "").strip().lower()
    if not mode:
        home = env.get("HOME") or os.path.expanduser("~")
        oc = oc_config or env.get("OC_CONFIG") or os.path.join(home, ".openclaw")
        if str(oc).endswith(".json"):
            oc = os.path.dirname(str(oc))
        try:
            with open(os.path.join(str(oc), "kie-live-adapter-mode.conf"),
                      encoding="utf-8") as fh:
                mode = fh.readline().strip().lower()
        except OSError:
            mode = ""
    mode = mode or "shadow"
    if mode not in ("off", "shadow", "active"):
        mode = "shadow"
    return mode


def kie_is_active(env=None, oc_config=None):
    """True only when Skill 74 reports `active`."""
    return resolve_kie_mode(env=env, oc_config=oc_config) == "active"


def client_skip_reason(mode=None, turned_off=False):
    """Plain-English reason for the client. No provider names, no fallback."""
    if turned_off:
        return (
            "This week's drama song video was skipped because the weekly "
            "drama song is switched off in your planner setup. Turn it on to "
            "get next week's video. Every other scheduled post still "
            "publishes."
        )
    return (
        "This week's drama song video was skipped because your KIE "
        "connection is switched off or in observation mode, so no video was "
        "made this week. Switch the KIE connection on to get the weekly "
        "drama song. Every other scheduled post still publishes."
    )


# --- style + brief ---------------------------------------------------------

def load_style(path=None, env=None):
    """Client's saved style with the plan 6.15 defaults pre-filled.

    Missing or unreadable file -> the defaults (Lifelike 3D / Soul Ballad /
    All Suno / 60 seconds), never an error: the weekly run must not die on a
    first-run box.
    """
    env = dict(os.environ if env is None else env)
    raw_path = path or env.get("DRAMA_SONG_STYLE_FILE") or DEFAULT_STYLE_PATH
    expanded = os.path.expanduser(str(raw_path))
    data = {}
    try:
        loaded = json.loads(Path(expanded).read_text(encoding="utf-8"))
        if isinstance(loaded, dict):
            data = loaded
    except (OSError, ValueError):
        data = {}

    style = dict(DEFAULTS)
    style["enabled"] = bool(data.get("enabled", True))
    for key in ("look", "music", "voice", "cta_text", "cta_link"):
        if isinstance(data.get(key), str) and data[key].strip():
            style[key] = data[key].strip()
    try:
        length = int(data.get("length", DEFAULTS["length"]))
    except (TypeError, ValueError):
        length = DEFAULTS["length"]
    if length not in LENGTHS:
        length = DEFAULTS["length"]
    style["length"] = length
    return style


def build_brief(theme, style, length=60):
    """The one 9:16 weekly ad brief handed to Skill 75 (its intake is
    permissive: provided / extracted / inherited / assumed per field)."""
    return {
        "schema_version": "blackceo.campaign/v1",
        "source": "35-social-media-planner/weekly-step",
        "title": "Drama song of the week: %s" % (theme or "").strip(),
        "theme": (theme or "").strip(),
        "shape": SHAPE,
        "length_option": int(length),
        "look": style["look"],
        "music": style["music"],
        "voice": style["voice"],
        "cta_text": style.get("cta_text", ""),
        "cta_link": style.get("cta_link", ""),
        "weekly": True,
        "one_per_week": True,
    }


# --- length + channel acceptance ------------------------------------------

def validate_duration(duration_s, length=60):
    """(ok, reason) against the plan 6.15 caps. None -> cannot pass."""
    if duration_s is None:
        return False, "no duration reported for this week's video"
    try:
        dur = float(duration_s)
    except (TypeError, ValueError):
        return False, "duration is not a number: %r" % (duration_s,)
    if int(length) == 90:
        low, high = NINETY_WINDOW_S
        if dur < low or dur > high:
            return False, (
                "90-second option must run %.1f to %.1f seconds, got %.1f"
                % (low, high, dur)
            )
        return True, ""
    if dur > HARD_CAP_S:
        return False, (
            "planner version must end by %.1f seconds (GoHighLevel limits "
            "YouTube Shorts and Instagram feed to 60 seconds); got %.1f — "
            "trim or fail" % (HARD_CAP_S, dur)
        )
    return True, ""


def _external_router():
    """Sibling unit `core/smp/length_routing` is the authority when present;
    the baseline ROUTE table below stays as the standalone fallback."""
    import importlib.util

    smp_dir = Path(__file__).resolve().parents[1]
    for cand in (
        smp_dir / "length_routing" / "length_routing.py",
        smp_dir / "length_routing" / "routing.py",
        smp_dir / "length_routing" / "__init__.py",
    ):
        if not cand.is_file():
            continue
        try:
            spec = importlib.util.spec_from_file_location("smp_length_routing", cand)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
        except Exception:
            return None
        for name in ("channel_acceptance", "route_channels", "route"):
            fn = getattr(mod, name, None)
            if callable(fn):
                return fn
        return None
    return None


def channel_acceptance(length, connected, router=None):
    """Every connected channel, allowed or not, each with a reason.

    `router` (injectable; defaults to core/smp/length_routing when it exists)
    wins so the wave's two units cannot ship two contradicting tables.
    """
    connected = list(connected)
    if router is None:
        router = _external_router()
    if router is not None:
        try:
            out = router(int(length), connected)
        except Exception:
            out = None
        if isinstance(out, list) and out:
            return out

    length = int(length)
    allowed_for = ROUTE.get(length, ())
    plan = []
    for channel in connected:
        name = str(channel).strip()
        if not name:
            continue
        if name in NEVER:
            plan.append({"channel": name, "allowed": False, "reason": NEVER[name]})
            continue
        if name.endswith(STORIES_SUFFIX):
            plan.append({"channel": name, "allowed": False, "reason": TEASER_REASON})
            continue
        if name in allowed_for:
            plan.append({
                "channel": name,
                "allowed": True,
                "reason": "%s-second weekly drama song accepted by %s"
                          % (length, name),
            })
            continue
        if name in ("YouTube Shorts", "Instagram feed"):
            why = ("%s accepts 60 seconds or less, so the %s-second version "
                   "cannot post there" % (name, length))
        else:
            why = "%s is not in the %s-second weekly route" % (name, length)
        plan.append({"channel": name, "allowed": False, "reason": why})
    return plan


# --- Skill 75 dispatch (Skill 74 is the only KIE path) ---------------------

def factory_argv(entry, brief_path, python=None):
    """Skill 75's control entrypoint, intake stage. Nothing KIE-shaped here:
    Skill 75 reaches KIE through Skill 74 on the client's own key."""
    return [
        python or sys.executable,
        str(entry),
        "intake",
        "--brief-file",
        str(brief_path),
    ]


def _subprocess_runner(cmd):
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=1800, check=False
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return 127, "", str(exc)
    return proc.returncode, proc.stdout or "", proc.stderr or ""


def run_factory(entry, brief_path, runner=None):
    """Dispatch one ad build to Skill 75. `runner(cmd) -> (rc, out, err)` is
    injectable so tests never touch a provider."""
    cmd = factory_argv(entry, brief_path)
    runner = runner or _subprocess_runner
    rc, out, err = runner(cmd)
    parsed = None
    text = (out or "").strip()
    if text:
        try:
            loaded = json.loads(text.splitlines()[-1])
            if isinstance(loaded, dict):
                parsed = loaded
        except ValueError:
            parsed = None
    return {"argv": cmd, "returncode": rc, "stdout": out, "stderr": err,
            "envelope": parsed}


# --- the weekly step -------------------------------------------------------

def run_weekly(theme, style_file=None, out_dir=None, length=None, dry_run=False,
               connected=None, factory_entry=None, env=None, runner=None,
               oc_config=None):
    """Run one week. Returns the result/skip envelope (never raises for a
    normal weekly outcome; the skip path is a success)."""
    env = dict(os.environ if env is None else env)
    if not out_dir:
        return envelope("weekly", "error",
                        error="out_dir is required"), None
    out_path = Path(os.path.expanduser(str(out_dir)))
    out_path.mkdir(parents=True, exist_ok=True)

    # Argument validation runs before the mode gate: a bad length is a bad
    # length whatever KIE says.
    if length is not None:
        try:
            length = int(length)
        except (TypeError, ValueError):
            return envelope("weekly", "rejected",
                            error="--length must be 60 or 90"), None
        if length not in LENGTHS:
            return envelope("weekly", "rejected",
                            error="--length must be 60 or 90"), None

    mode = resolve_kie_mode(env=env, oc_config=oc_config)
    style = load_style(path=style_file, env=env)

    if not kie_is_active(env=env, oc_config=oc_config):
        skip = envelope(
            "weekly",
            "skipped",
            reason=client_skip_reason(mode),
            kie_mode=mode,
            video=None,
            week=out_path.name,
        )
        _write_json(out_path / "drama-song-skipped.json", skip)
        return skip, None

    if not style.get("enabled", True):
        skip = envelope(
            "weekly",
            "skipped",
            reason=client_skip_reason(turned_off=True),
            kie_mode=mode,
            video=None,
            week=out_path.name,
        )
        _write_json(out_path / "drama-song-skipped.json", skip)
        return skip, None

    if length is None:
        length = style.get("length", 60)
    try:
        length = int(length)
    except (TypeError, ValueError):
        return envelope("weekly", "rejected",
                        error="--length must be 60 or 90"), None
    if length not in LENGTHS:
        return envelope("weekly", "rejected",
                        error="--length must be 60 or 90"), None

    if connected is None:
        connected = list(ROUTE[60])
    channels = channel_acceptance(length, connected)
    brief = build_brief(theme, style, length=length)

    if dry_run:
        result = envelope(
            "weekly",
            "dry-run",
            note="no factory dispatch: Skill 74 active and --dry-run set",
            kie_mode=mode,
            brief=brief,
            hard_cap_s=HARD_CAP_S,
            duration_s=None,
            video_path=None,
            stories_teaser_path=None,
            cost_cents=None,
            channels=channels,
            style={k: style[k] for k in
                   ("look", "music", "voice", "length", "cta_text", "cta_link")},
        )
        _write_json(out_path / "drama-song-result.json", result)
        return result, None

    entry = factory_entry or env.get("DRAMA_SONG_FACTORY_ENTRY")
    if not entry:
        err = envelope("weekly", "error",
                       error="Skill 75 entry not found: pass --factory-entry "
                             "or set DRAMA_SONG_FACTORY_ENTRY")
        _write_json(out_path / "drama-song-result.json", err)
        return err, None
    entry_path = Path(os.path.expanduser(str(entry)))
    if not entry_path.is_file():
        err = envelope("weekly", "error",
                       error="Skill 75 control entrypoint not found: %s"
                             % entry_path.name)
        _write_json(out_path / "drama-song-result.json", err)
        return err, None

    brief_path = _write_json(out_path / "drama-song-brief.json", brief)
    call = run_factory(entry_path, brief_path, runner=runner)
    factory_out = call.get("envelope") or {}
    if call["returncode"] != 0 and not factory_out:
        err = envelope("weekly", "error",
                       error="Skill 75 intake failed (exit %s)"
                             % call["returncode"],
                       stderr=(call.get("stderr") or "")[-500:])
        _write_json(out_path / "drama-song-result.json", err)
        return err, None

    duration = factory_out.get("duration_s")
    ok_duration, duration_reason = validate_duration(duration, length) if duration is not None else (True, "")
    status = "ok"
    reason = ""
    if duration is not None and not ok_duration:
        status, reason = "failed", duration_reason

    result = envelope(
        "weekly",
        status,
        reason=reason,
        kie_mode=mode,
        brief=brief,
        hard_cap_s=HARD_CAP_S,
        duration_s=duration,
        video_path=factory_out.get("video_path"),
        stories_teaser_path=factory_out.get("stories_teaser_path"),
        cost_cents=factory_out.get("cost_cents"),
        channels=channels,
        factory_status=factory_out.get("status"),
        style={k: style[k] for k in
               ("look", "music", "voice", "length", "cta_text", "cta_link")},
    )
    _write_json(out_path / "drama-song-result.json", result)
    return result, None


# --- CLI -------------------------------------------------------------------

def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="weekly_step.py",
        description="Skill 35 weekly drama-song step (plan 6.15 / D27): one "
                    "9:16 ad per week through Skill 75, Skill 74 active only.",
    )
    ap.add_argument("--theme", required=True, help="this week's Theme of the Week")
    ap.add_argument("--style-file", default=None,
                    help="client drama-song style JSON (default: the planner path)")
    ap.add_argument("--out-dir", required=True, help="this week's output directory")
    ap.add_argument("--length", type=int, default=None,
                    help="60 (hard cap %.1f s) or 90 (88-95 s); anything "
                         "else is rejected" % HARD_CAP_S)
    ap.add_argument("--dry-run", action="store_true",
                    help="build the plan and write the result, never dispatch")
    ap.add_argument("--connected", default=None,
                    help="comma-separated connected planner channels")
    ap.add_argument("--factory-entry", default=None,
                    help="Skill 75 factory.py path (or DRAMA_SONG_FACTORY_ENTRY)")
    args = ap.parse_args(argv)

    connected = None
    if args.connected is not None:
        connected = [c.strip() for c in args.connected.split(",") if c.strip()]

    result, _ = run_weekly(
        theme=args.theme,
        style_file=args.style_file,
        out_dir=args.out_dir,
        length=args.length,
        dry_run=args.dry_run,
        connected=connected,
        factory_entry=args.factory_entry,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return exit_code_for(result.get("status", "error"))


if __name__ == "__main__":
    sys.exit(main())
