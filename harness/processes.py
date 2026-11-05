from contextlib import contextmanager
from functools import wraps
import os
import signal
import subprocess
import threading


class TerminationRequested(KeyboardInterrupt):
    signal_name = 'SIGTERM'


def interrupt_on_term(function):
    @wraps(function)
    def wrapped(*args, **kwargs):
        with termination_handler():
            return function(*args, **kwargs)
    return wrapped


@contextmanager
def termination_handler():
    if threading.current_thread() is not threading.main_thread():
        yield
        return
    previous = signal.getsignal(signal.SIGTERM)

    def stop(signum, frame):
        raise TerminationRequested()

    signal.signal(signal.SIGTERM, stop)
    try:
        yield
    finally:
        signal.signal(signal.SIGTERM, previous)


def terminate_tree(process):
    if os.name == 'nt':
        try:
            subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'],
                           capture_output=True, timeout=10, creationflags=subprocess.CREATE_NO_WINDOW)
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


def run_command(command, *, timeout, **kwargs):
    process = subprocess.Popen(
        command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        start_new_session=os.name != 'nt',
        creationflags=(subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW) if os.name == 'nt' else 0,
        **kwargs,
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
