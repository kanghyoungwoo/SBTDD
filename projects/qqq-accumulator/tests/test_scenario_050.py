import unittest

from qqq_support import FixtureF, et


class TestGuardNoBrokerAdapter(unittest.TestCase):
    def test_cli_run_without_broker_exits_2(self):
        env = FixtureF(self)
        code, _out, _err = env.cli(
            "run", broker=None, notifier=env.notifier, now=et(11, 5, 15, 30))
        self.assertEqual(code, 2)
        self.assertEqual(len(env.store.list_orders()), 0)


if __name__ == "__main__":
    unittest.main()
