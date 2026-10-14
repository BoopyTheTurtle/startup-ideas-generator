// Runs `uv run python -m pipeline merge KEEP DROP --reason TEXT` from the repo root.
// Python owns merges (members move, centroid recomputes, aliases update), so the app
// shells out instead of writing those tables. execFile with an argument array: no shell,
// so nothing in the reason can be interpreted as a command. SIG_DB passes through the
// environment, so the CLI writes the same database the app reads.
import { execFile } from "node:child_process";
import { REPO_ROOT } from "@/lib/paths";

const TIMEOUT_MS = 150_000;
const LOCK_WAIT_MINUTES = "1"; // another pipeline command holding the lock: give up after a minute
const LOCK_TIMEOUT_EXIT = 75;

export type MergeOutcome = { ok: boolean; message: string };

function tail(text: string, max = 800): string {
  const t = text.trim();
  return t.length > max ? `…${t.slice(-max)}` : t;
}

export function runMerge(keep: number, drop: number, reason: string): Promise<MergeOutcome> {
  const args = [
    "run",
    "python",
    "-m",
    "pipeline",
    "--lock-wait",
    LOCK_WAIT_MINUTES,
    "merge",
    String(keep),
    String(drop),
    "--reason",
    reason,
  ];
  return new Promise((resolve) => {
    execFile(
      "uv",
      args,
      {
        cwd: REPO_ROOT,
        timeout: TIMEOUT_MS,
        windowsHide: true,
        maxBuffer: 1024 * 1024,
        encoding: "utf8",
        env: { ...process.env, PYTHONUTF8: "1" },
      },
      (error, stdout, stderr) => {
        const out = tail(`${stdout}\n${stderr}`);
        if (!error) {
          resolve({ ok: true, message: tail(stdout) || `Merged problem ${drop} into ${keep}.` });
          return;
        }
        const e = error as Error & { killed?: boolean; code?: string | number };
        if (e.code === "ENOENT") {
          resolve({ ok: false, message: "Could not start `uv`: is it on the app's PATH?" });
        } else if (e.killed) {
          resolve({ ok: false, message: `pipeline merge timed out after ${TIMEOUT_MS / 1000}s. ${out}` });
        } else if (e.code === LOCK_TIMEOUT_EXIT) {
          resolve({
            ok: false,
            message: "Another pipeline command holds the lock. Try again when it finishes.",
          });
        } else {
          resolve({ ok: false, message: out || `pipeline merge failed (${String(e.code ?? e.message)}).` });
        }
      },
    );
  });
}
