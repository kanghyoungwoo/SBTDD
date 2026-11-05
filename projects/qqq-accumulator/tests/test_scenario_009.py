import os
import unittest
from datetime import date

from src.app import DataImportError, import_csv
from qqq_support import open_days, week_store, write_bars


class TestImportOutsideCalendar(unittest.TestCase):
    def test_bars_beyond_calendar_are_rejected(self):
        root, store = week_store(self)
        dates = open_days(date(2026, 11, 2), date(2026, 11, 9))
        path = write_bars(os.path.join(root, "bars.csv"), dates)
        with self.assertRaises(DataImportError):
            import_csv(store, path)
        self.assertEqual(len(store.list_bars()), 0)


if __name__ == "__main__":
    unittest.main()
