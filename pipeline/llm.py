"""LLM runtime: one interface, so moving from Claude Code to the API is config, not code.

ClaudeCode calls the `claude` CLI in print mode with tools disabled and a JSON schema, so
calls run under Edgar's Claude subscription without a session. It runs from the temp
directory so no project CLAUDE.md is loaded into the prompt.
"""

import json
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from typing import Protocol

DEFAULT_MODEL = "claude-haiku-5-5"


class LLMError(RuntimeError):
    pass


@dataclass
class LLMResult:
    data: dict
    model: str
    cost_usd: float


class Runtime(Protocol):
    name: str

    def run(self, system: str, user: str, schema: dict, model: str) -> LLMResult: ...


class ClaudeCode:
    name = "claude-code"

    def __init__(self, timeout_s: int = 600):
        exe = shutil.which("claude")
        if not exe:
            raise LLMError("claude CLI not found on PATH")
        self.exe = exe
        self.timeout_s = timeout_s

    def run(self, system: str, user: str, schema: dict, model: str = DEFAULT_MODEL) -> LLMResult:
        cmd = [self.exe, "-p", "--output-format", "json", "--model", model, "--tools", "",
               "--no-session-persistence", "--system-prompt", system,
               "--json-schema", json.dumps(schema), "Process the input on stdin."]
        try:
            proc = subprocess.run(cmd, input=user, capture_output=True, text=True,
                                  encoding="utf-8", cwd=tempfile.gettempdir(),
                                  timeout=self.timeout_s)
        except subprocess.TimeoutExpired as e:
            raise LLMError(f"claude timed out after {self.timeout_s}s") from e
        try:
            out = json.loads(proc.stdout)
        except json.JSONDecodeError as e:
            tail = (proc.stderr or proc.stdout or "")[-300:]
            raise LLMError(f"claude exit {proc.returncode}, unparseable output: {tail}") from e
        if out.get("is_error") or "structured_output" not in out:
            raise LLMError(f"claude error: {str(out.get('result') or out)[:300]}")
        used = list((out.get("modelUsage") or {}).keys())
        return LLMResult(out["structured_output"], used[0] if used else model,
                         float(out.get("total_cost_usd") or 0.0))
