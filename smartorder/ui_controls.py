"""Small reusable controls; large reports render cells only when visible."""
from PyQt5.QtCore import Qt, QAbstractTableModel, QModelIndex, QSortFilterProxyModel, QEvent, QTimer, pyqtSignal
from PyQt5.QtGui import QColor, QPalette, QBrush, QFontMetrics
from PyQt5.QtWidgets import (QComboBox, QFrame, QVBoxLayout, QLineEdit, QListView,
    QTableView, QTableWidgetItem, QAbstractItemView, QHeaderView, QApplication)


class SearchComboBox(QComboBox):
    def showPopup(self):
        if not hasattr(self, "search_popup"):
            self.search_popup = QFrame(self, Qt.Popup | Qt.FramelessWindowHint)
            self.search_popup.setObjectName("SearchComboPopup")
            layout = QVBoxLayout(self.search_popup)
            layout.setContentsMargins(8, 8, 8, 8)
            self.search = QLineEdit(self.search_popup)
            self.search.setPlaceholderText("Поиск в списке…")
            layout.addWidget(self.search)
            self.search_view = QListView(self.search_popup)
            self.search_view.setEditTriggers(QAbstractItemView.NoEditTriggers)
            self.proxy = QSortFilterProxyModel(self.search_popup)
            self.proxy.setSourceModel(self.model())
            self.proxy.setFilterCaseSensitivity(Qt.CaseInsensitive)
            self.search_view.setModel(self.proxy)
            layout.addWidget(self.search_view)
            self.search.textChanged.connect(self.proxy.setFilterFixedString)
            self.search_view.clicked.connect(self._choose)
            self.search.installEventFilter(self)
            self.search_view.installEventFilter(self)
        dark = self.window().property("theme") == "dark"
        bg, fg, border = ("#161F32", "#E8EEF9", "#3A4B65") if dark else ("#FFFFFF", "#192B45", "#D1DAE7")
        pal = self.search_popup.palette()
        for role, color in ((QPalette.Window, bg), (QPalette.Base, bg), (QPalette.Text, fg), (QPalette.WindowText, fg)):
            pal.setColor(role, QColor(color))
        self.search_popup.setPalette(pal)
        self.search_popup.setAutoFillBackground(True)
        self.search_popup.setStyleSheet(f"QFrame#SearchComboPopup{{background:{bg};border:1px solid {border};border-radius:8px;}} QLineEdit,QListView{{background:{bg};color:{fg};border:1px solid {border};font-size:14px;}} QLineEdit{{padding:7px;}} QListView::item{{padding:8px;}} QListView::item:selected{{background:#285C84;color:white;}}")
        from .liquid_effects import style_popup
        style_popup(self.search_popup, "dark" if dark else "light")
        self.search.clear()
        self.proxy.invalidateFilter()
        index = self.proxy.mapFromSource(self.model().index(self.currentIndex(), self.modelColumn()))
        self.search_view.setCurrentIndex(index)
        self.search_popup.resize(max(360, min(650, self.width() + 200)), 350)
        point = self.mapToGlobal(self.rect().bottomLeft())
        screen = QApplication.screenAt(point) or QApplication.primaryScreen()
        area = screen.availableGeometry()
        point.setX(max(area.left(), min(point.x(), area.right() - self.search_popup.width())))
        if point.y() + self.search_popup.height() > area.bottom():
            point.setY(self.mapToGlobal(self.rect().topLeft()).y() - self.search_popup.height())
        self.search_popup.move(point)
        self.search_popup.show()
        self.search.setFocus()

    def hidePopup(self):
        if hasattr(self, "search_popup"):
            self.search_popup.hide()
        super().hidePopup()

    def _choose(self, index):
        if index.isValid():
            source = self.proxy.mapToSource(index)
            self.setCurrentIndex(source.row())
            self.activated.emit(source.row())
            self.hidePopup()

    def eventFilter(self, obj, event):
        if event.type() == QEvent.KeyPress:
            if event.key() == Qt.Key_Escape:
                self.hidePopup()
                return True
            if event.key() in (Qt.Key_Return, Qt.Key_Enter):
                current = self.search_view.currentIndex()
                if not current.isValid():
                    current = self.proxy.index(0, 0)
                self._choose(current)
                return True
            if obj is self.search and event.key() in (Qt.Key_Down, Qt.Key_Up):
                self.search_view.setFocus()
                self.search_view.setCurrentIndex(self.proxy.index(0, 0))
                return True
        return super().eventFilter(obj, event)


def display_value(key, value):
    if key.endswith("seconds") and isinstance(value, (float, int)):
        value = max(0, int(value))
        return f"{value//3600:02}:{value//60%60:02}:{value%60:02}"
    if isinstance(value, (float, int)):
        return f"{value:,.2f}".replace(",", " ").rstrip("0").rstrip(".")
    return str(value)


class ReportModel(QAbstractTableModel):
    def __init__(self, columns, parent):
        super().__init__(parent)
        self.columns, self.rows = columns, []

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.columns)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        row = self.rows[index.row()]
        if role == Qt.UserRole:
            return row
        if role in (Qt.DisplayRole, Qt.ToolTipRole):
            key = self.columns[index.column()][0]
            return display_value(key, row.get(key, ""))

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            from .i18n import tr
            return tr(self.columns[section][1])

    def set_rows(self, rows):
        self.beginResetModel()
        self.rows = rows
        self.endResetModel()


