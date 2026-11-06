"""Navegación estable y resultados de conexión en la pestaña de endpoints."""
import json
import os
from pathlib import Path

import pytest

import AnalisisR as app

# Ruta real de Rscript antes de cualquier parche: la ventana se prueba con y sin R.
RSCRIPT = app.engine.find_rscript()

def enviado(window):
    """Consulta que ha recibido el endpoint en la última operación."""
    carpeta = window.folder / f"operacion_{window.job:03d}"
    return json.loads((carpeta / "request.json").read_text(encoding="utf-8"))["ask"]


def cerrar(window, answer="Resultado"):
    """Cierra la operación en curso para poder lanzar la siguiente."""
    app.write_json(window.folder / f"operacion_{window.job:03d}" / "result.json", {"answer": answer})
    window.proc.done.emit(0)



@pytest.fixture
def window(tmp_path, monkeypatch):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    pytest.importorskip("PySide6")
    import analisisr_ui as ui
    import analisisr_session as sessions

    qt = ui.QApplication.instance() or ui.QApplication([])
    qt.setStyle("Fusion")
    qt.setStyleSheet(ui.QSS)
    monkeypatch.setattr(app.secrets, "load", lambda: {})
    monkeypatch.setattr(app.engine, "find_rscript", lambda: RSCRIPT or "Rscript")
    monkeypatch.setattr(app.secrets, "config_dir", lambda: tmp_path / "config")
    monkeypatch.setattr(ui.Proc, "start", lambda *args, **kwargs: None)
    mkdtemp = sessions.tempfile.mkdtemp

    def local_temp(*args, **kwargs):
        kwargs.setdefault("dir", tmp_path)
        return mkdtemp(*args, **kwargs)

    monkeypatch.setattr(sessions.tempfile, "mkdtemp", local_temp)
    monkeypatch.setattr(sessions, "temporary_root", lambda: tmp_path)
    view = app.create_window()
    view.show()
    qt.processEvents()
    yield view
    view.close()
    qt.processEvents()


@pytest.mark.parametrize("tab,action", [(1, "profile"), (2, "probe"), (3, "chat")])
def test_operacion_no_cambia_pestana_y_permite_navegar(window, tab, action, monkeypatch):
    window.tabs.setCurrentIndex(tab)
    result = {"kind": "local", "host": "http://localhost:8090", "model_alias": "test-model"}
    monkeypatch.setattr(window, "data_request", lambda: {})
    request = window.endpoint()
    window.start(action, request, window.show_probe)
    assert window.proc is not None
    assert window.tabs.currentIndex() == tab
    assert all(window.tabs.isTabEnabled(index) for index in range(4))
    assert not window.tabs.widget(1).isEnabled()
    assert not window.tabs.widget(2).isEnabled()
    selected = 1 + (tab % 3)
    window.tabs.setCurrentIndex(selected)
    folder = window.folder / "operacion_001"
    app.write_json(folder / "result.json", result)
    window.proc.done.emit(0)
    assert window.tabs.currentIndex() == selected
    assert window.proc is None
    assert window.tabs.widget(1).isEnabled()
    assert window.tabs.widget(2).isEnabled()
    assert window.send.isEnabled()


@pytest.mark.parametrize("error", [None, "HTTP 401: clave rechazada"])
def test_prueba_endpoint_informa_exito_y_error_en_su_pestana(window, error):
    window.tabs.setCurrentIndex(2)
    request = dict(window.endpoint(), action="probe")
    window.start("probe", request, window.show_probe)
    assert "Comprobando" in window.probe_result.toPlainText()
    result = ({"error": error} if error else {
        "kind": "local", "host": "http://localhost:8090", "model_alias": "test-model", "n_ctx": 8192,
    })
    app.write_json(window.folder / "operacion_001" / "result.json", result)
    window.proc.done.emit(1 if error else 0)
    text = window.probe_result.toPlainText()
    assert window.tabs.currentIndex() == 2
    assert "Proveedor:" in text and "URL:" in text and "Modelo configurado:" in text
    if error:
        assert "No se pudo conectar" in text and error in text
    else:
        assert "Conexión correcta" in text and "test-model" in text and "8192" in text


