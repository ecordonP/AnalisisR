# -*- mode: python ; coding: utf-8 -*-
"""python -m PyInstaller --noconfirm AnalisisR_onedir.spec

Ofusca los seis módulos con PyArmor y genera una carpeta con interfaz,
trabajador, Qt y recursos. Falla si no puede ofuscar: nunca sustituye la
compilación protegida por código sin protección.

No se incluye R: AnalizaR Desktop usa la instalación de R del equipo donde se ejecuta,
y sin ella la aplicación solo abre la pestaña Entorno R para avisar.
"""
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(SPECPATH).resolve()
sys.path.insert(0, str(ROOT))
SOURCES = ["AnalisisR.py", "analisisr_core.py", "analisisr_ui.py", "analisisr_secrets.py",
           "analisisr_session.py", "analisisr_docx.py"]
source_hashes = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in SOURCES}
OBF = ROOT / "build" / "pyarmor"
subprocess.run([sys.executable, "-m", "pyarmor.cli", "gen", "-O", str(OBF), *SOURCES],
               cwd=ROOT, check=True)
runtimes = list(OBF.glob("pyarmor_runtime_*/pyarmor_runtime.pyd"))
if len(runtimes) != 1 or any(not (OBF / name).is_file() for name in SOURCES):
    raise RuntimeError("Faltan módulos o el runtime de PyArmor no es único.")
runtime_name = runtimes[0].parent.name

a = Analysis(
    [str(ROOT / "AnalisisR.py")], pathex=[str(ROOT)], binaries=[],
    datas=[(str(ROOT / "assets"), "assets"), (str(ROOT / "README.md"), ".")],
    hiddenimports=[Path(name).stem for name in SOURCES[1:]],
    hookspath=[], hooksconfig={}, runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "numpy", "pandas", "scipy", "IPython", "pytest",
              "PyQt5", "PyQt6", "PySide2", "PySide6.QtWebEngineCore",
              "PySide6.QtWebEngineWidgets", "PySide6.QtQml", "PySide6.QtQuick",
              "PySide6.QtMultimedia", "PySide6.QtTest"],
    noarchive=False, optimize=0,
)

# Reemplazar también la caché de código evita incluir los módulos originales.
from PyInstaller.config import CONF
code_cache = getattr(a.pure, "_code_cache", None)
if code_cache is None:
    code_cache = CONF["code_cache"].get(id(a.pure))
protected = set()
for toc in (a.scripts, a.pure):
    for index, (name, path, kind) in enumerate(toc):
        original = Path(path)
        if original.parent == ROOT and original.name in SOURCES:
            obfuscated = OBF / original.name
            if "__pyarmor__" not in obfuscated.read_text(encoding="utf-8"):
                raise RuntimeError(f"No se ha protegido {original.name}")
            toc[index] = (name, str(obfuscated), kind)
            if code_cache is not None:
                code_cache.pop(name, None)
            protected.add(original.name)
if protected != set(SOURCES):
    raise RuntimeError("No se reemplazaron todos los módulos: " + str(set(SOURCES) - protected))
a.pure.append((runtime_name, str(OBF / runtime_name / "__init__.py"), "PYMODULE"))
a.binaries.append((f"{runtime_name}/pyarmor_runtime.pyd", str(runtimes[0]), "EXTENSION"))

pyz = PYZ(a.pure)
common = dict(exclude_binaries=True, debug=False, strip=False, upx=False,
              icon=str(ROOT / "assets" / "analizar.ico"))
gui = EXE(pyz, a.scripts, [], name="AnalizaR", console=False, **common)
worker = EXE(pyz, a.scripts, [], name="AnalizaRWorker", console=True, **common)
coll = COLLECT(gui, worker, a.binaries, a.datas, strip=False, upx=False, name="AnalizaR")

destination = Path(coll.name).resolve()

manifest = {
    "application": "AnalizaR Desktop", "format": "onedir", "protected": sorted(protected),
    "source_hashes": source_hashes,
    "pyarmor_runtime": runtime_name, "python": sys.version.split()[0],
    "bundled_r": False,
    "executables": {name: hashlib.sha256((destination / name).read_bytes()).hexdigest()
                    for name in ("AnalizaR.exe", "AnalizaRWorker.exe")},
}
(destination / "build-info.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
(destination / "LEEME.txt").write_text(
    "AnalizaR Desktop\nDesarrollado por Eulogio Cordón 2026.\n\n"
    "Ejecuta AnalizaR.exe. Conserva toda esta carpeta: _internal es necesario.\n"
    "Incluye Python y Qt, y no necesita Python instalado. R NO va incluido: instala R 4.x\n"
    "y los paquetes que indica la pestaña Entorno R, donde también puedes señalar su carpeta.\n"
    "Sin R la aplicación abre, avisa y no permite ningún análisis.\n"
    "La guía se abre desde Ayuda/F1. Los endpoints y sus claves se configuran en la aplicación.\n"
    "Los modelos de IA locales y servicios externos requieren su propio endpoint; no se incluyen modelos ni claves.\n"
    "Las preferencias se guardan en el perfil del usuario. Guarda tus sesiones e informes antes de cerrar.\n"
    "Todos los temporales se crean en temporales/, dentro del directorio del programa, y se limpian al terminar y salir.\n"
    "Las licencias de R y de sus paquetes son las de la instalación de R del equipo.\n",
    encoding="utf-8")
print(f"Distribución protegida preparada: {destination}", flush=True)
