"""Presupuesto fijo en la app y desactivación en chat y sondeos, sin red."""
import pytest

import AnalisisR as app
import analisisr_core as core


@pytest.mark.parametrize("kind,model,options", [
    ("deepseek", "deepseek-flash", {"thinking": {"type": "disabled"}}),
    ("openai", "gpt-5.1", {"reasoning_effort": "none"}),
    ("anthropic", "claude-sonnet-4-6", {"thinking": {"type": "disabled"}}),
    ("anthropic", "claude-sonnet-5-5", {"thinking": {"type": "between_tools"},
                                       "output_config": {"effort": "low"}}),
    ("gemini", "gemini-2.5-flash", {"thinkingConfig": {"thinkingBudget": 0, "includeThoughts": False}}),
])
def test_chat_y_sondeo_desactivan_razonamiento(kind, model, options, monkeypatch):
    backend = app.make_backend(dict(backend=kind, host="", model=model, reasoning_budget=500))
    assert backend.rb == 0
    assert backend.max_tokens == 64000 and backend.timeout == 300
    sent = []

    def response(url, payload, headers, method="POST"):
        sent.append(payload)
        return {"model": model, "content": [{"type": "text", "text": "ok"}],
                "choices": [{"message": {"content": "ok"}}],
                "candidates": [{"content": {"parts": [{"text": "ok"}]}}]}

    monkeypatch.setattr(backend, "resolved_key", lambda: "test-key")
    monkeypatch.setattr(backend, "list_models", lambda: [model])
    monkeypatch.setattr(backend, "_http_json", response)
    assert backend.chat("s", "u") == "ok"
    assert backend.probe()["ok"]
    assert len(sent) == 2
    for payload in sent:
        actual = payload["generationConfig"] if kind == "gemini" else payload
        assert all(actual[key] == value for key, value in options.items())


@pytest.mark.parametrize("kind,model", [
    ("openai", "o3"), ("openai", "gpt-5"), ("openai", "gpt-5-mini"),
    ("openai", "gpt-6-astra"), ("openai", "gpt-6.1-sol"),
    ("gemini", "gemini-2.5-pro"), ("anthropic", "claude-opus-5-5"),
    ("anthropic", "claude-fable-5-1"), ("anthropic", "claude-mythos-preview"),
])
def test_modelo_de_razonamiento_obligatorio_se_rechaza(kind, model):
    with pytest.raises(ValueError, match="no permite desactivar"):
        app.make_backend(dict(backend=kind, host="", model=model))


@pytest.mark.parametrize("message,usage", [
    ({"content": "ok", "reasoning_content": "razonamiento"}, {}),
    ({"content": "ok"}, {"completion_tokens_details": {"reasoning_tokens": 3}}),
    ({"content": "<think>razonamiento</think>ok"}, {}),
])
def test_servidor_que_ignora_desactivacion_no_se_acepta(message, usage, monkeypatch):
    backend = app.make_backend(dict(backend="openai", host="", model="gpt-5.1"))
    monkeypatch.setattr(backend, "resolved_key", lambda: "test-key")
    monkeypatch.setattr(backend, "list_models", lambda: [backend.model])
    monkeypatch.setattr(backend, "_http_json", lambda *a: {
        "choices": [{"message": message}], "usage": usage})
    with pytest.raises(RuntimeError, match="ha usado razonamiento"):
        backend.chat("s", "u")
    result = backend.probe()
    assert not result["ok"] and "razonamiento" in result["error"]


@pytest.mark.parametrize("kind,response", [
    ("gemini", {"candidates": [{"content": {"parts": [{"text": "pensamiento", "thought": True}]}}]}),
    ("gemini", {"candidates": [{"content": {"parts": [{"text": "ok"}]}}],
                "usageMetadata": {"thoughtsTokenCount": 4}}),
    ("anthropic", {"content": [{"type": "thinking", "thinking": "pensamiento"}]}),
])
def test_rechaza_pensamiento_de_otros_proveedores(kind, response, monkeypatch):
    backend = app.make_backend(dict(backend=kind, host="", model="compatible"))
    monkeypatch.setattr(backend, "resolved_key", lambda: "test-key")
    monkeypatch.setattr(backend, "_http_json", lambda *a: response)
    with pytest.raises(RuntimeError, match="ha usado razonamiento"):
        backend.chat("s", "u")


def test_incompatibilidad_no_reintenta_activando_pensamiento(monkeypatch):
    backend = app.make_backend(dict(backend="openai", host="", model="gpt-future"))
    calls = []

    def fail(url, payload, headers):
        calls.append(payload)
        raise core.ProviderError(400, url, "reasoning_effort none unsupported")

    monkeypatch.setattr(backend, "resolved_key", lambda: "test-key")
    monkeypatch.setattr(backend, "_http_json", fail)
    with pytest.raises(SystemExit, match="no admite desactivar"):
        backend.chat("s", "u")
    assert len(calls) == 1 and calls[0]["reasoning_effort"] == "none"


def test_bloque_think_vacio_no_es_razonamiento():
    backend = app.make_backend(dict(backend="local", host="", model="qwen"))
    backend._check_reasoning(content="<think>\n</think>Respuesta")
    assert backend._no_reasoning_options() == {
        "reasoning_budget": 0, "reasoning_effort": "none",
        "chat_template_kwargs": {"enable_thinking": False}}
