import unittest

from qqq_support import FixtureF, et


class TestGuardLiveStage(unittest.TestCase):
    def test_live_stage_is_not_supported(self):
        env = FixtureF(self, stage="live")
        result = env.run(et(11, 5, 15, 30))
        self.assertEqual(result.exit_code, 2)
        self.assertEqual(env.broker.place_calls, 0)
        self.assertIn("STAGE_NOT_SUPPORTED", result.reasons)


if __name__ == "__main__":
    unittest.main()
