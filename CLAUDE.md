# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

**AnalizaR Desktop** — a standalone PySide6 (Qt) desktop app: import a dataset, talk to an AI
endpoint in natural language, and let it run the statistics locally through `Rscript`.
All user-facing text is in Spanish.

**An R installation is mandatory and is never bundled.** Every statistical procedure is
computed in R; there is no Python fallback. Without R the window opens with only the
first tab (`1 · Entorno R`) enabled, warns what to install, and refuses every operation.

The directory is self-contained: the six `AnalisisR*.py` modules, `assets/`, `tests/`,
the PyInstaller spec and the two PowerShell scripts are everything the app needs. It has
no dependency on any sibling directory and must stay that way —
`tests/test_independencia.py` copies the modules to an isolated folder and fails if an
import reaches outside.

`README.md` here is the product documentation and is kept current — read it for feature
behaviour, privacy rules, R package requirements and deployment details. `AGENTS.md` is
partly stale (it claims external imports, no tests and no requirements file — all three
are wrong now) and is kept out of the published repository until it is refreshed.

## Commands

```powershell
python -m pip install -r requirements.txt          # PySide6; + pytest python-docx for tests
python AnalisisR.py                                # launch the GUI
python -m py_compile AnalisisR.py                  # syntax-only check
python -m pytest -q                                # whole suite, from the repo root
python -m pytest tests/test_sintaxis_r.py -q       # single file
python -m pytest tests/test_mejoras.py -q -k sesion # single test by name
python AnalisisR.py --worker <ruta/request.json>   # run one worker request headlessly
```

Run pytest **from the repo root**: there is no `conftest.py` or pytest config, and the
suite relies on `tests/test_analisisr.py` inserting the root into `sys.path`. Tests that
need `Rscript`, Qt or `python-docx` skip themselves when the dependency is missing; none
needs an API key or a remote endpoint.

Build and deploy (Windows, PyArmor Pro + PyInstaller; no R is packaged, ~120 MB):

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\compilar.ps1              # build + validate
powershell -NoProfile -ExecutionPolicy Bypass -File .\compilar.ps1 -Desplegar   # ...and install
```

`compilar.ps1` chains `pyinstaller AnalisisR_onedir.spec` → `tools/validar_paquete.py dist/AnalizaR`
→ `desplegar.ps1`; a failed validation blocks deployment. `build/`, `dist/`, `temporales/`
and `build_*.log` are generated — never edit them.

## Architecture

**GUI/worker split.** Everything slow or risky runs in a separate process, so the UI stays
cancellable. `main()` dispatches on `--worker <request.json>`; the GUI writes
`request.json` into `self.folder / "operacion_NNN"`, spawns itself via `ui.Proc`
(`sys.executable AnalisisR.py --worker ...`, or `AnalizaRWorker.exe` when frozen) and
reads `result.json` back. `worker()` handles the actions `profile`, `probe`, `chat`,
`diagnose` and `selftest`, always writes `result.json` (errors become `{"error": ...}`)
and always writes a `manifest.json` of SHA-256 hashes in its `finally`. Adding a feature
that touches data or the network means adding an action here, not calling it from the UI
thread. `Proc.kill()` kills the whole process tree (`engine.kill_tree`) because `Rscript`
survives a plain `QProcess.kill()`.

**Module roles** (flat, no package; keep them importable side by side):

| Module | Role |
| --- | --- |
| `AnalisisR.py` | prompt templates (`TEMPLATES`, `SYSTEM`, `REFERENCIAS`/`CITAS`), `prepare_data`, `converse`, `worker`, `create_window` (the whole Qt window, defined inside the function; `build_environment` is the Entorno R tab) |
| `analisisr_core.py` | aliased as `engine`: readers, profiling, recoding, `PROVIDERS`/`Backend`, R discovery and execution, `RunLock`, process control |
| `analisisr_ui.py` | `QSS` stylesheet, `Proc`, `PromptEdit`, Markdown→chat rendering |
| `analisisr_secrets.py` | per-provider encrypted profiles (`backends.json`) in the OS config dir |
| `analisisr_session.py` | temp-dir policy, `SessionWorkspace`, portable `.analizar` save/load (it still opens `.analisisr`) |
| `analisisr_docx.py` | Word export by writing OOXML by hand — no `python-docx` at runtime |

**R is a subprocess, never a binding.** There is no `rpy2` anywhere: the bridge is
`Rscript` invoked through `engine.run_process`, which does not touch `R_HOME`/`R_LIBS` —
the system R keeps its own libraries. `find_rscript()` searches, in order, `R_HOME`, the
folder saved from the Entorno R tab (`entorno_r.json` in the config dir, via
`configured_r_home`/`save_r_home`), the `PATH`, and `detected_r_homes()` (the usual
install dirs). Same chain as EasySEM's `_find_rscript_path`. Keep new R work behind this
boundary, and never reintroduce a bundled copy: `tests/test_entorno_r.py` fails the build
if the spec copies R again.

**The R gate lives in the window.** `update_r_state()` is the single place that decides
whether the app is usable: it disables `self.r_pages` (Datos, Endpoints, Chat) and their
tabs when `find_rscript()` returns `None`, and `start()` refuses every action but
`diagnose` while `self.r_ready` is false. `refresh_r()` re-runs detection after the user
points at an R folder, with no restart. Operations disable `self.locked_pages` instead of
hardcoded tab indices, and `finished()` re-applies the gate — so inserting or reordering
a tab does not break them.

**The chat/R loop** (`converse`, `AnalisisR.py:580`) is the core of the app: the model gets
the dictionary **without rows**, may propose R blocks, and each block is syntax-checked
locally (`engine.r_parse_check`) before running. Hard caps live inline: 6 R attempts,
3 help rounds, 3 consecutive syntax errors, last 20 history turns. Each R block starts a
fresh session and must be self-contained.

**Templates drive the form.** A `TEMPLATES` prompt carries `[campo]` placeholders; `use_template`
builds the dialog from them, so a new template with a new field needs its `labels` entry, plus the
multi-select list, the distinctness pairs or the per-template minimum when they apply. Prompt text
must contain no `"` and no brackets other than the placeholders — `tests/test_gui_operaciones.py`
asserts the generated query has neither. `tests/test_guia.py` requires `assets/guia.html` to
document every template in the same order.

