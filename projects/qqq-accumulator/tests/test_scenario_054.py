import unittest
from datetime import time

from src.app import is_in_order_window
from qqq_support import et


class TestOrderWindowEarlyClose(unittest.TestCase):
    def test_window_shifts_earlier_on_early_close_day(self):
        start, end, close = time(15, 0), time(15, 45), time(13, 0)
        self.assertIs(is_in_order_window(et(11, 27, 12, 30), start, end, close), True)
        self.assertIs(is_in_order_window(et(11, 27, 15, 30), start, end, close), False)


if __name__ == "__main__":
    unittest.main()
