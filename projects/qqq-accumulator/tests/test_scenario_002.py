import os
import unittest

from qqq_support import FixtureF, write_rules


class TestConfigBadLimitMargin(unittest.TestCase):
    def test_string_limit_margin_exits_2_with_empty_stdout(self):
        env = FixtureF(self, overrides={"order.limit_margin_pct": '"abc"'})
        rules = write_rules(
            os.path.join(env.root, "rules.json"),
            [{"id": "le60", "type": "close_at_or_below", "threshold_usd": "60"}],
        )
        code, out, _err = env.cli("backtest", "--rules", rules)
        self.assertEqual(code, 2)
        self.assertEqual(out, "")


if __name__ == "__main__":
    unittest.main()
