from decimal import Decimal
from pathlib import Path
import tempfile

from smartorder.db import Database
from smartorder.domain import OrderLine
from smartorder.security import DEFAULT_ROLE_PERMISSIONS, Permission

ROOT = Path(__file__).resolve().parents[1]
HEAVY = (ROOT / "smartorder" / "heavy_ui.py").read_text(encoding="utf-8")
POLICY = (ROOT / "smartorder" / "policy.py").read_text(encoding="utf-8")
CONFIG = (ROOT / "smartorder" / "config.py").read_text(encoding="utf-8")


def _fixture():
    tmp = tempfile.TemporaryDirectory()
    db = Database(Path(tmp.name) / "work_orders.db")
    db.create_first_admin("admin", "password123")
    admin = db.authenticate("admin", "password123")
    master = db.add_employee(admin, "Мастер", True)
    worker = db.add_employee(admin, "Работник", False)
    dep = db.add_department(admin, "Цех")
    work = db.add_work_type(admin, "Работа", "R1", "2.5")
    return tmp, db, admin, master, worker, dep, work


def test_rc16_version():
    assert 'APP_VERSION = "1.0"' in CONFIG


def test_referenced_worker_and_work_are_soft_deleted_but_historical_order_survives():
    tmp, db, admin, master, worker, dep, work = _fixture()
    try:
        oid = db.save_order(
            admin, "24-09-2026", "Дневная", master, dep,
            [OrderLine(worker, "Работник", work, "Работа", "R1", Decimal("2.5"), actual_value=Decimal("2"))],
        )
        assert db.delete_employee(admin, worker) == "marked"
        assert db.delete_work_type(admin, work) == "marked"
        assert db.is_soft_deleted("employee", worker)
        assert db.is_soft_deleted("work_type", work)
        assert any(int(r[0]) == worker for r in db.get_employees(False))
        assert not any(int(r[0]) == worker for r in db.get_active_employees(False))
        assert any(int(r[0]) == work for r in db.get_work_types())
        assert not any(int(r[0]) == work for r in db.get_active_work_types())
        loaded = db.get_order(oid)
        assert loaded["lines"][0].employee_name == "Работник"
        assert loaded["lines"][0].work_name == "Работа"
    finally:
        tmp.cleanup()


def test_unused_entities_are_kept_in_recycle_bin_for_30_days():
    tmp, db, admin, master, worker, dep, work = _fixture()
    try:
        extra_worker = db.add_employee(admin, "Удаляемый сотрудник", False)
        extra_work = db.add_work_type(admin, "Удаляемая работа", "DEL", "1")
        assert db.delete_employee(admin, extra_worker) == "marked"
        assert db.delete_work_type(admin, extra_work) == "marked"
        assert db.is_soft_deleted("employee", extra_worker)
        assert db.is_soft_deleted("work_type", extra_work)
        assert any(int(r[0]) == extra_worker for r in db.get_employees(False))
        assert any(int(r[0]) == extra_work for r in db.get_work_types())
    finally:
        tmp.cleanup()


def test_accountant_catalog_full_and_both_nonadmins_have_admin_tab():
    accountant = DEFAULT_ROLE_PERMISSIONS["Бухгалтер"]
    for permission in (
        Permission.CATALOG_VIEW, Permission.CATALOG_CREATE, Permission.CATALOG_EDIT,
        Permission.CATALOG_DELETE, Permission.CATALOG_IMPORT, Permission.ADMIN_VIEW,
        Permission.BACKUP_MANAGE,
    ):
        assert permission in accountant
    assert Permission.ORDERS_CREATE not in accountant
    assert Permission.ADMIN_VIEW in DEFAULT_ROLE_PERMISSIONS["Мастер"]
    assert 'allowed={0,2,3,4}' in HEAVY
    assert 'allowed={0,1,3,4}' in HEAVY


def test_nonadmin_admin_controls_are_protected():
    assert 'self.access_control_check.setEnabled(False)' in HEAVY
    assert '"Добавить пользователя" in text or "Восстановить" in text' in HEAVY
    assert 'if self.user.role!="Администратор"' in HEAVY
    assert 'Восстановление общей базы доступно только администратору.' in HEAVY


def test_login_has_clear_eye_tel_and_only_requested_phone():
    assert 'class _RC16LoginLineEdit' in HEAVY
    assert '_RC16LoginLineEdit("clear")' in HEAVY
    assert '_RC16LoginLineEdit("eye")' in HEAVY
    assert 'tel:+79955528513' in HEAVY
    assert '+7 995-552-85-13' in HEAVY
    assert '660-45-62' not in HEAVY


def test_user_password_placeholder():
    assert 'Введите пароль не менее 8-ми символов' in HEAVY


def test_about_uses_public_version_and_browser_documents():
    assert 'Enterprise Edition · Версия 1.0' in HEAVY
    assert 'self._rc13_chip("Версия: 1.0")' in HEAVY
    assert 'ensure_user_guide_document()' in HEAVY
    assert 'ensure_troubleshooting_document()' in HEAVY
    assert 'Как работать в программе?' in HEAVY
    assert '[.pdf]' in HEAVY
    assert 'Скачивание… 90%' in HEAVY
    assert 'Успешно скачано' in HEAVY
    assert 'QPrinter.PdfFormat' in HEAVY
    assert 'Забыли пароль?' in HEAVY
    assert 'Возможные проблемы при работе с программой' in HEAVY
    assert 'Прочее' in HEAVY
    assert 'USER_GUIDE_HTML' in POLICY
    assert 'TROUBLESHOOTING_HTML' in POLICY
    assert 'Вписать лист на одну страницу' in POLICY


def test_order_number_preview_and_active_selection_only():
    assert 'next_order_number_preview' in (ROOT / "smartorder" / "db.py").read_text(encoding="utf-8")
    assert 'Номер наряда:' in HEAVY
    assert 'get_active_employees(True)' in HEAVY
    assert 'get_active_employees(False)' in HEAVY
    assert 'get_active_work_types()' in HEAVY


def test_soft_delete_marker_is_rendered_red_in_reference_tabs():
    assert 'Помечено на удаление ❌' in HEAVY
    assert 'QColor("#FF3B30")' in HEAVY


def test_tab_switch_rc16_does_not_repolish_whole_app():
    start = HEAVY.index('class RC16MainWindow')
    method = HEAVY.index('    def _tab_changed', start)
    end = HEAVY.index('    def _build_admin_tab', method)
    block = HEAVY[method:end]
    assert 'apply_apple_design(' not in block
    assert 'self.tabs.setUpdatesEnabled(False)' in block
    assert 'background:transparent' in HEAVY[start:method]


def test_rc16_final_aliases():
    assert 'HeavyWorkOrderDialog = RC16WorkOrderDialog' in HEAVY
    assert 'HeavyMainWindow = RC16MainWindow' in HEAVY
    assert 'LoginDialog = RC16LoginDialog' in HEAVY
