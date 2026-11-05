import unittest
from decimal import Decimal

from src.app import evaluate_adoption


class TestAdoptionAccepted(unittest.TestCase):
    def test_rule_meeting_both_thresholds_is_adopted(self):
        pairs = [(Decimal(101), Decimal(100))] * 7 + [(Decimal(99), Decimal(100))] * 3
        result = evaluate_adoption(
            Decimal(105), Decimal(100), pairs, Decimal(3), Decimal(60))
        self.assertIs(result.adopted, True)
        self.assertEqual(result.outperformance_pct, Decimal(5))
        self.assertEqual(result.rolling_ratio_pct, Decimal(70))


if __name__ == "__main__":
    unittest.main()
