"""Sesiones portables: JSON y archivos de trabajo en un ZIP, sin credenciales."""
from __future__ import annotations

import json
from contextlib import contextmanager
import hashlib
import os
from pathlib import Path, PurePosixPath
import shutil
import stat
import sys
import tempfile
import zipfile

SCHEMA = "analisisr.session/1"
# shortcut: hasta 1 GiB y 10000 archivos por sesión; ampliar si proyectos reales lo requieren.
MAX_BYTES = 1024 ** 3
MAX_FILES = 10000


def temporary_root() -> Path:
    base = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
    root = base / "temporales"
    root.mkdir(parents=True, exist_ok=True)
    return root


def configure_temporaries(operation: Path | None = None) -> None:
    root = temporary_root().resolve()
    target = operation.resolve() if operation and operation.resolve().is_relative_to(root) else root
    target.mkdir(parents=True, exist_ok=True)
    for name in ("TEMP", "TMP", "TMPDIR"):
        os.environ[name] = str(target)
    tempfile.tempdir = str(target)


@contextmanager
def temporary_file(suffix=".tmp"):
    fd, name = tempfile.mkstemp(dir=temporary_root(), prefix="AnalisisR_", suffix=suffix)
    os.close(fd)
    path = Path(name)
    try:
        yield path
    finally:
        path.unlink(missing_ok=True)


def replace_file(temporary: Path, destination: Path) -> None:
    try:
        os.replace(temporary, destination)
    except OSError as exc:
        import errno
        if exc.errno != errno.EXDEV:
            raise
        # Otra unidad: creación exclusiva conserva cualquier archivo anterior.
        created = False
        try:
            with destination.open("xb") as dst:
                created = True
                with temporary.open("rb") as src:
                    shutil.copyfileobj(src, dst)
        except BaseException:
            if created:
                destination.unlink(missing_ok=True)
            raise


class SessionWorkspace:
    """Archivos de la sesión en memoria entre operaciones; disco solo mientras se usa."""

    def __init__(self):
        self.folder = Path(tempfile.mkdtemp(prefix="AnalisisR_", dir=temporary_root())).resolve()
        self._root = self.folder
        self.files: dict[str, bytes] = {}

    def _check_root(self):
        if self.folder != self._root or self.folder.is_symlink() or self.folder.resolve() != self._root:
            raise ValueError("La carpeta temporal no coincide con la creada por esta sesión.")

    def restore(self):
        self._check_root()
        self.folder.mkdir(parents=True, exist_ok=True)
        for relative, content in self.files.items():
            target = self.folder / relative
            if not target.resolve().is_relative_to(self._root):
                raise ValueError("Archivo fuera de la carpeta temporal de la sesión.")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)

    def suspend(self):
        """Conserva todos los archivos antes de eliminarlos; un fallo no descarta los datos."""
        self._check_root()
        if not self.folder.exists():
            return
        paths = list(self.folder.rglob("*"))
        if any(p.is_symlink() or not p.resolve().is_relative_to(self._root) for p in paths):
            raise ValueError("La carpeta temporal contiene un enlace fuera de la sesión.")
        files = [p for p in paths if p.is_file()]
        if len(files) > MAX_FILES or sum(p.stat().st_size for p in files) > MAX_BYTES:
            raise ValueError("La sesión supera el límite de 1 GiB o 10000 archivos en memoria.")
        snapshot = {p.relative_to(self.folder).as_posix(): p.read_bytes() for p in files}
        self.files = snapshot
        self._remove()

    def read_text(self, path):
        path = Path(path)
        if path.is_file():
            return path.read_text(encoding="utf-8")
        relative = path.resolve().relative_to(self._root).as_posix()
        if relative not in self.files:
            raise FileNotFoundError(str(path))
        return self.files[relative].decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")

    def _remove(self):
        self._check_root()
        if self.folder.exists():
            shutil.rmtree(self.folder)

    def close(self):
        self._remove()
        self.files.clear()


