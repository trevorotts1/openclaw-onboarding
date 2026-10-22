"""S13 dedicated consumer-pin fault test (Master Plan v3.0 section 8.2
condition 3 `workers_stopped_no_dependent_consumers`; section 14 S13).

Proves the removal path REFUSES while a dependent consumer pin exists and
PROCEEDS once consumers reach zero. The pin is a REAL live process whose
cwd is the merged worktree, found by lsof — not a fabricated string — so the
refusal is measured against the detection a caller actually performs.

Closes the overnight acceptance gap: S13 was NOT_RUN because the contract
was enforced (consumers=0 observed live at every removal) but no fault test
ever pinned a live consumer.

Run: python3 -m pytest scripts/tests/test_cleanup_transaction_s13_consumer_pin.py -q
"""
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'lib'))
import cleanup_transaction as ct
from test_cleanup_transaction import Fixture


def live_pins(worktree):
    """Consumer pins for `worktree`: pids whose cwd is inside it.

    lsof is the native cwd-holder probe on macOS (no /proc). Returns
    ['pid=<n>:cwd=<path>', ...]; empty means no dependent consumer.
    """
    if not shutil.which('lsof'):
        return None                       # caller falls back, never silently 0
    out = subprocess.run(['lsof', '-d', 'cwd', '-Fpn'],
                         capture_output=True, text=True, check=True).stdout
    root = str(Path(worktree).resolve()) + '/'
    pins, pid = [], None
    for line in out.splitlines():
        if line.startswith('p'):
            pid = line[1:]
        elif line.startswith('n') and pid:
            if (line[1:] + '/').startswith(root):
                pins.append(f'pid={pid}:cwd={line[1:]}')
    return sorted(set(pins))


class ConsumerPinRefusalTests(unittest.TestCase):
    def setUp(self):
        self.fx = Fixture()
        self.consumer = subprocess.Popen(
            [sys.executable, '-c', 'import time; time.sleep(120)'],
            cwd=str(self.fx.worktree))

    def tearDown(self):
        if self.consumer.poll() is None:
            self.consumer.kill()
        self.consumer.wait()
        self.fx.cleanup()

    def wait_for_pin(self, timeout=10.0):
        deadline = time.time() + timeout
        while time.time() < deadline:
            pins = live_pins(self.fx.worktree)
            if pins:
                return pins
            time.sleep(0.2)
        return live_pins(self.fx.worktree)

    def test_s13_refuses_with_live_consumer_then_proceeds_when_zero(self):
        pins = self.wait_for_pin()
        if pins is None:                       # no lsof: declared pin, still real pid
            pins = [f'pid={self.consumer.pid}:cwd={self.fx.worktree}']
            self.assertIsNone(self.consumer.poll(), 'consumer must be alive')
        # CONTROL: the detector must be able to return non-empty, otherwise a
        # green refusal below would prove nothing (empty detector != no consumer).
        self.assertTrue(pins, 'live consumer not detected — detector broken, '
                             'not the contract')

        state_before = set(self.fx.state.iterdir())
        with self.assertRaises(ct.EligibilityFailure) as cm:
            self.fx.run(consumers=pins)
        self.assertEqual(cm.exception.result, ct.CLEANUP_BLOCKED)
        failed = {c['name'] for c in cm.exception.checks if not c['ok']}
        self.assertEqual(failed, {'workers_stopped_no_dependent_consumers'})
        detail = next(c['detail'] for c in cm.exception.checks
                      if c['name'] == 'workers_stopped_no_dependent_consumers')
        self.assertIn(str(self.consumer.pid), detail)

        # deferred, not partial: nothing removed, nothing written
        self.assertTrue(self.fx.worktree.exists())
        self.assertTrue(self.fx.outputs.exists())
        self.assertEqual(set(self.fx.state.iterdir()), state_before)
        self.assertIsNone(self.consumer.poll(), 'consumer must survive')

        # pin released -> consumers are zero -> removal proceeds
        self.consumer.kill()
        self.consumer.wait()
        pins_after = self.wait_for_pin(timeout=5.0) or []
        self.assertEqual(pins_after, [], f'pin still detected: {pins_after}')

        receipt = self.fx.run(consumers=pins_after)
        self.assertEqual(receipt['result'], ct.CLEANUP_DONE)
        self.assertTrue(
            receipt['eligibility_contract']['workers_stopped_no_dependent_consumers'])
        self.assertFalse(self.fx.worktree.exists())
        self.assertFalse(self.fx.outputs.exists())


if __name__ == '__main__':
    unittest.main()
