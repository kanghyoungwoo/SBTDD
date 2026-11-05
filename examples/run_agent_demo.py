"""Create an isolated, deliberately broken inventory example and repair it with Claude design/review and Codex implementation."""

from pathlib import Path
import shutil
import subprocess
import sys
import uuid


def main():
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
    return subprocess.call(
        [sys.executable, "-B", "-m", "harness", "--root", str(target), "agent", "--requirement", "REQ-STOCK"],
        cwd=project,
    )


if __name__ == "__main__":
    raise SystemExit(main())
