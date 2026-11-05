import io
import os
import unittest

from src.app import import_csv, main
from qqq_support import WEEK, d, db_path, week_store, write_bars, write_config


class TestImportDuplicateRejected(unittest.TestCase):
    def test_duplicate_date_leaves_previous_snapshot_untouched(self):
        root, store = week_store(self)
        first = write_bars(os.path.join(root, "bars.csv"), WEEK)
        first_result = import_csv(store, first)
        config = write_config(
            os.path.join(root, "config.toml"), db_path(root),
            os.path.join(root, "HALT"))
        dup_dates = [WEEK[0], d("2026-11-03"), d("2026-11-03")] + WEEK[2:]
        second = write_bars(os.path.join(root, "bars_dup.csv"), dup_dates)
        err = io.StringIO()
        code = main(["--config", config, "import-data", "--file", second],
                    stdout=io.StringIO(), stderr=err)
        self.assertEqual(code, 2)
        self.assertEqual(len(store.list_bars()), 5)
        self.assertEqual(store.snapshot_sha256("bars"), first_result.sha256)


if __name__ == "__main__":
    unittest.main()
