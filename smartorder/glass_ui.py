"""HTML/CSS orders surface, connected to the existing Qt controller.

Only presentation lives in Chromium. Orders, permissions, edit locks, Excel,
dialogs and live reads continue to use enterprise_ui and its repositories.
There is no HTTP server and no database access from JavaScript.
"""
from __future__ import annotations
from .i18n import source_text, item_source, tr

import hashlib
import json
import logging
from pathlib import Path

from PyQt5.QtCore import (QDate, QEvent, QObject, QPoint, QSize, Qt, QTimer, QUrl,
                          pyqtSignal, pyqtSlot)
from PyQt5.QtGui import QColor, QKeyEvent
from PyQt5.QtWebChannel import QWebChannel
from PyQt5.QtWebEngineCore import QWebEngineUrlRequestInterceptor
from PyQt5.QtWebEngineWidgets import QWebEnginePage, QWebEngineProfile, QWebEngineView
from PyQt5.QtWidgets import (QApplication, QDialog, QLabel, QMessageBox, QStackedWidget,
                             QWidget, QHBoxLayout, QVBoxLayout)

from .config import resource_path
from .enterprise_ui import MainWindow as EnterpriseWindow
from .heavy_ui import DateRangeDialog
from .security import ACCOUNTING_ROLES, ANALYTICS_ONLY_ROLES, Permission, split_roles
from .workshops import WORKSHOPS, allowed_workshops

log = logging.getLogger(__name__)
ASSET_ROOT = resource_path("smartorder/glass")
ACTIONS = frozenset({"ready", "painted", "select", "filter", "date", "date_range", "create", "edit",
                     "export", "delete", "open", "view", "history", "tab",
                     "columns", "theme", "zoom", "refresh", "workshop", "notifications",
                     "minimize", "maximize", "close", "move", "resize", "fullscreen"})


def row_key(ref):
    """Opaque stable handles: never accept a filesystem path from the page."""
    if isinstance(ref, int):
        return f"order:{ref}"
    return "draft:" + hashlib.sha256(str(ref).encode("utf-8")).hexdigest()[:24]


class LocalAssetsOnly(QWebEngineUrlRequestInterceptor):
    def interceptRequest(self, info):
        url = info.requestUrl()
        if url.scheme() == "file":
            try:
                allowed = Path(url.toLocalFile()).resolve().is_relative_to(ASSET_ROOT.resolve())
            except (OSError, ValueError):
                allowed = False
        else:
            allowed = url.toString() == "qrc:///qtwebchannel/qwebchannel.js"
        info.block(not allowed)


class OrdersPage(QWebEnginePage):
    def acceptNavigationRequest(self, url, navigation_type, is_main_frame):
        return bool(is_main_frame and url.isLocalFile()
                    and Path(url.toLocalFile()).resolve() == (ASSET_ROOT / "index.html").resolve())

    def javaScriptConsoleMessage(self, level, message, line, source):
        if level == QWebEnginePage.ErrorMessageLevel:
            log.error("Orders UI JavaScript, line %s: %s", line, message)

    def createWindow(self, window_type):
        return None


class OrdersBridge(QObject):
    stateChanged = pyqtSignal(str)
    message = pyqtSignal(str)

    def __init__(self, owner):
        super().__init__(owner)
        self.owner = owner

    @pyqtSlot(str, str, result=bool)
    def dispatch(self, action, encoded):
        if action not in ACTIONS or len(encoded) > 4096:
            return False
        try:
            payload = json.loads(encoded)
        except (ValueError, TypeError):
            return False
        if not isinstance(payload, dict):
            return False
        # Return the WebChannel response before a native dialog starts its
        # nested event loop. All existing Qt actions run on the GUI thread.
        QTimer.singleShot(0, lambda: self.owner._glass_command(action, payload))
        return True


