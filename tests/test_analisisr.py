"""Datos copiados, consentimiento de salida R y ventana de AnalisisR."""
import json
import os
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import AnalisisR as app


@pytest.fixture
def data(tmp_path):
    path = tmp_path / "origen.csv"
    path.write_text("x,y\n1,10\n2,20\n3,30\n", encoding="utf-8")
    folder = tmp_path / "sesion"
    folder.mkdir()
    return path, folder


def test_preparacion_recodifica_copia_y_limita_columnas(data):
    source, folder = data
    original = source.read_bytes()
    profile = app.prepare_data({"data": str(source), "recode": "x = invertir 1..3",
                                "keep": ["x"], "classes": {"x": "ordinal"}}, folder)
    assert source.read_bytes() == original
    assert (folder / "datos.csv").read_text() == "x\n3\n2\n1\n"
    assert profile["n_cols"] == 1
    assert profile["columns"][0]["class"] == "ordinal"
    assert profile["recoding"][0]["n_changed"] == 2
    # Junto al archivo del usuario solo puede aparecer el sidecar de tipos que él declara.
    vecinos = {f.name for f in source.parent.iterdir() if f.is_file()}
    assert vecinos == {source.name, "origen.analisisr.json"}
    assert json.loads((source.parent / "origen.analisisr.json").read_text(encoding="utf-8"))["classes"] == {
        "x": "ordinal", "y": "ordinal"}


def test_seleccion_vacia_no_se_admite(data):
    source, folder = data
    with pytest.raises(ValueError, match="Selecciona"):
        app.prepare_data({"data": str(source), "keep": []}, folder)


def test_columnas_duplicadas_no_se_admiten(data):
    source, folder = data
    source.write_text("x,x\n1,2\n")
    with pytest.raises(ValueError, match="únicos"):
        app.prepare_data({"data": str(source)}, folder)


class Backend:
    last_truncated = False

    def __init__(self, responses):
        self.responses = iter(responses)
        self.prompts = []

    def chat(self, system, user):
        self.prompts.append(user)
        return next(self.responses)


@pytest.mark.parametrize("share", [False, True])
def test_salida_r_solo_se_envia_con_consentimiento(data, monkeypatch, share):
    source, folder = data
    profile = app.prepare_data({"data": str(source)}, folder)
    monkeypatch.setattr(app.engine, "find_rscript", lambda: "Rscript")
    monkeypatch.setattr(app.engine, "chat_run_r", lambda *a, **kw: (True, "PRIVADO 12345"))
    backend = Backend(["```r\nprint(mean(dat$x))\n```", "La media es 2."])
    result = app.converse({"profile": profile, "ask": "Calcula la media", "run_r": True,
                           "share_output": share}, folder, backend)
    assert len(backend.prompts) == (2 if share else 1)
    assert ("PRIVADO" in "\n".join(backend.prompts)) == share
    assert result["scripts"]
    assert (folder / "salida_1.txt").exists()
    if not share:
        assert "PRIVADO" not in result["context_answer"]


def test_r_desactivado_no_ejecuta(data, monkeypatch):
    _, folder = data
    monkeypatch.setattr(app.engine, "chat_run_r", lambda *a, **kw: pytest.fail("R desactivado"))
    response = "```r\nprint(1)\n```"
    assert app.converse({"ask": "ejemplo", "run_r": False}, folder,
                        Backend([response]))["answer"] == response


@pytest.mark.parametrize("share", [False, True])
def test_salida_tabular_se_muestra_sin_bloque_de_consola(data, monkeypatch, share):
    source, folder = data
    profile = app.prepare_data({"data": str(source)}, folder)
    table = "| Variable | Media |\n| --- | --- |\n| x | 2 |"
    monkeypatch.setattr(app.engine, "find_rscript", lambda: "Rscript")
    monkeypatch.setattr(app.engine, "chat_run_r", lambda *a, **kw: (True, table))
    backend = Backend(['```r\ntabla(data.frame(Variable="x", Media=mean(dat$x)))\n```', table])
    result = app.converse({"profile": profile, "ask": "Media", "run_r": True,
                           "share_output": share}, folder, backend)
    assert table in result["answer"]
    assert "```" not in result["answer"]
    assert len(backend.prompts) == (2 if share else 1)
    if not share:
        assert table not in result["context_answer"]


