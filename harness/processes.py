from collections.abc import Callable, Iterator
from contextlib import contextmanager
from functools import wraps
import os
import signal
import subprocess
import sys
import threading
from types import FrameType
from typing import Any, NoReturn, ParamSpec, TypeVar


P = ParamSpec('P')
R = TypeVar('R')

# Creation flags: no console window for helper processes, and a new process group so a whole tree
# can be stopped. They exist only on Windows; elsewhere new sessions do the same job.
if sys.platform == 'win32':
    NO_WINDOW = subprocess.CREATE_NO_WINDOW
    NEW_GROUP = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
else:
    NO_WINDOW = NEW_GROUP = 0


class TerminationRequested(KeyboardInterrupt):
    signal_name = 'SIGTERM'


def interrupt_on_term(function: Callable[P, R]) -> Callable[P, R]:
    @wraps(function)
    def wrapped(*args: P.args, **kwargs: P.kwargs) -> R:
        with termination_handler():
            return function(*args, **kwargs)
    return wrapped


@contextmanager
def termination_handler() -> Iterator[None]:
    if threading.current_thread() is not threading.main_thread():
        yield
        return
    previous = signal.getsignal(signal.SIGTERM)

    def stop(signum: int, frame: FrameType | None) -> NoReturn:
        raise TerminationRequested()

    signal.signal(signal.SIGTERM, stop)
    try:
        yield
    finally:
        signal.signal(signal.SIGTERM, previous)


def terminate_tree(process: 'subprocess.Popen[Any]') -> None:
    if sys.platform == 'win32':
        try:
            subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'],
                           capture_output=True, timeout=10, creationflags=NO_WINDOW)
        except (OSError, subprocess.TimeoutExpired):
            pass
        finally:
            if process.poll() is None:
                process.kill()
    else:
        try:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                pass
            # Also stop descendants that outlived the group leader.
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


def run_command(command: list[str], *, timeout: float, **kwargs: Any) -> 'subprocess.CompletedProcess[Any]':
    process: subprocess.Popen[Any] = subprocess.Popen(
        command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        start_new_session=sys.platform != 'win32', creationflags=NEW_GROUP, **kwargs,
    )
    try:
        output, errors = process.communicate(timeout=timeout)
    except (subprocess.TimeoutExpired, KeyboardInterrupt) as error:
        terminate_tree(process)
        try:
            output, errors = process.communicate(timeout=5)
            if isinstance(error, subprocess.TimeoutExpired):
                error.output, error.stderr = output, errors
        except subprocess.TimeoutExpired:
            pass
        raise
    return subprocess.CompletedProcess(command, process.returncode, output, errors)
