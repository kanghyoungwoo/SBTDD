import unittest
from datetime import datetime, timezone
from zoneinfo import ZoneInfoNotFoundError

from qqq_support import FixtureF


def missing_tz_loader(name):
    raise ZoneInfoNotFoundError(name)


class TestGuardTimezoneUnavailable(unittest.TestCase):
    def test_missing_tz_data_exits_2_without_order(self):
        env = FixtureF(self)
        now = datetime(2026, 11, 5, 20, 30, tzinfo=timezone.utc)
        result = env.run(now, tz_loader=missing_tz_loader)
        self.assertEqual(result.exit_code, 2)
        self.assertEqual(env.broker.place_calls, 0)
        self.assertIn("TIMEZONE_UNAVAILABLE", result.reasons)


if __name__ == "__main__":
    unittest.main()
