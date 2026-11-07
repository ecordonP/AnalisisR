"""Metadatos de tipos reutilizables, binarias en 0/1 y codificación del diseño."""
import json
from pathlib import Path

import pytest

import AnalisisR as app
import analisisr_core as engine

MODELOS = ("ANCOVA", "Análisis de supervivencia", "Moderación", "Modelo multinivel",
           "Regresión", "Regresión logística", "Regresión multinomial", "Regresión ordinal",
           "Regresión para recuentos")


@pytest.fixture
def datos(tmp_path):
    source = tmp_path / "origen.csv"
    source.write_text("sexo,nivel,y\nHombre,bajo,10\nMujer,alto,12\n"
                      "Hombre,medio,9\nMujer,alto,15\n", encoding="utf-8")
    return source, tmp_path


def test_los_tipos_declarados_se_guardan_junto_a_los_datos(datos):
    source, folder = datos
    tipos = {"sexo": "binary", "nivel": "nominal", "y": "continuous"}
    profile = app.prepare_data({"data": str(source), "classes": tipos}, folder)
    sidecar = Path(profile["metadata_file"])
    assert sidecar == engine.metadata_path(source) and sidecar.is_file()
    guardado = json.loads(sidecar.read_text(encoding="utf-8"))
    assert guardado["schema"] == "analizar.metadata/1"
    assert guardado["classes"] == tipos and guardado["data_file"] == source.name


def test_importar_de_nuevo_recupera_los_tipos_declarados(datos):
    source, folder = datos
    app.prepare_data({"data": str(source), "classes": {"sexo": "binary", "nivel": "nominal",
                                                       "y": "ordinal"}}, folder)
    # Una importación posterior no envía tipos: deben venir del sidecar.
    reimportado = app.prepare_data({"data": str(source)}, folder)
    assert {c["column"]: c["class"] for c in reimportado["columns"]}["y"] == "ordinal"
    assert reimportado["metadata_applied"]["source"] == str(engine.metadata_path(source))
    assert "metadata_file" not in reimportado


def test_importar_sin_declarar_tipos_no_escribe_junto_a_los_datos(datos):
    source, folder = datos
    profile = app.prepare_data({"data": str(source)}, folder)
    assert not engine.metadata_path(source).exists()
    assert "metadata_file" not in profile


def test_metadatos_ilegibles_no_rompen_la_importacion(datos):
    source, folder = datos
    engine.metadata_path(source).write_text("{esto no es json", encoding="utf-8")
    profile = app.prepare_data({"data": str(source)}, folder)
    assert profile["n_cols"] == 3


def test_las_binarias_se_recodifican_a_cero_y_uno_con_la_primera_como_referencia(datos):
    source, folder = datos
    profile = app.prepare_data({"data": str(source), "classes": {"sexo": "binary"}}, folder)
    cambio = next(c for c in profile["binarizing"] if c["column"] == "sexo")
    assert cambio["recoded"] and cambio["reference"] == "Hombre" and cambio["event"] == "Mujer"
    assert cambio["mapping"] == {"Hombre": "0", "Mujer": "1"}
    filas = (folder / "datos.csv").read_text(encoding="utf-8").splitlines()
    assert filas[0].split(",")[0] == "sexo"
    assert [fila.split(",")[0] for fila in filas[1:]] == ["0", "1", "0", "1"]


def test_los_codigos_numericos_se_ordenan_como_en_r(tmp_path):
    source = tmp_path / "codigos.csv"
    source.write_text("grupo\n2\n1\n2\n1\n", encoding="utf-8")
    profile = app.prepare_data({"data": str(source), "classes": {"grupo": "binary"}}, tmp_path)
    cambio = profile["binarizing"][0]
    assert cambio["reference"] == "1" and cambio["mapping"] == {"1": "0", "2": "1"}


def test_las_etiquetas_de_valor_siguen_a_los_codigos_nuevos():
    header = ["sexo"]
    body = [["1"], ["2"], ["1"]]
    libro = {"value_labels": {"sexo": {"1": "Hombre", "2": "Mujer"}}}
    body, cambios, nuevo = engine.binarize(header, body, ["sexo"], libro)
    assert [fila[0] for fila in body] == ["0", "1", "0"]
    assert nuevo["value_labels"]["sexo"] == {"0": "Hombre", "1": "Mujer"}
    assert cambios[0]["labels"] == {"0": "Hombre", "1": "Mujer"}
    # El codebook original no se modifica.
    assert libro["value_labels"]["sexo"] == {"1": "Hombre", "2": "Mujer"}


