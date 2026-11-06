"""Motor propio de AnalisisR: datos, endpoints y ejecucion local de R.

Modulo autonomo: no depende de ningun otro proyecto ni de instalaciones externas.
"""
from __future__ import annotations

import csv

import datetime as _dt

import io

import hashlib

import glob

import json

import math

import os

import re

import shutil

import analisisr_secrets as _secrets
import analisisr_session as _session

import statistics as st

import subprocess

import tempfile

import time

import sys

import urllib.request

from pathlib import Path

T0 = _dt.datetime.now()

def log(msg: str) -> None:
    print(f"[{(_dt.datetime.now() - T0).total_seconds():6.1f}s] {msg}", flush=True)

def strip_think(t: str) -> str:
    """Elimina bloques de razonamiento <think>..</think> del backend."""
    t = re.sub(r"<think\b[^>]*>.*?(?:</think>|$)", "", t, flags=re.S | re.I)
    return t.strip()

def extract_r(text: str) -> str:
    """Devuelve el primer bloque de codigo R de la respuesta del modelo.
    Si la cerca de cierre NO aparece, devuelve el contenido igualmente: es probable
    que la respuesta se haya truncado por limite de tokens. No se adivina el resto.
    """
    m = re.search(r"```(?:r|R)[^\n]*\n(.*?)```", text, flags=re.S)
    if m:
        return m.group(1).strip()
    # Cerca de apertura SIN cierre => respuesta probablemente truncada por limite de tokens.
    m = re.search(r"```(?:r|R)[^\n]*\n(.*)$", text, flags=re.S)
    if m:
        return m.group(1).strip()
    m = re.search(r"```\s*\n(.*?)```", text, flags=re.S)
    if m and re.search(r"\blavaan|psych::|glm\(|polr\(", m.group(1)):
        return m.group(1).strip()
    if "```" in text:                    # hay cerca pero no se pudo clasificar
        return ""
    if re.search(r"^\s*(library|suppressMessages|d <-|fit <-)", text, flags=re.M):
        return text.strip()
    return ""

# AnalisisR no incluye R: usa la instalación del usuario, igual que EasySEM.
RSCRIPT_NAME = "Rscript.exe" if sys.platform.startswith("win") else "Rscript"
# Windows guarda además los binarios en bin/x64; mac y Linux solo en bin.
RSCRIPT_SUBDIRS = (("bin",), ("bin", "x64")) if sys.platform.startswith("win") else (("bin",),)
R_CONFIG = "entorno_r.json"


def configured_r_home() -> str:
    """Instalación de R elegida en la pestaña Entorno R; cadena vacía si no hay ninguna."""
    try:
        saved = json.loads((_secrets.config_dir() / R_CONFIG).read_text(encoding="utf-8"))
        return str(saved.get("r_home", "")) if isinstance(saved, dict) else ""
    except (OSError, ValueError):
        return ""


def save_r_home(home: str) -> Path:
    """Guarda la instalación elegida, o la olvida con una cadena vacía."""
    target = _secrets.config_dir() / R_CONFIG
    target.parent.mkdir(parents=True, exist_ok=True)
    with _session.temporary_file() as temporary:
        temporary.write_text(json.dumps({"r_home": str(home or "")}, ensure_ascii=False, indent=2),
                             encoding="utf-8")
        _session.replace_file(temporary, target)
    return target


def detected_r_homes() -> list[Path]:
    """Instalaciones de R habituales del sistema, de la más reciente a la más antigua."""
    if sys.platform.startswith("win"):
        patterns = ("C:/Program Files/R/R-*", "C:/Program Files/Microsoft/R Open/R-*")
    elif sys.platform == "darwin":
        patterns = ("/Library/Frameworks/R.framework/Versions/*/Resources",
                    "/opt/homebrew/lib/R", "/usr/local/lib/R")
    else:
        patterns = ("/usr/lib/R", "/usr/lib64/R", "/usr/local/lib/R", "/opt/R/*/lib/R")
    homes: list[Path] = []
    for pattern in patterns:
        homes += sorted((Path(found) for found in glob.glob(pattern)), reverse=True)
    return homes


def rscript_in(home) -> Path | None:
    """Rscript dentro de una instalación de R, o None si esa carpeta no lo contiene."""
    for parts in RSCRIPT_SUBDIRS:
        candidate = Path(home).joinpath(*parts, RSCRIPT_NAME)
        if candidate.is_file():
            return candidate
    return None


def find_rscript() -> str | None:
    """Busca Rscript en R_HOME, la ruta configurada, el PATH y las instalaciones detectadas.

    Es la única pieza de R que AnalisisR necesita: todo el cálculo va por subproceso,
    así que con encontrar Rscript basta. Sin R no hay alternativa en Python.
    """
    for home in (os.environ.get("R_HOME"), configured_r_home()):
        found = rscript_in(home) if home else None
        if found:
            return str(found)
    found = shutil.which(RSCRIPT_NAME) or shutil.which("Rscript")
    if found:
        return found
    for home in detected_r_homes():
        found = rscript_in(home)
        if found:
            return str(found)
    return None

TEXT_FORMATS = {
    ".csv": "CSV", ".txt": "texto delimitado", ".tsv": "TSV", ".dat": "texto delimitado",
}

R_FORMATS = {
    ".xlsx": ("readxl", "read_excel", "Excel (.xlsx)"),
    ".xlsm": ("readxl", "read_excel", "Excel (.xlsm)"),
    ".xls": ("readxl", "read_excel", "Excel 97-2003 (.xls)"),
    ".sav": ("haven", "read_sav", "IBM SPSS (.sav)"),
    ".zsav": ("haven", "read_sav", "IBM SPSS comprimido (.zsav)"),
    ".por": ("haven", "read_por", "IBM SPSS portable (.por)"),
    ".dta": ("haven", "read_dta", "Stata (.dta)"),
    ".sas7bdat": ("haven", "read_sas", "SAS (.sas7bdat)"),
    ".xpt": ("haven", "read_xpt", "SAS transporte (.xpt)"),
}

INPUT_FORMATS = {**TEXT_FORMATS, **{k: v[2] for k, v in R_FORMATS.items()}}

FORMATOS_AYUDA = ("csv, txt, tsv | xls, xlsx, xlsm | "
                  "sav, zsav, por (IBM SPSS) | dta (Stata) | sas7bdat, xpt (SAS)")

def formato_de(path: Path) -> str:
    return INPUT_FORMATS.get(path.suffix.lower(), "desconocido")

def read_text_flexible(path: Path) -> str:
    """UTF-8 con BOM, luego UTF-8, luego cp1252 (Excel en español suele ser cp1252)."""
    b = path.read_bytes()
    for enc in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            return b.decode(enc)
        except UnicodeDecodeError:
            continue
    return b.decode("utf-8", errors="replace")

R_IMPORT = r"""
args <- commandArgs(trailingOnly = TRUE)
src <- args[[1]]; dst <- args[[2]]; cb <- args[[3]]; pkg <- args[[4]]; fun <- args[[5]]
suppressPackageStartupMessages({
  if (!requireNamespace(pkg, quietly = TRUE))
    stop(sprintf("falta el paquete R '%s' para leer este formato", pkg))
  if (!requireNamespace("jsonlite", quietly = TRUE))
    stop("falta el paquete R 'jsonlite' para exportar el codebook")
  library(pkg, character.only = TRUE)
  library(jsonlite)
})
leer <- get(fun, envir = asNamespace(pkg))
d <- tryCatch(as.data.frame(leer(src)), error = function(e) stop(conditionMessage(e)))
if (!ncol(d)) stop("el archivo no contiene variables legibles")

# Las fechas van como texto ISO: write.csv las corrompe si quedan numéricas.
d[] <- lapply(d, function(x)
  if (inherits(x, "Date") || inherits(x, "POSIXct") || inherits(x, "POSIXlt"))
    format(x, tz = "UTC") else x)

# Codebook ANTES de escribir: write.csv descarta los atributos.
var_lab <- lapply(d, function(x) { l <- attr(x, "label"); if (is.null(l)) NULL else as.character(l) })
val_lab <- lapply(d, function(x) {
  v <- attr(x, "labels"); if (is.null(v) || is.null(names(v))) NULL else as.list(v)
})
na_vals <- lapply(d, function(x) {
  v <- attr(x, "na_values"); if (is.null(v)) NULL else as.numeric(v)
})

write.csv(d, dst, row.names = FALSE, na = "", fileEncoding = "UTF-8")
writeLines(toJSON(list(n = nrow(d), p = ncol(d),
                       variable_labels = var_lab,
                       value_labels = val_lab,
                       user_missing = na_vals),
                  auto_unbox = TRUE, null = "null", na = "null", pretty = TRUE), cb)
cat("IMPORT_OK\n")
"""

ID_HINTS = re.compile(r"^(id|id_?sujeto|identificador|sujeto|caso|participante|no|num|n_?º|"
                      r"numero|código|codigo|code|subject|case|resp(?:ondente)?|s[io]id?)\b", re.I)

COV_HINTS = re.compile(r"(gender|sexo|genero|género|edad|age|exp|nivel|grupo|condicion|"
                       r"condición|pais|país|centro|curso|hierro|cargo|tipo)", re.I)

