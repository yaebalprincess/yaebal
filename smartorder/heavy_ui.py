from __future__ import annotations
from .i18n import source_text, tr

import json
import os
import threading
import time
import zipfile
import platform
import socket
import shutil
import sys
from collections import deque
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from PyQt5.QtCore import (
    QDate, QEasingCurve, QEvent, QObject, QPoint, QPropertyAnimation, QRect, QSize, QUrl,
    Qt, QTimer, pyqtProperty, pyqtSignal,
)
from PyQt5.QtGui import QColor, QDesktopServices, QFont, QFontMetrics, QMovie, QPainter, QPixmap, QPolygon, QBrush, QTextCharFormat, QPalette, QIcon, QTextDocument, QPen, QLinearGradient
from PyQt5.QtPrintSupport import QPrinter
from PyQt5.QtWidgets import (
    QAbstractItemView, QAbstractSpinBox, QApplication, QCalendarWidget, QCheckBox, QComboBox,
    QDateEdit, QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QFrame,
    QGraphicsDropShadowEffect, QGraphicsOpacityEffect, QGroupBox, QHBoxLayout,
    QGridLayout, QHeaderView, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMainWindow,
    QMenu, QMessageBox, QPushButton, QProgressDialog, QRadioButton, QSizePolicy, QSlider,
    QScrollArea, QTabWidget, QTableWidget, QTableWidgetItem, QTextBrowser, QTextEdit, QToolButton, QVBoxLayout, QWidget,
)

from . import ui as _lite_ui
from .config import (
    APP_NAME, APP_VERSION, SettingsStore, UiSettings, database_path,
    local_drafts_dir, local_logs_dir, local_root, network_root, resource_path, shared_dirs, workshop_root,
)
from .db import Database, StaleOrderError
from .domain import dec, fmt, order_content_signature
from .excel import export_order_xlsx
from .update_manager import PatchError, publish_update_notice, stage_patch
from .security import ALL_PERMISSIONS, PERMISSION_LABELS, Permission, SessionUser, ROLES, ACCOUNTING_ROLES, split_roles
from .heavy_styles import APPLE_QSS, apply_apple_design, set_theme_recursive
from .policy import ensure_usage_policy_document, ensure_user_guide_document, ensure_troubleshooting_document, USER_GUIDE_HTML

BaseMainWindow = _lite_ui.MainWindow
BaseWorkOrderDialog = _lite_ui.WorkOrderDialog
FirstAdminDialog = _lite_ui.FirstAdminDialog
UserDialog = _lite_ui.UserDialog
MultiSelectDialog = _lite_ui.MultiSelectDialog
info = _lite_ui.info
warn = _lite_ui.warn
error = _lite_ui.error
make_item = _lite_ui.make_item
read_simple_xlsx = _lite_ui.read_simple_xlsx


# ---------------------------------------------------------------------------
# Heavy UI building blocks copied from the final Full branch, not from Lite UI.
# ---------------------------------------------------------------------------

def _find_logo(*names: str) -> Path | None:
    for name in names:
        for candidate in (name, f"resources/{name}"):
            try:
                path = resource_path(candidate)
                if path.exists():
                    return path
            except Exception:
                pass
    return None


def _set_logo(label: QLabel, size: int, *names: str) -> bool:
    label.setAlignment(Qt.AlignCenter)
    label.setFixedSize(size, size)
    label.setStyleSheet("background:transparent;border:none;")
    path = _find_logo(*names)
    if not path:
        return False
    pix = QPixmap(str(path))
    if pix.isNull():
        return False
    label.setPixmap(pix.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation))
    return True


class AnimatedToggle(QCheckBox):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(47, 27)
        self.setCursor(Qt.PointingHandCursor)
        self._offset = 2
        self.animation = QPropertyAnimation(self, b"offset", self)
        self.animation.setDuration(150)
        self.animation.setEasingCurve(QEasingCurve.InOutQuad)
        self.stateChanged.connect(self._animate)
        self.set_offset(self._offset)

    def setChecked(self, checked):
        super().setChecked(checked)
        if self.signalsBlocked() and hasattr(self, "animation"):
            self.animation.stop()
            self.set_offset(32 if checked else 2)

    def _animate(self, state):
        self.animation.stop()
        self.animation.setStartValue(self._offset)
        self.animation.setEndValue(32 if state else 2)
        self.animation.start()

    def get_offset(self):
        return self._offset

    def set_offset(self, value):
        self._offset = int(value)
        self.update()

    def hitButton(self,point):
        return self.rect().contains(point)

    def paintEvent(self, event):
        from PyQt5.QtCore import QRectF
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        track = QLinearGradient(0, 0, self.width(), self.height())
        track.setColorAt(0, QColor("#53b5ff" if self.isChecked() else "#8197b0"))
        track.setColorAt(1, QColor("#007aff" if self.isChecked() else "#6f86a2"))
        painter.setPen(QPen(QColor(255, 255, 255, 205), 1))
        painter.setBrush(track)
        painter.drawRoundedRect(QRectF(.5, .5, 46, 26), 13, 13)
        painter.setBrush(QColor("#fbfeff"))
        x = 2 + (self._offset - 2) * 19 / 30
        painter.drawEllipse(QRectF(x, 2, 23, 23))

    offset = pyqtProperty(int, get_offset, set_offset)


class SmartComboBox(QComboBox):
    def findText(self, text, flags=Qt.MatchExactly|Qt.MatchCaseSensitive):
        from .i18n import item_source
        for index in range(self.count()):
            if item_source(self,index)==text:return index
        return super().findText(text,flags)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumWidth(190)
        self._arrow_hover = False
        self._arrow_pressed = False
        self.setMouseTracking(True)
        self.setStyleSheet("QComboBox{padding-right:62px;}QComboBox::drop-down{width:0;border:none;}QComboBox::down-arrow{image:none;width:0;height:0;}")

    def _arrow_rect(self):
        return QRect(self.width() - 58, 3, 52, max(28, self.height() - 6))

    def mouseMoveEvent(self, event):
        hover = self._arrow_rect().contains(event.pos())
        if hover != self._arrow_hover:
            self._arrow_hover = hover
            self.update()
        super().mouseMoveEvent(event)

    def mousePressEvent(self, event):
        if self._arrow_rect().contains(event.pos()):
            self._arrow_pressed = True
            self.update()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        self._arrow_pressed = False
        self.update()
        super().mouseReleaseEvent(event)

    def leaveEvent(self, event):
        self._arrow_hover = False
        self._arrow_pressed = False
        self.update()
        super().leaveEvent(event)

    def showPopup(self):
        from .interaction_ui import prepare_combo_popup
        prepare_combo_popup(self)
        self.setMaxVisibleItems(min(10,max(1,self.count())))
        self.view().setUniformItemSizes(True)
        super().showPopup()
        frame=self.view().window();point=self.mapToGlobal(QPoint(0,self.height()+3))
        screen=QApplication.screenAt(point) or QApplication.primaryScreen();available=screen.availableGeometry()
        frame.move(max(available.left(),min(point.x(),available.right()-frame.width()+1)),min(point.y(),available.bottom()-frame.height()+1))

    def paintEvent(self, event):
        from PyQt5.QtWidgets import QStylePainter,QStyleOptionComboBox,QStyle
        option=QStyleOptionComboBox();self.initStyleOption(option);option.state &= ~QStyle.State_HasFocus
        native=QStylePainter(self);native.drawComplexControl(QStyle.CC_ComboBox,option);native.drawControl(QStyle.CE_ComboBoxLabel,option);native.end()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        from .liquid_effects import theme_of
        theme = theme_of(self)
        rect = self._arrow_rect()
        alpha = 55 if self._arrow_pressed else (34 if self._arrow_hover else 16)
        painter.setBrush(QColor(0, 122, 255, alpha))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(rect, 9, 9)
        painter.setBrush(QColor("#b9dcff") if theme == "dark" else QColor("#527fa7"))
        cx, cy = rect.x() + rect.width() // 2, rect.y() + rect.height() // 2 + 2
        painter.drawPolygon(QPolygon([QPoint(cx - 7, cy - 4), QPoint(cx + 7, cy - 4), QPoint(cx, cy + 5)]))


class ResponsiveGrid(QWidget):
    """Wraps controls into stable rows as the available width changes.

    Qt's box layouts do not reflow when a large application font makes a row
    wider than the window.  This small container keeps the same widgets and
    moves them between a few grid columns on resize, so controls never paint
    over their neighbours.  It deliberately uses minimum widths only as a
    layout hint; the widgets remain expandable and can shrink on small
    screens without changing the selected zoom value.
    """

    def __init__(self, widgets, min_cell_width=320, max_columns=4, parent=None):
        super().__init__(parent)
        self._widgets = list(widgets)
        self._min_cell_width = max(160, int(min_cell_width))
        self._max_columns = max(1, int(max_columns))
        self._columns = 0
        self._grid = QGridLayout(self)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setHorizontalSpacing(8)
        self._grid.setVerticalSpacing(8)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        self._relayout()

    def _column_count(self):
        width = max(1, self.width())
        return max(1, min(self._max_columns, width // self._min_cell_width))

    def _relayout(self):
        columns = self._column_count()
        if columns == self._columns and self._grid.count() == len(self._widgets):
            return
        preserve_visibility = self._columns != 0
        # ``isVisible()`` is false while the parent window is still hidden,
        # even when the child was explicitly shown. Using it here caused the
        # first resize pass to hide the zoom toolbar and action buttons.
        # ``isHidden()`` reflects the widget's explicit visibility state and
        # therefore preserves only intentional role-based hiding.
        hidden = {id(widget): widget.isHidden() and widget.testAttribute(Qt.WA_WState_ExplicitShowHide) for widget in self._widgets}
        while self._grid.count():
            item = self._grid.takeAt(0)
            if item is not None and item.widget() is not None:
                item.widget().setParent(self)
        for index, widget in enumerate(self._widgets):
            row, column = divmod(index, columns)
            self._grid.addWidget(widget, row, column)
            # Reparenting through ``takeAt`` can hide a child on some Qt
            # versions. Preserve an intentional hidden state (for example
            # the history panel for accounting roles) while showing controls
            # during the first layout pass.
            if hidden.get(id(widget), False):
                widget.hide()
            else:
                widget.show()
        for column in range(self._max_columns):
            self._grid.setColumnStretch(column, 1 if column < columns else 0)
        self._columns = columns
        self.updateGeometry()

    def resizeEvent(self, event):
        self._relayout()
        super().resizeEvent(event)


class SmartDateEdit(QDateEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setDisplayFormat("dd.MM.yyyy")
        self.setButtonSymbols(QAbstractSpinBox.NoButtons)
        self.setCalendarPopup(False)
        self.setMinimumWidth(176)
        self._icon_hover = False
        self._icon_pressed = False
        self.setMouseTracking(True)
        self.setStyleSheet("QDateEdit{padding-right:62px;}QDateEdit::drop-down{width:0;border:none;}QDateEdit::down-arrow{image:none;width:0;height:0;}QDateEdit::up-button,QDateEdit::down-button{width:0;height:0;border:none;}")
        self._popup = QCalendarWidget(self)
        self._popup.setWindowFlags(Qt.Popup)
        self._popup.hide()
        self._popup.clicked.connect(self._select_date)

    def _icon_rect(self):
        return QRect(self.width() - 58, 3, 52, max(28, self.height() - 6))

    def _select_date(self, date):
        self.setDate(date)
        self._popup.hide()

    def setTheme(self, theme):
        if theme == "dark":
            self._popup.setStyleSheet("QCalendarWidget QWidget{background:#1C1C1E;color:#F5F5F7;}QCalendarWidget QAbstractItemView{background:#2C2C2E;color:#F5F5F7;selection-background-color:#0A84FF;selection-color:white;}QCalendarWidget QToolButton{color:#F5F5F7;background:transparent;border-radius:8px;padding:6px;}QCalendarWidget QToolButton:hover{background:rgba(10,132,255,45);}")
        else:
            self._popup.setStyleSheet("QCalendarWidget QWidget{background:#FFF;color:#1D1D1F;}QCalendarWidget QAbstractItemView{background:#FFF;color:#1D1D1F;selection-background-color:#007AFF;selection-color:white;}QCalendarWidget QToolButton{color:#1D1D1F;background:transparent;border-radius:8px;padding:6px;}QCalendarWidget QToolButton:hover{background:rgba(0,122,255,28);}")
        self.update()

    def mouseMoveEvent(self, event):
        hover = self._icon_rect().contains(event.pos())
        if hover != self._icon_hover:
            self._icon_hover = hover
            self.update()
        super().mouseMoveEvent(event)

    def mousePressEvent(self, event):
        if self._icon_rect().contains(event.pos()):
            self._icon_pressed = True
            self.update()
            self._popup.setSelectedDate(self.date())
            self._popup.move(self.mapToGlobal(QPoint(0, self.height() + 4)))
            self._popup.show()
            return
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        self._icon_pressed = False
        self.update()
        super().mouseReleaseEvent(event)

    def leaveEvent(self, event):
        self._icon_hover = False
        self._icon_pressed = False
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        theme = self.property("theme") or "light"
        rect = self._icon_rect()
        alpha = 55 if self._icon_pressed else (35 if self._icon_hover else 18)
        painter.setBrush(QColor(0, 122, 255, alpha))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(rect, 9, 9)
        painter.setPen(QColor("#F5F5F7") if theme == "dark" else QColor("#1D1D1F"))
        x, y = rect.x() + rect.width() // 2 - 9, rect.y() + rect.height() // 2 - 9
        painter.drawRoundedRect(QRect(x, y + 3, 18, 16), 3, 3)
        painter.drawLine(x, y + 8, x + 18, y + 8)
        painter.drawLine(x + 5, y, x + 5, y + 5)
        painter.drawLine(x + 13, y, x + 13, y + 5)


class ScrollToTopButton(QPushButton):
    def __init__(self, table: QTableWidget):
        super().__init__("↑", table.viewport())
        self.table = table
        self.setObjectName("ScrollTopButton")
        self.setFixedSize(54, 54)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip("Наверх")
        self._scroll_anim = None
        self._press_anim = None
        self._opacity = QGraphicsOpacityEffect(self)
        self._opacity.setOpacity(0.0)
        self.setGraphicsEffect(self._opacity)
        self.hide()
        table.verticalScrollBar().valueChanged.connect(self._update_visibility)
        table.verticalScrollBar().rangeChanged.connect(lambda *_: self._update_visibility())
        self.clicked.connect(self._go)

    def _place(self):
        vp = self.table.viewport()
        self.move(max(8, vp.width() - self.width() - 22), max(8, vp.height() - self.height() - 22))
        self.raise_()

    def _update_visibility(self):
        self._place()
        show = self.table.verticalScrollBar().value() > max(40, self.table.verticalScrollBar().pageStep() // 5)
        if show and not self.isVisible():
            self.show(); self._fade(1.0)
        elif not show and self.isVisible():
            self._fade(0.0, hide=True)

    def _fade(self, end: float, hide=False):
        anim = QPropertyAnimation(self._opacity, b"opacity", self)
        anim.setDuration(180)
        anim.setStartValue(self._opacity.opacity())
        anim.setEndValue(end)
        anim.setEasingCurve(QEasingCurve.InOutCubic)
        if hide:
            anim.finished.connect(self.hide)
        self._fade_anim = anim
        anim.start()

    def _go(self):
        bar = self.table.verticalScrollBar()
        scroll = QPropertyAnimation(bar, b"value", self)
        scroll.setDuration(420)
        scroll.setStartValue(bar.value())
        scroll.setEndValue(0)
        scroll.setEasingCurve(QEasingCurve.OutCubic)
        self._scroll_anim = scroll
        scroll.start()
        g = self.geometry()
        anim = QPropertyAnimation(self, b"geometry", self)
        anim.setDuration(430)
        anim.setEasingCurve(QEasingCurve.OutBack)
        anim.setStartValue(g)
        anim.setKeyValueAt(0.28, QRect(g.x()+5, g.y()+5, g.width()-10, g.height()-8))
        anim.setKeyValueAt(0.62, QRect(g.x()-2, g.y()-9, g.width()+4, g.height()+3))
        anim.setEndValue(g)
        self._press_anim = anim
        anim.start()


class MotionFilter(QObject):
    """Actual hover/press animation without moving layout-managed controls."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self._anims = {}

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Show and isinstance(obj, QDialog):
            # Theme the native caption after Qt has created its real handle.
            # Never manufacture handles for hidden widgets/popups.
            from PyQt5 import sip
            theme, _ = _theme_of(obj)
            QTimer.singleShot(0, lambda w=obj,d=theme=="dark":_rc4_set_windows_titlebar_dark(w,d) if not sip.isdeleted(w) else None)
        if isinstance(obj, QPushButton) and obj.objectName() != "ScrollTopButton":
            if event.type() in (QEvent.Enter, QEvent.Leave, QEvent.MouseButtonPress, QEvent.MouseButtonRelease):
                self._animate_button(obj, event.type())
        return False

    def _animate_button(self, btn: QPushButton, event_type):
        effect = getattr(btn, "_smartorder_shadow", None)
        if effect is None:
            effect = QGraphicsDropShadowEffect(btn)
            effect.setColor(QColor(0, 122, 255, 75))
            effect.setBlurRadius(5)
            effect.setOffset(0, 1)
            btn.setGraphicsEffect(effect)
            btn._smartorder_shadow = effect
        target_blur, target_y = (18, 4)
        if event_type == QEvent.Leave:
            target_blur, target_y = 5, 1
        elif event_type == QEvent.MouseButtonPress:
            target_blur, target_y = 2, 0
        elif event_type == QEvent.MouseButtonRelease:
            target_blur, target_y = 18, 4
        key = id(btn)
        old = self._anims.get(key)
        if old:
            for a in old:
                try: a.stop()
                except Exception: pass
        a1 = QPropertyAnimation(effect, b"blurRadius", btn); a1.setDuration(120); a1.setEndValue(float(target_blur)); a1.setEasingCurve(QEasingCurve.OutCubic)
        a2 = QPropertyAnimation(effect, b"yOffset", btn); a2.setDuration(120); a2.setEndValue(float(target_y)); a2.setEasingCurve(QEasingCurve.OutCubic)
        self._anims[key] = (a1, a2); a1.start(); a2.start()


def install_motion_effects(app: QApplication):
    from .liquid_effects import install_liquid_effects
    return install_liquid_effects(app)


class GifBackgroundWidget(QWidget):
    def __init__(self, candidates, parent=None):
        super().__init__(parent)
        self.bg_label = QLabel(self)
        self.bg_label.setScaledContents(True)
        self.movie = None
        for candidate in candidates:
            try:
                path = resource_path(candidate)
                if not path.exists():
                    continue
                movie = QMovie(str(path))
                movie.setCacheMode(QMovie.CacheAll)
                if movie.isValid():
                    self.movie = movie
                    self.bg_label.setMovie(movie)
                    movie.start()
                    break
            except Exception:
                pass
        if self.movie is None:
            self.bg_label.setStyleSheet("background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #063B4B,stop:.5 #0B6570,stop:1 #021F2A);")
        self.bg_label.lower()

    def resizeEvent(self, event):
        self.bg_label.setGeometry(self.rect())
        if self.movie:
            try: self.movie.setScaledSize(self.size())
            except Exception: pass
        super().resizeEvent(event)


# ---------------------------------------------------------------------------
# Heavy login: same structure/measurements as the final monolith.
# ---------------------------------------------------------------------------

class HeavyLoginDialog(QDialog):
    def __init__(self, db: Database, parent=None):
        super().__init__(parent)
        self.db = db
        self.user: SessionUser | None = None
        self.setWindowTitle("Авторизация - SmartOrder")
        self.setModal(True)
        # Allow the login card to grow with the selected UI scale. A fixed
        # 400x550 surface clipped the 175–200% font on small displays.
        self.setMinimumSize(400, 550)
        self.resize(400, 550)
        self.setObjectName("LoginDialog")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self._build()
        from .appearance import restore_startup_surface
        restore_startup_surface(self)
        self.username_edit.setFocus()

    def _build(self):
        self.bg = GifBackgroundWidget([
            "login_background.gif", "loading.gif", "loading2.gif",
            "resources/login_background.gif", "resources/loading.gif", "resources/loading2.gif",
        ], self)
        self.bg.setGeometry(self.rect())
        container = QWidget(self); self._form_container = container; container.setGeometry(self.rect()); container.setStyleSheet("background:transparent;")
        root = QVBoxLayout(container); root.setContentsMargins(24, 18, 24, 20); root.setSpacing(8)
        logo = QLabel()
        if not _set_logo(logo, 92, "smartorder_logo_icon_light.png", "smartorder_logo_icon.png", "smartorder_logo_white.png", "smartorder_logo.png"):
            logo.setText("S"); logo.setAlignment(Qt.AlignCenter); logo.setStyleSheet("color:white;font-size:48px;font-weight:900;background:transparent;")
        root.addWidget(logo, alignment=Qt.AlignCenter)
        title = QLabel("SmartOrder"); title.setAlignment(Qt.AlignCenter); title.setStyleSheet("color:#FFF;background:transparent;font-size:18px;font-weight:900;"); root.addWidget(title)
        subtitle = QLabel("Формирование нарядов\nна сдельную работу"); subtitle.setAlignment(Qt.AlignCenter); subtitle.setWordWrap(True); subtitle.setMinimumHeight(44); subtitle.setMaximumHeight(100); subtitle.setMinimumWidth(320); subtitle.setStyleSheet("color:#FFF;background:transparent;font-size:13px;font-weight:800;"); root.addWidget(subtitle, alignment=Qt.AlignCenter)
        form = QFormLayout(); form.setLabelAlignment(Qt.AlignRight|Qt.AlignVCenter); form.setFormAlignment(Qt.AlignHCenter); form.setHorizontalSpacing(10); form.setVerticalSpacing(10)
        self.username_edit = QLineEdit(); self.username_edit.setPlaceholderText("Введите логин"); self.username_edit.setMinimumWidth(235); self.username_edit.setMinimumHeight(44); self.username_edit.returnPressed.connect(lambda: self.password_edit.setFocus())
        self.password_edit = QLineEdit(); self.password_edit.setEchoMode(QLineEdit.Password); self.password_edit.setPlaceholderText("Введите пароль"); self.password_edit.setMinimumWidth(235); self.password_edit.setMinimumHeight(44); self.password_edit.returnPressed.connect(self._login)
        input_style = "QLineEdit{background:rgba(255,255,255,220);color:#1D1D1F;border:2px solid #007AFF;border-radius:12px;padding:8px 12px;font-size:13px;}QLineEdit:focus{background:#FFF;}"
        self.username_edit.setStyleSheet(input_style); self.password_edit.setStyleSheet(input_style)
        login_label = QLabel("Логин:"); pass_label = QLabel("Пароль:")
        for lab in (login_label, pass_label): lab.setStyleSheet("color:#FFF;background:transparent;font-size:13px;font-weight:900;")
        form.addRow(login_label, self.username_edit); form.addRow(pass_label, self.password_edit); root.addLayout(form)
        forgot = QPushButton("Забыли пароль?"); forgot.setObjectName("GhostButton"); forgot.setFlat(True); forgot.setStyleSheet("QPushButton{color:#0A84FF;background:transparent;border:none;font-weight:800;}QPushButton:hover{color:#66B5FF;}"); forgot.clicked.connect(lambda: info(self, "Восстановление пароля", "Обратитесь к IT отделу для сброса пароля.\n\nКонтактная информация:\nТелефон: +7 995-552-85-13\nEmail: artem.pestretsov@tmbsir.ru")); root.addWidget(forgot, alignment=Qt.AlignCenter)
        row = QHBoxLayout(); row.setSpacing(8)
        ok = QPushButton("Войти"); cancel = QPushButton("Отмена")
        ok.setMinimumHeight(46); cancel.setMinimumHeight(46); ok.setObjectName("PrimaryButton"); cancel.setObjectName("SecondaryButton")
        ok.setStyleSheet("QPushButton{background:#007AFF;color:#FFF;border:1px solid #007AFF;border-radius:11px;font-weight:900;min-width:125px;}QPushButton:hover{background:#0A84FF;}")
        cancel.setStyleSheet("QPushButton{background:rgba(0,122,255,25);color:#0A84FF;border:1px solid #0A84FF;border-radius:11px;font-weight:900;min-width:125px;}QPushButton:hover{background:rgba(0,122,255,55);}")
        ok.clicked.connect(self._login); cancel.clicked.connect(self.reject); row.addWidget(ok,1); row.addWidget(cancel,1); root.addLayout(row); root.addStretch(1)

    def resizeEvent(self, event):
        try: self.bg.setGeometry(self.rect())
        except Exception: pass
        container = getattr(self, "_form_container", None)
        if container is not None: container.setGeometry(self.rect())
        super().resizeEvent(event)

    def _login(self):
        try:
            user = self.db.authenticate(self.username_edit.text(), self.password_edit.text())
        except Exception as exc:
            error(self, "Ошибка подключения к базе", exc); return
        if not user:
            warn(self, "Вход", "Неверный логин/пароль или учётная запись отключена")
            self.password_edit.clear(); self.password_edit.setFocus(); return
        self.user = user
        self.accept()


# ---------------------------------------------------------------------------
# Heavy work-order editor: Full layout, LiteCore transactions underneath.
# ---------------------------------------------------------------------------

class HeavyWorkOrderDialog(BaseWorkOrderDialog):
    def _build(self):
        self.setObjectName("WorkOrderDialog")
        layout = QVBoxLayout(self); layout.setContentsMargins(16, 14, 16, 14); layout.setSpacing(10)
        info_group = QGroupBox("Информация о наряде"); info_group.setObjectName("OrderInfoGroup")
        form = QFormLayout(info_group); form.setContentsMargins(14,24,14,14); form.setVerticalSpacing(10)
        self.order_date = SmartDateEdit(); self.order_date.setDate(QDate.currentDate()); self.order_date.setMinimumWidth(180)
        self.shift = SmartComboBox(); self.shift.setMinimumWidth(240); self.shift.addItems(["Ночная", "Дневная"])
        self.master = SmartComboBox(); self.master.setMinimumWidth(260)
        for row in self.db.get_employees(True): self.master.addItem(str(row[1]), int(row[0]))
        self.department = SmartComboBox(); self.department.setMinimumWidth(260)
        for row in self.db.get_departments(): self.department.addItem(str(row[1]), int(row[0]))
        self.comment = QLineEdit(); self.comment.setPlaceholderText("Необязательный комментарий")
        form.addRow("Дата наряда:", self.order_date); form.addRow("Тип смены:", self.shift); form.addRow("Мастер:", self.master); form.addRow("Подразделение:", self.department); form.addRow("Комментарий:", self.comment)
        layout.addWidget(info_group)
        self.table = QTableWidget(0, 10)
        self.table.setHorizontalHeaderLabels(["ФИО\nработника","Часы\nработы","Работы","Код\nработы","Стоимость\nв рублях","ФИКС\nКол-во коробок","ФИКС\nВес коробок кг.","ФИКС\nИтоговый вес в кг.","ФАКТ\nчасы/кг/шт.","Оплата"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows); self.table.setSelectionMode(QAbstractItemView.ExtendedSelection); self.table.setAlternatingRowColors(True); self.table.verticalHeader().setVisible(False); self.table.horizontalHeader().setDefaultAlignment(Qt.AlignCenter); self.table.horizontalHeader().setFixedHeight(60); self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        widths=[250,105,300,130,125,125,125,150,150,125]
        for i,w in enumerate(widths): self.table.setColumnWidth(i,w)
        self.table.itemChanged.connect(self._on_cell_changed); layout.addWidget(self.table,1)
        controls = QHBoxLayout(); controls.setSpacing(10)
        self.add_employee_btn = QPushButton("Добавить работников"); self.add_work_btn = QPushButton("Добавить работы"); self.delete_row_btn = QPushButton("Удалить выбранных"); self.delete_row_btn.setObjectName("DangerButton")
        self.add_employee_btn.clicked.connect(self._add_employees); self.add_work_btn.clicked.connect(self._add_works); self.delete_row_btn.clicked.connect(self._delete_rows)
        controls.addWidget(self.add_employee_btn); controls.addWidget(self.add_work_btn); controls.addWidget(self.delete_row_btn); controls.addStretch(); layout.addLayout(controls)
        self.scroll_top = ScrollToTopButton(self.table)
        box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel); box.button(QDialogButtonBox.Ok).setText("Сохранить"); box.button(QDialogButtonBox.Ok).setObjectName("PrimaryButton"); box.button(QDialogButtonBox.Cancel).setText("Отмена"); box.accepted.connect(self._accept); box.rejected.connect(self.reject); self.button_box=box; layout.addWidget(box)

    def showEvent(self, event):
        super().showEvent(event)
        try: self.showMaximized()
        except Exception: pass
        try: apply_apple_design(self, "dark" if getattr(self.parent(), "ui_settings", UiSettings()).theme == "dark" else "light", getattr(getattr(self.parent(), "ui_settings", None), "zoom", 100))
        except Exception: pass

    def reject(self):
        if not self.view_only:
            try: self._save_draft()
            except Exception: pass
        super().reject()

    def load_draft_payload(self, payload: dict):
        date = QDate.fromString(str(payload.get("order_date", "")), "dd-MM-yyyy")
        if date.isValid(): self.order_date.setDate(date)
        self.shift.setCurrentText(str(payload.get("shift_type", "")))
        self._set_combo_data(self.master, payload.get("master_id")); self._set_combo_data(self.department, payload.get("department_id")); self.comment.setText(str(payload.get("comment", "")))
        self.table.blockSignals(True)
        try:
            self.table.setRowCount(0)
            for raw in payload.get("lines", []):
                row=self.table.rowCount(); self.table.insertRow(row); self._ensure_row(row)
                self.table.setItem(row,0,make_item(raw.get("employee_name", ""),raw.get("employee_id")))
                self.table.item(row,1).setText(str(raw.get("hours", "") or "")); self.table.setItem(row,2,make_item(raw.get("work_name", ""),raw.get("work_type_id"))); self.table.setItem(row,3,make_item(raw.get("work_code", ""))); self.table.setItem(row,4,make_item(str(raw.get("price", "") or "")))
                self.table.item(row,5).setText(str(raw.get("fixed_boxes", "") or "")); self.table.item(row,6).setText(str(raw.get("fixed_weight", "") or "")); self.table.item(row,8).setText(str(raw.get("actual_value", "") or "")); self._apply_flags(row)
        finally:
            self.table.blockSignals(False)
        self._refresh_totals()


# Make inherited Lite methods instantiate the heavy editor without duplicating DB logic.
_lite_ui.WorkOrderDialog = HeavyWorkOrderDialog


# ---------------------------------------------------------------------------
# Heavy main window. Lazy tabs preserve Lite startup performance.
# ---------------------------------------------------------------------------

class HeavyMainWindow(BaseMainWindow):
    def _build(self):
        self.setObjectName("SmartOrderWindow"); self.setAttribute(Qt.WA_StyledBackground, True)
        shell = QWidget(); shell.setObjectName("AppShell")
        main = QVBoxLayout(shell); main.setContentsMargins(16,14,16,12); main.setSpacing(14)
        top = QHBoxLayout(); top.setContentsMargins(4,2,4,2); top.setSpacing(10)
        top.addWidget(QLabel("Масштаб:")); self.zoom = QSlider(Qt.Horizontal); self.zoom.setRange(50,200); self.zoom.setValue(self.ui_settings.zoom); self.zoom.setMaximumWidth(470); self.zoom.setMinimumWidth(250); self.zoom.valueChanged.connect(self._apply_zoom); top.addWidget(self.zoom)
        self.zoom_label=QLabel(f"{self.ui_settings.zoom}%"); self.zoom_label.setFixedWidth(52); top.addWidget(self.zoom_label)
        self.fullscreen_hint_label=QLabel("Esc - для полноэкранного режима"); self.fullscreen_hint_label.setStyleSheet("color:#6E6E73;font-weight:700;background:transparent;"); top.addWidget(self.fullscreen_hint_label); top.addStretch()
        self.sync_btn=QPushButton("Синхронизация"); self.sync_btn.setObjectName("GhostButton"); self.sync_btn.clicked.connect(self._sync_current_tab); top.addWidget(self.sync_btn)
        self.db_state=QLabel("БД: проверка…"); self.db_state.setObjectName("MutedLabel"); top.addWidget(self.db_state)
        self.theme_caption=QLabel("Светлая тема"); self.theme_caption.setStyleSheet("font-weight:800;background:transparent;"); top.addWidget(self.theme_caption)
        self.theme=AnimatedToggle(); self.theme.setChecked(self.ui_settings.theme=="dark"); self.theme.toggled.connect(self._theme_toggled); top.addWidget(self.theme)
        main.addLayout(top)
        self.tabs=QTabWidget();from .interaction_ui import FittingTabBar;self.tabs.setTabBar(FittingTabBar(self.tabs)); self.tabs.setUsesScrollButtons(True); self.tabs.setElideMode(Qt.ElideNone); self.tabs.tabBar().setExpanding(False); self.tabs.tabBar().setMinimumHeight(46); self.tabs.currentChanged.connect(self._tab_changed)
        self._loaded_tabs={0}; self._building_tab=False
        self._build_orders_tab()
        for title in ("Номенклатура","Сотрудники","Администрирование","О приложении ⍰"):
            self.tabs.addTab(QWidget(), title)
        if not self.can(Permission.CATALOG_VIEW): self.tabs.setTabEnabled(1,False)
        if not self.can(Permission.EMPLOYEES_VIEW): self.tabs.setTabEnabled(2,False)
        if not self.can(Permission.ADMIN_VIEW): self.tabs.setTabEnabled(3,False)
        main.addWidget(self.tabs,1); self.setCentralWidget(shell)
        self.setWindowTitle("SmartOrder - Формирование нарядов на сдельную работу")

    def keyPressEvent(self, event):
        if event.key()==Qt.Key_Escape:
            if self.isFullScreen(): self.showMaximized(); self.fullscreen_hint_label.setText("Esc - для полноэкранного режима")
            else: self.showFullScreen(); self.fullscreen_hint_label.setText("Esc - выйти из полноэкранного режима")
            return
        super().keyPressEvent(event)

    def _build_orders_tab(self):
        tab=QWidget(); self.orders_tab=tab; layout=QVBoxLayout(tab); layout.setContentsMargins(0,0,0,0); layout.setSpacing(10)
        header=QHBoxLayout(); header.setContentsMargins(18,6,6,0); header.setSpacing(10)
        left=QWidget(); left.setObjectName("OrderHeaderPlainPanel"); left.setMinimumHeight(142); left.setMaximumHeight(160); left.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Fixed)
        lv=QVBoxLayout(left); lv.setContentsMargins(20,8,12,10); lv.setSpacing(12)
        filters=QHBoxLayout(); filters.setSpacing(6)
        self.order_filter_date=SmartDateEdit(); self.order_filter_date.setDate(QDate.currentDate()); self.order_filter_date.dateChanged.connect(self.refresh_orders)
        self.order_filter_master=SmartComboBox(); self.order_filter_master.addItem("Все мастера",None)
        for r in self.db.get_employees(True): self.order_filter_master.addItem(str(r[1]),int(r[0]))
        self.order_filter_master.currentIndexChanged.connect(self.refresh_orders)
        self.order_filter_shift=SmartComboBox(); self.order_filter_shift.addItems(["Все смены","Ночная","Дневная"]); self.order_filter_shift.currentIndexChanged.connect(self.refresh_orders)
        self.order_filter_dep=SmartComboBox(); self.order_filter_dep.addItem("Все подразделения",None)
        for r in self.db.get_departments(): self.order_filter_dep.addItem(str(r[1]),int(r[0]))
        self.order_filter_dep.currentIndexChanged.connect(self.refresh_orders)
        labels=[("Дата наряда:",self.order_filter_date),("Мастер:",self.order_filter_master),("Смена:",self.order_filter_shift),("Подразделение:",self.order_filter_dep)]
        for i,(txt,w) in enumerate(labels):
            lab=QLabel(txt); lab.setStyleSheet("font-weight:800;background:transparent;"); filters.addWidget(lab); filters.addWidget(w); filters.addSpacing(8 if i<len(labels)-1 else 0)
        filters.addStretch(); lv.addLayout(filters)
        buttons=QHBoxLayout(); buttons.setSpacing(12)
        self.create_order_btn=QPushButton("Создать наряд"); self.create_order_btn.setObjectName("PrimaryButton"); self.create_order_btn.clicked.connect(self.create_order); self.create_order_btn.setVisible(self.can(Permission.ORDERS_CREATE)); buttons.addWidget(self.create_order_btn,1)
        self.edit_order_btn=QPushButton("Редактировать"); self.edit_order_btn.setObjectName("SecondaryButton"); self.edit_order_btn.clicked.connect(self.edit_order); self.edit_order_btn.setEnabled(False); self.edit_order_btn.setVisible(self.can(Permission.ORDERS_EDIT)); buttons.addWidget(self.edit_order_btn,1)
        self.export_order_btn=QPushButton("Выгрузить в EXCEL"); self.export_order_btn.setObjectName("SecondaryButton"); self.export_order_btn.clicked.connect(self.export_order); self.export_order_btn.setEnabled(False); self.export_order_btn.setVisible(self.can(Permission.ORDERS_EXPORT)); buttons.addWidget(self.export_order_btn,1)
        self.delete_draft_btn=QPushButton("Удалить черновик"); self.delete_draft_btn.setObjectName("DangerButton"); self.delete_draft_btn.clicked.connect(self.delete_selected_draft); self.delete_draft_btn.setEnabled(False); buttons.addWidget(self.delete_draft_btn,1)
        lv.addLayout(buttons); header.addWidget(left,1)
        self.info_panel=QWidget(); self.info_panel.setObjectName("GlassPanel"); self.info_panel.setMinimumWidth(270); self.info_panel.setMaximumWidth(300); self.info_panel.setMinimumHeight(112); self.info_panel.setMaximumHeight(132); self.info_panel.setSizePolicy(QSizePolicy.Fixed,QSizePolicy.Fixed)
        iv=QVBoxLayout(self.info_panel); iv.setContentsMargins(14,12,14,12); iv.setSpacing(6); title=QLabel("ИСТОРИЯ РЕДАКТИРОВАНИЙ"); title.setAlignment(Qt.AlignCenter); title.setStyleSheet("font-size:10pt;font-weight:800;color:#007AFF;background:transparent;"); iv.addWidget(title)
        self.info_users_list=QListWidget(); self.info_users_list.setMaximumHeight(92); self.info_users_list.setStyleSheet("QListWidget{border:none;background:transparent;font-size:9pt;}QListWidget::item{padding:2px;}"); self.info_users_list.itemDoubleClicked.connect(self._show_history_details); iv.addWidget(self.info_users_list,1); header.addWidget(self.info_panel,0); layout.addLayout(header)
        self.orders_table=QTableWidget(0,6); self.orders_table.setHorizontalHeaderLabels(["№","Дата наряда","Тип смены","Мастер","Подразделение","Дата регистрации"]); self.orders_table.setSelectionBehavior(QAbstractItemView.SelectRows); self.orders_table.setSelectionMode(QAbstractItemView.SingleSelection); self.orders_table.setMinimumHeight(540); self.orders_table.setMouseTracking(True); self.orders_table.setContextMenuPolicy(Qt.CustomContextMenu); self.orders_table.customContextMenuRequested.connect(self._orders_context_menu); self.orders_table.itemSelectionChanged.connect(self._order_selection_changed); self.orders_table.itemDoubleClicked.connect(lambda *_: self._open_selected())
        hh=self.orders_table.horizontalHeader(); hh.setMinimumSectionSize(115); hh.setFixedHeight(50); hh.setSectionResizeMode(QHeaderView.Interactive)
        for i,w in enumerate([120,170,145,260,260,220]): self.orders_table.setColumnWidth(i,w)
        self.orders_table.verticalHeader().setDefaultSectionSize(44); layout.addWidget(self.orders_table,1)

        # Keep the complete orders page inside a real viewport.  The zoom
        # control changes the application font, and Qt consequently grows
        # labels/combos according to their text.  Without a viewport the
        # header's fixed controls could force the page beyond the window
        # (especially at 150--200% or on a narrow monitor), which made the
        # right-hand history panel overlap the filters and table.  A
        # widget-resizable scroll area lets the page use all available space
        # at normal zoom while exposing horizontal/vertical scrollbars when
        # the requested zoom genuinely needs more room.
        scroll = QScrollArea()
        scroll.setObjectName("OrdersResponsiveScroll")
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        tab.setSizePolicy(QSizePolicy.MinimumExpanding, QSizePolicy.MinimumExpanding)
        scroll.setWidget(tab)
        self.orders_scroll = scroll
        self.tabs.addTab(scroll,"Наряд")

    def _draft_records(self):
        result=[]; masters={int(r[0]):str(r[1]) for r in self.db.get_employees(True)}; deps={int(r[0]):str(r[1]) for r in self.db.get_departments()}
        for p in local_drafts_dir().glob("*.json"):
            try:
                data=json.loads(p.read_text(encoding="utf-8")); date=str(data.get("order_date", "")); shift=str(data.get("shift_type", "")); mid=data.get("master_id"); did=data.get("department_id"); updated=str(data.get("updated_at", "")); label="Черновик"
                result.append((p,label,date,shift,masters.get(int(mid),"") if mid is not None else "",deps.get(int(did),"") if did is not None else "",updated))
            except Exception: pass
        return result

    def refresh_orders(self):
        if not hasattr(self,"orders_table"): return
        try:
            date=self.order_filter_date.date().toString("dd-MM-yyyy"); shift=source_text(self.order_filter_shift); shift=None if shift=="Все смены" else shift
            rows=self.db.list_orders(date=date,master_id=self.order_filter_master.currentData(),department_id=self.order_filter_dep.currentData(),shift=shift,limit=1500)
            display=[]
            for row in rows: display.append((int(row[0]),str(row[1]),str(row[2]),str(row[3]),str(row[4] or ""),str(row[5] or ""),str(row[6] or ""),False))
            for p,label,d,s,m,dep,upd in self._draft_records():
                if d and d!=date: continue
                if shift and s!=shift: continue
                mid=self.order_filter_master.currentData(); did=self.order_filter_dep.currentData()
                # draft names are already resolved; filters by ids are checked from payload
                try:
                    raw=json.loads(p.read_text(encoding="utf-8"))
                    if mid is not None and raw.get("master_id")!=mid: continue
                    if did is not None and raw.get("department_id")!=did: continue
                except Exception: pass
                display.insert(0,(str(p),label,d,s,m,dep,upd,True))
            self.orders_table.setUpdatesEnabled(False); self.orders_table.setRowCount(len(display))
            for r,rec in enumerate(display):
                ref,version,d,s,m,dep,reg,is_draft=rec; vals=[version,d.replace("-","."),s,m,dep,reg]
                for c,v in enumerate(vals): self.orders_table.setItem(r,c,make_item(v))
                self.orders_table.item(r,0).setData(Qt.UserRole,ref)
                if is_draft:
                    for c in range(6): self.orders_table.item(r,c).setForeground(QColor("#FF9500"))
            self.orders_table.setUpdatesEnabled(True); self._order_selection_changed()
        except Exception as exc:
            self.orders_table.setUpdatesEnabled(True); error(self,"Не удалось загрузить наряды",exc)

    def _selected_ref(self):
        row=self.orders_table.currentRow()
        if row<0:return None
        item=self.orders_table.item(row,0); return item.data(Qt.UserRole) if item else None

    def _selected_order_id(self):
        ref=self._selected_ref(); return ref if isinstance(ref,int) else None

    def _order_selection_changed(self):
        ref=self._selected_ref(); is_draft=isinstance(ref,str) and ref.lower().endswith(".json")
        self.edit_order_btn.setEnabled(bool(ref) and self.can(Permission.ORDERS_EDIT)); self.export_order_btn.setEnabled(isinstance(ref,int) and self.can(Permission.ORDERS_EXPORT)); self.delete_draft_btn.setEnabled(is_draft)
        self.info_users_list.clear()
        if isinstance(ref,int):
            try:
                for rec in self.db.order_history(ref):
                    txt=f"{rec['version']} · {rec['edited_by'] or 'Создан'}"
                    if rec['edit_date']: txt+=f" · {rec['edit_date']}"
                    item=QListWidgetItem(txt); item.setData(Qt.UserRole,rec); self.info_users_list.addItem(item)
            except Exception: pass
        elif is_draft: self.info_users_list.addItem("Локальный черновик текущего пользователя")

    def create_order(self):
        if not self.can(Permission.ORDERS_CREATE):return
        dlg=HeavyWorkOrderDialog(self.db,self.user,parent=self)
        if dlg.exec_()==QDialog.Accepted:
            data=dlg.get_data()
            try:
                oid=self.db.save_order(self.user,data["order_date"],data["shift_type"],data["master_id"],data["department_id"],data["lines"],data["comment"],separate_worker=bool(data.get("separate_worker",False))); dlg._delete_draft(); info(self,"Наряд",f"Наряд № {self.db.get_order(oid)['info']['version']} создан"); self.refresh_orders(); self._auto_backup("order_created")
            except Exception as exc:error(self,"Не удалось сохранить наряд",exc)
        else:self.refresh_orders()

    def edit_order(self):
        ref=self._selected_ref()
        if isinstance(ref,str): self._open_draft(Path(ref)); return
        order_id=ref if isinstance(ref,int) else None
        if not order_id or not self.can(Permission.ORDERS_EDIT):return
        if not self.db.is_latest_order(order_id):warn(self,"Редактирование","Редактировать можно только последнюю версию наряда");return
        token=None
        try:
            token,owner=self.db.acquire_edit_lock(order_id,self.user)
            if not token:warn(self,"Наряд уже редактируется",f"Пользователь: {owner.get('username')}\nКомпьютер: {owner.get('computer')}");return
            order=self.db.get_order(order_id); dlg=HeavyWorkOrderDialog(self.db,self.user,order=order,lock_token=token,parent=self)
            try:
                if dlg.exec_()==QDialog.Accepted:
                    data=dlg.get_data(); new_id=self.db.save_order(self.user,data["order_date"],data["shift_type"],data["master_id"],data["department_id"],data["lines"],data["comment"],parent_id=order_id,separate_worker=bool(data.get("separate_worker",False))); dlg._delete_draft(); info(self,"Наряд",f"Создана новая версия № {self.db.get_order(new_id)['info']['version']}"); self._auto_backup("order_edited")
            finally: dlg.stop_lock(); self.refresh_orders()
        except StaleOrderError as exc:warn(self,"Редактирование",str(exc))
        except Exception as exc:
            if token:
                try:self.db.release_edit_lock(order_id,token)
                except Exception:pass
            error(self,"Редактирование",exc)

    def view_order(self):
        oid=self._selected_order_id()
        if oid:
            order=self.db.get_order(oid)
            if order: HeavyWorkOrderDialog(self.db,self.user,order=order,view_only=True,parent=self).exec_()

    def export_order(self):
        oid=self._selected_order_id()
        if not oid or not self.can(Permission.ORDERS_EXPORT):return
        order=self.db.get_order(oid); suggested=f"Наряд_{order['info']['version']}_{order['info']['order_date'].replace('-','.')}.xlsx"; path,_=QFileDialog.getSaveFileName(self,"Сохранить наряд",suggested,"Excel (*.xlsx)")
        if not path:return
        try: result=export_order_xlsx(path,order); self.db.log_action(self.user.username,"Выгрузил","Наряд",str(order['info']['version']),str(result)); info(self,"Excel",f"Сохранено:\n{result}")
        except Exception as exc:error(self,"Ошибка экспорта",exc)

    def _open_selected(self):
        ref=self._selected_ref()
        if isinstance(ref,str):self._open_draft(Path(ref))
        elif isinstance(ref,int):self.view_order()

    def _open_draft(self,path:Path):
        try: payload=json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:error(self,"Черновик",exc);return
        dlg=HeavyWorkOrderDialog(self.db,self.user,parent=self); dlg.load_draft_payload(payload)
        if dlg.exec_()==QDialog.Accepted:
            data=dlg.get_data(); parent_id=payload.get("parent_order_id")
            try: oid=self.db.save_order(self.user,data["order_date"],data["shift_type"],data["master_id"],data["department_id"],data["lines"],data["comment"],parent_id=parent_id,separate_worker=bool(data.get("separate_worker",False))); path.unlink(missing_ok=True); dlg._delete_draft(); info(self,"Наряд",f"Наряд № {self.db.get_order(oid)['info']['version']} сохранён")
            except Exception as exc:error(self,"Наряд",exc)
        self.refresh_orders()

    def delete_selected_draft(self):
        ref=self._selected_ref()
        if not isinstance(ref,str):return
        if QMessageBox.question(self,"Удаление черновика","Удалить выбранный черновик?",QMessageBox.Yes|QMessageBox.No,QMessageBox.No)!=QMessageBox.Yes:return
        try:Path(ref).unlink(missing_ok=True);self.refresh_orders()
        except Exception as exc:error(self,"Черновик",exc)

    def _orders_context_menu(self,pos):
        if self.orders_table.itemAt(pos) is None:return
        self.orders_table.selectRow(self.orders_table.itemAt(pos).row()); ref=self._selected_ref(); menu=QMenu(self); a_open=menu.addAction("Открыть"); a_edit=menu.addAction("Редактировать"); a_export=menu.addAction("Выгрузить в Excel"); a_delete=menu.addAction("Удалить черновик"); a_history=menu.addAction("Посмотреть подробную историю"); a_export.setEnabled(isinstance(ref,int)); a_delete.setEnabled(isinstance(ref,str)); a_history.setEnabled(isinstance(ref,int)); act=menu.exec_(self.orders_table.viewport().mapToGlobal(pos))
        if act==a_open:self._open_selected()
        elif act==a_edit:self.edit_order()
        elif act==a_export:self.export_order()
        elif act==a_delete:self.delete_selected_draft()
        elif act==a_history:self._show_history_details()

    def _show_history_details(self,item=None):
        oid=self._selected_order_id()
        if not oid:return
        try: rows=self.db.order_history(oid)
        except Exception as exc:error(self,"История",exc);return
        dlg=QDialog(self);dlg.setWindowTitle("История редактирования наряда");dlg.resize(760,520);v=QVBoxLayout(dlg);title=QLabel("История редактирования");title.setObjectName("TitleLabel");v.addWidget(title);body=QTextEdit();body.setObjectName("HistoryTextEdit");body.setReadOnly(True);parts=[]
        for r in rows:
            parts.append(f"Версия: {r['version']}\nРедактор: {r['edited_by'] or 'Создан'}\nДата изменения: {r['edit_date'] or r['registration_date']}\n")
        body.setPlainText("\n".join(parts));v.addWidget(body,1);box=QDialogButtonBox(QDialogButtonBox.Close);box.rejected.connect(dlg.reject);box.button(QDialogButtonBox.Close).setText("Закрыть");v.addWidget(box);apply_apple_design(dlg,self.ui_settings.theme,self.ui_settings.zoom);dlg.exec_()

    # ----- heavy catalog -----
    def _build_catalog_tab(self):
        tab=QWidget(); layout=QVBoxLayout(tab); layout.setContentsMargins(10,8,10,8); layout.setSpacing(10)
        form=QHBoxLayout(); form.addWidget(QLabel("Наименование:")); self.work_name=QLineEdit(); self.work_name.setMinimumWidth(300); form.addWidget(self.work_name); form.addWidget(QLabel("Код работы:")); self.work_code=QLineEdit(); self.work_code.setMinimumWidth(150); form.addWidget(self.work_code); form.addWidget(QLabel("Стоимость:")); self.work_price=QLineEdit(); self.work_price.setMinimumWidth(130); form.addWidget(self.work_price)
        # setVisible(True) must only run on children of the page. A button in
        # an unattached layout would otherwise open as a separate window.
        add = QPushButton("Добавить", tab)
        add.setObjectName("PrimaryButton")
        add.clicked.connect(self.add_work_type)
        add.setVisible(self.can(Permission.CATALOG_CREATE))
        form.addWidget(add)
        imp = QPushButton("Загрузить из Excel", tab)
        imp.clicked.connect(self.import_work_types)
        imp.setVisible(self.can(Permission.CATALOG_IMPORT))
        form.addWidget(imp)
        layout.addLayout(form)
        search=QHBoxLayout(); search.addWidget(QLabel("Поиск:")); self.work_search=QLineEdit(); self.work_search.setPlaceholderText("Введите название или код работы"); self.work_search.textChanged.connect(self.refresh_work_types); search.addWidget(self.work_search); self.work_results_label=QLabel(); self.work_results_label.setObjectName("MutedLabel"); search.addWidget(self.work_results_label); search.addStretch(); layout.addLayout(search)
        self.work_table=QTableWidget(0,4); self.work_table.setHorizontalHeaderLabels(["Наименование","Код работы","Стоимость в рублях","Дата регистрации"]); self.work_table.setSelectionBehavior(QAbstractItemView.SelectRows); self.work_table.setSelectionMode(QAbstractItemView.SingleSelection); self.work_table.setEditTriggers(QAbstractItemView.NoEditTriggers); self.work_table.itemSelectionChanged.connect(self._heavy_work_selection); self.work_table.verticalHeader().setDefaultSectionSize(44); self.work_table.horizontalHeader().setFixedHeight(50); self.work_table.horizontalHeader().setSectionResizeMode(0,QHeaderView.Stretch); self.work_table.setColumnWidth(1,150); self.work_table.setColumnWidth(2,150); self.work_table.setColumnWidth(3,170); layout.addWidget(self.work_table,1); self.work_top=ScrollToTopButton(self.work_table)
        bottom=QHBoxLayout(); self.work_edit_btn=QPushButton("Редактировать"); self.work_edit_btn.setEnabled(False); self.work_edit_btn.clicked.connect(lambda:(self.work_name.setFocus(),self.work_save_btn.setEnabled(True))); bottom.addWidget(self.work_edit_btn); self.work_save_btn=QPushButton("Сохранить"); self.work_save_btn.setEnabled(False); self.work_save_btn.clicked.connect(self.edit_work_type); bottom.addWidget(self.work_save_btn); self.work_delete_btn=QPushButton("Удалить"); self.work_delete_btn.setObjectName("DangerButton"); self.work_delete_btn.setEnabled(False); self.work_delete_btn.clicked.connect(self.delete_work_type); bottom.addWidget(self.work_delete_btn); bottom.addStretch(); layout.addLayout(bottom)
        return tab

    def refresh_work_types(self):
        if not hasattr(self,"work_table"):return
        needle=self.work_search.text().strip().casefold().replace("ё","е"); all_rows=self.db.get_work_types(); rows=[r for r in all_rows if not needle or needle in (str(r[1])+" "+str(r[2])).casefold().replace("ё","е")]; self.work_table.setRowCount(len(rows))
        for i,r in enumerate(rows):
            vals=[r[1],r[2],fmt(r[3]),r[4]]
            for c,v in enumerate(vals):self.work_table.setItem(i,c,make_item(v))
            self.work_table.item(i,0).setData(Qt.UserRole,int(r[0]))
        self.work_results_label.setText(f"Найдено: {len(rows)} из {len(all_rows)}")

    def _heavy_work_selection(self):
        row=self.work_table.currentRow(); enabled=row>=0; self.work_edit_btn.setEnabled(enabled); self.work_delete_btn.setEnabled(enabled); self.work_save_btn.setEnabled(False)
        if enabled:self.work_name.setText(self.work_table.item(row,0).text());self.work_code.setText(self.work_table.item(row,1).text());self.work_price.setText(self.work_table.item(row,2).text())

    def edit_work_type(self):
        row=self.work_table.currentRow()
        if row<0:return
        try:self.db.update_work_type(self.user,int(self.work_table.item(row,0).data(Qt.UserRole)),self.work_name.text(),self.work_code.text(),self.work_price.text());self.refresh_work_types();self._clear_work_form();self.work_save_btn.setEnabled(False)
        except Exception as exc:error(self,"Номенклатура",exc)

    def delete_work_type(self):
        row=self.work_table.currentRow()
        if row<0:return
        if QMessageBox.question(self,"Удаление",f"Удалить работу «{self.work_table.item(row,0).text()}»?",QMessageBox.Yes|QMessageBox.No,QMessageBox.No)!=QMessageBox.Yes:return
        try:self.db.delete_work_type(self.user,int(self.work_table.item(row,0).data(Qt.UserRole)));self.refresh_work_types();self._clear_work_form()
        except Exception as exc:error(self,"Удаление",exc)

    # ----- heavy employees -----
    def _build_employees_tab(self):
        tab=QWidget(); layout=QVBoxLayout(tab); layout.setContentsMargins(10,8,10,8); layout.setSpacing(10)
        modes=QHBoxLayout(); self.mode_worker=QRadioButton("Работники"); self.mode_master=QRadioButton("Мастера"); self.mode_department=QRadioButton("Подразделения"); self.mode_worker.setChecked(True)
        for b in (self.mode_worker,self.mode_master,self.mode_department):b.toggled.connect(self.refresh_people);modes.addWidget(b)
        modes.addStretch();layout.addLayout(modes)
        form = QHBoxLayout()
        self.person_form_label = QLabel("ФИО:")
        form.addWidget(self.person_form_label)
        self.person_name = QLineEdit()
        form.addWidget(self.person_name)
        add = QPushButton("Добавить", tab)
        add.setObjectName("PrimaryButton")
        add.clicked.connect(self.add_person)
        add.setVisible(self.can(Permission.EMPLOYEES_CREATE))
        form.addWidget(add)
        imp = QPushButton("Загрузить из Excel", tab)
        imp.clicked.connect(self.import_people)
        imp.setVisible(self.can(Permission.EMPLOYEES_IMPORT))
        form.addWidget(imp)
        form.addStretch()
        layout.addLayout(form)
        search=QHBoxLayout(); search.addWidget(QLabel("Поиск:")); self.person_search=QLineEdit(); self.person_search.setPlaceholderText("Введите ФИО"); self.person_search.textChanged.connect(self.refresh_people); search.addWidget(self.person_search); self.people_results_label=QLabel("Найдено: 0"); self.people_results_label.setObjectName("MutedLabel"); search.addWidget(self.people_results_label); search.addStretch();layout.addLayout(search)
        self.people_table=QTableWidget(0,3); self.people_table.setHorizontalHeaderLabels(["ФИО / Название","Дата регистрации","Дата редактирования"]); self.people_table.setSelectionBehavior(QAbstractItemView.SelectRows); self.people_table.setSelectionMode(QAbstractItemView.SingleSelection); self.people_table.setEditTriggers(QAbstractItemView.NoEditTriggers); self.people_table.itemSelectionChanged.connect(self._heavy_people_selection); self.people_table.horizontalHeader().setFixedHeight(50); self.people_table.horizontalHeader().setSectionResizeMode(0,QHeaderView.Stretch); self.people_table.setColumnWidth(1,220); self.people_table.setColumnWidth(2,220); self.people_table.verticalHeader().setDefaultSectionSize(44);layout.addWidget(self.people_table,1);self.people_top=ScrollToTopButton(self.people_table)
        bottom=QHBoxLayout(); self.person_save_btn=QPushButton("Сохранить"); self.person_save_btn.setEnabled(False); self.person_save_btn.clicked.connect(self.edit_person); bottom.addWidget(self.person_save_btn); self.person_edit_btn=QPushButton("Редактировать"); self.person_edit_btn.setEnabled(False); self.person_edit_btn.clicked.connect(lambda:(self.person_name.setFocus(),self.person_save_btn.setEnabled(True))); bottom.addWidget(self.person_edit_btn); self.person_delete_btn=QPushButton("Удалить"); self.person_delete_btn.setObjectName("DangerButton"); self.person_delete_btn.setEnabled(False); self.person_delete_btn.clicked.connect(self.delete_person); bottom.addWidget(self.person_delete_btn); bottom.addStretch();layout.addLayout(bottom)
        for b in (self.mode_worker,self.mode_master,self.mode_department):b.toggled.connect(self._employee_mode_visual)
        return tab

    def _employee_mode_visual(self):
        dep=self.mode_department.isChecked();self.person_form_label.setText("Подразделение:" if dep else "ФИО:");self.person_name.setPlaceholderText("Введите название подразделения" if dep else "Введите ФИО");self.person_search.setPlaceholderText("Введите название" if dep else "Введите ФИО")

    def refresh_people(self):
        if not hasattr(self,"people_table"):return
        self._employee_mode_visual();mode=self._people_mode(); all_rows=self.db.get_departments() if mode=="department" else self.db.get_employees(mode=="master");needle=self.person_search.text().strip().casefold().replace("ё","е");rows=[r for r in all_rows if not needle or needle in str(r[1]).casefold().replace("ё","е")];self.people_table.setRowCount(len(rows))
        for i,r in enumerate(rows):
            reg=r[2] if mode=="department" else r[3];editd=(r[3] if mode=="department" else r[4]) or "";vals=[r[1],reg,editd]
            for c,v in enumerate(vals):self.people_table.setItem(i,c,make_item(v))
            self.people_table.item(i,0).setData(Qt.UserRole,int(r[0]))
        self.people_results_label.setText(f"Найдено: {len(rows)}")

    def _heavy_people_selection(self):
        row=self.people_table.currentRow();enabled=row>=0;self.person_edit_btn.setEnabled(enabled);self.person_delete_btn.setEnabled(enabled);self.person_save_btn.setEnabled(False)
        if enabled:self.person_name.setText(self.people_table.item(row,0).text())

    def edit_person(self):
        row=self.people_table.currentRow()
        if row<0:return
        ident=int(self.people_table.item(row,0).data(Qt.UserRole));name=self.person_name.text().strip()
        try:
            if self._people_mode()=="department":self.db.update_department(self.user,ident,name)
            else:self.db.update_employee(self.user,ident,name)
            self.refresh_people();self._refresh_reference_filters();self.person_save_btn.setEnabled(False)
        except Exception as exc:error(self,"Сотрудники",exc)

    def delete_person(self):
        row=self.people_table.currentRow()
        if row<0:return
        if QMessageBox.question(self,"Удаление",f"Удалить «{self.people_table.item(row,0).text()}»?",QMessageBox.Yes|QMessageBox.No,QMessageBox.No)!=QMessageBox.Yes:return
        ident=int(self.people_table.item(row,0).data(Qt.UserRole))
        try:
            if self._people_mode()=="department":self.db.delete_department(self.user,ident)
            else:self.db.delete_employee(self.user,ident)
            self.refresh_people();self._refresh_reference_filters()
        except Exception as exc:error(self,"Удаление",exc)

    # ----- heavy admin -----
    def _build_admin_tab(self):
        tab=QWidget(); layout=QVBoxLayout(tab); layout.setContentsMargins(10,8,10,8); layout.setSpacing(8)
        access=QCheckBox("Разрешительный режим (авторизация обязательна)");access.setChecked(self.db.is_access_control_enabled());access.setEnabled(True);access.toggled.connect(self._toggle_access_control);self.access_control_check=access;layout.addWidget(access)
        user_group=QGroupBox("Управление пользователями");uv=QVBoxLayout(user_group);self.users_table=QTableWidget(0,4);self.users_table.setHorizontalHeaderLabels(["Логин","Роль","Статус","Действия"]);self.users_table.setEditTriggers(QAbstractItemView.NoEditTriggers);self.users_table.horizontalHeader().setFixedHeight(44);self.users_table.horizontalHeader().setSectionResizeMode(0,QHeaderView.Stretch);self.users_table.setColumnWidth(1,170);self.users_table.setColumnWidth(2,120);self.users_table.setColumnWidth(3,360);self.users_table.setMinimumHeight(190);self.users_table.setMaximumHeight(260);uv.addWidget(self.users_table)
        ubr=QHBoxLayout();add=QPushButton("Добавить пользователя");add.setObjectName("PrimaryButton");add.clicked.connect(self.add_user);ubr.addWidget(add);perms=QPushButton("Права ролей…");perms.clicked.connect(self._open_permissions_dialog);ubr.addWidget(perms);ubr.addStretch();uv.addLayout(ubr);layout.addWidget(user_group)
        backup=QGroupBox("💾 Резервное копирование");backup.setObjectName("BackupGroup");bh=QHBoxLayout(backup);bcreate=QPushButton("📀 Создать бэкап");bcreate.clicked.connect(self.create_backup);brestore=QPushButton("🔄 Восстановить");brestore.clicked.connect(self.restore_backup);self.backup_combo=SmartComboBox();self.backup_combo.setMinimumWidth(200);bdelete=QPushButton("Удалить");bdelete.setObjectName("DangerButton");bdelete.clicked.connect(self.delete_backup);barchive=QPushButton("Архивный снимок");barchive.clicked.connect(self.create_archive_snapshot)
        for w in (bcreate,brestore,QLabel("Копии:"),self.backup_combo,bdelete,barchive):bh.addWidget(w)
        bh.addStretch();backup.setMaximumHeight(92);layout.addWidget(backup)
        audit_group=QGroupBox("Журнал действий");av=QVBoxLayout(audit_group);self.audit_table=QTableWidget(0,6);self.audit_table.setHorizontalHeaderLabels(["Дата/Время","Пользователь","Действие","Тип объекта","Объект","Детали"]);self.audit_table.setEditTriggers(QAbstractItemView.NoEditTriggers);self.audit_table.setSelectionBehavior(QAbstractItemView.SelectRows);self.audit_table.horizontalHeader().setFixedHeight(46);self.audit_table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive);self.audit_table.setColumnWidth(0,170);self.audit_table.setColumnWidth(1,150);self.audit_table.setColumnWidth(2,200);self.audit_table.setColumnWidth(3,145);self.audit_table.setColumnWidth(4,210);self.audit_table.horizontalHeader().setStretchLastSection(True);av.addWidget(self.audit_table,1);layout.addWidget(audit_group,1)
        return tab

    def refresh_users(self):
        if not hasattr(self,"users_table"):return
        rows=self.db.list_users();self.users_table.setRowCount(len(rows))
        for i,r in enumerate(rows):
            uid,username,role,active=int(r[0]),str(r[1]),str(r[2]),bool(r[3]);self.users_table.setItem(i,0,make_item(username,uid));self.users_table.setItem(i,1,make_item(role));self.users_table.setItem(i,2,make_item("Активен" if active else "Отключён"));w=QWidget();h=QHBoxLayout(w);h.setContentsMargins(2,2,2,2);e=QPushButton("Редактировать");t=QPushButton("Отключить" if active else "Включить");e.clicked.connect(lambda _,u=uid,n=username,rn=role:self._edit_user_by_id(u,n,rn));t.clicked.connect(lambda _,u=uid,a=active:self._toggle_user_by_id(u,a));h.addWidget(e);h.addWidget(t);self.users_table.setCellWidget(i,3,w);self.users_table.setRowHeight(i,56)

    def _edit_user_by_id(self,uid,username,role):
        dlg=UserDialog(username,role,False,self)
        if dlg.exec_()!=QDialog.Accepted:return
        try:self.db.update_user(self.user,uid,dlg.username.text(),dlg.selected_roles(),dlg.password.text());self.refresh_users()
        except Exception as exc:error(self,"Пользователь",exc)

    def _toggle_user_by_id(self,uid,active):
        try:self.db.set_user_active(self.user,uid,not active);self.refresh_users()
        except Exception as exc:error(self,"Пользователь",exc)

    def _open_permissions_dialog(self):
        dlg=QDialog(self);dlg.setWindowTitle("Права ролей");dlg.resize(680,650);v=QVBoxLayout(dlg);top=QHBoxLayout();top.addWidget(QLabel("Роль:"));role=SmartComboBox();role.addItems(ROLES);top.addWidget(role);top.addStretch();v.addLayout(top);lst=QListWidget();v.addWidget(lst,1)
        def refill():
            current=self.db.role_permissions(role.currentText());lst.clear()
            for code in ALL_PERMISSIONS:
                item=QListWidgetItem(PERMISSION_LABELS.get(code,code));item.setData(Qt.UserRole,code);item.setFlags(item.flags()|Qt.ItemIsUserCheckable);item.setCheckState(Qt.Checked if code in current else Qt.Unchecked);lst.addItem(item)
            lst.setEnabled(role.currentText()!="Администратор")
        role.currentTextChanged.connect(refill);refill();box=QDialogButtonBox(QDialogButtonBox.Save|QDialogButtonBox.Cancel);box.button(QDialogButtonBox.Save).setText("Сохранить");box.accepted.connect(dlg.accept);box.rejected.connect(dlg.reject);v.addWidget(box);apply_apple_design(dlg,self.ui_settings.theme,self.ui_settings.zoom)
        if dlg.exec_()==QDialog.Accepted and role.currentText()!="Администратор":
            perms=[lst.item(i).data(Qt.UserRole) for i in range(lst.count()) if lst.item(i).checkState()==Qt.Checked]
            try:self.db.set_role_permissions(self.user,role.currentText(),perms);info(self,"Права","Права роли сохранены. Применятся при следующем входе.")
            except Exception as exc:error(self,"Права",exc)

    def refresh_audit(self):
        if not hasattr(self,"audit_table"):return
        rows=self.db.recent_audit(200);self.audit_table.setRowCount(len(rows))
        for i,r in enumerate(rows):
            for c,v in enumerate(r):self.audit_table.setItem(i,c,make_item(v))
            self.audit_table.setRowHeight(i,42)

    # ----- about -----
    def _build_about_tab(self):
        tab=GifBackgroundWidget(["loading2.gif","login_background.gif","resources/loading2.gif"]);root=QVBoxLayout(tab);root.setContentsMargins(30,20,30,24);root.setSpacing(12);logo=QLabel();
        if _set_logo(logo,148,"smartorder_logo_icon_light.png","smartorder_logo_icon.png","smartorder_logo_white.png","smartorder_logo.png"):root.addWidget(logo,alignment=Qt.AlignCenter)
        edition=QLabel(f"Enterprise Edition · Version: {APP_VERSION}");edition.setAlignment(Qt.AlignCenter);edition.setStyleSheet("font-size:15px;color:#E5E7EB;background:transparent;");root.addWidget(edition)
        cards=QHBoxLayout();cards.setSpacing(18);system=QFrame();system.setObjectName("AboutTransparentCard");system.setStyleSheet("QFrame#AboutTransparentCard{background:rgba(0,0,0,0);border:1px solid rgba(255,255,255,110);border-radius:16px;}QFrame#AboutTransparentCard QLabel{background:transparent;color:white;}");sv=QVBoxLayout(system);st=QLabel("System");st.setStyleSheet("font-size:18px;font-weight:800;color:#0A84FF;background:transparent;");sv.addWidget(st);sv.addWidget(QLabel(f"Среда выполнения: Python\nДвижок: PyQt5 5.15.x\nЯдро: SmartOrder LiteCore\nVersion: {APP_VERSION}\n\nОбщая БД: {database_path()}\nСетевой корень: {network_root()}"));sv.addStretch();cards.addWidget(system,1)
        guide=QFrame();guide.setObjectName("AboutTransparentCard");guide.setStyleSheet(system.styleSheet());gv=QVBoxLayout(guide);gt=QLabel("Как работать в программе?");gt.setStyleSheet("font-size:18px;font-weight:800;color:#0A84FF;background:transparent;");gv.addWidget(gt);steps=["Заполните справочники: номенклатура, сотрудники, мастера, подразделения.","Во вкладке «Наряд» нажмите «Создать наряд».","Выберите дату, смену, мастера и подразделение.","Добавьте работников и работы.","Заполните часы, ФИКС или ФАКТ.","Сохраните наряд.","При необходимости откройте, отредактируйте или выгрузите наряд в Excel."]
        for idx,text in enumerate(steps,1):lab=QLabel(f"{idx}. {text}");lab.setWordWrap(True);lab.setStyleSheet("font-size:14px;background:transparent;color:white;");gv.addWidget(lab)
        gv.addStretch();cards.addWidget(guide,1);root.addLayout(cards,1);foot=QFrame();foot.setObjectName("AboutTransparentCard");foot.setStyleSheet(system.styleSheet());fv=QVBoxLayout(foot);p=QLabel("Powered by OITS&ZI");p.setAlignment(Qt.AlignCenter);p.setStyleSheet("font-weight:800;background:transparent;color:white;");fv.addWidget(p);c=QLabel("Copyright © 2026 tmbsir");c.setAlignment(Qt.AlignCenter);c.setStyleSheet("background:transparent;color:white;");fv.addWidget(c);root.addWidget(foot);return tab

    def _replace_tab(self,index,widget,title):
        current=self.tabs.currentIndex();self.tabs.blockSignals(True);self.tabs.removeTab(index);self.tabs.insertTab(index,widget,title);self.tabs.setCurrentIndex(index if current==index else current);self.tabs.blockSignals(False)

    def _tab_changed(self,index):
        if self._building_tab:return
        if index not in self._loaded_tabs:
            self._building_tab=True
            try:
                if index==1:self._replace_tab(1,self._build_catalog_tab(),"Номенклатура");self.refresh_work_types()
                elif index==2:self._replace_tab(2,self._build_employees_tab(),"Сотрудники");self.refresh_people()
                elif index==3:self._replace_tab(3,self._build_admin_tab(),"Администрирование");self.refresh_users();self.refresh_audit();self.refresh_backups()
                elif index==4:self._replace_tab(4,self._build_about_tab(),"О приложении ⍰")
                self._loaded_tabs.add(index);apply_apple_design(self,self.ui_settings.theme,self.ui_settings.zoom);self._fade_current_tab()
            finally:self._building_tab=False
        else:
            # Loaded tabs are pure UI switches. Do not hit SMB just because the user changes tabs.
            # Explicit Synchronization and successful CRUD operations refresh the relevant data.
            self._fade_current_tab()

    def _fade_current_tab(self):
        # RC6: whole-tab opacity effects are disabled because some Windows/Qt
        # builds can surface an empty helper window after idle.
        try:
            for name in ("_admin_db_hover_filter","_audit_help_hover_filter"):
                flt=getattr(self,name,None)
                if flt is not None:flt.hide_popup()
            w=self.tabs.currentWidget()
            if w is not None:w.update()
        except Exception:pass

    def _sync_current_tab(self):
        self.db.invalidate_cache();idx=self.tabs.currentIndex()
        if idx==0:self.refresh_orders()
        elif idx==1 and 1 in self._loaded_tabs:self.refresh_work_types()
        elif idx==2 and 2 in self._loaded_tabs:self.refresh_people();self._refresh_reference_filters()
        elif idx==3 and 3 in self._loaded_tabs:self.refresh_users();self.refresh_audit();self.refresh_backups()
        self._ping_async()

    def _theme_toggled(self,checked):
        self.ui_settings.theme="dark" if checked else "light";self.theme_caption.setText("Тёмная тема" if checked else "Светлая тема");self._apply_theme()

    def _apply_theme(self):
        apply_apple_design(self,self.ui_settings.theme,self.ui_settings.zoom)

    def _apply_zoom(self,value):
        value=max(50,min(200,int(value)));self.ui_settings.zoom=value
        if hasattr(self,"zoom_label"):self.zoom_label.setText(f"{value}%")
        app=QApplication.instance()
        if app is not None:
            base= getattr(app,"_smartorder_base_font",None)
            if base is None:
                base=QFont(app.font())
                if base.pointSizeF() <= 0: base.setPointSizeF(12.0)
                app._smartorder_base_font=QFont(base)
            font=QFont(base);font.setPointSizeF(max(8.0,base.pointSizeF()*value/100.0));app.setFont(font)
        apply_apple_design(self,self.ui_settings.theme,value)
        try:self.settings_store.save(self.ui_settings)
        except Exception:pass

    def _toggle_access_control(self, checked: bool):
        box=getattr(self,"access_control_check",None)
        if getattr(self,"_access_toggle_busy",False):
            return
        self._access_toggle_busy=True
        try:
            self.db.set_access_control(self.user,bool(checked))
            info(self,"Разрешительный режим",
                 "Авторизация будет обязательна при следующем запуске SmartOrder." if checked else
                 "Разрешительный режим выключен. При следующем запуске SmartOrder откроется без окна авторизации.")
        except Exception as exc:
            if box is not None:
                try:
                    box.blockSignals(True);box.setChecked(self.db.is_access_control_enabled());box.blockSignals(False)
                except Exception:pass
            error(self,"Разрешительный режим",exc)
        finally:
            self._access_toggle_busy=False

    def _ping_done(self,ok:bool,ms:float,message:str):
        self._ping_running=False
        if ok:
            if ms>300:self.db_state.setText(f"● БД доступна, медленный ответ · {ms:.0f} мс");self.db_state.setObjectName("DbStateSlow")
            elif ms>150:self.db_state.setText(f"● БД доступна · {ms:.0f} мс");self.db_state.setObjectName("DbStateSlow")
            else:self.db_state.setText(f"● БД доступна · {ms:.0f} мс");self.db_state.setObjectName("DbStateOk")
            self.db_state.setToolTip("Медиана трёх рабочих SQLite-запросов после отдельного SMB-прогрева.")
        else:self.db_state.setText("● БД недоступна");self.db_state.setObjectName("DbStateBad");self.db_state.setToolTip(message)
        self.db_state.style().unpolish(self.db_state);self.db_state.style().polish(self.db_state)

    def _refresh_reference_filters(self):
        if hasattr(self,"order_filter_master"):
            current=self.order_filter_master.currentData();self.order_filter_master.blockSignals(True);self.order_filter_master.clear();self.order_filter_master.addItem("Все мастера",None)
            for r in self.db.get_employees(True):self.order_filter_master.addItem(str(r[1]),int(r[0]))
            idx=self.order_filter_master.findData(current);self.order_filter_master.setCurrentIndex(idx if idx>=0 else 0);self.order_filter_master.blockSignals(False)
        if hasattr(self,"order_filter_dep"):
            current=self.order_filter_dep.currentData();self.order_filter_dep.blockSignals(True);self.order_filter_dep.clear();self.order_filter_dep.addItem("Все подразделения",None)
            for r in self.db.get_departments():self.order_filter_dep.addItem(str(r[1]),int(r[0]))
            idx=self.order_filter_dep.findData(current);self.order_filter_dep.setCurrentIndex(idx if idx>=0 else 0);self.order_filter_dep.blockSignals(False)

    def showEvent(self,event):
        super().showEvent(event);self.theme_caption.setText("Тёмная тема" if self.ui_settings.theme=="dark" else "Светлая тема");QTimer.singleShot(0,lambda:apply_apple_design(self,self.ui_settings.theme,self.ui_settings.zoom))



# ===========================================================================
# RC3 — Heavy UX compatibility layer on top of LiteCore
# ===========================================================================

def _theme_of(widget) -> tuple[str, int]:
    theme, zoom = "light", 100
    cur = widget
    for _ in range(8):
        if cur is None: break
        settings = getattr(cur, "ui_settings", None)
        if settings is not None:
            theme = getattr(settings, "theme", theme)
            zoom = getattr(settings, "zoom", zoom)
            break
        cur = cur.parent() if hasattr(cur, "parent") else None
    return theme, zoom


def _apply_modal_theme(dialog, parent=None):
    theme, zoom = _theme_of(parent or dialog.parent())
    apply_apple_design(dialog, theme, zoom)
    try:
        dialog.setProperty("theme", theme)
        set_theme_recursive(dialog, theme)
    except Exception:
        pass


def _friendly_error(exc) -> str:
    text = str(exc or "Неизвестная ошибка")
    low = text.lower()
    if "unique constraint failed: work_types.name" in low:
        return "Работа с таким наименованием уже существует."
    if "unique constraint failed: work_types.code" in low:
        return "Такой код работы уже используется."
    if "database is locked" in low or "database table is locked" in low:
        return "Общая база временно занята другим пользователем. Повторите действие через несколько секунд."
    if "foreign key constraint failed" in low:
        return "Эта запись уже используется в сохранённых данных и не может быть удалена без нарушения истории."
    return text


def _message(parent, icon, title, text, buttons=QMessageBox.Ok, default=QMessageBox.NoButton):
    box = QMessageBox(parent)
    box.setIcon(icon); box.setWindowTitle(str(title)); box.setText(str(text)); box.setStandardButtons(buttons)
    if default != QMessageBox.NoButton:
        box.setDefaultButton(default)
    _apply_modal_theme(box, parent)
    try:
        yes = box.button(QMessageBox.Yes)
        no = box.button(QMessageBox.No)
        if yes is not None: yes.setText("Да")
        if no is not None: no.setText("Нет")
    except Exception:
        pass
    result = box.exec_()
    return result


def info(parent, title: str, text: str):
    return _message(parent, QMessageBox.Information, title, text)


def warn(parent, title: str, text: str):
    return _message(parent, QMessageBox.Warning, title, text)


def error(parent, title: str, exc):
    return _message(parent, QMessageBox.Critical, title, _friendly_error(exc))


def question(parent, title: str, text: str, default=QMessageBox.No):
    return _message(parent, QMessageBox.Question, title, text, QMessageBox.Yes | QMessageBox.No, default)


# Make inherited Lite methods use the same readable themed dialogs.
_lite_ui.info = info
_lite_ui.warn = warn
_lite_ui.error = error


class HeavyUserDialog(QDialog):
    def __init__(self, username="", role="", require_password=True, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Создание нового пользователя" if require_password else "Редактирование пользователя")
        self.setModal(True)
        self.setMinimumWidth(430)
        self.setObjectName("ModalDialog")
        root = QVBoxLayout(self); root.setContentsMargins(22, 18, 22, 18); root.setSpacing(12)
        subtitle = QLabel("Заполните данные для нового пользователя" if require_password else "Измените данные пользователя")
        subtitle.setObjectName("UserDialogSubtitle"); subtitle.setProperty("fontRole", "subtitle")
        subtitle.setWordWrap(True); subtitle.setStyleSheet("font-weight:400;"); root.addWidget(subtitle)
        form = QFormLayout(); form.setHorizontalSpacing(14); form.setVerticalSpacing(10)
        self.username = QLineEdit(username); self.username.setPlaceholderText("Логин")
        self.password = QLineEdit(); self.password.setEchoMode(QLineEdit.Password)
        self.password.setPlaceholderText("Пароль" if require_password else "Оставьте пустым, чтобы не менять")
        self.role_list=QListWidget();self.role_list.setObjectName("UserRoleList");self.role_list.setSelectionMode(QAbstractItemView.NoSelection);self.role_list.setMaximumHeight(150)
        selected=set(split_roles(role))
        for name in ROLES:
            item=QListWidgetItem(name);item.setData(Qt.UserRole,name);item.setFlags(item.flags()|Qt.ItemIsUserCheckable);item.setCheckState(Qt.Checked if name in selected else Qt.Unchecked);self.role_list.addItem(item)
        form.addRow("Логин:", self.username); form.addRow("Пароль:", self.password); form.addRow("Роли:", self.role_list)
        root.addLayout(form)
        box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        box.button(QDialogButtonBox.Ok).setText("ОК"); box.button(QDialogButtonBox.Ok).setObjectName("PrimaryButton")
        box.button(QDialogButtonBox.Cancel).setText("Отмена")
        box.accepted.connect(self.accept); box.rejected.connect(self.reject); root.addWidget(box)
        _apply_modal_theme(self, parent)

    def selected_roles(self):
        values=[]
        for i in range(self.role_list.count()):
            item=self.role_list.item(i)
            if item.checkState()==Qt.Checked: values.append(str(item.data(Qt.UserRole)))
        return ";".join(values)


class _HeavyCheckListDialog(QDialog):
    def __init__(self, title: str, rows: list[tuple], formatter, parent=None):
        super().__init__(parent)
        self.rows = list(rows); self.formatter = formatter; self.selected_keys = set()
        self.setWindowTitle(title); self.setModal(True); self.resize(720, 610); self.setMinimumSize(560, 430)
        root = QVBoxLayout(self); root.setContentsMargins(16, 16, 16, 16); root.setSpacing(10)
        self.search = QLineEdit(); self.search.setPlaceholderText("Поиск..."); self.search.textChanged.connect(self._populate); root.addWidget(self.search)
        self.result_label = QLabel(); self.result_label.setObjectName("MutedLabel"); root.addWidget(self.result_label)
        self.list = QListWidget(); self.list.setMouseTracking(True); self.list.setSelectionMode(QAbstractItemView.NoSelection)
        self.list.itemClicked.connect(self._toggle); root.addWidget(self.list, 1)
        box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        box.button(QDialogButtonBox.Ok).setText("ОК"); box.button(QDialogButtonBox.Ok).setObjectName("PrimaryButton")
        box.button(QDialogButtonBox.Cancel).setText("Отмена")
        box.accepted.connect(self.accept); box.rejected.connect(self.reject); root.addWidget(box)
        self._populate(); _apply_modal_theme(self, parent)

    def _key(self, row): return row[0]

    def _toggle(self, item):
        key = item.data(Qt.UserRole)
        if key in self.selected_keys: self.selected_keys.remove(key); item.setCheckState(Qt.Unchecked)
        else: self.selected_keys.add(key); item.setCheckState(Qt.Checked)

    def _populate(self, *_):
        needle = self.search.text().strip().casefold().replace("ё", "е")
        self.list.blockSignals(True); self.list.clear(); shown = 0
        for row in self.rows:
            text = self.formatter(row)
            if needle and needle not in text.casefold().replace("ё", "е"): continue
            item = QListWidgetItem(text); item.setData(Qt.UserRole, self._key(row)); item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked if self._key(row) in self.selected_keys else Qt.Unchecked)
            self.list.addItem(item); shown += 1
        self.list.blockSignals(False); self.result_label.setText(f"Найдено: {shown} из {len(self.rows)}")

    def selected(self): return [r for r in self.rows if self._key(r) in self.selected_keys]


class EmployeeSelectionDialog(_HeavyCheckListDialog):
    def __init__(self, db, parent=None):
        rows = [(int(r[0]), str(r[1])) for r in db.get_employees(False)]
        super().__init__("Выбор работников", rows, lambda r: r[1], parent)


class WorkSelectionDialog(_HeavyCheckListDialog):
    def __init__(self, db, parent=None):
        rows = [(int(r[0]), str(r[1]), str(r[2]), float(r[3])) for r in db.get_work_types()]
        super().__init__("Выбор работ", rows, lambda r: f"{r[1]}   |   {r[2]}   |   {fmt(r[3])} руб.", parent)


class DateRangeDialog(QDialog):
    def __init__(self, start_date: QDate, end_date: QDate, parent=None):
        super().__init__(parent); self.setWindowTitle("Выбор периода"); self.setModal(True); self.setMinimumWidth(430)
        self._start = QDate(start_date) if start_date.isValid() else QDate.currentDate()
        self._end = QDate(end_date) if end_date.isValid() else QDate(self._start)
        if self._start > self._end: self._start, self._end = self._end, self._start
        self._waiting_for_end = False; self._formatted = []
        root = QVBoxLayout(self); root.setContentsMargins(10,10,10,10); root.setSpacing(8)
        self.hint = QLabel("Выберите начало и конец периода"); self.hint.setStyleSheet("font-weight:800;color:#007AFF;background:transparent;"); root.addWidget(self.hint)
        self.calendar = QCalendarWidget(self); self.calendar.setObjectName("Win10Calendar"); self.calendar.setGridVisible(False); self.calendar.setFirstDayOfWeek(Qt.Monday); self.calendar.setVerticalHeaderFormat(QCalendarWidget.NoVerticalHeader); self.calendar.setSelectedDate(self._start); self.calendar.clicked.connect(self._clicked); root.addWidget(self.calendar)
        self.period_label = QLabel(); self.period_label.setAlignment(Qt.AlignCenter); self.period_label.setStyleSheet("font-weight:800;color:#0785FF;background:transparent;"); root.addWidget(self.period_label)
        row = QHBoxLayout(); today=QPushButton("Сегодня"); reset=QPushButton("Сбросить"); cancel=QPushButton("Отмена"); choose=QPushButton("Выбрать"); choose.setObjectName("PrimaryButton")
        today.clicked.connect(self._today); reset.clicked.connect(self._today); cancel.clicked.connect(self.reject); choose.clicked.connect(self.accept)
        row.addWidget(today); row.addWidget(reset); row.addStretch(); row.addWidget(cancel); row.addWidget(choose); root.addLayout(row)
        self._refresh_marks()
        _apply_modal_theme(self, parent)
        from .liquid_style import style_range_calendar
        style_range_calendar(self.calendar, _theme_of(self)[0])

    def _clicked(self, date):
        if not self._waiting_for_end:
            self._start = QDate(date); self._end = QDate(date); self._waiting_for_end = True; self.hint.setText("Выберите конец периода")
        else:
            if date < self._start: self._end = QDate(self._start); self._start = QDate(date)
            else: self._end = QDate(date)
            self._waiting_for_end = False; self.hint.setText("Выберите начало и конец периода")
        self._refresh_marks()

    def _today(self):
        d=QDate.currentDate(); self._start=QDate(d); self._end=QDate(d); self._waiting_for_end=False; self.calendar.setSelectedDate(d); self.hint.setText("Выберите начало и конец периода"); self._refresh_marks()

    def _refresh_marks(self):
        blank=QTextCharFormat()
        for d in self._formatted: self.calendar.setDateTextFormat(d, blank)
        self._formatted=[]; s,e=self.selected_range(); d=QDate(s); theme,_=_theme_of(self); dark=theme=="dark"
        while d<=e and len(self._formatted)<1500:
            f=QTextCharFormat()
            if d==s or d==e: f.setBackground(QBrush(QColor("#0785FF"))); f.setForeground(QBrush(QColor("#FFFFFF"))); f.setFontWeight(QFont.Bold)
            else: f.setBackground(QBrush(QColor("#234B73" if dark else "#D9EDFF"))); f.setForeground(QBrush(QColor("#E7F2FF" if dark else "#102B50")))
            self.calendar.setDateTextFormat(d,f); self._formatted.append(QDate(d)); d=d.addDays(1)
        txt=s.toString("dd.MM.yyyy") if s==e else f"{s.toString('dd.MM.yyyy')} - {e.toString('dd.MM.yyyy')}"; self.period_label.setText("Период: "+txt)

    def selected_range(self):
        s,e=QDate(self._start),QDate(self._end); return (e,s) if s>e else (s,e)


class DateRangeEdit(QLineEdit):
    dateChanged = pyqtSignal()
    def __init__(self, parent=None):
        super().__init__(parent); self.setObjectName("Win10DateRangeEdit"); self.setReadOnly(True); self.setCursor(Qt.PointingHandCursor); self.setMouseTracking(True); self.setMinimumWidth(280); self.setTextMargins(0,0,48,0); self._start_date=QDate.currentDate(); self._end_date=QDate.currentDate(); self._hover=False; self._update_text()
    def startDate(self): return QDate(self._start_date)
    def endDate(self): return QDate(self._end_date)
    def date(self): return QDate(self._start_date)
    def setDate(self,d): self.setDateRange(d,d)
    def setDateRange(self,start,end,emit=True):
        start,end=QDate(start),QDate(end)
        if start>end:start,end=end,start
        changed=start!=self._start_date or end!=self._end_date; self._start_date=QDate(start);self._end_date=QDate(end);self._update_text()
        if emit and changed:self.dateChanged.emit()
    def _update_text(self): self.setText(self._start_date.toString("dd.MM.yyyy") if self._start_date==self._end_date else f"{self._start_date.toString('dd.MM.yyyy')} - {self._end_date.toString('dd.MM.yyyy')}")
    def _icon_rect(self): return QRect(self.width()-44,3,38,max(28,self.height()-6))
    def mousePressEvent(self,event):
        if event.button()==Qt.LeftButton:
            dlg=DateRangeDialog(self._start_date,self._end_date,self.window())
            if dlg.exec_()==QDialog.Accepted:self.setDateRange(*dlg.selected_range())
            event.accept();return
        super().mousePressEvent(event)
    def mouseMoveEvent(self,event): self._hover=self._icon_rect().contains(event.pos());self.update();super().mouseMoveEvent(event)
    def leaveEvent(self,event): self._hover=False;self.update();super().leaveEvent(event)
    def paintEvent(self,event):
        super().paintEvent(event);p=QPainter(self);p.setRenderHint(QPainter.Antialiasing);r=self._icon_rect();theme,_=_theme_of(self);p.setPen(Qt.NoPen);p.setBrush(QColor(10,132,255,62 if self._hover else 30));p.drawRoundedRect(r,4,4);p.setPen(QColor("#F5F5F7" if theme=="dark" else "#1D1D1F"));x=r.x()+r.width()//2-9;y=r.y()+r.height()//2-9;p.drawRoundedRect(QRect(x,y+3,18,16),2,2);p.drawLine(x,y+8,x+18,y+8);p.drawLine(x+5,y,x+5,y+5);p.drawLine(x+13,y,x+13,y+5)


class RC3WorkOrderDialog(HeavyWorkOrderDialog):
    HEADERS = ["ФИО\nработника","Часы\nработы","Работы","Код\nработы","Стоимость\nв рублях","ФИКС\nКол-во коробок","ФИКС\nВес коробок кг.","ФИКС\nИтоговый вес","ФИКС\nОплата","ФАКТ\nчасы/кг/шт.","Оплата"]
    MANUAL = {1,5,6,9}
    TOTAL_COLS = (5,6,7,8,9,10)

    def _build(self):
        self.setObjectName("WorkOrderDialog"); layout=QVBoxLayout(self);layout.setContentsMargins(16,14,16,14);layout.setSpacing(9)
        if self.order is not None and not self.view_only:
            banner = QFrame(self)
            banner.setObjectName("EditModeBanner")
            banner_layout = QHBoxLayout(banner)
            banner_layout.setContentsMargins(10, 2, 10, 2)
            label = QLabel("В режиме редактирования", banner)
            label.setObjectName("EditModeLabel")
            banner_layout.addWidget(label)
            layout.addWidget(banner, 0, Qt.AlignRight)
        info_group=QGroupBox("Информация о наряде");info_group.setObjectName("OrderInfoGroup");form=QFormLayout(info_group);form.setContentsMargins(14,24,14,14);form.setVerticalSpacing(10)
        self.order_date=SmartDateEdit();self.order_date.setDate(QDate.currentDate());self.order_date.setMinimumWidth(250)
        self.shift=SmartComboBox();self.shift.setObjectName("ShiftTypeComboV31");self.shift.setMinimumWidth(470);self.shift.addItems(["Ночная","Дневная"]);self.shift.view().setMinimumWidth(540)
        self.master=SmartComboBox();self.master.setMinimumWidth(390);self.master.view().setMinimumWidth(430)
        for row in self.db.get_employees(True):self.master.addItem(str(row[1]),int(row[0]))
        self.department=SmartComboBox();self.department.setMinimumWidth(390);self.department.view().setMinimumWidth(430)
        for row in self.db.get_departments():self.department.addItem(str(row[1]),int(row[0]))
        self.comment=QLineEdit();self.comment.setPlaceholderText("Комментарий")
        self.separate_worker_check=QCheckBox("Отдельный работник")
        self.separate_worker_check.toggled.connect(lambda *_:(self._normalize_employee_display(),self._refresh_totals()))
        for label,w in (("Дата наряда:",self.order_date),("Тип смены:",self.shift),("Мастер:",self.master),("Подразделение:",self.department),("Комментарий:",self.comment)):form.addRow(label,w)
        form.addRow("",self.separate_worker_check)
        layout.addWidget(info_group)
        self.table=QTableWidget(0,11);self.table.setHorizontalHeaderLabels(self.HEADERS);self.table.setSelectionBehavior(QAbstractItemView.SelectItems);self.table.setSelectionMode(QAbstractItemView.ExtendedSelection);self.table.setAlternatingRowColors(True);self.table.verticalHeader().setVisible(False);self.table.horizontalHeader().setDefaultAlignment(Qt.AlignCenter);self.table.horizontalHeader().setFixedHeight(64);self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        widths=[270,120,360,150,150,165,175,175,150,180,150]
        for i,w in enumerate(widths):self.table.setColumnWidth(i,w)
        self.table.setEditTriggers(QAbstractItemView.DoubleClicked|QAbstractItemView.SelectedClicked|QAbstractItemView.EditKeyPressed);self.table.itemClicked.connect(self._edit_clicked_cell);self.table.itemChanged.connect(self._on_cell_changed);layout.addWidget(self.table,1)
        controls=QHBoxLayout();controls.setSpacing(10);self.add_employee_btn=QPushButton("Добавить работников");self.add_work_btn=QPushButton("Добавить работы");self.delete_row_btn=QPushButton("Удалить выбранных");self.delete_row_btn.setObjectName("DangerButton");self.add_employee_btn.clicked.connect(self._add_employees);self.add_work_btn.clicked.connect(self._add_works);self.delete_row_btn.clicked.connect(self._delete_rows);controls.addWidget(self.add_employee_btn);controls.addWidget(self.add_work_btn);controls.addWidget(self.delete_row_btn);controls.addStretch();layout.addLayout(controls)
        self.scroll_top=ScrollToTopButton(self.table)
        box=QDialogButtonBox(QDialogButtonBox.Ok|QDialogButtonBox.Cancel);box.button(QDialogButtonBox.Ok).setText("Сохранить");box.button(QDialogButtonBox.Ok).setObjectName("PrimaryButton");box.button(QDialogButtonBox.Cancel).setText("Отмена");box.accepted.connect(self._accept);box.rejected.connect(self.reject);self.button_box=box;layout.addWidget(box)

    def _ensure_row(self,row):
        while self.table.rowCount()<=row:self.table.insertRow(self.table.rowCount())
        for c in range(11):
            if self.table.item(row,c) is None:self.table.setItem(row,c,make_item("",editable=c in self.MANUAL))
        self._apply_flags(row)

    def _apply_flags(self,row):
        total=self._is_total(row)
        for c in range(11):
            item=self.table.item(row,c)
            if item is None: item=make_item("");self.table.setItem(row,c,item)
            flags=item.flags()|Qt.ItemIsEnabled|Qt.ItemIsSelectable
            if total or c not in self.MANUAL or self.view_only:flags&=~Qt.ItemIsEditable
            else:flags|=Qt.ItemIsEditable
            item.setFlags(flags)

    def _line_from_row(self,row):
        def text(c):
            i=self.table.item(row,c);return i.text().strip() if i else ""
        def role(c):
            i=self.table.item(row,c);return i.data(Qt.UserRole) if i else None
        from .domain import OrderLine
        return OrderLine(employee_id=role(0),employee_name=text(0),work_type_id=role(2),work_name=text(2),work_code=text(3),price=dec(text(4)),hours=dec(text(1)),fixed_boxes=dec(text(5)),fixed_weight=dec(text(6)),actual_value=dec(text(9)))

    def _write_calculated(self,row,line):
        self.table.blockSignals(True)
        try:
            self._ensure_row(row);self.table.item(row,7).setText(fmt(line.fixed_total));self.table.item(row,8).setText(fmt(line.fixed_payment,2));self.table.item(row,10).setText(fmt(line.actual_payment,2));self._apply_flags(row)
        finally:self.table.blockSignals(False)

    def _on_cell_changed(self,item):
        if self._cell_busy or self.view_only or self._is_total(item.row()):return
        self._cell_busy=True
        try:
            if item.column() in self.MANUAL and item.text().strip():
                normalized=item.text().strip().replace(",", ".")
                if dec(normalized) is not None:
                    self.table.blockSignals(True);item.setText(normalized);self.table.blockSignals(False)
            self._write_calculated(item.row(),self._line_from_row(item.row()));self._refresh_totals()
        finally:self._cell_busy=False

    def _edit_clicked_cell(self,item):
        if self.view_only or self._is_total(item.row()) or item.column() not in self.MANUAL:return
        QTimer.singleShot(0,lambda i=item:self.table.editItem(i))

    def _special_department(self):
        text=self.department.currentText().casefold().replace("ё","е")
        return "студент" in text or "сдель" in text or ("отдельн" in text and "работник" in text)

    def _refresh_totals(self):
        if getattr(self,"_rc3_totals_busy",False):return
        self._rc3_totals_busy=True
        try:
            self._remove_totals()
            for r in range(self.table.rowCount()):
                if any(self.table.item(r,c) and (self.table.item(r,c).text().strip() or self.table.item(r,c).data(Qt.UserRole) is not None) for c in range(11)):
                    self._ensure_row(r);self._write_calculated(r,self._line_from_row(r))
            if self.table.rowCount()==0:self.table.insertRow(0);self._ensure_row(0);return
            groups=[]
            for r in range(self.table.rowCount()):
                if self._is_total(r):continue
                line=self._line_from_row(r)
                if not line.employee_name and line.employee_id is None and line.work_type_id is None:continue
                key=(line.employee_id,line.employee_name)
                if not groups or groups[-1][0]!=key:groups.append([key,[]])
                groups[-1][1].append(r)
            sums={c:Decimal("0") for c in self.TOTAL_COLS};has={c:False for c in self.TOTAL_COLS}
            def n(r,c):return dec(self.table.item(r,c).text() if self.table.item(r,c) else "")
            for _,rows in groups:
                for r in rows:
                    for c in self.TOTAL_COLS:
                        v=n(r,c)
                        if v is not None:sums[c]+=v;has[c]=True
            self.table.blockSignals(True)
            try:
                # Individual subtotals for Heavy special departments, and whenever one employee has several works.
                for (key,rows) in reversed(groups):
                    if not (self._special_department() or len(rows)>1):continue
                    pos=max(rows)+1;self.table.insertRow(pos)
                    for c in range(11):self.table.setItem(pos,c,make_item(""))
                    name=key[1] or "Сотруднику";self.table.item(pos,0).setText(f"ИТОГО по {name}:")
                    for c in self.TOTAL_COLS:
                        vals=[n(r,c) for r in rows];vals=[v for v in vals if v is not None]
                        if vals:self.table.item(pos,c).setText(fmt(sum(vals,Decimal("0")),2 if c in {8,10} else 4))
                    self._apply_flags(pos)
                pos=self.table.rowCount();self.table.insertRow(pos)
                for c in range(11):self.table.setItem(pos,c,make_item(""))
                self.table.item(pos,0).setText("ИТОГО:")
                for c in self.TOTAL_COLS:
                    if has[c]:self.table.item(pos,c).setText(fmt(sums[c],2 if c in {8,10} else 4))
                self._apply_flags(pos)
            finally:self.table.blockSignals(False)
        finally:self._rc3_totals_busy=False

    def _add_employees(self):
        dlg=EmployeeSelectionDialog(self.db,self)
        if dlg.exec_()!=QDialog.Accepted:return
        selected=dlg.selected()
        if not selected:return
        self._remove_totals();existing={(self.table.item(r,0).data(Qt.UserRole) if self.table.item(r,0) else None) for r in range(self.table.rowCount())}
        first=None;self.table.blockSignals(True)
        try:
            # reuse one empty initial row
            for emp_id,name in selected:
                if emp_id in existing:continue
                reuse=next((r for r in range(self.table.rowCount()) if all(not (self.table.item(r,c) and (self.table.item(r,c).text().strip() or self.table.item(r,c).data(Qt.UserRole) is not None)) for c in range(11))),None)
                row=reuse if reuse is not None else self.table.rowCount();self._ensure_row(row);self.table.setItem(row,0,make_item(name,emp_id));self._apply_flags(row);existing.add(emp_id);first=row if first is None else first
        finally:self.table.blockSignals(False)
        self._refresh_totals()
        if first is not None:self.table.setCurrentCell(first,0);self.table.selectRow(first)

    def _target_employee(self):
        row=self.table.currentRow()
        candidates=list(range(max(0,row),-1,-1)) if row>=0 else []
        candidates += [r for r in range(self.table.rowCount()) if r not in candidates]
        for r in candidates:
            if self._is_total(r):continue
            item=self.table.item(r,0)
            if item and (item.data(Qt.UserRole) is not None or item.text().strip()):return r,item.data(Qt.UserRole),item.text().strip()
        return None,None,""

    def _add_works(self):
        target,emp_id,emp_name=self._target_employee()
        if target is None:
            warn(self,"Работы","Сначала добавьте хотя бы одного работника.");return
        dlg=WorkSelectionDialog(self.db,self)
        if dlg.exec_()!=QDialog.Accepted:return
        selected=dlg.selected()
        if not selected:return
        self._remove_totals()
        # Identify all current rows belonging to this employee.
        rows=[]
        for r in range(self.table.rowCount()):
            i=self.table.item(r,0)
            if i and ((emp_id is not None and i.data(Qt.UserRole)==emp_id) or (emp_id is None and i.text().strip()==emp_name)):rows.append(r)
        existing={self.table.item(r,2).data(Qt.UserRole) for r in rows if self.table.item(r,2)}
        insert_at=max(rows)+1 if rows else self.table.rowCount();reusable=next((r for r in rows if not (self.table.item(r,2) and self.table.item(r,2).text().strip())),None)
        self.table.blockSignals(True)
        try:
            for work_id,name,code,price in selected:
                if work_id in existing:continue
                row=reusable if reusable is not None else insert_at
                if reusable is None:self.table.insertRow(row);insert_at+=1
                reusable=None;self._ensure_row(row);self.table.setItem(row,0,make_item(emp_name,emp_id));self.table.setItem(row,2,make_item(name,work_id));self.table.setItem(row,3,make_item(code));self.table.setItem(row,4,make_item(fmt(price)));self._apply_flags(row);existing.add(work_id)
        finally:self.table.blockSignals(False)
        self._refresh_totals();self.table.setCurrentCell(target,0)

    def _delete_rows(self):
        rows=sorted({i.row() for i in self.table.selectedIndexes() if not self._is_total(i.row())},reverse=True)
        if not rows:return
        self.table.blockSignals(True)
        try:
            for r in rows:self.table.removeRow(r)
        finally:self.table.blockSignals(False)
        self._refresh_totals()

    def _load_order(self,order):
        info_data=order["info"]
        d=QDate.fromString(str(info_data.get("order_date","")),"dd-MM-yyyy")
        if d.isValid():self.order_date.setDate(d)
        self.shift.setCurrentText(str(info_data.get("shift_type","")));self._set_combo_data(self.master,info_data.get("master_id"));self._set_combo_data(self.department,info_data.get("department_id"));self.comment.setText(str(info_data.get("comment","") or ""))
        self.table.blockSignals(True)
        try:
            self.table.setRowCount(0)
            for line in order.get("lines",[]):
                row=self.table.rowCount();self.table.insertRow(row);self._ensure_row(row);self.table.setItem(row,0,make_item(line.employee_name,line.employee_id));self.table.item(row,1).setText(fmt(line.hours));self.table.setItem(row,2,make_item(line.work_name,line.work_type_id));self.table.setItem(row,3,make_item(line.work_code));self.table.setItem(row,4,make_item(fmt(line.price)));self.table.item(row,5).setText(fmt(line.fixed_boxes));self.table.item(row,6).setText(fmt(line.fixed_weight));self.table.item(row,9).setText(fmt(line.actual_value));self._write_calculated(row,line);self._apply_flags(row)
        finally:self.table.blockSignals(False)
        self._refresh_totals()

    def load_draft_payload(self,payload:dict):
        d=QDate.fromString(str(payload.get("order_date","")),"dd-MM-yyyy")
        if d.isValid():self.order_date.setDate(d)
        self.shift.setCurrentText(str(payload.get("shift_type","Ночная")));self._set_combo_data(self.master,payload.get("master_id"));self._set_combo_data(self.department,payload.get("department_id"));self.comment.setText(str(payload.get("comment","") or ""));self.table.setRowCount(0)
        from .domain import OrderLine
        for raw in payload.get("lines",[]):
            line=OrderLine(employee_id=raw.get("employee_id"),employee_name=str(raw.get("employee_name","") or ""),work_type_id=raw.get("work_type_id"),work_name=str(raw.get("work_name","") or ""),work_code=str(raw.get("work_code","") or ""),price=dec(raw.get("price")),hours=dec(raw.get("hours")),fixed_boxes=dec(raw.get("fixed_boxes")),fixed_weight=dec(raw.get("fixed_weight")),actual_value=dec(raw.get("actual_value")))
            row=self.table.rowCount();self.table.insertRow(row);self._ensure_row(row);self.table.setItem(row,0,make_item(line.employee_name,line.employee_id));self.table.item(row,1).setText(fmt(line.hours));self.table.setItem(row,2,make_item(line.work_name,line.work_type_id));self.table.setItem(row,3,make_item(line.work_code));self.table.setItem(row,4,make_item(fmt(line.price)));self.table.item(row,5).setText(fmt(line.fixed_boxes));self.table.item(row,6).setText(fmt(line.fixed_weight));self.table.item(row,9).setText(fmt(line.actual_value));self._write_calculated(row,line)
        self._refresh_totals()

    def _validate(self):
        data=self.get_data()
        if data["master_id"] is None:return "Не выбран мастер"
        if data["department_id"] is None:return "Не выбрано подразделение"
        if not data["lines"]:return "В наряде нет работ"
        for i,line in enumerate(data["lines"],1):
            for label,val in (("часы",line.hours),("количество коробок",line.fixed_boxes),("вес коробок",line.fixed_weight),("ФАКТ",line.actual_value)):
                if val is not None and val<0:return f"Строка {i}: поле «{label}» не может быть отрицательным"
        return None


class ArchiveSnapshotsDialog(QDialog):
    def __init__(self, db: Database, parent=None):
        super().__init__(parent);self.db=db;self.setWindowTitle("Архивные снимки SmartOrder");self.resize(980,620)
        root=QVBoxLayout(self);explain=QLabel("Архивный снимок — это отдельная неизменяемая копия общей БД на конкретный момент времени. Он нужен для просмотра старых состояний без восстановления рабочей базы.");explain.setWordWrap(True);explain.setObjectName("MutedLabel");root.addWidget(explain)
        self.table=QTableWidget(0,4);self.table.setHorizontalHeaderLabels(["Дата","Период","Файл","Размер"]);self.table.setSelectionBehavior(QAbstractItemView.SelectRows);self.table.setSelectionMode(QAbstractItemView.SingleSelection);self.table.setEditTriggers(QAbstractItemView.NoEditTriggers);self.table.verticalHeader().setVisible(False);self.table.horizontalHeader().setSectionResizeMode(2,QHeaderView.Stretch);root.addWidget(self.table,1)
        row=QHBoxLayout();open_btn=QPushButton("Открыть снимок");open_btn.setObjectName("PrimaryButton");open_btn.clicked.connect(self._open);refresh=QPushButton("Обновить");refresh.clicked.connect(self.refresh);close=QPushButton("Закрыть");close.clicked.connect(self.reject);row.addWidget(open_btn);row.addWidget(refresh);row.addStretch();row.addWidget(close);root.addLayout(row);self.refresh();QTimer.singleShot(0,lambda:_apply_modal_theme(self,parent))
    def refresh(self):
        files=sorted(shared_dirs()["archives"].rglob("*.db"),key=lambda p:p.stat().st_mtime if p.exists() else 0,reverse=True);self.table.setRowCount(len(files))
        for r,p in enumerate(files):
            try:stamp=datetime.fromtimestamp(p.stat().st_mtime).strftime("%d.%m.%Y %H:%M:%S");size=f"{p.stat().st_size/1024/1024:.2f} МБ"
            except Exception:stamp="";size=""
            period=p.parent.name if p.parent!=shared_dirs()["archives"] else "—";vals=[stamp,period,p.name,size]
            for c,v in enumerate(vals):self.table.setItem(r,c,make_item(v))
            self.table.item(r,0).setData(Qt.UserRole,str(p))
    def _open(self):
        r=self.table.currentRow()
        if r<0:return
        path=Path(self.table.item(r,0).data(Qt.UserRole))
        try:rows=self.db.read_archive_orders(path)
        except Exception as exc:error(self,"Архив",exc);return
        dlg=QDialog(self);dlg.setWindowTitle(f"Архив: {path.name}");dlg.resize(1100,650);v=QVBoxLayout(dlg);t=QTableWidget(len(rows),6);t.setHorizontalHeaderLabels(["№","Дата наряда","Смена","Мастер","Подразделение","Дата регистрации"]);t.setEditTriggers(QAbstractItemView.NoEditTriggers);t.setSelectionBehavior(QAbstractItemView.SelectRows);t.verticalHeader().setVisible(False);t.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        for i,row in enumerate(rows):
            for c,val in enumerate(row):t.setItem(i,c,make_item(val))
        v.addWidget(t,1);box=QDialogButtonBox(QDialogButtonBox.Close);box.button(QDialogButtonBox.Close).setText("Закрыть");box.rejected.connect(dlg.reject);v.addWidget(box);_apply_modal_theme(dlg,self);dlg.exec_()


class RC3MainWindow(HeavyMainWindow):
    def _build(self):
        self._session_started=time.monotonic();self._last_ping=(False,0.0,"Проверка...")
        self.setObjectName("SmartOrderWindow");self.setAttribute(Qt.WA_StyledBackground,True);shell=QWidget();shell.setObjectName("AppShell");main=QVBoxLayout(shell);main.setContentsMargins(16,14,16,12);main.setSpacing(14)
        zoom_label = QLabel("Масштаб:")
        self.zoom = QSlider(Qt.Horizontal)
        self.zoom.setRange(50, 200)
        self.zoom.setValue(self.ui_settings.zoom)
        self.zoom.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.zoom.setMinimumWidth(150)
        self.zoom.setMaximumWidth(520)
        self.zoom.valueChanged.connect(self._apply_zoom)
        self.zoom_label = QLabel(f"{self.ui_settings.zoom}%")
        self.zoom_label.setMinimumWidth(52)
        self.zoom_label.setAlignment(Qt.AlignCenter)
        self.fullscreen_hint_label = QLabel("Esc - для полноэкранного режима")
        self.fullscreen_hint_label.setWordWrap(False)
        self.fullscreen_hint_label.setStyleSheet("color:#6E6E73;font-weight:700;background:transparent;")
        self.theme_caption = QLabel("Светлая тема")
        self.theme_caption.setWordWrap(False)
        self.theme_caption.setStyleSheet("font-weight:800;background:transparent;")
        self.theme = AnimatedToggle()
        self.theme.setChecked(self.ui_settings.theme == "dark")
        self.theme.toggled.connect(self._theme_toggled)

        zoom_cell = QWidget(); zoom_layout = QHBoxLayout(zoom_cell)
        zoom_layout.setContentsMargins(0, 0, 0, 0); zoom_layout.setSpacing(8)
        zoom_layout.addWidget(zoom_label); zoom_layout.addWidget(self.zoom, 1); zoom_layout.addWidget(self.zoom_label)
        hint_cell = QWidget(); hint_layout = QHBoxLayout(hint_cell)
        hint_layout.setContentsMargins(0, 0, 0, 0); hint_layout.addWidget(self.fullscreen_hint_label); hint_layout.addStretch()
        # The theme control is moved into the native title bar beside the
        # administrator/workshop badge. Keep only scale and fullscreen hint
        # in the content toolbar so the main controls stay compact.
        top = ResponsiveGrid([zoom_cell, hint_cell], min_cell_width=360, max_columns=2)
        top.setContentsMargins(4, 2, 4, 2)
        main.addWidget(top)
        self.tabs=QTabWidget();from .interaction_ui import FittingTabBar;self.tabs.setTabBar(FittingTabBar(self.tabs));self.tabs.setUsesScrollButtons(True);self.tabs.setElideMode(Qt.ElideNone);self.tabs.tabBar().setExpanding(False);self.tabs.tabBar().setMinimumHeight(46);self.tabs.currentChanged.connect(self._tab_changed);self._loaded_tabs={0};self._building_tab=False;self._build_orders_tab()
        for title in ("Номенклатура","Сотрудники","Администрирование","О приложении ⍰"):self.tabs.addTab(QWidget(),title)
        # RC9 fixed RBAC from the technical specification.
        # All tabs remain visible in the same order for every role.
        # Forbidden tabs are disabled instead of hidden. About is available to everybody.
        allowed={0,4}
        if self.can(Permission.CATALOG_VIEW): allowed.add(1)
        if self.can(Permission.EMPLOYEES_VIEW): allowed.add(2)
        if self.can(Permission.ADMIN_VIEW): allowed.add(3)
        for i in range(self.tabs.count()):
            enabled=i in allowed
            self.tabs.setTabEnabled(i, enabled)
        main.addWidget(self.tabs,1);self.setCentralWidget(shell);self.setWindowTitle("SmartOrder - Формирование нарядов на сдельную работу")
        self._session_timer=QTimer(self);self._session_timer.setInterval(1000);self._session_timer.timeout.connect(self._update_session_labels);self._session_timer.start()

    def _build_orders_tab(self):
        page = QWidget()
        self.orders_tab = page
        page.setObjectName("OrdersPage")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(8, 6, 8, 8)
        layout.setSpacing(10)

        left = QWidget()
        self.orders_header_left = left
        left.setObjectName("OrderHeaderPlainPanel")
        left.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        lv = QVBoxLayout(left)
        lv.setContentsMargins(12, 8, 12, 10)
        lv.setSpacing(10)

        self.order_filter_date = DateRangeEdit()
        self.order_filter_date.setDateRange(QDate.currentDate(), QDate.currentDate(), False)
        self.order_filter_date.dateChanged.connect(self.refresh_orders)
        self.order_filter_master = SmartComboBox()
        self.order_filter_master.addItem("Все мастера", None)
        for r in self.db.get_employees(True):
            self.order_filter_master.addItem(str(r[1]), int(r[0]))
        self.order_filter_master.currentIndexChanged.connect(self.refresh_orders)
        self.order_filter_shift = SmartComboBox()
        self.order_filter_shift.addItems(["Все смены", "Ночная", "Дневная"])
        self.order_filter_shift.currentIndexChanged.connect(self.refresh_orders)
        self.order_filter_dep = SmartComboBox()
        self.order_filter_dep.addItem("Все подразделения", None)
        for r in self.db.get_departments():
            self.order_filter_dep.addItem(str(r[1]), int(r[0]))
        self.order_filter_dep.currentIndexChanged.connect(self.refresh_orders)

        filter_cells = []
        for text, widget in (("Дата наряда:", self.order_filter_date), ("Мастер:", self.order_filter_master),
                             ("Смена:", self.order_filter_shift), ("Подразделение:", self.order_filter_dep)):
            cell = QWidget()
            cell_layout = QHBoxLayout(cell)
            cell_layout.setContentsMargins(0, 0, 0, 0)
            cell_layout.setSpacing(6)
            label = QLabel(text)
            label.setWordWrap(False)
            label.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
            widget.setMinimumWidth(0)
            widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            cell_layout.addWidget(label)
            cell_layout.addWidget(widget, 1)
            filter_cells.append(cell)
        filters = ResponsiveGrid(filter_cells, min_cell_width=340, max_columns=4)
        lv.addWidget(filters)

        buttons = []
        self.create_order_btn = QPushButton("Создать наряд")
        self.create_order_btn.setObjectName("PrimaryButton")
        self.create_order_btn.clicked.connect(self.create_order)
        self.create_order_btn.setVisible(self.can(Permission.ORDERS_CREATE))
        buttons.append(self.create_order_btn)
        self.edit_order_btn = QPushButton("Редактировать")
        self.edit_order_btn.setObjectName("SecondaryButton")
        self.edit_order_btn.clicked.connect(self.edit_order)
        self.edit_order_btn.setEnabled(False)
        self.edit_order_btn.setVisible(self.can(Permission.ORDERS_EDIT))
        buttons.append(self.edit_order_btn)
        self.export_order_btn = QPushButton("Выгрузить в EXCEL")
        self.export_order_btn.setObjectName("SecondaryButton")
        self.export_order_btn.clicked.connect(self.export_order)
        self.export_order_btn.setEnabled(False)
        self.export_order_btn.setVisible(self.can(Permission.ORDERS_EXPORT))
        buttons.append(self.export_order_btn)
        self.delete_draft_btn = QPushButton("Удалить черновик")
        self.delete_draft_btn.setObjectName("DangerButton")
        self.delete_draft_btn.clicked.connect(self.delete_selected_draft)
        self.delete_draft_btn.setEnabled(False)
        self.delete_draft_btn.setVisible(True)
        buttons.append(self.delete_draft_btn)
        for button in buttons:
            button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            button.setMinimumHeight(34)
            button.setAutoDefault(False)
        lv.addWidget(ResponsiveGrid(buttons, min_cell_width=230, max_columns=4))

        self.info_panel = QWidget()
        self.info_panel.setObjectName("GlassPanel")
        self.info_panel.setMinimumWidth(220)
        self.info_panel.setMaximumWidth(340)
        self.info_panel.setMinimumHeight(112)
        self.info_panel.setMaximumHeight(190)
        self.info_panel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        iv = QVBoxLayout(self.info_panel)
        iv.setContentsMargins(12, 10, 12, 10)
        iv.setSpacing(6)
        title = QLabel("ИСТОРИЯ РЕДАКТИРОВАНИЙ")
        title.setAlignment(Qt.AlignCenter)
        title.setWordWrap(False)
        title.setStyleSheet("font-size:10pt;font-weight:800;color:#007AFF;background:transparent;")
        iv.addWidget(title)
        self.info_users_list = QListWidget()
        self.info_users_list.setMinimumHeight(50)
        self.info_users_list.setMaximumHeight(140)
        self.info_users_list.setWordWrap(False)
        self.info_users_list.setTextElideMode(Qt.ElideRight)
        self.info_users_list.setStyleSheet("QListWidget{border:none;background:transparent;font-size:9pt;}QListWidget::item{padding:2px;}")
        self.info_users_list.itemDoubleClicked.connect(self._show_history_details)
        iv.addWidget(self.info_users_list, 1)

        header = ResponsiveGrid([left, self.info_panel], min_cell_width=760, max_columns=2)
        self.orders_header_grid = header
        header.setObjectName("OrdersHeaderResponsive")
        layout.addWidget(header)

        self.orders_table = QTableWidget(0, 6)
        self.orders_table.setHorizontalHeaderLabels(["№", "Дата наряда", "Тип смены", "Мастер", "Подразделение", "Дата регистрации"])
        self.orders_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.orders_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.orders_table.setWordWrap(False)
        self.orders_table.setTextElideMode(Qt.ElideRight)
        self.orders_table.setMinimumHeight(220)
        self.orders_table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.orders_table.setMouseTracking(True)
        self.orders_table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.orders_table.customContextMenuRequested.connect(self._orders_context_menu)
        self.orders_table.itemSelectionChanged.connect(self._order_selection_changed)
        self.orders_table.itemDoubleClicked.connect(lambda *_: self._open_selected())
        hh = self.orders_table.horizontalHeader()
        hh.setMinimumSectionSize(90)
        hh.setMinimumHeight(38)
        hh.setTextElideMode(Qt.ElideRight)
        hh.setSectionResizeMode(QHeaderView.Stretch)
        self.orders_table.verticalHeader().setVisible(False)
        self.orders_table.verticalHeader().setDefaultSectionSize(44)
        layout.addWidget(self.orders_table, 1)

        scroll = QScrollArea()
        scroll.setObjectName("OrdersResponsiveScroll")
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setWidget(page)
        self.orders_scroll = scroll
        self.info_panel.setVisible(self.can(Permission.ORDERS_HISTORY))
        self.tabs.addTab(scroll, "Наряд")

    def refresh_orders(self):
        if not hasattr(self,"orders_table"):return
        try:
            s=self.order_filter_date.startDate();e=self.order_filter_date.endDate();shift=source_text(self.order_filter_shift);shift=None if shift=="Все смены" else shift
            rows=self.db.list_orders(date_from=s.toString("yyyy-MM-dd"),date_to=e.toString("yyyy-MM-dd"),master_id=self.order_filter_master.currentData(),department_id=self.order_filter_dep.currentData(),shift=shift,limit=1500);display=[]
            for row in rows:display.append((int(row[0]),str(row[1]),str(row[2]),str(row[3]),str(row[4] or ""),str(row[5] or ""),str(row[6] or ""),False))
            for p,label,d,sh,m,dep,upd in self._draft_records():
                q=QDate.fromString(d,"dd-MM-yyyy")
                if q.isValid() and (q<s or q>e):continue
                if shift and sh!=shift:continue
                try:
                    raw=json.loads(p.read_text(encoding="utf-8"));mid=self.order_filter_master.currentData();did=self.order_filter_dep.currentData()
                    if mid is not None and raw.get("master_id")!=mid:continue
                    if did is not None and raw.get("department_id")!=did:continue
                except Exception:pass
                display.insert(0,(str(p),label,d,sh,m,dep,upd,True))
            self.orders_table.setUpdatesEnabled(False);self.orders_table.setRowCount(len(display))
            for r,rec in enumerate(display):
                ref,version,d,sh,m,dep,reg,is_draft=rec
                for c,v in enumerate([version,d.replace("-","."),sh,m,dep,reg]):self.orders_table.setItem(r,c,make_item(v))
                self.orders_table.item(r,0).setData(Qt.UserRole,ref)
                if is_draft:
                    for c in range(6):self.orders_table.item(r,c).setForeground(QColor("#FF9500"))
            self.orders_table.setUpdatesEnabled(True);self._order_selection_changed()
        except Exception as exc:self.orders_table.setUpdatesEnabled(True);error(self,"Не удалось загрузить наряды",exc)

    def _order_selection_changed(self):
        ref=self._selected_ref();is_draft=isinstance(ref,str) and ref.lower().endswith(".json");self.edit_order_btn.setEnabled(bool(ref) and self.can(Permission.ORDERS_EDIT));self.export_order_btn.setEnabled(isinstance(ref,int) and self.can(Permission.ORDERS_EXPORT));self.delete_draft_btn.setEnabled(is_draft and self.can(Permission.ORDERS_DELETE_DRAFT));self.info_users_list.clear()
        if isinstance(ref,int):
            try:
                history=list(reversed(self.db.order_history(ref)))
                for idx,rec in enumerate(history):
                    actor=rec["edited_by"] or "Система";when=rec["edit_date"] or rec["registration_date"]
                    action="Создал" if idx==0 else "Редактировал"
                    item=QListWidgetItem(f"{action}: {actor}" + (f" · {when}" if when else ""));item.setData(Qt.UserRole,rec);self.info_users_list.addItem(item)
            except Exception:pass
        elif is_draft:self.info_users_list.addItem("Локальный черновик текущего пользователя")

    def _open_selected(self):
        if not self.can(Permission.ORDERS_VIEW):return
        return super()._open_selected()

    def delete_selected_draft(self):
        ref=self._selected_ref()
        if not isinstance(ref,str):return
        if question(self,"Удаление черновика","Удалить выбранный черновик?")!=QMessageBox.Yes:return
        try:
            Path(ref).unlink(missing_ok=True)
            self.refresh_orders()
            info(self,"Черновик","Черновик удалён.")
        except Exception as exc:error(self,"Черновик",exc)

    def _orders_context_menu(self,pos):
        if self.orders_table.itemAt(pos) is None:return
        self.orders_table.selectRow(self.orders_table.itemAt(pos).row());ref=self._selected_ref();menu=QMenu(self)
        if self.can(Permission.ORDERS_HISTORY):
            a_open=menu.addAction("Открыть");a_edit=menu.addAction("Редактировать");a_edit.setEnabled(self.can(Permission.ORDERS_EDIT));a_history=menu.addAction("Посмотреть подробную историю")
        else:a_open=a_edit=a_history=None
        a_export=menu.addAction("Выгрузить в Excel");a_export.setEnabled(isinstance(ref,int) and self.can(Permission.ORDERS_EXPORT));a_delete=None
        if self.can(Permission.ORDERS_DELETE_DRAFT):a_delete=menu.addAction("Удалить черновик");a_delete.setEnabled(isinstance(ref,str))
        act=menu.exec_(self.orders_table.viewport().mapToGlobal(pos))
        if act==a_open:self._open_selected()
        elif act==a_edit:self.edit_order()
        elif act==a_export:self.export_order()
        elif a_delete is not None and act==a_delete:self.delete_selected_draft()
        elif act==a_history:self._show_history_details()

    def add_work_type(self):
        try:
            if not self.work_name.text().strip() or not self.work_code.text().strip() or dec(self.work_price.text()) is None:raise ValueError("Заполните наименование, код и стоимость")
            self.db.add_work_type(self.user,self.work_name.text(),self.work_code.text(),self.work_price.text());name=self.work_name.text().strip();self.refresh_work_types();self._clear_work_form();info(self,"Номенклатура",f"Работа «{name}» добавлена.")
        except Exception as exc:error(self,"Номенклатура",exc)

    def import_work_types(self):
        path,_=QFileDialog.getOpenFileName(self,"Импорт номенклатуры из Excel","","Excel/CSV (*.xlsx *.csv)")
        if not path:return
        try:
            raw=read_simple_xlsx(path)
            if not raw:raise ValueError("Файл не содержит данных")
            header=[str(x).strip().casefold().replace("ё","е") for x in raw[0]]
            def find_col(keys):
                for i,h in enumerate(header):
                    if any(k in h for k in keys):return i
                return None
            ni=find_col(("наимен","работ"));ci=find_col(("код",));pi=find_col(("стоим","цен"));start=1 if ni is not None and ci is not None and pi is not None else 0
            ni=0 if ni is None else ni;ci=1 if ci is None else ci;pi=2 if pi is None else pi;valid=[]
            for row in raw[start:]:
                if max(ni,ci,pi)>=len(row):continue
                name,code=str(row[ni]).strip(),str(row[ci]).strip();price=dec(row[pi])
                if name and code and price is not None:valid.append((name,code,float(price)))
            if not valid:raise ValueError("Не найдены строки вида: Наименование / Код / Стоимость")
            added,dup=self.db.import_work_types(self.user,valid);self.refresh_work_types();info(self,"Импорт номенклатуры",f"Добавлено: {added}\nДубликаты: {dup}")
        except Exception as exc:error(self,"Импорт номенклатуры",exc)

    def delete_work_type(self):
        row=self.work_table.currentRow()
        if row<0:return
        if question(self,"Удаление",f"Удалить работу «{self.work_table.item(row,0).text()}»?")!=QMessageBox.Yes:return
        try:self.db.delete_work_type(self.user,int(self.work_table.item(row,0).data(Qt.UserRole)));self.refresh_work_types();self._clear_work_form()
        except Exception as exc:error(self,"Удаление",exc)

    def _build_employees_tab(self):
        tab=super()._build_employees_tab()
        for b in (self.mode_worker,self.mode_master,self.mode_department):b.toggled.connect(self._people_mode_changed)
        return tab

    def _people_mode_changed(self,checked):
        if not checked:return
        if hasattr(self,"person_name"):self.person_name.clear()
        if hasattr(self,"person_search"):self.person_search.clear()
        if hasattr(self,"people_table"):self.people_table.clearSelection();self.people_table.setCurrentCell(-1,-1)
        if hasattr(self,"person_save_btn"):self.person_save_btn.setEnabled(False)
        if hasattr(self,"person_edit_btn"):self.person_edit_btn.setEnabled(False)
        if hasattr(self,"person_delete_btn"):self.person_delete_btn.setEnabled(False)
        self.refresh_people()

    def add_person(self):
        name=self.person_name.text().strip()
        if not name:return
        try:
            mode=self._people_mode()
            if mode=="department":self.db.add_department(self.user,name);kind="Подразделение"
            else:self.db.add_employee(self.user,name,mode=="master");kind="Мастер" if mode=="master" else "Сотрудник"
            self.person_name.clear();self.refresh_people();self._refresh_reference_filters();info(self,"Добавление",f"{kind} «{name}» добавлен.")
        except Exception as exc:error(self,"Сотрудники",exc)

    def import_people(self):
        path,_=QFileDialog.getOpenFileName(self,"Импорт из Excel","","Excel/CSV (*.xlsx *.csv)")
        if not path:return
        try:
            raw=read_simple_xlsx(path);names=[]
            for row in raw:
                if row and str(row[0]).strip() and str(row[0]).strip().casefold() not in {"фио","сотрудник","мастер","подразделение","наименование"}:names.append(str(row[0]).strip())
            mode=self._people_mode()
            if mode=="department":added,dup=self.db.import_departments(self.user,names);kind="подразделений"
            else:added,dup=self.db.import_people(self.user,names,mode=="master");kind="мастеров" if mode=="master" else "сотрудников"
            self.refresh_people();self._refresh_reference_filters();info(self,"Импорт",f"Добавлено {kind}: {added}\nДубликаты: {dup}")
        except Exception as exc:error(self,"Импорт",exc)

    def delete_person(self):
        row=self.people_table.currentRow()
        if row<0:return
        if question(self,"Удаление",f"Удалить «{self.people_table.item(row,0).text()}»?")!=QMessageBox.Yes:return
        ident=int(self.people_table.item(row,0).data(Qt.UserRole))
        try:
            if self._people_mode()=="department":self.db.delete_department(self.user,ident)
            else:self.db.delete_employee(self.user,ident)
            self.refresh_people();self._refresh_reference_filters()
        except Exception as exc:error(self,"Удаление",exc)

    def _build_admin_tab(self):
        tab=QWidget();layout=QVBoxLayout(tab);layout.setContentsMargins(10,8,10,8);layout.setSpacing(8)
        # Status/synchronization live only in Administration.
        status=QHBoxLayout();self.admin_sync_btn=QPushButton("⟳  Синхронизация");self.admin_sync_btn.setObjectName("SecondaryButton");self.admin_sync_btn.clicked.connect(self._sync_current_tab);status.addWidget(self.admin_sync_btn);self.admin_db_state=QLabel("● БД: проверка…");self.admin_db_state.setObjectName("DbStateSlow");status.addWidget(self.admin_db_state);status.addStretch();layout.addLayout(status)
        if self.user.has_role("Администратор"):
            access=QCheckBox("Разрешительный режим (авторизация обязательна)");access.setChecked(self.db.is_access_control_enabled());access.setEnabled(True);access.toggled.connect(self._toggle_access_control);self.access_control_check=access;layout.addWidget(access)
            user_group=QGroupBox("Управление пользователями");uv=QVBoxLayout(user_group);self.users_table=QTableWidget(0,4);self.users_table.setObjectName("UsersTableV32");self.users_table.setHorizontalHeaderLabels(["Логин","Роль","Статус","Действия"]);self.users_table.setEditTriggers(QAbstractItemView.NoEditTriggers);self.users_table.horizontalHeader().setSectionResizeMode(0,QHeaderView.Stretch);self.users_table.setColumnWidth(1,170);self.users_table.setColumnWidth(2,120);self.users_table.setColumnWidth(3,360);self.users_table.setMaximumHeight(260);self.users_table.verticalHeader().setVisible(False);uv.addWidget(self.users_table);row=QHBoxLayout();add=QPushButton("Добавить пользователя");add.setObjectName("PrimaryButton");add.clicked.connect(self.add_user);row.addWidget(add);row.addStretch();uv.addLayout(row);layout.addWidget(user_group)
        backup=QGroupBox("💾 Резервное копирование и архивы");backup.setObjectName("BackupGroup");bv=QVBoxLayout(backup);bh=QHBoxLayout();bcreate=QPushButton("📀 Создать бэкап");bcreate.clicked.connect(self.create_backup);brestore=QPushButton("↶ Восстановить");brestore.clicked.connect(self.restore_backup);self.backup_combo=SmartComboBox();self.backup_combo.setMinimumWidth(190);bdelete=QPushButton("Удалить");bdelete.setObjectName("DangerButton");bdelete.clicked.connect(self.delete_backup);barchive=QPushButton("Архивный снимок");barchive.setToolTip("Создаёт отдельную копию БД для безопасного просмотра состояния на этот момент, не заменяя рабочую базу.");barchive.clicked.connect(self.create_archive_snapshot);bopen=QPushButton("Открыть архивные снимки");bopen.clicked.connect(self.open_archive_snapshots);logs=QPushButton("Собрать логи");logs.clicked.connect(self.collect_logs)
        for w in (bcreate,brestore,QLabel("Копии:"),self.backup_combo,bdelete,barchive,bopen,logs):bh.addWidget(w)
        bh.addStretch();bv.addLayout(bh);desc=QLabel("Архивный снимок — безопасная копия БД на конкретный момент. Его можно открыть для просмотра, не восстанавливая рабочую базу.");desc.setObjectName("MutedLabel");desc.setWordWrap(True);bv.addWidget(desc);layout.addWidget(backup)
        if self.user.has_role("Администратор"):
            patch_row=QHBoxLayout();self.update_patch_btn=QPushButton("Обновить патч");self.update_patch_btn.setObjectName("SecondaryButton");self.update_patch_btn.setToolTip("Выберите ZIP-патч с patch.json и payload/. База данных не изменяется.");self.update_patch_btn.clicked.connect(self.apply_patch_update);patch_row.addWidget(self.update_patch_btn);patch_row.addStretch();layout.addLayout(patch_row)
        if self.user.has_role("Администратор"):
            audit_group=QGroupBox("Журнал действий");av=QVBoxLayout(audit_group);self.audit_table=QTableWidget(0,6);self.audit_table.setObjectName("AuditTable");self.audit_table.setHorizontalHeaderLabels(["Дата/Время","Пользователь","Действие","Тип объекта","Объект","Детали"]);self.audit_table.setEditTriggers(QAbstractItemView.NoEditTriggers);self.audit_table.setSelectionBehavior(QAbstractItemView.SelectRows);self.audit_table.verticalHeader().setVisible(False);self.audit_table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive);self.audit_table.horizontalHeader().setStretchLastSection(True);av.addWidget(self.audit_table,1);layout.addWidget(audit_group,1)
        else:layout.addStretch(1)
        bottom=QHBoxLayout();bottom.addStretch();self.admin_session_label=QLabel();self.admin_session_label.setObjectName("MutedLabel");self.admin_session_label.setStyleSheet("font-size:10px;background:transparent;");bottom.addWidget(self.admin_session_label);layout.addLayout(bottom);self._apply_last_ping();self._update_session_labels();QTimer.singleShot(50,self._ping_async);return tab

    def refresh_users(self):
        if not self.user.has_role("Администратор") or not hasattr(self,"users_table"):return
        return super().refresh_users()
    def refresh_audit(self):
        if not self.user.has_role("Администратор") or not hasattr(self,"audit_table"):return
        return super().refresh_audit()

    def _edit_user_by_id(self,uid,username,role):
        dlg=HeavyUserDialog(username,role,False,self)
        if dlg.exec_()!=QDialog.Accepted:return
        try:self.db.update_user(self.user,uid,dlg.username.text(),dlg.selected_roles(),dlg.password.text());self.refresh_users()
        except Exception as exc:error(self,"Пользователь",exc)

    def add_user(self):
        if not self.user.has_role("Администратор"):return
        dlg=HeavyUserDialog(parent=self)
        if dlg.exec_()!=QDialog.Accepted:return
        try:self.db.add_user(self.user,dlg.username.text(),dlg.password.text(),dlg.selected_roles());self.refresh_users();info(self,"Пользователь",f"Пользователь «{dlg.username.text().strip()}» добавлен.")
        except Exception as exc:error(self,"Пользователь",exc)

    def create_archive_snapshot(self):
        try:
            month=datetime.now().strftime("%Y-%m");folder=shared_dirs()["archives"]/month;folder.mkdir(parents=True,exist_ok=True);target=folder/f"work_orders_archive_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.db";self.db.backup_to(target);self.db.log_action(self.user.username,"Создал архивный снимок БД","Система",target.name,str(target));info(self,"Архивный снимок",f"Снимок создан:\n{target}\n\nЭто отдельная копия БД для просмотра старого состояния. Рабочая база не изменяется.")
        except Exception as exc:error(self,"Архив",exc)

    def apply_patch_update(self):
        """Stage an application-only patch without touching any database."""
        if not self.can(Permission.APP_UPDATE):
            return
        path,_=QFileDialog.getOpenFileName(self,"Выберите ZIP-патч SmartOrder","","Патч SmartOrder (*.zip)")
        if not path:return
        choice=QDialog(self);choice.setWindowTitle("Параметры обновления");choice.setModal(True);choice.setMinimumWidth(520)
        choice_layout=QVBoxLayout(choice)
        choice_layout.addWidget(QLabel("Патч должен содержать patch.json и файлы только в payload/. База данных в обновление не входит."))
        notify=QCheckBox("Оповестить пользователей после подготовки обновления")
        notify.setChecked(True);choice_layout.addWidget(notify)
        buttons=QDialogButtonBox(QDialogButtonBox.Ok|QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("Продолжить")
        buttons.button(QDialogButtonBox.Cancel).setText("Отмена")
        buttons.accepted.connect(choice.accept);buttons.rejected.connect(choice.reject);choice_layout.addWidget(buttons)
        apply_apple_design(choice,self.ui_settings.theme,self.ui_settings.zoom)
        if choice.exec_()!=QDialog.Accepted:return
        progress=QProgressDialog("Проверка и загрузка обновления…",None,0,0,self)
        progress.setWindowTitle("Обновление SmartOrder");progress.setAutoClose(False);progress.setMinimumDuration(0);progress.setModal(True);progress.show();QApplication.processEvents()
        try:
            manifest=stage_patch(path)
            if notify.isChecked():
                publish_update_notice(manifest, network_root())
            self.db.log_action(self.user.username,"Подготовил обновление","Приложение",manifest["version"],"Патч staged; база данных не изменялась")
            progress.close();progress.deleteLater()
            notice="\nОбъявление опубликовано для пользователей." if notify.isChecked() else ""
            info(self,"Обновление подготовлено",f"Версия {manifest['version']} загружена.\n\nПерезапустите SmartOrder, чтобы применить файлы патча.{notice}\n\nФормат патча: patch.json + payload/; база данных в патч не включается.")
        except (PatchError,OSError,ValueError) as exc:
            progress.close();progress.deleteLater();error(self,"Обновление",exc)

    def open_archive_snapshots(self):ArchiveSnapshotsDialog(self.db,self).exec_()

    def delete_backup(self):
        if not hasattr(self,"backup_combo") or self.backup_combo.currentIndex()<0:return
        path=Path(self.backup_combo.currentData())
        if question(self,"Удаление",f"Удалить резервную копию {path.name}?")!=QMessageBox.Yes:return
        try:path.unlink();self.db.log_action(self.user.username,"Удалил резервную копию","Система",path.name,"");self.refresh_backups()
        except Exception as exc:error(self,"Удаление",exc)

    def restore_backup(self):
        if not hasattr(self,"backup_combo") or self.backup_combo.currentIndex()<0:return
        source=Path(self.backup_combo.currentData())
        if question(self,"Восстановление","Рабочая база будет заменена выбранной копией. Перед восстановлением SmartOrder автоматически создаст страховочную копию. Продолжить?")!=QMessageBox.Yes:return
        try:
            before=shared_dirs()["before_restore"]/f"before_restore_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.db";self.db.backup_to(before);self.db.restore_from(source);self.db.log_action(self.user.username,"Восстановил БД","Система",source.name,f"Страховочная копия: {before}");self.db.invalidate_cache();self.refresh_orders();info(self,"Восстановление","База восстановлена. Страховочная копия создана автоматически.")
        except Exception as exc:error(self,"Восстановление",exc)

    def collect_logs(self):
        try:
            folder=local_logs_dir();folder.mkdir(parents=True,exist_ok=True);target=folder/f"SmartOrder_logs_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.zip"
            with zipfile.ZipFile(target,"w",zipfile.ZIP_DEFLATED) as z:
                for base in (local_logs_dir(), local_root()/"diagnostics"):
                    if base.exists():
                        for f in base.rglob("*"):
                            if f.is_file() and f!=target:
                                try:z.write(f,arcname=f"logs/{base.name}/{f.relative_to(base)}")
                                except Exception:pass
                report=(f"SmartOrder {APP_VERSION}\nUser: {self.user.username} ({self.user.role})\nComputer: {socket.gethostname()}\nOS: {platform.platform()}\nPython: {platform.python_version()}\nDB: {database_path()}\nNetwork root: {network_root()}\nSession: {self._session_text()}\n")
                z.writestr("system_info.txt",report)
                try:
                    rows=self.db.recent_audit(200);z.writestr("recent_audit.txt","\n".join(" | ".join(str(v or "") for v in r) for r in rows))
                except Exception as exc:z.writestr("recent_audit_error.txt",str(exc))
            info(self,"Логи",f"Диагностический архив создан:\n{target}")
            if os.name=="nt":
                try:
                    os.startfile(str(folder))
                except Exception:
                    pass
        except Exception as exc:error(self,"Сбор логов",exc)

    def _session_text(self):
        total=max(0,int(time.monotonic()-self._session_started));h,rem=divmod(total,3600);m,sec=divmod(rem,60);return tr("Текущая сессия:")+f" {h:02d}:{m:02d}:{sec:02d}"
    def _update_session_labels(self):
        text=self._session_text()
        for name in ("admin_session_label","about_session_label","personalization_session_label"):
            lab=getattr(self,name,None)
            if lab is not None:lab.setText(text)

    def _about_selectable(self,label: QLabel,links: bool=False):
        try:
            flags=Qt.TextSelectableByMouse
            if links: flags|=Qt.LinksAccessibleByMouse
            label.setTextInteractionFlags(flags)
            pal=label.palette();pal.setColor(QPalette.Highlight,QColor("#FFD60A"));pal.setColor(QPalette.HighlightedText,QColor("#111111"));label.setPalette(pal)
            label.setCursor(Qt.PointingHandCursor if links else Qt.IBeamCursor)
        except Exception:pass
        return label

    def _about_browser(self, html: str, link_handler=None):
        browser=QTextBrowser()
        browser.setFrameShape(QFrame.NoFrame)
        browser.setOpenExternalLinks(False)
        browser.setOpenLinks(False)
        browser.setTextInteractionFlags(Qt.TextBrowserInteraction | Qt.TextSelectableByMouse)
        browser.setHtml(html)
        browser.setStyleSheet("QTextBrowser{background:transparent;border:none;color:#FFFFFF;font-size:14px;selection-background-color:#FFD60A;selection-color:#111111;} QScrollBar{width:8px;} a{color:#0A84FF;text-decoration:none;}")
        pal=browser.palette();pal.setColor(QPalette.Base,QColor(0,0,0,0));pal.setColor(QPalette.Highlight,QColor("#FFD60A"));pal.setColor(QPalette.HighlightedText,QColor("#111111"));browser.setPalette(pal)
        if link_handler is not None:
            browser.anchorClicked.connect(link_handler)
        return browser

    def _build_about_tab(self):
        tab=GifBackgroundWidget(["loading2.gif","login_background.gif","resources/loading2.gif"]);root=QVBoxLayout(tab);root.setContentsMargins(30,20,30,24);root.setSpacing(12)
        logo=QLabel()
        if _set_logo(logo,148,"smartorder_logo_icon_light.png","smartorder_logo_icon.png","smartorder_logo_white.png","smartorder_logo.png"):root.addWidget(logo,alignment=Qt.AlignCenter)
        edition=self._about_selectable(QLabel(f"Enterprise Edition · Version: {APP_VERSION}"));edition.setAlignment(Qt.AlignCenter);edition.setStyleSheet("font-size:15px;color:#E5E7EB;background:transparent;");root.addWidget(edition)
        style="QFrame#AboutTransparentCard{background:rgba(0,0,0,0);border:1px solid rgba(255,255,255,110);border-radius:16px;}"
        cards=QHBoxLayout();cards.setSpacing(18)
        policy_path=ensure_usage_policy_document()
        system=QFrame();system.setObjectName("AboutTransparentCard");system.setStyleSheet(style);sv=QVBoxLayout(system);sv.setContentsMargins(14,14,14,14)
        system_html=(f'<div style="color:#0A84FF;font-size:18px;font-weight:800;">System</div><br>'
                     f'Среда выполнения: Python {platform.python_version()}<br>Движок: PyQt5 5.15.x<br>Язык: Python<br>Version: {APP_VERSION}<br><br>'
                     '<a href="policy">Положение об использовании ПО</a>')
        sb=self._about_browser(system_html, lambda _url,p=policy_path: QDesktopServices.openUrl(QUrl.fromLocalFile(str(p))) if p else None);sv.addWidget(sb,1);cards.addWidget(system,1)
        guide=QFrame();guide.setObjectName("AboutTransparentCard");guide.setStyleSheet(style);gv=QVBoxLayout(guide);gv.setContentsMargins(14,14,14,14)
        steps=["Заполните справочники: номенклатура, сотрудники, мастера, подразделения.","Во вкладке «Наряд» нажмите «Создать наряд».","Выберите дату, смену, мастера и подразделение.","Добавьте работников и работы.","Заполните часы, фикс или факт.","Сохраните наряд.","При необходимости откройте, отредактируйте или выгрузите наряд в Excel."]
        guide_html='<div style="color:#0A84FF;font-size:18px;font-weight:800;">Как работать в программе?</div><br>'+''.join(f'{i}. {text}<br><br>' for i,text in enumerate(steps,1))
        gb=self._about_browser(guide_html);gv.addWidget(gb,1);cards.addWidget(guide,1);root.addLayout(cards,1)
        foot=QFrame();foot.setObjectName("AboutTransparentCard");foot.setStyleSheet(style);fv=QVBoxLayout(foot);footer_html='<div style="text-align:center;font-weight:700;">Powered by OITS&amp;ZI</div><div style="text-align:center;">Copyright © 2026 <a href="https://tmbsir.ru/">tmbsir</a></div>'
        fb=self._about_browser(footer_html, lambda url: QDesktopServices.openUrl(url));fb.setMaximumHeight(82);fv.addWidget(fb);root.addWidget(foot)
        bottom=QHBoxLayout();bottom.addStretch();self.about_session_label=QLabel();self.about_session_label.setStyleSheet("font-size:10px;color:#E5E7EB;background:transparent;");bottom.addWidget(self.about_session_label);root.addLayout(bottom);self._update_session_labels();return tab

    def _ping_done(self,ok:bool,ms:float,message:str):
        self._ping_running=False;self._last_ping=(ok,ms,message);self._apply_last_ping()
    def _apply_last_ping(self):
        lab=getattr(self,"admin_db_state",None)
        if lab is None:return
        ok,ms,message=self._last_ping
        if ok:
            if ms>300:lab.setText(f"● БД доступна, медленный ответ · {ms:.0f} мс");lab.setObjectName("DbStateSlow")
            elif ms>150:lab.setText(f"● БД доступна · {ms:.0f} мс");lab.setObjectName("DbStateSlow")
            else:lab.setText(f"● БД доступна · {ms:.0f} мс");lab.setObjectName("DbStateOk")
            lab.setToolTip("Медиана трёх рабочих SQLite-запросов после отдельного SMB-прогрева.")
        else:lab.setText("● БД недоступна" if message!="Проверка..." else "● БД: проверка…");lab.setObjectName("DbStateBad" if message!="Проверка..." else "DbStateSlow");lab.setToolTip(message)
        lab.style().unpolish(lab);lab.style().polish(lab)


# Runtime aliases: Heavy visuals, LiteCore database.
UserDialog = HeavyUserDialog
MultiSelectDialog = _HeavyCheckListDialog
HeavyWorkOrderDialog = RC3WorkOrderDialog
HeavyMainWindow = RC3MainWindow
LoginDialog = HeavyLoginDialog
MainWindow = RC3MainWindow
WorkOrderDialog = RC3WorkOrderDialog


# ===========================================================================
# RC4 — Heavy behaviour parity + stable revision semantics
# ===========================================================================

_RC4_EMPLOYEE_NAME_ROLE = int(Qt.UserRole) + 41
_RC4_OLD_APPLY_MODAL_THEME = _apply_modal_theme


def _rc4_set_windows_titlebar_dark(widget, dark: bool) -> None:
    """Keep the native Windows caption in sync with the selected theme."""
    if os.name != "nt" or widget is None or isinstance(widget, QFileDialog):
        return
    if not widget.isWindow() or not widget.isVisible() or widget.windowHandle() is None:
        return
    if widget.windowType() in (Qt.Popup, Qt.ToolTip):
        return
    try:
        import ctypes
        hwnd = int(widget.winId())
        value = ctypes.c_int(1 if dark else 0)
        # DWMWA_USE_IMMERSIVE_DARK_MODE is 20 on current Windows 10/11,
        # with 19 used by older Windows 10 builds.
        for attr in (20, 19):
            try:
                result = ctypes.windll.dwmapi.DwmSetWindowAttribute(
                    ctypes.c_void_p(hwnd), ctypes.c_uint(attr),
                    ctypes.byref(value), ctypes.sizeof(value),
                )
                if result == 0:
                    break
            except Exception:
                continue
    except Exception:
        pass


def _apply_modal_theme(dialog, parent=None):
    _RC4_OLD_APPLY_MODAL_THEME(dialog, parent)
    theme, _ = _theme_of(parent or (dialog.parent() if hasattr(dialog, "parent") else dialog))
    _rc4_set_windows_titlebar_dark(dialog, theme == "dark")


def _rc4_employee_item(display_name: str, employee_id, full_name: str | None = None) -> QTableWidgetItem:
    full = str(full_name if full_name is not None else display_name or "")
    item = make_item(str(display_name or ""), employee_id)
    item.setData(_RC4_EMPLOYEE_NAME_ROLE, full)
    if not str(display_name or "").strip() and full:
        item.setToolTip(full)
    return item


def _rc4_full_employee_name(item: QTableWidgetItem | None) -> str:
    if item is None:
        return ""
    try:
        value = item.data(_RC4_EMPLOYEE_NAME_ROLE)
        if value not in (None, ""):
            return str(value)
    except Exception:
        pass
    return str(item.text() or "")


class _RC4FullscreenIcon(QWidget):
    def __init__(self, entering: bool, parent=None):
        super().__init__(parent)
        self.entering = bool(entering)
        self.setFixedSize(58, 58)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        pen = painter.pen()
        pen.setColor(QColor(self.property("iconColor") or "#FFFFFF"))
        pen.setWidth(4)
        pen.setCapStyle(Qt.RoundCap)
        painter.setPen(pen)
        m, arm = 9, 14
        w, h = self.width(), self.height()
        if self.entering:
            # Four outward YouTube-like fullscreen corners.
            segs = [
                (m, m+arm, m, m), (m, m, m+arm, m),
                (w-m-arm, m, w-m, m), (w-m, m, w-m, m+arm),
                (m, h-m-arm, m, h-m), (m, h-m, m+arm, h-m),
                (w-m-arm, h-m, w-m, h-m), (w-m, h-m-arm, w-m, h-m),
            ]
        else:
            # Inward corners communicate leaving fullscreen.
            c1, c2 = m+8, w-m-8
            t1, t2 = m+8, h-m-8
            segs = [
                (c1, t1, c1+arm, t1), (c1, t1, c1, t1+arm),
                (c2-arm, t1, c2, t1), (c2, t1, c2, t1+arm),
                (c1, t2, c1+arm, t2), (c1, t2-arm, c1, t2),
                (c2-arm, t2, c2, t2), (c2, t2-arm, c2, t2),
            ]
        for x1, y1, x2, y2 in segs:
            painter.drawLine(x1, y1, x2, y2)


class _RC4FullscreenFeedback(QFrame):
    def __init__(self, parent, entering: bool):
        super().__init__(parent)
        self.setObjectName("FullscreenFeedback")
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setFixedSize(390, 158)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 18, 24, 18)
        layout.setSpacing(8)
        layout.addWidget(_RC4FullscreenIcon(entering, self), 0, Qt.AlignCenter)
        label = QLabel("Полноэкранный режим" if entering else "Оконный режим", self)
        label.setAlignment(Qt.AlignCenter)
        label.setObjectName("FullscreenFeedbackText")
        layout.addWidget(label)
        hint = QLabel("Esc — вернуться обратно" if entering else "Esc — открыть на весь экран", self)
        hint.setAlignment(Qt.AlignCenter)
        hint.setObjectName("FullscreenFeedbackHint")
        layout.addWidget(hint)
        self.effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self.effect)
        self.effect.setOpacity(0.0)
        self.fade_in = QPropertyAnimation(self.effect, b"opacity", self)
        self.fade_in.setDuration(300)
        self.fade_in.setStartValue(0.0)
        self.fade_in.setEndValue(0.92)
        self.fade_in.setEasingCurve(QEasingCurve.OutCubic)
        self.fade_out = QPropertyAnimation(self.effect, b"opacity", self)
        self.fade_out.setDuration(620)
        self.fade_out.setStartValue(0.92)
        self.fade_out.setEndValue(0.0)
        self.fade_out.setEasingCurve(QEasingCurve.InOutCubic)
        self.fade_out.finished.connect(self.deleteLater)
        self.fade_in.finished.connect(lambda: QTimer.singleShot(850, self.fade_out.start))
        parent.installEventFilter(self)

    def _center(self):
        parent = self.parentWidget()
        if parent is not None:
            self.move(parent.rect().center() - self.rect().center())

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Resize and self.isVisible():
            self._center()
        return False

    def start(self):
        self._center()
        self.show(); self.raise_(); self.fade_in.start()


class _RC5InfoPopup(QFrame):
    """Theme-aware child help panel; never creates a native top-level window."""
    def __init__(self,parent: QWidget,text: str,theme: str):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents,True)
        self.setObjectName("RC5InfoPopup")
        layout=QVBoxLayout(self);layout.setContentsMargins(14,11,14,11)
        label=QLabel(str(text or ""),self);label.setWordWrap(True);label.setMaximumWidth(520);layout.addWidget(label)
        if theme=="dark":
            self.setStyleSheet("QFrame#RC5InfoPopup{background:#2C2C2E;border:1px solid #636366;border-radius:10px;} QLabel{color:#F5F5F7;background:transparent;font-size:12px;}")
        else:
            self.setStyleSheet("QFrame#RC5InfoPopup{background:#FFFFFF;border:1px solid #C7C7CC;border-radius:10px;} QLabel{color:#1D1D1F;background:transparent;font-size:12px;}")
        self.adjustSize()

class _RC5InfoHoverFilter(QObject):
    def __init__(self,target: QWidget,provider):
        super().__init__(target)
        self.target=target;self.provider=provider;self.popup=None
        self.hide_timer=QTimer(self);self.hide_timer.setSingleShot(True);self.hide_timer.timeout.connect(self.hide_popup)
        target.setMouseTracking(True);target.installEventFilter(self);target.setToolTip("")
    def eventFilter(self,obj,event):
        if obj is self.target and event.type()==QEvent.Enter:
            self.show_popup()
        elif obj is self.target and event.type() in (QEvent.Leave,QEvent.Hide,QEvent.FocusOut,QEvent.MouseButtonPress,QEvent.Wheel):
            self.hide_popup()
        return False
    def show_popup(self):
        self.hide_popup()
        try:
            text=self.provider() if callable(self.provider) else str(self.provider or "")
            if not str(text or "").strip():return
            theme,_=_theme_of(self.target);host=self.target.window()
            self.popup=_RC5InfoPopup(host,text,theme)
            pos=host.mapFromGlobal(self.target.mapToGlobal(QPoint(0,self.target.height()+7)))
            self.popup.adjustSize()
            x=min(max(6,pos.x()),max(6,host.width()-self.popup.width()-6))
            y=min(max(6,pos.y()),max(6,host.height()-self.popup.height()-6))
            self.popup.move(x,y);self.popup.show();self.popup.raise_();self.hide_timer.start(2400)
        except Exception:
            self.popup=None
    def hide_popup(self):
        self.hide_timer.stop()
        if self.popup is not None:
            try:self.popup.hide();self.popup.deleteLater()
            except Exception:pass
            self.popup=None


def _rc4_find_layout_with_widget(layout, target):
    if layout is None:
        return None
    for i in range(layout.count()):
        item = layout.itemAt(i)
        if item.widget() is target:
            return layout
        child = item.layout()
        if child is not None:
            found = _rc4_find_layout_with_widget(child, target)
            if found is not None:
                return found
    return None


class RC4WorkOrderDialog(RC3WorkOrderDialog):
    """Heavy editor visuals with deterministic, non-recursive table logic."""

    def __init__(self, *args, **kwargs):
        self._rc4_original_signature = None
        super().__init__(*args, **kwargs)
        if self.order is not None:
            info_data = self.order.get("info", {})
            self._rc4_original_signature = order_content_signature(
                str(info_data.get("order_date", "")),
                str(info_data.get("shift_type", "")),
                info_data.get("master_id"), info_data.get("department_id"),
                list(self.order.get("lines", [])), str(info_data.get("comment", "") or ""),
            )
        self._start_edit_banner_pulse()

    def _build(self):
        super()._build()
        # Make the table comfortable on 1080p/1440p terminals while retaining horizontal scrolling.
        widths = [285, 125, 390, 155, 160, 175, 185, 185, 160, 190, 160]
        for i, width in enumerate(widths):
            self.table.setColumnWidth(i, width)

    def showEvent(self, event):
        super().showEvent(event)
        theme, _ = _theme_of(self.parent() or self)
        QTimer.singleShot(0, lambda: _rc4_set_windows_titlebar_dark(self, theme == "dark"))

    def _start_edit_banner_pulse(self):
        if self.order is None or self.view_only:
            return
        banner = self.findChild(QFrame, "EditModeBanner")
        if banner is None or getattr(self, "_edit_banner_anim", None) is not None:
            return
        effect = QGraphicsOpacityEffect(banner)
        banner.setGraphicsEffect(effect)
        effect.setOpacity(1.0)
        anim = QPropertyAnimation(effect, b"opacity", banner)
        anim.setDuration(1450)
        anim.setStartValue(1.0)
        anim.setKeyValueAt(0.50, 0.52)
        anim.setEndValue(1.0)
        anim.setLoopCount(-1)
        anim.setEasingCurve(QEasingCurve.InOutSine)
        banner._pulse_effect = effect
        banner._pulse_anim = anim
        self._edit_banner_anim = anim
        anim.start()

    def _apply_flags(self, row):
        """Heavy FIX/FACT mode locking.

        FACT and FIX are mutually exclusive manual input modes.  Calculated
        columns are always read-only.  The rule is intentionally identical for
        ordinary and grouped departments.
        """
        total = self._is_total(row)
        actual_item = self.table.item(row, 9)
        boxes_item = self.table.item(row, 5)
        weight_item = self.table.item(row, 6)
        has_actual = bool(actual_item and actual_item.text().strip())
        has_fixed = bool(
            (boxes_item and boxes_item.text().strip())
            or (weight_item and weight_item.text().strip())
        )
        for col in range(11):
            item = self.table.item(row, col)
            if item is None:
                item = make_item("")
                self.table.setItem(row, col, item)
            flags = item.flags() | Qt.ItemIsSelectable
            # Keep cells enabled unless a mutually-exclusive input mode locks them.
            flags |= Qt.ItemIsEnabled
            editable = (col in self.MANUAL) and not total and not self.view_only
            if has_actual and col in {5, 6, 7, 8}:
                editable = False
                flags &= ~Qt.ItemIsEnabled
            if has_fixed and not has_actual and col in {9, 10}:
                editable = False
                flags &= ~Qt.ItemIsEnabled
            if editable:
                flags |= Qt.ItemIsEditable
            else:
                flags &= ~Qt.ItemIsEditable
            item.setFlags(flags)

    def _line_from_row(self, row):
        def text(c):
            item = self.table.item(row, c)
            return item.text().strip() if item else ""
        def role(c):
            item = self.table.item(row, c)
            return item.data(Qt.UserRole) if item else None
        from .domain import OrderLine
        emp_item = self.table.item(row, 0)
        return OrderLine(
            employee_id=role(0), employee_name=_rc4_full_employee_name(emp_item),
            work_type_id=role(2), work_name=text(2), work_code=text(3), price=dec(text(4)),
            hours=dec(text(1)), fixed_boxes=dec(text(5)), fixed_weight=dec(text(6)),
            actual_value=dec(text(9)),
        )

    def _write_calculated(self, row, line):
        # Preserve the caller's blockSignals state.  RC3 unblocked signals from inside
        # _load_order(), which caused the observed 123 -> 246 -> 492 -> 984 corruption.
        was_blocked = self.table.signalsBlocked()
        self.table.blockSignals(True)
        try:
            self._ensure_row(row)
            self.table.item(row, 7).setText(fmt(line.fixed_total))
            self.table.item(row, 8).setText(fmt(line.fixed_payment, 2))
            self.table.item(row, 10).setText(fmt(line.actual_payment, 2))
            self._apply_flags(row)
        finally:
            self.table.blockSignals(was_blocked)

    def _on_cell_changed(self, item):
        if self._cell_busy or self.view_only or self._is_total(item.row()):
            return
        self._cell_busy = True
        was_blocked = self.table.signalsBlocked()
        try:
            row = item.row()
            col = item.column()
            if col in self.MANUAL and item.text().strip():
                normalized = item.text().strip().replace(",", ".")
                if dec(normalized) is not None:
                    self.table.blockSignals(True)
                    item.setText(normalized)
                    self.table.blockSignals(was_blocked)

            # Heavy mutually-exclusive mode: whichever side the operator starts
            # filling wins.  Clear the opposite manual mode, then lock it.
            self.table.blockSignals(True)
            if col == 9 and item.text().strip():
                for c in (5, 6):
                    other = self.table.item(row, c)
                    if other is not None:
                        other.setText("")
            elif col in {5, 6} and item.text().strip():
                actual = self.table.item(row, 9)
                if actual is not None:
                    actual.setText("")
            self.table.blockSignals(was_blocked)

            self._write_calculated(row, self._line_from_row(row))
            self._apply_flags(row)
            self._refresh_totals()
        finally:
            self.table.blockSignals(was_blocked)
            self._cell_busy = False

    def _edit_clicked_cell(self, item):
        if self.view_only or self._is_total(item.row()) or item.column() not in self.MANUAL:
            return
        if not (item.flags() & Qt.ItemIsEditable) or not (item.flags() & Qt.ItemIsEnabled):
            return
        QTimer.singleShot(0, lambda i=item: self.table.editItem(i))

    def _subtotal_department(self) -> bool:
        return bool(getattr(self,"separate_worker_check",None) and self.separate_worker_check.isChecked())

    def _grouped_assignment_department(self) -> bool:
        # Grouping is an explicit per-order choice now; department names no
        # longer change the calculation form implicitly.
        return bool(getattr(self,"separate_worker_check",None) and self.separate_worker_check.isChecked())

    def _normalize_employee_display(self):
        grouped = self._grouped_assignment_department()
        last_key = None
        for row in range(self.table.rowCount()):
            if self._is_total(row):
                last_key = None
                continue
            item = self.table.item(row, 0)
            if item is None:
                last_key = None
                continue
            full = _rc4_full_employee_name(item)
            emp_id = item.data(Qt.UserRole)
            if not full and emp_id is None:
                last_key = None
                continue
            key = (emp_id, full)
            work_item = self.table.item(row, 2)
            has_work = bool(work_item and (work_item.text().strip() or work_item.data(Qt.UserRole) is not None))
            display = "" if grouped and key == last_key and has_work else full
            item.setText(display)
            item.setData(_RC4_EMPLOYEE_NAME_ROLE, full)
            item.setToolTip(full if not display and full else "")
            last_key = key

    def _refresh_totals(self):
        if getattr(self, "_rc4_totals_busy", False):
            return
        self._rc4_totals_busy = True
        was_blocked = self.table.signalsBlocked()
        self.table.blockSignals(True)
        try:
            # Remove old visual totals first.
            for row in range(self.table.rowCount()-1, -1, -1):
                if self._is_total(row):
                    self.table.removeRow(row)
            # Recalculate rows without emitting itemChanged while a load/refresh is in progress.
            for row in range(self.table.rowCount()):
                if any(self.table.item(row,c) and (
                    self.table.item(row,c).text().strip() or self.table.item(row,c).data(Qt.UserRole) is not None
                ) for c in range(11)):
                    self._ensure_row(row)
                    self._write_calculated(row, self._line_from_row(row))
            if self.table.rowCount() == 0:
                self.table.insertRow(0); self._ensure_row(0)
                return

            self._normalize_employee_display()
            groups = []
            for row in range(self.table.rowCount()):
                line = self._line_from_row(row)
                if not line.employee_name and line.employee_id is None and line.work_type_id is None:
                    continue
                key = (line.employee_id, line.employee_name)
                if not groups or groups[-1][0] != key:
                    groups.append([key, []])
                groups[-1][1].append(row)

            sums = {c: Decimal("0") for c in self.TOTAL_COLS}
            has = {c: False for c in self.TOTAL_COLS}
            def number(r, c):
                item = self.table.item(r, c)
                return dec(item.text() if item else "")
            for _, rows in groups:
                for row in rows:
                    work_item = self.table.item(row, 2)
                    if not (work_item and (work_item.text().strip() or work_item.data(Qt.UserRole) is not None)):
                        continue
                    for c in self.TOTAL_COLS:
                        value = number(row, c)
                        if value is not None:
                            sums[c] += value; has[c] = True

            # Individual subtotal only for specified special departments.
            if self._subtotal_department():
                for (key, rows) in reversed(groups):
                    if key[0] is None and not str(key[1] or "").strip():
                        continue
                    work_rows = [r for r in rows if self.table.item(r,2) and (
                        self.table.item(r,2).text().strip() or self.table.item(r,2).data(Qt.UserRole) is not None
                    )]
                    if not work_rows:
                        continue
                    pos = max(work_rows) + 1
                    self.table.insertRow(pos)
                    for c in range(11): self.table.setItem(pos, c, make_item(""))
                    name = key[1] or "сотруднику"
                    self.table.item(pos,0).setText(f"ИТОГО по {name}:")
                    for c in self.TOTAL_COLS:
                        vals = [number(r,c) for r in work_rows]
                        vals = [v for v in vals if v is not None]
                        if vals:
                            self.table.item(pos,c).setText(fmt(sum(vals, Decimal("0")), 2 if c in {8,10} else 4))
                    self._apply_flags(pos)

            pos = self.table.rowCount()
            self.table.insertRow(pos)
            for c in range(11): self.table.setItem(pos,c,make_item(""))
            self.table.item(pos,0).setText("ИТОГО:")
            for c in self.TOTAL_COLS:
                if has[c]: self.table.item(pos,c).setText(fmt(sums[c], 2 if c in {8,10} else 4))
            self._apply_flags(pos)
        finally:
            self.table.blockSignals(was_blocked)
            self._rc4_totals_busy = False

    def _add_employees(self):
        dlg = EmployeeSelectionDialog(self.db, self)
        if dlg.exec_() != QDialog.Accepted:
            return
        selected = dlg.selected()
        if not selected:
            return
        self._remove_totals()
        existing = {
            self.table.item(r,0).data(Qt.UserRole)
            for r in range(self.table.rowCount())
            if self.table.item(r,0)
        }
        first_identity = None
        was_blocked = self.table.signalsBlocked()
        self.table.blockSignals(True)
        try:
            for emp_id, name in selected:
                if emp_id in existing:
                    continue
                reuse = next((
                    r for r in range(self.table.rowCount())
                    if not self._is_total(r) and not (
                        self.table.item(r,0) and (
                            self.table.item(r,0).data(Qt.UserRole) is not None
                            or _rc4_full_employee_name(self.table.item(r,0))
                        )
                    )
                ), None)
                row = reuse if reuse is not None else self.table.rowCount()
                self._ensure_row(row)
                self.table.setItem(row,0,_rc4_employee_item(name,emp_id,name))
                self._apply_flags(row)
                existing.add(emp_id)
                if first_identity is None:
                    first_identity = (emp_id, name)
        finally:
            self.table.blockSignals(was_blocked)
        self._refresh_totals()
        if first_identity is not None:
            actual_row = self._find_employee_row(*first_identity)
            if actual_row is not None:
                self.table.setCurrentCell(actual_row,0)
                self.table.selectRow(actual_row)

    def _find_employee_row(self, employee_id, employee_name=""):
        normalized = str(employee_name or "").strip().casefold()
        for row in range(self.table.rowCount()):
            if self._is_total(row):
                continue
            item = self.table.item(row, 0)
            if item is None:
                continue
            if employee_id is not None and item.data(Qt.UserRole) == employee_id:
                return row
            if employee_id is None and normalized and _rc4_full_employee_name(item).strip().casefold() == normalized:
                return row
        return None

    def _target_employee(self):
        """Resolve the employee from the current visual selection.

        Totals can be inserted above later employees, so a stale row index must
        never make work jump to the previous worker.  When the current row is a
        total, prefer the following employee before looking backwards.
        """
        row = self.table.currentRow()
        ordered = []
        if row >= 0:
            ordered.append(row)
            ordered.extend(range(row + 1, self.table.rowCount()))
            ordered.extend(range(row - 1, -1, -1))
        else:
            ordered.extend(range(self.table.rowCount()))
        seen = set()
        for r in ordered:
            if r in seen or self._is_total(r):
                continue
            seen.add(r)
            item = self.table.item(r, 0)
            if item and (item.data(Qt.UserRole) is not None or _rc4_full_employee_name(item)):
                return r, item.data(Qt.UserRole), _rc4_full_employee_name(item)
        return None, None, ""

    def _add_works(self):
        grouped_mode = self._grouped_assignment_department()
        target_snapshot = self._target_employee() if grouped_mode else (None, None, "")
        dlg = WorkSelectionDialog(self.db, self)
        if dlg.exec_() != QDialog.Accepted:
            return
        selected = dlg.selected()
        if not selected:
            return
        self._remove_totals()

        if grouped_mode:
            # Students / Students night / pieceworker / separate worker: Heavy grouped mode.
            target, emp_id, emp_name = target_snapshot
            if target is None:
                warn(self, "Работы", "Сначала добавьте хотя бы одного работника.")
                self._refresh_totals()
                return
            rows = []
            for r in range(self.table.rowCount()):
                item = self.table.item(r, 0)
                if item and (
                    (emp_id is not None and item.data(Qt.UserRole) == emp_id)
                    or (emp_id is None and _rc4_full_employee_name(item) == emp_name)
                ):
                    rows.append(r)
            existing = {self.table.item(r, 2).data(Qt.UserRole) for r in rows if self.table.item(r, 2)}
            insert_at = max(rows) + 1 if rows else self.table.rowCount()
            reusable = next(
                (r for r in rows if not (self.table.item(r, 2) and self.table.item(r, 2).text().strip())),
                None,
            )
            was_blocked = self.table.signalsBlocked()
            self.table.blockSignals(True)
            try:
                first_work = not any(
                    self.table.item(r, 2) and self.table.item(r, 2).text().strip()
                    for r in rows
                )
                for work_id, name, code, price in selected:
                    if work_id in existing:
                        continue
                    row = reusable if reusable is not None else insert_at
                    if reusable is None:
                        self.table.insertRow(row)
                        insert_at += 1
                    reusable = None
                    self._ensure_row(row)
                    self.table.setItem(
                        row, 0,
                        _rc4_employee_item(emp_name if first_work else "", emp_id, emp_name),
                    )
                    self.table.setItem(row, 2, make_item(name, work_id))
                    self.table.setItem(row, 3, make_item(code))
                    self.table.setItem(row, 4, make_item(fmt(price)))
                    self._apply_flags(row)
                    existing.add(work_id)
                    first_work = False
            finally:
                self.table.blockSignals(was_blocked)
            self._refresh_totals()
            actual_row = self._find_employee_row(emp_id, emp_name)
            if actual_row is not None:
                self.table.setCurrentCell(actual_row, 0)
                self.table.selectRow(actual_row)
            return

        # Ordinary departments: employees and works are independent columns.
        # Works fill rows without a work; extra works create work-only rows.
        free_rows=[]
        for r in range(self.table.rowCount()):
            if self._is_total(r): continue
            item=self.table.item(r,2)
            if not (item and (item.data(Qt.UserRole) is not None or item.text().strip())):
                free_rows.append(r)
        was_blocked=self.table.signalsBlocked(); self.table.blockSignals(True)
        try:
            next_free=0
            for work_id,name,code,price in selected:
                if next_free < len(free_rows):
                    row=free_rows[next_free]; next_free+=1
                else:
                    row=self.table.rowCount(); self.table.insertRow(row)
                self._ensure_row(row)
                self.table.setItem(row,2,make_item(name,work_id)); self.table.setItem(row,3,make_item(code)); self.table.setItem(row,4,make_item(fmt(price)))
                self._apply_flags(row)
        finally:
            self.table.blockSignals(was_blocked)
        self._refresh_totals()
        if selected:
            first=free_rows[0] if free_rows else max(0,self.table.rowCount()-len(selected)-1)
            if 0 <= first < self.table.rowCount(): self.table.setCurrentCell(first,2)

    def _selected_data_rows(self):
        rows = {idx.row() for idx in self.table.selectedIndexes() if not self._is_total(idx.row())}
        current = self.table.currentRow()
        if current >= 0 and not self._is_total(current):
            rows.add(current)
        return sorted(rows)

    def _delete_rows(self):
        rows = self._selected_data_rows()
        if not rows:
            warn(self, "Удаление", "Выберите строку с работником или работой.")
            return

        menu = QMenu(self)
        delete_work = menu.addAction("Удалить работу (очистить строку)")
        delete_employee = menu.addAction("Удалить работника")
        pos = self.delete_row_btn.mapToGlobal(QPoint(0, self.delete_row_btn.height()))
        action = menu.exec_(pos)
        if action is None:
            return

        self._remove_totals()
        was_blocked = self.table.signalsBlocked()
        self.table.blockSignals(True)
        try:
            if action == delete_employee:
                # In grouped departments one employee can occupy several work rows.
                # Remove the worker identity from the whole selected employee block,
                # but keep every work and all entered work values intact.
                identities = []
                for row in rows:
                    item = self.table.item(row, 0)
                    if item is None:
                        continue
                    emp_id = item.data(Qt.UserRole)
                    full = _rc4_full_employee_name(item)
                    if emp_id is not None or full:
                        key = (emp_id, full)
                        if key not in identities:
                            identities.append(key)
                for row in range(self.table.rowCount()):
                    item = self.table.item(row, 0)
                    if item is None:
                        continue
                    key = (item.data(Qt.UserRole), _rc4_full_employee_name(item))
                    if key in identities:
                        self.table.setItem(row, 0, _rc4_employee_item("", None, ""))
                        self._apply_flags(row)
            elif action == delete_work:
                # Keep the worker, clear the whole work payload.  A pure work-only
                # row becomes empty and can be removed completely.
                remove_after = []
                for row in rows:
                    if row >= self.table.rowCount():
                        continue
                    employee_item = self.table.item(row, 0)
                    has_employee = bool(employee_item and (
                        employee_item.data(Qt.UserRole) is not None
                        or _rc4_full_employee_name(employee_item)
                    ))
                    for col in range(1, 11):
                        role = None if col != 2 else None
                        self.table.setItem(row, col, make_item("", role, editable=col in self.MANUAL))
                    self._apply_flags(row)
                    if not has_employee:
                        remove_after.append(row)
                for row in sorted(remove_after, reverse=True):
                    self.table.removeRow(row)
        finally:
            self.table.blockSignals(was_blocked)

        self._refresh_totals()

    def _load_order(self, order):
        info_data = order["info"]
        d = QDate.fromString(str(info_data.get("order_date", "")), "dd-MM-yyyy")
        if d.isValid(): self.order_date.setDate(d)
        self.shift.setCurrentText(str(info_data.get("shift_type", "")))
        self._set_combo_data(self.master, info_data.get("master_id"))
        self._set_combo_data(self.department, info_data.get("department_id"))
        self.comment.setText(str(info_data.get("comment", "") or ""))
        if hasattr(self,"separate_worker_check"):
            self.separate_worker_check.setChecked(bool(info_data.get("separate_worker",False)))
        was_blocked = self.table.signalsBlocked(); self.table.blockSignals(True)
        try:
            self.table.setRowCount(0)
            grouped = self._grouped_assignment_department()
            last_key = None
            for line in order.get("lines", []):
                row = self.table.rowCount(); self.table.insertRow(row); self._ensure_row(row)
                key = (line.employee_id, str(line.employee_name or ""))
                display = "" if grouped and key == last_key else str(line.employee_name or "")
                self.table.setItem(row,0,_rc4_employee_item(display,line.employee_id,line.employee_name))
                self.table.item(row,1).setText(fmt(line.hours))
                self.table.setItem(row,2,make_item(line.work_name,line.work_type_id))
                self.table.setItem(row,3,make_item(line.work_code))
                self.table.setItem(row,4,make_item(fmt(line.price)))
                self.table.item(row,5).setText(fmt(line.fixed_boxes))
                self.table.item(row,6).setText(fmt(line.fixed_weight))
                self.table.item(row,9).setText(fmt(line.actual_value))
                self._write_calculated(row,line); self._apply_flags(row)
                last_key = key
        finally:
            self.table.blockSignals(was_blocked)
        self._refresh_totals()

    def load_draft_payload(self, payload: dict):
        d = QDate.fromString(str(payload.get("order_date", "")), "dd-MM-yyyy")
        if d.isValid(): self.order_date.setDate(d)
        self.shift.setCurrentText(str(payload.get("shift_type", "Ночная")))
        self._set_combo_data(self.master,payload.get("master_id")); self._set_combo_data(self.department,payload.get("department_id"))
        self.comment.setText(str(payload.get("comment", "") or ""))
        if hasattr(self,"separate_worker_check"):
            self.separate_worker_check.setChecked(bool(payload.get("separate_worker",False)))
        from .domain import OrderLine
        was_blocked = self.table.signalsBlocked(); self.table.blockSignals(True)
        try:
            self.table.setRowCount(0)
            grouped = self._grouped_assignment_department()
            last_key = None
            for raw in payload.get("lines", []):
                line = OrderLine(
                    employee_id=raw.get("employee_id"), employee_name=str(raw.get("employee_name", "") or ""),
                    work_type_id=raw.get("work_type_id"), work_name=str(raw.get("work_name", "") or ""),
                    work_code=str(raw.get("work_code", "") or ""), price=dec(raw.get("price")),
                    hours=dec(raw.get("hours")), fixed_boxes=dec(raw.get("fixed_boxes")),
                    fixed_weight=dec(raw.get("fixed_weight")), actual_value=dec(raw.get("actual_value")),
                )
                row=self.table.rowCount(); self.table.insertRow(row); self._ensure_row(row)
                key=(line.employee_id,line.employee_name); display="" if grouped and key==last_key else line.employee_name
                self.table.setItem(row,0,_rc4_employee_item(display,line.employee_id,line.employee_name))
                self.table.item(row,1).setText(fmt(line.hours)); self.table.setItem(row,2,make_item(line.work_name,line.work_type_id)); self.table.setItem(row,3,make_item(line.work_code)); self.table.setItem(row,4,make_item(fmt(line.price))); self.table.item(row,5).setText(fmt(line.fixed_boxes)); self.table.item(row,6).setText(fmt(line.fixed_weight)); self.table.item(row,9).setText(fmt(line.actual_value)); self._write_calculated(row,line); self._apply_flags(row)
                last_key=key
        finally:
            self.table.blockSignals(was_blocked)
        self._refresh_totals()

    def get_data(self) -> dict:
        # Preserve employee-only rows in the layout; they are intentionally allowed.
        lines = []
        for row in range(self.table.rowCount()):
            if self._is_total(row):
                continue
            line = self._line_from_row(row)
            if (
                line.employee_id is not None or line.employee_name
                or line.work_type_id is not None or line.work_name
            ):
                lines.append(line)
        return {
            "order_date": self.order_date.date().toString("dd-MM-yyyy"),
            "shift_type": source_text(self.shift),
            "master_id": self.master.currentData(),
            "department_id": self.department.currentData(),
            "comment": self.comment.text().strip(),
            "separate_worker": bool(getattr(self,"separate_worker_check",None) and self.separate_worker_check.isChecked()),
            "lines": lines,
        }

    def _validate(self):
        data = self.get_data()
        if data["master_id"] is None:
            return "Не выбран мастер"
        if data["department_id"] is None:
            return "Не выбрано подразделение"
        works = [ln for ln in data["lines"] if ln.work_type_id is not None or ln.work_name]
        if not works:
            return "В наряде нет работ"
        for i, line in enumerate(works, 1):
            for label, val in (
                ("часы", line.hours),
                ("количество коробок", line.fixed_boxes),
                ("вес коробок", line.fixed_weight),
                ("ФАКТ", line.actual_value),
            ):
                if val is not None and val < 0:
                    return f"Работа {i}: поле «{label}» не может быть отрицательным"
        return None

    def current_content_signature(self):
        data = self.get_data()
        return order_content_signature(
            data["order_date"], data["shift_type"], data["master_id"], data["department_id"],
            data["lines"], data["comment"],
        )

    def has_changes(self) -> bool:
        if self.order is None:
            return True
        separate_worker = self.separate_worker_check.isChecked()
        return (self.current_content_signature() != self._rc4_original_signature
                or separate_worker != bool(self.order["info"].get("separate_worker")))

    def _save_draft(self):
        try:
            data = self.get_data()
            if not data["lines"]:
                return
            payload = {k:v for k,v in data.items() if k != "lines"}
            payload["parent_order_id"] = self.order_id
            payload["lines"] = [line.__dict__ | {
                "price":fmt(line.price), "hours":fmt(line.hours), "fixed_boxes":fmt(line.fixed_boxes),
                "fixed_weight":fmt(line.fixed_weight), "actual_value":fmt(line.actual_value),
            } for line in data["lines"]]
            payload["updated_at"] = datetime.now().isoformat(timespec="seconds")
            self._draft_path().write_text(json.dumps(payload,ensure_ascii=False,default=str,indent=2),encoding="utf-8")
        except Exception:
            pass


class RC4MainWindow(RC3MainWindow):
    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(0, self._apply_native_titlebars)

    def _apply_native_titlebars(self):
        dark = self.ui_settings.theme == "dark"
        for widget in QApplication.topLevelWidgets():
            try: _rc4_set_windows_titlebar_dark(widget, dark)
            except Exception: pass

    def _theme_toggled(self, checked):
        super()._theme_toggled(checked)
        # Theme changes only here (and is persisted immediately); saving an order never touches it.
        try: self.settings_store.save(self.ui_settings)
        except Exception: pass
        QTimer.singleShot(0, self._apply_native_titlebars)

    def _apply_theme(self):
        super()._apply_theme()
        try:
            self._style_audit_help_badge()
        except Exception:
            pass
        QTimer.singleShot(0, self._apply_native_titlebars)

    def _animate_fullscreen_hint(self):
        label = getattr(self, "fullscreen_hint_label", None)
        if label is None:
            return
        try:
            old = getattr(self, "_fullscreen_hint_anim", None)
            if old is not None: old.stop()
            effect = QGraphicsOpacityEffect(label); label.setGraphicsEffect(effect)
            anim = QPropertyAnimation(effect, b"opacity", label)
            anim.setDuration(430); anim.setStartValue(1.0); anim.setKeyValueAt(.5,.28); anim.setEndValue(1.0)
            anim.setEasingCurve(QEasingCurve.InOutQuad)
            self._fullscreen_hint_anim = anim; self._fullscreen_hint_effect = effect
            anim.finished.connect(lambda: label.setGraphicsEffect(None))
            anim.start()
        except Exception:
            pass

    def _show_fullscreen_feedback(self, entering: bool):
        old = getattr(self, "_fullscreen_feedback", None)
        if old is not None:
            try:
                old.hide()
                old.deleteLater()
            except (RuntimeError, AttributeError):
                pass
        self._fullscreen_feedback = None
        try:
            feedback = _RC4FullscreenFeedback(self, entering)
            self._fullscreen_feedback = feedback
            feedback.destroyed.connect(
                lambda *_: setattr(self, "_fullscreen_feedback", None)
                if getattr(self, "_fullscreen_feedback", None) is feedback else None
            )
            feedback.start()
        except Exception:
            self._fullscreen_feedback = None

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            entering = not self.isFullScreen()
            self._animate_fullscreen_hint()
            if entering:
                self.showFullScreen(); self.fullscreen_hint_label.setText("Esc - выйти из полноэкранного режима")
            else:
                self.showMaximized(); self.fullscreen_hint_label.setText("Esc - для полноэкранного режима")
            QTimer.singleShot(55, lambda e=entering: self._show_fullscreen_feedback(e))
            return
        super(RC3MainWindow, self).keyPressEvent(event)

    def edit_order(self):
        ref = self._selected_ref()
        if isinstance(ref, str):
            self._open_draft(Path(ref))
            return
        order_id = ref if isinstance(ref, int) else None
        if not order_id or not self.can(Permission.ORDERS_EDIT):
            return
        token = None
        dialog = None
        try:
            if not self.db.is_latest_order(order_id):
                warn(self, "Редактирование", "Редактировать можно только последнюю версию наряда")
                return
            token, owner = self.db.acquire_edit_lock(order_id, self.user)
            if not token:
                warn(self, "Наряд уже редактируется", f"Пользователь: {owner.get('username')}\nКомпьютер: {owner.get('computer')}")
                return
            order = self.db.get_order(order_id)
            if order is None:
                warn(self, "Редактирование", "Наряд больше недоступен.")
                return
            dialog = WorkOrderDialog(self.db, self.user, order=order, lock_token=token, parent=self)
            if dialog.exec_() != QDialog.Accepted:
                return
            if not dialog.has_changes():
                dialog._delete_draft()
                info(self, "Наряд", f"Наряд № {order['info'].get('version', '')} не изменён. Новая версия не создана.")
                return
            data = dialog.get_data()
            new_id = self.db.save_order(
                self.user, data["order_date"], data["shift_type"], data["master_id"],
                data["department_id"], data["lines"], data["comment"], parent_id=order_id,
                separate_worker=bool(data.get("separate_worker", False)),
            )
            dialog._delete_draft()
            version = self.db.get_order(new_id)["info"]["version"]
            info(self, "Наряд", f"Изменения сохранены как новая версия № {version}")
            self._auto_backup("order_edited")
        except StaleOrderError as exc:
            warn(self, "Редактирование", str(exc))
        except Exception as exc:
            error(self, "Редактирование", exc)
        finally:
            if dialog is not None:
                dialog.stop_lock()
                dialog.deleteLater()
            elif token:
                self.db.release_edit_lock(order_id, token)
            if token:
                self.refresh_orders()

    def _build_admin_tab(self):
        tab = super()._build_admin_tab()
        self._upgrade_admin_status(tab)
        self._upgrade_admin_help_and_restore(tab)
        return tab

    def _upgrade_admin_status(self, tab):
        btn = getattr(self,"admin_sync_btn",None); state = getattr(self,"admin_db_state",None)
        if btn is None or state is None:
            return
        layout = _rc4_find_layout_with_widget(tab.layout(), btn)
        if layout is None:
            return
        btn.setText("⟳"); btn.setObjectName("AdminSyncIconButton"); btn.setFixedSize(46,46)
        btn.setToolTip("Синхронизировать текущие данные и проверить общую БД")
        layout.removeWidget(state)
        self.admin_last_sync = QLabel("Последняя синхронизация: —")
        self.admin_last_sync.setObjectName("AdminLastSyncLabel")
        self.admin_db_dot = QLabel("●")
        self.admin_db_dot.setObjectName("AdminDbPulseDot")
        self.admin_db_dot.setFixedWidth(15)
        state.setObjectName("AdminDbStateText")
        state.setTextInteractionFlags(Qt.TextSelectableByMouse)
        state.setToolTip("")
        self._admin_db_hover_filter = _RC5InfoHoverFilter(state, self._db_status_help_text)
        layout.insertWidget(1,self.admin_last_sync)
        layout.insertWidget(2,self.admin_db_dot)
        layout.insertWidget(3,state,1)
        self._set_last_sync_now()
        self._apply_last_ping()

    def _upgrade_admin_help_and_restore(self, tab):
        for button in tab.findChildren(QPushButton):
            if "Восстановить" in button.text():
                button.setText("🔄 Восстановить"); button.setObjectName("RestoreBackupButton")
        audit = getattr(self,"audit_table",None)
        if audit is not None:
            group = audit.parentWidget()
            while group is not None and not isinstance(group,QGroupBox):
                group = group.parentWidget()
            if isinstance(group,QGroupBox) and getattr(self,"audit_help_badge",None) is None:
                group.setTitle("")
                lay = group.layout()
                header = QHBoxLayout()
                title = QLabel("Журнал действий")
                title.setStyleSheet("color:#007AFF;font-weight:900;background:transparent;")
                badge = QLabel("?")
                badge.setAlignment(Qt.AlignCenter)
                badge.setFixedSize(22,22)
                badge.setCursor(Qt.WhatsThisCursor)
                self.audit_help_badge = badge
                self._style_audit_help_badge()
                effect = QGraphicsOpacityEffect(badge)
                badge.setGraphicsEffect(effect)
                effect.setOpacity(1.0)
                anim = QPropertyAnimation(effect,b"opacity",badge)
                anim.setDuration(1100)
                anim.setStartValue(1.0)
                anim.setKeyValueAt(.5,.30)
                anim.setEndValue(1.0)
                anim.setLoopCount(-1)
                anim.setEasingCurve(QEasingCurve.InOutSine)
                anim.start()
                self._audit_help_effect = effect
                self._audit_help_anim = anim
                self._audit_help_hover_filter = _RC5InfoHoverFilter(badge, self._audit_help_text)
                header.addWidget(title)
                header.addWidget(badge)
                header.addStretch(1)
                if isinstance(lay,QVBoxLayout):
                    lay.insertLayout(0,header)

    def _audit_help_text(self):
        return (
            "Журнал действий показывает, кто, когда и что сделал в SmartOrder: "
            "создание и редактирование нарядов, импорт справочников, резервные копии, "
            "восстановление и действия с пользователями. Он нужен для аудита и диагностики."
        )

    def _db_status_help_text(self):
        ok, ms, message = getattr(self, "_last_ping", (False, 0.0, "Проверка..."))
        path = str(database_path())
        if ok:
            return (
                f"Состояние общей базы SmartOrder\n"
                f"Путь: {path}\n"
                f"Время ответа: {ms:.0f} мс\n"
                "Показана медиана трёх SQLite-запросов после отдельного SMB-прогрева."
            )
        return f"Состояние общей базы SmartOrder\nПуть: {path}\n{message}"

    def _style_audit_help_badge(self):
        badge = getattr(self, "audit_help_badge", None)
        if badge is None:
            return
        if self.ui_settings.theme == "dark":
            badge.setStyleSheet(
                "color:#FFFFFF;background:transparent;border:1px solid #FFFFFF;"
                "border-radius:10px;font-weight:900;"
            )
        else:
            badge.setStyleSheet(
                "color:#000000;background:transparent;border:1px solid #000000;"
                "border-radius:10px;font-weight:900;"
            )

    def _ensure_db_dot_animation(self, running: bool):
        dot = getattr(self,"admin_db_dot",None)
        if dot is None:return
        anim = getattr(self,"_admin_db_dot_anim",None)
        if running:
            if anim is None:
                effect=QGraphicsOpacityEffect(dot);dot.setGraphicsEffect(effect);effect.setOpacity(1.0)
                anim=QPropertyAnimation(effect,b"opacity",dot);anim.setDuration(1200);anim.setStartValue(1.0);anim.setKeyValueAt(.5,.30);anim.setEndValue(1.0);anim.setLoopCount(-1);anim.setEasingCurve(QEasingCurve.InOutSine)
                self._admin_db_dot_anim=anim;self._admin_db_dot_effect=effect;anim.start()
            elif anim.state()!=QPropertyAnimation.Running:anim.start()
        elif anim is not None:
            anim.stop()
            try:self._admin_db_dot_effect.setOpacity(1.0)
            except Exception:pass

    def _apply_last_ping(self):
        state=getattr(self,"admin_db_state",None)
        dot=getattr(self,"admin_db_dot",None)
        if state is None or dot is None:
            try:return super()._apply_last_ping()
            except Exception:return
        ok,ms,message=self._last_ping
        path=str(database_path())
        if ok:
            dot.setStyleSheet("color:#30D158;font-size:15px;font-weight:900;background:transparent;")
            self._ensure_db_dot_animation(True)
            suffix="медленный ответ · " if ms>300 else ""
            state.setText(f"БД доступна · {suffix}{ms:.0f} мс · {path}")
            state.setStyleSheet("color:#1D1D1F;font-weight:800;background:transparent;" if self.ui_settings.theme!="dark" else "color:#F5F5F7;font-weight:800;background:transparent;")
            state.setToolTip("")
        else:
            self._ensure_db_dot_animation(False)
            color="#FF9F0A" if message=="Проверка..." else "#FF453A"
            dot.setStyleSheet(f"color:{color};font-size:15px;font-weight:900;background:transparent;")
            state.setText("БД: проверка…" if message=="Проверка..." else f"БД недоступна · {path}")
            state.setToolTip("")

    def _ping_done(self,ok:bool,ms:float,message:str):
        self._ping_running=False;self._last_ping=(ok,ms,message);self._apply_last_ping()

    def _set_last_sync_now(self):
        lab=getattr(self,"admin_last_sync",None)
        if lab is not None:
            lab.setText("Последняя синхронизация: " + datetime.now().strftime("%d-%m-%Y %H:%M:%S"))

    def _sync_current_tab(self):
        super()._sync_current_tab(); self._set_last_sync_now()

    def refresh_users(self):
        if not self.user.has_role("Администратор") or not hasattr(self,"users_table"):
            return
        rows=self.db.list_users();self.users_table.setRowCount(len(rows));self.users_table.setColumnWidth(3,430)
        for i,r in enumerate(rows):
            uid,username,role,active=int(r[0]),str(r[1]),str(r[2]),bool(r[3])
            self.users_table.setItem(i,0,make_item(username,uid));self.users_table.setItem(i,1,make_item(role));self.users_table.setItem(i,2,make_item("Активен" if active else "Отключён"))
            host=QWidget();row_layout=QHBoxLayout(host);row_layout.setContentsMargins(4,4,4,4);row_layout.setSpacing(8)
            edit_btn=QPushButton("Изменить");edit_btn.setObjectName("UserEditButton")
            delete_btn=QPushButton("Удалить");delete_btn.setObjectName("UserDeleteButton")
            toggle_btn=QPushButton("Отключить" if active else "Включить");toggle_btn.setObjectName("UserToggleButton")
            edit_btn.clicked.connect(lambda _,u=uid,n=username,rn=role:self._edit_user_by_id(u,n,rn))
            delete_btn.clicked.connect(lambda _,u=uid,n=username:self._delete_user_by_id(u,n))
            toggle_btn.clicked.connect(lambda _,u=uid,a=active:self._toggle_user_by_id(u,a))
            row_layout.addWidget(edit_btn);row_layout.addWidget(delete_btn);row_layout.addWidget(toggle_btn);row_layout.addStretch(1)
            self.users_table.setCellWidget(i,3,host);self.users_table.setRowHeight(i,62)

    def _delete_user_by_id(self,uid,username):
        if question(self,"Удаление",f"Удалить пользователя «{username}»?\n\nЭто действие нельзя отменить.")!=QMessageBox.Yes:return
        try:self.db.delete_user(self.user,uid);self.refresh_users();info(self,"Пользователь",f"Пользователь «{username}» удалён.")
        except Exception as exc:error(self,"Удаление пользователя",exc)

    def closeEvent(self,event):
        if getattr(self,"_rc4_exit_confirmed",False):
            try:self.settings_store.save(self.ui_settings)
            except Exception:pass
            event.accept();return
        if question(self,"Выход","Вы действительно хотите выйти?")!=QMessageBox.Yes:
            event.ignore();return
        self._rc4_exit_confirmed=True
        try:self.settings_store.save(self.ui_settings)
        except Exception:pass
        event.accept()


# Final runtime aliases for RC4.
HeavyWorkOrderDialog = RC4WorkOrderDialog
WorkOrderDialog = RC4WorkOrderDialog
_lite_ui.WorkOrderDialog = RC4WorkOrderDialog
HeavyMainWindow = RC4MainWindow
MainWindow = RC4MainWindow

# ===========================================================================
# RC12 — compact employee deletion, shared live drafts, cross-client refresh,
#        and Caps Lock feedback on the login dialog.
# ===========================================================================

_RC12_DRAFT_REVISION = ".revision"


def _rc12_shared_drafts_dir(create: bool = False) -> Path:
    # Do not call shared_dirs() from the live watcher: that helper mkdirs all
    # backup folders and would add several SMB metadata round-trips every poll.
    path = workshop_root() / "drafts"
    if create:
        path.mkdir(parents=True, exist_ok=True)
    return path


def _rc12_touch_draft_revision(folder=None) -> None:
    """Notify other clients that the shared draft list changed."""
    try:
        folder = _rc12_shared_drafts_dir(create=True) if folder is None else folder
        target = folder / _RC12_DRAFT_REVISION
        tmp = folder / f"{_RC12_DRAFT_REVISION}.{os.getpid()}.tmp"
        tmp.write_text(str(time.time_ns()), encoding="ascii")
        os.replace(tmp, target)
    except Exception:
        pass


def _rc12_read_draft_revision() -> str:
    try:
        return (_rc12_shared_drafts_dir() / _RC12_DRAFT_REVISION).read_text(encoding="ascii").strip()
    except Exception:
        return "0"


class RC12LoginDialog(HeavyLoginDialog):
    """Heavy login with a subtle blinking Caps Lock indicator."""
    def __init__(self, db: Database, parent=None):
        super().__init__(db, parent)
        self._caps_label = QLabel("Caps Lock включён", self)
        self._caps_label.setAlignment(Qt.AlignCenter)
        self._caps_label.setStyleSheet(
            "color:rgba(255,255,255,190);background:transparent;border:none;"
            "font-size:11px;font-weight:700;"
        )
        self._caps_label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self._caps_effect = QGraphicsOpacityEffect(self._caps_label)
        self._caps_label.setGraphicsEffect(self._caps_effect)
        self._caps_effect.setOpacity(.18)
        self._caps_anim = QPropertyAnimation(self._caps_effect, b"opacity", self)
        self._caps_anim.setDuration(1050)
        self._caps_anim.setStartValue(.15)
        self._caps_anim.setKeyValueAt(.5, .62)
        self._caps_anim.setEndValue(.15)
        self._caps_anim.setLoopCount(-1)
        self._caps_anim.setEasingCurve(QEasingCurve.InOutSine)
        self._caps_label.hide()
        self._caps_timer = QTimer(self)
        self._caps_timer.setInterval(180)
        self._caps_timer.timeout.connect(self._update_caps_state)
        self._caps_timer.start()
        QTimer.singleShot(0, self._position_caps_label)
        self._update_caps_state()

    @staticmethod
    def _caps_lock_on() -> bool:
        if os.name != "nt":
            return False
        try:
            import ctypes
            return bool(ctypes.windll.user32.GetKeyState(0x14) & 1)
        except Exception:
            return False

    def _position_caps_label(self):
        try:
            pos = self.password_edit.mapTo(self, QPoint(0, 0))
            width = self.password_edit.width()
            self._caps_label.setGeometry(pos.x(), pos.y() + self.password_edit.height() + 1, width, 20)
            self._caps_label.raise_()
        except Exception:
            pass

    def _update_caps_state(self):
        enabled = self._caps_lock_on()
        if enabled:
            self._position_caps_label()
            if not self._caps_label.isVisible():
                self._caps_label.show(); self._caps_label.raise_()
            if self._caps_anim.state() != QPropertyAnimation.Running:
                self._caps_anim.start()
        else:
            if self._caps_anim.state() == QPropertyAnimation.Running:
                self._caps_anim.stop()
            self._caps_label.hide()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._position_caps_label()


class RC12WorkOrderDialog(RC4WorkOrderDialog):
    """RC12 row deletion semantics and shared drafts."""

    def _draft_path(self) -> Path:
        existing = getattr(self, "_rc12_draft_file", None)
        if existing:
            return Path(existing)
        safe_host = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in socket.gethostname()) or "pc"
        if self.order_id:
            name = f"order_{self.order_id}_{self.user.id}_{safe_host}.json"
        else:
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            name = f"new_order_{self.user.id}_{safe_host}_{os.getpid()}_{stamp}.json"
        try:
            path = _rc12_shared_drafts_dir() / name
        except Exception:
            path = local_drafts_dir() / name
        self._rc12_draft_file = path
        return path

    def _save_draft(self):
        try:
            data = self.get_data()
            if not data["lines"]:
                return
            payload = {k: v for k, v in data.items() if k != "lines"}
            payload["parent_order_id"] = self.order_id
            payload["draft_owner_id"] = self.user.id
            payload["draft_owner_username"] = self.user.username
            payload["draft_owner_computer"] = socket.gethostname()
            payload["lines"] = [line.__dict__ | {
                "price": fmt(line.price), "hours": fmt(line.hours),
                "fixed_boxes": fmt(line.fixed_boxes), "fixed_weight": fmt(line.fixed_weight),
                "actual_value": fmt(line.actual_value),
            } for line in data["lines"]]
            payload["updated_at"] = datetime.now().isoformat(timespec="seconds")
            path = self._draft_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(path.suffix + f".{os.getpid()}.tmp")
            tmp.write_text(json.dumps(payload, ensure_ascii=False, default=str, indent=2), encoding="utf-8")
            os.replace(tmp, path)
            if path.parent == _rc12_shared_drafts_dir():
                _rc12_touch_draft_revision()
        except Exception:
            # Fallback keeps draft safety even if the shared folder is temporarily unavailable.
            try:
                fallback = local_drafts_dir() / self._draft_path().name
                fallback.write_text(json.dumps(payload, ensure_ascii=False, default=str, indent=2), encoding="utf-8")
                self._rc12_draft_file = fallback
            except Exception:
                pass

    def _delete_draft(self):
        try:
            path = self._draft_path()
            shared = False
            try: shared = path.parent == _rc12_shared_drafts_dir()
            except Exception: pass
            path.unlink(missing_ok=True)
            if shared:
                _rc12_touch_draft_revision()
        except Exception:
            pass

    def _compact_ordinary_employees(self, removed_keys: set[tuple[object, str]]) -> None:
        """Pack remaining employee identities upward while preserving all work columns."""
        data_rows = [r for r in range(self.table.rowCount()) if not self._is_total(r)]
        remaining: list[tuple[object, str]] = []
        seen: set[tuple[object, str]] = set()
        for row in data_rows:
            item = self.table.item(row, 0)
            if item is None:
                continue
            key = (item.data(Qt.UserRole), _rc4_full_employee_name(item))
            if key == (None, "") or key in removed_keys or key in seen:
                continue
            remaining.append(key); seen.add(key)
        for row in data_rows:
            self.table.setItem(row, 0, _rc4_employee_item("", None, ""))
        for row, (emp_id, full) in zip(data_rows, remaining):
            self.table.setItem(row, 0, _rc4_employee_item(full, emp_id, full))
            self._apply_flags(row)
        # Remove only truly empty trailing rows. Work-only rows are preserved.
        for row in range(self.table.rowCount() - 1, -1, -1):
            if self._is_total(row):
                continue
            has_employee = self.table.item(row, 0) and (
                self.table.item(row, 0).data(Qt.UserRole) is not None
                or bool(_rc4_full_employee_name(self.table.item(row, 0)))
            )
            has_work = self.table.item(row, 2) and (
                self.table.item(row, 2).data(Qt.UserRole) is not None
                or bool(self.table.item(row, 2).text().strip())
            )
            if has_employee or has_work:
                break
            self.table.removeRow(row)

    def _delete_rows(self):
        rows = self._selected_data_rows()
        if not rows:
            warn(self, "Удаление", "Выберите строку с работником или работой.")
            return
        menu = QMenu(self)
        delete_work = menu.addAction("Удалить работу (очистить строку)")
        delete_employee = menu.addAction("Удалить работника")
        pos = self.delete_row_btn.mapToGlobal(QPoint(0, self.delete_row_btn.height()))
        action = menu.exec_(pos)
        if action is None:
            return
        self._remove_totals()
        was_blocked = self.table.signalsBlocked(); self.table.blockSignals(True)
        try:
            if action == delete_employee:
                identities: set[tuple[object, str]] = set()
                for row in rows:
                    item = self.table.item(row, 0)
                    if item is None:
                        continue
                    key = (item.data(Qt.UserRole), _rc4_full_employee_name(item))
                    if key != (None, ""):
                        identities.add(key)
                if not identities:
                    return
                if self._grouped_assignment_department():
                    # In grouped Heavy modes the employee owns the complete work block.
                    # Deleting the employee therefore removes every work assigned to them.
                    remove_rows = []
                    for row in range(self.table.rowCount()):
                        if self._is_total(row):
                            continue
                        item = self.table.item(row, 0)
                        if item is None:
                            continue
                        key = (item.data(Qt.UserRole), _rc4_full_employee_name(item))
                        if key in identities:
                            remove_rows.append(row)
                    for row in sorted(remove_rows, reverse=True):
                        self.table.removeRow(row)
                else:
                    # Ordinary departments keep work payload, but employee slots are compacted.
                    self._compact_ordinary_employees(identities)
            elif action == delete_work:
                remove_after = []
                for row in rows:
                    if row >= self.table.rowCount():
                        continue
                    employee_item = self.table.item(row, 0)
                    has_employee = bool(employee_item and (
                        employee_item.data(Qt.UserRole) is not None
                        or _rc4_full_employee_name(employee_item)
                    ))
                    for col in range(1, 11):
                        self.table.setItem(row, col, make_item("", None, editable=col in self.MANUAL))
                    self._apply_flags(row)
                    if not has_employee:
                        remove_after.append(row)
                for row in sorted(remove_after, reverse=True):
                    self.table.removeRow(row)
        finally:
            self.table.blockSignals(was_blocked)
        self._refresh_totals()


class _RC12ChangeBridge(QObject):
    checked = pyqtSignal(int, str)


class RC12MainWindow(RC4MainWindow):
    """Live shared-data watcher without SMB work on the GUI thread."""
    def __init__(self, db: Database, user: SessionUser):
        self._rc12_change_token = None
        self._rc12_draft_revision = None
        self._rc12_watch_running = False
        self._rc12_dirty_tabs = set()
        super().__init__(db, user)
        self._rc12_change_bridge = _RC12ChangeBridge(self)
        self._rc12_change_bridge.checked.connect(self._rc12_changes_checked)
        self._rc12_watch_timer = QTimer(self)
        self._rc12_watch_timer.setInterval(2200)
        self._rc12_watch_timer.timeout.connect(self._rc12_watch_tick)
        self._rc12_watch_timer.start()
        QTimer.singleShot(350, self._rc12_watch_tick)

    def _draft_records(self):
        masters = {int(r[0]): str(r[1]) for r in self.db.get_employees(True)}
        deps = {int(r[0]): str(r[1]) for r in self.db.get_departments()}
        result = []
        paths: list[Path] = []
        try: paths.extend(sorted(_rc12_shared_drafts_dir().glob("*.json")))
        except Exception: pass
        # Keep pre-RC12 local drafts visible on the machine where they were created.
        try: paths.extend(sorted(local_drafts_dir().glob("*.json")))
        except Exception: pass
        seen = set()
        for p in paths:
            key = str(p).casefold()
            if key in seen: continue
            seen.add(key)
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                date = str(data.get("order_date", "")); shift = str(data.get("shift_type", ""))
                mid = data.get("master_id"); did = data.get("department_id"); updated = str(data.get("updated_at", ""))
                owner = str(data.get("draft_owner_username", "") or "").strip()
                computer = str(data.get("draft_owner_computer", "") or "").strip()
                if p.parent == _rc12_shared_drafts_dir():
                    suffix = " · ".join(x for x in (owner, computer) if x)
                    label = "Черновик" + (f" · {suffix}" if suffix else " · общий")
                else:
                    label = "Черновик · локальный"
                result.append((p, label, date, shift,
                    masters.get(int(mid), "") if mid is not None else "",
                    deps.get(int(did), "") if did is not None else "", updated))
            except Exception:
                pass
        return result

    def _order_selection_changed(self):
        super()._order_selection_changed()
        ref = self._selected_ref()
        if not (isinstance(ref, str) and ref.lower().endswith(".json")):
            return
        try:
            data = json.loads(Path(ref).read_text(encoding="utf-8"))
            owner = str(data.get("draft_owner_username", "") or "").strip()
            computer = str(data.get("draft_owner_computer", "") or "").strip()
            self.info_users_list.clear()
            parts = ["Черновик"] + [x for x in (owner, computer) if x]
            self.info_users_list.addItem(" · ".join(parts))
        except Exception:
            pass

    def _open_draft(self, path: Path):
        try: payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc: error(self, "Черновик", exc); return
        parent_id = payload.get("parent_order_id")
        permission = Permission.ORDERS_EDIT if parent_id is not None else Permission.ORDERS_CREATE
        if not self.can(permission):
            warn(self, "Черновик", "Недостаточно прав для продолжения черновика.")
            return
        dlg = WorkOrderDialog(self.db, self.user, parent=self)
        dlg._rc12_draft_file = path
        dlg.load_draft_payload(payload)
        if dlg.exec_() == QDialog.Accepted:
            data = dlg.get_data()
            try:
                oid = self.db.save_order(
                    self.user, data["order_date"], data["shift_type"], data["master_id"],
                    data["department_id"], data["lines"], data["comment"], parent_id=parent_id, separate_worker=bool(data.get("separate_worker",False)),
                )
                path.unlink(missing_ok=True); _rc12_touch_draft_revision(); dlg._delete_draft()
                info(self, "Наряд", f"Наряд № {self.db.get_order(oid)['info']['version']} сохранён")
            except Exception as exc: error(self, "Наряд", exc)
        dlg.deleteLater()
        self.refresh_orders()

    def delete_selected_draft(self):
        ref = self._selected_ref()
        if not isinstance(ref, str): return
        if question(self, "Удаление черновика", "Удалить выбранный черновик?") != QMessageBox.Yes: return
        try:
            path = Path(ref)
            path.unlink(missing_ok=True)
            _rc12_touch_draft_revision(path.parent)
            self.refresh_orders(); info(self, "Черновик", "Черновик удалён.")
        except Exception as exc: error(self, "Черновик", exc)

    def _rc12_watch_tick(self):
        if self._rc12_watch_running:
            return
        self._rc12_watch_running = True
        def worker():
            try:
                db_token = self.db.change_token()
            except Exception:
                db_token = -1
            draft_revision = _rc12_read_draft_revision()
            try: self._rc12_change_bridge.checked.emit(int(db_token), str(draft_revision))
            except Exception: pass
        threading.Thread(target=worker, name="SmartOrderChangeWatch", daemon=True).start()

    def _rc12_changes_checked(self, db_token: int, draft_revision: str):
        self._rc12_watch_running = False
        if self._rc12_change_token is None:
            self._rc12_change_token = db_token
        elif db_token >= 0 and db_token != self._rc12_change_token:
            self._rc12_change_token = db_token
            self.db.invalidate_cache()
            self._rc12_dirty_tabs.update({0,1,2,3})
        if self._rc12_draft_revision is None:
            self._rc12_draft_revision = draft_revision
        elif draft_revision != self._rc12_draft_revision:
            self._rc12_draft_revision = draft_revision
            self._rc12_dirty_tabs.add(0)
        # Never interrupt a modal editor. The next poll/tab switch applies the refresh.
        if QApplication.activeModalWidget() is not None:
            return
        self._rc12_refresh_active_if_dirty()

    def _rc12_refresh_active_if_dirty(self):
        idx = self.tabs.currentIndex() if hasattr(self, "tabs") else -1
        if idx not in self._rc12_dirty_tabs:
            return
        try:
            if idx == 0:
                self.refresh_orders()
            elif idx == 1 and idx in self._loaded_tabs:
                self.refresh_work_types()
            elif idx == 2 and idx in self._loaded_tabs:
                self.refresh_people(); self._refresh_reference_filters()
            elif idx == 3 and idx in self._loaded_tabs:
                self.refresh_audit()
                if self.can(Permission.USERS_VIEW) or self.can(Permission.USERS_MANAGE): self.refresh_users()
            self._rc12_dirty_tabs.discard(idx)
        except Exception:
            pass

    def _tab_changed(self, index):
        super()._tab_changed(index)
        # If another client changed this section while it was hidden, refresh it once.
        if index in self._rc12_dirty_tabs and QApplication.activeModalWidget() is None:
            QTimer.singleShot(0, self._rc12_refresh_active_if_dirty)

    def closeEvent(self, event):
        try: self._rc12_watch_timer.stop()
        except Exception: pass
        super().closeEvent(event)


# Final runtime aliases for RC12.
HeavyWorkOrderDialog = RC12WorkOrderDialog
WorkOrderDialog = RC12WorkOrderDialog
_lite_ui.WorkOrderDialog = RC12WorkOrderDialog
HeavyMainWindow = RC12MainWindow
MainWindow = RC12MainWindow
LoginDialog = RC12LoginDialog


# ==========================================================================
# RC13 — deterministic grouped deletion, text-sized About backplates,
#         drafts only when a NEW order is closed without saving.
# ==========================================================================

class RC13WorkOrderDialog(RC12WorkOrderDialog):
    """Focused RC13 fixes without changing the LiteCore database path."""

    def __init__(self, *args, **kwargs):
        self._rc13_loaded_draft_parent_id = None
        super().__init__(*args, **kwargs)
        # A draft must appear only after the operator closes an unsaved NEW order.
        # The base 30-second autosave would expose a draft while the dialog is still open,
        # and could also create edit-drafts.  Stop it; reject()/X remains the save point.
        try:
            self._draft_timer.stop()
        except Exception:
            pass

    def load_draft_payload(self, payload: dict):
        self._rc13_loaded_draft_parent_id = payload.get("parent_order_id")
        return super().load_draft_payload(payload)

    def _save_draft(self):
        # Existing saved orders never create drafts when Edit is cancelled/closed.
        if self.order_id is not None or self.order is not None:
            return
        # Legacy edit-drafts from previous RCs also must not be re-created on close.
        if self._rc13_loaded_draft_parent_id is not None:
            return
        return super()._save_draft()

    def _delete_rows(self):
        rows = self._selected_data_rows()
        if not rows:
            warn(self, "Удаление", "Выберите строку с работником или работой.")
            return

        menu = QMenu(self)
        delete_work = menu.addAction("Удалить работу (очистить строку)")
        delete_employee = menu.addAction("Удалить работника")
        pos = self.delete_row_btn.mapToGlobal(QPoint(0, self.delete_row_btn.height()))
        action = menu.exec_(pos)
        if action is None:
            return

        # IMPORTANT: capture the semantic target BEFORE removing visual total rows.
        # Total rows sit between employee blocks in Students/Separate worker modes and
        # removing them changes numeric row indexes.  RC12 captured indexes first,
        # which made the first click only remove totals and the second click delete.
        identities: set[tuple[object, str]] = set()
        work_items = []
        if action == delete_employee:
            for row in rows:
                if row < 0 or row >= self.table.rowCount() or self._is_total(row):
                    continue
                item = self.table.item(row, 0)
                if item is None:
                    continue
                key = (item.data(Qt.UserRole), _rc4_full_employee_name(item))
                if key != (None, ""):
                    identities.add(key)
            if not identities:
                warn(self, "Удаление", "В выбранной строке нет работника.")
                return
        else:
            # Keep references to work cells themselves; QTableWidget keeps these items
            # alive when unrelated total rows are removed, so we can find the exact rows
            # after the table has compacted.
            for row in rows:
                if row < 0 or row >= self.table.rowCount() or self._is_total(row):
                    continue
                item = self.table.item(row, 2)
                if item is not None:
                    work_items.append(item)
            if not work_items:
                warn(self, "Удаление", "В выбранной строке нет работы.")
                return

        self._remove_totals()
        was_blocked = self.table.signalsBlocked()
        self.table.blockSignals(True)
        try:
            if action == delete_employee:
                if self._grouped_assignment_department():
                    # Students / Students night / Pieceworker / Separate worker:
                    # employee owns the whole work block, therefore delete it atomically.
                    remove_rows = []
                    for row in range(self.table.rowCount()):
                        item = self.table.item(row, 0)
                        if item is None:
                            continue
                        key = (item.data(Qt.UserRole), _rc4_full_employee_name(item))
                        if key in identities:
                            remove_rows.append(row)
                    for row in reversed(remove_rows):
                        self.table.removeRow(row)
                else:
                    # Ordinary department: remove/compact employee identities only;
                    # work payload remains where it is.
                    self._compact_ordinary_employees(identities)
            else:
                # Resolve selected work rows after total-row removal by item identity.
                resolved_rows = []
                for work_item in work_items:
                    for row in range(self.table.rowCount()):
                        if self.table.item(row, 2) is work_item:
                            resolved_rows.append(row)
                            break
                remove_after = []
                for row in sorted(set(resolved_rows)):
                    employee_item = self.table.item(row, 0)
                    has_employee = bool(employee_item and (
                        employee_item.data(Qt.UserRole) is not None
                        or _rc4_full_employee_name(employee_item)
                    ))
                    for col in range(1, 11):
                        self.table.setItem(row, col, make_item("", None, editable=col in self.MANUAL))
                    self._apply_flags(row)
                    if not has_employee:
                        remove_after.append(row)
                for row in sorted(remove_after, reverse=True):
                    self.table.removeRow(row)
        finally:
            self.table.blockSignals(was_blocked)

        # Exactly one rebuild after the semantic mutation.  Subtotals and grand total
        # never disappear as an intermediate visible state.
        self._refresh_totals()


class RC13MainWindow(RC12MainWindow):
    """RC13 About tab: translucent backing follows the text, not the cards."""

    @staticmethod
    def _rc13_chip(text: str, *, blue: bool = False, bold: bool = False) -> str:
        color = "#0A84FF" if blue else "#F5F5F7"
        weight = "800" if bold else "500"
        # Inline span means the translucent backing follows only the rendered text.
        return (
            '<span style="background-color:rgba(0,0,0,0.52);'
            'padding:2px 5px; color:' + color + '; font-weight:' + weight + ';">'
            + text + '</span>'
        )

    def _build_about_tab(self):
        tab = GifBackgroundWidget(["loading2.gif", "login_background.gif", "resources/loading2.gif"])
        root = QVBoxLayout(tab); root.setContentsMargins(30,20,30,24); root.setSpacing(12)
        logo = QLabel()
        if _set_logo(logo,148,"smartorder_logo_icon_light.png","smartorder_logo_icon.png","smartorder_logo_white.png","smartorder_logo.png"):
            root.addWidget(logo, alignment=Qt.AlignCenter)

        edition = self._about_selectable(QLabel(f"Enterprise Edition · Version: {APP_VERSION}"))
        edition.setAlignment(Qt.AlignCenter)
        edition.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Preferred)
        edition.setStyleSheet(
            "font-size:15px;color:#F5F5F7;background-color:rgba(0,0,0,132);"
            "padding:3px 7px;border-radius:5px;"
        )
        root.addWidget(edition, alignment=Qt.AlignCenter)

        # Cards themselves stay fully transparent.  Only text fragments have backing.
        style = "QFrame#AboutTransparentCard{background:rgba(0,0,0,0);border:none;}"
        cards = QHBoxLayout(); cards.setSpacing(18)
        policy_path = ensure_usage_policy_document()

        system = QFrame(); system.setObjectName("AboutTransparentCard"); system.setStyleSheet(style)
        sv = QVBoxLayout(system); sv.setContentsMargins(14,14,14,14)
        system_lines = [
            self._rc13_chip("System", blue=True, bold=True),
            self._rc13_chip(f"Среда выполнения: Python {platform.python_version()}"),
            self._rc13_chip("Движок: PyQt5 5.15.x"),
            self._rc13_chip("Язык: Python"),
            self._rc13_chip(f"Version: {APP_VERSION}"),
            '<a href="policy" style="color:#0A84FF;text-decoration:none;">' +
                self._rc13_chip("Положение об использовании ПО", blue=True, bold=True) + '</a>',
        ]
        system_html = '<div style="line-height:1.8;">' + '<br><br>'.join(system_lines) + '</div>'
        sb = self._about_browser(
            system_html,
            lambda _url,p=policy_path: QDesktopServices.openUrl(QUrl.fromLocalFile(str(p))) if p else None,
        )
        sv.addWidget(sb,1); cards.addWidget(system,1)

        guide = QFrame(); guide.setObjectName("AboutTransparentCard"); guide.setStyleSheet(style)
        gv = QVBoxLayout(guide); gv.setContentsMargins(14,14,14,14)
        steps = [
            "Заполните справочники: номенклатура, сотрудники, мастера, подразделения.",
            "Во вкладке «Наряд» нажмите «Создать наряд».",
            "Выберите дату, смену, мастера и подразделение.",
            "Добавьте работников и работы.",
            "Заполните часы, фикс или факт.",
            "Сохраните наряд.",
            "При необходимости откройте, отредактируйте или выгрузите наряд в Excel.",
        ]
        guide_lines = [self._rc13_chip("Как работать в программе?", blue=True, bold=True)]
        guide_lines += [self._rc13_chip(f"{i}. {text}") for i,text in enumerate(steps,1)]
        guide_html = '<div style="line-height:1.8;">' + '<br><br>'.join(guide_lines) + '</div>'
        gb = self._about_browser(guide_html); gv.addWidget(gb,1); cards.addWidget(guide,1)
        root.addLayout(cards,1)

        foot = QFrame(); foot.setObjectName("AboutTransparentCard"); foot.setStyleSheet(style)
        fv = QVBoxLayout(foot)
        footer_html = (
            '<div style="text-align:center;line-height:1.8;">' +
            self._rc13_chip("Powered by OITS&amp;ZI", bold=True) + '<br>' +
            self._rc13_chip('Copyright © 2026 ') +
            '<a href="https://tmbsir.ru/" style="color:#0A84FF;text-decoration:none;">' +
            self._rc13_chip("tmbsir", blue=True, bold=True) + '</a></div>'
        )
        fb = self._about_browser(footer_html, lambda url: QDesktopServices.openUrl(url))
        fb.setMaximumHeight(82); fv.addWidget(fb); root.addWidget(foot)

        bottom = QHBoxLayout(); bottom.addStretch()
        self.about_session_label = QLabel(); self.about_session_label.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Preferred)
        self.about_session_label.setStyleSheet(
            "font-size:10px;color:#F5F5F7;background-color:rgba(0,0,0,132);"
            "padding:2px 5px;border-radius:4px;"
        )
        bottom.addWidget(self.about_session_label); root.addLayout(bottom)
        self._update_session_labels()
        return tab


# Final runtime aliases for RC13.
HeavyWorkOrderDialog = RC13WorkOrderDialog
WorkOrderDialog = RC13WorkOrderDialog
_lite_ui.WorkOrderDialog = RC13WorkOrderDialog
HeavyMainWindow = RC13MainWindow
MainWindow = RC13MainWindow
LoginDialog = RC12LoginDialog


# ===========================================================================
# RC14 — compact work deletion, deterministic combo popups, immediate native
#        titlebar recolor, visible FIX/FACT locks, wider audit columns, and
#        Escape auto-repeat protection.
# ===========================================================================

class RC14SmartComboBox(SmartComboBox):
    """Heavy combo popup that never inherits a white native container in dark mode."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMaxVisibleItems(12)

    def showPopup(self):
        view = self.view()
        count = max(1, min(self.count(), self.maxVisibleItems()))
        # Force enough vertical room for every short list item.  In particular,
        # the 2-item Day/Night selector must show both values without wheel scrolling.
        popup_height = max(48, count * 36 + 12)
        try:
            view.setMinimumHeight(popup_height)
            view.setMaximumHeight(popup_height)
            view.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff if self.count() <= self.maxVisibleItems() else Qt.ScrollBarAsNeeded)
            view.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            view.setSpacing(0)
        except Exception:
            pass
        super().showPopup()

        # QComboBox creates a separate top-level popup QFrame on Windows.  Styling
        # only the item view leaves native white strips around it; style the frame,
        # viewport and palettes after Qt has created the popup window.
        theme = str(self.property("theme") or "").lower()
        if theme not in ("dark", "light"):
            try:
                theme = str(self.window().property("theme") or "light").lower()
            except Exception:
                theme = "light"
        dark = theme == "dark"
        bg = QColor("#2C2C2E" if dark else "#FFFFFF")
        fg = QColor("#F5F5F7" if dark else "#1D1D1F")
        border = "rgba(255,255,255,38)" if dark else "rgba(60,60,67,36)"
        try:
            popup = view.window()
            popup.setAttribute(Qt.WA_StyledBackground, True)
            popup.setAutoFillBackground(True)
            pal = popup.palette(); pal.setColor(QPalette.Window, bg); pal.setColor(QPalette.Base, bg); pal.setColor(QPalette.Text, fg); popup.setPalette(pal)
            vpal = view.palette(); vpal.setColor(QPalette.Base, bg); vpal.setColor(QPalette.Window, bg); vpal.setColor(QPalette.Text, fg); view.setPalette(vpal)
            view.viewport().setAutoFillBackground(True); view.viewport().setPalette(vpal)
            popup.setStyleSheet(
                "QFrame{background-color:%s;border:1px solid %s;border-radius:9px;}"
                "QAbstractItemView{background-color:%s;color:%s;border:none;outline:0;padding:4px;}"
                "QAbstractItemView::item{min-height:32px;padding:3px 8px;border:none;}"
                "QAbstractItemView::item:selected{background-color:%s;color:#FFFFFF;}"
                "QAbstractItemView::item:hover{background-color:%s;color:#FFFFFF;}"
                "QScrollBar{background-color:%s;border:none;}"
                % (
                    bg.name(), border, bg.name(), fg.name(),
                    "#0A84FF" if dark else "#007AFF",
                    "#3A3A3C" if dark else "#0A84FF",
                    bg.name(),
                )
            )
            width = max(self.width(), view.minimumWidth(), 320)
            popup.resize(width, popup_height + 4)
            view.resize(width - 2, popup_height)
            from .liquid_effects import style_popup
            style_popup(popup, theme)
            popup.update(); view.update(); view.viewport().update()
        except Exception:
            pass


# All Heavy widgets resolve SmartComboBox from module globals at runtime, so the
# RC14 popup implementation is picked up by both new-order and main-window filters.
SmartComboBox = RC14SmartComboBox


def _rc14_force_windows_titlebar(widget: QWidget, dark: bool) -> None:
    """Apply DWM dark/light frame immediately instead of waiting for activation."""
    # winId() creates a native window. Hidden QComboBox containers and tooltips
    # must never acquire one just because a page/theme changed.
    if isinstance(widget, QFileDialog) or not widget.isWindow() or not widget.isVisible() or widget.windowHandle() is None:
        return
    if widget.windowType() in (Qt.Popup, Qt.ToolTip):
        return
    signature = (int(widget.winId()), bool(dark)) if os.name == "nt" else None
    if signature is not None and getattr(widget, "_legacy_frame_signature", None) == signature:
        return
    _rc4_set_windows_titlebar_dark(widget, dark)
    if os.name != "nt":
        return
    try:
        import ctypes
        hwnd = int(widget.winId())
        # SWP_NOSIZE|SWP_NOMOVE|SWP_NOZORDER|SWP_NOACTIVATE|SWP_FRAMECHANGED
        ctypes.windll.user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, 0x0001|0x0002|0x0004|0x0010|0x0020)
        # RDW_INVALIDATE|RDW_UPDATENOW|RDW_FRAME|RDW_ALLCHILDREN
        ctypes.windll.user32.RedrawWindow(hwnd, None, None, 0x0001|0x0100|0x0400|0x0080)
        widget._legacy_frame_signature = signature
        widget.update()
    except Exception:
        pass


class RC14WorkOrderDialog(RC13WorkOrderDialog):
    """RC14 order editor: compact rows and visually explicit FIX/FACT locks."""

    def _build(self):
        super()._build()
        # Keep both shift values visible without a scroll gesture.
        try:
            self.shift.setMinimumWidth(520)
            self.shift.view().setMinimumWidth(590)
            self.shift.setMaxVisibleItems(8)
        except Exception:
            pass

    @staticmethod
    def _has_work_payload(table: QTableWidget, row: int) -> bool:
        item = table.item(row, 2)
        return bool(item and (item.data(Qt.UserRole) is not None or item.text().strip()))

    def _work_payload(self, row: int) -> dict[int, tuple[str, object]]:
        """Snapshot all work-side cells; employee identity (column 0) is separate."""
        payload = {}
        for col in range(1, 11):
            item = self.table.item(row, col)
            payload[col] = ((item.text() if item else ""), (item.data(Qt.UserRole) if item else None))
        return payload

    def _write_work_payload(self, row: int, payload: dict[int, tuple[str, object]] | None) -> None:
        self._ensure_row(row)
        for col in range(1, 11):
            if payload is None:
                self.table.setItem(row, col, make_item("", None, editable=col in self.MANUAL))
            else:
                text, role = payload.get(col, ("", None))
                self.table.setItem(row, col, make_item(text, role, editable=col in self.MANUAL))
        self._apply_flags(row)

    def _rebuild_ordinary_after_work_delete(self, removed_rows: set[int]) -> None:
        """Ordinary mode = two independent packed lists: employees and work payloads."""
        employees: list[tuple[object, str]] = []
        seen = set()
        works: list[dict[int, tuple[str, object]]] = []
        for row in range(self.table.rowCount()):
            if self._is_total(row):
                continue
            emp = self.table.item(row, 0)
            key = (emp.data(Qt.UserRole), _rc4_full_employee_name(emp)) if emp else (None, "")
            if key != (None, "") and key not in seen:
                employees.append(key); seen.add(key)
            if row not in removed_rows and self._has_work_payload(self.table, row):
                works.append(self._work_payload(row))

        count = max(len(employees), len(works), 1)
        self.table.setRowCount(0)
        for index in range(count):
            row = self.table.rowCount(); self.table.insertRow(row); self._ensure_row(row)
            if index < len(employees):
                emp_id, full = employees[index]
                self.table.setItem(row, 0, _rc4_employee_item(full, emp_id, full))
            else:
                self.table.setItem(row, 0, _rc4_employee_item("", None, ""))
            self._write_work_payload(row, works[index] if index < len(works) else None)

    def _rebuild_grouped_after_work_delete(self, removed_rows: set[int]) -> None:
        """Grouped mode packs works only inside their owner block; blocks never mix."""
        blocks: list[dict] = []
        by_key: dict[tuple[object, str], dict] = {}
        unassigned_counter = 0
        for row in range(self.table.rowCount()):
            if self._is_total(row):
                continue
            emp = self.table.item(row, 0)
            key = (emp.data(Qt.UserRole), _rc4_full_employee_name(emp)) if emp else (None, "")
            if key == (None, ""):
                # Preserve legacy/unassigned work rows as independent blocks.
                if not self._has_work_payload(self.table, row) or row in removed_rows:
                    continue
                block = {"key": (None, ""), "works": [self._work_payload(row)], "token": unassigned_counter}
                unassigned_counter += 1; blocks.append(block)
                continue
            block = by_key.get(key)
            if block is None:
                block = {"key": key, "works": [], "token": None}
                by_key[key] = block; blocks.append(block)
            if row not in removed_rows and self._has_work_payload(self.table, row):
                block["works"].append(self._work_payload(row))

        self.table.setRowCount(0)
        for block in blocks:
            emp_id, full = block["key"]
            works = block["works"]
            if emp_id is None and not full:
                for payload in works:
                    row = self.table.rowCount(); self.table.insertRow(row); self._ensure_row(row)
                    self.table.setItem(row, 0, _rc4_employee_item("", None, ""))
                    self._write_work_payload(row, payload)
                continue
            # Even after deleting the employee's last work, keep one employee-only row.
            rows_needed = max(1, len(works))
            for index in range(rows_needed):
                row = self.table.rowCount(); self.table.insertRow(row); self._ensure_row(row)
                self.table.setItem(row, 0, _rc4_employee_item(full if index == 0 else "", emp_id, full))
                self._write_work_payload(row, works[index] if index < len(works) else None)

    def _apply_flags(self, row):
        super()._apply_flags(row)
        if row < 0 or row >= self.table.rowCount():
            return
        total = self._is_total(row)
        actual = self.table.item(row, 9)
        boxes = self.table.item(row, 5)
        weight = self.table.item(row, 6)
        has_actual = bool(actual and actual.text().strip())
        has_fixed = bool((boxes and boxes.text().strip()) or (weight and weight.text().strip()))
        locked = set()
        reason = ""
        if not total and has_actual:
            locked = {5, 6, 7, 8}; reason = "Недоступно: используется режим ФАКТ"
        elif not total and has_fixed:
            locked = {9, 10}; reason = "Недоступно: используется режим ФИКС"
        theme, _ = _theme_of(self)
        bg = QColor("#5A2328" if theme == "dark" else "#FFE3E1")
        fg = QColor("#FFB3B0" if theme == "dark" else "#B42318")
        for col in range(11):
            item = self.table.item(row, col)
            if item is None:
                continue
            if col in locked:
                item.setBackground(QBrush(bg)); item.setForeground(QBrush(fg)); item.setToolTip(reason)
            else:
                # Remove the explicit RC14 lock brush; QSS resumes control.
                item.setBackground(QBrush()); item.setForeground(QBrush())
                if item.toolTip().startswith("Недоступно: используется режим"):
                    item.setToolTip("")

    def _delete_rows(self):
        rows = self._selected_data_rows()
        if not rows:
            warn(self, "Удаление", "Выберите строку с работником или работой.")
            return

        menu = QMenu(self)
        delete_work = menu.addAction("Удалить работу (очистить строку)")
        delete_employee = menu.addAction("Удалить работника")
        pos = self.delete_row_btn.mapToGlobal(QPoint(0, self.delete_row_btn.height()))
        action = menu.exec_(pos)
        if action is None:
            return

        identities: set[tuple[object, str]] = set()
        work_items: list[QTableWidgetItem] = []
        if action == delete_employee:
            for row in rows:
                if row < 0 or row >= self.table.rowCount() or self._is_total(row):
                    continue
                item = self.table.item(row, 0)
                key = (item.data(Qt.UserRole), _rc4_full_employee_name(item)) if item else (None, "")
                if key != (None, ""):
                    identities.add(key)
            if not identities:
                warn(self, "Удаление", "В выбранной строке нет работника.")
                return
        else:
            for row in rows:
                if row < 0 or row >= self.table.rowCount() or self._is_total(row):
                    continue
                item = self.table.item(row, 2)
                if item is not None and (item.data(Qt.UserRole) is not None or item.text().strip()):
                    work_items.append(item)
            if not work_items:
                warn(self, "Удаление", "В выбранной строке нет работы.")
                return

        self._remove_totals()
        # Resolve selected work rows AFTER total-row removal by item identity.
        removed_work_rows: set[int] = set()
        if action == delete_work:
            for target in work_items:
                for row in range(self.table.rowCount()):
                    if self.table.item(row, 2) is target:
                        removed_work_rows.add(row); break

        was_blocked = self.table.signalsBlocked(); self.table.blockSignals(True)
        try:
            if action == delete_employee:
                if self._grouped_assignment_department():
                    # Grouped employee owns its complete block: remove all rows atomically.
                    remove_rows = []
                    for row in range(self.table.rowCount()):
                        item = self.table.item(row, 0)
                        key = (item.data(Qt.UserRole), _rc4_full_employee_name(item)) if item else (None, "")
                        if key in identities:
                            remove_rows.append(row)
                    for row in reversed(remove_rows):
                        self.table.removeRow(row)
                else:
                    self._compact_ordinary_employees(identities)
            else:
                if self._grouped_assignment_department():
                    self._rebuild_grouped_after_work_delete(removed_work_rows)
                else:
                    self._rebuild_ordinary_after_work_delete(removed_work_rows)
        finally:
            self.table.blockSignals(was_blocked)
        self._refresh_totals()


class RC14MainWindow(RC13MainWindow):
    def _build_orders_tab(self):
        tab = super()._build_orders_tab()
        try:
            # ResponsiveGrid owns the filter width. Hard minimums here would
            # recreate the original 200% overlap on compact screens.
            self.order_filter_shift.setMinimumWidth(0)
            self.order_filter_shift.view().setMinimumWidth(0)
            self.order_filter_shift.setMaxVisibleItems(10)
        except Exception:
            pass
        return tab

    def _build_admin_tab(self):
        tab = super()._build_admin_tab()
        try:
            header = self.audit_table.horizontalHeader()
            header.setSectionResizeMode(QHeaderView.Interactive)
            # Wider defaults so none of the first four captions are clipped.
            for column, width in ((0,220),(1,180),(2,230),(3,190),(4,220)):
                self.audit_table.setColumnWidth(column, width)
            header.setStretchLastSection(True)
        except Exception:
            pass
        return tab

    def _apply_native_titlebars(self):
        dark = self.ui_settings.theme == "dark"
        for widget in QApplication.topLevelWidgets():
            try: _rc14_force_windows_titlebar(widget, dark)
            except Exception: pass

    def _theme_toggled(self, checked):
        super()._theme_toggled(checked)
        # Do not wait for Windows activation/deactivation to repaint the non-client frame.
        self._apply_native_titlebars()
        try: QApplication.processEvents()
        except Exception: pass
        QTimer.singleShot(35, self._apply_native_titlebars)
        QTimer.singleShot(120, self._apply_native_titlebars)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            # Holding Escape generates a storm of auto-repeat key events.  Repeated
            # showFullScreen/showMaximized plus opacity widgets can exhaust the GUI
            # event queue and was the cause of the observed hang/close.
            if event.isAutoRepeat():
                event.accept(); return
            now = time.monotonic()
            if now - getattr(self, "_rc14_last_escape", 0.0) < 0.30:
                event.accept(); return
            self._rc14_last_escape = now
            entering = not self.isFullScreen()
            self._animate_fullscreen_hint()
            if entering:
                self.showFullScreen(); self.fullscreen_hint_label.setText("Esc - выйти из полноэкранного режима")
            else:
                self.showMaximized(); self.fullscreen_hint_label.setText("Esc - для полноэкранного режима")
            self._apply_native_titlebars()
            QTimer.singleShot(55, lambda e=entering: self._show_fullscreen_feedback(e))
            event.accept(); return
        super().keyPressEvent(event)


# Final runtime aliases for RC14.
HeavyWorkOrderDialog = RC14WorkOrderDialog
WorkOrderDialog = RC14WorkOrderDialog
_lite_ui.WorkOrderDialog = RC14WorkOrderDialog
HeavyMainWindow = RC14MainWindow
MainWindow = RC14MainWindow
LoginDialog = RC12LoginDialog

# ===========================================================================
# RC15 — calendar theme parity, natural department numbering, polished people
#        mode selectors, stronger FIX/FACT lock color, and two-column About help.
# ===========================================================================

class _RC15CalendarNavMotion(QObject):
    """SmartOrder hover/press motion for internal calendar navigation buttons."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self._anims = {}

    def eventFilter(self, obj, event):
        if isinstance(obj, QToolButton) and event.type() in (
            QEvent.Enter, QEvent.Leave, QEvent.MouseButtonPress, QEvent.MouseButtonRelease
        ):
            self._animate(obj, event.type())
        return False

    def _animate(self, btn, kind):
        effect = getattr(btn, "_rc15_calendar_shadow", None)
        if effect is None:
            effect = QGraphicsDropShadowEffect(btn)
            effect.setColor(QColor(10, 132, 255, 90))
            effect.setBlurRadius(3)
            effect.setOffset(0, 0)
            btn.setGraphicsEffect(effect)
            btn._rc15_calendar_shadow = effect
        blur, y = 15.0, 2.0
        if kind == QEvent.Leave:
            blur, y = 3.0, 0.0
        elif kind == QEvent.MouseButtonPress:
            blur, y = 1.0, 0.0
        elif kind == QEvent.MouseButtonRelease:
            blur, y = 15.0, 2.0
        old = self._anims.pop(id(btn), None)
        if old:
            for anim in old:
                try: anim.stop()
                except Exception: pass
        a1 = QPropertyAnimation(effect, b"blurRadius", btn)
        a1.setDuration(115); a1.setEndValue(blur); a1.setEasingCurve(QEasingCurve.OutCubic)
        a2 = QPropertyAnimation(effect, b"yOffset", btn)
        a2.setDuration(115); a2.setEndValue(y); a2.setEasingCurve(QEasingCurve.OutCubic)
        self._anims[id(btn)] = (a1, a2)
        a1.start(); a2.start()


class RC15DateRangeDialog(DateRangeDialog):
    """Range calendar with SmartOrder navigation and full dark-mode rendering."""
    def __init__(self, start_date: QDate, end_date: QDate, parent=None):
        super().__init__(start_date, end_date, parent)
        try:
            self.setWindowFlag(Qt.WindowContextHelpButtonHint, False)
        except Exception:
            pass
        self._rc15_nav_motion = _RC15CalendarNavMotion(self)
        self._rc15_polish_calendar()
        try:
            _apply_modal_theme(self, parent)
        except Exception:
            pass

    def _rc15_polish_calendar(self):
        theme, _ = _theme_of(self)
        dark = theme == "dark"
        cal = self.calendar
        try:
            cal.setMinimumWidth(410)
            cal.setMinimumHeight(265)
            cal.setHorizontalHeaderFormat(QCalendarWidget.ShortDayNames)
        except Exception:
            pass

        prev_btn = cal.findChild(QToolButton, "qt_calendar_prevmonth")
        next_btn = cal.findChild(QToolButton, "qt_calendar_nextmonth")
        for tool in cal.findChildren(QToolButton):
            try:
                tool.setCursor(Qt.PointingHandCursor)
                tool.installEventFilter(self._rc15_nav_motion)
            except Exception:
                pass
        for btn, text in ((prev_btn, "‹"), (next_btn, "›")):
            if btn is None:
                continue
            try:
                btn.setIcon(QIcon())
                btn.setText(text)
                btn.setToolButtonStyle(Qt.ToolButtonTextOnly)
                btn.setCursor(Qt.PointingHandCursor)
                btn.setFixedSize(36, 32)
                btn.setFont(QFont("Segoe UI", 20, QFont.Bold))
            except Exception:
                pass

        for btn in self.findChildren(QPushButton):
            try:
                btn.setCursor(Qt.PointingHandCursor)
                if btn.text() == "Выбрать":
                    btn.setObjectName("PrimaryButton")
                elif btn.text() in {"Сегодня", "Сбросить", "Отмена"}:
                    btn.setObjectName("SecondaryButton")
            except Exception:
                pass

        if dark:
            css = r'''
QCalendarWidget#Win10Calendar { background:#1C1C1E; color:#F5F5F7; border:1px solid rgba(255,255,255,28); border-radius:12px; }
QCalendarWidget#Win10Calendar QWidget#qt_calendar_navigationbar { background:#2C2C2E; border:none; border-bottom:1px solid rgba(255,255,255,22); }
QCalendarWidget#Win10Calendar QAbstractItemView { background:#1C1C1E; color:#F5F5F7; selection-background-color:#0A84FF; selection-color:#FFFFFF; border:none; outline:0; }
QCalendarWidget#Win10Calendar QAbstractItemView::item:hover { background:rgba(10,132,255,48); color:#FFFFFF; }
QCalendarWidget#Win10Calendar QToolButton { color:#F5F5F7; background:transparent; border:1px solid transparent; border-radius:9px; padding:4px 8px; font-weight:700; }
QCalendarWidget#Win10Calendar QToolButton:hover { color:#0A84FF; background:rgba(10,132,255,28); border-color:rgba(10,132,255,100); }
QCalendarWidget#Win10Calendar QToolButton:pressed { color:#FFFFFF; background:rgba(10,132,255,75); border-color:#0A84FF; }
QCalendarWidget#Win10Calendar QToolButton#qt_calendar_prevmonth,
QCalendarWidget#Win10Calendar QToolButton#qt_calendar_nextmonth { color:#0A84FF; background:rgba(10,132,255,16); border:1px solid rgba(10,132,255,80); border-radius:9px; padding:0; }
QCalendarWidget#Win10Calendar QToolButton#qt_calendar_prevmonth:hover,
QCalendarWidget#Win10Calendar QToolButton#qt_calendar_nextmonth:hover { background:rgba(10,132,255,42); border-color:#0A84FF; color:#FFFFFF; }
QCalendarWidget#Win10Calendar QSpinBox { background:#3A3A3C; color:#F5F5F7; border:1px solid rgba(255,255,255,30); border-radius:7px; padding:3px 6px; selection-background-color:#0A84FF; }
QCalendarWidget#Win10Calendar QMenu { background:#2C2C2E; color:#F5F5F7; border:1px solid rgba(255,255,255,30); }
QCalendarWidget#Win10Calendar QMenu::item:selected { background:#0A84FF; color:#FFFFFF; }
'''
            try:
                for day in (Qt.Monday, Qt.Tuesday, Qt.Wednesday, Qt.Thursday, Qt.Friday):
                    f = QTextCharFormat(); f.setForeground(QBrush(QColor("#D1D1D6"))); cal.setWeekdayTextFormat(day, f)
                for day in (Qt.Saturday, Qt.Sunday):
                    f = QTextCharFormat(); f.setForeground(QBrush(QColor("#FF6961"))); cal.setWeekdayTextFormat(day, f)
            except Exception:
                pass
        else:
            # Keep the established light calendar palette; only replace/navigation-polish the arrows.
            css = r'''
QCalendarWidget#Win10Calendar QToolButton#qt_calendar_prevmonth,
QCalendarWidget#Win10Calendar QToolButton#qt_calendar_nextmonth { color:#007AFF; background:rgba(0,122,255,14); border:1px solid rgba(0,122,255,72); border-radius:9px; padding:0; }
QCalendarWidget#Win10Calendar QToolButton#qt_calendar_prevmonth:hover,
QCalendarWidget#Win10Calendar QToolButton#qt_calendar_nextmonth:hover { background:rgba(0,122,255,30); border-color:#007AFF; color:#005FCC; }
QCalendarWidget#Win10Calendar QToolButton#qt_calendar_prevmonth:pressed,
QCalendarWidget#Win10Calendar QToolButton#qt_calendar_nextmonth:pressed { background:rgba(0,122,255,55); }
'''
        try:
            cal.setStyleSheet(css)
        except Exception:
            pass


# DateRangeEdit resolves this module global when clicked.
DateRangeDialog = RC15DateRangeDialog


class RC15WorkOrderDialog(RC14WorkOrderDialog):
    """Use the exact Danger-button red for FIX/FACT fields locked by the opposite mode."""
    def _apply_flags(self, row):
        super()._apply_flags(row)
        if row < 0 or row >= self.table.rowCount() or self._is_total(row):
            return
        actual = self.table.item(row, 9)
        boxes = self.table.item(row, 5)
        weight = self.table.item(row, 6)
        has_actual = bool(actual and actual.text().strip())
        has_fixed = bool((boxes and boxes.text().strip()) or (weight and weight.text().strip()))
        locked = {5, 6, 7, 8} if has_actual else ({9, 10} if has_fixed else set())
        for col in locked:
            item = self.table.item(row, col)
            if item is None:
                continue
            item.setBackground(QBrush(QColor("#FF3B30")))
            item.setForeground(QBrush(QColor("#FFFFFF")))


class RC15MainWindow(RC14MainWindow):
    """RC15 presentation fixes without adding synchronous SMB work."""
    _PEOPLE_MODE_QSS = r'''
QRadioButton#PeopleModeRadio {
    min-height:28px; padding:4px 11px 4px 8px; spacing:8px;
    border:1px solid transparent; border-radius:11px; background:transparent;
}
QRadioButton#PeopleModeRadio:checked { color:#007AFF; border:1px solid #007AFF; background:rgba(0,122,255,14); }
QRadioButton#PeopleModeRadio:hover { border-color:rgba(0,122,255,90); background:rgba(0,122,255,10); }
QRadioButton#PeopleModeRadio::indicator { width:16px; height:16px; border-radius:8px; border:2px solid #8E8E93; background:#E5E5EA; }
QRadioButton#PeopleModeRadio::indicator:checked { background:#007AFF; border:4px solid #D9ECFF; }
QRadioButton#PeopleModeRadio[theme="dark"] { color:#F5F5F7; }
QRadioButton#PeopleModeRadio[theme="dark"]:checked { color:#0A84FF; border-color:#0A84FF; background:rgba(10,132,255,20); }
QRadioButton#PeopleModeRadio[theme="dark"]:hover { border-color:rgba(10,132,255,120); background:rgba(10,132,255,14); }
QRadioButton#PeopleModeRadio[theme="dark"]::indicator { background:#636366; border-color:#8E8E93; }
QRadioButton#PeopleModeRadio[theme="dark"]::indicator:checked { background:#0A84FF; border:4px solid #48484A; }
'''

    def _build_employees_tab(self):
        tab = super()._build_employees_tab()
        for btn in (self.mode_worker, self.mode_master, self.mode_department):
            try:
                btn.setObjectName("PeopleModeRadio")
                btn.setFocusPolicy(Qt.NoFocus)
                btn.setMinimumHeight(38)
                btn.setStyleSheet(self._PEOPLE_MODE_QSS)
                btn.setAttribute(Qt.WA_StyledBackground, True)
            except Exception:
                pass
        return tab

    def _build_about_tab(self):
        tab = GifBackgroundWidget(["loading2.gif", "login_background.gif", "resources/loading2.gif"])
        root = QVBoxLayout(tab); root.setContentsMargins(30, 20, 30, 24); root.setSpacing(10)
        logo = QLabel()
        if _set_logo(logo, 132, "smartorder_logo_icon_light.png", "smartorder_logo_icon.png", "smartorder_logo_white.png", "smartorder_logo.png"):
            root.addWidget(logo, alignment=Qt.AlignCenter)

        edition = self._about_selectable(QLabel(f"Enterprise Edition · Version: {APP_VERSION}"))
        edition.setAlignment(Qt.AlignCenter); edition.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Preferred)
        edition.setStyleSheet("font-size:15px;color:#F5F5F7;background-color:rgba(0,0,0,132);padding:3px 7px;border-radius:5px;")
        root.addWidget(edition, alignment=Qt.AlignCenter)

        transparent = "QFrame#AboutTransparentCard{background:rgba(0,0,0,0);border:none;}"
        policy_path = ensure_usage_policy_document()
        system = QFrame(); system.setObjectName("AboutTransparentCard"); system.setStyleSheet(transparent)
        sv = QHBoxLayout(system); sv.setContentsMargins(14, 4, 14, 4)
        system_html = '<div style="line-height:1.7;">' + '<br>'.join([
            self._rc13_chip("System", blue=True, bold=True),
            self._rc13_chip(f"Среда выполнения: Python {platform.python_version()}"),
            self._rc13_chip("Движок: PyQt5 5.15.x"),
            self._rc13_chip(f"Version: {APP_VERSION}"),
            '<a href="policy" style="color:#0A84FF;text-decoration:none;">' + self._rc13_chip("Положение об использовании ПО", blue=True, bold=True) + '</a>',
        ]) + '</div>'
        sb = self._about_browser(system_html, lambda _url, p=policy_path: QDesktopServices.openUrl(QUrl.fromLocalFile(str(p))) if p else None)
        sb.setMaximumHeight(140); sv.addWidget(sb, 1); root.addWidget(system)

        guide = QFrame(); guide.setObjectName("AboutTransparentCard"); guide.setStyleSheet(transparent)
        gv = QVBoxLayout(guide); gv.setContentsMargins(14, 4, 14, 4); gv.setSpacing(8)
        title = self._about_browser('<div style="text-align:center;">' + self._rc13_chip("Как работать в программе?", blue=True, bold=True) + '</div>')
        title.setMaximumHeight(48); gv.addWidget(title)
        columns = QHBoxLayout(); columns.setSpacing(18)
        ordinary = [
            "Заполните справочники: номенклатура, сотрудники, мастера, подразделения.",
            "Во вкладке «Наряд» нажмите «Создать наряд».",
            "Выберите дату, смену, мастера и подразделение.",
            "Добавьте работников и работы. Для обычных подразделений сотрудники и работы могут существовать независимо.",
            "Заполните ФИКС или ФАКТ. Поля противоположного режима блокируются автоматически.",
            "Проверьте рассчитанные значения и нажмите «Сохранить».",
        ]
        special = [
            "Выберите подразделение «Студенты», «Студенты ночь» или «Суточные», затем дату, смену и мастера.",
            "Добавьте всех работников, которые участвуют в наряде.",
            "Перед добавлением работ выделите строку нужного работника.",
            "Добавьте все работы выбранному работнику — они располагаются единым блоком под его ФИО.",
            "По каждой работе заполните ФИКС или ФАКТ; расчёт выполняется автоматически.",
            "Проверьте итог по каждому работнику и общий итог, затем сохраните наряд.",
        ]
        def instruction_html(header, items):
            lines = [self._rc13_chip(header, blue=True, bold=True)]
            lines += [self._rc13_chip(f"{i}. {text}") for i, text in enumerate(items, 1)]
            return '<div style="line-height:1.65;">' + '<br><br>'.join(lines) + '</div>'

        left = self._about_browser(instruction_html("Все остальные", ordinary))
        right = self._about_browser(instruction_html("Студенты / Ночь, Суточные", special))
        columns.addWidget(left, 1); columns.addWidget(right, 1); gv.addLayout(columns, 1)
        common = [
            "7. При необходимости откройте, отредактируйте или выгрузите наряд в Excel.",
            "8. При выгрузке в Excel и для отправки на печать, необходимо реализовать следующие действия: Файл → Печать. Найти масштабирование в окнах и выбрать «Вписать лист на одну страницу». После чего можно отправить на печать, нажав на кнопку «Печать».",
        ]
        common_html = '<div style="line-height:1.7;">' + '<br><br>'.join(self._rc13_chip(x, bold=True) for x in common) + '</div>'
        common_browser = self._about_browser(common_html); common_browser.setMaximumHeight(120); gv.addWidget(common_browser)
        root.addWidget(guide, 1)

        foot = QFrame(); foot.setObjectName("AboutTransparentCard"); foot.setStyleSheet(transparent)
        fv = QHBoxLayout(foot)
        footer = self._about_browser('<div style="text-align:center;">' + self._rc13_chip("Powered by OITS&amp;ZI", bold=True) + ' &nbsp; ' + self._rc13_chip("Copyright © 2026 tmbsir") + '</div>')
        footer.setMaximumHeight(48); fv.addWidget(footer); root.addWidget(foot)
        bottom = QHBoxLayout(); bottom.addStretch(); self.about_session_label = QLabel(); self.about_session_label.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Preferred)
        self.about_session_label.setStyleSheet("font-size:10px;color:#F5F5F7;background-color:rgba(0,0,0,132);padding:2px 5px;border-radius:4px;")
        bottom.addWidget(self.about_session_label); root.addLayout(bottom); self._update_session_labels()
        return tab


# Final runtime aliases for RC15.
HeavyWorkOrderDialog = RC15WorkOrderDialog
WorkOrderDialog = RC15WorkOrderDialog
_lite_ui.WorkOrderDialog = RC15WorkOrderDialog
HeavyMainWindow = RC15MainWindow
MainWindow = RC15MainWindow
LoginDialog = RC12LoginDialog

# ===========================================================================
# RC16 — login affordances, browser/PDF help, soft-delete UX, RBAC update,
#        stable tab switching and order-number preview.
# ===========================================================================

_RC16_MARKED_SUFFIX = " — Помечено на удаление ❌"


class _RC16GlyphButton(QToolButton):
    """Borderless animated glyph used inside login line edits."""
    def __init__(self, kind: str, parent=None):
        super().__init__(parent)
        self.kind = str(kind)
        self.crossed = False
        self._alpha = .46
        self._pressed = False
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.NoFocus)
        self.setFixedSize(30, 30)
        self.setStyleSheet("QToolButton{background:transparent;border:none;padding:0;margin:0;}")
        self._anim = QPropertyAnimation(self, b"alpha", self)
        self._anim.setDuration(115)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)

    @pyqtProperty(float)
    def alpha(self):
        return self._alpha

    @alpha.setter
    def alpha(self, value):
        self._alpha = max(0.0, min(1.0, float(value)))
        self.update()

    def _animate(self, value: float):
        try: self._anim.stop()
        except Exception: pass
        self._anim.setStartValue(self._alpha)
        self._anim.setEndValue(float(value))
        self._anim.start()

    def enterEvent(self, event):
        self._animate(.82); super().enterEvent(event)

    def leaveEvent(self, event):
        self._pressed = False; self._animate(.46); super().leaveEvent(event)

    def mousePressEvent(self, event):
        self._pressed = True; self._animate(.98); self.update(); super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        self._pressed = False; self._animate(.82); self.update(); super().mouseReleaseEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        a = int(255 * self._alpha)
        color = QColor(86, 86, 92, a)
        pen = QPen(color, 1.8 if not self._pressed else 2.1)
        pen.setCapStyle(Qt.RoundCap); pen.setJoinStyle(Qt.RoundJoin)
        painter.setPen(pen); painter.setBrush(Qt.NoBrush)
        inset = 8 if not self._pressed else 9
        rect = self.rect().adjusted(inset, inset, -inset, -inset)
        if self.kind == "clear":
            painter.drawLine(rect.topLeft(), rect.bottomRight())
            painter.drawLine(rect.topRight(), rect.bottomLeft())
        else:
            eye = self.rect().adjusted(6, 9, -6, -9)
            painter.drawEllipse(eye)
            pupil = QRect(self.width()//2-2, self.height()//2-2, 4, 4)
            painter.setBrush(color); painter.drawEllipse(pupil); painter.setBrush(Qt.NoBrush)
            if self.crossed:
                painter.drawLine(6, self.height()-7, self.width()-6, 7)
        painter.end()


class _RC16LoginLineEdit(QLineEdit):
    def __init__(self, kind: str, parent=None):
        super().__init__(parent)
        self.kind = str(kind)
        self.icon_button = _RC16GlyphButton(kind, self)
        self.setTextMargins(0, 0, 34, 0)
        if self.kind == "clear":
            self.icon_button.clicked.connect(self.clear)
            self.textChanged.connect(lambda text: self.icon_button.setVisible(bool(text)))
            self.icon_button.hide()
        else:
            self.setEchoMode(QLineEdit.Password)
            self.icon_button.clicked.connect(self._toggle_password)
            self.icon_button.show()

    def _toggle_password(self):
        visible = self.echoMode() == QLineEdit.Password
        self.setEchoMode(QLineEdit.Normal if visible else QLineEdit.Password)
        self.icon_button.crossed = not visible
        self.icon_button.update()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.icon_button.move(self.width() - self.icon_button.width() - 7, (self.height()-self.icon_button.height())//2)
        self.icon_button.raise_()


class _RC16SupportDialog(QDialog):
    def __init__(self, kind: str = "password", parent=None):
        super().__init__(parent)
        self.kind = str(kind)
        self.setModal(True)
        self.setMinimumWidth(520)
        self.setWindowTitle("Помощь SmartOrder" if self.kind != "password" else "Восстановление пароля")
        root = QVBoxLayout(self); root.setContentsMargins(22,18,22,18); root.setSpacing(12)
        title = QLabel("Забыли пароль?" if self.kind == "password" else "Прочее")
        title.setObjectName("TitleLabel"); root.addWidget(title)
        browser = QTextBrowser(); browser.setFrameShape(QFrame.NoFrame); browser.setOpenLinks(False); browser.setOpenExternalLinks(False)
        if self.kind == "password":
            html = (
                '<div style="line-height:1.65;">Обратитесь в IT-отдел для сброса пароля.<br><br>'
                '<b>Контактная информация:</b><br>'
                'Телефон: <a href="tel:+79955528513" style="color:#0A84FF;text-decoration:underline;">+7 995-552-85-13</a><br>'
                'Email: <a href="mailto:artem.pestretsov@tmbsir.ru" style="color:#0A84FF;text-decoration:underline;">artem.pestretsov@tmbsir.ru</a><br><br>'
                '<span style="color:#8E8E93;">Нажатие на номер передаёт адрес <b>tel:</b> в Windows. Если приложение для звонков не назначено, Windows предложит выбрать обработчик.</span></div>'
            )
        else:
            html = (
                '<div style="line-height:1.65;">Если проблема не относится к типовым случаям, зафиксируйте, что именно вы делали перед ошибкой, '
                'сделайте скриншот и во вкладке <b>Администрирование</b> нажмите <b>«Собрать логи»</b>.<br><br>'
                'Проверьте подключение к сети предприятия и повторите «Синхронизация». Не копируйте и не открывайте рабочий файл базы вручную.<br><br>'
                '<b>IT-отдел:</b><br>Телефон: <a href="tel:+79955528513" style="color:#0A84FF;text-decoration:underline;">+7 995-552-85-13</a><br>'
                'Email: <a href="mailto:artem.pestretsov@tmbsir.ru" style="color:#0A84FF;text-decoration:underline;">artem.pestretsov@tmbsir.ru</a></div>'
            )
        browser.setHtml(html)
        browser.anchorClicked.connect(self._open_link)
        root.addWidget(browser, 1)
        box = QDialogButtonBox(QDialogButtonBox.Close); box.button(QDialogButtonBox.Close).setText("Закрыть"); box.rejected.connect(self.reject); root.addWidget(box)
        _apply_modal_theme(self, parent)

    @staticmethod
    def _open_link(url: QUrl):
        try: QDesktopServices.openUrl(url)
        except Exception: pass


class RC16LoginDialog(RC12LoginDialog):
    def _build(self):
        self.bg = GifBackgroundWidget([
            "login_background.gif", "loading.gif", "loading2.gif",
            "resources/login_background.gif", "resources/loading.gif", "resources/loading2.gif",
        ], self)
        self.bg.setGeometry(self.rect())
        container = QWidget(self); self._form_container = container; container.setGeometry(self.rect()); container.setStyleSheet("background:transparent;")
        root = QVBoxLayout(container); root.setContentsMargins(24,18,24,20); root.setSpacing(8)
        logo = QLabel()
        if not _set_logo(logo,92,"smartorder_logo_icon_light.png","smartorder_logo_icon.png","smartorder_logo_white.png","smartorder_logo.png"):
            logo.setText("S"); logo.setAlignment(Qt.AlignCenter); logo.setStyleSheet("color:white;font-size:48px;font-weight:900;background:transparent;")
        root.addWidget(logo, alignment=Qt.AlignCenter)
        title=QLabel("SmartOrder");title.setAlignment(Qt.AlignCenter);title.setStyleSheet("color:#FFF;background:transparent;font-size:18px;font-weight:900;");root.addWidget(title)
        subtitle=QLabel("Формирование нарядов\nна сдельную работу");subtitle.setAlignment(Qt.AlignCenter);subtitle.setWordWrap(True);subtitle.setFixedHeight(44);subtitle.setMinimumWidth(320);subtitle.setStyleSheet("color:#FFF;background:transparent;font-size:13px;font-weight:800;");root.addWidget(subtitle,alignment=Qt.AlignCenter)
        form=QFormLayout();form.setLabelAlignment(Qt.AlignRight|Qt.AlignVCenter);form.setFormAlignment(Qt.AlignHCenter);form.setHorizontalSpacing(10);form.setVerticalSpacing(10)
        self.username_edit=_RC16LoginLineEdit("clear");self.username_edit.setPlaceholderText("Введите логин");self.username_edit.setMinimumWidth(235);self.username_edit.setMinimumHeight(44);self.username_edit.returnPressed.connect(lambda:self.password_edit.setFocus())
        self.password_edit=_RC16LoginLineEdit("eye");self.password_edit.setPlaceholderText("Введите пароль");self.password_edit.setMinimumWidth(235);self.password_edit.setMinimumHeight(44);self.password_edit.returnPressed.connect(self._login)
        input_style="QLineEdit{background:rgba(255,255,255,220);color:#1D1D1F;border:2px solid #007AFF;border-radius:12px;padding:8px 42px 8px 12px;font-size:13px;}QLineEdit:focus{background:#FFF;}"
        self.username_edit.setStyleSheet(input_style);self.password_edit.setStyleSheet(input_style)
        login_label=QLabel("Логин:");pass_label=QLabel("Пароль:")
        for lab in (login_label,pass_label):lab.setStyleSheet("color:#FFF;background:transparent;font-size:13px;font-weight:900;")
        form.addRow(login_label,self.username_edit);form.addRow(pass_label,self.password_edit);root.addLayout(form)
        forgot=QPushButton("Забыли пароль?");forgot.setObjectName("GhostButton");forgot.setFlat(True);forgot.setStyleSheet("QPushButton{color:#0A84FF;background:transparent;border:none;font-weight:800;}QPushButton:hover{color:#66B5FF;}");forgot.clicked.connect(lambda:_RC16SupportDialog("password",self).exec_());root.addWidget(forgot,alignment=Qt.AlignCenter)
        row=QHBoxLayout();row.setSpacing(8);ok=QPushButton("Войти");cancel=QPushButton("Отмена");ok.setMinimumHeight(46);cancel.setMinimumHeight(46);ok.setObjectName("PrimaryButton");cancel.setObjectName("SecondaryButton")
        ok.setStyleSheet("QPushButton{background:#007AFF;color:#FFF;border:1px solid #007AFF;border-radius:11px;font-weight:900;min-width:125px;}QPushButton:hover{background:#0A84FF;}")
        cancel.setStyleSheet("QPushButton{background:rgba(0,122,255,25);color:#0A84FF;border:1px solid #0A84FF;border-radius:11px;font-weight:900;min-width:125px;}QPushButton:hover{background:rgba(0,122,255,55);}")
        ok.clicked.connect(self._login);cancel.clicked.connect(self.reject);row.addWidget(ok,1);row.addWidget(cancel,1);root.addLayout(row);root.addStretch(1)


class RC16UserDialog(HeavyUserDialog):
    def __init__(self, username="", role="", require_password=True, parent=None):
        super().__init__(username, role, require_password, parent)
        self.password.setPlaceholderText("Введите пароль не менее 8-ми символов" if require_password else "Оставьте пустым, чтобы не менять")


class RC16EmployeeSelectionDialog(_HeavyCheckListDialog):
    def __init__(self, db, parent=None):
        rows=[(int(r[0]),str(r[1])) for r in db.get_active_employees(False)]
        super().__init__("Выбор работников", rows, lambda r:r[1], parent)


class RC16WorkSelectionDialog(_HeavyCheckListDialog):
    def __init__(self, db, parent=None):
        rows=[(int(r[0]),str(r[1]),str(r[2]),float(r[3])) for r in db.get_active_work_types()]
        super().__init__("Выбор работ", rows, lambda r:f"{r[1]}   |   {r[2]}   |   {fmt(r[3])} руб.", parent)


class RC16WorkOrderDialog(RC15WorkOrderDialog):
    def _build(self):
        super()._build()
        # New orders may only select active masters. Existing edited orders keep
        # their historical master visible even after that master is soft-deleted.
        try:
            current_id = self.order["info"].get("master_id") if self.order else None
            current_name = str(self.order["info"].get("master") or "") if self.order else ""
            self.master.blockSignals(True); self.master.clear()
            for row in self.db.get_active_employees(True):
                self.master.addItem(str(row[1]), int(row[0]))
            if current_id is not None and self.master.findData(current_id) < 0:
                self.master.addItem((current_name or f"Мастер #{current_id}") + _RC16_MARKED_SUFFIX, int(current_id))
            self.master.blockSignals(False)
        except Exception:
            pass
        try:
            number = str(self.order["info"].get("version", "")) if self.order else self.db.next_order_number_preview()
            chip = QLabel(f"№ {number}")
            chip.setObjectName("OrderNumberChipRC16")
            chip.setStyleSheet("color:#FFFFFF;background:#007AFF;border-radius:8px;padding:4px 10px;font-weight:900;")
            group = self.findChild(QGroupBox, "OrderInfoGroup")
            if group is not None and isinstance(group.layout(), QFormLayout):
                group.layout().insertRow(0, "Номер наряда:", chip)
            self.order_number_label = chip
        except Exception:
            pass


class _RC16DownloadBanner(QFrame):
    def __init__(self, parent):
        super().__init__(parent)
        self.setObjectName("EditModeBanner")
        self.setFixedHeight(48); self.setFixedWidth(560)
        lay=QHBoxLayout(self);lay.setContentsMargins(14,6,14,6)
        self.label=QLabel("Скачивание… 90%");self.label.setObjectName("EditModeLabel");self.label.setAlignment(Qt.AlignCenter);lay.addWidget(self.label,1)
        self.hide()

    def place(self):
        p=self.parentWidget()
        if p is not None:self.move(max(16,(p.width()-self.width())//2),26)

    def start(self, finished_callback=None):
        self.place();self.raise_();self.show();self._value=90;self._callback=finished_callback
        self.label.setText("Скачивание… 90%")
        timer=QTimer(self);timer.setInterval(28);self._timer=timer
        def tick():
            self._value += 1
            if self._value >= 100:
                timer.stop();self.label.setText("Успешно скачано")
                if callable(self._callback):
                    try:self._callback()
                    except Exception:pass
                QTimer.singleShot(900,self.hide)
            else:self.label.setText(f"Скачивание… {self._value}%")
        timer.timeout.connect(tick);timer.start()


def _rc16_write_guide_pdf() -> Path:
    base=Path(os.environ.get("USERPROFILE") or str(Path.home()))/"Downloads"/"SmartOrder"
    base.mkdir(parents=True,exist_ok=True)
    target=base/"SmartOrder_Как_работать_в_программе.pdf"
    document=QTextDocument();document.setHtml(USER_GUIDE_HTML)
    printer=QPrinter(QPrinter.HighResolution);printer.setOutputFormat(QPrinter.PdfFormat);printer.setOutputFileName(str(target))
    document.print_(printer)
    return target


class RC16MainWindow(RC15MainWindow):
    def _build(self):
        super()._build()
        # All tabs remain visible; RBAC only controls whether the user can open them.
        allowed={0,4}
        if self.can(Permission.CATALOG_VIEW): allowed.add(1)
        if self.can(Permission.EMPLOYEES_VIEW): allowed.add(2)
        if self.can(Permission.ADMIN_VIEW): allowed.add(3)
        for i in range(self.tabs.count()): self.tabs.setTabEnabled(i, i in allowed)
        # Transparent pre-load pages eliminate the white native page flash before a lazy tab is built.
        for i in range(1,self.tabs.count()):
            w=self.tabs.widget(i)
            if w is not None:
                w.setObjectName("LiquidTabHost")
                w.setAttribute(Qt.WA_StyledBackground,True);w.setAutoFillBackground(False)
                w.setStyleSheet("QWidget#LiquidTabHost{background:transparent;border:none;}")

    def _replace_tab(self,index,widget,title):
        """Mount lazy content inside the existing tab host.

        Removing/inserting a QTabWidget page creates a transient native
        placeholder on some Windows/Qt builds, which appears as a small white
        window while switching tabs. Reuse the original host widget instead.
        """
        host=self.tabs.widget(index)
        if host is None:
            return super()._replace_tab(index,widget,title)
        host.setUpdatesEnabled(False)
        try:
            layout=host.layout()
            if layout is None:
                layout=QVBoxLayout(host);layout.setContentsMargins(0,0,0,0);layout.setSpacing(0)
            while layout.count():
                item=layout.takeAt(0);old=item.widget() if item is not None else None
                if old is not None:
                    old.hide();old.deleteLater()
            widget.setParent(host);widget.setAttribute(Qt.WA_StyledBackground,True)
            layout.addWidget(widget);widget.show()
            self.tabs.setTabText(index,title)
        finally:
            host.setUpdatesEnabled(True);host.update()
        return host

    def _tab_changed(self,index):
        if self._building_tab:return
        if index not in self._loaded_tabs:
            self._building_tab=True
            self.tabs.setUpdatesEnabled(False)
            try:
                if index==1: widget=self._build_catalog_tab(); title="Номенклатура"
                elif index==2: widget=self._build_employees_tab(); title="Сотрудники"
                elif index==3: widget=self._build_admin_tab(); title="Администрирование"
                elif index==4: widget=self._build_about_tab(); title="О приложении ⍰"
                else: return
                widget.setAttribute(Qt.WA_StyledBackground,True);widget.setProperty("theme",self.ui_settings.theme)
                # Do not re-polish the whole QApplication/MainWindow here: that used to
                # instantiate/polish native popup containers and caused white flashes.
                self._replace_tab(index,widget,title);self._loaded_tabs.add(index)
                if index==1:self.refresh_work_types()
                elif index==2:self.refresh_people()
                elif index==3:self.refresh_users();self.refresh_audit();self.refresh_backups()
            finally:
                self.tabs.setUpdatesEnabled(True);self.tabs.update();self._building_tab=False
        else:
            try:
                w=self.tabs.currentWidget()
                if w is not None:w.update()
            except Exception:pass

    def _build_admin_tab(self):
        # Reuse the mature admin layout. For Master/Accountant build the same page
        # as Administrator, then disable only protected account/restore controls.
        if self.user.has_role("Администратор"):
            return super()._build_admin_tab()
        real=self.user
        fake=SessionUser(real.id,real.username,"Администратор",frozenset(ALL_PERMISSIONS))
        self.user=fake
        try:tab=super()._build_admin_tab()
        finally:self.user=real
        try:
            self.access_control_check.setEnabled(False)
        except Exception:pass
        for button in tab.findChildren(QPushButton):
            text=button.text().strip()
            if "Добавить пользователя" in text or "Восстановить" in text:
                button.setEnabled(False)
        return tab

    def refresh_users(self):
        if not hasattr(self,"users_table"):return
        rows=self.db.list_users();self.users_table.setRowCount(len(rows));self.users_table.setColumnWidth(3,430)
        admin=self.user.has_role("Администратор")
        for i,r in enumerate(rows):
            uid,username,role,active=int(r[0]),str(r[1]),str(r[2]),bool(r[3])
            self.users_table.setItem(i,0,make_item(username,uid));self.users_table.setItem(i,1,make_item(role));self.users_table.setItem(i,2,make_item("Активен" if active else "Отключён"))
            host=QWidget();h=QHBoxLayout(host);h.setContentsMargins(4,4,4,4);h.setSpacing(8)
            e=QPushButton("Изменить");e.setObjectName("UserEditButton");d=QPushButton("Удалить");d.setObjectName("UserDeleteButton");t=QPushButton("Отключить" if active else "Включить");t.setObjectName("UserToggleButton")
            for btn in (e,d,t):btn.setEnabled(admin)
            if admin:
                e.clicked.connect(lambda _,u=uid,n=username,rn=role:self._edit_user_by_id(u,n,rn));d.clicked.connect(lambda _,u=uid,n=username:self._delete_user_by_id(u,n));t.clicked.connect(lambda _,u=uid,a=active:self._toggle_user_by_id(u,a))
            h.addWidget(e);h.addWidget(d);h.addWidget(t);h.addStretch(1);self.users_table.setCellWidget(i,3,host);self.users_table.setRowHeight(i,62)

    def refresh_audit(self):
        if not hasattr(self,"audit_table"):return
        rows=self.db.recent_audit(200);self.audit_table.setRowCount(len(rows))
        for i,r in enumerate(rows):
            for c,v in enumerate(r):self.audit_table.setItem(i,c,make_item(v))
            self.audit_table.setRowHeight(i,42)

    def restore_backup(self):
        if not self.can(Permission.BACKUP_RESTORE):
            warn(self,"Восстановление","Восстановление общей базы доступно только администратору.");return
        return super().restore_backup()

    def refresh_work_types(self):
        if not hasattr(self,"work_table"):return
        marked=self.db._soft_deleted_entries("work_type")
        needle=self.work_search.text().strip().casefold().replace("ё","е");all_rows=self.db.get_work_types()
        rows=[r for r in all_rows if not needle or needle in (str(r[1])+" "+str(r[2])+(_RC16_MARKED_SUFFIX if int(r[0]) in marked else "")).casefold().replace("ё","е")]
        self.work_table.setRowCount(len(rows))
        for i,r in enumerate(rows):
            ident=int(r[0]);is_marked=ident in marked;name=str(r[1]);display=name+(_RC16_MARKED_SUFFIX if is_marked else "")
            vals=[display,r[2],fmt(r[3]),r[4]]
            for c,v in enumerate(vals):self.work_table.setItem(i,c,make_item(v))
            item=self.work_table.item(i,0);item.setData(Qt.UserRole,ident);item.setData(Qt.UserRole+1,is_marked);item.setData(Qt.UserRole+2,name)
            if is_marked:item.setForeground(QBrush(QColor("#FF3B30")))
        self.work_results_label.setText(f"Найдено: {len(rows)} из {len(all_rows)}")

    def _heavy_work_selection(self):
        row=self.work_table.currentRow();enabled=row>=0;marked=False
        if enabled:
            item=self.work_table.item(row,0);marked=bool(item.data(Qt.UserRole+1));raw=str(item.data(Qt.UserRole+2) or item.text())
            self.work_name.setText(raw);self.work_code.setText(self.work_table.item(row,1).text());self.work_price.setText(self.work_table.item(row,2).text())
        self.work_edit_btn.setEnabled(enabled and not marked);self.work_delete_btn.setEnabled(enabled and not marked);self.work_save_btn.setEnabled(False)

    def delete_work_type(self):
        row=self.work_table.currentRow()
        if row<0:return
        item=self.work_table.item(row,0);raw=str(item.data(Qt.UserRole+2) or item.text());ident=int(item.data(Qt.UserRole))
        if question(self,"Удаление",f"Удалить работу «{raw}»?")!=QMessageBox.Yes:return
        try:
            result=self.db.delete_work_type(self.user,ident);self.refresh_work_types();self._clear_work_form()
            if result=="marked":info(self,"Номенклатура",f"Работа «{raw}» используется в сохранённых нарядах.\n\nОна оставлена в справочнике как «Помечено на удаление ❌» и больше не будет доступна при создании новых нарядов.")
        except Exception as exc:error(self,"Удаление",exc)

    def refresh_people(self):
        if not hasattr(self,"people_table"):return
        self._employee_mode_visual();mode=self._people_mode();marked=set()
        if mode=="department":all_rows=self.db.get_departments()
        else:
            all_rows=self.db.get_employees(mode=="master");marked=self.db._soft_deleted_entries("employee")
        needle=self.person_search.text().strip().casefold().replace("ё","е")
        rows=[]
        for r in all_rows:
            display=str(r[1])+(_RC16_MARKED_SUFFIX if int(r[0]) in marked else "")
            if not needle or needle in display.casefold().replace("ё","е"):rows.append((r,display))
        self.people_table.setRowCount(len(rows))
        for i,(r,display) in enumerate(rows):
            is_marked=int(r[0]) in marked;reg=r[2] if mode=="department" else r[3];editd=(r[3] if mode=="department" else r[4]) or "";vals=[display,reg,editd]
            for c,v in enumerate(vals):self.people_table.setItem(i,c,make_item(v))
            item=self.people_table.item(i,0);item.setData(Qt.UserRole,int(r[0]));item.setData(Qt.UserRole+1,is_marked);item.setData(Qt.UserRole+2,str(r[1]))
            if is_marked:item.setForeground(QBrush(QColor("#FF3B30")))
        self.people_results_label.setText(f"Найдено: {len(rows)}")

    def _heavy_people_selection(self):
        row=self.people_table.currentRow();enabled=row>=0;marked=False
        if enabled:
            item=self.people_table.item(row,0);marked=bool(item.data(Qt.UserRole+1));self.person_name.setText(str(item.data(Qt.UserRole+2) or item.text()))
        self.person_edit_btn.setEnabled(enabled and not marked);self.person_delete_btn.setEnabled(enabled and not marked);self.person_save_btn.setEnabled(False)

    def delete_person(self):
        row=self.people_table.currentRow()
        if row<0:return
        item=self.people_table.item(row,0);raw=str(item.data(Qt.UserRole+2) or item.text());ident=int(item.data(Qt.UserRole));mode=self._people_mode()
        if question(self,"Удаление",f"Удалить «{raw}»?")!=QMessageBox.Yes:return
        try:
            if mode=="department":result=self.db.delete_department(self.user,ident)
            else:result=self.db.delete_employee(self.user,ident)
            self.refresh_people();self._refresh_reference_filters()
            if result=="marked":info(self,"Удаление",f"«{raw}» используется в сохранённых нарядах.\n\nЗапись оставлена в справочнике как «Помечено на удаление ❌» и больше не будет доступна при создании новых нарядов.")
        except Exception as exc:error(self,"Удаление",exc)

    def _build_about_tab(self):
        tab=GifBackgroundWidget(["loading2.gif","login_background.gif","resources/loading2.gif"])
        root=QVBoxLayout(tab);root.setContentsMargins(30,20,30,24);root.setSpacing(10)
        logo=QLabel()
        if _set_logo(logo,132,"smartorder_logo_icon_light.png","smartorder_logo_icon.png","smartorder_logo_white.png","smartorder_logo.png"):root.addWidget(logo,alignment=Qt.AlignCenter)
        edition=self._about_selectable(QLabel(f"Enterprise Edition · Версия {APP_VERSION}"));edition.setAlignment(Qt.AlignCenter);edition.setSizePolicy(QSizePolicy.Maximum,QSizePolicy.Preferred);edition.setStyleSheet("font-size:15px;color:#F5F5F7;background-color:rgba(0,0,0,132);padding:3px 7px;border-radius:5px;");root.addWidget(edition,alignment=Qt.AlignCenter)
        transparent="QFrame#AboutTransparentCard{background:rgba(0,0,0,0);border:none;}"
        docs=QHBoxLayout();docs.setSpacing(18)
        policy_path=ensure_usage_policy_document();guide_path=ensure_user_guide_document();trouble_path=ensure_troubleshooting_document()
        system=QFrame();system.setObjectName("AboutTransparentCard");system.setStyleSheet(transparent);sv=QVBoxLayout(system);sv.setContentsMargins(14,4,14,4)
        sys_html='<div style="line-height:1.75;">'+ '<br>'.join([
            self._rc13_chip("System",blue=True,bold=True),self._rc13_chip(f"Среда выполнения: Python {platform.python_version()}"),self._rc13_chip("Движок: PyQt5 5.15.x"),self._rc13_chip("Версия: 1.0"),
            '<a href="policy" style="color:#0A84FF;text-decoration:underline;">'+self._rc13_chip("Положение об использовании ПО",blue=True,bold=True)+'</a>'])+'</div>'
        def system_link(url):
            if url.toString()=="policy" and policy_path:QDesktopServices.openUrl(QUrl.fromLocalFile(str(policy_path)))
        sv.addWidget(self._about_browser(sys_html,system_link),1);docs.addWidget(system,1)
        documentation=QFrame();documentation.setObjectName("AboutTransparentCard");documentation.setStyleSheet(transparent);dv=QVBoxLayout(documentation);dv.setContentsMargins(14,4,14,4)
        guide_html='<div style="line-height:1.9;">'+self._rc13_chip("Документация",blue=True,bold=True)+'<br><br><a href="guide" style="color:#0A84FF;text-decoration:underline;">'+self._rc13_chip("Как работать в программе?",blue=True,bold=True)+'</a> &nbsp; <a href="pdf" style="color:#0A84FF;text-decoration:underline;">'+self._rc13_chip("[.pdf]",blue=True,bold=True)+'</a></div>'
        def guide_link(url):
            key=url.toString()
            if key=="guide" and guide_path:QDesktopServices.openUrl(QUrl.fromLocalFile(str(guide_path)))
            elif key=="pdf":self._rc16_download_guide_pdf(tab)
        dv.addWidget(self._about_browser(guide_html,guide_link),1);docs.addWidget(documentation,1);root.addLayout(docs)
        help_frame=QFrame();help_frame.setObjectName("AboutTransparentCard");help_frame.setStyleSheet(transparent);hv=QVBoxLayout(help_frame);hv.setContentsMargins(14,3,14,3)
        help_html='<div style="line-height:2.0;">'+self._rc13_chip("Помощь",blue=True,bold=True)+'<br>'+'<a href="forgot" style="color:#0A84FF;text-decoration:underline;">'+self._rc13_chip("Забыли пароль?")+'</a><br>'+'<a href="problems" style="color:#0A84FF;text-decoration:underline;">'+self._rc13_chip("Возможные проблемы при работе с программой")+'</a><br>'+'<a href="other" style="color:#0A84FF;text-decoration:underline;">'+self._rc13_chip("Прочее")+'</a></div>'
        def help_link(url):
            key=url.toString()
            if key=="forgot":_RC16SupportDialog("password",self).exec_()
            elif key=="problems" and trouble_path:QDesktopServices.openUrl(QUrl.fromLocalFile(str(trouble_path)))
            elif key=="other":_RC16SupportDialog("other",self).exec_()
        hb=self._about_browser(help_html,help_link);hb.setMaximumHeight(170);hv.addWidget(hb);root.addWidget(help_frame)
        foot=QFrame();foot.setObjectName("AboutTransparentCard");foot.setStyleSheet(transparent);fv=QHBoxLayout(foot);fb=self._about_browser('<div style="text-align:center;">'+self._rc13_chip("Powered by OITS&amp;ZI",bold=True)+' &nbsp; '+self._rc13_chip("Copyright © 2026 tmbsir")+'</div>');fb.setMaximumHeight(48);fv.addWidget(fb);root.addWidget(foot)
        bottom=QHBoxLayout();bottom.addStretch();self.about_session_label=QLabel();self.about_session_label.setStyleSheet("font-size:10px;color:#F5F5F7;background-color:rgba(0,0,0,132);padding:2px 5px;border-radius:4px;");bottom.addWidget(self.about_session_label);root.addLayout(bottom);self._update_session_labels()
        tab._rc16_download_banner=_RC16DownloadBanner(tab)
        return tab

    def _rc16_download_guide_pdf(self, tab):
        banner=getattr(tab,"_rc16_download_banner",None)
        if banner is not None:
            banner.place();banner.label.setText("Скачивание… 90%");banner.raise_();banner.show();QApplication.processEvents()
        try:target=_rc16_write_guide_pdf()
        except Exception as exc:
            if banner is not None:banner.hide()
            error(self,"PDF",exc);return
        def done():
            try:QDesktopServices.openUrl(QUrl.fromLocalFile(str(target.parent)))
            except Exception:pass
        if banner is not None:banner.start(done)
        else:done()


# RC16 final runtime aliases.
EmployeeSelectionDialog = RC16EmployeeSelectionDialog
WorkSelectionDialog = RC16WorkSelectionDialog
HeavyUserDialog = RC16UserDialog
HeavyWorkOrderDialog = RC16WorkOrderDialog
WorkOrderDialog = RC16WorkOrderDialog
_lite_ui.WorkOrderDialog = RC16WorkOrderDialog
HeavyMainWindow = RC16MainWindow
MainWindow = RC16MainWindow
LoginDialog = RC16LoginDialog

# ===================== RC17: recent-deleted recycle view + retention =====================
class RC17WorkOrderDialog(RC16WorkOrderDialog):
    def _build(self):
        super()._build()
        # New orders only see active departments. Historical edited orders keep
        # their original department visible even after it was marked for deletion.
        try:
            current_id = self.order["info"].get("department_id") if self.order else None
            current_name = str(self.order["info"].get("department") or "") if self.order else ""
            self.department.blockSignals(True)
            self.department.clear()
            for row in self.db.get_active_departments():
                self.department.addItem(str(row[1]), int(row[0]))
            if current_id is not None and self.department.findData(current_id) < 0:
                self.department.addItem((current_name or f"Подразделение #{current_id}") + _RC16_MARKED_SUFFIX, int(current_id))
            if current_id is not None:
                idx = self.department.findData(current_id)
                if idx >= 0:
                    self.department.setCurrentIndex(idx)
            self.department.blockSignals(False)
        except Exception:
            pass


class RC17MainWindow(RC16MainWindow):
    """RC17 recycle-bin presentation without adding synchronous SMB polling."""

    def _build_employees_tab(self):
        tab = super()._build_employees_tab()
        self._show_recent_deleted_people = False
        self.recent_deleted_btn = QPushButton("Недавно удалённые")
        self.recent_deleted_btn.setObjectName("SecondaryButton")
        self.recent_deleted_btn.setCheckable(True)
        self.recent_deleted_btn.setMinimumWidth(190)
        self.recent_deleted_btn.setToolTip("Показывает сотрудников, мастеров или подразделения, удалённые за последние 30 дней")
        self.recent_deleted_btn.toggled.connect(self._toggle_recent_deleted_people)
        try:
            top = tab.layout().itemAt(0)
            if top is not None and top.layout() is not None:
                # The modes row already has a stretch, so this lands in the
                # requested upper-right free area.
                top.layout().addWidget(self.recent_deleted_btn)
        except Exception:
            pass
        self.refresh_people()
        return tab

    def _toggle_recent_deleted_people(self, checked):
        self._show_recent_deleted_people = bool(checked)
        self.recent_deleted_btn.setText("← Текущие" if checked else "Недавно удалённые")
        try:
            self.person_name.clear()
            self.person_search.clear()
            self.people_table.clearSelection()
            self.people_table.setCurrentCell(-1, -1)
        except Exception:
            pass
        self.refresh_people()

    def refresh_people(self):
        if not hasattr(self, "people_table"):
            return
        self._employee_mode_visual()
        mode = self._people_mode()
        recent = bool(getattr(self, "_show_recent_deleted_people", False))
        needle = self.person_search.text().strip().casefold().replace("ё", "е")

        if recent:
            if mode == "department":
                source = self.db.list_recent_deleted_departments(30)
                rows = []
                for r in source:
                    # id,name,registration_date,edit_date,marked_at,marked_by
                    display = str(r[1]) + _RC16_MARKED_SUFFIX
                    if not needle or needle in display.casefold().replace("ё", "е"):
                        rows.append((r, display, r[2], r[4]))
            else:
                source = self.db.list_recent_deleted_employees(mode == "master", 30)
                rows = []
                for r in source:
                    # id,name,is_master,registration_date,edit_date,marked_at,marked_by
                    display = str(r[1]) + _RC16_MARKED_SUFFIX
                    if not needle or needle in display.casefold().replace("ё", "е"):
                        rows.append((r, display, r[3], r[5]))
            self.people_table.setHorizontalHeaderLabels(["ФИО / Название", "Дата регистрации", "Удалено"])
        else:
            if mode == "department":
                source = self.db.get_active_departments()
                rows = [(r, str(r[1]), r[2], r[3] or "") for r in source if not needle or needle in str(r[1]).casefold().replace("ё", "е")]
            else:
                source = self.db.get_active_employees(mode == "master")
                rows = [(r, str(r[1]), r[3], r[4] or "") for r in source if not needle or needle in str(r[1]).casefold().replace("ё", "е")]
            self.people_table.setHorizontalHeaderLabels(["ФИО / Название", "Дата регистрации", "Дата редактирования"])

        self.people_table.setRowCount(len(rows))
        for i, (r, display, reg, last_date) in enumerate(rows):
            vals = [display, reg, last_date]
            for c, value in enumerate(vals):
                self.people_table.setItem(i, c, make_item(value))
            item = self.people_table.item(i, 0)
            item.setData(Qt.UserRole, int(r[0]))
            item.setData(Qt.UserRole + 1, recent)
            item.setData(Qt.UserRole + 2, str(r[1]))
            if recent:
                item.setForeground(QBrush(QColor("#FF3B30")))
        self.people_results_label.setText(("Недавно удалено: " if recent else "Найдено: ") + str(len(rows)))
        try:
            self.person_edit_btn.setEnabled(False)
            self.person_delete_btn.setEnabled(False)
            self.person_save_btn.setEnabled(False)
        except Exception:
            pass

    def _heavy_people_selection(self):
        if bool(getattr(self, "_show_recent_deleted_people", False)):
            row = self.people_table.currentRow()
            if row >= 0:
                item = self.people_table.item(row, 0)
                self.person_name.setText(str(item.data(Qt.UserRole + 2) or ""))
            self.person_edit_btn.setEnabled(False)
            self.person_delete_btn.setEnabled(False)
            self.person_save_btn.setEnabled(False)
            return
        return super()._heavy_people_selection()


# RC17 final runtime aliases.
HeavyWorkOrderDialog = RC17WorkOrderDialog
WorkOrderDialog = RC17WorkOrderDialog
_lite_ui.WorkOrderDialog = RC17WorkOrderDialog
HeavyMainWindow = RC17MainWindow
MainWindow = RC17MainWindow


# ===========================================================================
# RC18 — compact Admin/audit, recycle restore, responsive zoom and About layout
# ===========================================================================
from PyQt5.QtGui import QKeySequence
from PyQt5.QtWidgets import QScrollArea, QShortcut


class _RC18SupportDialog(QDialog):
    """Unified support window used by Login and About."""
    def __init__(self, kind: str = "password", parent=None):
        super().__init__(parent)
        self.kind = str(kind)
        self.setModal(True)
        self.setMinimumWidth(550)
        self.setWindowTitle("Восстановление пароля" if self.kind == "password" else "Помощь SmartOrder")
        root = QVBoxLayout(self); root.setContentsMargins(22,18,22,18); root.setSpacing(12)
        title = QLabel("Забыли пароль?" if self.kind == "password" else "Прочее")
        title.setObjectName("TitleLabel"); root.addWidget(title)
        browser = QTextBrowser()
        browser.setFrameShape(QFrame.NoFrame)
        browser.setOpenLinks(False); browser.setOpenExternalLinks(False)
        contacts = (
            'Телефон: <a href="tel:+79955528513" style="color:#0A84FF;text-decoration:underline;">+7 995-552-85-13</a><br>'
            'Bitrix24: <a href="https://sir01.bitrix24.ru/company/personal/user/1292/" '
            'style="color:#0A84FF;text-decoration:underline;">Написать</a><br>'
            'Email: <a href="mailto:artem.pestretsov@tmbsir.ru" '
            'style="color:#0A84FF;text-decoration:underline;">artem.pestretsov@tmbsir.ru</a>'
        )
        if self.kind == "password":
            html = (
                '<div style="line-height:1.7;">Обратитесь в IT-отдел для сброса пароля.<br><br>'
                '<b>Контактная информация:</b><br>' + contacts +
                '<br><br><span style="color:#8E8E93;">Нажатие на номер передаёт адрес <b>tel:</b> '
                'в Windows. Если обработчик звонков не назначен, Windows предложит выбрать приложение.</span></div>'
            )
        else:
            html = (
                '<div style="line-height:1.7;">Если проблема не относится к типовым случаям, '
                'зафиксируйте действия перед ошибкой, сделайте скриншот и во вкладке '
                '<b>Администрирование</b> нажмите <b>«Собрать логи»</b>.<br><br>'
                'Проверьте подключение к сети предприятия и выполните «Синхронизация». '
                'Не открывайте рабочий файл базы вручную.<br><br>'
                '<b>IT-отдел:</b><br>' + contacts + '</div>'
            )
        browser.setHtml(html)
        browser.anchorClicked.connect(lambda url: QDesktopServices.openUrl(url))
        root.addWidget(browser,1)
        box=QDialogButtonBox(QDialogButtonBox.Close)
        box.button(QDialogButtonBox.Close).setText("Закрыть")
        box.rejected.connect(self.reject); root.addWidget(box)
        _apply_modal_theme(self,parent)


# Login RC16 lambdas resolve this module-global at click time.
_RC16SupportDialog = _RC18SupportDialog


class RC18WorkOrderDialog(RC17WorkOrderDialog):
    """Compact order number + correct dark native caption from the first paint."""
    def _build(self):
        super()._build()
        try:
            chip = getattr(self, "order_number_label", None)
            if chip is not None:
                number = chip.text().replace("№", "").strip()
                chip.setText(f"<b>{number}</b>")
                chip.setTextFormat(Qt.RichText)
                chip.setStyleSheet("background:transparent;border:none;padding:0;color:inherit;font-weight:900;")
                chip.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Preferred)
            group = self.findChild(QGroupBox, "OrderInfoGroup")
            if group is not None and isinstance(group.layout(), QFormLayout):
                group.layout().setVerticalSpacing(5)
                group.layout().setContentsMargins(14,18,14,10)
        except Exception:
            pass
        try:
            theme, zoom = _theme_of(self.parent())
            self.setProperty("theme", theme)
            set_theme_recursive(self, theme)
            apply_apple_design(self, theme, zoom)
        except Exception:
            pass

    def showEvent(self, event):
        try:
            theme, _ = _theme_of(self.parent())
            # Set the Windows non-client theme before the first visible frame.
            _rc14_force_windows_titlebar(self, theme == "dark")
        except Exception:
            pass
        super().showEvent(event)
        try:
            theme, _ = _theme_of(self.parent())
            _rc14_force_windows_titlebar(self, theme == "dark")
            QTimer.singleShot(0, lambda: _rc14_force_windows_titlebar(self, theme == "dark"))
        except Exception:
            pass


class _DiagnosticsGraph(QWidget):
    """Small dependency-free live graph used by the in-app diagnostics center."""
    def __init__(self, title: str, suffix: str = "", parent=None):
        super().__init__(parent)
        self.title = title
        self.suffix = suffix
        self.values = deque(maxlen=60)
        self.setMinimumHeight(215)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def add_value(self, value):
        try:
            self.values.append(max(0.0, float(value)))
        except Exception:
            return
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        dark = str(self.property("theme") or "dark") == "dark"
        bg = QColor("#232325" if dark else "#FFFFFF")
        border = QColor(255,255,255,35) if dark else QColor(0,0,0,25)
        text = QColor("#F5F5F7" if dark else "#1D1D1F")
        muted = QColor("#A8A8AD" if dark else "#6E6E73")
        grid = QColor(255,255,255,22) if dark else QColor(0,0,0,18)
        blue = QColor("#0A84FF" if dark else "#007AFF")
        r = self.rect().adjusted(1,1,-1,-1)
        painter.setPen(QPen(border,1))
        painter.setBrush(QBrush(bg))
        painter.drawRoundedRect(r, 14, 14)
        painter.setPen(text)
        font = painter.font(); font.setBold(True); font.setPointSize(max(9,font.pointSize()))
        painter.setFont(font)
        painter.drawText(16, 26, self.title)
        vals = list(self.values)
        current = vals[-1] if vals else 0.0
        painter.setPen(muted)
        font.setBold(False); font.setPointSize(max(8,font.pointSize()-1)); painter.setFont(font)
        painter.drawText(16, 47, f"Сейчас: {current:.1f}{self.suffix} · точек: {len(vals)}")
        plot = QRect(16, 60, max(10,self.width()-32), max(20,self.height()-78))
        painter.setPen(QPen(grid,1))
        for i in range(5):
            y = plot.top() + int(plot.height()*i/4)
            painter.drawLine(plot.left(), y, plot.right(), y)
        if len(vals) < 2:
            painter.setPen(muted); painter.drawText(plot, Qt.AlignCenter, "Ожидание данных…")
            return
        ymax = max(max(vals), 1.0)
        # Add headroom so a single spike does not touch the card edge.
        ymax *= 1.15
        points=[]
        count=len(vals)
        for i,val in enumerate(vals):
            x=plot.left()+int((plot.width()-1)*i/max(1,count-1))
            y=plot.bottom()-int((plot.height()-1)*val/ymax)
            points.append(QPoint(x,y))
        painter.setPen(QPen(blue,2))
        painter.drawPolyline(QPolygon(points))
        painter.setPen(muted)
        painter.drawText(plot.left(), plot.top()+12, f"{ymax:.0f}{self.suffix}")
        painter.drawText(plot.left(), plot.bottom(), "0")


class _DiagnosticsSignals(QObject):
    sample = pyqtSignal(object)


class DiagnosticsCenterDialog(QDialog):
    """Maximized, live, read-mostly diagnostics center for SmartOrder."""
    def __init__(self, owner):
        super().__init__(owner)
        self.owner = owner
        self.db = owner.db
        self._closed = False
        self._probe_running = False
        self._last_deep_probe = 0.0
        self._force_quick = True
        self._signals = _DiagnosticsSignals(self)
        self._signals.sample.connect(self._apply_sample)
        self._heartbeat_last = time.monotonic()
        self._build_ui()
        self._apply_theme()
        self._probe_timer = QTimer(self); self._probe_timer.setInterval(2000); self._probe_timer.timeout.connect(self._kick_probe); self._probe_timer.start()
        self._clock_timer = QTimer(self); self._clock_timer.setInterval(1000); self._clock_timer.timeout.connect(self._heartbeat); self._clock_timer.start()
        QTimer.singleShot(0, self._kick_probe)

    def _apply_theme(self):
        theme = getattr(getattr(self.owner, "ui_settings", None), "theme", "light")
        try:
            _apply_modal_theme(self, self.owner)
        except Exception:
            pass
        self.setProperty("theme", theme)
        set_theme_recursive(self, theme)
        for graph in (self.db_graph, self.ui_graph):
            graph.setProperty("theme", theme); graph.update()
        dark = theme == "dark"
        self.setStyleSheet(("QDialog{background:#1C1C1E;color:#F5F5F7;}" if dark else "QDialog{background:#F5F5F7;color:#1D1D1F;}") +
                           "QFrame#DiagCard{border:1px solid rgba(128,128,128,45);border-radius:14px;padding:4px;}"
                           "QLabel#DiagTitle{font-size:22px;font-weight:800;color:#0A84FF;}"
                           "QLabel#DiagCardTitle{font-size:15px;font-weight:800;color:#0A84FF;}"
                           "QLabel#DiagValue{font-size:13px;font-weight:650;}"
                           "QLabel#DiagMuted{font-size:11px;color:#8E8E93;}")

    def _card(self, title: str):
        frame=QFrame(); frame.setObjectName("DiagCard")
        lay=QVBoxLayout(frame); lay.setContentsMargins(14,12,14,12); lay.setSpacing(6)
        head=QLabel(title); head.setObjectName("DiagCardTitle"); lay.addWidget(head)
        value=QLabel("Загрузка…"); value.setObjectName("DiagValue"); value.setWordWrap(True); lay.addWidget(value)
        return frame, value

    def _build_ui(self):
        self.setWindowTitle("Центр диагностики SmartOrder")
        self.setWindowFlag(Qt.WindowContextHelpButtonHint, False)
        # The dialog is maximized by the caller, but its minimum must still
        # fit a 1024x768 desktop and high-DPI window decorations.
        self.setMinimumSize(720, 480)
        root=QVBoxLayout(self); root.setContentsMargins(18,14,18,14); root.setSpacing(10)
        top=QHBoxLayout(); title=QLabel("Центр диагностики"); title.setObjectName("DiagTitle"); top.addWidget(title)
        self.live_label=QLabel("● LIVE"); self.live_label.setStyleSheet("color:#34C759;font-weight:800;"); top.addWidget(self.live_label); top.addStretch(1)
        self.clock_label=QLabel(); self.clock_label.setObjectName("DiagMuted"); top.addWidget(self.clock_label)
        close=QPushButton("Закрыть"); close.clicked.connect(self.accept); top.addWidget(close); root.addLayout(top)

        cards=QHBoxLayout(); cards.setSpacing(10)
        card,self.db_value=self._card("База данных"); cards.addWidget(card,1)
        card,self.storage_value=self._card("Хранилище"); cards.addWidget(card,1)
        card,self.backup_value=self._card("Резервные копии"); cards.addWidget(card,1)
        card,self.client_value=self._card("Клиент / ресурсы"); cards.addWidget(card,1)
        root.addLayout(cards)

        graphs=QHBoxLayout(); graphs.setSpacing(10)
        self.db_graph=_DiagnosticsGraph("Отклик SQLite / SMB", " мс", self); graphs.addWidget(self.db_graph,1)
        self.ui_graph=_DiagnosticsGraph("Задержка UI event loop", " мс", self); graphs.addWidget(self.ui_graph,1)
        root.addLayout(graphs,1)

        details=QFrame(); details.setObjectName("DiagCard"); dv=QVBoxLayout(details); dv.setContentsMargins(14,10,14,10)
        dh=QHBoxLayout(); dtitle=QLabel("Диагностика одним экраном"); dtitle.setObjectName("DiagCardTitle"); dh.addWidget(dtitle); dh.addStretch(1)
        self.quick_btn=QPushButton("Проверить целостность БД"); self.quick_btn.clicked.connect(self._request_quick_check); dh.addWidget(self.quick_btn)
        logs=QPushButton("Собрать логи"); logs.clicked.connect(self._collect_logs); dh.addWidget(logs)
        open_logs=QPushButton("Папка логов"); open_logs.clicked.connect(self._open_logs); dh.addWidget(open_logs); dv.addLayout(dh)
        self.details_browser=QTextBrowser(); self.details_browser.setFrameShape(QFrame.NoFrame); self.details_browser.setOpenExternalLinks(False); self.details_browser.setMaximumHeight(190); dv.addWidget(self.details_browser)
        root.addWidget(details)

    def _heartbeat(self):
        now=time.monotonic(); jitter=max(0.0,(now-self._heartbeat_last)*1000.0-1000.0); self._heartbeat_last=now
        self.ui_graph.add_value(jitter)
        self.clock_label.setText(datetime.now().strftime("%d.%m.%Y %H:%M:%S"))

    def _request_quick_check(self):
        self._force_quick=True
        self.quick_btn.setEnabled(False); self.quick_btn.setText("Проверка…")
        self._kick_probe()

    def _kick_probe(self):
        if self._closed or self._probe_running:
            return
        self._probe_running=True
        now=time.monotonic(); deep=(now-self._last_deep_probe)>=10.0
        if deep: self._last_deep_probe=now
        quick=self._force_quick; self._force_quick=False
        threading.Thread(target=self._probe_worker,args=(deep,quick),daemon=True).start()

    @staticmethod
    def _latest_db_file(folder: Path, recursive: bool=False):
        try:
            files=list(folder.rglob("*.db") if recursive else folder.glob("*.db"))
            files=[p for p in files if p.is_file()]
            if not files: return {"count":0,"latest":"—","age":"—","bytes":0}
            latest=max(files,key=lambda p:p.stat().st_mtime); total=sum(p.stat().st_size for p in files)
            age=max(0,int(time.time()-latest.stat().st_mtime)); hours=age/3600.0
            return {"count":len(files),"latest":latest.name,"age":f"{hours:.1f} ч","bytes":total}
        except Exception as exc:
            return {"count":0,"latest":"ошибка","age":str(exc),"bytes":0}

    @staticmethod
    def _human_bytes(value):
        try: value=float(value)
        except Exception: return "—"
        units=("Б","КБ","МБ","ГБ","ТБ")
        idx=0
        while value>=1024 and idx<len(units)-1: value/=1024.0; idx+=1
        return f"{value:.1f} {units[idx]}"

    @staticmethod
    def _is_remote_path(path: Path):
        raw=str(path)
        if raw.startswith("\\\\"):
            return True
        if os.name=="nt":
            try:
                import ctypes
                drive=Path(path).drive
                if drive:
                    return int(ctypes.windll.kernel32.GetDriveTypeW(drive+"\\"))==4
            except Exception:
                pass
        return False

    def _probe_worker(self, deep: bool, quick: bool):
        payload={"deep":deep,"quick_ran":False}
        try:
            started=time.perf_counter(); ms=self.db.stable_ping_ms(3); payload.update(db_ok=True,db_ms=ms,probe_ms=(time.perf_counter()-started)*1000.0,db_error="")
        except Exception as exc:
            payload.update(db_ok=False,db_ms=0.0,probe_ms=0.0,db_error=str(exc))
        dbp=Path(database_path())
        try: payload["db_size"]=dbp.stat().st_size
        except Exception: payload["db_size"]=0
        payload["db_path"]=str(dbp); payload["remote_db"]=self._is_remote_path(dbp)
        try:
            usage=shutil.disk_usage(str(dbp.parent)); payload.update(disk_total=usage.total,disk_free=usage.free)
        except Exception as exc:
            payload.update(disk_total=0,disk_free=0,disk_error=str(exc))
        try: payload["change_token"]=self.db.change_token()
        except Exception: payload["change_token"]="—"
        if quick:
            try: payload["quick_check"]=self.db.quick_check(); payload["quick_ran"]=True
            except Exception as exc: payload["quick_check"]=f"Ошибка: {exc}"; payload["quick_ran"]=True
        if deep:
            try:
                dirs=shared_dirs()
                payload["manual"]=self._latest_db_file(dirs["manual"])
                payload["auto"]=self._latest_db_file(dirs["auto"])
                payload["before_restore"]=self._latest_db_file(dirs["before_restore"])
                payload["archives"]=self._latest_db_file(dirs["archives"],True)
            except Exception as exc:
                payload["backup_error"]=str(exc)
            try:
                logs=local_logs_dir(); files=[p for p in logs.rglob("*") if p.is_file()]
                payload["logs_count"]=len(files); payload["logs_bytes"]=sum(p.stat().st_size for p in files)
                crash=logs/"crash.log"
                payload["crash_size"]=crash.stat().st_size if crash.exists() else 0
            except Exception:
                pass
        try:
            if not self._closed: self._signals.sample.emit(payload)
        finally:
            self._probe_running=False

    def _apply_sample(self, data):
        if self._closed: return
        ok=bool(data.get("db_ok")); ms=float(data.get("db_ms",0.0) or 0.0)
        self.db_graph.add_value(ms if ok else 0.0)
        mode="Сетевая" if data.get("remote_db") else "Локальная"
        db_state=(f"OK · {ms:.1f} мс" if ok else f"НЕДОСТУПНА · {data.get('db_error','')}")
        quick=getattr(self,"_last_quick","не проверено")
        if data.get("quick_ran"):
            quick=str(data.get("quick_check","unknown")); self._last_quick=quick
            self.quick_btn.setEnabled(True); self.quick_btn.setText("Проверить целостность БД")
        self.db_value.setText(f"{db_state}\nРежим: {mode}\nquick_check: {quick}\nChange token: {data.get('change_token','—')}")
        total=int(data.get("disk_total",0) or 0); free=int(data.get("disk_free",0) or 0)
        pct=(free/total*100.0) if total else 0.0
        self.storage_value.setText(f"БД: {self._human_bytes(data.get('db_size',0))}\nСвободно: {self._human_bytes(free)} / {self._human_bytes(total)} ({pct:.0f}%)\n{data.get('db_path','')}")
        if data.get("deep"):
            self._last_backup_data=data
        deep=getattr(self,"_last_backup_data",{})
        def one(key,label):
            d=deep.get(key) or {}; return f"{label}: {d.get('latest','—')} · {d.get('age','—')} · {d.get('count',0)} шт."
        self.backup_value.setText("\n".join((one("auto","Auto"),one("manual","Manual"),one("before_restore","Before restore"),one("archives","Archives"))))
        resources=[]
        for label,name in (("Login GIF","login_background.gif"),("About GIF","loading2.gif"),("EXE icon","smartorder_app_icon.ico")):
            try: exists=resource_path(name).exists()
            except Exception: exists=False
            resources.append(f"{label}: {'OK' if exists else 'НЕ НАЙДЕН'}")
        self.client_value.setText(f"SmartOrder {APP_VERSION}\n{self.owner.user.username} · {self.owner.user.role}\nПК: {socket.gethostname()}\n"+" · ".join(resources))
        logs_count=deep.get("logs_count","—"); logs_size=self._human_bytes(deep.get("logs_bytes",0)); crash=self._human_bytes(deep.get("crash_size",0))
        remote_note="OK: общая/сетевая БД" if data.get("remote_db") else "ВНИМАНИЕ: путь БД определяется как локальный"
        quick_color="#34C759" if str(quick).lower()=="ok" else "#FF9F0A"
        html=(f'<b>Путь БД:</b> {data.get("db_path","")}<br>'
              f'<b>Тип подключения:</b> {remote_note}<br>'
              f'<b>Целостность:</b> <span style="color:{quick_color}">{quick}</span><br>'
              f'<b>Логи:</b> {logs_count} файлов · {logs_size}; crash.log: {crash}<br>'
              f'<b>Сессия:</b> {self.owner._session_text()}<br>'
              f'<b>Network root:</b> {network_root()}<br>'
              f'<b>Local logs:</b> {local_logs_dir()}')
        self.details_browser.setHtml(html)

    def _collect_logs(self):
        try: self.owner.collect_logs()
        except Exception as exc: error(self,"Центр диагностики",exc)

    def _open_logs(self):
        folder=local_logs_dir(); folder.mkdir(parents=True,exist_ok=True)
        if os.name=="nt":
            try: os.startfile(str(folder))
            except Exception as exc: error(self,"Папка логов",exc)
        else:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    def closeEvent(self,event):
        self._closed=True
        try: self._probe_timer.stop(); self._clock_timer.stop()
        except Exception: pass
        super().closeEvent(event)



class RC18MainWindow(RC17MainWindow):
    AUDIT_RANGE_DAYS = 30

    def _build(self):
        super()._build()
        self._rc18_zoom_timer = QTimer(self)
        self._rc18_zoom_timer.setSingleShot(True)
        self._rc18_zoom_timer.setInterval(85)
        self._rc18_zoom_timer.timeout.connect(self._rc18_commit_zoom)
        self._rc18_shortcuts = []
        for seq, delta in (("Ctrl++", 10), ("Ctrl+=", 10), ("Ctrl+-", -10)):
            shortcut = QShortcut(QKeySequence(seq), self)
            shortcut.activated.connect(lambda d=delta: self._rc18_zoom_step(d))
            self._rc18_shortcuts.append(shortcut)

    # ---------------- synchronization / audit ----------------
    def _sync_current_tab(self):
        manual = self.sender() is getattr(self, "admin_sync_btn", None)
        super()._sync_current_tab()
        if manual:
            try:
                ok, ms, message = getattr(self, "_last_ping", (False, 0.0, ""))
                detail = (
                    f"ПК: {socket.gethostname()}; последний отклик: {ms:.0f} мс"
                    if ok else f"ПК: {socket.gethostname()}; {message or 'проверка БД запущена'}"
                )
                self.db.log_action(
                    self.user.username, "Синхронизировал", "База данных",
                    Path(database_path()).name, detail,
                )
                if hasattr(self, "audit_table"):
                    self.refresh_audit()
            except Exception:
                pass

    def _build_admin_tab(self):
        content = super()._build_admin_tab()
        try:
            base_layout = content.layout()
            if isinstance(base_layout, QVBoxLayout):
                base_layout.setContentsMargins(8,5,8,5)
                base_layout.setSpacing(5)
        except Exception:
            pass

        # Full-screen diagnostics center is opened from Administration, not as a permanent tab.
        try:
            for group in content.findChildren(QGroupBox):
                if "Резервное копирование" not in group.title():
                    continue
                gv = group.layout()
                if not isinstance(gv, QVBoxLayout) or gv.count() < 1:
                    continue
                row_item = gv.itemAt(0)
                row = row_item.layout() if row_item is not None else None
                if isinstance(row, QHBoxLayout):
                    self.diagnostics_center_btn = QPushButton("Центр диагностики")
                    self.diagnostics_center_btn.setObjectName("SecondaryButton")
                    self.diagnostics_center_btn.setToolTip("Live-состояние БД, резервных копий, диска, ресурсов и интерфейса.")
                    self.diagnostics_center_btn.clicked.connect(self.open_diagnostics_center)
                    # Insert before the trailing stretch when it exists.
                    row.insertWidget(max(0, row.count()-1), self.diagnostics_center_btn)
                break
        except Exception:
            pass

        # Audit filters use the same Heavy date-range calendar as Orders.
        audit = getattr(self, "audit_table", None)
        if audit is not None:
            group = audit.parentWidget()
            while group is not None and not isinstance(group, QGroupBox):
                group = group.parentWidget()
            if isinstance(group, QGroupBox):
                group.setMinimumHeight(360)
                lay = group.layout()
                filters = QHBoxLayout(); filters.setSpacing(7)
                filters.addWidget(QLabel("Период:"))
                self.audit_date_filter = DateRangeEdit()
                self.audit_date_filter.setMinimumWidth(270)
                self.audit_date_filter.setDateRange(
                    QDate.currentDate().addDays(-self.AUDIT_RANGE_DAYS),
                    QDate.currentDate(), False,
                )
                self.audit_date_filter.dateChanged.connect(self.refresh_audit)
                filters.addWidget(self.audit_date_filter)
                filters.addWidget(QLabel("Пользователь:"))
                self.audit_user_filter = SmartComboBox()
                self.audit_user_filter.setMinimumWidth(190)
                self.audit_user_filter.addItem("Все пользователи", None)
                self._rc18_reload_audit_users()
                self.audit_user_filter.currentIndexChanged.connect(self.refresh_audit)
                filters.addWidget(self.audit_user_filter)
                filters.addStretch(1)
                # RC4 puts its title/help header at index 0.
                if isinstance(lay, QVBoxLayout):
                    lay.insertLayout(min(1, lay.count()), filters)
                header = audit.horizontalHeader()
                for col, width in ((0,220),(1,190),(2,235),(3,195),(4,230)):
                    audit.setColumnWidth(col,width)
                header.setStretchLastSection(True)

        # At 200% allow scrolling instead of overlap/clipping.
        scroll = QScrollArea()
        scroll.setObjectName("AdminResponsiveScroll")
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        content.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        scroll.setWidget(content)
        return scroll

    def open_diagnostics_center(self):
        dialog = DiagnosticsCenterDialog(self)
        dialog.setWindowState(dialog.windowState() | Qt.WindowMaximized)
        dialog.exec_()

    def _rc18_reload_audit_users(self):
        combo = getattr(self, "audit_user_filter", None)
        if combo is None:
            return
        current = combo.currentData()
        combo.blockSignals(True)
        combo.clear(); combo.addItem("Все пользователи", None)
        try:
            for username in self.db.audit_usernames():
                combo.addItem(username, username)
        except Exception:
            pass
        idx = combo.findData(current)
        combo.setCurrentIndex(idx if idx >= 0 else 0)
        combo.blockSignals(False)

    def refresh_audit(self):
        if not hasattr(self, "audit_table"):
            return
        try:
            self._rc18_reload_audit_users()
            start = end = user = None
            if hasattr(self, "audit_date_filter"):
                start = self.audit_date_filter.startDate().toString("yyyy-MM-dd")
                end = self.audit_date_filter.endDate().toString("yyyy-MM-dd")
            if hasattr(self, "audit_user_filter"):
                user = self.audit_user_filter.currentData()
            rows = self.db.recent_audit_filtered(start, end, user, 1000)
            self.audit_table.setUpdatesEnabled(False)
            self.audit_table.setRowCount(len(rows))
            for i, row in enumerate(rows):
                for c, value in enumerate(row):
                    self.audit_table.setItem(i,c,make_item(value))
                self.audit_table.setRowHeight(i,38)
            self.audit_table.setUpdatesEnabled(True)
        except Exception as exc:
            try: self.audit_table.setUpdatesEnabled(True)
            except Exception: pass
            error(self, "Журнал действий", exc)

    # ---------------- people recycle / restore ----------------
    def _build_employees_tab(self):
        tab = super()._build_employees_tab()
        try:
            self.recent_deleted_btn.setObjectName("SecondaryButton")
            self.people_table.setContextMenuPolicy(Qt.CustomContextMenu)
            self.people_table.customContextMenuRequested.connect(self._rc18_people_context_menu)
        except Exception:
            pass
        return tab

    def _toggle_recent_deleted_people(self, checked):
        super()._toggle_recent_deleted_people(checked)
        # MotionFilter animates all QPushButtons; force a repaint after text swap.
        try: self.recent_deleted_btn.update()
        except Exception: pass

    def delete_person(self):
        row = self.people_table.currentRow()
        if row < 0:
            return
        name = str(self.people_table.item(row,0).data(Qt.UserRole + 2) or self.people_table.item(row,0).text())
        mode = self._people_mode()
        if mode == "master":
            prompt = f'Удалить мастера "{name}" ?'
        elif mode == "department":
            prompt = f'Удалить подразделение "{name}" ?'
        else:
            prompt = f'Удалить работника "{name}" ?'
        if question(self, "Удаление", prompt) != QMessageBox.Yes:
            return
        ident = int(self.people_table.item(row,0).data(Qt.UserRole))
        try:
            if mode == "department":
                self.db.delete_department(self.user, ident)
            else:
                self.db.delete_employee(self.user, ident)
            self.refresh_people(); self._refresh_reference_filters()
        except Exception as exc:
            error(self, "Удаление", exc)

    def _rc18_people_context_menu(self, pos):
        item = self.people_table.itemAt(pos)
        if item is None:
            return
        self.people_table.selectRow(item.row())
        if not bool(getattr(self, "_show_recent_deleted_people", False)):
            return
        menu = QMenu(self)
        restore = menu.addAction("Восстановить")
        restore.setEnabled(self.can(Permission.EMPLOYEES_RESTORE))
        act = menu.exec_(self.people_table.viewport().mapToGlobal(pos))
        if act != restore or not restore.isEnabled():
            return
        ident = int(self.people_table.item(item.row(),0).data(Qt.UserRole))
        entity_type = "department" if self._people_mode() == "department" else "employee"
        try:
            self.db.restore_soft_deleted(self.user, entity_type, ident)
            self.refresh_people(); self._refresh_reference_filters()
            info(self, "Восстановление", "Запись восстановлена и снова доступна для выбора.")
        except Exception as exc:
            error(self, "Восстановление", exc)

    # ---------------- catalog recycle / context menu ----------------
    def _build_catalog_tab(self):
        tab = super()._build_catalog_tab()
        self._show_recent_deleted_work = False
        self.work_recent_btn = QPushButton("Недавно удалённые")
        self.work_recent_btn.setObjectName("SecondaryButton")
        self.work_recent_btn.setCheckable(True)
        self.work_recent_btn.setMinimumWidth(190)
        self.work_recent_btn.toggled.connect(self._rc18_toggle_recent_work)
        try:
            search_item = tab.layout().itemAt(1)
            search_layout = search_item.layout() if search_item is not None else None
            if search_layout is not None:
                # Insert immediately after "Найдено N из N", before the stretch.
                search_layout.insertWidget(max(0, search_layout.count()-1), self.work_recent_btn)
        except Exception:
            pass
        self.work_table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.work_table.customContextMenuRequested.connect(self._rc18_work_context_menu)
        self.work_table.setColumnWidth(2,205)
        self.work_table.setColumnWidth(3,220)
        self.refresh_work_types()
        return tab

    def _rc18_toggle_recent_work(self, checked):
        self._show_recent_deleted_work = bool(checked)
        self.work_recent_btn.setText("← Текущие" if checked else "Недавно удалённые")
        try:
            self.work_name.clear(); self.work_code.clear(); self.work_price.clear()
            self.work_table.clearSelection()
        except Exception:
            pass
        self.refresh_work_types()

    def refresh_work_types(self):
        if not hasattr(self, "work_table"):
            return
        recent = bool(getattr(self, "_show_recent_deleted_work", False))
        needle = self.work_search.text().strip().casefold().replace("ё","е")
        if recent:
            source = self.db.list_recent_deleted_work_types(30)
            rows = [r for r in source if not needle or needle in (str(r[1])+" "+str(r[2])).casefold().replace("ё","е")]
            self.work_table.setHorizontalHeaderLabels(["Наименование","Код работы","Стоимость в рублях","Удалено"])
        else:
            source = self.db.get_active_work_types()
            rows = [r for r in source if not needle or needle in (str(r[1])+" "+str(r[2])).casefold().replace("ё","е")]
            self.work_table.setHorizontalHeaderLabels(["Наименование","Код работы","Стоимость в рублях","Дата регистрации"])
        self.work_table.setUpdatesEnabled(False)
        self.work_table.setRowCount(len(rows))
        for i,r in enumerate(rows):
            if recent:
                vals=[str(r[1])+_RC16_MARKED_SUFFIX,r[2],fmt(r[3]),r[6]]
            else:
                vals=[r[1],r[2],fmt(r[3]),r[4]]
            for c,v in enumerate(vals):
                self.work_table.setItem(i,c,make_item(v))
            first=self.work_table.item(i,0)
            first.setData(Qt.UserRole,int(r[0]))
            first.setData(Qt.UserRole+1,recent)
            first.setData(Qt.UserRole+2,str(r[1]))
            if recent:
                first.setForeground(QBrush(QColor("#FF3B30")))
        self.work_table.setUpdatesEnabled(True)
        total = len(source)
        self.work_results_label.setText(("Недавно удалено: " if recent else "Найдено: ") + f"{len(rows)}" + ("" if recent else f" из {total}"))
        try:
            self.work_edit_btn.setEnabled(False)
            self.work_save_btn.setEnabled(False)
            self.work_delete_btn.setEnabled(False)
        except Exception:
            pass

    def _heavy_work_selection(self):
        if bool(getattr(self, "_show_recent_deleted_work", False)):
            row=self.work_table.currentRow()
            if row>=0:
                item=self.work_table.item(row,0)
                self.work_name.setText(str(item.data(Qt.UserRole+2) or ""))
                self.work_code.setText(self.work_table.item(row,1).text())
                self.work_price.setText(self.work_table.item(row,2).text())
            self.work_edit_btn.setEnabled(False);self.work_save_btn.setEnabled(False);self.work_delete_btn.setEnabled(False)
            return
        return super()._heavy_work_selection()

    def _rc18_work_context_menu(self, pos):
        item = self.work_table.itemAt(pos)
        if item is None or item.column() not in (0, 1):
            return
        row=item.row(); self.work_table.selectRow(row)
        recent = bool(getattr(self, "_show_recent_deleted_work", False))
        menu=QMenu(self)
        copy_action=menu.addAction("Копировать")
        edit_action=delete_action=restore_action=None
        if recent:
            restore_action=menu.addAction("Восстановить")
            restore_action.setEnabled(self.can(Permission.CATALOG_RESTORE))
        else:
            edit_action=menu.addAction("Редактировать");edit_action.setEnabled(self.can(Permission.CATALOG_EDIT))
            delete_action=menu.addAction("Удалить");delete_action.setEnabled(self.can(Permission.CATALOG_DELETE))
        act=menu.exec_(self.work_table.viewport().mapToGlobal(pos))
        if act==copy_action:
            QApplication.clipboard().setText(str(item.text()))
        elif edit_action is not None and act==edit_action:
            self._heavy_work_selection(); self.work_name.setFocus(); self.work_save_btn.setEnabled(True)
        elif delete_action is not None and act==delete_action:
            self.delete_work_type()
        elif restore_action is not None and act==restore_action and restore_action.isEnabled():
            ident=int(self.work_table.item(row,0).data(Qt.UserRole))
            try:
                self.db.restore_soft_deleted(self.user,"work_type",ident)
                self.refresh_work_types()
                info(self,"Восстановление","Работа восстановлена и снова доступна для новых нарядов.")
            except Exception as exc:
                error(self,"Восстановление",exc)

    # ---------------- history creator ----------------
    def _order_selection_changed(self):
        super()._order_selection_changed()
        ref=self._selected_ref()
        if not isinstance(ref,int) or not hasattr(self,"info_users_list"):
            return
        try:
            creator=self.db.order_creator(ref)
            if creator:
                for i in range(self.info_users_list.count()):
                    item=self.info_users_list.item(i)
                    if item.text().startswith("Создал: Система"):
                        suffix=item.text()[len("Создал: Система"):]
                        item.setText(f"Создал: {creator}{suffix}")
                        break
        except Exception:
            pass

    # ---------------- responsive zoom ----------------
    def _rc18_zoom_step(self, delta: int):
        slider=getattr(self,"zoom",None)
        if slider is None:
            return
        slider.setValue(max(slider.minimum(),min(slider.maximum(),slider.value()+int(delta))))

    def _compact_responsive_layout(self):
        """Reduce empty gaps as typography grows, keeping labels readable."""
        z=max(0.5,min(2.0,float(getattr(self.ui_settings,"zoom",100))/100.0))
        gap=max(4,int(10/(0.75+0.25*z)))
        for grid in self.findChildren(ResponsiveGrid):
            try:
                grid._grid.setHorizontalSpacing(gap)
                grid._grid.setVerticalSpacing(gap)
            except Exception:
                pass
        left=getattr(self,"orders_header_left",None)
        if left is not None and left.layout() is not None:
            left.layout().setSpacing(gap)
        try:
            self._configure_orders_columns()
        except Exception:
            pass

    def _ensure_tab_widths(self):
        bar=getattr(getattr(self,"tabs",None),"tabBar",lambda:None)()
        if bar is None:
            return
        metrics=QFontMetrics(bar.font())
        width=max([metrics.horizontalAdvance(self.tabs.tabText(i))+32 for i in range(self.tabs.count())] or [140])
        bar.setStyleSheet(f"QTabBar::tab{{min-width:{max(140,width)}px;}}")
        bar.setElideMode(Qt.ElideNone);bar.setUsesScrollButtons(True);bar.setExpanding(False)

    def _configure_orders_columns(self):
        """Reserve compact identifier columns and keep registration visible."""
        table=getattr(self,"orders_table",None)
        if table is None:
            return
        header=table.horizontalHeader()
        labels=[header.model().headerData(i,Qt.Horizontal,Qt.DisplayRole) or "" for i in range(table.columnCount())]
        metrics=QFontMetrics(header.font())
        fixed={
            0:max(58,metrics.horizontalAdvance(str(labels[0]))+26),
            1:max(108,metrics.horizontalAdvance(str(labels[1]))+30),
            2:max(104,metrics.horizontalAdvance(str(labels[2]))+30),
            5:max(150,metrics.horizontalAdvance(str(labels[5]))+30),
        }
        header.setStretchLastSection(False)
        for column in range(table.columnCount()):
            if column in fixed:
                header.setSectionResizeMode(column,QHeaderView.Fixed)
                table.setColumnWidth(column,fixed[column])
            else:
                header.setSectionResizeMode(column,QHeaderView.Stretch)

    def _apply_zoom(self, value):
        value=max(50,min(200,int(value))); self.ui_settings.zoom=value
        if hasattr(self,"zoom_label"):
            self.zoom_label.setText(f"{value}%")
        timer=getattr(self,"_rc18_zoom_timer",None)
        if timer is None:
            return super()._apply_zoom(value)
        timer.start()

    def _set_visual_zoom(self,value):
        """Apply a visual font/style scale without changing the saved slider."""
        value=max(50,min(200,int(value)))
        app=QApplication.instance()
        if app is not None:
            base=getattr(app,"_smartorder_base_font",None)
            if base is None:
                base=QFont(app.font())
                if base.pointSizeF() <= 0: base.setPointSizeF(12.0)
                app._smartorder_base_font=QFont(base)
            font=QFont(base);font.setPointSizeF(max(8.0,base.pointSizeF()*value/100.0));app.setFont(font)
        apply_apple_design(self,self.ui_settings.theme,value)
        try:
            for browser in self.findChildren(QTextBrowser):
                from .appearance import appearance_of, font_for
                browser.document().setDefaultFont(font_for("body", value, appearance_of(self)))
        except Exception:pass

    def _rc18_commit_zoom(self):
        value=int(self.ui_settings.zoom)
        self._set_visual_zoom(value)
        self._ensure_tab_widths()
        self._compact_responsive_layout()
        try:
            if getattr(self,"_last_saved_zoom",None) != value:
                self.settings_store.save(self.ui_settings)
                self._last_saved_zoom=value
        except Exception:pass
        # QTextDocument does not always inherit a changed QApplication font.
        try:
            for browser in self.findChildren(QTextBrowser):
                from .appearance import appearance_of, font_for
                browser.document().setDefaultFont(font_for("body", value, appearance_of(self)))
        except Exception:
            pass
        # Recover history panel after extreme zoom/fullscreen re-layouts.
        try:
            if hasattr(self,"info_panel"):
                self.info_panel.setVisible(self.can(Permission.ORDERS_HISTORY))
                self.info_panel.updateGeometry()
            current=self.tabs.currentWidget()
            if current is not None:
                current.updateGeometry();current.update()
            self.tabs.updateGeometry();self.tabs.update()
        except Exception:
            pass

    # ---------------- About ----------------
    def _build_about_tab(self):
        tab=GifBackgroundWidget(["loading2.gif","login_background.gif","resources/loading2.gif"])
        root=QVBoxLayout(tab);root.setContentsMargins(28,16,28,16);root.setSpacing(8)

        logo=QLabel()
        if _set_logo(logo,112,"smartorder_logo_icon_light.png","smartorder_logo_icon.png","smartorder_logo_white.png","smartorder_logo.png"):
            root.addWidget(logo,alignment=Qt.AlignCenter)
        edition=self._about_selectable(QLabel(f"Enterprise Edition · Версия {APP_VERSION}"))
        edition.setAlignment(Qt.AlignCenter);edition.setSizePolicy(QSizePolicy.Maximum,QSizePolicy.Preferred)
        edition.setStyleSheet("color:#F5F5F7;background-color:rgba(0,0,0,132);padding:3px 7px;border-radius:5px;")
        root.addWidget(edition,alignment=Qt.AlignCenter)

        policy_path=ensure_usage_policy_document()
        guide_path=ensure_user_guide_document()
        trouble_path=ensure_troubleshooting_document()
        transparent="QFrame#AboutTransparentCard{background:rgba(0,0,0,0);border:none;}"

        columns=QHBoxLayout();columns.setSpacing(26)

        # Left: System.
        system=QFrame();system.setObjectName("AboutTransparentCard");system.setStyleSheet(transparent)
        sv=QVBoxLayout(system);sv.setContentsMargins(12,6,12,6)
        system_html='<div style="line-height:1.8;">'+'<br><br>'.join([
            self._rc13_chip("System",blue=True,bold=True),
            self._rc13_chip(f"Среда выполнения: Python {platform.python_version()}"),
            self._rc13_chip("Движок: PyQt5 5.15.x"),
            self._rc13_chip("Версия: 1.0"),
            '<a href="policy" style="color:#0A84FF;text-decoration:underline;">'+self._rc13_chip("Положение об использовании ПО",blue=True,bold=True)+'</a>',
        ])+'</div>'
        sb=self._about_browser(system_html,lambda _url:QDesktopServices.openUrl(QUrl.fromLocalFile(str(policy_path))) if policy_path else None)
        sv.addWidget(sb,1);columns.addWidget(system,1)

        # Right: Documentation over Help.
        right=QVBoxLayout();right.setSpacing(10)
        docs=QFrame();docs.setObjectName("AboutTransparentCard");docs.setStyleSheet(transparent)
        dv=QVBoxLayout(docs);dv.setContentsMargins(12,6,12,6)
        docs_html='<div style="line-height:1.9;">'+'<br>'.join([
            self._rc13_chip("Документация",blue=True,bold=True),
            '<a href="guide" style="color:#0A84FF;text-decoration:underline;">'+self._rc13_chip("Как работать в программе?",blue=True,bold=True)+'</a> &nbsp; '
            '<a href="pdf" style="color:#0A84FF;text-decoration:underline;">'+self._rc13_chip("[.pdf]",blue=True,bold=True)+'</a>',
            '<a href="problems" style="color:#0A84FF;text-decoration:underline;">'+self._rc13_chip("Возможные проблемы при работе с SmartOrder V 1.0")+'</a>',
        ])+'</div>'
        def docs_link(url):
            key=url.toString()
            if key=="guide" and guide_path:QDesktopServices.openUrl(QUrl.fromLocalFile(str(guide_path)))
            elif key=="pdf":self._rc16_download_guide_pdf(tab)
            elif key=="problems" and trouble_path:QDesktopServices.openUrl(QUrl.fromLocalFile(str(trouble_path)))
        dv.addWidget(self._about_browser(docs_html,docs_link),1);right.addWidget(docs,1)

        help_frame=QFrame();help_frame.setObjectName("AboutTransparentCard");help_frame.setStyleSheet(transparent)
        hv=QVBoxLayout(help_frame);hv.setContentsMargins(12,6,12,6)
        help_html='<div style="line-height:1.9;">'+'<br>'.join([
            self._rc13_chip("Помощь",blue=True,bold=True),
            '<a href="forgot" style="color:#0A84FF;text-decoration:underline;">'+self._rc13_chip("Забыли пароль?")+'</a>',
            '<a href="other" style="color:#0A84FF;text-decoration:underline;">'+self._rc13_chip("Прочее")+'</a>',
        ])+'</div>'
        def help_link(url):
            if url.toString()=="forgot":_RC18SupportDialog("password",self).exec_()
            elif url.toString()=="other":_RC18SupportDialog("other",self).exec_()
        hv.addWidget(self._about_browser(help_html,help_link),1);right.addWidget(help_frame,1)
        columns.addLayout(right,1)
        root.addLayout(columns,1)

        # Footer aligned with the session widget.
        bottom=QHBoxLayout();bottom.setSpacing(12)
        footer_html=(
            '<div>'+self._rc13_chip("Powered by OITS&amp;ZI",bold=True)+' &nbsp; '
            '<a href="https://tmbsir.ru/" style="color:#0A84FF;text-decoration:underline;">'
            +self._rc13_chip("Copyright © 2026 tmbsir")+'</a></div>'
        )
        footer=self._about_browser(footer_html,lambda url:QDesktopServices.openUrl(url))
        footer.setMaximumHeight(46);bottom.addWidget(footer,0,Qt.AlignLeft|Qt.AlignVCenter)
        bottom.addStretch(1)
        self.about_session_label=QLabel()
        self.about_session_label.setStyleSheet("font-size:10px;color:#F5F5F7;background-color:rgba(0,0,0,132);padding:2px 5px;border-radius:4px;")
        bottom.addWidget(self.about_session_label,0,Qt.AlignRight|Qt.AlignVCenter)
        root.addLayout(bottom);self._update_session_labels()
        tab._rc16_download_banner=_RC16DownloadBanner(tab)
        return tab


# RC18 final runtime aliases.
HeavyWorkOrderDialog = RC18WorkOrderDialog
WorkOrderDialog = RC18WorkOrderDialog
_lite_ui.WorkOrderDialog = RC18WorkOrderDialog
HeavyMainWindow = RC18MainWindow
MainWindow = RC18MainWindow
LoginDialog = RC16LoginDialog


# RC18 UI recycle delete handlers: every deletion first goes to the 30-day bin.
def _rc18_delete_work_type_ui(self):
    row=self.work_table.currentRow()
    if row<0 or bool(getattr(self,"_show_recent_deleted_work",False)):
        return
    item=self.work_table.item(row,0)
    raw=str(item.data(Qt.UserRole+2) or item.text())
    ident=int(item.data(Qt.UserRole))
    if question(self,"Удаление",f'Удалить работу "{raw}" ?')!=QMessageBox.Yes:
        return
    try:
        self.db.delete_work_type(self.user,ident)
        self.refresh_work_types();self._clear_work_form()
        info(self,"Удаление",f'Работа «{raw}» перемещена в «Недавно удалённые» на 30 дней.')
    except Exception as exc:
        error(self,"Удаление",exc)


_RC18_OLD_DELETE_PERSON = RC18MainWindow.delete_person
def _rc18_delete_person_ui(self):
    row=self.people_table.currentRow()
    if row<0 or bool(getattr(self,"_show_recent_deleted_people",False)):
        return
    item=self.people_table.item(row,0)
    name=str(item.data(Qt.UserRole+2) or item.text())
    mode=self._people_mode()
    if mode=="master": prompt=f'Удалить мастера "{name}" ?'
    elif mode=="department": prompt=f'Удалить подразделение "{name}" ?'
    else: prompt=f'Удалить работника "{name}" ?'
    if question(self,"Удаление",prompt)!=QMessageBox.Yes:
        return
    ident=int(item.data(Qt.UserRole))
    try:
        if mode=="department": self.db.delete_department(self.user,ident)
        else: self.db.delete_employee(self.user,ident)
        self.refresh_people();self._refresh_reference_filters()
        info(self,"Удаление",f'«{name}» перемещён(а) в «Недавно удалённые» на 30 дней.')
    except Exception as exc:
        error(self,"Удаление",exc)


RC18MainWindow.delete_work_type=_rc18_delete_work_type_ui
RC18MainWindow.delete_person=_rc18_delete_person_ui


class RC20WorkOrderDialog(RC18WorkOrderDialog):
    """One visible payment column while old snapshots keep their components."""
    TOTAL_COLS = (5, 6, 7, 9, 10)

    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        theme,zoom=_theme_of(self.parent())
        set_theme_recursive(self,theme)
        # Choose final geometry and colours before exec_()/show(). Maximizing
        # from showEvent caused a second native window transition and repaint.
        palette=self.palette()
        palette.setColor(QPalette.Window,QColor("#1C1C1E" if theme=="dark" else "#F5F5F7"))
        palette.setColor(QPalette.WindowText,QColor("#F5F5F7" if theme=="dark" else "#1D1D1F"))
        self.setPalette(palette);self.setAutoFillBackground(True)
        self.setWindowState(self.windowState()|Qt.WindowMaximized)

    def showEvent(self,event):
        # Skip legacy layers that maximize again, restyle the application and
        # force multiple synchronous non-client repaints during the first show.
        QDialog.showEvent(self,event)
        theme,_=_theme_of(self.parent())
        _rc4_set_windows_titlebar_dark(self,theme=="dark")

    def _build(self):
        self.setProperty("fullWindowControls", True)
        super()._build()
        from .order_calendar import install_order_calendar
        install_order_calendar(self.order_date)
        self.table.setColumnHidden(8, True)
        self.table.horizontalHeaderItem(10).setText("Оплата")
        self.table.horizontalHeaderItem(1).setText("Часы")
        self.table.horizontalHeaderItem(1).setToolTip("Часы работы")
        if hasattr(self, "order_number_label"):
            theme, _ = _theme_of(self.parent())
            self.order_number_label.setStyleSheet("background:transparent;border:none;padding:0;color:" + ("#FFFFFF" if theme == "dark" else "#202020") + ";font-weight:900;")
        from .interaction_ui import align_order_footer
        align_order_footer(self)
        from .order_table_layout import EditorColumnLayout
        self.editor_columns = EditorColumnLayout(self)
        self.table.cellDoubleClicked.connect(self._work_double_clicked)

    def _work_double_clicked(self, row, column):
        if self.view_only or column != 2 or self._is_total(row) or self.separate_worker_check.isChecked():
            return
        self.table.setCurrentCell(row, column)
        self._add_works()

    def _export_current_order(self):
        if not self.user.can(Permission.ORDERS_EXPORT):return
        version = self.order['info']['version'] if self.order else 'Новый'
        path, _ = QFileDialog.getSaveFileName(self, "Выгрузить наряд", f"Наряд_{version}.xlsx", "Excel (*.xlsx)")
        if not path:return
        if not path.lower().endswith('.xlsx'):path += '.xlsx'
        try:
            result = export_order_xlsx(path, self.current_order_snapshot())
            info(self, "Excel", f"Сохранено:\n{result}")
        except Exception as exc:error(self, "Excel", exc)

    def current_order_snapshot(self):
        if self.view_only and self.order is not None:
            return self.order
        data = self.get_data()
        return {"info": {**(self.order["info"] if self.order else {}),
                         **{key: value for key, value in data.items() if key != "lines"},
                         "version": self.order["info"]["version"] if self.order else "Новый",
                         "master": self.master.currentText(), "department": self.department.currentText()},
                "lines": data["lines"]}

    def _print_current_order(self):
        if not self.user.can(Permission.ORDERS_EXPORT):
            return
        from .order_printing import request_print
        try:
            if hasattr(self.db, "manager"):
                self.db.manager.require(self.db.user, Permission.ORDERS_EXPORT)
            request_print(self.current_order_snapshot(), self)
        except Exception as exc:
            error(self, "Печать", exc)

    def _write_calculated(self, row, line):
        was_blocked = self.table.signalsBlocked()
        self.table.blockSignals(True)
        try:
            super()._write_calculated(row, line)
            self.table.item(row, 10).setText(fmt(line.total_payment, 2))
            self._apply_flags(row)
        finally:
            self.table.blockSignals(was_blocked)

    def _apply_flags(self, row):
        super()._apply_flags(row)
        item = self.table.item(row, 10)
        if item is not None:
            item.setFlags((item.flags() | Qt.ItemIsEnabled | Qt.ItemIsSelectable) & ~Qt.ItemIsEditable)
            item.setBackground(QBrush()); item.setForeground(QBrush()); item.setToolTip("Оплата = рассчитанная оплата ФИКС + рассчитанная оплата ФАКТ")


HeavyWorkOrderDialog = RC20WorkOrderDialog
WorkOrderDialog = RC20WorkOrderDialog
_lite_ui.WorkOrderDialog = RC20WorkOrderDialog
