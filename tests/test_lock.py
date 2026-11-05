import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from harness.agent import AgentError, run_agent, run_process, verification_cli
from harness.guard import tree_snapshot
from harness.lock import TOKEN_VARIABLE, ProjectLocked, project_lock
from harness.spec import run_init
from tests import test_agent, test_cli, test_init


REPO = Path(__file__).resolve().parents[1]
HOLDER = ("import sys, time; from pathlib import Path; from harness.lock import project_lock; "
          "lock = project_lock(Path(sys.argv[1]), 'holder'); lock.__enter__(); "
          "print('locked', flush=True); time.sleep(60)")


def hold_lock(test, root):
    """Hold the project lock from another process, as a concurrent harness command would."""
    process = subprocess.Popen([sys.executable, "-c", HOLDER, str(root)], cwd=REPO, text=True,
                               stdout=subprocess.PIPE, env=dict(os.environ, PYTHONPATH=str(REPO)))

    def stop():
        process.kill()
        process.wait()
        process.stdout.close()

    test.addCleanup(stop)
    test.assertEqual(process.stdout.readline().strip(), "locked")
    return process, stop


class LockTests(unittest.TestCase):
    setUp = test_agent.AgentTests.setUp
    save = test_cli.HarnessTests.save
    cli = test_cli.HarnessTests.cli

    def test_concurrent_run_is_refused_without_marking_evidence(self):
        (self.root / "logic.py").write_text("VALUE = 2\n", encoding="utf-8")
        self.manifest["checks"][0]["command"] = [
            "{python}", "-c", "import pathlib, time; pathlib.Path('started').touch(); time.sleep(3)"]
        self.save()
        first = subprocess.Popen(
            [sys.executable, "-B", "-m", "harness", "--root", str(self.root), "run"], cwd=REPO,
            env=dict(os.environ, PYTHONPATH=str(REPO), PYTHONIOENCODING="utf-8"),
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8")
        deadline = time.monotonic() + 15
        while not (self.root / "started").exists() and first.poll() is None and time.monotonic() < deadline:
            time.sleep(0.05)
        self.assertTrue((self.root / "started").exists(), "the first run never started its check")
        second = self.cli("run", expected=2)
        output, _ = first.communicate(timeout=30)
        self.assertEqual(first.returncode, 0, output)
        self.assertEqual(json.loads(output)["status"], "passed")
        self.assertEqual(second["reason"], "project_locked")
        self.assertEqual(second["lock_owner"]["command"], "run")
        self.assertNotIn("token_sha256", second["lock_owner"])
        self.assertFalse((self.root / ".harness" / "integrity-violation.json").exists())
        self.assertEqual(len(list((self.root / ".harness" / "runs").glob("*.json"))), 1)
        self.assertEqual(self.cli("status")["status"], "passed")

    def test_lock_is_released_when_holder_is_killed(self):
        _, stop = hold_lock(self, self.root)
        with self.assertRaises(ProjectLocked) as error:
            with project_lock(self.root, "run"):
                pass
        self.assertEqual(error.exception.owner["command"], "holder")
        stop()
        deadline = time.monotonic() + 5  # Windows may release a dead process's locks a moment later.
        while True:
            try:
                with project_lock(self.root, "run") as token:
                    self.assertTrue(token)
                break
            except ProjectLocked:
                if time.monotonic() > deadline:
                    raise
                time.sleep(0.1)

    def test_agent_and_init_write_nothing_while_locked(self):
        hold_lock(self, self.root)
        before = tree_snapshot(self.root / ".harness")
        with patch("harness.agent.invoke_codex") as codex, self.assertRaises(ProjectLocked):
            run_agent(self.root, self.manifest)
        codex.assert_not_called()
        empty = self.root / "new"
        empty.mkdir()
        hold_lock(self, empty)
        brief = self.root / "brief.txt"
        brief.write_text("Return 2", encoding="utf-8")
        with patch("harness.spec.invoke_claude") as claude, self.assertRaises(ProjectLocked):
            run_init(empty, brief)
        claude.assert_not_called()
        self.assertEqual(tree_snapshot(self.root / ".harness"), before)
        self.assertEqual(sorted(p.name for p in (empty / ".harness").iterdir()), ["lock", "lock-owner.json"])

    def test_holders_verifier_joins_lock_but_forged_token_does_not(self):
        with project_lock(self.root, "agent"):
            self.assertEqual(verification_cli(self.root, self.manifest, "run")["status"], "failed")
        hold_lock(self, self.root)
        with patch.dict(os.environ, {TOKEN_VARIABLE: "forged"}), self.assertRaises(AgentError) as error:
            verification_cli(self.root, self.manifest, "run")
        self.assertEqual(error.exception.reason, "verification_error")
        self.assertIn("Another harness command", str(error.exception))

    def test_checks_and_ai_tools_do_not_receive_lock_token(self):
        self.manifest["checks"][0]["command"] = [
            "{python}", "-c", f"import os; print(os.environ.get('{TOKEN_VARIABLE}'))"]
        self.save()
        with project_lock(self.root, "agent"):
            result = verification_cli(self.root, self.manifest, "run")
        self.assertEqual(result["results"][0]["stdout"].strip(), "None")
        directory = self.root / "call"
        directory.mkdir()
        with patch.dict(os.environ, {TOKEN_VARIABLE: "inherited"}), \
                patch("harness.agent.subprocess.Popen") as launch:
            launch.return_value.communicate.return_value = ("{}", "")
            launch.return_value.returncode = 0
            run_process(self.root, ["codex"], "prompt", directory, 30, "Codex")
        self.assertNotIn(TOKEN_VARIABLE, launch.call_args.kwargs["env"])


class WindowsLockBranchTests(unittest.TestCase):
    """Exercise the Windows code path's logic on any OS; the OS behavior itself needs a Windows run."""

    def test_far_byte_lock_and_lock_violation_mapping(self):
        import errno
        from harness import lock
        calls = []

        class FakeMsvcrt:
            LK_NBLCK, LK_UNLCK = 2, 0

            def __init__(self, failure=None):
                self.failure = failure

            def locking(self, descriptor, mode, nbytes):
                calls.append((os.lseek(descriptor, 0, os.SEEK_CUR), mode, nbytes))
                if mode == self.LK_NBLCK and self.failure:
                    raise OSError(self.failure, "lock failed")

        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        descriptor = os.open(Path(temporary.name) / "lock", os.O_RDWR | os.O_CREAT)
        self.addCleanup(os.close, descriptor)
        with patch.object(lock.os, "name", "nt"):
            with patch.object(lock, "msvcrt", FakeMsvcrt(), create=True):
                self.assertTrue(lock.try_lock(descriptor))
                lock.unlock(descriptor)
            with patch.object(lock, "msvcrt", FakeMsvcrt(errno.EACCES), create=True):
                self.assertFalse(lock.try_lock(descriptor))
            with patch.object(lock, "msvcrt", FakeMsvcrt(errno.EBADF), create=True), self.assertRaises(OSError):
                lock.try_lock(descriptor)
        offset = lock.WINDOWS_LOCK_OFFSET
        self.assertEqual(calls, [(offset, 2, 1), (offset, 0, 1), (offset, 2, 1), (offset, 2, 1)])
        self.assertEqual(os.fstat(descriptor).st_size, 0)


class InitLockTests(unittest.TestCase):
    setUp = test_init.InitTests.setUp
    run_with = test_init.InitTests.run_with

    def test_init_holds_lock_and_releases_it(self):
        result, _, _ = self.run_with()
        self.assertEqual(result["status"], "ready")
        self.assertEqual(json.loads((self.root / ".harness" / "lock-owner.json").read_text(encoding="utf-8"))["command"], "init")
        with project_lock(self.root, "run") as token:
            self.assertTrue(token)


if __name__ == "__main__":
    unittest.main()
