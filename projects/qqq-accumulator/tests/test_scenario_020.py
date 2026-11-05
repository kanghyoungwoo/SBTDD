import unittest
from decimal import Decimal

from src.app import Rule, simulate
from qqq_support import make_bars, make_settings


class TestNoLookahead(unittest.TestCase):
    def test_future_prices_do_not_change_past_decisions(self):
        a = make_bars([100, 100, 50, 50, 100, 100])
        b = make_bars([100, 100, 50, 10, 500, 1])
        rules = [Rule("le60", "close_at_or_below", Decimal(60))]
        settings = make_settings()
        res_a = simulate(a, rules, settings)
        res_b = simulate(b, rules, settings)
        cutoff = a[2].date
        early_a = [x for x in res_a.decisions if x.date <= cutoff]
        early_b = [x for x in res_b.decisions if x.date <= cutoff]
        self.assertEqual(len(early_a), 3)
        self.assertEqual(early_a, early_b)


if __name__ == "__main__":
    unittest.main()
