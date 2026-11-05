import json
import unittest
from datetime import date
from decimal import Decimal

from qqq_support import FixtureF, et


class TestStatusAfterFill(unittest.TestCase):
    def test_status_reports_shares_cost_and_recent_orders(self):
        env = FixtureF(self)
        env.run(et(11, 5, 15, 30))
        env.broker.settle_close(date(2026, 11, 5), Decimal(98))
        env.run(et(11, 5, 16, 30))
        code, out, _err = env.cli("status")
        self.assertEqual(code, 0)
        data = json.loads(out)
        self.assertEqual(Decimal(data["shares"]), Decimal(4))
        self.assertEqual(Decimal(data["average_cost_usd"]), Decimal(98))
        latest = data["recent_orders"][0]
        self.assertEqual(latest["status"], "FILLED")
        self.assertEqual(Decimal(latest["quantity"]), Decimal(4))
        self.assertEqual(Decimal(latest["limit_price"]), Decimal("102.00"))
        self.assertEqual(data["active_halts"], [])


if __name__ == "__main__":
    unittest.main()
