import os
import sqlite3
import unittest

from src.app import Store
from qqq_support import db_path, new_root


class TestStoreWalStrict(unittest.TestCase):
    def test_database_is_wal_and_all_tables_strict(self):
        root = new_root(self)
        path = db_path(root)
        store = Store.open(path)
        self.addCleanup(store.close)
        self.assertTrue(os.path.exists(path))
        conn = sqlite3.connect(path)
        try:
            mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
            tables = conn.execute(
                "SELECT name, sql FROM sqlite_master "
                "WHERE type = 'table' AND name NOT LIKE 'sqlite_%'").fetchall()
        finally:
            conn.close()
        self.assertEqual(mode.lower(), "wal")
        self.assertGreater(len(tables), 0)
        for name, sql in tables:
            self.assertIn("STRICT", sql.upper(), name)


if __name__ == "__main__":
    unittest.main()
