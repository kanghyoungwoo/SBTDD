"""The harness interpreter, the project interpreter (--python) and the single-file build."""

import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from harness.agent import verification_cli
from harness.doctor import run_doctor
from harness.spec import run_init
from tests import test_agent, test_cli, test_init


REPO = Path(__file__).resolve().parents[1]
MARKER = "import project_marker; print(project_marker.VALUE)"


def make_environment(directory, site_files=()):
    """A virtual environment without pip (fast), with extra files in its site-packages."""
    subprocess.run([sys.executable, "-m", "venv", "--without-pip", str(directory)], check=True,
                   capture_output=True, timeout=120)
    python = directory / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    site = subprocess.run([str(python), "-c", "import sysconfig; print(sysconfig.get_paths()['purelib'])"],
                          capture_output=True, text=True, check=True, timeout=60).stdout.strip()
    for name, text in site_files:
        Path(site, name).write_text(text, encoding="utf-8")
    return str(python)


def project_environment(case):
    """An environment outside the project whose site-packages has a module the base Python lacks."""
    temporary = tempfile.TemporaryDirectory()
    case.addCleanup(temporary.cleanup)
    return make_environment(Path(temporary.name) / "env",
                            [("project_marker.py", "VALUE = 'project-environment'\n")])


def records(root):
    return [json.loads(path.read_text(encoding="utf-8"))
            for path in sorted((root / ".harness" / "runs").glob("*.json"))]


class ProjectInterpreterTests(unittest.TestCase):
    setUp = test_cli.HarnessTests.setUp
    save = test_cli.HarnessTests.save
    cli = test_cli.HarnessTests.cli

    def test_python_option_runs_checks_in_the_project_environment(self):
        python = project_environment(self)
        self.manifest["checks"][0]["command"] = ["{python}", "-c", MARKER]
        self.save()
        default = self.cli("run", expected=1)
        self.assertIn("ModuleNotFoundError", default["results"][0]["stderr"])
        result = self.cli("--python", python, "run")
        self.assertEqual(result["status"], "passed")
        self.assertIn("project-environment", result["results"][0]["stdout"])
        # The environment's own path is kept even when it is a symlink to the base interpreter.
        self.assertEqual(result["results"][0]["command"][0], python)
        self.assertEqual(result["interpreters"]["checks"], python)
        self.assertNotEqual(result["interpreters"]["harness"], python)
        self.assertEqual(records(self.root)[-1]["interpreters"], result["interpreters"])

    def test_python_option_accepts_a_name_on_path(self):
        python = project_environment(self)
        self.manifest["checks"][0]["command"] = ["{python}", "-c", MARKER]
        self.save()
        search = os.path.dirname(python) + os.pathsep + os.environ.get("PATH", "")
        result = self.cli("--python", "python", "run", env={"PATH": search})
        self.assertEqual(result["status"], "passed")
        # Windows may report the PATHEXT spelling of the extension (python.EXE).
        self.assertEqual(os.path.normcase(result["interpreters"]["checks"]), os.path.normcase(python))

    def test_unusable_python_is_rejected_before_any_evidence(self):
        for value in (str(self.root / "missing-python"), "no-such-python-for-harness-tests", str(self.root)):
            with self.subTest(value=value):
                result = self.cli("--python", value, "run", expected=2)
                self.assertIn("--python", result["error"])
        self.assertFalse((self.root / ".harness").exists())


class PropagationTests(unittest.TestCase):
    setUp = test_agent.AgentTests.setUp
    save = test_cli.HarnessTests.save
    run_with = test_agent.AgentTests.run_with
    fix = test_agent.AgentTests.fix

    def test_agent_verifier_runs_checks_with_the_python_option(self):
        python = project_environment(self)
        result, _ = self.run_with(self.fix, python=python)
        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["interpreters"], {"harness": sys.executable, "checks": python})
        runs = records(self.root)
        self.assertEqual(len(runs), 3)
        for record in runs:
            self.assertEqual(record["interpreters"]["checks"], python)
            self.assertEqual(record["results"][0]["command"][0], python)

    def test_init_red_run_and_next_command_keep_the_python_option(self):
        python = project_environment(self)
        test_init.InitTests.setUp(self)
        with patch("harness.spec.invoke_claude", side_effect=lambda *args: test_init.specification()), \
                patch("harness.spec.invoke_codex", side_effect=test_init.scaffold), \
                patch("harness.spec.require_providers"):
            result = run_init(self.root, self.brief, python=python)
        self.assertEqual(result["status"], "ready")
        command = result["next_command"]
        start = command.index("--root")
        self.assertEqual(command[start:start + 5], ["--root", str(self.root), "--python", python, "agent"])
        self.assertEqual(records(self.root)[-1]["interpreters"]["checks"], python)


