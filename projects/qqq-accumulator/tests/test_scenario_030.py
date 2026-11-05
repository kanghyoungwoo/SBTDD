import unittest
from datetime import date
from decimal import Decimal

from qqq_support import FixtureF, et


class TestRunUnfilledNoReorder(unittest.TestCase):
    def test_unfilled_order_is_not_reordered_same_day(self):
        env = FixtureF(self)
        env.run(et(11, 5, 15, 30))
        env.broker.settle_close(date(2026, 11, 5), Decimal(103))
        first = env.run(et(11, 5, 16, 30))
        second = env.run(et(11, 5, 15, 45))
        order = env.store.list_orders()[0]
        self.assertEqual(order.status, "UNFILLED")
        self.assertEqual(env.store.holdings(), Decimal(0))
        self.assertEqual(first.orders_sent, 0)
        self.assertEqual(second.orders_sent, 0)
        self.assertEqual(env.broker.place_calls, 1)
        self.assertIn("ALREADY_ORDERED", second.reasons)


if __name__ == "__main__":
    unittest.main()
