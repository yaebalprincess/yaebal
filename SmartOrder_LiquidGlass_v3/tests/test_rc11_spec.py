from pathlib import Path
from decimal import Decimal
import tempfile
import zipfile

from smartorder.db import Database
from smartorder.domain import OrderLine
from smartorder.excel import export_order_xlsx

ROOT = Path(__file__).resolve().parents[1]
HEAVY = (ROOT / "smartorder" / "heavy_ui.py").read_text(encoding="utf-8")


def _sheet_xml(path: Path) -> str:
    with zipfile.ZipFile(path) as zf:
        return zf.read("xl/worksheets/sheet1.xml").decode("utf-8")


def _build_order(department_name: str):
    tmp = tempfile.TemporaryDirectory()
    db = Database(Path(tmp.name) / "work_orders.db")
    db.create_first_admin("admin", "password123")
    admin = db.authenticate("admin", "password123")
    master = db.add_employee(admin, "Мастер", True)
    worker = db.add_employee(admin, "Работник", False)
    dep = db.add_department(admin, department_name)
    w1 = db.add_work_type(admin, "Работа 1", "W-1", "2")
    w2 = db.add_work_type(admin, "Работа 2", "W-2", "3")
    lines = [
        OrderLine(worker, "Работник", w1, "Работа 1", "W-1", Decimal("2"), actual_value=Decimal("2")),
        OrderLine(worker, "Работник", w2, "Работа 2", "W-2", Decimal("3"), actual_value=Decimal("3")),
    ]
    oid = db.save_order(admin, "17-09-2026", "Ночная", master, dep, lines)
    return tmp, db.get_order(oid)


def test_fact_locks_fix_and_fix_locks_fact_in_ui_source():
    assert "if has_actual and col in {5, 6, 7, 8}" in HEAVY
    assert "if has_fixed and not has_actual and col in {9, 10}" in HEAVY
    assert "if col == 9 and item.text().strip()" in HEAVY
    assert "elif col in {5, 6} and item.text().strip()" in HEAVY


def test_delete_selected_has_worker_and_work_choices():
    assert 'menu.addAction("Удалить работу (очистить строку)")' in HEAVY
    assert 'menu.addAction("Удалить работника")' in HEAVY
    # RC12: ordinary departments compact employee slots and preserve work payload;
    # grouped departments delete the employee-owned work block.
    block = HEAVY.rsplit("def _delete_rows(self):", 1)[1]
    assert "self._compact_ordinary_employees(identities)" in block
    assert "self.table.removeRow(row)" in block
    assert "_rebuild_ordinary_after_work_delete" in block
    assert "_rebuild_grouped_after_work_delete" in block


def test_grouped_mode_includes_students_pieceworker_and_separate_worker():
    block = HEAVY.split("def _grouped_assignment_department", 1)[1].split("def _normalize_employee_display", 1)[0]
    assert '"студент" in text' in block
    assert '"сдель" in text' in block
    assert '"отдельн" in text and "работник" in text' in block


def test_grouped_work_target_is_snapshotted_before_totals_are_removed():
    block = HEAVY.split("def _add_works(self):", 2)[-1].split("# Ordinary departments", 1)[0]
    assert block.index("target_snapshot = self._target_employee()") < block.index("dlg = WorkSelectionDialog")
    assert block.index("target_snapshot = self._target_employee()") < block.index("self._remove_totals()")
    assert "actual_row = self._find_employee_row(emp_id, emp_name)" in block


def test_subtotal_is_not_created_for_unassigned_work_group():
    block = HEAVY.split("# Individual subtotal only for specified special departments.", 1)[1].split("pos = self.table.rowCount()", 1)[0]
    assert 'if key[0] is None and not str(key[1] or "").strip()' in block


def test_shift_dropdowns_use_responsive_widths():
    assert "self.shift.setMinimumWidth(470)" in HEAVY
    assert "self.shift.view().setMinimumWidth(540)" in HEAVY
    assert "ResponsiveGrid(filter_cells, min_cell_width=340, max_columns=4)" in HEAVY
    assert "self.order_filter_shift.setMinimumWidth(0)" in HEAVY


def test_pieceworker_print_form_does_not_repeat_employee_name():
    tmp, order = _build_order("Сдельный рабочий")
    try:
        target = Path(tmp.name) / "piece.xlsx"
        export_order_xlsx(target, order)
        xml = _sheet_xml(target)
        assert xml.count("<t>Работник</t>") == 1
        assert "ИТОГО по Работник:" not in xml
    finally:
        tmp.cleanup()


def test_students_print_form_name_once_plus_subtotal_caption():
    tmp, order = _build_order("Студенты ночь")
    try:
        target = Path(tmp.name) / "students.xlsx"
        export_order_xlsx(target, order)
        xml = _sheet_xml(target)
        # One visible employee cell; the name can additionally occur in subtotal text.
        assert xml.count("<t>Работник</t>") == 1
        assert "ИТОГО по Работник:" in xml
    finally:
        tmp.cleanup()


def test_separate_worker_print_form_is_grouped_and_has_subtotal():
    tmp, order = _build_order("Отдельный работник")
    try:
        target = Path(tmp.name) / "separate.xlsx"
        export_order_xlsx(target, order)
        xml = _sheet_xml(target)
        assert xml.count("<t>Работник</t>") == 1
        assert "ИТОГО по Работник:" in xml
    finally:
        tmp.cleanup()
