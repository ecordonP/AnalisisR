"""Independencia de código, configuración y credenciales de Verosímil."""
from __future__ import annotations

import os
import json
from pathlib import Path
import shutil
import subprocess
import sys
from types import SimpleNamespace

import pytest

import AnalisisR as app


@pytest.mark.parametrize("with_gui", [False, True])
def test_copia_aislada_sin_modulos_verosimil(tmp_path: Path, with_gui: bool) -> None:
    if with_gui:
        pytest.importorskip("PySide6")
    folder = tmp_path / "standalone"
    folder.mkdir()
    for name in ("AnalisisR.py", "analisisr_core.py", "analisisr_secrets.py", "analisisr_ui.py",
                 "analisisr_session.py", "analisisr_docx.py"):
        shutil.copyfile(Path(app.__file__).parent / name, folder / name)
    shutil.copytree(Path(app.__file__).parent / "assets", folder / "assets")
    (folder / "source.csv").write_text("x,y\n1,10\n2,20\n", encoding="utf-8")
    bootstrap = r'''
import importlib.abc
import json
import sys
from pathlib import Path

folder = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(folder))
class NoVerosimil(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.startswith("verosimil") or fullname == "gui":
            raise AssertionError("Dependencia externa: " + fullname)
sys.meta_path.insert(0, NoVerosimil())
import AnalisisR as app
for module in (app, app.engine, app.secrets):
    assert Path(module.__file__).parent == folder
request = folder / "request.json"
app.write_json(request, {"action": "profile", "data": str(folder / "source.csv")})
assert app.worker(request) == 0
assert json.loads((folder / "result.json").read_text(encoding="utf-8"))["n_cols"] == 2
if sys.argv[2] == "gui":
    import analisisr_ui as ui
    app.secrets.load = lambda: {}
    qt = ui.QApplication([])
    window = app.create_window()
    assert window.tabs.count() == 4
    window.answered("Pregunta", {"answer": "**Respuesta**"})
    assert "Respuesta" in window.chat.toPlainText()
    window.close()
'''
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen", PYTHONPATH="")
    result = subprocess.run(
        [sys.executable, "-I", "-c", bootstrap, str(folder), "gui" if with_gui else "worker"],
        cwd=folder, env=env, capture_output=True, text=True, encoding="utf-8", timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_perfiles_y_bloqueos_son_propios(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("APPDATA", "XDG_CONFIG_HOME"):
        monkeypatch.setenv(name, str(tmp_path))
    monkeypatch.setattr(app.secrets.os.path, "expanduser", lambda path: str(tmp_path))
    assert app.secrets.APP_DIR_NAME == "AnalisisR"
    assert app.secrets.KEYRING_SERVICE == "AnalisisR"
    foreign = tmp_path / "Verosimil" / "backends.json"
    foreign.parent.mkdir()
    foreign.write_text('{"profiles":{"local":{"model":"foreign"}}}', encoding="utf-8")
    original = foreign.read_bytes()
    assert app.secrets.load() == {}
    app.secrets.upsert("local", "http://localhost:8090", "own", None)
    assert app.secrets.load()["local"]["model"] == "own"
    assert foreign.read_bytes() == original
    monkeypatch.setattr(app.engine._session, "temporary_root", lambda: tmp_path / "temporales")
    lock = app.engine.RunLock("local", "http://localhost:8090")
    assert lock.path.parent == tmp_path / "temporales" / "locks"
    with lock:
        assert lock.path.is_file()
    assert not lock.path.exists()


def test_variable_api_propia(monkeypatch: pytest.MonkeyPatch) -> None:
    backend = app.engine.Backend("openai", "", "example", 100, 0, 0.2, 10)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANALISISR_API_KEY", raising=False)
    monkeypatch.setenv("VEROSIMIL_API_KEY", "foreign")
    assert backend.resolved_key() is None
    monkeypatch.setenv("ANALISISR_API_KEY", "own")
    assert backend.resolved_key() == "own"


def test_gemini_respeta_clave_propia_y_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    backend = app.engine.Backend("gemini", "https://example.invalid", "example", 100, 0, 0.2, 10)
    for name in ("GEMINI_API_KEY", "GOOGLE_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("ANALISISR_API_KEY", "test-key")
    seen = []

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return json.dumps({"candidates": [{"content": {"parts": [{"text": "ok"}]}}]}).encode()

    def urlopen(request, timeout):
        seen.append(request)
        return Response()

    monkeypatch.setattr(app.engine.urllib.request, "urlopen", urlopen)
    assert backend.chat("system", "user") == "ok"
    assert seen[0].full_url == "https://example.invalid/v1beta/models/example:generateContent?key=test-key"


@pytest.mark.parametrize("platform", ["win32", "linux"])
def test_cifrado_real_no_guarda_clave_en_claro(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, platform: str,
) -> None:
    monkeypatch.setattr(app.secrets, "keyring_disponible", lambda: (False, "test"))
    monkeypatch.setenv("ANALISISR_MASTER_KEY", "test-only-master-key")
    if platform == "win32":
        if not sys.platform.startswith("win"):
            pytest.skip("DPAPI requiere Windows")
        try:
            app.secrets._dpapi(b"test-only", True)
        except OSError as exc:
            pytest.skip(f"DPAPI no disponible en este entorno: {exc}")
    else:
        pytest.importorskip("cryptography")
        monkeypatch.setattr(app.secrets, "sys", SimpleNamespace(platform="linux"))
    path = tmp_path / "backends.json"
    key = "test-only-api-key"
    app.secrets.upsert("openai", "https://example.invalid", "example", key, path)
    assert key not in path.read_text(encoding="utf-8")
    token = app.secrets.load(path)["openai"]["api_key"]
    assert app.secrets.decrypt(token) == key
    app.secrets.upsert("openai", "https://example.invalid", "other", None, path)
    assert app.secrets.load(path)["openai"]["api_key"] == token


def test_fallo_de_cifrado_conserva_perfiles(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "backends.json"
    app.secrets.upsert("local", "http://localhost:8090", "own", None, path)
    original = path.read_bytes()

    def unavailable(*args, **kwargs):
        raise OSError("Cifrado no disponible")

    monkeypatch.setattr(app.secrets, "encrypt", unavailable)
    with pytest.raises(OSError, match="Cifrado no disponible"):
        app.secrets.upsert("openai", "https://example.invalid", "example", "test-key", path)
    assert path.read_bytes() == original
