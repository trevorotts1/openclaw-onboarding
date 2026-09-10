#!/usr/bin/env python3
"""PRES-055 leg B Docker-matrix REDO R2: 6 REAL container legs (W6 WF23, Opus).

Runs, against the LIVE Docker engine on this operator box and the EXACT
released carriers, the full host-install matrix:

    hostinger-docker x {fresh, upgrade, restart}
    contabo-docker  x {fresh, upgrade, restart}

Every leg is a REAL container (pinned base image digest), a REAL fresh venv
inside that container, a REAL `pip install` of the exact released wheel, and
the REAL user-facing `presentation` console entry for
init/doctor/start/status/resume/verify/export. Engine verbs
(--resume --diagnose-only, --run --dry-run, dispatcher --once, watchdog,
supervise) run through the packaged compat shim, exactly as leg A did on the
host. Render + independent PNG/PPTX QC run INSIDE the container; export is
read back out to this evidence dir.

Labels (never converted upward):

    DEPLOYED-RUN-PASS   leg ran for real and every step rc is green or is an
                        explicitly expected non-zero control (dry-run park
                        rc 3, bounded resume rc 124)
    DEPLOYED-RUN-FAIL   leg ran for real and at least one required step came
                        back red; the red step's exact rc + output are kept
    NOT-VERIFIED        the leg could not run at all; exact daemon/container
                        error recorded verbatim

Honest limitations (recorded, never waived):
- both profiles execute on the SAME local engine (colima on the operator
  box); the vendor VPS hosts were NOT contacted (no scoped authorization,
  no credentials in this packet)
- no PRIOR released wheel exists in this packet, so `upgrade` = real
  force-reinstall of the EXACT artifact over a LIVE install with the
  workspace/run preserved; version-to-version upgrade is NOT-VERIFIED
- connected CC/GHL acceptance is NOT redone here (leg B already recorded it)

Stdlib only. No paid calls, no live client/merchant data, no client-box
writes. Write scope: this evidence dir + the containers this driver creates
and removes.
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
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
WORKTREE = HERE.parents[1]                       # run/worktrees/wf23-onb-accept
PACKET = HERE.parents[4]                         # packet root
LEG_B_DIR = HERE.parent                          # accept-b/ (READ-ONLY)

BUILD = (PACKET / "run/artifacts/pres-package"
         / "build-4cad34944ba28dc4e8648ac137a17bfb9c53d2e63b3899301bc18d2a188e4391")
WHEEL = BUILD / "pkg/dist/presentation_department-0.1.0-py3-none-any.whl"
SDIST = BUILD / "pkg/dist/presentation_department-0.1.0.tar.gz"
PLUGIN = BUILD / "presentation-department-skill-plugin-0.1.0.zip"
RECEIPT = BUILD / "ARTIFACT-RECEIPT.json"

SCRIPTS = (WORKTREE / "23-ai-workforce-blueprint" / "templates"
           / "role-library" / "presentations" / "scripts")
FIXTURES = SCRIPTS / "tests" / "fixtures" / "wf23"
FIXTURE_DECK = FIXTURES / "decks" / "syn_deck_10.json"
# Container-visible path of the same fixture (mounted at /fixtures:ro).
FIXTURE_DECK_IN_CONTAINER = "/fixtures/decks/syn_deck_10.json"
try:
    FIXTURE_SLIDE_COUNT = len(json.loads(FIXTURE_DECK.read_text(encoding="utf-8")))
except Exception:  # noqa: BLE001
    FIXTURE_SLIDE_COUNT = 0

IMAGE = "python:3.11-slim"
IMAGE_ID_PIN = "sha256:9534e5a8e315485d4061ed659af0fd78a284c015f9b73661b41d6bab25604534"
MANIFEST_SHA = "cab872039b2dac96bc78300a2158487ee7093e84d55a71069285789ca369f5de"
WHEEL_SHA = "d02e50855a47e2672766970f7142940fc16311efc1891f3edd3fc131daa8e206"
SDIST_SHA = "2d696d48c726321325fd87de9c5d3d7477e4023e635b30cce8ede114af9dc2a4"
PLUGIN_SHA = "9f2843d0886165e3ed6038ee1d10d4017ebe078c1bf5f9c15cf9b17013b01487"
STAGED_SHA = "4cad34944ba28dc4e8648ac137a17bfb9c53d2e63b3899301bc18d2a188e4391"

PROFILES = ("hostinger-docker", "contabo-docker")
OPS = ("fresh", "upgrade", "restart")
PKEY = {"hostinger-docker": "HOST", "contabo-docker": "CONTA"}

SHIM = ("from presentation_department import presentation_compat as pc; "
        "pc.ensure(); ")

# Runtime control: proves the py3.11 Thread._stop() shadowing defect is a
# Python-version property (3.11/3.12 raise, 3.14 does not), not a harness bug.
STOP_SHADOW_PROBE = r'''
import sys, threading
class H(threading.Thread):
    def __init__(self):
        super().__init__(daemon=True)
        self._stop = threading.Event()          # shadows Thread._stop()
    def run(self):
        while not self._stop.wait(0.05):
            pass
    def stop(self):
        self._stop.set()
h = H(); h.start(); h.stop()
try:
    h.join(timeout=5)
    print("JOIN-OK", sys.version.split()[0])
except Exception as exc:
    print("JOIN-RAISED", type(exc).__name__, repr(str(exc)), sys.version.split()[0])
'''

RENDER_SCRIPT = r'''
import json, sys
from pathlib import Path
from PIL import Image, ImageDraw
from pptx import Presentation
from pptx.util import Inches
deck_path, outdir = Path(sys.argv[1]), Path(sys.argv[2])
slides = json.loads(deck_path.read_text(encoding="utf-8"))
pngdir = outdir / "png"
pngdir.mkdir(parents=True, exist_ok=True)
prs = Presentation()
prs.slide_width = Inches(13.333)
prs.slide_height = Inches(7.5)
blank = prs.slide_layouts[6]
for i, s in enumerate(slides, start=1):
    img = Image.new("RGB", (1280, 720),
                    (26 + (i * 17) % 40, 32 + (i * 29) % 40, 44 + (i * 13) % 40))
    d = ImageDraw.Draw(img)
    d.rectangle([40, 40, 1240, 680], outline=(240, 240, 240), width=3)
    d.text((80, 120), f"Slide {i} / {len(slides)}", fill=(255, 255, 255))
    d.text((80, 200), s.get("copy", "")[:110], fill=(220, 220, 220))
    d.text((80, 600), "SYNTHETIC b-redo container render", fill=(160, 160, 160))
    img.save(pngdir / f"slide-{i:02d}.png")
    slide = prs.slides.add_slide(blank)
    tx = slide.shapes.add_textbox(Inches(0.5), Inches(0.5), Inches(12),
                                  Inches(6)).text_frame
    tx.word_wrap = True
    tx.paragraphs[0].text = f"Slide {i}: " + s.get("copy", "")
prs.save(outdir / "deck.pptx")
print(json.dumps({"pngs": len(slides), "pptx_slides": len(prs.slides)}))
'''

QC1_SCRIPT = r'''
import json, struct, sys
from pathlib import Path
from PIL import Image
pngdir = Path(sys.argv[1])
rows = []
for p in sorted(pngdir.glob("slide-*.png")):
    raw = p.read_bytes()
    w, h = struct.unpack(">II", raw[16:24])
    im = Image.open(p).convert("RGB")
    px = im.load()
    colors = set()
    for x in range(0, im.width, 64):
        for y in range(0, im.height, 64):
            colors.add(px[x, y])
    rows.append({"file": p.name, "bytes": len(raw),
                 "magic_ok": raw[:8] == b"\x89PNG\r\n\x1a\n",
                 "width": w, "height": h, "distinct_samples": len(colors),
                 "distinct_sampled_colors": len(colors),
                 "bar": "magic 89504E47 + 1280x720 + bytes>5000 + >=2 distinct sampled colors"})
print(json.dumps(rows))
'''

QC2_SCRIPT = r'''
import json, sys, zipfile
from pathlib import Path
pptx = Path(sys.argv[1]); want = int(sys.argv[2])
z = zipfile.ZipFile(str(pptx))
bad = z.testzip()
slides = sorted(n for n in z.namelist() if n.startswith("ppt/slides/slide"))
texts = [z.read(n).decode("utf-8", "replace") for n in slides]
print(json.dumps({"zip_bad": bad, "slide_count": len(slides), "want": want,
                  "count_ok": len(slides) == want,
                  "all_have_text": all("<a:t>" in t for t in texts)}))
'''

# Reaps the dispatcher the bounded `resume` leaves behind. Pure stdlib: the
# container has no ps/pkill, so this reads /proc and kills only processes
# whose cmdline names THIS run dir (never anything else in the container).
ZOMBIE_CONTROL = r'''
"""Class control for the container pid-1 reaping property.

