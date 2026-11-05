from pathlib import Path

from smartorder.security import DEFAULT_ROLE_PERMISSIONS, Permission

ROOT = Path(__file__).resolve().parents[1]
UI = (ROOT / "smartorder" / "heavy_ui.py").read_text(encoding="utf-8")
APP = (ROOT / "smartorder" / "app.py").read_text(encoding="utf-8")


def test_master_and_accountant_access_rc16():
    master = DEFAULT_ROLE_PERMISSIONS["Мастер"]
    assert Permission.ORDERS_CREATE in master
    assert Permission.EMPLOYEES_EDIT in master
    assert Permission.CATALOG_VIEW not in master
    assert Permission.ADMIN_VIEW in master
    assert Permission.BACKUP_MANAGE in master

    accountant = DEFAULT_ROLE_PERMISSIONS["Бухгалтер"]
    assert Permission.ORDERS_VIEW in accountant
    assert Permission.ORDERS_EXPORT in accountant
    assert Permission.ORDERS_CREATE not in accountant
    for permission in (
        Permission.CATALOG_VIEW, Permission.CATALOG_CREATE, Permission.CATALOG_EDIT,
        Permission.CATALOG_DELETE, Permission.CATALOG_IMPORT, Permission.ADMIN_VIEW,
        Permission.BACKUP_MANAGE,
    ):
        assert permission in accountant


def test_all_tabs_visible_but_role_denied_tabs_disabled():
    assert "allowed={0,2,3,4}" in UI  # Master: Orders, Employees, Admin, About
    assert "allowed={0,1,3,4}" in UI  # Accountant: Orders, Catalog, Admin, About
    assert "self.tabs.setTabEnabled(i, enabled)" in UI
    assert "setTabVisible" not in UI


def test_about_and_theme_are_not_role_gated():
    # About is explicitly index 4 in every allowed role set; theme switch is built before role gating.
    assert 'allowed={0,1,2,3,4}' in UI
    assert 'self.theme=AnimatedToggle()' in UI
    role_block = UI.split("# RC9 fixed RBAC", 1)[1].split("main.addWidget(self.tabs,1)", 1)[0]
    assert "4}" in role_block


def test_accountant_history_panel_hidden():
    assert 'self.info_panel.setVisible(self.user.role not in ACCOUNTING_ROLES)' in UI


def test_startup_splash_exists_without_artificial_sleep():
    assert "QSplashScreen" in APP
    assert "Подключение к общей базе и загрузка интерфейса" in APP
    assert "Загрузка рабочего окна" in APP
    assert "time.sleep(" not in APP


def test_launcher_is_native_and_daily_shortcut_has_no_priority_boost():
    build = (ROOT / "Build_SmartOrder.ps1").read_text(encoding="ascii")
    native = (ROOT / "NativeLauncher.cs").read_text(encoding="utf-8")
    installer = (ROOT / "Install_and_Start_SmartOrder.ps1").read_text(encoding="utf-8-sig")
    assert "NativeLauncher.cs" in build
    assert '"--onefile"' not in build
    assert "ABOVE_NORMAL" not in native
    assert "PriorityClass" not in installer
    assert "$lnk.TargetPath=$LocalLauncher" in installer
