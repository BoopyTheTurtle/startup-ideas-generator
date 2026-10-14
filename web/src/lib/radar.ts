// Read queries behind the steering pages: themes, problems, quotes, snapshots, merges,
// decisions, runs. Server only. Every exported reader awaits connection() first,
// because node:sqlite is synchronous and would otherwise run during prerendering.
import { connection } from "next/server";
import { open } from "@/lib/db";

type Conn = NonNullable<ReturnType<typeof open>>;

// Active pains: an item's extraction under the active extract prompt, else its latest
// (pipeline.embed.ACTIVE_PAIN_SQL). Python records the active prompt's id in
// pipeline_state (key active_extract_prompt_id); before that table exists, or while the
// key is unset, the prompt of the newest extraction row stands in.
const NEWEST_PROMPT = "(SELECT x3.prompt_id FROM extraction x3 ORDER BY x3.id DESC LIMIT 1)";

function activePromptSql(conn: Conn): string {
  if (!hasTable(conn, "pipeline_state")) return NEWEST_PROMPT;
  return `COALESCE((SELECT CAST(ps.value AS INTEGER) FROM pipeline_state ps
                     WHERE ps.key = 'active_extract_prompt_id'), ${NEWEST_PROMPT})`;
}

function activePainSql(conn: Conn): string {
  return `
  SELECT p.* FROM pain p
  JOIN extraction x ON x.id = p.extraction_id
  WHERE x.id = COALESCE(
    (SELECT x2.id FROM extraction x2
      WHERE x2.raw_item_id = x.raw_item_id AND x2.prompt_id = ${activePromptSql(conn)}),
    (SELECT MAX(x2.id) FROM extraction x2 WHERE x2.raw_item_id = x.raw_item_id))`;
}

// One row per pain with the raw item it came from. `pains` is a pain-shaped subquery.
function painInfo(pains: string): string {
  return `
    SELECT a.id AS pain_id, a.problem, a.who, a.workaround, a.cost_cue, a.intensity,
           a.evidence_level, a.quote, a.quote_kind,
           r.id AS raw_item_id, r.source, r.url, r.country, r.lang, r.created_at, r.fetched_at,
           COALESCE(r.author_hash, 'item:' || r.id) AS author_key
      FROM (${pains}) a
      JOIN extraction x ON x.id = a.extraction_id
      JOIN raw_item r ON r.id = x.raw_item_id`;
}

function activeInfo(conn: Conn): string {
  return painInfo(activePainSql(conn));
}
const ALL_INFO = painInfo("SELECT * FROM pain");

// Quote cards: verbatim first, then stronger evidence, then higher intensity.
const QUOTE_ORDER = `(i.quote_kind = 'verbatim') DESC, i.evidence_level DESC, i.intensity DESC, i.pain_id`;

export type Quote = {
  pain_id: number;
  problem: string;
  who: string;
  workaround: string | null;
  cost_cue: string | null;
  intensity: number;
  evidence_level: string;
  quote: string;
  quote_kind: "verbatim" | "paraphrase";
  raw_item_id: number;
  source: string;
  url: string | null;
  country: string | null;
  lang: string | null;
  created_at: string | null;
  fetched_at: string;
};

const QUOTE_COLS = `i.pain_id, i.problem, i.who, i.workaround, i.cost_cue, i.intensity,
  i.evidence_level, i.quote, i.quote_kind, i.raw_item_id, i.source, i.url, i.country, i.lang,
  i.created_at, i.fetched_at`;

function hasTable(conn: Conn, name: string): boolean {
  return !!conn.prepare("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?").get(name);
}

// --- Themes ----------------------------------------------------------------------------

export type ThemeRun = { id: number; started_at: string; finished_at: string | null };

export type ThemeProblem = { theme_id: number; problem_id: number; title: string; status: string; n: number; total: number };

export type Theme = {
  id: number;
  run_id: number;
  title: string;
  statement: string | null;
  title_source: string;
  size: number;
  distinct_authors: number;
  sources: number;
  countries: number;
  cohesion: number | null;
  source_names: string | null;
};

