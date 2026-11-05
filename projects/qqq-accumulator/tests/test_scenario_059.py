import json
import unittest
from decimal import Decimal

from src.app import record_adjustment
from qqq_support import FixtureF, et


class TestStatusShowsHalt(unittest.TestCase):
    def test_status_reports_active_halt_and_last_run(self):
        env = FixtureF(self, position="11")
        record_adjustment(env.store, Decimal(10), "초기 보유")
        env.run(et(11, 5, 15, 30))
        code, out, _err = env.cli("status")
        self.assertEqual(code, 0)
        data = json.loads(out)
        self.assertIn("POSITION_MISMATCH", data["active_halts"])
        self.assertEqual(data["last_run"]["exit_code"], 1)


if __name__ == "__main__":
    unittest.main()
