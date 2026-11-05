import unittest
from decimal import Decimal

from qqq_support import FixtureF, et


class TestRunDryRun(unittest.TestCase):
    def test_dry_run_records_intent_without_sending(self):
        env = FixtureF(self, stage="dry-run")
        result = env.run(et(11, 5, 15, 30))
        self.assertEqual(result.exit_code, 0)
        self.assertEqual(env.broker.place_calls, 0)
        rows = [o for o in env.store.list_orders()
                if o.status == "DRY_RUN"
                and o.quantity == Decimal(4)
                and o.limit_price == Decimal("102.00")]
        self.assertEqual(len(rows), 1)
        self.assertIn("DRY_RUN_RECORDED", result.reasons)


if __name__ == "__main__":
    unittest.main()
