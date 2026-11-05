import unittest
from decimal import Decimal

from src.app import simulate
from qqq_support import make_bars, make_settings


class TestUnfilledLoc(unittest.TestCase):
    def test_close_above_limit_leaves_order_unfilled(self):
        bars = make_bars([100, 101])
        settings = make_settings(deposit_n=10, deposit_amount=Decimal(100))
        result = simulate(bars, [], settings)
        m = result.metrics["baseline"]
        self.assertEqual(m.final_shares, Decimal(0))
        self.assertEqual(m.cash_usd, Decimal(100))
        self.assertEqual(m.unfilled_count, 1)
        self.assertEqual(m.equivalent_shares, Decimal("0.990099"))


if __name__ == "__main__":
    unittest.main()
