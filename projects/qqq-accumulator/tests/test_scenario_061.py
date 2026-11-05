import unittest
from decimal import Decimal

from src.app import simulate
from src.models import Rule
from qqq_support import make_bars, make_settings


def band(rebuy="0", fraction="100"):
    return Rule("band", "ma_band", ma_days=3, sell_above_pct=Decimal(10),
                sell_fraction_pct=Decimal(fraction),
                rebuy_at_or_below_pct=Decimal(rebuy))


class TestBandSellHighRebuyLow(unittest.TestCase):
    def test_sell_above_band_and_rebuy_below_average_adds_shares(self):
        bars = make_bars([100, 100, 100, 120, 120, 90, 90])
        result = simulate(bars, [band()], make_settings(deposit_n=100))
        sides = [(x.date, x.side, x.quantity, x.limit_price)
                 for x in result.decisions if x.rule_id == "band"]
        self.assertEqual(sides, [
            (bars[0].date, "buy", Decimal(1), Decimal(100)),
            (bars[3].date, "sell", Decimal(1), Decimal(120)),
            (bars[5].date, "buy", Decimal("1.333333"), Decimal(90)),
        ])
        m = result.metrics["band"]
        self.assertEqual(m.final_shares, Decimal("1.333333"))
        self.assertEqual(m.sell_count, 1)
        self.assertEqual(m.realized_gain_usd, Decimal(20))
        self.assertEqual(m.tax_usd, Decimal(0))
        self.assertEqual(result.metrics["baseline"].final_shares, Decimal(1))
        self.assertEqual(m.final_shares_diff_vs_baseline, Decimal("0.333333"))


if __name__ == "__main__":
    unittest.main()
