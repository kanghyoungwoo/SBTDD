import io
import unittest

from src.app import main
from qqq_support import backtest_setup


class TestBacktestUnknownRuleType(unittest.TestCase):
    def test_unknown_rule_type_exits_2_with_empty_stdout(self):
        env = backtest_setup(self, [{"id": "r1", "type": "rsi", "threshold_usd": "30"}])
        out = io.StringIO()
        code = main(["--config", env.config, "backtest", "--rules", env.rules],
                    stdout=out, stderr=io.StringIO())
        self.assertEqual(code, 2)
        self.assertEqual(out.getvalue(), "")


if __name__ == "__main__":
    unittest.main()