export type ThemeWithDetail = Theme & { samples: Quote[]; problems: ThemeProblem[] };

function latestThemesRunSync(conn: Conn): ThemeRun | null {
  if (!hasTable(conn, "theme")) return null;
  const row = conn
    .prepare(
      `SELECT id, started_at, finished_at FROM run
        WHERE kind = 'themes' AND status = 'ok' ORDER BY id DESC LIMIT 1`,
    )
    .get();
  return (row as ThemeRun | undefined) ?? null;
}

const THEME_COLS = `t.id, t.run_id, t.title, t.statement, t.title_source, t.size, t.distinct_authors,
  t.sources, t.countries, t.cohesion,
  (SELECT GROUP_CONCAT(src, ', ') FROM (
     SELECT DISTINCT r.source AS src FROM theme_member tm
       JOIN pain p ON p.id = tm.pain_id
       JOIN extraction x ON x.id = p.extraction_id
       JOIN raw_item r ON r.id = x.raw_item_id
      WHERE tm.theme_id = t.id ORDER BY src)) AS source_names`;

// Links between the themes of one run and problems, by raw item. Theme members are the
// pains active when the themes run happened; problem members follow re-extraction to the
// new pains. Joining both on the raw item keeps the overlap stable when an item is
// re-extracted after the themes run. n counts the problem's active pains whose item sits
// in the theme; total counts all its active pains.
type ThemeLink = ThemeProblem & { theme_title: string; theme_title_source: string };

function themeLinks(
  conn: Conn,
  runId: number,
  opts: { themeId?: number; problemId?: number; majorityOnly: boolean },
): ThemeLink[] {
  return conn
    .prepare(
      `WITH info AS (${activeInfo(conn)}),
            pm AS (SELECT m.problem_id, i.pain_id, i.raw_item_id
                     FROM problem_member m JOIN info i ON i.pain_id = m.pain_id),
            totals AS (SELECT problem_id, COUNT(*) AS total FROM pm GROUP BY problem_id),
            titem AS (SELECT DISTINCT tm.theme_id, x.raw_item_id
                        FROM theme_member tm
                        JOIN theme t ON t.id = tm.theme_id AND t.run_id = ?
                        JOIN pain p ON p.id = tm.pain_id
                        JOIN extraction x ON x.id = p.extraction_id
                       WHERE ? IS NULL OR tm.theme_id = ?),
            inside AS (SELECT ti.theme_id, pm.problem_id, COUNT(DISTINCT pm.pain_id) AS n
                         FROM titem ti JOIN pm ON pm.raw_item_id = ti.raw_item_id
                        WHERE ? IS NULL OR pm.problem_id = ?
                        GROUP BY ti.theme_id, pm.problem_id)
       SELECT s.theme_id, s.problem_id, p.title, p.status, s.n, t.total,
              th.title AS theme_title, th.title_source AS theme_title_source
         FROM inside s
         JOIN totals t ON t.problem_id = s.problem_id
         JOIN problem p ON p.id = s.problem_id AND p.status != 'merged'
         JOIN theme th ON th.id = s.theme_id
        WHERE ? = 0 OR s.n * 2 > t.total
        ORDER BY s.n DESC, s.theme_id`,
    )
    .all(
      runId,
      opts.themeId ?? null,
      opts.themeId ?? null,
      opts.problemId ?? null,
      opts.problemId ?? null,
      opts.majorityOnly ? 1 : 0,
    ) as ThemeLink[];
}

// Problems whose active members fall mostly (over half) inside a theme of `runId`.
function themeProblems(conn: Conn, runId: number, themeId: number | null): ThemeProblem[] {
  return themeLinks(conn, runId, { themeId: themeId ?? undefined, majorityOnly: true });
}

export type ProblemTheme = { theme_id: number; title: string; title_source: string; n: number; total: number };

