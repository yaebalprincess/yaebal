"""Explain saved revisions using immutable line snapshots, not today's catalogue."""
from dataclasses import asdict
from html import escape

from .domain import fmt


FIELDS = (("employee_name", "Работник"), ("work_name", "Работа"),
          ("work_code", "Код работы"), ("hours", "Часы"), ("price", "Расценка"),
          ("fixed_boxes", "ФИКС: ящики"), ("fixed_weight", "ФИКС: вес ящика, кг"),
          ("actual_value", "ФАКТ"))
HEADERS = (("order_date", "Дата наряда"), ("shift_type", "Смена"),
           ("master", "Мастер"), ("department", "Подразделение"),
           ("comment", "Комментарий"), ("separate_worker", "Отдельный работник"))


def display(value):
    if value is None or value == "":
        return "—"
    if isinstance(value, (int, float)) or hasattr(value, "quantize"):
        return fmt(value)
    return str(value)


def identity(line):
    return (line.employee_id if line.employee_id is not None else line.employee_name,
            line.work_type_id if line.work_type_id is not None else (line.work_name, line.work_code))


def line_changes(before, after):
    """Match identical duplicates first so reordering never invents edits."""
    previous = list(before)
    remaining = []
    for line in after:
        match = next((index for index, old in enumerate(previous) if asdict(old) == asdict(line)), None)
        if match is None:
            remaining.append(line)
        else:
            previous.pop(match)
    changes = []
    for line in remaining:
        match = next((index for index, old in enumerate(previous) if identity(old) == identity(line)), None)
        if match is None:
            changes.append(("Добавлена работа", line, [(title, None, getattr(line, field)) for field, title in FIELDS
                                                      if getattr(line, field) not in (None, "")]))
        else:
            old = previous.pop(match)
            fields = [(title, getattr(old, field), getattr(line, field)) for field, title in FIELDS
                      if getattr(old, field) != getattr(line, field)]
            changes.append(("Изменена работа", line, fields))
    changes.extend(("Удалена работа", line, []) for line in previous)
    return changes


def revision_html(order, previous):
    e = lambda value: escape(display(value))
    info = order["info"]
    actor = info.get("edited_by") or "Автор не указан"
    stamp = info.get("edit_date") or info.get("registration_date") or "Время не указано"
    parts = [f'<h2>Наряд № {e(info["version"])}</h2><p><b>{e(actor)}</b> · {e(stamp)}</p>']
    if previous is None and info.get("parent_id"):
        parts.append("<p>Предыдущая версия недоступна для сравнения. Ниже — состав этой сохранённой версии.</p>")
    elif previous is None:
        parts.append("<p>Создание наряда</p>")
    old_info = previous["info"] if previous else {}
    parts.append("<table cellpadding='5' width='100%'>")
    for field, title in HEADERS:
        old, new = old_info.get(field), info.get(field)
        if old != new and (previous or new not in (None, "", 0)):
            if field == "separate_worker":
                old, new = ("Да" if old else "Нет"), ("Да" if new else "Нет")
            parts.append(f'<tr><td><b>{e(title)}</b></td><td>{e(old)} → {e(new)}</td></tr>')
    parts.append("</table>")
    changes = line_changes(previous["lines"] if previous else [], order["lines"])
    for action, line, fields in changes:
        parts.append(f'<h3>{action}: {e(line.work_name or "Без работы")}</h3>'
                     f'<p>Работник: <b>{e(line.employee_name)}</b> · Код: {e(line.work_code)}</p>')
        if fields:
            parts.append("<table cellpadding='4' width='100%'>")
            for title, old, new in fields:
                parts.append(f'<tr><td>{e(title)}</td><td>{e(old)} → <b>{e(new)}</b></td></tr>')
            parts.append("</table>")
        elif action == "Удалена работа":
            parts.append(f'<p>Часы: {e(line.hours)} · Расценка: {e(line.price)} · '
                         f'ФИКС: {e(line.fixed_boxes)} × {e(line.fixed_weight)} кг · ФАКТ: {e(line.actual_value)}</p>')
    if not changes and previous:
        parts.append("<p>Состав работ не менялся.</p>")
    return "".join(parts)


def history_html(db, order_id, revision_id=None):
    records = db.order_history(order_id)
    if revision_id is not None:
        records = [record for record in records if record["id"] == revision_id]
    parts = []
    for record in records:
        order = db.get_order(record["id"])
        if order is None:
            continue
        parent = order["info"].get("parent_id")
        previous = db.get_order(parent) if parent else None
        parts.append(revision_html(order, previous))
    return "<hr>".join(parts) or "<p>Версия наряда больше недоступна.</p>"