def read_table(path: Path, workdir: Path | None = None) -> tuple[list[str], list[list[str]], dict]:
    """Lee el archivo en cualquiera de los formatos admitidos.

    - Texto (csv/txt/tsv/dat): lo lee Python, con sniffing de delimitador.
    - Binario (Excel, SPSS, Stata, SAS): se convierte a CSV con R (readxl/haven) en
      `workdir` y se extrae un codebook con etiquetas de variable y de valores.
      Esas etiquetas importan: en un cuestionario SPSS suelen ser el enunciado del ítem.

    Nunca escribe junto al archivo del usuario.
    """
    ext = path.suffix.lower()
    if ext not in INPUT_FORMATS:
        raise SystemExit(
            f"ERROR: formato no admitido: '{ext or 'sin extension'}'\n"
            f"  Formatos admitidos: {FORMATOS_AYUDA}")

    meta: dict = {"source_format": formato_de(path), "source_file": str(path.resolve())}

    if ext in R_FORMATS:
        rs = find_rscript()
        if not rs:
            raise SystemExit(f"ERROR: para leer {formato_de(path)} hace falta Rscript.")
        pkg, fun, _ = R_FORMATS[ext]
        workdir = Path(workdir or path.parent)
        workdir.mkdir(parents=True, exist_ok=True)
        csv_out = (workdir / "datos_importados.csv").resolve()
        cb_out = (workdir / "codebook.json").resolve()
        script = workdir / "_import.R"
        script.write_text(R_IMPORT, encoding="utf-8")
        out_r, err_r, code_r = run_process(
            [rs, str(script), str(path.resolve()), str(csv_out), str(cb_out), pkg, fun],
            timeout=1800)
        if code_r != 0 or "IMPORT_OK" not in out_r:
            lineas = (err_r or out_r).strip().splitlines()
            detalle = " | ".join(lineas[-3:]) if lineas else "sin detalle de R"
            raise SystemExit(
                f"ERROR al leer {formato_de(path)} con R ({pkg}::{fun}):\n  {detalle}")
        path = csv_out
        meta["converted_from"] = meta["source_file"]
        meta["converter"] = f"{pkg}::{fun}"
        try:
            meta["codebook"] = json.loads(cb_out.read_text(encoding="utf-8"))
        except Exception:                                       # noqa: BLE001
            meta["codebook"] = {}

    raw = read_text_flexible(path)
    read_file = str(Path(path).resolve())
    head = raw.split("\n", 1)[0]
    delim, n = None, 0
    for d in ("\t", ";", "|", ","):
        if head.count(d) > n:
            delim, n = d, head.count(d)
    delim = delim or ","
    rows = list(csv.reader(io.StringIO(raw), delimiter=delim))
    rows = [r for r in rows if any((c or "").strip() for c in r)]
    header = [h.strip().strip('"') for h in rows[0]]
    width = len(header)
    body = [(r + [""] * (width - len(r)))[:width] for r in rows[1:]]
    meta.update({"delimiter": delim, "n_rows": len(body), "n_cols": width,
                 "read_file": read_file})
    return header, body, meta

MISSING_VALUES = frozenset(("", "na", "na.", "nan", "null", "none", "-", "#n/a", "n/a"))

def as_float(s: str):
    s = (s or "").strip().replace(",", ".").replace("%", "")
    if s.lower() in MISSING_VALUES:
        return None
    try:
        return float(s)
    except ValueError:
        return None

def quantile(sorted_vals: list[float], q: float) -> float | None:
    if not sorted_vals:
        return None
    pos, k = (len(sorted_vals) - 1) * q, None
    lo, hi = math.floor(pos), math.ceil(pos)
    return sorted_vals[lo] if lo == hi else sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * (pos - lo)

def moments(v: list[float]) -> tuple[float | None, float | None]:
    """Asimetría g1 y curtosis excedente g2 (muestrales, consistentes con psych::skew/kurt)."""
    n = len(v)
    if n < 3:
        return None, None
    # La curtosis excedente divide por (n-3): con n<4 no está definida.
    # Antes reventaba con ZeroDivisionError en datasets diminutos.
    m = st.fmean(v)
    m2 = sum((x - m) ** 2 for x in v) / n
    if m2 == 0:
        return None, None
    m3 = sum((x - m) ** 3 for x in v) / n
    m4 = sum((x - m) ** 4 for x in v) / n
    g1 = (n ** 2 / ((n - 1) * (n - 2))) * (m3 / m2 ** 1.5)
    if n < 4:
        return g1, None
    g2 = (((n * (n + 1)) / ((n - 1) * (n - 2) * (n - 3))) * (m4 / m2 ** 2)
          - (3 * (n - 1) ** 2) / ((n - 2) * (n - 3)))
    return g1, g2

MEASURE_TYPES = ("id", "binary", "nominal", "ordinal", "continuous", "text")

CLASS_ALIASES = {"categorical": "nominal", "factor": "nominal", "constant": "nominal"}

def normalize_class(value: str | None) -> str | None:
    """Devuelve el nivel de medida canónico, o None si no se reconoce."""
    if not value:
        return None
    v = str(value).strip().lower()
    v = CLASS_ALIASES.get(v, v)
    return v if v in MEASURE_TYPES else None

def metadata_path(data_path: Path) -> Path:
    """Archivo de metadatos junto a los datos: viaja con ellos y es legible.

    Un sidecar (`datos.analisisr.json`) evita que la información se pierda al mover el
    proyecto de equipo, cosa que sí ocurriría guardándola sólo en la configuración local.
    """
    p = Path(data_path)
    return p.with_name(p.stem + ".analisisr.json")