def test_los_ausentes_y_las_no_binarias_no_se_tocan():
    header = ["sexo", "edad"]
    body = [["Hombre", "30"], ["", "41"], ["Mujer", "52"], ["NA", "60"]]
    body, cambios, _ = engine.binarize(header, body, ["sexo"], {})
    assert [fila[0] for fila in body] == ["0", "", "1", "NA"]
    assert [fila[1] for fila in body] == ["30", "41", "52", "60"]
    assert len(cambios) == 1


def test_una_columna_ya_en_cero_uno_o_con_otras_categorias_se_informa_sin_cambiar():
    body = [["0"], ["1"], ["0"]]
    body, cambios, _ = engine.binarize(["x"], body, ["x"], {})
    assert not cambios[0]["recoded"] and cambios[0]["reason"] == "ya estaba en 0/1"
    assert [fila[0] for fila in body] == ["0", "1", "0"]
    tres = [["a"], ["b"], ["c"]]
    tres, cambios, _ = engine.binarize(["x"], tres, ["x"], {})
    assert not cambios[0]["recoded"] and "3 categorías" in cambios[0]["reason"]
    assert [fila[0] for fila in tres] == ["a", "b", "c"], "no debe recodificar lo que no es binario"


@pytest.mark.parametrize("name", MODELOS)
def test_las_plantillas_de_modelo_exigen_codificacion_indicadora(name):
    prompt = app.TEMPLATES[name]
    for pieza in ("contr.treatment", "k-1 variables indicadoras", "primera categoría",
                  "recodificadas a 0 y 1", "variable_categoria"):
        assert pieza in prompt, (name, pieza)


def test_ninguna_plantilla_permite_decidir_con_un_na():
    for name, prompt in app.TEMPLATES.items():
        assert "isTRUE()" in prompt, name


def test_el_prompt_de_afc_avisa_del_p_de_texto_de_mvn():
    prompt = app.TEMPLATES["Análisis factorial confirmatorio"]
    assert "sub('>', '', sub('<', '', trimws(as.character(p.value))))" in prompt
    # El patrón no puede llevar corchetes: el relleno de plantillas los toma por campos.
    assert "[" not in prompt.replace("[factores]", "")
    assert "TRUE/FALSE es necesario" in prompt and "grepl('Not normal'" in prompt


def test_ningun_prompt_usa_corchetes_fuera_de_sus_campos():
    """Un corchete que no sea un campo rompería el relleno de la consulta."""
    import re

    for name, prompt in app.TEMPLATES.items():
        campos = set(re.findall(r"\[([^\]]+)\]", prompt))
        limpio = re.sub(r"\[([^\]]+)\]", "", prompt)
        assert "[" not in limpio and "]" not in limpio, name
        assert campos <= {"variables", "predictores", "ítems", "covariables", "medidas",
                          "evaluaciones", "factores", "grupo", "agrupamiento", "respuesta",
                          "puntuación", "antes", "después", "variable_1", "variable_2",
                          "filas", "columnas", "exposición", "predictor", "mediador",
                          "moderador", "tiempo", "evento",
                          "pruebas_multivariantes", "pruebas_univariantes"}, (name, campos)


@pytest.fixture
def ventana(tmp_path, monkeypatch):
    import os

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
    yield view
    view.close()
    qt.processEvents()


def test_reimportar_con_tipos_guardados_carga_los_datos_y_lo_registra(ventana, datos):
    """Un fallo al registrar los tipos recuperados abortaba la importación con «'class'»."""
    view, (source, folder) = ventana, datos
    app.prepare_data({"data": str(source), "classes": {"sexo": "binary", "nivel": "nominal",
                                                       "y": "ordinal"}}, folder)
    reimportado = app.prepare_data({"data": str(source)}, folder)
    view.loaded(reimportado)
    registro = view.log.toPlainText()
    assert view.profile is reimportado
    assert view.table.rowCount() == 3
    assert "Tipos recuperados del archivo de metadatos" in registro
    # Solo se registran los tipos que difieren de los detectados.
    assert "sexo: nominal → binary" in registro
    assert "Variable binaria sexo recodificada a 0/1: Hombre=0 (referencia), Mujer=1" in registro


