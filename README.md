# startup-ideas-generator

A personal tool for finding a startup worth building. Python collectors read public
complaint data weekly: forums, app reviews, petitions, consumer complaint databases, and
EU consultation feedback across the US, EEA, and UK. Claude agents turn the text into
problems people describe, cluster them, and track their rise and fall. A local Next.js
app lets one person steer the narrowing from hundreds of problems to one problem, one
segment, and an idea backed by an evidence dossier and a test plan.

Every claim links back to a verbatim quote from a source record. The tool audits itself
weekly and proposes its own improvements.

See [SPEC.md](SPEC.md) for the design and [PLAN.md](PLAN.md) for build progress.

## Run

Requires uv and Node 24.

```bash
uv sync
uv run python -m pipeline smoke
npm --prefix web install
npm --prefix web run dev
```

Open http://localhost:3000.
