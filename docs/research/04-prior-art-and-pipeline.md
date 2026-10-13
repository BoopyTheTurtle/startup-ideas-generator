# Prior art and pipeline patterns

Stage 0 research, 2026-10-13. Covers existing opportunity-discovery tools, the technical
patterns for turning text signals into problem clusters cheaply, and how to structure
Claude agents around the pipeline. Prices come from vendor pages where reachable and from
third-party listings otherwise; the source of each is marked.

## Part A — Prior art

### Commercial tools

Every commercial tool in this space sells one of two things: trend curves (is interest
in X rising?) or curated idea lists (here is a problem worth solving). None sells a
transparent, auditable path from raw complaint to problem statement. That gap is our
opening, and our main design constraint.

| Tool | What it does | Data and method | Price | Copy / avoid |
|---|---|---|---|---|
| Exploding Topics | Database of rising topics, products, startups, by category | "Consumer behavior signals across dozens of platforms," flagged by an algorithm, then confirmed by human curators ([pricing page](https://explodingtopics.com/pricing)). Owned by Semrush since August 2024 ([DesignRush](https://news.designrush.com/semrush-buys-exploding-topics-to-strengthen-market-research-capabilities)) | $39 / $99 / $249 per month ([pricing page](https://explodingtopics.com/pricing)) | Copy the algorithm-then-human-curation loop and the "meta trend" grouping. Avoid opaque sources: users cannot tell why a topic qualifies |
| Glimpse | Browser extension and API that turn Google Trends' 0–100 index into absolute search volume, plus forecasts and alerts | Built on Google Trends; absolute volume is Glimpse's own estimate ([Glimpse](https://meetglimpse.com/insights/google-trends-search-volume/)) | API is quote-only ([OutlierKit](https://outlierkit.com/resources/glimpse-pricing/)) | Copy year-over-year growth as the headline metric. We cannot afford it; use raw Trends indices and compare relative growth only |
| SparkToro | Audience research: where a defined group of people reads, listens, and talks | Demographics, social, websites, podcasts, YouTube, Reddit, search and bio keywords ([pricing page](https://sparktoro.com/pricing)) | Free (3 previews), Business $150/mo, Agency $300/mo; now ships MCP access ([pricing page](https://sparktoro.com/pricing)) | Useful downstream, in the dossier stage, to answer "where does this person type hang out?" Not a problem source |
| Treendly | Trend tracking with a one-year forecast per trend ([changelog](https://changelog.flatnine.co/treendly/trend-forecasting-see-where-trends-are-heading)) | Sources undisclosed | Free tier (3 monitored trends, API/MCP access); Pro €99/yr ([pricing page](https://treendly.com/pricing)) | Cheapest trend API with MCP; worth a trial as a secondary signal. Avoid relying on forecasts we cannot audit |
| Trends.vc | Founder-written market reports plus a paid community | Human research; method undisclosed ([site](https://join.trends.vc/)) | Free reports; Trends Pro price unlisted | Copy the report format (problem, players, playbook, risks) as a dossier template |
| IdeaBrowser (Greg Isenberg) | Curated catalog of 1,000+ ideas, each scored on search volume, growth, pain, feasibility, revenue potential; a research agent for user ideas | Reddit, search, and YouTube signals plus a human curation team ([Stork](https://www.stork.ai/tool/ideabrowser-com)) | Reported $499 / $1,499 / $2,999 per year as of October 2026 ([Preuve](https://preuve.ai/compare/ideabrowser)); vendor page returned HTTP 429, so unverified | Copy the per-idea scorecard. Avoid its weakness, flagged by a competitor: the research agent does not cite claims back to sources ([BigIdeasDB](https://bigideasdb.com/ideabrowser-alternative)). Its own pages call scores "educational" |
| ProblemHunt | Users post problems they would pay to have solved, with contact details ([Product Hunt](https://www.producthunt.com/posts/problemhunt)) | Self-submitted | Free | A source of explicit willingness-to-pay statements, small but high-signal |

### The GummySearch failure and what it means for Reddit

GummySearch, the best-known Reddit audience-research tool, closed to new business on
November 30, 2025, after it failed to win a commercial license for Reddit's Data API. The
founder wrote that the team "were not able to reach an agreement" aligned with Reddit's
policies, and that the product had to become non-commercial or shut down; it had served
over 135,000 users ([GummySearch](https://gummysearch.com/final-chapter)). Paid access
runs out over 2026 and all data is deleted on December 1, 2026
([closure notice](https://gummysearch.com/closing-time)).

Reddit tightened access further the same month. Its Responsible Builder Policy ended
self-service API keys: every new OAuth token now needs explicit approval, and developers
are steered to Devvit ([r/redditdev announcement](https://www.reddit.com/r/redditdev/comments/1oug31u/)).
Third-party write-ups report the free tier at 100 queries per minute for approved
non-commercial use, with commercial use negotiated privately and no public rate card
([SocialCrawl](https://www.socialcrawl.dev/blog/reddit-data-api-2026)); these are vendor
blogs, so treat the numbers as indicative.

Three implications follow. First, a personal, non-commercial research tool sits inside
the policy that sank GummySearch's business, but we still need approval for an OAuth
app, and approval can take weeks. Second, open-source miners already route around the
API: one uses Reddit's public JSON endpoints, another uses web search plus RSS feeds paced
by rate-limit headers ([Reddit-AI-Analysis](https://github.com/Aillumine/Reddit-AI-Analysis),
[reddit-research](https://github.com/zachwelch98/reddit-research)). Those routes work
today and can close tomorrow. Third, any product built on this pipeline later inherits
GummySearch's risk; Reddit should be one source among several, never the spine.

### Open-source projects

Several small GitHub projects already implement the extract-cluster-score loop. None has
traction (most show zero or one star), but together they validate the architecture and
offer tested field lists and weights.

- **reddit-research** ([zachwelch98](https://github.com/zachwelch98/reddit-research)) is
  the closest match to our design. It classifies posts with Claude Haiku 4.5 through the
  Message Batches API with the rubric prompt-cached; extracts a one-sentence problem,
  persona, industry, workflow, tools mentioned, and 0–3 scores for willingness to pay,
  underservedness, AI solvability, and intensity, each with an evidence quote; embeds
  summaries with Voyage into **sqlite-vec**; clusters with k-means, dissolving clusters
  under three members; assigns new items to the nearest centroid above cosine 0.88; and
  relabels a cluster with Sonnet when it grows by half. Every ranked problem links to its
  posts. It reports $1.57 to classify 964 posts and ships an eval command that measures
  precision and recall against hand labels. Its author warns the classifier has not yet
  been checked against those labels.
- **Pain-Point-Miner** ([alexgutscher26](https://github.com/alexgutscher26/Pain-Point-Miner))
  extracts intensity, urgency, monetization, market maturity, existing alternatives,
  sentiment, and workaround complexity; clusters on OpenAI embeddings in PGVector; and
  tracks keyword frequency over time to flag rising problems. It wraps scraped text in
  delimiters before the LLM sees it, a cheap prompt-injection guard worth copying.
- **pain-discovery** ([albertorsesc](https://github.com/albertorsesc/pain-discovery/blob/main/README.md))
  runs fully local on Ollama models, scans Reddit, Hacker News (Algolia), and 1–2 star
  Trustpilot reviews, filters by engagement thresholds, deduplicates in three layers
  (cursor, lookup, UNIQUE constraint), and stores everything in SQLite behind a local
  dashboard. It clusters with an LLM rather than embeddings, which scales poorly.
- **idea-pain-point-finder** ([stevenzhang070302](https://github.com/stevenzhang070302/idea-pain-point-finder))
  uses LangGraph agents to pick communities and score "desperation."

Academic work on app-review mining supports a cheap classifier tier: zero-shot GPT-3.5
reached F1 0.849 sorting reviews into bugs, feature requests, and experiences, and
fine-tuned Llama 2 and Mistral came close
([Gunathilaka and de Silva, 2025](https://scitepress.org/PublishedPapers/2025/133756)).

### Lessons from failures

Two failure modes recur. Platform dependence killed GummySearch outright. Weak validation
kills the founders these tools serve: CB Insights finds "no market need" in 42% of
startup post-mortems ([Stax Bill](https://staxbill.com/lessons-from-saas-startups-that-failed)),
and founders repeatedly confuse engagement with willingness to pay
([PeerPush](https://peerpush.com/p/the-saas-validation-playbook)). Our scorer should
therefore weight explicit payment signals (money spent, tools tried, hours lost) above
upvotes and emotion, as reddit-research does when it scores intensity at zero weight.

## Part B — Pipeline patterns

### Stage layout

The proven shape is a funnel: cheap filters on everything, a small model on survivors,
embeddings on extracted problems, and a frontier model only on clusters.

1. **Collect** raw records weekly into `raw_item`, keyed by source and source ID, with
   the full text and a content hash. Never mutate raw rows.
2. **Pre-filter** with rules: engagement thresholds, language, length, and a pain-phrase
   regex ("I hate," "is there a tool," "how do you deal with," "I'd pay"). This removes
   most volume for free, as pain-discovery's thresholds and reddit-research's
   pain-phrase search both show.
3. **Extract** one structured record per pain mention with a small model. Use a JSON
   schema with: `is_pain` (bool), `problem` (one sentence, solution-free), `who`
   (role/person type), `context` (workflow, industry), `current_workaround`,
   `tools_mentioned`, `payment_signal` (0–3), `frequency_signal`, `intensity` (0–3), and
   `evidence_quote` (verbatim span). Require the quote; it anchors provenance and
   exposes hallucination.
4. **Embed** the `problem` + `who` string, not the raw post. Short normalized statements
   cluster far better than noisy posts.
5. **Cluster and link** extracted problems to canonical problems (below).
6. **Score and trend** canonical problems weekly.
7. **Synthesize** names, statements, and dossiers with a larger model.

### Embeddings and clustering

Local embeddings cost nothing and suit this volume. For CPU on Windows,
nomic-embed-text-v1.5 (~137M parameters, Matryoshka dimensions) and all-MiniLM-L6-v2
(~0.1 GB) are the usual picks; Qwen3-Embedding-0.6B leads on quality per memory
([D-Central](https://d-central.tech/local-embedding-models/)). Benchmark two candidates on
a hand-labelled sample of our own problems before committing, because MTEB variants are
not comparable with each other. Store the model name with every vector; changing models
means re-embedding everything.

For clustering, three options fit:

- **HDBSCAN** (in scikit-learn since 1.3,
  [docs](https://scikit-learn.org/stable/modules/generated/sklearn.cluster.HDBSCAN.html))
  finds clusters of varying density and labels outliers as noise, which suits long-tail
  complaints. Reduce dimensions with UMAP first.
- **BERTopic** wraps embeddings, UMAP, HDBSCAN, and c-TF-IDF keywords, supports LLM
  topic labels, `topics_over_time`, and `merge_models` to fold a new week's model into a
  baseline, adding only dissimilar topics
  ([BERTopic docs mirror](https://huggingface.co/kisejin/TopicModelingRepo/blob/main/BERTopic/docs/getting_started/merge/merge.md)).
  Good for exploration notebooks; heavier than we need in production.
- **k-means plus LLM labelling**, the Clio pattern: summarize each item, embed, k-means,
  then let an LLM name clusters and build a hierarchy. Anthropic's manual review found
  about 97% of Clio's cluster titles accurate ([Clio, arXiv 2412.13678](https://arxiv.org/pdf/2412.13678)).

### "The same problem" across weeks and sources

Entity resolution matters more than the clustering algorithm. Without it, each weekly
run produces fresh clusters and trends become impossible to measure. The pattern that
works is a **stable canonical-problem table with incremental assignment**:

1. Each canonical problem keeps a centroid, a name, a statement, and a version.
2. A new extracted problem joins the nearest canonical problem when similarity clears a
   threshold (reddit-research uses cosine 0.88 to the centroid). Tune it on labelled pairs.
3. Unassigned items accumulate in a pool; when the pool clusters (HDBSCAN, minimum size
   3), the cluster becomes a candidate canonical problem.
4. A weekly LLM pass reviews near-duplicate canonical pairs (centroid similarity in a
   grey band, say 0.80–0.88) and proposes merges or splits; the human approves in the UI.
   Record merges in a `problem_alias` table so old IDs still resolve.
5. Re-cluster from scratch only on demand, and map old canonical IDs to new ones by
   member overlap.

Deduplicate at the record level too: exact hashes for cross-posts, and near-duplicate
detection (MinHash or embedding similarity > 0.95) for copy-pasted complaints, so one
loud poster cannot fake frequency.

### Trend detection

Trend math runs on weekly counts per canonical problem and per source, stored as a
time series rather than recomputed from raw rows.

- **Growth**: compare a recent window with a baseline (e.g., last 4 weeks vs the prior
  12), using counts of *distinct authors*, not posts. Add a smoothed rate so one viral
  thread does not dominate.
- **Anomalies**: robust z-score on residuals (median and MAD), which tolerates the heavy
  tails of social data.
- **Seasonality**: for Google Trends and other search series, decompose with STL
  (`statsmodels.tsa.seasonal.STL`, `period=52` for weekly data) and measure growth on the
  trend component, or compare year over year as Glimpse does
  ([STL overview](https://doc.dataiku.com/dss/11/time-series/time-series-preparation/decomposition.html)).
  STL needs at least two years of history; pull it once at backfill.
- **Cold start**: social sources give us no history on day one. Backfill where APIs allow
  (Hacker News Algolia does); otherwise label trends "insufficient data" until eight weeks
  accumulate.

### Provenance

Every inferred claim must trace back to source records. That is our differentiator over
IdeaBrowser and the cheapest guard against hallucination. The schema enforces it:

```sql
raw_item(id, source, source_id, url, author_hash, created_at, fetched_at,
         title, body, metrics_json, content_hash, UNIQUE(source, source_id))
run(id, kind, started_at, git_sha, prompt_id, model, cost_usd, status)
prompt(id, name, version, text_hash, created_at)          -- prompt registry
extraction(id, raw_item_id, run_id, prompt_id, is_pain, problem, who,
           payload_json, evidence_quote, quote_start, quote_end)
embedding(owner_type, owner_id, model, dim)                -- plus a vec0 table
problem(id, name, statement, status, version, created_run_id)
problem_member(problem_id, extraction_id, similarity, assigned_run_id)
problem_alias(old_id, new_id, reason, decided_by, decided_at)
signal_weekly(problem_id, source, week, mentions, authors, engagement)
score(problem_id, run_id, rubric_version, total, components_json)
decision(id, problem_id, action, reason, user_note, created_at)  -- steering log
```

Rules: append-only raw and extraction tables; every derived row carries `run_id` and
`prompt_id`; the dossier writer may cite only `raw_item.id` values it read, and a
validator rejects citations that do not exist or whose quote fails to match the stored
text.

### Vectors in SQLite

Use **sqlite-vec**. It installs with `pip install sqlite-vec`, runs on Windows, and
supports metadata and partition-key columns for filtering
([GitHub](https://github.com/asg017/sqlite-vec)). It is pre-v1, so pin the version.
Brute-force search over tens of thousands of 384–768-dimension vectors takes
milliseconds, which covers years of weekly runs. Keep vectors in `vec0` tables beside
the relational data so one file holds everything and Next.js can read the same database.
For clustering itself, load vectors into NumPy; sqlite-vec serves nearest-neighbour
assignment and the UI's "similar problems" view.

### Cost control

Claude's small model makes bulk extraction nearly free. Current list prices: Haiku 5.5
at $0.10 / $0.50 per million input/output tokens, $0.05 / $0.25 through the Batch API;
Sonnet 5.5 at $2 / $10; cache reads at 0.1x input (0.05x on Sonnet 5.5 and Opus 5.5)
([Anthropic pricing](https://platform.claude.com/docs/en/about-claude/pricing)). Batch
and caching discounts stack. Ten thousand pre-filtered posts a week at ~600 input and
~150 output tokens costs about $0.70 a week on batched Haiku 5.5. Synthesis on a few
dozen clusters with Sonnet stays in single dollars.

Rules that keep it there:

- Rules and local models filter first; the LLM sees only survivors.
- Batch every bulk call; batches can take up to 24 hours, which suits a weekly cadence.
  Use the 1-hour cache for shared rubrics, since batch requests may outlast the 5-minute
  cache ([batch docs](https://docs.claude.com/en/docs/build-with-claude/message-batches)).
- Cache by `(content_hash, prompt_id)`: never re-extract an unchanged record under an
  unchanged prompt.
- Relabel clusters only on material change (reddit-research's 50% growth rule).
- Run an `estimate` command before any paid call, as reddit-research does, and log
  `cost_usd` per run.

Fully local extraction through Ollama remains possible (pain-discovery proves it), but on
a typical Windows laptop it is slow and less accurate; at under a dollar a week, batched
Haiku wins until volume grows a hundredfold.

### Recommended stack

| Layer | Choice |
|---|---|
| Collectors | Python 3.12, `httpx`, `tenacity` for retries, `feedparser` for RSS, `pytrends` or equivalent for Trends; one module per source with a cursor table |
| Storage | SQLite in WAL mode (lets Next.js read while Python writes); `sqlite-vec` pinned |
| Schema and migrations | Plain SQL files plus a tiny migration runner; `sqlite-utils` for ad-hoc work |
| Extraction | `anthropic` SDK, Message Batches, JSON schema output, Haiku 5.5 |
| Embeddings | `sentence-transformers` with nomic-embed-text-v1.5 or all-MiniLM-L6-v2, CPU |
| Clustering | `umap-learn` + scikit-learn `HDBSCAN`; BERTopic in notebooks for exploration |
| Trends | `pandas`, `statsmodels` (STL), robust z-scores |
| Validation | `pydantic` models mirroring the extraction schema |
| Scheduling | Windows Task Scheduler calling `python -m pipeline weekly` |

## Part C — Agent design

### What Claude Code offers today

Claude Code provides three building blocks, each documented and current as of this
month.

- **Subagents** live in `.claude/agents/*.md` with frontmatter for `tools`, `model`,
  `permissionMode`, `maxTurns`, preloaded `skills`, and a persistent `memory` directory.
  Each starts with a fresh context and returns only its final summary; subagents can nest
  three levels deep and run up to 20 at once
  ([subagents docs](https://code.claude.com/docs/en/sub-agents)).
- **Skills** live in `.claude/skills/<name>/SKILL.md`, load only when invoked, can bundle
  scripts referenced through `${CLAUDE_SKILL_DIR}`, can pre-run shell commands to inject
  live context, and can run in a forked subagent with `context: fork`
  ([skills docs](https://code.claude.com/docs/en/skills)).
- **Scheduling**: Desktop scheduled tasks run locally on Windows with file access, fire
  only while the app is open and the machine awake, and run one catch-up after missed
  runs ([Desktop docs](https://code.claude.com/docs/en/desktop-scheduled-tasks)). `/loop`
  tasks die with the session and expire after seven days; cloud routines cannot see local
  files ([scheduling docs](https://code.claude.com/docs/en/scheduled-tasks)). Headless
  `claude -p` supports `--output-format json` with `--json-schema`, `--allowedTools`,
  `--max-budget-usd`, and `--permission-prompts none` for unattended runs, and reports
  `total_cost_usd` ([headless docs](https://code.claude.com/docs/en/headless)).

### Division of labour

Deterministic work belongs in Python; judgement belongs in Claude. Collection,
filtering, batched extraction, embedding, clustering, and trend math are scripts the
Task Scheduler runs. Claude agents handle what needs reading and reasoning, and they act
on the database through those same scripts.

| Agent / skill | Kind | Model | Job |
|---|---|---|---|
| `/weekly-run` | Skill, user-invoked | — | Runs the Python pipeline, reads the run report, flags failed collectors and cost anomalies |
| `cluster-curator` | Subagent | Sonnet | Reviews new candidate problems and grey-band merge pairs; names and states problems; writes proposals to a `proposal` table for human approval |
| `scorer` | Skill with a rubric file | Sonnet | Applies the versioned rubric to shortlisted problems, citing member records for each component |
| `dossier-writer` | Subagent | Opus or Sonnet | Builds the evidence dossier for one chosen problem; may cite only `raw_item` IDs it queried |
| `red-team` | Subagent, read-only tools | different model from the writer | Attacks the dossier: existing competitors, weak evidence, sample bias, platform risk; outputs objections the writer must answer |
| `/eval` | Skill | — | Runs the extractor and scorer against the eval set and diffs against the last prompt version |

Shared state lives in SQLite, never in agent context. Agents read through a small,
read-only query script (or a SQLite MCP server restricted to SELECT) and write only
through scripts that insert proposals, scores, and dossiers with `run_id` and
`prompt_id` attached. Files hold what humans edit: rubrics, prompts, and dossiers as
Markdown under `docs/dossiers/`. Give each subagent a minimal tool list; the red-team
should have no write access at all.

### Making the system improve

Improvement needs three loops, each logged in the database.

1. **Eval sets.** Hand-label 200 raw items (pain or not, correct problem statement) and
   30–50 canonical problems as known-good or known-bad, including some deliberately bad
   (vague, solved, no payer). Every prompt change runs `/eval` and must not regress
   precision. reddit-research's labelling tool and eval command are a working template.
2. **Steering as feedback.** Every UI action (promote, reject, merge, split, rename,
   "wrong person type") writes a `decision` row with a reason code and free-text note.
   Rejected problems become negative examples for the scorer; repeated reject reasons
   become rubric amendments the curator proposes and Edgar approves. Over time the
   decision log becomes the best eval set we own.
3. **Prompt and rubric versioning.** Store prompts as files in git with a content hash
   registered in the `prompt` table; every derived row records which version produced it.
   This lets us re-score history under a new rubric and compare rankings side by side.

A subagent's `memory: project` directory suits soft lessons ("users reject problems
whose payer is a hobbyist"), but the database remains the authority, because the UI
and scripts cannot read agent memory.

## Implications for our design

1. **Build the provenance chain first.** Raw item → extraction with verbatim quote →
   canonical problem → score → dossier citation, enforced by schema and a citation
   validator. No competitor offers this; it is the product.
2. **Treat Reddit as fragile.** Apply for an OAuth app now under non-commercial terms,
   fall back to RSS and public JSON, and launch with sources that carry no licence risk:
   Hacker News (Algolia), app-store and Trustpilot reviews, GitHub issues, Stack Exchange,
   and Google Trends.
3. **Spend on synthesis, not volume.** Rules filter, batched Haiku 5.5 extracts for under
   a dollar a week, local embeddings cluster, Sonnet names and scores, Opus writes
   dossiers. Log cost per run from day one.
4. **Make canonical problems stable.** Incremental centroid assignment, a candidate pool,
   human-approved merges, and an alias table matter more than the choice of clustering
   algorithm; trends depend on them.
5. **Measure trends on distinct authors and seasonally adjusted search data**, and show
   "insufficient data" until eight weeks accumulate.
6. **Weight payment signals over engagement** in the scoring rubric, and version the
   rubric.
7. **Use SQLite + sqlite-vec in WAL mode** as the single store shared by Python, Next.js,
   and Claude agents; pin sqlite-vec while it remains pre-v1.
8. **Keep agents few and narrow**: curator, scorer, dossier-writer, red-team, plus
   `/weekly-run` and `/eval` skills. Python does the deterministic work on Task Scheduler;
   Claude Code sessions do the reading. Move bulk calls to the Claude API batch endpoint,
   not to Claude Code, since subscription usage limits suit interactive work.
9. **Log every steering decision with a reason** and grow the eval set from it; no prompt
   ships without an eval diff.
10. **Borrow freely from reddit-research**: its extraction fields, cosine-0.88 assignment,
    50%-growth relabel rule, cost estimator, and eval command match our design closely.
