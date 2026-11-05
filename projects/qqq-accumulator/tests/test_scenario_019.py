import unittest
from decimal import Decimal

from src.app import simulate
from qqq_support import decisions_of, make_bars, make_settings


class TestBuyFee(unittest.TestCase):
    def test_fee_is_part_of_cost_and_quantity(self):
        bars = make_bars([100, 100])
        settings = make_settings(
            deposit_n=10, deposit_amount=Decimal(101), fractional=False,
            buy_fee_pct=Decimal(1))
        result = simulate(bars, [], settings)
        self.assertEqual(decisions_of(result, "baseline"),
                         [(bars[0].date, Decimal(1), Decimal(100))])
        m = result.metrics["baseline"]
        self.assertEqual(m.final_shares, Decimal(1))
        self.assertEqual(m.cash_usd, Decimal(0))
        self.assertEqual(m.average_cost_usd, Decimal(101))


if __name__ == "__main__":
    unittest.main()
