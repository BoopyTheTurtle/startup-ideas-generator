---
name: improve
description: Build one improvement card that Edgar approved - branch and worktree, builder subagent, card-verify, reviewer subagent - and stop for his merge approval. Use as `/improve <card id>` after he approves a card in the app.
argument-hint: <card id>
---

# /improve <card id>

One approved card, start to a reviewed branch. Merging needs Edgar's own approval.

1. Check the card: `uv run python -m pipeline card-show ID`. It must be `approved`. If it
   is not, stop and say what state it is in. The weekly cap is two builds; `card-start`
   enforces it.
2. `uv run python -m pipeline card-start ID` creates branch `card/ID-...` and a worktree
   beside the repo, off `dev`, and prints the worktree path.
3. Start the `builder` subagent with the card id and the worktree path. It implements
   the card, adds tests, commits, and runs `card-verify`. If verify still lists problems
   after the builder's two tries, run `card-abandon ID --reason ...` unless the problem is
   a missing eval run, in which case tell Edgar the cost and ask before running it.
4. When `card-verify` passes, the card is `built`. Start the `reviewer` subagent with the
   card id. It records `approve` (card becomes `ready`) or `changes` (back to `building`;
   send it to the builder once more, then re-verify and re-review).
5. Report to Edgar: files changed, test count, the eval diff if any, the reviewer's notes.
   Then, in order:
   - If the card says it needs a held-out check, he must run it himself (his usual
     commands on the card's branch) and record pass or fail on the card's page. You never
     run it or look at the result.
   - He approves the merge on the card's page in the app.
   - Only then, and only when he asks, run `uv run python -m pipeline card-merge ID` from
     the main checkout with `dev` checked out. The next reassess measures the effect and
     opens a revert card if the metric moved the wrong way.

Never edit the loop's own files, never push, and never merge by hand.
