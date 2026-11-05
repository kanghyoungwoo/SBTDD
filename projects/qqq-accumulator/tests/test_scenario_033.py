import unittest
from datetime import date
from decimal import Decimal

from qqq_support import FixtureF, et, notes


class TestRunPerOrderLimit(unittest.TestCase):
    def test_per_order_limit_reduces_quantity_and_warns(self):
        env = FixtureF(self, overrides={"limits.per_order_usd": "300"})
        result = env.run(et(11, 5, 15, 30))
        self.assertEqual(result.exit_code, 0)
        sent = env.broker.list_orders(date(2026, 11, 5))
        self.assertEqual(len(sent), 1)
        self.assertEqual(sent[0].quantity, Decimal(2))
        self.assertEqual(sent[0].limit_price, Decimal("102.00"))
        self.assertEqual(
            len(notes(env.notifier, kind="WARNING", reason="PER_ORDER_LIMIT_APPLIED")), 1)


if __name__ == "__main__":
    unittest.main()
