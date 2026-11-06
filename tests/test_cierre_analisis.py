"""Cierre de análisis con varias fases, consultas de ayuda y fallos de R."""
import pytest

import AnalisisR as app


class Backend:
    last_truncated = False

    def __init__(self, responses):
        self.responses = iter(responses)
        self.prompts = []
        self.systems = []

    def chat(self, system, user):
        self.systems.append(system)
        self.prompts.append(user)
        return next(self.responses)


@pytest.fixture
def calculation(tmp_path, monkeypatch):
    source = tmp_path / "source.csv"
    source.write_text("item1,item2,item3\n1,2,1\n2,3,2\n3,4,3\n", encoding="utf-8")
    profile = app.prepare_data({"data": str(source)}, tmp_path)
    monkeypatch.setattr(app.engine, "find_rscript", lambda: "Rscript")
    return dict(ask="Fiabilidad", profile=profile, run_r=True, share_output=True), tmp_path


CODE = "```r\ntabla(data.frame(alfa=0.81))\n```"
TABLE = "| Coeficiente | Valor |\n| --- | --- |\n| Alfa | 0.81 |"


def test_fiabilidad_con_mas_de_tres_calculos_llega_a_interpretacion(calculation, monkeypatch):
    request, folder = calculation
    calls = []
    monkeypatch.setattr(app.engine, "chat_run_r", lambda *a, **kw: (calls.append(a[0]) or True, TABLE))
    backend = Backend([CODE] * 4 + ["El alfa calculado es 0.81; la precisión no se ha estimado."])
    result = app.converse(request, folder, backend)
    assert len(calls) == 4 and len(result["scripts"]) == 4
    assert "El alfa calculado" in result["answer"] and TABLE in result["answer"]
    assert "No se obtuvo una respuesta final" not in result["answer"]


def test_ayuda_no_consume_el_presupuesto_de_calculos(calculation, monkeypatch):
    request, folder = calculation
    calls = []
    monkeypatch.setattr(app.engine, "chat_r_help", lambda *a, **kw: "Documentación de psych")
    monkeypatch.setattr(app.engine, "chat_run_r", lambda *a, **kw: (calls.append(a[0]) or True, TABLE))
    backend = Backend(["AYUDA: psych::alpha", "AYUDA: psych::omega", CODE, CODE, "Interpretación final."])
    result = app.converse(request, folder, backend)
    assert len(calls) == 2
    assert "Interpretación final" in result["answer"]


def test_limite_de_calculos_conserva_resultados_y_ultimo_error(calculation, monkeypatch):
    request, folder = calculation
    outputs = iter([(True, TABLE)] + [(False, "Error de omega: modelo no identificable")] * 5)
    monkeypatch.setattr(app.engine, "chat_run_r", lambda *a, **kw: next(outputs))
    backend = Backend([CODE] * 7)
    result = app.converse(request, folder, backend)
    assert len(result["scripts"]) == 6 and len(backend.prompts) == 7
    assert TABLE in result["answer"]
    assert "Error de omega: modelo no identificable" in result["answer"]
    assert "No se obtuvo una respuesta final" not in result["answer"]


def test_ultimo_error_se_muestra_aunque_el_modelo_cierre_en_texto(calculation, monkeypatch):
    request, folder = calculation
    monkeypatch.setattr(app.engine, "chat_run_r", lambda *a, **kw: (False, "Error: falta el paquete psych"))
    backend = Backend([CODE, "No fue posible estimar omega."])
    result = app.converse(request, folder, backend)
    assert "Error: falta el paquete psych" in result["answer"]
    assert "No fue posible estimar omega" in result["answer"]


def test_tras_seis_calculos_se_solicita_interpretacion_sin_mas_r(calculation, monkeypatch):
    request, folder = calculation
    calls = []
    monkeypatch.setattr(app.engine, "chat_run_r", lambda *a, **kw: (calls.append(a[0]) or True, TABLE))
    backend = Backend([CODE] * 6 + ["Interpretación de los resultados disponibles."])
    result = app.converse(request, folder, backend)
    assert len(calls) == 6 and "FASE FINAL" in backend.systems[-1]
    assert "Interpretación de los resultados disponibles" in result["answer"]


def test_las_consultas_de_ayuda_tambien_tienen_limite(calculation, monkeypatch):
    request, folder = calculation
    help_calls = []
    monkeypatch.setattr(app.engine, "chat_r_help", lambda *a, **kw: help_calls.append(a) or "Ayuda R")
    backend = Backend(["AYUDA: psych::omega"] * 4)
    result = app.converse(request, folder, backend)
    assert len(help_calls) == 3 and "límite de consultas de ayuda" in result["answer"]
    assert "No se obtuvieron resultados válidos" in result["answer"]


def test_error_de_sintaxis_en_ultimo_paso_no_se_oculta_al_cerrar(calculation, monkeypatch):
    request, folder = calculation

    def run(code, *args, **kwargs):
        if code == "invalid":
            raise app.engine.RSyntaxError("Error inesperado if")
        return True, TABLE

    monkeypatch.setattr(app.engine, "chat_run_r", run)
    backend = Backend([CODE] * 5 + ["```r\ninvalid\n```", "Solo se obtuvo alfa."])
    result = app.converse(request, folder, backend)
    assert len(result["scripts"]) == 5
    assert "Error inesperado if" in result["answer"] and "no se ejecutó" in result["answer"]


