"""Build harness.pyz: the harness as one file that any Python 3.11 or newer can run.

    python -B tools/build_zipapp.py [--output dist/harness.pyz]
    python3 dist/harness.pyz --root PROJECT --python PROJECT/.venv/bin/python run

The archive holds only harness/*.py and a __main__.py that keeps the CLI's exit code. Entry names,
order, timestamps and permissions are fixed, so the same sources always produce the same bytes and a
copy can be checked against the SHA-256 printed here.
"""

import argparse
import hashlib
import os
from pathlib import Path
import zipfile


REPO = Path(__file__).resolve().parents[1]
SHEBANG = b"#!/usr/bin/env python3\n"
MAIN = b"import sys\n\nfrom harness.__main__ import main\n\nsys.exit(main())\n"
TIMESTAMP = (2000, 1, 1, 0, 0, 0)


def entries(source: Path = REPO / "harness") -> dict[str, bytes]:
    files = {"__main__.py": MAIN}
    for path in sorted(source.glob("*.py")):
        files["harness/" + path.name] = path.read_bytes()
    return files


def build(output: Path, source: Path = REPO / "harness") -> str:
    """Write the archive atomically and return its SHA-256."""
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(output.name + ".tmp")
    with temporary.open("wb") as stream:
        # Python runs a zip archive that starts with a shebang line, as zipapp writes it.
        stream.write(SHEBANG)
        with zipfile.ZipFile(stream, "w") as archive:
            for name, data in entries(source).items():
                info = zipfile.ZipInfo(name, date_time=TIMESTAMP)
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o644 << 16
                info.create_system = 3  # Unix, so the stored attributes mean the same on every OS.
                archive.writestr(info, data)
    os.chmod(temporary, 0o755)
    temporary.replace(output)
    return hashlib.sha256(output.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description="Build harness.pyz from harness/*.py.")
    parser.add_argument("--output", type=Path, default=REPO / "dist" / "harness.pyz")
    args = parser.parse_args()
    digest = build(args.output)
    print(f"{args.output} sha256={digest}")


if __name__ == "__main__":
    main()
