from __future__ import annotations
from .i18n import source_text

import json
import os
import threading
import time
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from PyQt5.QtCore import QDate, QObject, Qt, QTimer, pyqtSignal, QPropertyAnimation, QEasingCurve, QRect
from PyQt5.QtGui import QFont, QMovie
from PyQt5.QtWidgets import (
    QAbstractItemView, QApplication, QCheckBox, QComboBox, QDateEdit, QDialog,
    QDialogButtonBox, QFileDialog, QFormLayout, QGroupBox, QHBoxLayout, QHeaderView,
    QLabel, QLineEdit, QListWidget, QListWidgetItem, QMainWindow, QMessageBox, QFrame,
    QPushButton, QRadioButton, QSlider, QTabWidget, QTableWidget, QTableWidgetItem,
    QTextEdit, QVBoxLayout, QWidget,
)

from .config import APP_VERSION, SettingsStore, UiSettings, database_path, local_drafts_dir, shared_dirs, resource_path, network_root
from .db import Database, DatabaseError, StaleOrderError
from .domain import OrderLine, dec, fmt
from .excel import export_order_xlsx, read_simple_xlsx
from .security import ALL_PERMISSIONS, DEFAULT_ROLE_PERMISSIONS, PERMISSION_LABELS, Permission, SessionUser, ROLES
from .styles import DARK_QSS, LIGHT_QSS

ORDER_HEADERS = [
    "ФИО работника", "Часы работы", "Работы", "Код работы", "Стоимость",
    "ФИКС Кол-во", "ФИКС Вес", "ФИКС Итоговый вес", "ФАКТ часы/кг/шт", "Оплата",
]


def info(parent, title: str, text: str):
    QMessageBox.information(parent, title, text)


def warn(parent, title: str, text: str):
    QMessageBox.warning(parent, title, text)


def error(parent, title: str, exc):
    QMessageBox.critical(parent, title, str(exc))


def make_item(text="", data=None, editable=False) -> QTableWidgetItem:
    item = QTableWidgetItem(str(text if text is not None else ""))
    if data is not None:
        item.setData(Qt.UserRole, data)
    if not editable:
        item.setFlags(item.flags() & ~Qt.ItemIsEditable)
    return item

class GifBackgroundWidget(QWidget):
    """GIF cached in RAM; overlay widgets stay transparent."""
    def __init__(self, candidates=None, parent=None):
        super().__init__(parent)
        self._bg = QLabel(self)
        self._bg.setScaledContents(True)
        self._movie = None
        for name in (candidates or ["loading2.gif", "login_background.gif"]):
            try:
                path = resource_path(name)
                if not path.exists():
                    continue
                movie = QMovie(str(path))
                movie.setCacheMode(QMovie.CacheAll)
                if movie.isValid():
                    self._movie = movie
                    self._bg.setMovie(movie)
                    movie.start()
                    break
            except Exception:
                continue
        self._bg.lower()

    def resizeEvent(self, event):
        self._bg.setGeometry(self.rect())
        super().resizeEvent(event)


class BounceTopButton(QPushButton):
    def __init__(self, target, parent=None):
        super().__init__("↑ Наверх", parent)
        self.target = target
        self.setMaximumWidth(120)
        self.clicked.connect(self._go)
        self._anim = None

    def _go(self):
        try:
            self.target.scrollToTop()
        except Exception:
            try:
                self.target.verticalScrollBar().setValue(0)
            except Exception:
                pass
        g = self.geometry()
        anim = QPropertyAnimation(self, b"geometry", self)
        anim.setDuration(430)
        anim.setEasingCurve(QEasingCurve.OutBack)
        anim.setStartValue(g)
        anim.setKeyValueAt(0.28, QRect(g.x()+5, g.y()+5, max(30,g.width()-10), max(20,g.height()-8)))
        anim.setKeyValueAt(0.62, QRect(g.x()-2, g.y()-9, g.width()+4, g.height()+3))
        anim.setEndValue(g)
        self._anim = anim
        anim.start()


class FirstAdminDialog(QDialog):
    def __init__(self, db: Database, parent=None):
        super().__init__(parent)
        from .appearance import restore_startup_surface
        restore_startup_surface(self)
        self.db = db
        self.setWindowTitle("SmartOrder — первый запуск")
        form = QFormLayout(self)
        note = QLabel("Создайте первую учётную запись администратора. Пароль не хранится в открытом виде.")
        note.setWordWrap(True)
        form.addRow(note)
        self.username = QLineEdit("Админ")
        self.password = QLineEdit()
        self.password.setEchoMode(QLineEdit.Password)
        self.password2 = QLineEdit()
        self.password2.setEchoMode(QLineEdit.Password)
        form.addRow("Логин:", self.username)
        form.addRow("Пароль (≥ 8):", self.password)
        form.addRow("Повтор:", self.password2)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._create)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def _create(self):
        if self.password.text() != self.password2.text():
            warn(self, "Пароль", "Пароли не совпадают")
            return
        try:
            self.db.create_first_admin(self.username.text(), self.password.text())
            self.accept()
        except Exception as exc:
            error(self, "Не удалось создать администратора", exc)


class LoginDialog(QDialog):
    def __init__(self, db: Database, parent=None):
        super().__init__(parent)
        self.db = db
        self.user: SessionUser | None = None
        self.setWindowTitle("SmartOrder — вход")
        self.setMinimumSize(520, 560)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        bg = GifBackgroundWidget(["login_background.gif", "loading2.gif"], self)
        outer.addWidget(bg)
        layout = QVBoxLayout(bg)
        layout.setContentsMargins(54, 44, 54, 44)
        layout.addStretch()

        card = QFrame(bg)
        card.setObjectName("aboutGlass")
        card.setStyleSheet("QFrame#aboutGlass{background:rgba(8,18,32,90);border:1px solid rgba(255,255,255,120);border-radius:24px;} QFrame#aboutGlass QLabel{background:transparent;color:white;} QFrame#aboutGlass QLineEdit{background:rgba(255,255,255,215);color:#111827;}")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(34, 30, 34, 30)
        title = QLabel("SmartOrder")
        title.setAlignment(Qt.AlignCenter)
        font = title.font(); font.setPointSize(25); font.setBold(True); title.setFont(font)
        card_layout.addWidget(title)
        subtitle = QLabel("Вход в систему")
        subtitle.setAlignment(Qt.AlignCenter)
        card_layout.addWidget(subtitle)
        form = QFormLayout()
        self.username = QLineEdit()
        self.password = QLineEdit(); self.password.setEchoMode(QLineEdit.Password)
        self.password.returnPressed.connect(self._login)
        form.addRow("Логин:", self.username)
        form.addRow("Пароль:", self.password)
        card_layout.addLayout(form)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("Войти")
        buttons.accepted.connect(self._login)
        buttons.rejected.connect(self.reject)
        card_layout.addWidget(buttons)
        layout.addWidget(card)
        layout.addStretch()

    def _login(self):
        try:
            user = self.db.authenticate(self.username.text(), self.password.text())
        except Exception as exc:
            error(self, "Ошибка подключения к базе", exc)
            return
        if not user:
            warn(self, "Вход", "Неверный логин/пароль или учётная запись отключена")
            return
        self.user = user
        self.accept()


