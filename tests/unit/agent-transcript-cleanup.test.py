#!/usr/bin/env python3
"""scripts/agent-transcript-cleanup.py against a fixture agent database.

The fixture mirrors the OpenClaw agent schema the script was proven against (user_version 27, STRICT
tables, foreign keys with ON DELETE CASCADE, an fts5 table with a rows table that has NO foreign key and
a delete trigger, auto_vacuum=INCREMENTAL). Everything runs in a private temp directory; no real
OpenClaw home is ever read or written.
"""
import contextlib, hashlib, importlib.util, io, json, os, sqlite3, subprocess, sys, tempfile, time, unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "agent-transcript-cleanup.py"
DAY = 86400 * 1000
NOW = int(time.time() * 1000)

SCHEMA = """
CREATE TABLE session_windows (session_id TEXT PRIMARY KEY, session_key TEXT NOT NULL, previous_session_id TEXT,
  reason TEXT, created_at INTEGER, updated_at INTEGER, transcript_updated_at INTEGER) STRICT;
CREATE TABLE session_nodes (session_key TEXT PRIMARY KEY, current_session_id TEXT, status TEXT) STRICT;
CREATE TABLE transcript_events (session_id TEXT NOT NULL, seq INTEGER NOT NULL, body TEXT, PRIMARY KEY (session_id, seq),
  FOREIGN KEY (session_id) REFERENCES session_windows(session_id) ON DELETE CASCADE) STRICT;
CREATE TABLE transcript_event_identities (session_id TEXT NOT NULL, seq INTEGER NOT NULL, identity TEXT NOT NULL,
  PRIMARY KEY (session_id, seq, identity),
  FOREIGN KEY (session_id, seq) REFERENCES transcript_events(session_id, seq) ON DELETE CASCADE) STRICT;
CREATE TABLE session_transcript_active_events (session_id TEXT NOT NULL, seq INTEGER NOT NULL, PRIMARY KEY (session_id, seq),
  FOREIGN KEY (session_id, seq) REFERENCES transcript_events(session_id, seq) ON DELETE CASCADE) STRICT;
CREATE TABLE trajectory_runtime_events (id INTEGER PRIMARY KEY, session_id TEXT NOT NULL, payload TEXT,
  FOREIGN KEY (session_id) REFERENCES session_windows(session_id) ON DELETE CASCADE) STRICT;
CREATE TABLE session_transcript_index_state (session_id TEXT PRIMARY KEY, state TEXT,
  FOREIGN KEY (session_id) REFERENCES session_windows(session_id) ON DELETE CASCADE) STRICT;
CREATE TABLE session_conversations (session_id TEXT NOT NULL, conversation TEXT NOT NULL, PRIMARY KEY (session_id, conversation),
  FOREIGN KEY (session_id) REFERENCES session_windows(session_id) ON DELETE CASCADE) STRICT;
CREATE TABLE session_transcript_cold_archives (id INTEGER PRIMARY KEY, session_id TEXT NOT NULL, blob BLOB,
  FOREIGN KEY (session_id) REFERENCES session_windows(session_id) ON DELETE CASCADE) STRICT;
CREATE TABLE session_transcript_archives (id INTEGER PRIMARY KEY, session_key TEXT, blob BLOB) STRICT;
CREATE TABLE memory_chunks (id INTEGER PRIMARY KEY, text TEXT) STRICT;
CREATE VIRTUAL TABLE session_transcript_fts USING fts5(text);
CREATE TABLE session_transcript_fts_rows (id INTEGER PRIMARY KEY, session_id TEXT NOT NULL, message_id TEXT) STRICT;
CREATE TRIGGER session_transcript_fts_rows_after_delete AFTER DELETE ON session_transcript_fts_rows
BEGIN DELETE FROM session_transcript_fts WHERE rowid = old.id; END;
"""
CHILD_TABLES = ["transcript_events", "transcript_event_identities", "session_transcript_active_events",
                "trajectory_runtime_events", "session_transcript_index_state", "session_conversations",
                "session_transcript_cold_archives"]
OLD = ["old1", "old2", "old3", "old4", "old5", "old6", "old7"]
KEPT = ["cur", "recent", "running", "prev_of_recent", "conv"]


