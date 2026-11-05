import os
import unittest

from qqq_support import FixtureF, et


class TestGuardHaltFile(unittest.TestCase):
    def test_halt_file_blocks_orders(self):
        env = FixtureF(self, halt=True)
        self.assertTrue(os.path.exists(env.halt_path))
        result = env.run(et(11, 5, 15, 30))
        self.assertEqual(result.exit_code, 1)
        self.assertEqual(env.broker.place_calls, 0)
        self.assertIn("HALT_FILE", result.reasons)


if __name__ == "__main__":
    unittest.main()
