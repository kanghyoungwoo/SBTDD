import unittest
from datetime import date
from decimal import Decimal

from qqq_support import FixtureF, et


class TestRunReflectsFill(unittest.TestCase):
    def test_close_below_limit_fills_order(self):
        env = FixtureF(self)
        env.run(et(11, 5, 15, 30))
        env.broker.settle_close(date(2026, 11, 5), Decimal(98))
        env.run(et(11, 5, 16, 30))
        order = env.store.list_orders()[0]
        self.assertEqual(order.status, "FILLED")
        self.assertEqual(order.fill_price, Decimal(98))
        self.assertEqual(order.fill_cost, Decimal("392.00"))
        self.assertEqual(env.store.holdings(), Decimal(4))
        self.assertEqual(env.broker.get_orderable_cash_usd(), Decimal("108.00"))
        self.assertEqual(env.broker.place_calls, 1)


if __name__ == "__main__":
    unittest.main()
