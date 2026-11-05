import unittest

from qqq_support import FixtureF, et, notes


class TestConfigMissingPerOrder(unittest.TestCase):
    def test_missing_per_order_limit_exits_2_without_order(self):
        env = FixtureF(self, omit=("limits.per_order_usd",))
        code, _out, _err = env.cli(
            "run", broker=env.broker, notifier=env.notifier, now=et(11, 5, 15, 30))
        self.assertEqual(code, 2)
        self.assertEqual(env.broker.place_calls, 0)
        self.assertGreaterEqual(len(notes(env.notifier, kind="ERROR")), 1)


if __name__ == "__main__":
    unittest.main()
