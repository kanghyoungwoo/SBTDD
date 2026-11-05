import unittest

from qqq_support import FixtureF, et


class TestGuardCalendarMissing(unittest.TestCase):
    def test_date_outside_calendar_sends_nothing(self):
        env = FixtureF(self)
        result = env.run(et(1, 4, 15, 30, year=2027))
        self.assertEqual(result.exit_code, 1)
        self.assertEqual(env.broker.place_calls, 0)
        self.assertIn("CALENDAR_MISSING", result.reasons)


if __name__ == "__main__":
    unittest.main()
