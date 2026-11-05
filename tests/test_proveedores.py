"""Regresiones de endpoints adaptadas de Verosimil; transporte simulado."""
from __future__ import annotations

import json

import pytest

import analisisr_core as V


def test_deepseek_usa_los_valores_documentados():
    """api-docs.deepseek.com: base sin /v1 y modelo vigente deepseek-flash."""
    d = V.provider_defaults("deepseek")
    assert d["host"] == "https://api.deepseek.com"
    assert d["model"] == "deepseek-flash"
    assert d["style"] == "openai"
    assert "deepseek-v4-pro" in d["note"]


def test_no_quedan_nombres_retirados_como_valor_por_defecto():
    for k, d in V.PROVIDERS.items():
        assert d.get("model") not in ("deepseek-chat", "deepseek-reasoner"), k


def test_list_models_estilo_openai():
    visto = {}

    def falso(url, payload, headers, method="POST"):
        visto.update({"url": url, "method": method, "headers": headers})
        return {"data": [{"id": "deepseek-flash"}, {"id": "deepseek-v4-pro"}]}

    b = V.Backend("deepseek", "", None, 10, None, 0.0, 10, api_key="sk-1")
    b._http_json = falso
    assert b.list_models() == ["deepseek-flash", "deepseek-v4-pro"]
    assert visto["url"] == "https://api.deepseek.com/models"
    assert visto["method"] == "GET"
    assert visto["headers"]["Authorization"] == "Bearer sk-1"


def test_list_models_estilo_anthropic():
    visto = {}

    def falso(url, payload, headers, method="POST"):
        visto.update({"url": url, "headers": headers})
        return {"data": [{"id": "claude-3-5-haiku-latest"}, {"id": "claude-sonnet-x"}]}

    b = V.Backend("anthropic", "", None, 10, None, 0.0, 10, api_key="sk-ant")
    b._http_json = falso
    assert b.list_models() == ["claude-3-5-haiku-latest", "claude-sonnet-x"]
    assert visto["url"].endswith("/models?limit=100")
    assert visto["headers"]["anthropic-version"] == V.ANTHROPIC_VERSION


def test_list_models_estilo_gemini_quita_prefijo():
    def falso(url, payload, headers, method="POST"):
        assert "key=sk-g" in url
        return {"models": [{"name": "models/gemini-2.5-flash"},
                           {"name": "models/gemini-2.5-pro"}]}

    b = V.Backend("gemini", "", None, 10, None, 0.0, 10, api_key="sk-g")
    b._http_json = falso
    assert b.list_models() == ["gemini-2.5-flash", "gemini-2.5-pro"]


def test_probe_avisa_si_el_modelo_no_esta_en_el_listado():
    """El error típico de DeepSeek era el nombre del modelo: debe decirlo."""
    b = V.Backend("deepseek", "", "deepseek-chat", 10, None, 0.0, 10, api_key="sk-1")
    b.list_models = lambda: ["deepseek-flash", "deepseek-v4-pro"]
    r = b.probe()
    assert r["ok"] is True and r["model_listed"] is False
    assert "deepseek-chat" in r["warning"] and "deepseek-flash" in r["warning"]


def test_probe_ok_si_el_modelo_esta_listado():
    b = V.Backend("deepseek", "", "deepseek-flash", 10, None, 0.0, 10, api_key="sk-1")
    b.list_models = lambda: ["deepseek-flash", "deepseek-v4-pro"]
    b._http_json = lambda *a, **k: {"model": "deepseek-flash",
                                    "usage": {"prompt_tokens": 1, "completion_tokens": 1}}
    r = b.probe()
    assert r["ok"] and r["model_listed"] and not r.get("warning")
    assert r["model_alias"] == "deepseek-flash"


def test_probe_sin_listado_cae_en_ping():
    """Si el endpoint no implementa /models, el ping de 1 token sigue sirviendo."""
    b = V.Backend("openai", "", "gpt-4o-mini", 10, None, 0.0, 10, api_key="k")

    def sin_listado():
        raise RuntimeError("HTTP 404: not found")

    b.list_models = sin_listado
    b._http_json = lambda *a, **k: {"model": "gpt-4o-mini", "usage": {}}
    r = b.probe()
    assert r["ok"] and "list_models_error" in r


