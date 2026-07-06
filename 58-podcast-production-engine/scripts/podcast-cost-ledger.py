#!/usr/bin/env python3
# =============================================================================
# PODCAST PRODUCTION ENGINE (Skill 58) :: COST LEDGER
# Furnace design Guardrail 3 (per-episode and per-client-per-day ceilings) and
# Guardrail 4 (QC re-run cap and web-research cap).
# -----------------------------------------------------------------------------
# This is the SINGLE metering choke point. Every billable call in the pipeline
# (content-model turn, web-research call, cover-art task, audio synthesis) goes
# through two wrappers:
#   precheck  BEFORE the call - "would this cross a ceiling?" (refuses if so)
#   record    AFTER  the call - "here are the actual units consumed"
#
# Call sites meter UNITS (tokens, calls, images, TTS characters). The ledger
# converts units to dollars using config/cost-model.json (a static price table
# the operator can restamp). Prices drifting never requires a code change.
#
# Ceilings and caps live under podcast_engine.limits in the skill config and are
# per-client overridable. Every refusal is a typed CostCeilingExceeded result
# the pipeline maps to a hold state (cost_hold or queued); nothing is dropped.
#
# DOCTRINE HELD BY THIS SCRIPT:
#   - Self-metered and deterministic. No network, no model turn, ever.
#   - Never prints or echoes a secret value. It handles units and dollars only.
#   - Writes STATE files as the invoking (node) user; refuses to write as root.
#   - Zero client-facing output; operator/pipeline JSON on stdout only.
#   - No em dash characters anywhere; no triple-backtick fences in any output.
#   - Build-time reasoning models never ship here; this file names no model
#     provider at all, so the runtime routing policy stays owned by the config.
#
# EXIT CODES (so a gate can branch without parsing JSON):
#    0  allow / recorded / ok
#    2  soft ceiling warning (advisory; run continues)
#    3  usage or input error
#   10  per_episode_cost_usd_hard would be crossed         -> cost_hold
#   11  llm_tokens_per_episode_hard would be crossed        -> cost_hold
#   12  web_research_calls_per_episode would be crossed     -> refuse call
#   13  per_client_daily_cost_usd_hard would be crossed     -> daily hold
#   14  per_client_daily_episode_cap reached                -> queue next day
#   15  llm_max_output_tokens_per_call would be crossed     -> refuse call
# =============================================================================

"""Podcast Production Engine cost ledger - the single billable-call choke point."""

import argparse
import contextlib
import datetime as _dt
import errno
import json
import os
import sys

try:
    import fcntl  # POSIX advisory file lock; present on macOS and Linux.
    _HAVE_FCNTL = True
except Exception:  # pragma: no cover - non-POSIX fallback
    _HAVE_FCNTL = False

# ---------------------------------------------------------------------------
# Exit codes
# ---------------------------------------------------------------------------
EXIT_OK = 0
EXIT_SOFT = 2
EXIT_USAGE = 3
EXIT_EPISODE_HARD = 10
EXIT_TOKEN_BUDGET = 11
EXIT_RESEARCH_CAP = 12
EXIT_DAILY_HARD = 13
EXIT_EPISODE_CAP = 14
EXIT_OUTPUT_CAP = 15

CEILING_EXIT = {
    "per_episode_cost_usd_hard": EXIT_EPISODE_HARD,
    "llm_tokens_per_episode_hard": EXIT_TOKEN_BUDGET,
    "web_research_calls_per_episode": EXIT_RESEARCH_CAP,
    "per_client_daily_cost_usd_hard": EXIT_DAILY_HARD,
    "per_client_daily_episode_cap": EXIT_EPISODE_CAP,
    "llm_max_output_tokens_per_call": EXIT_OUTPUT_CAP,
}

# Recommended pipeline state per refused ceiling.
CEILING_STAGE = {
    "per_episode_cost_usd_hard": "cost_hold",
    "llm_tokens_per_episode_hard": "cost_hold",
    "web_research_calls_per_episode": "continue_without_call",
    "per_client_daily_cost_usd_hard": "cost_hold",
    "per_client_daily_episode_cap": "queued",
    "llm_max_output_tokens_per_call": "reject_call",
}

