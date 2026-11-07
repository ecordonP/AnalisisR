"""Limpieza de archivos propios conservando una sesión utilizable en memoria."""
from pathlib import Path

import pytest

import AnalisisR as app
import analisisr_session as sessions


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    mkdtemp = sessions.tempfile.mkdtemp

    def local_temp(*args, **kwargs):
        kwargs.setdefault("dir", tmp_path)
        return mkdtemp(*args, **kwargs)

    monkeypatch.setattr(sessions.tempfile, "mkdtemp", local_temp)
    monkeypatch.setattr(sessions, "temporary_root", lambda: tmp_path)
    work = sessions.SessionWorkspace()
    yield work
    work.folder = work._root
    work.close()


def test_limpia_y_restaura_datos_binarios_scripts_y_registros(workspace):
    root = workspace.folder
    (root / "datos.bin").write_bytes(b"\x00\xff\x01")
    operation = root / "operacion_001"
    operation.mkdir()
    script = operation / "analisis_1.R"
    script.write_text("tabla(dat)\n", encoding="utf-8")
    workspace.suspend()
    assert not root.exists()
    assert workspace.read_text(script) == "tabla(dat)\n"
    workspace.restore()
    assert (root / "datos.bin").read_bytes() == b"\x00\xff\x01"
    assert script.read_text() == "tabla(dat)\n"
    (root / "salida.txt").write_text("Segundo análisis", encoding="utf-8")
    workspace.suspend()
    assert not root.exists() and workspace.read_text(root / "salida.txt") == "Segundo análisis"
    assert workspace.read_text(script) == "tabla(dat)\n"


def test_no_borra_otras_sesiones_ni_archivos_originales(workspace, tmp_path):
    other = sessions.SessionWorkspace()
    source = tmp_path / "original.csv"
    source.write_text("x\n1\n", encoding="utf-8")
    try:
        (other.folder / "activo.txt").write_text("otra instancia")
        workspace.close()
        assert source.read_text() == "x\n1\n"
        assert (other.folder / "activo.txt").read_text() == "otra instancia"
        workspace.folder = tmp_path
        with pytest.raises(ValueError, match="no coincide"):
            workspace.close()
        assert source.exists()
    finally:
        other.close()


def test_error_de_copia_no_borra_archivos(workspace, monkeypatch):
    path = workspace.folder / "datos.csv"
    path.write_text("x\n1\n", encoding="utf-8")
    monkeypatch.setattr(Path, "read_bytes", lambda *a: (_ for _ in ()).throw(OSError("lectura fallida")))
    with pytest.raises(OSError, match="lectura fallida"):
        workspace.suspend()
    assert path.exists()


def test_sesion_se_guarda_y_reabre_despues_de_limpiar(workspace, tmp_path):
    source = tmp_path / "source.csv"
    source.write_text("x,y\n1,2\n2,3\n", encoding="utf-8")
    profile = app.prepare_data({"data": str(source)}, workspace.folder)
    state = {"profile": profile, "data_request": {"data": str(source), "keep": ["x", "y"]}}
    workspace.suspend()
    assert not workspace.folder.exists()
    workspace.restore()
    archive = tmp_path / "saved.analizar"
    sessions.save_session(archive, workspace.folder, state)
    workspace.suspend()
    loaded = sessions.load_session(archive, tmp_path / "loaded")
    assert Path(loaded["profile"]["data_for_r"]).is_file()
    workspace.close()
    assert archive.is_file() and source.is_file() and not workspace.files


def test_r_funciona_tras_restaurar_y_limpia_su_carpeta_auxiliar(workspace, tmp_path):
    rs = app.engine.find_rscript()
    if not rs:
        pytest.skip("Requiere Rscript")
    source = tmp_path / "source.csv"
    source.write_text("x\n1\n2\n3\n", encoding="utf-8")
    profile = app.prepare_data({"data": str(source)}, workspace.folder)
    workspace.suspend()
    workspace.restore()
    ok, output = app.engine.chat_run_r("tabla(data.frame(Media=mean(dat$x)))", profile, rs, temp_dir=workspace.folder)
    assert ok and "| 2 |" in output
    assert not list(workspace.folder.glob("analizar_chat_r_*"))
    workspace.suspend()
    assert not workspace.folder.exists()


def test_entorno_temporal_apunta_al_directorio_de_la_operacion(tmp_path, monkeypatch):
    import os

    root = tmp_path / "temporales"
    root.mkdir()
    monkeypatch.setattr(sessions, "temporary_root", lambda: root)
    monkeypatch.setattr(sessions.tempfile, "tempdir", sessions.tempfile.tempdir)
    for name in ("TEMP", "TMP", "TMPDIR"):
        monkeypatch.setenv(name, os.environ.get(name, ""))
    operation = root / "AnalizaR Desktop_test" / "operacion_001"
    sessions.configure_temporaries(operation)
    assert sessions.tempfile.gettempdir() == str(operation.resolve())
    assert all(os.environ[name] == str(operation.resolve()) for name in ("TEMP", "TMP", "TMPDIR"))


def test_temporales_congelados_estan_junto_al_ejecutable(tmp_path, monkeypatch):
    monkeypatch.setattr(sessions.sys, "frozen", True, raising=False)
    monkeypatch.setattr(sessions.sys, "executable", str(tmp_path / "AnalizaR.exe"))
    assert sessions.temporary_root() == tmp_path / "temporales"


def test_guardar_en_otra_unidad_conserva_archivos_existentes(workspace, tmp_path, monkeypatch):
    import errno

    def cross_device(*args):
        raise OSError(errno.EXDEV, "otra unidad")

    monkeypatch.setattr(sessions.os, "replace", cross_device)
    saved = tmp_path / "saved.analizar"
    saved.write_bytes(b"sesion anterior")
    with pytest.raises(FileExistsError):
        sessions.save_session(saved, workspace.folder, {})
    assert saved.read_bytes() == b"sesion anterior"
    other = tmp_path / "new.analizar"
    sessions.save_session(other, workspace.folder, {})
    assert sessions.load_session(other, tmp_path / "loaded") == {}
    assert not list(workspace.folder.glob("*.tmp"))