// Themes of the latest themes run that hold any of a problem's active pains.
function problemThemesSync(conn: Conn, problemId: number): ProblemTheme[] {
  const run = latestThemesRunSync(conn);
  if (!run) return [];
  return themeLinks(conn, run.id, { problemId, majorityOnly: false }).map((l) => ({
    theme_id: l.theme_id,
    title: l.theme_title,
    title_source: l.theme_title_source,
    n: l.n,
    total: l.total,
  }));
}

// Titles for page metadata and outcome banners. Missing ids are left out.
export async function problemTitles(ids: number[]): Promise<Map<number, string>> {
  await connection();
  const conn = open();
  const out = new Map<number, string>();
  if (!conn || ids.length === 0) return out;
  const rows = conn
    .prepare("SELECT id, title FROM problem WHERE id IN (SELECT value FROM json_each(?))")
    .all(JSON.stringify(ids)) as { id: number; title: string }[];
  for (const r of rows) out.set(r.id, r.title);
  return out;
}

export async function themeTitle(id: number): Promise<string | null> {
  await connection();
  const conn = open();
  if (!conn || !hasTable(conn, "theme")) return null;
  const row = conn.prepare("SELECT title FROM theme WHERE id = ?").get(id) as { title: string } | undefined;
  return row?.title ?? null;
}

export async function currentThemes(): Promise<{ run: ThemeRun | null; themes: ThemeWithDetail[] }> {
  await connection();
  const conn = open();
  if (!conn) return { run: null, themes: [] };
  const run = latestThemesRunSync(conn);
  if (!run) return { run: null, themes: [] };
  const themes = conn
    .prepare(
      `SELECT ${THEME_COLS} FROM theme t WHERE t.run_id = ?
        ORDER BY t.distinct_authors DESC, t.size DESC, t.id`,
    )
    .all(run.id) as Theme[];
  const samples = conn
    .prepare(
      `SELECT * FROM (
         SELECT tm.theme_id, ${QUOTE_COLS},
                ROW_NUMBER() OVER (PARTITION BY tm.theme_id ORDER BY ${QUOTE_ORDER}) AS rn
           FROM theme_member tm
           JOIN theme t ON t.id = tm.theme_id AND t.run_id = ?
           JOIN (${ALL_INFO}) i ON i.pain_id = tm.pain_id)
        WHERE rn <= 2`,
    )
    .all(run.id) as (Quote & { theme_id: number })[];
  const problems = themeProblems(conn, run.id, null);
  return {
    run,
    themes: themes.map((t) => ({
      ...t,
      samples: samples.filter((s) => s.theme_id === t.id),
      problems: problems.filter((p) => p.theme_id === t.id),
    })),
  };
}

export type ThemeDetail = {
  theme: Theme;
  run: ThemeRun | null;
  currentRunId: number | null;
  quotes: Quote[];
  problems: ThemeProblem[];
};

export async function themeDetail(id: number, limit = 100): Promise<ThemeDetail | null> {
  await connection();
  const conn = open();
  if (!conn || !hasTable(conn, "theme")) return null;
  const theme = conn.prepare(`SELECT ${THEME_COLS} FROM theme t WHERE t.id = ?`).get(id) as
    | Theme
    | undefined;
  if (!theme) return null;
  const run = (conn
    .prepare("SELECT id, started_at, finished_at FROM run WHERE id = ?")
    .get(theme.run_id) ?? null) as ThemeRun | null;
  const quotes = conn
    .prepare(
      `SELECT ${QUOTE_COLS} FROM theme_member tm JOIN (${ALL_INFO}) i ON i.pain_id = tm.pain_id
        WHERE tm.theme_id = ? ORDER BY ${QUOTE_ORDER} LIMIT ?`,
    )
    .all(id, limit) as Quote[];
  return {
    theme,
    run,
    currentRunId: latestThemesRunSync(conn)?.id ?? null,
    quotes,
    problems: themeProblems(conn, theme.run_id, id),
  };
}

// --- Problems --------------------------------------------------------------------------

