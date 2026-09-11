#!/usr/bin/env python3
"""PRES-023 gate — box-side bridge poll against the paginated pending index.

Run: python3 test/test_pres023_bridge_ack.py

Offline: _http is stubbed against an in-memory worker replica that honors the
PRES-023 worker contract (paginated scoped pending index, repeatable
ack=<sid>&stored_at_<sid>=<ts> pairs, cursor/truncated). Proves QC-PRES-023
acceptance from the BRIDGE side:

  1. more submissions than one list page: all discovered exactly once
  2. restart cursor halfway (max-pages budget hit): nothing lost, next poll
     resumes and still discovers everything exactly once
  3. large processed history does not make new-job discovery slow or wrong:
     every processed row is acked (repeatable pairs, no 50-cap drop) and the
     next poll's discovery cost tracks PENDING rows, not history
  4. the processed checkpoint is append-only versioned JSON lines — a torn
     tail line is skipped, never fatal, and nothing is rewritten
"""
from __future__ import annotations

import json
import os
import pathlib
import sys
import tempfile
import time
import unittest
import unittest.mock
import urllib.parse

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))              # repo layout: bridge/ next to test/
sys.path.insert(0, str(HERE.parent / "bridge"))   # intake_bridge lives in bridge/

import intake_bridge as ib  # noqa: E402


# ---- in-memory replica of the PRES-023 worker index semantics ----------------
class _FakeWorker:
    def __init__(self, page_limit: int = 100):
        self.rows: dict[str, dict] = {}   # session_id -> {file_name, stored_at}
        self.page_limit = page_limit
        self.requests: list[str] = []
        self.deleted: list[str] = []

    def _delete_by_ack(self, sid: str, stored_at: int | None) -> bool:
        """Delete the index row for sid. With stored_at, delete exactly
        intakes-index/<padded stored_at>-<sid>.json; with 0/None, delete any
        row for sid. Returns True when a row was removed."""
        if stored_at:
            key = f"intakes-index/{int(stored_at):012d}-{sid}.json"
            if key in self.rows:
                del self.rows[key]
                self.deleted.append(sid)
                return True
            return False
        for key in [k for k in self.rows if k.endswith(f"-{sid}.json")]:
            del self.rows[key]
            self.deleted.append(sid)
            return True
        return False

    def handle(self, method: str, url: str, token: str | None = None) -> tuple[int, dict]:
        self.requests.append(url)
        p = urllib.parse.urlparse(url)
        q = urllib.parse.parse_qs(p.query)
        if p.path == "/api/intake/list":
            if token != "admin":
                return 401, {"error": "unauthorized"}
            # Acks first (repeatable ack + stored_at_<sid> pairs).
            for sid in q.get("ack", []):
                # per-sid stored_at override, then the bare shared one.
                ts = int((q.get(f"stored_at_{sid}") or q.get("stored_at") or [0])[0])
                self._delete_by_ack(sid, ts or None)
            cursor = (q.get("cursor") or [None])[0]
            limit = int((q.get("limit") or [self.page_limit])[0])
            keys = sorted(self.rows)                      # index keys sort by stored_at
            # R2-correct cursor semantics: the cursor is the LAST KEY of the
            # previous page; listing continues strictly AFTER that key.
            # Key-based cursors survive concurrent deletes while paginating
            # (index-based ones shift under your feet) — this is exactly the
            # semantics the live R2 binding gives the worker, so the mock
            # mirrors it instead of an index cursor.
            start = 0
            if cursor:
                start = (keys.index(cursor) + 1) if cursor in keys else 0
            page = keys[start:start + limit]
            truncated = start + len(page) < len(keys)
            resp = {
                "intakes": [
                    {"session_id": self.rows[k]["session_id"],
                     "file_name": self.rows[k]["file_name"],
                     "stored_at": self.rows[k]["stored_at"]}
                    for k in page
                ],
                "truncated": truncated,
            }
            if truncated:
                resp["cursor"] = page[-1]
            return 200, resp
        return 404, {"error": "not found"}

    def store(self, sid: str, stored_at: int | None = None) -> None:
        ts = int(stored_at if stored_at is not None else time.time())
        self.rows[f"intakes-index/{ts:012d}-{sid}.json"] = {
            "session_id": sid, "file_name": f"intake-{sid}.json", "stored_at": ts,
        }


