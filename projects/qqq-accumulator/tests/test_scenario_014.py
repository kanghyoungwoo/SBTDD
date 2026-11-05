import unittest
from decimal import Decimal

from src.app import simulate
from qqq_support import decisions_of, make_bars, make_settings


class TestWholeSharesCarryCash(unittest.TestCase):
    def test_leftover_cash_is_carried_to_next_deposit(self):
        bars = make_bars([100, 100, 100, 100])
        settings = make_settings(deposit_amount=Decimal(250), fractional=False)
        result = simulate(bars, [], settings)
        self.assertEqual(decisions_of(result, "baseline"), [
            (bars[0].date, Decimal(2), Decimal(100)),
            (bars[2].date, Decimal(3), Decimal(100)),
        ])
        m = result.metrics["baseline"]
        self.assertEqual(m.final_shares, Decimal(5))
        self.assertEqual(m.cash_usd, Decimal(0))
        self.assertEqual(m.total_deposit_usd, Decimal(500))


if __name__ == "__main__":
    unittest.main()
