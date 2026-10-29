#!/usr/bin/env python3
"""fleet_preflight.py -- the weekly update's pre-flight checks.

Runs BEFORE any install step. Any enforced failure means NO install on this box
this run: the caller exits with the documented status PAUSED-PREFLIGHT (never a
crash, never a half-changed box). Order: (a) account standing, (b) provider
standing, (c) storage, (d) memory pressure.

  fleet_preflight.py --phase standing --standing blocked   (a, from the shell gate)
  fleet_preflight.py --phase checks                        (b, c, d)
  fleet_preflight.py --phase early                         (c, d; the roll runner, before its snapshot)

Exit: 0 = proceed, 10 = PAUSED-PREFLIGHT (reasons on stdout, status in
<root>/fleet-preflight/status.json), 2 = bad arguments. Any other internal error
also exits 0 (fail open: a broken check never freezes a box; same stance as the
fleet standing gate).

Status vocabulary (status.json "status"): "proceed" | "paused-preflight".
Per check: "ok" | "fail" | "warn" | "paused" | "skipped"; providers add
"not-configured" and "external-check-not-wired".

FIRST-WEEK GRACE: standing and provider failures only warn (and notify) until
FLEET_PREFLIGHT_ENFORCE_FROM (UTC). Storage and memory are enforced immediately.

NOTICES: one note per issue per ISO week, through the client's own Telegram
agent (`openclaw message send`, never direct HTTP), to the owner chat from
.workforce-build-state.json, never an operator chat id, never while
ownerSendsHold is set, at most NOTE_CAP_PER_WEEK notes per week. Signed
"Steph, BlackCEO Fleet Manager". The client-facing name is Convert and Flow.

Never prints a key or secret.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

# --- named constants ---------------------------------------------------------
FLEET_PREFLIGHT_ENFORCE_FROM = date(2026, 11, 5)   # UTC; standing/provider checks pause from this day

GIB = 1024 ** 3
# Storage minimum = measured footprint of one update + safety margin. The
# 20261029 roll saw 1-2 GB of snapshot/doctor captures per box (worst case 2),
# the package installs (the OpenClaw npm package, a private Node runtime and the
# npm cache) are estimated at 1 GB, and the margin is 1 GB. The skills snapshot
# keeps its own dynamic check (2x the skills tree + 512 MB) in take_snapshot.
STORAGE_CAPTURES_MAX_BYTES = 2 * GIB
STORAGE_PACKAGE_INSTALLS_BYTES = 1 * GIB
STORAGE_SAFETY_MARGIN_BYTES = 1 * GIB
STORAGE_MIN_FREE_BYTES = STORAGE_CAPTURES_MAX_BYTES + STORAGE_PACKAGE_INSTALLS_BYTES + STORAGE_SAFETY_MARGIN_BYTES

# Memory pressure thresholds. Heavy when ANY of these trips.
MEM_FREE_PCT_MIN = 10            # system-wide free percentage below this (Mac memory_pressure; Linux MemAvailable)
MAC_PRESSURE_HEAVY_LEVELS = (2, 4)   # kern.memorystatus_vm_pressure_level: 1 normal, 2 warn, 4 critical
PSI_SOME_AVG60_MAX = 25.0        # Linux /proc/pressure/memory "some avg60" percent
PSI_FULL_AVG60_MAX = 5.0         # Linux /proc/pressure/memory "full avg60" percent
MEMORY_MAX_DEFERRALS = 3         # consecutive pressure-skipped runs; the next run proceeds (bounded retry)

EXTERNAL_STATUS_MAX_AGE_S = 8 * 24 * 3600   # a result older than a week plus a day is ignored
NOTE_CAP_PER_WEEK = 2            # client-message cap: at most this many preflight notes per box per week
SIGNATURE = "Steph, BlackCEO Fleet Manager"
EX_PAUSED = 10

GRACE_TEXT = ("Since this is the first week the system is running, I'm not holding back any of your updates. "
              "Starting next week, the full system goes into effect, and you'll get your latest updates "
              "once everything is resolved.")

PROVIDERS = {  # key -> name a client sees
    "openrouter": "OpenRouter",
    "ollama": "Ollama",
    "agnes": "Agnes AI",
    "kie": "kie.ai",
    "gemini": "the Gemini API key",
}
# ONE read point per provider for results produced by other systems. Each entry
# is read from the single standing file (see read_external_provider_standing).
EXTERNAL_STANDING_KEYS = {p: p for p in PROVIDERS}
# Providers that have a check in this repo: embedding_health's smoke embeds.
REPO_SMOKE = {"gemini": "gemini", "openrouter": "openrouter"}
_AUTH_BILLING = re.compile(r"\b(401|402|403|429)\b|quota|billing|credit|insufficient|depleted|exhausted|"
                           r"invalid.*key|api key|permission|unauthori[sz]ed|forbidden", re.I)


# --- small helpers -----------------------------------------------------------
def now_utc() -> datetime:
    v = os.environ.get("FLEET_PREFLIGHT_NOW")      # test seam: ISO date or datetime, UTC
    if v:
        return datetime.fromisoformat(v.replace("Z", "+00:00")).astimezone(timezone.utc) if "T" in v \
            else datetime.fromisoformat(v).replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc)


def grace_active(now: datetime | None = None) -> bool:
    return (now or now_utc()).date() < FLEET_PREFLIGHT_ENFORCE_FROM


def resolve_root(arg: str = "") -> Path:
    if arg:   # an explicit root always wins, even before it has an openclaw.json
        return Path(arg)
    for r in (os.environ.get("OPENCLAW_ROOT", ""), "/data/.openclaw", str(Path.home() / ".openclaw")):
        if r and (Path(r) / "openclaw.json").exists():
            return Path(r)
    return Path(os.environ.get("OPENCLAW_ROOT") or Path.home() / ".openclaw")


def _load_json(p: Path) -> dict:
    try:
        d = json.loads(p.read_text())
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _write_json(p: Path, d: dict) -> None:
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_name(p.name + f".tmp{os.getpid()}")
        tmp.write_text(json.dumps(d, indent=2, sort_keys=True))
        os.replace(tmp, p)
    except OSError:
        pass


def state_dir(root: Path) -> Path:
    return root / "fleet-preflight"


# --- (b) provider standing ---------------------------------------------------
def read_external_provider_standing(root: Path, provider: str) -> dict | None:
    """THE read point for provider results produced by other systems. One file,
    FLEET_PROVIDER_STANDING_FILE or <root>/provider-standing.json:
      {"<provider>": {"status": "ok"|"fail", "checked_at": "<ISO UTC>", "detail": "..."}}
    Returns the entry, or None when there is none (or it is stale/malformed)."""
    f = Path(os.environ.get("FLEET_PROVIDER_STANDING_FILE") or root / "provider-standing.json")
    ent = _load_json(f).get(EXTERNAL_STANDING_KEYS[provider])
    if not isinstance(ent, dict) or ent.get("status") not in ("ok", "fail"):
        return None
    try:
        age = now_utc().timestamp() - datetime.fromisoformat(str(ent.get("checked_at")).replace("Z", "+00:00")).timestamp()
    except (ValueError, TypeError):
        return None
    return ent if -3600 <= age <= EXTERNAL_STATUS_MAX_AGE_S else None


def _repo_smoke(provider: str, root: Path) -> tuple[str, str] | None:
    """The repo's own check, embedding_health's smoke embed. (status, detail), or
    None when the box has no key for it. A transient failure is "warn", never "fail"."""
    try:
        import embedding_health as eh  # type: ignore
        cfg = eh.load_openclaw_json(root)
        if provider == "gemini":
            key = eh._get_api_key("GOOGLE_API_KEY", cfg) or eh._get_api_key("GEMINI_API_KEY", cfg)
            fn = eh._smoke_embed_google
        else:
            key = eh._get_api_key("OPENROUTER_API_KEY", cfg)
            fn = eh._smoke_embed_openrouter
        if not key:
            return None
        ok, detail = fn(key)
    except Exception as e:  # noqa: BLE001 -- a broken check never blocks
        return "warn", f"check could not run ({e.__class__.__name__})"
    detail = re.sub(r"[A-Za-z0-9_-]{24,}", "<redacted>", str(detail))[:160]
    if ok:
        return "ok", detail
    return ("fail" if _AUTH_BILLING.search(detail) else "warn"), detail


def check_providers(root: Path) -> dict:
    out = {}
    for p in PROVIDERS:
        repo = _repo_smoke(p, root) if p in REPO_SMOKE else None
        if repo and repo[0] != "warn":
            out[p] = {"status": repo[0], "source": "repo-smoke", "detail": repo[1]}
            continue
        ext = read_external_provider_standing(root, p)
        if ext:
            out[p] = {"status": ext["status"], "source": "external", "detail": str(ext.get("detail", ""))[:160]}
        elif repo:   # inconclusive repo check, nothing external
            out[p] = {"status": "warn", "source": "repo-smoke", "detail": repo[1]}
        elif p in REPO_SMOKE:
            out[p] = {"status": "not-configured", "source": "none", "detail": "no key on this box"}
        else:
            out[p] = {"status": "external-check-not-wired", "source": "none",
                      "detail": "no repo check and no result at the external read point"}
    return out


# --- (c) storage -------------------------------------------------------------
def check_storage(root: Path) -> dict:
    ov = os.environ.get("FLEET_PREFLIGHT_FREE_BYTES")
    try:
        free = int(ov) if ov else shutil.disk_usage(root if root.exists() else root.parent).free
    except (OSError, ValueError) as e:
        return {"status": "warn", "detail": f"could not measure free space ({e.__class__.__name__})"}
    ok = free >= STORAGE_MIN_FREE_BYTES
    return {"status": "ok" if ok else "fail", "free_bytes": free, "required_bytes": STORAGE_MIN_FREE_BYTES,
            "detail": f"{free // 2**20} MB free, {STORAGE_MIN_FREE_BYTES // 2**20} MB needed"}


# --- (d) memory pressure -----------------------------------------------------
def _run(*cmd: str) -> str:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=15).stdout
    except (OSError, subprocess.SubprocessError):
        return ""


def memory_reading() -> dict:
    """{"free_pct", "level" (Mac), "psi_some", "psi_full"}; absent keys = not measurable."""
    r: dict = {}
    for env, key, cast in (("FLEET_PREFLIGHT_MEM_FREE_PCT", "free_pct", float),
                           ("FLEET_PREFLIGHT_MAC_LEVEL", "level", int),
                           ("FLEET_PREFLIGHT_PSI_SOME", "psi_some", float),
                           ("FLEET_PREFLIGHT_PSI_FULL", "psi_full", float)):
        if os.environ.get(env):
            r[key] = cast(os.environ[env])
    if r:
        return r
    if sys.platform == "darwin":
        m = re.search(r"free percentage:\s*(\d+)", _run("memory_pressure"))
        if m:
            r["free_pct"] = float(m.group(1))
        m = re.search(r"^\s*(\d+)\s*$", _run("sysctl", "-n", "kern.memorystatus_vm_pressure_level"), re.M)
        if m:
            r["level"] = int(m.group(1))
        return r
    try:   # Linux / Docker
        mi = {k: int(v) for k, v in re.findall(r"^(MemTotal|MemAvailable):\s+(\d+)", Path("/proc/meminfo").read_text(), re.M)}
        if mi.get("MemTotal"):
            r["free_pct"] = 100.0 * mi.get("MemAvailable", 0) / mi["MemTotal"]
        psi = Path("/proc/pressure/memory").read_text()
        for kind in ("some", "full"):
            m = re.search(rf"^{kind} avg10=\S+ avg60=([\d.]+)", psi, re.M)
            if m:
                r[f"psi_{kind}"] = float(m.group(1))
    except OSError:
        pass
    return r


def check_memory(root: Path, run_id: str, count: bool = True) -> dict:
    rd = memory_reading()
    why = []
    if rd.get("free_pct") is not None and rd["free_pct"] < MEM_FREE_PCT_MIN:
        why.append(f"free memory {rd['free_pct']:.0f}% < {MEM_FREE_PCT_MIN}%")
    if rd.get("level") in MAC_PRESSURE_HEAVY_LEVELS:
        why.append(f"memory pressure level {rd['level']} (warn/critical)")
    if rd.get("psi_some") is not None and rd["psi_some"] > PSI_SOME_AVG60_MAX:
        why.append(f"memory stall some avg60 {rd['psi_some']}% > {PSI_SOME_AVG60_MAX}%")
    if rd.get("psi_full") is not None and rd["psi_full"] > PSI_FULL_AVG60_MAX:
        why.append(f"memory stall full avg60 {rd['psi_full']}% > {PSI_FULL_AVG60_MAX}%")
    sf = state_dir(root) / "memory-deferrals.json"
    st = _load_json(sf)
    out = {"status": "ok", "reading": rd, "detail": "; ".join(why) or "normal"}
    if not why:
        if st.get("count"):
            _write_json(sf, {"count": 0, "run_id": run_id})
        return out
    if st.get("run_id") != run_id and count:
        st = {"count": int(st.get("count") or 0) + 1, "run_id": run_id}
        _write_json(sf, st)
    n = int(st.get("count") or 0)
    if n > MEMORY_MAX_DEFERRALS:   # bounded: after this many skipped runs, install anyway
        out.update(status="warn", detail=out["detail"] + f"; deferred {n - 1} runs already, proceeding (bound {MEMORY_MAX_DEFERRALS})")
    else:
        out.update(status="fail", deferrals=n)
    return out


# --- notices -----------------------------------------------------------------
def _operator_chat_ids() -> set:
    try:
        t = (HERE / "nudge-incomplete-interviews.py").read_text()
        return set(re.findall(r"\d{6,}", re.search(r"OPERATOR_CHAT_IDS\s*=\s*\{([^}]*)\}", t).group(1)))
    except (OSError, AttributeError):
        return set()


def _owner_chat(root: Path) -> str:
    for ws in (root / "workspace", root):
        c = str(_load_json(ws / ".workforce-build-state.json").get("ownerChat") or "").strip()
        if c:
            return c.replace("telegram:", "").replace("tg:", "")
    return ""


def _held(root: Path) -> bool:
    for ws in (root / "workspace", root):
        f = ws / ".workforce-build-state.json"
        if f.exists():
            return _load_json(f).get("ownerSendsHold") is True
    return False


def note_text(issue: str, detail: str = "", grace: bool = False) -> str:
    """Plain, ELI5, signed. Convert and Flow is the only product name used."""
    if issue == "storage":
        body = ("Your computer is running low on storage space, so I'm not installing this week's update yet. "
                "I'll let you know so your AI can help you free up space. Nothing is broken and nothing was changed.")
    elif issue == "memory":
        body = ("Your computer is busy right now. I'm waiting so nothing gets interrupted, "
                "and I'll try again at the next scheduled update.")
    elif issue == "standing":
        body = "I ran the account standing check for your update and it did not pass."
    else:
        body = f"I ran the connection check for {detail} and it did not pass."
    if issue in ("standing", "provider"):
        body += " " + (GRACE_TEXT if grace else
                       "I'm holding this week's update. Once everything is resolved, you'll get your latest updates.")
    return f"{body}\n\n- {SIGNATURE}"


def _week_key(now: datetime) -> str:
    y, w, _ = now.isocalendar()
    return f"{y}-W{w:02d}"


def send_note(root: Path, issue_key: str, text: str, now: datetime | None = None) -> str:
    """One note per issue per ISO week. Returns "sent", or the reason it was not."""
    now = now or now_utc()
    nf = state_dir(root) / "notices.json"
    led = _load_json(nf)
    wk = _week_key(now)
    week = led.get(wk) if isinstance(led.get(wk), dict) else {}
    if issue_key in week:
        return "already-noted-this-week"
    if len(week) >= NOTE_CAP_PER_WEEK:
        return "weekly-note-cap"
    chat = _owner_chat(root)
    if not chat:
        return "no-owner-chat"
    if chat in _operator_chat_ids():
        return "refused-operator-chat"
    if _held(root):
        return "owner-sends-hold"
    if os.environ.get("FLEET_PREFLIGHT_NO_SEND") == "1" or not shutil.which("openclaw"):
        return "not-sent-no-gateway-cli"
    try:
        r = subprocess.run(["openclaw", "message", "send", "--channel", "telegram", "--target", chat,
                            "--message", text, "--json"], capture_output=True, text=True, timeout=30)
        from interview_invitation import acknowledgement  # type: ignore
        ok = r.returncode == 0 and acknowledgement(json.loads(r.stdout), chat) is not None
    except Exception:  # noqa: BLE001
        ok = False
    if not ok:
        return "send-unverified"   # not recorded, so the next run may try again
    led = {wk: {**week, issue_key: now.strftime("%Y-%m-%dT%H:%M:%SZ")}}   # older weeks are dropped
    _write_json(nf, led)
    return "sent"


# --- orchestration -----------------------------------------------------------
def run(phase: str, root: Path, standing: str = "unknown", notify: bool = True, run_id: str = "") -> dict:
    now = now_utc()
    grace = grace_active(now)
    run_id = run_id or os.environ.get("FLEET_PREFLIGHT_RUN_ID") or str(os.getpid())
    checks: dict = {}
    pauses: list = []      # (issue_key, text, label)
    notes: dict = {}
    notes_q: list = []   # (issue key, text), in check order

    if phase == "standing":
        blocked = standing == "blocked"
        checks["standing"] = {"status": ("warn" if grace else "paused") if blocked else "ok", "verdict": standing}
        if blocked:
            notes_q.append(("standing", note_text("standing", "", grace)))
            if not grace:
                pauses.append("account standing")
    if phase == "checks":
        checks["providers"] = check_providers(root)
        for p, r in checks["providers"].items():
            if r["status"] == "fail":
                r["enforced"] = not grace
                notes_q.append((f"provider:{p}", note_text("provider", PROVIDERS[p], grace)))
                if not grace:
                    pauses.append(f"{PROVIDERS[p]} standing")
        checks["providers_grace_warn_only"] = grace
    if phase in ("checks", "early"):
        checks["storage"] = check_storage(root)
        if checks["storage"]["status"] == "fail":
            pauses.append("storage"); notes_q.append(("storage", note_text("storage")))
        checks["memory"] = check_memory(root, run_id)
        if checks["memory"]["status"] == "fail":
            pauses.append("memory pressure"); notes_q.append(("memory", note_text("memory")))
    if notify:
        for key, text in notes_q:
            notes[key] = send_note(root, key, text, now)
    status = "paused-preflight" if pauses else "proceed"
    res = {"status": status, "phase": phase, "checked_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
           "enforce_from": FLEET_PREFLIGHT_ENFORCE_FROM.isoformat(), "grace_active": grace,
           "pause_reasons": pauses, "checks": checks, "notices": notes}
    prev = _load_json(state_dir(root) / "status.json").get("checks") or {}
    _write_json(state_dir(root) / "status.json", {**res, "checks": {**prev, **checks}})
    return res


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--phase", choices=("standing", "checks", "early"), required=True)
    ap.add_argument("--standing", choices=("allowed", "blocked", "unknown"), default="unknown")
    ap.add_argument("--root", default="")
    ap.add_argument("--no-notify", action="store_true")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    try:
        res = run(a.phase, resolve_root(a.root), a.standing, not a.no_notify)
    except Exception as e:  # noqa: BLE001 -- fail open
        print(f"[fleet-preflight] internal error ({e.__class__.__name__}); proceeding (fail open)")
        return 0
    if a.json:
        print(json.dumps(res, indent=2, sort_keys=True))
    if res["status"] == "paused-preflight":
        print("FLEET-PREFLIGHT-PAUSED: " + ", ".join(res["pause_reasons"]))
        return EX_PAUSED
    for name, c in res["checks"].items():
        if isinstance(c, dict) and c.get("status") in ("warn",):
            print(f"[fleet-preflight] {name}: warn (grace or inconclusive) -- proceeding")
    print("[fleet-preflight] proceed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
