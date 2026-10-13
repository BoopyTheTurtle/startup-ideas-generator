import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from pipeline import __main__ as cli
from pipeline.lock import LockTimeout, single_instance


def test_second_acquisition_times_out_until_release(tmp_path):
    path = tmp_path / ".pipeline.lock"
    with single_instance(timeout_s=1, path=path):
        with pytest.raises(LockTimeout):
            with single_instance(timeout_s=0.3, path=path, poll_s=0.05):
                pass
    with single_instance(timeout_s=0.3, path=path):
        pass


def test_lock_held_by_another_process(tmp_path):
    path = tmp_path / ".pipeline.lock"
    holder = textwrap.dedent(f"""
        import sys, time
        from pipeline.lock import single_instance
        with single_instance(timeout_s=5, path=__import__('pathlib').Path({str(path)!r})):
            print('locked', flush=True)
            time.sleep(60)
    """)
    proc = subprocess.Popen([sys.executable, "-c", holder], stdout=subprocess.PIPE, text=True,
                            cwd=Path(__file__).resolve().parent.parent)
    try:
        assert proc.stdout.readline().strip() == "locked"
        with pytest.raises(LockTimeout):
            with single_instance(timeout_s=0.5, path=path, poll_s=0.1):
                pass
    finally:
        proc.kill()
        proc.wait()
    with single_instance(timeout_s=5, path=path, poll_s=0.1):  # released on process exit
        pass


def test_cli_write_commands_wait_and_read_only_ones_do_not(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("SIG_DB", str(tmp_path / "t.db"))
    assert cli.main(["migrate"]) == 0
    with single_instance(timeout_s=1, path=tmp_path / ".pipeline.lock"):
        assert cli.main(["--lock-wait", "0.005", "smoke"]) == cli.LOCK_TIMEOUT_EXIT
        assert "not run" in capsys.readouterr().err
        assert cli.main(["status"]) == 0
    assert cli.main(["smoke"]) == 0
