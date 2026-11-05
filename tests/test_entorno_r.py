"""Detección del R del sistema, ruta configurable y bloqueo de la app sin R."""
import os
from pathlib import Path
import re

import pytest

import AnalisisR as app
import analisisr_core as engine


def fake_r(home: Path, subdir: str = "bin") -> Path:
    """Instalación mínima de R: solo hace falta que exista Rscript."""
    binario = home / subdir / engine.RSCRIPT_NAME
    binario.parent.mkdir(parents=True, exist_ok=True)
    binario.write_text("", encoding="utf-8")
    return binario


@pytest.fixture
def aislado(tmp_path, monkeypatch):
    """Sin R en el entorno ni en el PATH, y con configuración propia."""
    monkeypatch.setattr(engine._secrets, "config_dir", lambda: tmp_path / "config")
    monkeypatch.delenv("R_HOME", raising=False)
    monkeypatch.setenv("PATH", str(tmp_path / "vacio"))
    monkeypatch.setattr(engine, "detected_r_homes", lambda: [])
    return tmp_path


def test_sin_r_no_se_encuentra_rscript(aislado):
    assert engine.find_rscript() is None


def test_r_home_tiene_prioridad_sobre_la_ruta_configurada(aislado, monkeypatch):
    preferido = fake_r(aislado / "entorno")
    engine.save_r_home(str(aislado / "configurado"))
    fake_r(aislado / "configurado")
    monkeypatch.setenv("R_HOME", str(aislado / "entorno"))
    assert Path(engine.find_rscript()) == preferido


def test_la_ruta_configurada_se_guarda_y_se_usa(aislado):
    esperado = fake_r(aislado / "elegido")
    engine.save_r_home(str(aislado / "elegido"))
    assert engine.configured_r_home() == str(aislado / "elegido")
    assert Path(engine.find_rscript()) == esperado
    engine.save_r_home("")
    assert engine.configured_r_home() == ""
    assert engine.find_rscript() is None


def test_se_detecta_en_el_path_y_en_las_instalaciones_del_sistema(aislado, monkeypatch):
    en_path = fake_r(aislado / "deP")
    monkeypatch.setenv("PATH", str(en_path.parent))
    assert Path(engine.find_rscript()) == en_path
    monkeypatch.setenv("PATH", str(aislado / "vacio"))
    detectado = fake_r(aislado / "detectado", "bin/x64" if os.name == "nt" else "bin")
    monkeypatch.setattr(engine, "detected_r_homes", lambda: [aislado / "detectado"])
    assert Path(engine.find_rscript()) == detectado


def test_nunca_se_usa_un_r_empaquetado():
    """El paquete no incluye R: no debe quedar rastro de la búsqueda interna."""
    assert not hasattr(engine, "bundled_r_home")
    spec = (Path(__file__).resolve().parents[1] / "AnalisisR_onedir.spec").read_text(encoding="utf-8")
    for rastro in ("runtime/R", r"runtime\R", "library-user", "copy_runtime", "find_rscript"):
        assert rastro not in spec, rastro


def test_la_guia_y_el_diagnostico_declaran_las_mismas_librerias():
    """Lo que la guía promete comprobar es exactamente lo que comprueba el diagnóstico."""
    guia = (Path(__file__).resolve().parents[1] / "assets" / "guia.html").read_text(encoding="utf-8")
    bloque = re.search(r'<p id="paquetes-comprobados">(.*?)</p>', guia, re.S)
    assert bloque, "La guía debe listar las bibliotecas comprobadas en #paquetes-comprobados."
    assert set(re.findall(r"<code>([^<]+)</code>", bloque.group(1))) == set(engine.DIAGNOSTIC_PACKAGES)
    # Ningún ejemplo de la guía puede recomendar algo que el diagnóstico no verifique.
    for ejemplo in re.findall(r"install\.packages\(c\((.*?)\)", guia, re.S):
        assert set(re.findall(r'"([^"]+)"', ejemplo)) <= set(engine.DIAGNOSTIC_PACKAGES)


