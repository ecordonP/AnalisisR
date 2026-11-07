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
                  "what argument unknown", "residual.var no existe",
                  "subset(pe, op == '~~' & lhs == rhs)",
                  "número diferente de filas"):
        assert pieza in prompt, (name, pieza)


def test_la_mediacion_trae_una_receta_de_lavaan_comprobada():
    """Comprobada contra el intérprete real: sin receta el modelo inventaba la API."""
    prompt = app.TEMPLATES["Mediación"]
    for pieza in ("lavaan::sem(modelo, data = sub, estimator = 'ML', missing = 'fiml'",
                  "se = 'bootstrap', bootstrap = 5000)",
                  "boot.ci.type = 'perc'", "boot.ci.type = 'bca.simple'",
                  "lavaan::standardizedSolution(fit)", "est.std",
                  "No existen standardizedEstimates", "lavaan::lavTestLRT",
                  "subset(pe, label %in% c('a', 'b', 'cp', 'ab', 'total'))",
                  "'[predictor]', '[mediador]', '[respuesta]'"):
        assert pieza in prompt, pieza


def test_la_mediacion_pide_una_sola_vez_cada_variable(tmp_path, monkeypatch):
    """La receta repite los campos en el código: el formulario debe mostrar uno de cada."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    pytest.importorskip("PySide6")
    import analisisr_ui as ui
    import analisisr_session as sessions

    ui.QApplication.instance() or ui.QApplication([])
    monkeypatch.setattr(app.secrets, "load", lambda: {})
    monkeypatch.setattr(app.secrets, "config_dir", lambda: tmp_path / "config")
    monkeypatch.setattr(app.engine, "find_rscript", lambda: "Rscript")
    monkeypatch.setattr(sessions, "temporary_root", lambda: tmp_path)
    window = app.create_window()
    try:
        source = window.folder / "source.csv"
        source.write_text("x,m,y\n1,2,3\n2,3,4\n3,5,6\n", encoding="utf-8")
        window.loaded(app.prepare_data({"data": str(source)}, window.folder))
        window.applied_request = window.data_request()
        campos = {}

        def inspeccionar(dialog):
            for field in ("predictor", "mediador", "respuesta"):
                campos[field] = len(dialog.findChildren(ui.QComboBox, field))
            return ui.QDialog.Rejected

        monkeypatch.setattr(ui.QDialog, "exec", inspeccionar)
        window.templates.setCurrentText("Mediación")
        window.use_template()
        assert campos == {"predictor": 1, "mediador": 1, "respuesta": 1}, campos
    finally:
        window.close()


@pytest.mark.parametrize("name", ["Análisis factorial confirmatorio", "Invarianza de medida"])
def test_los_prompts_de_medida_declaran_la_llamada_de_mvn(name):
    """El modelo escribía tres nombres de prueba a mano y rompía el data.frame."""
    prompt = app.TEMPLATES[name]
    for pieza in ("una sola prueba", "no escribas a mano un vector con los nombres",
                  "número diferente de filas", "do.call(rbind, ...)",
                  "Test, Statistic, p.value, Method y MVN", "univariateTest"):
        assert pieza in prompt, (name, pieza)


@pytest.mark.parametrize("name", ["Análisis factorial confirmatorio", "Consistencia interna",
                                  "Invarianza de medida", "Mediación"])
def test_los_prompts_de_lavaan_cuentan_los_parametros_con_npar(name):
    prompt = app.TEMPLATES[name]
    assert "lavaan::fitMeasures(ajuste, 'npar')" in prompt
    assert "no es soportado por 'cat'" in prompt
    # compRelSEM con simplify=TRUE devuelve un vector sin nombres: comprobado en R.
    assert "simplify igual a FALSE" in prompt and "names() sobre él es NULL" in prompt
    assert "una sola variable latente no hay pares" in prompt


def test_una_consulta_libre_recibe_las_guias_de_api():
    """El prompt del usuario no lleva reglas de plantilla: sin esto inventa la API antigua."""
    consulta = ("Usando lavaan estima un modelo factorial de segundo orden. Determina la "
                "normalidad multivariante y con semTools calcula omega, AVE y la matriz HTMT.")
    guias = app.guias_necesarias(consulta)
    assert len(guias) == 3
    texto = " ".join(guias)
    for pieza in ("no existen mvnMethod, multivariateNorm", "univariateTest",
                  "semTools::htmt recibe como primer argumento la sintaxis del modelo",
                  "no existe method", "htmt2", "lavaan::lavInspect"):
        assert pieza in texto, pieza


def test_una_consulta_de_plantilla_no_recibe_guias(tmp_path, monkeypatch):
    """Las plantillas ya son autocontenidas: repetirles las guías solo gasta contexto."""
    class Backend:
        last_truncated = False

        def __init__(self):
            self.prompts = []

        def chat(self, system, user):
            self.prompts.append(user)
            return "Sin cálculo."

    monkeypatch.setattr(app.engine, "find_rscript", lambda: None)
    backend = Backend()
    app.converse({"ask": app.TEMPLATES["Análisis factorial confirmatorio"],
                  "plantilla": "Análisis factorial confirmatorio",
                  "profile": None, "run_r": False}, tmp_path, backend)
    assert "USO CORRECTO DEL PAQUETE" not in backend.prompts[0]


def test_la_guia_de_mvn_llega_al_contexto_de_la_consulta(tmp_path, monkeypatch):
    """Comprueba el punto de inserción real en converse, no solo la selección."""
    class Backend:
        last_truncated = False

        def __init__(self):
            self.prompts = []

        def chat(self, system, user):
            self.prompts.append(user)
            return "Sin cálculo."

    monkeypatch.setattr(app.engine, "find_rscript", lambda: None)
    backend = Backend()
    app.converse({"ask": "Comprueba la normalidad multivariante de los ítems con MVN",
                  "profile": None, "run_r": False}, tmp_path, backend)
    assert "no existen mvnMethod" in backend.prompts[0]
    assert "USO CORRECTO DEL PAQUETE" in backend.prompts[0]


def test_las_firmas_se_leen_del_r_instalado():
    """Escritas a mano caducarían al actualizar el paquete; aquí salen de args()."""
    import analisisr_core as engine

    rs = engine.find_rscript()
    if not rs:
        pytest.skip("Requiere Rscript")
    consulta = "normalidad multivariante con MVN y un modelo con lavaan"
    objetivo = app.funciones_a_documentar(consulta)
    assert "MVN::mvn" in objetivo and "lavaan::sem" in objetivo
    firmas = engine.function_signatures(rs, objetivo)
    assert "MVN::mvn" in firmas and "mvn_test" in firmas
    # La versión instalada queda escrita junto a la firma.
    assert "[MVN " in firmas and "[lavaan " in firmas
    # Una función inexistente se declara como tal en vez de callarse.
    inventada = engine.function_signatures(rs, ["MVN::mvnMethod"])
    assert "NO EXISTE" in inventada


def test_las_funciones_citadas_con_dos_puntos_se_documentan():
    objetivo = app.funciones_a_documentar("usa car::leveneTest y stats::oneway.test")
    assert objetivo[:2] == ["car::leveneTest", "stats::oneway.test"]
    assert app.funciones_a_documentar("dame los descriptivos de edad") == []


def test_el_punto_final_de_la_frase_no_se_cuela_en_el_nombre():
    """stats::lm. no existe: la consulta se gastaría en una función inventada."""
    assert app.funciones_a_documentar("ajusta con stats::lm.") == ["stats::lm"]
    for name in app.TEMPLATES:
        assert not [f for f in app.funciones_a_documentar(app.TEMPLATES[name]) if f.endswith(".")]


def test_las_firmas_se_consultan_antes_de_llamar_al_endpoint(tmp_path, monkeypatch):
    """El primer paso de cada consulta es leer la firma real en R, no preguntar al modelo."""
    orden = []

    class Backend:
        last_truncated = False
        ultimo = ""

        def chat(self, system, user):
            orden.append("endpoint")
            Backend.ultimo = user
            return "Sin cálculo."

    def firmas(*a, **kw):
        orden.append("firmas")
        return "MVN::mvn [MVN 6.3]: function (data, mvn_test = 'hz')"

    monkeypatch.setattr(app.engine, "find_rscript", lambda: "Rscript")
    monkeypatch.setattr(app.engine, "function_signatures", firmas)
    monkeypatch.setattr(app.engine, "diagnose_r", lambda: {"packages": []})
    app.converse({"ask": "comprueba la normalidad multivariante con MVN::mvn",
                  "profile": None, "run_r": True}, tmp_path, Backend())
    assert orden[:2] == ["firmas", "endpoint"], orden
    assert "FIRMAS REALES" in Backend.ultimo and "mvn_test" in Backend.ultimo


def test_se_documentan_todas_las_funciones_de_la_plantilla_mas_grande():
    """El tope no puede recortar la lista: la plantilla mayor nombra dieciséis funciones."""
    import analisisr_core as engine

    mayor = max((len(app.funciones_a_documentar(p)) for p in app.TEMPLATES.values()))
    assert mayor <= engine.FIRMAS_MAX, (mayor, engine.FIRMAS_MAX)


def test_los_prompts_explican_como_tabular_un_vector_con_nombres():
    """fitMeasures, AVE y compRelSEM devuelven vectores: as.data.frame() rompía la tabla."""
    for name, prompt in app.TEMPLATES.items():
        assert "data.frame(Indice = names(x), Valor = as.numeric(x), row.names = NULL)" in prompt, name
        assert "names attribute must be the same length as the vector" in prompt, name
    for name in ("Análisis factorial confirmatorio", "Invarianza de medida", "Mediación"):
        prompt = app.TEMPLATES[name]
        assert "data.frame(Indice = names(fm), Valor = as.numeric(fm)" in prompt, name
        # Comprobado en lavaan 0.7.3: los robustos mantienen el punto y srmr no tiene escalado.
        assert "chisq.scaled" in prompt and "srmr no tiene versión escalada" in prompt, name


def test_el_registro_nombra_todos_los_paquetes_consultados(tmp_path, monkeypatch, capsys):
    """Con la lista recortada no se veía si semTools se había comprobado."""
    class Backend:
        last_truncated = False

        def chat(self, system, user):
            return "Sin cálculo."

    monkeypatch.setattr(app.engine, "find_rscript", lambda: "Rscript")
    monkeypatch.setattr(app.engine, "function_signatures", lambda *a, **kw: "firmas")
    monkeypatch.setattr(app.engine, "diagnose_r", lambda: {"packages": []})
    app.converse({"ask": "modelo con lavaan, normalidad con MVN y validez con semTools",
                  "profile": None, "run_r": True}, tmp_path, Backend())
    linea = [l for l in capsys.readouterr().out.splitlines() if "firma real" in l][0]
    for paquete in ("MVN", "lavaan", "semTools"):
        assert paquete in linea, (paquete, linea)
    assert "…" not in linea