class MultiSelectDialog(QDialog):
    def __init__(self, title: str, rows: list[tuple], formatter, parent=None):
        super().__init__(parent)
        self.rows = rows
        self.formatter = formatter
        self.setWindowTitle(title)
        self.resize(620, 650)
        layout = QVBoxLayout(self)
        self.search = QLineEdit(); self.search.setPlaceholderText("Поиск…")
        self.search.textChanged.connect(self._filter)
        layout.addWidget(self.search)
        self.list = QListWidget(); self.list.setAlternatingRowColors(True)
        layout.addWidget(self.list, 1)
        buttons_row = QHBoxLayout()
        select_all = QPushButton("Выбрать видимое")
        clear = QPushButton("Снять выбор")
        select_all.clicked.connect(lambda: self._set_visible(Qt.Checked))
        clear.clicked.connect(lambda: self._set_all(Qt.Unchecked))
        buttons_row.addWidget(select_all); buttons_row.addWidget(clear); buttons_row.addStretch()
        layout.addLayout(buttons_row)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("Завершить выбор")
        buttons.accepted.connect(self.accept); buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self._populate()

    def _populate(self):
        self.list.clear()
        for row in self.rows:
            item = QListWidgetItem(self.formatter(row))
            item.setData(Qt.UserRole, row)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Unchecked)
            self.list.addItem(item)

    def _filter(self, text: str):
        needle = text.strip().casefold().replace("ё", "е")
        for i in range(self.list.count()):
            item = self.list.item(i)
            hay = item.text().casefold().replace("ё", "е")
            item.setHidden(bool(needle and needle not in hay))

    def _set_visible(self, state):
        for i in range(self.list.count()):
            item = self.list.item(i)
            if not item.isHidden():
                item.setCheckState(state)

    def _set_all(self, state):
        for i in range(self.list.count()):
            self.list.item(i).setCheckState(state)

    def selected(self) -> list[tuple]:
        result = []
        for i in range(self.list.count()):
            item = self.list.item(i)
            if item.checkState() == Qt.Checked:
                result.append(item.data(Qt.UserRole))
        return result


class UserDialog(QDialog):
    def __init__(self, username="", role="", require_password=True, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Пользователь")
        form = QFormLayout(self)
        self.username = QLineEdit(username)
        self.password = QLineEdit(); self.password.setEchoMode(QLineEdit.Password)
        if not require_password:
            self.password.setPlaceholderText("Оставьте пустым, чтобы не менять")
        self.role_list = QListWidget(); self.role_list.setSelectionMode(QAbstractItemView.NoSelection); self.role_list.setMaximumHeight(150)
        selected = set(str(role or "").replace(",", ";").split(";"))
        for name in ROLES:
            item = QListWidgetItem(name); item.setData(Qt.UserRole, name)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked if name in selected else Qt.Unchecked)
            self.role_list.addItem(item)
        form.addRow("Логин:", self.username)
        form.addRow("Пароль:", self.password)
        form.addRow("Роли:", self.role_list)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept); buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def selected_roles(self):
        return ";".join(str(self.role_list.item(i).data(Qt.UserRole)) for i in range(self.role_list.count()) if self.role_list.item(i).checkState() == Qt.Checked)


