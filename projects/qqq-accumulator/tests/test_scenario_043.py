import unittest
from decimal import Decimal

from qqq_support import FixtureF


class TestAdjustRequiresReason(unittest.TestCase):
    def test_empty_reason_is_rejected(self):
        env = FixtureF(self)
        code, _out, _err = env.cli("adjust", "--shares", "1", "--reason", "")
        self.assertEqual(code, 2)
        self.assertEqual(env.store.holdings(), Decimal(0))


if __name__ == "__main__":
    unittest.main()