# Kinds this ledger meters.
KINDS = ("llm", "research", "image", "tts", "episode", "smoke_probe")

# ---------------------------------------------------------------------------
# Consolidated furnace defaults (furnace design Section 8). These ship as the
# safe fallback so the ledger is always runnable and always bounded even before
# the per-client config is present. The skill config overrides any of them.
# ---------------------------------------------------------------------------
DEFAULT_LIMITS = {
    "per_episode_cost_usd_soft": 2.50,
    "per_episode_cost_usd_hard": 5.00,
    "per_client_daily_cost_usd_hard": 15.00,
    "per_client_daily_episode_cap": 3,
    "llm_tokens_per_episode_hard": 400000,
    "llm_max_output_tokens_per_call": 8000,
    "web_research_calls_per_episode": 12,
    "web_research_bonus_on_fabrication_fail": 4,
    "qc_max_attempts": 3,
    "image_gen_attempts_max": 3,
    "tts_synth_attempts_max": 2,
    "queue_max_hold_days": 60,
    # Optional one-episode escape hatch set by the operator to release a single
    # held episode past the per-episode hard ceiling. Empty means no override.
    "override_episode_id": "",
}

# Embedded default price table. The real prices are pinned by the config-set
# owner in config/cost-model.json; these placeholders keep the metering logic
# runnable and honest (stderr says when the embedded table is in use). The Fish
# Audio price of 0.000015 per character reflects 15 dollars per 1,000,000 bytes.
DEFAULT_COST_MODEL = {
    "_note": "embedded placeholder prices; config/cost-model.json overrides",
    "usd_per_input_token": {"default": 0.0000008},
    "usd_per_output_token": {"default": 0.0000024},
    "usd_per_research_call": {"default": 0.006},
    "usd_per_image_gen": {"default": 0.04},
    "usd_per_tts_char": {"default": 0.000015},
    "usd_per_smoke_probe": {"default": 0.0},
}


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------
def _eprint(msg):
    sys.stderr.write(str(msg).rstrip("\n") + "\n")


def _now_iso():
    return _dt.datetime.now().astimezone().isoformat(timespec="seconds")


def _today(date_override=None):
    if date_override:
        return date_override
    return _dt.date.today().isoformat()


def _skill_root():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _default_state_dir():
    env = os.environ.get("PODCAST_ENGINE_STATE_DIR")
    if env:
        return os.path.expanduser(env)
    return os.path.expanduser("~/.openclaw/podcast-engine/state")


def _refuse_root_write(state_dir):
    # Root-owned state can freeze the gateway for the node user. Refuse loudly
    # rather than silently create files the runtime user cannot rewrite.
    try:
        if hasattr(os, "geteuid") and os.geteuid() == 0:
            _eprint(
                "cost-ledger: refusing to write state as root (euid 0). "
                "Run as the node user so the gateway user owns podcast state."
            )
            sys.exit(EXIT_USAGE)
    except Exception:
        pass


def _ensure_dir(path):
    os.makedirs(path, exist_ok=True)


def _read_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError:
        return default
    except (ValueError, OSError) as exc:
        _eprint("cost-ledger: could not read %s (%s); using default" % (path, exc))
        return default


def _atomic_write_json(path, obj):
    _ensure_dir(os.path.dirname(path))
    tmp = path + ".tmp.%d" % os.getpid()
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, indent=2, sort_keys=True)
        fh.write("\n")
    os.replace(tmp, path)


@contextlib.contextmanager
def _locked(lock_path):
    # Serialize read-modify-write across concurrent wrappers.
    _ensure_dir(os.path.dirname(lock_path))
    if not _HAVE_FCNTL:
        yield
        return
    fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        except OSError:
            pass
        os.close(fd)


# ---------------------------------------------------------------------------
# Config and price loading
# ---------------------------------------------------------------------------
def _load_mapping(path):
    if not path or not os.path.exists(path):
        return None
    lower = path.lower()
    if lower.endswith((".yaml", ".yml")):
        try:
            import yaml  # optional; only if the shipped config is YAML
            with open(path, "r", encoding="utf-8") as fh:
                return yaml.safe_load(fh)
        except Exception as exc:  # pragma: no cover - depends on optional dep
            _eprint("cost-ledger: could not parse YAML %s (%s)" % (path, exc))
            return None
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (ValueError, OSError) as exc:
        _eprint("cost-ledger: could not parse %s (%s)" % (path, exc))
        return None


