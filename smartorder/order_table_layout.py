"""Responsive editor columns with account-wide saved proportions."""
from PyQt5.QtCore import QEvent, QObject, Qt, QTimer
from PyQt5.QtGui import QFontDatabase, QFontMetrics
from PyQt5.QtWidgets import QHeaderView
from PyQt5 import sip

from .config import SettingsStore, normalize_editor_columns


FLEX_COLUMNS = (0, 2, 4, 5, 6, 7, 9, 10)
DEFAULT_WEIGHTS = (.16, .20, .09, .085, .085, .12, .12, .14)


def distribute(total, weights, minimums):
    minimums = [min(value, total // len(weights)) for value in minimums]
    targets = [max(0, total * weight / sum(weights) - minimum)
               for weight, minimum in zip(weights, minimums)]
    available = max(0, total - sum(minimums))
    basis = sum(targets)
    widths = [minimum + int(available * target / basis) if basis else minimum
              for minimum, target in zip(minimums, targets)]
    widths[-1] += total - sum(widths)
    return widths


class EditorColumnLayout(QObject):
    def __init__(self, dialog):
        super().__init__(dialog)
        self.dialog = dialog
        self.table = dialog.table
        owner = dialog.parentWidget()
        while owner is not None and not hasattr(owner, "settings_store"):
            owner = owner.parentWidget()
        self.owner = owner
        self.store = owner.settings_store if owner is not None else SettingsStore(dialog.user.id, dialog.user.username)
        self.settings = owner.ui_settings if owner is not None else self.store.load()
        self.weights = normalize_editor_columns(self.settings.editor_column_weights) or list(DEFAULT_WEIGHTS)
        self.fitting = False
        self.dragging = False
        self.changed = None
        self.dirty = False
        self.code_font = QFontDatabase.systemFont(QFontDatabase.FixedFont)
        self.fit_timer = QTimer(self)
        self.fit_timer.setSingleShot(True)
        self.fit_timer.timeout.connect(self.fit)
        self.rows_timer = QTimer(self)
        self.rows_timer.setSingleShot(True)
        self.rows_timer.setInterval(45)
        self.rows_timer.timeout.connect(self.wrap_rows)
        self.table.setWordWrap(True)
        self.table.setTextElideMode(Qt.ElideNone)
        self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        header = self.table.horizontalHeader()
        header.setMinimumSectionSize(16)
        for column in FLEX_COLUMNS:
            header.setSectionResizeMode(column, QHeaderView.Interactive)
        for column in (1, 3):
            header.setSectionResizeMode(column, QHeaderView.Fixed)
        header.setSectionResizeMode(10, QHeaderView.Stretch)
        header.setStretchLastSection(False)
        header.sectionResized.connect(self.section_resized)
        header.viewport().installEventFilter(self)
        self.table.viewport().installEventFilter(self)
        self.table.installEventFilter(self)
        dialog.installEventFilter(self)
        self.table.itemChanged.connect(lambda *_: self.rows_timer.start())
        self.fit_timer.start(0)

    def eventFilter(self, widget, event):
        if sip.isdeleted(self.table):
            return False
        kind = event.type()
        if widget is self.table.horizontalHeader().viewport():
            if kind == QEvent.MouseButtonPress:
                self.dragging = True
            elif kind == QEvent.MouseButtonRelease:
                self.dragging = False
                self.fit()
                self.save()
        elif widget is self.dialog and kind in (QEvent.Hide, QEvent.Close):
            self.save()
        elif kind in (QEvent.Resize, QEvent.Show, QEvent.FontChange):
            self.fit_timer.start(0)
        return False

    def section_resized(self, column, old, new):
        if self.fitting:
            return
        if self.dragging and column in FLEX_COLUMNS[:-1]:
            self.changed = (column, new)
            self.dirty = True
        self.fit_timer.start(0)

    def fit(self):
        if sip.isdeleted(self.table) or self.fitting or self.table.viewport().width() < 40:
            return
        self.fitting = True
        try:
            header = self.table.horizontalHeader()
            metrics = self.table.fontMetrics()
            hours = max(metrics.horizontalAdvance("88"), header.fontMetrics().horizontalAdvance("Часы")) + 16
            self.code_font = QFontDatabase.systemFont(QFontDatabase.FixedFont)
            self.code_font.setPixelSize(max(6, metrics.height() - 2))
            code = QFontMetrics(self.code_font).horizontalAdvance("0000000") + 18
            header.resizeSection(1, hours)
            header.resizeSection(3, code)
            budget = max(8, self.table.viewport().width() - hours - code)
            minimums = [60, 80, 40, 40, 40, 45, 40, 50]
            if self.changed is not None:
                column, requested = self.changed
                position = FLEX_COLUMNS.index(column)
                compact = [min(width, budget // 8) for width in minimums]
                chosen = max(compact[position], min(requested, budget - sum(compact) + compact[position]))
                other_weights = [weight for index, weight in enumerate(self.weights) if index != position]
                other_mins = [width for index, width in enumerate(minimums) if index != position]
                widths = distribute(budget - chosen, other_weights, other_mins)
                widths.insert(position, chosen)
                self.weights = [width / budget for width in widths]
                self.changed = None
            else:
                widths = distribute(budget, self.weights, minimums)
            for column, width in zip(FLEX_COLUMNS[:-1], widths[:-1]):
                header.resizeSection(column, width)
            self.rows_timer.start()
        finally:
            self.fitting = False

    def wrap_rows(self):
        if sip.isdeleted(self.table):
            return
        blocked = self.table.blockSignals(True)
        try:
            for row in range(self.table.rowCount()):
                item = self.table.item(row, 3)
                if item is not None:
                    item.setFont(self.code_font)
                work = self.table.item(row, 2)
                if work is not None:
                    work.setToolTip(work.text())
            self.table.resizeRowsToContents()
        finally:
            self.table.blockSignals(blocked)

    def save(self):
        if self.dirty:
            self.settings.editor_column_weights = list(self.weights)
            self.store.save(self.settings)
            self.dirty = False
