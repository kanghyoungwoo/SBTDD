import os
import unittest
from decimal import Decimal

from src.app import import_csv
from qqq_support import WEEK, d, sha256_file, week_store, write_bars


class TestImportBars(unittest.TestCase):
    def test_bars_import_stores_raw_values_and_hash(self):
        root, store = week_store(self)
        path = write_bars(
            os.path.join(root, "bars.csv"), WEEK,
            overrides={d("2026-11-04"): {
                "open": "99.5", "high": "101.25", "low": "98", "close": "100",
                "volume": "1234", "split_factor": "1", "dividend": "0.25"}})
        result = import_csv(store, path)
        self.assertEqual(result.kind, "bars")
        self.assertEqual(result.rows, 5)
        self.assertEqual(result.sha256, sha256_file(path))
        bar = [b for b in store.list_bars() if b.date == d("2026-11-04")][0]
        self.assertEqual(bar.open, Decimal("99.5"))
        self.assertEqual(bar.high, Decimal("101.25"))
        self.assertEqual(bar.low, Decimal("98"))
        self.assertEqual(bar.close, Decimal("100"))
        self.assertEqual(bar.volume, 1234)
        self.assertEqual(bar.split_factor, Decimal("1"))
        self.assertEqual(bar.dividend, Decimal("0.25"))


if __name__ == "__main__":
    unittest.main()
