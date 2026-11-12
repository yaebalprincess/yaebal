"""Two equal actions inside the original export button boundary."""
from PyQt5.QtCore import QEvent
from PyQt5.QtWidgets import QFrame, QHBoxLayout, QPushButton

from .i18n import tr


class ExportActions(QFrame):
    def __init__(self, excel_button, print_callback, parent=None):
        super().__init__(parent)
        self.setObjectName("OrderExportActions")
        self.excel = excel_button
        self.excel.setObjectName("ExportExcelHalf")
        self.excel.setText(tr("Выгрузить в Excel"))
        self.print = QPushButton(tr("Прямая печать"), self)
        self.print.setObjectName("DirectPrintHalf")
        self.print.clicked.connect(print_callback)
        self.print.setEnabled(self.excel.isEnabled())
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)
        row.addWidget(self.excel, 1)
        row.addWidget(self.print, 1)
        self.setStyleSheet('''
QFrame#OrderExportActions{border:1px solid rgba(102,148,196,95);border-radius:9px;background:rgba(200,230,255,28);}
QPushButton#ExportExcelHalf,QPushButton#DirectPrintHalf{border:0;background:transparent;min-width:0;padding:6px 9px;}
QPushButton#ExportExcelHalf{border-right:1px solid rgba(102,148,196,95);border-top-right-radius:0;border-bottom-right-radius:0;}
QPushButton#DirectPrintHalf{border-top-left-radius:0;border-bottom-left-radius:0;}
QPushButton#ExportExcelHalf:hover,QPushButton#DirectPrintHalf:hover{background:rgba(75,155,225,36);}
''')
        self.excel.installEventFilter(self)

    def eventFilter(self, watched, event):
        if event.type() == QEvent.EnabledChange:
            self.print.setEnabled(self.excel.isEnabled())
        return False
