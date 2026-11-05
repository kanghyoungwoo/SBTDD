"""Create an isolated, deliberately broken inventory example and repair it.

By default Claude designs and reviews while Codex implements; --implementer claude uses Claude for both.
"""

import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
import uuid


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--implementer", choices=("codex", "claude"), default="codex")
    options = parser.parse_args()
    project = Path(__file__).resolve().parents[1]
    demos = project / ".harness" / "demos"
    demos.mkdir(parents=True, exist_ok=True)
    target = demos / ("inventory-" + uuid.uuid4().hex[:12])
    target.mkdir()
    for name in ("inventory.py", "test_inventory.py", "harness.json"):
        shutil.copyfile(project / "examples" / "inventory" / name, target / name)
    implementation = target / "inventory.py"
    source = implementation.read_text(encoding="utf-8")
    if source.count("self.stock -= quantity") != 1:
        raise ValueError("The inventory example changed; update the demo's injected fault.")
    implementation.write_text(source.replace("self.stock -= quantity", "self.stock += quantity"), encoding="utf-8")
    if options.implementer == "claude":
        contract = json.loads((target / "harness.json").read_text(encoding="utf-8"))
        contract["agent"]["workflow"] = "claude"
        (target / "harness.json").write_text(json.dumps(contract, ensure_ascii=False, indent=2), encoding="utf-8")
    return subprocess.call(
        [sys.executable, "-B", "-m", "harness", "--root", str(target), "agent", "--requirement", "REQ-STOCK"],
        cwd=project,
    )


if __name__ == "__main__":
    raise SystemExit(main())