def test_modelo_no_listado_se_muestra_como_aviso_y_se_limpia_al_editar(window):
    window.show_probe({"kind": "openai", "host": "https://example.invalid", "model": "other",
                       "available_models": ["model-a", "model-b"], "warning": "Modelo no listado"})
    text = window.probe_result.toPlainText()
    assert "model-a, model-b" in text and "Aviso: Modelo no listado" in text
    assert "Modelo informado por el servidor: No informado" in text
    window.model.setText("new-model")
    assert window.probe_result.toPlainText() == ""


def test_botones_compactos(window):
    import analisisr_ui as ui

    for index in range(window.tabs.count()):
        window.tabs.setCurrentIndex(index)
        ui.QApplication.processEvents()
        for button in window.tabs.widget(index).findChildren(ui.QPushButton):
            assert button.height() <= 36
            assert button.width() < window.tabs.width() / 2


def test_salida_se_renderiza_como_tabla_con_el_estilo_de_la_aplicacion(window):
    import analisisr_ui as ui

    window.answered("Descriptivos", {
        "answer": "| Variable | Media |\n| --- | --- |\n| Edad | 42.5 |",
    })
    tables = [frame for frame in window.chat.document().rootFrame().childFrames()
              if isinstance(frame, ui.QTextTable)]
    assert len(tables) == 1
    table = tables[0]
    assert table.rows() == 2 and table.columns() == 2
    assert table.cellAt(1, 1).firstCursorPosition().block().text() == "42.5"
    style = table.format()
    assert style.border() == 1
    assert style.borderStyle() == ui.QTextFrameFormat.BorderStyle_Solid
    assert style.borderBrush().color().name() == "#94a3b8"
    assert style.borderCollapse()
    assert style.cellPadding() == 5
    assert style.cellSpacing() == 0


def test_salida_de_consola_se_convierte_en_tabla_editable_de_word(window):
    import analisisr_ui as ui
    import analisisr_docx as documents

    text = "[1] 2.5\nvar_x | valor < 3"
    answer = app.format_r_output(text, True)
    window.answered("Calcula", {"answer": answer})
    tables = [frame for frame in window.chat.document().rootFrame().childFrames() if isinstance(frame, ui.QTextTable)]
    assert len(tables) == 1
    assert tables[0].cellAt(1, 0).firstCursorPosition().block().text() == "[1] 2.5"
    output = documents.markdown_to_docx(answer, window.folder / "plain-result.docx")
    docx = pytest.importorskip("docx")
    report = docx.Document(output)
    assert report.tables[0].cell(1, 0).text == "[1] 2.5"
    assert report.tables[0].cell(2, 0).text == "var_x | valor < 3"


def test_ayuda_abre_el_html_local_y_conserva_la_pestana(window, monkeypatch):
    import analisisr_ui as ui

    opened = []
    monkeypatch.setattr(ui.QDesktopServices, "openUrl", lambda url: opened.append(url) or True)
    window.tabs.setCurrentIndex(3)
    action = window.findChild(ui.QAction, "help_guide")
    assert action.shortcut().toString() == "F1"
    action.trigger()
    assert len(opened) == 1
    assert Path(opened[0].toLocalFile()) == app.ROOT / "assets" / "guia.html"
    assert (app.ROOT / "assets" / "guia.html").is_file()
    assert window.tabs.currentIndex() == 3


def test_areas_de_consulta_y_respuesta_tienen_tintes_translucidos(window):
    import analisisr_ui as ui

    window.tabs.setCurrentIndex(3)
    ui.QApplication.processEvents()
    prompt_image = window.question.viewport().grab().toImage()
    response_image = window.chat.viewport().grab().toImage()
    prompt = prompt_image.pixelColor(prompt_image.width() - 20, prompt_image.height() - 20)
    response = response_image.pixelColor(response_image.width() - 20, response_image.height() - 20)
    assert prompt.green() > prompt.red() and prompt.green() > prompt.blue()
    assert response.blue() > response.red() and response.blue() > response.green()
    assert prompt.alpha() == 18 and response.alpha() == 18


