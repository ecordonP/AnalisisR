"""Plantilla de normalidad: el usuario elige las pruebas de MVN y el prompt usa sus códigos."""
import json
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
            if nombre.startswith("pruebas_"):
                # Casillas: no se selecciona la fila, se marca cada prueba.
                assert lista.selectionMode() == ui.QAbstractItemView.NoSelection
                for i in range(lista.count()):
                    assert lista.item(i).checkState() == ui.Qt.Unchecked
                    assert lista.item(i).flags() & ui.Qt.ItemIsUserCheckable
            else:
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
        multi.item(0).setCheckState(ui.Qt.Checked)   # Mardia
        multi.item(3).setCheckState(ui.Qt.Checked)   # Royston
        dialog.findChild(ui.QListWidget, "pruebas_univariantes").item(2).setCheckState(ui.Qt.Checked)
        dialog.findChild(ui.QDialogButtonBox).accepted.emit()
        return dialog.result()

    monkeypatch.setattr(ui.QDialog, "exec", elegir)
    view.use_template()
    assert view.proc is not None
    consulta = json.loads((view.folder / "operacion_001" / "request.json").read_text(encoding="utf-8"))["ask"]
    assert not avisos
    assert view.question.toPlainText() == "", "el prompt no pasa por el cuadro de consulta"
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
        dialog.findChild(ui.QListWidget, "pruebas_multivariantes").item(1).setCheckState(ui.Qt.Checked)
        dialog.findChild(ui.QListWidget, "pruebas_univariantes").item(0).setCheckState(ui.Qt.Checked)
        dialog.findChild(ui.QDialogButtonBox).accepted.emit()
        return dialog.result()

    monkeypatch.setattr(ui.QDialog, "exec", elegir)
    view.use_template()
    assert view.proc is None and view.question.toPlainText() == ""
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
    assert view.proc is None and view.question.toPlainText() == ""
    assert avisos and "Pruebas" in avisos[0]


def test_el_prompt_no_inventa_grados_de_libertad():
    """Solo Doornik-Hansen devuelve df en MVN 6.3: el resto no puede salir como NA."""
    prompt = app.TEMPLATES["Normalidad"]
    assert "solo Doornik-Hansen devuelve la columna df" in prompt
    assert "No añadas" in prompt and "llena de NA" in prompt
    assert "aproximación lognormal" in prompt and "k(k+1)(k+2)/6" in prompt


def test_la_conclusion_no_puede_contradecir_al_p():
    """Un p<0,001 etiquetado como «no rechaza» era el error observado en una ejecución real."""
    prompt = app.TEMPLATES["Normalidad"]
    assert "coherente con su p" in prompt
    assert "jamás" in prompt and "no se rechaza" in prompt
    assert "no es evaluable" in prompt
    # No fiarse de los símbolos Unicode de la columna MVN.
    assert "marcas Unicode" in prompt
    for otra in ("Análisis factorial confirmatorio", "Invarianza de medida"):
        assert "no puede presentarse como que no se rechaza" in app.TEMPLATES[otra], otra


def test_al_enviar_una_plantilla_no_se_muestra_el_prompt(ventana, monkeypatch):
    """El chat solo anuncia la espera; el prompt completo viaja al endpoint como contexto."""
    view, ui = ventana

    def elegir(dialog):
        for i in (0, 1):
            dialog.findChild(ui.QListWidget, "variables").item(i).setSelected(True)
        dialog.findChild(ui.QListWidget, "pruebas_multivariantes").item(0).setCheckState(ui.Qt.Checked)
        dialog.findChild(ui.QListWidget, "pruebas_univariantes").item(0).setCheckState(ui.Qt.Checked)
        dialog.findChild(ui.QDialogButtonBox).accepted.emit()
        return dialog.result()

    monkeypatch.setattr(ui.QDialog, "exec", elegir)
    view.templates.setCurrentText("Normalidad")
    view.use_template()
    assert view.proc is not None, "la plantilla se envía directamente"
    assert view.question.toPlainText() == "", "el prompt no se escribe en el cuadro de consulta"
    peticion = json.loads((view.folder / "operacion_001" / "request.json").read_text(encoding="utf-8"))
    prompt = peticion["ask"]
    assert "MVN" in prompt and "mvn_test" in prompt, "el endpoint recibe el prompt íntegro"
    conversacion = view.chat.toPlainText()
    assert "Realizando análisis solicitado" in conversacion and "Espere por favor" in conversacion
    assert "MVN" not in conversacion and "mvn_test" not in conversacion

    # Tras la respuesta, el historial muestra la plantilla, nunca el prompt.
    app.write_json(view.folder / "operacion_001" / "result.json", {"answer": "Resultado"})
    view.proc.done.emit(0)
    turno = view.history[0]
    assert turno["content"] == "Análisis solicitado: Normalidad"
    assert turno["context"] == prompt
    assert "MVN" not in view.chat.toPlainText()


