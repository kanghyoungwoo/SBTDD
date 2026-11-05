import unittest
from datetime import datetime, time
from zoneinfo import ZoneInfo

from src.app import is_in_order_window


class TestOrderWindowDst(unittest.TestCase):
    def test_new_york_time_is_used_across_dst_change(self):
        seoul = ZoneInfo("Asia/Seoul")
        start, end, close = time(15, 0), time(15, 45), time(16, 0)
        before_change = datetime(2026, 10, 31, 4, 30, tzinfo=seoul)
        after_change = datetime(2026, 11, 3, 5, 30, tzinfo=seoul)
        too_late = datetime(2026, 11, 3, 5, 50, tzinfo=seoul)
        self.assertIs(is_in_order_window(before_change, start, end, close), True)
        self.assertIs(is_in_order_window(after_change, start, end, close), True)
        self.assertIs(is_in_order_window(too_late, start, end, close), False)


if __name__ == "__main__":
    unittest.main()
