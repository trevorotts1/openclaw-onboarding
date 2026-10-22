"""preflight.py: dependency/auth checks before paid work (24.2 row 2). stdlib only.

NAMES only: resolves tools via shutil.which, disk via shutil.disk_usage.
Never executes tools, never submits generation, never logs credential values.
Successful exit never means paid submission occurred.

D05 + D12 (Skill_75_Universal_Repair_Spec_v1.1 sections 9.1/9.2): the
effective requirement set is DERIVED from the selected production mode, media
choices, durations and channel via the dependency manifest (PREREQS.json):
the actual Python interpreter used to launch Skill 75 and the packages in it,
FFmpeg/ffprobe, storage/temp capacity, platform/architecture, credential
presence, runtime channel tools, model routes, provider transport mode,
callback/polling path, and media-analysis assets (faster-whisper only when the
lyric-timing fallback uses it; numpy/mediapipe/OpenCV and the pinned face
model when the lip-sync path requires them). Empty tool/module/credential
lists can never pass a media production; a gate that requires a package marks
it required, never optional. Missing requirements return an actionable repair
plan and the affected checks rerun automatically after repair
(``repair()``/``recheck()``). A non-generating diagnostic run declares itself
as such with reduced requirements. An unsupported local Python/architecture
names the precise incompatibility and never loops.
"""
import importlib
import importlib.util
import os
import platform as _platform
import re
import shutil
import subprocess
import sys
import tempfile

# ponytail: no network/catalog probe; add provider allowlist fetch when needed.


def check_tools(names):
    return {n: (shutil.which(n) is not None) for n in (names or [])}


def check_modules(names):
    out = {}
    for n in (names or []):
        try:
            importlib.import_module(n)
            out[n] = True
        except Exception:
            out[n] = False
    return out


def check_disk(path, min_free_bytes=0):
    try:
        u = shutil.disk_usage(path)
        return {"total": u.total, "free": u.free,
                "ok": u.free >= (min_free_bytes or 0)}
    except Exception as e:
        return {"error": str(e)[:200], "ok": False}


def check_storage_writable(path):
    return os.path.isdir(path) and os.access(path, os.W_OK | os.X_OK)


def check_credentials(names, env=None):
    env = env if env is not None else os.environ
    return {n: bool(_env_value(n, env)) for n in (names or [])}  # presence only, values never returned


# ── Credential presence across the env stores (values never leave this module) ─

#: Obvious-placeholder rejection, mirroring shared-utils/check-skill-prereqs.sh:
#: a stored PASTE_REAL_TOKEN is not a present credential.
_PLACEHOLDER_SUBSTRINGS = (
    "xxxxx", "your_key", "your-key", "your_api", "your-api", "yourkey",
    "your_token", "replace_me", "replace-me", "replaceme", "changeme",
    "change_me", "change-me", "_here", "-here", "placeholder", "sample",
    "dummy", "demo", "test_key", "fake_key", "sk-test", "sk-xxx", "sk-example",
    "sk-replace", "todo", "tbd", "fill_in", "fillin", "paste-your",
    "paste_real", "insert_your", "enter_your", "set_your", "no_key", "none_yet",
)


def _looks_real(value):
    if not value:
        return False
    lo = value.lower()
    if any(s in lo for s in _PLACEHOLDER_SUBSTRINGS):
        return False
    if value.startswith("<") and value.endswith(">"):
        return False
    return True


def _env_stores():
    """The env files a credential may live in (same contract as the shell
    checker's Rule 7 search). Nothing here is ever printed."""
    stores = []
    oc_root = os.path.expanduser("~/.openclaw")
    stores += [os.path.join(oc_root, "secrets", ".env"),
               os.path.join(oc_root, "workspace", ".env"),
               os.path.join(oc_root, ".env"),
               "/data/.openclaw/secrets/.env",
               "/data/.openclaw/.env"]
    return [p for p in stores if os.path.isfile(p)]


def _search_stores(name):
    """True when some store holds a real-looking NAME=value. Values are never
    returned, logged or compared beyond presence."""
    for path in _env_stores():
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("export "):
                        line = line[7:]
                    if line.startswith(name + "=") and not line.startswith("#"):
                        if _looks_real(line[len(name) + 1:].strip().strip('"').strip("'")):
                            return True
        except Exception:  # noqa: BLE001 - unreadable store is simply not there
            continue
    return False


def _env_value(name, env):
    """Presence truth only: the caller sees a bool, never the value."""
    val = (env or {}).get(name)
    if _looks_real(val if isinstance(val, str) else None):
        return True
    return _search_stores(name)


def _load_card_gate():
    """card_gate (F15) from core/style_defaults, or None; caller fails closed."""
    try:
        core = os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.dirname(os.path.abspath(__file__)))))
        if core not in sys.path:
            sys.path.insert(0, core)
        from style_defaults import card_gate as CG  # noqa: PLC0415
        return CG
    except Exception:  # noqa: BLE001 - fall back to the local fail-closed check
        return None


def check_card_receipt(run_state, card_receipt):
    """F15 (Critical, owner order 2026-10-08): before ANY paid job the run
    state must carry the recorded choice-card receipt -- one card, four
    answers (video_style, audio_style, length, video_model). ``card_receipt``
    overrides; else ``run_state['card_receipt']`` (or the run state's own
    card record) is read. Never silently passes: a missing/blank answer is
    reason ``CARD_UNANSWERED``."""
    cg = _load_card_gate()
    record = card_receipt if card_receipt is not None else run_state
    if cg is not None:
        ok, refusal = cg.gate_run_state(record if isinstance(record, dict) else None)
        if not ok:
            return refusal
        return None
    # Local fail-closed copy for the (defensive) case card_gate cannot import.
    answers = record if isinstance(record, dict) else None
    if isinstance(answers, dict):
        for key in ("answers", "card_answers", "card", "choice_card"):
            inner = answers.get(key)
            if isinstance(inner, dict):
                answers = inner
                break
    missing = [f for f in ("video_style", "audio_style", "length", "video_model")
               if not isinstance(answers, dict)
               or answers.get(f) is None
               or (isinstance(answers.get(f), str) and not answers.get(f).strip())]
    if missing:
        return {"reason_code": "CARD_UNANSWERED", "missing": missing,
                "next_action": "Show the choice card and record all four "
                               "answers (video style, audio style, length, "
                               "video model), with who and when, before any "
                               "paid job."}
    return None


