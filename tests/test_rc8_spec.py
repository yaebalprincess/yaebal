from pathlib import Path
from decimal import Decimal

from smartorder.domain import OrderLine, order_content_signature

ROOT = Path(__file__).resolve().parents[1]
UI = (ROOT / "smartorder" / "heavy_ui.py").read_text(encoding="utf-8")


def test_work_without_employee_is_not_rejected_by_ui():
    assert "работа не привязана к работнику" not in UI.casefold()


def test_signature_keeps_work_only_row():
    a = order_content_signature(
        "28-08-2026", "Ночная", 1, 1,
        [OrderLine(work_type_id=10, work_name="Работа", price=Decimal("2.5"))], ""
    )
    b = order_content_signature("28-08-2026", "Ночная", 1, 1, [], "")
    assert a != b


def test_signature_keeps_employee_only_row():
    a = order_content_signature(
        "28-08-2026", "Ночная", 1, 1,
        [OrderLine(employee_id=7, employee_name="Работник")], ""
    )
    b = order_content_signature("28-08-2026", "Ночная", 1, 1, [], "")
    assert a != b
