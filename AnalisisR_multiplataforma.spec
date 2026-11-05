# -*- mode: python ; coding: utf-8 -*-
"""python -m PyInstaller --noconfirm AnalisisR_multiplataforma.spec

Compilación sin protección y sin R, válida en Windows, Linux y macOS. Genera una
carpeta con la interfaz, el trabajador, Qt y los recursos; R lo aporta el equipo
donde se ejecuta, igual que en la versión de Windows.

La compilación protegida con PyArmor está en AnalisisR_onedir.spec y solo se usa
para distribuir en Windows. Las instrucciones por sistema están en BUILD.md.
"""
import sys
from pathlib import Path

ROOT = Path(SPECPATH).resolve()
SOURCES = ["AnalisisR.py", "analisisr_core.py", "analisisr_ui.py", "analisisr_secrets.py",
           "analisisr_session.py", "analisisr_docx.py"]
ES_WINDOWS = sys.platform.startswith("win")
# El icono .ico solo lo aprovecha Windows; en macOS haría falta un .icns propio.
ICONO = str(ROOT / "assets" / "analisisr.ico") if ES_WINDOWS else None

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

pyz = PYZ(a.pure)
common = dict(exclude_binaries=True, debug=False, strip=False, upx=False, icon=ICONO)
# El nombre del trabajador debe ser exactamente este: la interfaz lo busca junto a sí misma
# y le añade .exe solo en Windows.
gui = EXE(pyz, a.scripts, [], name="AnalisisR", console=False, **common)
worker = EXE(pyz, a.scripts, [], name="AnalisisRWorker", console=True, **common)
coll = COLLECT(gui, worker, a.binaries, a.datas, strip=False, upx=False, name="AnalisisR")
