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
  4. Reports the factory's outcome honestly. The factory prints an indented,
     multi-line JSON envelope, so the WHOLE stdout is parsed — never the last
     line alone. `waiting` becomes weekly status `waiting` with the factory's
     questions; nothing other than `ok` is ever reported as `ok`. `ok` is
     reported only when `video_path` is set and that file actually exists;
     anything else is `pending-production` and the brief is handed to the
     video department through the same path a direct request takes (B1).
  5. Enforces the planner hard cap (59.0 s for the 60-second option; the
     90-second option must land in 88-95 s) and records which connected
     channels accept that length, so the planner schedule can post it.

KIE path: Skill 74 only. This module resolves Skill 74's mode store (env
`KIE_LIVE_ADAPTER_MODE`, then `$OC_CONFIG/kie-live-adapter-mode.conf`, then
the `shadow` default — the adapter's own precedence) and dispatches to Skill
75. It carries no API host, no key handling and no second KIE client.

Channel routing: `core/smp/length_routing` is the single authority and ships
alongside this unit. There is no local fallback route table here (manual L2).
Same for the duration gate and the connected-channel default list.

stdlib only. Mocked tests: test_weekly_step.py (no network, no paid calls,
no media files).
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

SCHEMA_VERSION = "blackceo.smp-weekly-step/v1"
TOOL_VERSION = "0.1.1"

EXIT = {"ok": 0, "error": 1, "waiting": 2, "rejected": 4, "pending-production": 2}
# Exit map is code-owned, same shape as Skill 75's control entrypoint.
# `pending-production` shares exit 2 (waiting): the video is not made yet, and
# the planner must ask again rather than treat the week as failed.

# --- shape and length (plan 6.15, owner D27) --------------------------------

SHAPE = "9:16"
LENGTHS = (60, 90)

DEFAULTS = {
    "look": "Lifelike 3D",
    "music": "Soul Ballad",
    "voice": "All Suno",
    "length": 60,
    "cta_text": "",
    "cta_link": "",
    "offer": "",
    "audience": "",
    "action": "",
    "budget_minor": 0,
    "budget_currency": "",
}
DEFAULT_STYLE_PATH = (
    "~/.openclaw/workspace/social-media-planner/drama-song-style.json"
)

# `weekly` is not a factory field: intake never reads it, and the brief that
# reaches Skill 75 must carry the essentials (offer, audience, action,
# budget_minor, budget_currency) so a complete setup never lands in the
# factory's `missing-essentials` waiting loop.
BRIEF_KEYS = ("offer", "audience", "action", "budget_minor", "budget_currency")


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
        "waiting": EXIT["waiting"],
        "pending-production": EXIT["pending-production"],
    }.get(status, EXIT["error"])


def _write_json(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)
    return path


# --- Skill 74 mode gate (active only) ---------------------------------------

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
    first-run box. The weekly offer / audience / action / budget fields come
    from the same record (asked once at setup) and are blank by default so
    the factory asks for them rather than inventing any of them.
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
    for key in ("look", "music", "voice", "cta_text", "cta_link",
                "offer", "audience", "action", "budget_currency"):
        if isinstance(data.get(key), str) and data[key].strip():
            style[key] = data[key].strip()
    for key in ("length", "budget_minor"):
        try:
            value = int(data.get(key, DEFAULTS[key]))
        except (TypeError, ValueError):
            value = DEFAULTS[key]
        if key == "length" and value not in LENGTHS:
            value = DEFAULTS["length"]
        if key == "budget_minor" and value < 0:
            value = 0
        style[key] = value
    return style


def build_brief(theme, style, length=60):
    """The one 9:16 weekly ad brief handed to Skill 75.

    It carries the plan 6.15 style fields plus the essentials the factory's
    intake needs (offer, audience, action and the weekly budget), so a client
    who answered them at setup never lands in `missing-essentials`.
    """
    brief = {
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
        # Shape facts the planner already owns (plan 6.15): carrying them
        # means Skill 75's intake has nothing left to ask a client who
        # answered at setup. target_length_s is the option the planner
        # offers, never a guess.
        "placement": "9:16 vertical",
        "aspect_ratio": SHAPE,
        "target_length_s": int(length),
    }
    for key in BRIEF_KEYS:
        brief[key] = style.get(key, DEFAULTS[key])
    return brief