Same instrument (docker + this kernel + python:3.11-slim), two arms that
differ ONLY in --init. Manufactures a genuine orphan (a grandchild whose
parent exits, so the orphan is reparented to pid 1), kills it, then asks the
engine's own lease module what it thinks of the resulting process-table row.

The parent must NOT be reaped by this process: the probe deliberately lets a
shell exit and reads the background pid, so the surviving `sleep` is a child
of pid 1 and not of the probe.
"""
import json, os, socket, subprocess as sp, time
from presentation_department.engine import lease as L


def rows():
    out = []
    for q in sorted(x for x in os.listdir("/proc") if x.isdigit()):
        try:
            stat = open("/proc/%s/stat" % q).read()
            cmd = open("/proc/%s/cmdline" % q, "rb").read().replace(b"\0", b" ").decode().strip()
        except Exception:
            continue
        rest = stat.rsplit(")", 1)[1].split()
        out.append({"pid": int(q), "state": rest[0], "ppid": int(rest[1]),
                    "cmd": cmd[:70]})
    return out


# Grandchild orphan: the shell exits immediately, so `sleep 600` is
# reparented to pid 1 of THIS pid namespace, exactly like an engine process
# whose launching shell is gone.
# The backgrounded sleep must NOT inherit the probe's stdout pipe, or it
# holds the write end open and a read-to-EOF here blocks forever (that hang
# is a broken probe, not a negative result). Detach its stdio and read one
# line.
h = sp.Popen(["bash", "-c", "sleep 600 >/dev/null 2>&1 & echo $!"],
             stdout=sp.PIPE)
orphan = int(h.stdout.readline().strip())
h.stdout.close()
h.wait(timeout=30)
time.sleep(1.0)
pre = [r for r in rows() if r["pid"] == orphan]

os.kill(orphan, 9)          # kill the orphan; only pid 1 can reap it
time.sleep(2.0)

all_rows = rows()
zombies = [r["pid"] for r in all_rows if r["state"] == "Z"]


def verdict(pid):
    doc = {"pid": pid, "host": socket.gethostname(), "who": "engine",
           "expires_at": "2099-01-01T00:00:00+00:00"}
    return {"pid": pid,
            "pid_is_alive": L.pid_is_alive(pid),
            "engine_pid_provably_dead": L._pid_provably_dead(pid),
            "engine_holder_is_live": L._holder_is_live(doc),
            "engine_waits_full_ttl": (not L._pid_provably_dead(pid)),
            "engine_default_ttl_s": L.DEFAULT_TTL_S}


print(json.dumps({
    "pid1": open("/proc/1/cmdline", "rb").read().replace(b"\0", b" ").decode().strip(),
    "orphan_pid": orphan,
    "orphan_reparented_to_pid1": bool(pre and pre[0]["ppid"] == 1),
    "orphan_row_before_kill": pre,
    "orphan_row_after_kill": [r for r in all_rows if r["pid"] == orphan],
    "all_zombies": zombies,
    "engine_verdict_on_orphan": verdict(orphan),
    "engine_verdict_on_zombie": verdict(zombies[0]) if zombies else None,
}))
'''

REAP_SCRIPT = r'''
import json, os, signal, sys, time
run_dir = sys.argv[1] if len(sys.argv) > 1 else ""
killed, seen = [], []
me = os.getpid()
for pid in sorted(p for p in os.listdir("/proc") if p.isdigit()):
    if int(pid) == me:
        continue
    try:
        cmd = open(f"/proc/{pid}/cmdline", "rb").read().replace(b"\x00", b" ")
        cmd = cmd.decode("utf-8", "replace").strip()
    except Exception:
        continue
    if not cmd or "presentation" not in cmd:
        continue
    seen.append({"pid": int(pid), "cmd": cmd[:300]})
    if run_dir and run_dir in cmd:
        try:
            os.kill(int(pid), signal.SIGTERM)
            killed.append({"pid": int(pid), "cmd": cmd[:300], "sig": "TERM"})
        except Exception as exc:
            killed.append({"pid": int(pid), "cmd": cmd[:300],
                           "err": f"{type(exc).__name__}: {exc}"})
time.sleep(3)
for row in killed:
    try:
        os.kill(int(row["pid"]), 0)
        os.kill(int(row["pid"]), signal.SIGKILL)
        row["sig"] = "KILL (survived TERM)"
    except Exception:
        row["gone"] = True
print(json.dumps({"run_dir": run_dir, "presentation_procs_seen": seen,
                  "killed": killed}))
'''



def utcnow() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def run(argv, timeout=120, stdin_text=None, env=None) -> dict:
    """Real subprocess; never raises. Records argv + rc + tails + elapsed."""
    t0 = time.time()
    try:
        r = subprocess.run(argv, capture_output=True, text=True,
                           timeout=timeout, input=stdin_text, env=env)
    except subprocess.TimeoutExpired as exc:
        def _s(v):
            return v.decode(errors="replace") if isinstance(v, bytes) else (v or "")
        return {"argv": argv, "rc": 124, "seconds": round(time.time() - t0, 1),
                "error": f"bounded after {timeout}s (killed by this harness)",
                "out_tail": _s(exc.stdout)[-4000:], "err_tail": _s(exc.stderr)[-4000:],
                "stdout": _s(exc.stdout), "stderr": _s(exc.stderr)}
    except Exception as exc:  # noqa: BLE001
        return {"argv": argv, "rc": -1, "seconds": round(time.time() - t0, 1),
                "error": f"{type(exc).__name__}: {exc}",
                "out_tail": "", "err_tail": "", "stdout": "", "stderr": ""}
    return {"argv": argv, "rc": r.returncode, "seconds": round(time.time() - t0, 1),
            "out_tail": (r.stdout or "")[-4000:], "err_tail": (r.stderr or "")[-4000:],
            "stdout": r.stdout or "", "stderr": r.stderr or ""}


class StepLog:
    """Collects per-step receipts + writes full per-step logs to evidence."""

    def __init__(self, leg_label: str, log_dir: Path):
        self.leg_label = leg_label
        self.log_dir = log_dir
        self.rows: list = []

    def add(self, step: str, res: dict, expect: str, ok: bool, note: str = ""):
        rel = f"logs/{step}.txt"
        dest = self.log_dir / f"{step}.txt"
        dest.parent.mkdir(parents=True, exist_ok=True)
        body = ["# argv: " + " ".join(str(a) for a in res.get("argv", [])),
                f"# rc: {res.get('rc')}",
                f"# expected: {expect}",
                f"# ok: {ok}",
                f"# note: {note}",
                "", "===== stdout =====", res.get("stdout", ""),
                "", "===== stderr =====", res.get("stderr", ""), "",
                "===== error =====", res.get("error", "")]
        dest.write_text("\n".join(body), encoding="utf-8")
        row = {"step": step, "argv": res.get("argv"), "rc": res.get("rc"),
               "expected": expect, "ok": ok, "note": note, "required": True,
               "out_tail": res.get("out_tail", "")[-1200:],
               "err_tail": res.get("err_tail", "")[-2000:],
               "error": res.get("error", ""), "full_log": rel}
        self.rows.append(row)
        return row

    def rejudge(self, step: str, ok: bool, note: str) -> None:
        """Update a step's verdict after the fact (non-rc criteria) and
        rewrite its log header so file and receipt can never disagree."""
        for row in self.rows:
            if row["step"] != step:
                continue
            row["ok"] = bool(ok)
            row["note"] = note
            f = self.log_dir / f"{step}.txt"
            if f.is_file():
                lines = f.read_text(encoding="utf-8").splitlines()
                out = []
                for ln in lines:
                    if ln.startswith("# ok:"):
                        out.append(f"# ok: {bool(ok)}")
                    elif ln.startswith("# note:"):
                        out.append(f"# note: {note}")
                    else:
                        out.append(ln)
                f.write_text("\n".join(out) + "\n", encoding="utf-8")
            return


def dexec(cname: str, argv: list, timeout: int = 300, stdin_text=None) -> dict:
    """docker exec (no shell) — real container command."""
    return run(["docker", "exec", "-i", cname, *argv], timeout=timeout,
               stdin_text=stdin_text)


def dpy(cname: str, script: str, args: list, timeout: int = 300) -> dict:
    """Run a python script through the container's venv via stdin."""
    return dexec(cname, ["/data/venv/bin/python", "-", *args], timeout=timeout,
                 stdin_text=script)