def test_fiabilidad_real_con_coefficientalpha_en_cinco_etapas(tmp_path):
    import csv
    import random

    rs = app.engine.find_rscript()
    if not rs:
        pytest.skip("Requiere Rscript")
    out, _, status = app.engine.run_process([rs, "--vanilla", "-e", 'cat(requireNamespace("coefficientalpha", quietly=TRUE))'], timeout=30)
    if status or out.strip() != "TRUE":
        pytest.skip("Requiere coefficientalpha instalado")
    source = tmp_path / "items.csv"
    rng = random.Random(42)
    with source.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow([f"item{i}" for i in range(1, 6)])
        for _ in range(100):
            factor = rng.gauss(0, 1)
            writer.writerow([factor + rng.gauss(0, 0.7) for _ in range(5)])
    profile = app.prepare_data({"data": str(source)}, tmp_path)
    codes = [
        'invisible(capture.output(fit <- coefficientalpha::alpha(dat,varphi=0,se=TRUE,test=TRUE,complete=TRUE))); '
        's <- cov(dat); k <- ncol(dat); stopifnot(abs(fit$alpha-k/(k-1)*(1-sum(diag(s))/sum(s)))<1e-6); '
        'tabla(data.frame(Alfa_bruto=fit$alpha,SE=as.numeric(fit$se),F=fit$fit[1],df1=fit$fit[2],df2=fit$fit[3],p=fit$fit[4]))',
        'y <- as.data.frame(scale(dat)); invisible(capture.output(fit <- coefficientalpha::alpha(y,varphi=0,se=TRUE,test=TRUE,complete=TRUE))); '
        'tabla(data.frame(Alfa_estandarizado=fit$alpha,SE=as.numeric(fit$se)))',
        'invisible(capture.output(fit <- coefficientalpha::omega(dat,varphi=0,se=TRUE,test=TRUE,complete=TRUE))); '
        'tabla(data.frame(Omega_total=fit$omega,SE=as.numeric(fit$se),IC_inf=fit$omega-qnorm(.975)*as.numeric(fit$se),IC_sup=fit$omega+qnorm(.975)*as.numeric(fit$se)))',
        'y <- as.data.frame(scale(dat)); invisible(capture.output(fit <- coefficientalpha::omega(y,varphi=0,se=TRUE,test=TRUE,complete=TRUE))); '
        'tabla(data.frame(Omega_estandarizado=fit$omega,SE=as.numeric(fit$se)))',
        'items <- lapply(seq_len(ncol(dat)),function(j) { y <- dat[,-j,drop=FALSE]; '
        'invisible(capture.output(a <- coefficientalpha::alpha(y,varphi=0,se=FALSE,test=FALSE,complete=TRUE))); '
        'invisible(capture.output(o <- coefficientalpha::omega(y,varphi=0,se=FALSE,test=FALSE,complete=TRUE))); '
        'stopifnot(nrow(o$y)==nrow(dat),ncol(o$y)==ncol(dat)-1,is.finite(a$alpha),is.finite(o$omega)); '
        'data.frame(Item=names(dat)[j],Alfa_sin_item=a$alpha,Omega_sin_item=o$omega) }); tabla(do.call(rbind,items))',
    ]
    backend = Backend(["```r\n" + code + "\n```" for code in codes] + ["Coeficientes calculados; revisar dimensionalidad."])
    result = app.converse(dict(ask="Fiabilidad", profile=profile, run_r=True, share_output=True), tmp_path, backend)
    assert len(result["scripts"]) == 5
    assert all(label.replace("_", r"\_") in result["answer"]
               for label in ("Alfa_bruto", "Alfa_estandarizado", "Omega_total", "Omega_estandarizado", "Alfa_sin_item", "Omega_sin_item"))
    assert "Último error" not in result["answer"]


SIN_CERCA = """# =====================================
# BLOQUE 3: alfa ordinal
# =====================================
items <- c("SV1","SV2","SV3")
X <- dat[, items, drop=FALSE]
cat("n:", nrow(X), "\n")
tabla(data.frame(alfa=0.81))
"""


def test_el_codigo_sin_cerca_se_pide_otra_vez_en_lugar_de_mostrarse(calculation, monkeypatch):
    """Sin esto el bloque llegaba como prosa: el usuario veía el código y ningún resultado."""
    request, folder = calculation
    calls = []
    monkeypatch.setattr(app.engine, "chat_run_r", lambda *a, **kw: (calls.append(a[0]) or True, TABLE))
    backend = Backend([SIN_CERCA, CODE, "El alfa calculado es 0.81."])
    result = app.converse(request, folder, backend)
    assert len(calls) == 1, "el código reenviado con cerca debe ejecutarse"
    assert "cerca de apertura" in backend.prompts[1]
    assert "items <- c" not in result["answer"], "el código no puede acabar en la respuesta"
    assert "El alfa calculado" in result["answer"] and TABLE in result["answer"]


def test_solo_se_reclama_la_cerca_una_vez(calculation, monkeypatch):
    request, folder = calculation
    monkeypatch.setattr(app.engine, "chat_run_r", lambda *a, **kw: (True, TABLE))
    backend = Backend([SIN_CERCA, SIN_CERCA])
    result = app.converse(request, folder, backend)
    assert len(backend.prompts) == 2
    assert "BLOQUE 3" in result["answer"]


def test_una_interpretacion_normal_no_se_confunde_con_codigo():
    assert not app.engine.unfenced_r(TABLE)
    assert not app.engine.unfenced_r("El alfa es 0.81 y el omega 0.83; la precisión es estrecha.")
    assert app.engine.unfenced_r(SIN_CERCA)
