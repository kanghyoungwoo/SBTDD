import unittest

from qqq_support import FixtureF, d, et


class TestGuardAbnormalPrice(unittest.TestCase):
    def test_unexplained_price_jump_sends_nothing(self):
        drop = {"open": "80", "high": "80", "low": "80", "close": "80",
                "split_factor": "1"}
        env = FixtureF(self, bar_overrides={d("2026-11-04"): drop})
        result = env.run(et(11, 5, 15, 30))
        self.assertEqual(result.exit_code, 1)
        self.assertEqual(env.broker.place_calls, 0)
        self.assertIn("ABNORMAL_PRICE", result.reasons)


if __name__ == "__main__":
    unittest.main()
