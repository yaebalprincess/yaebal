"""Per-Windows-user local IPC: double-click opens in the existing logged-in app."""
import getpass
import hashlib
import json
import os
from pathlib import Path
from PyQt5.QtCore import QObject
from PyQt5.QtNetwork import QLocalServer, QLocalSocket
from PyQt5 import sip


def server_name():
    identity = getpass.getuser()
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes
        session = wintypes.DWORD()
        ctypes.windll.kernel32.ProcessIdToSessionId(os.getpid(),ctypes.byref(session))
        identity += "|"+os.environ.get("USERDOMAIN","")+"|"+str(session.value)
    return "SmartOrderOpen_" + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24]


def forward_to_running(path=None):
    socket = QLocalSocket()
    socket.connectToServer(server_name())
    if not socket.waitForConnected(400):return False
    request = json.dumps({"path":str(path) if path else None},ensure_ascii=False).encode("utf-8") + b"\n"
    socket.write(request)
    if not socket.waitForBytesWritten(400):return False
    accepted = socket.waitForReadyRead(1000) and bytes(socket.readAll()) == b"accepted\n"
    socket.disconnectFromServer()
    return bool(accepted)


class OpenRequestServer(QObject):
    def __init__(self, app):
        super().__init__(app)
        self.app, self.queue, self.sockets = app, [], set()
        self.server = QLocalServer(self)
        self.server.setSocketOptions(QLocalServer.UserAccessOption)
        QLocalServer.removeServer(server_name())
        if not self.server.listen(server_name()):raise RuntimeError("Не удалось открыть канал нарядов")
        self.server.newConnection.connect(self._connect)

    def _connect(self):
        if sip.isdeleted(self):return
        while self.server.hasPendingConnections():
            socket = self.server.nextPendingConnection()
            self.sockets.add(socket)
            socket.readyRead.connect(lambda s=socket:self._read(s))
            socket.disconnected.connect(lambda s=socket:self._remove(s))
            self._read(socket)

    def _remove(self,socket):
        if sip.isdeleted(self):return
        self.sockets.discard(socket)
        socket.deleteLater()

    def _read(self,socket):
        if sip.isdeleted(self) or sip.isdeleted(socket):return
        if socket.bytesAvailable()>32768:socket.abort();return
        if not socket.canReadLine():return
        try:
            request = json.loads(bytes(socket.readLine()).decode("utf-8"))
            path = request.get("path")
            if path is not None and (not isinstance(path,str) or len(path)>16000 or Path(path).suffix.casefold()!=".sorder"):
                raise ValueError("Некорректный путь наряда")
            socket.write(b"accepted\n");socket.flush()
            self.queue.append(path)
            self.deliver()
        except (ValueError,TypeError,AttributeError):socket.abort()

    def deliver(self):
        if sip.isdeleted(self):return
        from PyQt5.QtCore import QTimer
        from PyQt5.QtWidgets import QApplication
        window = getattr(self.app,"_smartorder_main_window",None)
        if window is None or getattr(window,"_file_loading",False) or QApplication.activeModalWidget() is not None:
            QTimer.singleShot(250,self.deliver);return
        window.showNormal() if window.isMinimized() else None
        window.raise_();window.activateWindow()
        if self.queue:
            path = self.queue.pop(0)
            if path:window.open_order_file(path)
        if self.queue:QTimer.singleShot(250,self.deliver)