@pytest.mark.parametrize("show_code", [False, True])
def test_pregunta_inmediata_y_codigo_al_final_sin_duplicar_historial(window, monkeypatch, show_code):
    previous = window.folder / "attempt_1.R"
    previous.write_text('print("OLD_ATTEMPT")', encoding="utf-8")
    script = window.folder / "attempt_2.R"
    script.write_text('print("FINAL_SCRIPT")', encoding="utf-8")
    window.question.setPlainText("Mi pregunta <literal>")
    window.show_code.setChecked(show_code)
    callbacks = []

    def start(action, request, callback):
        assert action == "chat"
        assert "Mi pregunta <literal>" in window.chat.toPlainText()
        assert window.history == []
        callbacks.append(callback)

    monkeypatch.setattr(window, "start", start)
    window.send_chat()
    # La preferencia se toma al enviar, aunque la casilla cambie mientras llega la respuesta.
    window.show_code.setChecked(not show_code)
    callbacks[0]({"answer": "Resultado local", "context_answer": "Salida conservada localmente",
                  "scripts": [str(previous), str(script)]})
    text = window.chat.toPlainText()
    assert text.count("Mi pregunta <literal>") == 1
    assert ("FINAL_SCRIPT" in text) == show_code
    assert "OLD_ATTEMPT" not in text
    assert window.history[-1]["context"] == "Salida conservada localmente"
    if show_code:
        assert window.history[-1]["content"].endswith('print("FINAL_SCRIPT")\n```')


def test_mostrar_codigo_no_oculta_resultado_si_falta_script(window):
    window.answered("Pregunta", {"answer": "Resultado", "scripts": [str(window.folder / "missing.R")]}, True)
    assert "Resultado" in window.chat.toPlainText()
    assert "No se pudo leer el código R" in window.log.toPlainText()


def test_error_navegador_indica_la_ruta_de_la_guia(window, monkeypatch):
    import analisisr_ui as ui

    warnings = []
    monkeypatch.setattr(ui.QDesktopServices, "openUrl", lambda url: False)
    monkeypatch.setattr(ui.QMessageBox, "warning", lambda parent, title, text: warnings.append(text))
    window.open_help()
    assert "navegador" in warnings[0]
    assert str(app.ROOT / "assets" / "guia.html") in warnings[0]


@pytest.mark.parametrize("share", [False, True])
def test_guardar_y_abrir_sesion_conserva_pendientes_y_excluye_claves(window, monkeypatch, share):
    import zipfile
    import analisisr_ui as ui

    base = window.folder.parent
    source = base / "source.csv"
    source.write_text("x,y\n1,10\n2,20\n", encoding="utf-8")
    profile = app.prepare_data({"data": str(source)}, window.folder)
    window.loaded(profile)
    window.applied_request = window.data_request()
    window.table.item(1, 0).setCheckState(ui.Qt.Unchecked)
    window.key.setText("PRIVATE_API_KEY_TEST")
    window.show_code.setChecked(True)
    window.run_r.setChecked(True)
    window.share.setChecked(share)
    window.question.setPlainText("Borrador pendiente")
    archive = base / "saved.analisisr"
    monkeypatch.setattr(ui.QFileDialog, "getSaveFileName", lambda *a: (str(archive), ""))
    window.save_session()
    assert archive.is_file()
    with zipfile.ZipFile(archive) as z:
        assert b"PRIVATE_API_KEY_TEST" not in z.read("session.json")
    source.unlink()
    monkeypatch.setattr(ui.QFileDialog, "getOpenFileName", lambda *a: (str(archive), ""))
    monkeypatch.setattr(ui.QMessageBox, "question", lambda *a: ui.QMessageBox.Yes)
    window.open_session()
    assert "x,y" in window.workspace.read_text(window.profile["source_file"])
    assert not window.folder.exists()
    assert window.data_request()["keep"] == ["x"]
    assert window.applied_request["keep"] == ["x", "y"]
    assert window.question.toPlainText() == "Borrador pendiente"
    assert window.show_code.isChecked()
    assert window.run_r.isChecked() and window.share.isChecked() == share
    assert window.key.text() == ""


