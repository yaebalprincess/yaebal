"""Personal reminders for the draft files already used by the orders list."""
import json
import re
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from .config import local_drafts_dir, local_state_dir
from .desktop_live import drafts_folder
from .security import Permission
from .workshops import WORKSHOPS, allowed_workshops


def _folders(root, workshop):
    return drafts_folder(root, workshop), local_drafts_dir(workshop)


def draft_workshop(root, user, path):
    parent = Path(path).parent
    return next((key for key in allowed_workshops(user) if parent in _folders(root, key)), None)


def _owned_by(path, payload, user, local):
    owner_id = payload.get("draft_owner_id")
    if owner_id is not None:
        return str(owner_id) == str(user.id)
    username = str(payload.get("draft_owner_username") or "").strip()
    if username:
        return username.casefold() == user.username.casefold()
    # The earliest clients stored the account ID in the local filename only.
    return local and re.fullmatch(rf"(?:new_order|order_\d+)_{user.id}\.json", path.name) is not None


def owned_drafts(manager, user):
    """Return each unsaved draft once, including local fallback copies."""
    if user.id <= 0:
        return {}
    manager.require(user, Permission.ORDERS_VIEW)
    result = {}
    for key in allowed_workshops(user):
        for local, folder in zip((False, True), _folders(manager.root, key)):
            try:
                paths = list(folder.glob("*.json"))
            except OSError:
                continue
            for path in paths:
                try:
                    updated = path.stat().st_mtime_ns
                    payload = json.loads(path.read_text(encoding="utf-8"))
                    if not isinstance(payload, dict):
                        continue
                    lines = payload.get("lines")
                    if not isinstance(lines, list) or not lines or not all(isinstance(line, dict) for line in lines):
                        continue
                    datetime.strptime(str(payload.get("order_date")), "%d-%m-%Y")
                    if not _owned_by(path, payload, user, local):
                        continue
                    for field in ("master_id", "department_id"):
                        if payload.get(field) is not None:
                            payload[field] = int(payload[field])
                except (OSError, TypeError, ValueError):
                    continue
                identity = f"{key}/{path.name}"
                previous = result.get(identity)
                if previous is None or updated > previous[0]:
                    result[identity] = (updated, key, path, payload)
    return result


def draft_rows(manager, user):
    records = owned_drafts(manager, user)
    references = {}
    rows = []
    for _, key, path, payload in sorted(records.values(), key=lambda record: record[0], reverse=True):
        if key not in references:
            db = manager.database(key, user)
            references[key] = (
                {row[0]: row[1] for row in db.get_employees(True)},
                {row[0]: row[1] for row in db.get_departments()},
            )
        masters, departments = references[key]
        rows.append((str(path), "Черновик · " + WORKSHOPS[key], str(payload["order_date"]),
                     str(payload.get("shift_type", "")), masters.get(payload.get("master_id"), ""),
                     departments.get(payload.get("department_id"), ""), str(payload.get("updated_at", "")), True))
    return rows


def _dismissal_path(user):
    return local_state_dir() / f"dismissed_drafts_{user.id}.json"


def dismissed_drafts(user):
    try:
        values = json.loads(_dismissal_path(user).read_text(encoding="utf-8"))
        return frozenset(value for value in values if isinstance(value, str)) if isinstance(values, list) else frozenset()
    except (OSError, ValueError):
        return frozenset()


def dismiss_drafts(user, keys):
    path = _dismissal_path(user)
    temporary = path.with_suffix(f".{uuid4().hex}.tmp")
    try:
        temporary.write_text(json.dumps(sorted(keys), ensure_ascii=False), encoding="utf-8")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
