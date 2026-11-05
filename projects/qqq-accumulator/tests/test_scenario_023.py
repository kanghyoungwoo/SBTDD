import unittest
from decimal import Decimal

from src.app import evaluate_adoption


class TestAdoptionRejected(unittest.TestCase):
    def test_small_outperformance_is_not_adopted(self):
        pairs = [(Decimal(101), Decimal(100))] * 10
        result = evaluate_adoption(
            Decimal(102), Decimal(100), pairs, Decimal(3), Decimal(60))
        self.assertIs(result.adopted, False)
        self.assertEqual(result.outperformance_pct, Decimal(2))

    def test_low_rolling_ratio_is_not_adopted(self):
        pairs = [(Decimal(101), Decimal(100))] * 5 + [(Decimal(99), Decimal(100))] * 5
        result = evaluate_adoption(
            Decimal(105), Decimal(100), pairs, Decimal(3), Decimal(60))
        self.assertIs(result.adopted, False)
        self.assertEqual(result.rolling_ratio_pct, Decimal(50))


if __name__ == "__main__":
    unittest.main()
