"""Print the same rows and subtotals as the Excel export."""
from html import escape

from PyQt5.QtGui import QFont, QTextDocument
from PyQt5.QtPrintSupport import QPrintDialog, QPrinter, QPrinterInfo
from PyQt5.QtWidgets import QDialog, QMessageBox

from .excel import order_rows
from .i18n import tr


def print_document(order):
    headers, rows, totals = order_rows(order)
    info = order["info"]
    weights = (14, 4, 23, 8, 7, 7, 8, 9, 8, 12)
    def cells(values, heading=False):
        tag = "th" if heading else "td"
        return "".join(f'<{tag} width="{100 * weight / sum(weights):.2f}%">{escape(str(value or ""))}</{tag}>'
                       for value, weight in zip(values, weights))
    body = []
    for values, subtotal in rows:
        body.append(f'<tr style="font-weight:{700 if subtotal else 400};">{cells(values)}</tr>')
    total = ["ИТОГО", "", "", "", "", *[f"{totals[index]:g}" for index in (5, 6, 7, 8, 9)]]
    body.append(f'<tr style="font-weight:700">{cells(total)}</tr>')
    html = f'''<html><head><style>
body,table,td,th,p {{font-family:"Times New Roman";font-size:14pt;}}
table {{border-collapse:collapse;width:100%;}}
td,th {{border:1px solid #333;padding:3px;vertical-align:top;}}
th {{font-weight:700;}}
</style></head><body>
<p><b>НАРЯД № {escape(str(info.get('version', 'Новый')))}</b></p>
<p>Дата {escape(str(info.get('order_date', '')))} · {escape(str(info.get('shift_type', '')))}<br>
Мастер {escape(str(info.get('master') or ''))} · Подразделение {escape(str(info.get('department') or ''))}</p>
<table cellpadding="3" cellspacing="0" width="100%"><thead><tr>{cells(headers, True)}</tr></thead><tbody>{''.join(body)}</tbody></table>
</body></html>'''
    document = QTextDocument()
    document.setDefaultFont(QFont("Times New Roman", 14))
    document.setDocumentMargin(0)
    document.setHtml(html)
    return document


def configure_printer(printer):
    printer.setOrientation(QPrinter.Landscape)
    printer.setPaperSize(QPrinter.A4)
    printer.setPageMargins(10, 10, 10, 10, QPrinter.Millimeter)


def request_print(order, parent):
    default = QPrinterInfo.defaultPrinter()
    if default.isNull():
        QMessageBox.information(parent, tr("Прямая печать"), "В Windows не выбран принтер по умолчанию.")
        return False
    printer = QPrinter(default, QPrinter.HighResolution)
    configure_printer(printer)
    printer.setDocName("Наряд № " + str(order["info"].get("version", "Новый")))
    dialog = QPrintDialog(printer, parent)
    if dialog.exec_() != QDialog.Accepted:
        return False
    print_document(order).print_(printer)
    return True