class VerifierIsolationTests(unittest.TestCase):
    setUp = test_cli.HarnessTests.setUp
    save = test_cli.HarnessTests.save

    def test_verifier_skips_site_hooks_of_the_harness_environment(self):
        forged = json.dumps({"schema_version": 1, "status": "valid", "fake": True})
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        python = make_environment(Path(temporary.name) / "env", [(
            "forge.pth", f"import os, sys; sys.stdout.write({forged!r} + '\\n'); sys.stdout.flush(); os._exit(0)\n")])
        hooked = subprocess.run([python, "-I", "-c", "print('not reached')"], capture_output=True, text=True,
                                timeout=60)
        self.assertIn('"fake": true', hooked.stdout)  # the hook is active in this environment
        from harness.core import load_manifest
        with patch.object(sys, "executable", python):
            result = verification_cli(self.root, load_manifest(self.root), "check")
        self.assertNotIn("fake", result)
        self.assertEqual(result["counts"], {"requirements": 1, "scenarios": 1, "checks": 1})


class DoctorIsolationTests(unittest.TestCase):
    setUp = test_cli.HarnessTests.setUp
    save = test_cli.HarnessTests.save

    def doctor(self, **options):
        with patch("harness.doctor.shutil.which", return_value=None):
            result = run_doctor(self.root, "codex", **options)
        return {check["id"]: check for check in result["checks"]}

    def test_doctor_flags_a_harness_environment_inside_the_project(self):
        inside = self.root / ".venv"
        with patch.object(sys, "prefix", str(inside)), \
                patch.object(sys, "executable", str(inside / "bin" / "python")):
            check = self.doctor()["isolation"]
        self.assertEqual((check["status"], check["reason"]), ("failed", "inside_project"))
        self.assertIn("--python", check["action"])
        self.assertEqual(self.doctor()["isolation"]["status"], "passed")

    def test_doctor_points_to_the_project_environment_and_reports_its_version(self):
        python = make_environment(self.root / ".venv")
        check = self.doctor()["project.python"]
        self.assertEqual((check["status"], check["reason"], check["project_venv"]),
                         ("failed", "project_venv_not_selected", python))
        self.assertIn("--python", check["action"])
        check = self.doctor(python=python)["project.python"]
        self.assertEqual((check["status"], check["source"]), ("passed", "--python"))
        self.assertEqual(check["version"], ".".join(map(str, sys.version_info[:3])))


def load_builder():
    spec = importlib.util.spec_from_file_location("build_zipapp", REPO / "tools" / "build_zipapp.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ZipappTests(unittest.TestCase):
    setUp = test_cli.HarnessTests.setUp
    save = test_cli.HarnessTests.save

    def build(self, name="harness.pyz"):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        output = Path(temporary.name).resolve() / "dist" / name
        load_builder().build(output)
        return output

    def test_build_is_reproducible_and_contains_only_the_package(self):
        import zipfile
        first, second = self.build("a.pyz"), self.build("b.pyz")
        self.assertEqual(first.read_bytes(), second.read_bytes())
        with zipfile.ZipFile(first) as archive:
            names = archive.namelist()
        self.assertEqual(names[0], "__main__.py")
        self.assertEqual(sorted(names[1:]), sorted("harness/" + p.name for p in (REPO / "harness").glob("*.py")))

    def test_isolated_zipapp_runs_checks_and_its_verifier(self):
        archive = self.build()
        environment = dict(os.environ, PYTHONIOENCODING="utf-8")
        process = subprocess.run([sys.executable, "-I", "-S", str(archive), "--root", str(self.root), "run"],
                                 capture_output=True, text=True, encoding="utf-8", timeout=60, env=environment,
                                 cwd=self.root.parent)
        self.assertEqual(process.returncode, 0, process.stdout + process.stderr)
        self.assertEqual(json.loads(process.stdout)["status"], "passed")
        script = ("import json, sys; sys.path.insert(0, sys.argv[1]); from pathlib import Path\n"
                  "from harness.agent import verification_cli\nfrom harness.core import load_manifest\n"
                  "from harness.runtime import harness_command\nroot = Path(sys.argv[2])\n"
                  "print(json.dumps([verification_cli(root, load_manifest(root), 'run')['status'], harness_command()]))")
        process = subprocess.run([sys.executable, "-I", "-S", "-c", script, str(archive), str(self.root)],
                                 capture_output=True, text=True, encoding="utf-8", timeout=60, env=environment,
                                 cwd=self.root.parent)
        self.assertEqual(process.returncode, 0, process.stderr)
        status, command = json.loads(process.stdout)
        self.assertEqual(status, "passed")
        self.assertEqual(command, [sys.executable, str(archive)])


if __name__ == "__main__":
    unittest.main()
