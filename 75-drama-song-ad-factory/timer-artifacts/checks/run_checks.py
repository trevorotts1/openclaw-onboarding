#!/usr/bin/env python3
"""U6 — runnable checks for the persistent Drama Studio bridge timer.

Row U6: "Direct-shell persistent Mac/Hostinger/Contabo timer, no idle model
event, correct user/paths and restart state" (joint plan section 5, row U6).

Every check prints its TRUE exit code and is paired with a NEGATIVE CONTROL the
same instrument must reject — a check that cannot fail is not evidence. The
script exits 0 only when every good case passes AND every planted-bad case is
correctly rejected.

Run:
    python3 75-drama-song-ad-factory/timer-artifacts/checks/run_checks.py

Writes only inside its own scratch (tempfile.mkdtemp) and, for check E, a copy
of the artifact tree made inside that scratch. It never registers a timer and
never touches launchd, cron, systemd, pm2 or any real scheduling surface.
Stdlib only.
"""
from __future__ import annotations

import os
import plistlib
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)          # 75-drama-song-ad-factory/timer-artifacts
INSTALLER = os.path.join(ROOT, "install-timer.sh")
RUN_TIMER = os.path.join(ROOT, "run-timer.sh")

RESULTS: list[tuple[str, bool, str]] = []


def record(name: str, ok: bool, detail: str) -> bool:
    RESULTS.append((name, ok, detail))
    flag = "PASS" if ok else "FAIL"
    print(f"  [{name:>10}] {flag} exit={0 if ok else 1}  {detail}")
    return ok


def sh(args, **kw):
    return subprocess.run(args, capture_output=True, text=True, **kw)


# --------------------------------------------------------------------------- #
# rendering
# --------------------------------------------------------------------------- #
MAC = dict(
    __SCRIPT_PATH__="/Users/trevor/.openclaw/skills/75-drama-song-ad-factory/timer-artifacts/run-timer.sh",
    __LOG_PATH__="/Users/trevor/Library/Logs/openclaw/drama-studio-timer.log",
    __HOME__="/Users/trevor",
    __USER__="trevor",
    __PATH__="/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:/opt/homebrew/bin",
    __STORE_DIR__="/Users/trevor/.drama-studio",
    __INTERVAL__="120",
    __SCHEDULE__="",
)
HOSTINGER = dict(
    __SCRIPT_PATH__="/data/.openclaw/scripts/run-timer.sh",
    __LOG_PATH__="/data/.openclaw/logs/drama-studio-timer.log",
    __HOME__="/data",
    __USER__="node",
    __PATH__="/data/.npm-global/bin:/usr/local/bin:/usr/bin:/bin",
    __STORE_DIR__="/data/.drama-studio",
    __INTERVAL__="120",
    __SCHEDULE__="*/2 * * * *",
)
CONTABO = dict(
    __SCRIPT_PATH__="/home/node/.openclaw/scripts/run-timer.sh",
    __LOG_PATH__="/home/node/.openclaw/logs/drama-studio-timer.log",
    __HOME__="/home/node",
    __USER__="node",
    __PATH__="/home/node/.openclaw/npm-global/bin:/usr/local/bin:/usr/bin:/bin",
    __STORE_DIR__="/home/node/.openclaw/.drama-studio",
    __INTERVAL__="120",
    __SCHEDULE__="*/2 * * * *",
)

TEMPLATES = {
    "mac": os.path.join(ROOT, "mac", "com.blackceo.drama-studio-bridge.plist.template"),
    "hostinger": os.path.join(ROOT, "hostinger", "drama-studio-timer.cron.template"),
    "contabo": os.path.join(ROOT, "contabo", "drama-studio-timer.cron.template"),
}
VALUES = {"mac": MAC, "hostinger": HOSTINGER, "contabo": CONTABO}


def render(platform: str, values: dict | None = None) -> str:
    with open(TEMPLATES[platform], "r", encoding="utf-8") as fh:
        text = fh.read()
    for k, v in (values or VALUES[platform]).items():
        text = text.replace(k, v)
    return text


def cron_line(rendered: str) -> str:
    """The single executable (non-comment, non-blank) definition line."""
    lines = [ln for ln in rendered.splitlines()
             if ln.strip() and not ln.lstrip().startswith("#")]
    return lines[-1] if lines else ""


