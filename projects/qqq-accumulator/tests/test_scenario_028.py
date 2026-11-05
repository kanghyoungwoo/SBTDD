import unittest
from datetime import date
from decimal import Decimal

from qqq_support import FixtureF, et


class TestRunSendsLocOrder(unittest.TestCase):
    def test_paper_run_sends_one_loc_buy(self):
        env = FixtureF(self)
        result = env.run(et(11, 5, 15, 30))
        self.assertEqual(result.exit_code, 0)
        self.assertEqual(result.orders_sent, 1)
        self.assertEqual(env.broker.place_calls, 1)
        sent = env.broker.list_orders(date(2026, 11, 5))
        self.assertEqual(len(sent), 1)
        self.assertEqual(sent[0].symbol, "QQQ")
        self.assertEqual(sent[0].trade_date, date(2026, 11, 5))
        self.assertEqual(sent[0].quantity, Decimal(4))
        self.assertEqual(sent[0].limit_price, Decimal("102.00"))
        order = env.store.list_orders()[0]
        self.assertEqual(order.status, "SENT")
        self.assertTrue(order.broker_order_id)


if __name__ == "__main__":
    unittest.main()
