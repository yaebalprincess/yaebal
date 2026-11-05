from __future__ import annotations

import math
import threading
from dataclasses import replace
from datetime import date
from pathlib import Path

from PyQt5.QtCore import Qt, QObject, QDate, QTimer, QPointF, QRectF, QPropertyAnimation, QEasingCurve, pyqtProperty, pyqtSignal
from PyQt5.QtGui import QColor, QPainter, QPen, QBrush, QLinearGradient, QConicalGradient, QPainterPath, QPolygonF, QFont, QPalette
from PyQt5.QtWidgets import (QWidget, QFrame, QLabel, QVBoxLayout, QHBoxLayout, QGridLayout, QScrollArea,
    QComboBox, QDateEdit, QPushButton, QCheckBox, QTabWidget, QTableWidget, QTableWidgetItem, QHeaderView,
    QAbstractItemView, QApplication, QDialog, QLineEdit, QFileDialog, QMessageBox, QTextBrowser)

from .analytics import build_report, export_report, aggregate, AnalyticsReport, filter_report
from .analytics_breakdown import period_rows, minmax_rows, grouped, breakdowns, calendar_months
from .workshops import WORKSHOPS
from .security import Permission
from .ui_controls import SearchComboBox, ReportTable
from .heavy_ui import DateRangeEdit
from .appearance import appearance_of, font_for
from .i18n import tr

COLORS = ["#16B9B0", "#7C71F5", "#ED71A7", "#F6AD68", "#42A5F5", "#A3BC64"]


def pretty(value):
    return f"{value:,.2f}".replace(",", " ").rstrip("0").rstrip(".")


def duration(seconds):
    total=max(0,int(seconds));return f"{total//3600:02}:{total//60%60:02}:{total%60:02}"


def palette(dark):
    return {"bg":"#c015273e" if dark else "#b0dcebf7", "card":"#d0112338" if dark else "#def1f9ff",
        "text":"#E7F2FF" if dark else "#102B50", "muted":"#B1C6DF" if dark else "#425F80",
        "grid":"#4c78a6d5" if dark else "#4c6694c4"}


def apply_surface_theme(widget,dark):
    pal=palette(dark);widget.setObjectName("AnalyticsSurface")
    qpal=widget.palette()
    for role,color in ((QPalette.Window,pal["bg"]),(QPalette.WindowText,pal["text"]),(QPalette.Base,pal["card"]),(QPalette.Text,pal["text"]),(QPalette.Button,pal["card"]),(QPalette.ButtonText,pal["text"]),(QPalette.AlternateBase,pal["bg"])):qpal.setColor(role,QColor(color))
    widget.setPalette(qpal);widget.setAutoFillBackground(True);widget.setProperty('theme','dark' if dark else 'light')
    widget.setStyleSheet(f"QWidget#AnalyticsSurface,QDialog#AnalyticsSurface{{font-size:13px;background:{pal['bg']};color:{pal['text']};}} QLabel{{color:{pal['text']};background:transparent;}} QScrollArea,QScrollArea>QWidget>QWidget{{background:{pal['bg']};border:none;}} QLineEdit,QComboBox,QDateEdit,QTextBrowser{{font-size:13px;background:{pal['card']};color:{pal['text']};border:1px solid {pal['grid']};border-radius:7px;padding:6px;}} QComboBox QAbstractItemView,QAbstractItemView,QListView{{background:{pal['card']};color:{pal['text']};border:1px solid {pal['grid']};selection-background-color:#285C84;selection-color:#FFFFFF;}} QPushButton{{font-size:13px;min-height:26px;background:{pal['card']};color:{pal['text']};border:1px solid {pal['grid']};border-radius:8px;padding:8px 12px;}} QPushButton:hover{{border-color:#16B9B0;}} QPushButton:pressed{{background:#285C84;color:#FFFFFF;}} QTabWidget::pane{{border:1px solid {pal['grid']};}} QTabBar::tab{{background:{pal['card']};color:{pal['text']};padding:9px 12px;}} QTabBar::tab:selected{{border-bottom:2px solid #16B9B0;}} QTableWidget,QTableView{{background:{pal['card']};color:{pal['text']};alternate-background-color:{pal['bg']};gridline-color:{pal['grid']};border:1px solid {pal['grid']};border-radius:10px;}} QHeaderView::section{{background:{pal['card']};color:{pal['muted']};padding:9px;border:0;}}")
    for chart in widget.findChildren(AnimatedChart):chart.dark=dark;chart.update()
    if isinstance(widget,QDialog):
        from .heavy_ui import _rc14_force_windows_titlebar
        _rc14_force_windows_titlebar(widget,dark)
    from .liquid_effects import apply_liquid_surface
    widget.setStyleSheet("")
    widget.setAutoFillBackground(False)
    apply_liquid_surface(widget, "dark" if dark else "light")