# --------------------------------------------------------------------------- #
# A — definitions parse as valid for the platform
# --------------------------------------------------------------------------- #
def a1_mac_plist_parses() -> bool:
    try:
        plistlib.loads(render("mac").encode("utf-8"))
        ok = True
        det = "rendered LaunchAgent parses"
    except Exception as e:  # noqa: BLE001
        ok, det = False, f"rendered plist did not parse: {e}"
    return record("A1 mac pars", ok, det)


def a1n_mac_plist_malformed_rejected() -> bool:
    bad = render("mac").replace("</dict>\n</plist>", "</plist>")  # close dict missing
    try:
        plistlib.loads(bad.encode("utf-8"))
        rejected = False
    except Exception:  # noqa: BLE001
        rejected = True
    return record("A1-neg", rejected, "malformed plist rejected non-zero" if rejected
                  else "malformed plist ACCEPTED (detector broken)")


# ---- strict cron field parse -------------------------------------------------
CRON_ITEM = re.compile(r"^(\*|\d+(-\d+)?)(/\d+)?$")
FIELD_BOUNDS = {"min": (0, 59), "hour": (0, 23), "dom": (1, 31),
                "mon": (1, 12), "dow": (0, 7)}


def cron_field_ok(field: str, lo: int, hi: int) -> bool:
    if not field:
        return False
    for item in field.split(","):
        if not CRON_ITEM.match(item):
            return False
        body, _, step = item.partition("/")
        if step and not (1 <= int(step) <= hi):
            return False
        if body == "*":
            continue
        for rng in body.split(","):
            a, _, b = rng.partition("-")
            try:
                va = int(a)
                vb = int(b) if b else va
            except ValueError:
                return False
            if not (lo <= va <= hi and lo <= vb <= hi and va <= vb):
                return False
    return True


def parse_cron(line: str) -> tuple[bool, str]:
    parts = line.split(None, 5)
    if len(parts) < 6:
        return False, f"expected 5 schedule fields + command, got {max(len(parts)-1,0)} fields"
    names = ["min", "hour", "dom", "mon", "dow"]
    for name, field in zip(names, parts[:5]):
        lo, hi = FIELD_BOUNDS[name]
        if not cron_field_ok(field, lo, hi):
            return False, f"bad {name} field '{field}'"
    cmd = parts[5].strip()
    if not cmd:
        return False, "empty command"
    if "/bin/sh" not in cmd or not re.search(r"/bin/sh\s+/\S+", cmd):
        return False, "command is not a direct '/bin/sh <abs script>' invocation"
    return True, "cron line parses"


def a2_hostinger_parses() -> bool:
    ok, det = parse_cron(cron_line(render("hostinger")))
    return record("A2 host pars", ok, det)


def a2n_hostinger_malformed_rejected() -> bool:
    line = cron_line(render("hostinger"))
    bad = " ".join(line.split()[:4]) + " /bin/sh /x"  # drop a schedule field
    ok, _ = parse_cron(bad)
    return record("A2-neg", not ok, "malformed (missing field) cron rejected" if not ok
                  else "malformed cron ACCEPTED (detector broken)")


def a3_contabo_parses() -> bool:
    ok, det = parse_cron(cron_line(render("contabo")))
    return record("A3 cont pars", ok, det)


def a3n_contabo_badtoken_rejected() -> bool:
    line = cron_line(render("contabo"))
    bad = line.replace("*/2", "*/a", 1)
    ok, _ = parse_cron(bad)
    return record("A3-neg", not ok, "malformed (bad step) cron rejected" if not ok
                  else "malformed cron ACCEPTED (detector broken)")


# --------------------------------------------------------------------------- #
# B — direct shell; no idle model event; no interactive session
# --------------------------------------------------------------------------- #
MODEL_TOKENS = ("claude", "claude-nine", "9router", "openclaw cron", "systemEvent",
                "agentIdle", "message", "--bg", "--watch", "--hook", "monitor")
INTERACTIVE_TOKENS = ("--interactive", " ssh ", "ssh -t", "tty", "-i ")


