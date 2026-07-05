from governance.run_log import (
    CANONICAL_RUN_FIELDS,
    append_run_log,
    build_run_record,
    load_run_log,
    telemetry_from_response,
)


def mapping() -> dict:
    return {
        "source_field": "probableCause",
        "source_value": "link_down",
        "destination_fields": ["assignment_group"],
        "confidence_score": 0.86,
        "governance_status": "Pending Approval",
    }


def proposal(confidence: float, citation: str) -> dict:
    return {
        "source_field": "probableCause",
        "source_value": "link_down",
        "destination_fields": ["assignment_group"],
        "transformation_logic": "link_down -> assignment_group=Transport NOC",
        "confidence_score": confidence,
        "reasoning": "Evidence supports Transport NOC.",
        "evidence_citations": [citation],
        "governance_status": "Pending Approval",
        "validation_flags": [],
    }


def test_shared_logger_writes_agreed_schema(tmp_path):
    record = build_run_record(
        engine="local",
        model="llama3.1",
        model_label="llama3.1",
        domain="Assurance",
        mapping=mapping(),
        proposal=proposal(0.91, "TKT-1001"),
        run_succeeded=True,
        latency_ms=123,
        prompt_tokens=10,
        completion_tokens=20,
        total_tokens=30,
    )

    written = append_run_log(tmp_path, "local_engine_runs.jsonl", record)
    loaded = load_run_log(tmp_path, "local_engine_runs.jsonl")

    assert loaded == [written]
    assert list(written.keys())[:len(CANONICAL_RUN_FIELDS)] == CANONICAL_RUN_FIELDS
    assert written["engine"] == "local"
    assert written["model"] == "llama3.1"
    assert written["mapping_identifier"]["mapping_key"] == "Assurance|probableCause|link_down|assignment_group"
    assert written["proposal"]["confidence_score"] == 0.91
    assert written["confidence_score"] == 0.91
    assert written["citations"] == ["TKT-1001"]
    assert written["latency_ms"] == 123
    assert written["prompt_tokens"] == 10
    assert written["completion_tokens"] == 20
    assert written["total_tokens"] == 30


def test_records_from_different_engines_line_up_field_for_field(tmp_path):
    records = [
        build_run_record(
            engine="claude",
            model="claude-sonnet-4-6",
            model_label="Claude Sonnet 4.6",
            domain="Assurance",
            mapping=mapping(),
            proposal=proposal(0.89, "TKT-1001"),
            run_succeeded=True,
        ),
        build_run_record(
            engine="openai",
            model="gpt-5.5",
            model_label="ChatGPT-5.5",
            domain="Assurance",
            mapping=mapping(),
            proposal=proposal(0.92, "TKT-1002"),
            run_succeeded=True,
            validation_flags=["fabricated_citations: ['TKT-9999']"],
        ),
    ]

    for record in records:
        append_run_log(tmp_path, "comparison_runs.jsonl", record)

    loaded = load_run_log(tmp_path, "comparison_runs.jsonl")

    assert len(loaded) == 2
    assert list(loaded[0].keys()) == list(loaded[1].keys())
    assert all(field in loaded[0] for field in CANONICAL_RUN_FIELDS)
    assert loaded[0]["latency_ms"] is None
    assert loaded[0]["prompt_tokens"] is None
    assert loaded[0]["completion_tokens"] is None
    assert loaded[0]["total_tokens"] is None
    assert loaded[1]["validation_flags"] == ["fabricated_citations: ['TKT-9999']"]


def test_telemetry_from_openai_compatible_usage():
    response = type("Response", (), {
        "usage": type("Usage", (), {
            "prompt_tokens": 11,
            "completion_tokens": 22,
            "total_tokens": 33,
        })()
    })()

    assert telemetry_from_response(response, latency_ms=44) == {
        "latency_ms": 44,
        "prompt_tokens": 11,
        "completion_tokens": 22,
        "total_tokens": 33,
    }


def test_telemetry_from_ollama_native_counts():
    response = {
        "prompt_eval_count": 12,
        "eval_count": 23,
        "total_duration": 45_600_000,
    }

    assert telemetry_from_response(response) == {
        "latency_ms": 46,
        "prompt_tokens": 12,
        "completion_tokens": 23,
        "total_tokens": 35,
    }