@pytest.mark.parametrize("share", [False, True])
def test_resultados_siempre_tienen_tabla_sin_pedirlo(data, monkeypatch, share):
    source, folder = data
    profile = app.prepare_data({"data": str(source)}, folder)
    monkeypatch.setattr(app.engine, "find_rscript", lambda: "Rscript")
    monkeypatch.setattr(app.engine, "chat_run_r", lambda *a, **kw: (True, "[1] 2.5"))
    backend = Backend(["```r\nprint(mean(dat$x))\n```", "La media es 2.5."])
    result = app.converse({"profile": profile, "ask": "Calcula la media", "run_r": True,
                           "share_output": share}, folder, backend)
    assert app.MARKDOWN_TABLE.search(result["answer"])
    assert "```text" not in result["answer"]
    assert all(app.RESULT_FORMAT in prompt for prompt in backend.prompts)
    if not share:
        assert "2.5" not in result["context_answer"]


def test_tablas_encerradas_en_bloques_se_muestran_como_tablas():
    table = "| Variable | Media |\n| --- | --- |\n| x | 2 |"
    assert app.format_r_output("```markdown\n" + table + "\n```", True) == table
    assert app.unfence_tables("Texto\n\n```text\n" + table + "\n```\n") == "Texto\n\n" + table + "\n"
    assert app.format_r_output("Error en round()", False).startswith("```text")


def test_r_real_imprime_tablas_con_nombres_ausentes_y_caracteres_especiales(data):
    rs = app.engine.find_rscript()
    if not rs:
        pytest.skip("Requiere Rscript")
    source, folder = data
    profile = app.prepare_data({"data": str(source)}, folder)
    code = r'''tabla(data.frame(Etiqueta=c("a|b", "línea\nnueva"),
                              Valor=c(mean(dat$x), NA), row.names=c("uno", "dos")))'''
    ok, output = app.engine.chat_run_r(code, profile, rs)
    assert ok, output
    assert "| Variable | Etiqueta | Valor |" in output
    assert "| uno | a\\|b | 2 |" in output
    assert "| dos | línea nueva | NA |" in output


@pytest.mark.parametrize("code", ['system("echo test")', 'write.csv(dat, "copy.csv")'])
def test_filtro_r_se_conserva(data, monkeypatch, code):
    _, folder = data
    monkeypatch.setattr(app.engine, "run_process", lambda *a, **kw: pytest.fail("Código bloqueado"))
    ok, message = app.engine.chat_run_r(code, {}, "Rscript")
    assert not ok
    assert message


def test_diccionario_no_envia_valores(data):
    source, folder = data
    source.write_text("grupo,valor\nPRIVADO_A,12345.678\nPRIVADO_B,23456.789\n", encoding="utf-8")
    profile = app.prepare_data({"data": str(source)}, folder)
    backend = Backend(["Respuesta sin cálculo"])
    app.converse({"ask": "Describe las variables", "profile": profile}, folder, backend)
    prompt = "\n".join(backend.prompts)
    for private in ("PRIVADO_A", "PRIVADO_B", "12345.678", "23456.789"):
        assert private not in prompt


def test_worker_informa_errores(data):
    _, folder = data
    request = folder / "request.json"
    app.write_json(request, {"action": "desconocida"})
    assert app.worker(request) == 1
    assert "desconocida" in json.loads((folder / "result.json").read_text())["error"]
    assert (folder / "manifest.json").exists()


