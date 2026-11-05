import io
import json
import os
import unittest

from src.app import main
from qqq_support import backtest_setup, write_config, db_path, write_rules

BAND = {"id": "band", "type": "ma_band", "ma_days": 20,
        "sell_above_pct": "15", "sell_fraction_pct": "50",
        "rebuy_at_or_below_pct": "0"}
SELL_SIM = {"sell_sim.sell_fee_pct": "0.25",
            "sell_sim.capital_gains_tax_pct": "22",
            "sell_sim.annual_exemption_usd": "1800"}


def backtest(env, config):
    out, err = io.StringIO(), io.StringIO()
    code = main(["--config", config, "backtest", "--rules", env.rules],
                stdout=out, stderr=err)
    return code, out.getvalue()


class TestBandRuleInBacktestCli(unittest.TestCase):
    def config(self, env, overrides):
        base = {"order.limit_margin_pct": "0", "shares.fractional": "true"}
        base.update(overrides)
        return write_config(os.path.join(env.root, "band.toml"), db_path(env.root),
                            os.path.join(env.root, "HALT"), overrides=base)

    def test_band_rule_reports_sell_metrics(self):
        env = backtest_setup(self, [BAND])
        code, out = backtest(env, self.config(env, SELL_SIM))
        self.assertEqual(code, 0)
        metrics = json.loads(out)["segments"]["evaluation"]["rules"]["band"]
        for key in ("sell_count", "realized_gain_usd", "tax_usd"):
            self.assertIn(key, metrics)

    def test_band_rule_requires_sell_sim_settings(self):
        env = backtest_setup(self, [BAND])
        code, out = backtest(env, self.config(env, {}))
        self.assertEqual(code, 2)
        self.assertEqual(out, "")

    def test_invalid_band_parameters_are_rejected(self):
        for bad in ({"sell_fraction_pct": "0"}, {"ma_days": 1},
                    {"rebuy_at_or_below_pct": "15"}, {"sell_above_pct": "-1"}):
            env = backtest_setup(self, [dict(BAND, **bad)])
            write_rules(env.rules, [dict(BAND, **bad)])
            code, out = backtest(env, self.config(env, SELL_SIM))
            self.assertEqual(code, 2, bad)
            self.assertEqual(out, "")


if __name__ == "__main__":
    unittest.main()