def _find_skill_config(explicit):
    if explicit:
        return explicit
    env = os.environ.get("PODCAST_ENGINE_CONFIG")
    if env:
        return env
    root = _skill_root()
    for name in ("podcast-engine.yaml", "podcast-engine.yml",
                 "podcast-engine.json", "config.yaml", "config.json"):
        candidate = os.path.join(root, "config", name)
        if os.path.exists(candidate):
            return candidate
    return None


def load_limits(config_path):
    limits = dict(DEFAULT_LIMITS)
    cfg = _load_mapping(_find_skill_config(config_path))
    if isinstance(cfg, dict):
        node = cfg.get("podcast_engine", cfg)
        if isinstance(node, dict):
            override = node.get("limits", {})
            if isinstance(override, dict):
                for key, val in override.items():
                    limits[key] = val
    return limits


def load_cost_model(cost_model_path):
    path = cost_model_path or os.path.join(_skill_root(), "config", "cost-model.json")
    model = _load_mapping(path)
    if not isinstance(model, dict):
        _eprint("cost-ledger: cost-model.json not found; using embedded placeholder prices")
        return dict(DEFAULT_COST_MODEL)
    return model


def _price(model_table, key, model_id):
    table = model_table.get(key)
    if not isinstance(table, dict):
        table = DEFAULT_COST_MODEL.get(key, {})
    if model_id and model_id in table:
        return float(table[model_id])
    if "default" in table:
        return float(table["default"])
    fallback = DEFAULT_COST_MODEL.get(key, {})
    return float(fallback.get("default", 0.0))


def estimate_cost(kind, cost_model, input_tokens=0, output_tokens=0,
                  units=0, model_id=None):
    """Convert metered units into a dollar estimate for one call."""
    if kind == "llm":
        return (input_tokens * _price(cost_model, "usd_per_input_token", model_id)
                + output_tokens * _price(cost_model, "usd_per_output_token", model_id))
    if kind == "research":
        n = units or 1
        return n * _price(cost_model, "usd_per_research_call", model_id)
    if kind == "image":
        n = units or 1
        return n * _price(cost_model, "usd_per_image_gen", model_id)
    if kind == "tts":
        return units * _price(cost_model, "usd_per_tts_char", model_id)
    if kind == "smoke_probe":
        return units * _price(cost_model, "usd_per_smoke_probe", model_id)
    if kind == "episode":
        return 0.0
    return 0.0


# ---------------------------------------------------------------------------
# Ledger state access
# ---------------------------------------------------------------------------
def _daily_path(state_dir, date_str):
    return os.path.join(state_dir, "ledger", "%s.json" % date_str)


def _episode_path(state_dir, episode_id):
    return os.path.join(state_dir, "ledger", "episodes", "%s.json" % episode_id)


def _lock_path(state_dir):
    return os.path.join(state_dir, "ledger", ".ledger.lock")


def _new_daily(date_str):
    return {"date": date_str, "clients": {}}


def _client_bucket(daily, client):
    clients = daily.setdefault("clients", {})
    return clients.setdefault(client, {
        "usd_total": 0.0,
        "episode_admissions": [],
        "smoke_probes": 0,
        "lines": 0,
    })


def _new_episode(episode_id, client):
    return {
        "episode_id": episode_id,
        "client": client,
        "opened": _now_iso(),
        "usd": 0.0,
        "tokens": {"input": 0, "output": 0, "total": 0},
        "research_calls": 0,
        "research_cap_bonus": 0,
        "image_gens": 0,
        "tts_chars": 0,
        "lines": [],
    }


def _load_episode(state_dir, episode_id):
    if not episode_id:
        return None
    return _read_json(_episode_path(state_dir, episode_id), None)


def _effective_research_cap(limits, episode):
    base = int(limits["web_research_calls_per_episode"])
    bonus = int(episode.get("research_cap_bonus", 0)) if episode else 0
    return base + bonus