def test_exportacion_word_incluye_codigo_aunque_no_se_mueste_en_chat(window, monkeypatch):
    import analisisr_ui as ui
    docx = pytest.importorskip("docx")

    script = window.folder / "analysis.R"
    script.write_text("tabla(dat)\n", encoding="utf-8")
    window.answered("Descriptivos", {"answer": "| Variable | Media |\n| --- | --- |\n| x | 2 |",
                                    "scripts": [str(script)]})
    path = window.folder.parent / "report.docx"
    monkeypatch.setattr(ui.QFileDialog, "getSaveFileName", lambda *a: (str(path), ""))
    window.export_word()
    report = docx.Document(path)
    assert report.tables[0].cell(1, 1).text == "2"
    assert "tabla(dat)" in [p.text for p in report.paragraphs]


def test_plantillas_se_envian_con_nombres_reales_y_sin_mostrar_el_prompt(window, monkeypatch):
    import analisisr_ui as ui

    avisos = []
    monkeypatch.setattr(ui.QMessageBox, "information", lambda *args: avisos.append(args[-1]))
    source = window.folder / "source.csv"
    source.write_text("edad,puntuacion,grupo\n20,10,1\n30,12,2\n", encoding="utf-8")
    window.loaded(app.prepare_data({"data": str(source)}, window.folder))
    window.applied_request = window.data_request()

    def choose(dialog):
        name = window.templates.currentText()
        builder = dialog.findChild(ui.FactorBuilder)
        if builder is not None:
            builder.name.setText("Factor1")
            for index in (0, 1):
                builder.items.item(index).setSelected(True)
            assert builder.add_factor()
        for widget in dialog.findChildren(ui.QListWidget):
            if builder is not None and widget in (builder.items, builder.summary):
                continue
            indices = ([1] if widget.objectName() == "covariables" else
                       [1] if widget.objectName() == "predictores" and name == "Modelo multinivel" else
                       [2] if widget.objectName() == "predictores" and name == "Análisis de supervivencia" else
                       [1, 2] if widget.objectName() == "predictores" else
                       [0, 1, 2] if name == "Análisis factorial exploratorio" else [0, 1])
            for index in indices:
                # Las listas de casillas no son seleccionables: hay que marcarlas.
                if widget.item(index).flags() & ui.Qt.ItemIsSelectable:
                    widget.item(index).setSelected(True)
                else:
                    widget.item(index).setCheckState(ui.Qt.Checked)
        for widget in dialog.findChildren(ui.QComboBox):
            widget.setCurrentIndex(0 if widget.objectName() == "exposición" else
                                   3 if widget.objectName() in ("grupo", "mediador", "moderador",
                                                                "agrupamiento") else
                                   2 if widget.objectName() in ("después", "variable_2", "columnas",
                                                                "predictor", "evento") else 1)
        dialog.findChild(ui.QDialogButtonBox).accepted.emit()
        return dialog.result()

    monkeypatch.setattr(ui.QDialog, "exec", choose)
    for name in app.TEMPLATES:
        window.templates.setCurrentText(name)
        window.use_template()
        assert not avisos, (name, avisos)
        assert window.proc is not None, name
        prompt = enviado(window)
        assert prompt and "[" not in prompt and "]" not in prompt, name
        assert "edad" in prompt and '"' not in prompt
        if name in ("Fiabilidad", "Consistencia interna"):
            assert "coefficientalpha::alpha" in prompt and "coefficientalpha::omega" in prompt
            assert "psych::alpha" not in prompt and "psych::omega" not in prompt
        # El prompt no pasa por el cuadro de consulta ni se muestra en el chat.
        assert window.question.toPlainText() == "", name
        assert "Realizando análisis solicitado" in window.chat.toPlainText()
        cerrar(window)
        assert window.history[-2]["content"] == "Análisis solicitado: " + name


