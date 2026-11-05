import unittest
from datetime import date

from qqq_support import FixtureF, et


class TestGuardStaleBar(unittest.TestCase):
    def test_missing_previous_trading_day_bar_sends_nothing(self):
        env = FixtureF(self, bars_until=date(2026, 11, 3))
        result = env.run(et(11, 5, 15, 30))
        self.assertEqual(result.exit_code, 1)
        self.assertEqual(env.broker.place_calls, 0)
        self.assertIn("STALE_BAR", result.reasons)


if __name__ == "__main__":
    unittest.main()
