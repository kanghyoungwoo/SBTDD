import io
import json
import unittest

from src.app import main
from qqq_support import backtest_setup


class TestBacktestCommand(unittest.TestCase):
    def test_backtest_outputs_segments_rolling_adoption_and_hash(self):
        env = backtest_setup(self, [
            {"id": "le60", "type": "close_at_or_below", "threshold_usd": "60"}])
        out = io.StringIO()
        code = main(["--config", env.config, "backtest", "--rules", env.rules],
                    stdout=out, stderr=io.StringIO())
        self.assertEqual(code, 0)
        data = json.loads(out.getvalue())
        self.assertEqual(data["data"]["bars_sha256"], env.bars_sha)
        self.assertEqual(data["segments"]["evaluation"]["start"], "2025-01-01")
        self.assertEqual(data["segments"]["tuning"]["end"], "2024-12-31")
        self.assertEqual(data["rolling"]["le60"]["windows"], 13)
        self.assertIs(data["adoption"]["le60"]["adopted"], False)
        self.assertEqual(data["selected_rule"], "baseline")
        baseline = data["segments"]["evaluation"]["rules"]["baseline"]
        for key in ("final_shares", "cash_usd", "equivalent_shares",
                    "total_deposit_usd", "average_cost_usd", "cash_waiting_days",
                    "unfilled_count", "final_shares_diff_vs_baseline"):
            self.assertIn(key, baseline)


if __name__ == "__main__":
    unittest.main()
