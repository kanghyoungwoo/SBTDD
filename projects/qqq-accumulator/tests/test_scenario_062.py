import unittest
from datetime import date
from decimal import Decimal

from src.app import simulate
from src.models import Rule
from qqq_support import make_bars, make_settings


def band(fraction="100"):
    return Rule("band", "ma_band", ma_days=3, sell_above_pct=Decimal(10),
                sell_fraction_pct=Decimal(fraction),
                rebuy_at_or_below_pct=Decimal(0))


class TestBandCapitalGainsTax(unittest.TestCase):
    def test_tax_is_held_back_from_rebuy(self):
        bars = make_bars([100, 100, 100, 120, 120, 90, 90])
        result = simulate(bars, [band()], make_settings(
            deposit_n=100, capital_gains_tax_pct=Decimal(22)))
        m = result.metrics["band"]
        self.assertEqual(m.tax_usd, Decimal("4.40"))
        self.assertEqual(m.final_shares, Decimal("1.284444"))
        self.assertEqual(m.cash_usd, Decimal(0))

    def test_gain_within_annual_exemption_is_not_taxed(self):
        bars = make_bars([100, 100, 100, 120, 120, 90, 90])
        result = simulate(bars, [band()], make_settings(
            deposit_n=100, capital_gains_tax_pct=Decimal(22),
            annual_exemption_usd=Decimal(25)))
        self.assertEqual(result.metrics["band"].tax_usd, Decimal(0))
        self.assertEqual(result.metrics["band"].final_shares, Decimal("1.333333"))

    def test_exemption_applies_per_calendar_year(self):
        closes = [100, 100, 100, 120, 120, 90, 90, 90, 90, 110, 110, 90]
        settings = make_settings(deposit_n=100, capital_gains_tax_pct=Decimal(22),
                                 annual_exemption_usd=Decimal(15))
        same_year = simulate(make_bars(closes, start=date(2025, 12, 1)),
                             [band("50")], settings).metrics["band"]
        two_years = simulate(make_bars(closes, start=date(2025, 12, 19)),
                             [band("50")], settings).metrics["band"]
        self.assertEqual(same_year.sell_count, 2)
        self.assertEqual(same_year.realized_gain_usd, Decimal("19.17"))
        self.assertEqual(same_year.tax_usd, Decimal("0.92"))
        self.assertEqual(two_years.sell_count, 2)
        self.assertEqual(two_years.tax_usd, Decimal(0))


if __name__ == "__main__":
    unittest.main()
