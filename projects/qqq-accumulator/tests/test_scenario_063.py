import unittest
from decimal import Decimal

from src.app import simulate
from src.models import Rule
from qqq_support import make_bars, make_settings


class TestBandMissesRally(unittest.TestCase):
    def test_price_that_keeps_rising_leaves_band_with_fewer_shares(self):
        bars = make_bars([100, 100, 100, 120, 120, 130, 140, 150])
        rule = Rule("band", "ma_band", ma_days=3, sell_above_pct=Decimal(10),
                    sell_fraction_pct=Decimal(100),
                    rebuy_at_or_below_pct=Decimal(0))
        m = simulate(bars, [rule], make_settings(deposit_n=100)).metrics["band"]
        self.assertEqual(m.final_shares, Decimal(0))
        self.assertEqual(m.cash_usd, Decimal(120))
        self.assertEqual(m.equivalent_shares, Decimal("0.8"))
        self.assertEqual(m.final_shares_diff_vs_baseline, Decimal(-1))
        self.assertEqual(m.equivalent_shares_diff_vs_baseline, Decimal("-0.2"))


if __name__ == "__main__":
    unittest.main()