def load_metadata(data_path: Path) -> dict:
    """Lee el sidecar. Un archivo corrupto no rompe el perfilado: se ignora."""
    f = metadata_path(data_path)
    if not f.is_file():
        return {}
    try:
        datos = json.loads(f.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return {"_error": f"metadatos ilegibles en {f.name}"}
    if not isinstance(datos, dict):
        return {"_error": f"metadatos con formato inesperado en {f.name}"}
    return datos

def apply_class_overrides(prof: dict, overrides: dict[str, str]) -> list[dict]:
    """Aplica los niveles elegidos y recalcula los agregados del perfil.

    Devuelve la lista de cambios efectivos. Un nombre que no exista en los datos se
    ignora en lugar de inventar una columna.
    """
    por_columna = {c["column"]: c for c in prof.get("columns", [])}
    cambios: list[dict] = []
    for col, nuevo in (overrides or {}).items():
        destino = normalize_class(nuevo)
        if col not in por_columna or not destino:
            continue
        c = por_columna[col]
        anterior = c.get("class")
        if anterior == destino:
            continue
        c["class_detected"] = c.get("class_detected", anterior)
        c["class"] = destino
        c["class_source"] = "metadato"
        cambios.append({"column": col, "from": anterior, "to": destino})

    # recalcular los agregados que dependen de la clase
    by: dict[str, list[str]] = {}
    for c in prof.get("columns", []):
        by.setdefault(c.get("class", "?"), []).append(c["column"])
    prof["columns_by_class"] = by
    prof["id_columns"] = by.get("id", [])
    prof["n_items"] = len(by.get("ordinal", [])) + len(by.get("continuous", []))
    prof["covariates"] = [c["column"] for c in prof.get("columns", [])
                          if c.get("role_hint") == "covariate"
                          and c.get("class") in ("binary", "nominal", "categorical",
                                                 "continuous", "ordinal")]
    return cambios

def profile_column(name: str, cells: list[str], n: int) -> dict:
    vals = [as_float(c) for c in cells]
    num = [v for v in vals if v is not None]
    non_num = sum(1 for v in vals if v is None)
    observed = [(c or "").strip() for c in cells
                if (c or "").strip().lower() not in MISSING_VALUES]
    uniq_all = set(observed)
    d = {"column": name, "n_missing": non_num, "pct_missing": round(100 * non_num / max(n, 1), 2),
         "n_unique": len(uniq_all)}
    numeric_share = len(num) / max(n, 1)
    if numeric_share < 0.5:
        missing = len(cells) - len(observed)
        d.update(n_missing=missing, pct_missing=round(100 * missing / max(n, 1), 2))
        d["class"] = "nominal" if len(uniq_all) <= 12 else "text"
        d["levels"] = sorted(x for x in uniq_all)[:12]
        return d
    ints = all(float(v).is_integer() for v in num)
    k = len({v for v in num})
    d.update({"min": min(num), "max": max(num), "mean": round(st.fmean(num), 4),
              "sd": round(st.stdev(num), 4) if len(num) > 1 else 0.0,
              "q1": quantile(sorted(num), .25), "median": quantile(sorted(num), .5),
              "q3": quantile(sorted(num), .75), "is_integer": ints, "n_distinct": k})
    g1, g2 = moments(num)
    d["skew"], d["kurtosis"] = (round(g1, 3) if g1 is not None else None,
                                round(g2, 3) if g2 is not None else None)
    zeros = sum(1 for v in num if v == 0)
    d["structural_zero_pct"] = round(100 * zeros / len(num), 2)
    if d["structural_zero_pct"] > 0.5:
        d["floor_zero"] = True
    if ID_HINTS.match(name) or (k == n and ints and min(num) >= 0 and k > 0.95 * n and max(num) > 50):
        d["class"] = "id"
    elif k == 1:
        d["class"] = "constant"
    elif k == 2 and ints and set(num) <= {0, 1, 2}:
        d["class"] = "binary"
    elif ints and 2 < k <= 21 and (d["max"] - d["min"]) <= 30:
        d["class"] = "ordinal"          #Likert / summed rating
        d["categories"] = sorted({v for v in num})
        # A6: categorías con pocos casos producen umbrales inestables con WLSMV.
        conteo = {c: sum(1 for v in num if v == c) for c in d["categories"]}
        d["category_counts"] = {str(c): n for c, n in conteo.items()}
        minimo = 10
        raras = {c: n for c, n in conteo.items() if n < minimo}
        if raras:
            d["rare_categories"] = {str(c): n for c, n in raras.items()}
            d["sparse"] = "categorias_con_menos_de_10_casos"
    elif k <= 6 and ints:
        d["class"] = "nominal"
        d["levels"] = sorted({v for v in num})
    else:
        d["class"] = "continuous"
    if d["class"] not in ("id", "constant") and COV_HINTS.search(name):
        d["role_hint"] = "covariate"
    if d["pct_missing"] > 30:
        d["warn"] = "missing_gt_30pct"
    return d

def _clave_valor(v: str):
    """Valor comparable: número si lo es, texto normalizado si no. `None` si falta."""
    n = as_float(v)
    if n is not None:
        return n
    t = (v or "").strip()
    return None if t.lower() in MISSING_VALUES else t

def parse_recode(spec: str) -> list[dict]:
    """Reglas de recodificación, una por línea. Determinista y declarada.

    Dos formas, que cubren lo que de verdad se pide en psicometría:

        x2 = invertir 1..5           # ítem inverso: v -> (1+5) - v
        grade = 1,2 -> 1; 3,4 -> 2   # agrupar categorías
        sexo = "M" -> 1; "F" -> 2; resto -> NA

    No se interpreta lenguaje natural ni se delega en el modelo: una transformación que
    cambia los datos tiene que ser reproducible y quedar escrita en el manifiesto.
    """
    reglas: list[dict] = []
    for linea in re.split(r"[\n\r]+", spec or ""):
        linea = linea.split("#", 1)[0].strip().rstrip(";").strip()
        if not linea:
            continue
        col, sep, resto = linea.partition("=")
        col, resto = col.strip(), resto.strip()
        if not sep or not col:
            raise SystemExit(f"ERROR: regla de recodificación sin '=': «{linea}»")
        m = re.fullmatch(r"invertir\s+(-?[\d.]+)\s*\.\.\s*(-?[\d.]+)", resto, flags=re.I)
        if m:
            lo, hi = float(m.group(1)), float(m.group(2))
            if not lo < hi:
                raise SystemExit(f"ERROR: en «{linea}» el mínimo debe ser menor que el máximo")
            reglas.append({"column": col, "kind": "invertir", "min": lo, "max": hi,
                           "rule": linea})
            continue
        mapa, otros = {}, None
        for trozo in resto.split(";"):
            trozo = trozo.strip()
            if not trozo:
                continue
            izq, flecha, der = trozo.partition("->")
            if not flecha:
                raise SystemExit(f"ERROR: en «{linea}» falta '->' en «{trozo}»")
            destino = der.strip().strip('"\'')
            if izq.strip().lower() == "resto":
                otros = destino
                continue
            for origen in izq.split(","):
                origen = origen.strip().strip('"\'')
                if not origen:
                    raise SystemExit(f"ERROR: en «{linea}» hay un origen vacío")
                clave = _clave_valor(origen)
                if clave is None:
                    raise SystemExit(f"ERROR: en «{linea}» no se puede recodificar un "
                                     f"valor ausente («{origen}»)")
                mapa[clave] = destino
        if not mapa and otros is None:
            raise SystemExit(f"ERROR: regla de recodificación vacía: «{linea}»")
        reglas.append({"column": col, "kind": "mapa", "map": mapa, "otros": otros,
                       "rule": linea})
    return reglas

def apply_recode(header: list[str], body: list[list[str]],
                 reglas: list[dict]) -> tuple[list[list[str]], list[dict]]:
    """Aplica las reglas sobre la copia que lee R y devuelve lo que hizo cada una.

    Un valor observado que ninguna regla cubre es un error, no un caso que se deja pasar:
    `1,2 -> 1; 3,4 -> 2` sobre una escala de cinco puntos dejaría el 5 mezclado con los
    códigos nuevos sin que nadie lo note. Para dejarlo fuera hay que escribir `resto`.
    """
    idx = {h: i for i, h in enumerate(header)}
    nuevo = [list(f) for f in body]
    aplicadas: list[dict] = []
    for r in reglas:
        j = idx.get(r["column"])
        if j is None:
            raise SystemExit(f"ERROR: la recodificación nombra «{r['column']}», que no es "
                             f"una columna del archivo")
        cambios, mapa_usado = 0, {}
        if r["kind"] == "invertir":
            fuera = sorted({v for v in (as_float(f[j]) for f in nuevo)
                            if v is not None and not (r["min"] <= v <= r["max"])})
            if fuera:
                raise SystemExit(f"ERROR: «{r['rule']}» deja fuera del rango los valores "
                                 f"{', '.join(_fmt_num(v) for v in fuera)}")
            for f in nuevo:
                v = as_float(f[j])
                if v is None:
                    continue
                destino = r["min"] + r["max"] - v
                mapa_usado[_fmt_num(v)] = _fmt_num(destino)
                if destino != v:
                    cambios += 1
                f[j] = _fmt_num(destino)
        else:
            observados = {_clave_valor(f[j]) for f in nuevo}
            observados.discard(None)
            sin_cubrir = sorted(_fmt_num(v) if isinstance(v, float) else str(v)
                                for v in observados - set(r["map"]))
            if sin_cubrir and r["otros"] is None:
                raise SystemExit(f"ERROR: «{r['rule']}» no dice qué hacer con "
                                 f"{', '.join(sin_cubrir)}; añade «resto -> valor»")
            for f in nuevo:
                clave = _clave_valor(f[j])
                if clave is None:
                    continue
                destino = r["map"].get(clave, r["otros"])
                if destino is None:
                    continue
                destino = "" if destino.upper() == "NA" else destino
                mapa_usado[str(clave) if not isinstance(clave, float) else _fmt_num(clave)] = (
                    destino or "NA")
                if destino != f[j]:
                    cambios += 1
                f[j] = destino
        aplicadas.append({"column": r["column"], "rule": r["rule"], "kind": r["kind"],
                          "map": mapa_usado, "n_changed": cambios})
    return nuevo, aplicadas

def _fmt_num(v: float) -> str:
    return str(int(v)) if float(v).is_integer() else repr(round(float(v), 10))

def collapse_rare_categories(header: list[str], body: list[list[str]],
                             columns: list[str], minimo: int = 10) -> tuple[list[list[str]], list[dict]]:
    """Fusiona categorías con menos de `minimo` casos en la adyacente más poblada.

    Se resuelve encadenando: si la vecina elegida también es rara, el mapa se reescribe
    hacia su destino final (1→2 y 2→3 termina siendo 1→3 y 2→3). Se aplica sólo sobre la
    copia que lee R y queda registrado: colapsar cambia los datos.
    """
    idx = {h: i for i, h in enumerate(header)}
    cambios: list[dict] = []
    nuevo = [list(f) for f in body]
    for col in columns:
        j = idx.get(col)
        if j is None:
            continue
        valores = [as_float(f[j]) for f in nuevo]
        distintos = sorted({v for v in valores if v is not None})
        if len(distintos) < 3:
            continue
        conteo = {c: sum(1 for v in valores if v == c) for c in distintos}
        mapa: dict[float, float] = {}
        for c in distintos:
            if conteo[c] >= minimo or conteo[c] == 0:
                continue
            pos = distintos.index(c)
            vecinos = [distintos[k] for k in (pos - 1, pos + 1) if 0 <= k < len(distintos)]
            vecinos = [v for v in vecinos if conteo.get(v, 0) > 0]
            if not vecinos:
                continue
            destino = max(vecinos, key=lambda v: (conteo.get(v, 0), -abs(v - c)))
            # si el destino ya está mapeado, se sigue la cadena hasta el final
            while destino in mapa:
                destino = mapa[destino]
            mapa[c] = destino
        # reescribir el mapa para que apunte siempre al destino final
        for k in list(mapa):
            destino = mapa[k]
            while destino in mapa:
                destino = mapa[destino]
            mapa[k] = destino
        if not mapa:
            continue
        for f in nuevo:
            v = as_float(f[j])
            if v is not None and v in mapa:
                destino = mapa[v]
                f[j] = str(int(destino)) if float(destino).is_integer() else str(destino)
        cambios.append({"column": col, "min_count": minimo,
                        "merged": {str(k): v for k, v in sorted(mapa.items())},
                        "counts_before": {str(k): conteo[k] for k in sorted(mapa)}})
    return nuevo, cambios

def phase1_profile(data_path: Path, workdir: Path | None = None,
                   overrides: dict[str, str] | None = None,
                   keep: list[str] | None = None) -> dict:
    """Perfil empírico de los datos. `keep` limita el análisis a esas columnas.

    Filtrar aquí y no más abajo hace que todo lo derivado —clases, ítems, covariables,
    nombres inseguros y el diccionario que viaja al prompt— salga ya coherente, sin tocar
    el archivo de datos: R sigue leyendo el CSV entero y el modelo sólo ve lo declarado.
    """
    header, body, meta = read_table(data_path, workdir)
    cols = list(zip(*body)) if body else [[] for _ in header]
    prof = [profile_column(h, list(c), meta["n_rows"]) for h, c in zip(header, cols)]
    excluidas, desconocidas = [], []
    if keep is not None:
        pedidas = {c.strip() for c in keep if c and c.strip()}
        desconocidas = sorted(pedidas - {p["column"] for p in prof})
        excluidas = [p["column"] for p in prof if p["column"] not in pedidas]
        prof = [p for p in prof if p["column"] in pedidas]
        if not prof:
            raise SystemExit("ERROR: la selección de variables no deja ninguna columna "
                             "del archivo; revisa la selección de variables.")
    ids = [p["column"] for p in prof if p["class"] == "id"]
    by = {}
    for p in prof:
        by.setdefault(p["class"], []).append(p["column"])
    r_ident = re.compile(r"^[A-Za-z.][A-Za-z0-9._]*$")
    reserved = {"in", "if", "else", "for", "while", "function", "TRUE", "FALSE", "NA",
                "NULL", "next", "break", "repeat"}
    unsafe = [p["column"] for p in prof
              if p["column"] in reserved or not r_ident.match(p["column"])]
    out = {
        "phase": 1, "file": str(data_path), "read_file": meta.get("read_file"), "generated": _dt.datetime.now().isoformat(timespec="seconds"),
        "n_rows": meta["n_rows"], "n_cols": meta["n_cols"], "delimiter": meta["delimiter"],
        "source_format": meta.get("source_format"),
        "source_file": meta.get("source_file"),
        "converted_from": meta.get("converted_from"),
        "converter": meta.get("converter"),
        "codebook": meta.get("codebook") or {},
        "id_columns": ids, "columns_by_class": by,
        "n_items": len(by.get("ordinal", [])) + len(by.get("continuous", [])),
        "covariates": [p["column"] for p in prof if p.get("role_hint") == "covariate"
                       and p["class"] in ("binary", "nominal", "categorical", "continuous", "ordinal")],
        "columns": prof,
        "unsafe_names": unsafe,
        "r_safe_names": not unsafe,
    }
    if keep is not None:
        out["columns_selected"] = [p["column"] for p in prof]
        out["columns_excluded"] = excluidas
        if desconocidas:
            out["columns_unknown"] = desconocidas
    # El perfil publica siempre la ruta que debe leer R (main la reescribe si normaliza).
    out.setdefault("data_for_r", meta.get("read_file"))
    dispersas = [p["column"] for p in prof if p.get("sparse")]
    if dispersas:
        out["warnings"] = [f"{c}: categorías con menos de 10 casos (umbrales inestables "
                           f"con WLSMV; puede colapsarse con --collapse-rare N)"
                           for c in dispersas]
    flagged = [p["column"] for p in prof if p.get("warn")]
    if flagged:
        out["warnings"] = [f"{c}: >30% de faltantes" for c in flagged]

    # Niveles de medida: lo declarado por el usuario manda sobre la heurística.
    detectadas = {p["column"]: p["class"] for p in out["columns"]}
    meta_libre = overrides if overrides is not None else (load_metadata(data_path).get("classes") or {})
    if meta_libre:
        cambios = apply_class_overrides(out, meta_libre)
        out["class_overrides"] = {
            "source": "cli" if overrides is not None else str(metadata_path(data_path)),
            "applied": cambios,
            "ignored": sorted(set(meta_libre) - set(detectadas)),
            "detected": {c["column"]: detectadas.get(c["column"]) for c in cambios},
        }
        if cambios:
            log("  niveles de medida aplicados desde metadatos: "
                + ", ".join(f"{c['column']}: {c['from']} -> {c['to']}" for c in cambios[:6])
                + ("…" if len(cambios) > 6 else ""))
    return out

EXPOSURE_LABELS = {
    "schema": "esquema (sin valores)",
    "aggregates": "agregados (rangos y recuentos)",
    "stats": "estadísticos (momentos)",
}

def default_exposure(kind: str) -> str:
    """La nube recibe lo mínimo; el motor local puede recibir momentos."""
    return "stats" if kind == "local" else "schema"

def exposure_allows(exposure: str, campo: str) -> bool:
    """Lista blanca por campo: lo que no está aquí, no se serializa."""
    permitidos = {
        "schema": {"column", "class", "pct_missing", "n_missing", "n_distinct"},
        "aggregates": {"column", "class", "pct_missing", "n_missing", "n_distinct",
                       "min", "max", "categories", "levels", "is_integer",
                       "structural_zero_pct", "floor_zero", "warn", "role_hint",
                       "class_detected", "class_source"},
        "stats": {"column", "class", "pct_missing", "n_missing", "n_distinct",
                  "min", "max", "categories", "levels", "is_integer",
                  "structural_zero_pct", "floor_zero", "warn", "role_hint",
                  "class_detected", "class_source", "mean", "sd", "skew", "kurtosis",
                  "median", "q1", "q3"},
    }
    return campo in permitidos.get(exposure, permitidos["schema"])

def save_metadata(data_path: Path, classes: dict[str, str]) -> Path:
    """Guarda junto a los datos los niveles de medida declarados por el usuario.

    El sidecar viaja con el archivo y `phase1_profile` lo aplica al reimportarlo, así
    que redefinir los tipos solo hace falta una vez. Se escribe directamente: si una
    interrupción lo dejara a medias, `load_metadata` lo ignora y basta volver a aplicar.
    """
    destino = metadata_path(data_path)
    previo = load_metadata(data_path)
    contenido = {k: v for k, v in previo.items() if k != "_error"} if isinstance(previo, dict) else {}
    niveles = {col: normalize_class(valor) for col, valor in (classes or {}).items()}
    contenido.update(schema="analisisr.metadata/1",
                     classes={col: nivel for col, nivel in niveles.items() if nivel},
                     saved=_dt.datetime.now().isoformat(timespec="seconds"),
                     data_file=Path(data_path).name)
    destino.write_text(json.dumps(contenido, ensure_ascii=False, indent=2), encoding="utf-8")
    return destino


def binarize(header: list[str], body: list[list[str]], columnas: list[str],
             codebook: dict | None = None) -> tuple[list[list[str]], list[dict], dict]:
    """Recodifica cada variable binaria a 0/1, con su primera categoría como referencia.

    La primera categoría es el primer nivel en orden natural (numérico si lo son, y
    alfabético si no), igual que haría `factor()` en R. Las etiquetas de valor del
    codebook se reasignan a los códigos nuevos para que el diccionario no mienta.
    Los ausentes se conservan tal cual.
    """
    libro = json.loads(json.dumps(codebook or {}))
    etiquetas = libro.get("value_labels") or {}
    cambios: list[dict] = []
    for nombre in columnas:
        if nombre not in header:
            continue
        i = header.index(nombre)
        presentes = {}
        for fila in body:
            clave = _clave_valor(fila[i])
            if clave is not None:
                presentes.setdefault(clave, fila[i])
        if len(presentes) != 2:
            cambios.append({"column": nombre, "recoded": False,
                            "reason": f"{len(presentes)} categorías observadas; se esperaban 2"})
            continue
        orden = sorted(presentes, key=lambda v: (isinstance(v, str), v))
        mapa = {presentes[orden[0]]: "0", presentes[orden[1]]: "1"}
        originales = [presentes[orden[0]], presentes[orden[1]]]
        if originales == ["0", "1"]:
            cambios.append({"column": nombre, "recoded": False, "reason": "ya estaba en 0/1",
                            "reference": "0"})
            continue
        for fila in body:
            if _clave_valor(fila[i]) is not None:
                fila[i] = mapa[fila[i]]
        previas = etiquetas.get(nombre)
        nuevas = None
        if isinstance(previas, dict):
            nuevas = {}
            for clave, texto in previas.items():
                igual = next((orig for orig in originales
                              if str(clave).strip() == orig
                              or (as_float(str(clave)) is not None and as_float(str(clave)) == as_float(orig))),
                             None)
                nuevas[mapa[igual] if igual is not None else str(clave)] = texto
            etiquetas[nombre] = nuevas
        cambios.append({"column": nombre, "recoded": True, "mapping": mapa,
                        "reference": originales[0], "event": originales[1],
                        "labels": nuevas})
    if etiquetas:
        libro["value_labels"] = etiquetas
    return body, cambios, libro


def dictionary_text(prof: dict, exposure: str = "stats",
                    max_cols: int = 120) -> str:
    """Diccionario para el prompt, limitado por el nivel de exposición.

    Nunca serializa microdatos: sólo metadatos por variable, y sólo los campos que la
    lista blanca de `exposure_allows` admite para el nivel pedido.
    """
    def ok(campo: str) -> bool:
        return exposure_allows(exposure, campo)

    lines = [f"n = {prof['n_rows']} filas, {prof['n_cols']} columnas. "
             f"IDs: {prof['id_columns'] or 'ninguna detectada'}"
             + (f" | formato de origen: {prof['source_format']}" if prof.get("source_format") else "")
             + f" | exposición: {EXPOSURE_LABELS.get(exposure, exposure)}"]
    cb = prof.get("codebook") or {}
    vlab = cb.get("variable_labels") or {}
    vval = cb.get("value_labels") or {}
    for p in prof["columns"][:max_cols]:
        bits = [p["class"]]
        if ok("n_distinct") and p.get("n_distinct") is not None:
            bits.append(f"k={p['n_distinct']}")
        if ok("min") and p.get("min") is not None:
            bits.append(f"rango=[{p.get('min')},{p.get('max')}]")
        if ok("mean") and p.get("mean") is not None:
            bits.append(f"mean={p.get('mean')}, sd={p.get('sd')}")
            if p.get("skew") is not None:
                bits.append(f"skew={p['skew']}")
        if ok("categories") and p["class"] == "ordinal" and len(p.get("categories", [])) <= 9:
            bits.append(f"cats={p['categories']}")
        if ok("levels") and p.get("levels") and exposure != "stats":
            bits.append(f"niveles={p['levels'][:8]}")
        bits.append(f"missing={p['pct_missing']}%")
        if p.get("floor_zero") and ok("floor_zero"):
            bits.append("zeros>0.5%")
        if p.get("warn"):
            bits.append("MISSING>30%")
        etiqueta = vlab.get(p["column"])
        if isinstance(etiqueta, str) and etiqueta.strip():
            etiqueta = " ".join(etiqueta.split())[:70]
            bits.append(f"«{etiqueta}»")
        codigos = vval.get(p["column"])
        if ok("levels") and isinstance(codigos, dict) and 0 < len(codigos) <= 9:
            pares = ", ".join(f"{k}={str(v)[:22]}" for k, v in sorted(codigos.items(),
                                                                     key=lambda kv: str(kv[0])))
            bits.append(f"vals={{{pares}}}")
        lines.append(f"  {p['column']}: " + ", ".join(bits))
    return "\n".join(lines)

PROVIDERS: dict[str, dict] = {
    "local": {
        "label": "Local (llama-server)", "style": "local",
        "host": "http://127.0.0.1:8090", "model": None,
        "key_env": None, "needs_key": False,
        "note": "Inferencia en el equipo; los datos no salen.",
    },
    "openai": {
        "label": "ChatGPT (OpenAI)", "style": "openai",
        "host": "https://api.openai.com/v1", "model": "gpt-4o-mini",
        "key_env": "OPENAI_API_KEY", "needs_key": True,
        "note": "Endpoint compatible OpenAI. Modelo editable según la cuenta.",
    },
    "deepseek": {
        "label": "DeepSeek", "style": "openai",
        # Documentado en api-docs.deepseek.com: la base no lleva /v1.
        "host": "https://api.deepseek.com", "model": "deepseek-flash",
        "key_env": "DEEPSEEK_API_KEY", "needs_key": True,
        "note": "Modelos vigentes: deepseek-flash y deepseek-v4-pro. Los nombres antiguos "
                "(deepseek-chat, deepseek-reasoner) están retirados. También expone una "
                "base compatible con Anthropic en https://api.deepseek.com/anthropic.",
    },
    "anthropic": {
        "label": "Claude (Anthropic)", "style": "anthropic",
        "host": "https://api.anthropic.com/v1", "model": "claude-3-5-haiku-latest",
        "key_env": "ANTHROPIC_API_KEY", "needs_key": True,
        "note": "API Messages de Anthropic (cabecera x-api-key + anthropic-version).",
    },
    "gemini": {
        "label": "Google Gemini", "style": "gemini",
        "host": "https://generativelanguage.googleapis.com",
        "model": "gemini-2.5-flash",
        "key_env": "GEMINI_API_KEY", "needs_key": True,
        "note": "REST v1beta con clave en la query.",
    },
    "none": {"label": "Sin LLM", "style": "none", "host": "", "model": None,
             "key_env": None, "needs_key": False, "note": "Sólo perfil y contrato."},
}

ANTHROPIC_VERSION = "2023-06-01"

def provider_defaults(kind: str) -> dict:
    return PROVIDERS.get(kind, PROVIDERS["local"])

class ProviderError(RuntimeError):
    """Error HTTP del proveedor, con estado y cuerpo para decidir si reintentar."""

    def __init__(self, status: int, url: str, body: str):
        self.status = status
        self.url = url.split("?")[0]
        self.body = (body or "").strip()
        super().__init__(f"HTTP {status} en {self.url}: {self.body[:300] or 'sin cuerpo'}")

    @property
    def transitorio(self) -> bool:
        return self.status in (408, 409, 425, 429, 500, 502, 503, 504)

class Backend:
    """Cliente de inferencia. local = llama-server (OpenAI-compat); gemini = REST."""
    def __init__(self, kind: str, host: str, model: str | None, max_tokens: int,
                 reasoning_budget: int | None, temperature: float, timeout: int,
                 api_key: str | None = None):
        self.kind = kind
        dflt = provider_defaults(kind)
        self.host = (host or dflt.get("host") or "").rstrip("/")
        self.model = model or dflt.get("model")
        self.api_key = api_key
        self.max_tokens = max_tokens
        self.rb, self.temp, self.timeout = reasoning_budget, temperature, timeout
        self.last_finish: str | None = None
        self.last_truncated = False
        self.last_usage: dict = {}
        self.exposure: str = default_exposure(self.kind)

    def _no_reasoning_options(self) -> dict:
        """Parámetros de desactivación; nunca sustituir cero por un esfuerzo positivo."""
        if self.rb != 0:
            return {}
        model = (self.model or "").lower()
        mandatory = (
            self.kind == "openai" and (
                re.match(r"^o[134](?:-|$)", model)
                or re.fullmatch(r"gpt-5(?:-(?:mini|nano|pro))?(?:-\d{4}-\d{2}-\d{2})?", model)
                or re.match(r"^gpt-6(?:-astra|\.1-sol)(?:-|$)", model))
            or self.kind == "gemini" and re.match(r"^gemini-2\.5-pro(?:-|$)", model)
            or self.kind == "anthropic" and re.fullmatch(
                r"claude-(?:opus-5-5|fable-5(?:-1)?|mythos-5(?:-1)?|mythos-preview)(?:-\d{8}|-latest)?", model)
        )
        if mandatory:
            raise ValueError(f"El modelo {self.model} no permite desactivar el razonamiento. Selecciona un modelo compatible con presupuesto cero.")
        if self.kind == "local":
            return {"reasoning_budget": 0, "reasoning_effort": "none",
                    "chat_template_kwargs": {"enable_thinking": False}}
        if self.kind == "deepseek":
            return {"thinking": {"type": "disabled"}}
        if self.kind == "anthropic":
            options = {"thinking": {"type": "between_tools" if model.startswith("claude-sonnet-5-5") else "disabled"}}
            if model.startswith(("claude-opus-5", "claude-sonnet-5", "claude-haiku-5-5")):
                options["output_config"] = {"effort": "low"}
            return options
        if self.kind == "gemini":
            if model.startswith(("gemini-1.", "gemini-2.0")) and "thinking" not in model:
                return {}
            return {"thinkingConfig": {"thinkingBudget": 0, "includeThoughts": False}}
        if self.kind == "openai" and not model.startswith(("gpt-4", "gpt-3.5", "chatgpt-4o")):
            return {"reasoning_effort": "none"}
        return {}

    def _check_reasoning(self, tokens=0, thinking=False, content="") -> None:
        thinking = thinking or any(block.strip() for block in re.findall(
            r"<think\b[^>]*>(.*?)(?:</think>|$)", content, flags=re.S | re.I))
        if self.rb == 0 and (thinking or isinstance(tokens, (int, float)) and tokens > 0):
            raise RuntimeError("El endpoint ha usado razonamiento pese a solicitar su desactivación. "
                               "Selecciona otro modelo o configura el servidor para desactivarlo.")
    # -- credenciales -----------------------------------------------------
    def resolved_key(self) -> str | None:
        """Clave en este orden: explicita > variable del proveedor > ANALISISR_API_KEY.

        La GUI pasa la clave ya descifrada por entorno, no por argumentos de línea de
        órdenes: así no queda en la lista de procesos ni en el historial.
        """
        if self.api_key:
            return self.api_key
        dflt = provider_defaults(self.kind)
        for var in (dflt.get("key_env"), "ANALISISR_API_KEY"):
            if var and os.environ.get(var):
                return os.environ[var]
        return None

    def probe(self) -> dict:
        self._no_reasoning_options()
        if self.kind == "none":
            return {"kind": "none"}
        if provider_defaults(self.kind).get("needs_key"):
            return dict(self._probe_cloud(), reasoning_budget=self.rb)
        if self.kind != "local":
            return {"kind": self.kind}
        try:
            with urllib.request.urlopen(f"{self.host}/health", timeout=5) as r:
                health = json.load(r)
            props = {}
            try:
                with urllib.request.urlopen(f"{self.host}/props", timeout=5) as r:
                    props = json.load(r)
            except Exception:
                pass
            return {"kind": "local", "host": self.host, "health": health,
                    "model_alias": props.get("model_alias"),
                    "reasoning_budget": self.rb,
                    "n_ctx": props.get("default_generation_settings", {}).get("n_ctx")}
        except Exception as e:                                    # noqa: BLE001
            return {"kind": "local", "host": self.host, "error": str(e)}
    def chat(self, system: str, user: str) -> str:
        """Envia la peticion al backend con reintentos SOLO cuando tiene sentido.

        Un 401 no se arregla reintentando: es una clave mal puesta o revocada, y decir
        "el backend no responde" oculta la causa. Los 429/5xx sí son transitorios y se
        reintentan con espera creciente. Las conexiones cortadas (llama-server sin
        memoria) se reintentan con menos tokens de salida.
        """
        if self.kind == "none":
            return ""
        estilo = provider_defaults(self.kind).get("style", self.kind)
        etiqueta = provider_defaults(self.kind).get("label", self.kind)

        if estilo == "local":
            budget = self.max_tokens or 3000
            ultimo = None
            for intento in range(3):
                try:
                    return self._chat_local(system, user, budget)
                except urllib.error.HTTPError as e:
                    # Un 404 con el servidor vivo significa que el id del modelo no es el
                    # que sirve: reintentar con menos tokens no arregla un nombre mal
                    # escrito, y el mensaje mandaba a comprobar si llama-server seguia
                    # vivo. Medido: servia `qwen3.8-27b` y se pedia `Qwen3.8-27B`.
                    if e.code == 404:
                        raise SystemExit(self._error_modelo_local(e)) from e
                    if e.code == 400 and self.rb == 0:
                        raise SystemExit("El servidor local rechazó la petición con razonamiento desactivado. "
                                         "Comprueba el modelo y que el servidor admita estos parámetros.") from e
                    ultimo = e
                    log(f"  backend: HTTP {e.code} del motor local -> sin mas reintentos")
                    break
                except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError,
                        urllib.error.URLError, TimeoutError, OSError) as e:
                    ultimo = e
                    sufijo = "" if intento == 2 else f" reintento {intento + 2}/3 con menos tokens"
                    log(f"  backend: corte de conexion ({type(e).__name__}) ->"
                        f"{sufijo or ' sin mas reintentos'}")
                    budget = max(1200, int(budget * 0.6))
            raise SystemExit(
                f"ERROR: el motor local no responde en {self.host} ({ultimo}).\n"
                f"  Comprueba que llama-server siga vivo (p. ej. curl {self.host}/v1/models)\n"
                f"  y relanza; si murio durante una generacion larga, baja --max-tokens.")

        enviar = {"openai": self._chat_openai, "anthropic": self._chat_anthropic,
                  "gemini": self._chat_gemini}.get(estilo)
        if not enviar:
            return ""
        intento = 0
        while True:
            try:
                return enviar(system, user)
            except ProviderError as e:
                if e.transitorio and intento < 2:
                    espera = 2 ** intento
                    log(f"  {etiqueta}: {e.status} transitorio; reintento en {espera}s")
                    time.sleep(espera)
                    intento += 1
                    continue
                raise SystemExit(self._mensaje_error(e, etiqueta)) from e
            except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError,
                    TimeoutError) as e:
                if intento < 2:
                    log(f"  {etiqueta}: conexión interrumpida; reintento {intento + 2}/3")
                    intento += 1
                    time.sleep(2 ** intento)
                    continue
                raise SystemExit(f"ERROR: conexión interrumpida con {etiqueta} en "
                                 f"{self.host} ({type(e).__name__}).") from e

    def _mensaje_error(self, e: "ProviderError", etiqueta: str) -> str:
        """Traduce el estado HTTP a una instrucción concreta."""
        pista = {
            400: "petición rechazada: suele ser un nombre de modelo inexistente o un "
                 "parámetro no admitido. Ejecuta «Probar conexión» para ver los modelos "
                 "disponibles.",
            401: "la API key fue rechazada. Comprueba que sea del proveedor correcto y que "
                 "siga vigente; si la guardaste en esta app, vuelve a guardarla.",
            402: "saldo insuficiente en la cuenta del proveedor.",
            403: "la clave es válida pero no tiene permiso sobre ese modelo o recurso.",
            404: "endpoint o modelo inexistente. Revisa la URL base y el nombre del modelo.",
            422: "el proveedor no acepta alguno de los parámetros enviados.",
            429: "límite de peticiones alcanzado; espera unos segundos y reintenta.",
        }.get(e.status, "error del proveedor.")
        if self.rb == 0 and e.status == 400 and any(word in e.body.lower() for word in ("reasoning", "thinking")):
            pista = "el modelo o endpoint no admite desactivar el razonamiento. Selecciona un modelo compatible; AnalisisR no lo activará como alternativa."
        return (f"ERROR de {etiqueta} ({e.status}): {pista}\n"
                f"  endpoint: {e.url}\n  modelo: {self.model}\n"
                f"  respuesta: {e.body[:300] or 'sin cuerpo'}\n"
                "  Usa Probar conexión en la pestaña Endpoints IA.")

    # -- transporte comun -------------------------------------------------
    def _http_json(self, url: str, payload: dict | None, headers: dict,
                   method: str = "POST") -> dict:
        """Peticion JSON con error tipado: el estado decide si se reintenta o se aborta."""
        data = json.dumps(payload).encode() if payload is not None else None
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            cuerpo = ""
            try:
                cuerpo = e.read().decode("utf-8", "replace")[:400]
            except Exception:                                     # noqa: BLE001
                pass
            raise ProviderError(e.code, url, cuerpo) from e
        except urllib.error.URLError as e:
            raise RuntimeError(f"no se pudo conectar con {url.split('?')[0]}: "
                               f"{getattr(e, 'reason', e)}") from e


    def modelos_locales(self) -> list[str]:
        """Ids que sirve el motor local, o lista vacia si no se pueden consultar."""
        try:
            with urllib.request.urlopen(f"{self.host}/v1/models", timeout=8) as r:
                datos = json.load(r)
        except Exception:                                      # noqa: BLE001
            return []
        return [m.get("id", "") for m in (datos.get("data") or []) if m.get("id")]

    def _error_modelo_local(self, e) -> str:
        ids = self.modelos_locales()
        if not ids:
            return (f"ERROR: el motor local contesto 404 en {self.host} y no se pudo "
                    f"consultar {self.host}/v1/models.\n"
                    f"  Comprueba que llama-server este sirviendo en ese puerto.")
        coincide = next((i for i in ids if i.lower() == (self.model or "").lower()), None)
        detalle = (f"  El nombre coincide salvo mayusculas: usa exactamente «{coincide}»."
                   if coincide else
                   f"  Deja el modelo en blanco o usa uno de esos ids exactos.")
        return (f"ERROR: el motor local no reconoce el modelo «{self.model}» "
                f"(HTTP 404 en {self.host}).\n"
                f"  El servidor esta vivo y sirve: {', '.join(ids)}\n" + detalle)

    # -- estilo OpenAI (ChatGPT, DeepSeek y compatibles) -------------------
    def _chat_openai(self, system: str, user: str) -> str:
        clave = self.resolved_key()
        if not clave:
            raise SystemExit(
                f"ERROR: falta la API key para {provider_defaults(self.kind)['label']}.\n"
                f"  Configúrala en la pestaña de backend (se guarda cifrada) o expórtala en "
                f"{provider_defaults(self.kind).get('key_env')}.")
        payload = {
            "model": self.model,
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": user}],
            "temperature": self.temp,
            "stream": False,
        }
        if self.max_tokens:
            payload["max_completion_tokens" if self.kind == "openai" else "max_tokens"] = self.max_tokens
        payload.update(self._no_reasoning_options())
        j = self._http_json(f"{self.host}/chat/completions", payload,
                            {"Content-Type": "application/json",
                             "Authorization": f"Bearer {clave}"})
        eleccion = (j.get("choices") or [{}])[0]
        msg = eleccion.get("message") or {}
        self.last_finish = eleccion.get("finish_reason")
        self.last_truncated = self.last_finish in ("length", "max_tokens")
        uso = j.get("usage") or {}
        self.last_usage = {k: uso.get(k) for k in ("prompt_tokens", "completion_tokens")}
        contenido = strip_think(msg.get("content") or "")
        razon = strip_think(msg.get("reasoning_content") or "")
        self._check_reasoning((uso.get("completion_tokens_details") or {}).get("reasoning_tokens", 0),
                              bool((msg.get("reasoning_content") or "").strip()), msg.get("content") or "")
        return contenido if contenido or not razon else razon

    # -- estilo Anthropic (Claude) ----------------------------------------
    def _chat_anthropic(self, system: str, user: str) -> str:
        clave = self.resolved_key()
        if not clave:
            raise SystemExit(
                "ERROR: falta la API key de Anthropic (Claude).\n"
                "  Configúrala en la pestaña de backend o expórtala en ANTHROPIC_API_KEY.")
        payload = {
            "model": self.model,
            "max_tokens": self.max_tokens or 4096,
            "temperature": self.temp,
            "system": system,
            "messages": [{"role": "user", "content": user}],
        }
        payload.update(self._no_reasoning_options())
        j = self._http_json(f"{self.host}/messages", payload,
                            {"Content-Type": "application/json",
                             "x-api-key": clave,
                             "anthropic-version": ANTHROPIC_VERSION})
        self.last_finish = j.get("stop_reason")
        self.last_truncated = self.last_finish == "max_tokens"
        uso = j.get("usage") or {}
        self.last_usage = {"prompt_tokens": uso.get("input_tokens"),
                           "completion_tokens": uso.get("output_tokens")}
        self._check_reasoning(thinking=any(b.get("type") in ("thinking", "redacted_thinking")
                                          for b in (j.get("content") or [])))
        partes = [b.get("text", "") for b in (j.get("content") or [])
                  if b.get("type") == "text"]
        return strip_think("".join(partes))

    # -- listado de modelos: la fuente de 'no funciona' suele ser el nombre ----
    def list_models(self) -> list[str] | None:
        """Modelos anunciados por el endpoint. None si no implementa el listado.

        Los proveedores renombran y retiran modelos (DeepSeek retiró deepseek-chat y
        deepseek-reasoner). Preguntar por la lista convierte un 400 opaco en un mensaje
        con los nombres válidos.
        """
        clave = self.resolved_key()
        estilo = provider_defaults(self.kind).get("style")
        if estilo == "anthropic":
            j = self._http_json(f"{self.host}/models?limit=100", None,
                                {"x-api-key": clave,
                                 "anthropic-version": ANTHROPIC_VERSION}, "GET")
            return [m.get("id") for m in (j.get("data") or []) if m.get("id")]
        if estilo == "gemini":
            j = self._http_json(f"{self.host}/v1beta/models?key={clave}&pageSize=100",
                                None, {"Content-Type": "application/json"}, "GET")
            return [(m.get("name") or "").replace("models/", "")
                    for m in (j.get("models") or []) if m.get("name")]
        j = self._http_json(f"{self.host}/models", None,
                            {"Authorization": f"Bearer {clave}"}, "GET")
        return [m.get("id") for m in (j.get("data") or []) if m.get("id")]

    # -- sondeo de credenciales en la nube --------------------------------
    def _probe_cloud(self) -> dict:
        """Comprueba credenciales, lista modelos y valida el nombre elegido."""
        base = {"kind": self.kind, "host": self.host, "model": self.model}
        if not self.resolved_key():
            return base | {"error": "sin API key configurada"}
        estilo = provider_defaults(self.kind).get("style")
        options = self._no_reasoning_options()

        disponibles: list[str] | None = None
        try:
            disponibles = self.list_models()
        except Exception as e:                                    # noqa: BLE001
            base["list_models_error"] = str(e)[:200]

        if disponibles:
            base["available_models"] = disponibles[:40]
            base["model_listed"] = self.model in disponibles
            if self.model not in disponibles:
                base["warning"] = (
                    f"el modelo '{self.model}' no figura en el listado del proveedor; "
                    f"disponibles: {', '.join(disponibles[:8])}")
                base["ok"] = True          # las credenciales sí funcionan
                return base

        # Ping real de 1 token: confirma que el modelo concreto responde.
        try:
            if estilo == "anthropic":
                j = self._http_json(
                    f"{self.host}/messages",
                    {"model": self.model, "max_tokens": 1, "temperature": 0,
                     "messages": [{"role": "user", "content": "ping"}], **options},
                    {"Content-Type": "application/json",
                     "x-api-key": self.resolved_key(),
                     "anthropic-version": ANTHROPIC_VERSION})
                base |= {"ok": True, "model_alias": j.get("model") or self.model,
                         "usage": j.get("usage")}
            elif estilo == "gemini":
                j = self._http_json(
                    f"{self.host}/v1beta/models/{self.model}:generateContent"
                    f"?key={self.resolved_key()}",
                    {"contents": [{"role": "user", "parts": [{"text": "ping"}]}],
                     "generationConfig": {"maxOutputTokens": 1, **options}},
                    {"Content-Type": "application/json"})
                base |= {"ok": True, "model_alias": self.model,
                         "usage": j.get("usageMetadata")}
            else:
                j = self._http_json(
                    f"{self.host}/chat/completions",
                    {"model": self.model,
                     "max_completion_tokens" if self.kind == "openai" else "max_tokens": 1, "temperature": 0,
                     "messages": [{"role": "user", "content": "ping"}], **options},
                    {"Content-Type": "application/json",
                     "Authorization": f"Bearer {self.resolved_key()}"})
                base |= {"ok": True, "model_alias": j.get("model") or self.model,
                         "usage": j.get("usage")}
            thought_parts = [part for candidate in (j.get("candidates") or [])
                             for part in candidate.get("content", {}).get("parts", [])]
            thinking = (any(b.get("type") in ("thinking", "redacted_thinking") for b in (j.get("content") or []))
                        or any(p.get("thought") for p in thought_parts)
                        or any((c.get("message") or {}).get("reasoning_content") for c in (j.get("choices") or [])))
            tokens = ((j.get("usage") or {}).get("completion_tokens_details") or {}).get("reasoning_tokens", 0)
            tokens = tokens or (j.get("usageMetadata") or {}).get("thoughtsTokenCount", 0)
            content = "".join((c.get("message") or {}).get("content") or "" for c in (j.get("choices") or []))
            self._check_reasoning(tokens, thinking, content)
        except SystemExit:
            raise
        except Exception as e:                                    # noqa: BLE001
            base |= {"error": str(e)[:300], "ok": False}
            if disponibles:
                base["warning"] = ("el listado de modelos respondió, pero el ping falló: "
                                   "revisa permisos del modelo o el saldo de la cuenta")
        return base

    def _chat_local(self, system: str, user: str, max_tokens: int) -> str:
        payload = {"messages": [{"role": "system", "content": system},
                                {"role": "user", "content": user}],
                   "temperature": self.temp, "max_tokens": max_tokens,
                   "cache_prompt": True}
        if self.model:
            payload["model"] = self.model
        if self.rb is not None:
            payload["reasoning_budget"] = self.rb
        payload.update(self._no_reasoning_options())
        req = urllib.request.Request(f"{self.host}/v1/chat/completions",
                                     data=json.dumps(payload).encode(),
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            j = json.load(r)
        m = j["choices"][0]["message"]
        content = strip_think(m.get("content") or "")
        reason = strip_think(m.get("reasoning_content") or "")
        self._check_reasoning(((j.get("usage") or {}).get("completion_tokens_details") or {}).get("reasoning_tokens", 0),
                              bool((m.get("reasoning_content") or "").strip()), m.get("content") or "")
        self.last_finish = j["choices"][0].get("finish_reason")
        self.last_truncated = self.last_finish in ("length", "max_tokens")
        # Si el código quedó só dentro del razonamiento, se rastrea también ahí.
        return content if (extract_r(content) or not reason) else content + "\n" + reason
    def _chat_gemini(self, system: str, user: str) -> str:
        if self.kind == "gemini":
            key = self.resolved_key() or os.environ.get("GOOGLE_API_KEY")
            if not key:
                raise SystemExit("ERROR: falta GEMINI_API_KEY para backend=gemini.")
            mdl = self.model or "gemini-2.5-flash"
            url = (f"{self.host}/v1beta/models/"
                   f"{mdl}:generateContent?key={key}")
            payload = {"systemInstruction": {"parts": [{"text": system}]},
                       "contents": [{"role": "user", "parts": [{"text": user}]}],
                       "generationConfig": {"temperature": self.temp,
                                            "maxOutputTokens": self.max_tokens}}
            payload["generationConfig"].update(self._no_reasoning_options())
            j = self._http_json(url, payload, {"Content-Type": "application/json"})
            candidate = j["candidates"][0]
            parts = candidate["content"]["parts"]
            self._check_reasoning((j.get("usageMetadata") or {}).get("thoughtsTokenCount", 0),
                                  any(p.get("thought") for p in parts))
            self.last_finish = candidate.get("finishReason")
            self.last_truncated = self.last_finish == "MAX_TOKENS"
            return strip_think("".join(p.get("text", "") for p in parts if not p.get("thought")))
        raise ValueError(self.kind)

_HIJOS: "set[subprocess.Popen]" = set()

_LIMPIEZA_INSTALADA = False

def kill_tree(pid: int) -> bool:
    """Mata el proceso y todos sus descendientes.

    Matar sólo el padre deja `Rscript` huérfano consumiendo CPU y VRAM: en Windows se usa
    `taskkill /T`; en POSIX, el grupo de procesos.
    """
    if not isinstance(pid, int) or pid <= 0:
        return False
    try:
        if sys.platform.startswith("win"):
            r = subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)],
                               capture_output=True, text=True, timeout=30)
            return r.returncode == 0
        import signal as _signal
        try:
            os.killpg(os.getpgid(pid), _signal.SIGTERM)
        except OSError:
            os.kill(pid, _signal.SIGTERM)
        return True
    except Exception:                                        # noqa: BLE001
        return False

