# Substr8 Phase 1

Substr8 is a pilot for Evidence-Governed Substrate Engineering (EGSE) in OSS/BSS integration work. It focuses on the integration substrate below the application layer: mappings, exceptions, suppression rules, enrichment logic, tribal knowledge, and operator-specific workflow decisions.

Substr8 does not execute AI decisions. It manufactures governed integration substrates from operational evidence.

Good agentic design is a prerequisite for AI governance, but it is not sufficient.

## What This Phase Proves

Phase 1 proves the governance lifecycle and the evidence/confidence data contract. It shows that a TMF642 Alarm Management to ServiceNow Incident mapping can be discovered from synthetic evidence, reviewed, approved, versioned, audited, and blocked when evidence is insufficient.

Phase 1 deliberately does not prove that a model can discover bespoke operator substrate from raw evidence. That discovery-intelligence thesis is deferred to Phase 2. This prototype runs entirely in deterministic mock mode: no Claude, OpenAI, Gemini, Anthropic, ServiceNow, or external LLM API is called.

Building the governance scaffold before adding intelligence is intentional. The mock engine sits exactly where a future model-backed engine will sit, emits the same proposal shape, and consumes the same evidence contract. That makes the future engine swap narrow: replace proposal generation, keep review, policy, versioning, and audit unchanged.

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

## Run Locally

```powershell
cd substr8
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python generate_outputs.py
python -m pytest
python ui\app.py
```

Open the Flask app at `http://127.0.0.1:5000`.

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

Phase 2 replaces `MockDiscoveryEngine` with a real discovery engine, such as a future `ClaudeDiscoveryEngine`, while preserving the interface and output shape. Later phases can add a runtime executor that enforces approved substrates and handles correlation, deduplication, and alarm storms.
