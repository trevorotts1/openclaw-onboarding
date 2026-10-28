#!/usr/bin/env python3
"""scripts/agent-browser-reaper.sh against a faked `ps`: profile scope, macOS ages, orphaned daemons, webhook, kill order.

A REAL run of the REAL script. HOME/TMPDIR are a temp dir, `agent-browser` is a no-op stub, and `ps` is a
shim that serves a fixture table (macOS style: no `etimes`, BSD `etime`; or Linux style). Only processes this
test spawns itself are ever signalled; every other row in the table is a fake command line with a fake pid.
"""
import http.server, json, os, shutil, signal, subprocess, tempfile, threading, time, unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
REAPER = REPO / "scripts" / "agent-browser-reaper.sh"
BASH = os.environ.get("REAPER_BASH", "bash")      # REAPER_BASH=/bin/bash runs it under the macOS system bash 3.2

PS_SHIM = r'''#!/usr/bin/env bash
# fake ps: FAKE_PS_TABLE has "PID PPID ETIME COMMAND..." rows; FAKE_PS_STYLE=mac|linux
spec=""; pidsel=""; list=0
while [ $# -gt 0 ]; do
  case "$1" in -axww|-ax|-A|-e) list=1 ;; -o) spec="$2"; shift ;; -p) pidsel="$2"; shift ;; esac
  shift
done
secs='function secs(e,  d,n,t){ d=0; if (e ~ /-/) { split(e,t,"-"); d=t[1]; e=t[2] } n=split(e,t,":"); return d*86400+(n==3?t[1]*3600+t[2]*60+t[3]:t[1]*60+t[2]) }'
if [ "$list" = 1 ]; then
  awk -v spec="$spec" 'BEGIN{n=split(spec,f,","); for(i=1;i<=n;i++) sub(/=.*/,"",f[i])}
    { c=$0; sub(/^[ \t]*[0-9]+[ \t]+[0-9]+[ \t]+[^ \t]+[ \t]+/,"",c); o="";
      for(i=1;i<=n;i++){ v=(f[i]=="pid")?$1:(f[i]=="ppid")?$2:(f[i]=="etime")?$3:c; o=o (i>1?" ":"") v } print o }' "$FAKE_PS_TABLE"
  exit 0
fi
row="$(awk -v p="$pidsel" '$1==p{print; exit}' "$FAKE_PS_TABLE")"
[ -n "$row" ] || exit 1
case "$spec" in
  etimes=) if [ "$FAKE_PS_STYLE" = mac ]; then echo "%cpu %mem acflag acflg args blocked caught comm command cpu cputime etime f flags gid lstart nice pcpu pid ppid rss start state stat time tty uid user vsz wchan xstat"; exit 1; fi
           echo "$row" | awk "$secs"' {print secs($3)}' ;;
  etime=)  echo "$row" | awk '{print $3}' ;;
  lstart=) echo "Mon Jan  1 00:00:00 2026" ;;
  *) exit 1 ;;
esac
'''
AB_STUB = "#!/usr/bin/env bash\nexit 0\n"


def sec(etime):
    day, _, rest = etime.rpartition("-") if "-" in etime else ("0", "", etime)
    parts = [int(x) for x in rest.split(":")]
    s = parts[-1] + 60 * parts[-2] + (3600 * parts[-3] if len(parts) == 3 else 0)
    return int(day) * 86400 + s


