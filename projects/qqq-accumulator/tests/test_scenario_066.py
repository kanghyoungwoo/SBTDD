import unittest

from qqq_support import FixtureF, et


class TestBandRuleNeverOperates(unittest.TestCase):
    def test_run_rejects_ma_band_as_operating_rule(self):
        env = FixtureF(self, overrides={"operating_rule.type": '"ma_band"'})
        result = env.run(et(11, 5, 15, 30))
        self.assertEqual(result.exit_code, 2)
        self.assertEqual(result.reasons, ["CONFIG_ERROR"])
        self.assertEqual(env.broker.place_calls, 0)
        self.assertEqual(env.store.list_orders(), [])


if __name__ == "__main__":
    unittest.main()