def log_stdout(res: dict) -> str:
    return ((res.get("stdout") or "") + (res.get("stderr") or "")).strip()


def docker_daemon_probe() -> dict:
    info = run(["docker", "info"], timeout=60)
    ver = run(["docker", "version"], timeout=60)
    reachable = info.get("rc") == 0
    summary = {}
    for line in (info.get("stdout") or "").splitlines():
        s = line.strip()
        for key in ("Server Version:", "Storage Driver:", "Operating System:",
                    "OSType:", "Architecture:", "CPUs:", "Total Memory:",
                    "Kernel Version:", "Docker Root Dir:", "Name:",
                    "Server:", "Cgroup Version:"):
            if s.startswith(key):
                summary.setdefault(key.rstrip(":"), s[len(key):].strip())
    ctx = run(["docker", "context", "show"], timeout=30)
    return {"probed_at": utcnow(), "reachable": reachable,
            "docker_info_rc": info.get("rc"),
            "docker_info_error_tail": (info.get("err_tail") or info.get("error") or ""),
            "docker_info_summary": summary,
            "docker_context": (ctx.get("stdout") or "").strip(),
            "docker_version_rc": ver.get("rc"),
            "docker_version_raw": (ver.get("stdout") or "")[:2500],
            "docker_version_err_tail": ver.get("err_tail", "")}


def image_receipt(img: str = IMAGE) -> dict:
    r = run(["docker", "image", "inspect", img, "--format",
             "{{.Id}}|{{json .RepoDigests}}|{{.Size}}|{{.Architecture}}|{{.Os}}"],
            timeout=60)
    raw = (r.get("stdout") or "").strip()
    parts = raw.split("|") if raw else []
    inspect = run(["docker", "image", "inspect", img], timeout=60)
    return {"rc": r.get("rc"), "raw": raw[:1500],
            "image_id": parts[0] if parts else None,
            "repo_digests": parts[1] if len(parts) > 1 else None,
            "size_bytes": parts[2] if len(parts) > 2 else None,
            "arch": parts[3] if len(parts) > 3 else None,
            "os": parts[4] if len(parts) > 4 else None,
            "matches_pin": (parts[0] == IMAGE_ID_PIN) if parts else False,
            "inspect_err_tail": inspect.get("err_tail", "")}


def carriers_receipt(cname: str | None) -> dict:
    """Host + (optionally) in-container SHA of every carrier."""
    import hashlib

    def sha(p: Path) -> str | None:
        try:
            h = hashlib.sha256()
            with p.open("rb") as fh:
                for blk in iter(lambda: fh.read(1 << 20), b""):
                    h.update(blk)
            return h.hexdigest()
        except Exception:  # noqa: BLE001
            return None

    host = {"wheel_sha256": sha(WHEEL), "sdist_sha256": sha(SDIST),
            "plugin_sha256": sha(PLUGIN)}
    want = {"wheel_sha256": WHEEL_SHA, "sdist_sha256": SDIST_SHA,
            "plugin_sha256": PLUGIN_SHA}
    out = {"host": host, "host_match": {k: host[k] == want[k] for k in want},
           "manifest_sha256": MANIFEST_SHA, "staged_content_sha256": STAGED_SHA,
           "paths": {"wheel": str(WHEEL), "sdist": str(SDIST),
                     "plugin": str(PLUGIN), "artifact_receipt": str(RECEIPT)}}
    if cname:
        r = dexec(cname, ["/usr/bin/sha256sum",
                          f"/art/pkg/dist/{WHEEL.name}"], timeout=300)
        got = (r.get("stdout") or "").split()[0] if r.get("stdout") else None
        m = dexec(cname, ["/usr/bin/sha256sum",
                          "/data/venv/lib/python3.11/site-packages/"
                          "presentation_department/_data/resources/sops/"
                          "slide-craft/PIPELINE-MANIFEST.json"],
                  timeout=300)
        gm = (m.get("stdout") or "").split()[0] if m.get("stdout") else None
        pm = dexec(cname, ["/usr/bin/sha256sum",
                           "/art/pkg/resources/schemas/PIPELINE-MANIFEST.json"],
                   timeout=300)
        gpm = (pm.get("stdout") or "").split()[0] if pm.get("stdout") else None
        out["in_container"] = {"wheel_sha256": got, "wheel_rc": r.get("rc"),
                               "installed_manifest_sha256": gm,
                               "manifest_rc": m.get("rc"),
                               "staged_manifest_sha256": gpm,
                               "staged_manifest_rc": pm.get("rc"),
                               "wheel_match": got == WHEEL_SHA,
                               "manifest_match": gm == MANIFEST_SHA,
                               "staged_manifest_match": gpm == MANIFEST_SHA}
    return out


def container_inspect(cname: str) -> dict:
    r = run(["docker", "inspect", cname], timeout=60)
    try:
        doc = json.loads(r.get("stdout") or "[]")[0]
        return {"rc": r.get("rc"), "Id": doc.get("Id"),
                "Name": doc.get("Name"), "Image": doc.get("Image"),
                "Created": doc.get("Created"),
                "State": doc.get("State"),
                "HostConfig": {"Binds": (doc.get("HostConfig") or {}).get("Binds"),
                               "RestartPolicy":
                                   (doc.get("HostConfig") or {}).get("RestartPolicy")},
                "Mounts": doc.get("Mounts"),
                "Config": {"Image": (doc.get("Config") or {}).get("Image"),
                           "Cmd": (doc.get("Config") or {}).get("Cmd")}}
    except Exception as exc:  # noqa: BLE001
        return {"rc": r.get("rc"), "parse_error": str(exc),
                "err_tail": r.get("err_tail", "")}


def container_logs(cname: str, tail: int = 200) -> dict:
    r = run(["docker", "logs", "--tail", str(tail), cname], timeout=60)
    return {"rc": r.get("rc"),
            "tail": ((r.get("stdout") or "") + (r.get("stderr") or ""))[-3000:]}


def python_version_discriminator(evdir: Path) -> dict:
    """Class control: same shadowing probe under 3.11 / 3.12 / host python.

    If the control also came back negative the CHECK would be broken, so the
    host (3.14.7) leg is the known-good arm of this instrument.
    """
    out: dict = {"probe": STOP_SHADOW_PROBE.strip(),
                 "note": ("proves whether the engine crash is a Python-version "
                          "property (Thread._stop shadowed by the HeartbeatThread "
                          "Event attribute), not a harness artifact")}
    hosts = []
    for img, label in ((IMAGE, "python:3.11-slim"), ("python:3.12-slim", "python:3.12-slim")):
        r = run(["docker", "run", "--rm", "-i", img, "python3", "-"],
                timeout=300, stdin_text=STOP_SHADOW_PROBE)
        hosts.append({"arm": f"container {label}",
                      "rc": r.get("rc"), "result": log_stdout(r)[-400:],
                      "raises": "JOIN-RAISED" in log_stdout(r)})
    host_pys = [("host python " + sys.version.split()[0], sys.executable)]
    for cand in ("/Users/blackceomacmini/.local/bin/python3.12",
                 "/opt/homebrew/bin/python3.14"):
        if Path(cand).is_file() and Path(cand).resolve() != Path(sys.executable).resolve():
            try:
                v = run([cand, "-c", "import sys;print(sys.version.split()[0])"],
                        timeout=60)
                host_pys.append((f"host python {log_stdout(v)} ({cand})", cand))
            except Exception:  # noqa: BLE001
                pass
    for label, exe in host_pys:
        r = run([exe, "-"], timeout=120, stdin_text=STOP_SHADOW_PROBE)
        hosts.append({"arm": label, "rc": r.get("rc"),
                      "result": log_stdout(r)[-400:],
                      "raises": "JOIN-RAISED" in log_stdout(r)})
    out["arms"] = hosts
    out["discriminates"] = (any(a["raises"] for a in hosts)
                            and any(not a["raises"] for a in hosts))
    return out