class _StubHttp:
    """Installs itself over ib._http and restores it on exit."""

    def __init__(self, worker: _FakeWorker, statuses=None):
        self.worker = worker
        self.statuses = statuses or {}

    def __enter__(self):
        self._orig = ib._http
        statuses = self.statuses
        worker = self.worker

        def fake_http(method, url, *, token=None, body=None, timeout=20):
            if statuses:
                for path_part, code in statuses.items():
                    if path_part in url:
                        return code, {"error": f"stub {code}"}
            return worker.handle(method, url, token=token)
        ib._http = fake_http
        return self

    def __exit__(self, *exc):
        ib._http = self._orig
        return False


def _args(worker_url: str, ledger: pathlib.Path, **kw) -> object:
    ns = type("NS", (), {})()
    ns.worker_url = worker_url
    ns.poll_ledger = str(ledger)
    ns.max_pages = kw.get("max_pages", 10)
    ns.verbose = kw.get("verbose", False)
    ns.run_dir = kw.get("run_dir", str(pathlib.Path(ledger).parent / "run"))
    ns.per_session_dirs = False
    return ns


def _ingest_stub(rc=0, calls=None):
    def fake_cmd_ingest(sub_args):
        if calls is not None:
            calls.append(sub_args.session_id)
        return rc
    return fake_cmd_ingest


