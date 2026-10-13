// Locates the repository root, where data/ and evals/ live, however the app starts.
// SIG_ROOT wins when set. Otherwise walk up from the working directory to the first
// folder holding pyproject.toml, so `npm --prefix web run dev` from the repo root and
// `npm run dev` from web/ both find it. The module's own location is no help here: the
// bundler moves server code into web/.next/.
import { existsSync } from "node:fs";
import path from "node:path";

function findRepoRoot(): string {
  if (process.env.SIG_ROOT) return path.resolve(process.env.SIG_ROOT);
  let dir = process.cwd();
  for (;;) {
    // A runtime lookup, not a build input.
    if (existsSync(/*turbopackIgnore: true*/ path.join(dir, "pyproject.toml"))) return dir;
    const parent = path.dirname(dir);
    if (parent === dir) break;
    dir = parent;
  }
  throw new Error(
    `no pyproject.toml above ${process.cwd()}; start the app inside the repo or set SIG_ROOT`,
  );
}

export const REPO_ROOT = findRepoRoot();