class OrdersWebView(QWebEngineView):
    def __init__(self, owner):
        super().__init__(owner)
        self.setObjectName("LiquidGlassOrdersView")
        self.setContextMenuPolicy(Qt.NoContextMenu)
        self.profile = QWebEngineProfile(self)  # ephemeral, no browser account/storage
        self.interceptor = LocalAssetsOnly(self.profile)
        self.profile.setUrlRequestInterceptor(self.interceptor)
        self.profile.downloadRequested.connect(lambda download: download.cancel())
        page = OrdersPage(self.profile, self)
        # The profile must outlive the page's private renderer during teardown.
        self.profile.setParent(page)
        page.setBackgroundColor(QColor(Qt.transparent))
        from PyQt5.QtWebEngineWidgets import QWebEngineSettings
        for attribute in (QWebEngineSettings.JavascriptCanOpenWindows,
                          QWebEngineSettings.JavascriptCanAccessClipboard,
                          QWebEngineSettings.LocalContentCanAccessRemoteUrls,
                          QWebEngineSettings.ErrorPageEnabled):
            page.settings().setAttribute(attribute, False)
        self.setPage(page)
        self.channel = QWebChannel(page)
        self.bridge = OrdersBridge(owner)
        self.channel.registerObject("orders", self.bridge)
        page.setWebChannel(self.channel)
        self.loadFinished.connect(owner._glass_loaded)
        self.renderProcessTerminated.connect(lambda *_: owner._glass_failed())
        self.load(QUrl.fromLocalFile(str((ASSET_ROOT / "index.html").resolve())))


class FlexibleStack(QStackedWidget):
    # Hidden native pages can have large table minimums. They must not force
    # the responsive HTML orders page beyond the available monitor size.
    def minimumSizeHint(self):
        return QSize(0, 0)

    def sizeHint(self):
        return QSize(900, 500)


