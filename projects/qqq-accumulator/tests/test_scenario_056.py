import unittest
from decimal import Decimal

from qqq_support import FixtureF, et


class TestNotifierFailureIgnored(unittest.TestCase):
    def test_failing_notifier_does_not_change_order_or_exit_code(self):
        env = FixtureF(self, notifier_fail=True,
                       overrides={"limits.per_order_usd": "300"})
        result = env.run(et(11, 5, 15, 30))
        self.assertEqual(result.exit_code, 0)
        order = env.store.list_orders()[0]
        self.assertEqual(order.status, "SENT")
        self.assertEqual(order.quantity, Decimal(2))
        self.assertEqual(env.broker.place_calls, 1)


if __name__ == "__main__":
    unittest.main()