class WorkOrderDialog(QDialog):
    def __init__(self, db: Database, user: SessionUser, order: dict | None = None, view_only=False, lock_token=None, parent=None):
        super().__init__(parent)
        self.db, self.user, self.order = db, user, order
        self.order_id = int(order["info"]["id"]) if order else None
        self.view_only = view_only
        self.lock_token = lock_token
        self._cell_busy = False
        self._saved_successfully = False
        self.setWindowTitle("Просмотр наряда" if view_only else ("Редактирование наряда" if order else "Формирование наряда"))
        self.resize(1500, 840)
        self._build()
        if order:
            self._load_order(order)
        else:
            self._insert_blank_if_needed()
        self._refresh_totals()
        if view_only:
            self._set_view_only()
        self._draft_timer = QTimer(self)
        if not view_only:
            self._draft_timer.setInterval(30000)
            self._draft_timer.timeout.connect(self._save_draft)
            self._draft_timer.start()
        self._lock_timer = QTimer(self)
        if self.order_id and self.lock_token:
            self._lock_timer.setInterval(20000)
            self._lock_timer.timeout.connect(self._heartbeat)
            self._lock_timer.start()

    def _build(self):
        layout = QVBoxLayout(self)
        info_group = QGroupBox("Информация о наряде")
        form = QFormLayout(info_group)
        self.order_date = QDateEdit(); self.order_date.setCalendarPopup(True); self.order_date.setDisplayFormat("dd-MM-yyyy"); self.order_date.setDate(QDate.currentDate())
        self.shift = QComboBox(); self.shift.addItems(["Ночная", "Дневная"])
        self.master = QComboBox()
        for row in self.db.get_employees(True): self.master.addItem(str(row[1]), int(row[0]))
        self.department = QComboBox()
        for row in self.db.get_departments(): self.department.addItem(str(row[1]), int(row[0]))
        self.comment = QLineEdit(); self.comment.setPlaceholderText("Необязательный комментарий")
        form.addRow("Дата наряда:", self.order_date); form.addRow("Тип смены:", self.shift)
        form.addRow("Мастер:", self.master); form.addRow("Подразделение:", self.department); form.addRow("Комментарий:", self.comment)
        layout.addWidget(info_group)

        buttons = QHBoxLayout()
        self.add_employee_btn = QPushButton("Добавить сотрудников")
        self.add_work_btn = QPushButton("Добавить работы")
        self.delete_row_btn = QPushButton("Удалить строки"); self.delete_row_btn.setObjectName("danger")
        self.add_employee_btn.clicked.connect(self._add_employees)
        self.add_work_btn.clicked.connect(self._add_works)
        self.delete_row_btn.clicked.connect(self._delete_rows)
        buttons.addWidget(self.add_employee_btn); buttons.addWidget(self.add_work_btn); buttons.addWidget(self.delete_row_btn); buttons.addStretch()
        layout.addLayout(buttons)

        self.table = QTableWidget(0, len(ORDER_HEADERS)); self.table.setHorizontalHeaderLabels(ORDER_HEADERS)
        self.table.setAlternatingRowColors(True); self.table.setSelectionBehavior(QAbstractItemView.SelectRows); self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        widths = [250, 105, 300, 130, 125, 125, 125, 150, 150, 125]
        for i, width in enumerate(widths): self.table.setColumnWidth(i, width)
        self.table.itemChanged.connect(self._on_cell_changed)
        layout.addWidget(self.table, 1)
        top_row = QHBoxLayout(); top_row.addStretch(); top_row.addWidget(BounceTopButton(self.table, self)); layout.addLayout(top_row)
        box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        box.button(QDialogButtonBox.Ok).setText("Завершить формирование")
        box.accepted.connect(self._accept); box.rejected.connect(self.reject)
        self.button_box = box
        layout.addWidget(box)

    def _is_total(self, row: int) -> bool:
        item = self.table.item(row, 0)
        return bool(item and item.text().strip().upper().startswith("ИТОГО"))

    def _remove_totals(self):
        self.table.blockSignals(True)
        try:
            for row in range(self.table.rowCount() - 1, -1, -1):
                if self._is_total(row): self.table.removeRow(row)
        finally:
            self.table.blockSignals(False)

    def _insert_blank_if_needed(self):
        if self.table.rowCount() == 0:
            self.table.insertRow(0); self._ensure_row(0)

    def _ensure_row(self, row: int):
        while self.table.rowCount() <= row: self.table.insertRow(self.table.rowCount())
        for col in range(self.table.columnCount()):
            if self.table.item(row, col) is None:
                self.table.setItem(row, col, make_item("", editable=col in {1, 5, 6, 8}))
        self._apply_flags(row)

    def _apply_flags(self, row: int):
        readonly = {0, 2, 3, 4, 7, 9}
        for col in range(self.table.columnCount()):
            item = self.table.item(row, col)
            if item is None: continue
            flags = item.flags() | Qt.ItemIsEnabled | Qt.ItemIsSelectable
            if self._is_total(row) or col in readonly or self.view_only: flags &= ~Qt.ItemIsEditable
            else: flags |= Qt.ItemIsEditable
            item.setFlags(flags)

    def _line_from_row(self, row: int) -> OrderLine:
        def text(c):
            item = self.table.item(row, c); return item.text().strip() if item else ""
        def role(c):
            item = self.table.item(row, c); return item.data(Qt.UserRole) if item else None
        return OrderLine(
            employee_id=role(0), employee_name=text(0), work_type_id=role(2), work_name=text(2),
            work_code=text(3), price=dec(text(4)), hours=dec(text(1)), fixed_boxes=dec(text(5)),
            fixed_weight=dec(text(6)), actual_value=dec(text(8)),
        )

    def _write_calculated(self, row: int, line: OrderLine):
        self.table.blockSignals(True)
        try:
            self.table.item(row, 7).setText(fmt(line.fixed_total))
            self.table.item(row, 9).setText(fmt(line.payment, 2))
        finally:
            self.table.blockSignals(False)

    def _on_cell_changed(self, item: QTableWidgetItem):
        if self._cell_busy or self._is_total(item.row()) or self.view_only: return
        self._cell_busy = True
        try:
            row, col = item.row(), item.column()
            line = self._line_from_row(row)
            if col == 8 and line.actual_value is not None:
                self.table.blockSignals(True)
                self.table.item(row, 5).setText(""); self.table.item(row, 6).setText("")
                self.table.blockSignals(False)
                line.fixed_boxes = line.fixed_weight = None
            elif col in {5, 6} and (line.fixed_boxes is not None or line.fixed_weight is not None):
                self.table.blockSignals(True); self.table.item(row, 8).setText(""); self.table.blockSignals(False)
                line.actual_value = None
            self._write_calculated(row, line)
            self._refresh_totals()
        finally:
            self._cell_busy = False

    def _refresh_totals(self):
        self._remove_totals()
        # Remove completely empty rows except keep one.
        for row in range(self.table.rowCount() - 1, -1, -1):
            if all(not (self.table.item(row, c) and (self.table.item(row, c).text().strip() or self.table.item(row, c).data(Qt.UserRole) is not None)) for c in range(self.table.columnCount())):
                if self.table.rowCount() > 1: self.table.removeRow(row)
        self._insert_blank_if_needed()
        totals = {c: Decimal("0") for c in (5, 6, 7, 8, 9)}
        has = {c: False for c in totals}
        for row in range(self.table.rowCount()):
            line = self._line_from_row(row)
            if not line.work_name and line.work_type_id is None: continue
            self._write_calculated(row, line)
            for col, value in ((5, line.fixed_boxes), (6, line.fixed_weight), (7, line.fixed_total), (8, line.actual_value), (9, line.payment)):
                if value is not None: totals[col] += value; has[col] = True
        row = self.table.rowCount(); self.table.insertRow(row)
        for c in range(self.table.columnCount()): self.table.setItem(row, c, make_item(""))
        self.table.item(row, 0).setText("ИТОГО:")
        f = self.table.item(row, 0).font(); f.setBold(True)
        for c in range(self.table.columnCount()): self.table.item(row, c).setFont(f)
        for c in totals:
            if has[c]: self.table.item(row, c).setText(fmt(totals[c], 2 if c == 9 else 4))
        self._apply_flags(row)

    def _add_employees(self):
        rows = [(int(r[0]), str(r[1])) for r in self.db.get_employees(False)]
        dlg = MultiSelectDialog("Выбор сотрудников", rows, lambda r: r[1], self)
        if dlg.exec_() != QDialog.Accepted: return
        selected = dlg.selected()
        if not selected: return
        self._remove_totals()
        existing = {self.table.item(r, 0).data(Qt.UserRole) for r in range(self.table.rowCount()) if self.table.item(r, 0)}
        self.table.blockSignals(True)
        try:
            # Reuse one blank row first.
            for employee_id, name in selected:
                if employee_id in existing: continue
                reuse = next((r for r in range(self.table.rowCount()) if not (self.table.item(r, 0).text().strip() if self.table.item(r,0) else "") and not (self.table.item(r,2).text().strip() if self.table.item(r,2) else "")), None)
                row = reuse if reuse is not None else self.table.rowCount()
                self._ensure_row(row)
                self.table.setItem(row, 0, make_item(name, employee_id))
                self._apply_flags(row); existing.add(employee_id)
        finally:
            self.table.blockSignals(False)
        self._refresh_totals()

    def _selected_employee_identities(self) -> list[tuple[int | None, str]]:
        rows = sorted({idx.row() for idx in self.table.selectionModel().selectedRows() if not self._is_total(idx.row())})
        identities = []
        for row in rows:
            item = self.table.item(row, 0)
            if item and (item.data(Qt.UserRole) is not None or item.text().strip()):
                identities.append((item.data(Qt.UserRole), item.text().strip()))
        if not identities and self.table.currentRow() >= 0 and not self._is_total(self.table.currentRow()):
            item = self.table.item(self.table.currentRow(), 0)
            if item and (item.data(Qt.UserRole) is not None or item.text().strip()): identities.append((item.data(Qt.UserRole), item.text().strip()))
        # Stable unique.
        return list(dict.fromkeys(identities))

    def _add_works(self):
        employees = self._selected_employee_identities()
        if not employees:
            warn(self, "Работы", "Сначала выделите строку сотрудника")
            return
        works = [(int(r[0]), str(r[1]), str(r[2]), float(r[3])) for r in self.db.get_work_types()]
        dlg = MultiSelectDialog("Выбор работ", works, lambda r: f"{r[1]}   |   {r[2]}   |   {fmt(r[3])} руб.", self)
        if dlg.exec_() != QDialog.Accepted: return
        selected = dlg.selected()
        if not selected: return
        self._remove_totals()
        self.table.blockSignals(True)
        try:
            for employee_id, employee_name in employees:
                emp_rows = [r for r in range(self.table.rowCount()) if self.table.item(r,0) and self.table.item(r,0).data(Qt.UserRole) == employee_id]
                existing_work_ids = {self.table.item(r,2).data(Qt.UserRole) for r in emp_rows if self.table.item(r,2)}
                empty_row = next((r for r in emp_rows if not (self.table.item(r,2).text().strip() if self.table.item(r,2) else "")), None)
                for work_id, work_name, code, price in selected:
                    if work_id in existing_work_ids: continue
                    row = empty_row if empty_row is not None else self.table.rowCount()
                    empty_row = None
                    self._ensure_row(row)
                    self.table.setItem(row, 0, make_item(employee_name, employee_id))
                    self.table.setItem(row, 2, make_item(work_name, work_id))
                    self.table.setItem(row, 3, make_item(code))
                    self.table.setItem(row, 4, make_item(fmt(price)))
                    self._apply_flags(row); existing_work_ids.add(work_id)
        finally:
            self.table.blockSignals(False)
        self._refresh_totals()

    def _delete_rows(self):
        rows = sorted({idx.row() for idx in self.table.selectionModel().selectedRows() if not self._is_total(idx.row())}, reverse=True)
        if not rows: return
        self.table.blockSignals(True)
        try:
            for row in rows: self.table.removeRow(row)
        finally:
            self.table.blockSignals(False)
        self._refresh_totals()

    def _load_order(self, order: dict):
        info_data = order["info"]
        self.order_date.setDate(QDate.fromString(str(info_data.get("order_date", "")), "dd-MM-yyyy"))
        self.shift.setCurrentText(str(info_data.get("shift_type", "")))
        self._set_combo_data(self.master, info_data.get("master_id")); self._set_combo_data(self.department, info_data.get("department_id"))
        self.comment.setText(str(info_data.get("comment", "")))
        self.table.blockSignals(True)
        try:
            self.table.setRowCount(0)
            for line in order["lines"]:
                row = self.table.rowCount(); self.table.insertRow(row); self._ensure_row(row)
                self.table.setItem(row, 0, make_item(line.employee_name, line.employee_id))
                self.table.item(row, 1).setText(fmt(line.hours))
                self.table.setItem(row, 2, make_item(line.work_name, line.work_type_id))
                self.table.setItem(row, 3, make_item(line.work_code)); self.table.setItem(row, 4, make_item(fmt(line.price)))
                self.table.item(row, 5).setText(fmt(line.fixed_boxes)); self.table.item(row, 6).setText(fmt(line.fixed_weight))
                self.table.item(row, 8).setText(fmt(line.actual_value)); self._write_calculated(row, line); self._apply_flags(row)
        finally:
            self.table.blockSignals(False)

    @staticmethod
    def _set_combo_data(combo: QComboBox, value):
        idx = combo.findData(value)
        if idx >= 0: combo.setCurrentIndex(idx)

    def get_data(self) -> dict:
        lines = []
        for row in range(self.table.rowCount()):
            if self._is_total(row): continue
            line = self._line_from_row(row)
            if line.work_type_id is not None or line.work_name:
                lines.append(line)
        return {
            "order_date": self.order_date.date().toString("dd-MM-yyyy"),
            "shift_type": source_text(self.shift),
            "master_id": self.master.currentData(),
            "department_id": self.department.currentData(),
            "comment": self.comment.text().strip(),
            "lines": lines,
        }

    def _validate(self) -> str | None:
        data = self.get_data()
        if data["master_id"] is None: return "Не выбран мастер"
        if data["department_id"] is None: return "Не выбрано подразделение"
        if not data["lines"]: return "В наряде нет работ"
        for idx, line in enumerate(data["lines"], 1):
            if line.fixed_boxes is not None and line.fixed_boxes < 0: return f"Строка {idx}: отрицательное количество коробок"
            if line.fixed_weight is not None and line.fixed_weight < 0: return f"Строка {idx}: отрицательный вес"
            if line.actual_value is not None and line.actual_value < 0: return f"Строка {idx}: отрицательный ФАКТ"
            if line.fixed_total is not None and line.actual_value is not None: return f"Строка {idx}: одновременно ФИКС и ФАКТ"
        return None

    def _accept(self):
        if self.view_only: self.accept(); return
        problem = self._validate()
        if problem: warn(self, "Проверьте наряд", problem); return
        self._saved_successfully = True
        self._delete_draft()
        self.accept()

    def _set_view_only(self):
        for widget in (self.order_date, self.shift, self.master, self.department, self.comment): widget.setEnabled(False)
        for btn in (self.add_employee_btn, self.add_work_btn, self.delete_row_btn): btn.hide()
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        ok = self.button_box.button(QDialogButtonBox.Ok)
        if ok: ok.hide()
        self.button_box.button(QDialogButtonBox.Cancel).setText("Закрыть")

    def _draft_path(self) -> Path:
        key = f"order_{self.order_id}" if self.order_id else "new_order"
        return local_drafts_dir() / f"{key}_{self.user.id}.json"

    def _save_draft(self):
        try:
            data = self.get_data()
            if not data["lines"]: return
            payload = {k: v for k, v in data.items() if k != "lines"}
            payload["lines"] = [line.__dict__ | {"price": fmt(line.price), "hours": fmt(line.hours), "fixed_boxes": fmt(line.fixed_boxes), "fixed_weight": fmt(line.fixed_weight), "actual_value": fmt(line.actual_value)} for line in data["lines"]]
            payload["updated_at"] = datetime.now().isoformat(timespec="seconds")
            self._draft_path().write_text(json.dumps(payload, ensure_ascii=False, default=str, indent=2), encoding="utf-8")
        except Exception:
            pass

    def _delete_draft(self):
        try: self._draft_path().unlink(missing_ok=True)
        except Exception: pass

    def _heartbeat(self):
        try:
            if not self.db.heartbeat_edit_lock(self.order_id, self.lock_token):
                self._lock_timer.stop(); warn(self, "Редактирование", "Блокировка редактирования потеряна. Сохранение может быть отклонено.")
        except Exception:
            pass

    def stop_lock(self):
        self._lock_timer.stop()
        if self.order_id and self.lock_token:
            self.db.release_edit_lock(self.order_id, self.lock_token)
            self.lock_token = None


