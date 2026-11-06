from __future__ import annotations

import base64
import hashlib
import hmac
import os
import re
from dataclasses import dataclass

_SCRYPT_N = 1 << 14
_SCRYPT_R = 8
_SCRYPT_P = 1
_SALT_BYTES = 16
_DKLEN = 32
_LEGACY_SHA256 = re.compile(r"^[0-9a-fA-F]{64}$")


def split_roles(value: str | object) -> tuple[str, ...]:
    """Normalize legacy single roles and the new semicolon-separated roles."""
    return tuple(dict.fromkeys(("Экономист" if part.strip()=="Аналитик" else part.strip()) for part in re.split(r"[;,|]+", str(value or "")) if part.strip()))


def has_role(value: str | object, role: str) -> bool:
    return role in split_roles(value)


def hash_password(password: str) -> str:
    salt = os.urandom(_SALT_BYTES)
    digest = hashlib.scrypt(
        password.encode("utf-8"), salt=salt, n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P, dklen=_DKLEN
    )
    return "$".join(
        [
            "scrypt",
            str(_SCRYPT_N),
            str(_SCRYPT_R),
            str(_SCRYPT_P),
            base64.urlsafe_b64encode(salt).decode("ascii"),
            base64.urlsafe_b64encode(digest).decode("ascii"),
        ]
    )


def verify_password(password: str, encoded: str) -> tuple[bool, bool]:
    """Returns (valid, should_upgrade). Supports legacy raw SHA-256."""
    encoded = str(encoded or "")
    if _LEGACY_SHA256.fullmatch(encoded):
        legacy = hashlib.sha256(password.encode("utf-8")).hexdigest()
        return hmac.compare_digest(legacy.lower(), encoded.lower()), True
    try:
        kind, n, r, p, salt64, digest64 = encoded.split("$", 5)
        if kind != "scrypt":
            return False, False
        salt = base64.urlsafe_b64decode(salt64.encode("ascii"))
        expected = base64.urlsafe_b64decode(digest64.encode("ascii"))
        # Password hashes live in a shared SQLite file.  Bound parameters
        # before passing attacker-controlled values to hashlib.scrypt so a
        # tampered record cannot force unbounded CPU/RAM allocation.
        n_value, r_value, p_value = int(n), int(r), int(p)
        if n_value < (1 << 12) or n_value > (1 << 20) or n_value & (n_value - 1):
            return False, False
        if r_value < 1 or r_value > 32 or p_value < 1 or p_value > 8:
            return False, False
        # scrypt's working set is approximately 128 * N * r bytes. Keep a
        # corrupted record from reserving gigabytes during a login attempt.
        if 128 * n_value * r_value > 128 * 1024 * 1024:
            return False, False
        if not 8 <= len(salt) <= 64 or not 16 <= len(expected) <= 128:
            return False, False
        actual = hashlib.scrypt(
            password.encode("utf-8"), salt=salt, n=n_value, r=r_value, p=p_value, dklen=len(expected)
        )
        return hmac.compare_digest(actual, expected), False
    except Exception:
        return False, False