def _instalar_limpieza() -> None:
    """Ante Ctrl+C o SIGTERM, primero se matan los hijos y luego se sale."""
    global _LIMPIEZA_INSTALADA
    if _LIMPIEZA_INSTALADA:
        return
    import signal as _signal

    def _salir(signum, _frame):
        for h in list(_HIJOS):
            kill_tree(h.pid)
        raise SystemExit(130)

    for sig in (_signal.SIGINT, _signal.SIGTERM):
        try:
            _signal.signal(sig, _salir)
        except (ValueError, OSError):                        # no siempre es el hilo principal
            pass
    _LIMPIEZA_INSTALADA = True

def run_process(cmd: list[str], timeout: int = 600, **kw) -> tuple[str, str, int]:
    """`subprocess.run` con registro del hijo, timeout y muerte en cascada.

    Devuelve (stdout, stderr, código). En timeout devuelve código -1 tras matar el árbol.
    """
    _instalar_limpieza()
    # Popen no tiene `capture_output`: se traduce a las tuberías equivalentes.
    if kw.pop("capture_output", True):
        kw.setdefault("stdout", subprocess.PIPE)
        kw.setdefault("stderr", subprocess.PIPE)
    kw.setdefault("text", True)
    kw.setdefault("encoding", "utf-8")
    kw.setdefault("errors", "replace")
    if sys.platform.startswith("win"):
        kw.setdefault("creationflags", subprocess.CREATE_NO_WINDOW)
    # R es el del sistema: conserva su propio R_HOME y sus bibliotecas sin tocar el entorno.
    proc = subprocess.Popen(cmd, **kw)
    _HIJOS.add(proc)
    try:
        try:
            out, err = proc.communicate(timeout=timeout)
            return (out or ""), (err or ""), proc.returncode
        except subprocess.TimeoutExpired:
            kill_tree(proc.pid)
            try:
                out, err = proc.communicate(timeout=30)
            except subprocess.TimeoutExpired:
                proc.kill()
                out, err = "", ""
            return (out or ""), (err or "") + f"\nTIMEOUT tras {timeout}s (árbol terminado)", -1
    finally:
        _HIJOS.discard(proc)

