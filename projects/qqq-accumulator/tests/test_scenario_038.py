import unittest
from datetime import date

from qqq_support import FixtureF, et


class TestUnknownOrderResolvedAfterClose(unittest.TestCase):
    def test_unknown_becomes_not_placed_and_trading_resumes(self):
        env = FixtureF(self)
        env.broker.fail_next_place("timeout_before_accept")
        env.run(et(11, 5, 15, 30))
        env.run(et(11, 5, 15, 40))
        self.assertEqual(env.order_on(date(2026, 11, 5)).status, "UNKNOWN")
        env.reimport_bars(date(2026, 11, 5))
        env.run(et(11, 5, 16, 30))
        self.assertEqual(env.order_on(date(2026, 11, 5)).status, "NOT_PLACED")
        result = env.run(et(11, 6, 15, 30))
        self.assertEqual(result.exit_code, 0)
        self.assertEqual(result.orders_sent, 1)
        self.assertEqual(env.broker.place_calls, 2)


if __name__ == "__main__":
    unittest.main()
