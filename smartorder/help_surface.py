"""Opaque, themed surfaces for help; never inherit glass window transparency."""
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor, QPalette


def opaque_help(widget, theme):
    dark=theme=="dark"
    base,paper,ink,muted,edge=("#192e46","#213c56","#e7f2ff","#b1c6df","#557492") if dark else ("#eef7ff","#ffffff","#102b50","#425f80","#b6d3ec")
    widget.setProperty("plainSurface",True)
    widget.setAttribute(Qt.WA_TranslucentBackground,False)
    widget.setAttribute(Qt.WA_NoSystemBackground,False)
    widget.setAutoFillBackground(True)
    palette=widget.palette()
    for role in (QPalette.Window,QPalette.Button):palette.setColor(role,QColor(base))
    for role in (QPalette.Base,QPalette.AlternateBase):palette.setColor(role,QColor(paper))
    for role in (QPalette.WindowText,QPalette.Text,QPalette.ButtonText):palette.setColor(role,QColor(ink))
    widget.setPalette(palette)
    widget.setStyleSheet(f'''
QDialog,QFrame#TrainingCard{{background:{base};color:{ink};border-radius:14px;}}
QLabel{{color:{ink};background:transparent;border:0;}}
QLabel#TrainingTitle{{font-size:22px;font-weight:700;}}
QLabel#TrainingKicker{{color:{muted};font-size:11px;}}
QTextBrowser{{background:{paper};color:{ink};border:1px solid {edge};border-radius:10px;padding:12px;}}
QPushButton{{background:{paper};color:{ink};border:1px solid {edge};border-radius:9px;padding:9px 14px;min-height:24px;}}
QPushButton:hover{{border-color:#168cf5;}}
QPushButton#PrimaryButton{{background:#087bfa;color:#ffffff;border-color:#168cf5;font-weight:700;}}
QPushButton:disabled{{color:{muted};}}
''')
    return ink


def center_dialog(dialog, owner, preferred_size=None):
    if preferred_size is None:dialog.adjustSize()
    else:dialog.resize(*preferred_size)
    dialog.move(owner.frameGeometry().center()-dialog.rect().center())