def test_worker_como_proceso_hijo(data):
    source, folder = data
    request = folder / "request.json"
    app.write_json(request, {"action": "profile", "data": str(source), "keep": ["x"]})
    out, err, code = app.engine.run_process([sys.executable, str(Path(app.__file__).resolve()),
                                           "--worker", str(request)], timeout=30)
    assert code == 0, out + err
    profile = json.loads((folder / "result.json").read_text(encoding="utf-8"))
    assert profile["n_cols"] == 1
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["artifacts"]["datos.csv"]["sha256"] == app.engine.sha256_file(folder / "datos.csv")


def test_r_real_lee_copia_recodificada(data):
    rs = app.engine.find_rscript()
    if not rs:
        pytest.skip("Requiere Rscript")
    source, folder = data
    profile = app.prepare_data({"data": str(source), "recode": "x = invertir 1..3",
                                "keep": ["x"]}, folder)
    ok, output = app.engine.chat_run_r('stopifnot(ncol(dat) == 1, dat$x[1] == 3); cat("OK_ANALISISR")',
                                      profile, rs)
    assert ok, output
    assert "OK_ANALISISR" in output


def test_descriptivos_resumen_columnas_y_no_sus_nombres(data):
    rs = app.engine.find_rscript()
    if not rs:
        pytest.skip("Requiere Rscript")
    source, folder = data
    source.write_text("x,y,grupo\n1,10,A\n3,,B\n5,30,A\n", encoding="utf-8")
    profile = app.prepare_data({"data": str(source)}, folder)
    bad, _ = app.engine.chat_run_r('vars <- c("x", "y"); round(sapply(vars, median, na.rm=TRUE), 2)', profile, rs)
    assert not bad
    code = '''vars <- c("x", "y", "grupo")
res <- descriptivos(dat[, vars, drop=FALSE])
stopifnot(res$Media[1] == 3, res$DE[1] == 2, res$Mediana[1] == 3,
          res$RIC[1] == 2, res$Media[2] == 20, res$Ausentes[2] == 1,
          is.na(res$Media[3]), nzchar(res$Observaciones[3]))
tabla(res)'''
    ok, output = app.engine.chat_run_r(code, profile, rs)
    assert ok, output
    assert "No numérica" in output
    assert "mean.default" not in output and "round(" not in output


def test_descriptivos_soportan_columnas_vacias_y_un_solo_dato(data):
    rs = app.engine.find_rscript()
    if not rs:
        pytest.skip("Requiere Rscript")
    source, folder = data
    profile = app.prepare_data({"data": str(source)}, folder)
    code = '''res <- descriptivos(data.frame(vacia=rep(NA_real_,3), unica=c(7,NA,NA)))
stopifnot(res$Ausentes[1] == 3, is.na(res$Media[1]),
          res$Media[2] == 7, is.na(res$DE[2]), res$RIC[2] == 0)
tabla(res)'''
    ok, output = app.engine.chat_run_r(code, profile, rs)
    assert ok, output


def test_ventana_seleccion_historial_y_credenciales(data, monkeypatch):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    pytest.importorskip("PySide6")
    import analisisr_ui as ui

    qt = ui.QApplication.instance() or ui.QApplication([])
    source, folder = data
    monkeypatch.setattr(app.secrets, "load", lambda: {})
    window = app.create_window()
    try:
        assert window.tabs.count() == 4
        assert window.run_r.isChecked()
        assert window.share.isChecked()
        profile = app.prepare_data({"data": str(source)}, folder)
        window.loaded(profile)
        window.applied_request = window.data_request()
        assert window.data_request()["keep"] == ["x", "y"]
        window.answered("Mi pregunta <b>literal</b>", {
            "answer": "SALIDA PRIVADA", "context_answer": "Salida local"})
        calls = []
        monkeypatch.setattr(window, "start", lambda *args: calls.append(args))
        window.question.setPlainText("Continúa")
        window.send_chat()
        assert calls[0][1]["history"][-1]["content"] == "Salida local"
        assert "<b>literal</b>" in window.chat.toPlainText()
        window.model.setText("otro-modelo")
        assert window.history == []
        assert qt is not None
    finally:
        window.close()
