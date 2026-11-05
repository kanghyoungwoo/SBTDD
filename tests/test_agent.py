import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

from tests import test_cli
from harness.agent import AgentError, invoke_codex, run_agent


def response(outcome="continue", question="", red_check_ids=None):
    return {"outcome": outcome, "summary": "Test response", "question": question,
            "red_check_ids": ["CHK-1"] if red_check_ids is None else red_check_ids}


class AgentTests(unittest.TestCase):
    save = test_cli.HarnessTests.save
    cli = test_cli.HarnessTests.cli

    def setUp(self):
        test_cli.HarnessTests.setUp(self)
        self.manifest["agent"] = {"code_paths": ["logic.py"], "test_paths": ["test_logic.py"]}
        (self.root / "logic.py").write_text("VALUE = 3\n", encoding="utf-8")
        self.save()

    def run_with(self, action, **kwargs):
        with patch("harness.agent.invoke_codex", side_effect=action) as agent, \
                patch("harness.agent.require_providers"):
            result = run_agent(self.root, self.manifest, **kwargs)
        stored = self.root / result["record"]
        self.assertEqual(json.loads(stored.read_text(encoding="utf-8")), result)
        return result, agent

    def fix(self, root, context, directory, timeout):
        if context["phase"] == "implement":
            (root / "logic.py").write_text("VALUE = 2\n", encoding="utf-8")
        return response()

    def test_red_green_through_verification_cli(self):
        result, agent = self.run_with(self.fix)
        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["project_status"], "passed")
        self.assertEqual(result["requirement"], "REQ-1")
        self.assertEqual(result["attempts"], 1)
        self.assertEqual([call.args[1]["phase"] for call in agent.call_args_list], ["tests", "implement"])
        self.assertTrue(all(call.args[1]["requirement"]["id"] == "REQ-1" for call in agent.call_args_list))
        records = [json.loads(p.read_text(encoding="utf-8"))
                   for p in sorted((self.root / ".harness" / "runs").glob("*.json"))]
        self.assertEqual([record["status"] for record in records], ["failed", "failed", "passed"])

    def test_test_phase_can_add_new_tests(self):
        tests = self.root / "tests"
        tests.mkdir()
        (self.root / "test_logic.py").replace(tests / "test_logic.py")
        self.manifest["inputs"] = ["logic.py", "tests"]
        self.manifest["agent"]["test_paths"] = ["tests"]
        self.manifest["checks"][0]["command"] = ["{python}", "-B", "-m", "unittest", "discover", "-s", "tests"]
        self.save()
        def change(root, context, directory, timeout):
            if context["phase"] == "tests":
                source = (tests / "test_logic.py").read_text(encoding="utf-8")
                (tests / "test_added.py").write_text(source.replace("test_value", "test_regression"), encoding="utf-8")
            else:
                (root / "logic.py").write_text("VALUE = 2\n", encoding="utf-8")
            return response()
        result, _ = self.run_with(change)
        self.assertEqual(result["status"], "passed")
        self.assertIn("tests/test_added.py", result["phases"][1]["changed_files"])

    def test_already_passed_avoids_agent(self):
        (self.root / "logic.py").write_text("VALUE = 2\n", encoding="utf-8")
        result, agent = self.run_with(self.fix)
        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["reason"], "already_passed")
        agent.assert_not_called()

    def test_question_stops_before_implementation(self):
        result, agent = self.run_with(lambda *args: response("needs_input", "Which value is expected?"))
        self.assertEqual(result["status"], "needs_input")
        self.assertEqual(result["question"], "Which value is expected?")
        self.assertEqual(agent.call_count, 1)

    def test_contract_change_stops(self):
        def change(root, context, directory, timeout):
            self.manifest["scenarios"][0]["then"] = "Changed expectation"
            self.save()
            return response()
        result, agent = self.run_with(change)
        self.assertEqual(result["status"], "needs_input")
        self.assertEqual(result["reason"], "contract_changed")
        self.assertIn("harness.json", result["changed_files"])
        self.assertEqual(agent.call_count, 1)

    def test_test_phase_cannot_edit_implementation(self):
        def change(root, *args):
            (root / "logic.py").write_text("VALUE = 2\n", encoding="utf-8")
            return response()
        result, agent = self.run_with(change)
        self.assertEqual(result["reason"], "scope_changed")
        self.assertEqual(result["status"], "needs_input")
        self.assertEqual(agent.call_count, 1)

    def test_existing_tests_cannot_be_rewritten(self):
        def change(root, *args):
            (root / "test_logic.py").write_text("# tests removed\n", encoding="utf-8")
            return response()
        result, _ = self.run_with(change)
        self.assertEqual(result["reason"], "scope_changed")
        self.assertIn("test_logic.py", result["changed_files"])

    def test_implementation_cannot_weaken_tests(self):
        def change(root, context, directory, timeout):
            if context["phase"] == "implement":
                (root / "test_logic.py").write_text("# tests removed\n", encoding="utf-8")
            return response()
        result, _ = self.run_with(change)
        self.assertEqual(result["reason"], "scope_changed")
        self.assertEqual(result["attempts"], 1)

    def test_no_progress_stops_without_retry(self):
        result, agent = self.run_with(lambda *args: response())
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["reason"], "no_progress")
        self.assertEqual(agent.call_count, 2)

    def test_attempt_limit(self):
        def change(root, context, directory, timeout):
            if context["phase"] == "implement":
                (root / "logic.py").write_text(f"VALUE = {10 + context['attempt']}\n", encoding="utf-8")
            return response()
        result, agent = self.run_with(change, max_attempts=2)
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["reason"], "attempt_limit")
        self.assertEqual(result["attempts"], 2)
        self.assertEqual(agent.call_count, 3)

    def test_red_requires_matching_failed_check(self):
        result, agent = self.run_with(lambda *args: response(red_check_ids=["MISSING"]))
        self.assertEqual(result["status"], "needs_input")
        self.assertEqual(result["reason"], "red_not_observed")
        self.assertEqual(agent.call_count, 1)

    def test_launch_error_is_not_red(self):
        self.manifest["checks"][0]["command"] = ["missing-harness-test-executable-92ad"]
        self.save()
        result, agent = self.run_with(self.fix)
        self.assertEqual(result["status"], "needs_input")
        self.assertEqual(result["reason"], "verification_setup")
        agent.assert_not_called()

    def test_agent_error_is_recorded_without_retry(self):
        result, agent = self.run_with(AgentError("agent_timeout", "Timed out"))
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["reason"], "agent_timeout")
        self.assertEqual(agent.call_count, 1)

    def add_other_requirement(self):
        test_cli.HarnessTests.add_second_requirement(self)
        (self.root / "other.py").write_text("VALUE = 2\n", encoding="utf-8")
        self.manifest["inputs"].append("other.py")
        self.manifest["agent"]["code_paths"].append("other.py")
        self.manifest["checks"][1]["command"] = ["{python}", "-c", "import other; assert other.VALUE == 2"]
        self.save()

    def test_first_failed_requirement_is_selected(self):
        self.add_other_requirement()
        (self.root / "logic.py").write_text("VALUE = 2\n", encoding="utf-8")
        (self.root / "other.py").write_text("VALUE = 3\n", encoding="utf-8")
        result, agent = self.run_with(lambda *args: response("needs_input", "Clarify second requirement"))
        self.assertEqual(result["requirement"], "REQ-2")
        self.assertEqual(agent.call_args.args[1]["requirement"]["id"], "REQ-2")

    def test_existing_unrelated_failure_is_reported(self):
        self.add_other_requirement()
        (self.root / "other.py").write_text("VALUE = 3\n", encoding="utf-8")
        result, _ = self.run_with(self.fix, requirement="REQ-1")
        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["project_status"], "failed")

    def test_regression_is_retried(self):
        self.add_other_requirement()
        def change(root, context, directory, timeout):
            if context["phase"] == "implement":
                (root / "logic.py").write_text("VALUE = 2\n", encoding="utf-8")
                value = 3 if context["attempt"] == 1 else 2
                (root / "other.py").write_text(f"VALUE = {value}\n", encoding="utf-8")
                if context["attempt"] == 2:
                    self.assertIn("CHK-2", context["regressions"])
            return response()
        result, _ = self.run_with(change)
        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["attempts"], 2)

    def test_cli_validation(self):
        self.cli("agent", "--max-attempts", "0", expected=2)
        self.cli("agent", "--timeout-seconds", "0", expected=2)
        self.cli("agent", "--requirement", "MISSING", expected=2)
        del self.manifest["agent"]
        self.save()
        self.assertIn("agent", self.cli("agent", expected=2)["error"])

    def test_excluded_path_cannot_be_an_agent_scope(self):
        (self.root / ".harness").mkdir()
        self.manifest["inputs"] = ["."]
        self.manifest["agent"]["code_paths"] = [".harness"]
        self.save()
        self.assertIn("excluded", self.cli("check", expected=2)["error"])

    def test_scope_configuration_is_validated(self):
        for paths in [["."], ["../outside"], ["missing.py"], ["test_logic.py"]]:
            with self.subTest(paths=paths):
                self.manifest["agent"]["code_paths"] = paths
                self.save()
                self.cli("check", expected=2)

    def test_public_cli_skips_ai_for_passed_target(self):
        (self.root / "logic.py").write_text("VALUE = 2\n", encoding="utf-8")
        tools = tempfile.TemporaryDirectory()
        self.addCleanup(tools.cleanup)
        called = Path(tools.name) / "called"
        if os.name == "nt":
            (Path(tools.name) / "codex.bat").write_text(f'@echo called> "{called}"\r\n@exit /b 1\r\n')
        else:
            fake = Path(tools.name) / "codex"
            fake.write_text(f'#!/bin/sh\ntouch "{called}"\nexit 1\n')
            fake.chmod(0o755)
        result = self.cli("agent", "--requirement", "REQ-1",
                          env={"PATH": tools.name + os.pathsep + os.environ.get("PATH", "")})
        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["reason"], "already_passed")
        self.assertFalse(called.exists(), "a passed target must not start Codex")


