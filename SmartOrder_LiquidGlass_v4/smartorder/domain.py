from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Optional

MONEY_STEP = Decimal("0.01")


def dec(value) -> Optional[Decimal]:
    if value is None:
        return None
    text = str(value).strip().replace(",", ".")
    if not text:
        return None
    try:
        return Decimal(text)
    except (InvalidOperation, ValueError):
        return None


def money(value: Decimal | None) -> Decimal | None:
    if value is None:
        return None
    return value.quantize(MONEY_STEP, rounding=ROUND_HALF_UP)


def fmt(value: Decimal | int | float | None, places: int = 4) -> str:
    if value is None:
        return ""
    d = value if isinstance(value, Decimal) else Decimal(str(value))
    text = f"{d:.{places}f}".rstrip("0").rstrip(".")
    return text or "0"


@dataclass
class OrderLine:
    employee_id: int | None = None
    employee_name: str = ""
    work_type_id: int | None = None
    work_name: str = ""
    work_code: str = ""
    price: Decimal | None = None
    hours: Decimal | None = None
    fixed_boxes: Decimal | None = None
    fixed_weight: Decimal | None = None
    actual_value: Decimal | None = None

    @property
    def fixed_total(self) -> Decimal | None:
        if self.fixed_boxes is None or self.fixed_weight is None:
            return None
        return self.fixed_boxes * self.fixed_weight

    @property
    def fixed_payment(self) -> Decimal | None:
        if self.price is None or self.fixed_total is None:
            return None
        return money(self.price * self.fixed_total)

    @property
    def actual_payment(self) -> Decimal | None:
        if self.price is None or self.actual_value is None:
            return None
        return money(self.price * self.actual_value)

    @property
    def total_payment(self) -> Decimal | None:
        """RC20 displayed FACT payment; retain both original components in storage."""
        fixed, actual = self.fixed_payment, self.actual_payment
        if fixed is None and actual is None:
            return None
        return money((fixed or Decimal(0)) + (actual or Decimal(0)))

    @property
    def payment(self) -> Decimal | None:
        """Legacy single-payment compatibility.

        Heavy UI displays FIX and FACT payments independently.  Older tables
        only have one `payment` column, so keep a deterministic fallback.
        """
        return self.fixed_payment if self.fixed_payment is not None else self.actual_payment

    def normalize_modes(self, changed: str | None = None) -> None:
        # RC3 intentionally does not clear the other calculation mode.
        # FIX and FACT are independent columns according to the specification.
        return


def _canon_decimal(value) -> str | None:
    """Stable Decimal representation for edit-change detection."""
    d = dec(value)
    if d is None:
        return None
    if d == 0:
        return "0"
    return format(d.normalize(), "f")


def order_content_signature(
    order_date: str, shift_type: str, master_id, department_id,
    lines: list[OrderLine], comment: str = "",
) -> tuple:
    """Return only business content that should create a new order revision.

    Derived totals are intentionally omitted; they are deterministic from the
    manual fields.  Reopening an order and pressing Save without changing this
    content must therefore NOT create 1.1/1.2/etc.
    """
    line_sig = []
    for line in lines or []:
        has_employee = line.employee_id is not None or bool(str(line.employee_name or "").strip())
        has_work = line.work_type_id is not None or bool(str(line.work_name or "").strip())
        if not has_employee and not has_work:
            continue
        line_sig.append((
            int(line.employee_id) if line.employee_id is not None else None,
            str(line.employee_name or "").strip(),
            int(line.work_type_id) if line.work_type_id is not None else None,
            str(line.work_name or "").strip(),
            str(line.work_code or "").strip(),
            _canon_decimal(line.price),
            _canon_decimal(line.hours),
            _canon_decimal(line.fixed_boxes),
            _canon_decimal(line.fixed_weight),
            _canon_decimal(line.actual_value),
        ))
    return (
        str(order_date or "").strip(),
        str(shift_type or "").strip(),
        int(master_id) if master_id is not None else None,
        int(department_id) if department_id is not None else None,
        str(comment or "").strip(),
        tuple(line_sig),
    )
