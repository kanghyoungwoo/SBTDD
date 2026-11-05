import socket
import unittest
from datetime import date
from decimal import Decimal
from unittest import mock

from qqq_support import FixtureF, et


def _network_blocked(*args, **kwargs):
    raise OSError("network access is disabled in tests")


class TestOfflineRun(unittest.TestCase):
    def test_run_and_reconcile_need_no_network(self):
        for name in ("socket", "create_connection"):
            patcher = mock.patch.object(socket, name, _network_blocked)
            patcher.start()
            self.addCleanup(patcher.stop)
        env = FixtureF(self)
        first = env.run(et(11, 5, 15, 30))
        self.assertEqual(first.exit_code, 0)
        env.broker.settle_close(date(2026, 11, 5), Decimal(98))
        env.run(et(11, 5, 16, 30))
        self.assertEqual(env.store.list_orders()[0].status, "FILLED")


if __name__ == "__main__":
    unittest.main()
