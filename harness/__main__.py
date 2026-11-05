import argparse
import json
from pathlib import Path
import sys

from .core import HarnessError, fingerprint, load_manifest, project_status, run_checks
from .agent import run_agent
from .spec import run_init
from .doctor import run_doctor
from .lock import ProjectLocked


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise HarnessError(message)


def main():
    parser = Parser(description="Verify requirements, scenarios, and test evidence.")
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="project containing harness.json")
    commands = parser.add_subparsers(dest="command", required=True)
    initializer = commands.add_parser("init", help="create a new Python project contract and TDD scaffold from a brief")
    initializer.add_argument("--brief", type=Path, required=True, help="UTF-8 requirements file, relative to the current directory")
    initializer.add_argument("--timeout-seconds", type=int, default=300, help="timeout for each AI invocation")
    doctor = commands.add_parser("doctor", help="check local CLIs, login and project setup without model calls")
    doctor.add_argument("--provider", choices=("all", "codex", "claude"), default="all")
    commands.add_parser("check", help="validate the project contract without running tests")
    runner = commands.add_parser("run", help="run checks and save evidence")
    runner.add_argument("--requirement", help="run only checks linked to this requirement")
    commands.add_parser("status", help="compare recorded results with current inputs")
    agent = commands.add_parser("agent", help="develop one requirement with the configured AI workflow and verify the result")
    agent.add_argument("--requirement", help="target requirement; defaults to the first failing requirement")
    agent.add_argument("--max-attempts", type=int, default=3, help="maximum implementation attempts")
    agent.add_argument("--timeout-seconds", type=int, default=300, help="timeout for each AI invocation")
    try:
        args = parser.parse_args()
        root = args.root.resolve()
        if args.command == "doctor":
            result = run_doctor(root, args.provider)
        elif args.command == "init":
            result = run_init(root, args.brief, args.timeout_seconds)
        else:
            manifest = load_manifest(root)
            current = fingerprint(root, manifest)
        if args.command == "check":
            result = {"schema_version": 1, "command": "check", "status": "valid",
                      "fingerprint": current,
                      "counts": {key: len(manifest[key]) for key in ("requirements", "scenarios", "checks")}}
        elif args.command == "run":
            result = run_checks(root, manifest, current, args.requirement)
        elif args.command == "agent":
            result = run_agent(root, manifest, args.requirement, args.max_attempts, args.timeout_seconds)
        elif args.command == "status":
            result = project_status(root, manifest, current)
        exit_code = 0 if result["status"] in ("valid", "passed", "ready") else 2 if result["status"] == "error" else 1
    except ProjectLocked as error:
        # Nothing was written: another harness process owns the evidence folder right now.
        result = {"schema_version": 1, "command": args.command, "status": "error", "reason": "project_locked",
                  "error": str(error), "lock_owner": error.owner}
        exit_code = 2
    except (HarnessError, OSError) as error:
        result = {"schema_version": 1, "status": "error", "error": str(error)}
        exit_code = 2
    sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