class Permission:
    ORDERS_VIEW = "orders.view"
    ORDERS_CREATE = "orders.create"
    ORDERS_EDIT = "orders.edit"
    ORDERS_EXPORT = "orders.export"
    ORDERS_FILTER = "orders.filter"
    ORDERS_HISTORY = "orders.history"
    ORDERS_DELETE_DRAFT = "orders.delete_draft"
    NOTIFICATIONS_VIEW = "notifications.view"
    USERS_VIEW = "users.view"
    DATA_SYNC = "data.sync"
    DIAGNOSTICS_VIEW = "diagnostics.view"
    APP_UPDATE = "app.update"
    ACCESS_CONTROL = "access.control"
    CATALOG_VIEW = "catalog.view"
    CATALOG_CREATE = "catalog.create"
    CATALOG_EDIT = "catalog.edit"
    CATALOG_DELETE = "catalog.delete"
    CATALOG_IMPORT = "catalog.import"
    CATALOG_RESTORE = "catalog.restore"
    EMPLOYEES_VIEW = "employees.view"
    EMPLOYEES_CREATE = "employees.create"
    EMPLOYEES_EDIT = "employees.edit"
    EMPLOYEES_DELETE = "employees.delete"
    EMPLOYEES_IMPORT = "employees.import"
    EMPLOYEES_RESTORE = "employees.restore"
    ADMIN_VIEW = "admin.view"
    USERS_MANAGE = "users.manage"
    PERMISSIONS_MANAGE = "permissions.manage"
    AUDIT_VIEW = "audit.view"
    BACKUP_MANAGE = "backup.manage"
    BACKUP_RESTORE = "backup.restore"
    BACKUP_DELETE = "backup.delete"
    IDENTITY_BACKUP = "identity.backup"
    ANALYTICS_VIEW = "analytics.view"
    ANALYTICS_EXPORT = "analytics.export"


ALL_PERMISSIONS = [
    value for key, value in Permission.__dict__.items()
    if key.isupper() and isinstance(value, str)
]

PERMISSION_LABELS = {
    Permission.ORDERS_FILTER: "Наряды: фильтры",
    Permission.ORDERS_HISTORY: "Наряды: история изменений",
    Permission.ORDERS_DELETE_DRAFT: "Наряды: удаление черновиков",
    Permission.NOTIFICATIONS_VIEW: "Уведомления: просмотр",
    Permission.USERS_VIEW: "Пользователи: просмотр",
    Permission.DATA_SYNC: "Данные: синхронизация",
    Permission.DIAGNOSTICS_VIEW: "Диагностика: просмотр",
    Permission.APP_UPDATE: "Программа: обновление",
    Permission.ACCESS_CONTROL: "Разрешительный режим: редактирование",
    Permission.ORDERS_VIEW: "Наряды: просмотр",
    Permission.ORDERS_CREATE: "Наряды: создание",
    Permission.ORDERS_EDIT: "Наряды: редактирование",
    Permission.ORDERS_EXPORT: "Наряды: Excel",
    Permission.CATALOG_VIEW: "Номенклатура: просмотр",
    Permission.CATALOG_CREATE: "Номенклатура: создание",
    Permission.CATALOG_EDIT: "Номенклатура: редактирование",
    Permission.CATALOG_DELETE: "Номенклатура: удаление",
    Permission.CATALOG_IMPORT: "Номенклатура: импорт",
    Permission.CATALOG_RESTORE: "Номенклатура: восстановление",
    Permission.EMPLOYEES_VIEW: "Сотрудники: просмотр",
    Permission.EMPLOYEES_CREATE: "Сотрудники: создание",
    Permission.EMPLOYEES_EDIT: "Сотрудники: редактирование",
    Permission.EMPLOYEES_DELETE: "Сотрудники: удаление",
    Permission.EMPLOYEES_IMPORT: "Сотрудники: импорт",
    Permission.EMPLOYEES_RESTORE: "Сотрудники: восстановление",
    Permission.ADMIN_VIEW: "Администрирование: вкладка",
    Permission.USERS_MANAGE: "Пользователи: управление",
    Permission.PERMISSIONS_MANAGE: "Роли: права",
    Permission.AUDIT_VIEW: "Журнал: просмотр",
    Permission.BACKUP_MANAGE: "База: резервные копии",
    Permission.BACKUP_RESTORE: "База: восстановление",
    Permission.BACKUP_DELETE: "База: удаление копий",
    Permission.IDENTITY_BACKUP: "Учётные записи: резервная копия",
    Permission.ANALYTICS_VIEW: "Аналитика: просмотр",
    Permission.ANALYTICS_EXPORT: "Аналитика: Excel",
}