def load_module():
    spec = importlib.util.spec_from_file_location("atc", str(SCRIPT))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def add_window(c, sid, key, age_days, prev=None, rows=3, blob=0):
    t = NOW - int(age_days * DAY)
    c.execute("INSERT INTO session_windows VALUES (?,?,?,?,?,?,?)", (sid, key, prev, "cron", t, t, t))
    for i in range(rows):
        c.execute("INSERT INTO transcript_events VALUES (?,?,?)", (sid, i, "body %s %d" % (sid, i)))
        c.execute("INSERT INTO transcript_event_identities VALUES (?,?,?)", (sid, i, "id-%s-%d" % (sid, i)))
        c.execute("INSERT INTO session_transcript_active_events VALUES (?,?)", (sid, i))
        c.execute("INSERT INTO trajectory_runtime_events (session_id, payload) VALUES (?,?)", (sid, "p%d" % i))
        cur = c.execute("INSERT INTO session_transcript_fts_rows (session_id, message_id) VALUES (?,?)", (sid, "m%d" % i))
        c.execute("INSERT INTO session_transcript_fts (rowid, text) VALUES (?,?)", (cur.lastrowid, "hello %s %d" % (sid, i)))
    c.execute("INSERT INTO session_transcript_index_state VALUES (?,?)", (sid, "done"))
    c.execute("INSERT INTO session_conversations VALUES (?,?)", (sid, "conv-" + sid)) if sid == "conv" else None
    c.execute("INSERT INTO session_transcript_cold_archives (session_id, blob) VALUES (?,?)", (sid, b"x" * blob))


def build_db(path, blob=0, wal=False, extra_schema=""):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    c = sqlite3.connect(path, isolation_level=None)
    c.execute("PRAGMA auto_vacuum=2")
    if wal:
        c.execute("PRAGMA journal_mode=WAL")
    c.executescript(SCHEMA + extra_schema)
    c.execute("BEGIN")
    prev = None
    for i, sid in enumerate(OLD):                      # key A: old windows chained, newest old first
        add_window(c, sid, "A", 40 + i, prev=None, blob=blob)
    add_window(c, "cur", "A", 30, blob=blob)           # current window of key A, old by age
    add_window(c, "prev_of_recent", "B", 50, blob=blob)
    add_window(c, "recent", "B", 2, prev="prev_of_recent", blob=blob)
    add_window(c, "running", "R", 60, blob=blob)       # old, but its key is running
    add_window(c, "running_current", "R", 1, blob=blob)
    add_window(c, "conv", "C", 70, blob=blob)          # old, not current: kept only by its conversation row
    add_window(c, "conv_cur", "C", 1, blob=blob)
    c.execute("INSERT INTO session_nodes VALUES ('A','cur','done'),('B','recent','done'),('R','running_current','running'),"
              "('C','conv_cur','done')")
    c.execute("INSERT INTO session_transcript_archives (session_key, blob) VALUES ('A', x'00')")
    c.execute("INSERT INTO memory_chunks (text) VALUES ('keep me')")
    c.execute("COMMIT")
    c.execute("PRAGMA user_version=27")
    c.close()


