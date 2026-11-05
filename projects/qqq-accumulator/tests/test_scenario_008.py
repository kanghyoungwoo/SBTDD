import os
import unittest

from src.app import DataImportError, import_csv
from qqq_support import WEEK, d, week_store, write_bars


class TestImportNonPositivePrice(unittest.TestCase):
    def test_zero_close_is_rejected(self):
        root, store = week_store(self)
        path = write_bars(
            os.path.join(root, "bars_zero.csv"), WEEK,
            overrides={d("2026-11-05"): {"close": "0"}})
        with self.assertRaises(DataImportError):
            import_csv(store, path)
        self.assertEqual(len(store.list_bars()), 0)

    def test_negative_open_is_rejected(self):
        root, store = week_store(self)
        path = write_bars(
            os.path.join(root, "bars_neg.csv"), WEEK,
            overrides={d("2026-11-05"): {"open": "-1"}})
        with self.assertRaises(DataImportError):
            import_csv(store, path)
        self.assertEqual(len(store.list_bars()), 0)


if __name__ == "__main__":
    unittest.main()
