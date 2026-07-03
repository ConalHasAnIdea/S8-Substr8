# Codex Prompt — Substr8: Wire GPT-5.5 Into the UI as a Third Engine

Add OpenAI (GPT-5.5) as a third selectable discovery engine in the UI,
mirroring exactly how the Claude engine is already wired. The mock stays the
default and primary engine; Claude and now GPT-5.5 are additive comparison
engines. Do not change the mock or the Claude integration — replicate the
Claude pattern for OpenAI alongside it.

Reuse the already-built `openai_discovery_engine.py` (drop into discovery/).
It already implements `propose_one()` with the same interface as
`claude_discovery_engine.py`, including markdown fence stripping, citation
validation by substring containment, null-confidence status override, and
graceful error handling. Do not rewrite it.

## Critical safety/cost constraints (identical to the Claude integration)

- The OpenAI API key must be read ONLY from the environment variable
  OPENAI_API_KEY. Never hardcode it, never write it to any file under data/
  or output/, never render it in any template or log line, never echo it in
  an error message (an auth error shows "authentication failed — check
  OPENAI_API_KEY" without the key value).
- GPT-5.5 calls cost real money and have real latency. Show a loading state
  while a call runs; handle and clearly display failure.
- Do NOT auto-run GPT-5.5 for every mapping or in a loop. Each run is a
  deliberate per-mapping user action (a "Run with GPT-5.5" button per
  mapping). No background polling, no bulk "run all."

## What to build

### 1. Engine availability
In the Discovery Engine dropdown (and wherever the Claude engine option is
surfaced), add "GPT-5.5" (or "OpenAI GPT-5.5"). It becomes selectable ONLY
when OPENAI_API_KEY is detected in the environment at app startup. If not
detected, show it disabled with the tag "Not configured" — the same
treatment the Claude option uses when ANTHROPIC_API_KEY is absent.

### 2. Per-mapping run action
Mirror the existing "Run with Claude" per-mapping action with a parallel "Run
with GPT-5.5" action on each mapping card. Clicking it:
- Shows a loading state for that mapping's card.
- Calls `OpenAIDiscoveryEngine.propose_one()` for that exact
  source_field / source_value / destination_fields, using the same
  EvidenceRetriever data the mock and Claude use (identical evidence,
  genuine apples-to-apples).
- On success, displays the GPT-5.5 result ALONGSIDE the existing Mock result
  and any existing Claude result on the same card — do not overwrite either.
  The card should be able to show Mock, Claude, and GPT-5.5 results together,
  each clearly labeled, each with its own confidence score, citation set, and
  reasoning.
- On failure (auth, rate limit/quota, malformed response, timeout), show a
  clear inline error state on that mapping's card ("GPT-5.5 engine error:
  <reason>") without crashing and without echoing the key.
- Allow re-running (the model is non-deterministic; repeat runs may differ,
  which is itself worth being able to see).

### 3. Persisted comparison record
Mirror the Claude run persistence. Append every completed GPT-5.5 run
(success or failure) to `output/openai_engine_runs.jsonl`, append-only, one
entry per run, same shape as the Claude runs file but with an "engine":
"gpt-5.5" field (and add the same "engine" field to Claude's entries if not
already present, so the two run-logs are distinguishable when read together).
Each entry includes: timestamp, engine, domain, source_field, source_value,
mock_confidence_score, mock_governance_status, engine_confidence_score,
engine_governance_status, engine_citations, engine_reasoning,
validation_flags, run_succeeded, error. Multiple runs on the same mapping are
all retained (never overwritten) and viewable in that mapping's run history.

### 4. Visual framing
Where Mock/Claude/GPT-5.5 results appear together, the existing caption
distinguishing deterministic (Mock) from probabilistic (a real model's one
response at one moment, may differ on repeat and may differ between models)
should cover all three. A model's score is one model's one response; two
different models may differ from each other as well as from the mock. Keep
this calm and short — do not build elaborate explanatory UI.

### 5. Do NOT
- Do not let a GPT-5.5 run affect governance_status, approval state, or
  substrate version cuts. Like the Claude comparison, this is
  informational/diagnostic only; the Mock-derived mapping remains the one
  that flows through approval, versioning, and audit.
- Do not weaken or remove the citation-fabrication validation in
  openai_discovery_engine.py.
- Do not build a bulk "run all mappings" action.
- Do not display the API key anywhere, including error messages.

## Tests
Add tests proving:
- GPT-5.5 is selectable only when OPENAI_API_KEY is present; otherwise shows
  "Not configured."
- A successful GPT-5.5 run persists a correctly-shaped entry (with
  engine="gpt-5.5") to openai_engine_runs.jsonl without modifying the
  mapping's own governance_status.
- A simulated failed/malformed response is handled gracefully (persisted with
  run_succeeded=false and a non-empty error, no crash).
- Running GPT-5.5 twice on the same mapping produces two distinct entries
  (not an overwrite).
- Mock, Claude, and GPT-5.5 results can coexist on one mapping card without
  any of them overwriting the others.
- The UI-facing data layer never includes the raw API key value.
- All existing tests (mock, Claude) still pass unchanged.

## Acceptance criteria
- GPT-5.5 selectable only when OPENAI_API_KEY present; "Not configured"
  otherwise.
- Each mapping has its own "Run with GPT-5.5" action; no bulk run.
- GPT-5.5 results display alongside Mock and Claude without overwriting either.
- All runs (success and failure) persisted to openai_engine_runs.jsonl, never
  overwritten, multiple runs retained and viewable.
- GPT-5.5 runs never affect governance_status, approval, or substrate
  versioning.
- No API key in any template, log, or error message.
- Mock and Claude integrations are unchanged and all their tests still pass.
