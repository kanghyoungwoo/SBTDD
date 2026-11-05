"""Which interpreter runs the harness, which one runs the project's checks, and how to start the harness.

The harness only needs the standard library, so it can run from its own environment (pipx, uv tool or
harness.pyz) while `{python}` in check commands names the project's interpreter (`--python`).
"""

import os
from pathlib import Path
import shutil
import sys

from .core import require


def package_root() -> Path:
    """The directory, or the harness.pyz archive, that contains the `harness` package."""
    return Path(__file__).resolve().parents[1]


def harness_command() -> list[str]:
    """Arguments that start this same harness again, for commands handed back to the user."""
    root = package_root()
    if root.is_file():
        return [sys.executable, str(root)]
    return [sys.executable, "-B", "-m", "harness"]


def resolve_python(value: str) -> str:
    """Absolute path of the interpreter given with --python.

    Symlinks are kept: a virtual environment's interpreter is usually a link to the base interpreter,
    and following it would silently drop the environment. A bare name is looked up on PATH.
    """
    require(bool(value.strip()) and "\0" not in value, "--python must name an interpreter")
    candidate = value
    separators = {os.sep, os.altsep} - {None}
    if not separators.intersection(value) and not os.path.exists(value):
        found = shutil.which(value)
        require(found is not None, f"--python: interpreter not found on PATH: {value}")
        assert found is not None
        candidate = found
    path = os.path.abspath(candidate)
    require(os.path.isfile(path) and os.access(path, os.X_OK), f"--python: not an executable file: {value}")
    return path


def environment_inside(root: Path) -> Path | None:
    """The harness interpreter's environment when it lives inside the project, otherwise None.

    Code in that environment's site hooks (.pth files, sitecustomize) runs inside the harness itself.
    """
    resolved = root.resolve()
    for value in (sys.prefix, os.path.dirname(os.path.abspath(sys.executable))):
        location = Path(value).resolve()
        if location.is_relative_to(resolved):
            return location
    return None


def project_environment(root: Path) -> str | None:
    """The interpreter of the project's .venv, if it has one."""
    for relative in (("bin", "python"), ("Scripts", "python.exe")):
        candidate = root.joinpath(".venv", *relative)
        if candidate.is_file():
            return str(candidate)
    return None


def same_path(first: str, second: str) -> bool:
    return os.path.normcase(os.path.abspath(first)) == os.path.normcase(os.path.abspath(second))
