import unittest
from datetime import date

from qqq_support import FixtureF, et, notes


class TestDailySummary(unittest.TestCase):
    def test_one_summary_per_trading_day_even_without_order(self):
        env = FixtureF(self, overrides={"operating_rule.threshold_usd": "50"})
        day = date(2026, 11, 5)
        first = env.run(et(11, 5, 15, 30))
        self.assertIn("NO_SIGNAL", first.reasons)
        self.assertEqual(first.exit_code, 0)
        self.assertEqual(len(notes(env.notifier, kind="DAILY_SUMMARY", trade_date=day)), 0)
        env.run(et(11, 5, 16, 15))
        self.assertEqual(len(notes(env.notifier, kind="DAILY_SUMMARY", trade_date=day)), 1)
        env.run(et(11, 5, 16, 30))
        self.assertEqual(len(notes(env.notifier, kind="DAILY_SUMMARY", trade_date=day)), 1)


if __name__ == "__main__":
    unittest.main()
