"""
Standalone three-way cross-model probe: Mock vs Claude vs GPT-5.5.

Runs the same three cases (confident / thin / insufficient) plus the shared
injection suite (discovery.injection_suite) across all three engines on
IDENTICAL evidence, and prints them together so the cross-model differences are
the visible output. This is the "is this Claude-specific or
probabilistic-in-general?" question, made concrete.

Usage:
    pip install anthropic openai
    export ANTHROPIC_API_KEY=sk-ant-...
    export OPENAI_API_KEY=sk-...
    python -m discovery.cross_model_probe

If only one key is set, that engine runs and the other is skipped with a note.
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from discovery.injection_suite import print_scorecard, score_engines
from discovery.mock_discovery_engine import MockDiscoveryEngine

DATA_DIR = Path(__file__).resolve().parents[1] / "data"

CASES = [
    ("CONFIDENT", "probableCause", "link_down", ["assignment_group"]),
    ("THIN", "probableCause", "optical_degrade", ["assignment_group"]),
    ("INSUFFICIENT", "probableCause", "solar_flare_noise", ["assignment_group"]),
]


def get_mock_baseline() -> dict:
    results = MockDiscoveryEngine().discover(DATA_DIR)
    return {(r["source_field"], r.get("source_value")): r for r in results}


def _summarize(label: str, result: dict) -> None:
    print(f"  {label:8s} confidence={result.get('confidence_score')!s:6s} "
          f"status={result.get('governance_status')}")
    cites = result.get("evidence_citations", [])
    print(f"  {'':8s} citations={cites}")
    if result.get("validation_flags"):
        print(f"  {'':8s} !! flags={result['validation_flags']}")


def run_three_way(claude_engine, openai_engine, baseline) -> None:
    for label, field, value, dest in CASES:
        mock = baseline.get((field, value), {})
        print(f"\n{'='*72}\nCASE: {label}  ({field}={value})\n{'='*72}")
        print(f"  {'MOCK':8s} confidence={mock.get('confidence_score')!s:6s} "
              f"status={mock.get('governance_status')}")

        if claude_engine:
            try:
                _summarize("CLAUDE", claude_engine.propose_one(DATA_DIR, field, value, dest))
            except Exception as e:
                print(f"  CLAUDE   ERROR: {e}")
        else:
            print(f"  {'CLAUDE':8s} (skipped — ANTHROPIC_API_KEY not set)")

        if openai_engine:
            try:
                _summarize("GPT-5.5", openai_engine.propose_one(DATA_DIR, field, value, dest))
            except Exception as e:
                print(f"  GPT-5.5  ERROR: {e}")
        else:
            print(f"  {'GPT-5.5':8s} (skipped — OPENAI_API_KEY not set)")


def run_injection(claude_engine, openai_engine) -> None:
    """Run the shared injection suite across whichever engines are configured,
    with the deterministic mock as the reference row. Payloads live in
    discovery.injection_suite (one source of truth)."""
    engines = {"MockDiscoveryEngine": MockDiscoveryEngine()}
    if claude_engine:
        engines["ClaudeDiscoveryEngine"] = claude_engine
    if openai_engine:
        engines["OpenAIDiscoveryEngine"] = openai_engine
    print_scorecard(score_engines(engines))


if __name__ == "__main__":
    baseline = get_mock_baseline()

    claude_engine = None
    if os.environ.get("ANTHROPIC_API_KEY"):
        from discovery.claude_discovery_engine import ClaudeDiscoveryEngine
        claude_engine = ClaudeDiscoveryEngine()

    openai_engine = None
    if os.environ.get("OPENAI_API_KEY"):
        from discovery.openai_discovery_engine import OpenAIDiscoveryEngine
        openai_engine = OpenAIDiscoveryEngine()

    if not claude_engine and not openai_engine:
        print("No API keys set. Set ANTHROPIC_API_KEY and/or OPENAI_API_KEY.")
        sys.exit(1)

    run_three_way(claude_engine, openai_engine, baseline)
    run_injection(claude_engine, openai_engine)