DEFAULT_ROLE_PERMISSIONS = {
    # Role defaults; an account may replace these with explicit permissions.
    "Администратор": set(ALL_PERMISSIONS),
    "Мастер": {
        # Full Orders + Employees. Administration is visible for synchronization,
        # backups, archive viewing, logs and audit; account/access changes stay admin-only.
        Permission.ORDERS_VIEW, Permission.ORDERS_CREATE, Permission.ORDERS_EDIT, Permission.ORDERS_EXPORT,
        Permission.EMPLOYEES_VIEW, Permission.EMPLOYEES_CREATE, Permission.EMPLOYEES_EDIT,
        Permission.EMPLOYEES_DELETE, Permission.EMPLOYEES_IMPORT,
        Permission.ADMIN_VIEW, Permission.AUDIT_VIEW, Permission.BACKUP_MANAGE,
    },
    "Бухгалтер": {
        # Orders: list + export. Catalog: full functionality. Administration is
        # available with the same protected controls as Master.
        Permission.ORDERS_VIEW, Permission.ORDERS_EXPORT,
        Permission.CATALOG_VIEW, Permission.CATALOG_CREATE, Permission.CATALOG_EDIT,
        Permission.CATALOG_DELETE, Permission.CATALOG_IMPORT,
        Permission.ADMIN_VIEW, Permission.AUDIT_VIEW, Permission.BACKUP_MANAGE,
    },
}

ACCOUNTING_ROLES = {"Бухгалтер", "Экономист"}
ANALYTICS_ROLES = {"Администратор", "Бухгалтер", "Экономист"}
ANALYTICS_ONLY_ROLES = {"Экономист"}
WORKSHOP_ROLES = {
    "Мастер Упаковка": ("packaging",),
    "Мастер Коптильный Цех": ("smoking", "drying"),
    "Мастер Цех Сушки": ("drying", "smoking"),
    "Мастер Сычужный цех": ("rennet", "cheese"),
    "Мастер Сыр цех": ("cheese", "rennet"),
    "Мастер Адыгейский Цех": ("adyghe",),
    # Preserve the legacy account, restricting it to the existing database.
    "Мастер": ("packaging",),
}
DEFAULT_ROLE_PERMISSIONS["Бухгалтер"].update({Permission.ANALYTICS_VIEW, Permission.ANALYTICS_EXPORT})
DEFAULT_ROLE_PERMISSIONS["Мастер"].update({Permission.ORDERS_FILTER, Permission.ORDERS_HISTORY, Permission.ORDERS_DELETE_DRAFT, Permission.NOTIFICATIONS_VIEW, Permission.DATA_SYNC, Permission.DIAGNOSTICS_VIEW})
DEFAULT_ROLE_PERMISSIONS["Бухгалтер"].update({Permission.ORDERS_FILTER, Permission.NOTIFICATIONS_VIEW, Permission.DATA_SYNC, Permission.DIAGNOSTICS_VIEW})
DEFAULT_ROLE_PERMISSIONS["Экономист"] = {Permission.ORDERS_VIEW, Permission.ANALYTICS_VIEW, Permission.ANALYTICS_EXPORT, Permission.NOTIFICATIONS_VIEW}
for _role in WORKSHOP_ROLES:
    DEFAULT_ROLE_PERMISSIONS[_role] = set(DEFAULT_ROLE_PERMISSIONS["Мастер"])
ROLES = [
    "Администратор", "Бухгалтер", "Экономист",
    *(r for r in sorted(WORKSHOP_ROLES) if r != "Мастер"),
]



@dataclass(frozen=True)
class SessionUser:
    id: int
    username: str
    role: str
    permissions: frozenset[str]

    @property
    def roles(self) -> tuple[str, ...]:
        return split_roles(self.role)

    def has_role(self, role: str) -> bool:
        return has_role(self.role, role)

    def has_any_role(self, roles) -> bool:
        allowed = {str(item) for item in roles}
        return any(item in allowed for item in self.roles)

    def can(self, permission: str) -> bool:
        return permission in self.permissions
