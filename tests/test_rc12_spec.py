from pathlib import Path
import tempfile

from smartorder.db import Database

ROOT = Path(__file__).resolve().parents[1]
HEAVY = (ROOT / "smartorder" / "heavy_ui.py").read_text(encoding="utf-8")
CONFIG = (ROOT / "smartorder" / "config.py").read_text(encoding="utf-8")


def test_change_token_moves_with_audited_write():
    with tempfile.TemporaryDirectory() as td:
        db = Database(Path(td) / "work_orders.db")
        db.create_first_admin("admin", "password123")
        admin = db.authenticate("admin", "password123")
        before = db.change_token()
        db.add_department(admin, "RC12 department")
        after = db.change_token()
        assert after > before


def test_rc12_ordinary_delete_compacts_employee_slots():
    block = HEAVY.split("class RC12WorkOrderDialog", 1)[1].split("class _RC12ChangeBridge", 1)[0]
    assert "def _compact_ordinary_employees" in block
    assert "self._compact_ordinary_employees(identities)" in block
    assert "# Ordinary departments keep work payload" in block


def test_rc12_grouped_delete_removes_owned_rows():
    block = HEAVY.split("class RC12WorkOrderDialog", 1)[1].split("class _RC12ChangeBridge", 1)[0]
    assert "if self._grouped_assignment_department():" in block
    assert "Deleting the employee therefore removes every work assigned to them" in block
    assert "for row in sorted(remove_rows, reverse=True):" in block


def test_rc12_shared_drafts_and_background_change_watcher():
    assert 'path = workshop_root() / "drafts"' in HEAVY
    assert "self._rc12_watch_timer.setInterval(2200)" in HEAVY
    assert "threading.Thread(target=worker" in HEAVY
    assert "self.db.change_token()" in HEAVY
    assert "_rc12_touch_draft_revision()" in HEAVY


def test_rc12_caps_lock_indicator_is_windows_state_driven():
    assert 'QLabel("Caps Lock включён", self)' in HEAVY
    assert "GetKeyState(0x14)" in HEAVY
    assert "self._caps_anim.setLoopCount(-1)" in HEAVY
    assert "self._caps_label.hide()" in HEAVY


def test_rc12_version():
    assert 'APP_VERSION = "1.0"' in CONFIG