class ReportTable(QTableView):
    itemDoubleClicked = pyqtSignal(object)

    def __init__(self, columns):
        super().__init__()
        self.report_model = ReportModel(columns, self)
        self.setModel(self.report_model)
        self.setProperty("columns", columns)
        self.setAlternatingRowColors(True)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setEditTriggers(QAbstractItemView.NoEditTriggers)
        # Keep labels on one line at every application zoom.  Qt's default
        # word wrapping can turn a long master/department name into a tall
        # cell and make adjacent rows appear to overlap when the global font
        # is enlarged.  Eliding the tail preserves row geometry and keeps the
        # full value available through the existing tooltip role.
        self.setWordWrap(False)
        self.setTextElideMode(Qt.ElideRight)
        self.verticalHeader().hide()
        self.verticalHeader().setDefaultSectionSize(36)
        self.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.horizontalHeader().setStretchLastSection(True)
        self.horizontalHeader().setTextElideMode(Qt.ElideRight)
        self.setMinimumHeight(290)
        for i, (_, label) in enumerate(columns):
            self.setColumnWidth(i, max(125, min(285, len(label) * 8 + 26)))
        self.doubleClicked.connect(lambda index: self.itemDoubleClicked.emit(self.item(index.row(), index.column())))

    def rowCount(self):
        return self.report_model.rowCount()

    def columnCount(self):
        return self.report_model.columnCount()

    def horizontalHeaderItem(self, column):
        return QTableWidgetItem(self.report_model.columns[column][1])

    def item(self, row, column):
        index = self.report_model.index(row, column)
        if not index.isValid():
            return None
        item = QTableWidgetItem(index.data())
        item.setData(Qt.UserRole, index.data(Qt.UserRole))
        return item


class OrderModel(ReportModel):
    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():return None
        rec=self.rows[index.row()]
        if role in (Qt.DisplayRole,Qt.ToolTipRole):
            value=rec[index.column()+1]
            return str(value).replace('-', '.') if index.column()==1 else str(value)
        if role==Qt.UserRole:return rec[0]
        if role==Qt.ForegroundRole and rec[7]:return QBrush(QColor('#FF9500'))


class OrderCell(QTableWidgetItem):
    def __init__(self,text,row,column,ref):
        super().__init__(text)
        self._row,self._column=row,column
        self.setData(Qt.UserRole,ref)
    def row(self):return self._row
    def column(self):return self._column


class OrderListView(ReportTable):
    itemSelectionChanged=pyqtSignal()
    def __init__(self,columns):
        super().__init__(columns)
        self.report_model=OrderModel(columns,self);self.setModel(self.report_model)
        self.setObjectName('OrdersLiveTable')
        self.setStyleSheet('QTableView{background:#FFFFFF;color:#1D1D1F;alternate-background-color:#F5F5F7;gridline-color:#D1D1D6;border:1px solid #C8C8CE;border-radius:12px;} QTableView[theme="dark"]{background:#2C2C2E;color:#F5F5F7;alternate-background-color:#3A3A3C;gridline-color:#4B4B4E;border-color:#4B4B4E;} QTableView::item:selected{background:#285C84;color:white;}')
        self.selectionModel().selectionChanged.connect(lambda *_:self.itemSelectionChanged.emit())
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setMinimumHeight(540)
        self.verticalHeader().setDefaultSectionSize(44)
        # The previous hidden QTableWidget had not been laid out yet: copying
        # its widths left five narrow columns and one enormous last column.
        self.horizontalHeader().setStretchLastSection(False)
        self.horizontalHeader().setResizeContentsPrecision(200)
        self._content_widths=None
        self._width_timer=QTimer(self);self._width_timer.setSingleShot(True)
        self._width_timer.timeout.connect(self._fit_columns)
        self.report_model.modelReset.connect(self._invalidate_widths)
        self._invalidate_widths()

    def _invalidate_widths(self):
        self._content_widths=None
        self._width_timer.start(0)

    def _fit_columns(self):
        if self._content_widths is None:
            metrics=QFontMetrics(self.horizontalHeader().font())
            defaults=(72,132,118,240,270,165)
            maximums=(110,185,170,360,420,225)
            # Keep the identifier/date/shift columns compact. Long master or
            # department names are elided in the cell instead of expanding
            # the whole page and hiding the registration-date column.
            scale=min(1.35,max(0.80,QFontMetrics(self.font()).height()/16.))
            self._content_widths=[min(maximums[i],max(round(defaults[i]*scale),metrics.horizontalAdvance(label)+28))
                for i,(_,label) in enumerate(self.report_model.columns)]
        widths=list(self._content_widths)
        extra=max(0,self.viewport().width()-sum(widths))
        widths[3]+=extra//2; widths[4]+=extra-extra//2
        for column,width in enumerate(widths):self.setColumnWidth(column,width)

    def resizeEvent(self,event):
        super().resizeEvent(event)
        if hasattr(self,'_width_timer'):self._width_timer.start(0)

    def changeEvent(self,event):
        super().changeEvent(event)
        if event.type() in (QEvent.FontChange,QEvent.StyleChange) and hasattr(self,'_width_timer'):
            self._invalidate_widths()

    def currentRow(self):return self.currentIndex().row()
    def setCurrentCell(self,row,column):self.setCurrentIndex(self.report_model.index(row,column))
    def selectRow(self,row):
        self.setCurrentIndex(self.report_model.index(row,0));super().selectRow(row)
    def itemAt(self,pos):
        index=self.indexAt(pos)
        return self.item(index.row(),index.column()) if index.isValid() else None
    def item(self,row,column):
        index=self.report_model.index(row,column)
        if not index.isValid():return None
        return OrderCell(index.data(),row,column,index.data(Qt.UserRole))
