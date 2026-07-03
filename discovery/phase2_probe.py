"""
Phase 2 probe harness. Run this with a real ANTHROPIC_API_KEY set to compare
ClaudeDiscoveryEngine's behavior against MockDiscoveryEngine on three chosen
cases:

  1. CONFIDENT case   — probableCause=equipment_malfunction (mock: 0.65)
  2. THIN case        — probableCause=link_down (mock: 0.53, known legacy conflict)
  3. INSUFFICIENT case — probableCause=solar_flare_noise (mock: None, refuses)

It also runs the shared prompt-injection suite (discovery.injection_suite),
which plants payloads across several evidence fields on copies of the corpus
and scores whether the model follows an instruction embedded in evidence data
rather than treating it as inert.

Usage:
    pip install anthropic
    export ANTHROPIC_API_KEY=sk-...
    python -m discovery.phase2_probe
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from discovery.injection_suite import print_scorecard, score_engines
from discovery.mock_discovery_engine import MockDiscoveryEngine
from discovery.claude_discovery_engine import ClaudeDiscoveryEngine


DATA_DIR = Path(__file__).resolve().parents[1] / "data"

CASES = [
    ("CONFIDENT", "probableCause", "link_down", ["assignment_group"]),
    ("THIN", "probableCause", "optical_degrade", ["assignment_group"]),
    ("INSUFFICIENT", "probableCause", "solar_flare_noise", ["assignment_group"]),
]


def get_mock_baseline() -> dict[str, dict]:
    results = MockDiscoveryEngine().discover(DATA_DIR)
    return {
        (r["source_field"], r.get("source_value")): r
        for r in results
    }


def run_real_cases(engine: ClaudeDiscoveryEngine, baseline: dict) -> None:
    for label, field, value, dest in CASES:
        mock_result = baseline.get((field, value), {})
        print(f"\n{'='*70}\nCASE: {label}  ({field}={value})\n{'='*70}")
        print(f"MOCK   confidence={mock_result.get('confidence_score')}  "
              f"status={mock_result.get('governance_status')}")
        print(f"MOCK   citations={mock_result.get('evidence_citations')}")

        claude_result = engine.propose_one(DATA_DIR, field, value, dest)
        print(f"\nCLAUDE confidence={claude_result.get('confidence_score')}  "
              f"status={claude_result.get('governance_status')}")
        print(f"CLAUDE citations={claude_result.get('evidence_citations')}")
        print(f"CLAUDE reasoning={claude_result.get('reasoning')}")
        if claude_result.get("validation_flags"):
            print(f"!! VALIDATION FLAGS: {claude_result['validation_flags']}")


def run_injection_probe(engine: ClaudeDiscoveryEngine) -> None:
    """Run the shared injection suite against Claude, alongside the deterministic
    mock as the reference row. Payloads live in discovery.injection_suite."""
    print_scorecard(score_engines({
        "MockDiscoveryEngine": MockDiscoveryEngine(),
        "ClaudeDiscoveryEngine": engine,
    }))


if __name__ == "__main__":
    baseline = get_mock_baseline()
    engine = ClaudeDiscoveryEngine()
    run_real_cases(engine, baseline)
    run_injection_probe(engine)