def sha256_file(path: Path) -> str | None:
    if not path.is_file():
        return None
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for bloque in iter(lambda: fh.read(1 << 20), b""):
            h.update(bloque)
    return h.hexdigest()

class RunLock:
    """Bloqueo por backend para evitar que dos procesos usen a la vez el mismo motor.

    llama-server tiene un slot: dos ejecuciones simultáneas se reparten la cola y el
    usuario ve tiempos raros sin explicación. Con el lock, o hay turno o hay mensaje.
    """

    def __init__(self, kind: str, host: str, enabled: bool = True):
        self.enabled = enabled
        clave = re.sub(r"[^\w.-]+", "_", f"{kind}_{host}")[:80]
        self.path = _session.temporary_root() / "locks" / f"{clave}.lock"
        self.tomado = False

    def __enter__(self) -> "RunLock":
        if not self.enabled:
            return self
        self.path.parent.mkdir(parents=True, exist_ok=True)
        for intento in (1, 2):
            try:
                fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                with os.fdopen(fd, "w", encoding="utf-8") as fh:
                    json.dump({"pid": os.getpid(), "started":
                               _dt.datetime.now().isoformat(timespec="seconds")}, fh)
                self.tomado = True
                return self
            except FileExistsError:
                info = {}
                try:
                    info = json.loads(self.path.read_text(encoding="utf-8"))
                except (ValueError, OSError):
                    pass
                if intento == 1 and not _pid_alive(info.get("pid")):
                    log(f"  AVISO: lock huérfano ({info.get('pid')}); se reemplaza")
                    try:
                        self.path.unlink()
                    except OSError:
                        pass
                    continue
                raise SystemExit(
                    f"ERROR: otra ejecución está usando el backend ({self.path.name}).\n"
                    f"  pid={info.get('pid')} desde {info.get('started')}.\n"
                    "  Espera a que termine antes de volver a intentarlo.")
        return self

    def __exit__(self, *exc) -> None:
        if self.tomado:
            try:
                self.path.unlink()
            except OSError:
                pass
            self.tomado = False

