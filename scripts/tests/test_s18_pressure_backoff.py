"""Skill 06 pressure/backoff fault test (Master Plan v3.0 section 14, S18).

*** EVERY RESULT IN THIS FILE IS SIMULATED. ***

No real CPU, memory, disk, browser or network pressure is applied at any point.
Pressure events are injected IN-PROCESS, synchronously, against the real
production seams in ``scripts/lib/swarm_controls.py``:

  * over-admission  -> ``AdmissionLedger.acquire`` past a cap (SlotRefused)
  * slow consumers  -> ``AdmissionLedger.sweep_stale`` after heartbeats expire
  * timeouts        -> ``MergeLock`` bounded wait under real flock contention
  * host pressure   -> ``health_check`` with ``_disk_free_gib``/``_mem_free_gib``
                       replaced by synthetic readings

Asserted: admission rejection while pressure holds, bounded retry SPACING
(the exact backoff poll interval and the ceiling on attempts), and recovery
once pressure clears.

Real-machine pressure testing (actual personal-app CPU/memory load, "throttle
project work, never personal processes") stays NOT_RUN BY DESIGN — it is not
performed here and must not be inferred from a green run of this file.

Run sequentially, one heavy job at a time:
  python3 -m pytest scripts/tests/test_s18_pressure_backoff.py -q
"""
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts' / 'lib'))
import swarm_controls as sc  # noqa: E402

POLL_S = 0.05          # MergeLock contention poll interval (production value)


class FakeClock:
    """Virtual clock substituted for swarm_controls' ``time`` module.

    ``sleep`` advances virtual time by the requested amount and records it, so
    backoff spacing is asserted exactly instead of being wall-clock flaky.
    """

    def __init__(self, start=1000.0):
        self.t = start
        self.sleeps = []

    def time(self):
        return self.t

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.t += seconds


class OverAdmissionTests(unittest.TestCase):
    """Pressure event: more requesters than the cap admits."""

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)

    def test_agent_pressure_refused_then_recovers_after_release(self):
        clock = {'t': 1000.0}
        ledger = sc.AdmissionLedger(self.dir.name, now=lambda: clock['t'])
        toks = [ledger.acquire('agent', f'a{i}') for i in range(sc.AGENT_START_CAP)]
        # SIMULATED pressure: one requester over the start cap.
        with self.assertRaises(sc.SlotRefused):
            ledger.acquire('agent', 'overflow')
        self.assertEqual(ledger.counts()['agent'], sc.AGENT_START_CAP)
        # Recovery: pressure clears one slot at a time.
        ledger.release(toks[0])
        ledger.acquire('agent', 'overflow')
        self.assertEqual(ledger.counts()['agent'], sc.AGENT_START_CAP)

    def test_heavy_job_pressure_refused_then_recovers(self):
        ledger = sc.AdmissionLedger(self.dir.name)
        tok = ledger.acquire('heavy', 'suite')
        with self.assertRaises(sc.SlotRefused):
            ledger.acquire('heavy', 'second-heavy')   # one heavy job host-wide
        ledger.release(tok)
        ledger.acquire('heavy', 'second-heavy')
        self.assertEqual(ledger.counts()['heavy'], 1)

    def test_expanding_cap_under_pressure_still_clamps(self):
        ledger = sc.AdmissionLedger(self.dir.name)
        for i in range(sc.AGENT_START_CAP):
            ledger.acquire('agent', f'a{i}')
        self.assertEqual(ledger.expand_agent_cap(), sc.AGENT_MAX_CAP)
        self.assertEqual(ledger.expand_agent_cap(), sc.AGENT_MAX_CAP)  # clamped
        # Headroom opened by the expansion is exactly MAX - START slots.
        for i in range(sc.AGENT_MAX_CAP - sc.AGENT_START_CAP):
            ledger.acquire('agent', f'b{i}')
        self.assertEqual(ledger.counts()['agent'], sc.AGENT_MAX_CAP)
        with self.assertRaises(sc.SlotRefused):
            ledger.acquire('agent', 'beyond-max')     # hard ceiling holds


class SlowConsumerTests(unittest.TestCase):
    """Pressure event: a consumer stops heartbeating (stalled, not dead)."""

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)

    def test_stalled_consumers_hold_slots_until_expiry_then_recover(self):
        clock = {'t': 1000.0}
        ledger = sc.AdmissionLedger(self.dir.name, now=lambda: clock['t'])
        for i in range(sc.AGENT_START_CAP):
            ledger.acquire('agent', f'slow{i}')
        clock['t'] += 60          # inside the stale window: pressure persists
        self.assertEqual(ledger.sweep_stale(max_age_s=120), [])
        with self.assertRaises(sc.SlotRefused):
            ledger.acquire('agent', 'newcomer')
        clock['t'] += 120         # expiry crossed: pressure clears
        self.assertEqual(len(ledger.sweep_stale(max_age_s=120)),
                         sc.AGENT_START_CAP)
        ledger.acquire('agent', 'newcomer')
        self.assertEqual(ledger.counts()['agent'], 1)

    def test_heartbeat_keeps_a_live_consumer_admitted(self):
        clock = {'t': 1000.0}
        ledger = sc.AdmissionLedger(self.dir.name, now=lambda: clock['t'])
        tok = ledger.acquire('agent', 'alive')
        for _ in range(5):
            clock['t'] += 100
            ledger.heartbeat(tok)     # a live consumer is never swept
        self.assertEqual(ledger.sweep_stale(max_age_s=120), [])
        self.assertEqual(ledger.counts()['agent'], 1)


