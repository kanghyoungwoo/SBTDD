import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

from harness.agent import AgentError
from harness.core import fingerprint, load_manifest, project_status
from harness.spec import run_init, validate_spec


REPO = Path(__file__).resolve().parents[1]


def specification(outcome="continue", question=""):
    return {
        "outcome": outcome, "summary": "A value function", "question": question,
        "title": "Value project", "design": "Expose src.app.value() returning the integer 2. No arguments or dependencies.",
        "requirements": [{"id": "REQ-VALUE", "description": "Return the value 2"}],
        "scenarios": [{"id": "SCN-VALUE", "requirement": "REQ-VALUE",
                       "given": "The application is available", "when": "value() is called", "then": "It returns 2"}],
    }


def scaffold(root, context, directory, timeout):
    (root / "src" / "app.py").write_text("def value():\n    raise NotImplementedError\n", encoding="utf-8")
    (root / "tests" / "test_scenario_001.py").write_text(
        "import unittest\nfrom src.app import value\n"
        "class ValueTests(unittest.TestCase):\n"
        "    def test_value(self):\n        self.assertEqual(value(), 2)\n", encoding="utf-8")
    return {"outcome": "continue", "summary": "Created API stub and business assertion",
            "question": "", "red_check_ids": ["CHK-001"]}


class InitTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name).resolve()
        self.root = self.base / "project"
        self.root.mkdir()
        self.brief = self.base / "request.txt"
        self.brief.write_text("값 2를 반환하는 함수를 만들어 주세요.", encoding="utf-8")

    def run_with(self, claude=None, codex=None):
        with patch("harness.spec.invoke_claude", side_effect=claude or (lambda *args: specification())) as designer, \
                patch("harness.spec.invoke_codex", side_effect=codex or scaffold) as builder, \
                patch("harness.spec.require_providers"):
            result = run_init(self.root, self.brief)
        self.assertEqual(json.loads((self.root / result["record"]).read_text(encoding="utf-8")), result)
        return result, designer, builder

    def test_brief_to_contract_scaffold_and_observed_red(self):
        result, claude, codex = self.run_with()
        self.assertEqual(result["status"], "ready")
        self.assertEqual(result["red_check_ids"], ["CHK-001"])
        self.assertEqual(claude.call_args.args[1]["phase"], "spec")
        self.assertIn("값 2", claude.call_args.args[1]["brief"])
        self.assertEqual(codex.call_args.args[1]["phase"], "scaffold")
        manifest = load_manifest(self.root)
        self.assertEqual(manifest["agent"]["workflow"], "claude-codex")
        self.assertEqual(manifest["checks"][0]["command"],
                         ["{python}", "-B", "-m", "unittest", "discover", "-s", "tests", "-p", "test_scenario_001.py"])
        self.assertIn("REQ-VALUE", (self.root / "SPEC.md").read_text(encoding="utf-8"))
        self.assertIn("SCN-VALUE", (self.root / "SPEC.md").read_text(encoding="utf-8"))
        self.assertEqual((self.root / "BRIEF.md").read_text(encoding="utf-8"), self.brief.read_text(encoding="utf-8"))
        self.assertEqual(project_status(self.root, manifest, fingerprint(self.root, manifest))["status"], "failed")
        self.assertEqual(result["next_command"][-2:], ["--requirement", "REQ-VALUE"])
        ignored = (self.root / ".gitignore").read_text(encoding="utf-8").splitlines()
        self.assertIn(".harness/", ignored)
        self.assertIn(".gitignore", result["artifacts"])
        self.assertNotIn(".gitignore", manifest["inputs"])

    def test_generated_project_enters_existing_agent_workflow(self):
        from harness.agent import run_agent
        from tests.test_roles import design, review
        self.run_with()
        def implement(root, context, *args):
            if context["phase"] == "implement":
                (root / "src" / "app.py").write_text("def value():\n    return 2\n", encoding="utf-8")
            return {"outcome": "continue", "summary": "Implement the value contract",
                    "question": "", "red_check_ids": ["CHK-001"]}
        with patch("harness.agent.invoke_codex", side_effect=implement), \
                patch("harness.agent.require_providers"), \
                patch("harness.claude.invoke_claude", side_effect=lambda root, context, *args:
                      design() if context["phase"] == "design" else review()):
            result = run_agent(self.root, load_manifest(self.root))
        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["review_status"], "approved")

    def test_spec_question_does_not_publish_project(self):
        result, _, codex = self.run_with(claude=lambda *args: specification("needs_input", "Which value is required?"))
        self.assertEqual(result["status"], "needs_input")
        self.assertEqual(result["question"], "Which value is required?")
        self.assertFalse((self.root / "harness.json").exists())
        codex.assert_not_called()

    def test_invalid_references_are_rejected_before_scaffolding(self):
        def invalid(*args):
            value = specification()
            value["scenarios"][0]["requirement"] = "REQ-MISSING"
            return value
        result, _, codex = self.run_with(claude=invalid)
        self.assertEqual(result["status"], "error")
        self.assertFalse((self.root / "harness.json").exists())
        codex.assert_not_called()

    def test_scaffold_question_preserves_draft(self):
        def question(*args):
            return {"outcome": "needs_input", "summary": "Ambiguous API", "question": "Which return type?", "red_check_ids": []}
        result, _, _ = self.run_with(codex=question)
        self.assertEqual(result["status"], "needs_input")
        self.assertFalse((self.root / "harness.json").exists())
        self.assertTrue((self.root / result["draft"] / "SPEC.md").exists())

    def test_scaffold_cannot_rewrite_generated_contract(self):
        def change(root, context, directory, timeout):
            result = scaffold(root, context, directory, timeout)
            (root / "SPEC.md").write_text("Weaken the requirement", encoding="utf-8")
            return result
        result, _, _ = self.run_with(codex=change)
        self.assertEqual(result["reason"], "scope_changed")
        self.assertFalse((self.root / "src").exists())

    def test_missing_tests_and_already_implemented_scaffolds_are_rejected(self):
        problems = {"no_tests": "no_tests", "implemented": "not_failing", "import_error": "import_error",
                    "fake_failure": "assertion_failures", "test_only_error": "not_source_stub"}
        for kind in problems:
            with self.subTest(kind=kind):
                def broken(root, context, directory, timeout):
                    response = scaffold(root, context, directory, timeout)
                    if kind == "no_tests":
                        (root / "tests" / "test_scenario_001.py").write_text("# No tests\n", encoding="utf-8")
                    elif kind == "implemented":
                        (root / "src" / "app.py").write_text("def value():\n    return 2\n", encoding="utf-8")
                    elif kind == "import_error":
                        (root / "src" / "app.py").write_text("import missing_dependency_for_harness_test\n", encoding="utf-8")
                    elif kind == "test_only_error":
                        (root / "tests" / "test_scenario_001.py").write_text(
                            "import unittest\nclass EmptyTests(unittest.TestCase):\n"
                            "    def test_placeholder(self):\n        raise NotImplementedError\n", encoding="utf-8")
                    else:
                        (root / "tests" / "test_scenario_001.py").write_text(
                            "import unittest\nclass EmptyTests(unittest.TestCase):\n"
                            "    def test_placeholder(self):\n        self.fail('TODO')\n", encoding="utf-8")
                    return response
                result, _, _ = self.run_with(codex=broken)
                self.assertEqual(result["status"], "needs_input")
                self.assertEqual(result["reason"], "scaffold_not_red")
                self.assertEqual(result["stub_red_problems"], {"CHK-001": problems[kind]})
                self.assertFalse((self.root / "harness.json").exists())

    def test_wrong_red_ids_cannot_complete_initialization(self):
        def wrong(root, context, directory, timeout):
            response = scaffold(root, context, directory, timeout)
            response["red_check_ids"] = ["CHK-MISSING"]
            return response
        result, _, _ = self.run_with(codex=wrong)
        self.assertEqual(result["reason"], "scaffold_not_red")

    def test_preexisting_project_is_never_overwritten(self):
        existing = self.root / "user.py"
        existing.write_text("important = True\n", encoding="utf-8")
        with patch("harness.spec.invoke_claude") as claude, self.assertRaises(ValueError):
            run_init(self.root, self.brief)
        self.assertEqual(existing.read_text(encoding="utf-8"), "important = True\n")
        claude.assert_not_called()

    def test_brief_can_already_be_in_empty_project(self):
        self.brief = self.root / "BRIEF.md"
        self.brief.write_text("Return 2", encoding="utf-8")
        result, _, _ = self.run_with()
        self.assertEqual(result["status"], "ready")
        self.assertEqual(self.brief.read_text(encoding="utf-8"), "Return 2")

    def test_concurrent_user_file_prevents_publication(self):
        def concurrent(root, context, directory, timeout):
            (self.root / "keep.txt").write_text("User work", encoding="utf-8")
            return scaffold(root, context, directory, timeout)
        result, _, _ = self.run_with(codex=concurrent)
        self.assertEqual(result["status"], "needs_input")
        self.assertEqual(result["reason"], "project_changed")
        self.assertFalse((self.root / "harness.json").exists())
        self.assertEqual((self.root / "keep.txt").read_text(encoding="utf-8"), "User work")

    def test_changed_brief_prevents_publication(self):
        def concurrent(root, context, directory, timeout):
            self.brief.write_text("Return 3 instead", encoding="utf-8")
            return scaffold(root, context, directory, timeout)
        result, _, _ = self.run_with(codex=concurrent)
        self.assertEqual(result["reason"], "brief_changed")
        self.assertFalse((self.root / "harness.json").exists())

    def test_claude_cannot_write_project_files(self):
        def change(root, *args):
            (root / "unexpected.py").write_text("pass\n", encoding="utf-8")
            return specification()
        result, _, codex = self.run_with(claude=change)
        self.assertEqual(result["reason"], "scope_changed")
        codex.assert_not_called()
        self.assertFalse((self.root / "unexpected.py").exists())

    def test_provider_error_is_preserved_without_publishing(self):
        result, _, _ = self.run_with(codex=AgentError("agent_exit", "Usage limit reached"))
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["reason"], "agent_exit")
        self.assertFalse((self.root / "harness.json").exists())

    def test_init_cli_does_not_require_existing_manifest(self):
        empty = self.base / "empty.txt"
        empty.write_text("   ", encoding="utf-8")
        result = subprocess.run(
            [sys.executable, "-B", "-m", "harness", "--root", str(self.root), "init", "--brief", str(empty)],
            cwd=REPO, env=dict(os.environ, PYTHONIOENCODING="utf-8"),
            capture_output=True, text=True, encoding="utf-8", timeout=15)
        self.assertEqual(result.returncode, 2)
        self.assertIn("brief", json.loads(result.stdout)["error"].lower())
        self.assertNotIn("harness.json", result.stdout)

    def test_spec_schema_rejects_missing_information(self):
        for value in (dict(specification(), requirements=[]), dict(specification(), design=""),
                      specification("needs_input", ""), dict(specification(), extra=True)):
            with self.subTest(value=value), self.assertRaises(AgentError):
                validate_spec(value)


    def test_module_import_failure_is_not_a_source_stub_red(self):
        def broken(root, context, directory, timeout):
            response = scaffold(root, context, directory, timeout)
            (root / "src" / "app.py").write_text("raise NotImplementedError\n", encoding="utf-8")
            return response
        result, _, _ = self.run_with(codex=broken)
        self.assertEqual(result["status"], "needs_input")
        self.assertEqual(result["reason"], "scaffold_not_red")
        self.assertEqual(result["stub_red_problems"], {"CHK-001": "import_error"})
        self.assertFalse((self.root / "harness.json").exists())

    def test_partial_or_mixed_unittest_outcomes_are_explained(self):
        from harness.spec import stub_red_problem
        def result(stderr, exit_code=1, reason="exit_code"):
            return {"status": "failed" if exit_code else "passed", "reason": reason,
                    "exit_code": exit_code, "stderr": stderr}
        for value, problem in [(result("", None, "timeout"), "timeout"),
                               (result("Ran 2 tests in 0.1s\n\nFAILED (errors=1)\n"), "partial_errors"),
                               (result("Ran 2 tests in 0.1s\n\nFAILED (errors=1, skipped=1)\n"), "unexpected_outcomes"),
                               (result("Ran 1 test in 0.1s\nSegmentation fault\n"), "unrecognized_output")]:
            with self.subTest(problem=problem):
                self.assertEqual(stub_red_problem(self.root, value), problem)

    def test_reserved_brief_name_is_rejected_before_generation(self):
        for name in ("SPEC.md", ".gitignore"):
            with self.subTest(name=name):
                self.brief = self.root / name
                self.brief.write_text("Return 2", encoding="utf-8")
                with patch("harness.spec.invoke_claude") as claude, self.assertRaisesRegex(ValueError, "reserved"):
                    run_init(self.root, self.brief)
                claude.assert_not_called()
                self.assertEqual(list(self.root.iterdir()), [self.brief])
                self.brief.unlink()

    def test_claude_spec_uses_spec_schema_and_instructions(self):
        from harness.claude import invoke_claude
        directory = self.root / "logs"
        directory.mkdir()
        process = Mock(returncode=0)
        process.communicate.return_value = (json.dumps({"type": "result", "subtype": "success",
                                                      "is_error": False, "structured_output": specification()}), "")
        with patch("harness.claude.shutil.which", return_value="claude.exe"), \
                patch("harness.agent.subprocess.Popen", return_value=process) as launch:
            result = invoke_claude(self.root, {"phase": "spec", "brief": "Return 2"}, directory, 30)
        self.assertEqual(result["requirements"][0]["id"], "REQ-VALUE")
        command = launch.call_args.args[0]
        schema = json.loads(command[command.index("--json-schema") + 1])
        self.assertIn("requirements", schema["properties"])
        self.assertNotIn("verdict", schema["properties"])
        self.assertIn("NEW Python project", process.communicate.call_args.kwargs["input"])

    def test_codex_scaffold_uses_stub_instructions(self):
        from harness.agent import invoke_codex
        directory = self.root / "logs"
        directory.mkdir()
        process = Mock(returncode=0)
        process.communicate.return_value = (json.dumps({"outcome": "continue", "summary": "Stub ready",
                                                      "question": "", "red_check_ids": ["CHK-001"]}), "")
        with patch("harness.agent.shutil.which", return_value="codex.exe"), \
                patch("harness.agent.subprocess.Popen", return_value=process):
            result = invoke_codex(self.root, {"phase": "scaffold"}, directory, 30)
        self.assertEqual(result["red_check_ids"], ["CHK-001"])
        self.assertIn("Do not implement business behavior yet", process.communicate.call_args.kwargs["input"])

    def test_ready_is_successful_in_public_cli(self):
        from harness.__main__ import main
        for extra, options in [([], {"implementer": "codex", "review_model": None, "implement_model": None,
                                     "python": None}),
                               (["--implementer", "claude", "--review-model", "opus", "--implement-model", "sonnet"],
                                {"implementer": "claude", "review_model": "opus", "implement_model": "sonnet",
                                 "python": None})]:
            with self.subTest(extra=extra), \
                    patch("sys.argv", ["harness", "--root", str(self.root), "init", "--brief", str(self.brief), *extra]), \
                    patch("harness.__main__.run_init", return_value={"status": "ready"}) as initialize, \
                    patch("harness.__main__.load_manifest", side_effect=AssertionError("Must not load an existing contract")), \
                    patch("builtins.print"):
                self.assertEqual(main(), 0)
            initialize.assert_called_once_with(self.root, self.brief, 300, **options)

    def test_claude_implementer_scaffolds_and_generates_claude_workflow(self):
        def writer(root, context, directory, timeout, model=None):
            self.assertEqual(model, "sonnet")
            return scaffold(root, context, directory, timeout)
        def designer(root, context, directory, timeout, model=None):
            self.assertEqual(model, "opus")
            return specification()
        with patch("harness.spec.invoke_claude", side_effect=designer), \
                patch("harness.spec.invoke_claude_writer", side_effect=writer), \
                patch("harness.spec.invoke_codex") as codex, \
                patch("harness.spec.require_providers") as providers:
            result = run_init(self.root, self.brief, implementer="claude", review_model="opus", implement_model="sonnet")
        self.assertEqual(result["status"], "ready")
        codex.assert_not_called()
        providers.assert_called_once_with(["claude"], claude_writer=True)
        self.assertEqual([(p["phase"], p.get("provider")) for p in result["phases"]],
                         [("spec", "claude"), ("scaffold", "claude"), ("red", None)])
        self.assertEqual(load_manifest(self.root)["agent"]["workflow"], "claude")
        self.assertEqual(result["models"], {"review": "opus", "implement": "sonnet"})
        self.assertEqual(result["next_command"][-4:], ["--review-model", "opus", "--implement-model", "sonnet"])

    def test_implement_model_needs_claude_implementer(self):
        with patch("harness.spec.invoke_claude") as claude, self.assertRaisesRegex(ValueError, "implement-model"):
            run_init(self.root, self.brief, implement_model="sonnet")
        claude.assert_not_called()
        self.assertEqual(list(self.root.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
