import unittest
from datetime import date

from qqq_support import FixtureF, et


class TestRecoverTimeoutAfterAccept(unittest.TestCase):
    def test_sending_order_is_linked_without_resend(self):
        env = FixtureF(self)
        env.broker.fail_next_place("timeout_after_accept")
        first = env.run(et(11, 5, 15, 30))
        self.assertEqual(first.exit_code, 2)
        self.assertEqual(env.order_on(date(2026, 11, 5)).status, "SENDING")
        env.run(et(11, 5, 15, 45))
        order = env.order_on(date(2026, 11, 5))
        accepted = env.broker.list_orders(date(2026, 11, 5))
        self.assertEqual(len(accepted), 1)
        self.assertEqual(order.status, "SENT")
        self.assertEqual(order.broker_order_id, accepted[0].broker_order_id)
        self.assertEqual(env.broker.place_calls, 1)


if __name__ == "__main__":
    unittest.main()