class TimeoutBackoffTests(unittest.TestCase):
    """Pressure event: the merge lock is contended, so waits time out."""

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)

    def _hold_lock(self):
        """Hold the flock from a SEPARATE file description (same process is
        enough: flock is per open(), verified) — a real, not mocked, contender.
        """
        import fcntl
        lock = sc.MergeLock(self.dir.name)
        fh = open(lock.lock_path, 'a+')
        fcntl.flock(fh, fcntl.LOCK_EX)
        self.addCleanup(lambda: (fcntl.flock(fh, fcntl.LOCK_UN), fh.close()))
        return fh

    def test_contended_lock_backs_off_at_the_production_interval(self):
        self._hold_lock()
        lock = sc.MergeLock(self.dir.name)
        clock = FakeClock()
        with mock.patch.object(sc, 'time', clock):
            with self.assertRaises(sc.SlotRefused):
                lock._acquire_blocking(timeout_s=0.25)
        # SIMULATED timeout: bounded, evenly spaced, no busy-spin.
        self.assertEqual(set(clock.sleeps), {POLL_S})
        self._assert_bounded(clock.sleeps, 0.25)

    def test_bounded_wait_never_exceeds_its_deadline(self):
        self._hold_lock()
        lock = sc.MergeLock(self.dir.name)
        clock = FakeClock()
        with mock.patch.object(sc, 'time', clock):
            with self.assertRaises(sc.SlotRefused):
                lock._acquire_blocking(timeout_s=1.0)
        self._assert_bounded(clock.sleeps, 1.0)

    def _assert_bounded(self, sleeps, timeout_s):
        """The wait is bounded: it always backs off at least until the deadline
        and never overshoots it by more than one poll interval (a contended
        lock can never spin faster, nor wait past its deadline)."""
        waited = sum(sleeps)
        self.assertGreaterEqual(waited, timeout_s)
        self.assertLess(waited, timeout_s + POLL_S + 1e-9)

    def test_lock_acquired_immediately_once_pressure_clears(self):
        import fcntl
        holder = open(sc.MergeLock(self.dir.name).lock_path, 'a+')
        fcntl.flock(holder, fcntl.LOCK_EX)
        fcntl.flock(holder, fcntl.LOCK_UN)      # pressure clears
        holder.close()
        lock = sc.MergeLock(self.dir.name)
        clock = FakeClock()
        with mock.patch.object(sc, 'time', clock):
            fh = lock._acquire_blocking(timeout_s=0.25)
        self.assertEqual(clock.sleeps, [])       # no backoff needed
        lock._held = fh
        lock._unlock()

    def test_try_acquire_reports_busy_without_spinning(self):
        self._hold_lock()
        lock = sc.MergeLock(self.dir.name)
        started = time.monotonic()
        ok, gen = lock.try_acquire('owner', 'batch-1')   # LOCK_NB: no wait
        elapsed = time.monotonic() - started
        self.assertEqual((ok, gen), (False, None))
        self.assertLess(elapsed, 1.0)


