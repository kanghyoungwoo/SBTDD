import unittest
from decimal import Decimal

from src.app import Rule, simulate
from qqq_support import decisions_of, make_bars, make_settings


class TestCloseAtOrBelowRule(unittest.TestCase):
    def test_le60_buys_all_cash_when_close_is_low(self):
        bars = make_bars([100, 100, 50, 50, 100, 100])
        le60 = Rule("le60", "close_at_or_below", Decimal(60))
        result = simulate(bars, [le60], make_settings())
        self.assertEqual(decisions_of(result, "le60"),
                         [(bars[2].date, Decimal(4), Decimal(50))])
        m = result.metrics["le60"]
        self.assertEqual(m.final_shares, Decimal(4))
        self.assertEqual(m.cash_usd, Decimal(100))
        self.assertEqual(m.equivalent_shares, Decimal(5))
        self.assertEqual(m.total_deposit_usd, Decimal(300))
        self.assertEqual(m.average_cost_usd, Decimal(50))
        self.assertEqual(m.unfilled_count, 0)
        self.assertEqual(m.cash_waiting_days, 4)
        self.assertEqual(m.final_shares_diff_vs_baseline, Decimal(0))
        self.assertEqual(m.equivalent_shares_diff_vs_baseline, Decimal(1))


if __name__ == "__main__":
    unittest.main()