def test_plantillas_se_muestran_en_orden_alfabetico(window):
    assert [window.templates.itemText(i) for i in range(1, window.templates.count())] == [
        "Acuerdo entre evaluaciones", "Análisis clúster", "Análisis de supervivencia",
        "Análisis discriminante", "Análisis factorial confirmatorio", "Análisis factorial exploratorio",
        "ANCOVA", "ANOVA", "ANOVA de medidas repetidas", "Antes y después",
        "Ausentes e imputación múltiple", "Consistencia interna", "Correlación",
        "Curva ROC y capacidad diagnóstica", "Descriptivos", "Diferencia entre medias", "Fiabilidad",
        "Invarianza de medida", "Mediación", "Modelo multinivel", "Moderación", "Normalidad", "Regresión",
        "Regresión logística", "Regresión multinomial", "Regresión ordinal", "Regresión para recuentos",
        "Tablas de contingencia",
    ]


@pytest.mark.parametrize("name,field,selection,message", [
    ("Análisis clúster", "variables", [0], "al menos 2"),
    ("Análisis factorial exploratorio", "variables", [0, 1], "al menos 3"),
    ("Consistencia interna", "ítems", [0], "al menos dos"),
    ("Análisis discriminante", "predictores", [0, 1], "no puede ser también predictora"),
    ("Regresión logística", "predictores", [0, 1], "no puede ser también predictora"),
    ("Regresión ordinal", "predictores", [0, 1], "no puede ser también predictora"),
    ("Regresión multinomial", "predictores", [0, 1], "no puede ser también predictora"),
    ("Regresión para recuentos", "predictores", [0, 1], "no puede ser también predictora"),
    ("Acuerdo entre evaluaciones", "evaluaciones", [0], "al menos 2"),
    ("ANOVA de medidas repetidas", "medidas", [1], "al menos 2"),
    ("Ausentes e imputación múltiple", "variables", [0], "al menos 2"),
    ("Modelo multinivel", "predictores", [0, 1], "no puede ser también predictora"),
])
def test_nuevas_plantillas_validan_seleccion(window, monkeypatch, name, field, selection, message):
    import analisisr_ui as ui

    source = window.folder / "source.csv"
    source.write_text("x,y,z\n1,2,3\n2,3,4\n", encoding="utf-8")
    window.loaded(app.prepare_data({"data": str(source)}, window.folder))
    window.applied_request = window.data_request()
    warnings = []
    monkeypatch.setattr(ui.QMessageBox, "information", lambda *args: warnings.append(args[-1]))

    def choose(dialog):
        listing = dialog.findChild(ui.QListWidget, field)
        for index in selection:
            listing.item(index).setSelected(True)
        for widget in dialog.findChildren(ui.QComboBox):
            widget.setCurrentIndex(1)
        dialog.findChild(ui.QDialogButtonBox).accepted.emit()
        return dialog.result()

    monkeypatch.setattr(ui.QDialog, "exec", choose)
    window.templates.setCurrentText(name)
    window.use_template()
    assert message in warnings[0]
    assert not window.question.toPlainText() and window.proc is None


@pytest.mark.parametrize("selection,message", [([], "Covariables"), ([0], "distintas"), ([1], "distintas")])
def test_ancova_exige_covariables_distintas(window, monkeypatch, selection, message):
    import analisisr_ui as ui

    source = window.folder / "source.csv"
    source.write_text("x,grupo,covariable\n1,0,2\n2,1,3\n", encoding="utf-8")
    window.loaded(app.prepare_data({"data": str(source)}, window.folder))
    window.applied_request = window.data_request()
    warnings = []
    monkeypatch.setattr(ui.QMessageBox, "information", lambda *args: warnings.append(args[-1]))

    def choose(dialog):
        dialog.findChild(ui.QComboBox, "puntuación").setCurrentIndex(1)
        dialog.findChild(ui.QComboBox, "grupo").setCurrentIndex(2)
        listing = dialog.findChild(ui.QListWidget, "covariables")
        for index in selection:
            listing.item(index).setSelected(True)
        dialog.findChild(ui.QDialogButtonBox).accepted.emit()
        return dialog.result()

    monkeypatch.setattr(ui.QDialog, "exec", choose)
    window.templates.setCurrentText("ANCOVA")
    window.use_template()
    assert message in warnings[0] and not window.question.toPlainText()


