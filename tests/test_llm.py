import json
import sys
import time

import pytest

from pipeline.llm import ClaudeCode, LLMError

SCHEMA = {"type": "object"}


class Scripted(ClaudeCode):
    """ClaudeCode with the CLI replaced by a Python one-liner."""

    def __init__(self, code: str, timeout_s: int = 30):
        self.exe, self.timeout_s, self.code = sys.executable, timeout_s, code

    def command(self, system, schema, model):
        return [sys.executable, "-c", self.code]


def ok_output(data):
    return json.dumps({"structured_output": data, "modelUsage": {"m": {}}, "total_cost_usd": 0.5})


def test_command_isolates_the_cli():
    cc = Scripted("")
    cmd = ClaudeCode.command(cc, "sys", SCHEMA, "claude-haiku-5-5")
    for flag in ("--strict-mcp-config", "--disable-slash-commands", "--no-session-persistence"):
        assert flag in cmd
    assert cmd[cmd.index("--setting-sources") + 1] == ""
    assert cmd[cmd.index("--tools") + 1] == ""


def test_run_reads_stdin_and_parses():
    # The child decodes stdin as UTF-8 explicitly, as the real claude CLI does; a bare
    # sys.stdin.read() would use the Windows console code page.
    code = ("import sys, json; d = sys.stdin.buffer.read().decode('utf-8');"
            f" print(json.dumps({{'structured_output': {{'echo': d}}, 'modelUsage': {{'m': 1}}}}))")
    res = Scripted(code).run("s", "héllo", SCHEMA, "x")
    assert res.data == {"echo": "héllo"} and res.model == "m"


def test_invalid_utf8_becomes_llm_error_not_unicode_error():
    code = "import sys; sys.stdout.buffer.write(b'\\xff\\xfe not json')"
    with pytest.raises(LLMError, match="unparseable"):
        Scripted(code).run("s", "u", SCHEMA, "x")


def test_timeout_kills_the_process_tree():
    t0 = time.monotonic()
    with pytest.raises(LLMError, match="timed out"):
        Scripted("import time; time.sleep(60)", timeout_s=1).run("s", "u", SCHEMA, "x")
    assert time.monotonic() - t0 < 20


def test_missing_executable_is_llm_error():
    cc = Scripted("")
    cc.command = lambda *a: [r"Z:\no\such\claude.exe"]
    with pytest.raises(LLMError, match="could not start"):
        cc.run("s", "u", SCHEMA, "x")


@pytest.mark.parametrize("stdout", ["[1, 2]", json.dumps({"structured_output": [1]}),
                                    json.dumps({"is_error": True, "result": "nope"})])
def test_bad_shapes_are_llm_errors(stdout):
    with pytest.raises(LLMError) as e:
        ClaudeCode.parse(stdout, "", 1, "x")
    assert e.value.exit_code == 1


def test_parse_ok():
    res = ClaudeCode.parse(ok_output({"a": 1}), "", 0, "x")
    assert res.data == {"a": 1} and res.cost_usd == 0.5