export type SnapshotPoint = {
  run_id: number;
  run_started_at: string;
  mentions: number;
  distinct_authors: number;
  sources: number;
  new_mentions: number;
};

export type ProblemRow = {
  id: number;
  title: string;
  status: string;
  title_source: string;
  mentions: number;
  distinct_authors: number;
  sources: number;
  countries: number;
  new_mentions: number | null; // in the latest snapshot run; null when the problem has no row there
  history: SnapshotPoint[];
};

export type RadarFilter = { status: string; source: string; sort: "authors" | "growth" };

export const STATUS_FILTERS = ["open", "new", "watching", "promoted", "archived", "all"] as const;

function statsSql(conn: Conn, where: string): string {
  return `
    WITH info AS (${activeInfo(conn)})
    SELECT pr.id, pr.title, pr.status, pr.title_source, pr.statement, pr.merged_into,
           pr.created_run_id, pr.updated_at,
           COUNT(i.pain_id) AS mentions,
           COUNT(DISTINCT i.author_key) AS distinct_authors,
           COUNT(DISTINCT i.source) AS sources,
           COUNT(DISTINCT i.country) AS countries
      FROM problem pr
      LEFT JOIN problem_member m ON m.problem_id = pr.id
      LEFT JOIN info i ON i.pain_id = m.pain_id
     WHERE ${where}
     GROUP BY pr.id`;
}

function latestSnapshotRun(conn: Conn): number | null {
  const row = conn.prepare("SELECT MAX(run_id) AS id FROM snapshot").get() as { id: number | null };
  return row.id;
}

function histories(conn: Conn, ids: number[]): Map<number, SnapshotPoint[]> {
  const out = new Map<number, SnapshotPoint[]>();
  if (ids.length === 0) return out;
  const rows = conn
    .prepare(
      `SELECT s.problem_id, s.run_id, r.started_at AS run_started_at, s.mentions,
              s.distinct_authors, s.sources, s.new_mentions
         FROM snapshot s JOIN run r ON r.id = s.run_id
        WHERE s.problem_id IN (SELECT value FROM json_each(?))
        ORDER BY s.run_id`,
    )
    .all(JSON.stringify(ids)) as (SnapshotPoint & { problem_id: number })[];
  for (const { problem_id, ...p } of rows) {
    const list = out.get(problem_id) ?? [];
    list.push(p);
    out.set(problem_id, list);
  }
  return out;
}

export async function radarProblems(filter: RadarFilter): Promise<{
  problems: ProblemRow[];
  snapshotRuns: number;
  latestRun: number | null;
} | null> {
  await connection();
  const conn = open();
  if (!conn) return null;
  const clauses = ["pr.status != 'merged'"];
  const args: string[] = [];
  if (filter.status === "open") clauses.push("pr.status IN ('new', 'watching', 'promoted')");
  else if (filter.status !== "all") {
    clauses.push("pr.status = ?");
    args.push(filter.status);
  }
  if (filter.source) {
    clauses.push(`EXISTS (SELECT 1 FROM problem_member m2 JOIN raw_item r2 ON r2.id =
      (SELECT x2.raw_item_id FROM pain p2 JOIN extraction x2 ON x2.id = p2.extraction_id
        WHERE p2.id = m2.pain_id)
      WHERE m2.problem_id = pr.id AND r2.source = ?)`);
    args.push(filter.source);
  }
  const rows = conn.prepare(statsSql(conn, clauses.join(" AND "))).all(...args) as Omit<
    ProblemRow,
    "history" | "new_mentions"
  >[];
  const latestRun = latestSnapshotRun(conn);
  const hist = histories(
    conn,
    rows.map((r) => r.id),
  );
  const problems: ProblemRow[] = rows.map((r) => {
    const history = hist.get(r.id) ?? [];
    const last = history.at(-1);
    return {
      ...r,
      history,
      new_mentions: last && last.run_id === latestRun ? last.new_mentions : null,
    };
  });
  problems.sort((a, b) =>
    filter.sort === "growth"
      ? (b.new_mentions ?? -1) - (a.new_mentions ?? -1) ||
        b.distinct_authors - a.distinct_authors ||
        a.id - b.id
      : b.distinct_authors - a.distinct_authors || b.mentions - a.mentions || a.id - b.id,
  );
  const runs = conn.prepare("SELECT COUNT(DISTINCT run_id) AS n FROM snapshot").get() as { n: number };
  return { problems, snapshotRuns: runs.n, latestRun };
}

