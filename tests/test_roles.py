import json
import subprocess
import unittest
from unittest.mock import Mock, patch

from tests import test_agent, test_cli
from harness.agent import AgentError, run_agent
from harness.claude import invoke_claude, validate_design, validate_review


def design(outcome="continue", question=""):
    return {"outcome": outcome, "summary": "Use the existing value contract", "question": question,
            "steps": ["Set VALUE to 2 in logic.py"], "test_strategy": "Reuse CHK-1 and run all checks"}


def review(verdict="approved", question="", path="logic.py"):
    return {"verdict": verdict, "summary": "Review result", "question": question,
            "findings": ([{"path": path, "issue": "Implementation needs clarification",
                           "change": "Explain the constant in a comment"}]
                         if verdict == "changes_requested" else [])}


class RoleWorkflowTests(unittest.TestCase):
    save = test_cli.HarnessTests.save
    cli = test_cli.HarnessTests.cli
    fix = test_agent.AgentTests.fix
    add_other_requirement = test_agent.AgentTests.add_other_requirement

    def setUp(self):
        test_agent.AgentTests.setUp(self)
        self.manifest["agent"]["workflow"] = "claude-codex"
        self.save()

    def run_with(self, codex=None, claude=None, **kwargs):
        def default_claude(root, context, directory, timeout):
            return design() if context["phase"] == "design" else review()
        with patch("harness.agent.invoke_codex", side_effect=codex or self.fix) as implementation, \
                patch("harness.claude.invoke_claude", side_effect=claude or default_claude) as reviewer, \
                patch("harness.agent.require_providers"):
            result = run_agent(self.root, self.manifest, **kwargs)
        self.assertEqual(json.loads((self.root / result["record"]).read_text(encoding="utf-8")), result)
        return result, implementation, reviewer

    def test_design_implementation_verification_review(self):
        result, codex, claude = self.run_with()
        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["review_status"], "approved")
        self.assertEqual(result["workflow"], "claude-codex")
        phases = [p for p in result["phases"] if "provider" in p]
        self.assertEqual([(p["phase"], p["provider"]) for p in phases],
                         [("design", "claude"), ("tests", "codex"),
                          ("implement", "codex"), ("review", "claude")])
        self.assertEqual(codex.call_args_list[0].args[1]["design"], design())
        context = claude.call_args_list[-1].args[1]
        self.assertEqual(context["verification"]["status"], "passed")
        self.assertEqual(context["verification"]["fingerprint_after"], result["review_fingerprint"])
        diff = (self.root / context["diff_path"]).read_text(encoding="utf-8")
        self.assertIn("-VALUE = 3", diff)
        self.assertIn("+VALUE = 2", diff)
        self.assertEqual(context["contract"], self.manifest)

    def test_review_rejection_is_fed_back_and_reverified(self):
        def implement(root, context, directory, timeout):
            if context["phase"] == "implement" and context["attempt"] == 2:
                self.assertEqual(context["review"]["verdict"], "changes_requested")
                (root / "logic.py").write_text("VALUE = 2  # specified value\n", encoding="utf-8")
                return test_agent.response()
            return self.fix(root, context, directory, timeout)
        def assess(root, context, directory, timeout):
            if context["phase"] == "design":
                return design()
            return review("changes_requested" if context["attempt"] == 1 else "approved")
        result, _, claude = self.run_with(codex=implement, claude=assess)
        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["attempts"], 2)
        reviews = [c.args[1] for c in claude.call_args_list if c.args[1]["phase"] == "review"]
        self.assertNotEqual(reviews[0]["verification"]["run_id"], reviews[1]["verification"]["run_id"])
        self.assertNotEqual(reviews[0]["verification"]["fingerprint"], reviews[1]["verification"]["fingerprint"])

    def test_tests_alone_cannot_approve_rejected_code(self):
        result, _, _ = self.run_with(
            claude=lambda root, context, *args: design() if context["phase"] == "design" else review("changes_requested"),
            max_attempts=1)
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["reason"], "review_rejected")
        self.assertEqual(result["project_status"], "passed")
        self.assertEqual(result["review_status"], "changes_requested")

    def test_no_change_after_rejection_stops(self):
        result, _, claude = self.run_with(
            claude=lambda root, context, *args: design() if context["phase"] == "design" else review("changes_requested"))
        self.assertEqual(result["reason"], "no_progress")
        self.assertEqual(result["attempts"], 2)
        self.assertEqual(claude.call_count, 2)

    def test_design_question_stops_before_codex(self):
        result, codex, _ = self.run_with(claude=lambda *args: design("needs_input", "Which contract is intended?"))
        self.assertEqual(result["status"], "needs_input")
        self.assertEqual(result["question"], "Which contract is intended?")
        codex.assert_not_called()

    def test_review_question_stops_without_retry(self):
        result, _, _ = self.run_with(claude=lambda root, context, *args:
                                    design() if context["phase"] == "design" else review("needs_input", "Clarify the boundary"))
        self.assertEqual(result["status"], "needs_input")
        self.assertEqual(result["review_status"], "needs_input")
        self.assertEqual(result["attempts"], 1)

    def test_claude_cannot_change_tracked_files(self):
        for phase in ("design", "review"):
            with self.subTest(phase=phase):
                (self.root / "logic.py").write_text("VALUE = 3\n", encoding="utf-8")
                def change(root, context, *args):
                    if context["phase"] == phase:
                        (root / "logic.py").write_text("VALUE = 2  # changed by reviewer\n", encoding="utf-8")
                    return design() if context["phase"] == "design" else review()
                result, _, _ = self.run_with(claude=change)
                self.assertEqual(result["status"], "needs_input")
                self.assertEqual(result["reason"], "scope_changed")
                self.assertNotEqual(result["review_status"], "approved")

    def test_protected_review_change_requires_input(self):
        result, _, _ = self.run_with(claude=lambda root, context, *args:
                                    design() if context["phase"] == "design" else review("changes_requested", path="harness.json"))
        self.assertEqual(result["status"], "needs_input")
        self.assertEqual(result["reason"], "review_scope")
        self.assertEqual(result["attempts"], 1)

    def test_already_green_target_is_still_reviewed(self):
        (self.root / "logic.py").write_text("VALUE = 2\n", encoding="utf-8")
        result, codex, claude = self.run_with(requirement="REQ-1")
        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["review_status"], "approved")
        self.assertEqual(result["attempts"], 0)
        self.assertEqual([c.args[1]["phase"] for c in claude.call_args_list], ["design", "review"])
        codex.assert_not_called()

    def test_all_green_without_target_does_not_claim_review_approval(self):
        (self.root / "logic.py").write_text("VALUE = 2\n", encoding="utf-8")
        result, codex, claude = self.run_with()
        self.assertEqual(result["status"], "needs_input")
        self.assertEqual(result["reason"], "requirement_required")
        codex.assert_not_called()
        claude.assert_not_called()

    def test_initial_review_rejection_requires_observed_red(self):
        (self.root / "logic.py").write_text("VALUE = 2\n", encoding="utf-8")
        result, codex, _ = self.run_with(requirement="REQ-1", claude=lambda root, context, *args:
                                       design() if context["phase"] == "design" else review("changes_requested"))
        self.assertEqual(result["reason"], "red_not_observed")
        self.assertEqual([c.args[1]["phase"] for c in codex.call_args_list], ["tests"])

    def test_failed_checks_do_not_reach_review(self):
        result, _, claude = self.run_with(codex=lambda *args: test_agent.response())
        self.assertEqual(result["status"], "failed")
        self.assertEqual([c.args[1]["phase"] for c in claude.call_args_list], ["design"])

    def test_regression_is_fixed_before_review(self):
        self.add_other_requirement()
        def implement(root, context, directory, timeout):
            if context["phase"] == "implement":
                (root / "other.py").write_text("VALUE = %d\n" % (3 if context["attempt"] == 1 else 2), encoding="utf-8")
            return self.fix(root, context, directory, timeout)
        result, _, claude = self.run_with(codex=implement)
        self.assertEqual(result["status"], "passed")
        self.assertEqual(claude.call_args_list[-1].args[1]["attempt"], 2)
        self.assertEqual(claude.call_count, 2)

    def test_change_between_verification_and_review_invalidates_evidence(self):
        from harness.agent import verification_cli
        count = 0
        def verify(root, manifest, *args):
            nonlocal count
            result = verification_cli(root, manifest, *args)
            if args == ("run",):
                count += 1
                if count == 2:
                    (root / "logic.py").write_text("VALUE = 2  # concurrent change\n", encoding="utf-8")
            return result
        with patch("harness.agent.verification_cli", side_effect=verify):
            result, _, claude = self.run_with()
        self.assertEqual(result["reason"], "inputs_changed")
        self.assertNotEqual(result["review_status"], "approved")
        self.assertEqual(claude.call_count, 1)

    def test_claude_error_is_persisted_without_retry(self):
        result, codex, _ = self.run_with(claude=AgentError("agent_exit", "Claude authentication failed"))
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["phases"][-1]["provider"], "claude")
        self.assertEqual(result["phases"][-1]["status"], "error")
        codex.assert_not_called()

    def test_workflow_configuration_validation(self):
        self.cli("check")
        for value in ("unknown", [], None):
            self.manifest["agent"]["workflow"] = value
            self.save()
            self.assertIn("workflow", self.cli("check", expected=2)["error"])


