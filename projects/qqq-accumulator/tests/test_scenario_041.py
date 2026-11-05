import unittest
from decimal import Decimal

from src.app import record_adjustment
from qqq_support import FixtureF, et


class TestAdjustResumesOrders(unittest.TestCase):
    def test_adjust_with_reason_resumes_when_quantities_match(self):
        env = FixtureF(self, position="11")
        record_adjustment(env.store, Decimal(10), "초기 보유")
        env.run(et(11, 5, 15, 30))
        code, _out, _err = env.cli("adjust", "--shares", "1", "--reason", "수동 매수 반영")
        self.assertEqual(code, 0)
        result = env.run(et(11, 5, 15, 40))
        self.assertEqual(env.store.holdings(), Decimal(11))
        self.assertEqual(result.exit_code, 0)
        self.assertEqual(result.orders_sent, 1)


if __name__ == "__main__":
    unittest.main()
