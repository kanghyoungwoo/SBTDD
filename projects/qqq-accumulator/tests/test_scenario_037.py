import unittest
from datetime import date

from qqq_support import FixtureF, et, notes


class TestRecoverTimeoutBeforeAccept(unittest.TestCase):
    def test_unmatched_sending_order_becomes_unknown(self):
        env = FixtureF(self)
        env.broker.fail_next_place("timeout_before_accept")
        first = env.run(et(11, 5, 15, 30))
        self.assertEqual(first.exit_code, 2)
        second = env.run(et(11, 5, 15, 40))
        self.assertEqual(second.exit_code, 1)
        self.assertEqual(env.order_on(date(2026, 11, 5)).status, "UNKNOWN")
        self.assertIn("UNRESOLVED_ORDER", second.reasons)
        self.assertEqual(env.broker.place_calls, 1)
        self.assertGreaterEqual(len(notes(env.notifier, kind="SAFETY")), 1)


if __name__ == "__main__":
    unittest.main()