class AnimatedChart(QWidget):
    axisClicked=pyqtSignal(int)
    """Qt-painted charts with data interpolation, hover tracking and gradient fills."""
    def __init__(self, title, kind="line", suffix="", parent=None):
        super().__init__(parent)
        self.title,self.kind,self.suffix=title,kind,suffix
        self.labels=[];self.values=[];self.old=[];self.xy=[];self.dark=False;self._progress=1.0;self._hits=[];self._hover=-1
        self._rotation=QPointF();self.selected_axis=-1;self.metric_values=[]
        self.rotation_anim=QPropertyAnimation(self,b"rotation",self);self.rotation_anim.setDuration(140);self.rotation_anim.setEasingCurve(QEasingCurve.OutCubic)
        self.setMinimumSize(300,255);self.setMouseTracking(True)
        self.anim=QPropertyAnimation(self,b"progress",self);self.anim.setDuration(650);self.anim.setEasingCurve(QEasingCurve.OutCubic)

    def get_progress(self):return self._progress
    def set_progress(self,v):self._progress=float(v);self.update()
    progress=pyqtProperty(float,get_progress,set_progress)

    def set_data(self,labels,values,xy=None):
        current=self.interpolated();self.anim.stop()
        self.old=current if list(labels)==self.labels and len(current)==len(values) else [0.0]*len(values)
        self.labels=list(labels);self.values=[float(v) for v in values];self.xy=xy or []
        self._hover=-1;self._progress=0;self.anim.setStartValue(0.0);self.anim.setEndValue(1.0);self.anim.start()

    def interpolated(self):
        return [o+(v-o)*self._progress for o,v in zip(self.old,self.values)]

    def get_rotation(self):return self._rotation
    def set_rotation(self,value):self._rotation=value;self.update()
    rotation=pyqtProperty(QPointF,get_rotation,set_rotation)

    def rotate_to(self,value):
        self.rotation_anim.stop();self.rotation_anim.setStartValue(self._rotation);self.rotation_anim.setEndValue(value);self.rotation_anim.start()

    def mouseMoveEvent(self,event):
        if self.kind=="radar":
            self.rotate_to(QPointF((event.pos().x()/max(self.width(),1)-.5)*.7,(event.pos().y()/max(self.height(),1)-.5)*.5))
        pos=event.pos();hit=next((i for i,r in self._hits if r.contains(pos)), -1)
        if hit!=self._hover:self._hover=hit;self.update()
        super().mouseMoveEvent(event)

    def mousePressEvent(self,event):
        if self.kind=="radar" and event.button()==Qt.LeftButton:
            hit=next((i for i,r in self._hits if r.contains(event.pos())),-1)
            if hit>=0:self.selected_axis=hit;self.axisClicked.emit(hit);self.update()
        super().mousePressEvent(event)

    def leaveEvent(self,event):
        self._hover=-1
        if self.kind=="radar":self.rotate_to(QPointF())
        self.update();super().leaveEvent(event)

    def paintEvent(self,event):
        p=QPainter(self);p.setRenderHint(QPainter.Antialiasing);pal=palette(self.dark)
        p.setPen(QPen(QColor(pal["grid"]),1));p.setBrush(QColor(pal["card"]));p.drawRoundedRect(QRectF(self.rect()).adjusted(1,1,-1,-1),18,18)
        appearance = appearance_of(self)
        zoom = getattr(QApplication.instance(), "_smartorder_stylesheet_zoom", 100)
        p.setPen(QColor(pal["text"]));p.setFont(font_for("table_header",zoom,appearance));p.drawText(QRectF(20,14,self.width()-40,30),Qt.AlignLeft|Qt.AlignVCenter,tr(self.title))
        p.setFont(font_for("table",zoom,appearance));self._hits=[]
        if not self.values:
            p.setPen(QColor(pal["muted"]));p.drawText(self.rect(),Qt.AlignCenter,"Нет данных за выбранный период");return
        vals=self.interpolated();area=QRectF(54,66,self.width()-80,self.height()-112)
        if self.kind=="radar":self._radar(p,area,vals,pal)
        elif self.kind=="donut":self._donut(p,area,vals,pal)
        elif self.kind=="bar":self._bars(p,area,vals,pal)
        elif self.kind=="histogram":self._histogram(p,area,vals,pal)
        else:self._line(p,area,vals,pal)
        if 0<=self._hover<len(vals):
            actual=self.metric_values[self._hover] if self.kind=="radar" and len(self.metric_values)==len(vals) else self.values[self._hover]
            text=f"{self.labels[self._hover]} · {pretty(actual)}"+(" · нажмите для детализации" if self.kind=="radar" else " "+self.suffix)
            box=QRectF(16,self.height()-36,self.width()-32,26);p.setPen(Qt.NoPen);p.setBrush(QColor(pal["bg"]));p.drawRoundedRect(box,7,7)
            p.setPen(QColor(pal["text"]));p.drawText(box,Qt.AlignCenter,text)

    def _line(self,p,area,vals,pal):
        top=max(max(vals,default=0),1)*1.1
        p.setPen(QPen(QColor(pal["grid"]),1,Qt.DashLine))
        for n in range(5):
            y=area.bottom()-area.height()*n/4;p.drawLine(QPointF(area.left(),y),QPointF(area.right(),y))
            p.setPen(QColor(pal["muted"]));p.drawText(QRectF(2,y-9,46,18),Qt.AlignRight|Qt.AlignVCenter,pretty(top*n/4));p.setPen(QPen(QColor(pal["grid"]),1,Qt.DashLine))
        xs=[self.xy[i][0] for i in range(len(vals))] if self.kind=="scatter" and self.xy else list(range(len(vals)))
        xmin=min(xs,default=0);xmax=max(xs,default=1);span=max(xmax-xmin,1)
        pts=[QPointF(area.left()+area.width()*(x-xmin)/span if len(vals)>1 else area.center().x(),area.bottom()-area.height()*max(0,v)/top) for x,v in zip(xs,vals)]
        grad=QLinearGradient(area.topLeft(),area.bottomRight());grad.setColorAt(0,QColor(COLORS[0]));grad.setColorAt(1,QColor(COLORS[1]))
        if self.kind!="scatter":
            path=QPainterPath();path.moveTo(pts[0])
            for a,b in zip(pts,pts[1:]):
                mx=(a.x()+b.x())/2;path.cubicTo(QPointF(mx,a.y()),QPointF(mx,b.y()),b)
            fill=QPainterPath(path);fill.lineTo(pts[-1].x(),area.bottom());fill.lineTo(pts[0].x(),area.bottom());fill.closeSubpath()
            shade=QLinearGradient(area.topLeft(),area.bottomLeft());shade.setColorAt(0,QColor(22,185,176,85));shade.setColorAt(1,QColor(22,185,176,0));p.fillPath(fill,QBrush(shade));p.setPen(QPen(QBrush(grad),3));p.drawPath(path)
        for i,pt in enumerate(pts):
            p.setPen(Qt.NoPen);p.setBrush(QColor(COLORS[i%len(COLORS)] if self.kind=="scatter" else COLORS[0]));r=6 if i==self._hover else 3.5;p.drawEllipse(pt,r,r);self._hits.append((i,QRectF(pt.x()-10,pt.y()-10,20,20)))
        p.setPen(QColor(pal["muted"]))
        if self.kind=="scatter":p.drawText(QRectF(area.left(),area.bottom()+10,area.width(),20),Qt.AlignCenter,"Введённые часы → ФИКС, кг")
        else:
            for i in sorted(set([0,len(pts)//2,len(pts)-1])):
                p.drawText(QRectF(pts[i].x()-50,area.bottom()+10,100,20),Qt.AlignCenter,self.labels[i])

    def _bars(self,p,area,vals,pal):
        n=len(vals);maximum=max(max(vals),1);gap=area.height()/max(n,1)
        label_width=min(155,area.width()*0.4)
        for i,v in enumerate(vals):
            y=area.top()+i*gap+4;bar=QRectF(area.left()+label_width,y,max(2,(area.width()-label_width-52)*v/maximum),max(5,min(24,gap-8)))
            grad=QLinearGradient(bar.topLeft(),bar.topRight());grad.setColorAt(0,QColor(COLORS[i%6]));grad.setColorAt(1,QColor(COLORS[(i+1)%6]));p.setPen(Qt.NoPen);p.setBrush(grad);p.drawRoundedRect(bar,5,5)
            p.setPen(QColor(pal["text"]));p.drawText(QRectF(12,y,label_width+32,bar.height()),Qt.AlignVCenter,self.labels[i][:27]);p.drawText(QRectF(bar.right()+7,y,80,bar.height()),Qt.AlignVCenter,pretty(v));self._hits.append((i,QRectF(10,y,self.width()-20,gap)))

    def _histogram(self,p,area,vals,pal):
        maximum=max(max(vals,default=0),1)*1.1;step=area.width()/max(len(vals),1)
        p.setPen(QPen(QColor(pal["grid"]),1,Qt.DashLine))
        for level in range(5):
            y=area.bottom()-area.height()*level/4;p.drawLine(QPointF(area.left(),y),QPointF(area.right(),y));p.setPen(QColor(pal["muted"]));p.drawText(QRectF(2,y-9,46,18),Qt.AlignRight|Qt.AlignVCenter,pretty(maximum*level/4));p.setPen(QPen(QColor(pal["grid"]),1,Qt.DashLine))
        for i,value in enumerate(vals):
            x=area.left()+i*step+step*.17;height=max(1,area.height()*max(0,value)/maximum);bar=QRectF(x,area.bottom()-height,step*.66,height)
            grad=QLinearGradient(bar.topLeft(),bar.bottomLeft());grad.setColorAt(0,QColor(COLORS[i%6]));grad.setColorAt(1,QColor(COLORS[(i+1)%6]));p.setPen(Qt.NoPen);p.setBrush(grad);p.drawRoundedRect(bar,4,4)
            self._hits.append((i,QRectF(area.left()+i*step,area.top(),step,area.height())))
            if i%max(1,math.ceil(len(vals)/8))==0 or i==len(vals)-1:
                p.setPen(QColor(pal["muted"]));p.drawText(QRectF(bar.center().x()-42,area.bottom()+8,84,24),Qt.AlignCenter,self.labels[i])

    def _radar(self,p,area,vals,pal):
        center=area.center();radius=min(area.width()*.32,area.height()*.4)
        yaw,pitch=self._rotation.x(),self._rotation.y()
        def project(x,y,z):
            xx=x*math.cos(yaw)+z*math.sin(yaw);zz=-x*math.sin(yaw)+z*math.cos(yaw)
            yy=y*math.cos(pitch)-zz*math.sin(pitch);depth=y*math.sin(pitch)+zz*math.cos(pitch)
            scale=1/(1-depth/(radius*5+1))
            return QPointF(center.x()+xx*scale,center.y()+yy*scale)
        def points(values,z):
            return QPolygonF([project(math.cos(-math.pi/2+i*2*math.pi/5)*radius*v,math.sin(-math.pi/2+i*2*math.pi/5)*radius*v,z) for i,v in enumerate(values[:5])])
        front=points([1]*5,18);back=points([1]*5,-18)
        p.setPen(QPen(QColor(pal["grid"]),1));p.setBrush(Qt.NoBrush);p.drawPolygon(back)
        for a,b in zip(front,back):p.drawLine(a,b)
        for k in range(1,6):p.drawPolygon(points([k/5]*5,18))
        origin=project(0,0,18)
        for pt in front:p.drawLine(origin,pt)
        ratios=[max(0,min(1,v/100)) for v in vals]
        face=points(ratios,18);rear=points(ratios,-18)
        for i in range(5):
            j=(i+1)%5;shade=QColor(COLORS[i%6]);shade.setAlpha(75)
            p.setPen(QPen(QColor(COLORS[i%6]),1));p.setBrush(shade);p.drawPolygon(QPolygonF([face[i],face[j],rear[j],rear[i]]))
        gradient=QLinearGradient(area.topLeft(),area.bottomRight());gradient.setColorAt(0,QColor(22,185,176,165));gradient.setColorAt(1,QColor(237,113,167,95))
        p.setBrush(gradient);p.setPen(QPen(QColor(COLORS[0]),2));p.drawPolygon(face)
        for i,pt in enumerate(front):
            pos=project(math.cos(-math.pi/2+i*2*math.pi/5)*radius*1.32,math.sin(-math.pi/2+i*2*math.pi/5)*radius*1.32,18)
            selected=i==self.selected_axis;hover=i==self._hover
            p.setPen(QPen(QColor(COLORS[2] if selected else COLORS[0] if hover else pal["grid"]),3 if selected else 1))
            p.setBrush(QColor(COLORS[2] if selected else pal["card"]));p.drawEllipse(pt,5 if selected else 3,5 if selected else 3)
            p.setPen(QColor(COLORS[2] if selected else pal["muted"]));p.drawText(QRectF(pos.x()-66,pos.y()-16,132,32),Qt.AlignCenter,self.labels[i])
            self._hits.extend([(i,QRectF(pos.x()-65,pos.y()-16,130,32)),(i,QRectF(pt.x()-14,pt.y()-14,28,28))])

    def _donut(self,p,area,vals,pal):
        size=min(area.width(),area.height())*0.88;box=QRectF(area.center().x()-size/2,area.center().y()-size/2,size,size)
        total=sum(vals);angle=90.0
        p.setPen(QPen(QColor(pal["grid"]),18));p.drawEllipse(box)
        for i,v in enumerate(vals):
            span=360*v/total if total else 0;p.setPen(QPen(QColor(COLORS[i%6]),18,Qt.SolidLine,Qt.RoundCap));p.drawArc(box,int(angle*16),-int(max(0,span-3)*16));angle-=span
        appearance=appearance_of(self);zoom=getattr(QApplication.instance(),"_smartorder_stylesheet_zoom",100)
        p.setPen(QColor(pal["text"]));p.setFont(font_for("heading",zoom,appearance));p.drawText(box,Qt.AlignCenter,pretty(total));p.setFont(font_for("body",zoom,appearance));p.setPen(QColor(pal["muted"]));p.drawText(QRectF(box.left(),box.center().y()+20,size,30),Qt.AlignCenter,self.suffix)


class MetricCard(QFrame):
    def __init__(self,label,color,parent=None):
        super().__init__(parent);self.setObjectName("MetricCard");self.setMinimumHeight(100);self.color=color;self.dark=False;self._hover=0.0
        l=QVBoxLayout(self);l.setContentsMargins(20,15,20,15);self.label=QLabel(label);self.value=QLabel("—");self.value.setStyleSheet("font-size:25px;font-weight:800;background:transparent;");l.addWidget(self.label);l.addWidget(self.value)
        self.anim=QPropertyAnimation(self,b"hover",self);self.anim.setDuration(160)
    def get_hover(self):return self._hover
    def set_hover(self,v):self._hover=v;self.update()
    hover=pyqtProperty(float,get_hover,set_hover)
    def enterEvent(self,e):self.anim.stop();self.anim.setStartValue(self._hover);self.anim.setEndValue(1.0);self.anim.start();super().enterEvent(e)
    def leaveEvent(self,e):self.anim.stop();self.anim.setStartValue(self._hover);self.anim.setEndValue(0.0);self.anim.start();super().leaveEvent(e)
    def paintEvent(self,e):
        p=QPainter(self);p.setRenderHint(QPainter.Antialiasing);pal=palette(self.dark);p.setPen(QPen(QColor(self.color if self._hover else pal["grid"]),1+self._hover));grad=QLinearGradient(0,0,self.width(),self.height());c=QColor(self.color);c.setAlpha(int(20+25*self._hover));grad.setColorAt(0,QColor(pal["card"]));grad.setColorAt(1,c);p.setBrush(grad);p.drawRoundedRect(QRectF(self.rect()).adjusted(1,1,-1,-1),16,16)


def table(columns,cell_widgets=False):
    if not cell_widgets:return ReportTable(columns)
    w=QTableWidget(0,len(columns));w.setHorizontalHeaderLabels([label for _,label in columns]);w.setProperty("columns",columns)
    w.setAlternatingRowColors(True);w.setSelectionBehavior(QAbstractItemView.SelectRows);w.setEditTriggers(QAbstractItemView.NoEditTriggers);w.verticalHeader().hide();w.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents);w.horizontalHeader().setStretchLastSection(True);w.setMinimumHeight(290);return w


def fill_table(w,rows):
    if isinstance(w,ReportTable):
        w.report_model.set_rows(rows);return
    cols=w.property("columns");w.setSortingEnabled(False);w.setRowCount(len(rows))
    for i,r in enumerate(rows):
        for j,(key,label) in enumerate(cols):
            val=r.get(key,"");text=duration(val) if key.endswith("seconds") else pretty(val) if isinstance(val,(float,int)) else str(val)
            item=QTableWidgetItem(text);item.setData(Qt.UserRole,r)
            if isinstance(val,(float,int)):item.setData(Qt.DisplayRole,text)
            w.setItem(i,j,item)
    w.resizeRowsToContents()


class _ReportSignals(QObject):
    done=pyqtSignal(int,object,str)
    exported=pyqtSignal(str,str)
    filtered=pyqtSignal(int,object,str)


METRICS=[("orders","Наряды"),("hours","Часы работы"),("fixed_kg","ФИКС Итоговый вес, кг"),("actual_hours","ФАКТ часы"),("total_pay","ФАКТ Оплата, ₽")]
AXIS_LABELS=["Наряды","Часы работы","ФИКС, кг","ФАКТ, ч","ФАКТ, ₽"]
LIMIT_COLUMNS=[("day_min_kg","Min кг/день"),("day_min_kg_when","Дни Min"),("day_max_kg","Max кг/день"),("day_max_kg_when","Дни Max"),("month_min_kg","Min кг/месяц"),("month_min_kg_when","Месяцы Min"),("month_max_kg","Max кг/месяц"),("month_max_kg_when","Месяцы Max"),("year_min_kg","Min кг/год"),("year_min_kg_when","Годы Min"),("year_max_kg","Max кг/год"),("year_max_kg_when","Годы Max")]
PEOPLE_LIMIT_COLUMNS=[("day_min_people","Min сотрудников/день"),("day_min_people_when","Дни Min сотрудников"),("day_max_people","Max сотрудников/день"),("day_max_people_when","Дни Max сотрудников"),("month_min_people","Min сотрудников/месяц"),("month_min_people_when","Месяцы Min сотрудников"),("month_max_people","Max сотрудников/месяц"),("month_max_people_when","Месяцы Max сотрудников")]



class AnalyticsWidget(QWidget):
    def __init__(self,owner):
        super().__init__();self.owner=owner;self.manager=owner.workshop_manager;self.user=owner.user;self.report=None;self.base_report=None;self._filter_generation=0;self._generation=0;self._running=False;self._exporting=False;self._pending_request=None;self._deferred_report=None;self._deferred_filtered=None;self._filter_running=False;self._pending_filter=None
        self.signals=_ReportSignals(self);self.signals.done.connect(self._loaded);self.signals.exported.connect(self._exported);self.signals.filtered.connect(self._filtered)
        root=QVBoxLayout(self);root.setContentsMargins(18,12,18,12);root.setSpacing(12)
        title=QLabel("Аналитика производства");title.setStyleSheet("font-size:25px;font-weight:800;background:transparent;");root.addWidget(title)
        self.caption=QLabel("Цеха · работы и коды · подразделения · сотрудники на сменах · мастера");root.addWidget(self.caption)
        filters=QHBoxLayout();self.shop=QComboBox();self.shop.addItem("Все цеха",None)
        for k,v in WORKSHOPS.items():self.shop.addItem(v,k)
        self.start=QDateEdit(self);self.end=QDateEdit(self);self.start.hide();self.end.hide();today=QDate.currentDate()
        for w in (self.start,self.end):w.setCalendarPopup(True);w.setDisplayFormat("dd.MM.yyyy")
        self.start.setDate(QDate(today.year(),today.month(),1));self.end.setDate(today)
        self.period=DateRangeEdit();self.period.setDateRange(self.start.date(),today,False);self.period.dateChanged.connect(self._range_changed)
        self.refresh=QPushButton("Обновить");self.refresh.clicked.connect(self.reload)
        self.charts=QCheckBox("Графики в Excel");self.charts.setChecked(True)
        self.export=QPushButton("Экспорт в Excel");self.export.setObjectName("PrimaryButton");self.export.clicked.connect(self.export_excel);self.export.setEnabled(False)
        for w in (QLabel("Цех:"),self.shop,QLabel("Период:"),self.period,self.refresh,self.charts,self.export):filters.addWidget(w)
        root.addLayout(filters)
        selection=QHBoxLayout();self.production_filters={}
        for field,label in (("department","Подразделение:"),("code","Работа / код:"),("master","Мастер:"),("shift","Смена:")):
            combo=SearchComboBox();combo.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon);combo.setMinimumContentsLength(12);combo.setMinimumWidth(115);combo.setMaximumWidth(360);combo.addItem("Все",None);combo.currentIndexChanged.connect(self._apply_filters);self.production_filters[field]=combo
            selection.addWidget(QLabel(label));selection.addWidget(combo,1)
        self.preset=QComboBox();self.preset.addItems(["Произвольный период","Этот месяц","Этот год","Прошлый год"]);self.preset.activated.connect(self._period_preset);selection.addWidget(self.preset)
        units=QPushButton("Единицы ФАКТ");units.clicked.connect(self._fact_units);selection.addWidget(units);root.addLayout(selection)
        self.status=QLabel("Загрузка…");self.status.setWordWrap(True);root.addWidget(self.status)
        scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setFrameShape(QFrame.NoFrame);root.addWidget(scroll,1)
        content=QWidget();scroll.setWidget(content);body=QVBoxLayout(content);body.setSpacing(14)
        cards=QHBoxLayout();self.cards=[]
        for i,(_,label) in enumerate(METRICS):
            c=MetricCard(label,COLORS[i]);cards.addWidget(c,1);self.cards.append(c)
        body.addLayout(cards)
        self.metric_info=QLabel("Наведите курсор на 3D-профиль; нажмите угол для выбора показателя.");self.metric_info.setWordWrap(True);body.addWidget(self.metric_info)
        grid=QGridLayout();self.timeline=AnimatedChart("Динамика ФИКС по дням","line","кг");self.radar=AnimatedChart("Профиль 3D · ведущий цех","radar","%");self.bars=AnimatedChart("Объём по цехам","bar","кг");self.donut=AnimatedChart("Доля объёма по цехам","donut","кг")
        grid.addWidget(self.timeline,0,0,1,2);grid.addWidget(self.radar,0,2);grid.addWidget(self.bars,1,0,1,2);grid.addWidget(self.donut,1,2);grid.setColumnStretch(0,1);grid.setColumnStretch(1,1);grid.setColumnStretch(2,1);body.addLayout(grid);self.radar.axisClicked.connect(self._select_axis)
        metric_line=QHBoxLayout();metric_line.addWidget(QLabel("Показатель графиков:"));self.metric=QComboBox();self.metric.addItems([label for _,label in METRICS]);self.metric.setCurrentIndex(2);self.metric.currentIndexChanged.connect(self._draw_charts);metric_line.addWidget(self.metric);metric_line.addStretch();body.addLayout(metric_line)
        workforce=QHBoxLayout();workforce.addWidget(QLabel("Помесячная гистограмма:"));self.workforce_metric=QComboBox();self.workforce_metric.addItems(["Уникальные сотрудники","Выходы сотрудников на смены","ФИКС Итоговый вес, кг"]);self.workforce_metric.currentIndexChanged.connect(self._draw_charts);workforce.addWidget(self.workforce_metric);workforce.addStretch();body.addLayout(workforce)
        self.workforce_chart=AnimatedChart("Сотрудники по месяцам","histogram","чел.");body.addWidget(self.workforce_chart)
        self.pages=QTabWidget();self.pages.setUsesScrollButtons(True);self.pages.tabBar().setExpanding(False);body.addWidget(self.pages)
        self.breakdown_tables={}
        self.shop_table=table([("workshop","Цех"),*METRICS,("employees","Уникальные сотрудники"),*LIMIT_COLUMNS,*PEOPLE_LIMIT_COLUMNS]);self.shop_table.itemDoubleClicked.connect(lambda item:self._entity_detail(item,"shop"));self.pages.addTab(self.shop_table,"Цеха / Min–Max");self.breakdown_tables["shop_limits"]=self.shop_table
        employee_page=QWidget();el=QVBoxLayout(employee_page);self.employee_search=QLineEdit();self.employee_search.setPlaceholderText("Поиск сотрудника по ФИО · двойной щелчок открывает профиль");self.employee_search.textChanged.connect(self._fill_employees);el.addWidget(self.employee_search)
        self.employee_table=table([("employee","Сотрудник"),*METRICS]);self.employee_table.itemDoubleClicked.connect(self._employee_detail);el.addWidget(self.employee_table);self.pages.addTab(employee_page,"Сотрудники")
        self.department_table=table([("workshop","Цех"),("department","Подразделение"),*METRICS,*LIMIT_COLUMNS]);self.department_table.itemDoubleClicked.connect(lambda item:self._entity_detail(item,"department"));self.pages.addTab(self.department_table,"Подразделения");self.breakdown_tables["department_limits"]=self.department_table
        work_table=table([("workshop","Цех"),("code","Код работы"),("work","Работа / вид продукции"),*METRICS,*LIMIT_COLUMNS]);work_table.itemDoubleClicked.connect(lambda item:self._entity_detail(item,"work"));self.pages.addTab(work_table,"Работы / коды");self.breakdown_tables["work_limits"]=work_table
        dep_work=table([("workshop","Цех"),("department","Подразделение"),("code","Код"),("work","Работа / вид продукции"),*METRICS,*LIMIT_COLUMNS]);self.pages.addTab(dep_work,"Работы подразделений");self.breakdown_tables["department_work_limits"]=dep_work
        monthly=table([("period","Месяц"),*METRICS,("employees","Уникальные сотрудники"),("employee_shifts","Выходы на смены")]);self.pages.addTab(monthly,"По месяцам");self.breakdown_tables["attendance_months"]=monthly
        yearly=table([("period","Год (в выбранном периоде)"),*METRICS,("employees","Уникальные сотрудники"),("employee_shifts","Выходы на смены")]);self.pages.addTab(yearly,"По годам");self.breakdown_tables["years"]=yearly
        attendance=table([("workshop","Цех"),("period","Дата"),("shift","Смена"),("employees","Уникальные сотрудники"),("employee_shifts","Выходы"),("fixed_kg","ФИКС, кг")]);self.pages.addTab(attendance,"Сотрудники на сменах");self.breakdown_tables["attendance_days"]=attendance
        master_shifts=table([("workshop","Цех"),("master","Мастер"),("shift","Смена"),*METRICS,*LIMIT_COLUMNS,*PEOPLE_LIMIT_COLUMNS]);master_shifts.itemDoubleClicked.connect(lambda item:self._entity_detail(item,"master"));self.pages.addTab(master_shifts,"Выработка мастеров");self.breakdown_tables["master_shifts"]=master_shifts
        self.master_table=table([("workshop","Цех"),("master","Мастер наряда"),("created","Наряды мастера"),("edits","Правки нарядов"),*METRICS]);self.master_table.itemDoubleClicked.connect(self._master_detail);self.pages.addTab(self.master_table,"Мастера")
        self.account_table=table([("username","Логин"),("created","Создал"),("edits","Изменил"),("sessions","Сессии"),("total_seconds","Всего времени"),("longest_seconds","Самая длинная"),("shortest_seconds","Самая короткая"),("last_seconds","Последняя"),("last_state","Статус")]);self.account_table.itemDoubleClicked.connect(self._account_detail);self.pages.addTab(self.account_table,"Логины / сессии программы")
        self.details_table=table([("workshop","Цех"),("date","Дата"),("version","Наряд"),("employee","ФИО"),("department","Подразделение"),("work","Работа"),("hours","Часы"),("fixed_kg","ФИКС, кг"),("actual_hours","ФАКТ часы"),("total_pay","ФАКТ Оплата"),("code","Код"),("shift","Смена"),("creator","Автор создания")]);self.pages.addTab(self.details_table,"Детализация")
        note=QLabel("Двойной щелчок по сотруднику — его работы, цеха, динамика и профиль. По логину — история сессий.\nВыходы сотрудников определяются по нарядам. Сессии относятся только к логинам пользователей приложения. ФАКТ часы требуют выбора единицы работы.");note.setWordWrap(True);body.addWidget(note)
        method=QPushButton("Методика расчёта и ограничения данных");method.clicked.connect(self._methodology);body.addWidget(method)
        self.shop.currentIndexChanged.connect(self.reload);self.start.dateChanged.connect(self.reload);self.end.dateChanged.connect(self.reload)
        self.filter_timer=QTimer(self);self.filter_timer.setSingleShot(True);self.filter_timer.setInterval(100);self.filter_timer.timeout.connect(self._start_filter)
        self.reload_timer=QTimer(self);self.reload_timer.setSingleShot(True);self.reload_timer.setInterval(100);self.reload_timer.timeout.connect(self._start_reload)
        self.timer=QTimer(self);self.timer.setInterval(15000);self._calendar_day=date.today();self.timer.timeout.connect(self._check_calendar);self.timer.start()
        self.set_theme(owner.ui_settings.theme);QTimer.singleShot(0,self.reload)

    def _check_calendar(self):
        today=date.today()
        if today!=self._calendar_day:self._calendar_day=today;self.reload()

    def set_theme(self,theme):
        self.dark=theme=="dark";apply_surface_theme(self,self.dark)
        for c in self.cards:c.dark=self.dark;c.update()
        for dialog in self.findChildren(QDialog):apply_surface_theme(dialog,self.dark)

    def _period_preset(self,index):
        today=QDate.currentDate()
        if index==0:return
        year=today.year()-(1 if index==3 else 0)
        start=QDate(year,today.month() if index==1 else 1,1)
        end=today if index in (1,2) else QDate(year,12,31)
        for widget,value in ((self.start,start),(self.end,end)):widget.blockSignals(True);widget.setDate(value);widget.blockSignals(False)
        self.reload()

    def _populate_filters(self,report):
        for field,combo in self.production_filters.items():
            previous=combo.currentData();combo.blockSignals(True);combo.clear();combo.addItem("Все",None)
            for label,value in report.filter_choices.get(field,[]):combo.addItem(label,value)
            combo.setToolTip(combo.currentText())
            if not combo.property("tooltipConnected"):combo.currentTextChanged.connect(combo.setToolTip);combo.setProperty("tooltipConnected",True)
            combo.setCurrentIndex(max(0,combo.findData(previous)));combo.blockSignals(False)

    def _apply_filters(self,*_):
        if not self.base_report or self._running or self.reload_timer.isActive() or self._pending_request is not None:return
        self._filter_generation+=1
        filters={field:combo.currentData() for field,combo in self.production_filters.items()}
        self._pending_filter=(self._filter_generation,self.base_report,filters)
        self.export.setEnabled(False);self.filter_timer.start()

    def _start_filter(self):
        if self._filter_running or self._pending_filter is None:return
        generation,base,filters=self._pending_filter;self._pending_filter=None
        if generation!=self._filter_generation:return
        if not any(filters.values()):
            self._filtered(generation,base,"");return
        self._filter_running=True;self.status.setText("Расчёт выбранного среза…")
        manager,user,signals=self.manager,self.user,self.signals
        def worker():
            try:manager.require(user,Permission.ANALYTICS_VIEW);report=filter_report(base,filters);error=""
            except Exception as exc:report=None;error=str(exc)
            try:signals.filtered.emit(generation,report,error)
            except RuntimeError:pass
        threading.Thread(target=worker,name="SmartOrderAnalyticsSlice",daemon=True).start()

    def _filtered(self,generation,report,error):
        self._filter_running=False
        if self._pending_filter is not None:self.filter_timer.start();return
        if generation!=self._filter_generation:return
        if error:self.status.setText(error);return
        if not self.isVisible():self._deferred_filtered=report;return
        self._render_report(report)

    def _select_axis(self,index):
        self.radar.selected_axis=index;self.metric.setCurrentIndex(index);self._draw_charts()

    def _entity_detail(self,item,kind):
        row=item.data(Qt.UserRole)
        if row and self.report:ProductionAnalyticsDialog(self,row,kind).exec_()

    def _fact_units(self):
        if self.report:FactUnitsDialog(self).exec_()

    def _range_changed(self):
        self.start.blockSignals(True);self.end.blockSignals(True)
        self.start.setDate(self.period.startDate());self.end.setDate(self.period.endDate())
        self.start.blockSignals(False);self.end.blockSignals(False);self.reload()

    def reload(self,*_):
        self.period.setDateRange(self.start.date(),self.end.date(),False)
        self._filter_generation+=1;self._generation+=1;self._deferred_report=None;self._deferred_filtered=None;self._pending_filter=None;self.filter_timer.stop()
        self._pending_request=(self._generation,self.start.date().toPyDate(),self.end.date().toPyDate(),self.shop.currentData())
        self.export.setEnabled(False);self.reload_timer.start()

    def _start_reload(self):
        if self._running or self._pending_request is None:return
        gen,start,end,key=self._pending_request;self._pending_request=None
        if start>end:self.status.setText("Дата начала позже даты окончания");return
        self._running=True;self.status.setText("Чтение баз цехов…")
        manager,user,signals=self.manager,self.user,self.signals
        def worker():
            try:r=build_report(manager,user,start,end,key);err=""
            except Exception as exc:r=None;err=str(exc)
            try:signals.done.emit(gen,r,err)
            except RuntimeError:pass
        threading.Thread(target=worker,name="SmartOrderAnalytics",daemon=True).start()

    def _loaded(self,generation,report,error):
        self._running=False
        if self._pending_request is not None:
            self.reload_timer.start();return
        if generation!=self._generation:return
        if error:self.status.setText("Ошибка аналитики: "+error);return
        if not self.isVisible():self._deferred_report=report;return
        self.base_report=report;self._populate_filters(report);self._apply_filters()

    def showEvent(self,event):
        super().showEvent(event)
        if self._deferred_report is not None:
            report=self._deferred_report;self._deferred_report=None
            self.base_report=report;self._populate_filters(report);self._apply_filters()
        elif self._deferred_filtered is not None:
            report=self._deferred_filtered;self._deferred_filtered=None;self._render_report(report)

    def _render_report(self,report):
        self.report=report;self.export.setEnabled(True)
        status=f"За сегодня: {report.totals.get('today_orders',0)} нарядов · {report.totals.get('today_employees',0)} уникальных сотрудников на сменах. За выбранный период: {len(report.orders)} нарядов · {len(report.details)} строк"
        if report.missing_workshops:status+=" · Базы ещё не созданы: "+", ".join(report.missing_workshops)
        self.status.setText(status)
        for (key,_),card in zip(METRICS,self.cards):
            value=report.totals.get(key,0);card.value.setText(pretty(value))
        self._draw_charts();self._fill_employees()
        for key,widget in self.breakdown_tables.items():fill_table(widget,report.breakdown.get(key,[]))
        masters={(r["workshop_key"],r["master"]):dict(r) for r in report.breakdown.get("master_limits",[])}
        for row in report.masters:masters.setdefault((row["workshop_key"],row["master"]),{}).update(row)
        for row in masters.values():row.setdefault("created",0);row.setdefault("edits",0)
        fill_table(self.master_table,list(masters.values()));fill_table(self.account_table,report.accounts);fill_table(self.details_table,report.details)

    def _draw_charts(self,*_):
        if not self.report:return
        r=self.report;key,label=METRICS[self.metric.currentIndex()];daily=sorted(r.daily,key=lambda x:x["date"])
        self.timeline.title=f"Динамика · {label}";self.timeline.suffix=label;self.timeline.set_data([x["date"][5:] for x in daily],[x[key] for x in daily])
        self.bars.title=f"Цеха · {label}";self.bars.suffix=label;self.bars.set_data([x["workshop"] for x in r.workshops],[x[key] for x in r.workshops])
        self.donut.title="Доли по цехам · "+label;self.donut.suffix=label;self.donut.set_data([x["workshop"] for x in r.workshops],[x[key] for x in r.workshops])
        values=[]
        for field,_ in METRICS:
            all_vals=[x[field] for x in r.workshops];values.append(100*max(all_vals,default=0)/sum(all_vals) if sum(all_vals) else 0)
        self.radar.metric_values=[r.totals.get(field,0) for field,_ in METRICS]
        self.radar.set_data(AXIS_LABELS,values)
        self.radar.selected_axis=self.metric.currentIndex()
        total=self.radar.metric_values[self.metric.currentIndex()]
        self.metric_info.setText(f"Выбран угол: {label} · всего за период: {pretty(total)}. Вершины показывают долю ведущего цеха, данные графиков — абсолютные значения.")
        workforce_key,suffix=[("employees","чел."),("employee_shifts","выходов"),("fixed_kg","кг")][self.workforce_metric.currentIndex()]
        months=r.breakdown.get("attendance_months",[])
        self.workforce_chart.title=self.workforce_metric.currentText()+" по месяцам";self.workforce_chart.suffix=suffix
        self.workforce_chart.set_data([x["period"] for x in months],[x[workforce_key] for x in months])

    def _fill_employees(self,*_):
        if self.report:fill_table(self.employee_table,[r for r in self.report.employees if self.employee_search.text().casefold() in r["employee"].casefold()])

    def _employee_detail(self,item):
        row=item.data(Qt.UserRole)
        if row and self.report:EmployeeAnalyticsDialog(self,row).exec_()

    def _account_detail(self,item):
        row=item.data(Qt.UserRole)
        if not row or not self.report:return
        dialog=QDialog(self);apply_surface_theme(dialog,self.dark);dialog.setWindowTitle("Сессии · "+row["username"]);dialog.resize(1150,560);l=QVBoxLayout(dialog)
        l.addWidget(QLabel(f"Всего: {duration(row.get('total_seconds',0))} · длинная: {duration(row.get('longest_seconds',0))} · короткая: {duration(row.get('shortest_seconds',0))} · последняя: {duration(row.get('last_seconds',0))}"))
        t=table([("workshop_name","Цех"),("session_started","Начало сеанса, UTC"),("started_at","Начало посещения, UTC"),("ended_at","Конец посещения, UTC"),("seconds_in_period","За период, сек"),("state","Статус")]);fill_table(t,[r for r in self.report.sessions if r["username"]==row["username"]]);l.addWidget(t)
        l.addWidget(QLabel("Открытая программа включает бездействие. Минимум и максимум — завершённые или прерванные сессии."));dialog.exec_()

    def _master_detail(self,item):
        self._entity_detail(item,"master")

    def _methodology(self):
        if not self.report:return
        d=QDialog(self);apply_surface_theme(d,self.dark);d.setWindowTitle("Методика аналитики");d.resize(720,480);l=QVBoxLayout(d);b=QTextBrowser();b.setPlainText(self.report.methodology);l.addWidget(b);d.exec_()

    def export_excel(self):
        if not self.report or self._exporting or self._running or self.reload_timer.isActive() or self._filter_running or self.filter_timer.isActive():return
        try:self.manager.require(self.user,Permission.ANALYTICS_EXPORT)
        except Exception as exc:QMessageBox.warning(self,"Экспорт",str(exc));return
        path,_=QFileDialog.getSaveFileName(self,"Сохранить аналитику",f"SmartOrder_Аналитика_{self.report.start}_{self.report.end}.xlsx","Excel (*.xlsx)")
        if not path:return
        if not path.lower().endswith(".xlsx"):path+=".xlsx"
        self._exporting=True;self.export.setEnabled(False);r=self.report;charts=self.charts.isChecked();self.status.setText("Сохранение Excel…")
        def worker():
            try:export_report(Path(path),r,charts);err=""
            except Exception as exc:err=str(exc)
            try:self.signals.exported.emit(path,err)
            except RuntimeError:pass
        threading.Thread(target=worker,name="SmartOrderExcelAnalytics",daemon=True).start()

    def _exported(self,path,error):
        self._exporting=False;self.export.setEnabled(self.report is not None);self.status.setText("Ошибка экспорта: "+error if error else "Отчёт сохранён: "+path)


class EmployeeAnalyticsDialog(QDialog):
    def __init__(self,page,row):
        super().__init__(page);self.page=page;self.source_report=page.report;self.employee=row;self.selected_metric=1
        self.setWindowTitle("Профиль сотрудника · "+row["employee"]);self.resize(1240,880)
        root=QVBoxLayout(self);heading=QLabel(row["employee"]);heading.setTextFormat(Qt.PlainText);heading.setStyleSheet("font-size:24px;font-weight:800;");root.addWidget(heading)
        filters=QHBoxLayout();self.shop=QComboBox();self.shop.addItem("Все цеха отчёта",None)
        keys={r["workshop_key"] for r in page.report.annual_details if r["employee_key"]==row["employee_key"]}
        for k in WORKSHOPS:
            if k in keys:self.shop.addItem(WORKSHOPS[k],k)
        self.year=QComboBox();years=sorted({r["date"][:4] for r in page.report.annual_details},reverse=True)
        for year in years:self.year.addItem(year,year)
        self.scope=QComboBox();self.scope.addItems(["Выбранный период","Полный выбранный год"])
        for widget in (QLabel("Цех:"),self.shop,QLabel("Год:"),self.year,self.scope):filters.addWidget(widget)
        filters.addStretch();self.export=QPushButton("Excel сотрудника");self.export.clicked.connect(self.export_employee);filters.addWidget(self.export);root.addLayout(filters)
        self.summary=QLabel();self.summary.setWordWrap(True);root.addWidget(self.summary)
        grid=QGridLayout();self.radar=AnimatedChart("3D-профиль сотрудника","radar","%");self.line=AnimatedChart("Часы работы по дням","line","ч");self.scatter=AnimatedChart("Время и объём работ","scatter","кг")
        for i,c in enumerate((self.radar,self.line,self.scatter)):grid.addWidget(c,0,i)
        root.addLayout(grid);self.radar.axisClicked.connect(self._axis_selected)
        self.selected_info=QLabel();self.selected_info.setWordWrap(True);root.addWidget(self.selected_info)
        self.pages=QTabWidget();self.pages.setUsesScrollButtons(True);root.addWidget(self.pages,1)
        self.table=table([("workshop","Цех"),("date","Дата"),("version","Наряд"),("shift","Смена"),("department","Подразделение"),("code","Код"),("work","Работа"),("hours","Часы работы"),("fixed_kg","ФИКС, кг"),("actual_hours","ФАКТ часы"),("total_pay","ФАКТ Оплата")]);self.pages.addTab(self.table,"Строки выбранного среза")
        self.annual_table=table([("year","Полный календарный год"),("workshop","Цех"),("code","Код"),("work","Работа"),*METRICS,*LIMIT_COLUMNS]);self.pages.addTab(self.annual_table,"Работы за год / Min–Max")
        self.monthly_table=table([("month","Месяц"),("workshop","Цех"),("code","Код"),("work","Работа"),*METRICS,*LIMIT_COLUMNS[:4]]);self.pages.addTab(self.monthly_table,"Min–Max работ по месяцам")
        self.departments_table=table([("workshop","Цех"),("department","Подразделение"),("employee_shifts","Смен с этим подразделением"),("orders","Наряды"),("fixed_kg","ФИКС, кг")]);self.pages.addTab(self.departments_table,"Где работал чаще за год")
        note=QLabel("Годовые таблицы охватывают полный календарный год, выбранный выше. Данные графиков и строк зависят от переключателя периода/года.\nВыходы — записи в нарядах, без сессий сотрудника. Профиль нормирован относительно других сотрудников того же среза; угол выбирается нажатием.");note.setWordWrap(True);root.addWidget(note)
        self.dark=page.dark;apply_surface_theme(self,self.dark)
        for widget in (self.shop,self.year,self.scope):widget.currentIndexChanged.connect(self.refresh)
        self.refresh()

    def _axis_selected(self,index):self.selected_metric=index;self.refresh()

    def refresh(self,*_):
        shop=self.shop.currentData();year=self.year.currentData()
        all_annual=[r for r in self.source_report.annual_details if (not shop or r["workshop_key"]==shop) and (not year or r["date"][:4]==year)]
        self.annual_rows=[r for r in all_annual if r["employee_key"]==self.employee["employee_key"]]
        source=all_annual if self.scope.currentIndex()==1 else [r for r in self.source_report.details if not shop or r["workshop_key"]==shop]
        self.rows=[r for r in source if r["employee_key"]==self.employee["employee_key"]]
        totals=aggregate(self.rows,["employee_key"]);t=totals[0] if totals else dict.fromkeys([k for k,_ in METRICS],0)
        label="полный год "+str(year) if self.scope.currentIndex()==1 else f"период {self.source_report.start} — {self.source_report.end}"
        self.summary.setText(label+" · "+" · ".join(f"{title}: {pretty(t[field])}" for field,title in METRICS)+f"\nФИКС / час работы: {pretty(t['fixed_kg']/t['hours']) if t['hours'] else '—'} кг/ч")
        peers=aggregate(source,["employee_key"])
        values=[100*t[field]/max([r[field] for r in peers] or [1]) if max([r[field] for r in peers] or [0]) else 0 for field,_ in METRICS]
        self.radar.metric_values=[t[field] for field,_ in METRICS];self.radar.selected_axis=self.selected_metric;self.radar.set_data(AXIS_LABELS,values)
        field,title=METRICS[self.selected_metric];days=sorted(aggregate(self.rows,["date"]),key=lambda r:r["date"])
        self.line.title=title+" по дням";self.line.suffix=title;self.line.set_data([r["date"][5:] for r in days],[r[field] for r in days])
        self.scatter.set_data([r["date"] for r in days],[r["fixed_kg"] for r in days],[(r["hours"],r["fixed_kg"]) for r in days])
        self.selected_info.setText(f"Выбран угол: {title} · значение: {pretty(t[field])}. График по дням показывает этот показатель.")
        fill_table(self.table,self.rows)
        annual=[{**r,"year":r["date"][:4],"month":r["date"][:7]} for r in self.annual_rows]
        fill_table(self.annual_table,minmax_rows(annual,["year","workshop_key","workshop","code","work"]))
        fill_table(self.monthly_table,minmax_rows(annual,["month","workshop_key","workshop","code","work"]))
        departments=grouped(self.annual_rows,["workshop_key","workshop","department"]);departments.sort(key=lambda r:(-r["employee_shifts"],-r["orders"],r["department"]));fill_table(self.departments_table,departments)

    def export_employee(self):
        export_slice(self.page,self,self.rows,self.annual_rows,"SmartOrder_Сотрудник.xlsx",self.shop.currentData(), self.year.currentData() if self.scope.currentIndex()==1 else None)


class ProductionAnalyticsDialog(QDialog):
    def __init__(self,page,row,kind):
        super().__init__(page);self.page=page;self.source_report=page.report;self.row=row;self.kind=kind
        name=row.get({"shop":"workshop","department":"department","work":"work","master":"master"}[kind],"")
        self.setWindowTitle("Аналитика · "+name);self.resize(1240,860);root=QVBoxLayout(self)
        title=QLabel(name);title.setTextFormat(Qt.PlainText);title.setStyleSheet("font-size:25px;font-weight:800;");root.addWidget(title)
        filters=QHBoxLayout();self.scope=QComboBox();self.scope.addItems(["Выбранный период","Полный выбранный год"]);self.year=QComboBox()
        for y in sorted({r["date"][:4] for r in page.report.annual_details},reverse=True):self.year.addItem(y,y)
        self.work=QComboBox();self.work.addItem("Все работы / виды продукции",None)
        own=[r for r in page.report.annual_details if self._matches(r)]
        for code,name in sorted({(r["code"],r["work"]) for r in own}):self.work.addItem(code+" · "+name,(code,name))
        for w in (self.scope,self.year,self.work):filters.addWidget(w)
        filters.addStretch();export=QPushButton("Excel этого среза");export.clicked.connect(lambda:export_slice(page,self,self.rows,self.annual_rows,"SmartOrder_Производство.xlsx",row["workshop_key"],self.year.currentData() if self.scope.currentIndex()==1 else None));filters.addWidget(export);root.addLayout(filters)
        self.summary=QLabel();self.summary.setWordWrap(True);root.addWidget(self.summary)
        self.chart=AnimatedChart("ФИКС по дням","line","кг");self.staff_chart=AnimatedChart("Сотрудники по месяцам","histogram","чел.");graphs=QHBoxLayout();graphs.addWidget(self.chart);graphs.addWidget(self.staff_chart);root.addLayout(graphs)
        self.pages=QTabWidget();root.addWidget(self.pages,1);self.tables={}
        for key,label,columns in [
            ("period","Итог / Min–Max",[*METRICS,("employees","Уникальные сотрудники"),*LIMIT_COLUMNS,*PEOPLE_LIMIT_COLUMNS]),
            ("days","По дням",[("period","Дата"),*METRICS,("employees","Сотрудники")]),
            ("months","По месяцам",[("period","Месяц"),*METRICS,("employees","Сотрудники"),("employee_shifts","Выходы")]),
            ("years","По годам",[("period","Год"),*METRICS,("employees","Сотрудники")]),
            ("works","Работы / коды",[("code","Код"),("work","Работа"),*METRICS,*LIMIT_COLUMNS]),
            ("shifts","Смены",[("shift","Смена"),*METRICS,*LIMIT_COLUMNS,*PEOPLE_LIMIT_COLUMNS]),
            ("departments","Подразделения",[("department","Подразделение"),*METRICS,*LIMIT_COLUMNS]),
            ("staff","Выходы на смены",[("period","Дата"),("shift","Смена"),("employees","Уникальные сотрудники"),("fixed_kg","ФИКС, кг")])]:
            w=table(columns);self.tables[key]=w;self.pages.addTab(w,label)
        note=QLabel("Суммы производства — по последним версиям нарядов. Min/Max — только по периодам с нарядами. Сотрудники — уникальные ФИО, выходы — дата + смена + цех.\nДля мастера: показатели относятся к мастеру в шапке документа; реальные создания/правки по логину находятся в таблице «Логины / сессии программы».");note.setWordWrap(True);root.addWidget(note)
        for combo in (self.scope,self.year,self.work):combo.currentIndexChanged.connect(self.refresh)
        apply_surface_theme(self,page.dark);self.refresh()

    def _matches(self,r):
        if r["workshop_key"]!=self.row["workshop_key"]:return False
        if self.kind=="department":return r["department"]==self.row["department"]
        if self.kind=="work":return r["code"]==self.row["code"] and r["work"]==self.row["work"]
        if self.kind=="master":return r["master_id"]==self.row["master_id"] if self.row.get("master_id") is not None else r["master"]==self.row["master"]
        return True

    def refresh(self,*_):
        year=self.year.currentData();work=self.work.currentData()
        def matches(r):return self._matches(r) and (not work or (r["code"],r["work"])==tuple(work))
        self.annual_rows=[r for r in self.source_report.annual_details if matches(r) and (not year or r["date"][:4]==year)]
        self.rows=self.annual_rows if self.scope.currentIndex()==1 else [r for r in self.source_report.details if matches(r)]
        start=date(int(year),1,1) if self.scope.currentIndex()==1 and year else self.source_report.start
        end=date(int(year),12,31) if self.scope.currentIndex()==1 and year else self.source_report.end
        totals=grouped(self.rows,[]);total=totals[0] if totals else {**dict.fromkeys([k for k,_ in METRICS],0),"employees":0}
        self.summary.setText(f"{start} — {end} · "+" · ".join(f"{label}: {pretty(total[key])}" for key,label in METRICS)+f" · уникальных сотрудников: {total['employees']}"+(f"\nНаряды, где указан мастер, зарегистрированные за период отчёта: {self.row.get('created',0)} · правки: {self.row.get('edits',0)}" if self.kind=="master" else ""))
        data={"period":minmax_rows(self.rows,[]),"days":period_rows(self.rows,"day"),"months":calendar_months(self.rows,start,end),"years":period_rows(self.rows,"year"),"works":minmax_rows(self.rows,["code","work"]),"shifts":minmax_rows(self.rows,["shift"]),"departments":minmax_rows(self.rows,["department"]),"staff":period_rows(self.rows,"day",["shift"])}
        for key,widget in self.tables.items():fill_table(widget,data[key])
        self.chart.set_data([r["period"] for r in data["days"]],[r["fixed_kg"] for r in data["days"]]);self.staff_chart.set_data([r["period"] for r in data["months"]],[r["employees"] for r in data["months"]])


def export_slice(page,parent,rows,annual,filename,shop=None,year=None):
    try:page.manager.require(page.user,Permission.ANALYTICS_EXPORT)
    except Exception as exc:QMessageBox.warning(parent,"Экспорт",str(exc));return
    path,_=QFileDialog.getSaveFileName(parent,"Сохранить отчёт",filename,"Excel (*.xlsx)")
    if not path:return
    if not path.lower().endswith(".xlsx"):path+=".xlsx"
    source=getattr(parent,"source_report",page.report);start=date(int(year),1,1) if year else source.start;end=date(int(year),12,31) if year else source.end
    order_ids={(r["workshop_key"],r["order_id"]):{"workshop_key":r["workshop_key"],"id":r["order_id"]} for r in rows}
    report=replace(source,start=start,end=end,workshop=shop,details=rows,annual_details=annual,employees=aggregate(rows,["employee_key","employee"]),workshops=aggregate(rows,["workshop_key","workshop"]),departments=aggregate(rows,["workshop_key","workshop","department"]),daily=aggregate(rows,["date"]),orders=list(order_ids.values()),masters=[],accounts=[],sessions=[],events=[],selection=source.selection+" · "+parent.windowTitle(),breakdown=breakdowns(rows,annual,start,end))
    try:export_report(Path(path),report,page.charts.isChecked());QMessageBox.information(parent,"Экспорт","Отчёт сохранён")
    except Exception as exc:QMessageBox.warning(parent,"Экспорт",str(exc))


class FactUnitsDialog(QDialog):
    def __init__(self,page):
        super().__init__(page);self.page=page;self.setWindowTitle("Единицы ФАКТ по кодам работ");self.resize(900,650);root=QVBoxLayout(self)
        note=QLabel("В старой базе единица ФАКТ не записывалась. Укажите её для работы: в «ФАКТ часы» попадут только часы. Килограммы, штуки и неизвестные единицы не суммируются как часы. Настройка применяется к историческим значениям выбранной работы; суммы и оплата не изменяются.");note.setWordWrap(True);root.addWidget(note)
        self.table=table([("workshop","Цех"),("code","Код"),("work","Работа"),("unit","Единица ФАКТ")],cell_widgets=True);root.addWidget(self.table,1)
        works={(r["workshop_key"],r["work_type_id"]):r for r in page.base_report.annual_details if r["work_type_id"] is not None}
        self.items=[];self.table.setRowCount(len(works))
        for index,((shop,work_id),row) in enumerate(sorted(works.items(),key=str)):
            for col,field in enumerate(("workshop","code","work")):self.table.setItem(index,col,QTableWidgetItem(row[field]))
            combo=QComboBox()
            for label,value in (("Не указана","unknown"),("Часы","h"),("Килограммы","kg"),("Штуки","pcs")):combo.addItem(label,value)
            combo.setCurrentIndex(max(0,combo.findData(row["actual_unit"])));self.table.setCellWidget(index,3,combo);self.items.append((shop,work_id,row["actual_unit"],combo))
        controls=QHBoxLayout();hours=QPushButton("Все показанные работы — часы");hours.clicked.connect(lambda:[combo.setCurrentIndex(combo.findData("h")) for _,_,_,combo in self.items]);controls.addWidget(hours);controls.addStretch();save=QPushButton("Сохранить единицы");save.clicked.connect(self.save);controls.addWidget(save);root.addLayout(controls);apply_surface_theme(self,page.dark)

    def save(self):
        try:
            self.page.manager.require(self.page.user,Permission.CATALOG_EDIT)
            for shop,ident,previous,combo in self.items:
                if combo.currentData()!=previous:self.page.manager.database(shop,self.page.user).set_work_fact_unit(self.page.user,ident,combo.currentData())
            self.page.reload();self.accept()
        except Exception as exc:QMessageBox.warning(self,"Единицы ФАКТ",str(exc))