def cleanup_stale_locks() -> None:
    for path in (_session.temporary_root() / "locks").glob("*.lock"):
        if path.is_symlink():
            continue
        try:
            info = json.loads(path.read_text(encoding="utf-8"))
        except (ValueError, FileNotFoundError):
            continue
        if not _pid_alive(info.get("pid")):
            path.unlink(missing_ok=True)


def _pid_alive(pid) -> bool:
    if not isinstance(pid, int) or pid <= 0:
        return False
    if sys.platform.startswith("win"):
        import ctypes
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        h = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not h:
            return False
        try:
            code = ctypes.c_ulong()
            if not ctypes.windll.kernel32.GetExitCodeProcess(h, ctypes.byref(code)):
                return False
            return code.value == 259  # STILL_ACTIVE
        finally:
            ctypes.windll.kernel32.CloseHandle(h)
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False

CHAT_HELP_R = r"""
args <- commandArgs(trailingOnly = TRUE)
limite <- 7000
for (topico in args) {
  partes <- strsplit(topico, "::", fixed = TRUE)[[1]]
  pkg <- partes[1]
  fn <- if (length(partes) > 1) partes[2] else NA_character_
  cat("\n######## ", topico, " ########\n")
  if (!requireNamespace(pkg, quietly = TRUE)) { cat("PAQUETE NO INSTALADO\n"); next }
  cat("version instalada:", as.character(packageVersion(pkg)), "\n")
  if (!is.na(fn)) {
    f <- try(get(fn, envir = asNamespace(pkg)), silent = TRUE)
    if (inherits(f, "try-error")) { cat("LA FUNCION NO EXISTE en este paquete\n"); next }
    cat("firma con valores por omision:\n  ",
        paste(trimws(deparse(args(f))), collapse = " "), "\n\n")
  }
  db <- try(tools::Rd_db(pkg), silent = TRUE)
  if (inherits(db, "try-error") || !length(db)) { cat("(el paquete no trae ayuda)\n"); next }
  alias <- lapply(db, function(rd)
    unlist(lapply(rd[vapply(rd, function(x) identical(attr(x, "Rd_tag"), "\\alias"),
                            logical(1))], function(x) trimws(paste(unlist(x), collapse = "")))))
  elegido <- if (is.na(fn)) names(db)[1] else
    names(db)[vapply(alias, function(a) fn %in% a, logical(1))][1]
  if (is.na(elegido)) {
    cat("sin pagina propia; temas del paquete:\n  ",
        paste(head(sort(unique(unlist(alias))), 40), collapse = ", "), "\n")
    next
  }
  texto <- utils::capture.output(
    tools::Rd2txt(db[[elegido]], options = list(underline_titles = FALSE)))
  junto <- paste(texto, collapse = "\n")
  if (nchar(junto) > limite) junto <- paste0(substr(junto, 1, limite), "\n[...ayuda recortada]")
  cat(junto, "\n")
}
"""