@unittest.skipIf(Path("/data/.openclaw").is_dir(), "refusing to run the reaper against a real /data/.openclaw")
class Reaper(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="abtest-")   # NOT "reaper": the daemon sweep skips any command line containing that word)
        self.home = self.tmp / "home"; (self.home / ".openclaw").mkdir(parents=True)
        self.oc = self.home / ".openclaw"
        self.bin = self.tmp / "bin"; self.bin.mkdir()
        for name, body in (("ps", PS_SHIM), ("agent-browser", AB_STUB)):
            (self.bin / name).write_text(body); (self.bin / name).chmod(0o755)
        self.spawned = []
    def tearDown(self):
        for pid in self.spawned:
            try: os.kill(pid, signal.SIGKILL)
            except OSError: pass
        shutil.rmtree(self.tmp, ignore_errors=True)

    # -- helpers -------------------------------------------------------------------------------
    def spawn(self, ignore_term=False):
        """A real sleeper that is reparented away from this test (so a kill leaves no zombie)."""
        code = "import signal,time\n" + ("signal.signal(signal.SIGTERM, signal.SIG_IGN)\n" if ignore_term else "") + "time.sleep(300)"
        out = subprocess.run(["bash", "-c", "python3 -c '%s' >/dev/null 2>&1 & echo $!" % code], capture_output=True, text=True).stdout
        pid = int(out.strip()); self.spawned.append(pid)
        return pid
    def alive(self, pid, wait=4.0):
        end = time.time() + wait
        while time.time() < end:
            try: os.kill(pid, 0)
            except OSError: return False
            time.sleep(0.1)
        return True
    def run_reaper(self, rows, style="mac", dry=True, env=None, lease=False):
        table = self.tmp / "ps.table"
        table.write_text("".join("%s %s %s %s\n" % r for r in rows))
        if lease:
            leases = self.tmp / "tmp" / "agent-browser" / "leases"; leases.mkdir(parents=True, exist_ok=True)
            (leases / "live.lease").write_text(json.dumps({"started_epoch": int(time.time()), "ttl_sec": 999999}))
        e = dict(os.environ, HOME=str(self.home), TMPDIR=str(self.tmp / "tmp"), PATH="%s:%s" % (self.bin, os.environ["PATH"]),
                 FAKE_PS_TABLE=str(table), FAKE_PS_STYLE=style, AB_REAPER_DRY_RUN="1" if dry else "0", AB_STOP_GRACE_S="1",
                 AB_MAX_LIVE="99")
        for k in ("AB_PROC_HARD_AGE_MIN", "RESCUE_RANGERS_WEBHOOK_URL", "RESCUE_RANGERS_WEBHOOK_SECRET"): e.pop(k, None)
        e.update(env or {})
        (self.tmp / "tmp").mkdir(exist_ok=True)
        r = subprocess.run([BASH, str(REAPER)], capture_output=True, text=True, env=e, timeout=120)
        return r, r.stdout + r.stderr
    def would(self, out):
        """pids the dry run planned to signal."""
        import re
        return {int(m) for m in re.findall(r"would SIGTERM then \(after grace\) SIGKILL .*? pid (\d+)", out)}

    OLD = "7-12:30:45"   # 649845 s
    def chrome(self, pid, flags, etime=OLD, ppid=1, exe="/Applications/Chromium.app/Contents/MacOS/Chromium --headless"):
        return (pid, ppid, etime, "%s %s" % (exe, flags))

    # -- 1. profile scope ----------------------------------------------------------------------
    def test_current_agent_browser_profile_path_is_scoped(self):
        rows = [self.chrome(41001, "--user-data-dir=%s/tmp/agent-browser-chrome-8f3a1c" % self.oc)]
        r, out = self.run_reaper(rows, style="linux")
        self.assertEqual(self.would(out), {41001}, out)
    def test_heartbeat_profile_and_chrome_for_testing_are_scoped(self):
        rows = [self.chrome(41002, "--user-data-dir=%s/.ab-heartbeat --no-first-run" % self.home),
                self.chrome(41003, "--headless=new --remote-debugging-port=0",
                            exe="%s/.agent-browser/browsers/chrome-131.0/chrome-mac-arm64/Google Chrome for Testing" % self.home)]
        r, out = self.run_reaper(rows, style="linux")
        self.assertEqual(self.would(out), {41002, 41003}, out)
    def test_a_normal_chrome_window_never_matches(self):
        home = str(self.home)
        rows = [self.chrome(42001, "--user-data-dir=%s/Library/Application Support/Google/Chrome" % home,
                            exe="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
                self.chrome(42002, "--type=renderer --user-data-dir=%s/Library/Application Support/Google/Chrome --lang=en" % home,
                            exe="/Applications/Google Chrome.app/Contents/Frameworks/Google Chrome Helper (Renderer).app/Contents/MacOS/Google Chrome Helper (Renderer)"),
                self.chrome(42003, "--profile-directory=Default", exe="/usr/bin/google-chrome"),
                self.chrome(42004, "", exe="/Applications/Claude.app/Contents/MacOS/Claude"),
                self.chrome(42005, "--user-data-dir=%s/.cache/ms-playwright/mcp-chrome-1" % home, exe="/usr/bin/chromium"),
                # look-alikes outside the scoped trees
                self.chrome(42006, "--user-data-dir=/tmp/agent-browser-chrome-zzz", exe="/usr/bin/chromium"),
                self.chrome(42007, "--user-data-dir=%s/.ab-heartbeat-notes" % home, exe="/usr/bin/chromium")]
        for style in ("mac", "linux"):
            r, out = self.run_reaper(rows, style=style)
            self.assertEqual(self.would(out), set(), out)
            self.assertIn("profile tree: 0", out)

    # -- 2. macOS ages -------------------------------------------------------------------------
    def test_macos_ps_without_etimes_still_gets_an_age_from_etime(self):
        rows = [self.chrome(43001, "--user-data-dir=%s/.agent-browser/p1" % self.home, etime="07-12:30:45"),
                self.chrome(43002, "--user-data-dir=%s/.agent-browser/p2" % self.home, etime="02:05:30"),
                self.chrome(43003, "--user-data-dir=%s/.agent-browser/p3" % self.home, etime="45:12"),    # 45 min: too young
                self.chrome(43004, "--user-data-dir=%s/.agent-browser/p4" % self.home, etime="00:30")]
        r, out = self.run_reaper(rows, style="mac")
        self.assertEqual(self.would(out), {43001, 43002}, out)
        self.assertIn("pid 43001 (age %ds" % sec("7-12:30:45"), out)
        self.assertIn("pid 43002 (age %ds" % sec("02:05:30"), out)
        self.assertNotIn("cannot confirm age", out)
    def test_kill_age_default_is_still_60_minutes(self):
        self.assertIn('PROC_HARD_AGE_MIN="${AB_PROC_HARD_AGE_MIN:-60}"', REAPER.read_text())
        rows = [self.chrome(44001, "--user-data-dir=%s/.agent-browser/a" % self.home, etime="59:59"),
                self.chrome(44002, "--user-data-dir=%s/.agent-browser/b" % self.home, etime="1:00:00")]
        for style in ("mac", "linux"):
            r, out = self.run_reaper(rows, style=style)
            self.assertEqual(self.would(out), {44002}, (style, out))
    def test_an_unreadable_age_still_fails_safe(self):
        r, out = self.run_reaper([self.chrome(44003, "--user-data-dir=%s/.agent-browser/c" % self.home, etime="garbage")], style="mac")
        self.assertEqual(self.would(out), set(), out)

    # -- 3. orphaned daemons -------------------------------------------------------------------
    def daemon(self, pid, etime=OLD, ppid=1, exe=None, args=""):
        exe = exe or "%s/.local/lib/node_modules/agent-browser/bin/agent-browser-darwin-arm64" % self.home
        return (pid, ppid, etime, ("%s %s" % (exe, args)).strip())
    def test_orphaned_daemon_with_no_browser_is_reaped(self):
        r, out = self.run_reaper([self.daemon(45001)], style="mac")
        self.assertEqual(self.would(out), {45001}, out)
        self.assertIn("orphaned agent-browser daemon pid 45001", out)
    def test_daemon_whose_browser_is_reaped_in_this_pass_is_reaped_too(self):
        rows = [self.daemon(45010), self.chrome(45011, "--user-data-dir=%s/tmp/agent-browser-chrome-aa" % self.oc, ppid=45010)]
        r, out = self.run_reaper(rows, style="mac")
        self.assertEqual(self.would(out), {45010, 45011}, out)
    def test_daemon_is_kept_when_it_has_a_live_browser_child(self):
        rows = [self.daemon(45020),
                self.chrome(45021, "--user-data-dir=%s/tmp/agent-browser-chrome-bb" % self.oc, ppid=45020, etime="05:00"),  # young: kept
                self.daemon(45030),
                self.chrome(45031, "--headless", ppid=45030, exe="/usr/bin/chromium")]                                      # unscoped: never touched
        r, out = self.run_reaper(rows, style="mac")
        self.assertEqual(self.would(out), set(), out)
    def test_daemon_gates(self):
        rows = [self.daemon(45040, ppid=1234),                          # parent is not PID 1
                self.daemon(45041, etime="30:00"),                      # younger than the kill age
                self.daemon(45042, exe="/opt/homebrew/bin/agent-browser"),                     # the CLI, not a daemon
                self.daemon(45043, exe="/opt/homebrew/bin/agent-browser-reaper-helper"),       # the reaper's own family
                (45044, 1, self.OLD, "bash /opt/scripts/agent-browser-reaper.sh"),
                (45045, 1, self.OLD, "/usr/sbin/launchd"),
                (45046, 1, self.OLD, "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")]
        r, out = self.run_reaper(rows, style="mac")
        self.assertEqual(self.would(out), set(), out)
        r, out = self.run_reaper([self.daemon(45050)], style="mac", lease=True)       # any live lease: conservative
        self.assertEqual(self.would(out), set(), out)

    # -- 4. webhook branch ---------------------------------------------------------------------
    def test_tripwire_webhook_branch_sends_its_message(self):
        got = []
        class H(http.server.BaseHTTPRequestHandler):
            def log_message(self, *a): pass
            def do_POST(self):
                got.append(self.rfile.read(int(self.headers.get("Content-Length", 0))).decode())
                self.send_response(200); self.send_header("Content-Length", "0"); self.end_headers()
        srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H); threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            rows = [self.chrome(46001, "--user-data-dir=%s/.agent-browser/w" % self.home, etime="00:30")]   # young: no kill, tripwire only
            r, out = self.run_reaper(rows, dry=False, env={"AB_MAX_LIVE": "0",
                                     "RESCUE_RANGERS_WEBHOOK_URL": "http://127.0.0.1:%d/escalate" % srv.server_address[1]})
        finally:
            srv.shutdown(); srv.server_close()
        self.assertNotIn("can only be used in a function", out)
        self.assertEqual(r.returncode, 0, out)
        self.assertEqual(len(got), 1, out)
        self.assertIn("tripwire", json.loads(got[0])["message"])

    # -- 5. real kills: SIGTERM before SIGKILL ---------------------------------------------------
    def test_sigterm_goes_first_and_sigkill_only_for_a_survivor(self):
        stubborn, polite, bystander = self.spawn(ignore_term=True), self.spawn(), self.spawn()
        rows = [self.chrome(stubborn, "--user-data-dir=%s/.agent-browser/s" % self.home),
                self.chrome(polite, "--user-data-dir=%s/tmp/agent-browser-chrome-p" % self.oc),
                self.chrome(bystander, "--user-data-dir=%s/Library/Application Support/Google/Chrome" % self.home,
                            exe="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")]
        r, out = self.run_reaper(rows, style="mac", dry=False)
        self.assertEqual(r.returncode, 0, out)
        self.assertFalse(self.alive(stubborn), out); self.assertFalse(self.alive(polite), out)
        self.assertTrue(self.alive(bystander, wait=0.5), "a normal Chrome window must survive")
        term, kill = "SIGTERM to leaked scoped Chromium pid %d " % stubborn, "SIGKILL leaked scoped Chromium pid %d " % stubborn
        self.assertIn(term, out); self.assertIn(kill, out); self.assertLess(out.index(term), out.index(kill))
        self.assertIn("SIGTERM to leaked scoped Chromium pid %d " % polite, out)
        self.assertNotIn("SIGKILL leaked scoped Chromium pid %d " % polite, out)      # exited on SIGTERM: no SIGKILL
    def test_orphaned_daemon_is_really_stopped(self):
        daemon = self.spawn()
        r, out = self.run_reaper([self.daemon(daemon)], style="mac", dry=False)
        self.assertFalse(self.alive(daemon), out)
        self.assertIn("SIGTERM to orphaned agent-browser daemon pid %d " % daemon, out)

if __name__ == "__main__":
    unittest.main()