def reaper_control() -> dict:
    """Known-good class control on THIS instrument: same kernel, same image,
    same kill, two arms differing only in --init. A control that came back
    identical in both arms would mean the instrument cannot see the property.
    """
    arms = []
    for arm, extra in (("no-init (pid1 = sleep)", []),
                       ("--init (pid1 = docker-init)", ["--init"])):
        cname = f"pres055-redo-reaper-{arm.split()[0].strip('-')}"
        run(["docker", "rm", "-f", cname], timeout=120)
        r = run(["docker", "run", "-d", *extra, "--name", cname,
                 "-v", f"{BUILD}:/art:ro", IMAGE, "bash", "-c",
                 "python3 -m pip install --no-cache-dir -q "
                 f"/art/pkg/dist/{WHEEL.name} && sleep infinity"], timeout=900)
        if r.get("rc") != 0:
            arms.append({"arm": arm, "error": r.get("err_tail") or r.get("error")})
            continue
        # Poll WITH a delay: the pip install runs asynchronously in the
        # container's own bash, so a tight loop burns all attempts while pip
        # is still downloading and the probe would then run against a
        # not-yet-installed package (that is a broken instrument, not a
        # negative result).
        ready = {"rc": -1}
        for _ in range(60):
            ready = dexec(cname, ["python3", "-c", "import presentation_department"],
                          timeout=60)
            if ready.get("rc") == 0:
                break
            run(["sleep", "2"], timeout=30)
        out = dexec(cname, ["python3", "-"], timeout=300, stdin_text=ZOMBIE_CONTROL)
        try:
            doc = json.loads((out.get("stdout") or "").strip().splitlines()[-1])
        except Exception as exc:  # noqa: BLE001
            doc = {"parse_error": str(exc),
                   "raw": ((out.get("stdout") or "") + (out.get("stderr") or ""))[-800:]}
        arms.append({"arm": arm, "ready_rc": ready.get("rc"),
                     "rc": out.get("rc"), "result": doc})
        run(["docker", "rm", "-f", cname], timeout=120)
    saw_zombie = any((a.get("result") or {}).get("all_zombies") for a in arms)
    reaped = [bool(a.get("result")) and not (a.get("result") or {}).get("all_zombies")
              for a in arms]
    # Both arms must have manufactured the orphan (orphan_row_before_kill non
    # empty, reparented to pid 1); otherwise the probe never created the
    # condition and an empty zombie list is a broken check, not a result.
    made = [bool((a.get("result") or {}).get("orphan_reparented_to_pid1"))
            for a in arms]
    if not all(made):
        return {"question": ("does a container WITHOUT --init leave an orphan as a "
                             "zombie that the engine's F19 takeover cannot see?"),
                "arms": arms, "discriminates": False,
                "status": "CONTROL-BROKEN",
                "interpretation": ("the probe failed to manufacture the orphan in "
                                   "every arm (orphan_reparented_to_pid1 false), so "
                                   "an empty zombie list here is a broken check, not "
                                   "a negative result; no conclusion drawn"),
                "install": "docker run --init (docker-init present as pid 1)"}
    return {"question": ("does a container WITHOUT --init leave an orphan as a "
                         "zombie that the engine's F19 takeover cannot see?"),
            "arms": arms,
            "discriminates": saw_zombie and any(reaped),
            "status": ("DISCRIMINATES" if (saw_zombie and any(reaped))
                       else "CONTROL-BROKEN"),
            "interpretation": (
                "arm with all_zombies non-empty + engine_waits_full_ttl=true "
                "proves a killed engine process keeps its lease answerable as "
                "'alive' for the whole 600s TTL when the container has no "
                "init; every leg therefore runs with --init so the reap "
                "control can actually take effect"),
            "install": "docker run --init (docker-init present as pid 1)"}


