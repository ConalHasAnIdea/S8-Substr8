from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[1]


def read_ui_file(path: str) -> str:
    return (BASE_DIR / path).read_text(encoding="utf-8")


def test_openai_dropdown_has_enabled_and_not_configured_states():
    template = read_ui_file("ui/templates/index.html")

    assert "{% if openai_configured %}" in template
    assert '{{ openai_engine_label }}' in template
    assert "OpenAI GPT-5.5 - Not configured" in template


def test_openai_availability_is_resolved_per_request_from_store_or_environment():
    app_source = read_ui_file("ui/app.py")

    assert "def openai_configured()" in app_source
    assert "bool(get_api_key(OPENAI))" in app_source
    assert "openai_configured=openai_configured()" in app_source
    assert "sk-" not in app_source


def test_mock_claude_and_openai_panels_coexist_on_mapping_card():
    template = read_ui_file("ui/templates/index.html")

    assert "<h4>Substr8 Mock</h4>" in template
    assert "<h4>Anthropic</h4>" in template
    assert "<h4>OpenAI</h4>" in template
    assert "item.claude_runs" in template
    assert "item.openai_runs" in template
    assert "Run with ChatGPT" in template
    assert "OpenAI engine error:" in template


def test_claude_panel_has_model_selector_without_adding_engine_column():
    template = read_ui_file("ui/templates/index.html")

    assert 'select name="claude_model"' in template
    assert "claude_model_options" in template
    assert "run.model_label" in template
    assert "<h4>Anthropic</h4>" in template


def test_openai_panel_has_model_selector_without_adding_engine_column():
    template = read_ui_file("ui/templates/index.html")

    assert 'select name="openai_model"' in template
    assert "openai_model_options" in template
    assert "ChatGPT-5.5" in template
    assert "<h4>OpenAI</h4>" in template


def test_model_selectors_use_session_backed_selected_values():
    app_source = read_ui_file("ui/app.py")
    index_template = read_ui_file("ui/templates/index.html")
    detail_template = read_ui_file("ui/templates/mapping_detail.html")

    assert 'session["assurance_openai_model"] = model' in app_source
    assert 'session["order_management_openai_model"] = model' in app_source
    assert 'session["assurance_claude_model"] = model' in app_source
    assert 'session["order_management_claude_model"] = model' in app_source
    assert "selected_openai_model=selected_openai_model(" in app_source
    assert "selected_claude_model=selected_claude_model(" in app_source
    assert "option.value == selected_openai_model" in index_template
    assert "option.value == selected_claude_model" in index_template
    assert "option.value == selected_openai_model" in detail_template
    assert "option.value == selected_claude_model" in detail_template
