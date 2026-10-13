# 02 — Ideation methods: from raw signals to validated ideas

Stage 0 research, October 13, 2026. Question: which methods turn raw signals into
well-formed problem hypotheses, and how should a funnel narrow broad problem spaces into
specific ones? Claims below were checked against the linked sources; vendor claims are
marked as such.

## Summary

Problems, not ideas, should be the system's main unit. Every credible method here —
JTBD, Dan Olsen's problem/solution split, Torres's trees, the Mom Test, Paul Graham's
essay — puts the problem and the person first and the solution last. The evidence on
LLM ideation agrees: models generate plausible, individually strong ideas, but the sets
collapse toward the same few answers, and models judge ideas poorly. The machine should
therefore do breadth work (extraction, clustering, trend tracking, diverse candidate
generation) and leave the humans the judgments where machines measurably fail
(choosing segments, rating novelty, deciding what is worth a conversation).

## Methods

### Jobs-to-be-Done and Outcome-Driven Innovation

**Core idea.** People "hire" products to get a job done; each job breaks into desired
outcomes. Ulwick's ODI surveys customers on each outcome's importance and satisfaction,
then scores Opportunity = Importance + max(Importance − Satisfaction, 0), so importance
weighs roughly double ([Wikipedia](https://en.wikipedia.org/wiki/Outcome-Driven_Innovation)).
Strategyn computes both inputs as top-two-box percentages, not averaged scale points
([Strategyn](https://strategyn.com/quantify-your-customers-unmet-needs)).

**Inputs.** A defined job, a list of outcome statements, and a quantitative survey of a
named segment. **Funnel stage.** Problem + segment, after a segment is chosen.
**Evidence.** Strategyn's 86% success rate comes from an unnamed "independent study"
with no published definition of success or comparison group; treat it as marketing
([Strategyn](https://strategyn.com/successful-innovation-strategy/)). The scoring logic
itself is sound and widely adopted. **Failure modes.** Requires real survey data;
outcome lists drift into features; JTBD schools dispute the theory
([Klement critique](https://hackernoon.com/lite/why-jobs-to-be-done-doesnt-work-and-what-you-should-be-doing-instead)).

**For us.** We cannot survey weekly, but we can borrow the shape: express every problem
as a job and outcome, and proxy importance (frequency, intensity, spend) and
dissatisfaction (complaints about current solutions) from signals. The score becomes a
ranking heuristic, never a measured fact.

### Pain mining from communities and reviews

**Core idea.** People describe problems unprompted in forums, reviews, support threads,
and job posts. Pull the text, extract pains, cluster them, rank by frequency and
intensity, and keep permalinks as evidence
([practitioner guide](https://echai.ventures/how-founders-use-ai/market-research/how-do-i-mine-reddit-reviews-and-online-communities-with-ai-to-find-real-pain-points)).
Pre-LLM work already detected pain points in social posts with machine learning
(Salminen et al. 2022, [QCRI summary](https://acua.qcri.org/blog/?p=321)); LLM
extraction now works on review corpora
([arXiv 2510.16551](https://arxiv.org/abs/2510.16551v1)).

**Inputs.** Text with timestamps and source links. **Funnel stage.** Signal → problem
clusters; the system's main engine. **Evidence.** Extraction works but degrades on
informal text: a vendor benchmark of ten LLMs scored average F1 0.599 on Reddit versus
0.808 on Capterra ([BigIdeasDB, vendor](https://bigideasdb.com/llm-benchmark-pain-point-extraction)).
**Failure modes.** Loud minorities masquerade as markets; complainers rarely pay;
platforms skew toward developers and consumers; venting differs from willingness to
pay. Mitigate with source diversity, counts of distinct authors rather than posts, and
explicit signals of spend or workaround effort.

### Trend stacking and "why now"

**Core idea.** A good idea often becomes possible only because something changed.
Sequoia's business-plan template asks founders to trace the category's history and name
the recent trends that make the solution possible
([Sequoia template copy](https://fenix.tecnico.ulisboa.pt/downloadFile/1126518382322406/Sequoia%20Capital_pitchdecktemplate.pdf)).
Trend stacking combines two or more independent shifts (a cost curve, a regulation, a
behavior change) so the intersection is new.

**Inputs.** Time series: search interest, launches, filings, regulation, prices.
**Funnel stage.** Annotates clusters and ideas; it explains timing, not problems.
**Evidence.** Exploding Topics scrapes Reddit, Google, Amazon, and YouTube, flags
growing terms by machine, then has humans approve only those with sustained growth and
business value ([methodology](https://explodingtopics.com/methodology),
[process](https://explodingtopics.com/blog/find-trending-topics)). Its labels
(Exploding, Regular, Peaked) rest on Google search data; its 87% backtested accuracy is
self-reported. **Failure modes.** Search interest is attention, not demand; fads look
like trends for months; everyone reads the same trend lists, so trend-only ideas crowd.
Exploding Topics' own human review step exists because automation captures many
irrelevant topics. Mitigate by requiring sustained growth across several weeks and at
least two independent sources.

### Paul Graham: organic ideas, living in the future, schlep blindness

**Core idea.** Made-up "sitcom" ideas sound plausible but attract only polite interest.
Good ideas grow from noticing: "Live in the future, then build what's missing." Good
startups start like wells — narrow and deep — not broad and shallow. Founders filter out
tedious ideas (schlep blindness) and distasteful ones; the schlep filter does the most
harm ([How to Get Startup Ideas](https://paulgraham.com/startupideas.html)).

**Inputs.** A founder's own experience at a leading edge. **Funnel stage.** A filter at
every stage and a warning against the whole project. **Evidence.** Anecdotal but
consistent with Shane's findings below. **Failure modes.** An automated generator
produces exactly the sitcom ideas Graham warns about: plausible, broad, shallow.
**For us.** Score depth (how badly a small group wants it) over breadth; reward schlep
(regulated, messy, operational problems) instead of penalizing it; ask the human which
clusters touch a future they already live in.

### YC Requests for Startups

**Core idea.** Investors publish themes they want funded. The Fall 2026 list has 13
entries, including AI for the aging population, AI-native compliance infrastructure,
self-maintaining APIs, and new operating systems for the physical world. YC states the
list covers a fraction of what it funds ([YC RFS](https://www.ycombinator.com/rfs)).

**Funnel stage.** A prior over problem spaces, not a source of problems. **Failure
modes.** Thousands of founders read the same list, so it signals crowding as much as
opportunity. Use it as one weak signal type, tagged by date.

### Blue Ocean Strategy

**Core idea.** Create uncontested market space by removing, reducing, raising, and
creating factors relative to an industry's norms. **Funnel stage.** Late — shaping an
idea's positioning. **Evidence.** Retrospective, author-selected cases; critics argue
survivorship bias, and I found no test against failed blue-ocean attempts
([Kelley](https://bradenkelley.com/tag/blue-ocean-strategy/),
[Twente thesis](https://essay.utwente.nl/essays/65556)). **For us.** Its
strategy-canvas idea gives a useful prompt structure ("which factors do current
solutions overserve?"), which pairs with ODI's overserved outcomes. Low priority.

### Problem space versus solution space

**Core idea.** Dan Olsen's product-market-fit pyramid puts target customers and
underserved needs at the base and the value proposition, features, and UX above. Teams
fail by jumping to features before the problem is clear
([Mind the Product](https://www.mindtheproduct.com/sunday-rewind-mastering-the-problem-space-for-product-market-fit-by-dan-olsen)).
**Funnel stage.** The rule for the whole funnel. **For us.** Keep solution words out of
Problem records. A problem statement that names a product ("people need an app for X")
is a solution in disguise and should fail validation.

### Teresa Torres's opportunity solution trees

**Core idea.** A tree runs from one desired outcome, to opportunities (needs, pains,
desires found in research), to candidate solutions, to experiments that test each
solution's assumptions. A real opportunity admits several solutions; if only one comes
to mind, a solution has been framed as an opportunity
([ProdPad](https://www.prodpad.com/glossary/opportunity-solution-tree/)). Torres stresses
a living tree updated as evidence arrives.

**Funnel stage.** Problem + segment → idea. **Evidence.** Widely used practitioner
method; no controlled evaluation found. **For us.** The tree is our data model in
miniature: Problems nest into parent problems; each Idea hangs off a Problem; each Idea
carries assumptions and tests. Torres's test ("does this admit several solutions?")
makes a good automated check.

### The Mom Test

**Core idea.** Ask about the person's life, not your idea; ask about past specifics, not
hypotheticals; talk less. People are optimistic about what they would do and pay in an
imagined future ([summary](https://mtlynch.io/book-reports/the-mom-test/)).
**Funnel stage.** Validation, after an idea exists. **For us.** The system cannot run
these conversations, but it can prepare them: for each shortlisted problem, generate
interview questions about past behavior and current workarounds, and log the answers as
Evidence. The same rule applies to signals: a post describing what someone did ("I
spent three hours reconciling…") outweighs one stating what they want.

### Customer development and the Lean Canvas

**Core idea.** Steve Blank's four steps — customer discovery, customer validation,
customer creation, company building — treat a startup's beliefs as hypotheses to test
outside the building, looping back on failure
([Wikipedia](https://en.wikipedia.org/wiki/Steve_Blank)). Ash Maurya's Lean Canvas puts
Problem, Customer Segments (early adopters), Existing Alternatives, and Unfair
Advantage on one page ([LeanStack](https://leanspark.leanstack.com/learn/what-is-lean-canvas/)).

**Evidence.** The strongest of any method here. In a randomized trial of 116 Italian
startups, founders taught to form and test hypotheses performed better and switched
ideas more often ([Camuffo et al. 2020](https://iris.unibocconi.it/handle/11565/4013977)).
A replication across 759 firms found more idea termination and a non-linear effect on
pivots ([Camuffo et al. 2024](https://openaccess.city.ac.uk/id/eprint/32437)). The
mechanism: fewer false positives (pursuing bad ideas) and fewer false negatives
(dropping good ones). **For us.** Every Idea should carry explicit, falsifiable
assumptions and a kill condition; a Lean Canvas makes a good output template for the
final stage.

### Pattern libraries: unbundling and "vertical SaaS for X"

**Core idea.** Recurring structural moves generate ideas: unbundle a horizontal platform
into focused products, or rebuild horizontal software for one industry. Andrew Parker's
map of startups attacking Craigslist categories is the classic example; by 2015, 82
companies on its update had raised $8.87B
([CB Insights](https://www.cbinsights.com/research/craigslist-unbundling/)).

**Funnel stage.** Idea generation, applied to a chosen problem + segment. **Failure
modes.** Patterns produce solutions looking for problems ("Uber for X") and list
survivors only. **For us.** Use patterns as diversity operators — one prompt per pattern
— after a problem is fixed, never as a starting point.

### Academic work on opportunity recognition

Shane's study of eight teams commercializing one MIT 3D-printing patent found each saw a
different opportunity, shaped by prior knowledge of markets, ways to serve them, and
customer problems ([Shane 2000](https://www.ices.hr/en/wp-content/uploads/2019/01/Shane-Prior-Knowledge-and-the-Discovery-of-Entrepreneurial-Opportunities.pdf)).
Baron frames opportunity recognition as pattern recognition — connecting seemingly
unrelated changes — and Baron and Ensley found experienced founders hold richer,
more business-focused prototypes than novices
([Baron 2006](https://indico.ph.liv.ac.uk/event/1424/sessions/1151/attachments/3346/4675/Baron-OpportunityRecognitionPattern-2006.pdf),
[Baron & Ensley 2006](https://ideas.repec.org/a/inm/ormnsc/v52y2006i9p1331-1344.html)).
**For us.** Opportunity is relative to the person. The system should store Edgar's
knowledge and access as a profile and score founder fit explicitly; the human's prior
knowledge is an input, not noise.

## Evidence on LLM-assisted ideation

**LLM ideas look novel but shrink when executed.** In a study with 104 NLP researchers,
blind reviewers rated LLM research ideas more novel than expert ideas (5.64 versus 4.84
of 10) and slightly less feasible ([Si, Yang & Hashimoto 2024](https://arxiv.org/abs/2409.04109)).
When 43 experts then spent 100+ hours executing randomly assigned ideas, LLM ideas'
scores fell significantly more on every metric, and on many metrics the ranking flipped
in favor of humans ([Si et al. 2025](https://arxiv.org/abs/2506.20803)). Reviewers judging
a bare idea assume it will work; execution exposes the gaps.

**Homogeneity is the central failure.** Of 4,000 seed ideas per topic, only about 5%
survived deduplication at 0.8 cosine similarity ([Si et al. 2024](https://arxiv.org/html/2409.04109)).
Different models converge on the same answers to open-ended prompts — the "Artificial
Hivemind" effect, a NeurIPS 2025 best paper ([Jiang et al.](https://arxiv.org/abs/2510.22954v1)).
Writers given AI ideas wrote individually better stories that resembled each other more
([Doshi & Hauser 2024](https://pmc.ncbi.nlm.nih.gov/articles/PMC11244532)). For product
ideas, a July 2026 study found LLM ideas scored higher on purchase intent and were about
seven times as likely to reach the top 10%, yet were less novel and less diverse
([Terwiesch et al. 2026](https://arxiv.org/abs/2607.27553)).

**Diversity responds to known mitigations.** The same study brought diversity near human
levels by pooling ideas across vendors, chain-of-thought prompting, injecting
heterogeneous personas or constraints, and agents that explore broadly; generating more
ideas also improved coverage ([Terwiesch et al. 2026](https://arxiv.org/abs/2607.27553)).
Earlier work found chain-of-thought gave the largest diversity gain
([Meincke, Mollick & Terwiesch](https://papers.ssrn.com/abstract=4708466)). Distinct
personas cut plot similarity from 0.92 within a persona to 0.20 across personas
([Wan & Kalman 2025](https://arxiv.org/abs/2504.13868)).

**LLMs judge ideas poorly.** The best LLM judge agreed with human consensus 53% of the
time, below the 56% human-to-human rate ([Si et al. 2024](https://arxiv.org/html/2409.04109)).
Plain LLMs over-predict startup success under class imbalance
([SSFF, NeurIPS 2025](https://neurips.cc/virtual/2025/132524)). A pre-registered study found ChatGPT
beat human investors at predicting fundraising outcomes and survival
([Kleinert seminar](https://dipsa.unibg.it/sites/dip6/files/research_seminar_prof._kleinert_june_17.pdf)),
but a related 171-pitch study, which I could reach only through an abstract mirror,
attributes the survival accuracy largely to models' prior exposure to the ventures
online. Neither result transfers to judging unlaunched ideas.

**LLMs invent demand.** Synthetic survey respondents produce willingness-to-pay
estimates that are often inaccurate and sometimes wrong-signed, and they rate novelty
higher than humans do; fine-tuning helps only within known categories
([Brand, Israeli & Ngwe](https://papers.ssrn.com/abstract=4395751),
[Harvard D^3](https://d3.harvard.edu/?p=20067)).

### Failure modes and mitigations

| Failure | Cause | Mitigation |
|---|---|---|
| Homogeneity | Mode collapse; same prompt, same answer | Seed generation with specific evidence, not topics; personas and pattern operators; more than one model; embedding dedup against all past ideas |
| Generic ideas | Broad, shallow framing | Require a named segment and a concrete scenario quoted from a Signal; score depth over breadth |
| Hallucinated demand | LLM fills gaps with plausible claims | Every claim links to Evidence rows; no Evidence, no claim; never use synthetic respondents as demand |
| Survivorship bias | Pattern libraries and case studies list winners | Track dead companies and failed attempts as Evidence against; ask "who tried this and failed?" |
| Solutions looking for problems | Starting from technology or patterns | Generate ideas only from a Problem record; Torres's several-solutions test |
| Novelty illusion | Judges reward unexecuted novelty | Weight feasibility and evidence over novelty; humans rate novelty |
| Unreliable self-evaluation | LLM judges near chance | Use LLMs for pairwise pre-sorting and checklists only; humans make cuts |
| Trend chasing | Attention mistaken for demand | Require sustained, multi-source growth; tag public lists as crowded |

## Proposed funnel

The funnel has five stages. Stages 1 and 2 run unattended each week; stages 3 to 5 run
on the problems a human promotes.

| Stage | Input | Output | Machine does | Human steering |
|---|---|---|---|---|
| **1. Harvest** | Raw items from collectors | Signal rows: text, source, author hash, timestamp, link | Normalize, dedup, filter spam | Choose sources; mute noisy ones |
| **2. Problem mapping** | New Signals | Problem clusters with JTBD phrasing, counts, trend | Extract pain statements (job, outcome, workaround, spend cue); embed; assign to existing Problems or propose new ones; compute weekly metrics | Merge, split, rename clusters; star or archive — light, weekly |
| **3. Problem + segment** | A promoted Problem | 1–3 Segment pairings, each with an opportunity score and "why now" note | Split the problem's Signals by who complains; estimate importance and dissatisfaction proxies; attach trends | **Highest value.** Pick the segment, weigh founder fit, apply Graham's depth test |
| **4. Idea generation** | Problem + Segment | 10–30 diverse candidate Ideas, deduped | Generate from several personas, patterns, and models; dedup against history; attach assumptions and kill conditions | Shortlist 2–3; rate novelty (machines fail here) |
| **5. Validation brief** | A shortlisted Idea | Lean Canvas, riskiest assumptions, Mom Test questions, competitor and graveyard list | Draft canvas and questions; search for existing and dead competitors | Run conversations; log outcomes as Evidence; kill or advance |

Human steering matters most at stage 3. Shane and Baron show that opportunity depends
on who sees it, and the LLM evidence shows models fail at judging. Choosing which
person to serve is the cheapest, highest-leverage human decision in the system.
Stage 4's novelty rating comes second.

## Data model sketch

The model keeps raw evidence immutable and stores weekly snapshots, so each run
recomputes metrics without losing history.

```
Signal         id, source, source_url, author_hash, posted_at, collected_at,
               run_id, text, kind (complaint|request|workaround|trend|launch|...)
Extraction     id, signal_id, job, outcome, current_workaround, spend_cue,
               intensity (1-5), segment_hint, model, prompt_version
Problem        id, title (job + outcome, solution-free), description,
               parent_id (tree), status (new|watching|promoted|archived|merged),
               merged_into_id, created_run_id
ProblemSignal  problem_id, extraction_id, similarity, assigned_by (model|human)
Segment        id, name, description (role, context, size hint)
ProblemSegment problem_id, segment_id, importance_proxy, dissatisfaction_proxy,
               opportunity_score, founder_fit (human), why_now, status
Trend          id, name, source, series (JSON of weekly values), direction
ProblemTrend   problem_id, trend_id, relation_note
Idea           id, problem_segment_id, title, pitch, pattern (unbundle|vertical|...),
               generator (model + persona), embedding, assumptions (JSON),
               kill_condition, status (candidate|shortlisted|validating|killed|advanced)
Evidence       id, target_type (problem|segment|idea), target_id, stance (for|against),
               kind (signal|interview|competitor|failed_attempt|trend),
               ref (signal_id or URL), note, added_by, added_at
Snapshot       run_id, problem_id, signal_count, distinct_authors, source_count,
               intensity_mean, growth_4w, score, rank
Run            id, started_at, collectors_ok, model_versions, notes
Decision       id, target_type, target_id, action (promote|merge|kill|...), reason,
               decided_at
```

Three choices make weekly re-runs work. Snapshot rows per run and problem let the app
chart each problem's rise and fall and compute growth over trailing weeks. Problems
change by merge and split, never by deletion, so history stays traceable. Decision rows
record each human judgment with its reason, so later runs can respect it and the system
can learn from past cuts. Embeddings for Signals and Ideas live alongside, for
clustering and for deduplicating new ideas against every idea ever generated.

## Implications for our design

1. **Make the Problem the core entity.** Ideas exist only as children of a
   Problem + Segment, which blocks solutions looking for problems by construction.
2. **Spend automation on breadth, humans on judgment.** LLMs extract and cluster well
   and judge poorly. Weekly human steering should be short and focused on stage 3.
3. **Phrase every problem as a job and outcome, free of solution words.** Score with an
   ODI-style formula over proxies, and label it a heuristic in the UI.
4. **Count distinct people, not posts.** Weight past-behavior signals (workarounds,
   spend, hours lost) above wishes, following the Mom Test.
5. **Treat trends as annotations.** They explain "why now" but never create a
   problem alone; require multi-week, multi-source growth.
6. **Engineer diversity in.** Seed generation with concrete Signals, rotate personas and
   patterns, use more than one model, and deduplicate against all history.
7. **Ground every claim in Evidence rows,** including evidence against and failed
   predecessors. Never let an LLM assert demand.
8. **Encode Edgar's background as a founder profile** and score fit, since opportunity
   is relative to the person who sees it.
9. **End the funnel at a validation brief, not an idea.** Falsifiable assumptions, kill
   conditions, and Mom Test questions turn output into the hypothesis testing that the
   strongest evidence here supports.
10. **Version prompts and models in every row** so changes in rankings can be traced to
    the world rather than to the pipeline.