def _inside(root, p):
    root = os.path.realpath(root)
    target = os.path.realpath(os.path.join(root, p)) if not os.path.isabs(p) else os.path.realpath(p)
    return target == root or target.startswith(root + os.sep), target


# ── D12: one canonical duration table (six lengths, 120 s included) ─────────

#: Defensive fallback ONLY for the case style_defaults cannot import at all.
#: test_preflight_capability_derivation locks it to both canonical tables
#: (style_defaults.defaults.LENGTH_OPTIONS_S and music_styles.OFFERED_LENGTHS_S),
#: so it can never silently drift from them.
_FALLBACK_LENGTHS_S = (60, 90, 120, 180, 300, 600)


def _core_dir():
    here = os.path.dirname(os.path.abspath(__file__))  # .../scripts/core/intake_preflight
    return os.path.dirname(here)                       # .../scripts/core


def skill_root():
    return os.path.dirname(os.path.dirname(_core_dir()))   # skill folder


def _canonical_lengths():
    """The canonical duration table, imported (never re-declared): the F15
    length menu in style_defaults.defaults."""
    core = _core_dir()
    if core not in sys.path:
        sys.path.insert(0, core)
    try:
        from style_defaults import defaults as _D  # noqa: PLC0415
        return tuple(_D.LENGTH_OPTIONS_S)
    except Exception:  # noqa: BLE001 - defensive fallback, lockstep-tested
        return _FALLBACK_LENGTHS_S


#: Version-2 delivery profiles (H8, D12): every canonical length x two
#: shapes, named ``drama-<shape>-<length>s`` -- the only profiles preflight
#: allows by default. Derived from the ONE canonical duration table, so a
#: duration added there (120 s, F15) is a profile here. The version-1
#: ``short-9x16-30s`` profile is retired.
PROFILE_LENGTHS_S = _canonical_lengths()
PROFILE_SHAPES = ("9x16", "16x9")
DEFAULT_PROFILES = tuple(
    "drama-%s-%ss" % (shape, secs)
    for secs in PROFILE_LENGTHS_S for shape in PROFILE_SHAPES
)


# ── D05: capability-derived requirements (spec 9.1) ─────────────────────────

MIN_PYTHON = (3, 9)
SUPPORTED_PLATFORMS = ("darwin", "linux")
SUPPORTED_ARCHS = ("x86_64", "arm64")
_ARCH_ALIASES = {"amd64": "x86_64", "x64": "x86_64", "aarch64": "arm64"}

#: Storage/temp floor for a media production: base working set + a per-minute
#: per-media estimate. ponytail: coarse constants; replace with per-codec
#: estimates when the render pipeline publishes real numbers.
STORAGE_BASE_BYTES = 256 * 1024 * 1024
STORAGE_PER_MEDIA_MINUTE_BYTES = 128 * 1024 * 1024

#: Media choices a production can declare. Anything paid implies the KIE
#: credential and the model-route/transport declarations below.
DEFAULT_MEDIA = ("music", "lyrics", "voiceover", "clips", "assembly")
LIPSYNC_MEDIA = ("lipsync",)
ASR_FALLBACK_FASTER_WHISPER = "faster-whisper"
TRANSPORT_MODES = ("callback", "polling")

#: Runtime channel tools per delivery channel (factory.py delivery sink is
#: `openclaw message send`; "text" is in-conversation and needs no tool).
CHANNEL_TOOL_NAMES = {"openclaw": ("openclaw",), "telegram": ("openclaw",),
                      "studio": ("openclaw",), "text": ()}


def _profile_seconds(profile):
    m = re.search(r"-(\d+)s$", str(profile or ""))
    return int(m.group(1)) if m else None


def capability_context(payload):
    """Normalised capability inputs: production mode, media choices, durations
    and channel. Explicit ``capabilities`` win; a bare payload is a full
    drama-song production at the default duration (a media production), and
    ``mode: diagnostic`` / ``generating: false`` declares a non-generating run."""
    p = payload or {}
    caps = p.get("capabilities") if isinstance(p.get("capabilities"), dict) else {}
    declared = bool(p.get("capabilities"))
    mode_raw = str(p.get("mode") or caps.get("mode") or "production").strip().lower()
    diagnostic = (mode_raw in ("diagnostic", "non-generating", "inspect")
                  or caps.get("generating") is False)
    media = caps.get("media")
    media = list(DEFAULT_MEDIA) if media is None else [str(m) for m in (media or [])]
    duration = (caps.get("duration_s") or p.get("duration_s")
                or _profile_seconds(p.get("profile")))
    if not isinstance(duration, int):
        card = p.get("card_receipt") if isinstance(p.get("card_receipt"), dict) else {}
        answers = card.get("answers") if isinstance(card.get("answers"), dict) else card
        length = (answers or {}).get("length")
        duration = length if isinstance(length, int) else PROFILE_LENGTHS_S[0]
    channel = str(caps.get("channel") or "").strip().lower()
    return {
        "mode": "diagnostic" if diagnostic else "production",
        "generating": not diagnostic,
        "media": media,
        "duration_s": int(duration),
        "channel": channel,
        "channel_declared": bool(channel),
        "lyric_timing_fallback": str(caps.get("lyric_timing_fallback") or "").strip().lower(),
        "lip_sync": bool(caps.get("lip_sync")) or any(m in LIPSYNC_MEDIA for m in media),
        "singing_detector": bool(caps.get("singing_detector")) or "singing-share" in media,
        "agnes_path": bool(caps.get("agnes_path")),
        "transport": str(caps.get("transport") or "").strip().lower(),
        "transport_declared": bool(caps.get("transport")),
        "model_routes": [str(r) for r in (caps.get("model_routes") or []) if str(r).strip()],
        "routes_declared": caps.get("model_routes") is not None,
        "callback_path": str(caps.get("callback_path") or "").strip(),
        "polling_path": str(caps.get("polling_path") or "").strip(),
        "temp_dir": caps.get("temp_dir") or p.get("temp_dir"),
        "declared": declared,
    }


