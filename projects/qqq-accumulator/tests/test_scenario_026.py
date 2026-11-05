import unittest
from decimal import Decimal

from src.app import compute_order


class TestComputeOrderPerOrderLimit(unittest.TestCase):
    def test_per_order_limit_binds(self):
        plan = compute_order(
            prev_close=Decimal(100), limit_margin_pct=Decimal(2),
            rule_amount=Decimal(500), orderable_cash=Decimal(500),
            per_order_limit=Decimal(300), monthly_remaining=Decimal(5000),
            buy_fee_pct=Decimal(0), fractional=False)
        self.assertEqual(plan.limit_price, Decimal("102.00"))
        self.assertEqual(plan.quantity, Decimal(2))
        self.assertEqual(plan.amount, Decimal(300))
        self.assertEqual(plan.binding, "PER_ORDER_LIMIT")


if __name__ == "__main__":
    unittest.main()