def _validate_state(state: dict) -> None:
    endpoint = state.get("endpoint", {})
    if (not isinstance(endpoint, dict) or
            any(not isinstance(endpoint.get(k, ""), str) for k in ("backend", "host", "model")) or
            any(not isinstance(endpoint.get(k, 0), int) for k in ("max_tokens", "timeout")) or
            not isinstance(state.get("question", ""), str)):
        raise ValueError("Configuración de sesión no válida.")
    for turn in state.get("history", []):
        if (not isinstance(turn.get("context", ""), str) or
                not isinstance(turn.get("scripts", []), list) or
                any(not isinstance(p, str) for p in turn.get("scripts", []))):
            raise ValueError("Historial de sesión no válido.")
    profile = state.get("profile")
    if profile is None:
        return
    treatment = state.get("data_request")
    if (not isinstance(treatment, dict) or not isinstance(treatment.get("keep"), list) or
            any(not isinstance(k, str) for k in treatment["keep"]) or
            not isinstance(treatment.get("recode", ""), str) or
            not isinstance(treatment.get("collapse", 0), int)):
        raise ValueError("Tratamiento de datos no válido.")
    for item in (profile, state.get("table_profile") or profile):
        if (not isinstance(item, dict) or not isinstance(item.get("columns"), list) or
                not isinstance(item.get("source_file"), str) or
                any(not isinstance(item.get(k), int) for k in ("n_rows", "n_cols"))):
            raise ValueError("Perfil de datos no válido.")
        for column in item["columns"]:
            if (not isinstance(column, dict) or not isinstance(column.get("column"), str) or
                    column.get("class") not in ("id", "binary", "nominal", "ordinal", "continuous", "text")):
                raise ValueError("Columnas de sesión no válidas.")


