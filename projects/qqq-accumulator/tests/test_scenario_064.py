import unittest
from decimal import Decimal

from src.app import simulate
from src.models import Rule
from qqq_support import make_bars, make_settings


class TestBandSplitIsNotABuySignal(unittest.TestCase):
    def test_split_halving_price_does_not_trigger_rebuy(self):
        bars = make_bars([100, 100, 100, 120, 120, 60, 60, 60], splits={5: 2})
        rule = Rule("band", "ma_band", ma_days=3, sell_above_pct=Decimal(10),
                    sell_fraction_pct=Decimal(100),
                    rebuy_at_or_below_pct=Decimal(-5))
        result = simulate(bars, [rule], make_settings(deposit_n=100))
        buys_after_sell = [x for x in result.decisions
                           if x.rule_id == "band" and x.side == "buy"
                           and x.date > bars[3].date]
        self.assertEqual(buys_after_sell, [])
        self.assertEqual(result.metrics["band"].cash_usd, Decimal(120))
        self.assertEqual(result.metrics["baseline"].final_shares, Decimal(2))


if __name__ == "__main__":
    unittest.main()
