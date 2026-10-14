// Runs `uv run --frozen --no-sync python -m pipeline merge KEEP DROP --reason CODE
// [--note TEXT]` from the repo root. Python owns merges (members move, centroid
// recomputes, aliases update, the higher status carries over), so the app shells out
// instead of writing those tables. execFile with an argument array: no shell, so nothing
// in the note can be interpreted as a command. --frozen --no-sync keep uv from resolving
// or installing packages inside a request; the environment `uv sync` built is used as is.
// SIG_DB passes through the environment, so the CLI writes the same database the app reads.
import { execFile } from "node:child_process";
import { REPO_ROOT } from "@/lib/paths";

const TIMEOUT_MS = 150_000;
const LOCK_WAIT_MINUTES = "1"; // another pipeline command holding the lock: give up after a minute
const LOCK_TIMEOUT_EXIT = 75;

export type MergeOutcome = { ok: boolean; message: string };

type Exec = { error: (Error & { code?: string | number }) | null; stdout: string; stderr: string; timedOut: boolean };

function tail(text: string, max = 800): string {
  const t = text.trim();
  return t.length > max ? `…${t.slice(-max)}` : t;
}

// On Windows `uv` starts python as a child; killing uv alone would leave python running
// (and holding the pipeline lock), so the whole tree goes.
function killTree(pid: number | undefined): void {
  if (pid === undefined) return;
  if (process.platform === "win32") {
    execFile("taskkill", ["/T", "/F", "/PID", String(pid)], { windowsHide: true }, () => {});
  } else {
    try {
      process.kill(pid, "SIGKILL");
    } catch {
      // already gone
    }
  }
}

function pipeline(args: string[]): Promise<Exec> {
  return new Promise((resolve) => {
    let timedOut = false;
    const child = execFile(
      "uv",
      ["run", "--frozen", "--no-sync", "python", "-m", "pipeline", ...args],
      {
        cwd: REPO_ROOT,
        windowsHide: true,
        maxBuffer: 1024 * 1024,
        encoding: "utf8",
        env: { ...process.env, PYTHONUTF8: "1" },
      },
      (error, stdout, stderr) => {
        clearTimeout(timer);
        resolve({ error: error as Exec["error"], stdout, stderr, timedOut });
      },
    );
    const timer = setTimeout(() => {
      timedOut = true;
      killTree(child.pid);
    }, TIMEOUT_MS);
  });
}

export async function runMerge(keep: number, drop: number, reason: string, note: string): Promise<MergeOutcome> {
  const base = ["--lock-wait", LOCK_WAIT_MINUTES, "merge", String(keep), String(drop), "--reason", reason];
  let res = await pipeline(note ? [...base, "--note", note] : base);
  // A pipeline older than migration 006 has no --note; keep the note in the reason there.
  if (note && res.error && /unrecognized arguments: --note/.test(res.stderr)) {
    res = await pipeline([...base.slice(0, -1), `${reason}: ${note}`.slice(0, 300)]);
  }
  const { error, stdout, stderr, timedOut } = res;
  const out = tail(`${stdout}\n${stderr}`);
  if (!error) {
    return { ok: true, message: tail(stdout) || `Merged problem ${drop} into ${keep}.` };
  }
  if (error.code === "ENOENT") {
    return { ok: false, message: "Could not start `uv`: is it on the app's PATH?" };
  }
  if (timedOut) {
    return {
      ok: false,
      message: `pipeline merge timed out after ${TIMEOUT_MS / 1000}s and was stopped. It may still have completed — reload to check.`,
    };
  }
  if (error.code === LOCK_TIMEOUT_EXIT) {
    return { ok: false, message: "Another pipeline command holds the lock. Try again when it finishes." };
  }
  return { ok: false, message: out || `pipeline merge failed (${String(error.code ?? error.message)}).` };
}
