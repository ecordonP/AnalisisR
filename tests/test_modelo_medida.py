"""Definición de variables latentes y consulta de AFC con validez discriminante."""
import json
import os
import re

import pytest

import AnalisisR as app


@pytest.fixture
def constructor(monkeypatch):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    pytest.importorskip("PySide6")
    import analisisr_ui as ui

    ui.QApplication.instance() or ui.QApplication([])
    widget = ui.FactorBuilder(["a1", "a2", "a3", "b1", "b2", "b3"])
    avisos = []
    monkeypatch.setattr(widget, "aviso", avisos.append)
    return widget, avisos


def añadir(widget, nombre, indicadores):
    widget.name.setText(nombre)
    widget.items.clearSelection()
    for fila in range(widget.items.count()):
        if widget.items.item(fila).text() in indicadores:
            widget.items.item(fila).setSelected(True)
    return widget.add_factor()


def test_dos_latentes_con_sus_indicadores(constructor):
    widget, avisos = constructor
    assert añadir(widget, "Calidad", ["a1", "a2", "a3"])
    assert añadir(widget, "Lealtad", ["b1", "b2"])
    assert not avisos
    assert widget.factors == [("Calidad", ["a1", "a2", "a3"]), ("Lealtad", ["b1", "b2"])]
    assert widget.text() == "Calidad medida por a1, a2 y a3; Lealtad medida por b1 y b2"
    assert widget.summary.count() == 2


def test_un_indicador_no_puede_estar_en_dos_latentes(constructor):
    widget, avisos = constructor
    añadir(widget, "Calidad", ["a1", "a2"])
    assert not añadir(widget, "Lealtad", ["a2", "b1"])
    assert "ya pertenecen a otra variable latente: a2" in avisos[0]
    assert len(widget.factors) == 1


@pytest.mark.parametrize("nombre,indicadores,mensaje", [
    ("", ["a1", "a2"], "debe empezar por una letra"),
    ("2factor", ["a1", "a2"], "debe empezar por una letra"),
    ("a1", ["a2", "a3"], "no puede coincidir con una columna"),
    ("Calidad", ["a1"], "al menos dos indicadores"),
])
def test_definiciones_invalidas_se_rechazan(constructor, nombre, indicadores, mensaje):
    widget, avisos = constructor
    assert not añadir(widget, nombre, indicadores)
    assert mensaje in avisos[0] and widget.factors == []


def test_nombre_repetido_se_rechaza(constructor):
    widget, avisos = constructor
    añadir(widget, "Calidad", ["a1", "a2"])
    assert not añadir(widget, "Calidad", ["b1", "b2"])
    assert "Ya existe una variable latente con ese nombre" in avisos[0]


def test_quitar_una_latente_mantiene_el_resto(constructor):
    widget, _ = constructor
    añadir(widget, "Calidad", ["a1", "a2"])
    añadir(widget, "Lealtad", ["b1", "b2"])
    widget.summary.setCurrentRow(0)
    widget.remove_factor()
    assert [n for n, _ in widget.factors] == ["Lealtad"]
    assert widget.summary.count() == 1


def test_el_prompt_de_afc_pide_htmt_con_intervalos_y_api_valida():
    prompt = app.TEMPLATES["Análisis factorial confirmatorio"]
    for pieza in ("htmt2=FALSE", "htmt2=TRUE", "boot::boot", "conf=0.90",
                  "compRelSEM(ajuste, simplify=TRUE)", "cor.lv", "Fornell-Larcker",
                  "lavTestLRT", "0,85", "0,90", "0,50", "0,70"):
        assert pieza in prompt, pieza
    # El argumento que hizo fallar un análisis real no debe volver a sugerirse.
    assert "type='correlation'" in prompt and "no existe" in prompt
    assert "cor_bentler" in prompt


@pytest.mark.parametrize("name", ["Análisis factorial confirmatorio", "Invarianza de medida"])
def test_los_prompts_de_medida_exigen_normalidad_multivariante_y_regla_de_estimador(name):
    """Misma regla en ambas: Mardia y Henze-Zirkler con MVN, y estimador justificado."""
    prompt = app.TEMPLATES[name]
    for pieza in ("requireNamespace('MVN', quietly=TRUE)", "mvn_test='mardia'", "mvn_test='hz'",
                  "multivariate_normality", "mvn_test y no", "ordered=", "MLR", "isTRUE()",
                  "sub('>', '', sub('<', '', trimws(as.character(p.value))))",
                  "TRUE/FALSE es necesario", "grepl('Not normal'"):
        assert pieza in prompt, (name, pieza)
    assert "MVN" in app.engine.DIAGNOSTIC_PACKAGES


