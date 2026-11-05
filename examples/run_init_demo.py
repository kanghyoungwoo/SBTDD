"""Generate a new project from a brief, then implement and review its requirements."""

import json
from pathlib import Path
import subprocess
import sys
import uuid


def main():
    project = Path(__file__).resolve().parents[1]
    target = project / ".harness" / "demos" / ("new-project-" + uuid.uuid4().hex[:12])
    target.mkdir(parents=True)

    def call(*arguments):
        process = subprocess.run(
            [sys.executable, "-B", "-m", "harness", "--root", str(target), *arguments],
            cwd=project, capture_output=True, text=True, encoding="utf-8")
        try:
            result = json.loads(process.stdout)
        except json.JSONDecodeError:
            result = {"status": "error", "message": process.stderr or process.stdout}
        return process.returncode, result

    code, initialization = call("init", "--brief", str(project / "examples" / "new_project_brief.md"))
    if code:
        print(json.dumps(initialization, ensure_ascii=False, indent=2))
        return code
    records = []
    for requirement in initialization["requirements"]:
        code, result = call("agent", "--requirement", requirement)
        if code:
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return code
        records.append(result["record"])
    code, state = call("status")
    print(json.dumps({"status": state["status"], "project_root": str(target),
                      "initialization_record": initialization["record"], "agent_records": records,
                      "requirements": state.get("requirements", [])}, ensure_ascii=False, indent=2))
    return code


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
