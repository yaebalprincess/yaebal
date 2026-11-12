"""Small monochrome symbols drawn in the application's own palette."""
from functools import lru_cache

from PyQt5.QtCore import QPointF, QRectF, Qt
from PyQt5.QtGui import QColor, QIcon, QIconEngine, QPainter, QPainterPath, QPen, QPixmap

WORKSHOP_SYMBOLS = {"smoking": "flame", "drying": "sun", "rennet": "flask",
                    "cheese": "circle", "adyghe": "circle", "packaging": "package"}


@lru_cache(maxsize=48)
def symbol_icon(name, theme="light"):
    return QIcon(SymbolEngine(name, theme))


class SymbolEngine(QIconEngine):
    def __init__(self, name, theme):
        super().__init__()
        self.name, self.theme = name, theme

    def clone(self):
        return SymbolEngine(self.name, self.theme)

    def paint(self, painter, rect, mode, state):
        draw_symbol(painter, QRectF(rect), self.name, self.theme, mode)

    def pixmap(self, size, mode, state):
        pixmap = QPixmap(size)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        draw_symbol(painter, QRectF(pixmap.rect()), self.name, self.theme, mode)
        painter.end()
        return pixmap


def draw_symbol(painter, rect, name, theme, mode=QIcon.Normal):
    painter.save()
    painter.setRenderHint(QPainter.Antialiasing)
    painter.translate(rect.topLeft())
    painter.scale(rect.width() / 24, rect.height() / 24)
    if mode == QIcon.Disabled:
        painter.setOpacity(.45)
    painter.setPen(QPen(QColor("#b1c6df" if theme == "dark" else "#425f80"), 1.7,
                        Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    painter.setBrush(Qt.NoBrush)
    path = QPainterPath()
    if name == "flame":
        path.moveTo(13, 2); path.cubicTo(16, 8, 10, 9, 17, 7)
        path.cubicTo(24, 17, 14, 24, 7, 20); path.cubicTo(1, 16, 6, 10, 8, 8)
        path.cubicTo(7, 12, 14, 10, 13, 2); painter.drawPath(path)
    elif name == "sun":
        painter.drawEllipse(QRectF(7, 7, 10, 10))
        for x1, y1, x2, y2 in [(12,1,12,4),(12,20,12,23),(1,12,4,12),(20,12,23,12),
                              (4,4,6,6),(18,18,20,20),(4,20,6,18),(18,6,20,4)]:
            painter.drawLine(QPointF(x1,y1),QPointF(x2,y2))
    elif name == "flask":
        path.moveTo(9,2); path.lineTo(15,2); path.moveTo(10,2); path.lineTo(10,9)
        path.lineTo(4,19); path.quadTo(3,22,6,22); path.lineTo(18,22)
        path.quadTo(21,22,20,19); path.lineTo(14,9); path.lineTo(14,2)
        path.moveTo(7,15); path.lineTo(17,15); painter.drawPath(path)
    elif name == "circle":
        painter.drawEllipse(QRectF(4,4,16,16))
    elif name == "package":
        for points in [[(3,6),(12,2),(21,6),(21,18),(12,22),(3,18),(3,6),(12,10),(21,6)],
                       [(12,10),(12,22)],[(7,4),(16,8),(16,12)]]:
            path = QPainterPath(QPointF(*points[0]))
            for point in points[1:]: path.lineTo(*point)
            painter.drawPath(path)
    elif name == "user":
        painter.drawEllipse(QRectF(8,2,8,8))
        path.moveTo(4,22); path.lineTo(4,19); path.cubicTo(4,10,20,10,20,19)
        path.lineTo(20,22); painter.drawPath(path)
    elif name == "bell":
        path.moveTo(5,17); path.lineTo(19,17); path.lineTo(17,14); path.lineTo(17,9)
        path.cubicTo(17,2,7,2,7,9); path.lineTo(7,14); path.closeSubpath()
        path.moveTo(10,21); path.quadTo(12,23,14,21)
        painter.drawPath(path)
    elif name == "book":
        path.moveTo(12,5); path.cubicTo(9,2,5,2,2,4); path.lineTo(2,20)
        path.cubicTo(5,18,9,18,12,21); path.cubicTo(15,18,19,18,22,20)
        path.lineTo(22,4); path.cubicTo(19,2,15,2,12,5); path.lineTo(12,21)
        painter.drawPath(path)
    elif name == "restore":
        path.moveTo(4,9); path.cubicTo(9,-1,23,6,20,16)
        path.cubicTo(18,24,6,24,4,17); path.moveTo(3,3);path.lineTo(3,10);path.lineTo(10,10)
        painter.drawPath(path)
    else:
        painter.drawRoundedRect(QRectF(3,3,18,18),2,2)
        painter.drawRect(QRectF(7,3,10,6)); painter.drawRect(QRectF(7,14,10,7))
    painter.restore()