def invocation_text(platform: str) -> str:
    """Only the executable invocation, never the explanatory comments."""
    if platform == "mac":
        d = plistlib.loads(render("mac").encode("utf-8"))
        argv = " ".join(d.get("ProgramArguments", []))
        env = " ".join(f"{k}={v}" for k, v in d.get("EnvironmentVariables", {}).items())
        return argv + " " + env
    return cron_line(render(platform))


def b_direct_and_no_model(platform: str) -> bool:
    inv = invocation_text(platform)
    low = inv.lower()
    bad = [t for t in MODEL_TOKENS if t.lower() in low]
    inter = [t for t in INTERACTIVE_TOKENS if t.lower() in low]
    ok = not bad and not inter and "/bin/sh" in inv and "run-timer.sh" in inv
    det = "direct /bin/sh, no model/idle token, no interactive token"
    if bad:
        det = f"model/idle tokens present: {bad}"
    elif inter:
        det = f"interactive tokens present: {inter}"
    elif not ("/bin/sh" in inv and "run-timer.sh" in inv):
        det = "invocation is not a direct /bin/sh run-timer.sh"
    return record(f"B {platform[:4]} direct", ok, det)


def b_run_timer_is_noninteractive() -> bool:
    with open(RUN_TIMER, "r", encoding="utf-8") as fh:
        src = fh.read()
    # The words may appear in the comments; only the EXEC line must be clean.
    exec_lines = [ln for ln in src.splitlines()
                  if ln.strip().startswith("exec ")]
    exec_ok = any("python3" in ln or '"$PYTHON"' in ln for ln in exec_lines)
    forbidden_in_exec = any(t in " ".join(exec_lines).lower() for t in ("claude", "-i ", "ssh"))
    ok = exec_ok and not forbidden_in_exec
    return record("B script", ok,
                  "run-timer.sh execs python3 directly, no model/interactive token on the exec line"
                  if ok else "run-timer.sh exec line is not a clean direct python3 exec")


def b_neg_idle_event_rejected() -> bool:
    # A planted plist gated on a model idle event, calling claude interactively.
    bad = """<?xml version="1.0" encoding="UTF-8"?>
<plist version="1.0"><dict>
  <key>Label</key><string>com.blackceo.drama-studio-bridge</string>
  <key>ProgramArguments</key><array><string>/bin/sh</string>
    <string>-c</string><string>claude -p "check inbox"</string></array>
  <key>WatchPaths</key><array><string>/tmp/idle</string></array>
  <key>KeepAlive</key><true/>
</dict></plist>"""
    d = plistlib.loads(bad.encode("utf-8"))
    inv = " ".join(d.get("ProgramArguments", [])).lower()
    has_idle_trigger = "watchpaths" in bad.lower() or "keepalive" in bad.lower()
    has_model = "claude" in inv or "agentidle" in bad.lower()
    rejected = has_idle_trigger and has_model
    return record("B-neg", rejected,
                  "idle/model-event definition rejected (WatchPaths + claude)"
                  if rejected else "idle/model-event definition ACCEPTED (detector broken)")


# --------------------------------------------------------------------------- #
# C — user and path handling; wrong user or wrong path refused non-zero
# --------------------------------------------------------------------------- #
def identity(platform: str, user: str, home: str) -> int:
    r = sh(["bash", INSTALLER, "--platform", platform, "--check-identity",
            "--identity-user", user, "--identity-home", home])
    return r.returncode


def c_identity_rules() -> bool:
    real_user = subprocess.run(["id", "-un"], capture_output=True, text=True).stdout.strip()
    real_home = f"/Users/{real_user}"
    cases = [
        ("mac good", "mac", real_user, real_home, 0),
        ("mac bad-user", "mac", "root", "/var/root", 1),
        ("mac bad-path", "mac", real_user, "/Users/someone-else", 1),
        ("host good", "hostinger", "node", "/data", 0),
        ("host bad-user", "hostinger", "root", "/data", 1),
        ("cont good", "contabo", "node", "/home/node", 0),
        ("cont bad-user", "contabo", "root", "/home/node", 1),
        ("cont bad-path", "contabo", "node", "/tmp/node-home", 1),
    ]
    ok = True
    details = []
    for label, plat, user, home, want in cases:
        got = 0 if identity(plat, user, home) == 0 else 1
        good = (got == want)
        ok = ok and good
        details.append(f"{label}->{got}:{'ok' if good else 'BAD'}")
    return record("C identity", ok, " ".join(details))


