# Substr8 — What Each Productization Gap Actually Means

A plain-language reference so you can defend every gap one layer deeper than
the slide. For each item: what it is, why a real product needs it, what
Substr8 does instead today, and the one-sentence honest version to say out
loud if asked.

The gaps fall into two piles. Pile one is ordinary product-hardening — real
but unglamorous work any competent team can do. Pile two is the genuinely
unsolved core — the actual research question. Keep that distinction in your
head; it's the whole framing.

---

# PILE ONE — Ordinary hardening (real work, but not the interesting risk)

## 1. Authentication and authorization (no "auth")

**What it is.** Two related things often shortened to "auth."
*Authentication* = proving you are who you say you are (logging in).
*Authorization* = what you're allowed to do once you're in (permissions /
roles). A real system knows that Jordan is Jordan (authentication) and that
Jordan, as a Client Ops Lead, can approve mappings but a vendor engineer
cannot (authorization).

**Why a product needs it.** In a real telco, who approved what is a
compliance and accountability fact. If anyone can click "Approve" and the
system has no idea who they really are, the entire governance story
collapses — an audit trail that says "approved by [whoever was at the
keyboard]" is worthless to a regulator.

**What Substr8 does instead.** There is no login at all. The "reviewer"
and "acting as" concepts are illustrative — the app doesn't actually verify
identity. We deliberately did NOT fake a login system, because a fake one
would be worse than an honest absence.

**Say-it-out-loud version.** "There's no real authentication — no login, no
verified identity behind an approval. In production, every governance action
has to be tied to a verified user with the right role, and that's
non-negotiable for a regulated operator. We left it out deliberately rather
than fake it."

---

## 2. A database (it runs on local files)

**What it is.** Right now Substr8 stores everything in plain files on a
laptop — JSON and YAML files in folders. A *database* is purpose-built
software (Postgres, SQL Server, etc.) for storing data that many people and
processes read and write at once, reliably, with guarantees that two people
editing the same thing at the same time don't corrupt it, and that a crash
mid-write doesn't leave you with half-saved garbage.

**Why a product needs it.** Files-on-a-laptop works for one person clicking
through a demo. It falls apart the moment you have multiple users, multiple
simultaneous edits, or any requirement that data survive a crash or be
backed up, queried, or reported on at scale. The append-only audit log being
"a .jsonl file" is fine for a prototype and unacceptable for a system of
record.

**What Substr8 does instead.** Reads and writes local files
(`audit_log.jsonl`, `proposed_mapping.yaml`, etc.). Single user, single
machine, no concurrency protection.

**Say-it-out-loud version.** "It's file-based, not database-backed. That's
fine for a single-user prototype but a real system of record needs a proper
database — for concurrency, durability, backup, and the ability to actually
query the audit history at scale."

---

## 3. Concurrency (two people at once)

**What it is.** *Concurrency* = more than one person (or process) doing
things at the same time. The classic problem: two reviewers open the same
mapping, both edit it, both save — whose change wins, and did one silently
erase the other's? Real systems have to handle this deliberately (locking,
versioning, conflict detection).

**Why a product needs it.** A Tier 1 integration team is 6–10 people working
in parallel. If the system can't safely handle two of them touching the same
thing at once, it corrupts data or loses work.

**What Substr8 does instead.** Assumes one person at a time. The assignment
"lock" we built is a visible workflow nicety, not a real concurrency control
— it doesn't actually prevent two processes from colliding.

**Say-it-out-loud version.** "It assumes a single user. Real multi-reviewer
use needs genuine concurrency handling so two people editing the same mapping
don't clobber each other — what we built is a workflow lock, not a true
technical one."

---

## 4. Real connectors / integrations (the data is synthetic)

**What it is.** A *connector* is the actual working code that talks to a real
external system — pulls real alarms from a real TMF642 source, creates a real
incident in a real ServiceNow instance, reserves real inventory in Oracle
UIM. It handles that system's authentication, its specific API quirks, its
errors, its rate limits, its version changes.