def hard_cap_s(router=None):
    """The planner hard cap, read from `core/smp/length_routing` (no copy)."""
    mod = router if router is not None else _load_router()
    if mod is None:
        return None
    return getattr(mod, "HARD_CAP_S", None)


# --- length + channel acceptance --------------------------------------------

def _load_router():
    """The sibling `core/smp/length_routing` unit is the single authority.

    It ships alongside this module (manual C4 step 4 / L2): no local route
    table, no local duration table, no silent second opinion. When it cannot
    be loaded the weekly run refuses by name instead of guessing at a table.
    """
    smp_dir = Path(__file__).resolve().parents[1]
    cand = smp_dir / "length_routing" / "length_routing.py"
    if not cand.is_file():
        return None
    try:
        spec = importlib.util.spec_from_file_location("smp_length_routing", cand)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
    except Exception:
        return None
    return mod


def validate_duration(duration_s, length=60, router=None):
    """(ok, reason) against the planner caps. None -> cannot pass.

    `core/smp/length_routing` owns the numbers; this is a thin adapter so the
    weekly step cannot drift from the owner plan.
    """
    mod = router if router is not None else _load_router()
    if mod is None:
        return False, (
            "core/smp/length_routing is missing beside weekly_step: the "
            "planner length rules are not available, so this week's video "
            "cannot be validated. Restore the length_routing unit before "
            "re-running the weekly step"
        )
    fn = mod if callable(mod) else getattr(mod, "validate_duration", None)
    if not callable(fn):
        return False, "core/smp/length_routing exposes no validate_duration"
    try:
        return fn(duration_s, int(length))
    except Exception as exc:
        return False, "length_routing.validate_duration failed: %s" % (exc,)


def channel_acceptance(length, connected, router=None):
    """Every connected channel, allowed or not, each with a reason.

    `core/smp/length_routing` is the only table. There is no fallback copy
    here: a missing or broken router is an error, never a guessed plan.
    """
    mod = router if router is not None else _load_router()
    if mod is None:
        raise RuntimeError(
            "core/smp/length_routing is missing beside weekly_step: the "
            "planner channel route is not available, so this week's channel "
            "plan cannot be built. Restore the length_routing unit before "
            "re-running the weekly step"
        )
    if callable(mod):
        fn = mod
    else:
        fn = (getattr(mod, "channel_acceptance", None)
              or getattr(mod, "route_channels", None)
              or getattr(mod, "route", None))
    if not callable(fn):
        raise RuntimeError(
            "core/smp/length_routing exposes no channel route function")
    try:
        out = fn(int(length), list(connected))
    except Exception as exc:
        raise RuntimeError(
            "core/smp/length_routing route failed: %s" % (exc,)
        )
    if not isinstance(out, list):
        raise RuntimeError(
            "core/smp/length_routing returned no channel plan: %r" % (out,))
    return out


def default_connected():
    """The planner's connected-channel default, straight from length_routing.

    There is no local copy of that list here (manual L2): when the router is
    unavailable the weekly run refuses by name instead of guessing a table.
    """
    mod = _load_router()
    if mod is None:
        raise RuntimeError(
            "core/smp/length_routing is missing beside weekly_step: the "
            "planner channel route is not available, so this week's channel "
            "plan cannot be built. Restore the length_routing unit before "
            "re-running the weekly step"
        )
    fn = getattr(mod, "channels_for_option", None)
    if callable(fn):
        try:
            return list(fn(60))
        except Exception:
            pass
    limits = getattr(mod, "CHANNEL_LIMITS", None)
    if isinstance(limits, dict) and limits:
        return list(limits)
    raise RuntimeError(
        "core/smp/length_routing exposes no channel list: restore the "
        "length_routing unit before re-running the weekly step"
    )