# ---------------------------------------------------------------------------
# Precheck (BEFORE the call)
# ---------------------------------------------------------------------------
def do_precheck(args):
    state_dir = args.state_dir
    limits = load_limits(args.config)
    cost_model = load_cost_model(args.cost_model)
    date_str = _today(args.date)
    kind = args.kind

    episode = _load_episode(state_dir, args.episode_id)
    ep_usd = float(episode["usd"]) if episode else 0.0
    ep_tokens = int(episode["tokens"]["total"]) if episode else 0
    ep_research = int(episode["research_calls"]) if episode else 0

    daily = _read_json(_daily_path(state_dir, date_str), _new_daily(date_str))
    bucket = daily.get("clients", {}).get(args.client, {})
    daily_usd = float(bucket.get("usd_total", 0.0))
    admissions = list(bucket.get("episode_admissions", []))

    override_id = str(limits.get("override_episode_id", "") or "")
    override_active = bool(args.episode_id) and args.episode_id == override_id

    call_usd = estimate_cost(
        kind, cost_model,
        input_tokens=args.input_tokens, output_tokens=args.output_tokens,
        units=args.units, model_id=args.model,
    )

    result = {
        "decision": "allow",
        "kind": kind,
        "client": args.client,
        "episode_id": args.episode_id,
        "date": date_str,
        "call_cost_usd_estimate": round(call_usd, 6),
        "projected_episode_usd": round(ep_usd + call_usd, 6),
        "projected_daily_usd": round(daily_usd + call_usd, 6),
        "override_active": override_active,
        "warnings": [],
    }

    def refuse(ceiling, detail):
        result["decision"] = "refuse"
        result["error"] = "CostCeilingExceeded"
        result["ceiling"] = ceiling
        result["recommended_stage"] = CEILING_STAGE.get(ceiling, "cost_hold")
        result["detail"] = detail
        _emit(result, args)
        sys.exit(CEILING_EXIT.get(ceiling, EXIT_EPISODE_HARD))

    # --- daily episode admission cap (episode 4+ of the day queues) ----------
    if kind == "episode":
        if args.episode_id and args.episode_id in admissions:
            result["detail"] = "episode already admitted today"
            result["already_admitted"] = True
            _emit(result, args)
            return EXIT_OK
        if len(set(admissions)) >= int(limits["per_client_daily_episode_cap"]):
            refuse("per_client_daily_episode_cap",
                   "daily episode cap %d reached; queue to next local day"
                   % int(limits["per_client_daily_episode_cap"]))
        result["detail"] = "admission allowed"
        _emit(result, args)
        return EXIT_OK

    # --- per-call output-token cap (content calls only) ----------------------
    if kind == "llm":
        cap = int(limits["llm_max_output_tokens_per_call"])
        if int(args.output_tokens) > cap:
            refuse("llm_max_output_tokens_per_call",
                   "requested output %d exceeds per-call cap %d"
                   % (int(args.output_tokens), cap))
        budget = int(limits["llm_tokens_per_episode_hard"])
        projected_tokens = ep_tokens + int(args.input_tokens) + int(args.output_tokens)
        if projected_tokens > budget:
            refuse("llm_tokens_per_episode_hard",
                   "projected episode tokens %d exceed budget %d (all passes and "
                   "all QC attempts share one budget)" % (projected_tokens, budget))
        result["projected_episode_tokens"] = projected_tokens

    # --- web-research call cap (Guardrail 4) ---------------------------------
    if kind == "research":
        cap = _effective_research_cap(limits, episode)
        n = int(args.units or 1)
        if ep_research + n > cap:
            refuse("web_research_calls_per_episode",
                   "research call %d exceeds cap %d (writer proceeds with what it "
                   "has)" % (ep_research + n, cap))
        result["research_cap"] = cap
        result["research_used"] = ep_research

    # --- per-episode hard ceiling (override may release one episode) ---------
    if not override_active:
        ep_hard = float(limits["per_episode_cost_usd_hard"])
        if ep_usd + call_usd > ep_hard:
            refuse("per_episode_cost_usd_hard",
                   "projected episode cost %.4f exceeds hard ceiling %.2f"
                   % (ep_usd + call_usd, ep_hard))

    # --- per-client daily hard ceiling ---------------------------------------
    daily_hard = float(limits["per_client_daily_cost_usd_hard"])
    if daily_usd + call_usd > daily_hard:
        refuse("per_client_daily_cost_usd_hard",
               "projected daily cost %.4f exceeds daily hard ceiling %.2f"
               % (daily_usd + call_usd, daily_hard))

    # --- soft ceiling is advisory, never a refusal ---------------------------
    ep_soft = float(limits["per_episode_cost_usd_soft"])
    if ep_usd + call_usd >= ep_soft:
        result["warnings"].append("per_episode_cost_usd_soft")
        result["soft_exceeded"] = True

    _emit(result, args)
    if result.get("soft_exceeded"):
        return EXIT_SOFT
    return EXIT_OK