def test_un_cambio_con_claves_inesperadas_no_impide_cargar(ventana, datos):
    view, (source, folder) = ventana, datos
    profile = app.prepare_data({"data": str(source)}, folder)
    profile["metadata_applied"] = {"applied": [{"otra_clave": "valor"}]}
    profile["binarizing"] = [{"recoded": True}]
    view.loaded(profile)
    assert view.profile is profile and view.table.rowCount() == 3


def test_la_correlacion_admite_varias_variables_y_elige_el_metodo():
    """Antes solo aceptaba un par fijo; ahora es una matriz con método por par."""
    prompt = app.TEMPLATES["Correlación"]
    assert "[variables]" in prompt
    assert "[variable_1]" not in prompt and "[variable_2]" not in prompt
    for pieza in ("todos los pares", "par a par", "Shapiro–Wilk", "MVN::mvn",
                  "punto-biserial", "phi", "V de Cramer", "k(k-1)/2", "Holm"):
        assert pieza in prompt, pieza


def test_levene_recibe_el_grupo_como_factor():
    """Las binarias llegan como 0/1: con una columna numérica car::leveneTest se detiene."""
    for name in ("Diferencia entre medias", "ANOVA"):
        prompt = app.TEMPLATES[name]
        assert "factor(grupo), center = median" in prompt, name
        assert "not appropriate with quantitative explanatory variables" in prompt, name


def test_ninguna_plantilla_permite_objetos_numerados_por_grupo():
    for name, prompt in app.TEMPLATES.items():
        assert "desc_g1" in prompt and "do.call(rbind, ...)" in prompt, name


def test_cada_plantilla_trae_su_bibliografia_citable():
    """La lista es cerrada: sin ella el modelo inventaría autores, años y DOI."""
    import re

    assert set(app.REFERENCIAS) == set(app.TEMPLATES)
    for name, obras in app.REFERENCIAS.items():
        assert len(obras) >= 3, name
        for obra in obras:
            # APA mínima: autor, año entre paréntesis y título.
            assert re.search(r"\(\d{4}\)\.", obra), (name, obra)
            assert '"' not in obra and "[" not in obra and "]" not in obra, (name, obra)
            assert obra in app.TEMPLATES[name], (name, obra)


def test_el_prompt_prohibe_citar_fuera_de_la_lista():
    for name, prompt in app.TEMPLATES.items():
        assert "sección final titulada Referencias" in prompt, name
        assert "No añadas ninguna obra que no esté en la lista" in prompt, name
        assert "no inventes autores, años, páginas ni DOI" in prompt, name
        assert "R.version.string" in prompt, name


def test_una_consulta_libre_recibe_bibliografia_de_su_tema():
    """Las plantillas la llevan dentro; el texto libre la recibe por el tema detectado."""
    obras = app.bibliografia_para("modelo de segundo orden con lavaan y normalidad multivariante")
    assert obras, "una consulta de SEM debe traer bibliografía"
    assert any("Kline" in o for o in obras) and any("MVN" in o for o in obras)
    assert len(obras) == len(set(obras)), "no debe repetir obras entre temas"
    assert app.bibliografia_para("hola") == []


def test_la_bibliografia_libre_llega_al_contexto(tmp_path, monkeypatch):
    class Backend:
        last_truncated = False

        def __init__(self):
            self.prompts = []

        def chat(self, system, user):
            self.prompts.append(user)
            return "Sin cálculo."

    monkeypatch.setattr(app.engine, "find_rscript", lambda: None)
    backend = Backend()
    app.converse({"ask": "Haz una regresión logística de compra sobre edad",
                  "profile": None, "run_r": False}, tmp_path, backend)
    assert "BIBLIOGRAFÍA DE ESTA CONSULTA" in backend.prompts[0]
    assert "Hosmer" in backend.prompts[0]