def test_probe_reporta_error_del_proveedor():
    b = V.Backend("deepseek", "", "deepseek-flash", 10, None, 0.0, 10, api_key="sk-mala")
    b.list_models = lambda: ["deepseek-flash"]

    def falla(*a, **k):
        raise RuntimeError("HTTP 401: Authentication Fails")

    b._http_json = falla
    r = b.probe()
    assert "401" in r["error"] and "warning" in r


def _backend_que_falla(status, veces=99):
    b = V.Backend("deepseek", "", None, 100, None, 0.0, 10, api_key="sk-x")
    estado = {"n": 0}

    def falso(url, payload, headers, method="POST"):
        estado["n"] += 1
        if estado["n"] <= veces:
            raise V.ProviderError(status, url, "cuerpo del proveedor")
        return {"model": "deepseek-flash", "choices": [{"message": {"content": "ok"}}],
                "usage": {}}

    b._http_json = falso
    return b, estado


def test_401_no_se_reintenta(monkeypatch):
    b, estado = _backend_que_falla(401)
    monkeypatch.setattr(V.time, "sleep", lambda s: None)
    with pytest.raises(SystemExit) as e:
        b.chat("s", "u")
    assert estado["n"] == 1                      # un solo intento
    msg = str(e.value)
    assert "401" in msg and "API key" in msg and "cuerpo del proveedor" in msg


def test_404_sugiere_revisar_el_modelo(monkeypatch):
    b, _ = _backend_que_falla(404)
    monkeypatch.setattr(V.time, "sleep", lambda s: None)
    with pytest.raises(SystemExit) as e:
        b.chat("s", "u")
    assert "modelo" in str(e.value).lower()


def test_429_se_reintenta_y_acaba_bien(monkeypatch):
    b, estado = _backend_que_falla(429, veces=2)
    monkeypatch.setattr(V.time, "sleep", lambda s: None)
    assert b.chat("s", "u") == "ok"
    assert estado["n"] == 3


def test_429_agotado_informa(monkeypatch):
    b, estado = _backend_que_falla(429)
    monkeypatch.setattr(V.time, "sleep", lambda s: None)
    with pytest.raises(SystemExit) as e:
        b.chat("s", "u")
    assert estado["n"] == 3 and "límite" in str(e.value)


def test_provider_error_marca_transitorios():
    assert V.ProviderError(429, "u", "").transitorio is True
    assert V.ProviderError(503, "u", "").transitorio is True
    assert V.ProviderError(401, "u", "").transitorio is False
    assert V.ProviderError(400, "u", "").transitorio is False


def _deepseek(rb, monkeypatch, respuesta=None):
    b = V.Backend("deepseek", "https://api.deepseek.com", "deepseek-flash", 6000, rb, 0.0, 60)
    monkeypatch.setattr(b, "resolved_key", lambda: "clave")
    enviado = {}
    def fake(url, payload, headers):
        enviado.update(payload)
        return respuesta or {"choices": [{"message": {"content": "```r\nfit <- 1\n```"},
                                          "finish_reason": "stop"}],
                             "usage": {"prompt_tokens": 10, "completion_tokens": 20}}
    monkeypatch.setattr(b, "_http_json", fake)
    b._chat_openai("sistema", "usuario")
    return b, enviado


def test_reasoning_budget_cero_desactiva_el_pensamiento_en_deepseek(monkeypatch):
    _, enviado = _deepseek(0, monkeypatch)
    assert enviado["thinking"] == {"type": "disabled"}
    assert enviado["max_tokens"] == 6000


def test_con_presupuesto_positivo_no_se_toca_el_modo_del_proveedor(monkeypatch):
    _, enviado = _deepseek(400, monkeypatch)
    assert "thinking" not in enviado


def test_otros_proveedores_openai_no_reciben_thinking(monkeypatch):
    b = V.Backend("openai", "https://api.openai.com/v1", "gpt-x", 6000, 0, 0.0, 60)
    monkeypatch.setattr(b, "resolved_key", lambda: "clave")
    enviado = {}
    monkeypatch.setattr(b, "_http_json", lambda u, p, h: (enviado.update(p), {"choices": [
        {"message": {"content": "x"}, "finish_reason": "stop"}]})[1])
    b._chat_openai("s", "u")
    assert "thinking" not in enviado


