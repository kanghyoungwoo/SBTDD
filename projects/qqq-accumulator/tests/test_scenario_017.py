import unittest
from decimal import Decimal

from src.app import simulate
from qqq_support import decisions_of, make_bars, make_settings


class TestDividendWithholding(unittest.TestCase):
    def test_dividend_is_credited_net_and_not_a_deposit(self):
        bars = make_bars([100, 100, 100], dividends={2: "0.5"})
        settings = make_settings(
            deposit_n=10, deposit_amount=Decimal(400), fractional=False,
            withholding_pct=Decimal(15))
        result = simulate(bars, [], settings)
        self.assertEqual(decisions_of(result, "baseline"),
                         [(bars[0].date, Decimal(4), Decimal(100))])
        m = result.metrics["baseline"]
        self.assertEqual(m.final_shares, Decimal(4))
        self.assertEqual(m.cash_usd, Decimal("1.70"))
        self.assertEqual(m.total_deposit_usd, Decimal(400))


if __name__ == "__main__":
    unittest.main()
