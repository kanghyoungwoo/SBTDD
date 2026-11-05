import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


REPO = Path(__file__).resolve().parents[1]


class HarnessTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        # Resolved like the CLI's --root: temporary folders can sit behind a symlink (macOS /var).
        self.root = Path(self.temp.name).resolve()
        (self.root / "logic.py").write_text("VALUE = 2\n", encoding="utf-8")
        (self.root / "test_logic.py").write_text(
            "import unittest\nfrom logic import VALUE\n"
            "class LogicTests(unittest.TestCase):\n"
            "    def test_value(self):\n"
            "        self.assertEqual(VALUE, 2)\n",
            encoding="utf-8",
        )
        self.manifest = {
            "version": 1,
            "inputs": ["logic.py", "test_logic.py"],
            "requirements": [{"id": "REQ-1", "description": "올바른 값 반환"}],
            "scenarios": [{
                "id": "SCN-1", "requirement": "REQ-1",
                "given": "값이 2일 때", "when": "조회하면", "then": "2를 반환한다",
            }],
            "checks": [{
                "id": "CHK-1", "kind": "acceptance", "scenarios": ["SCN-1"],
                "command": ["{python}", "-B", "-m", "unittest", "test_logic"],
            }],
        }
        self.save()

    def save(self):
        (self.root / "harness.json").write_text(
            json.dumps(self.manifest, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def cli(self, *args, expected=0, env=None):
        env = dict(os.environ, PYTHONPATH=str(REPO), PYTHONIOENCODING="utf-8", **(env or {}))
        result = subprocess.run(
            [sys.executable, "-B", "-m", "harness", "--root", str(self.root), *args],
            cwd=REPO, env=env, capture_output=True, text=True, encoding="utf-8",
            timeout=15,
        )
        self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
        self.assertEqual(result.stderr, "")
        return json.loads(result.stdout)

    def test_valid_links(self):
        result = self.cli("check")
        self.assertEqual(result["status"], "valid")
        self.assertEqual(result["counts"], {"requirements": 1, "scenarios": 1, "checks": 1})

    def test_invalid_links(self):
        self.manifest["scenarios"][0]["requirement"] = "REQ-MISSING"
        self.save()
        result = self.cli("check", expected=2)
        self.assertIn("REQ-MISSING", result["error"])

    def test_missing_acceptance(self):
        self.manifest["checks"][0]["kind"] = "unit"
        self.save()
        self.assertIn("acceptance", self.cli("check", expected=2)["error"])

    def test_duplicate_ids(self):
        self.manifest["requirements"].append(dict(self.manifest["requirements"][0]))
        self.save()
        self.assertIn("duplicate", self.cli("check", expected=2)["error"])

    def test_uncovered_requirement(self):
        self.manifest["requirements"].append({"id": "REQ-2", "description": "다른 요구사항"})
        self.save()
        self.assertIn("REQ-2", self.cli("check", expected=2)["error"])

    def test_invalid_configuration(self):
        original = json.loads(json.dumps(self.manifest))
        for field, value in [("version", 2), ("inputs", []), ("unknown", True)]:
            with self.subTest(field=field):
                self.manifest = dict(original, **{field: value})
                self.save()
                self.assertEqual(self.cli("check", expected=2)["status"], "error")

    def test_invalid_paths(self):
        for path in ["missing.py", "../outside.py", str(REPO)]:
            with self.subTest(path=path):
                self.manifest["inputs"] = [path]
                self.save()
                self.assertEqual(self.cli("check", expected=2)["status"], "error")

    def test_unverified_status(self):
        result = self.cli("status", expected=1)
        self.assertEqual(result["status"], "unverified")
        self.assertEqual(result["requirements"][0]["status"], "unverified")
        self.assertFalse((self.root / ".harness").exists())

    def test_run_and_status(self):
        run = self.cli("run")
        self.assertEqual(run["status"], "passed")
        self.assertEqual(run["results"][0]["exit_code"], 0)
        self.assertIn("Ran 1 test", run["results"][0]["stderr"])
        records = list((self.root / ".harness" / "runs").glob("*.json"))
        self.assertEqual(len(records), 1)
        self.assertEqual(json.loads(records[0].read_text(encoding="utf-8")), run)
        status = self.cli("status")
        self.assertEqual(status["status"], "passed")
        self.assertEqual(status["scenarios"][0]["checks"], ["CHK-1"])

    def test_failure_then_recovery(self):
        (self.root / "logic.py").write_text("VALUE = 3\n", encoding="utf-8")
        run = self.cli("run", expected=1)
        self.assertEqual(run["results"][0]["status"], "failed")
        self.assertIn("AssertionError", run["results"][0]["stderr"])
        self.assertEqual(self.cli("status", expected=1)["status"], "failed")
        (self.root / "logic.py").write_text("VALUE = 2\n", encoding="utf-8")
        self.cli("run")
        self.assertEqual(self.cli("status")["status"], "passed")
        self.assertEqual(len(list((self.root / ".harness" / "runs").glob("*.json"))), 2)

    def test_changed_inputs_are_stale(self):
        self.cli("run")
        with (self.root / "logic.py").open("a", encoding="utf-8") as stream:
            stream.write("# changed\n")
        result = self.cli("status", expected=1)
        self.assertEqual(result["status"], "stale")
        self.assertEqual(result["checks"][0]["last_result"], "passed")

    def test_changed_contract_is_stale(self):
        self.cli("run")
        self.manifest["scenarios"][0]["then"] = "새로운 기대 결과"
        self.save()
        self.assertEqual(self.cli("status", expected=1)["status"], "stale")

    def test_directory_addition_and_deletion(self):
        source = self.root / "src"
        source.mkdir()
        (source / "a.txt").write_text("A", encoding="utf-8")
        self.manifest["inputs"].append("src")
        self.save()
        self.cli("run")
        (source / "b.txt").write_text("B", encoding="utf-8")
        self.assertEqual(self.cli("status", expected=1)["status"], "stale")
        self.cli("run")
        (source / "b.txt").unlink()
        self.assertEqual(self.cli("status", expected=1)["status"], "stale")

    def test_run_records_and_cache_are_not_inputs(self):
        self.manifest["inputs"] = ["."]
        self.save()
        self.cli("run")
        cache = self.root / "__pycache__"
        cache.mkdir(exist_ok=True)
        (cache / "generated.pyc").write_bytes(b"cache")
        self.assertEqual(self.cli("status")["status"], "passed")

    def add_second_requirement(self):
        self.manifest["requirements"].append({"id": "REQ-2", "description": "추가 요구사항"})
        self.manifest["scenarios"].append({
            "id": "SCN-2", "requirement": "REQ-2",
            "given": "다른 상황", "when": "실행하면", "then": "성공한다",
        })
        second = dict(self.manifest["checks"][0], id="CHK-2", scenarios=["SCN-2"])
        self.manifest["checks"].append(second)
        self.save()

    def test_selected_run_preserves_other_results(self):
        self.add_second_requirement()
        run = self.cli("run", "--requirement", "REQ-1")
        self.assertEqual([item["id"] for item in run["results"]], ["CHK-1"])
        self.assertEqual(self.cli("status", expected=1)["status"], "unverified")
        self.cli("run", "--requirement", "REQ-2")
        self.assertEqual(self.cli("status")["status"], "passed")

    def test_unknown_requirement(self):
        result = self.cli("run", "--requirement", "REQ-MISSING", expected=2)
        self.assertIn("REQ-MISSING", result["error"])
        self.assertFalse((self.root / ".harness").exists())

    def test_launch_error_continues(self):
        self.add_second_requirement()
        self.manifest["checks"][0]["command"] = ["harness-nonexistent-executable-92ad"]
        self.save()
        run = self.cli("run", expected=1)
        self.assertEqual(run["results"][0]["reason"], "launch_error")
        self.assertEqual(run["results"][1]["status"], "passed")

    def test_timeout(self):
        self.manifest["checks"][0].update(
            command=["{python}", "-c", "import time; print('started', flush=True); time.sleep(10)"],
            timeout_seconds=1,
        )
        self.save()
        run = self.cli("run", expected=1)
        self.assertEqual(run["results"][0]["reason"], "timeout")
        self.assertIn("started", run["results"][0]["stdout"])

    def test_inputs_changed_during_run(self):
        self.manifest["checks"][0]["command"] = [
            "{python}", "-c",
            "from pathlib import Path; Path('logic.py').write_text('VALUE = 5\\n')",
        ]
        self.save()
        run = self.cli("run", expected=1)
        self.assertEqual(run["status"], "stale")
        self.assertFalse(run["stable"])
        self.assertEqual(self.cli("status", expected=1)["status"], "stale")

    def test_corrupt_history(self):
        self.cli("run")
        record = next((self.root / ".harness" / "runs").glob("*.json"))
        record.write_text('{"schema_version": 1}', encoding="utf-8")
        result = self.cli("status", expected=2)
        self.assertIn("record", result["error"])

    def test_malformed_json(self):
        (self.root / "harness.json").write_text("{broken", encoding="utf-8")
        self.assertIn("harness.json", self.cli("check", expected=2)["error"])

    def test_every_repository_test_is_linked_to_a_check(self):
        manifest = json.loads((REPO / "harness.json").read_text(encoding="utf-8"))
        names = [part for check in manifest["checks"] for part in check["command"] if part.startswith("tests.")]

        def test_ids(suite):
            for item in suite:
                yield from test_ids(item) if isinstance(item, unittest.TestSuite) else [item.id()]

        suite = unittest.defaultTestLoader.discover(str(REPO / "tests"), top_level_dir=str(REPO))
        unlinked = [test_id for test_id in test_ids(suite)
                    if not any(test_id == name or test_id.startswith(name + ".") for name in names)]
        self.assertEqual(unlinked, [], "Link these tests to a check in harness.json")


if __name__ == "__main__":
    unittest.main()