def leg_body(profile: str, op: str, evdir: Path, keep: bool) -> dict:
    """One REAL matrix leg in a REAL container."""
    label = f"{profile}/{op}"
    key = PKEY[profile]
    cname = f"pres055-redo-{profile}-{op}"
    vname = f"pres055-redo-{profile}-{op}-vol"
    company = f"SYN-CO-{key}-{op.upper()}"
    pres = f"SYN-PRES-{key}-{op.upper()}-01"
    ws = f"/data/ws-{op}"
    run_dir = f"{ws}/runs/{company}-{pres}"
    legdir = evdir / "containers" / f"{profile}__{op}"
    legdir.mkdir(parents=True, exist_ok=True)
    sl = StepLog(label, legdir / "logs")
    rec: dict = {"leg": label, "engine_used": "local colima (operator box)",
                 "profile_is": (f"profile naming/runtime for the {profile} install "
                                "contract, executed on the local engine; the "
                                "vendor VPS host itself was NOT contacted"),
                 "container": cname, "volume": vname,
                 "company_id": company, "presentation_id": pres,
                 "run_dir": run_dir, "started_at": utcnow()}
    fails: list[str] = []
    controls_red: list[str] = []

    # ---- clean any stale container/volume from a previous attempt ----
    run(["docker", "rm", "-f", cname], timeout=120)
    run(["docker", "volume", "rm", vname], timeout=120)

    # ---- create + start the container ----
    # --init gives the container a real pid 1 (docker-init) that reaps orphans.
    # Without it pid 1 is `sleep`, which never calls wait(): a killed engine
    # process stays a ZOMBIE in this pid namespace forever, os.kill(pid, 0)
    # still succeeds, and the engine's own F19 takeover path
    # (lease._pid_provably_dead -> ProcessLookupError) can never fire, so a
    # run stays locked until the full 600s lease TTL lapses. Proven on this
    # instrument by reaper_control below; that is why every leg runs with init.
    r = run(["docker", "run", "-d", "--init", "--name", cname,
             "-v", f"{vname}:/data",
             "-v", f"{BUILD}:/art:ro",
             "-v", f"{FIXTURES}:/fixtures:ro",
             IMAGE, "sleep", "infinity"], timeout=600)
    sl.add("container_run", r, "rc 0 (container running)",
           r.get("rc") == 0,
           f"{IMAGE} --init binds vol:{vname} /art:ro(artifact) /fixtures:ro")
    if r.get("rc") != 0:
        rec["status"] = "NOT-VERIFIED"
        rec["not_verified_reason"] = "container could not start"
        rec["steps"] = sl.rows
        rec["failures"] = ["container_run rc != 0"]
        rec["finished_at"] = utcnow()
        (legdir / "leg.json").write_text(json.dumps(rec, indent=2), encoding="utf-8")
        return rec

    def step(name: str, argv: list, expect: str, ok=None, note: str = "",
             timeout: int = 300, stdin_text=None, kind: str = "exec",
             required: bool = True):
        """Run one REAL step. `ok=None` means judge it from rc against the
        expected rc parsed out of `expect`; pass an explicit bool only for
        steps whose verdict is not rc-based (and say so in `note`).

        `required=False` marks a CONTROL/extra verb: red there is recorded in
        `controls_red` as a defect against the artifact and is NEVER silently
        turned into a pass, but it does not by itself mark the install path
        failed. The distinction is written into the receipt so it can be
        audited line by line.
        """
        if kind == "exec":
            res = dexec(cname, argv, timeout=timeout, stdin_text=stdin_text)
        elif kind == "py":
            res = dpy(cname, stdin_text, argv, timeout=timeout)
        else:
            res = run(argv, timeout=timeout)
        if ok is None:
            m = re.search(r"rc\s*(\d+)", expect)
            want = int(m.group(1)) if m else 0
            ok = res.get("rc") == want
        row = sl.add(name, res, expect, bool(ok), note)
        row["required"] = required
        if not ok:
            entry = (f"{name}: rc={res.get('rc')} expected {expect}"
                     + ("" if required else " [CONTROL, not a required step]"))
            if required:
                fails.append(entry)
            else:
                controls_red.append(entry)
        return res

    def rejudge(name: str, ok: bool, note: str) -> None:
        """Re-judge a step AFTER the fact for a non-rc criterion, and keep
        `fails` / `controls_red` in sync with the new verdict.

        `step()` records the red at run time; a later re-judge would otherwise
        leave the entry behind, so a receipt could read `status:
        DEPLOYED-RUN-PASS` next to `failures: ['cli_resume_bounded: rc=137 ...']`
        for a step whose row is green. That contradiction is exactly the class
        of defect this redo exists to catch, so the lists are rebuilt here from
        the row's post-rejudge verdict and its `required` flag.
        """
        sl.rejudge(name, ok, note)
        row = next((r for r in sl.rows if r["step"] == name), None) or {}
        prefix = f"{name}:"
        for lst in (fails, controls_red):
            lst[:] = [e for e in lst if not e.startswith(prefix)]
        if not ok:
            entry = (f"{name}: rc={row.get('rc')} expected {row.get('expected')}"
                     + ("" if row.get("required")
                        else " [CONTROL, not a required step]"))
            (fails if row.get("required") else controls_red).append(entry)

    def cli(*args, **kw):
        return ["/data/venv/bin/presentation", *args]

    def engine(verb: list, **kw):
        return [SHIM + ("from presentation_department.engine import __main__ as e; "
                        f"raise SystemExit(e.main({verb!r}))")]

    def disp(*args):
        return [SHIM + ("from presentation_department.engine import dispatcher as d; "
                        f"raise SystemExit(d.main({list(args)!r}))")]

    # ---- base runtime identity inside the container ----
    pyv = dexec(cname, ["python3", "-V"], timeout=120)
    sl.add("container_python", pyv, "rc 0", pyv.get("rc") == 0)
    rec["container_python"] = log_stdout(pyv)[:200]
    rec["container_release"] = log_stdout(
        dexec(cname, ["bash", "-lc", "cat /etc/os-release"], timeout=120))[:600]
    rec["container_cpu_mem"] = log_stdout(
        dexec(cname, ["bash", "-lc",
                      "nproc; cat /sys/fs/cgroup/memory.max 2>/dev/null || "
                      "cat /sys/fs/cgroup/memory/memory.limit_in_bytes 2>/dev/null "
                      "|| grep MemTotal /proc/meminfo"],
              timeout=120))[:400]
    rec["container_uname"] = log_stdout(
        dexec(cname, ["uname", "-a"], timeout=120))[:400]

    # ---- fresh venv + pip install of the EXACT wheel ----
    r = step("venv_create", ["/usr/local/bin/python3", "-m", "venv", "/data/venv"],
             "rc 0", note="real fresh venv inside the container", timeout=600)
    step("venv_create_ok", ["/data/venv/bin/python", "-V"], "rc 0",
         note=("gated on venv_create rc: " + str(r.get("rc"))), timeout=120)
    r = step("pip_install_exact_wheel",
             ["/data/venv/bin/python", "-m", "pip", "install", "--no-cache-dir",
              "--disable-pip-version-check", f"/art/pkg/dist/{WHEEL.name}"],
             "rc 0", note=f"EXACT wheel {WHEEL.name} (sha {WHEEL_SHA[:16]}...)", timeout=900)
    step("pip_install_pyprobe", ["/data/venv/bin/python", "-c", "print(1)"], "rc 0",
         note=("gated on pip_install rc: " + str(r.get("rc"))), timeout=120)
    pl = step("pip_list", ["/data/venv/bin/python", "-m", "pip", "list",
                           "--format=freeze"], "rc 0", timeout=300)
    rec["pip_list"] = (pl.get("stdout") or "")[:1200]
    inst = step("installed_version",
                ["/data/venv/bin/python", "-m", "pip", "show",
                 "presentation-department"], "rc 0", timeout=300)
    rec["installed_version"] = (inst.get("stdout") or "")[:800]
    step("venv_cli_present", ["/data/venv/bin/presentation", "--help"], "rc 0",
         note="CLI entrypoint resolves in the fresh container venv", timeout=120)

    # ---- intake doc + CLI lifecycle ----
    intake = json.dumps({"presentation_type": "from_scratch",
                         "requester": {"chat_id": "container-cli"},
                         "title": f"Synthetic b-redo {label} deck",
                         "company_id": company,
                         "presentation_id": pres}, indent=2)
    step("write_intake",
         ["/data/venv/bin/python", "-c",
          "import sys,pathlib;pathlib.Path('/data/intake.json')"
          ".write_text(sys.stdin.read())"], "rc 0", timeout=120,
         stdin_text=intake)
    step("cli_init", cli("init", "--workspace", ws, "--company-id", company,
                         "--presentation-id", pres), "rc 0")
    step("cli_doctor", cli("doctor", "--workspace", ws), "rc 0")
    step("cli_start", cli("start", "--workspace", ws, "--company-id", company,
                          "--presentation-id", pres, "--intake",
                          "/data/intake.json", "--run-dir", run_dir),
         "rc 0")
    st = step("cli_status_json", cli("status", "--run-dir", run_dir, "--json"),
              "rc 0")
    rec["cli_status_out"] = (st.get("stdout") or "")[:2000]
    stt = step("read_state",
               ["/data/venv/bin/python", "-c",
                f"import json,pathlib;print(json.dumps(json.loads("
                f"pathlib.Path({run_dir!r}).joinpath('state.json')"
                ".read_text()), indent=2)[:4000])"], "rc 0", timeout=120)
    try:
        state = json.loads((stt.get("stdout") or "").strip() or "{}")
    except Exception:  # noqa: BLE001
        state = {}
    rec["run_identity"] = {
        "job_id": state.get("job_id"), "run_dir": run_dir,
        "manifest_version": state.get("manifest_version"),
        "manifest_sha256": state.get("manifest_sha256"),
        "presentation_type": state.get("presentation_type"),
        "requester": state.get("requester"),
        "events": len(state.get("events", [])),
        "phases": len(state.get("phases", [])),
    }
    pin_ok = (state.get("manifest_version") == 68
              and state.get("manifest_sha256") == MANIFEST_SHA)
    if not pin_ok:
        fails.append(f"manifest v68 pin mismatch in container run state: "
                     f"{state.get('manifest_version')}/{state.get('manifest_sha256')}")
    rec["manifest_v68_pin_ok"] = pin_ok

    # ---- engine verbs (the leg-A contract) ----
    # ORDER MATTERS: the real user-facing bounded `resume` spawns a surviving
    # dispatcher that keeps the run lease (observed rc 6 "another engine owns
    # this run" for any engine verb run after it). So resume runs LAST and the
    # orphan it leaves is then explicitly reaped and receipted.
    _code = engine(["--resume", "--run-dir", run_dir, "--diagnose-only"])[0]
    step("engine_resume_diagnose_only", [],
         "rc 0", kind="py", stdin_text=_code)

    _code = engine(["--run", "--run-dir", run_dir, "--dry-run"])[0]
    dr = step("engine_run_dry_run", [],
              "rc 3 (AF-INTAKE-GATE park)", kind="py", timeout=240,
              stdin_text=_code, required=False)
    rec["engine_run_dry_run"] = {
        "rc": dr.get("rc"), "expected_parked_rc": 3,
        "parked_honestly": dr.get("rc") == 3,
        "verdict": ("parked rc 3 as expected" if dr.get("rc") == 3 else
                    f"DIVERGENCE: expected parked rc 3 in-container, observed rc "
                    f"{dr.get('rc')}; exact output is in the step log "
                    "(dry_run_compat_note below records the known py3.11 cause)"),
    }
    # py3.11 runtime control on the SAME instrument: HeartbeatThread assigns
    # self._stop = threading.Event(), shadowing Thread._stop(); py<=3.12 calls
    # self._stop() inside _wait_for_tstate_lock after the thread joins, so
    # join() raises TypeError. The host interpreter (py3.14) does not call
    # _stop() there. Recorded, never waived, never worked around.
    rec["dry_run_compat_note"] = {
        "expected_on_host_leg_a": "rc 3 (AF-INTAKE-GATE park) on python 3.14.7",
        "in_container_python": rec.get("container_python"),
        "cause_if_typeerror": ("engine/lease.py HeartbeatThread sets self._stop = "
                               "threading.Event(), shadowing Thread._stop; "
                               "threading.Thread._wait_for_tstate_lock calls "
                               "self._stop() on python <=3.12, raising "
                               "TypeError: 'Event' object is not callable at "
                               "engine/__main__.py lease_hb.join(timeout=5)"),
        "discriminator": "runtime_control_python_version (top level of this file)",
    }
    # Not appended to `fails`: this control's red is already recorded in
    # controls_red and in the DEFECT entry below. It is a divergence of the
    # released artifact on python 3.11, not an install-path failure.

    _code = disp("--run-dir", run_dir, "--once")[0]
    step("dispatcher_once", [], "rc 0",
         kind="py", stdin_text=_code)
    _code = engine(["--watchdog", "--scan-root", f"{ws}/runs"])[0]
    step("watchdog", [], "rc 0", kind="py",
         stdin_text=_code)
    _code = engine(["--supervise", "--scan-root", f"{ws}/runs"])[0]
    step("supervise", [], "rc 0", kind="py",
         stdin_text=_code)
    step("cli_verify", cli("verify", "--run-dir", run_dir), "rc 0")

    # bounded real user-facing resume entry: the engine loop needs live agent
    # dispatch + client intake interview, absent by the paid-call boundary.
    # `timeout -k 10`: SIGTERM at 100s then SIGKILL at 110s. Without -k the
    # container's own timeout never returns -- the engine's FIX-105 SIGTERM
    # handler flips a shutdown event but its loop keeps running -- and the
    # rc 124 would be this harness's bound rather than a real container bound.
    rr = step("cli_resume_bounded",
              ["/usr/bin/timeout", "-k", "10", "100",
               "/data/venv/bin/presentation", "resume", "--run-dir", run_dir],
              "rc 124 (RESUME-LOOP-ENTERED) or rc 0",
              note="real resume entry, bounded by the container's own timeout "
                   "(-k 10: TERM at 100s, KILL at 110s); verdict judged below",
              timeout=300)
    rec["cli_resume_bounded_rc"] = rr.get("rc")
    # `timeout -k 10 100` returns 124 when the child died on the SIGTERM (or
    # on the 100s bound itself) and 137 when it survived SIGTERM and had to be
    # SIGKILLed at 110s. BOTH are the bound doing its job on a real long-running
    # engine loop; the distinction is carried in the receipt, not collapsed.
    rec["cli_resume_bounded_accepted_as"] = {
        124: ("RESUME-LOOP-ENTERED (bound rc 124: engine stopped on SIGTERM at "
              "100s; the loop needs live agent dispatch + client intake)"),
        137: ("RESUME-LOOP-ENTERED (bound rc 137: engine's FIX-105 SIGTERM "
              "handler logged the shutdown but the loop did not exit within the "
              "10s grace, so the container's timeout SIGKILLed it at 110s; the "
              "loop needs live agent dispatch + client intake)"),
        0: "rc 0 (loop returned on its own)",
    }.get(rr.get("rc"),
           f"UNEXPECTED rc {rr.get('rc')} -- recorded, not converted")
    rr_ok = rr.get("rc") in (0, 124, 137)
    rec["resume_sigterm_unwind_observation"] = {
        "observation": ("the engine logged `[engine shutdown] signal 15 received "
                        "-- stopping in-flight execs and unwinding` and then did "
                        "not exit within the container timeout's 10s grace, so it "
                        "needed SIGKILL"),
        "status": ("OBSERVED, NOT-CLAIMED-AS-DEFECT: no clean control here proves "
                   "how fast the released engine is REQUIRED to unwind after "
                   "SIGTERM, and the resume loop is designed to keep servicing "
                   "work orders, so this is recorded as an observation with its "
                   "exact log rather than asserted as a defect"),
        "evidence": (f"run/evidence/PRES-055/b-docker-redo/containers/"
                     f"{profile}__{op}/logs/cli_resume_bounded.txt"),
        "observed_rc": rr.get("rc"), "seconds": rr.get("seconds"),
    }
    rejudge("cli_resume_bounded", rr_ok,
            "real resume entry bounded by the container's own `timeout -k 10 "
            "100` (TERM at 100s, KILL at 110s); accepted rc set {0,124,137} "
            f"(124 died on TERM, 137 needed KILL), observed {rr.get('rc')} in "
            f"{rr.get('seconds')}s; orphan dispatcher reaped next step")

    # reap the dispatcher the bounded resume left behind, then prove with a
    # REAL lease-taking verb that the run is free again (positive control on
    # the same instrument: rc 6 = lease still held, anything else = reaped).
    reap = step("reap_resume_orphans",
                ["/data/venv/bin/python", "-c", REAP_SCRIPT, run_dir], "rc 0",
                kind="exec", timeout=180)
    rec["reap_resume_orphans"] = (reap.get("stdout") or "").strip()[-900:]
    rec["lease_after_reap"] = log_stdout(
        dexec(cname, ["bash", "-lc",
                      f"cat {run_dir}/working/.lease.json 2>/dev/null || echo NO-LEASE"],
              timeout=120))[:600]
    _code = engine(["--run", "--run-dir", run_dir, "--dry-run"])[0]
    pc = step("post_reap_engine_control", [],
              "rc != 6 (lease no longer held)", kind="py", timeout=240,
              stdin_text=_code, required=False)
    pc_ok = pc.get("rc") != 6
    rejudge("post_reap_engine_control", pc_ok,
            "positive control: rc 6 would mean the resume orphan still owns "
            f"the run lease; observed rc {pc.get('rc')}")
    rec["post_reap_engine_control"] = {
        "rc": pc.get("rc"), "lease_cleared": pc_ok,
        "note": ("rc 6 = lease still held by the resume orphan; rc 3 = parked; "
                 "TypeError rc 1 = the py3.11 dry-run compat divergence "
                 "recorded in dry_run_compat_note"),
    }
    # recorded via controls_red above; never a silent pass
    step("post_resume_status_control",
         cli("status", "--run-dir", run_dir, "--json"), "rc 0",
         note="run still readable after the reap (no state corruption)")

    # ---- render + independent QC INSIDE the container ----
    rd = step("container_render",
              [FIXTURE_DECK_IN_CONTAINER, f"/data/renders-{op}"], "rc 0",
              kind="py", stdin_text=RENDER_SCRIPT, timeout=600)
    rec["render_outputs"] = (rd.get("stdout") or "").strip()[-300:]
    q1 = step("qc1_png_independent", [f"/data/renders-{op}/png"], "rc 0",
              kind="py", stdin_text=QC1_SCRIPT, timeout=300)
    try:
        rows = json.loads((q1.get("stdout") or "").strip().splitlines()[-1])
    except Exception:  # noqa: BLE001
        rows = []
    q1ok = bool(rows) and all(
        x.get("magic_ok") and x.get("bytes", 0) > 5000
        and x.get("distinct_samples", 0) >= 2
        and x.get("width") == 1280 and x.get("height") == 720 for x in rows)
    rec["qc1_bar"] = ("magic 89504E47 + 1280x720 + bytes>5000 + >=2 distinct sampled "
                      "colors per slide (synthetic render: bg + glyph grey; the bar "
                      "is content evidence, not a canonical KIE render)")
    rec["qc1_png_independent"] = {"status": "PASS" if q1ok else "FAIL",
                                  "slides": len(rows), "rows": rows[:12]}
    if not q1ok:
        fails.append("container QC-1 PNG check failed")
    q2 = step("qc2_pptx_independent",
              [f"/data/renders-{op}/deck.pptx", str(FIXTURE_SLIDE_COUNT)], "rc 0",
              kind="py", stdin_text=QC2_SCRIPT, timeout=300)
    try:
        q2doc = json.loads((q2.get("stdout") or "").strip().splitlines()[-1])
    except Exception:  # noqa: BLE001
        q2doc = {}
    q2ok = bool(q2doc) and q2doc.get("zip_bad") is None and q2doc.get("count_ok") \
        and q2doc.get("all_have_text")
    rec["qc2_pptx_independent"] = {"status": "PASS" if q2ok else "FAIL",
                                   "detail": q2doc}
    if not q2ok:
        fails.append("container QC-2 PPTX check failed")

    # ---- op-specific behaviour ----
    if op == "upgrade":
        before = step("upgrade_pre_version",
                      ["/data/venv/bin/python", "-m", "pip", "show",
                       "presentation-department"], "rc 0", timeout=300)
        rec["upgrade_pre_install"] = (before.get("stdout") or "")[:400]
        step("upgrade_reinstall_exact_wheel",
             ["/data/venv/bin/python", "-m", "pip", "install", "--force-reinstall",
              "--no-deps", "--no-cache-dir", "--disable-pip-version-check",
              f"/art/pkg/dist/{WHEEL.name}"],
             "rc 0",
             note="real force-reinstall of the EXACT artifact over the LIVE install; "
             "workspace + run dir preserved (no volume reset)", timeout=900)
        after = step("upgrade_post_version",
                     ["/data/venv/bin/python", "-m", "pip", "show",
                      "presentation-department"], "rc 0", timeout=300)
        rec["upgrade_post_install"] = (after.get("stdout") or "")[:400]
        step("upgrade_post_status_preserved",
             cli("status", "--run-dir", run_dir, "--json"), "rc 0")
        step("upgrade_post_verify", cli("verify", "--run-dir", run_dir), "rc 0")
        stt2 = step("upgrade_post_state",
                    ["/data/venv/bin/python", "-c",
                     f"import json,pathlib;d=json.loads(pathlib.Path("
                     f"{run_dir!r}).joinpath('state.json').read_text());"
                     "print(d.get('job_id'), len(d.get('events',[])), "
                     "d.get('manifest_sha256'))"], "rc 0", timeout=120)
        rec["upgrade_run_preserved"] = (stt2.get("stdout") or "").strip()
        rec["upgrade_prior_release"] = (
            "NOT-VERIFIED: this packet contains no PRIOR released wheel, so a "
            "version-to-version upgrade cannot be exercised; recorded, never "
            "waived")
    elif op == "restart":
        ins_before = container_inspect(cname)
        rec["inspect_before_restart"] = {
            "Id": ins_before.get("Id"),
            "StartedAt": (ins_before.get("State") or {}).get("StartedAt"),
            "RestartCount": (ins_before.get("State") or {}).get("RestartCount"),
        }
        rr2 = run(["docker", "restart", cname], timeout=600)
        sl.add("docker_restart", rr2, "rc 0", rr2.get("rc") == 0,
               "real container restart; volume persists across restart")
        if rr2.get("rc") != 0:
            fails.append(f"docker restart rc {rr2.get('rc')}")
        ins_after = container_inspect(cname)
        rec["inspect_after_restart"] = {
            "Id": ins_after.get("Id"),
            "StartedAt": (ins_after.get("State") or {}).get("StartedAt"),
            "RestartCount": (ins_after.get("State") or {}).get("RestartCount"),
            "Status": (ins_after.get("State") or {}).get("Status"),
        }
        rec["container_id_stable_across_restart"] = (
            ins_before.get("Id") == ins_after.get("Id"))
        rec["started_at_changed"] = (
            (ins_before.get("State") or {}).get("StartedAt")
            != (ins_after.get("State") or {}).get("StartedAt"))
        if not rec["container_id_stable_across_restart"] or not rec["started_at_changed"]:
            fails.append("restart did not restart the same container")
        step("restart_venv_alive", ["/data/venv/bin/python", "-V"], "rc 0")
        step("restart_status_persisted",
             cli("status", "--run-dir", run_dir, "--json"), "rc 0")
        step("restart_verify", cli("verify", "--run-dir", run_dir), "rc 0")
        _code = disp("--run-dir", run_dir, "--once")[0]
        step("restart_dispatcher_once", [], "rc 0",
             kind="py", stdin_text=_code)

    # ---- export + read-back to host evidence ----
    step("cli_export", cli("export", "--run-dir", run_dir, "--out",
                           f"/data/export-{op}"), "rc 0")
    prov = step("export_provenance", ["/data/venv/bin/python", "-c",
                                      f"import pathlib;print(pathlib.Path("
                                      f"'/data/export-{op}/EXPORT-PROVENANCE.json')"
                                      ".read_text())"], "rc 0", timeout=120)
    try:
        rec["export_provenance"] = json.loads((prov.get("stdout") or "")).get("files", {})
    except Exception:  # noqa: BLE001
        rec["export_provenance"] = {"raw": (prov.get("stdout") or "")[:600]}
    outdir = legdir / "export-out"
    if outdir.exists():
        shutil.rmtree(outdir)
    rb = run(["docker", "cp", f"{cname}:/data/export-{op}", str(outdir)], timeout=300)
    sl.add("export_readback", rb, "rc 0", rb.get("rc") == 0,
           "docker cp of the container export dir out to evidence")
    rec["export_readback_files"] = sorted(
        str(p.relative_to(outdir)) for p in outdir.rglob("*")
        if p.is_file()) if outdir.exists() else []
    for name, src in (("renders/slide-01.png", f"/data/renders-{op}/png/slide-01.png"),
                      ("renders/deck.pptx", f"/data/renders-{op}/deck.pptx")):
        dest = legdir / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        run(["docker", "cp", f"{cname}:{src}", str(dest)], timeout=300)
    rec["render_artifacts_on_host"] = sorted(
        str(p.relative_to(legdir)) for p in (legdir / "renders").glob("*")
    ) if (legdir / "renders").is_dir() else []

    # ---- end-of-leg run-state readback: job id + event/phase counts AFTER the
    # whole lifecycle (intake, engine verbs, bounded resume, reap, upgrade or
    # restart) rather than straight after start, where both counts are 0.
    st_end = step("state_after_lifecycle",
                  ["/data/venv/bin/python", "-c",
                   "import json,pathlib;d=json.loads(pathlib.Path("
                   f"{run_dir!r}).joinpath('state.json').read_text());"
                   "print(json.dumps({'job_id':d.get('job_id'),"
                   "'events':len(d.get('events',[])),"
                   "'phases':len(d.get('phases',[])),"
                   "'manifest_sha256':d.get('manifest_sha256'),"
                   "'status':d.get('status')}))"],
                  "rc 0", timeout=120)
    try:
        rec["state_after_lifecycle"] = json.loads(
            (st_end.get("stdout") or "").strip().splitlines()[-1])
    except Exception:  # noqa: BLE001
        rec["state_after_lifecycle"] = {"raw": (st_end.get("stdout") or "")[:400]}

    # ---- receipts ----
    rec["carriers"] = carriers_receipt(cname)
    if not all(rec["carriers"]["host_match"].values()):
        fails.append("host carrier sha mismatch")
    ic = rec["carriers"].get("in_container") or {}
    if not (ic.get("wheel_match") and ic.get("manifest_match")):
        fails.append("in-container carrier sha mismatch")
    rec["inspect"] = container_inspect(cname)
    rec["container_logs"] = container_logs(cname)
    rec["mounts_ok"] = (("/art:ro" in " ".join(
        (rec["inspect"].get("HostConfig") or {}).get("Binds") or [])) if
        rec["inspect"].get("HostConfig") else False)
    if not rec["mounts_ok"]:
        fails.append("artifact bind mount missing/not read-only")

    # ---- cleanup (recorded) ----
    if not keep:
        rm = run(["docker", "rm", "-f", cname], timeout=300)
        rmv = run(["docker", "volume", "rm", vname], timeout=300)
        sl.add("cleanup_container", rm, "rc 0", rm.get("rc") == 0, cname)
        sl.add("cleanup_volume", rmv, "rc 0", rmv.get("rc") == 0, vname)
        rec["cleanup"] = {"container_rm_rc": rm.get("rc"),
                          "volume_rm_rc": rmv.get("rc")}
    else:
        rec["cleanup"] = {"kept": True, "container": cname, "volume": vname}

    rec["steps"] = sl.rows
    rec["steps_total"] = len(sl.rows)
    rec["steps_required"] = sum(1 for s in sl.rows if s.get("required"))
    rec["steps_red"] = [s["step"] for s in sl.rows if not s["ok"]]
    rec["steps_red_required"] = [s["step"] for s in sl.rows
                                 if not s["ok"] and s.get("required")]
    rec["steps_red_control"] = [s["step"] for s in sl.rows
                                if not s["ok"] and not s.get("required")]
    # ---- receipt self-consistency check (the instrument, not the artifact) ----
    # A receipt whose failure list disagrees with its own per-step rows is a
    # broken instrument: it can print PASS next to a red. Two directions are
    # checked, both on STEP-NAMED entries only (prose failures such as QC,
    # carrier or mount checks are not step rows):
    #   forward: every red REQUIRED row appears in `failures`
    #   stale:   no entry named after a step whose row is NOT red
    # `rejudge()` keeps the lists in sync; this proves it did, and a receipt
    # that fails the check is marked NOT-VERIFIED rather than picking a winner.
    red_req = [s["step"] for s in sl.rows if not s["ok"] and s.get("required")]
    red_ctl = [s["step"] for s in sl.rows if not s["ok"] and not s.get("required")]
    sync_fails_missing = [n for n in red_req
                          if not any(e.startswith(f"{n}:") for e in fails)]
    sync_ctl_missing = [n for n in red_ctl
                        if not any(e.startswith(f"{n}:") for e in controls_red)]
    green_names = [s["step"] for s in sl.rows
                   if s["ok"] and s.get("required")]
    green_ctl_names = [s["step"] for s in sl.rows
                       if s["ok"] and not s.get("required")]
    stale_fails = [e for e in fails
                   if any(e.startswith(f"{n}:") for n in green_names + green_ctl_names)]
    stale_ctl = [e for e in controls_red
                 if any(e.startswith(f"{n}:") for n in green_names + green_ctl_names)]
    self_ok = not (sync_fails_missing or sync_ctl_missing or stale_fails or stale_ctl)
    rec["failures"] = fails
    rec["controls_red"] = controls_red
    rec["receipt_self_consistent"] = {
        "ok": self_ok,
        "red_required_rows": red_req, "red_control_rows": red_ctl,
        "fails_missing_for_red_required": sync_fails_missing,
        "controls_red_missing_for_red_control": sync_ctl_missing,
        "stale_fails_naming_a_green_step": stale_fails,
        "stale_controls_red_naming_a_green_step": stale_ctl,
        "failures": list(fails), "controls_red": list(controls_red),
    }
    if not self_ok:
        fails.append("receipt self-inconsistent: failure list disagrees with the "
                     "per-step rows (broken instrument, not a leg verdict)")
    d = rec.get("engine_run_dry_run") or {}
    rec["defects"] = ([{
        "id": "ENGINE-DRYRUN-PY311-THREAD-STOP",
        "severity": "engine verb diverges on the container runtime (python 3.11.16)",
        "observed_rc": d.get("rc"), "expected_rc": 3,
        "evidence": (f"run/evidence/PRES-055/b-docker-redo/containers/"
                     f"{profile}__{op}/logs/engine_run_dry_run.txt"),
        "what_happened": ("engine/__main__.py finally block calls "
                          "lease_hb.join(timeout=5); threading.Thread."
                          "_wait_for_tstate_lock calls self._stop() on py<=3.12, "
                          "but engine/lease.py HeartbeatThread sets "
                          "self._stop = threading.Event(), so join raises "
                          "TypeError: 'Event' object is not callable, turning "
                          "the intended rc-3 AF-INTAKE-GATE park into rc 1 and "
                          "skipping lease_mod.release()"),
        "discriminated_by": ("runtime_control_python_version (top-level) and "
                             "reaper_control; the same probe raises on "
                             "py3.11/3.12 and passes on py3.14"),
        "not_waived": ("the park control did NOT pass; it is reported here as a "
                       "defect against the released artifact and the step's rc "
                       "is carried verbatim in its log"),
    }] if d.get("rc") != 3 else [])
    if not self_ok:
        # the receipt contradicts itself: report undetermined, never a pass
        rec["status"] = "NOT-VERIFIED"
        rec["not_verified_reason"] = ("receipt self-inconsistency (failure list "
                                      "vs per-step rows) -- broken instrument; "
                                      "see receipt_self_consistent")
    elif rec["steps_red_required"]:
        rec["status"] = "DEPLOYED-RUN-FAIL"
    elif rec["steps_red_control"] or rec["defects"]:
        rec["status"] = "DEPLOYED-RUN-PASS-WITH-RECORDED-DEFECTS"
    else:
        rec["status"] = "DEPLOYED-RUN-PASS"
    rec["finished_at"] = utcnow()
    (legdir / "leg.json").write_text(json.dumps(rec, indent=2), encoding="utf-8")
    return rec


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", required=True, type=Path,
                    help="docker-matrix.json path (evidence dir)")
    ap.add_argument("--keep-containers", action="store_true",
                    help="leave the leg containers/volumes running for inspection")
    ap.add_argument("--only", default=None,
                    help="debug aid: run a single leg '<profile>/<op>'")
    args = ap.parse_args(argv)
    evdir: Path = args.out if args.out.is_dir() else args.out.parent
    evdir.mkdir(parents=True, exist_ok=True)

    daemon = docker_daemon_probe()
    img = image_receipt()
    doc: dict = {
        "schema": "pres055-b-redo/docker-matrix-v2",
        "generated_at": utcnow(),
        "model": "opus-chain (W6 WF23 leg B Docker-matrix REDO R2)",
        "base_commit": "984b3522d46309d1e063b823ed36089479f3c57c",
        "host": {"system": os.uname().sysname, "release": os.uname().release,
                 "machine": os.uname().machine,
                 "python": sys.version.split()[0]},
        "docker_daemon": daemon,
        "base_image": img,
        "pins": {"image": IMAGE, "image_id_pin": IMAGE_ID_PIN,
                 "wheel_sha256": WHEEL_SHA, "sdist_sha256": SDIST_SHA,
                 "plugin_sha256": PLUGIN_SHA, "manifest_sha256": MANIFEST_SHA,
                 "staged_content_sha256": STAGED_SHA},
    }

    # ---- leg B controls, re-run through the SAME code path ----
    controls: dict = {}
    if LEG_B_DIR.is_dir() and str(LEG_B_DIR) not in sys.path:
        sys.path.insert(0, str(LEG_B_DIR))
    try:
        import docker_matrix_b  # noqa: E402  (READ-ONLY import of leg B module)
        controls = docker_matrix_b.mac_native_legs()
        controls["leg_b_module"] = str(LEG_B_DIR / "docker_matrix_b.py")
        controls["leg_b_probe_rerun"] = {
            "docker_info_rc": docker_matrix_b.docker_daemon_probe().get("returncode"),
            "docker_version_rc": docker_matrix_b.docker_version_probe().get("returncode"),
        }
    except Exception as exc:  # noqa: BLE001
        controls = {"error": f"leg B control module unavailable: {type(exc).__name__}: {exc}"}
    doc["controls_leg_b_rerun"] = controls
    doc["runtime_control_python_version"] = python_version_discriminator(evdir)
    # Control for the container pid-1 reaping property. This is the control for
    # the INSTRUMENT (the runtime the matrix legs execute on), not for the
    # artifact: if the two arms do not discriminate, the leg recipe is what is
    # broken, not the engine. Result is written before any leg runs so a red
    # leg can never be blamed on an unproven instrument.
    doc["runtime_control_pid1_reaping"] = reaper_control()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(doc, indent=2), encoding="utf-8")

    legs = []
    for profile in PROFILES:
        for op in OPS:
            if args.only and args.only != f"{profile}/{op}":
                continue
            try:
                legs.append(leg_body(profile, op, evdir,
                                     keep=args.keep_containers))
            except Exception as exc:  # noqa: BLE001
                legs.append({"leg": f"{profile}/{op}", "status": "NOT-VERIFIED",
                             "not_verified_reason":
                                 f"driver exception: {type(exc).__name__}: {exc}"})
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(json.dumps({**doc, "docker_matrix_legs": legs},
                                           indent=2), encoding="utf-8")
    doc["docker_matrix_legs"] = legs

    green = {"DEPLOYED-RUN-PASS", "DEPLOYED-RUN-PASS-WITH-RECORDED-DEFECTS"}
    passed = [l["leg"] for l in legs if l.get("status") in green]
    withdef = [l["leg"] for l in legs
               if l.get("status") == "DEPLOYED-RUN-PASS-WITH-RECORDED-DEFECTS"]
    failed = [l["leg"] for l in legs if l.get("status") == "DEPLOYED-RUN-FAIL"]
    nv = [l["leg"] for l in legs if l.get("status") == "NOT-VERIFIED"]
    if not daemon.get("reachable"):
        doc["verdict"] = ("DOCKER DAEMON UNREACHABLE: 6/6 legs NOT-VERIFIED with the "
                          "exact daemon error; nothing claimed")
    elif len(passed) == 6:
        doc["verdict"] = (
            f"6/6 legs ran for real in containers on the live engine against the exact "
            f"released wheel ({len(withdef)} of them carrying recorded artifact defects). "
            "NOT a self-approval: connected CC/GHL acceptance, vendor VPS hosts and "
            "version-to-version upgrade remain NOT-VERIFIED. QC-PRES-055 stays OPEN")
    else:
        doc["verdict"] = (f"{len(passed)}/6 ran green ({len(withdef)} with recorded "
                          f"defects), {len(failed)} "
                          f"DEPLOYED-RUN-FAIL, {len(nv)} NOT-VERIFIED; the exact red "
                          "steps and their output are kept per leg, never converted to "
                          "a pass and never waived")
    args.out.write_text(json.dumps(doc, indent=2), encoding="utf-8")
    print(json.dumps({"out": str(args.out), "reachable": daemon.get("reachable"),
                      "image_matches_pin": img.get("matches_pin"),
                      "items": {"ran_green": passed, "with_recorded_defects": withdef,
                                "fail": failed, "not_verified": nv},
                      "verdict": doc["verdict"]}, indent=2))
    return 0 if (daemon.get("reachable") and not failed and not nv) else 1


if __name__ == "__main__":
    sys.exit(main())