# ---------------------------------------------------------------------------
# Record (AFTER the call)
# ---------------------------------------------------------------------------
def do_record(args):
    _refuse_root_write(args.state_dir)
    state_dir = args.state_dir
    limits = load_limits(args.config)
    cost_model = load_cost_model(args.cost_model)
    date_str = _today(args.date)
    kind = args.kind

    call_usd = estimate_cost(
        kind, cost_model,
        input_tokens=args.input_tokens, output_tokens=args.output_tokens,
        units=args.units, model_id=args.model,
    )

    with _locked(_lock_path(state_dir)):
        # --- daily ledger -----------------------------------------------------
        daily_path = _daily_path(state_dir, date_str)
        daily = _read_json(daily_path, _new_daily(date_str))
        bucket = _client_bucket(daily, args.client)
        bucket["usd_total"] = round(float(bucket.get("usd_total", 0.0)) + call_usd, 6)
        bucket["lines"] = int(bucket.get("lines", 0)) + 1
        if kind == "smoke_probe":
            bucket["smoke_probes"] = int(bucket.get("smoke_probes", 0)) + int(args.units or 0)
        if kind == "episode" and args.episode_id:
            if args.episode_id not in bucket["episode_admissions"]:
                bucket["episode_admissions"].append(args.episode_id)
        _atomic_write_json(daily_path, daily)

        # --- per-episode ledger ----------------------------------------------
        episode = None
        if args.episode_id:
            ep_path = _episode_path(state_dir, args.episode_id)
            episode = _read_json(ep_path, None) or _new_episode(args.episode_id, args.client)
            episode["usd"] = round(float(episode["usd"]) + call_usd, 6)
            if kind == "llm":
                episode["tokens"]["input"] += int(args.input_tokens)
                episode["tokens"]["output"] += int(args.output_tokens)
                episode["tokens"]["total"] = (episode["tokens"]["input"]
                                              + episode["tokens"]["output"])
            elif kind == "research":
                episode["research_calls"] += int(args.units or 1)
            elif kind == "image":
                episode["image_gens"] += int(args.units or 1)
            elif kind == "tts":
                episode["tts_chars"] += int(args.units or 0)
            line = {
                "at": _now_iso(),
                "kind": kind,
                "usd": round(call_usd, 6),
            }
            if args.note:
                line["note"] = args.note
            episode["lines"].append(line)
            _atomic_write_json(ep_path, episode)

    daily_hard = float(limits["per_client_daily_cost_usd_hard"])
    ep_hard = float(limits["per_episode_cost_usd_hard"])
    ep_soft = float(limits["per_episode_cost_usd_soft"])
    override_id = str(limits.get("override_episode_id", "") or "")
    override_active = bool(args.episode_id) and args.episode_id == override_id

    ep_usd = float(episode["usd"]) if episode else 0.0
    daily_usd = float(bucket["usd_total"])

    soft_exceeded = bool(episode) and ep_usd >= ep_soft
    hard_exceeded = bool(episode) and ep_usd >= ep_hard and not override_active
    daily_hard_exceeded = daily_usd >= daily_hard

    action = "continue"
    if hard_exceeded or daily_hard_exceeded:
        action = "cost_hold"
    elif soft_exceeded:
        action = "soft_warn"

    result = {
        "decision": "recorded",
        "kind": kind,
        "client": args.client,
        "episode_id": args.episode_id,
        "date": date_str,
        "recorded_usd": round(call_usd, 6),
        "episode_usd": round(ep_usd, 6),
        "daily_usd": round(daily_usd, 6),
        "soft_exceeded": soft_exceeded,
        "hard_exceeded": hard_exceeded,
        "daily_hard_exceeded": daily_hard_exceeded,
        "recommended_action": action,
    }
    if episode:
        result["episode_tokens"] = episode["tokens"]["total"]
        result["research_calls"] = episode["research_calls"]
    _emit(result, args)
    if hard_exceeded:
        return EXIT_EPISODE_HARD
    if daily_hard_exceeded:
        return EXIT_DAILY_HARD
    if soft_exceeded:
        return EXIT_SOFT
    return EXIT_OK


