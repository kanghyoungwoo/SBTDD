import unittest
from decimal import Decimal

from src.app import simulate
from qqq_support import make_bars, make_settings


class TestSplitEvent(unittest.TestCase):
    def test_two_for_one_split_doubles_shares(self):
        bars = make_bars([100, 100, 50], splits={2: 2})
        settings = make_settings(deposit_n=10, deposit_amount=Decimal(100))
        result = simulate(bars, [], settings)
        m = result.metrics["baseline"]
        self.assertEqual(m.final_shares, Decimal(2))
        self.assertEqual(m.equivalent_shares, Decimal(2))
        self.assertEqual(m.average_cost_usd, Decimal(50))


if __name__ == "__main__":
    unittest.main()