def test_una_consulta_escrita_a_mano_si_se_muestra(ventana, monkeypatch):
    view, ui = ventana
    view.question.setPlainText("Describe las variables x e y")
    view.send_chat()
    assert view.proc is not None
    assert "Describe las variables x e y" in view.chat.toPlainText()
    assert "Realizando análisis solicitado" not in view.chat.toPlainText()


def test_el_contexto_declara_los_paquetes_instalados(tmp_path, monkeypatch):
    """Sin esta lista el modelo adivinaba y abortaba análisis con paquetes sí instalados."""
    prompts = []

    class Backend:
        last_truncated = False

        def chat(self, system, user):
            prompts.append(user)
            return "Listo, sin código."

    source = tmp_path / "d.csv"
    source.write_text("x,y\n1,2\n2,3\n3,5\n", encoding="utf-8")
    profile = app.prepare_data({"data": str(source)}, tmp_path)
    monkeypatch.setattr(app.engine, "find_rscript", lambda: "Rscript")
    monkeypatch.setattr(app.engine, "diagnose_r", lambda: {"packages": [
        {"package": "MVN", "version": "6.3", "installed": True},
        {"package": "lavaan", "version": "0.7.3", "installed": True},
        {"package": "metafor", "version": "NO_INSTALADO", "installed": False}]})
    app.converse({"ask": "Normalidad de x e y", "profile": profile, "run_r": True},
                 tmp_path, backend=Backend())
    contexto = prompts[0]
    assert "PAQUETES R INSTALADOS Y DISPONIBLES: MVN, lavaan" in contexto
    assert "No instalados: metafor" in contexto
    assert "no supongas" in contexto


def test_un_fallo_al_listar_paquetes_no_rompe_la_consulta(tmp_path, monkeypatch):
    class Backend:
        last_truncated = False

        def chat(self, system, user):
            return "Respuesta sin R."

    def revienta():
        raise OSError("Rscript no disponible")

    monkeypatch.setattr(app.engine, "find_rscript", lambda: "Rscript")
    monkeypatch.setattr(app.engine, "diagnose_r", revienta)
    resultado = app.converse({"ask": "Describe", "profile": None, "run_r": True},
                             tmp_path, backend=Backend())
    assert "Respuesta sin R" in resultado["answer"]


def test_el_rechazo_de_install_packages_aclara_que_no_prueba_nada():
    motivo = app.engine.chat_r_guard("if (!requireNamespace('MVN')) install.packages('MVN')")
    assert "install.packages()" in motivo
    assert "no dice nada sobre qué paquetes hay instalados" in motivo
    assert "requireNamespace()" in motivo


def test_ninguna_plantilla_permite_instalar_paquetes():
    for name, prompt in app.TEMPLATES.items():
        assert "No escribas nunca install.packages()" in prompt, name


def test_el_diagnostico_ya_conocido_no_se_recalcula(tmp_path, monkeypatch):
    """Recalcular los 25 paquetes cuesta unos dos segundos por turno."""
    llamadas = []

    class Backend:
        last_truncated = False

        def chat(self, system, user):
            llamadas.append(user)
            return "Sin código."

    monkeypatch.setattr(app.engine, "find_rscript", lambda: "Rscript")
    monkeypatch.setattr(app.engine, "diagnose_r",
                        lambda: (_ for _ in ()).throw(AssertionError("no debe recalcularse")))
    app.converse({"ask": "Normalidad", "profile": None, "run_r": True,
                  "packages": [{"package": "MVN", "version": "6.3", "installed": True}]},
                 tmp_path, backend=Backend())
    assert "PAQUETES R INSTALADOS Y DISPONIBLES: MVN" in llamadas[0]


def test_el_gl_de_mardia_es_obligatorio_y_las_demas_filas_declaran_su_referencia():
    prompt = app.TEMPLATES["Normalidad"]
    assert "nunca NA ni una" in prompt and "celda vacía" in prompt
    assert "Para la asimetría de Mardia informa siempre sus grados de libertad" in prompt
    assert "k(k+1)(k+2)/6" in prompt
    for referencia in ("normal estándar", "aproximación lognormal", "remuestreo"):
        assert referencia in prompt, referencia