**Consent is a data path, not a checkbox.** R output only reaches the endpoint when the
request carries `share_output`; the syntax diagnostic is exempt because it contains no
data values. Keep that distinction when editing `converse`.

**Data is never modified in place.** `prepare_data` reads the source, applies recoding and
collapsing, and writes a working `datos.csv` plus `profile.json` into the operation folder.
Tests assert the source bytes are unchanged.

**All temporaries live under the program folder.** `analisisr_session.temporary_root()` →
`<app>/temporales`, and `configure_temporaries()` repoints `TEMP`/`TMP`/`TMPDIR` and
`tempfile.tempdir` there so R inherits it; the install directory must be writable.
`SessionWorkspace` holds session files in memory between operations and deletes the folder
each time (`suspend`/`restore`), guarded by symlink and root checks and a 1 GiB / 10000 file
cap. Use `temporary_file()` + `replace_file()` for atomic writes — `replace_file` handles
the cross-drive `EXDEV` case without clobbering an existing file.

**Providers.** `engine.PROVIDERS` holds one entry per backend (`local` llama-server,
`openai`, `deepseek`, `anthropic`, `gemini`, `none`) with host, default model, key env var
and `style`; `Backend` branches on `style`, not on `kind`. Reasoning is forcibly disabled
per provider and a response that reports thinking tokens is rejected
(`Backend._no_reasoning_options`, `tests/test_sin_razonamiento.py`) — adding a provider
means adding its disable syntax there too.

## Conventions

- 4-space indent, `snake_case`, uppercase constants, `pathlib.Path` for filesystem work.
- UTF-8 JSON (`ensure_ascii=False`, via `write_json`); Spanish for UI text, messages,
  docstrings and comments.
- Known shortcuts are marked with a `# shortcut: <limit>, <when to upgrade>` comment.
- Keep reusable logic out of UI callbacks — the worker must be able to call it.
- Secrets stay in the `analisisr_secrets` flow (keyring/DPAPI, Fernet elsewhere); never in
  a `request.json`, a session file or a commit.
- Generated R runs with the user's permissions; the operation filter is not a sandbox.
