"""Open the real orders window against an isolated temporary database.

Run from the project root: python tools/preview_liquid_glass.py
No production databases or saved user preferences are accessed.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main():
    parser = argparse.ArgumentParser(description="Предпросмотр окна Smart Order Liquid Glass")
    parser.add_argument("--screenshot", type=Path)
    parser.add_argument("--pdf", type=Path, help="Снимок HTML-страницы через Chromium PDF renderer")
    parser.add_argument("--width", type=int, default=1727)
    parser.add_argument("--height", type=int, default=910)
    parser.add_argument("--zoom", type=int, default=100)
    parser.add_argument("--theme", choices=["light", "dark"], default="light")
    parser.add_argument("--language",choices=["ru","en","es","kk","fr","de","ja","tt"],default="ru")
    parser.add_argument("--tab", choices=["orders", "catalog", "employees", "admin", "analytics", "personalization", "about"], default="orders")
    parser.add_argument("--role",choices=["Администратор","Экономист","Бухгалтер"],default="Администратор")
    parser.add_argument("--dialog", choices=["create", "calendar", "employees", "works", "news", "backup", "user"], help="Открыть вложенное окно")
    parser.add_argument("--popup", choices=["master", "shift", "department", "workshop", "date"], help="Открыть стеклянную панель в снимке")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="SmartOrderGlass-") as folder:
        root = Path(folder)
        os.environ["LOCALAPPDATA"] = str(root / "local")
        os.environ["SMARTORDER_NETWORK_ROOT"] = str(root / "shared")
        from PyQt5.QtCore import QEvent, QTimer, Qt
        from PyQt5.QtWidgets import QApplication
        QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
        QApplication.setAttribute(Qt.AA_ShareOpenGLContexts, True)
        QApplication.setAttribute(Qt.AA_DontUseNativeDialogs, True)
        from smartorder.glass_ui import MainWindow
        from smartorder.config import SettingsStore, UiSettings
        from smartorder.db import Database
        from smartorder.workshops import WorkshopManager
        app = QApplication(sys.argv[:1])
        app.setStyle("Fusion")
        SettingsStore().save(UiSettings(args.theme, max(50, min(200, args.zoom)), language=args.language))
        db = Database(root / "shared" / "work_orders.db")
        db.create_first_admin("admin", "preview-only-password")
        manager = WorkshopManager(db, db.path.parent)
        user = manager.auth.authenticate("admin", "preview-only-password")
        if args.role!="Администратор":
            manager.auth.add_user(user,"preview-user","preview-only-password",args.role)
            user=manager.auth.authenticate("preview-user","preview-only-password")
        SettingsStore(user.id, user.username).save(UiSettings(args.theme, max(50, min(200, args.zoom)), language=args.language))
        window = MainWindow(db, user, manager)
        if args.screenshot or args.pdf:
            window.resize(args.width, args.height)
            window.show()
        else:
            window.showMaximized()
        if args.screenshot or args.pdf:
            timer = QTimer(window)
            timer.setInterval(100)
            attempts = 0

            def capture():
                nonlocal attempts
                attempts += 1
                if window._glass_ready and not window._orders_running:
                    timer.stop()

                    def save():
                        if args.pdf:
                            from PyQt5.QtCore import QMarginsF, QSizeF
                            from PyQt5.QtGui import QPageLayout, QPageSize
                            from PyQt5.QtWebEngineWidgets import QWebEngineSettings
                            window._glass.settings().setAttribute(QWebEngineSettings.PrintElementBackgrounds, True)
                            size = QPageSize(QSizeF(args.width * .75, args.height * .75), QPageSize.Point)
                            layout = QPageLayout(size, QPageLayout.Portrait, QMarginsF(0, 0, 0, 0), QPageLayout.Point)
                            def printed(data):
                                args.pdf.parent.mkdir(parents=True, exist_ok=True)
                                args.pdf.write_bytes(bytes(data))
                                print(str(args.pdf.resolve()), flush=True)
                                window._rc4_exit_confirmed = True
                                window.close()
                                app.quit()
                            window._glass.page().printToPdf(printed, layout)
                            return
                        args.screenshot.parent.mkdir(parents=True, exist_ok=True)
                        target = getattr(window, "_preview_dialog", None) or window
                        if not target.grab().save(str(args.screenshot)):
                            raise RuntimeError("Не удалось сохранить снимок окна")
                        print(str(args.screenshot.resolve()), flush=True)
                        if getattr(window, "_preview_dialog", None) is not None:
                            window._preview_dialog.close()
                            window._preview_dialog.deleteLater()
                        window._rc4_exit_confirmed = True
                        window.close()
                        app.quit()
                    def prepare_capture():
                        if args.tab != "orders":
                            window.tabs.setCurrentIndex(["orders", "catalog", "employees", "admin", "analytics", "personalization", "about"].index(args.tab))
                        if args.dialog:
                            from smartorder.heavy_ui import WorkOrderDialog, DateRangeDialog, EmployeeSelectionDialog, WorkSelectionDialog
                            from PyQt5.QtCore import QDate
                            if args.dialog == "create":
                                dialog = WorkOrderDialog(window.db, window.user, parent=window)
                            elif args.dialog == "user":
                                from smartorder.account_ui import AccountDialog
                                dialog=AccountDialog("new-user","Экономист",parent=window)
                            elif args.dialog == "calendar":
                                dialog = DateRangeDialog(QDate.currentDate(), QDate.currentDate(), window)
                            elif args.dialog == "employees":
                                dialog = EmployeeSelectionDialog(window.db, window)
                            elif args.dialog == "news":
                                from smartorder.news_ui import NewsDialog
                                dialog = NewsDialog(window, root / "preview-news.txt", prefix="Smart Order · Liquid Glass v7\nИндивидуальные права, отложенная активация и синхронизация персонализации.")
                            elif args.dialog == "backup":
                                from PyQt5.QtWidgets import QMessageBox
                                dialog = QMessageBox(QMessageBox.Information, "Резервная копия", "Создана резервная копия\nНаряды и история изменений сохранены.", QMessageBox.Ok, window)
                            else:
                                dialog = WorkSelectionDialog(window.db, window)
                            window._preview_dialog = dialog
                            dialog.show()
                            if args.screenshot:
                                dialog.setWindowState(Qt.WindowNoState)
                                if args.dialog == "create": dialog.resize(args.width, args.height)
                            dialog.move(window.frameGeometry().center() - dialog.rect().center())
                            QTimer.singleShot(650, save)
                            return
                        if args.popup:
                            identifier = {"date":"date", "workshop":"account"}.get(args.popup, args.popup + "-trigger")
                            window._glass.page().runJavaScript(
                                "document.getElementById('" + identifier + "').click()",
                                lambda _: QTimer.singleShot(250, save))
                        else:
                            QTimer.singleShot(650, save)
                    QTimer.singleShot(1000, prepare_capture)
                elif attempts > 150 or window._glass_error:
                    print("Окно не загрузилось", file=sys.stderr, flush=True)
                    app.exit(1)
            timer.timeout.connect(capture)
            timer.start()
        result = app.exec_()
        window._rc4_exit_confirmed = True
        window.close()
        window.deleteLater()
        app.sendPostedEvents(None, QEvent.DeferredDelete)
        app.processEvents()
        return result


if __name__ == "__main__":
    raise SystemExit(main())