def counts(path):
    c = sqlite3.connect(path)
    out = {t: {} for t in ["session_windows"] + CHILD_TABLES + ["session_transcript_fts_rows"]}
    for t in out:
        for sid, n in c.execute("SELECT session_id, count(*) FROM %s GROUP BY session_id" % t):
            out[t][sid] = n
    out["fts"] = c.execute("SELECT count(*) FROM session_transcript_fts").fetchone()[0]
    out["nodes"] = c.execute("SELECT count(*) FROM session_nodes").fetchone()[0]
    out["archives"] = c.execute("SELECT count(*) FROM session_transcript_archives").fetchone()[0]
    out["memory"] = c.execute("SELECT count(*) FROM memory_chunks").fetchone()[0]
    c.close()
    return out


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class Base(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.home = os.path.join(self._td.name, "home")
        self.db = os.path.join(self.home, "agents", "main", "agent", "openclaw-agent.sqlite")
        self.assertNotIn("/.openclaw", self.home)

    def tearDown(self):
        self._td.cleanup()

    def run_script(self, *args, env=None):
        e = dict(os.environ)
        for v in ("OPENCLAW_HOME", "OC_ROOT", "OPENCLAW_STATE_DIR", "OPENCLAW_MAINTENANCE", "OPENCLAW_MAINTENANCE_SILENT"):
            e.pop(v, None)
        e.update(env or {})
        return subprocess.run([sys.executable, "-I", str(SCRIPT), "--home", self.home, *args],
                              capture_output=True, text=True, env=e)

    def agent(self, r):
        return json.loads(r.stdout)["agents"][0]

    def archive_files(self):
        d = Path(self.home) / "archives" / "agent-transcripts" / "main"
        return sorted(d.glob("*.sqlite")) if d.is_dir() else []


class Cleanup(Base):
    def test_kept_untouched_old_removed_children_and_fts_gone_archive_equal(self):
        build_db(self.db)
        before = counts(self.db)
        r = self.run_script("--json")
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        a = self.agent(r)
        self.assertEqual(a["windows_removed"], len(OLD))
        after = counts(self.db)
        for sid in KEPT + ["running_current", "conv_cur"]:
            for t in ["session_windows"] + CHILD_TABLES + ["session_transcript_fts_rows"]:
                self.assertEqual(after[t].get(sid), before[t].get(sid), "%s.%s changed" % (t, sid))
        for sid in OLD:
            for t in ["session_windows"] + CHILD_TABLES + ["session_transcript_fts_rows"]:
                self.assertNotIn(sid, after[t], "%s left rows in %s" % (sid, t))
        self.assertEqual(after["fts"], before["fts"] - 3 * len(OLD))
        self.assertEqual((after["nodes"], after["archives"], after["memory"]),
                         (before["nodes"], before["archives"], before["memory"]))
        # the archive holds exactly what was removed
        arch = self.archive_files()
        self.assertEqual(len(arch), 1)
        self.assertRegex(arch[0].name, r"^\d{4}-\d{2}\.sqlite$")
        ac = sqlite3.connect(str(arch[0]))
        removed_rows = 0
        for t in ["session_windows"] + CHILD_TABLES + ["session_transcript_fts_rows"]:
            exp = sum(before[t].get(s, 0) for s in OLD)
            got = ac.execute('SELECT count(*) FROM "%s"' % t).fetchone()[0]
            self.assertEqual(got, exp, t)
            removed_rows += exp
        self.assertEqual(ac.execute("SELECT count(*) FROM session_transcript_fts_text").fetchone()[0], 3 * len(OLD))
        text = ac.execute("SELECT text FROM session_transcript_fts_text WHERE rowid_src IS NOT NULL LIMIT 1").fetchone()[0]
        self.assertTrue(text.startswith("hello old"))
        ac.close()
        self.assertEqual(a["archived_rows"], removed_rows + 3 * len(OLD))
        log = Path(self.home, "logs", "agent-transcript-cleanup.log").read_text()
        self.assertEqual(len(log.strip().splitlines()), 1)
        self.assertIn("agent=main", log)
        self.assertIn("windows_removed=%d" % len(OLD), log)
        self.assertEqual(a["integrity"], "ok")

    def test_archive_permissions_match_source(self):
        build_db(self.db)
        os.chmod(self.db, 0o600)
        self.assertEqual(self.run_script().returncode, 0)
        st, ast = os.stat(self.db), os.stat(self.archive_files()[0])
        self.assertEqual((ast.st_uid, ast.st_gid), (st.st_uid, st.st_gid))
        self.assertEqual(ast.st_mode & 0o777, 0o600)

    def test_dry_run_writes_nothing(self):
        build_db(self.db)
        d0 = digest(self.db)
        r = self.run_script("--dry-run", "--json")
        self.assertEqual(r.returncode, 0, r.stderr)
        a = self.agent(r)
        self.assertEqual(a["candidates"], len(OLD))
        self.assertEqual(a["would_remove_rows"]["session_windows"], len(OLD))
        self.assertEqual(digest(self.db), d0)
        self.assertEqual(self.archive_files(), [])
        self.assertFalse(Path(self.home, "logs").exists())
        self.assertFalse(Path(self.db + "-wal").exists())

    def test_idempotent_second_run_removes_nothing(self):
        build_db(self.db)
        self.assertEqual(self.run_script().returncode, 0)
        d1 = counts(self.db)
        r = self.run_script("--json")
        self.assertEqual(r.returncode, 0)
        self.assertEqual(self.agent(r)["windows_removed"], 0)
        self.assertEqual(counts(self.db), d1)

    def test_keep_days_governs_recent(self):
        build_db(self.db)
        r = self.run_script("--json", "--keep-days", "45")   # old1..old6 are 40..46 days old: only some are old
        self.assertEqual(r.returncode, 0)
        left = {row[0] for row in sqlite3.connect(self.db).execute("SELECT session_id FROM session_windows")}
        self.assertIn("old1", left)          # 40 days, newer than 45
        self.assertNotIn("old7", left)       # 46 days, older than 45
        for sid in KEPT:
            self.assertIn(sid, left)

    def test_default_keep_days_is_three(self):
        build_db(self.db)
        c = sqlite3.connect(self.db)
        t = NOW - 5 * DAY
        c.execute("INSERT INTO session_windows VALUES ('five_days','A',NULL,'cron',?,?,?)", (t, t, t))
        c.execute("INSERT INTO session_windows VALUES ('two_days','A',NULL,'cron',?,?,?)", (NOW - 2 * DAY,) * 3)
        c.commit(); c.close()
        self.assertEqual(load_module().DEFAULT_KEEP_DAYS, 3)
        dry = self.agent(self.run_script("--dry-run", "--json"))
        dry14 = self.agent(self.run_script("--dry-run", "--json", "--keep-days", "14"))
        self.assertEqual(dry["candidates"], len(OLD) + 1)      # five_days is a candidate by default
        self.assertEqual(dry14["candidates"], len(OLD))         # and is kept at 14 days
        self.run_script()
        left = {r[0] for r in sqlite3.connect(self.db).execute("SELECT session_id FROM session_windows")}
        self.assertNotIn("five_days", left)
        self.assertIn("two_days", left)

    def test_quick_check_skipped_on_huge_database_and_without_removals(self):
        build_db(self.db)
        mod = load_module()
        mod.INTEGRITY_MAX_BYTES = 1000                         # the fixture is now "over 1 GB"
        with contextlib.redirect_stdout(io.StringIO()) as out:
            rc = mod.main(["--home", self.home, "--json"])
        a = json.loads(out.getvalue())["agents"][0]
        self.assertEqual(rc, 0)
        self.assertEqual(a["windows_removed"], len(OLD))
        self.assertEqual(a["integrity"], "integrity check skipped (database over 1 GB before vacuum)")
        self.assertIn("integrity check skipped", Path(self.home, "logs", "agent-transcript-cleanup.log").read_text())
        r = self.run_script("--json")                           # second run removes nothing: no check at all
        self.assertEqual(self.agent(r)["integrity"], "not run (nothing removed)")

    def test_quick_check_is_aborted_by_its_time_cap(self):
        build_db(self.db)
        mod = load_module()
        c = sqlite3.connect(self.db)
        self.assertEqual(mod.integrity(c, 60), "ok")
        mod._now = lambda: 10 ** 9                              # the cap has already passed
        self.assertEqual(mod.integrity(c, -1), "integrity check skipped (time cap -1s)")
        c.close()

    def test_unknown_discovered_cascade_child_is_archived_and_removed(self):
        extra = ("CREATE TABLE acp_parent_stream_events (id INTEGER PRIMARY KEY, session_id TEXT NOT NULL, v TEXT, "
                 "FOREIGN KEY (session_id) REFERENCES session_windows(session_id) ON DELETE CASCADE) STRICT;"
                 "CREATE TABLE grand (id INTEGER PRIMARY KEY, ev_session TEXT, ev_seq INTEGER, "
                 "FOREIGN KEY (ev_session, ev_seq) REFERENCES transcript_events(session_id, seq) ON DELETE CASCADE) STRICT;")
        build_db(self.db, extra_schema=extra)
        c = sqlite3.connect(self.db)
        c.execute("INSERT INTO acp_parent_stream_events (session_id, v) VALUES ('old1','x'),('cur','y')")
        c.execute("INSERT INTO grand (ev_session, ev_seq) VALUES ('old1',0),('old2',1),('cur',0)")
        c.commit(); c.close()
        r = self.run_script("--json")
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        c = sqlite3.connect(self.db)
        self.assertEqual(c.execute("SELECT session_id FROM acp_parent_stream_events").fetchall(), [("cur",)])
        self.assertEqual(c.execute("SELECT ev_session FROM grand").fetchall(), [("cur",)])
        ac = sqlite3.connect(str(self.archive_files()[0]))
        self.assertEqual(ac.execute("SELECT count(*) FROM acp_parent_stream_events").fetchone()[0], 1)
        self.assertEqual(ac.execute("SELECT count(*) FROM grand").fetchone()[0], 2)

    def test_unloadable_virtual_table_is_skipped_never_touched(self):
        build_db(self.db)
        c = sqlite3.connect(self.db)
        c.execute("PRAGMA writable_schema=ON")
        c.execute("INSERT INTO sqlite_master (type,name,tbl_name,rootpage,sql) VALUES "
                  "('table','vec_items','vec_items',0,'CREATE VIRTUAL TABLE vec_items USING vec0(embedding float[4])')")
        c.execute("PRAGMA writable_schema=OFF")
        c.commit(); c.close()
        c = sqlite3.connect(self.db)
        with self.assertRaises(sqlite3.Error):             # proves the fixture really is unloadable here
            c.execute("PRAGMA table_info(vec_items)").fetchall()
        c.close()
        r = self.run_script("--json")
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        a = self.agent(r)
        self.assertEqual(a["windows_removed"], len(OLD))
        self.assertIn("vec_items", a["skipped_virtual"])
        self.assertEqual(a["integrity"], "ok")             # quick_check ignores virtual tables here
        self.assertIn("vec_items", Path(self.home, "logs", "agent-transcript-cleanup.log").read_text() + json.dumps(a))

    def test_quick_check_that_cannot_run_is_reported_skipped_not_failed(self):
        mod = load_module()

        class Boom:
            def execute(self, *a, **k):
                raise sqlite3.OperationalError("no such module: vec0")

        self.assertEqual(mod.integrity(Boom()), "integrity check skipped (vec0)")

    def test_lock_prevents_overlap(self):
        import fcntl
        build_db(self.db)
        os.makedirs(os.path.join(self.home, "logs"))
        fh = open(os.path.join(self.home, "logs", "agent-transcript-cleanup.lock"), "a+")
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        d0 = digest(self.db)
        r = self.run_script("--json")
        fh.close()
        self.assertEqual(r.returncode, 0)
        self.assertEqual(json.loads(r.stdout)["status"], "locked")
        self.assertEqual(digest(self.db), d0)

    def test_agent_flag_limits_scope(self):
        build_db(self.db)
        other = os.path.join(self.home, "agents", "other", "agent", "openclaw-agent.sqlite")
        build_db(other)
        o0 = digest(other)
        r = self.run_script("--json", "--agent", "main")
        self.assertEqual(r.returncode, 0)
        self.assertEqual(len(json.loads(r.stdout)["agents"]), 1)
        self.assertEqual(digest(other), o0)

    def test_quiet_under_maintenance_env(self):
        build_db(self.db)
        r = self.run_script(env={"OPENCLAW_MAINTENANCE": "1"})
        self.assertEqual(r.returncode, 0)
        self.assertEqual(r.stdout.strip(), "")
        self.assertTrue(Path(self.home, "logs", "agent-transcript-cleanup.log").exists())


class Refusals(Base):
    def assert_refused(self, why):
        d0 = digest(self.db)
        r = self.run_script("--json")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn(why, self.agent(r)["detail"])
        self.assertEqual(digest(self.db), d0, "database was written")
        self.assertEqual(self.archive_files(), [])

    def test_unknown_user_version(self):
        build_db(self.db)
        c = sqlite3.connect(self.db); c.execute("PRAGMA user_version=28"); c.close()
        self.assert_refused("user_version 28")

    def test_non_cascade_foreign_key_to_windows(self):
        build_db(self.db, extra_schema="CREATE TABLE loose (id INTEGER PRIMARY KEY, session_id TEXT, "
                 "FOREIGN KEY (session_id) REFERENCES session_windows(session_id)) STRICT;")
        self.assert_refused("not CASCADE")

    def test_non_cascade_foreign_key_to_transcript_events(self):
        build_db(self.db, extra_schema="CREATE TABLE loose2 (id INTEGER PRIMARY KEY, s TEXT, q INTEGER, "
                 "FOREIGN KEY (s, q) REFERENCES transcript_events(session_id, seq) ON DELETE SET NULL) STRICT;")
        self.assert_refused("SET NULL")

    def test_cascade_into_protected_table(self):
        build_db(self.db, extra_schema="CREATE TABLE memory_links (id INTEGER PRIMARY KEY, session_id TEXT, "
                 "FOREIGN KEY (session_id) REFERENCES session_windows(session_id) ON DELETE CASCADE) STRICT;")
        self.assert_refused("protected table")

    def test_timestamps_in_seconds(self):
        build_db(self.db)
        c = sqlite3.connect(self.db)
        c.execute("UPDATE session_windows SET created_at=1700000000, updated_at=1700000000, transcript_updated_at=1700000000 "
                  "WHERE session_id='old1'")
        c.commit(); c.close()
        self.assert_refused("seconds")

    def test_missing_required_table(self):
        build_db(self.db)
        c = sqlite3.connect(self.db); c.execute("DROP TABLE session_conversations"); c.close()
        self.assert_refused("session_conversations")


class Pacing(Base):
    def test_batch_and_max_seconds_then_resume(self):
        build_db(self.db)
        mod = load_module()
        ticks = {"n": 0}

        def fake_now():
            ticks["n"] += 1
            return float(ticks["n"])

        real = mod._now
        mod._now = fake_now
        try:
            # start=1, deadline=1+2.5=3.5; loop checks at 2, 3 pass, 4 stops -> two batches of 2 windows
            with contextlib.redirect_stdout(io.StringIO()):
                rc = mod.main(["--home", self.home, "--batch", "2", "--max-seconds", "2.5", "--json"])
        finally:
            mod._now = real
        self.assertEqual(rc, 0)
        left = {row[0] for row in sqlite3.connect(self.db).execute("SELECT session_id FROM session_windows")}
        removed = [s for s in OLD if s not in left]
        self.assertEqual(len(removed), 4)                 # 2 batches x batch=2, then stopped early
        r = self.run_script("--json", "--batch", "3")
        a = self.agent(r)
        self.assertEqual(a["windows_removed"], 3)
        self.assertEqual(a["batches"], 1)
        self.assertEqual(r.returncode, 0)
        left = {row[0] for row in sqlite3.connect(self.db).execute("SELECT session_id FROM session_windows")}
        self.assertFalse(set(OLD) & left)

    def test_max_seconds_zero_removes_nothing(self):
        build_db(self.db)
        d0 = counts(self.db)
        r = self.run_script("--json", "--max-seconds", "0")
        self.assertEqual(r.returncode, 0)
        a = self.agent(r)
        self.assertTrue(a["stopped_early"])
        self.assertEqual(a["windows_removed"], 0)
        self.assertEqual(counts(self.db), d0)


class Shrink(Base):
    def test_file_and_page_count_shrink_after_incremental_vacuum(self):
        build_db(self.db, blob=200_000)                   # about 2.4 MB in the doomed windows
        size0 = os.path.getsize(self.db)
        pages0 = sqlite3.connect(self.db).execute("PRAGMA page_count").fetchone()[0]
        r = self.run_script("--json")
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        a = self.agent(r)
        self.assertGreater(a["pages_vacuumed"], 0)
        c = sqlite3.connect(self.db)
        self.assertLess(c.execute("PRAGMA page_count").fetchone()[0], pages0)
        self.assertEqual(c.execute("PRAGMA freelist_count").fetchone()[0], 0)
        self.assertLess(os.path.getsize(self.db), size0 - 1_000_000)
        self.assertLess(a["after_bytes"], a["before_bytes"])

    def test_wal_database_page_count_shrinks_and_checkpoints(self):
        build_db(self.db, blob=200_000, wal=True)
        pages0 = sqlite3.connect(self.db).execute("PRAGMA page_count").fetchone()[0]
        r = self.run_script("--json")
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        c = sqlite3.connect(self.db)
        self.assertLess(c.execute("PRAGMA page_count").fetchone()[0], pages0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
