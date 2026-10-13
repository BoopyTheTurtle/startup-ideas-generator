"""Single-instance lock: one writing pipeline command at a time, across processes.

The daily forum task and the weekly run can overlap, and Edgar may run a command by
hand meanwhile. Each writing command holds an OS file lock on `.pipeline.lock` next to
the database (data/.pipeline.lock by default). The OS releases it when the process
exits, so a crash never leaves a stale lock.
"""

import os
import sys
import time
from contextlib import contextmanager
from pathlib import Path

from pipeline import db

if os.name == "nt":
    import msvcrt
else:
    import fcntl


class LockTimeout(RuntimeError):
    pass


def lock_path() -> Path:
    return db.db_path().parent / ".pipeline.lock"


def _try_lock(f) -> bool:
    try:
        if os.name == "nt":
            f.seek(0)
            msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except OSError:
        return False


def _unlock(f) -> None:
    if os.name == "nt":
        f.seek(0)
        msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        fcntl.flock(f.fileno(), fcntl.LOCK_UN)


@contextmanager
def single_instance(timeout_s: float = 3600, path: Path | None = None, poll_s: float = 2.0):
    """Hold the pipeline lock for the block. Waits up to `timeout_s`, then raises
    LockTimeout."""
    path = path or lock_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    f = open(path, "a+b")
    try:
        deadline = time.monotonic() + timeout_s
        announced = False
        while not _try_lock(f):
            if time.monotonic() >= deadline:
                raise LockTimeout(f"another pipeline command still holds {path} after"
                                  f" {timeout_s / 60:.0f} min")
            if not announced:
                print(f"pipeline: another pipeline command holds {path}; waiting up to"
                      f" {timeout_s / 60:.0f} min", file=sys.stderr, flush=True)
                announced = True
            time.sleep(min(poll_s, max(0.0, deadline - time.monotonic())))
        try:
            yield
        finally:
            _unlock(f)
    finally:
        f.close()