@pytest.mark.parametrize("exposure", [0, 1, 2, 3])
def test_recuentos_exposicion_opcional_y_distinta(window, monkeypatch, exposure):
    import analisisr_ui as ui

    source = window.folder / "source.csv"
    source.write_text("eventos,edad,tiempo\n1,20,10\n2,30,20\n", encoding="utf-8")
    window.loaded(app.prepare_data({"data": str(source)}, window.folder))
    window.applied_request = window.data_request()
    warnings = []
    monkeypatch.setattr(ui.QMessageBox, "information", lambda *args: warnings.append(args[-1]))

    def choose(dialog):
        dialog.findChild(ui.QComboBox, "respuesta").setCurrentIndex(1)
        dialog.findChild(ui.QListWidget, "predictores").item(1).setSelected(True)
        dialog.findChild(ui.QComboBox, "exposición").setCurrentIndex(exposure)
        dialog.findChild(ui.QDialogButtonBox).accepted.emit()
        return dialog.result()

    monkeypatch.setattr(ui.QDialog, "exec", choose)
    window.templates.setCurrentText("Regresión para recuentos")
    window.use_template()
    if exposure in (1, 2):
        assert window.proc is None and "exposición debe ser distinta" in warnings[0]
        return
    prompt = enviado(window)
    if True:
        assert not warnings and "[" not in prompt
        assert "Exposición seleccionada: " + ("tiempo" if exposure else "no especificada") + "." in prompt


@pytest.mark.parametrize("name", ["Diferencia entre medias", "ANOVA", "Tablas de contingencia"])
def test_plantillas_de_comparacion_exigen_variables_distintas(window, monkeypatch, name):
    import analisisr_ui as ui

    source = window.folder / "source.csv"
    source.write_text("puntuacion,grupo\n10,0\n20,1\n", encoding="utf-8")
    window.loaded(app.prepare_data({"data": str(source)}, window.folder))
    window.applied_request = window.data_request()
    messages = []
    monkeypatch.setattr(ui.QMessageBox, "information", lambda parent, title, text: messages.append(text))

    def choose_same(dialog):
        for widget in dialog.findChildren(ui.QComboBox):
            widget.setCurrentIndex(1)
        dialog.findChild(ui.QDialogButtonBox).accepted.emit()
        return dialog.result()

    monkeypatch.setattr(ui.QDialog, "exec", choose_same)
    window.templates.setCurrentText(name)
    window.use_template()
    assert "distintas" in messages[0]
    assert window.question.toPlainText() == ""
    assert window.proc is None


def test_plantilla_sin_datos_no_inserta_campos_pendientes(window, monkeypatch):
    import analisisr_ui as ui

    messages = []
    monkeypatch.setattr(ui.QMessageBox, "information", lambda parent, title, text: messages.append(text))
    window.templates.setCurrentText("Descriptivos")
    window.use_template()
    assert "Importa" in messages[0]
    assert window.question.toPlainText() == ""


def test_no_se_envian_campos_sin_completar_de_plantillas_antiguas(window, monkeypatch):
    import analisisr_ui as ui

    messages, calls = [], []
    monkeypatch.setattr(ui.QMessageBox, "warning", lambda parent, title, text: messages.append(text))
    monkeypatch.setattr(window, "start", lambda *args: calls.append(args))
    window.question.setPlainText("Compara [puntuación] por [grupo]")
    window.send_chat()
    assert calls == []
    assert "sin completar" in messages[0]


def test_indices_de_r_no_se_confunden_con_campos_de_plantilla(window, monkeypatch):
    calls = []
    monkeypatch.setattr(window, "start", lambda *args: calls.append(args))
    window.question.setPlainText("Explica dat[variables]")
    window.send_chat()
    assert len(calls) == 1