class CodexAdapterTests(unittest.TestCase):
    save = test_cli.HarnessTests.save

    def setUp(self):
        test_cli.HarnessTests.setUp(self)
        self.directory = self.root / ".harness" / "adapter-test"
        self.directory.mkdir(parents=True)
        self.context = {"phase": "tests", "requirement": {"id": "REQ-1"}}

    def test_codex_arguments_stdin_and_structured_response(self):
        process = Mock(returncode=0)
        process.communicate.return_value = (json.dumps(response()), "progress")
        with patch("harness.agent.shutil.which", return_value="codex.exe"), \
                patch("harness.agent.subprocess.Popen", return_value=process) as launch:
            result = invoke_codex(self.root, self.context, self.directory, 30)
        self.assertEqual(result["outcome"], "continue")
        command = launch.call_args.args[0]
        self.assertEqual(command[:4], ["codex.exe", "--ask-for-approval", "never", "exec"])
        self.assertEqual(command[command.index("--sandbox") + 1], "workspace-write")
        self.assertIn("--output-schema", command)
        self.assertNotIn("--model", command)
        self.assertNotIn("--dangerously-bypass-approvals-and-sandbox", command)
        self.assertIn("REQ-1", process.communicate.call_args.kwargs["input"])
        self.assertTrue((self.directory / "prompt.txt").exists())
        self.assertTrue((self.directory / "response.json").exists())

    def test_prompts_forbid_unverified_claims(self):
        from harness.agent import INSTRUCTIONS, SCAFFOLD_INSTRUCTIONS
        from harness.spec import SPEC_INSTRUCTIONS
        self.assertIn("report only what you changed and what you actually observed", INSTRUCTIONS)
        self.assertIn("do not claim unverified results", SCAFFOLD_INSTRUCTIONS)
        self.assertIn("explicit assumption the user can review", SPEC_INSTRUCTIONS)

    def test_malformed_response_is_rejected(self):
        for output in ["not json", json.dumps({"outcome": "continue"}),
                       json.dumps(response("needs_input", ""))]:
            with self.subTest(output=output):
                process = Mock(returncode=0)
                process.communicate.return_value = (output, "")
                with patch("harness.agent.shutil.which", return_value="codex"), \
                        patch("harness.agent.subprocess.Popen", return_value=process):
                    with self.assertRaises(AgentError) as error:
                        invoke_codex(self.root, self.context, self.directory, 30)
                self.assertEqual(error.exception.reason, "invalid_response")

    @unittest.skipUnless(__import__("os").name == "nt", "Windows process termination")
    def test_tree_termination_failure_still_kills_parent(self):
        from harness.agent import terminate_tree
        process = Mock(pid=12345)
        process.poll.return_value = None
        with patch("harness.agent.subprocess.run", side_effect=subprocess.TimeoutExpired("taskkill", 10)):
            terminate_tree(process)
        process.kill.assert_called_once()

    def test_timeout_terminates_agent_tree(self):
        process = Mock(returncode=1)
        process.communicate.side_effect = [subprocess.TimeoutExpired("codex", 1), ("", "stopped")]
        with patch("harness.agent.shutil.which", return_value="codex"), \
                patch("harness.agent.subprocess.Popen", return_value=process), \
                patch("harness.agent.terminate_tree") as terminate:
            with self.assertRaises(AgentError) as error:
                invoke_codex(self.root, self.context, self.directory, 1)
        self.assertEqual(error.exception.reason, "agent_timeout")
        terminate.assert_called_once_with(process)

    def test_checkpoint_retries_transient_file_lock(self):
        from pathlib import Path
        from harness.agent import write_json
        original = Path.replace
        attempts = []
        def locked_once(path, target):
            attempts.append(path)
            if len(attempts) == 1:
                raise PermissionError("File is temporarily locked")
            return original(path, target)
        target = self.directory / "checkpoint.json"
        with patch.object(Path, "replace", locked_once), patch("harness.agent.time.sleep"):
            write_json(target, {"status": "failed"})
        self.assertEqual(len(attempts), 2)
        self.assertEqual(json.loads(target.read_text(encoding="utf-8")), {"status": "failed"})

    def test_nonzero_agent_exit_is_error(self):
        process = Mock(returncode=1)
        process.communicate.return_value = (json.dumps(response()), "authentication failed")
        with patch("harness.agent.shutil.which", return_value="codex"), \
                patch("harness.agent.subprocess.Popen", return_value=process):
            with self.assertRaises(AgentError) as error:
                invoke_codex(self.root, self.context, self.directory, 30)
        self.assertEqual(error.exception.reason, "agent_exit")


if __name__ == "__main__":
    unittest.main()
