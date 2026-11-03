from PyQt5.QtCore import Qt,QPoint,QPointF,QEvent
from PyQt5.QtGui import QPalette,QColor,QMouseEvent
from PyQt5.QtTest import QTest
from PyQt5.QtWidgets import QTextBrowser
from smartorder.analytics_ui import EmployeeAnalyticsDialog,ProductionAnalyticsDialog,FactUnitsDialog,METRICS
from smartorder.heavy_ui import WorkOrderDialog,GifBackgroundWidget
from test_rc19_ui import app,ui,drain
from test_rc19_workshops_analytics import order


def test_dark_profile_surface_and_clicking_3d_metric_changes_real_chart(ui,app):
    create,manager,admin,_=ui;order(manager,admin,'packaging');w=create();w.theme.setChecked(True);w.tabs.setCurrentIndex(4)
    drain(app,lambda:w.analytics and w.analytics.report)
    page=w.analytics;d=EmployeeAnalyticsDialog(page,page.report.employees[0]);d.show();app.processEvents()
    assert d.palette().color(QPalette.Window)==QColor('#0D1322') and d.palette().color(QPalette.WindowText)==QColor('#E8EEF9')
    assert all(c.dark for c in (d.radar,d.line,d.scatter))
    page.radar.anim.setCurrentTime(650);page.radar.repaint();app.processEvents()
    hit=next(rect for index,rect in page.radar._hits if index==4)
    QTest.mouseClick(page.radar,Qt.LeftButton,pos=hit.center().toPoint());app.processEvents()
    assert page.metric.currentIndex()==4 and 'ФАКТ Оплата' in page.timeline.title
    event=QMouseEvent(QEvent.MouseMove,QPointF(d.radar.width()-15,d.radar.height()/2),Qt.NoButton,Qt.NoButton,Qt.NoModifier)
    app.sendEvent(d.radar,event);d.radar.rotation_anim.setCurrentTime(140)
    assert abs(d.radar.get_rotation().x())>.05
    d.radar.anim.setCurrentTime(650);d.radar.repaint();app.processEvents()
    rect=next(rect for index,rect in d.radar._hits if index==4)
    QTest.mouseClick(d.radar,Qt.LeftButton,pos=rect.center().toPoint());app.processEvents()
    assert d.selected_metric==4 and d.line.values==[40]
    assert d.table.horizontalHeaderItem(d.table.columnCount()-1).text()=='ФАКТ Оплата'
    d.close();d.deleteLater()


def test_order_dark_number_combined_payment_and_hidden_old_column(ui,app):
    create,manager,admin,_=ui;db,ident,_,_,_=order(manager,admin,'packaging');w=create();w.theme.setChecked(True)
    dialog=WorkOrderDialog(w.db,w.user,w.db.get_order(ident),parent=w);dialog.show();app.processEvents()
    assert '#FFFFFF' in dialog.order_number_label.styleSheet()
    assert dialog.table.isColumnHidden(8)
    assert dialog.table.horizontalHeaderItem(10).text()=='Оплата'
    row=next(r for r in range(dialog.table.rowCount()) if not dialog._is_total(r) and dialog.table.item(r,2).text())
    assert dialog.table.item(row,10).text()=='40' and dialog.table.item(row,10).flags()&Qt.ItemIsEnabled
    dialog.close();dialog.deleteLater()


def test_dropdown_workshop_theme_gif_about_and_news_documentation(ui,app):
    create,manager,admin,_=ui;w=create();w.theme.setChecked(True);w.choose_workshop();app.processEvents()
    assert w.workshop_menu.isVisible() and '#292C34' in w.workshop_menu.styleSheet() and 'color:#FFFFFF' in w.workshop_menu.styleSheet()
    assert len([a for a in w.workshop_menu.actions() if a.data()])==6
    w.workshop_menu.close();w.tabs.setCurrentIndex(5);app.processEvents()
    assert isinstance(w.tabs.currentWidget(),GifBackgroundWidget)
    browsers=w.tabs.currentWidget().findChildren(QTextBrowser)
    assert any('Новости обновлений' in b.toPlainText() for b in browsers)
    assert all('Редактировать UPDATE_NEWS' not in b.toPlainText() and 'руководство RC20' not in b.toPlainText() for b in browsers)
    assert w.titlebar.title.text()=='Smart Order — Формирование нарядов на работу'


def test_profiles_and_fact_units_use_annual_work_rows(ui,app):
    create,manager,admin,_=ui;db,ident,line,m,d=order(manager,admin,'packaging',day='07-01-2026')
    db.save_order(admin,'07-02-2026','Ночная',m,d,[line]);w=create();w.tabs.setCurrentIndex(4)
    drain(app,lambda:w.analytics and w.analytics.report)
    page=w.analytics;page.start.setDate(page.start.date().fromString('2026-01-01','yyyy-MM-dd'));page.end.setDate(page.end.date().fromString('2026-01-31','yyyy-MM-dd'))
    drain(app,lambda:page.report and page.report.start.month==1 and page.report.end.day==31)
    dialog=EmployeeAnalyticsDialog(page,page.report.employees[0]);assert dialog.annual_table.rowCount()==1 and dialog.monthly_table.rowCount()==2
    dialog.scope.setCurrentIndex(1);assert len(dialog.rows)==2
    production=ProductionAnalyticsDialog(page,page.report.breakdown['shop_limits'][0],'shop');production.scope.setCurrentIndex(1)
    assert production.tables['months'].rowCount()==12 and len(production.rows)==2
    units=FactUnitsDialog(page);assert len(units.items)==1
    units.close();units.deleteLater();production.close();production.deleteLater();dialog.close();dialog.deleteLater()
