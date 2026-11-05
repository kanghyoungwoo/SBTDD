import os
import unittest

from src.app import load_config
from qqq_support import db_path, new_root, write_config


class TestConfigDefaultStage(unittest.TestCase):
    def test_missing_stage_defaults_to_dry_run(self):
        root = new_root(self)
        path = write_config(
            os.path.join(root, "config.toml"), db_path(root),
            os.path.join(root, "HALT"), stage=None)
        config = load_config(path)
        self.assertEqual(config.stage, "dry-run")


if __name__ == "__main__":
    unittest.main()