# --------------------------------------------------------------------------- #
# D — restart state after reboot / login / kill
# --------------------------------------------------------------------------- #
def contabo_state_persistent(line: str) -> bool:
    """The single rule D rests on: Contabo state on the volume, not the throwaway $HOME."""
    return "DS_STATE_DIR=/home/node/.openclaw/.drama-studio" in line


def d_restart_state() -> bool:
    ok = True
    det = []
    # mac: RunAtLoad (login/reboot) + StartInterval (periodic), no KeepAlive
    d = plistlib.loads(render("mac").encode("utf-8"))
    if d.get("RunAtLoad") is not True:
        ok = False; det.append("mac: RunAtLoad missing")
    if int(d.get("StartInterval", 0)) != 120:
        ok = False; det.append("mac: StartInterval != 120")
    if "KeepAlive" in d:
        ok = False; det.append("mac: KeepAlive present (would re-run on exit)")
    if not d.get("EnvironmentVariables", {}).get("DS_STATE_DIR", "").startswith("/Users/"):
        ok = False; det.append("mac: state dir not under HOME")
    # hostinger: state under persistent /data
    h = cron_line(render("hostinger"))
    if "DS_STATE_DIR=/data/.drama-studio" not in h or "HOME=/data" not in h:
        ok = False; det.append("hostinger: state not on persistent /data")
    # contabo: state under the volume, NOT the ephemeral /home/node layer
    c = cron_line(render("contabo"))
    if not contabo_state_persistent(c):
        ok = False; det.append("contabo: state not on the persistent volume")
    return record("D restart", ok, " | ".join(det) or
                  "mac RunAtLoad+120s no-KeepAlive; host/cont state on persistent roots")


def d_neg_missing_runatload_rejected() -> bool:
    d = plistlib.loads(render("mac").encode("utf-8"))
    d.pop("RunAtLoad", None)
    rejected = d.get("RunAtLoad") is not True
    return record("D-neg1", rejected, "plist missing RunAtLoad rejected (no login/reboot run)"
                  if rejected else "plist without RunAtLoad ACCEPTED (detector broken)")


def d_neg_ephemeral_state_rejected() -> bool:
    bad = cron_line(render("contabo")).replace(
        "DS_STATE_DIR=/home/node/.openclaw/.drama-studio",
        "DS_STATE_DIR=/home/node/.drama-studio")
    rejected = not contabo_state_persistent(bad)
    return record("D-neg2", rejected,
                  "contabo state on ephemeral $HOME rejected" if rejected
                  else "ephemeral state ACCEPTED (detector broken)")


# --------------------------------------------------------------------------- #
# E — dry-run/self-test registers nothing and writes nothing outside scratch
# --------------------------------------------------------------------------- #
def snapshot(root: str) -> dict:
    snap = {}
    for dirpath, _dirs, files in os.walk(root):
        for f in files:
            p = os.path.join(dirpath, f)
            try:
                st = os.stat(p)
                snap[p] = (st.st_mtime_ns, st.st_size)
            except OSError:
                pass
    return snap


def real_mac_home() -> str:
    user = subprocess.run(["id", "-un"], capture_output=True, text=True).stdout.strip()
    return f"/Users/{user}"


def e_dry_run_writes_nothing(work: str, tree: str) -> bool:
    # Identity HOME stays the real one (so the contract passes); the install ROOT
    # is a scratch dir, so anything the path would write lands in scratch.
    fake_root = os.path.join(work, "fakehome")
    os.makedirs(fake_root, exist_ok=True)
    before = snapshot(work)
    r = sh(["bash", os.path.join(tree, "install-timer.sh"),
            "--platform", "mac", "--dry-run", "--root", fake_root, "--home", real_mac_home()])
    after = snapshot(work)
    wrote = set(after) - set(before) or any(before[k] != after[k] for k in before if k in after)
    ok = r.returncode == 0 and not wrote and os.listdir(fake_root) == []
    return record("E dry-run", ok,
                  "dry-run exit=0, no file created anywhere in scratch"
                  if ok else f"dry-run rc={r.returncode} created/changed files: {wrote}")


