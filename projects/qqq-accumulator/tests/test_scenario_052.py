import unittest

from qqq_support import FixtureF, et


class TestGuardOutsideWindow(unittest.TestCase):
    def test_before_window_sends_nothing(self):
        env = FixtureF(self)
        result = env.run(et(11, 5, 14, 0))
        self.assertEqual(result.exit_code, 0)
        self.assertEqual(env.broker.place_calls, 0)
        self.assertIn("OUTSIDE_WINDOW", result.reasons)


if __name__ == "__main__":
    unittest.main()