**Why a product needs it.** Obviously — without it, nothing real happens. And
notably: building and maintaining these connectors against one operator's
specific environment is *exactly the expensive bespoke labor your whole
thesis is about*. So you can't hand-wave it; it's the heart of the problem,
not a detail.

**What Substr8 does instead.** Everything is synthetic and mocked. No live
TMF642 feed, no real ServiceNow, no real UIM. The dropdowns showing Jira,
ASAP, etc. are deliberately inert.

**Say-it-out-loud version.** "All the data is synthetic — there are no live
connectors. And I'd flag that building real connectors is itself the
expensive bespoke work the thesis is about, so I'm not pretending it's
trivial. The prototype proves the discovery-and-governance mechanism, not the
integration plumbing."

---

## 5. Monitoring and observability

**What it is.** *Monitoring/observability* = the system's ability to tell you
how it's doing while it runs — is it up, is it slow, is it erroring, how
often, where? In production you need dashboards and alerts so you know
something broke before your users do.

**Why a product needs it.** A system in a Tier 1 NOC that silently fails is
a disaster. You need to know latency, error rates, API costs, and failures
in real time.

**What Substr8 does instead.** Nothing. Errors print to a terminal or show
on a card. No metrics, no alerting, no logging infrastructure.

**Say-it-out-loud version.** "There's no monitoring or observability — no
metrics, no alerting. Standard production work, just not built."

---

## 6. Scale / load (it's never been tested under volume)

**What it is.** *Scale* = does it still work when the numbers get big? A real
operator might have millions of alarms a day and thousands of mappings.
*Load testing* = deliberately throwing large volumes at the system to see
where it breaks.

**Why a product needs it.** A thing that works on 10 alarms may fall over at
10,000. You don't know until you test. (This connects to the alarm-storm
discussion — high volume is exactly where naive designs break.)

**What Substr8 does instead.** Tested on a handful of synthetic cases. Never
load-tested. We even saw a small foretaste of this: the Claude engine
truncated its response on the *largest* evidence case because the token
budget wasn't sized for it.

**Say-it-out-loud version.** "It's never been tested at scale — a handful of
synthetic cases, not Tier 1 volumes. And we already saw a hint of why that
matters: the model truncated on the largest evidence set, which is exactly
the kind of volume-sensitive failure you only find by testing for it."

---

# PILE TWO — The genuinely unsolved core (the actual research question)

## 7. Measured accuracy and confidence calibration ("n=2", evaluation)

**What it is — start with "n".** "n" is just the number of times you tried
something. n=1 means you tested it once. n=2, twice. In any kind of
evaluation, a result from n=1 or n=2 is an anecdote, not evidence — it might
be a fluke. To actually *trust* a result, you need a large n: dozens or
hundreds of cases, so you can see the pattern rather than a coincidence.

**What "calibration" means.** A confidence score is *calibrated* if it means
what it says. If the engine says "0.8 confidence" on a hundred mappings, then
roughly 80 of them should actually turn out correct. If it says 0.8 but is
only right half the time, the number is *miscalibrated* — it's lying, and a
governance system that trusts it is being misled. You only find out by
checking predictions against known-correct answers across many cases.

**What "evaluation" / "held-out" means.** *Evaluation* = systematically
measuring how well the engine performs against cases where you already know
the right answer. *Held-out* means you set aside some known-answer cases that
the engine never saw during design, then test on those — so you're measuring
real performance, not the engine regurgitating something it was tuned on.

**Why a product needs it.** This is the whole ballgame for the discovery
engine. The entire thesis is "AI can discover the mapping." The only way to
claim that responsibly is to measure how often it's right, and whether its
confidence scores can be trusted, across a real, large set of cases. Without
that, "the AI discovered it" is a hope, not a finding.

**What Substr8 does instead.** Tested 3 mapping cases, each a small number of
times (n=2–3). That's enough to *observe interesting behavior* — the
confidence divergence, the injection resistance — but nowhere near enough to
*claim accuracy or calibration*. The idiosyncrasies register is honest about
this throughout.