def load_manifest(path=None):
    """PREREQS.json (the existing dependency manifest). Returns {} when it
    cannot be read -- callers fail closed, never pass, on an unreadable
    manifest."""
    cand = path or os.environ.get("SKILL75_PREREQS") or os.path.join(
        skill_root(), "PREREQS.json")
    try:
        import json
        with open(cand, encoding="utf-8") as f:
            doc = json.load(f)
        return doc if isinstance(doc, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


def _manifest_entry(manifest, entry_id):
    for e in (manifest or {}).get("prerequisites") or []:
        if isinstance(e, dict) and e.get("id") == entry_id:
            return e
    return None


def _req(req_id, kind, why, manifest=None, manifest_id=None, hard=True, args=None):
    """One derived requirement. ``severity`` is ALWAYS required for a hard
    gate requirement -- a capability that requires a package can never call it
    optional (D05); ``manifest_severity`` records what PREREQS.json said."""
    entry = _manifest_entry(manifest, manifest_id) if manifest_id else None
    return {"id": req_id, "kind": kind, "severity": "required" if hard else "optional",
            "hard": hard, "why": why,
            "manifest_id": manifest_id,
            "manifest_severity": (entry or {}).get("severity"),
            "satisfy": (entry or {}).get("satisfy", ""),
            "args": args or {}}


def derive_requirements(ctx, manifest=None, payload=None):
    """The effective dependency set (spec 9.1), derived from the selected
    production mode, media choices, durations and channel via PREREQS.json.
    Non-generating diagnostic runs get the reduced set and nothing else."""
    reqs = []
    reqs.append(_req("platform-arch", "platform",
                     "every run: supported platform/architecture",
                     args={"platforms": SUPPORTED_PLATFORMS, "archs": SUPPORTED_ARCHS}))
    reqs.append(_req("python-interpreter", "python",
                     "every run: the interpreter that launches Skill 75",
                     manifest=manifest, manifest_id="python3-binary",
                     args={"min_python": MIN_PYTHON}))
    reqs.append(_req("storage-capacity", "storage",
                     "every run: storage capacity and writability",
                     args={"min_free_bytes": 0}))
    reqs.append(_req("temp-capacity", "temp", "every run: temp capacity and writability",
                     args={"min_free_bytes": 0}))
    if not ctx.get("generating"):
        return reqs  # non-generating diagnostic mode: reduced requirements

    media = ctx.get("media") or []
    minutes = max(1, -(-int(ctx.get("duration_s") or 60) // 60))
    floor = STORAGE_BASE_BYTES + STORAGE_PER_MEDIA_MINUTE_BYTES * minutes * max(1, len(media))
    for r in reqs:
        if r["kind"] in ("storage", "temp"):
            r["args"]["min_free_bytes"] = floor
            r["why"] += " (floor %d bytes for %ds of media)" % (floor, ctx.get("duration_s"))

    if media:
        for tool in ("ffmpeg", "ffprobe"):
            reqs.append(_req(tool + "-binary", "tool",
                             "media production %s: assembly/probe tool" % (", ".join(media),),
                             manifest=manifest,
                             manifest_id="ffmpeg-binary" if tool == "ffmpeg" else None,
                             args={"tool": tool}))
        reqs.append(_req("kie-api-key", "credential",
                         "paid media generation: KIE credential presence",
                         manifest=manifest, manifest_id="kie-api-key",
                         args={"envVar": "KIE_API_KEY"}))
        reqs.append(_req("model-routes", "route",
                         "media production: at least one declared model route",
                         hard=ctx.get("routes_declared"), args={}))
        reqs.append(_req("provider-transport", "transport",
                         "media production: provider transport mode (callback|polling)",
                         manifest=manifest,
                         manifest_id="skill-46-callback-relay"
                         if ctx.get("transport") == "callback" else None,
                         hard=ctx.get("transport_declared"),
                         args={"modes": TRANSPORT_MODES}))
        if ctx.get("transport") == "callback":
            reqs.append(_req("callback-path", "callback-path",
                             "callback transport: the callback/polling path",
                             manifest=manifest, manifest_id="skill-46-callback-relay",
                             hard=True, args={"field": "callback_path"}))
        elif ctx.get("transport") == "polling":
            reqs.append(_req("polling-path", "polling-path",
                             "polling transport: the polling path",
                             hard=True, args={"field": "polling_path"}))
        if ctx.get("channel_declared"):
            tools = CHANNEL_TOOL_NAMES.get(ctx.get("channel"))
            if tools is None:
                reqs.append(_req("channel-tool", "channel",
                                 "delivery channel %r is not a supported channel"
                                 % ctx.get("channel"), hard=True,
                                 args={"channel": ctx.get("channel"), "tools": ()}))
            elif tools:
                reqs.append(_req("channel-tool", "channel",
                                 "runtime channel tool for %s delivery" % ctx.get("channel"),
                                 hard=True,
                                 args={"channel": ctx.get("channel"), "tools": tuple(tools)}))

    if ctx.get("lip_sync"):
        # The lip-sync gates REQUIRE these four pieces; PREREQS.json lists them
        # optional (the shell checker cannot verify them) -- when the lip-sync
        # path is selected they are REQUIRED here, never optional (D05).
        for mod, dist in (("mediapipe", "mediapipe"), ("cv2", "opencv-python-headless"),
                          ("numpy", "numpy")):
            reqs.append(_req("lipsync-module-" + mod, "module",
                             "lip-sync picture gate + measured clip gate need " + mod,
                             manifest=manifest, manifest_id="python-mediapipe",
                             args={"module": mod, "dist": dist}))
        reqs.append(_req("face-landmarker-model", "asset",
                         "lip-sync gates need the pinned face_landmarker.task",
                         manifest=manifest, manifest_id="face-landmarker-model",
                         args={}))

    if ctx.get("lyric_timing_fallback") == ASR_FALLBACK_FASTER_WHISPER:
        reqs.append(_req("faster-whisper", "module",
                         "tier-2 lyric-timing fallback selected: local ASR required",
                         manifest=manifest, manifest_id="faster-whisper-optional",
                         args={"module": "faster_whisper", "dist": "faster-whisper"}))

    if ctx.get("singing_detector"):
        reqs.append(_req("numpy-singing-detector", "module",
                         "singing detector measures sung share: numpy required",
                         manifest=manifest, manifest_id="numpy-optional",
                         args={"module": "numpy", "dist": "numpy"}))

    if ctx.get("agnes_path"):
        reqs.append(_req("agnes-key", "credential",
                         "optional Agnes path selected: Agnes key presence",
                         manifest=manifest, manifest_id="agnes-key",
                         args={"envVar": "AGNES_AI_API_KEY"}))
        # tesseract keeps its supported alternative (words overlaid at
        # assembly) -- it is reported, never promoted to a hard gate (9.1).
        reqs.append(_req("tool-tesseract", "tool",
                         "Agnes words-in-pictures OCR (alternative exists: "
                         "words overlaid at assembly)",
                         manifest=manifest, manifest_id="tool-tesseract",
                         hard=False, args={"tool": "tesseract"}))

    return reqs


def face_model_state(path=None):
    """(state, detail) for the pinned face model. One pin authority:
    install_face_model (the installer's own is_good), read at the same
    default/override both gates read ($LIPSYNC_FACE_MODEL or
    <skill>/assets/face_landmarker.task). ponytail: preflight-local read; the
    single shared locator across installer/picture gate/clip gate is U2's."""
    dest = path or os.environ.get("LIPSYNC_FACE_MODEL") or os.path.join(
        skill_root(), "assets", "face_landmarker.task")
    try:
        lip_gate = os.path.join(skill_root(), "scripts", "core", "lip_sync", "lip_gate")
        if lip_gate not in sys.path:
            sys.path.insert(0, lip_gate)
        import install_face_model as IFM  # noqa: PLC0415
    except Exception as e:  # noqa: BLE001
        return ("UNKNOWN", "install_face_model unreadable: %s" % str(e)[:120])
    if not os.path.isfile(dest):
        return ("MISSING", dest)
    if IFM.is_good(dest):
        return ("PRESENT", dest)
    return ("PRESENT-BUT-BROKEN",
            "%s: size/sha256 mismatch (pinned sha256 %s)" % (dest, IFM.MODEL_SHA256[:16] + "…"))


def interpreter_identity():
    """The ACTUAL interpreter launching Skill 75 -- preflight runs in-process
    with the launcher (factory.py), so this is the interpreter every derived
    package check and every repair install targets."""
    return {"path": sys.executable, "version": _platform.python_version(),
            "implementation": _platform.python_implementation(),
            "machine": _platform.machine(), "platform": sys.platform}


def check_requirement(req, ctx=None, payload=None):
    """-> {"ok": True|False|None, "detail": str}. None = soft/undeclared
    requirement recorded honestly (never a silent PASS)."""
    kind, args = req["kind"], req.get("args") or {}
    if kind == "platform":
        plat = sys.platform
        arch = _ARCH_ALIASES.get(_platform.machine(), _platform.machine())
        ok = plat in SUPPORTED_PLATFORMS and arch in SUPPORTED_ARCHS
        return {"ok": ok, "detail": "%s/%s (supported: %s x %s)" % (
            plat, arch, ",".join(SUPPORTED_PLATFORMS), ",".join(SUPPORTED_ARCHS))}
    if kind == "python":
        v = sys.version_info[:2]
        ok = v >= tuple(args.get("min_python") or MIN_PYTHON)
        return {"ok": ok, "detail": "%s %s at %s (requires CPython >= %s)" % (
            _platform.python_implementation(), _platform.python_version(), sys.executable,
            ".".join(str(x) for x in (args.get("min_python") or MIN_PYTHON)))}
    if kind == "tool":
        tool = args.get("tool")
        return {"ok": shutil.which(tool) is not None,
                "detail": "%s -> %s" % (tool, shutil.which(tool) or "not on PATH")}
    if kind == "module":
        mod = args.get("module")
        try:
            found = importlib.util.find_spec(mod) is not None
        except Exception:  # noqa: BLE001
            found = False
        return {"ok": found, "detail": "%s in %s: %s" % (
            mod, sys.executable, "importable" if found else "not importable")}
    if kind == "asset":
        state, detail = face_model_state()
        return {"ok": state == "PRESENT", "detail": "%s (%s)" % (state, detail)}
    if kind == "credential":
        name = args.get("envVar")
        env = (payload or {}).get("env")
        return {"ok": bool(_env_value(name, env if env is not None else os.environ)),
                "detail": "%s set (presence only; value never logged)" % name}
    if kind in ("storage", "temp"):
        if kind == "storage":
            path = (args.get("path") or (payload or {}).get("storage_dir")
                    or (payload or {}).get("approved_root") or os.getcwd())
        else:
            path = (args.get("path") or (ctx or {}).get("temp_dir")
                    or tempfile.gettempdir())
        floor = args.get("min_free_bytes") or 0
        if kind == "storage":
            # an explicit payload floor may raise, never lower, the derived one
            floor = max(floor, (payload or {}).get("min_free_bytes") or 0)
        wr = check_storage_writable(path)
        disk = check_disk(path, floor)
        return {"ok": bool(wr and disk.get("ok")), "detail":
                "%s writable=%s free=%s floor=%s" % (
                    path, wr, disk.get("free"), floor)}
    if kind == "channel":
        tools = args.get("tools") or ()
        if not tools:
            return {"ok": True, "detail": "channel %s needs no external tool"
                    % args.get("channel")}
        hits = {t: shutil.which(t) for t in tools}
        return {"ok": any(hits.values()), "detail": str(hits)}
    if kind == "route":
        if not ctx.get("routes_declared"):
            return {"ok": None, "detail": "model routes not declared by this run"}
        return {"ok": bool(ctx.get("model_routes")),
                "detail": "routes=%s" % (ctx.get("model_routes") or [])}
    if kind == "transport":
        if not ctx.get("transport_declared"):
            return {"ok": None, "detail": "transport mode not declared by this run"}
        return {"ok": ctx.get("transport") in TRANSPORT_MODES,
                "detail": "transport=%s" % ctx.get("transport")}
    if kind in ("callback-path", "polling-path"):
        field = args.get("field")
        val = ctx.get(field) or ""
        return {"ok": bool(val), "detail": "%s=%r" % (field, val)}
    return {"ok": False, "detail": "unknown requirement kind %r" % kind}


def repair_plan_for(failures, ctx=None, manifest=None):
    """Actionable repair plan for failed requirements (spec 9.2: reject with a
    plan, then rerun). ``auto`` items run through repair(); system installs and
    credentials stay operator actions unless explicitly allowed. An
    unsupported platform/Python is named precisely and never looped."""
    plan, unsupported = [], []
    for req in failures:
        rid, kind = req["id"], req["kind"]
        satisfy = req.get("satisfy") or ""
        if kind in ("platform", "python"):
            unsupported.append({
                "id": rid,
                "incompatibility": check_requirement(req, ctx or {})["detail"],
                "action": "Run Skill 75 on a supported interpreter/host; this "
                          "one cannot satisfy %s. No install is attempted." % rid})
            continue
        if kind == "module":
            dist = (req.get("args") or {}).get("dist") or (req.get("args") or {}).get("module")
            if rid.startswith("lipsync-module-"):
                plan.append({"id": rid, "auto": True, "args": req.get("args") or {},
                             "command_argv": [sys.executable, os.path.join(
                                 skill_root(), "scripts", "lipsync_preflight.py"), "--repair"],
                             "command": "%s scripts/lipsync_preflight.py --repair" % sys.executable,
                             "why": "existing authorized setup path for the lip-sync stack"})
            else:
                plan.append({"id": rid, "auto": True, "args": req.get("args") or {},
                             "command_argv": [sys.executable, "-m", "pip", "install", dist],
                             "command": "%s -m pip install %s" % (sys.executable, dist),
                             "why": "install %s into the interpreter that launches "
                                    "Skill 75 (never an unrelated interpreter)" % dist})
        elif kind == "asset":
            plan.append({"id": rid, "auto": True, "args": req.get("args") or {},
                         "command_argv": [sys.executable, os.path.join(
                             skill_root(), "scripts", "lipsync_preflight.py"), "--repair"],
                         "command": "%s scripts/lipsync_preflight.py --repair "
                                    "(or: %s scripts/core/lip_sync/lip_gate/install_face_model.py)"
                                    % (sys.executable, sys.executable),
                         "why": "existing verified installer (pinned sha256); re-running "
                                "with a good file is a no-op"})
        elif kind == "tool":
            tool = (req.get("args") or {}).get("tool")
            if _platform.system() == "Darwin":
                cmd = "brew install %s" % ("ffmpeg" if tool in ("ffmpeg", "ffprobe") else tool)
            else:
                cmd = "apt-get update && apt-get install -y %s" % (
                    "ffmpeg" if tool in ("ffmpeg", "ffprobe") else tool)
            plan.append({"id": rid, "auto": True, "system": True, "command_argv": None,
                         "command": cmd,
                         "why": satisfy or "system package install; verified by re-running "
                                "the check in the launching interpreter"})
        elif kind == "credential":
            plan.append({"id": rid, "manual": True,
                         "command": None,
                         "action": satisfy or "Ask the operator for %s; never mint a key."
                                   % (req.get("args") or {}).get("envVar"),
                         "why": "credentials require the operator's actual input"})
        elif kind in ("storage", "temp"):
            plan.append({"id": rid, "manual": True, "command": None,
                         "action": "Free or relocate %s to meet the derived floor."
                                   % (req.get("args") or {}).get("path", "storage"),
                         "why": satisfy or "capacity"})
        else:
            plan.append({"id": rid, "manual": True, "command": None,
                         "action": satisfy or "Declare %s in the run's capabilities." % rid,
                         "why": "declaration requirement"})
    return {"plan": plan, "unsupported": unsupported}


def _default_runner(argv, timeout=900):
    """Run one repair command (argv list, never a shell) and keep the causal
    error text. One attempt per command -- a failure is reported, never looped."""
    try:
        r = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
        return {"rc": r.returncode, "stdout_tail": (r.stdout or "")[-2000:],
                "stderr_tail": (r.stderr or "")[-2000:]}
    except Exception as e:  # noqa: BLE001
        return {"rc": None, "error": "%s: %s" % (type(e).__name__, str(e)[:200])}


def check(payload):
    """payload keys: tools, modules, storage_dir, min_free_bytes, approved_root,
    references[], profile, allowed_profiles[], schema_version, allowed_schemas[],
    credentials[], env{}, auth{}, summary_digest, run_state, card_receipt,
    mode, capabilities{}, manifest_path. Returns outcome/reason/checks.

    D05: after the explicit lists (whose behaviour is unchanged), the effective
    dependency set is derived from the selected production mode, media choices,
    durations and channel via PREREQS.json. Empty tool/module/credential lists
    therefore never pass a media production; missing derived requirements come
    back with a repair plan. A non-generating run declares itself (reason
    ``preflight-pass-diagnostic``, never ``preflight-pass``)."""
    p = payload or {}
    checks = {}
    schemas = p.get("allowed_schemas") or ["blackceo.campaign/v1"]
    sv = p.get("schema_version") or "blackceo.campaign/v1"
    checks["schema_trusted"] = sv in schemas
    if not checks["schema_trusted"]:
        return {"outcome": "error", "reason_code": "schema-untrusted",
                "checks": checks, "next_action": f"Use a trusted schema: {schemas}."}
    allowed = p.get("allowed_profiles") or list(DEFAULT_PROFILES)
    checks["profile_known"] = (p.get("profile") or DEFAULT_PROFILES[0]) in allowed
    if not checks["profile_known"]:
        return {"outcome": "rejected", "reason_code": "delivery-profile-unknown",
                "checks": checks, "next_action": f"Choose a delivery profile in {allowed}."}

    root = p.get("approved_root") or p.get("storage_dir") or os.getcwd()
    bad, outside = [], []
    for r in (p.get("references") or []):
        ok, target = _inside(root, r)
        if not ok:
            outside.append(r)
        elif not (os.path.isfile(target) and os.path.getsize(target) > 0):
            bad.append(r)
    checks["references_ok"] = not bad
    checks["references_inside_approved_storage"] = not outside
    if outside:
        return {"outcome": "rejected", "reason_code": "reference-outside-approved-storage",
                "checks": checks, "missing": [], "outside": outside,
                "next_action": "Move references inside approved storage and retry."}
    if bad:
        return {"outcome": "error", "reason_code": "reference-missing-or-truncated",
                "checks": checks, "missing": bad,
                "next_action": "Restore missing/truncated references and retry."}
    tools = check_tools(p.get("tools"))
    checks["tools"] = tools
    if not all(tools.values()):
        return {"outcome": "error", "reason_code": "tool-unavailable",
                "checks": checks, "missing": sorted(k for k, v in tools.items() if not v),
                "next_action": "Install missing runtime tools and retry."}
    mods = check_modules(p.get("modules"))
    checks["modules"] = mods
    if not all(mods.values()):
        return {"outcome": "error", "reason_code": "module-unavailable",
                "checks": checks, "missing": sorted(k for k, v in mods.items() if not v),
                "next_action": "Install missing Python modules and retry."}
    sdir = p.get("storage_dir") or root
    checks["storage_writable"] = check_storage_writable(sdir)
    disk = check_disk(sdir, p.get("min_free_bytes") or 0)
    checks["disk"] = {k: disk[k] for k in ("total", "free", "ok") if k in disk}
    if not checks["storage_writable"]:
        return {"outcome": "error", "reason_code": "storage-not-writable",
                "checks": checks, "next_action": f"Make {sdir} writable and retry."}
    if not disk.get("ok"):
        return {"outcome": "error", "reason_code": "disk-limit",
                "checks": checks, "next_action": "Free disk space and retry."}
    creds = check_credentials(p.get("credentials"), p.get("env"))
    checks["credentials_present"] = creds
    if creds and not all(creds.values()):
        return {"outcome": "rejected", "reason_code": "credential-missing",
                "checks": checks, "missing": sorted(k for k, v in creds.items() if not v),
                "next_action": "Provide credentials (presence only; values never logged)."}

    # ── D05: capability-derived requirements (spec 9.1). The explicit lists
    # above keep their exact behaviour; these derive the REAL dependency set
    # from the selected production mode, media choices, durations and channel
    # via PREREQS.json, so empty tool/module/credential lists can never pass a
    # media production. A gate that requires a package marks it required.
    ctx = capability_context(p)
    checks["mode"] = ctx["mode"]
    checks["generating"] = ctx["generating"]
    checks["interpreter"] = interpreter_identity()
    manifest = load_manifest(p.get("manifest_path"))
    manifest_ok = bool((manifest or {}).get("prerequisites"))
    checks["manifest"] = "read" if manifest_ok else "unavailable"
    derived = derive_requirements(ctx, manifest if manifest_ok else None, p)
    drows, dfail = [], []
    for req in derived:
        res = check_requirement(req, ctx, p)
        drows.append({"id": req["id"], "kind": req["kind"], "severity": req["severity"],
                      "manifest_id": req["manifest_id"],
                      "manifest_severity": req["manifest_severity"],
                      "why": req["why"], "ok": res["ok"], "detail": res["detail"]})
        if req.get("hard", True) and res["ok"] is False:
            dfail.append(req)
    checks["derived"] = drows
    checks["requirements"] = [{"id": r["id"], "severity": r["severity"],
                               "manifest_severity": r["manifest_severity"],
                               "why": r["why"]} for r in derived]
    if ctx["generating"] and (not ctx["media"] or not derived):
        return {"outcome": "error", "reason_code": "requirements-empty",
                "checks": checks, "missing": [],
                "next_action": "A media production derives a real dependency set "
                               "from its mode, media, durations and channel; declare "
                               "them (capabilities{}) so preflight can check them. "
                               "Empty tool/module/credential lists never pass."}
    if ctx["generating"] and not manifest_ok:
        return {"outcome": "error", "reason_code": "manifest-unavailable",
                "checks": checks, "missing": ["PREREQS.json"],
                "repair_plan": {"plan": [{"id": "PREREQS.json", "manual": True,
                                 "command": None,
                                 "action": "Restore PREREQS.json (the dependency "
                                           "manifest) to the skill folder."}],
                                 "unsupported": []},
                "next_action": "Restore PREREQS.json and retry; a media production "
                               "cannot verify its dependency set without it."}
    if dfail:
        plan = repair_plan_for(dfail, ctx, manifest)
        reason = "dependency-missing"
        if all(r["kind"] == "platform" for r in dfail):
            reason = "platform-unsupported"
        elif all(r["kind"] in ("platform", "python") for r in dfail):
            reason = "python-unsupported"
        out = {"outcome": "error", "reason_code": reason,
               "checks": checks, "missing": sorted(r["id"] for r in dfail),
               "repair_plan": plan}
        if reason == "dependency-missing":
            out["rerun"] = ("recheck(payload) / repair(payload) reruns the affected "
                            "checks automatically after repair")
            out["next_action"] = ("Apply the repair plan (%d item(s)), then rerun; the "
                                  "affected checks rerun automatically."
                                  % len(plan["plan"]))
        else:
            out["loop"] = False
            out["next_action"] = ("; ".join(u["incompatibility"]
                                  for u in plan["unsupported"])
                                  or "Unsupported interpreter/host; no install is attempted.")
        return out
    if not ctx["generating"]:
        # Non-generating diagnostic mode: reduced requirements, declares itself.
        return {"outcome": "ok", "reason_code": "preflight-pass-diagnostic",
                "checks": checks, "mode": "diagnostic", "generating": False,
                "readiness": "diagnostic-only",
                "next_action": "Diagnostic only (non-generating): reduced "
                               "requirements verified; this is NOT paid-work readiness."}

    auth = p.get("auth") or {}
    if not auth:
        return {"outcome": "rejected", "reason_code": "approval-missing",
                "checks": checks, "next_action": "Record authorization scope before paid work."}
    import time
    exp = auth.get("expires_unix")
    if isinstance(exp, (int, float)) and int(time.time()) > exp:
        return {"outcome": "rejected", "reason_code": "approval-expired",
                "checks": checks, "next_action": "Renew expired authorization."}
    scope = auth.get("scope")
    dgst = p.get("summary_digest")
    if scope not in ("campaign", dgst):
        return {"outcome": "rejected", "reason_code": "approval-out-of-scope",
                "checks": checks, "next_action": "Bind authorization to this campaign summary digest."}
    card_refusal = check_card_receipt(p.get("run_state"), p.get("card_receipt"))
    # F15: paid work (which is what preflight gates) never starts on an
    # unanswered card, whichever entry path launched the run.
    if card_refusal is not None:
        checks["card_recorded"] = False
        return {"outcome": "waiting", "reason_code": card_refusal["reason_code"],
                "checks": checks, "missing": card_refusal.get("missing", []),
                "next_action": card_refusal.get(
                    "next_action", "Show and answer the choice card first.")}
    checks["card_recorded"] = True
    checks["readiness"] = "full"
    return {"outcome": "ok", "reason_code": "preflight-pass",
            "checks": checks, "next_action": "Proceed to claim eligible stage."}


def recheck(payload, prior=None, only=None):
    """Rerun the affected derived checks (or ``only`` ids) and report
    before/after per requirement. ``before`` comes from ``prior`` (the failing
    result) when given, so a post-repair rerun shows the actual transition.
    Called automatically at the end of repair()."""
    ctx = capability_context(payload or {})
    manifest = load_manifest((payload or {}).get("manifest_path"))
    derived = derive_requirements(ctx, manifest, payload or {})
    if prior is not None:
        before = {row["id"]: row["ok"] for row in
                  ((prior.get("checks") or {}).get("derived") or [])}
    else:
        before = {r["id"]: check_requirement(r, ctx, payload)["ok"] for r in derived}
    ids = set(only or []) or {r["id"] for r in derived}
    after = {}
    for r in derived:
        if r["id"] in ids:
            after[r["id"]] = check_requirement(r, ctx, payload)["ok"]
    return {"affected": sorted(ids), "before": before, "after": after}


def isolated_env_python(env_dir):
    return os.path.join(env_dir, "Scripts", "python.exe") if sys.platform == "win32" \
        else os.path.join(env_dir, "bin", "python")


def ensure_isolated_env(env_dir, run=None):
    """Create/refresh the isolated environment ordinary installs belong in
    (``python -m venv`` is idempotent over an existing venv). Returns its
    interpreter path or None. ponytail: one shared env per skill; per-capability
    envs when two stacks ever need conflicting pins."""
    run = run or _default_runner
    res = run([sys.executable, "-m", "venv", env_dir])
    py = isolated_env_python(env_dir)
    return py if (res or {}).get("rc") == 0 and os.path.isfile(py) else None


def repair(payload, runner=None, allow_system_install=False, isolated_env_dir=None,
           fallback_env_dir=None):
    """Apply the repair plan for whatever check() rejected, then rerun the
    affected checks automatically (spec 9.2). Idempotent: requirements already
    satisfied install nothing and repair() on a healthy payload is a no-op.
    Installs target the ACTUAL interpreter that launches Skill 75
    (sys.executable); when that interpreter is externally managed (PEP 668) or
    an isolated env is declared, installs land in that env and the receipt
    names the interpreter the launcher must use (verified there). A failed
    install keeps its causal stderr and is never retried in a loop. An
    unsupported platform/Python returns its precise incompatibility and
    attempts nothing."""
    run = runner or _default_runner
    prior = check(payload or {})
    if prior.get("outcome") == "ok":
        return {"already_satisfied": prior.get("missing", []) or "all",
                "attempts": [], "result": prior,
                "interpreter": interpreter_identity(),
                "note": "idempotent: nothing to repair"}
    plan = (prior.get("repair_plan") or {}).get("plan") or []
    unsupported = (prior.get("repair_plan") or {}).get("unsupported") or []
    if unsupported:
        # Precise incompatibility, never a retry loop: an unsupported
        # interpreter/host gets no install attempts at all.
        return {"unsupported": unsupported, "attempts": [], "loop": False,
                "manual": plan, "result": prior,
                "note": "unsupported interpreter/host: named precisely, no install attempted"}
    caps = (payload or {}).get("capabilities") if isinstance(
        (payload or {}).get("capabilities"), dict) else {}
    env_dir = (isolated_env_dir or (payload or {}).get("isolated_env_dir")
               or caps.get("isolated_env_dir") or os.environ.get("SKILL75_ISOLATED_ENV"))
    install_py, env_receipt = sys.executable, None
    if env_dir:
        py = ensure_isolated_env(env_dir, run)
        if py:
            install_py, env_receipt = py, {"env_dir": env_dir, "python": py}
    attempts, manual = [], []
    groups = {}
    for item in plan:
        if item.get("manual"):
            manual.append(item)
            continue
        if item.get("system") and not allow_system_install:
            manual.append(dict(item, note="system install: rerun repair(allow_system_install=True) "
                                          "or apply the command as the operator"))
            continue
        argv = item.get("command_argv")
        if not argv and item.get("command"):
            argv = ["/bin/bash", "-lc", item["command"]]
        if not argv:
            continue
        argv = [install_py if a == sys.executable else a for a in argv]
        key = item.get("command") or " ".join(argv)
        groups.setdefault(key, {"argv": list(argv), "ids": []})["ids"].append(item["id"])
    for key in sorted(groups):
        g = groups[key]
        res = run(g["argv"])
        attempt = {"ids": g["ids"], "id": g["ids"][0], "argv": g["argv"],
                   "command": key, "result": res}
        if env_receipt:
            attempt["isolated_env"] = env_receipt
        pip_like = (g["argv"] and "-m" in g["argv"] and "pip" in g["argv"]) or (
            "lipsync_preflight.py" in key)
        if (res or {}).get("rc") != 0 and pip_like and "externally-managed-environment" \
                in ((res or {}).get("stderr_tail") or ""):
            # PEP 668: the launching interpreter refuses global installs. ONE
            # retry in the isolated env the runtime expects -- never a loop.
            fb_dir = env_dir or fallback_env_dir or os.path.join(
                skill_root(), ".venv-skill75")
            py = env_receipt and env_receipt["python"] or ensure_isolated_env(fb_dir, run)
            if py and py != g["argv"][0]:
                if not env_receipt:
                    env_receipt = {"env_dir": fb_dir, "python": py,
                                   "fallback": "PEP 668 externally-managed interpreter"}
                argv2 = [py if a == g["argv"][0] else a for a in g["argv"]]
                res2 = run(argv2)
                attempt["pep668_refusal"] = res
                attempt["isolated_retry"] = {"env_dir": fb_dir, "argv": argv2,
                                             "result": res2}
                attempt["launcher_must_use"] = py
                attempt["result"] = res2
                res = res2
                g["argv"] = argv2
        mod = next(((it.get("args") or {}).get("module")
                    for it in plan if it["id"] in g["ids"] and
                    (it.get("args") or {}).get("module")), None)
        if mod and (res or {}).get("rc") == 0:
            # verify the launcher ACTUALLY uses the install: import in the same
            # interpreter the install targeted (record-only; the post-repair
            # recheck below is the gate).
            attempt["launcher_verify"] = _default_runner(
                [g["argv"][0], "-c",
                 "import importlib.util,sys;"
                 "sys.exit(0 if importlib.util.find_spec(%r) else 3)" % mod],
                timeout=120)
            if g["argv"][0] != sys.executable:
                attempt["launcher_must_use"] = g["argv"][0]
        attempts.append(attempt)
    ok_ids = {i for a in attempts if (a["result"] or {}).get("rc") == 0 for i in a["ids"]}
    bad_ids = {i for a in attempts if (a["result"] or {}).get("rc") != 0 for i in a["ids"]}
    rerun = recheck(payload or {}, prior=prior)
    result = check(payload or {})
    out = {"attempts": attempts, "manual": manual,
           "repaired": sorted(ok_ids), "failed": sorted(bad_ids),
           "rerun": rerun, "result": result,
           "interpreter": interpreter_identity(),
           "note": "affected checks reran automatically after repair; installs "
                   "target and are verified in the launching interpreter"}
    if env_receipt:
        out["isolated_env"] = env_receipt
        out["note"] += ("; installs landed in the isolated env at %s -- the "
                        "launcher must run Skill 75 with %s (launcher_verify "
                        "probes that interpreter)" % (env_receipt["env_dir"],
                                                      env_receipt["python"]))
    return out
