from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
import sys

APP_NAME = "SmartOrder"
APP_VERSION = "1.0"
_ACTIVE_WORKSHOP = "packaging"
WORKSHOP_DB_FILES = {
    "packaging":"work_orders_ypak.db", "smoking":"work_orders_koptil.db",
    "drying":"work_orders_sushka.db", "rennet":"work_orders_sychug.db",
    "cheese":"work_orders_syr.db", "adyghe":"work_orders_adyg.db",
}


def set_active_workshop(key: str) -> None:
    global _ACTIVE_WORKSHOP
    if key not in {"packaging", "smoking", "drying", "rennet", "cheese", "adyghe"}:
        raise ValueError("Неизвестный цех")
    _ACTIVE_WORKSHOP = key


def workshop_root(key: str | None = None) -> Path:
    key = key or _ACTIVE_WORKSHOP
    if key == "packaging":
        return network_root()
    if key not in {"smoking", "drying", "rennet", "cheese", "adyghe"}:
        raise ValueError("Неизвестный цех")
    return network_root() / "workshops" / key


def _local_appdata() -> Path:
    value = os.environ.get("LOCALAPPDATA")
    if value:
        return Path(value)
    return Path.home() / ".smartorder"


def resource_path(relative: str) -> Path:
    """Resource path for source and PyInstaller builds."""
    rel = str(relative or "").replace("\\", "/").lstrip("/")
    candidates = []
    if getattr(sys, "frozen", False):
        base = Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
        candidates.extend([base / rel, base / "resources" / rel])
        exe = Path(sys.executable).resolve().parent
        candidates.extend([exe / rel, exe / "resources" / rel, exe / "_internal" / "resources" / rel])
    else:
        root = Path(__file__).resolve().parent.parent
        candidates.extend([root / rel, root / "resources" / rel])
    for path in candidates:
        if path.exists():
            return path
    return candidates[0] if candidates else Path(rel)


def network_root() -> Path:
    """Network root is injected by launcher. No drive letter is hardcoded."""
    configured = (os.environ.get("SMARTORDER_NETWORK_ROOT") or "").strip().strip('"')
    if configured:
        return Path(configured)
    db_path = (os.environ.get("SMARTORDER_DB_PATH") or "").strip().strip('"')
    if db_path:
        return Path(db_path).parent
    # Direct EXE fallback.  The supported server layout is
    #   SmartOrder\SmartOrderApp\SmartOrderApp.exe
    # so the shared root is one level above the payload folder.  This keeps
    # direct runs deterministic even when Explorer/Windows supplies another CWD.
    if getattr(sys, "frozen", False):
        try:
            exe_dir = Path(sys.executable).resolve().parent
            if exe_dir.name.casefold() == "smartorderapp":
                return exe_dir.parent
            return exe_dir
        except Exception:
            pass
    return Path.cwd()


def base_database_path() -> Path:
    organized = network_root() / "databases" / WORKSHOP_DB_FILES["packaging"]
    if organized.exists():
        return organized
    configured = (os.environ.get("SMARTORDER_DB_PATH") or "").strip().strip('"')
    if configured:
        return Path(configured)
    # Full/Heavy layout keeps the shared DB directly in the SmartOrder network root.
    # This is also the first-run creation location.
    legacy = network_root() / "work_orders.db"
    return legacy if legacy.exists() else organized


def database_path() -> Path:
    return base_database_path() if _ACTIVE_WORKSHOP == "packaging" else network_root() / "databases" / WORKSHOP_DB_FILES[_ACTIVE_WORKSHOP]


def network_identity() -> str:
    raw = str(network_root()).replace("/", "\\").rstrip("\\").lower()
    return hashlib.sha256(raw.encode("utf-8", errors="ignore")).hexdigest()[:16]


def local_root() -> Path:
    root = _local_appdata() / APP_NAME
    root.mkdir(parents=True, exist_ok=True)
    return root


def local_state_dir() -> Path:
    path = local_root() / "state" / network_identity()
    path.mkdir(parents=True, exist_ok=True)
    return path


def local_drafts_dir() -> Path:
    path = local_state_dir() / "drafts"
    if _ACTIVE_WORKSHOP != "packaging":
        path = path / _ACTIVE_WORKSHOP
    path.mkdir(parents=True, exist_ok=True)
    return path


def local_logs_dir() -> Path:
    path = local_root() / "logs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def shared_dirs() -> dict[str, Path]:
    root = workshop_root()
    result = {
        "root": root,
        "manual": root / "backups" / "manual",
        "auto": root / "backups" / "auto",
        "before_restore": root / "backups" / "before_restore",
        "archives": root / "archives",
    }
    for key, path in result.items():
        if key != "root":
            path.mkdir(parents=True, exist_ok=True)
    return result


@dataclass
class UiSettings:
    theme: str = "light"
    zoom: int = 100
    appearance: dict = field(default_factory=dict)


class SettingsStore:
    def __init__(self) -> None:
        self.path = local_state_dir() / "ui.json"

    def load(self) -> UiSettings:
        from .appearance_config import normalize_appearance
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return UiSettings(
                theme=str(data.get("theme", "light")),
                zoom=max(50, min(200, int(data.get("zoom", 100)))),
                appearance=normalize_appearance(data.get("appearance")),
            )
        except Exception:
            return UiSettings()

    def save(self, settings: UiSettings) -> None:
        from .appearance_config import normalize_appearance
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(
            json.dumps({"theme": settings.theme, "zoom": settings.zoom,
                        "appearance": normalize_appearance(settings.appearance)}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        os.replace(tmp, self.path)