def save_session(path: Path, folder: Path, state: dict) -> None:
    """Guarda una instantánea y reemplaza el destino solo al completar el ZIP."""
    path, folder = Path(path).resolve(), Path(folder).resolve()
    if path.is_relative_to(folder):
        raise ValueError("Guarda la sesión fuera de su carpeta temporal de trabajo.")
    source = Path(state["profile"]["source_file"]) if state.get("profile") else None
    if source and not source.is_file():
        raise ValueError("No se encuentra el origen de los datos; vuelve a importarlo antes de guardar.")
    files = [p for p in folder.rglob("*") if p.is_file() and not p.is_symlink()]
    if len(files) + 2 > MAX_FILES or sum(p.stat().st_size for p in files) + (source.stat().st_size if source else 0) > MAX_BYTES:
        raise ValueError("La sesión supera el límite de 1 GiB o 10000 archivos.")
    path.parent.mkdir(parents=True, exist_ok=True)
    folder.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=folder, suffix=".tmp")
    os.close(fd)
    try:
        with zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED) as archive:
            manifest = {"schema": SCHEMA, "root": str(folder), "state": state,
                        "source": str(source) if source else None,
                        "source_entry": "source/original" + source.suffix if source else None}
            archive.writestr("session.json", json.dumps(manifest, ensure_ascii=False))
            for item in files:
                archive.write(item, "artifacts/" + item.relative_to(folder).as_posix())
            if source:
                archive.write(source, manifest["source_entry"])
        replace_file(Path(temporary), path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def _replace(text: str, old: str, new: str) -> str:
    """Actualiza rutas normales, POSIX y escapadas en JSON/código R."""
    for before, after in ((json.dumps(old)[1:-1], json.dumps(new)[1:-1]),
                          (old, new), (old.replace("\\", "/"), new.replace("\\", "/"))):
        text = text.replace(before, after)
    return text


def load_session(path: Path, folder: Path) -> dict:
    """Valida y extrae en una carpeta vacía, sin ejecutar archivos de la sesión."""
    folder = Path(folder).resolve()
    if folder.exists() and any(folder.iterdir()):
        raise ValueError("La carpeta de destino de la sesión debe estar vacía.")
    try:
        with zipfile.ZipFile(path) as archive:
            entries = archive.infolist()
            if len(entries) > MAX_FILES or sum(p.file_size for p in entries) > MAX_BYTES:
                raise ValueError("Sesión demasiado grande.")
            names = [p.filename for p in entries]
            if len(set(names)) != len(names):
                raise ValueError("La sesión contiene archivos duplicados.")
            for entry in entries:
                name = PurePosixPath(entry.filename)
                if (not name.parts or name.is_absolute() or ".." in name.parts or "\\" in entry.filename
                        or ":" in entry.filename or stat.S_ISLNK(entry.external_attr >> 16)
                        or not (entry.filename == "session.json" or name.parts[0] in ("artifacts", "source"))):
                    raise ValueError("La sesión contiene una ruta no permitida.")
            info = archive.getinfo("session.json")
            if info.file_size > 10 * 1024 * 1024:
                raise ValueError("El índice de sesión es demasiado grande.")
            manifest = json.loads(archive.read(info))
            state = manifest.get("state")
            if manifest.get("schema") != SCHEMA or not isinstance(manifest.get("root"), str) or not manifest["root"] or not isinstance(state, dict):
                raise ValueError("Formato de sesión no compatible.")
            if not isinstance(state.get("history", []), list) or any(
                    not isinstance(t, dict) or t.get("role") not in ("user", "assistant")
                    or not isinstance(t.get("content"), str) for t in state.get("history", [])):
                raise ValueError("Historial de sesión no válido.")
            if (not isinstance(state.get("endpoint", {}), dict) or
                    not isinstance(state.get("job", 0), int) or state.get("job", 0) < 0):
                raise ValueError("Configuración de sesión no válida.")
            profile = state.get("profile")
            if profile is not None and (not isinstance(profile, dict) or
                    not isinstance(profile.get("columns"), list) or
                    not isinstance(profile.get("source_file"), str) or
                    not isinstance(state.get("data_request"), dict)):
                raise ValueError("Datos de sesión no válidos.")
            _validate_state(state)
            source_entry = manifest.get("source_entry")
            if source_entry and (not isinstance(source_entry, str) or
                    not isinstance(manifest.get("source"), str) or
                    source_entry not in names or not source_entry.startswith("source/")):
                raise ValueError("El origen de datos no está incluido en la sesión.")
            folder.mkdir(parents=True, exist_ok=True)
            for entry in entries:
                if entry.filename == "session.json" or entry.is_dir():
                    continue
                relative = entry.filename.removeprefix("artifacts/")
                target = (folder / relative).resolve()
                if not target.is_relative_to(folder):
                    raise ValueError("Ruta de sesión fuera de la carpeta de trabajo.")
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(entry) as src, target.open("wb") as dst:
                    shutil.copyfileobj(src, dst)
        mapping = [(manifest["root"], str(folder))]
        if source_entry:
            mapping.append((manifest["source"], str(folder / source_entry)))
        def relocate(text: str) -> str:
            for old, new in mapping:
                text = _replace(text, old, new)
            return text
        state = json.loads(relocate(json.dumps(state, ensure_ascii=False)))
        for turn in state.get("history", []):
            if any(not Path(p).resolve().is_relative_to(folder) for p in turn.get("scripts", [])):
                raise ValueError("Los scripts deben pertenecer a la carpeta de la sesión.")
        if state.get("profile"):
            profile = state["profile"]
            for value in (profile["source_file"], profile.get("data_for_r") or profile.get("file", "")):
                if not Path(value).resolve().is_relative_to(folder) or not Path(value).is_file():
                    raise ValueError("Los datos de la sesión deben estar incluidos en el archivo.")
        for item in folder.rglob("*"):
            if item.is_file() and item.suffix.lower() in (".json", ".r"):
                item.write_text(relocate(item.read_text(encoding="utf-8")), encoding="utf-8")
        for item in folder.rglob("manifest.json"):
            manifest_data = json.loads(item.read_text(encoding="utf-8"))
            if manifest_data.get("schema") == "analisisr.operation/1":
                manifest_data["artifacts"] = {
                    p.name: {"sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
                    for p in item.parent.iterdir() if p.is_file() and p.name != "manifest.json"}
                item.write_text(json.dumps(manifest_data, ensure_ascii=False, indent=2), encoding="utf-8")
        return state
    except (zipfile.BadZipFile, KeyError, TypeError, json.JSONDecodeError) as exc:
        raise ValueError("Archivo de sesión no válido o incompleto.") from exc
