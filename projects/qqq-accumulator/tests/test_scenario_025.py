import unittest
from decimal import Decimal

from src.app import compute_order


class TestComputeOrderBasic(unittest.TestCase):
    def test_limit_price_and_whole_share_quantity(self):
        plan = compute_order(
            prev_close=Decimal(100), limit_margin_pct=Decimal(2),
            rule_amount=Decimal(500), orderable_cash=Decimal(500),
            per_order_limit=Decimal(1000), monthly_remaining=Decimal(5000),
            buy_fee_pct=Decimal(0), fractional=False)
        self.assertEqual(plan.limit_price, Decimal("102.00"))
        self.assertEqual(plan.quantity, Decimal(4))
        self.assertIsNone(plan.reason)


if __name__ == "__main__":
    unittest.main()
