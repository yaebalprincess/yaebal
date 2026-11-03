from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HEAVY = (ROOT / "smartorder" / "heavy_ui.py").read_text(encoding="utf-8")
CONFIG = (ROOT / "smartorder" / "config.py").read_text(encoding="utf-8")


def _block(start: str, end: str | None = None) -> str:
    part = HEAVY.split(start, 1)[1]
    return part.split(end, 1)[0] if end else part


def test_rc14_shift_popup_has_room_for_all_short_items_and_no_native_white_frame():
    block = _block("class RC14SmartComboBox", "def _rc14_force_windows_titlebar")
    assert "count * 36 + 12" in block
    assert "Qt.ScrollBarAlwaysOff" in block
    assert "popup.setAutoFillBackground(True)" in block
    assert "view.viewport().setAutoFillBackground(True)" in block
    assert 'bg = QColor("#2C2C2E" if dark else "#FFFFFF")' in block


def test_rc14_work_delete_compacts_ordinary_and_grouped_layouts():
    block = _block("class RC14WorkOrderDialog", "class RC14MainWindow")
    assert "def _rebuild_ordinary_after_work_delete" in block
    assert "count = max(len(employees), len(works), 1)" in block
    assert "def _rebuild_grouped_after_work_delete" in block
    assert "rows_needed = max(1, len(works))" in block
    assert "self._rebuild_grouped_after_work_delete(removed_work_rows)" in block
    assert "self._rebuild_ordinary_after_work_delete(removed_work_rows)" in block


def test_rc14_fix_fact_locked_cells_are_visibly_red():
    block = _block("class RC14WorkOrderDialog", "class RC14MainWindow")
    assert 'locked = {5, 6, 7, 8}' in block
    assert 'locked = {9, 10}' in block
    assert '#5A2328' in block
    assert '#FFE3E1' in block
    assert 'Недоступно: используется режим ФАКТ' in block
    assert 'Недоступно: используется режим ФИКС' in block


def test_rc14_titlebar_forces_nonclient_repaint_immediately():
    assert "SetWindowPos" in HEAVY
    assert "RedrawWindow" in HEAVY
    block = _block("class RC14MainWindow")
    assert "QApplication.processEvents()" in block
    assert "QTimer.singleShot(35, self._apply_native_titlebars)" in block


def test_rc14_audit_defaults_are_wider():
    block = _block("class RC14MainWindow")
    for token in ("(0,220)", "(1,180)", "(2,230)", "(3,190)"):
        assert token in block


def test_rc14_escape_ignores_auto_repeat_and_is_debounced():
    block = _block("class RC14MainWindow")
    assert "event.isAutoRepeat()" in block
    assert 'getattr(self, "_rc14_last_escape", 0.0)' in block
    assert "< 0.30" in block


def test_rc14_version():
    assert 'APP_VERSION = "1.0"' in CONFIG