def test_r_esta_activado_sin_opcion_de_revision(window):
    import analisisr_ui as ui

    assert window.run_r.isChecked()
    assert window.share.isChecked()
    assert window.tokens.value() == 64000
    assert window.timeout.value() == 300
    assert not any("Revisar R" in check.text() for check in window.findChildren(ui.QCheckBox))


@pytest.mark.parametrize("share", [False, True])
def test_envio_al_worker_respeta_casilla_de_salida_y_limites(window, monkeypatch, share):
    calls = []
    window.share.setChecked(share)
    monkeypatch.setattr(window, "start", lambda *args: calls.append(args))
    window.question.setPlainText("Explica el contraste t")
    window.send_chat()
    assert calls[0][1]["share_output"] == share
    assert calls[0][1]["max_tokens"] == 64000
    assert calls[0][1]["timeout"] == 300


def test_arroba_inserta_varias_variables_en_la_posicion_del_cursor(window, monkeypatch):
    import analisisr_ui as ui
    from PySide6.QtTest import QTest

    source = window.folder / "source.csv"
    source.write_text("edad,puntuacion,grupo\n20,10,1\n30,12,2\n", encoding="utf-8")
    window.loaded(app.prepare_data({"data": str(source)}, window.folder))
    window.question.setPlainText("Compara  por grupo")
    cursor = window.question.textCursor()
    cursor.setPosition(len("Compara "))
    window.question.setTextCursor(cursor)

    def choose(dialog):
        listing = dialog.findChild(ui.QListWidget)
        assert [listing.item(i).text() for i in range(listing.count())] == ["edad", "puntuacion", "grupo"]
        listing.item(0).setSelected(True)
        listing.item(1).setSelected(True)
        dialog.accept()
        return dialog.result()

    monkeypatch.setattr(ui.QDialog, "exec", choose)
    QTest.keyClicks(window.question, "@")
    assert window.question.toPlainText() == "Compara edad, puntuacion por grupo"


def test_cancelar_selector_arroba_conserva_el_texto(window, monkeypatch):
    import analisisr_ui as ui

    window.profile = {"columns": [{"column": "edad"}]}
    window.question.setPlainText("Texto previo")
    monkeypatch.setattr(ui.QDialog, "exec", lambda dialog: ui.QDialog.Rejected)
    window.insert_variables()
    assert window.question.toPlainText() == "Texto previo"


def test_recientes_abren_el_archivo_y_se_actualizan_solo_al_importar(window, monkeypatch):
    source = window.folder / "source.csv"
    source.write_text("x,y\n1,10\n2,20\n", encoding="utf-8")
    calls = []
    monkeypatch.setattr(window, "start", lambda *args: calls.append(args))
    window.open_data(source)
    assert app.recent_data_files() == []
    profile = app.prepare_data({"data": str(source)}, window.folder)
    calls[0][2](profile)
    assert app.recent_data_files() == [source]
    assert window.recent.isEnabled()
    calls.clear()
    window.recent_menu.actions()[0].trigger()
    assert calls[0][0] == "profile" and Path(calls[0][1]["data"]) == source




def test_icono_de_ventana_esta_disponible(window):
    assert not window.windowIcon().isNull()