# ---------------------------------------------------------------------------
# Summary (read only; called at stage boundaries to enforce the soft-warn)
# ---------------------------------------------------------------------------
def do_summary(args):
    state_dir = args.state_dir
    limits = load_limits(args.config)
    date_str = _today(args.date)

    out = {"client": args.client, "date": date_str}
    exit_code = EXIT_OK

    if args.episode_id:
        episode = _load_episode(state_dir, args.episode_id) or _new_episode(
            args.episode_id, args.client)
        ep_usd = float(episode["usd"])
        ep_soft = float(limits["per_episode_cost_usd_soft"])
        ep_hard = float(limits["per_episode_cost_usd_hard"])
        override_id = str(limits.get("override_episode_id", "") or "")
        override_active = args.episode_id == override_id
        out["episode"] = {
            "episode_id": args.episode_id,
            "usd": round(ep_usd, 6),
            "tokens_total": episode["tokens"]["total"],
            "research_calls": episode["research_calls"],
            "research_cap": _effective_research_cap(limits, episode),
            "image_gens": episode["image_gens"],
            "tts_chars": episode["tts_chars"],
            "soft_ceiling": ep_soft,
            "hard_ceiling": ep_hard,
            "soft_exceeded": ep_usd >= ep_soft,
            "hard_exceeded": (ep_usd >= ep_hard) and not override_active,
            "override_active": override_active,
        }
        if out["episode"]["hard_exceeded"]:
            exit_code = EXIT_EPISODE_HARD
        elif out["episode"]["soft_exceeded"]:
            exit_code = EXIT_SOFT

    if args.client:
        daily = _read_json(_daily_path(state_dir, date_str), _new_daily(date_str))
        bucket = daily.get("clients", {}).get(args.client, {})
        daily_usd = float(bucket.get("usd_total", 0.0))
        admitted = len(set(bucket.get("episode_admissions", [])))
        cap = int(limits["per_client_daily_episode_cap"])
        daily_hard = float(limits["per_client_daily_cost_usd_hard"])
        out["daily"] = {
            "usd_total": round(daily_usd, 6),
            "usd_hard": daily_hard,
            "episodes_admitted": admitted,
            "episode_cap": cap,
            "episodes_remaining": max(0, cap - admitted),
            "smoke_probes": int(bucket.get("smoke_probes", 0)),
            "daily_hard_exceeded": daily_usd >= daily_hard,
        }
        if out["daily"]["daily_hard_exceeded"] and exit_code == EXIT_OK:
            exit_code = EXIT_DAILY_HARD

    _emit(out, args)
    return exit_code


# ---------------------------------------------------------------------------
# Grant a one-time research bonus (Guardrail 4 fabrication-fail supplemental).
# qc-attempt-gate owns WHEN to call this; the ledger owns the cap arithmetic.
# ---------------------------------------------------------------------------
def do_grant_research_bonus(args):
    _refuse_root_write(args.state_dir)
    state_dir = args.state_dir
    limits = load_limits(args.config)
    bonus = int(limits["web_research_bonus_on_fabrication_fail"])
    if not args.episode_id:
        _eprint("cost-ledger: grant-research-bonus requires --episode-id")
        return EXIT_USAGE
    with _locked(_lock_path(state_dir)):
        ep_path = _episode_path(state_dir, args.episode_id)
        episode = _read_json(ep_path, None) or _new_episode(args.episode_id, args.client or "unknown")
        already = int(episode.get("research_cap_bonus", 0)) > 0
        if not already:
            episode["research_cap_bonus"] = bonus
            _atomic_write_json(ep_path, episode)
    result = {
        "decision": "granted" if not already else "already_granted",
        "episode_id": args.episode_id,
        "bonus_calls": bonus,
        "effective_research_cap": _effective_research_cap(limits, episode),
    }
    _emit(result, args)
    return EXIT_OK


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------
def _emit(obj, args):
    sys.stdout.write(json.dumps(obj, indent=2, sort_keys=True) + "\n")


