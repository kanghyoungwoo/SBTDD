import unittest

from qqq_support import FixtureF, et, notes


class TestRunInsufficientCash(unittest.TestCase):
    def test_cash_below_one_share_warns_and_creates_no_order(self):
        env = FixtureF(self, cash="50")
        result = env.run(et(11, 5, 15, 30))
        self.assertEqual(result.exit_code, 0)
        self.assertEqual(env.broker.place_calls, 0)
        self.assertEqual(len(env.store.list_orders()), 0)
        self.assertIn("INSUFFICIENT_CASH", result.reasons)
        self.assertEqual(
            len(notes(env.notifier, kind="WARNING", reason="INSUFFICIENT_CASH")), 1)


if __name__ == "__main__":
    unittest.main()