def test_importacion_analisis_sucesivos_word_y_sesion_con_temporales_limpios(window, monkeypatch):
    import analisisr_ui as ui

    if not RSCRIPT:
        pytest.skip("Requiere Rscript")
    base = window.folder.parent
    source = base / "original.csv"
    source.write_text("x\n1\n2\n3\n", encoding="utf-8")
    original = source.read_bytes()

    class Backend:
        last_truncated = False

        def __init__(self):
            self.responses = iter(["```r\ntabla(data.frame(Media=mean(dat$x)))\n```", "La media es 2."])

        def chat(self, *args):
            return next(self.responses)

    monkeypatch.setattr(app, "make_backend", lambda *args: Backend())

    def complete():
        request = window.folder / f"operacion_{window.job:03d}" / "request.json"
        assert app.worker(request) == 0
        window.proc.done.emit(0)
        assert not window.folder.exists()

    window.open_data(source)
    complete()
    for index in range(2):
        window.question.setPlainText(f"Calcula la media, consulta {index + 1}")
        window.send_chat()
        complete()
        assert "La media es 2" in window.chat.toPlainText()
    assert source.read_bytes() == original
    report = base / "resultados.docx"
    monkeypatch.setattr(ui.QFileDialog, "getSaveFileName", lambda *a: (str(report), ""))
    window.export_word()
    assert report.is_file() and not window.folder.exists()
    archive = base / "resultados.analisisr"
    monkeypatch.setattr(ui.QFileDialog, "getSaveFileName", lambda *a: (str(archive), ""))
    window.save_session()
    assert archive.is_file() and not window.folder.exists()
    monkeypatch.setattr(ui.QFileDialog, "getOpenFileName", lambda *a: (str(archive), ""))
    monkeypatch.setattr(ui.QMessageBox, "question", lambda *a: ui.QMessageBox.Yes)
    window.open_session()
    assert not window.folder.exists()
    assert "x" in window.workspace.read_text(window.profile["data_for_r"])
    window.close()
    assert not window.folder.exists() and not window.workspace.files
    assert report.is_file() and archive.is_file() and source.read_bytes() == original


def test_cancelacion_limpia_disco_y_conserva_el_diagnostico(window, monkeypatch):
    import analisisr_ui as ui

    warnings = []
    monkeypatch.setattr(ui.QMessageBox, "warning", lambda *a: warnings.append(a[-1]))
    window.start("chat", window.endpoint(), lambda _: pytest.fail("No debe aceptar un cálculo cancelado"))
    auxiliary = window.folder / "operacion_001" / "analisisr_chat_r_interrumpido"
    auxiliary.mkdir()
    (auxiliary / "chat.R").write_text("código interrumpido", encoding="utf-8")
    window.proc.done.emit(-1)
    assert warnings and not window.folder.exists()
    assert window.workspace.read_text(auxiliary / "chat.R") == "código interrumpido"


def test_cerrar_detiene_proceso_activo_y_borra_temporales(window, monkeypatch):
    import sys
    import analisisr_ui as ui

    monkeypatch.setattr(ui.QMessageBox, "warning", lambda *a: pytest.fail(str(a[-1])))
    window.start("chat", window.endpoint(), lambda _: pytest.fail("No debe interpretar al cerrar"))
    window.proc.p.start(sys.executable, ["-c", "import time; time.sleep(30)"])
    assert window.proc.p.waitForStarted(5000)
    assert window.proc.running
    window.close()
    assert window.proc is None or not window.proc.running
    assert not window.folder.exists() and not window.workspace.files


def test_version_compilada_lanza_el_trabajador_ejecutable(window, monkeypatch):
    import sys
    import analisisr_ui as ui

    calls = []
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(window.folder.parent / "AnalisisR.exe"))
    monkeypatch.setattr(ui.Proc, "start", lambda self, *args: calls.append(args))
    window.start("diagnose", {}, lambda _: None)
    program, args, *_ = calls[0]
    assert Path(program).name == "AnalisisRWorker.exe"
    assert args[0] == "--worker" and len(args) == 2


def test_endpoint_muestra_y_fija_presupuesto_cero(window):
    import analisisr_ui as ui

    assert window.endpoint()["reasoning_budget"] == 0
    assert any("presupuesto 0 (fijo)" in label.text() for label in window.findChildren(ui.QLabel))
    window.show_probe({"kind": "local"})
    assert "Razonamiento solicitado: desactivado (presupuesto 0)" in window.probe_result.toPlainText()


def test_guardar_rechaza_modelo_con_razonamiento_obligatorio(window, monkeypatch):
    import analisisr_ui as ui

    window.provider.setCurrentIndex(window.provider.findData("openai"))
    window.model.setText("o3")
    saved, warnings = [], []
    monkeypatch.setattr(app.secrets, "upsert", lambda *a: saved.append(a))
    monkeypatch.setattr(ui.QMessageBox, "warning", lambda *a: warnings.append(a[-1]))
    window.save_endpoint()
    assert not saved and "no permite desactivar" in warnings[0]
