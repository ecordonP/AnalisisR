"""Sesiones portables, informes Word, diagnóstico y aprobación de R."""
import json
from pathlib import Path
import shutil
import zipfile
from xml.etree import ElementTree as ET

import pytest

import AnalisisR as app
import analisisr_docx as documents
import analisisr_session as sessions


def test_sesion_reabre_datos_y_codigo_sin_depender_del_origen(tmp_path):
    source = tmp_path / "source.csv"
    source.write_text("x,y\n1,10\n2,20\n", encoding="utf-8")
    old = tmp_path / "old"
    old.mkdir()
    operation = old / "operacion_001"
    operation.mkdir()
    profile = app.prepare_data({"data": str(source)}, operation)
    script = operation / "analisis_1.R"
    script.write_text(app.engine.chat_r_script("tabla(dat)", profile), encoding="utf-8")
    app.write_json(operation / "manifest.json", {"schema": "analizar.operation/1", "artifacts": {}})
    state = {"profile": profile, "data_request": {"data": str(source), "keep": ["x", "y"]}, "history": [{"role": "assistant", "content": "Resultado",
                                              "context": "Resultado local", "scripts": [str(script)]}]}
    archive = tmp_path / "saved.analizar"
    sessions.save_session(archive, old, state)
    source.unlink()
    assert old.resolve().is_relative_to(tmp_path.resolve())
    shutil.rmtree(old)
    new = tmp_path / "restored"
    loaded = sessions.load_session(archive, new)
    assert Path(loaded["profile"]["source_file"]).read_text(encoding="utf-8") == "x,y\n1,10\n2,20\n"
    assert Path(loaded["profile"]["data_for_r"]).is_file()
    new_script = Path(loaded["history"][0]["scripts"][0])
    assert new_script.is_file()
    assert str(old) not in new_script.read_text(encoding="utf-8")
    manifest = json.loads((new / "operacion_001" / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["artifacts"][new_script.name]["sha256"] == app.engine.sha256_file(new_script)
    rs = app.engine.find_rscript()
    if rs:
        out, err, code = app.engine.run_process([rs, str(new_script)], timeout=30)
        assert code == 0, out + err
        assert "| x | y |" in out


@pytest.mark.parametrize("entry", ["../escape.txt", "artifacts/../../escape.txt", "C:/escape.txt", "artifacts/..\\escape.txt"])
def test_sesion_rechaza_rutas_fuera_de_su_carpeta(tmp_path, entry):
    archive = tmp_path / "bad.analizar"
    with zipfile.ZipFile(archive, "w") as z:
        z.writestr("session.json", json.dumps({"schema": sessions.SCHEMA, "root": "old", "state": {}}))
        z.writestr(entry, "bad")
    with pytest.raises(ValueError, match="ruta"):
        sessions.load_session(archive, tmp_path / "load")
    assert not (tmp_path / "escape.txt").exists()


def test_error_guardando_sesion_no_sobrescribe_archivo_anterior(tmp_path):
    archive = tmp_path / "saved.analizar"
    archive.write_bytes(b"previous-session")
    folder = tmp_path / "work"
    folder.mkdir()
    with pytest.raises(ValueError, match="origen"):
        sessions.save_session(archive, folder, {"profile": {"source_file": str(tmp_path / "missing.csv")}})
    assert archive.read_bytes() == b"previous-session"


def test_word_conserva_tablas_y_codigo_literal(tmp_path):
    markdown = '## Resultados\n\n| Variable | Media |\n| --- | --- |\n| x | 2 |\n\n### Código R\n\n```r\n  a_b <- 1 < 2\nprint(a_b)\n```'
    output = documents.markdown_to_docx(markdown, tmp_path / "report.docx", titulo="AnalizaR Desktop")
    docx = pytest.importorskip("docx")
    document = docx.Document(output)
    assert document.tables[0].cell(1, 1).text == "2"
    assert "  a_b <- 1 < 2" in [p.text for p in document.paragraphs]
    assert "print(a_b)" in [p.text for p in document.paragraphs]
    with zipfile.ZipFile(output) as z:
        for name in z.namelist():
            if name.endswith((".xml", ".rels")):
                ET.fromstring(z.read(name))


class Backend:
    last_truncated = False

    def __init__(self, responses):
        self.responses = iter(responses)

    def chat(self, system, user):
        return next(self.responses)


def test_codigo_se_ejecuta_directamente_con_r_habilitado(tmp_path, monkeypatch):
    data = tmp_path / "source.csv"
    data.write_text("x\n1\n2\n3\n", encoding="utf-8")
    profile = app.prepare_data({"data": str(data)}, tmp_path)
    monkeypatch.setattr(app.engine, "find_rscript", lambda: "Rscript")
    calls = []
    monkeypatch.setattr(app.engine, "chat_run_r", lambda code, *args, **kw: (calls.append(code) or True, "2"))
    request = {"ask": "Media", "profile": profile, "run_r": True}
    result = app.converse(request, tmp_path, Backend(['```r\nprint(mean(dat$x))\n```']))
    assert calls == ["print(mean(dat$x))"]
    assert "2" in result["answer"]


def test_diagnostico_sin_r_y_con_r_simulado(monkeypatch):
    monkeypatch.setattr(app.engine, "find_rscript", lambda: None)
    assert app.engine.diagnose_r()["rscript"] is None
    monkeypatch.setattr(app.engine, "find_rscript", lambda: "Rscript")
    monkeypatch.setattr(app.engine, "run_process", lambda *a, **kw: (
        "R\tR version test\nLIB\t/library\npsych\t2.5\nlavaan\tNO_INSTALADO\n", "", 0))
    result = app.engine.diagnose_r()
    assert result["version"] == "R version test"
    assert result["libraries"] == ["/library"]
    assert result["packages"][0]["installed"]
    assert not result["packages"][1]["installed"]


def test_diagnostico_real_de_r():
    if not app.engine.find_rscript():
        pytest.skip("Requiere Rscript")
    result = app.engine.diagnose_r()
    assert result["version"].startswith("R version")
    assert {p["package"] for p in result["packages"]} == set(app.engine.DIAGNOSTIC_PACKAGES)


def test_trabajador_ejecuta_codigo_con_r_real_sin_confirmaciones(tmp_path, monkeypatch):
    if not app.engine.find_rscript():
        pytest.skip("Requiere Rscript")
    source = tmp_path / "source.csv"
    source.write_text("x\n1\n2\n3\n", encoding="utf-8")
    folder = tmp_path / "first"
    folder.mkdir()
    profile = app.prepare_data({"data": str(source)}, folder)
    backend = Backend(['```r\ntabla(data.frame(Media=mean(dat$x)))\n```'])
    monkeypatch.setattr(app, "make_backend", lambda request: backend)
    monkeypatch.setattr(app.engine._secrets, "config_dir", lambda: tmp_path / "config")
    request = {"action": "chat", "backend": "local", "host": "http://localhost:8090",
               "ask": "Media", "profile": profile, "run_r": True}
    app.write_json(folder / "request.json", request)
    assert app.worker(folder / "request.json") == 0
    result = json.loads((folder / "result.json").read_text(encoding="utf-8"))
    assert "| Media |" in result["answer"] and "| 2 |" in result["answer"]
    assert Path(result["scripts"][-1]).is_file()


def test_una_sesion_del_nombre_anterior_sigue_abriendose(tmp_path):
    """El esquema analisisr.session/1 debe seguir cargando tras el cambio de nombre."""
    import json
    import zipfile

    import analisisr_session as sessions

    folder = tmp_path / "trabajo"
    folder.mkdir()
    estado = {"profile": None, "history": [],
              "endpoint": {"backend": "none", "host": "", "model": "", "max_tokens": 1000, "timeout": 60},
              "question": ""}
    antigua = tmp_path / "vieja.analisisr"
    with zipfile.ZipFile(antigua, "w") as archivo:
        archivo.writestr("session.json", json.dumps(
            {"schema": "analisisr.session/1", "root": str(folder), "state": estado,
             "source": None, "source_entry": None}, ensure_ascii=False))
    destino = tmp_path / "destino"
    destino.mkdir()
    assert sessions.load_session(antigua, destino)["endpoint"]["backend"] == "none"


def test_la_configuracion_del_nombre_anterior_se_migra(tmp_path, monkeypatch):
    """Sin esto el cambio de nombre dejaría atrás los perfiles y la ruta de R guardadas."""
    import analisisr_secrets as secrets

    monkeypatch.setenv("APPDATA", str(tmp_path))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.setattr(secrets.os.path, "expanduser", lambda path: str(tmp_path))
    antigua = tmp_path / secrets.LEGACY_APP_DIR_NAME
    antigua.mkdir()
    (antigua / "backends.json").write_text('{"profiles": {"deepseek": {"model": "x"}}}', encoding="utf-8")
    (antigua / "entorno_r.json").write_text('{"r_home": "C:/R"}', encoding="utf-8")
    nueva = secrets.config_dir()
    assert nueva.name == secrets.APP_DIR_NAME
    assert secrets.load() == {"deepseek": {"model": "x"}}
    assert (nueva / "entorno_r.json").is_file()
    # El original no se toca: si el usuario vuelve a la versión anterior, sigue ahí.
    assert (antigua / "backends.json").is_file()