def _local(rb, monkeypatch, respuesta=None):
    b = V.Backend("local", "http://127.0.0.1:8080", "qwen", 131000, rb, 0.0, 60)
    enviado = {}
    class Resp:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return json.dumps(respuesta or {"choices": [
            {"message": {"content": "```r\nfit <- 1\n```"}, "finish_reason": "stop"}]}).encode()
    def fake_urlopen(req, timeout=None):
        enviado.update(json.loads(req.data.decode()))
        return Resp()
    monkeypatch.setattr(V.urllib.request, "urlopen", fake_urlopen)
    b._chat_local("sistema", "usuario", 131000)
    return b, enviado


def test_presupuesto_cero_desactiva_el_pensamiento_en_local(monkeypatch):
    _, enviado = _local(0, monkeypatch)
    assert enviado["reasoning_budget"] == 0
    assert enviado["reasoning_effort"] == "none"
    assert enviado["chat_template_kwargs"] == {"enable_thinking": False}


def test_con_presupuesto_positivo_local_no_manda_chat_template_kwargs(monkeypatch):
    _, enviado = _local(400, monkeypatch)
    assert enviado["reasoning_budget"] == 400
    assert "chat_template_kwargs" not in enviado


def _local_404(monkeypatch, modelo, ids):
    import urllib.error
    b = V.Backend("local", "http://127.0.0.1:8090", modelo, 6000, 0, 0.0, 30)
    def revienta(*a, **k):
        raise urllib.error.HTTPError("u", 404, "Not Found", None, None)
    monkeypatch.setattr(b, "_chat_local", revienta)
    monkeypatch.setattr(b, "modelos_locales", lambda: ids)
    with pytest.raises(SystemExit) as e:
        b.chat("s", "u")
    return str(e.value)


def test_el_404_local_nombra_los_modelos_que_sirve(monkeypatch):
    msg = _local_404(monkeypatch, "Qwen3.8-27B", ["qwen3.8-27b"])
    assert "no reconoce el modelo" in msg
    assert "El servidor esta vivo y sirve: qwen3.8-27b" in msg
    assert "salvo mayusculas" in msg and "«qwen3.8-27b»" in msg
    assert "siga vivo" not in msg, "ya no debe culpar al servidor"


def test_si_el_nombre_no_se_parece_sugiere_dejarlo_en_blanco(monkeypatch):
    msg = _local_404(monkeypatch, "otro-modelo", ["qwen3.8-27b", "llama-3"])
    assert "qwen3.8-27b, llama-3" in msg
    assert "en blanco" in msg and "salvo mayusculas" not in msg


def test_si_no_se_puede_listar_se_dice_sin_inventar(monkeypatch):
    msg = _local_404(monkeypatch, "x", [])
    assert "no se pudo consultar" in msg and "/v1/models" in msg


def test_un_404_no_consume_los_reintentos_de_tokens(monkeypatch):
    import urllib.error
    b = V.Backend("local", "http://127.0.0.1:8090", "x", 6000, 0, 0.0, 30)
    intentos = []
    def revienta(system, user, budget):
        intentos.append(budget)
        raise urllib.error.HTTPError("u", 404, "Not Found", None, None)
    monkeypatch.setattr(b, "_chat_local", revienta)
    monkeypatch.setattr(b, "modelos_locales", lambda: ["otro"])
    with pytest.raises(SystemExit):
        b.chat("s", "u")
    assert len(intentos) == 1, "un nombre mal escrito no se arregla bajando tokens"


def test_un_corte_de_conexion_si_reintenta_con_menos_tokens(monkeypatch):
    b = V.Backend("local", "http://127.0.0.1:8090", "x", 6000, 0, 0.0, 30)
    intentos = []
    def revienta(system, user, budget):
        intentos.append(budget)
        raise ConnectionResetError("corte")
    monkeypatch.setattr(b, "_chat_local", revienta)
    with pytest.raises(SystemExit) as e:
        b.chat("s", "u")
    assert len(intentos) == 3 and intentos[1] < intentos[0]
    assert "no responde" in str(e.value)