class ExponentialBackoffSpacingTests(unittest.TestCase):
    """Pressure event: a transient failure repeats. The retry SPACING seam is
    ``browser_manager.bounded_retry`` — the Python-side reference loop that the
    swarm's browser lanes follow (``sleep`` is injected, so nothing sleeps)."""

    def setUp(self):
        sys.path.insert(0, str(ROOT / '06-ghl-install-pages' / 'tools'))
        import browser_manager
        self.bm = browser_manager

    def test_spacing_doubles_and_stops_at_the_attempt_cap(self):
        sleeps = []

        def always_fails(attempt):
            raise TimeoutError('SIMULATED transient pressure')

        with self.assertRaises(TimeoutError):
            self.bm.bounded_retry(always_fails, max_attempts=4,
                                  base_delay=2.0, sleep=sleeps.append)
        self.assertEqual(sleeps, [2.0, 4.0, 8.0])   # 3 gaps for 4 attempts
        for earlier, later in zip(sleeps, sleeps[1:]):
            self.assertEqual(later, earlier * 2)

    def test_a_recovering_consumer_stops_backing_off_immediately(self):
        sleeps = []
        calls = []

        def fails_twice_then_succeeds(attempt):
            calls.append(attempt)
            if attempt < 3:
                raise TimeoutError('SIMULATED transient pressure')
            return 'ok'

        out = self.bm.bounded_retry(fails_twice_then_succeeds, max_attempts=4,
                                    base_delay=1.0, sleep=sleeps.append)
        self.assertEqual(out, 'ok')
        self.assertEqual(calls, [1, 2, 3])
        self.assertEqual(sleeps, [1.0, 2.0])        # backoff, then no wait

    def test_no_backoff_after_the_final_failed_attempt(self):
        sleeps = []

        def always_fails(attempt):
            raise TimeoutError('SIMULATED transient pressure')

        with self.assertRaises(TimeoutError):
            self.bm.bounded_retry(always_fails, max_attempts=1,
                                  base_delay=2.0, sleep=sleeps.append)
        self.assertEqual(sleeps, [])                # capped out: no wasted wait

    def test_terminal_session_expiry_never_backs_off(self):
        sleeps = []

        def expired(attempt):
            raise self.bm.SessionExpiredError('SIMULATED expired session')

        with self.assertRaises(self.bm.SessionExpiredError):
            self.bm.bounded_retry(expired, max_attempts=5,
                                  base_delay=2.0, sleep=sleeps.append)
        self.assertEqual(sleeps, [])                # terminal is never retried

    def test_admission_pressure_clears_and_the_ledger_admits_again(self):
        """End-to-end pressure/recovery across both seams: transient failures
        back off, and once the underlying admission slot frees the operation
        succeeds on the next attempt."""
        with tempfile.TemporaryDirectory() as state_dir:
            ledger = sc.AdmissionLedger(state_dir)
            blocker = ledger.acquire('heavy', 'blocker')   # SIMULATED pressure
            sleeps = []

            def admit(attempt=None):
                return ledger.acquire('heavy', 'queued-job')

            with self.assertRaises(sc.SlotRefused):
                self.bm.bounded_retry(admit, max_attempts=2,
                                      base_delay=1.0, sleep=sleeps.append)
            self.assertEqual(sleeps, [1.0])
            ledger.release(blocker)                        # pressure clears
            self.bm.bounded_retry(admit, max_attempts=2,
                                  base_delay=1.0, sleep=sleeps.append)
            self.assertEqual(ledger.counts()['heavy'], 1)   # recovered


class HostPressureTests(unittest.TestCase):
    """Pressure event: the host itself is short on disk / memory."""

    def _health(self, internal, external, mem):
        with mock.patch.object(sc, '_disk_free_gib',
                               side_effect=lambda p: internal
                               if p == '/internal' else external), \
             mock.patch.object(sc, '_mem_free_gib', return_value=mem):
            return sc.health_check('/internal', '/external')

    def test_pressure_changes_the_verdict_and_recovery_restores_start(self):
        relaxed = self._health(500.0, 900.0, 32.0)
        self.assertEqual(relaxed['overall'], 'start')
        held = self._health(12.0, 20.0, 3.0)      # SIMULATED pressure
        self.assertEqual(
            (held['internal_verdict'], held['external_verdict'],
             held['overall']), ('hold', 'hold', 'hold'))
        critical = self._health(3.0, 5.0, 0.5)    # SIMULATED heavy pressure
        self.assertEqual(critical['overall'], 'critical')
        recovered = self._health(500.0, 900.0, 32.0)   # pressure clears
        self.assertEqual(recovered['overall'], 'start')

    def test_worst_dimension_wins_and_memory_is_never_ignored(self):
        only_mem = self._health(500.0, 900.0, 1.0)
        self.assertEqual(only_mem['overall'], 'critical')
        only_external = self._health(500.0, 10.0, 32.0)
        self.assertEqual(only_external['overall'], 'critical')
        self.assertEqual(only_external['internal_verdict'], 'start')

    def test_band_edges_are_the_documented_thresholds(self):
        self.assertEqual(self._health(25.0, 40.0, 6.0)['overall'], 'start')
        self.assertEqual(self._health(24.9, 40.0, 6.0)['overall'], 'hold')
        self.assertEqual(self._health(9.9, 40.0, 6.0)['overall'], 'critical')
        self.assertEqual(self._health(25.0, 39.9, 6.0)['overall'], 'hold')
        self.assertEqual(self._health(25.0, 14.9, 6.0)['overall'], 'critical')
        self.assertEqual(self._health(25.0, 40.0, 5.9)['overall'], 'hold')
        self.assertEqual(self._health(25.0, 40.0, 1.9)['overall'], 'critical')

    def test_report_shape_survives_pressure(self):
        out = self._health(12.0, 20.0, 3.0)
        self.assertEqual(sorted(out), ['external_free_gib', 'external_verdict',
                                       'internal_free_gib', 'internal_verdict',
                                       'loadavg', 'mem_free_gib', 'overall'])
        self.assertEqual(len(out['loadavg']), 3)


if __name__ == '__main__':
    unittest.main()
