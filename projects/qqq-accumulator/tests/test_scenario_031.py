import unittest

from qqq_support import FixtureF, et


class TestRunSameDayTwice(unittest.TestCase):
    def test_second_run_same_day_does_not_send(self):
        env = FixtureF(self)
        env.run(et(11, 5, 15, 30))
        second = env.run(et(11, 5, 15, 45))
        self.assertEqual(env.broker.place_calls, 1)
        self.assertEqual(second.exit_code, 0)
        self.assertEqual(second.orders_sent, 0)
        self.assertIn("ALREADY_ORDERED", second.reasons)


if __name__ == "__main__":
    unittest.main()
