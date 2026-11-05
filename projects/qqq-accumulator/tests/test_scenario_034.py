import unittest
from datetime import date
from decimal import Decimal

from qqq_support import FixtureF, et, notes


class TestRunMonthlyLimit(unittest.TestCase):
    def test_exhausted_monthly_limit_stops_ordering(self):
        env = FixtureF(self, overrides={"limits.monthly_usd": "400"})
        env.run(et(11, 4, 15, 30))
        env.broker.settle_close(date(2026, 11, 4), Decimal(100))
        env.run(et(11, 4, 16, 30))
        self.assertEqual(env.order_on(date(2026, 11, 4)).status, "FILLED")
        env.broker.set_orderable_cash(Decimal(500))
        result = env.run(et(11, 5, 15, 30))
        self.assertEqual(result.exit_code, 1)
        self.assertIn("MONTHLY_LIMIT_REACHED", result.reasons)
        self.assertEqual(env.broker.place_calls, 1)
        self.assertEqual(
            len(notes(env.notifier, kind="SAFETY", reason="MONTHLY_LIMIT_REACHED")), 1)


if __name__ == "__main__":
    unittest.main()