CHAT_HELP_CACHE: dict[tuple[str, str], str] = {}

CHAT_HELP_MAX = 2

def chat_r_help(rs: str | None, topicos: list[str], temp_dir: Path | None = None) -> str:
    """Ayuda de la version INSTALADA para `pkg::fn` o `pkg`, cacheada."""
    limpios, vistos = [], set()
    for t in topicos:
        t = re.sub(r"[^\w.:]", "", (t or "").strip())
        if t and t not in vistos and re.fullmatch(r"[\w.]+(::[\w.]+)?", t):
            vistos.add(t)
            limpios.append(t)
    limpios = limpios[:CHAT_HELP_MAX]
    if not rs or not limpios:
        return ""
    faltan = [t for t in limpios if (rs, t) not in CHAT_HELP_CACHE]
    if faltan:
        carpeta = Path(tempfile.mkdtemp(prefix="analisisr_chat_help_", dir=temp_dir))
        try:
            script = carpeta / "ayuda.R"
            script.write_text(CHAT_HELP_R, encoding="utf-8")
            out, _err, codigo = run_process([rs, str(script), *faltan], timeout=180)
            bloques = (out or "").split("######## ")
            for t in faltan:
                trozo = next((b for b in bloques if b.strip().startswith(t)), "")
                CHAT_HELP_CACHE[(rs, t)] = (
                    "######## " + trozo.strip() if trozo and codigo == 0
                    else f"######## {t} ########\n(no se pudo leer la ayuda)")
        finally:
            shutil.rmtree(carpeta, ignore_errors=True)
    return "\n\n".join(CHAT_HELP_CACHE[(rs, t)] for t in limpios)

