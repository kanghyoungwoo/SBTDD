import unittest
from decimal import Decimal

from src.app import record_adjustment
from qqq_support import FixtureF, et, notes


class TestPositionMismatchHalts(unittest.TestCase):
    def test_db_10_vs_broker_11_stops_new_orders(self):
        env = FixtureF(self, position="11")
        record_adjustment(env.store, Decimal(10), "초기 보유")
        result = env.run(et(11, 5, 15, 30))
        self.assertEqual(result.exit_code, 1)
        self.assertIn("POSITION_MISMATCH", result.reasons)
        self.assertEqual(env.broker.place_calls, 0)
        self.assertEqual(
            len(notes(env.notifier, kind="SAFETY", reason="POSITION_MISMATCH")), 1)


if __name__ == "__main__":
    unittest.main()