class MainWindow(EnterpriseWindow):
    def __init__(self, db, user, manager=None, tracker=None):
        self._glass = None
        self._glass_ready = False
        self._glass_painted = False
        self._glass_busy = False
        self._glass_last_state = ""
        self._web_rows = []
        self._web_row_indices = {}
        self._glass_error = False
        self._tab_frame = None
        super().__init__(db, user, manager, tracker)
        self._legacy_shell = self.centralWidget()
        self._legacy_shell.setObjectName("LiquidNativeShell")
        from .liquid_effects import apply_liquid_surface
        apply_liquid_surface(self._legacy_shell, self.ui_settings.theme)
        self._glass_stack = FlexibleStack(self.tabs)
        self._glass_stack.setObjectName("LiquidGlassStack")
        self._native_orders = self.tabs.widget(0)
        current = self.tabs.currentIndex()
        self.tabs.blockSignals(True)
        self.tabs.removeTab(0)
        self._glass_stack.addWidget(self._native_orders)
        self.tabs.insertTab(0, self._glass_stack, "Наряд")
        self.tabs.setCurrentIndex(current)
        self.tabs.blockSignals(False)
        self._unify_shell()
        self.tabs.tabBarClicked.connect(self._capture_tab_frame)
        self._glass_push_timer = QTimer(self)
        self._glass_push_timer.setSingleShot(True)
        self._glass_push_timer.setInterval(25)
        self._glass_push_timer.timeout.connect(self._publish_glass_state)
        self._glass = OrdersWebView(self)
        self._glass_stack.addWidget(self._glass)
        self._glass_stack.setCurrentWidget(self._glass)
        self.orders_table.report_model.modelReset.connect(self._glass_rows_changed)
        self.orders_table.itemSelectionChanged.connect(self._schedule_glass_state)
        history_model = self.info_users_list.model()
        for signal in (history_model.rowsInserted, history_model.rowsRemoved,
                       history_model.modelReset, history_model.dataChanged):
            signal.connect(self._schedule_glass_state)
        self.theme.toggled.connect(self._schedule_glass_state)
        self.zoom.valueChanged.connect(lambda *_:None if self.zoom.isSliderDown() else self._schedule_glass_state())
        self._glass_chrome_timer = QTimer(self)
        self._glass_chrome_timer.setInterval(500)
        self._glass_chrome_timer.timeout.connect(self._poll_glass_chrome)
        self._glass_chrome_timer.start()
        self._glass_rows_changed()
        self.setMinimumSize(640, 440)

    def _unify_shell(self):
        """One persistent title bar, scale toolbar and tab bar for all pages."""
        layout = self._legacy_shell.layout()
        layout.setSpacing(0)
        from .appearance_config import normalize_appearance
        fonts = normalize_appearance(self.ui_settings.appearance)["fonts"]
        title_size = max(fonts["window_title"]["size"], fonts["caption"]["size"])
        self.titlebar.setFixedHeight(max(47, round(title_size)+20))
        old_toolbar = next((w for w in self._legacy_shell.findChildren(QWidget)
                            if hasattr(w, "_widgets") and self.zoom in w.findChildren(QWidget)), None)
        bar = QWidget()
        bar.setObjectName("UnifiedScaleToolbar")
        bar.setFixedHeight(50)
        row = QHBoxLayout(bar)
        row.setContentsMargins(25, 0, 18, 0); row.setSpacing(16)
        label = QLabel("Масштаб:"); label.setFixedWidth(110); self.scale_caption=label
        row.addWidget(label)
        layout.removeWidget(self.zoom_message);row.addWidget(self.zoom_message,1)
        self.zoom.setMaximumWidth(480); self.zoom.setMinimumWidth(100)
        row.addWidget(self.zoom, 1)
        self.zoom_label.setFixedWidth(64); row.addWidget(self.zoom_label)
        self.fullscreen_hint_label.setStyleSheet("background:transparent;")
        self.fullscreen_hint_label.setText("Esc — для полноэкранного режима")
        row.addWidget(self.fullscreen_hint_label, 1)
        if old_toolbar is not None:
            index = layout.indexOf(old_toolbar)
            layout.removeWidget(old_toolbar); old_toolbar.hide()
        else: index = 1
        layout.insertWidget(max(1, index), bar)
        index = layout.indexOf(self.tabs)
        layout.removeWidget(self.tabs)
        workspace = QWidget()
        workspace.setObjectName("UnifiedWorkspace")
        body = QVBoxLayout(workspace); body.setSpacing(0); body.setContentsMargins(14, 0, 14, 12)
        body.addWidget(self.tabs)
        layout.insertWidget(index, workspace, 1)
        self.tabs.setTabText(6, "О приложении")
        self._ensure_tab_widths();self._update_zoom_mode()

    def _ensure_tab_widths(self):
        if not hasattr(self,"tabs"):return
        from .appearance import font_for
        from .appearance_config import normalize_appearance
        import json
        bar=self.tabs.tabBar();font=font_for("tabs",self.ui_settings.zoom,self.ui_settings.appearance)
        spec=normalize_appearance(self.ui_settings.appearance)["fonts"]["tabs"]
        scale=self.ui_settings.zoom/100;padding=round(22*scale);bar.setProperty("tabHorizontalPadding",padding)
        css=f'QTabBar{{font-family:{json.dumps(font.family())};font-size:{font.pixelSize()}px;font-weight:{spec["weight"]};font-style:{"italic" if spec["italic"] else "normal"};}}QTabBar::tab{{min-height:{max(30,font.pixelSize()+16)}px;padding:6px {padding}px;}}'
        if bar.styleSheet()!=css:bar.setStyleSheet(css)
        bar.setExpanding(False);bar.setElideMode(Qt.ElideNone);bar.setUsesScrollButtons(True);bar.updateGeometry()

    def set_appearance(self, appearance):
        super().set_appearance(appearance)
        self._schedule_glass_state()

    def _glass_rows_changed(self, *_):
        self._web_rows = []
        self._web_row_indices = {}
        for index, rec in enumerate(self.orders_table.report_model.rows):
            key = row_key(rec[0])
            self._web_row_indices[key] = index
            cells = [str(value or "") for value in rec[1:7]]
            cells[1] = cells[1].replace("-", ".")
            self._web_rows.append({"key": key, "cells": cells, "draft": bool(rec[7])})
        self._schedule_glass_state()

    def _schedule_glass_state(self, *_):
        timer = getattr(self, "_glass_push_timer", None)
        if timer is not None:
            timer.start()

    def _poll_glass_chrome(self):
        if self._glass is None or self._live_closed or not self._glass.isVisible():
            return
        current = (*self._glass_status(), self.orders_table.toolTip(),
                   self._notification_count, self.ui_settings.theme, self.ui_settings.zoom,
                   self.isMaximized(), self.isFullScreen(),
                   tuple((b.isEnabled(), b.isHidden()) for b in self._glass_buttons().values()))
        if current != getattr(self, "_glass_last_chrome", None):
            self._glass_last_chrome = current
            self._schedule_glass_state()

    def _glass_buttons(self):
        return {"create": self.create_order_btn, "edit": self.edit_order_btn,
                "export": self.export_order_btn, "delete": self.delete_draft_btn}

    def _glass_status(self):
        ok, milliseconds, message = getattr(self, "_last_ping", (False, 0.0, "Проверка..."))
        if ok:
            suffix = " · медленный ответ" if milliseconds > 300 else ""
            return "БД доступна" + suffix, f"Отклик базы: {milliseconds:.0f} мс. Обновить данные (F5)."
        if message in {"Проверка...", ""}:
            return "БД: проверка…", "Проверяется подключение к общей базе данных."
        return "БД недоступна", str(message)

    def _orders_allowed(self):
        return self.tabs.isTabEnabled(0) and self.can(Permission.ORDERS_VIEW)

    def glass_state(self):
        """Snapshot existing GUI models only; this method performs no DB reads."""
        allowed = self._orders_allowed()
        ref = self._selected_ref()
        status, status_tip = self._glass_status()
        filters = {}
        for name, combo in (("master", self.order_filter_master),
                            ("shift", self.order_filter_shift), ("department", self.order_filter_dep)):
            shift = name == "shift"
            filters[name] = {
                "value": source_text(combo) if shift else combo.currentData(),
                "options": [{"value": item_source(combo,i) if shift else combo.itemData(i),
                             "label": tr(combo.itemText(i))} for i in range(combo.count())]
            }
        filters["date"] = self.order_filter_date.text()
        filters["dateStart"] = self.order_filter_date.startDate().toString("yyyy-MM-dd")
        filters["dateEnd"] = self.order_filter_date.endDate().toString("yyyy-MM-dd")
        filters["today"] = QDate.currentDate().toString("yyyy-MM-dd")
        from .i18n import web_catalog
        accessible = allowed_workshops(self.user)
        return {
            "language": self.ui_settings.language, "translations": web_catalog(self.ui_settings.language),
            "columns": self.ui_settings.order_columns,
            "emptyMessage": tr("Для начала работы создайте наряд." if self.can(Permission.ORDERS_CREATE) else "Наряды пока не созданы."),
            "embedded": True, "currentTab": self.tabs.currentIndex(),
            "appearance": self.ui_settings.appearance,
            "theme": self.ui_settings.theme, "zoom": self.ui_settings.zoom,
            "username": self.user.username, "role": " · ".join(tr(role) for role in split_roles(self.user.role)),
            "workshop": tr(WORKSHOPS[self.workshop]), "allowed": allowed,
            "workshopKey": self.workshop,
            "topRestricted": self._orders_top_restricted(),
            "canFilter":self.can(Permission.ORDERS_FILTER),
            "canHistory":self.can(Permission.ORDERS_HISTORY),
            "workshops": [{"value": key, "label": tr(label), "enabled": key in accessible}
                          for key, label in WORKSHOPS.items()],
            "tabs": [{"label": self.tabs.tabText(i).replace(" ⍰", ""),
                      "enabled": self.tabs.isTabEnabled(i)} for i in range(self.tabs.count())],
            "filters": filters,
            "actions": {name: {"visible": not button.isHidden(),
                               "enabled": allowed and button.isEnabled() and not self._glass_busy}
                        for name, button in self._glass_buttons().items()},
            "rows": self._web_rows if allowed else [],
            "selected": row_key(ref) if ref is not None and allowed else None,
            "history": [self.info_users_list.item(i).text() for i in range(self.info_users_list.count())]
                       if allowed and self.can(Permission.ORDERS_HISTORY) else [],
            "busy": self._glass_busy,
            "status": status,
            "statusTip": self.orders_table.toolTip() or status_tip,
            "notifications": self._notification_count,
            "showNotifications": not self.titlebar.bell.isHidden(),
            "workshopEnabled": self.titlebar.badge.isEnabled(),
            "maximized": self.isMaximized() or self.isFullScreen(),
            "fullscreen": self.isFullScreen()
        }

    def _publish_glass_state(self, force=False):
        if not self._glass_ready or self._glass is None or self._live_closed:
            return
        encoded = json.dumps(self.glass_state(), ensure_ascii=False, separators=(",", ":"))
        if force or encoded != self._glass_last_state:
            self._glass_last_state = encoded
            self._glass.bridge.stateChanged.emit(encoded)

    def _retry_initial_state(self):
        if self._live_closed or self._glass_painted:
            self._initial_state_timer.stop();return
        self._initial_state_attempts+=1;self._publish_glass_state(force=True)
        if self._initial_state_attempts>=8:self._initial_state_timer.stop()

    def _glass_loaded(self, ok):
        if not ok:
            self._glass_failed()

    def _glass_failed(self):
        if self._live_closed or self._glass_error:
            return
        self._glass_error = True
        self._glass_ready = False
        self._glass_stack.setCurrentWidget(self._native_orders)
        QTimer.singleShot(0, lambda: QMessageBox.warning(
            self, "Отображение окна", "Не удалось загрузить стеклянное оформление. "
            "Открыт стандартный интерфейс. Проверьте установку PyQtWebEngine и файлы оформления."))

    def _select_glass_row(self, key):
        if key is None:
            self.orders_table.setCurrentCell(-1, -1)
            self.orders_table.clearSelection()
            return True
        if not isinstance(key, str) or key not in self._web_row_indices:
            return False
        index = self._web_row_indices[key]
        rows = self.orders_table.report_model.rows
        if index >= len(rows) or row_key(rows[index][0]) != key:
            return False
        if self.orders_table.currentRow() != index:
            self.orders_table.selectRow(index)
        return True

    def _glass_command(self, action, payload):
        if self._live_closed:
            return
        if action == "ready":
            self._glass_ready = True
            self._publish_glass_state(force=True)
            self._initial_state_attempts=0
            self._initial_state_timer=QTimer(self);self._initial_state_timer.setInterval(120);self._initial_state_timer.timeout.connect(self._retry_initial_state);self._initial_state_timer.start()
            return
        if action=="painted":
            self._glass_painted=True
            if hasattr(self,"_initial_state_timer"):self._initial_state_timer.stop()
            if self._glass is not None:self._glass.update()
            return
        if action not in ACTIONS or not isinstance(payload, dict):
            return
        if self._glass_busy and action not in {"minimize", "move", "resize"}:
            return
        native = action in {"create", "edit", "export", "delete", "open", "view", "date", "history"}
        if native:
            self._glass_busy = True
            self._publish_glass_state()
        try:
            self._execute_glass_command(action, payload)
        except (ValueError, TypeError, KeyError) as exc:
            log.warning("Rejected orders UI action %s: %s", action, exc)
        except Exception:
            log.exception("Orders UI action failed: %s", action)
            self._glass.bridge.message.emit("Не удалось выполнить действие. Повторите попытку.")
        finally:
            if native:
                self._glass_busy = False
            self._schedule_glass_state()

    def _execute_glass_command(self, action, data):
        if action in {"select", "filter", "date", "date_range", "create", "edit", "export", "delete", "open", "view", "history"}:
            if not self._orders_allowed() or not self.can(Permission.ORDERS_VIEW):
                return
        if action == "select":
            self._select_glass_row(data.get("key"))
        elif action == "filter":
            name = data.get("name")
            combo = {"master": self.order_filter_master, "shift": self.order_filter_shift,
                     "department": self.order_filter_dep}.get(name)
            if combo is None:
                return
            value = data.get("value")
            if name == "shift":
                index = combo.findText(str(value))
            else:
                if value is not None and (type(value) is not int):
                    return
                index = combo.findData(value)
            if index >= 0:
                combo.setCurrentIndex(index)
        elif action == "date":
            dialog = DateRangeDialog(self.order_filter_date.startDate(), self.order_filter_date.endDate(), self)
            if dialog.exec_() == QDialog.Accepted:
                self.order_filter_date.setDateRange(*dialog.selected_range())
        elif action == "date_range":
            start, end = data.get("start"), data.get("end")
            if not isinstance(start, str) or not isinstance(end, str) or len(start) != 10 or len(end) != 10:
                return
            first, last = QDate.fromString(start, "yyyy-MM-dd"), QDate.fromString(end, "yyyy-MM-dd")
            if first.isValid() and last.isValid():
                self.order_filter_date.setDateRange(first, last)
        elif action in {"edit", "export", "delete", "open", "view"}:
            # Commands carry a stable row handle, never a potentially stale index.
            if not self._select_glass_row(data.get("key")) or self._selected_ref() is None:
                return
            if action == "open":
                self._open_selected()
            elif action == "view":
                self.view_order()
            elif action == "edit" and self.can(Permission.ORDERS_EDIT) and self.edit_order_btn.isEnabled():
                self.edit_order()
            elif action == "export" and self.can(Permission.ORDERS_EXPORT) and self.export_order_btn.isEnabled():
                self.export_order()
            elif action == "delete" and self.delete_draft_btn.isEnabled() and not self.user.has_any_role(ACCOUNTING_ROLES):
                self.delete_selected_draft()
        elif action == "create" and self.can(Permission.ORDERS_CREATE):
            self.create_order()
        elif action == "history":
            index = data.get("index")
            if type(index) is int and 0 <= index < self.info_users_list.count():
                self._show_history_details(self.info_users_list.item(index))
        elif action == "tab":
            index = data.get("index")
            if type(index) is int and 0 <= index < self.tabs.count() and self.tabs.isTabEnabled(index):
                self._capture_tab_frame(index)
                self.tabs.setCurrentIndex(index)
        elif action == "columns":
            from .config import normalize_order_columns
            columns=normalize_order_columns(data.get("widths"))
            if columns:
                self.ui_settings.order_columns=columns;self.settings_store.save(self.ui_settings)
        elif action == "theme" and type(data.get("dark")) is bool:
            self.theme.setChecked(data["dark"])
        elif action == "zoom" and type(data.get("value")) is int:
            self.zoom.setValue(max(50, min(200, data["value"])))
        elif action == "refresh":
            self._sync_current_tab()
        elif action == "workshop" and self.titlebar.badge.isEnabled():
            key = data.get("key")
            if key is None:
                self.choose_workshop()
            elif isinstance(key, str) and key in allowed_workshops(self.user):
                self._switch_to_workshop(key)
        elif action == "notifications":
            self.show_notifications()
        elif action == "minimize":
            self.showMinimized()
        elif action == "maximize":
            self.titlebar.toggle_max()
        elif action == "close":
            self.close()  # existing confirmation and session cleanup
        elif action == "fullscreen":
            # Preserve the original repeat guard, native frame and animated hint.
            self.keyPressEvent(QKeyEvent(QEvent.KeyPress, Qt.Key_Escape, Qt.NoModifier))
        elif action == "move" and self.windowHandle() is not None:
            self.windowHandle().startSystemMove()
        elif action == "resize" and self.windowHandle() is not None:
            self.windowHandle().startSystemResize(Qt.RightEdge | Qt.BottomEdge)

    def _capture_tab_frame(self, index):
        self._tab_frame = None
        page = self.tabs.currentWidget()
        motion = getattr(self, "_window_motion", None)
        if (index >= 0 and index != self.tabs.currentIndex() and self.tabs.isTabEnabled(index)
                and page is not None and page.isVisible()
                and (motion is None or motion.animation is None)):
            self._tab_frame = (index, page.grab())

    def _tab_changed(self, index):
        frame, self._tab_frame = self._tab_frame, None
        effect = None
        if frame is not None and frame[0] == index:
            from .liquid_effects import transition_to
            effect = transition_to(self.tabs.widget(index), frame[1], hold=True)
        try:
            super()._tab_changed(index)
        finally:
            if effect is not None:
                effect.fade()
        if self._glass is not None:
            self._schedule_glass_state()

    def _show_fullscreen_feedback(self, entering):
        super()._show_fullscreen_feedback(entering)
        feedback = getattr(self, "_fullscreen_feedback", None)
        if feedback is not None:
            from .liquid_style import colors
            palette = colors(self.ui_settings.theme == "dark")
            feedback.setStyleSheet(
                "QFrame#FullscreenFeedback{background:transparent;"
                f"border:1px solid {palette['line']};border-radius:20px;}}"
                f"QLabel#FullscreenFeedbackText{{color:{palette['ink']};background:transparent;"
                "font-size:18px;font-weight:700;}"
                f"QLabel#FullscreenFeedbackHint{{color:{palette['muted']};background:transparent;"
                "font-size:12px;}"
            )
            from .heavy_ui import _RC4FullscreenIcon
            for icon in feedback.findChildren(_RC4FullscreenIcon):
                icon.setProperty("iconColor", palette["blue"].upper())
                icon.update()

    def choose_workshop(self):
        super().choose_workshop()
        if self._glass is not None and self._glass.isVisible() and self.workshop_menu.isVisible():
            self.workshop_menu.move(self.mapToGlobal(QPoint(max(12, self.width() - 290), 104)))

    def show_notifications(self):
        super().show_notifications()
        if self._glass is not None and self._glass.isVisible() and self.notification_popup is not None:
            self.notification_popup.move(self.mapToGlobal(QPoint(max(12, self.width() - 495), 108)))

    def changeEvent(self, event):
        super().changeEvent(event)
        motion = getattr(self, "_window_motion", None)
        if event.type() == QEvent.WindowStateChange and (motion is None or motion.animation is None):
            self._schedule_glass_state()

    def closeEvent(self, event):
        super().closeEvent(event)
        if event.isAccepted() and self._live_closed:
            self._glass_chrome_timer.stop()
            self._glass_push_timer.stop()
            self._glass_ready = False
