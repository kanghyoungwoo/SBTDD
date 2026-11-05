import unittest
from decimal import Decimal

from src.app import compute_order


class TestComputeOrderInsufficientCash(unittest.TestCase):
    def test_cash_below_one_share_gives_zero_quantity(self):
        plan = compute_order(
            prev_close=Decimal(100), limit_margin_pct=Decimal(2),
            rule_amount=Decimal(50), orderable_cash=Decimal(50),
            per_order_limit=Decimal(1000), monthly_remaining=Decimal(5000),
            buy_fee_pct=Decimal(0), fractional=False)
        self.assertEqual(plan.quantity, Decimal(0))
        self.assertEqual(plan.reason, "INSUFFICIENT_CASH")


if __name__ == "__main__":
    unittest.main()
