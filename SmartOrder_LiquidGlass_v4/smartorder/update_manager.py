"""Safe SmartOrder patch staging.

Patch archives never contain databases. They carry a ``patch.json`` manifest
and application files under ``payload/``; the running process stages the
archive and writes a pending manifest for the launcher to apply on restart.
"""
from __future__ import annotations

import json
import os
import shutil
import tempfile
import zipfile
from pathlib import Path
from datetime import datetime

from .config import APP_VERSION, local_root

MAX_PATCH_BYTES = 100 * 1024 * 1024
MAX_FILES = 2048
MAX_FILE_BYTES = 20 * 1024 * 1024


class PatchError(ValueError):
    pass


def _safe_relative(name: str) -> str:
    path = Path(str(name).replace("\\", "/"))
    if path.is_absolute() or ".." in path.parts or str(path) in ("", "."):
        raise PatchError(f"Недопустимый путь в патче: {name}")
    return path.as_posix()


def _install_root() -> Path:
    """Directory whose files are replaced when SmartOrder restarts."""
    import sys
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    # Source installs keep the package and launcher in the repository root.
    return Path(__file__).resolve().parent.parent


def _manifest_path() -> Path:
    return local_root() / "updates" / "pending_update.json"


def inspect_patch(path: str | Path) -> dict:
    archive = Path(path)
    if not archive.is_file() or archive.stat().st_size > MAX_PATCH_BYTES:
        raise PatchError("Патч отсутствует или превышает 100 МБ")
    try:
        with zipfile.ZipFile(archive, "r") as zf:
            infos = zf.infolist()
            if len(infos) > MAX_FILES:
                raise PatchError("В патче слишком много файлов")
            manifest_raw = zf.read("patch.json")
            manifest = json.loads(manifest_raw.decode("utf-8"))
            version = str(manifest.get("version", "")).strip()
            if not version:
                raise PatchError("В patch.json отсутствует version")
            files = []
            total = 0
            for info in infos:
                name = _safe_relative(info.filename)
                if name == "patch.json" or info.is_dir():
                    continue
                if not name.startswith("payload/"):
                    raise PatchError("Файлы патча должны находиться в payload/")
                lower_name = name.casefold()
                if lower_name.endswith((".db", ".sqlite", ".sqlite3")) or "/databases/" in lower_name:
                    raise PatchError("База данных не может входить в патч")
                if info.file_size > MAX_FILE_BYTES:
                    raise PatchError(f"Файл патча слишком большой: {name}")
                total += int(info.file_size)
                if total > MAX_PATCH_BYTES:
                    raise PatchError("Распакованный патч превышает 100 МБ")
                files.append(name)
            if not files:
                raise PatchError("Патч не содержит файлов payload/")
            return {"version": version, "title": str(manifest.get("title", "")),
                    "description": str(manifest.get("description", "")),
                    "files": files, "previous_version": str(manifest.get("previous_version", "")),
                    "source": str(archive)}
    except zipfile.BadZipFile as exc:
        raise PatchError("Файл патча повреждён или не является ZIP") from exc


def stage_patch(path: str | Path) -> dict:
    manifest = inspect_patch(path)
    target_root = local_root() / "updates" / manifest["version"]
    target_root.parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix="patch-", dir=str(target_root.parent)))
    try:
        with zipfile.ZipFile(path, "r") as zf:
            for name in manifest["files"]:
                destination = tmp / name.removeprefix("payload/")
                destination.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(name, "r") as src, destination.open("wb") as dst:
                    shutil.copyfileobj(src, dst, length=1024 * 1024)
        if target_root.exists():
            shutil.rmtree(target_root)
        os.replace(tmp, target_root)
    except Exception:
        shutil.rmtree(tmp, ignore_errors=True)
        raise
    manifest["staged_root"] = str(target_root)
    manifest["base_version"] = APP_VERSION
    pending = _manifest_path()
    pending.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def publish_update_notice(manifest: dict, root: str | Path | None = None) -> Path:
    """Publish a small shared announcement; it never touches a database."""
    target_root = Path(root) if root is not None else Path(os.environ.get("SMARTORDER_NETWORK_ROOT") or Path.cwd())
    target_root.mkdir(parents=True, exist_ok=True)
    target = target_root / "UPDATE_ANNOUNCEMENT.json"
    payload = {
        "version": str(manifest.get("version", "")),
        "title": str(manifest.get("title", "Обновление SmartOrder")),
        "description": str(manifest.get("description", "")),
        "created_at": datetime.now().strftime("%d.%m.%Y %H:%M"),
    }
    tmp = target.with_suffix(target.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, target)
    return target


def apply_pending_update(root: str | Path | None = None) -> dict | None:
    """Apply a staged patch atomically at process startup.

    The database is deliberately outside the payload and is never copied or
    opened here. Each destination is replaced through a temporary file; a
    failed file leaves the previous application file intact.
    """
    pending = _manifest_path()
    if not pending.exists():
        return None
    manifest = json.loads(pending.read_text(encoding="utf-8"))
    staged = Path(str(manifest.get("staged_root", "")))
    if not staged.is_dir():
        raise PatchError("Подготовленные файлы обновления не найдены")
    install = Path(root) if root is not None else _install_root()
    backup = local_root() / "updates" / "applied" / str(manifest.get("version", "unknown"))
    copied = []
    try:
        for item in manifest.get("files", []):
            relative = _safe_relative(str(item).removeprefix("payload/"))
            if relative.casefold().endswith((".db", ".sqlite", ".sqlite3")):
                raise PatchError("База данных не может входить в патч")
            source = staged / relative
            if not source.is_file():
                raise PatchError(f"Файл обновления отсутствует: {relative}")
            destination = install / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            if destination.exists() and destination.is_file():
                previous = backup / relative
                previous.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(destination, previous)
            temporary = destination.with_suffix(destination.suffix + ".smartorder-tmp")
            shutil.copy2(source, temporary)
            os.replace(temporary, destination)
            copied.append((relative, destination.exists() and previous.exists()))
        manifest["applied_files"] = [item[0] for item in copied]
        manifest["applied_at"] = datetime.now().isoformat(timespec="seconds")
        (backup / "applied.json").parent.mkdir(parents=True, exist_ok=True)
        (backup / "applied.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        pending.unlink(missing_ok=True)
        return manifest
    except Exception:
        for relative, had_previous in copied:
            destination = install / relative
            previous = backup / relative
            try:
                if had_previous and previous.exists():
                    shutil.copy2(previous, destination)
                elif destination.exists():
                    destination.unlink()
            except Exception:
                pass
        raise