def e_neg_detector_sees_a_write(work: str, tree: str) -> bool:
    # The SAME detector must see a write when one really happens (--apply),
    # proving the E instrument is not vacuous.
    fake_root = os.path.join(work, "applyhome")
    os.makedirs(fake_root, exist_ok=True)
    before = snapshot(work)
    r = sh(["bash", os.path.join(tree, "install-timer.sh"),
            "--platform", "mac", "--apply", "--root", fake_root, "--home", real_mac_home()])
    after = snapshot(work)
    wrote = set(after) - set(before)
    ok = r.returncode == 0 and len(wrote) > 0
    return record("E-neg", ok,
                  f"apply detected {len(wrote)} written file(s) -> detector discriminates"
                  if ok else f"apply rc={r.returncode} wrote {len(wrote)} -> detector blind")


def e_no_registration_anywhere(work: str) -> bool:
    # Behaviorally: after a dry-run, the operator registration surface is empty.
    la = os.path.join(work, "fakehome", "Library", "LaunchAgents")
    crons = os.path.join(work, "fakehome", ".openclaw", "scripts")
    ok = not os.path.exists(la) and not os.path.exists(crons)
    return record("E register", ok,
                  "no LaunchAgent/crontab written by the dry-run path"
                  if ok else "dry-run created a registration surface")


# --------------------------------------------------------------------------- #
# G — the POLLER itself refuses a wrong user/path (not just the installer)
# --------------------------------------------------------------------------- #
def run_timer_env(work: str, overrides: dict) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    # The tree under test, never an installed copy: the poller must exercise
    # this checkout's bridge (its `capability --gate` is part of the contract).
    env.setdefault("DS_SKILL_ROOT", os.path.dirname(ROOT))
    env.update(overrides)
    return subprocess.run([RUN_TIMER], capture_output=True, text=True, env=env, cwd=work)


def g_poller_refuses_wrong_user_path(work: str) -> bool:
    home = real_mac_home()
    # A HOME-legal path that does not exist: run-timer.sh only READS pairing
    # files from it, and an unpaired box is the canonical `disabled` capability
    # (SPEC 9.3 / D24), so the poller exits 0 in silence and writes nothing —
    # never a key, never a URL, never anything that enrols a chat-only box.
    scratch_state = f"{home}/.drama-studio-selftest-{os.getpid()}"
    cases = [
        ("contabo user enforced on mac",
         {"DS_PLATFORM": "contabo", "HOME": home}, 1, "contabo:"),
        ("mac wrong state path",
         {"DS_PLATFORM": "mac", "HOME": home, "DS_STATE_DIR": "/tmp/nope"}, 1,
         "state dir must be under HOME"),
        ("mac good identity, unpaired -> quiet skip 0",
         {"DS_PLATFORM": "mac", "HOME": home, "DS_STATE_DIR": scratch_state}, 0,
         ""),
    ]
    ok = True
    det = []
    for label, env, want_rc, needle in cases:
        r = run_timer_env(work, env)
        good = r.returncode == want_rc and needle in (r.stderr or "")
        ok = ok and good
        det.append(f"{label}: rc={r.returncode}{'ok' if good else ' BAD'}")
    # D24: an idle optional poller must never fail repeatedly or enrol the
    # user to silence logs. Second tick: no repeated failure, no new
    # transition noise, and the state root holds no identity at all.
    r2 = run_timer_env(work, {"DS_PLATFORM": "mac", "HOME": home,
                              "DS_STATE_DIR": scratch_state})
    quiet = (r2.returncode == 0 and "not paired" not in (r2.stderr or "")
             and (r2.stderr or "") == "")
    files = sorted(os.listdir(scratch_state)) if os.path.isdir(scratch_state) else []
    no_identity = not any(f in files for f in ("machine.key", "machine.url"))
    ok = ok and quiet and no_identity
    det.append(f"second tick quiet={quiet} files={files or '[]'}{'ok' if quiet and no_identity else ' BAD'}")
    return record("G poller", ok, " | ".join(det))


