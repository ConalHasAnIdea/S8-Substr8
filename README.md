# Substr8 Phase 1

> *Machina proponit, homo disponit.*
> — the machine proposes, the human disposes.

Substr8 is a pilot for Evidence-Governed Substrate Engineering (EGSE) in OSS/BSS integration work. It focuses on the integration substrate below the application layer: mappings, exceptions, suppression rules, enrichment logic, tribal knowledge, and operator-specific workflow decisions.

Substr8 does not execute AI decisions. It manufactures governed integration substrates from operational evidence.

Good agentic design is a prerequisite for AI governance, but it is not sufficient.

## What This Phase Proves

Phase 1 proves the governance lifecycle and the evidence/confidence data contract, across two live domains: TMF642 Alarm Management to ServiceNow Incident (Assurance) and TMF622 Product Order to Oracle UIM (Order Management & Fulfillment). Mappings are discovered from synthetic evidence, reviewed, assigned, approved, versioned, audited, and blocked when evidence is insufficient — through one shared engine and governance pipeline, not per-domain forks.

The deterministic `MockDiscoveryEngine` is the default and primary engine, and the governance thesis stands on it alone. Real model-backed engines (Claude and OpenAI GPT-5.5) are additionally wired in as opt-in, per-mapping comparison engines: they consume identical evidence, emit the identical proposal shape, and their results are recorded alongside the mock's for drift comparison — but they never affect governance status, approvals, or substrate versions. They activate only when an API key is provided (environment variable, or the in-memory Settings page); without keys, no external API is ever called. No ServiceNow or Oracle system is contacted in any configuration.

Building the governance scaffold before trusting intelligence was intentional. The mock engine sits exactly where the model-backed engines now also sit, emitting the same proposal shape from the same evidence contract — which is what made wiring in two real engines a narrow change: proposal generation swapped, while review, policy, versioning, and audit stayed identical.

## Governance Lifecycle

Substr8 treats governance as a lifecycle:

1. Discover
2. Review
3. Approve
4. Version
5. Deploy
6. Audit
7. Roll back

Mappings are approved and version-stamped individually. A substrate version is a different artifact: a deliberately cut, timestamped bundle of every mapping in Approved status for one schema pair at the moment of the cut — the thing a runtime executor would actually run against. A single approved mapping is not a substrate. Rollback operates on substrate versions, not individual mappings; in Phase 1 it records the decision in the audit log only, since no live runtime exists yet.

Runtime execution is outside Phase 1. Later phases can add correlation, deduplication, alarm-storm handling, and enforcement of approved substrates.

## Mock Discovery

`MockDiscoveryEngine` implements the abstract `DiscoveryEngine` interface. It reads local schemas, historical tickets, operator notes, legacy rules, and alarm fixtures. It then emits mapping proposals with:

- `source_field`
- `destination_fields`
- `transformation_logic`
- `confidence_score`
- `reasoning`
- `evidence_citations`
- `governance_status`

Confidence scores are derived from the synthetic corpus, not constants. The scoring formula is intentionally transparent: agreement ratio dampened by sample volume. Evidence citations are actual ticket IDs, operator note IDs, and legacy rule IDs.

Operator notes can also carry an explicit author from `data/team_roster.yaml`. Authority weights are illustrative inputs set manually by project leadership for Phase 1; they are not computed or inferred. A cited note can only nudge an existing evidence-derived confidence score by a small bounded amount, and the reasoning text names the author, role, and weight whenever that adjustment is applied.

The planted insufficient-evidence case is `probableCause=solar_flare_noise`. It appears in `data/alarm_fixtures.jsonl` but has no historical tickets, operator notes, or legacy rules. The engine emits `Insufficient Evidence - Human Required` with no confidence score and no citations.

ServiceNow `priority` is never mapped directly. The prototype maps to `impact` and `urgency`; `priority` is derived by the ServiceNow Priority Data Lookup matrix represented in `data/servicenow_incident_schema.json`.

When historical evidence splits roughly evenly between two destination values, the engine attaches an advisory split hint (possible conditional rule) rather than hiding the ambiguity behind a low score. The hint never changes governance status; the human decides whether two conditional mappings beat one uncertain one.

## Governance Features

- **Review queue** per domain: approve, reject, or request clarification, each requiring a decision reason. Reasons are gated deterministically (length, no copy-paste duplicates); an advisory Claude relevance check can additionally flag a recorded decision's reason for human follow-up, but can never block or reverse the decision.
- **Assignment as a soft lock**: a mapping can be assigned to a roster member or group, which disables decision controls until unassigned. Assignment, unassignment, and decision are three separate audit events.
- **Substrate versions**: deliberately cut, per-domain bundles of currently-Approved mappings, with an include/exclude preview before cutting, an active-version pointer, and audit-logged rollback.
- **Reviewer activity report**: per-member action counts and a revision rate (how often a member's approvals were later reversed), plus a live count of unassigned pre-decision mappings.
- **Demo reset**: confirmation-gated control that returns review state to pre-discovery without ever deleting audit history — the reset itself is an audit event.

## API Keys and the Settings Page

Model-backed comparison engines need keys. Two ways to provide them:

- Environment variables `ANTHROPIC_API_KEY` / `OPENAI_API_KEY`, or
- The **Settings** page in the UI: keys are validated with a cheap live call, then held in process memory only — never written to disk, logs, or cookies, and gone on restart. A key entered in Settings overrides the environment for the session.

This is a demo convenience. Production deployments should source keys from a proper secrets manager (HashiCorp Vault, AWS Secrets Manager, Azure Key Vault, GCP Secret Manager).

## Run Locally

```powershell
cd substr8
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe generate_outputs.py
.venv\Scripts\python.exe -m pytest
.venv\Scripts\python.exe ui\app.py
```

Open the Flask app at `http://127.0.0.1:5000`.

Calling the venv's `python.exe` directly avoids PowerShell execution-policy issues with `Activate.ps1`. Flask debug mode (interactive debugger + auto-reload) is off by default; opt in with `FLASK_DEBUG=1` for development only.

## Project Structure

```text
substr8/
  data/          synthetic schemas, tickets, notes, fixtures, and legacy rules
  discovery/     shared discovery interface, mock engine, retrieval, prompt builder, confidence
  governance/    approval, policy, audit log, and versioning
  output/        proposed mappings, approved mappings, substrate versions, audit log
  ui/            Flask review interface
  tests/         retrieval, schema, governance, and confidence derivation tests
```

## Roadmap

The Phase 2 engine swap has been probed: `ClaudeDiscoveryEngine` and `OpenAIDiscoveryEngine` run against real evidence behind the same interface, with citation-fabrication validation and drift comparison against the mock. Remaining Phase 2 work is promoting a model-backed engine from comparison-only to proposal-generating, including letting it reason about whether an evidence split is conditional or genuinely ambiguous. Later phases can add a runtime executor that enforces approved substrates and handles correlation, deduplication, and alarm storms.