def test_el_diagnostico_declara_si_estan_todas_las_librerias(ventana):
    view, _ = ventana
    comprobadas = [{"package": name, "version": "1.0", "installed": True}
                   for name in engine.DIAGNOSTIC_PACKAGES]
    view.show_diagnosis({"version": "R version test", "rscript": "Rscript",
                         "libraries": ["/library"], "packages": comprobadas})
    assert "Todas las bibliotecas requeridas están disponibles" in view.r_state.text()
    assert "están instaladas" in view.r_install.toPlainText()
    comprobadas[4] = dict(comprobadas[4], version="NO_INSTALADO", installed=False)
    view.show_diagnosis({"version": "R version test", "rscript": "Rscript",
                         "libraries": ["/library"], "packages": comprobadas})
    ausente = engine.DIAGNOSTIC_PACKAGES[4]
    assert f"Faltan 1 de {len(comprobadas)}" in view.r_state.text()
    assert ausente in view.r_state.text() and ausente in view.r_install.toPlainText()


@pytest.fixture
def ventana(tmp_path, monkeypatch):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    pytest.importorskip("PySide6")
    import analisisr_ui as ui
    import analisisr_session as sessions

    qt = ui.QApplication.instance() or ui.QApplication([])
    monkeypatch.setattr(app.secrets, "load", lambda: {})
    monkeypatch.setattr(app.secrets, "config_dir", lambda: tmp_path / "config")
    monkeypatch.setattr(engine._secrets, "config_dir", lambda: tmp_path / "config")
    monkeypatch.setattr(sessions, "temporary_root", lambda: tmp_path)
    monkeypatch.setattr(ui.Proc, "start", lambda *args, **kwargs: None)
    mkdtemp = sessions.tempfile.mkdtemp
    monkeypatch.setattr(sessions.tempfile, "mkdtemp",
                        lambda *a, **kw: mkdtemp(*a, **{**kw, "dir": tmp_path}))
    # Aislamiento real en vez de simular find_rscript: así se prueba la detección entera.
    monkeypatch.delenv("R_HOME", raising=False)
    monkeypatch.setenv("PATH", str(tmp_path / "vacio"))
    monkeypatch.setattr(engine, "detected_r_homes", lambda: [])
    view = app.create_window()
    yield view, ui
    view.close()
    qt.processEvents()


def test_sin_r_solo_queda_la_pestana_de_entorno(ventana):
    view, _ = ventana
    assert not view.r_ready
    assert view.tabs.isTabEnabled(0) and view.tabs.widget(0) is view.environment_page
    for index in range(1, view.tabs.count()):
        assert not view.tabs.isTabEnabled(index)
        assert not view.tabs.widget(index).isEnabled()
    assert "no puede funcionar sin él" in view.r_state.text()
    texto = view.r_install.toPlainText()
    assert "install.packages" in texto
    for name in ("lavaan", "coefficientalpha", "haven"):
        assert name in texto


def test_sin_r_no_se_lanza_ninguna_operacion(ventana, monkeypatch):
    view, ui = ventana
    avisos = []
    monkeypatch.setattr(ui.QMessageBox, "warning", lambda *args: avisos.append(args[2]))
    view.start("profile", {}, lambda _: None)
    assert view.proc is None and avisos and "Sin R" in avisos[0]
    view.start("chat", {}, lambda _: None)
    assert view.proc is None and len(avisos) == 2


def test_indicar_la_carpeta_de_r_desbloquea_la_aplicacion(ventana, tmp_path):
    view, _ = ventana
    fake_r(tmp_path / "R-4.6.1")
    view.r_home.setText(str(tmp_path / "R-4.6.1"))
    view.refresh_r()
    assert view.r_ready and engine.configured_r_home() == str(tmp_path / "R-4.6.1")
    for index in range(view.tabs.count()):
        assert view.tabs.isTabEnabled(index) and view.tabs.widget(index).isEnabled()


def test_ruta_sin_rscript_se_rechaza_con_aviso(ventana, tmp_path, monkeypatch):
    view, ui = ventana
    avisos = []
    monkeypatch.setattr(ui.QMessageBox, "warning", lambda *args: avisos.append(args[2]))
    (tmp_path / "no-es-r").mkdir()
    view.r_home.setText(str(tmp_path / "no-es-r"))
    view.refresh_r()
    assert avisos and engine.RSCRIPT_NAME in avisos[0]
    assert not view.r_ready
