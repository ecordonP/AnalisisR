# Compilar AnalisisR

AnalisisR se ejecuta tal cual con `python AnalisisR.py`; compilarlo solo sirve para
distribuirlo a equipos sin Python. **Ninguna compilación incluye R**: el equipo de destino
necesita R 4.x con los paquetes que indica la pestaña *Entorno R*.

## Requisitos comunes

- Python 3.10 o posterior (probado con 3.11 de 64 bits).
- `python -m pip install -r requirements.txt` (PySide6; `cryptography` fuera de Windows).
- `python -m pip install pyinstaller` (probado con PyInstaller 6.15.0).
- Compilar en el mismo sistema y arquitectura de destino: PyInstaller no cruza plataformas.

Antes de compilar, pasa las pruebas:

```bash
python -m pip install pytest python-docx
python -m pytest -q
```

## Windows, Linux y macOS (sin protección)

```bash
python -m PyInstaller --noconfirm AnalisisR_multiplataforma.spec
```

Resultado en `dist/AnalisisR/`: el ejecutable `AnalisisR` (interfaz), `AnalisisRWorker`
(procesos de datos, IA y R) y `_internal/` con Python, Qt y los recursos. En Windows ambos
llevan extensión `.exe`.

Conserva la carpeta completa y asegúrate de que sea **escribible**: todos los temporales se
crean en `temporales/`, dentro del propio directorio del programa, y los procesos de R los
heredan.

### Notas por sistema

- **Linux**: hacen falta las bibliotecas de sistema que pide Qt (en Debian/Ubuntu,
  `libxcb-cursor0`, `libxkbcommon-x11-0`, `libegl1`). Con Wayland, PySide6 usa `xcb` por
  omisión; exporta `QT_QPA_PLATFORM=wayland` si lo prefieres.
- **macOS**: el resultado es una carpeta, no un `.app`. Para un paquete con icono propio
  añade un `assets/analisisr.icns` y un bloque `BUNDLE()` al spec; para distribuirlo fuera
  de tu equipo necesitarás firmarlo y notarizarlo con tu cuenta de desarrollador.
  Si Gatekeeper bloquea los ejecutables, autorízalos en Ajustes → Privacidad y seguridad.
- **Windows**: existe además `AnalisisR_onedir.spec`, que ofusca los seis módulos con
  PyArmor Pro, escribe `build-info.json` y es el que usan `compilar.ps1`,
  `tools/validar_paquete.py` y `desplegar.ps1`. Esos tres son específicos de Windows y de
  la compilación protegida; no se aplican al spec multiplataforma, que no genera manifiesto.

## Comprobación del resultado

El trabajador acepta peticiones JSON, lo que permite verificar la compilación sin
interfaz gráfica:

```bash
mkdir -p dist/AnalisisR/temporales/v
printf '{"action":"selftest"}' > dist/AnalisisR/temporales/v/request.json
./dist/AnalisisR/AnalisisR --worker dist/AnalisisR/temporales/v/request.json
cat dist/AnalisisR/temporales/v/result.json
```

Debe devolver `version`, `frozen: true`, `tabs: 4`, `templates: 27`, si se ha detectado R
(`r_ready`) y la ruta de `Rscript`. Con `{"action":"diagnose"}` se obtiene la versión de R
y el estado de los paquetes requeridos.

## R en el equipo de destino

AnalisisR busca `Rscript` en este orden: la variable `R_HOME`, la carpeta indicada en la
pestaña *Entorno R*, el `PATH` y las instalaciones habituales del sistema
(`C:/Program Files/R` en Windows; el framework de CRAN, Homebrew y `/usr/lib/R` en macOS y
Linux). Sin R, la aplicación abre solo la pestaña *Entorno R* y avisa de lo que falta.
