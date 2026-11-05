import unittest
from datetime import date

from qqq_support import FixtureF, et


class TestGuardMarketClosed(unittest.TestCase):
    def test_holiday_sends_nothing(self):
        env = FixtureF(self, bars_until=date(2026, 11, 25))
        result = env.run(et(11, 26, 15, 30))
        self.assertEqual(result.exit_code, 0)
        self.assertEqual(env.broker.place_calls, 0)
        self.assertIn("MARKET_CLOSED", result.reasons)


if __name__ == "__main__":
    unittest.main()