// Sources that have at least one pain filed under a problem, for the radar filter.
export async function problemSources(): Promise<string[]> {
  await connection();
  const conn = open();
  if (!conn) return [];
  const rows = conn
    .prepare(
      `SELECT DISTINCT r.source FROM problem_member m
         JOIN pain p ON p.id = m.pain_id
         JOIN extraction x ON x.id = p.extraction_id
         JOIN raw_item r ON r.id = x.raw_item_id
        ORDER BY r.source`,
    )
    .all() as { source: string }[];
  return rows.map((r) => r.source);
}

// Follows merge aliases (problem_alias, then merged_into) to the problem an id lives in now.
export async function resolveProblemId(id: number): Promise<number | null> {
  await connection();
  const conn = open();
  if (!conn) return null;
  const seen = new Set<number>();
  let cur = id;
  while (!seen.has(cur)) {
    seen.add(cur);
    const alias = conn.prepare("SELECT new_id FROM problem_alias WHERE old_id = ?").get(cur) as
      | { new_id: number }
      | undefined;
    if (alias) {
      cur = alias.new_id;
      continue;
    }
    const row = conn.prepare("SELECT status, merged_into FROM problem WHERE id = ?").get(cur) as
      | { status: string; merged_into: number | null }
      | undefined;
    if (!row) return null;
    if (row.status === "merged" && row.merged_into != null) {
      cur = row.merged_into;
      continue;
    }
    return cur;
  }
  return null; // alias cycle
}

export type Decision = {
  id: number;
  action: string;
  reason: string | null;
  note: string | null;
  created_at: string;
};

export type MergePair = {
  a_id: number;
  b_id: number;
  similarity: number;
  status: string;
  run_id: number;
  other_id: number;
  other_title: string;
};

export type ProblemDetail = {
  problem: ProblemRow & {
    statement: string | null;
    created_run_id: number;
    updated_at: string;
  };
  quotes: Quote[];
  decisions: Decision[];
  pairs: MergePair[];
  aliases: { old_id: number; reason: string; decided_at: string }[];
  themes: ProblemTheme[];
  snapshotRuns: number;
};

export async function problemDetail(id: number, limit = 100): Promise<ProblemDetail | null> {
  await connection();
  const conn = open();
  if (!conn) return null;
  const row = conn.prepare(statsSql(conn, "pr.id = ?")).get(id) as
    | (Omit<ProblemRow, "history" | "new_mentions"> & {
        statement: string | null;
        created_run_id: number;
        updated_at: string;
      })
    | undefined;
  if (!row) return null;
  const history = histories(conn, [id]).get(id) ?? [];
  const latestRun = latestSnapshotRun(conn);
  const last = history.at(-1);
  const quotes = problemQuotesSync(conn, id, limit);
  const decisions = conn
    .prepare(
      `SELECT id, action, reason, note, created_at FROM decision
        WHERE problem_id = ? ORDER BY id DESC`,
    )
    .all(id) as Decision[];
  const pairs = conn
    .prepare(
      `SELECT c.a_id, c.b_id, c.similarity, c.status, c.run_id,
              CASE WHEN c.a_id = ? THEN c.b_id ELSE c.a_id END AS other_id,
              p.title AS other_title
         FROM merge_candidate c
         JOIN problem p ON p.id = CASE WHEN c.a_id = ? THEN c.b_id ELSE c.a_id END
        WHERE c.a_id = ? OR c.b_id = ?
        ORDER BY c.status = 'open' DESC, c.similarity DESC`,
    )
    .all(id, id, id, id) as MergePair[];
  const aliases = conn
    .prepare("SELECT old_id, reason, decided_at FROM problem_alias WHERE new_id = ? ORDER BY old_id")
    .all(id) as ProblemDetail["aliases"];
  const runs = conn.prepare("SELECT COUNT(DISTINCT run_id) AS n FROM snapshot").get() as { n: number };
  return {
    problem: {
      ...row,
      history,
      new_mentions: last && last.run_id === latestRun ? last.new_mentions : null,
    },
    quotes,
    decisions,
    pairs,
    aliases,
    themes: problemThemesSync(conn, id),
    snapshotRuns: runs.n,
  };
}