**Say-it-out-loud version.** "I have no measured accuracy yet. I've run three
cases two or three times each — that's enough to observe behavior, not to
claim the engine is reliable or that its confidence scores are calibrated.
'Calibrated' means an 0.8 should actually be right about 80% of the time, and
proving that needs a real evaluation across hundreds of known-answer cases.
That evaluation is the genuinely unsolved part, and I'd rather say that
plainly than overclaim from a sample of three."

---

## 8. Guardrail robustness under adversarial testing

**What it is.** *Adversarial testing* = deliberately attacking your own
system to see if its defenses hold — like the prompt-injection probe, where
we hid a malicious instruction inside ticket data to see if the model would
obey it. "Robustness" = does the defense hold up across *many varied
attacks*, not just the one you tried.

**Why a product needs it.** A guardrail that held once might fail against a
phrasing you didn't try. Until you've attacked it many ways — ideally with
someone *other* than the person who wrote the defense designing the attacks —
you can only say "it held on the cases we tried," not "it's robust."

**What Substr8 does instead.** One injection phrasing, tested twice, held
both times — and the second time the model even named the attack. Genuinely
encouraging, but n=2 on a single phrasing. The register explicitly lists
"try subtler phrasings" and "third-party adversarial test" as open.

**Say-it-out-loud version.** "The injection guardrail held on the one attack
I tried, twice — encouraging, but that's not a robustness claim. Real
assurance needs many attack phrasings, ideally designed by someone other than
me, before I'd call it robust rather than 'held on what I tested.'"

---

## 9. The runtime executor (deliberately out of scope)

**What it is.** Everything built so far is *build-time*: discovering and
approving the mapping. The *runtime executor* is the other half — the live
system that takes an approved mapping and actually runs it against the real
alarm stream, doing correlation, deduplication, and alarm-storm handling in
real time.

**Why it matters.** It's where the hardest live-operation problems live (the
alarm storm, the latency budget, the safety of suppressing alarms). We scoped
it out on purpose so Phase 1 could prove the governance lifecycle first.

**What Substr8 does instead.** Nothing at runtime. There is no live executor;
the storm scenario we discussed early on is not built.

**Say-it-out-loud version.** "There's no runtime executor — the live side
that runs an approved mapping against a real alarm stream, with correlation
and storm handling. That was a deliberate scope choice: prove the governed
discovery lifecycle first, build the runtime second."

---

## 10. Security review, data residency, privacy

**What it is.** *Security review* = a real assessment of how the system could
be attacked or leak data. *Data residency* = the requirement that an
operator's sensitive data physically stays within their environment/country
and never leaves to a third party. *Privacy controls* = handling of
customer-identifying data in alarms and tickets.

**Why a product needs it.** A Tier 1 will not send its real ticket history
and network topology to an outside API. This is the legitimate, hard
objection — and the honest answer (deploy the model inside the operator's own
environment, e.g. via Bedrock/Vertex in their VPC) is currently a *plan on a
slide*, not built or reviewed.

**What Substr8 does instead.** None of it. Synthetic data sidesteps the issue
entirely for now, which is fine for a prototype but is exactly the thing a
real deployment has to solve first.

**Say-it-out-loud version.** "No security review, no data-residency story in
code. The deployment-in-the-operator's-own-environment answer is real and
right, but right now it's a design direction, not something I've built or had
reviewed. For synthetic data it doesn't bite; for real operator data it's the
first thing you'd have to solve."

---

# The one framing sentence that ties it together

"Two kinds of gaps. Most of this list is ordinary product hardening — auth, a
database, real connectors, monitoring — real work, but nobody's worried it
can't be done. The smaller pile is the genuinely unsolved part: can the
discovery engine's accuracy and confidence actually be measured and trusted,
and are the governance guardrails robust under real adversarial pressure?
That second pile is the real research question, and the honest state is that
I've started probing it rigorously and documented exactly what I found,
rather than claiming it's solved."
