import os
import unittest

from src.app import DataImportError, import_csv
from qqq_support import WEEK, d, week_store, write_bars


class TestImportMissingTradingDay(unittest.TestCase):
    def test_missing_open_day_is_rejected(self):
        root, store = week_store(self)
        dates = [x for x in WEEK if x != d("2026-11-04")]
        path = write_bars(os.path.join(root, "bars.csv"), dates)
        with self.assertRaises(DataImportError):
            import_csv(store, path)
        self.assertEqual(len(store.list_bars()), 0)


if __name__ == "__main__":
    unittest.main()