function problemQuotesSync(conn: Conn, id: number, limit: number): Quote[] {
  return conn
    .prepare(
      `SELECT ${QUOTE_COLS} FROM problem_member m JOIN (${activeInfo(conn)}) i ON i.pain_id = m.pain_id
        WHERE m.problem_id = ? ORDER BY ${QUOTE_ORDER} LIMIT ?`,
    )
    .all(id, limit) as Quote[];
}

// --- Merges ----------------------------------------------------------------------------

export type MergeSide = {
  id: number;
  title: string;
  title_source: string;
  statement: string | null;
  status: string;
  mentions: number;
  distinct_authors: number;
  sources: number;
  quotes: Quote[];
};

export type OpenMerge = { a: MergeSide; b: MergeSide; similarity: number; run_id: number };

export async function openMerges(): Promise<OpenMerge[] | null> {
  await connection();
  const conn = open();
  if (!conn) return null;
  const pairs = conn
    .prepare(
      `SELECT a_id, b_id, similarity, run_id FROM merge_candidate
        WHERE status = 'open' ORDER BY similarity DESC`,
    )
    .all() as { a_id: number; b_id: number; similarity: number; run_id: number }[];
  if (pairs.length === 0) return [];
  const ids = [...new Set(pairs.flatMap((p) => [p.a_id, p.b_id]))];
  const stats = conn
    .prepare(statsSql(conn, "pr.id IN (SELECT value FROM json_each(?))"))
    .all(JSON.stringify(ids)) as (Omit<MergeSide, "quotes">)[];
  const byId = new Map(stats.map((s) => [s.id, s]));
  const side = (id: number): MergeSide | null => {
    const s = byId.get(id);
    return s ? { ...s, quotes: problemQuotesSync(conn, id, 3) } : null;
  };
  const out: OpenMerge[] = [];
  for (const p of pairs) {
    const a = side(p.a_id);
    const b = side(p.b_id);
    if (a && b) out.push({ a, b, similarity: p.similarity, run_id: p.run_id });
  }
  return out;
}

// --- Runs ------------------------------------------------------------------------------

export type RunWithCost = {
  id: number;
  kind: string;
  status: string;
  started_at: string;
  finished_at: string | null;
  note: string | null;
  cost_usd: number | null;
};

export async function runsWithCost(limit = 50): Promise<{
  runs: RunWithCost[];
  cost30d: number;
} | null> {
  await connection();
  const conn = open();
  if (!conn) return null;
  const runs = conn
    .prepare(
      `SELECT r.id, r.kind, r.status, r.started_at, r.finished_at, r.note,
              (SELECT SUM(m.value) FROM metric m
                WHERE m.run_id = r.id AND m.name LIKE '%cost_usd%') AS cost_usd
         FROM run r ORDER BY r.id DESC LIMIT ?`,
    )
    .all(limit) as RunWithCost[];
  const total = conn
    .prepare(
      `SELECT COALESCE(SUM(m.value), 0) AS v FROM metric m JOIN run r ON r.id = m.run_id
        WHERE m.name LIKE '%cost_usd%' AND julianday(r.started_at) >= julianday('now') - 30`,
    )
    .get() as { v: number };
  return { runs, cost30d: total.v };
}
