"""LLM runtime: one interface, so moving from Claude Code to the API is config, not code.

ClaudeCode calls the `claude` CLI in print mode with tools disabled and a JSON schema, so
calls run under Edgar's Claude subscription without a session. It runs from the temp
directory so no project CLAUDE.md is loaded into the prompt, and it turns off MCP
servers, skills, and user/project settings (hooks, plugins) so nothing but the model
sees the input.
"""

import json
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from typing import Protocol

DEFAULT_MODEL = "claude-haiku-5-5"
DEFAULT_TIMEOUT_S = 300


class LLMError(RuntimeError):
    """A failed model call. `exit_code` is the CLI's exit status when one exists; callers
    handling no-retain text log only the class and exit code, since the message may echo
    the input."""

    def __init__(self, message: str, exit_code: int | None = None):
        super().__init__(message)
        self.exit_code = exit_code


@dataclass
class LLMResult:
    data: dict
    model: str
    cost_usd: float


class Runtime(Protocol):
    name: str

    def run(self, system: str, user: str, schema: dict, model: str) -> LLMResult: ...


def _kill_tree(proc: subprocess.Popen) -> None:
    """Kill the CLI and its children (claude.cmd wraps node on Windows)."""
    if os.name == "nt":
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)],
                       capture_output=True, timeout=30, check=False)
    else:
        proc.kill()


class ClaudeCode:
    name = "claude-code"

    def __init__(self, timeout_s: int = DEFAULT_TIMEOUT_S):
        exe = shutil.which("claude")
        if not exe:
            raise LLMError("claude CLI not found on PATH")
        self.exe = exe
        self.timeout_s = timeout_s

    def command(self, system: str, schema: dict, model: str) -> list[str]:
        return [self.exe, "-p", "--output-format", "json", "--model", model, "--tools", "",
                "--no-session-persistence", "--strict-mcp-config", "--disable-slash-commands",
                "--setting-sources", "", "--system-prompt", system,
                "--json-schema", json.dumps(schema), "Process the input on stdin."]

    def run(self, system: str, user: str, schema: dict, model: str = DEFAULT_MODEL) -> LLMResult:
        cmd = self.command(system, schema, model)
        try:
            proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE, text=True, encoding="utf-8",
                                    errors="replace", cwd=tempfile.gettempdir())
        except (OSError, ValueError) as e:
            raise LLMError(f"could not start claude: {type(e).__name__}: {e}") from e
        try:
            stdout, stderr = proc.communicate(input=user, timeout=self.timeout_s)
        except subprocess.TimeoutExpired as e:
            _kill_tree(proc)
            proc.communicate()
            raise LLMError(f"claude timed out after {self.timeout_s}s",
                           exit_code=proc.returncode) from e
        except (OSError, ValueError, UnicodeError) as e:
            _kill_tree(proc)
            proc.communicate()
            raise LLMError(f"claude I/O failed: {type(e).__name__}: {e}",
                           exit_code=proc.returncode) from e
        return self.parse(stdout, stderr, proc.returncode, model)

    @staticmethod
    def parse(stdout: str, stderr: str, returncode: int | None, model: str) -> LLMResult:
        try:
            out = json.loads(stdout)
        except (json.JSONDecodeError, ValueError) as e:
            tail = (stderr or stdout or "")[-300:]
            raise LLMError(f"claude exit {returncode}, unparseable output: {tail}",
                           exit_code=returncode) from e
        if not isinstance(out, dict):
            raise LLMError(f"claude exit {returncode}, output is {type(out).__name__}",
                           exit_code=returncode)
        if out.get("is_error") or "structured_output" not in out:
            raise LLMError(f"claude error: {str(out.get('result') or out)[:300]}",
                           exit_code=returncode)
        data = out["structured_output"]
        if not isinstance(data, dict):
            raise LLMError(f"claude structured_output is {type(data).__name__}, not an object",
                           exit_code=returncode)
        used = list((out.get("modelUsage") or {}).keys())
        try:
            cost = float(out.get("total_cost_usd") or 0.0)
        except (TypeError, ValueError):
            cost = 0.0
        return LLMResult(data, used[0] if used else model, cost)