# --- Skill 75 dispatch (Skill 74 is the only KIE path) -----------------------

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
    injectable so tests never touch a provider.

    Skill 75 prints an indented, multi-line JSON envelope, so the WHOLE
    stdout is parsed. The old last-line parse always failed on that shape and
    reported "Skill 75 intake failed (exit 2)" for every waiting run.
    """
    cmd = factory_argv(entry, brief_path)
    runner = runner or _subprocess_runner
    rc, out, err = runner(cmd)
    parsed = None
    text = (out or "").strip()
    if text:
        try:
            loaded = json.loads(text)
            if isinstance(loaded, dict):
                parsed = loaded
        except ValueError:
            parsed = None
    return {"argv": cmd, "returncode": rc, "stdout": out, "stderr": err,
            "envelope": parsed}


def _dispatch_hook(hook, payload):
    """Run the B1 stage-runner hand-off without ever failing the weekly week.

    `DRAMA_SONG_STAGE_HOOK` names a script that accepts the JSON payload on
    stdin and hands the brief to the video department (the same path a direct
    request takes). Nothing is wired until B1 ships, so the hook is optional
    by construction and a failure here is reported, never swallowed into an
    `ok`.
    """
    if not hook:
        return None
    path = Path(os.path.expanduser(str(hook)))
    if not path.is_file():
        return {"attempted": False,
                "reason": "stage hook not found: %s" % path.name}
    cmd = [sys.executable, str(path)]
    try:
        proc = subprocess.run(
            cmd, input=json.dumps(payload), capture_output=True,
            text=True, timeout=300, check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return {"attempted": True, "ok": False, "error": str(exc)[:200]}
    return {
        "attempted": True,
        "ok": proc.returncode == 0,
        "returncode": proc.returncode,
        "stderr": (proc.stderr or "")[-300:],
    }


# --- the weekly step --------------------------------------------------------

def run_weekly(theme, style_file=None, out_dir=None, length=None, dry_run=False,
               connected=None, factory_entry=None, env=None, runner=None,
               oc_config=None, stage_hook=None):
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
        connected = default_connected()
    try:
        channels = channel_acceptance(length, connected)
    except RuntimeError as exc:
        err = envelope("weekly", "error", error=str(exc))
        _write_json(out_path / "drama-song-result.json", err)
        return err, None
    brief = build_brief(theme, style, length=length)

    if dry_run:
        result = envelope(
            "weekly",
            "dry-run",
            note="no factory dispatch: Skill 74 active and --dry-run set",
            kie_mode=mode,
            brief=brief,
            hard_cap_s=hard_cap_s(),
            duration_s=None,
            video_path=None,
            stories_teaser_path=None,
            cost_cents=None,
            channels=channels,
            style={k: style[k] for k in
                   ("look", "music", "voice", "length", "cta_text", "cta_link",
                    "offer", "audience", "action", "budget_minor",
                    "budget_currency")},
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
    if not factory_out:
        # No parseable envelope at all. Never reported as `ok`.
        err = envelope(
            "weekly", "error",
            error="Skill 75 printed no readable envelope (exit %s)"
                  % call["returncode"],
            factory_returncode=call["returncode"],
            factory_outcome=None,
            factory_reason_code=None,
            questions=None,
            question_message=None,
            stderr=(call.get("stderr") or "")[-500:],
        )
        _write_json(out_path / "drama-song-result.json", err)
        return err, None

    # (2) map the factory's outcome straight through. Skill 75's envelope
    # carries `outcome` (ok / waiting / parked / rejected / error) and
    # `reason_code`. `waiting` becomes the weekly `waiting` with the
    # questions; anything other than `ok` is never reported as `ok`.
    factory_status = factory_out.get("outcome") or factory_out.get("status")
    factory_reason = factory_out.get("reason_code")
    data = factory_out.get("data") or {}
    questions = data.get("questions") if isinstance(data, dict) else None
    question_message = (data.get("question_message")
                        if isinstance(data, dict) else None)
    if questions is None:
        questions = factory_out.get("questions")
    if question_message is None:
        question_message = factory_out.get("question_message")

    video_path = factory_out.get("video_path")
    stories_teaser_path = factory_out.get("stories_teaser_path")
    duration = factory_out.get("duration_s")

    def _common(**extra):
        payload = dict(
            kie_mode=mode,
            brief=brief,
            hard_cap_s=hard_cap_s(),
            duration_s=duration,
            video_path=video_path,
            stories_teaser_path=stories_teaser_path,
            cost_cents=factory_out.get("cost_cents"),
            channels=channels,
            factory_status=factory_status,
            factory_reason_code=factory_reason,
            style={k: style[k] for k in
                   ("look", "music", "voice", "length", "cta_text", "cta_link",
                    "offer", "audience", "action", "budget_minor",
                    "budget_currency")},
        )
        payload.update(extra)
        return payload

    if factory_status == "waiting":
        result = envelope(
            "weekly", "waiting",
            reason=(
                "the factory is waiting on the client's answers: %s"
                % (question_message or factory_reason or "questions outstanding")
            ),
            reason_code=factory_reason,
            questions=questions,
            question_message=question_message,
            **_common(),
        )
        _write_json(out_path / "drama-song-result.json", result)
        return result, None

    if factory_status != "ok":
        # `parked`, `rejected`, `failed`, `error` or anything else: never ok.
        failed = factory_status in ("failed", "rejected")
        result = envelope(
            "weekly",
            "failed" if failed else "error",
            reason=(
                "the factory did not produce this week's video: %s"
                % (factory_out.get("error") or factory_reason
                   or factory_status or "unknown factory outcome")
            ),
            reason_code=factory_reason,
            factory_outcome=factory_status,
            **_common(),
        )
        _write_json(out_path / "drama-song-result.json", result)
        return result, None

    # factory says ok. (3) ok is reported only when the file really exists.
    ok_duration, duration_reason = (
        validate_duration(duration, length)
        if duration is not None else (True, "")
    )
    if not ok_duration:
        result = envelope(
            "weekly", "failed", reason=duration_reason,
            reason_code="duration-out-of-window",
            factory_outcome=factory_status,
            **_common(),
        )
        _write_json(out_path / "drama-song-result.json", result)
        return result, None

    video_exists = bool(video_path) and Path(os.path.expanduser(str(video_path))).is_file()
    if video_exists:
        result = envelope(
            "weekly", "ok", reason="",
            factory_outcome=factory_status,
            video_exists=True,
            **_common(),
        )
        _write_json(out_path / "drama-song-result.json", result)
        return result, None

    # No file on disk: honest pending-production, and the brief is handed to
    # the video department through the same path a direct request takes (B1).
    handoff = _dispatch_hook(
        stage_hook or env.get("DRAMA_SONG_STAGE_HOOK"),
        {
            "schema_version": SCHEMA_VERSION,
            "source": "35-social-media-planner/weekly-step",
            "request_type": "direct-request-equivalent",
            "theme": (theme or "").strip(),
            "brief": brief,
            "reason": "weekly video not yet produced",
            "video_path": video_path,
        },
    )
    result = envelope(
        "weekly", "pending-production",
        reason=(
            "the factory accepted the brief but this week's video file is "
            "not on disk yet (%s); the brief is queued for the video "
            "department through the same path as a direct request"
            % (video_path or "no video_path reported")
        ),
        reason_code="pending-production",
        factory_outcome=factory_status,
        handoff=handoff,
        **_common(video_exists=False),
    )
    _write_json(out_path / "drama-song-result.json", result)
    return result, None


# --- CLI ----------------------------------------------------------------------

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
                    help="60 (planner hard cap from length_routing) or 90 "
                         "(88-95 s window); anything else is rejected")
    ap.add_argument("--dry-run", action="store_true",
                    help="build the plan and write the result, never dispatch")
    ap.add_argument("--connected", default=None,
                    help="comma-separated connected planner channels")
    ap.add_argument("--factory-entry", default=None,
                    help="Skill 75 factory.py path (or DRAMA_SONG_FACTORY_ENTRY)")
    ap.add_argument("--stage-hook", default=None,
                    help="optional B1 stage-runner script that hands the brief "
                         "to the video department (or DRAMA_SONG_STAGE_HOOK)")
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
        stage_hook=args.stage_hook,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return exit_code_for(result.get("status", "error"))


if __name__ == "__main__":
    sys.exit(main())