class PingBridge(QObject):
    done = pyqtSignal(bool, float, str)


class MainWindow(QMainWindow):
    def __init__(self, db: Database, user: SessionUser):
        super().__init__()
        self.db, self.user = db, user
        self.settings_store = SettingsStore(user.id, user.username); self.ui_settings = self.settings_store.load()
        if getattr(self, "_initial_ui_settings", None) is not None:
            from copy import deepcopy
            self.ui_settings = deepcopy(self._initial_ui_settings)
        from .i18n import set_language
        set_language(self.ui_settings.language)
        if self.ui_settings.auto_theme:
            from .config import scheduled_theme
            self.ui_settings.theme = scheduled_theme()
        self._auto_backup_last = 0.0; self._auto_backup_running = False
        self.setWindowTitle(f"SmartOrder {APP_VERSION} — {user.username} ({user.role})")
        self.resize(1500, 900)
        self._ping_bridge = PingBridge(self); self._ping_bridge.done.connect(self._ping_done)
        self._build()
        self._apply_theme(); self._apply_zoom(self.ui_settings.zoom)
        QTimer.singleShot(80, self.refresh_orders)
        QTimer.singleShot(250, self._ping_async)
        self._db_ping_timer = QTimer(self)
        self._db_ping_timer.setInterval(30000)
        self._db_ping_timer.timeout.connect(self._ping_async)
        self._db_ping_timer.start()

    def can(self, permission: str) -> bool: return self.user.can(permission)

    def _build(self):
        root = QWidget(); outer = QVBoxLayout(root); outer.setContentsMargins(12, 10, 12, 10)
        top = QHBoxLayout()
        top.addWidget(QLabel("Масштаб:")); self.zoom = QSlider(Qt.Horizontal); self.zoom.setRange(85, 140); self.zoom.setValue(self.ui_settings.zoom); self.zoom.setMaximumWidth(180)
        self.zoom_label = QLabel(f"{self.ui_settings.zoom}%"); self.zoom.valueChanged.connect(self._apply_zoom)
        top.addWidget(self.zoom); top.addWidget(self.zoom_label); top.addStretch()
        sync = QPushButton("Синхронизация"); sync.clicked.connect(self._sync_current_tab); top.addWidget(sync)
        self.db_state = QLabel("БД: проверка…"); self.db_state.setObjectName("muted"); top.addWidget(self.db_state)
        self.theme = QCheckBox("Тёмная тема"); self.theme.setChecked(self.ui_settings.theme == "dark"); self.theme.toggled.connect(self._theme_toggled); top.addWidget(self.theme)
        outer.addLayout(top)
        self.tabs = QTabWidget(); self.tabs.currentChanged.connect(self._tab_changed); outer.addWidget(self.tabs, 1)
        self._build_orders_tab()
        if self.can(Permission.CATALOG_VIEW): self._build_catalog_tab()
        if self.can(Permission.EMPLOYEES_VIEW): self._build_employees_tab()
        if self.can(Permission.ADMIN_VIEW): self._build_admin_tab()
        self._build_about_tab()
        self.setCentralWidget(root)

    # ----- orders -----
    def _build_orders_tab(self):
        tab = QWidget(); layout = QVBoxLayout(tab)
        filters = QHBoxLayout()
        self.all_dates = QCheckBox("Все даты"); self.all_dates.setChecked(False); self.all_dates.toggled.connect(self.refresh_orders)
        self.order_filter_date = QDateEdit(); self.order_filter_date.setCalendarPopup(True); self.order_filter_date.setDate(QDate.currentDate()); self.order_filter_date.setDisplayFormat("dd-MM-yyyy"); self.order_filter_date.dateChanged.connect(self.refresh_orders)
        self.order_filter_master = QComboBox(); self.order_filter_master.addItem("Все мастера", None)
        for r in self.db.get_employees(True): self.order_filter_master.addItem(str(r[1]), int(r[0]))
        self.order_filter_master.currentIndexChanged.connect(self.refresh_orders)
        self.order_filter_dep = QComboBox(); self.order_filter_dep.addItem("Все подразделения", None)
        for r in self.db.get_departments(): self.order_filter_dep.addItem(str(r[1]), int(r[0]))
        self.order_filter_dep.currentIndexChanged.connect(self.refresh_orders)
        self.order_search = QLineEdit(); self.order_search.setPlaceholderText("Поиск по №, мастеру, подразделению…"); self.order_search.returnPressed.connect(self.refresh_orders)
        for w in (QLabel("Дата:"), self.order_filter_date, self.all_dates, QLabel("Мастер:"), self.order_filter_master, QLabel("Подразделение:"), self.order_filter_dep, self.order_search): filters.addWidget(w)
        layout.addLayout(filters)
        buttons = QHBoxLayout()
        self.create_order_btn = QPushButton("Создать наряд"); self.create_order_btn.setObjectName("primary"); self.create_order_btn.clicked.connect(self.create_order); self.create_order_btn.setVisible(self.can(Permission.ORDERS_CREATE))
        self.edit_order_btn = QPushButton("Редактировать"); self.edit_order_btn.clicked.connect(self.edit_order); self.edit_order_btn.setVisible(self.can(Permission.ORDERS_EDIT))
        self.view_order_btn = QPushButton("Просмотр"); self.view_order_btn.clicked.connect(self.view_order)
        self.export_order_btn = QPushButton("Выгрузить в Excel"); self.export_order_btn.clicked.connect(self.export_order); self.export_order_btn.setVisible(self.can(Permission.ORDERS_EXPORT))
        refresh = QPushButton("Обновить"); refresh.clicked.connect(self.refresh_orders)
        for b in (self.create_order_btn, self.edit_order_btn, self.view_order_btn, self.export_order_btn, refresh): buttons.addWidget(b)
        buttons.addStretch(); layout.addLayout(buttons)
        self.orders_table = QTableWidget(0, 7); self.orders_table.setHorizontalHeaderLabels(["№", "Дата наряда", "Смена", "Мастер", "Подразделение", "Дата регистрации", "Редактор"])
        self.orders_table.setSelectionBehavior(QAbstractItemView.SelectRows); self.orders_table.setSelectionMode(QAbstractItemView.SingleSelection); self.orders_table.setAlternatingRowColors(True)
        self.orders_table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        for i,w in enumerate([90,120,100,250,240,170,150]): self.orders_table.setColumnWidth(i,w)
        self.orders_table.itemDoubleClicked.connect(lambda _: self.view_order())
        layout.addWidget(self.orders_table, 1); self.tabs.addTab(tab, "Наряд")

    def refresh_orders(self):
        try:
            date = None if self.all_dates.isChecked() else self.order_filter_date.date().toString("dd-MM-yyyy")
            rows = self.db.list_orders(date=date, master_id=self.order_filter_master.currentData(), department_id=self.order_filter_dep.currentData(), text=self.order_search.text())
            self.orders_table.setUpdatesEnabled(False); self.orders_table.setRowCount(len(rows))
            for r, row in enumerate(rows):
                values = [row[1], row[2], row[3], row[4], row[5], row[6], row[8] or ""]
                for c, value in enumerate(values): self.orders_table.setItem(r, c, make_item(value))
                self.orders_table.item(r, 0).setData(Qt.UserRole, int(row[0]))
            self.orders_table.setUpdatesEnabled(True)
        except Exception as exc:
            self.orders_table.setUpdatesEnabled(True); error(self, "Не удалось загрузить наряды", exc)

    def _selected_order_id(self):
        row = self.orders_table.currentRow()
        if row < 0: return None
        item = self.orders_table.item(row, 0); return item.data(Qt.UserRole) if item else None

    def create_order(self):
        if not self.can(Permission.ORDERS_CREATE): return
        dlg = WorkOrderDialog(self.db, self.user, parent=self)
        if dlg.exec_() == QDialog.Accepted:
            data = dlg.get_data()
            try:
                oid = self.db.save_order(self.user, data["order_date"], data["shift_type"], data["master_id"], data["department_id"], data["lines"], data["comment"], separate_worker=bool(data.get("separate_worker",False)))
                info(self, "Наряд", f"Наряд № {self.db.get_order(oid)['info']['version']} создан")
                self.refresh_orders(); self._auto_backup("order_created")
            except Exception as exc: error(self, "Не удалось сохранить наряд", exc)

    def edit_order(self):
        if not self.can(Permission.ORDERS_EDIT): return
        order_id = self._selected_order_id()
        if not order_id: return
        if not self.db.is_latest_order(order_id):
            warn(self, "Редактирование", "Редактировать можно только последнюю версию наряда")
            return
        token = None
        try:
            token, owner = self.db.acquire_edit_lock(order_id, self.user)
            if not token:
                warn(self, "Наряд уже редактируется", f"Пользователь: {owner.get('username')}\nКомпьютер: {owner.get('computer')}")
                return
            order = self.db.get_order(order_id)
            dlg = WorkOrderDialog(self.db, self.user, order=order, lock_token=token, parent=self)
            try:
                if dlg.exec_() == QDialog.Accepted:
                    data = dlg.get_data()
                    new_id = self.db.save_order(self.user, data["order_date"], data["shift_type"], data["master_id"], data["department_id"], data["lines"], data["comment"], parent_id=order_id, separate_worker=bool(data.get("separate_worker",False)))
                    info(self, "Наряд", f"Создана новая версия № {self.db.get_order(new_id)['info']['version']}")
                    self.refresh_orders(); self._auto_backup("order_edited")
            finally:
                dlg.stop_lock()
        except StaleOrderError as exc: warn(self, "Редактирование", str(exc))
        except Exception as exc:
            if token: self.db.release_edit_lock(order_id, token)
            error(self, "Редактирование", exc)

    def view_order(self):
        order_id = self._selected_order_id()
        if not order_id: return
        order = self.db.get_order(order_id)
        if order: WorkOrderDialog(self.db, self.user, order=order, view_only=True, parent=self).exec_()

    def export_order(self):
        if not self.can(Permission.ORDERS_EXPORT): return
        order_id = self._selected_order_id()
        if not order_id: return
        order = self.db.get_order(order_id)
        if not order: return
        suggested = f"Наряд_{order['info']['version']}_{order['info']['order_date'].replace('-', '.')}.xlsx"
        path, _ = QFileDialog.getSaveFileName(self, "Сохранить наряд", suggested, "Excel (*.xlsx)")
        if not path: return
        try:
            result = export_order_xlsx(path, order); self.db.log_action(self.user.username, "Выгрузил", "Наряд", str(order['info']['version']), str(result)); info(self, "Excel", f"Сохранено:\n{result}")
        except Exception as exc: error(self, "Ошибка экспорта", exc)

    # ----- catalog -----
    def _build_catalog_tab(self):
        tab = QWidget(); layout = QVBoxLayout(tab)
        form = QHBoxLayout(); self.work_name=QLineEdit(); self.work_name.setPlaceholderText("Наименование"); self.work_code=QLineEdit(); self.work_code.setPlaceholderText("Код работы"); self.work_price=QLineEdit(); self.work_price.setPlaceholderText("Стоимость")
        add=QPushButton("Добавить"); add.setObjectName("primary"); add.clicked.connect(self.add_work_type); add.setVisible(self.can(Permission.CATALOG_CREATE))
        edit=QPushButton("Сохранить изменение"); edit.clicked.connect(self.edit_work_type); edit.setVisible(self.can(Permission.CATALOG_EDIT))
        delete=QPushButton("Удалить"); delete.setObjectName("danger"); delete.clicked.connect(self.delete_work_type); delete.setVisible(self.can(Permission.CATALOG_DELETE))
        imp=QPushButton("Импорт Excel"); imp.clicked.connect(self.import_work_types); imp.setVisible(self.can(Permission.CATALOG_IMPORT))
        for w in (self.work_name,self.work_code,self.work_price,add,edit,delete,imp): form.addWidget(w)
        layout.addLayout(form)
        self.work_search=QLineEdit(); self.work_search.setPlaceholderText("Поиск по наименованию или коду"); self.work_search.textChanged.connect(self.refresh_work_types); layout.addWidget(self.work_search)
        self.work_table=QTableWidget(0,6); self.work_table.setHorizontalHeaderLabels(["№","Наименование","Код","Стоимость","Регистрация","Редактирование"]); self.work_table.setSelectionBehavior(QAbstractItemView.SelectRows); self.work_table.setSelectionMode(QAbstractItemView.SingleSelection); self.work_table.setAlternatingRowColors(True); self.work_table.itemSelectionChanged.connect(self._work_selection)
        self.work_table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive); self.work_table.setColumnWidth(1,380); layout.addWidget(self.work_table,1)
        self.tabs.addTab(tab,"Номенклатура")

    def refresh_work_types(self):
        if not hasattr(self,"work_table"): return
        needle=self.work_search.text().strip().casefold().replace("ё","е") if hasattr(self,"work_search") else ""
        rows=[r for r in self.db.get_work_types() if not needle or needle in (str(r[1])+" "+str(r[2])).casefold().replace("ё","е")]
        self.work_table.setRowCount(len(rows))
        for i,r in enumerate(rows):
            vals=[i+1,r[1],r[2],fmt(r[3]),r[4],r[5] or ""]
            for c,v in enumerate(vals): self.work_table.setItem(i,c,make_item(v))
            self.work_table.item(i,0).setData(Qt.UserRole,int(r[0]))

    def _work_selection(self):
        row=self.work_table.currentRow()
        if row>=0:
            self.work_name.setText(self.work_table.item(row,1).text()); self.work_code.setText(self.work_table.item(row,2).text()); self.work_price.setText(self.work_table.item(row,3).text())

    def add_work_type(self):
        try:
            if not self.work_name.text().strip() or not self.work_code.text().strip() or dec(self.work_price.text()) is None: raise ValueError("Заполните наименование, код и стоимость")
            self.db.add_work_type(self.user,self.work_name.text(),self.work_code.text(),self.work_price.text()); self.refresh_work_types(); self._clear_work_form()
        except Exception as exc: error(self,"Номенклатура",exc)

    def edit_work_type(self):
        row=self.work_table.currentRow()
        if row<0:return
        try:
            self.db.update_work_type(self.user,int(self.work_table.item(row,0).data(Qt.UserRole)),self.work_name.text(),self.work_code.text(),self.work_price.text()); self.refresh_work_types(); self._clear_work_form()
        except Exception as exc:error(self,"Номенклатура",exc)

    def delete_work_type(self):
        row=self.work_table.currentRow()
        if row<0:return
        if QMessageBox.question(self,"Удаление","Удалить выбранную работу?",QMessageBox.Yes|QMessageBox.No)!=QMessageBox.Yes:return
        try:self.db.delete_work_type(self.user,int(self.work_table.item(row,0).data(Qt.UserRole)));self.refresh_work_types();self._clear_work_form()
        except Exception as exc:error(self,"Удаление",exc)

    def _clear_work_form(self): self.work_name.clear();self.work_code.clear();self.work_price.clear()

    def import_work_types(self):
        path,_=QFileDialog.getOpenFileName(self,"Импорт номенклатуры","","Excel/CSV (*.xlsx *.csv)")
        if not path:return
        try:
            raw=read_simple_xlsx(path); valid=[]
            for row in raw:
                if len(row)<3:continue
                name,code,price=str(row[0]).strip(),str(row[1]).strip(),dec(row[2])
                if not name or not code or price is None:continue
                valid.append((name,code,float(price)))
            added,dup=self.db.import_work_types(self.user,valid);self.refresh_work_types();info(self,"Импорт",f"Добавлено: {added}\nДубликаты: {dup}")
        except Exception as exc:error(self,"Импорт",exc)

    # ----- employees -----
    def _build_employees_tab(self):
        tab=QWidget();layout=QVBoxLayout(tab)
        modes=QHBoxLayout();self.mode_worker=QRadioButton("Работники");self.mode_master=QRadioButton("Мастера");self.mode_department=QRadioButton("Подразделения");self.mode_worker.setChecked(True)
        for b in (self.mode_worker,self.mode_master,self.mode_department): b.toggled.connect(self.refresh_people);modes.addWidget(b)
        modes.addStretch();layout.addLayout(modes)
        form=QHBoxLayout();self.person_name=QLineEdit();self.person_name.setPlaceholderText("ФИО / Наименование")
        add=QPushButton("Добавить");add.setObjectName("primary");add.clicked.connect(self.add_person);add.setVisible(self.can(Permission.EMPLOYEES_CREATE))
        edit=QPushButton("Сохранить изменение");edit.clicked.connect(self.edit_person);edit.setVisible(self.can(Permission.EMPLOYEES_EDIT))
        delete=QPushButton("Удалить");delete.setObjectName("danger");delete.clicked.connect(self.delete_person);delete.setVisible(self.can(Permission.EMPLOYEES_DELETE))
        imp=QPushButton("Импорт Excel");imp.clicked.connect(self.import_people);imp.setVisible(self.can(Permission.EMPLOYEES_IMPORT))
        for w in (self.person_name,add,edit,delete,imp):form.addWidget(w)
        layout.addLayout(form);self.person_search=QLineEdit();self.person_search.setPlaceholderText("Поиск");self.person_search.textChanged.connect(self.refresh_people);layout.addWidget(self.person_search)
        self.people_table=QTableWidget(0,4);self.people_table.setHorizontalHeaderLabels(["№","ФИО / Наименование","Регистрация","Редактирование"]);self.people_table.setSelectionBehavior(QAbstractItemView.SelectRows);self.people_table.setSelectionMode(QAbstractItemView.SingleSelection);self.people_table.setAlternatingRowColors(True);self.people_table.itemSelectionChanged.connect(self._people_selection);self.people_table.setColumnWidth(1,460);layout.addWidget(self.people_table,1)
        self.tabs.addTab(tab,"Сотрудники")

    def _people_mode(self):
        if self.mode_department.isChecked():return "department"
        return "master" if self.mode_master.isChecked() else "worker"

    def refresh_people(self):
        if not hasattr(self,"people_table"):return
        mode=self._people_mode();rows=self.db.get_departments() if mode=="department" else self.db.get_employees(mode=="master")
        needle=self.person_search.text().strip().casefold().replace("ё","е") if hasattr(self,"person_search") else ""
        rows=[r for r in rows if not needle or needle in str(r[1]).casefold().replace("ё","е")]
        self.people_table.setRowCount(len(rows))
        for i,r in enumerate(rows):
            vals=[i+1,r[1],r[2] if mode=="department" else r[3],(r[3] if mode=="department" else r[4]) or ""]
            for c,v in enumerate(vals):self.people_table.setItem(i,c,make_item(v))
            self.people_table.item(i,0).setData(Qt.UserRole,int(r[0]))

    def _people_selection(self):
        row=self.people_table.currentRow()
        if row>=0:self.person_name.setText(self.people_table.item(row,1).text())

    def add_person(self):
        name=self.person_name.text().strip()
        if not name:return
        try:
            mode=self._people_mode()
            if mode=="department":self.db.add_department(self.user,name)
            else:self.db.add_employee(self.user,name,mode=="master")
            self.person_name.clear();self.refresh_people();self._refresh_reference_filters()
        except Exception as exc:error(self,"Сотрудники",exc)

    def edit_person(self):
        row=self.people_table.currentRow()
        if row<0:return
        ident=int(self.people_table.item(row,0).data(Qt.UserRole));name=self.person_name.text().strip()
        try:
            if self._people_mode()=="department":self.db.update_department(self.user,ident,name)
            else:self.db.update_employee(self.user,ident,name)
            self.refresh_people();self._refresh_reference_filters()
        except Exception as exc:error(self,"Сотрудники",exc)

    def delete_person(self):
        row=self.people_table.currentRow()
        if row<0:return
        if QMessageBox.question(self,"Удаление","Удалить выбранную запись? Исторические наряды сохранят снимки ФИО/работ.",QMessageBox.Yes|QMessageBox.No)!=QMessageBox.Yes:return
        ident=int(self.people_table.item(row,0).data(Qt.UserRole))
        try:
            if self._people_mode()=="department":self.db.delete_department(self.user,ident)
            else:self.db.delete_employee(self.user,ident)
            self.refresh_people();self._refresh_reference_filters()
        except Exception as exc:error(self,"Удаление",exc)

    def import_people(self):
        if self._people_mode()=="department":warn(self,"Импорт","Для подразделений используйте ручное добавление.");return
        path,_=QFileDialog.getOpenFileName(self,"Импорт сотрудников","","Excel/CSV (*.xlsx *.csv)")
        if not path:return
        try:
            raw=read_simple_xlsx(path);names=[]
            for row in raw:
                if row and str(row[0]).strip():names.append(str(row[0]).strip())
            added,dup=self.db.import_people(self.user,names,self._people_mode()=="master");self.refresh_people();self._refresh_reference_filters();info(self,"Импорт",f"Добавлено: {added}\nДубликаты: {dup}")
        except Exception as exc:error(self,"Импорт",exc)

    def _refresh_reference_filters(self):
        if hasattr(self,"order_filter_master"):
            current=self.order_filter_master.currentData();self.order_filter_master.blockSignals(True);self.order_filter_master.clear();self.order_filter_master.addItem("Все мастера",None)
            for r in self.db.get_employees(True):self.order_filter_master.addItem(str(r[1]),int(r[0]))
            idx=self.order_filter_master.findData(current);self.order_filter_master.setCurrentIndex(max(0,idx));self.order_filter_master.blockSignals(False)
        if hasattr(self,"order_filter_dep"):
            current=self.order_filter_dep.currentData();self.order_filter_dep.blockSignals(True);self.order_filter_dep.clear();self.order_filter_dep.addItem("Все подразделения",None)
            for r in self.db.get_departments():self.order_filter_dep.addItem(str(r[1]),int(r[0]))
            idx=self.order_filter_dep.findData(current);self.order_filter_dep.setCurrentIndex(max(0,idx));self.order_filter_dep.blockSignals(False)

    # ----- admin -----
    def _build_admin_tab(self):
        tab=QWidget();layout=QVBoxLayout(tab);self.admin_tabs=QTabWidget();layout.addWidget(self.admin_tabs);self.tabs.addTab(tab,"Администрирование")
        if self.can(Permission.USERS_MANAGE):self._build_users_admin()
        if self.can(Permission.PERMISSIONS_MANAGE):self._build_permissions_admin()
        if self.can(Permission.AUDIT_VIEW):self._build_audit_admin()
        if self.can(Permission.BACKUP_MANAGE):self._build_db_admin()

    def _build_users_admin(self):
        w=QWidget();l=QVBoxLayout(w);row=QHBoxLayout();a=QPushButton("Добавить пользователя");e=QPushButton("Редактировать");t=QPushButton("Вкл/выкл");a.clicked.connect(self.add_user);e.clicked.connect(self.edit_user);t.clicked.connect(self.toggle_user);row.addWidget(a);row.addWidget(e);row.addWidget(t);row.addStretch();l.addLayout(row)
        self.users_table=QTableWidget(0,4);self.users_table.setHorizontalHeaderLabels(["ID","Логин","Роль","Активен"]);self.users_table.setSelectionBehavior(QAbstractItemView.SelectRows);self.users_table.setSelectionMode(QAbstractItemView.SingleSelection);l.addWidget(self.users_table);self.admin_tabs.addTab(w,"Пользователи")

    def refresh_users(self):
        if not hasattr(self,"users_table"):return
        rows=self.db.list_users();self.users_table.setRowCount(len(rows))
        for i,r in enumerate(rows):
            for c,v in enumerate([r[0],r[1],r[2],"Да" if r[3] else "Нет"]):self.users_table.setItem(i,c,make_item(v))
            self.users_table.item(i,0).setData(Qt.UserRole,int(r[0]))

    def add_user(self):
        dlg=UserDialog(parent=self)
        if dlg.exec_()!=QDialog.Accepted:return
        try:self.db.add_user(self.user,dlg.username.text(),dlg.password.text(),dlg.selected_roles());self.refresh_users()
        except Exception as exc:error(self,"Пользователь",exc)

    def edit_user(self):
        row=self.users_table.currentRow()
        if row<0:return
        uid=int(self.users_table.item(row,0).data(Qt.UserRole));dlg=UserDialog(self.users_table.item(row,1).text(),self.users_table.item(row,2).text(),False,self)
        if dlg.exec_()!=QDialog.Accepted:return
        try:self.db.update_user(self.user,uid,dlg.username.text(),dlg.selected_roles(),dlg.password.text());self.refresh_users()
        except Exception as exc:error(self,"Пользователь",exc)

    def toggle_user(self):
        row=self.users_table.currentRow()
        if row<0:return
        uid=int(self.users_table.item(row,0).data(Qt.UserRole));active=self.users_table.item(row,3).text()=="Да"
        try:self.db.set_user_active(self.user,uid,not active);self.refresh_users()
        except Exception as exc:error(self,"Пользователь",exc)

    def _build_permissions_admin(self):
        w=QWidget();l=QVBoxLayout(w);top=QHBoxLayout();top.addWidget(QLabel("Роль:"));self.role_combo=QComboBox();self.role_combo.addItems(ROLES);self.role_combo.currentTextChanged.connect(self.refresh_permissions);save=QPushButton("Сохранить права");save.clicked.connect(self.save_permissions);top.addWidget(self.role_combo);top.addWidget(save);top.addStretch();l.addLayout(top);self.permissions_list=QListWidget();l.addWidget(self.permissions_list);self.admin_tabs.addTab(w,"Права ролей")

    def refresh_permissions(self):
        if not hasattr(self,"permissions_list"):return
        role=self.role_combo.currentText();current=self.db.role_permissions(role);self.permissions_list.clear()
        for code in ALL_PERMISSIONS:
            item=QListWidgetItem(PERMISSION_LABELS.get(code,code));item.setData(Qt.UserRole,code);item.setFlags(item.flags()|Qt.ItemIsUserCheckable);item.setCheckState(Qt.Checked if code in current else Qt.Unchecked);self.permissions_list.addItem(item)
        if role=="Администратор":
            self.permissions_list.setEnabled(False)
        else:self.permissions_list.setEnabled(True)

    def save_permissions(self):
        role=self.role_combo.currentText();perms=[self.permissions_list.item(i).data(Qt.UserRole) for i in range(self.permissions_list.count()) if self.permissions_list.item(i).checkState()==Qt.Checked]
        try:self.db.set_role_permissions(self.user,role,perms);info(self,"Права","Права роли сохранены. Они применятся при следующем входе пользователя.")
        except Exception as exc:error(self,"Права",exc)

    def _build_audit_admin(self):
        w=QWidget();l=QVBoxLayout(w);b=QPushButton("Обновить журнал");b.clicked.connect(self.refresh_audit);l.addWidget(b);self.audit_table=QTableWidget(0,6);self.audit_table.setHorizontalHeaderLabels(["Дата","Пользователь","Действие","Объект","Наименование","Подробности"]);self.audit_table.setAlternatingRowColors(True);l.addWidget(self.audit_table);self.admin_tabs.addTab(w,"Журнал")

    def refresh_audit(self):
        if not hasattr(self,"audit_table"):return
        rows=self.db.recent_audit(200);self.audit_table.setRowCount(len(rows))
        for i,r in enumerate(rows):
            for c,v in enumerate(r):self.audit_table.setItem(i,c,make_item(v))
        self.audit_table.resizeColumnsToContents()

    def _build_db_admin(self):
        w=QWidget();l=QVBoxLayout(w);self.db_path_label=QLabel(f"Общая БД: {database_path()}");self.db_path_label.setTextInteractionFlags(Qt.TextSelectableByMouse);l.addWidget(self.db_path_label)
        paths = shared_dirs(); paths_label = QLabel(f"Ручные: {paths['manual']}\nАвто: {paths['auto']}\nПеред восстановлением: {paths['before_restore']}\nАрхивы: {paths['archives']}"); paths_label.setTextInteractionFlags(Qt.TextSelectableByMouse); l.addWidget(paths_label)
        row=QHBoxLayout();ping=QPushButton("Проверить БД");ping.clicked.connect(self._ping_async);backup=QPushButton("Создать резервную копию");backup.clicked.connect(self.create_backup);archive=QPushButton("Архивный снимок");archive.clicked.connect(self.create_archive_snapshot);restore=QPushButton("Восстановить");restore.clicked.connect(self.restore_backup);delete=QPushButton("Удалить копию");delete.clicked.connect(self.delete_backup)
        for b in (ping,backup,archive,restore,delete):row.addWidget(b)
        row.addStretch();l.addLayout(row);self.backup_combo=QComboBox();l.addWidget(self.backup_combo);l.addStretch();self.admin_tabs.addTab(w,"База данных")

    def refresh_backups(self):
        if not hasattr(self,"backup_combo"):return
        self.backup_combo.clear();folder=shared_dirs()["manual"]
        for p in sorted(folder.glob("*.db"),reverse=True):self.backup_combo.addItem(p.name,str(p))

    def create_backup(self):
        try:
            folder=shared_dirs()["manual"];target=folder/f"work_orders_backup_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.db";self.db.backup_to(target);self.db.log_action(self.user.username,"Создал резервную копию БД","Система",target.name,str(target));self.refresh_backups();info(self,"Резервная копия",f"Создано:\n{target}")
        except Exception as exc:error(self,"Резервная копия",exc)

    def create_archive_snapshot(self):
        try:
            month = datetime.now().strftime("%Y-%m")
            folder = shared_dirs()["archives"] / month
            target = folder / f"work_orders_archive_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.db"
            self.db.backup_to(target)
            self.db.log_action(self.user.username,"Создал архивный снимок БД","Система",target.name,str(target))
            info(self,"Архив",f"Архивный снимок создан:\n{target}")
        except Exception as exc:
            error(self,"Архив",exc)

    def delete_backup(self):
        if not hasattr(self,"backup_combo") or self.backup_combo.currentIndex()<0:return
        path=Path(self.backup_combo.currentData())
        if QMessageBox.question(self,"Удаление",f"Удалить {path.name}?",QMessageBox.Yes|QMessageBox.No)!=QMessageBox.Yes:return
        try:path.unlink();self.db.log_action(self.user.username,"Удалил резервную копию","Система",path.name,"");self.refresh_backups()
        except Exception as exc:error(self,"Удаление",exc)

    def restore_backup(self):
        if not hasattr(self,"backup_combo") or self.backup_combo.currentIndex()<0:return
        source=Path(self.backup_combo.currentData())
        if QMessageBox.question(self,"Восстановление","Закройте SmartOrder у остальных пользователей. Текущая база будет заменена выбранной копией. Продолжить?",QMessageBox.Yes|QMessageBox.No,QMessageBox.No)!=QMessageBox.Yes:return
        try:
            before=shared_dirs()["before_restore"]/f"before_restore_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.db";self.db.backup_to(before);self.db.restore_from(source);self.db.log_action(self.user.username,"Восстановил БД","Система",source.name,f"Страховочная копия: {before}");self.refresh_orders();info(self,"Восстановление","База восстановлена")
        except Exception as exc:error(self,"Восстановление",exc)

    # ----- about / state -----
    def _build_about_tab(self):
        tab = GifBackgroundWidget(["loading2.gif", "login_background.gif"])
        root = QVBoxLayout(tab)
        root.setContentsMargins(30, 28, 30, 28)
        title = QLabel(f"SmartOrder Full · LiteCore {APP_VERSION}")
        title.setAlignment(Qt.AlignCenter)
        font = title.font(); font.setPointSize(24); font.setBold(True); title.setFont(font)
        title.setStyleSheet("background:transparent;color:white;")
        root.addWidget(title)
        cards = QHBoxLayout()
        system = QFrame(); system.setObjectName("aboutGlass")
        system.setStyleSheet("QFrame#aboutGlass{background:rgba(0,0,0,0);border:1px solid rgba(255,255,255,90);border-radius:20px;} QLabel{background:transparent;color:white;}")
        s = QVBoxLayout(system); s.setContentsMargins(24,22,24,22)
        h = QLabel("Система"); f=h.font(); f.setPointSize(16); f.setBold(True); h.setFont(f); s.addWidget(h)
        info_label = QLabel(
            f"Версия: {APP_VERSION}\n"
            f"Ядро: SmartOrder LiteCore\n"
            f"Общая БД: {database_path()}\n"
            f"Сетевой корень: {network_root()}\n\n"
            "SQLite: короткие транзакции · локальный клиент · SMB-safe retry · RAM cache"
        )
        info_label.setWordWrap(True); info_label.setTextInteractionFlags(Qt.TextSelectableByMouse); s.addWidget(info_label); s.addStretch()

        guide = QFrame(); guide.setObjectName("aboutGlass")
        guide.setStyleSheet("QFrame#aboutGlass{background:rgba(0,0,0,0);border:1px solid rgba(255,255,255,90);border-radius:20px;} QLabel{background:transparent;color:white;}")
        g = QVBoxLayout(guide); g.setContentsMargins(24,22,24,22)
        h2=QLabel("Как работать в программе?"); f2=h2.font(); f2.setPointSize(16); f2.setBold(True); h2.setFont(f2); g.addWidget(h2)
        txt=QLabel("Наряд — создание, просмотр, редактирование и Excel.\nНоменклатура — работы и цены.\nСотрудники — работники, мастера и подразделения.\nАдминистрирование — пользователи, права, журнал и резервные копии.\n\nИнтерфейс работает локально, данные и резервные копии остаются на общем сетевом ресурсе.")
        txt.setWordWrap(True); g.addWidget(txt); g.addStretch()
        cards.addWidget(system,1); cards.addWidget(guide,1); root.addLayout(cards,1)
        self.tabs.addTab(tab,"О программе")

    def _sync_current_tab(self):
        current = self.tabs.tabText(self.tabs.currentIndex())
        self.db.invalidate_cache()
        if current == "Наряд": self.refresh_orders()
        elif current == "Номенклатура": self.refresh_work_types()
        elif current == "Сотрудники": self.refresh_people(); self._refresh_reference_filters()
        elif current == "Администрирование": self.refresh_users(); self.refresh_permissions(); self.refresh_audit(); self.refresh_backups()
        self._ping_async()

    def _tab_changed(self, _index):
        current=self.tabs.tabText(self.tabs.currentIndex())
        if current=="Администрирование":
            self.refresh_users();self.refresh_permissions();self.refresh_audit();self.refresh_backups()
        elif current=="Номенклатура":self.refresh_work_types()
        elif current=="Сотрудники":self.refresh_people()
        elif current=="Наряд":self.refresh_orders()

    def _theme_toggled(self, checked): self.ui_settings.theme="dark" if checked else "light";self._apply_theme()
    def _apply_theme(self): QApplication.instance().setStyleSheet(DARK_QSS if self.ui_settings.theme=="dark" else LIGHT_QSS)
    def _apply_zoom(self,value):
        value=int(value);self.ui_settings.zoom=value
        if hasattr(self,"zoom_label"):self.zoom_label.setText(f"{value}%")
        font=QFont(QApplication.instance().font());font.setPointSizeF(10.5*value/100.0);QApplication.instance().setFont(font)

    def _ping_async(self):
        if getattr(self,"_ping_running",False):return
        self._ping_running=True
        def worker():
            try:self._ping_bridge.done.emit(True,self.db.stable_ping_ms(3),"")
            except Exception as exc:self._ping_bridge.done.emit(False,0.0,str(exc))
        threading.Thread(target=worker,name="SmartOrderPing",daemon=True).start()

    def _ping_done(self,ok:bool,ms:float,message:str):
        self._ping_running=False
        if ok:
            if ms > 300:
                self.db_state.setText(f"БД доступна, медленный ответ · {ms:.0f} мс"); self.db_state.setObjectName("db_slow")
            elif ms > 150:
                self.db_state.setText(f"БД доступна · {ms:.0f} мс"); self.db_state.setObjectName("db_slow")
            else:
                self.db_state.setText(f"БД доступна · {ms:.0f} мс"); self.db_state.setObjectName("db_ok")
            self.db_state.setToolTip("Показывается медиана 3 рабочих SQLite-запросов после отдельного SMB-прогрева.")
        else:
            self.db_state.setText("БД недоступна");self.db_state.setToolTip(message);self.db_state.setObjectName("db_bad")
        self.db_state.style().unpolish(self.db_state);self.db_state.style().polish(self.db_state)

    def _auto_backup(self, reason: str):
        now=time.monotonic()
        if self._auto_backup_running or now-self._auto_backup_last<600:return
        self._auto_backup_running=True;self._auto_backup_last=now
        target=shared_dirs()["auto"]/f"auto_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}_{reason}.db"
        def worker():
            try:self.db.backup_to(target)
            except Exception:pass
            finally:self._auto_backup_running=False
        threading.Thread(target=worker,name="SmartOrderBackup",daemon=True).start()

    def closeEvent(self,event):
        self.settings_store.save(self.ui_settings);event.accept()