class TestPres023BridgeAck(unittest.TestCase):
    WORKER_URL = "https://worker.test"

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ledger = pathlib.Path(self.tmp.name) / "poll_ledger.jsonl"
        self.worker = _FakeWorker(page_limit=100)
        # cmd_poll reads a run dir even when the ingest stub never writes it.
        self.run_dir = pathlib.Path(self.tmp.name) / "run"
        self.run_dir.mkdir()
        # _list_intakes refuses to run without the admin token in env.
        self._env_patcher = unittest.mock.patch.dict(os.environ, {"INTAKE_ADMIN_TOKEN": "admin"})
        self._env_patcher.start()

    def tearDown(self):
        self._env_patcher.stop()
        self.tmp.cleanup()

    def _poll(self, rc=0, calls=None, max_pages=10):
        with _StubHttp(self.worker):
            orig = ib.cmd_ingest
            ib.cmd_ingest = _ingest_stub(rc, calls)
            try:
                return ib.cmd_poll(_args(self.WORKER_URL, self.ledger, max_pages=max_pages))
                # cmd_poll returns 0
            finally:
                ib.cmd_ingest = orig

    def test_1_more_submissions_than_one_page_all_discovered_exactly_once(self):
        for i in range(250):  # 250 > page limit 100
            self.worker.store(f"s-{i:04d}", stored_at=1_700_000_000 + i)
        calls: list = []
        self._poll(calls=calls)
        self.assertEqual(len(calls), 250, "every pending submission ingested")
        self.assertEqual(len(set(calls)), 250, "each discovered exactly once")
        # Checkpoint holds every session exactly once.
        done = {json.loads(l)["session_id"] for l in self.ledger.read_text().splitlines() if l.strip()}
        self.assertEqual(done, {f"s-{i:04d}" for i in range(250)})
        # Acks ride the NEXT poll (checkpoint is written during ingest, acks
        # computed at poll start from the pending listing). Convergence is
        # what matters: each bounded poll acks at least one page-worth, the
        # remainder is never dropped, and the index drains to empty without a
        # single re-ingestion.
        for _ in range(5):
            if not self.worker.rows:
                break
            self._poll(calls=calls)
        self.assertEqual(len(calls), 250, "NO poll re-ingested anything (checkpoint dedupes)")
        self.assertEqual(len(self.worker.rows), 0, "all rows acked off the index after round trip")

    def test_2_restart_cursor_halfway_no_lost_work(self):
        for i in range(150):
            self.worker.store(f"r-{i:04d}", stored_at=1_700_000_000 + i)
        calls: list = []
        # max_pages=1 forces the poll to stop after the FIRST page (100 rows) —
        # the poll "crashes"/stops halfway; the rest stay pending.
        self._poll(calls=calls, max_pages=1)
        self.assertEqual(len(calls), 100, "first poll ingests exactly the first page")
        # Second poll resumes from the index (the index IS the durable cursor —
        # acked rows are gone, so nothing redelivered, nothing lost).
        self._poll(calls=calls)
        self.assertEqual(len(calls), 150, "resume discovers the remainder: no lost work")
        self.assertEqual(len(set(calls)), 150, "and still exactly once overall")
        # Third poll flushes the acks written during poll 2.
        self._poll(calls=calls)
        self.assertEqual(len(calls), 150, "nothing re-ingested after the ack flush")
        self.assertEqual(len(self.worker.rows), 0)

    def test_3_large_processed_history_does_not_grow_discovery(self):
        # 300 processed sessions are acked off the index across polls; a NEW
        # submission then lands and is discovered on a fresh 1-page poll.
        for i in range(300):
            self.worker.store(f"old-{i:04d}", stored_at=1_600_000_000 + i)
        calls: list = []
        self._poll(calls=calls)
        self.assertEqual(len(calls), 300)
        # Second + third polls flush the acks (bounded at MAX_ACKS_PER_POLL
        # per request; the remainder rides the next poll, never dropped).
        self._poll(calls=calls)
        self._poll(calls=calls)
        self._poll(calls=calls)
        self.assertEqual(len(calls), 300, "no re-ingestion while acks flush")
        self.assertEqual(len(self.worker.rows), 0, "history acked off the index")
        # A new submission: discovery sees ONLY it — one page, no history rescan.
        self.worker.store("new-0000", stored_at=1_800_000_000)
        calls2: list = []
        t0 = time.perf_counter()
        self._poll(calls=calls2)
        dt = time.perf_counter() - t0
        self.assertEqual(calls2, ["new-0000"], "only the new submission is discovered")
        self.assertLess(dt, 5.0, "new-job discovery latency did not scale with 300 rows of history")
        # No ack budget blowout: ack requests carried at most MAX_ACKS_PER_POLL pairs.
        ack_urls = [u for u in self.worker.requests if "ack=" in u]
        for u in ack_urls:
            n = len(urllib.parse.parse_qs(urllib.parse.urlparse(u).query).get("ack", []))
            self.assertLessEqual(n, ib.MAX_ACKS_PER_POLL)

    def test_3b_stale_acks_never_grow_unbounded(self):
        # 300 sessions processed; poll again with an EMPTY index — the stale
        # ack set must not hang the poll or send endless no-op acks forever.
        for i in range(300):
            self.worker.store(f"s-{i:04d}", stored_at=1_700_000_000 + i)
        self._poll()
        # Second poll with nothing pending: stale processed ids are still sent
        # as acks (bounded), the worker reports nothing pending, and the poll
        # finishes promptly. The sidecar keeps the map bounded.
        t0 = time.perf_counter()
        self._poll()
        self.assertLess(time.perf_counter() - t0, 5.0)
        sidecar = pathlib.Path(str(self.ledger) + ".stored_at.json")
        self.assertTrue(sidecar.is_file(), "stored_at sidecar written")
        self.assertEqual(len(json.loads(sidecar.read_text())), 300, "sidecar bounded to checkpoint size")

    def test_4_checkpoint_append_only_torn_tail_skipped(self):
        for i in range(3):
            self.worker.store(f"t-{i}")
        self._poll()
        raw = self.ledger.read_text()
        lines = [l for l in raw.splitlines() if l.strip()]
        self.assertEqual(len(lines), 3)
        for l in lines:
            rec = json.loads(l)  # every line is a JSON object
            self.assertIn("session_id", rec)
        # Torn tail: append a truncated line; fold must still read 3 sessions.
        with open(self.ledger, "a") as fh:
            fh.write('{"session_id": "t-3", "version"')  # torn
        done = ib._processed_ledger(_args(self.WORKER_URL, self.ledger))
        self.assertEqual(done, {"t-0", "t-1", "t-2"}, "torn tail skipped, 3 facts intact")

    def test_5_ack_pairs_name_exact_rows(self):
        # stored_at pair form: stored_at_<sid> names the exact index key.
        self.worker.store("exact-1", stored_at=1_234_567_890)
        code, resp = self.worker.handle(
            "GET", f"{self.WORKER_URL}/api/intake/list?ack=exact-1&stored_at_exact-1=1234567890",
            token="admin")
        self.assertEqual(code, 200)
        self.assertEqual(self.worker.rows, {}, "exact row deleted via the pair form")

    def test_6_legacy_ledger_upgrades_transparently(self):
        self.ledger.write_text("legacy-a legacy-b\n")
        done = ib._processed_ledger(_args(self.WORKER_URL, self.ledger))
        self.assertEqual(done, {"legacy-a", "legacy-b"})
        # The upgrade appended versioned lines; original content untouched.
        raw = self.ledger.read_text()
        self.assertIn("legacy-a legacy-b", raw, "legacy content not rewritten")
        self.assertIn('"migrated_from": "legacy-ledger"', raw)


if __name__ == "__main__":
    unittest.main()