def test_el_chat_anuncia_cada_paso_mientras_espera(ventana, monkeypatch):
    """Sin esto la espera parece un cuelgue: el chat solo mostraba el aviso inicial."""
    view, ui = ventana

    def elegir(dialog):
        for i in (0, 1):
            dialog.findChild(ui.QListWidget, "variables").item(i).setSelected(True)
        dialog.findChild(ui.QListWidget, "pruebas_multivariantes").item(0).setCheckState(ui.Qt.Checked)
        dialog.findChild(ui.QListWidget, "pruebas_univariantes").item(0).setCheckState(ui.Qt.Checked)
        dialog.findChild(ui.QDialogButtonBox).accepted.emit()
        return dialog.result()

    monkeypatch.setattr(ui.QDialog, "exec", elegir)
    view.templates.setCurrentText("Normalidad")
    view.use_template()
    assert view.proc is not None

    view.proc.line.emit("[   0.4s] PASO: Consultando al endpoint; 18432 caracteres de contexto")
    view.proc.line.emit("[  12.9s] PASO: Ejecutando el bloque 1 de código R")
    view.proc.line.emit("[  15.1s] algo interno que no es un paso")
    conversacion = view.chat.toPlainText()
    assert "Consultando al endpoint" in conversacion
    assert "Ejecutando el bloque 1 de código R" in conversacion
    assert "algo interno" not in conversacion, "solo los pasos marcados van al chat"
    # El registro conserva todas las líneas, pasos incluidos.
    registro = view.log.toPlainText()
    assert "algo interno" in registro and "Consultando al endpoint" in registro

    # Al llegar la respuesta, el chat se redibuja y los pasos desaparecen.
    app.write_json(view.folder / "operacion_001" / "result.json", {"answer": "Tabla final"})
    view.proc.done.emit(0)
    final = view.chat.toPlainText()
    assert "Tabla final" in final
    assert "Consultando al endpoint" not in final and "Ejecutando el bloque" not in final


def test_el_bloque_de_r_acepta_dat_y_datos():
    """Los prompts piden dat; el alias cubre el nombre que el modelo tiende a inventar."""
    script = app.engine.chat_r_script("cat(nrow(dat), nrow(datos))", {"file": "d.csv"})
    assert "dat <- utils::read.csv" in script
    assert "datos <- dat" in script
    # El alias se define antes del código del chat.
    assert script.index("datos <- dat") < script.index("# --- código del chat ---")


def test_ninguna_plantilla_pide_un_data_frame_inexistente():
    import re

    for name, prompt in app.TEMPLATES.items():
        assert not re.findall(r"[a-zA-Z_.]*\(datos[,)]|data=datos|datos_del_grupo", prompt), name
        assert "ya están cargados en el data.frame dat" in prompt, name


def test_el_prompt_prohibe_los_argumentos_que_rompen_mvn():
    """Una ejecución real murió con power_family=NULL: son cadenas con valor por omisión."""
    prompt = app.TEMPLATES["Normalidad"]
    assert "argumentos imprescindibles" in prompt
    assert "NULL o FALSE detiene la ejecución" in prompt and "match.arg" in prompt
    for valido in ("bcPower", "bcnPower", "yjPower", "quan", "adj"):
        assert valido in prompt, valido
    assert "mvn_test=NULL" in prompt and "univariate_test=NULL" in prompt


def test_el_prompt_fija_los_nombres_de_columna_con_sus_mayusculas():
    prompt = app.TEMPLATES["Normalidad"]
    assert "Test, Statistic, p.value, Method y MVN" in prompt
    assert "minúscula devuelve NULL" in prompt


def test_ninguna_plantilla_reimplementa_lo_que_r_ya_trae():
    for name, prompt in app.TEMPLATES.items():
        assert "usa p.adjust" in prompt, name
        assert "llega truncado" in prompt, name


def test_el_prompt_incluye_un_ejemplo_imitable_y_valido():
    """La prosa se ignoraba; un esqueleto verificado es mucho más difícil de desviar."""
    prompt = app.TEMPLATES["Normalidad"]
    for pieza in ("subset(dat, select = vars)", "MVN::mvn(dsel, mvn_test = 'mardia')",
                  "$multivariate_normality", "as.character(r$Test)", "r$Statistic",
                  "do.call(rbind, ...)", "tabla()"):
        assert pieza in prompt, pieza
    # El ejemplo no puede traer corchetes ni comillas dobles: romperían el relleno.
    import re
    assert "[" not in re.sub(r"\[[^\]]+\]", "", prompt) and '"' not in prompt
