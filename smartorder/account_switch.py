"""Return to the original login dialog without restarting or reusing a session."""
from PyQt5 import sip
from PyQt5.QtCore import QObject, QTimer
from PyQt5.QtWidgets import QApplication, QDialog, QMessageBox


def open_workspace(app, manager, user):
    from .config import SettingsStore, local_state_dir
    from .context_help import offer_training
    from .glass_ui import MainWindow
    from .i18n import set_language
    from .workspace_ui import WorkshopLoadingDialog, reveal_after_first_frame
    from .workshops import allowed_workshops

    allowed=allowed_workshops(user)
    if not allowed:raise ValueError("У учётной записи нет доступных цехов.")
    try:workshop=(local_state_dir()/f"workshop_{user.id}.txt").read_text().strip()
    except OSError:workshop=allowed[0]
    if workshop not in allowed:workshop=allowed[0]
    set_language(SettingsStore(user.id,user.username).load().language)
    loading=WorkshopLoadingDialog(workshop);loading.show();app.processEvents()
    try:
        window=MainWindow(manager.database(workshop,user),user,manager=manager)
        app._smartorder_main_window=window
        window.showMaximized();loading.raise_()
        server=getattr(app,"_order_request_server",None)
        if server is not None:server.deliver()
        reveal_after_first_frame(window,loading,lambda:offer_training(window))
        return window
    except Exception:
        loading.close();loading.deleteLater();raise


class AccountController(QObject):
    def __init__(self, app, manager, window, login_factory=None, window_factory=None, quit_callback=None):
        super().__init__(app)
        from .heavy_ui import LoginDialog
        self.app,self.manager=app,manager
        self.login_factory=login_factory or LoginDialog
        self.window_factory=window_factory or open_workspace
        self.quit_callback=quit_callback or app.quit
        self.busy=False;self.login=None
        self.attach(window)

    def attach(self, window):
        self.window=window
        self.app._smartorder_main_window=window
        window.accountSwitchRequested.connect(self.switch)

    def switch(self):
        if self.busy or self.window is None or sip.isdeleted(self.window):return
        self.busy=True
        self.previous_quit=self.app.quitOnLastWindowClosed()
        self.app.setQuitOnLastWindowClosed(False)
        old=self.window
        tour=getattr(old,"_master_tour",None)
        if tour is not None and tour.running:tour.finish()
        self.app._smartorder_main_window=None
        confirmed=getattr(old,"_rc4_exit_confirmed",False)
        old._rc4_exit_confirmed=True
        if not old.close():
            old._rc4_exit_confirmed=confirmed
            self.app._smartorder_main_window=old
            self.busy=False;self.app.setQuitOnLastWindowClosed(self.previous_quit)
            return
        # closeEvent saves the old profile, stops live reads and closes its
        # session/visit. Login never inherits a parent, password or old model.
        self.window=None
        old.deleteLater()
        QTimer.singleShot(0,self.authenticate)

    def authenticate(self):
        while self.busy:
            login=self.login_factory(self.manager.auth)
            self.login=login;self.app._smartorder_login_dialog=login
            result=login.exec_();user=login.user
            password=getattr(login,"password_edit",None)
            if password is not None:password.clear()
            login.deleteLater();self.login=None;self.app._smartorder_login_dialog=None
            if result!=QDialog.Accepted or user is None:
                self.busy=False;self.app.setQuitOnLastWindowClosed(self.previous_quit)
                self.quit_callback();return
            try:
                window=self.window_factory(self.app,self.manager,user)
            except Exception as exc:
                QMessageBox.critical(None,"Смена аккаунта","Не удалось открыть рабочее пространство:\n"+str(exc))
                continue
            self.attach(window)
            self.busy=False
            self.app.setQuitOnLastWindowClosed(self.previous_quit)