# --------------------------------------------------------------------------- #
# F — no embedded credential, nothing printed
# --------------------------------------------------------------------------- #
SECRET_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9]{16,}"),
    re.compile(r"AKIA[0-9A-Z]{12,}"),
    re.compile(r"AIza[0-9A-Za-z_\-]{20,}"),
    re.compile(r"ghp_[A-Za-z0-9]{20,}"),
    re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}"),
    re.compile(r"DS_KEY\s*=\s*['\"]?[A-Za-z0-9_\-]{12,}"),
    re.compile(r"BEGIN [A-Z ]*PRIVATE KEY"),
]

SHIPPED = [
    "run-timer.sh", "install-timer.sh",
    "mac/com.blackceo.drama-studio-bridge.plist.template",
    "hostinger/drama-studio-timer.cron.template",
    "contabo/drama-studio-timer.cron.template",
]


def secret_found(text: str) -> str | None:
    for pat in SECRET_PATTERNS:
        m = pat.search(text)
        if m:
            return m.group(0)[:8] + "…"
    return None


def f_no_secret() -> bool:
    hits = []
    for rel in SHIPPED:
        with open(os.path.join(ROOT, rel), "r", encoding="utf-8") as fh:
            h = secret_found(fh.read())
        if h:
            hits.append(f"{rel}:{h}")
    ok = not hits
    return record("F no-secret", ok,
                  "no credential literal in any shipped timer file"
                  if ok else f"credential literal found: {hits}")


def f_neg_secret_detected() -> bool:
    planted = 'DS_KEY="sk-ABCDEFGHIJKLMNOP1234567890"\n'
    found = secret_found(planted)
    return record("F-neg", bool(found), "planted secret detected by same scanner"
                  if found else "planted secret MISSED (scanner broken)")


def f_references_env() -> bool:
    with open(RUN_TIMER, "r", encoding="utf-8") as fh:
        src = fh.read()
    ok = ("$KEY_FILE" in src and "export DS_KEY" in src and "machine.key" in src)
    return record("F env-ref", ok,
                  "run-timer.sh reads the key from its 0600 store and exports DS_KEY (env only)"
                  if ok else "run-timer.sh does not reference the env store")


# --------------------------------------------------------------------------- #
def main() -> int:
    print("U6 timer-artifacts checks")
    print(f"  root  : {ROOT}")
    if not os.path.isfile(INSTALLER) or not os.path.isfile(RUN_TIMER):
        print("  FATAL: installer/run-timer missing", file=sys.stderr)
        return 2

    work = tempfile.mkdtemp(prefix="ds-timer-check-")
    tree = os.path.join(work, "tree")
    try:
        shutil.copytree(ROOT, tree)
        print("  scratch:", work)

        try:
            run_checks(work, tree)
        except Exception as e:  # noqa: BLE001  — a broken artifact must FAIL, not traceback
            record("harness", False, f"check harness aborted: {type(e).__name__}: {e}")
    finally:
        shutil.rmtree(work, ignore_errors=True)

    passed = sum(1 for _, ok, _ in RESULTS if ok)
    total = len(RESULTS)
    print(f"\n{passed}/{total} checks passed")
    return 0 if passed == total else 1


def run_checks(work: str, tree: str) -> None:
    for fn in (
        a1_mac_plist_parses,
        a1n_mac_plist_malformed_rejected,
        a2_hostinger_parses,
        a2n_hostinger_malformed_rejected,
        a3_contabo_parses,
        a3n_contabo_badtoken_rejected,
        lambda: b_direct_and_no_model("mac"),
        lambda: b_direct_and_no_model("hostinger"),
        lambda: b_direct_and_no_model("contabo"),
        b_run_timer_is_noninteractive,
        b_neg_idle_event_rejected,
        c_identity_rules,
        d_restart_state,
        d_neg_missing_runatload_rejected,
        d_neg_ephemeral_state_rejected,
        lambda: e_dry_run_writes_nothing(work, tree),
        lambda: e_neg_detector_sees_a_write(work, tree),
        lambda: e_no_registration_anywhere(work),
        lambda: g_poller_refuses_wrong_user_path(work),
        f_no_secret,
        f_neg_secret_detected,
        f_references_env,
    ):
        fn()


if __name__ == "__main__":
    sys.exit(main())
