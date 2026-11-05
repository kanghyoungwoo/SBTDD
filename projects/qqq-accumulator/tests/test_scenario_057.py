import unittest

from qqq_support import FixtureF, et, notes


class TestSafetyNotificationDeduplicated(unittest.TestCase):
    def test_halt_file_alert_is_sent_once_per_day(self):
        env = FixtureF(self, halt=True)
        env.run(et(11, 5, 15, 0))
        self.assertEqual(len(notes(env.notifier, kind="SAFETY", reason="HALT_FILE")), 1)
        env.run(et(11, 5, 15, 15))
        self.assertEqual(len(notes(env.notifier, kind="SAFETY", reason="HALT_FILE")), 1)


if __name__ == "__main__":
    unittest.main()
