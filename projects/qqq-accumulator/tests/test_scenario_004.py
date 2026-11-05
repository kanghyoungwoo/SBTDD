import io
import json
import os
import unittest
from datetime import date

from src.app import main
from qqq_support import db_path, new_root, write_calendar, write_text


class TestConfigImportNeedsNoNumbers(unittest.TestCase):
    def test_import_data_works_with_only_database_path(self):
        root = new_root(self)
        config = write_text(
            os.path.join(root, "config.toml"),
            "[paths]\ndatabase = %s\n" % json.dumps(db_path(root)))
        calendar = write_calendar(
            os.path.join(root, "calendar.csv"), date(2026, 11, 2), date(2026, 11, 6))
        code = main(["--config", config, "import-data", "--file", calendar],
                    stdout=io.StringIO(), stderr=io.StringIO())
        self.assertEqual(code, 0)


if __name__ == "__main__":
    unittest.main()
