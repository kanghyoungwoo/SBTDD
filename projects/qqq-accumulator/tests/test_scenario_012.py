import unittest
from decimal import Decimal

from src.app import simulate
from qqq_support import decisions_of, make_bars, make_settings


class TestBaselineExample(unittest.TestCase):
    def test_baseline_buys_four_shares(self):
        bars = make_bars([100, 100, 50, 50, 100, 100])
        result = simulate(bars, [], make_settings())
        self.assertEqual(decisions_of(result, "baseline"), [
            (bars[0].date, Decimal(1), Decimal(100)),
            (bars[2].date, Decimal(2), Decimal(50)),
            (bars[4].date, Decimal(1), Decimal(100)),
        ])
        m = result.metrics["baseline"]
        self.assertEqual(m.final_shares, Decimal(4))
        self.assertEqual(m.cash_usd, Decimal(0))
        self.assertEqual(m.equivalent_shares, Decimal(4))
        self.assertEqual(m.total_deposit_usd, Decimal(300))
        self.assertEqual(m.average_cost_usd, Decimal(75))
        self.assertEqual(m.unfilled_count, 0)
        self.assertEqual(m.cash_waiting_days, 0)


if __name__ == "__main__":
    unittest.main()