# ---------------------------------------------------------------------------
# Self test (deterministic, no network, temp state dir)
# ---------------------------------------------------------------------------
def do_self_test(_args):
    import tempfile

    passed = []
    failed = []

    def check(name, cond):
        (passed if cond else failed).append(name)

    tmp = tempfile.mkdtemp(prefix="podcast-ledger-selftest-")
    cost_model_path = os.path.join(tmp, "cost-model.json")
    _atomic_write_json(cost_model_path, {
        "usd_per_input_token": {"default": 0.000001},
        "usd_per_output_token": {"default": 0.000003},
        "usd_per_research_call": {"default": 0.01},
        "usd_per_image_gen": {"default": 0.04},
        "usd_per_tts_char": {"default": 0.000015},
        "usd_per_smoke_probe": {"default": 0.0},
    })

    class NS(object):
        pass

    def mk(**kw):
        ns = NS()
        ns.state_dir = tmp
        ns.config = None
        ns.cost_model = cost_model_path
        ns.client = "selftest"
        ns.episode_id = None
        ns.kind = None
        ns.input_tokens = 0
        ns.output_tokens = 0
        ns.units = 0
        ns.model = None
        ns.note = None
        ns.date = "2026-07-06"
        ns.json = True
        for k, v in kw.items():
            setattr(ns, k, v)
        return ns

    # Silence stdout during self test.
    real_stdout = sys.stdout
    devnull = open(os.devnull, "w")
    sys.stdout = devnull
    try:
        # 1. Output-token cap refusal.
        code = _run_guarded(do_precheck, mk(kind="llm", episode_id="ep1",
                                            output_tokens=9000, input_tokens=10))
        check("output-token cap refuses over 8000", code == EXIT_OUTPUT_CAP)

        # 2. Token budget refusal (single call above the episode budget).
        code = _run_guarded(do_precheck, mk(kind="llm", episode_id="ep1",
                                            input_tokens=500000, output_tokens=1))
        check("token budget refuses over 400000", code == EXIT_TOKEN_BUDGET)

        # 3. Normal llm precheck allows.
        code = _run_guarded(do_precheck, mk(kind="llm", episode_id="ep1",
                                            input_tokens=1000, output_tokens=500))
        check("normal llm precheck allows", code == EXIT_OK)

        # 4. Record accumulates tokens and dollars.
        _run_guarded(do_record, mk(kind="llm", episode_id="ep1",
                                   input_tokens=1000, output_tokens=500))
        ep = _read_json(_episode_path(tmp, "ep1"), {})
        check("record accumulates tokens", ep.get("tokens", {}).get("total") == 1500)
        check("record accumulates usd", round(ep.get("usd", 0), 6) == round(0.001 + 0.0015, 6))

        # 5. Research cap: 12 allowed, 13th refused.
        for _ in range(12):
            _run_guarded(do_record, mk(kind="research", episode_id="ep2", units=1))
        code = _run_guarded(do_precheck, mk(kind="research", episode_id="ep2", units=1))
        check("13th research call refused", code == EXIT_RESEARCH_CAP)

        # 6. Research bonus unlocks 4 more.
        _run_guarded(do_grant_research_bonus, mk(episode_id="ep2"))
        code = _run_guarded(do_precheck, mk(kind="research", episode_id="ep2", units=1))
        check("research bonus unlocks another call", code == EXIT_OK)

        # 7. Per-episode hard ceiling via a big TTS char count.
        code = _run_guarded(do_precheck, mk(kind="tts", episode_id="ep3", units=400000))
        check("per-episode hard ceiling refuses (tts)", code == EXIT_EPISODE_HARD)

        # 8. Daily episode cap: 3 admitted, 4th refused.
        for i in range(3):
            _run_guarded(do_record, mk(kind="episode", episode_id="cap%d" % i))
        code = _run_guarded(do_precheck, mk(kind="episode", episode_id="cap3"))
        check("4th episode of the day queued (cap)", code == EXIT_EPISODE_CAP)

        # 9. Already-admitted episode is idempotent (allow).
        code = _run_guarded(do_precheck, mk(kind="episode", episode_id="cap0"))
        check("already-admitted episode allowed", code == EXIT_OK)

        # 10. Override releases one episode past the per-episode hard ceiling.
        ov_cfg = os.path.join(tmp, "override.json")
        _atomic_write_json(ov_cfg, {"podcast_engine": {"limits": {
            "override_episode_id": "epov"}}})
        code = _run_guarded(do_precheck, mk(kind="tts", episode_id="epov",
                                            units=400000, config=ov_cfg))
        # Override releases the HARD ceiling; the soft ceiling still warns
        # (advisory), so a non-refusal result (ok or soft) is the pass.
        check("override releases one episode past hard ceiling",
              code in (EXIT_OK, EXIT_SOFT))
    finally:
        sys.stdout = real_stdout
        devnull.close()

    total = len(passed) + len(failed)
    report = {
        "self_test": "podcast-cost-ledger",
        "passed": len(passed),
        "total": total,
        "failed_checks": failed,
        "state_dir": tmp,
    }
    sys.stdout.write(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return EXIT_OK if not failed else EXIT_USAGE


def _run_guarded(fn, args):
    # Run a subcommand that may sys.exit and capture its exit code.
    try:
        rc = fn(args)
        return EXIT_OK if rc is None else rc
    except SystemExit as se:
        return int(se.code) if se.code is not None else EXIT_OK


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def build_parser():
    p = argparse.ArgumentParser(
        description="Podcast Production Engine cost ledger - the single "
                    "billable-call metering choke point (furnace Guardrails 3 and 4).")
    p.add_argument("--state-dir", default=_default_state_dir(),
                   help="podcast engine state directory")
    p.add_argument("--config", default=None, help="skill config path (limits)")
    p.add_argument("--cost-model", default=None, help="cost-model.json price table path")
    p.add_argument("--json", action="store_true", help="machine JSON output (default)")

    sub = p.add_subparsers(dest="cmd")

    def add_common(sp):
        sp.add_argument("--client", required=True)
        sp.add_argument("--episode-id", default=None)
        sp.add_argument("--kind", choices=KINDS, required=True)
        sp.add_argument("--input-tokens", type=int, default=0)
        sp.add_argument("--output-tokens", type=int, default=0)
        sp.add_argument("--units", type=int, default=0)
        sp.add_argument("--model", default=None)
        sp.add_argument("--date", default=None)

    sp_pre = sub.add_parser("precheck", help="check a call BEFORE it happens")
    add_common(sp_pre)

    sp_rec = sub.add_parser("record", help="record actual units AFTER a call")
    add_common(sp_rec)
    sp_rec.add_argument("--note", default=None)

    sp_sum = sub.add_parser("summary", help="read-only totals (stage boundary)")
    sp_sum.add_argument("--client", default=None)
    sp_sum.add_argument("--episode-id", default=None)
    sp_sum.add_argument("--date", default=None)

    sp_bonus = sub.add_parser("grant-research-bonus",
                              help="unlock one supplemental research pass")
    sp_bonus.add_argument("--client", default=None)
    sp_bonus.add_argument("--episode-id", required=True)

    sub.add_parser("self-test", help="run the deterministic self test")
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    # Normalize optional attributes so subcommand handlers can share one shape.
    for attr, default in (("note", None), ("date", None), ("model", None),
                          ("input_tokens", 0), ("output_tokens", 0), ("units", 0),
                          ("episode_id", None), ("client", None), ("kind", None),
                          ("json", True)):
        if not hasattr(args, attr):
            setattr(args, attr, default)

    if args.cmd == "precheck":
        return do_precheck(args)
    if args.cmd == "record":
        return do_record(args)
    if args.cmd == "summary":
        return do_summary(args)
    if args.cmd == "grant-research-bonus":
        return do_grant_research_bonus(args)
    if args.cmd == "self-test":
        return do_self_test(args)
    build_parser().print_help()
    return EXIT_USAGE


if __name__ == "__main__":
    try:
        sys.exit(main())
    except BrokenPipeError:  # pragma: no cover
        try:
            sys.stdout.close()
        except Exception:
            pass
        os._exit(EXIT_OK)
    except KeyboardInterrupt:  # pragma: no cover
        os._exit(130)
