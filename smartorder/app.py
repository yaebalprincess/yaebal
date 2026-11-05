from __future__ import annotations

import os
import sys
import traceback
import time
import threading
from pathlib import Path


def _prepare_windows_qt_dlls() -> None:
    """Prefer the Qt DLLs shipped with this Python environment.

    Corporate PCs often have another Qt5 installation in PATH (QGIS,
    Anaconda, vendor utilities, older SmartOrder builds).  Loading a foreign
    Qt5Core.dll produces the Windows error "procedure not found" before the
    application code starts.
    """
    if os.name != "nt" or getattr(sys, "frozen", False):
        return
    try:
        import PyQt5
        qt_bin = Path(PyQt5.__file__).resolve().parent / "Qt5" / "bin"
        if not qt_bin.is_dir():
            return
        # Python 3.8+ / Windows: explicit DLL search directory. Keep the
        # returned handle alive for the process lifetime.
        global _QT_DLL_DIR_HANDLE
        if hasattr(os, "add_dll_directory"):
            _QT_DLL_DIR_HANDLE = os.add_dll_directory(str(qt_bin))
        os.environ["PATH"] = str(qt_bin) + os.pathsep + os.environ.get("PATH", "")
    except Exception:
        pass


_QT_DLL_DIR_HANDLE = None
_prepare_windows_qt_dlls()

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication, QMessageBox, QSplashScreen
from PyQt5.QtGui import QIcon, QColor, QFont, QPainter, QPen, QPixmap

from .config import APP_NAME, APP_VERSION, SettingsStore, database_path, base_database_path, local_logs_dir, resource_path
from .db import Database
from .heavy_styles import apply_apple_design
from .security import SessionUser, DEFAULT_ROLE_PERMISSIONS
from .update_manager import PatchError, apply_pending_update

_MUTEX_HANDLE = None


def _create_startup_splash(theme: str = "light"):
    """Small branded splash used only while synchronous startup work runs."""
    dark = str(theme).lower() == "dark"
    width, height = 520, 210
    pixmap = QPixmap(width, height)
    pixmap.fill(QColor("#1C1C1E" if dark else "#F5F5F7"))
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing, True)
    painter.setPen(QPen(QColor("#3A3A3C" if dark else "#D1D1D6"), 1))
    painter.setBrush(QColor("#242426" if dark else "#FFFFFF"))
    painter.drawRoundedRect(1, 1, width - 2, height - 2, 18, 18)

    logo = None
    for name in ("smartorder_logo_icon_light.png", "smartorder_logo_icon.png", "smartorder_app_icon.ico"):
        try:
            path = resource_path(name)
            if path.exists():
                candidate = QPixmap(str(path))
                if not candidate.isNull():
                    logo = candidate.scaled(78, 78, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                    break
        except Exception:
            pass
    if logo is not None:
        painter.drawPixmap(34, 28, logo)

    painter.setPen(QColor("#0A84FF" if dark else "#007AFF"))
    title_font = QFont()
    title_font.setPointSize(22)
    title_font.setBold(True)
    painter.setFont(title_font)
    painter.drawText(132, 48, 350, 38, Qt.AlignLeft | Qt.AlignVCenter, "SmartOrder")

    painter.setPen(QColor("#F5F5F7" if dark else "#1D1D1F"))
    sub_font = QFont()
    sub_font.setPointSize(11)
    sub_font.setBold(True)
    painter.setFont(sub_font)
    painter.drawText(132, 82, 350, 30, Qt.AlignLeft | Qt.AlignVCenter, "Формирование нарядов на сдельную работу")

    painter.setPen(QColor("#98989D" if dark else "#6E6E73"))
    detail_font = QFont()
    detail_font.setPointSize(9)
    painter.setFont(detail_font)
    painter.drawText(34, 125, 452, 30, Qt.AlignLeft | Qt.AlignVCenter, "Подготовка рабочего пространства")
    painter.end()

    splash = QSplashScreen(pixmap, Qt.WindowStaysOnTopHint)
    splash.setObjectName("SmartOrderStartupSplash")
    splash._smartorder_status_color = QColor("#F5F5F7" if dark else "#1D1D1F")
    return splash


def _show_splash_status(splash, app, text: str) -> None:
    if splash is None:
        return
    try:
        splash.show()
        splash.showMessage(
            str(text),
            Qt.AlignHCenter | Qt.AlignBottom,
            getattr(splash, "_smartorder_status_color", QColor("#1D1D1F")),
        )
        app.processEvents()
    except Exception:
        pass


def single_instance_guard() -> bool:
    global _MUTEX_HANDLE
    if os.name != "nt":
        return True
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p]
        kernel32.CreateMutexW.restype = ctypes.c_void_p
        # Local = one process per Windows user/session, not one process for entire terminal server.
        handle = kernel32.CreateMutexW(None, False, "Local\\SmartOrder_TMB_v2")
        if kernel32.GetLastError() == 183:
            ctypes.windll.user32.MessageBoxW(None, "Программа уже запущена", APP_NAME, 0x40)
            return False
        _MUTEX_HANDLE = handle
    except Exception:
        pass
    return True


