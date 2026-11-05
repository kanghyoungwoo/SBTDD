import unittest
from datetime import date
from decimal import Decimal

from src.app import record_adjustment
from qqq_support import FixtureF, d, et


class TestSplitAppliedToHoldings(unittest.TestCase):
    def test_split_bar_doubles_db_holdings_and_is_not_abnormal(self):
        split_bar = {"open": "50", "high": "50", "low": "50", "close": "50",
                     "split_factor": "2"}
        env = FixtureF(self, position="20", bar_overrides={d("2026-11-04"): split_bar})
        record_adjustment(env.store, Decimal(10), "초기 보유")
        result = env.run(et(11, 5, 15, 30))
        self.assertEqual(env.store.holdings(), Decimal(20))
        self.assertNotIn("POSITION_MISMATCH", result.reasons)
        self.assertNotIn("ABNORMAL_PRICE", result.reasons)
        self.assertEqual(result.exit_code, 0)
        sent = env.broker.list_orders(date(2026, 11, 5))
        self.assertEqual(len(sent), 1)
        self.assertEqual(sent[0].limit_price, Decimal("51.00"))
        self.assertEqual(sent[0].quantity, Decimal(9))


if __name__ == "__main__":
    unittest.main()
