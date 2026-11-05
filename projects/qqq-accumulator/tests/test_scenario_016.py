import unittest
from decimal import Decimal

from src.app import simulate
from qqq_support import make_bars, make_settings


class TestKrwDeposit(unittest.TestCase):
    def test_krw_deposit_is_converted_net_of_fx_cost(self):
        bars = make_bars([100, 100])
        settings = make_settings(
            deposit_n=10, deposit_amount=Decimal(130000), currency="KRW",
            fx_cost_pct=Decimal(1))
        result = simulate(bars, [], settings, {bars[0].date: Decimal(1300)})
        m = result.metrics["baseline"]
        self.assertEqual(m.total_deposit_usd, Decimal("99.00"))
        self.assertEqual(m.final_shares, Decimal("0.99"))
        self.assertEqual(m.cash_usd, Decimal(0))


if __name__ == "__main__":
    unittest.main()
