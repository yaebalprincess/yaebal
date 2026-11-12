from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
import sys
from copy import deepcopy
from datetime import datetime

APP_NAME = "SmartOrder"
APP_VERSION = "1.0.10"
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


def local_drafts_dir(workshop: str | None = None) -> Path:
    path = local_state_dir() / "drafts"
    key = workshop or _ACTIVE_WORKSHOP
    if key != "packaging":
        path = path / key
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
    remember_personalization: bool = True
    auto_theme: bool = False
    about_theme: int = 2
    language: str = "ru"
    order_columns: list = field(default_factory=list)
    sync_personalization: bool = False
    editor_column_weights: list = field(default_factory=list)


LANGUAGE_CODES=("ru","en","es","kk","fr","de","ja","tt")


def settings_to_data(settings):
    from .appearance_config import normalize_appearance
    return {"theme":settings.theme,"zoom":settings.zoom,"appearance":normalize_appearance(settings.appearance),
            "remember_personalization":settings.remember_personalization,"auto_theme":settings.auto_theme,
            "about_theme":settings.about_theme,"language":settings.language,"order_columns":normalize_order_columns(settings.order_columns),
            "sync_personalization":settings.sync_personalization,
            "editor_column_weights":normalize_editor_columns(settings.editor_column_weights)}


def settings_from_data(data):
    from .appearance_config import normalize_appearance
    if not isinstance(data,dict):raise ValueError("Некорректная конфигурация")
    return UiSettings(theme="dark" if data.get("theme")=="dark" else "light",zoom=max(50,min(200,int(data.get("zoom",100)))),
        appearance=normalize_appearance(data.get("appearance")),remember_personalization=bool(data.get("remember_personalization",True)),
        auto_theme=bool(data.get("auto_theme",False)),about_theme=1 if data.get("about_theme")==1 else 2,
        language=data.get("language") if data.get("language") in LANGUAGE_CODES else "ru",
        order_columns=normalize_order_columns(data.get("order_columns")),sync_personalization=bool(data.get("sync_personalization",False)),
        editor_column_weights=normalize_editor_columns(data.get("editor_column_weights")))


def normalize_editor_columns(value):
    import math
    if not isinstance(value, list) or len(value) != 8:
        return []
    if any(type(item) not in (int, float) or not math.isfinite(item) or item <= 0 for item in value):
        return []
    total = sum(value)
    if not math.isfinite(total):
        return []
    return [item / total for item in value]


def normalize_order_columns(value):
    import math
    if not isinstance(value,list) or len(value)!=6:return []
    if any(type(x) not in (int,float) or not math.isfinite(x) or not 48<=x<=5000 for x in value):return []
    return [round(x,2) for x in value]


def scheduled_theme(now=None) -> str:
    """Use the workstation's local time, including local DST changes."""
    return "light" if 8 <= (now or datetime.now()).hour < 17 else "dark"


class SettingsStore:
    def __init__(self, user_id=None, username="") -> None:
        self.profile = user_id is not None
        suffix = hashlib.sha256(str(username).casefold().encode("utf-8")).hexdigest()[:16]
        self.path = local_state_dir() / (f"ui_{int(user_id)}_{suffix}.json" if self.profile else "ui.json")
        self._session = None
        self.on_save = None

    def load(self) -> UiSettings:
        from .appearance_config import normalize_appearance
        if self._session is not None:
            return deepcopy(self._session)
        try:
            source = self.path
            if self.profile and not source.exists():
                # v4 had one local file. Use it as an initial baseline only;
                # subsequent writes always go to the current user's profile.
                source = source.with_name("ui.json")
            data = json.loads(source.read_text(encoding="utf-8"))
            loaded = settings_from_data(data)
            result=loaded if loaded.remember_personalization or not self.profile else UiSettings(remember_personalization=False,sync_personalization=loaded.sync_personalization)
            self._session=deepcopy(result)
            return result
        except Exception:
            return UiSettings()

    def save(self, settings: UiSettings) -> None:
        from .appearance_config import normalize_appearance
        if self._session == settings: return
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(
            json.dumps(settings_to_data(settings), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        os.replace(tmp, self.path)
        self._session = deepcopy(settings)
        if callable(self.on_save):self.on_save(deepcopy(settings))

    def set_startup_enabled(self, settings, enabled):
        try: data=json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError,ValueError):
            self._session=None;self.save(settings)
            data=json.loads(self.path.read_text(encoding="utf-8"))
        data["remember_personalization"]=bool(enabled)
        tmp=self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding="utf-8")
        os.replace(tmp,self.path)
        settings.remember_personalization=bool(enabled);self._session=deepcopy(settings)
        if callable(self.on_save):self.on_save(settings_from_data(data))
