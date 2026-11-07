#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""analisisr_secrets.py — perfiles de backend con API key cifrada.

Cifrado en reposo:
  - Windows: DPAPI (`CryptProtectData`), ligado a la cuenta de usuario. Sin contraseña
    que recordar y sin clave maestra que se pueda copiar junto al archivo.
  - Otros sistemas: `cryptography.fernet` con clave derivada por PBKDF2 de una frase
    de paso, o `$ANALIZAR_MASTER_KEY`. Si no hay forma segura de cifrar, se niega a
    guardar en claro en lugar de fingir que protege.

El archivo sólo contiene: proveedor, endpoint, modelo y el token cifrado.
"""

from __future__ import annotations

import base64
import json
import os
import shutil
import sys
from pathlib import Path
from analisisr_session import temporary_file, replace_file

APP_DIR_NAME = "AnalizaR Desktop"
# Nombre anterior del programa: su carpeta se migra una vez para no perder los perfiles.
LEGACY_APP_DIR_NAME = "AnalisisR"
FILE_NAME = "backends.json"
# El servicio del keyring conserva el nombre antiguo a propósito: ahí está la clave maestra
# que descifra los perfiles ya guardados, y renombrarlo los dejaría ilegibles.
KEYRING_SERVICE = "AnalisisR"
KEYRING_PREFIX = "keyring:"


# --------------------------------------------------------------------------- #
# Ubicación del archivo de configuración
# --------------------------------------------------------------------------- #

def config_dir() -> Path:
    if sys.platform.startswith("win"):
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
    elif sys.platform == "darwin":
        base = os.path.expanduser("~/Library/Application Support")
    else:
        base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    d = Path(base) / APP_DIR_NAME
    nueva = not d.exists()
    d.mkdir(parents=True, exist_ok=True)
    if nueva:
        _migrate_legacy(Path(base) / LEGACY_APP_DIR_NAME, d)
    return d


def _migrate_legacy(antigua: Path, nueva: Path) -> None:
    """Copia la configuración del nombre anterior; el original se conserva intacto."""
    if antigua == nueva or antigua.is_symlink() or not antigua.is_dir():
        return
    for origen in antigua.iterdir():
        if not origen.is_file() or origen.is_symlink():
            continue
        try:
            shutil.copy2(origen, nueva / origen.name)
        except OSError:
            pass


def config_path() -> Path:
    return config_dir() / FILE_NAME


# --------------------------------------------------------------------------- #
# DPAPI (Windows)
# --------------------------------------------------------------------------- #

def _dpapi(blob: bytes, protect: bool) -> bytes:
    import ctypes
    from ctypes import wintypes

    class DATA_BLOB(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD),
                    ("pbData", ctypes.POINTER(ctypes.c_char))]

    def to_blob(data: bytes) -> DATA_BLOB:
        buf = ctypes.create_string_buffer(data, len(data))
        return DATA_BLOB(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))

    def from_blob(b: DATA_BLOB) -> bytes:
        return ctypes.string_at(b.pbData, b.cbData)

    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    entrada = to_blob(blob)
    salida = DATA_BLOB()
    # CRYPTPROTECT_UI_FORBIDDEN = 0x1: nunca abre diálogos desde un servicio/hilo sin UI
    ok = (crypt32.CryptProtectData if protect else crypt32.CryptUnprotectData)(
        ctypes.byref(entrada), None, None, None, None, 0x1, ctypes.byref(salida))
    if not ok:
        raise OSError(f"DPAPI falló (error {ctypes.GetLastError()})")
    try:
        return from_blob(salida)
    finally:
        kernel32.LocalFree(salida.pbData)


# --------------------------------------------------------------------------- #
# Fernet (otros sistemas)
# --------------------------------------------------------------------------- #

def _fernet(passphrase: str | None = None):
    try:
        from cryptography.fernet import Fernet
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    except ImportError as e:                                      # noqa: BLE001
        raise RuntimeError(
            "Para cifrar API keys en este sistema hace falta el paquete 'cryptography':\n"
            "  python -m pip install cryptography") from e
    # El nombre anterior se sigue aceptando: con otra clave maestra no se descifraría nada.
    secreto = (passphrase or os.environ.get("ANALIZAR_MASTER_KEY")
               or os.environ.get("ANALISISR_MASTER_KEY"))
    if not secreto:
        raise RuntimeError(
            "Define ANALIZAR_MASTER_KEY (o pasa una frase de paso) para cifrar las claves.")
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=b"analisisr-keystore-v1",
                     iterations=390000)
    return Fernet(base64.urlsafe_b64encode(kdf.derive(secreto.encode())))


# --------------------------------------------------------------------------- #
# API pública
# --------------------------------------------------------------------------- #

# --------------------------------------------------------------------------- #
# D3 — Almacén del sistema (Windows Credential Manager vía `keyring`)
# --------------------------------------------------------------------------- #

def keyring_disponible() -> tuple[bool, str]:
    """¿Se puede delegar el secreto al gestor del sistema operativo?"""
    try:
        import keyring                      # noqa: F401
        from keyring import get_keyring
    except ImportError:
        return False, "el paquete 'keyring' no está instalado"
    try:
        backend = get_keyring()
        nombre = backend.__class__.__name__
        if nombre in ("Keyring", "FailKeyring", "NullKeyring"):
            return False, f"sin backend utilizable ({nombre})"
        return True, nombre
    except Exception as e:                                        # noqa: BLE001
        return False, f"error consultando el backend: {e}"


def _keyring_set(provider: str, secreto: str) -> bool:
    import keyring
    keyring.set_password(KEYRING_SERVICE, provider, secreto)
    return True


def _keyring_get(provider: str) -> str:
    import keyring
    return keyring.get_password(KEYRING_SERVICE, provider) or ""


def _keyring_delete(provider: str) -> bool:
    import keyring
    try:
        keyring.delete_password(KEYRING_SERVICE, provider)
        return True
    except Exception:                                             # noqa: BLE001
        return False


def encrypt(plaintext: str, passphrase: str | None = None,
            provider: str | None = None) -> str:
    """Cifra el secreto. Con `provider` y gestor disponible, lo delega al sistema.

    El token que se guarda en el archivo pasa a ser `keyring:<proveedor>`: el archivo
    deja de contener material cifrado y el secreto vive en el almacén del SO.
    """
    if not plaintext:
        return ""
    if provider:
        ok, _ = keyring_disponible()
        if ok:
            _keyring_set(provider, plaintext)
            return f"{KEYRING_PREFIX}{provider}"
    if sys.platform.startswith("win"):
        return "dpapi:" + base64.b64encode(_dpapi(plaintext.encode("utf-8"), True)).decode()
    f = _fernet(passphrase)
    return "fernet:" + f.encrypt(plaintext.encode("utf-8")).decode()


def decrypt(token: str, passphrase: str | None = None) -> str:
    if not token:
        return ""
    if token.startswith(KEYRING_PREFIX):
        ok, motivo = keyring_disponible()
        if not ok:
            raise RuntimeError(
                f"el secreto está en el gestor del sistema y no está disponible ({motivo}).\n"
                f"  Instala 'keyring' o vuelve a guardar la clave en este equipo.")
        return _keyring_get(token[len(KEYRING_PREFIX):])
    if token.startswith("dpapi:"):
        if not sys.platform.startswith("win"):
            raise RuntimeError("este token DPAPI sólo se puede descifrar en Windows, "
                               "con la misma cuenta de usuario")
        return _dpapi(base64.b64decode(token[6:]), False).decode("utf-8")
    if token.startswith("fernet:"):
        return _fernet(passphrase).decrypt(token[7:].encode()).decode("utf-8")
    raise ValueError("token con formato desconocido")


def mask(secret: str) -> str:
    """Representación para mostrar y para logs: nunca la clave completa."""
    if not secret:
        return ""
    if len(secret) <= 8:
        return "•" * len(secret)
    return f"{secret[:4]}…{secret[-2:]} ({len(secret)} caracteres)"


def load(path: Path | None = None) -> dict:
    """Devuelve {proveedor: {host, model, api_key (token cifrado), saved_at}}."""
    f = path or config_path()
    if not f.is_file():
        return {}
    try:
        data = json.loads(f.read_text(encoding="utf-8"))
        return data.get("profiles", {}) if isinstance(data, dict) else {}
    except (ValueError, OSError):
        return {}


def save(profiles: dict, path: Path | None = None) -> Path:
    f = path or config_path()
    f.parent.mkdir(parents=True, exist_ok=True)
    payload = {"schema": "analizar.backends/1", "profiles": profiles}
    with temporary_file() as tmp:
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        try:
            os.chmod(tmp, 0o600)
        except OSError:
            pass
        replace_file(tmp, f)
    return f


def upsert(provider: str, host: str, model: str, api_key: str | None,
           path: Path | None = None) -> Path:
    """Guarda un perfil; si api_key es None conserva la clave ya almacenada."""
    import datetime as _dt
    perfiles = load(path)
    previo = perfiles.get(provider, {})
    token = previo.get("api_key", "")
    if api_key is not None:
        token = encrypt(api_key, provider=provider) if api_key else ""
    perfiles[provider] = {
        "host": host,
        "model": model,
        "api_key": token,
        "saved_at": _dt.datetime.now().isoformat(timespec="seconds"),
    }
    save(perfiles, path)
    return path or config_path()


def remove(provider: str, path: Path | None = None) -> Path:
    perfiles = load(path)
    previo = (perfiles.get(provider) or {}).get("api_key", "")
    if previo.startswith(KEYRING_PREFIX):
        _keyring_delete(provider)
    perfiles.pop(provider, None)
    save(perfiles, path)
    return path or config_path()


def check() -> dict:
    """Estado del almacén: método disponible y ruta, sin revelar secretos."""
    if sys.platform.startswith("win"):
        metodo = "DPAPI (ligado a la cuenta de Windows)"
        try:
            _dpapi(b"prueba", True)
            disponible = True
        except Exception as e:                                    # noqa: BLE001
            disponible, metodo = False, f"DPAPI no disponible: {e}"
    else:
        try:
            _fernet(None)
            disponible, metodo = True, "Fernet (PBKDF2 con ANALIZAR_MASTER_KEY)"
        except RuntimeError as e:
            disponible, metodo = False, str(e)
    ok_kr, detalle_kr = keyring_disponible()
    return {"path": str(config_path()), "method": metodo, "available": disponible,
            "keyring": ok_kr, "keyring_backend": detalle_kr,
            "providers_configured": sorted(load().keys())}