class ClaudeAdapterTests(unittest.TestCase):
    save = test_cli.HarnessTests.save

    def setUp(self):
        test_cli.HarnessTests.setUp(self)
        self.directory = self.root / ".harness" / "claude-adapter"
        self.directory.mkdir(parents=True)
        self.context = {"phase": "design", "requirement": {"id": "REQ-1"}}

    def invoke(self, payload, returncode=0):
        process = Mock(returncode=returncode)
        process.communicate.return_value = (json.dumps(payload), "")
        with patch("harness.claude.shutil.which", return_value="claude.exe"), \
                patch("harness.agent.subprocess.Popen", return_value=process) as launch:
            result = invoke_claude(self.root, self.context, self.directory, 30)
        return result, process, launch

    def test_claude_read_only_tools_and_structured_response(self):
        result, process, launch = self.invoke({"type": "result", "subtype": "success", "is_error": False,
                                               "structured_output": design()})
        self.assertEqual(result, design())
        command = launch.call_args.args[0]
        self.assertEqual(command[0], "claude.exe")
        self.assertEqual(command[command.index("--tools") + 1], "Read,Glob,Grep")
        self.assertEqual(command[command.index("--permission-mode") + 1], "dontAsk")
        self.assertIn("--safe-mode", command)
        self.assertIn("--no-session-persistence", command)
        self.assertNotIn("--model", command)
        self.assertNotIn("--dangerously-skip-permissions", command)
        self.assertNotIn("--continue", command)
        self.assertIn("REQ-1", process.communicate.call_args.kwargs["input"])
        self.assertEqual(json.loads((self.directory / "response.json").read_text(encoding="utf-8")), design())

    def test_review_rules_require_complete_findings_and_scoped_stub_checks(self):
        _, process, _ = self.invoke({"type": "result", "subtype": "success", "is_error": False,
                                     "structured_output": design()})
        prompt = process.communicate.call_args.kwargs["input"]
        self.assertIn("List every blocking issue you find in this round", prompt)
        self.assertIn("NotImplementedError on the behavior the selected", prompt)
        self.assertIn("Stubs that only serve other\nrequirements are expected", prompt)
        self.assertIn("Do not state anything you did not verify", prompt)

    def test_missing_or_failed_structured_output_is_not_accepted(self):
        for payload in ({"type": "result", "subtype": "success", "is_error": False, "result": "approved"},
                        {"type": "result", "subtype": "error_max_turns", "is_error": True, "structured_output": design()},
                        {"type": "result", "subtype": "success", "is_error": False, "structured_output": {}}):
            with self.subTest(payload=payload), self.assertRaises(AgentError):
                self.invoke(payload)

    def test_nonzero_exit_preserves_stdout_diagnostic(self):
        with self.assertRaises(AgentError) as error:
            self.invoke({"is_error": True, "result": "Subscription limit reached"}, returncode=1)
        self.assertEqual(error.exception.reason, "agent_exit")
        self.assertIn("Subscription limit", str(error.exception))

    def test_missing_claude_is_actionable(self):
        with patch("harness.claude.shutil.which", return_value=None), self.assertRaises(AgentError) as error:
            invoke_claude(self.root, self.context, self.directory, 30)
        self.assertEqual(error.exception.reason, "agent_missing")
        self.assertIn("claude auth login", str(error.exception))

    def test_timeout_terminates_process_tree(self):
        process = Mock(returncode=1)
        process.communicate.side_effect = [subprocess.TimeoutExpired("claude", 1), ("", "stopped")]
        with patch("harness.claude.shutil.which", return_value="claude.exe"), \
                patch("harness.agent.subprocess.Popen", return_value=process), \
                patch("harness.agent.terminate_tree") as terminate, self.assertRaises(AgentError) as error:
            invoke_claude(self.root, self.context, self.directory, 1)
        self.assertEqual(error.exception.reason, "agent_timeout")
        terminate.assert_called_once_with(process)

    def test_inconsistent_or_unsafe_decisions_are_rejected(self):
        bad_plan = dict(design(), steps=[])
        bad_review = dict(review(), findings=review("changes_requested")["findings"])
        for validator, value in [(validate_design, bad_plan),
                                 (validate_design, design("needs_input")),
                                 (validate_review, bad_review),
                                 (validate_review, dict(review("changes_requested"), findings=[])),
                                 (validate_review, review("needs_input")),
                                 (validate_review, review("changes_requested", path="../outside.py"))]:
            with self.subTest(value=value), self.assertRaises(AgentError):
                validator(value)


if __name__ == "__main__":
    unittest.main()
