import unittest
from decimal import Decimal

from src.app import record_adjustment
from qqq_support import FixtureF, et


class TestMismatchHaltPersists(unittest.TestCase):
    def test_halt_stays_until_adjust_even_if_quantities_match(self):
        env = FixtureF(self, position="11")
        record_adjustment(env.store, Decimal(10), "초기 보유")
        env.run(et(11, 5, 15, 30))
        env.broker.set_position(Decimal(10))
        result = env.run(et(11, 5, 15, 40))
        self.assertEqual(result.exit_code, 1)
        self.assertIn("POSITION_MISMATCH", result.reasons)
        self.assertEqual(env.broker.place_calls, 0)


if __name__ == "__main__":
    unittest.main()
