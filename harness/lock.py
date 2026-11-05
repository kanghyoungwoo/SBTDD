"""One writer of a project's .harness evidence at a time.

The lock is an operating-system file lock, so it disappears when its holder exits for any reason,
including SIGKILL. It coordinates honest harness processes; it is not a security boundary.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
import errno
import hashlib
import json
import os
from pathlib import Path
import secrets
import sys
import time
from typing import Any

from .guard import plain_path

if sys.platform == "win32":
    import msvcrt
else:
    import fcntl


TOKEN_VARIABLE = "HARNESS_LOCK_TOKEN"
LOCK_FILE = "lock"
OWNER_FILE = "lock-owner.json"
# Windows byte-range locks are mandatory: reads that overlap them fail even through another handle
# of the holder. Lock one byte far past the empty file's content so evidence snapshots can read it.
WINDOWS_LOCK_OFFSET = 1 << 30
_held: dict[Path, str] = {}


class ProjectLocked(ValueError):
    def __init__(self, root: Path, owner: dict[str, Any]) -> None:
        self.owner = owner
        holder = (f"{owner.get('command', 'a command')} (pid {owner.get('pid', '?')}, "
                  f"since {owner.get('started_at', '?')})" if owner else "an unknown command")
        super().__init__(f"Another harness command is using {root}: {holder}. Wait for it to finish; "
                         "the lock is released automatically when that process exits.")


def environment(**overrides: str) -> dict[str, str]:
    """Child environment without the lock token, so AI tools and checks cannot borrow the lock."""
    values = {key: value for key, value in os.environ.items() if key != TOKEN_VARIABLE}
    values.update(overrides)
    return values


def held_token(root: Path) -> str | None:
    return _held.get(root.resolve())


def digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def try_lock(descriptor: int) -> bool:
    if sys.platform == "win32":
        os.lseek(descriptor, WINDOWS_LOCK_OFFSET, os.SEEK_SET)
        try:
            msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)
        except OSError as error:
            if error.errno in (errno.EACCES, getattr(errno, "EDEADLOCK", errno.EDEADLK)):
                return False
            raise
        return True
    else:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return False
        return True


def unlock(descriptor: int) -> None:
    if sys.platform == "win32":
        os.lseek(descriptor, WINDOWS_LOCK_OFFSET, os.SEEK_SET)
        msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)
    else:
        fcntl.flock(descriptor, fcntl.LOCK_UN)


def read_owner(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def write_owner(path: Path, owner: dict[str, Any]) -> None:
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(owner, indent=2) + "\n", encoding="utf-8")
    for attempt in range(4):
        try:
            temporary.replace(path)
            return
        except PermissionError:  # Windows: a waiting process may be reading the owner file.
            if attempt == 3:
                raise
            time.sleep(0.05 * 2 ** attempt)


@contextmanager
def project_lock(root: Path, command: str) -> Iterator[str | None]:
    """Hold the project lock, or join it when started by the holder's own verifier call."""
    key = root.resolve()
    if key in _held:
        yield _held[key]
        return
    evidence = root / ".harness"
    path, owner_path = evidence / LOCK_FILE, evidence / OWNER_FILE
    for item in (path, owner_path, owner_path.with_name(OWNER_FILE + ".tmp")):
        plain_path(item)
    evidence.mkdir(parents=True, exist_ok=True)
    # Waiting processes only open the lock file; they never write evidence while it is held.
    descriptor = os.open(path, os.O_RDWR | os.O_CREAT, 0o644)
    try:
        if not try_lock(descriptor):
            owner = read_owner(owner_path)
            token = os.environ.get(TOKEN_VARIABLE, "")
            if token and secrets.compare_digest(digest(token), str(owner.get("token_sha256", ""))):
                yield None
                return
            raise ProjectLocked(root, {key: value for key, value in owner.items() if key != "token_sha256"})
        try:
            token = secrets.token_hex(16)
            write_owner(owner_path, {"command": command, "pid": os.getpid(), "token_sha256": digest(token),
                                     "started_at": datetime.now(timezone.utc).isoformat()})
            _held[key] = token
            yield token
        finally:
            _held.pop(key, None)
            unlock(descriptor)
    finally:
        os.close(descriptor)
