# Scoring problems and validating ideas from desk research

Stage 0 research, 2026-10-13. Scope: how to judge a problem statement, how to score
problems on market merit (founder fit excluded), and how to turn a chosen idea into an
evidence dossier and a real-world test plan.

## Summary

A good problem statement names a person, a situation, the workaround they use today, and
what the problem costs them. Practitioner scoring frameworks converge on a short list of
criteria: pain intensity, frequency, willingness to pay, segment size, how underserved the
segment is, timing, reachability, and risk. Desk research can support most of these scores
only weakly, because it observes what people *say* online rather than what they *do* with
money. The generator should therefore score with explicit evidence levels, cap scores that
lack behavioral evidence, rank finalists by pairwise comparison, and hand the user a test
plan whose pass and kill thresholds are fixed before any test runs.

---

## Part A — Problem statements

### What a good statement contains

A problem statement earns its keep when it can be wrong. Four elements make it falsifiable:

1. **A specific person.** A role plus a context narrow enough to find twenty of them
   ("solo bookkeepers serving 10–40 small-business clients"), never "SMBs" or "creators".
2. **A situation.** The moment the problem bites: a trigger, a frequency, a place.
3. **The current workaround.** What they do today: a spreadsheet, a hire, a tool they
   complain about, or nothing. Steve Blank's earlyvangelist test treats a home-built
   workaround as the strongest sign of pain: the person has the problem, knows it, is
   looking for a fix, has cobbled one together, and has or can get budget
   ([High Tech in the Hub on Blank](https://hightechinthehub.com/2010/11/the-most-important-customer-you-will-ever-know/)).
4. **The consequence.** What the problem costs in hours, money, risk, or missed revenue.
   A consequence without a unit is a mood.

Paul Graham adds the selection rule behind these elements: early on, prefer something a
small number of people want a large amount over something many people want a little
([How to Get Startup Ideas](https://paulgraham.com/startupideas.html)). A narrow, specific
statement points at that small, intense group.

### Templates practitioners use

| Template | Form | Source |
|---|---|---|
| JTBD job statement | verb + object + contextual clarifier; no adjectives such as "quick" or "easy" in the main job | Kalbach, *The Jobs to Be Done Playbook* ([UXmatters review](https://uxmatters.com/mt/archives/2020/07/book-review-the-jobs-to-be-done-playbook.php)) |
| Desired outcome statement | direction + unit of measure + object + clarifier, e.g. "minimize the time it takes to locate a file during a patient consultation" | Ulwick/Bettencourt ODI ([Salesforce Trailhead](https://trailhead.salesforce.com/content/learn/modules/jobs-to-be-done-framework-for-designers/craft-job-statements)) |
| Point-of-view statement | [user] needs to [need] because [insight] | Stanford d.school ([CS147 Define lecture](https://hci.stanford.edu/courses/cs147/2024/au/lectures/03-define.pdf)) |
| Opportunity (Torres) | a customer need, pain point, or desire, phrased from the customer's side, that would move a business outcome if addressed | Torres, opportunity solution tree ([Product Talk](https://www.producttalk.org/glossary-discovery-opportunity-solution-tree/)) |
| Hypothesis | "At least X% of Y will Z" | Savoia, *The Right It* ([Product Compass](https://www.productcompass.pm/p/how-to-build-the-right-product-with)) |

The templates divide the work. The job statement and desired outcome describe *what* the
person is trying to get done and how they measure success; the POV statement and Torres
opportunity capture *why* it hurts; Savoia's XYZ form turns the claim into a number a test
can refute. Our generator needs all three layers: a job, a pain with a consequence, and a
testable hypothesis.

A practical composite for the generator:

> **[Person]** in **[situation]** struggles to **[job]** because **[root cause]**. Today
> they **[workaround]**, which costs them **[consequence with unit]**.
> Hypothesis: at least **X%** of **[reachable list of Y]** will **[costly action Z]**.

### Anti-patterns

- **Solution in disguise.** "Users need an AI dashboard for invoices." If only one
  solution could satisfy the statement, it is a solution. Torres's school tests this by
  asking whether more than one distinct solution could address the opportunity
  ([LogRocket on OST anti-patterns](https://blog.logrocket.com/product-management/opportunity-solution-trees-a-list-of-anti-patterns-to-avoid)).
  Kevin Hale calls the upstream error a solution in search of a problem
  ([YC, How to Evaluate Startup Ideas](https://www.ycombinator.com/blog/startup-school-podcast-preview-with-kevin-hale)).
- **Vague segment.** "Small businesses", "Gen Z", "developers". The test: can you name a
  place where 100 of them gather, or a list you could buy?
- **Unfalsifiable claim.** "People want better tools for X." No observation could refute
  it. Fix with the XYZ form.
- **Missing workaround.** If nobody does anything about the problem today, the pain is
  probably mild. "Nothing" is a valid answer but a warning sign.
- **Consequence without a unit.** "It's frustrating." Ask: frustrating enough to spend
  what?
- **Business goal posing as a customer problem.** "We need more conversions." Torres
  recommends rewriting such goals from the customer's side
  ([Product Talk](https://www.producttalk.org/benefits-of-opportunity-solution-trees/)).

---

## Part B — Scoring rubrics

### What existing frameworks measure

| Framework | What it scores | Use for us |
|---|---|---|
| Hale's problem criteria | popular, growing, urgent, expensive, mandatory, frequent ([YC](https://www.ycombinator.com/blog/startup-school-podcast-preview-with-kevin-hale)) | Near-complete checklist for problem quality |
| Painkiller vs vitamin / hair on fire | urgency: would they run toward any fix? A popular shorthand, not tied to one author | One anchor of the pain criterion |
| Ulwick opportunity score | Importance + max(Importance − Satisfaction, 0); ≥10 marks underserved ([Strategyn](https://strategyn.com/quantify-your-customers-unmet-needs), [CustomerThink](https://customerthink.com/what-unmet-needs-should-be-targeted-for-growth/)) | Model for "underserved": importance counts double, satisfaction subtracts |
| Rob Walling's 5 P's | problem, purchaser, pricing model, market, product-founder fit ([Startups for the Rest of Us, ep. 628](https://www.startupsfortherestofus.com/episodes/episode-628-the-5-pm-pre-validation-framework)) | Adds "purchaser": who signs the cheque. Drop founder fit |
| Sequoia business plan | problem, solution, *why now*, market size (TAM/SAM/SOM), competition ([Sequoia template reproduction](https://www.alexanderjarvis.com/sequoia-capital-business-plan-template/)) | Source of the timing criterion |
| Bottom-up sizing | number of reachable buyers × annual price ([Visible](https://visible.vc/blog/bottom-up-market-sizing)) | Preferred over top-down analyst reports |
| Blank's earlyvangelist | has problem, knows it, looking, built workaround, has budget | Evidence of intensity and willingness to pay |

The frameworks agree on intensity, frequency, and money; they differ on whether market
size or underservedness matters more. Graham's argument favors underservedness early: a
deep, narrow well beats a wide, shallow pond. Our rubric therefore treats size as one
criterion among eight, not a multiplier.

Ulwick's formula only works with survey data from the segment, which desk research lacks.
Its logic still transfers: score importance (pain) and current satisfaction (how well
existing tools serve them) separately, and weight importance higher.

### Desk evidence is weak evidence

David Bland and Alex Osterwalder's evidence scale puts what people *say* at the bottom
and what they *do*, especially with money, at the top; more interviews never climb the
scale, because none of them asked anyone to commit
([Strategyzer, Testing Business Ideas](https://www.strategyzer.com/library/testing-business-ideas-book-summary),
[Pereira on the evidence scale](https://dpereira.substack.com/p/beyond-the-framework-six-years-of)).
Forum complaints, search volume, and reviews are mostly *say* data. Some desk signals do
reach the *do* level: paid competitors with real revenue, job postings for people who do
the workaround by hand, consultants billing for it, Upwork gigs, and price-tier pages.
The rubric must label each evidence item by level, so the scores show how much they rest
on talk.

**Evidence levels used below:**

| Level | Meaning | Desk examples |
|---|---|---|
| E1 — opinion | Stated preference, generic | Upvotes, "someone should build X" posts, survey hype |
| E2 — specific talk | A named, specific past incident with a cost | Detailed forum or review complaint describing what happened and what it cost |
| E3 — observed spend | Money or time already being spent on the problem | Competitor pricing with visible customers, job ads, freelancer gigs, paid templates, consultants |
| E4 — commitment to *us* | Action toward our offer | Pre-orders, LOIs, deposits — only from real-world tests |

Desk research tops out at E3. E4 comes only from Part C's tests.

### Proposed rubric

Eight criteria, each scored 1–5. Every score cites evidence IDs from the dossier and
carries a confidence: **High** (two or more independent E3 sources), **Medium** (one E3
or several consistent E2), **Low** (E1 only, or inference). A score of 4 or 5 requires
at least Medium confidence; a criterion with no evidence scores 2 and reads Low.

| # | Criterion | 1 | 3 | 5 | Evidence that supports it |
|---|---|---|---|---|---|
| 1 | **Pain intensity** (urgent, mandatory) | Mild annoyance; people shrug | Real cost, tolerated; solved "when there's time" | Blocks revenue, compliance, or safety; people act within days | Complaint language and stated costs (E2); compliance deadlines; earlyvangelist signs |
| 2 | **Frequency** | Once a year or less | Monthly | Daily or every transaction | Workflow descriptions, review text, job-ad task lists |
| 3 | **Willingness to pay / existing spend** | No one pays anything today | Some pay for adjacent tools or DIY time | Segment already pays ≥ the target price for a poor solution or labor | Competitor revenue/pricing, freelancer rates, job ads, budget line items (E3) |
| 4 | **Underserved** (Ulwick logic) | Strong, well-reviewed incumbents; complaints trivial | Incumbents exist; recurring complaints about a specific gap | Workaround is spreadsheets or manual labor, or incumbents score low on the exact job | Review mining (G2, Capterra, app stores): share of reviews naming the gap; absence of products |
| 5 | **Segment size** (bottom-up) | < 1,000 reachable buyers or < $1M serviceable revenue | ~10k buyers or ~$10–50M | ≥ 100k buyers or ≥ $100M, counted bottom-up | Census or registry counts, association memberships, LinkedIn counts × price benchmark |
| 6 | **Reachability** | No known channel; buyers invisible | Reachable through paid ads or a few communities | Concentrated in named communities, lists, marketplaces, or events | Named subreddits, associations, directories, newsletter sizes |
| 7 | **Why now / growth** | Static or shrinking; nothing changed | Moderate tailwind | A dated change (regulation, platform shift, cost collapse) created or enlarged the problem in the last ~3 years | Dated regulations, trend data, platform announcements |
| 8 | **Risk** (inverted: 5 = low risk) | Licensed activity, heavy regulation, or single-platform dependency | Manageable compliance or one notable dependency | No special regulation; no gatekeeper | Regulatory texts, platform ToS, liability precedents |

**Aggregation.** Use gates, then a weighted sum.

- *Gates:* Pain ≥ 3 and Willingness to pay ≥ 3, each at Medium confidence or better.
  An idea that fails a gate stays visible but drops from the ranked list.
- *Weights:* Pain 20%, Willingness to pay 20%, Underserved 15%, Frequency 10%,
  Reachability 10%, Why now 10%, Size 10%, Risk 5%. The weights encode Graham's "deep
  well" view and Walling's money-first view; they are a starting guess to revise.
- *Report:* total score, the weakest criterion, and an overall confidence equal to the
  lowest confidence among the gated criteria.

### Keeping LLM scores calibrated

LLM judges carry known biases. Zheng et al. found position bias (GPT-4 gave consistent
pairwise verdicts under swapped order only about 65% of the time), verbosity bias, and
self-preference ([MT-Bench paper](https://arxiv.org/pdf/2306.05685)). Verbalized
confidence runs inflated: models state high confidence on wrong answers
([Leng et al., ICLR 2025](https://proceedings.iclr.cc/paper_files/paper/2025/file/29fb6e1456b3d8b57ede5c45aa2c6537-Paper-Conference.pdf)).
Seven practices counter these:

1. **Separate evidence from judgment.** One pass extracts evidence items (quote, URL,
   date, evidence level) without scoring. A second pass scores only from that list. The
   scorer never browses.
2. **Require citations per score.** Each score lists evidence IDs and one sentence of
   reasoning. A validator rejects any score above 2 that cites nothing, and any 4–5
   without E3 evidence.
3. **Anchor the scale.** Give each level a written description and, where possible, a
   worked example. Rubric anchors improve consistency of numeric mapping
   ([Wiegreffe et al.](https://arxiv.org/html/2305.14770v6)). Keep the scale coarse
   (1–5, not 1–10).
4. **Derive confidence from evidence, not from the model.** Confidence follows the
   counting rule above. Never ask the model how sure it is.
5. **Rank finalists pairwise.** Absolute scores filter; pairwise comparison ranks.
   Pairwise LLM evaluation aligns better with human judgment than direct scoring
   ([Liu et al., PairS](https://arxiv.org/html/2403.16950v4)). Run each pair in both
   orders and count a win only when it holds both ways.
6. **Use a jury.** A panel of smaller models from different families matched human
   judgment better than one large judge and showed less self-preference
   ([Verga et al., PoLL](https://arxiv.org/abs/2404.18796v2)). Report the spread: when
   judges disagree by two or more points on a criterion, flag it for the user instead of
   averaging it away.
7. **Check stability and keep a reference set.** Score each idea several times and log
   variance; a stable judge can still be wrong, so also keep a small set of hand-scored
   problems and re-check the pipeline against them after any prompt change.

---

## Part C — Desk validation and test planning

### The evidence dossier

The dossier turns a chosen idea into claims with sources, so the user can see what is
known, what is assumed, and what the tests must settle. It should contain:

1. **Problem statement** in the composite template, plus the XYZ hypothesis.
2. **Demand evidence.** Quoted complaints with links, dates, and evidence level; search
   trends; community size. Count independent sources, not posts.
3. **Workarounds and existing spend.** What people do now and what it costs: tools,
   hires, freelancer rates, job ads.
4. **Competitors.** Direct, indirect, and the DIY option. For each: pricing, positioning,
   signs of traction, and a review-mining summary — top complaints, their share of
   negative reviews, and representative quotes.
5. **Pricing benchmarks.** Price points of competitors and substitutes; a proposed test
   price with justification.
6. **Segment size.** Bottom-up: count source × price, with each input cited; a top-down
   cross-check where available.
7. **Reachability.** Named channels with sizes, and the cheapest way to reach 100 people
   from the segment.
8. **Why now.** Dated changes with sources.
9. **Risks.** Regulatory, platform, liability, and incumbent-response risks.
10. **Scorecard.** The rubric with evidence IDs, confidences, and judge disagreements.
11. **Assumption map.** The riskiest assumptions, ordered by how fatal they are if false
    and how little evidence supports them. These drive the test plan.
12. **Kill criteria.** Written now, before any test (see below).

### Real-world tests

Desk evidence earns an idea the right to be tested; only tests reach E4. Each test follows
the Strategyzer test card — hypothesis, test, metric, and the threshold that decides it
([Strategyzer](https://strategyzer.com/library/validate-your-ideas-with-the-test-card)) —
and Savoia's advice to run cheap pretotypes in days, not months.

**Customer interviews (The Mom Test).** Talk about their life, not the idea; ask about
specific past events, not hypotheticals; listen more than you talk. Treat compliments and
future promises as noise. Count only commitments of time, reputation, or money: a next
meeting, an introduction to a decision-maker, a pre-order or deposit
([mtlynch summary](https://mtlynch.io/book-reports/the-mom-test/)). Recruit from the
dossier's reachability channels.

**Smoke test / fake door.** A landing page or ad that describes the offer and asks for an
action. No accepted benchmark exists; practitioner guides treat under ~2%
visitor-to-signup as noise and cite 5–10% or more as good, while ranking bare "notify me"
signups as weak evidence next to signups with qualifying questions or card capture
([Causo guide](https://hub.causo.ai/guides/fake-door-smoke-testing-validate-demand-2026)).
Fix the threshold and sample size before launch.

**Concierge MVP.** Deliver the outcome by hand to a few customers who know a person is
doing it; Food on the Table sold its service for $10 a month in person before writing
software ([OpenClassrooms](https://openclassrooms.com/en/courses/4544561-learn-about-lean-startup/4703206-discover-the-4-types-of-minimum-viable-product)).
It tests whether people pay and keep paying, and it teaches the workflow. The concierge's
charm can inflate results.

**Pre-sales.** Ask for money before building: a deposit, a paid pilot, or an LOI with a
price. Walling's school treats proof of payment, not interest, as validation
([MicroConf](https://microconf-on-air.castos.com/episodes/microconf-tactics-validate-your-saas-idea-fast-step-by-step-saas-validation-process)).

**Test-plan template.** One row per riskiest assumption:

| Field | Content |
|---|---|
| Assumption | From the assumption map |
| Hypothesis (XYZ) | At least X% of Y will Z |
| Test | Interview / smoke / concierge / pre-sale |
| Sample | Who, how many, from which channel |
| Metric | The single number that decides it |
| Pass | Threshold set in advance |
| Kill | Threshold set in advance |
| Ambiguous zone | What happens between pass and kill (one retest, then decide) |
| Budget and date | Money and time cap; decision date |
| Owner | Who reviews the result |

**Default thresholds** (starting points to tune per idea, not industry standards):

| Test | Sample | Pass | Kill |
|---|---|---|---|
| Problem interviews | 10–15 from segment | ≥ 60% describe a specific recent incident; ≥ 40% have a workaround; ≥ 3 commit to a follow-up or intro | < 30% recall a specific incident, or zero commitments |
| Smoke test | ≥ 300 targeted visitors | ≥ 5% signup with a qualifying question | < 2% |
| Price test | Same page with price shown | ≥ 1% click "buy" or enter card | No buy intent at any tested price |
| Concierge | 3–5 customers | ≥ 3 pay; ≥ 2 renew or ask for more | None pays after a second month |
| Pre-sale / LOI | 20 qualified prospects asked | ≥ 3 deposits or signed LOIs at target price | Zero after 20 asks |

### Kill criteria in practice

Annie Duke's *Quit* recommends writing kill criteria at the start, when emotion and sunk
cost hold no sway, and stating each as a **state plus a date**: the measurable condition
and the day you check it ([Coaching for Leaders](https://coachingforleaders.com/podcast/quit-bad-stuff-faster-annie-duke/)).
She also suggests a "quitting coach" who holds you to them. Applied here:

- Write kill criteria into the dossier before the first test, one per riskiest assumption.
- Phrase each as state + date: "If fewer than 3 of 20 asked prospects place a deposit by
  2026-12-15, drop the idea."
- Kill on the gated criteria first: no specific incidents (pain) or no payment
  (willingness to pay) ends the idea; weak reachability or size triggers a narrower
  segment, not a pivot.
- Allow one retest in the ambiguous zone, then decide.
- Record the outcome in a learning card, so dropped ideas and their reasons feed back into
  the generator's scoring.

---

## Implications for our design

1. **Make the problem statement a structured record**, not prose: person, situation, job,
   root cause, workaround, consequence (with unit), XYZ hypothesis. Validate each field;
   reject statements that fail the anti-pattern checks (one-solution test, unnamed
   segment, unitless consequence).
2. **Store evidence as typed items** with URL, quote, date, segment, and level E1–E4.
   Scores reference item IDs. This makes scores auditable and lets confidence be computed.
3. **Score in two stages:** absolute rubric to filter, then pairwise jury ranking with
   order swapping for the shortlist the user steers.
4. **Surface uncertainty:** show confidence per criterion, judge
   disagreement, and the weakest criterion beside the total.
5. **Emit the dossier and test plan together**, so every low-confidence score maps to a
   test with a pre-set kill threshold.

### Draft dossier outline

1. Problem statement (structured) and XYZ hypothesis
2. Scorecard: eight criteria, score, confidence, evidence IDs, judge spread
3. Demand evidence (by level)
4. Workarounds and existing spend
5. Competitors and review-mining summary
6. Pricing benchmarks and proposed test price
7. Segment size, bottom-up with cited inputs
8. Reachability: channels, sizes, cost to reach 100
9. Why now: dated changes
10. Risks
11. Assumption map, ranked by fatality × uncertainty
12. Test plan (one row per assumption) with pass, kill, and dates
13. Kill criteria (state + date) and decision owner
14. Evidence appendix: every item with URL, quote, date, level

### Draft rubric

| Criterion | Weight | Gate | 1 | 3 | 5 |
|---|---|---|---|---|---|
| Pain intensity | 20% | ≥ 3, Medium+ | Shrug | Costly, tolerated | Blocks revenue/compliance |
| Willingness to pay | 20% | ≥ 3, Medium+ | Nobody pays | Adjacent spend | Pays ≥ target today |
| Underserved | 15% | — | Strong incumbents | Recurring named gap | Manual workaround or poor incumbents |
| Frequency | 10% | — | Yearly | Monthly | Daily |
| Reachability | 10% | — | Invisible | Paid ads | Named communities and lists |
| Why now | 10% | — | Static | Tailwind | Dated change in last ~3 years |
| Segment size | 10% | — | < 1k buyers | ~10k | ≥ 100k (bottom-up) |
| Risk (inverted) | 5% | — | Licensed / single platform | One dependency | None |

Confidence: High = two or more independent E3 items; Medium = one E3 or several
consistent E2; Low = E1 or inference. Scores of 4–5 need Medium or better; uncited
criteria score 2, Low.