def test_la_invarianza_evalua_la_normalidad_dentro_de_cada_grupo():
    prompt = app.TEMPLATES["Invarianza de medida"]
    assert "dentro de cada grupo por separado" in prompt
    assert "MVN::mvn(subset(dat, grupo == nivel, select = columnas), mvn_test='mardia')" in prompt
    # Un estimador único para toda la secuencia: un grupo no normal basta para fijar MLR.
    assert "Si algún grupo la rechaza" in prompt and "no mezcles estimadores" in prompt


def test_el_prompt_de_afc_exige_normalidad_multivariante_y_regla_de_estimador():
    prompt = app.TEMPLATES["Análisis factorial confirmatorio"]
    for pieza in ("mvn_test='mardia'", "mvn_test='hz'",
                  "multivariate_normality", "univariate_normality", "descriptives",
                  "mvn_test y no", "estimator='WLSMV'", "ordered=", "estimator='MLR'",
                  "requireNamespace('MVN', quietly=TRUE)"):
        assert pieza in prompt, pieza
    # Las limitaciones deben citar los intervalos de las dos razones.
    assert "intervalos del HTMT y " in prompt and "del HTMT2" in prompt
    # El diagnóstico tiene que comprobar el paquete que el prompt exige.
    assert "MVN" in app.engine.DIAGNOSTIC_PACKAGES


def test_plantilla_de_afc_se_rellena_con_las_latentes_definidas(tmp_path, monkeypatch):
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
    window = app.create_window()
    try:
        source = window.folder / "escala.csv"
        source.write_text("a1,a2,a3,b1,b2\n1,2,3,4,5\n2,3,4,5,6\n3,4,5,6,7\n", encoding="utf-8")
        window.loaded(app.prepare_data({"data": str(source)}, window.folder))
        window.applied_request = window.data_request()
        avisos = []
        monkeypatch.setattr(ui.QMessageBox, "information", lambda *args: avisos.append(args[-1]))

        def definir(dialog):
            builder = dialog.findChild(ui.FactorBuilder)
            añadir(builder, "Calidad", ["a1", "a2", "a3"])
            añadir(builder, "Lealtad", ["b1", "b2"])
            dialog.findChild(ui.QDialogButtonBox).accepted.emit()
            return dialog.result()

        monkeypatch.setattr(ui.QDialog, "exec", definir)
        window.templates.setCurrentText("Análisis factorial confirmatorio")
        window.use_template()
        assert window.proc is not None
        carpeta = window.folder / f"operacion_{window.job:03d}"
        consulta = json.loads((carpeta / "request.json").read_text(encoding="utf-8"))["ask"]
        assert not avisos
        assert window.question.toPlainText() == ""
        app.write_json(carpeta / "result.json", {"answer": "Resultado"})
        window.proc.done.emit(0)
        assert "Calidad medida por a1, a2 y a3; Lealtad medida por b1 y b2" in consulta
        assert "[" not in consulta and "]" not in consulta

        # Sin definir ninguna latente no se envía nada.

        def sin_definir(dialog):
            dialog.findChild(ui.QDialogButtonBox).accepted.emit()
            return dialog.result()

        monkeypatch.setattr(ui.QDialog, "exec", sin_definir)
        window.use_template()
        assert window.proc is None
        assert "al menos una variable latente" in avisos[-1]
    finally:
        window.close()
        qt.processEvents()


@pytest.mark.parametrize("name", ["Análisis factorial confirmatorio", "Consistencia interna",
                                  "Invarianza de medida", "Mediación"])
def test_las_plantillas_de_lavaan_evitan_las_trampas_del_objeto_s4(name):
    """Comprobado en R: sin adjuntar el paquete, nobs() y coef() fallan sobre el ajuste."""
    prompt = app.TEMPLATES[name]
    for pieza in ("lavaan::", "no se pudo encontrar la función",
                  "no 'nobs' method is available", "lavInspect(ajuste, 'ntotal')",
                  "lavInspect(ajuste, 'boot')", "argumento tiene longitud cero",
                  "número diferente de filas"):
        assert pieza in prompt, (name, pieza)
