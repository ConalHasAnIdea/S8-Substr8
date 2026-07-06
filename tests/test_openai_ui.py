from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[1]


def read_ui_file(path: str) -> str:
    return (BASE_DIR / path).read_text(encoding="utf-8")


def test_engine_selector_uses_three_panes_not_a_flat_list():
    template = read_ui_file("ui/templates/index.html")

    assert "engine-panes" in template
    assert "<select name=\"discovery_engine\"" not in template
    assert ">Mock<" in template
    assert ">Local (self hosted)<" in template
    assert ">FrontierLLM<" in template


def test_frontier_pane_offers_chatgpt_and_claude_sonnet_5_in_one_dropdown():
    template = read_ui_file("ui/templates/index.html")

    assert 'value="{{ frontier_engine_label }}"' in template
    assert '<select name="frontier_provider">' in template
    assert ">ChatGPT-5.5<" in template
    assert ">Claude Sonnet 5<" in template
    assert "{% if not claude_configured %}disabled{% endif %}" in template
    assert "{% if not openai_configured %}disabled{% endif %}" in template


def test_openai_availability_is_resolved_per_request_from_store_or_environment():
    app_source = read_ui_file("ui/app.py")

    assert "def openai_configured()" in app_source
    assert "bool(get_api_key(OPENAI))" in app_source
    assert '"openai_configured": openai_configured()' in app_source
    assert "sk-" not in app_source


def test_mock_and_frontier_panels_coexist_on_mapping_card():
    template = read_ui_file("ui/templates/index.html")

    assert "<h4>Substr8 Mock</h4>" in template
    assert "<h4>FrontierLLM</h4>" in template
    assert "<h4>Anthropic</h4>" not in template
    assert "<h4>OpenAI</h4>" not in template
    assert "item.frontier_runs" in template
    assert "Run FrontierLLM" in template


def test_frontier_panel_has_one_merged_provider_dropdown_not_two_separate_ones():
    template = read_ui_file("ui/templates/index.html")

    assert 'select name="frontier_provider"' in template
    assert 'select name="claude_model"' not in template
    assert 'select name="openai_model"' not in template
    assert "run.model_label" in template
    assert "run.frontier_provider_label" in template


def test_frontier_run_history_shows_which_provider_produced_each_run():
    index_template = read_ui_file("ui/templates/index.html")
    detail_template = read_ui_file("ui/templates/mapping_detail.html")
    app_source = read_ui_file("ui/app.py")

    assert "frontier_provider_label" in index_template
    assert "frontier_provider_label" in detail_template
    assert "def frontier_runs_for_mapping(" in app_source
    assert '"Claude"' in app_source
    assert '"ChatGPT"' in app_source


def test_frontier_provider_selection_is_session_backed():
    app_source = read_ui_file("ui/app.py")
    index_template = read_ui_file("ui/templates/index.html")
    detail_template = read_ui_file("ui/templates/mapping_detail.html")

    assert 'session["assurance_frontier_provider"] = provider' in app_source
    assert 'session["order_management_frontier_provider"] = provider' in app_source
    assert "def selected_frontier_provider(domain_key" in app_source
    assert "selected_frontier_provider == 'openai'" in index_template
    assert "selected_frontier_provider == 'claude'" in index_template
    assert "selected_frontier_provider == 'openai'" in detail_template
    assert "selected_frontier_provider == 'claude'" in detail_template