def install_exception_hook():
    old = sys.excepthook
    def hook(exc_type, exc_value, exc_tb):
        try:
            path = local_logs_dir() / "crash.log"
            with path.open("a", encoding="utf-8") as fh:
                fh.write("\n" + "="*60 + "\n")
                fh.write(f"SmartOrder {APP_VERSION}\nDB: {database_path()}\n")
                traceback.print_exception(exc_type, exc_value, exc_tb, file=fh)
        finally:
            old(exc_type, exc_value, exc_tb)
    sys.excepthook = hook


def main(boot_started: float | None = None) -> int:
    boot_started = boot_started if boot_started is not None else time.perf_counter()
    def mark(label: str) -> None:
        try:
            elapsed = (time.perf_counter() - boot_started) * 1000.0
            with (local_logs_dir() / "startup.log").open("a", encoding="utf-8") as fh:
                from datetime import datetime
                fh.write(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | {elapsed:.1f} ms | {label}\n")
        except Exception:
            pass

    # Apply files staged by the administrator before importing the UI. The
    # updater only handles application payloads; shared SQLite files are never
    # part of this operation.
    try:
        apply_pending_update()
    except (PatchError, OSError, ValueError) as exc:
        try:
            (local_logs_dir() / "update.log").write_text(
                f"SmartOrder update was not applied: {exc}\n", encoding="utf-8"
            )
        except Exception:
            pass
    install_exception_hook()
    mark("app-module-ready")
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    # Chromium shares OpenGL contexts with the existing Qt desktop windows.
    # This must be configured before QApplication is constructed.
    QApplication.setAttribute(Qt.AA_ShareOpenGLContexts, True)
    QApplication.setAttribute(Qt.AA_DontUseNativeDialogs, True)
    app = QApplication(sys.argv)
    from .open_requests import forward_to_running, OpenRequestServer
    order_file = next((arg for arg in sys.argv[1:] if str(arg).lower().endswith('.sorder')),None)
    if forward_to_running(order_file):return 0
    if not single_instance_guard():return 0
    app._order_request_server = OpenRequestServer(app)
    if order_file:app._order_request_server.queue.append(order_file)
    mark("qt-application-ready")
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)
    app.setStyle("Fusion")
    try:
        startup_settings = SettingsStore().load()
        startup_theme = startup_settings.theme
        app._liquid_appearance = startup_settings.appearance
    except Exception:
        startup_theme = "light"
    apply_apple_design(None, startup_theme, 100)
    splash = _create_startup_splash(startup_theme)
    _show_splash_status(splash, app, "Запуск SmartOrder…")
    mark("splash-visible")

    for icon_name in ("smartorder_app_icon.ico", "smartorder_logo_icon.ico", "smartorder_logo_icon.png"):
        try:
            icon_path = resource_path(icon_name)
            if icon_path.exists():
                app.setWindowIcon(QIcon(str(icon_path)))
                break
        except Exception:
            pass

    # Startup I/O and Heavy UI import run in parallel. Database owns no persistent
    # SQLite connection, therefore creating the repository in this worker is safe.
    startup_box: dict[str, object] = {}

    def _prepare_database() -> None:
        try:
            from .workshops import WorkshopManager
            manager = WorkshopManager(Database(base_database_path()))
            startup_box["manager"] = manager
            startup_box["db"] = manager.auth
            startup_box["auth"] = manager.auth.startup_bundle()
        except BaseException as exc:
            startup_box["error"] = exc

    _show_splash_status(splash, app, "Подключение к общей базе и загрузка интерфейса…")
    db_thread = threading.Thread(target=_prepare_database, name="SmartOrderStartupDB", daemon=True)
    db_thread.start()

    from .heavy_ui import FirstAdminDialog, LoginDialog, MainWindow, install_motion_effects
    from .glass_ui import MainWindow
    mark("heavy-ui-imported")
    install_motion_effects(app)

    db_thread.join()
    if "error" in startup_box:
        exc = startup_box["error"]
        try:
            splash.hide()
        except Exception:
            pass
        QMessageBox.critical(
            None,
            "SmartOrder — база данных",
            f"Не удалось открыть общую базу:\n{database_path()}\n\n{exc}",
        )
        return 3

    db = startup_box["db"]
    has_users, access_enabled = startup_box["auth"]
    mark("database-and-startup-data-ready")

    if not has_users:
        try:
            splash.hide()
        except Exception:
            pass
        first = FirstAdminDialog(db)
        if first.exec_() != first.Accepted:
            return 0

    if access_enabled:
        try:
            splash.hide()
        except Exception:
            pass
        mark("login-dialog-opening")
        login = LoginDialog(db)
        if login.exec_() != login.Accepted or login.user is None:
            return 0
        session_user = login.user
        mark("login-accepted")
        _show_splash_status(splash, app, "Загрузка рабочего окна…")
    else:
        session_user = SessionUser(
            id=0,
            username="Система",
            role="Администратор",
            permissions=frozenset(DEFAULT_ROLE_PERMISSIONS.get("Администратор", set())),
        )
        mark("login-bypassed")
        _show_splash_status(splash, app, "Загрузка рабочего окна…")

    from .workshops import allowed_workshops
    from .config import local_state_dir
    from .workspace_ui import WorkshopLoadingDialog
    from .i18n import set_language
    allowed=allowed_workshops(session_user)
    try:workshop=(local_state_dir()/f"workshop_{session_user.id}.txt").read_text().strip()
    except OSError:workshop=allowed[0]
    if workshop not in allowed:workshop=allowed[0]
    set_language(SettingsStore(session_user.id,session_user.username).load().language)
    splash.hide()
    workshop_loading=WorkshopLoadingDialog(workshop)
    workshop_loading.show();app.processEvents()
    window = MainWindow(startup_box["manager"].database(workshop,session_user), session_user, manager=startup_box["manager"])
    workshop_loading.close();workshop_loading.deleteLater()
    app._smartorder_main_window = window
    mark("main-window-constructed")
    window.showMaximized()
    app._order_request_server.deliver()
    app.processEvents()
    try:
        splash.finish(window)
    except Exception:
        try:
            splash.hide()
        except Exception:
            pass
    mark("main-window-shown")

    # Retention maintenance is deliberately outside the startup critical path.
    # It runs in a daemon thread after the UI is already usable, and the DB
    # method itself has a once-per-day guard shared by all clients.
    def _retention_loop():
        waiter = threading.Event()
        while True:
            try:
                # Each workspace retains its own production history independently.
                with window.workshop_manager._lock:
                    databases = list(window.workshop_manager._databases.values())
                stats = {}
                for production_db in databases:
                    stats = production_db.run_retention_maintenance()
                if not stats.get("skipped"):
                    mark(
                        "retention-maintenance:"
                        f"orders={stats.get('orders', 0)};"
                        f"employees={stats.get('employees', 0)};"
                        f"departments={stats.get('departments', 0)}"
                    )
            except Exception:
                try:
                    with (local_logs_dir() / "retention.log").open("a", encoding="utf-8") as fh:
                        from datetime import datetime
                        fh.write(datetime.now().strftime("%Y-%m-%d %H:%M:%S") + " | " + traceback.format_exc() + "\n")
                except Exception:
                    pass
            waiter.wait(6 * 60 * 60)

    threading.Thread(target=_retention_loop, name="SmartOrderRetention", daemon=True).start()
    return app.exec_()


if __name__ == "__main__":
    raise SystemExit(main())