CHAT_R_PROHIBIDO = (
    "system", "system2", "shell", "shell.exec", "unlink", "file.remove", "file.rename",
    "file.copy", "file.create", "dir.create", "setwd", "install.packages", "remove.packages",
    "download.file", "url", "socketConnection", "Sys.setenv", "Sys.unsetenv", "q", "quit",
    "source", "sink", "save.image", "load", "eval", "parse", "deparse<-", "reg.finalizer",
)

CHAT_R_LIMITE_SALIDA = 12000

def chat_r_guard(code: str) -> str | None:
    """Motivo por el que NO se ejecuta este código, o `None` si puede correr."""
    if not (code or "").strip():
        return "el bloque de R está vacío"
    sin_comentarios = re.sub(r"#[^\n]*", "", code)
    for nombre in CHAT_R_PROHIBIDO:
        if re.search(rf"(?<![\w.]){re.escape(nombre)}\s*\(", sin_comentarios):
            return (f"el código llama a `{nombre}()`, que el chat no ejecuta: toca el "
                    f"sistema, la red o el estado de la sesión. No se ha ejecutado nada del "
                    f"bloque, así que esto no dice nada sobre qué paquetes hay instalados: "
                    f"quita esa llamada, comprueba la disponibilidad con requireNamespace() y "
                    f"vuelve a enviar el análisis")
    if re.search(r"(?<![\w.])(write\.csv|write\.table|writeLines|saveRDS|png|pdf|jpeg)\s*\(",
                 sin_comentarios):
        return "el código escribe archivos; el chat sólo calcula e imprime"
    return None

CHAT_TABLE_R = r'''
descriptivos <- function(datos) {
  if (!is.data.frame(datos) || !ncol(datos))
    stop("Selecciona columnas de dat: descriptivos(dat[, vars, drop=FALSE])")
  filas <- lapply(names(datos), function(nombre) {
    v <- datos[[nombre]]
    n <- sum(!is.na(v))
    numerica <- is.numeric(v)
    data.frame(Variable=nombre, n_valido=n, Ausentes=sum(is.na(v)),
      Media=if (numerica && n > 0) mean(v, na.rm=TRUE) else NA_real_,
      DE=if (numerica && n > 1) stats::sd(v, na.rm=TRUE) else NA_real_,
      Mediana=if (numerica && n > 0) stats::median(v, na.rm=TRUE) else NA_real_,
      RIC=if (numerica && n > 0) stats::IQR(v, na.rm=TRUE) else NA_real_,
      Observaciones=if (n == 0) "Sin valores válidos" else
                    if (!numerica) "No numérica: revisar codificación" else "",
      check.names=FALSE, stringsAsFactors=FALSE)
  })
  resultado <- do.call(rbind, filas)
  names(resultado)[2] <- "n válido"
  rownames(resultado) <- NULL
  resultado
}

tabla <- function(x) {
  if (!is.data.frame(x) && !is.matrix(x))
    stop("tabla() requiere un data.frame o una matriz")
  x <- as.data.frame(x, stringsAsFactors = FALSE, check.names = FALSE)
  if (!ncol(x)) stop("La tabla no tiene columnas")
  if (!identical(rownames(x), as.character(seq_len(nrow(x)))))
    x <- data.frame(Variable = rownames(x), x, check.names = FALSE)
  escapar <- function(v) {
    v <- as.character(v)
    v[is.na(v)] <- "NA"
    for (s in c("\\", "`", "*", "_", "[", "]", "|", "<", ">"))
      v <- gsub(s, paste0("\\", s), v, fixed = TRUE)
    gsub("[\r\n]+", " ", v)
  }
  celdas <- lapply(x, escapar)
  cat("\n| ", paste(escapar(names(x)), collapse = " | "), " |\n", sep = "")
  cat("| ", paste(rep("---", ncol(x)), collapse = " | "), " |\n", sep = "")
  for (i in seq_len(nrow(x)))
    cat("| ", paste(vapply(celdas, function(v) v[[i]], character(1)),
                    collapse = " | "), " |\n", sep = "")
  cat("\n")
  invisible(x)
}
'''


DIAGNOSTIC_PACKAGES = (
    "stats", "boot", "MASS", "nnet", "cluster", "survival", "psych", "coefficientalpha", "effectsize",
    "emmeans", "afex", "lme4", "ordinal", "glmmTMB", "lavaan", "semTools", "lavaangui", "misty", "mice", "pROC",
    "metafor", "MVN", "readxl", "haven", "jsonlite",
)


def diagnose_r() -> dict:
    """Comprueba R y paquetes instalados sin conectarse a la red ni instalarlos."""
    rs = find_rscript()
    if not rs:
        return {"rscript": None, "packages": [], "message": "No se encuentra Rscript. Instala R o revisa PATH."}
    packages = ",".join(json.dumps(p) for p in DIAGNOSTIC_PACKAGES)
    code = ('cat("R\\t", R.version.string, "\\n", sep=""); '
            'for (lib in .libPaths()) cat("LIB\\t", lib, "\\n", sep=""); '
            f'for (p in c({packages})) cat(p, "\\t", '
            'if (requireNamespace(p, quietly=TRUE)) as.character(packageVersion(p)) '
            'else "NO_INSTALADO", "\\n", sep="")')
    out, err, status = run_process([rs, "--vanilla", "-e", code], timeout=60)
    if status:
        raise RuntimeError("No se pudo diagnosticar R: " + (err or out))
    result = {"rscript": rs, "version": "", "libraries": [], "packages": []}
    for line in out.splitlines():
        key, separator, value = line.partition("\t")
        if not separator:
            continue
        if key == "R":
            result["version"] = value
        elif key == "LIB":
            result["libraries"].append(value)
        elif key in DIAGNOSTIC_PACKAGES:
            result["packages"].append({"package": key, "version": value,
                                       "installed": value != "NO_INSTALADO"})
    return result


def chat_r_script(code: str, prof: dict, keep: list[str] | None = None) -> str:
    """Script completo: lectura que impone la app + el código del modelo."""
    datos = prof.get("data_for_r") or prof.get("read_file") or prof.get("file")
    columnas = ""
    if keep:
        columnas = ("dat <- dat[, intersect(c("
                    + ", ".join(json.dumps(c) for c in keep) + "), names(dat)), drop = FALSE]\n")
    return (f"dat <- utils::read.csv({json.dumps(str(datos))}, check.names = FALSE,\n"
            f"                      encoding = \"UTF-8\", na.strings = c(\"\", \"NA\"))\n"
            + columnas
            # Alias defensivo: en un prompt en español el modelo tiende a escribir `datos`.
            + "datos <- dat\n"
            + "options(warn = 1, width = 120)\n"
            + CHAT_TABLE_R
            + "# --- código del chat ---\n" + code.strip() + "\n")

class RSyntaxError(ValueError):
    """El analizador de R ha rechazado el código antes de ejecutarlo."""


def r_parse_check(rs: str, path: Path, timeout: int = 30) -> tuple[bool, str]:
    """Analiza el código generado sin evaluarlo ni abrir los datos del usuario."""
    check = (
        "error <- tryCatch({invisible(parse(file=" + json.dumps(path.name)
        + ", encoding='UTF-8')); NULL}, error=function(e) conditionMessage(e)); "
        "if (is.null(error)) cat('PARSE_OK') else {cat('PARSE_FAIL\\n', error, sep=''); quit(status=2)}"
    )
    out, err, status = run_process([rs, "--vanilla", "-e", check], timeout=timeout, cwd=str(path.parent))
    if status == 0 and out.strip() == "PARSE_OK":
        return True, ""
    if status == 2 and out.startswith("PARSE_FAIL\n"):
        return False, out.split("\n", 1)[1].strip()[:2000]
    raise RuntimeError("No se pudo comprobar la sintaxis de R: " + (err or out)[:2000])


def chat_run_r(code: str, prof: dict, rs: str | None, keep: list[str] | None = None,
               timeout: int = 300, temp_dir: Path | None = None) -> tuple[bool, str]:
    """Valida y ejecuta el bloque. Si no es sintácticamente válido, lanza RSyntaxError."""
    if not rs:
        return False, "no hay Rscript en este equipo"
    motivo = chat_r_guard(code)
    if motivo:
        return False, motivo
    carpeta = Path(tempfile.mkdtemp(prefix="analisisr_chat_r_", dir=temp_dir))
    try:
        candidate = carpeta / "codigo.R"
        candidate.write_text(code.strip() + "\n", encoding="utf-8")
        valid, error = r_parse_check(rs, candidate, timeout=min(timeout, 30))
        if not valid:
            raise RSyntaxError(error)
        script = carpeta / "chat.R"
        script.write_text(chat_r_script(code, prof, keep), encoding="utf-8")
        out, err, codigo = run_process([rs, str(script)], timeout=timeout, cwd=str(carpeta))
        salida = ((out or "") + ("\n" + err if (err or "").strip() else "")).strip()
        if len(salida) > CHAT_R_LIMITE_SALIDA:
            salida = salida[:CHAT_R_LIMITE_SALIDA] + "\n[...salida recortada]"
        return codigo == 0, salida or "(sin salida)"
    finally:
        shutil.rmtree(carpeta, ignore_errors=True)
