"""La receta de la plantilla de normalidad se ejecuta de verdad en R, sin endpoint.

Es la única forma de distinguir un fallo del modelo de un fallo de la receta: aquí el
código es exactamente el que la plantilla pide, pasado por el envoltorio y el filtro
reales de la aplicación.
"""
import csv
import math
import random

import pytest

import AnalisisR as app
import analisisr_core as engine

RSCRIPT = engine.find_rscript()

# Lo que la plantilla pide: una llamada por prueba, sin argumentos de más.
CODIGO = """
vars <- c("extraversion", "optimism", "satisfaccion")
sub <- dat[, vars, drop = FALSE]
completos <- sum(stats::complete.cases(sub))
cat("n analizado:", completos, "de", nrow(sub), "\\n")
cat("ausentes por variable:", paste(colSums(is.na(sub)), collapse = ", "), "\\n")

limpia_p <- function(p) suppressWarnings(as.numeric(sub(">", "", sub("<", "", trimws(as.character(p))))))
k <- length(vars)

multi <- do.call(rbind, lapply(c("mardia", "hz", "hw", "royston", "doornik_hansen", "energy"),
  function(prueba) {
    set.seed(2026)
    r <- MVN::mvn(sub, mvn_test = prueba)$multivariate_normality
    p <- limpia_p(r$p.value)
    gl <- if ("df" %in% names(r)) as.character(r$df) else
      ifelse(grepl("Skewness", r$Test), as.character(k * (k + 1) * (k + 2) / 6),
      ifelse(grepl("Kurtosis", r$Test), "- normal estandar",
      ifelse(grepl("Henze", r$Test), "- aproximacion lognormal",
      ifelse(grepl("Royston", r$Test), "- gl equivalentes no devueltos", "- remuestreo"))))
    data.frame(Prueba = as.character(r$Test), Estadistico = r$Statistic,
               gl = gl, p = r$p.value, Metodo = as.character(r$Method),
               Conclusion = ifelse(isTRUE(any(is.na(p))), "no evaluable",
                            ifelse(p < 0.05, "se rechaza", "no se rechaza")),
               Coincide = grepl("Not normal", as.character(r$MVN)) == (p < 0.05))
  }))
tabla(multi)

uni <- do.call(rbind, lapply(c("SW", "SF", "AD", "CVM", "Lillie"), function(prueba) {
  r <- MVN::mvn(sub, univariate_test = prueba)$univariate_normality
  data.frame(Prueba = as.character(r$Test), Variable = as.character(r$Variable),
             Estadistico = r$Statistic, p = r$p.value, limpio = limpia_p(r$p.value))
}))
uni$p_holm <- stats::p.adjust(uni$limpio, method = "holm")
tabla(uni[, c("Prueba", "Variable", "Estadistico", "p", "p_holm")])

d <- MVN::mvn(sub, mvn_test = "hz")$descriptives
cat("columnas de descriptives:", paste(names(d), collapse = ", "), "\\n")
tabla(data.frame(n = d$n, Skew = d$Skew, Kurtosis = d$Kurtosis))
"""


@pytest.fixture
def datos(tmp_path):
    """406 filas con ausentes y asimetría, como el caso real del usuario."""
    random.seed(7)
    filas = []
    for i in range(406):
        extra = random.gauss(0, 1) if i >= 6 else ""
        opt = random.gauss(0, 1) if i >= 8 or i < 6 else ""
        filas.append([extra, opt, round(math.exp(random.gauss(0, 0.6)), 4)])
    ruta = tmp_path / "datos.csv"
    with ruta.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["extraversion", "optimism", "satisfaccion"])
        w.writerows(filas)
    return ruta


@pytest.mark.skipif(not RSCRIPT, reason="Requiere Rscript")
def test_la_receta_de_normalidad_corre_en_r_sin_errores(datos, tmp_path):
    if "MVN" not in [p["package"] for p in engine.diagnose_r()["packages"] if p["installed"]]:
        pytest.skip("Requiere el paquete MVN")
    assert engine.chat_r_guard(CODIGO) is None, "el filtro de la app rechazaría este bloque"
    perfil = {"file": str(datos), "data_for_r": str(datos)}
    ok, salida = engine.chat_run_r(CODIGO, perfil, RSCRIPT, timeout=300, temp_dir=tmp_path)
    assert ok, salida
    # Las once pruebas pedidas aparecen en la salida.
    for prueba in ("Mardia Skewness", "Mardia Kurtosis", "Henze-Zirkler", "Henze-Wagner",
                   "Royston", "Doornik-Hansen", "E-Statistic",
                   "Shapiro-Wilk", "Shapiro-Francia", "Anderson-Darling",
                   "Cramer-von Mises", "Lilliefors"):
        assert prueba in salida, (prueba, salida[:2000])
    # Grados de libertad: los de la asimetría de Mardia son k(k+1)(k+2)/6 = 10 con k=3.
    assert "10" in salida and "aproximacion lognormal" in salida
    assert "- remuestreo" in salida and "gl equivalentes no devueltos" in salida
    # La conclusión nunca contradice al p.
    assert "FALSE" not in salida.split("Coincide")[1][:400] if "Coincide" in salida else True
    assert "Error" not in salida and "no se pudo" not in salida
