"""Plantilla de normalidad: el usuario elige las pruebas de MVN y el prompt usa sus códigos."""
import os

import pytest

import AnalisisR as app

MULTIVARIANTES = ["Mardia (mardia)", "Henze-Zirkler (hz)", "Henze-Wagner (hw)",
                  "Royston (royston)", "Doornik-Hansen (doornik_hansen)", "Energía (energy)"]
UNIVARIANTES = ["Shapiro-Wilk (SW)", "Shapiro-Francia (SF)", "Anderson-Darling (AD)",
                "Cramér-von Mises (CVM)", "Lilliefors (Lillie)"]


def test_el_prompt_pide_las_pruebas_elegidas_con_los_codigos_de_mvn():
    prompt = app.TEMPLATES["Normalidad"]
    for pieza in ("requireNamespace('MVN', quietly=TRUE)", "mvn_test", "univariate_test",
                  "multivariate_normality", "univariate_normality", "descriptives",
                  "Calcula exactamente las pedidas", "no mvnTest"):
        assert pieza in prompt, pieza
    # Los códigos válidos en MVN 6.3, comprobados contra el paquete instalado.
    for codigo in ("mardia", "hz", "hw", "royston", "doornik_hansen", "energy",
                   "SW", "SF", "AD", "CVM", "Lillie"):
        assert codigo in prompt, codigo
    # La misma defensa que en las demás plantillas frente al p de texto.
    assert "sub('>', '', sub('<', '', trimws(as.character(p.value))))" in prompt
    assert "isTRUE()" in prompt and "TRUE/FALSE es necesario" in prompt


def test_el_prompt_explica_cada_prueba_y_sus_limites():
    prompt = app.TEMPLATES["Normalidad"]
    for pieza in ("asimetría y la curtosis multivariantes", "entre 3 y\n", "bootstrap",
                  "set.seed", "no coinciden en su conclusión", "los residuos del modelo",
                  "outlier_seed", "sin eliminar ningún caso"):
        assert pieza.strip() in prompt, pieza


@pytest.fixture
def ventana(tmp_path, monkeypatch):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    pytest.importorskip("PySide6")
    import analisisr_ui as ui
    import analisisr_session as sessions

    qt = ui.QApplication.instance() or ui.QApplication([])
    monkeypatch.setattr(app.secrets, "load", lambda: {})
    monkeypatch.setattr(app.secrets, "config_dir", lambda: tmp_path / "config")
    monkeypatch.setattr(app.engine, "find_rscript", lambda: "Rscript")
    monkeypatch.setattr(sessions, "temporary_root", lambda: tmp_path)
    mkdtemp = sessions.tempfile.mkdtemp
    monkeypatch.setattr(sessions.tempfile, "mkdtemp",
                        lambda *a, **kw: mkdtemp(*a, **{**kw, "dir": tmp_path}))
    monkeypatch.setattr(ui.Proc, "start", lambda *args, **kwargs: None)
    view = app.create_window()
    source = view.folder / "escala.csv"
    source.write_text("x,y,z\n1,2,3\n2,4,5\n3,5,8\n4,7,9\n", encoding="utf-8")
    view.loaded(app.prepare_data({"data": str(source)}, view.folder))
    view.applied_request = view.data_request()
    view.templates.setCurrentText("Normalidad")
    yield view, ui
    view.close()
    qt.processEvents()


def test_el_formulario_ofrece_las_pruebas_disponibles_en_mvn(ventana, monkeypatch):
    view, ui = ventana
    ofrecidas = {}

    def inspeccionar(dialog):
        for lista in dialog.findChildren(ui.QListWidget):
            nombre = lista.objectName()
            ofrecidas[nombre] = [lista.item(i).text() for i in range(lista.count())]
            assert lista.selectionMode() == ui.QAbstractItemView.MultiSelection
        dialog.reject()
        return dialog.result()

    monkeypatch.setattr(ui.QDialog, "exec", inspeccionar)
    view.use_template()
    assert ofrecidas["pruebas_multivariantes"] == MULTIVARIANTES
    assert ofrecidas["pruebas_univariantes"] == UNIVARIANTES
    # Las variables siguen siendo las columnas de los datos.
    assert ofrecidas["variables"] == ["x", "y", "z"]
    assert view.question.toPlainText() == ""


def test_la_consulta_recoge_solo_las_pruebas_seleccionadas(ventana, monkeypatch):
    view, ui = ventana
    avisos = []
    monkeypatch.setattr(ui.QMessageBox, "information", lambda *args: avisos.append(args[-1]))

    def elegir(dialog):
        dialog.findChild(ui.QListWidget, "variables").item(0).setSelected(True)
        dialog.findChild(ui.QListWidget, "variables").item(1).setSelected(True)
        multi = dialog.findChild(ui.QListWidget, "pruebas_multivariantes")
        multi.item(0).setSelected(True)   # Mardia
        multi.item(3).setSelected(True)   # Royston
        dialog.findChild(ui.QListWidget, "pruebas_univariantes").item(2).setSelected(True)  # AD
        dialog.findChild(ui.QDialogButtonBox).accepted.emit()
        return dialog.result()

    monkeypatch.setattr(ui.QDialog, "exec", elegir)
    view.use_template()
    consulta = view.question.toPlainText()
    assert not avisos
    assert "Pruebas multivariantes solicitadas: Mardia (mardia), Royston (royston)." in consulta
    assert "Pruebas univariantes solicitadas: Anderson-Darling (AD)." in consulta
    assert "de x, y con el paquete MVN" in consulta
    # El prompt explica todas las pruebas; lo exclusivo son las líneas de lo solicitado.
    import re

    pedidas = re.search(r"Pruebas multivariantes solicitadas: (.+?)\. Pruebas univariantes "
                        r"solicitadas: (.+?)\.", consulta, re.S)
    assert pedidas.group(1) == "Mardia (mardia), Royston (royston)"
    assert pedidas.group(2) == "Anderson-Darling (AD)"
    assert "[" not in consulta and "]" not in consulta


def test_una_sola_variable_no_permite_pruebas_multivariantes(ventana, monkeypatch):
    view, ui = ventana
    avisos = []
    monkeypatch.setattr(ui.QMessageBox, "information", lambda *args: avisos.append(args[-1]))

    def elegir(dialog):
        dialog.findChild(ui.QListWidget, "variables").item(0).setSelected(True)
        dialog.findChild(ui.QListWidget, "pruebas_multivariantes").item(1).setSelected(True)
        dialog.findChild(ui.QListWidget, "pruebas_univariantes").item(0).setSelected(True)
        dialog.findChild(ui.QDialogButtonBox).accepted.emit()
        return dialog.result()

    monkeypatch.setattr(ui.QDialog, "exec", elegir)
    view.use_template()
    assert view.question.toPlainText() == ""
    assert avisos and "al menos 2" in avisos[0]


def test_sin_elegir_pruebas_no_se_prepara_la_consulta(ventana, monkeypatch):
    view, ui = ventana
    avisos = []
    monkeypatch.setattr(ui.QMessageBox, "information", lambda *args: avisos.append(args[-1]))

    def elegir(dialog):
        for i in (0, 1):
            dialog.findChild(ui.QListWidget, "variables").item(i).setSelected(True)
        dialog.findChild(ui.QDialogButtonBox).accepted.emit()
        return dialog.result()

    monkeypatch.setattr(ui.QDialog, "exec", elegir)
    view.use_template()
    assert view.question.toPlainText() == ""
    assert avisos and "Pruebas" in avisos[0]
