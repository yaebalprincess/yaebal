"""Date and actor occupy separate lines of each reference audit cell."""
from PyQt5.QtCore import QSize, Qt
from PyQt5.QtGui import QColor, QPen
from PyQt5.QtWidgets import QStyle, QStyledItemDelegate, QStyleOptionViewItem

DATE_ROLE = Qt.UserRole + 31
AUTHOR_ROLE = Qt.UserRole + 32


class AuditStampDelegate(QStyledItemDelegate):
    def sizeHint(self, option, index):
        size = super().sizeHint(option, index)
        return QSize(size.width(), max(size.height(), option.fontMetrics.height() * 2 + 14))

    def paint(self, painter, option, index):
        date = index.data(DATE_ROLE)
        if date is None:
            return super().paint(painter, option, index)
        style_option = QStyleOptionViewItem(option)
        self.initStyleOption(style_option, index)
        style_option.text = ""
        style = option.widget.style()
        style.drawControl(QStyle.CE_ItemViewItem, style_option, painter, option.widget)
        painter.save()
        painter.setFont(option.font)
        rect = option.rect.adjusted(8, 3, -8, -3)
        top = rect.adjusted(0, 0, 0, -rect.height() // 2)
        bottom = rect.adjusted(0, rect.height() // 2, 0, 0)
        ink = option.palette.highlightedText().color() if option.state & QStyle.State_Selected else option.palette.text().color()
        painter.setPen(ink)
        painter.drawText(top, Qt.AlignLeft | Qt.AlignVCenter, option.fontMetrics.elidedText(date or "—", Qt.ElideRight, top.width()))
        color = QColor(ink)
        color.setAlpha(150)
        painter.setPen(QPen(color, .5))
        painter.drawLine(rect.left(), rect.center().y(), rect.right(), rect.center().y())
        author = index.data(AUTHOR_ROLE) or ("Автор не указан" if date else "—")
        painter.drawText(bottom, Qt.AlignLeft | Qt.AlignVCenter, option.fontMetrics.elidedText(author, Qt.ElideRight, bottom.width()))
        painter.restore()


def decorate_references(owner, table, kind, created_column, edited_column, recent=False):
    metadata = owner.db.reference_audit(kind)
    deleted_by = {}
    if recent:
        if kind == "work_type":
            records = owner.db.list_recent_deleted_work_types(30)
        elif kind == "department":
            records = owner.db.list_recent_deleted_departments(30)
        else:
            records = owner.db.list_recent_deleted_employees(owner._people_mode() == "master", 30)
        deleted_by = {record[0]: record[-1] for record in records}
    if not table.property("auditStamps"):
        table.setItemDelegateForColumn(created_column, AuditStampDelegate(table))
        table.setItemDelegateForColumn(edited_column, AuditStampDelegate(table))
        table.setProperty("auditStamps", True)
    for row in range(table.rowCount()):
        identity = table.item(row, 0).data(Qt.UserRole)
        created_by, edited_by = metadata.get(identity, ("", ""))
        if recent:
            edited_by = deleted_by.get(identity, "")
        for column, author in ((created_column, created_by), (edited_column, edited_by)):
            item = table.item(row, column)
            if item is None:
                continue
            date = item.text().split("\n", 1)[0]
            item.setData(DATE_ROLE, date)
            item.setData(AUTHOR_ROLE, author)
            item.setText(date + ("\n" + author if author else ""))
            item.setToolTip((date or "—") + "\n" + (author or ("Сведения об авторе отсутствуют в старых данных." if date else "Изменений нет.")))
        table.setRowHeight(row, max(58, table.fontMetrics().height() * 2 + 14))
