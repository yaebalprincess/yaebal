"""User-visible v12 regressions: reset, practice isolation, spotlights and frames."""
import importlib.util
from pathlib import Path

import pytest
from PyQt5.QtCore import QPoint, Qt, QTimer
from PyQt5.QtGui import QPalette
from PyQt5.QtTest import QTest
from PyQt5.QtWidgets import QDialogButtonBox, QLabel, QMessageBox, QPushButton, QTextBrowser

from smartorder import heavy_ui
from smartorder.config import SettingsStore
from smartorder.context_help import start_training
from smartorder.order_table_layout import DEFAULT_WEIGHTS
from test_liquid_glass import app, drain, glass, javascript, populate, system
from test_liquid_glass_v11 import script


def close_editor(dialog, app):
    dialog._save_draft=lambda:None
    dialog.reject(); dialog.deleteLater(); app.processEvents()


def test_column_reset_updates_current_and_future_orders(glass, app):
    owner,_,user=glass;db,identity,*_=populate(app,glass)
    dialog=heavy_ui.HeavyWorkOrderDialog(db,user,db.get_order(identity),parent=owner);dialog.show()
    drain(app,lambda:not dialog.editor_columns.fit_timer.isActive())
    layout=dialog.editor_columns
    layout.changed=(2,dialog.table.columnWidth(2)+100);layout.dirty=True;layout.fit();layout.save()
    assert layout.weights!=list(DEFAULT_WEIGHTS)
    QTest.mouseClick(dialog.reset_columns_btn,Qt.LeftButton)
    assert layout.weights==list(DEFAULT_WEIGHTS)
    assert SettingsStore(user.id,user.username).load().editor_column_weights==[]
    assert dialog.reset_columns_btn.mapTo(dialog,QPoint()).x()>dialog.delete_row_btn.mapTo(dialog,QPoint()).x()
    assert dialog.table.horizontalHeader().length()<=dialog.table.viewport().width()+2
    close_editor(dialog,app)
    another=heavy_ui.HeavyWorkOrderDialog(db,user,parent=owner)
    assert another.editor_columns.weights==list(DEFAULT_WEIGHTS)
    close_editor(another,app)


def test_excel_is_single_action_and_print_is_removed(glass,app):
    owner,_,_=glass
    assert javascript(app,owner,'document.querySelectorAll("#export").length')==1
    assert javascript(app,owner,'document.querySelectorAll("[data-action=print],.export-split").length')==0
    assert not hasattr(owner,"print_order") and not hasattr(owner,"print_order_btn")
    assert importlib.util.find_spec("smartorder.order_printing") is None
    assert owner._glass.bridge.dispatch("print","{}") is False
    assert set(owner.glass_state()["actions"])=={"create","edit","export","delete"}


@pytest.mark.parametrize("theme",["light","dark"])
def test_web_spotlight_is_above_rows_and_practice_hides_real_orders(glass,app,monkeypatch,theme):
    owner,_,_=glass;db,identity,*_=populate(app,glass)
    owner.theme.setChecked(theme=="dark")
    drain(app,lambda:owner._glass_painted)
    original=list(owner.orders_table.report_model.rows)
    start_training(owner);tour=owner._master_tour
    try:
        drain(app,lambda:javascript(app,owner,'!document.getElementById("training-layer").hidden'))
        assert javascript(app,owner,'document.querySelectorAll("#order-rows tr").length')==0
        assert owner.orders_table.report_model.rows==original
        details=javascript(app,owner,'''(()=>{const c=document.querySelector('.training-card'),r=c.getBoundingClientRect();return [getComputedStyle(c.querySelector('h2')).fontSize,getComputedStyle(c.querySelector('p')).fontSize,document.elementFromPoint(r.x+20,r.y+20).closest('.training-card')!==null,c.scrollHeight<=c.clientHeight+2];})()''')
        assert details==["24px","16px",True,True]
        # The shader covers the list, while the actual Create button remains
        # the clickable element at the centre of its spotlight.
        assert javascript(app,owner,'''(()=>{const r=document.getElementById('create').getBoundingClientRect();return document.elementFromPoint(r.x+r.width/2,r.y+r.height/2).id;})()''')=="create"
        assert not tour.coach.card.isVisible()  # Chromium owns this card.
        assert not tour.coach.geometry().intersects(tour.coach.web_rect())
        monkeypatch.setattr(heavy_ui,"question",lambda *args:QMessageBox.No)
        tour.request_finish();assert tour.running
        monkeypatch.setattr(heavy_ui,"question",lambda *args:QMessageBox.Yes)
        tour.request_finish()
        drain(app,lambda:javascript(app,owner,'document.getElementById("training-layer").hidden'))
        assert javascript(app,owner,'document.querySelectorAll("#order-rows tr").length')==1
        assert owner.orders_table.report_model.rows==original and db.get_order(identity)
    finally:
        if getattr(owner,"_master_tour",None):tour.finish()


@pytest.mark.parametrize("theme",["light","dark"])
def test_date_card_is_below_field_and_parent_stays_dimmed(glass,app,theme):
    owner,_,_=glass;owner.theme.setChecked(theme=="dark")
    drain(app,lambda:owner._glass_painted)
    start_training(owner);tour=owner._master_tour
    try:
        javascript(app,owner,'document.getElementById("create").click()')
        drain(app,lambda:tour.key=="date" and not tour.target.isEmpty())
        card=tour.coach.card;field=tour.editor.order_date
        field_bottom=field.mapTo(tour.editor,QPoint(0,field.height())).y()
        assert 0<=card.y()-field_bottom<=24
        assert card.body.font().pixelSize()>=16 and card.body.height()>=card.body.heightForWidth(card.body.width())
        assert tour.layers[owner].active is False
        assert javascript(app,owner,'document.querySelector(".training-card").hidden') is True
        assert tour.coach.mask().contains(QPoint(8,8))
        assert not tour.coach.mask().contains(field.mapTo(tour.editor,field.rect().center()))
        popup=field._popup
        QTest.mouseClick(field,Qt.LeftButton,pos=field._icon_rect().center())
        drain(app,lambda:popup.isVisible() and popup.ready and not popup.cover.isVisible(),timeout=12)
        assert tour.coach.card.body.height()>=tour.coach.card.body.heightForWidth(tour.coach.card.body.width())
        popup.hide()
        # A picker must keep the main window AND editor shaded.
        tour.index=tour.keys.index("employees");tour.present();app.processEvents()
        captured=[]
        def inspect():
            if tour.picker is None:QTimer.singleShot(20,inspect);return
            captured.extend([not tour.layers[owner].active,not tour.layers[tour.editor].active,
                             tour.coach.card.body.font().pixelSize()>=16])
            tour.picker.reject()
        QTimer.singleShot(50,inspect)
        QTest.mouseClick(tour.editor.add_employee_btn,Qt.LeftButton)
        assert captured==[True,True,True]
    finally:tour.finish();app.processEvents()


def test_numeric_lesson_commits_with_ok_without_enter(glass,app):
    from PyQt5.QtWidgets import QApplication
    owner,_,_=glass;start_training(owner);tour=owner._master_tour
    try:
        tour.click_target();drain(app,lambda:tour.editor is not None)
        tour._ensure_data(seed=True);tour.editor._load_order(tour.demo_order)
        tour.index=tour.keys.index("hours");tour.present();app.processEvents()
        table=tour.editor.table;item=table.item(tour.work_row(),1)
        table.setCurrentItem(item);table.editItem(item);app.processEvents()
        editor=QApplication.focusWidget()
        QTest.keyClick(editor,Qt.Key_A,Qt.ControlModifier);QTest.keyClicks(editor,"6")
        assert tour.key=="hours"
        QTest.mouseClick(tour.coach.card.confirm,Qt.LeftButton)
        drain(app,lambda:tour.key=="boxes")
        assert item.text()=="6"
    finally:tour.finish();app.processEvents()


@pytest.mark.parametrize("theme",["light","dark"])
def test_about_warning_and_footer_are_glass_in_both_themes(glass,app,theme):
    owner,_,_=glass;owner.theme.setChecked(theme=="dark");owner.tabs.setCurrentIndex(6)
    drain(app,lambda:hasattr(owner,"photosensitivity_warning"))
    page=owner.tabs.currentWidget();warning=owner.photosensitivity_warning
    text=" ".join(label.text() for label in warning.findChildren(QLabel))
    assert "ПРЕДУПРЕЖДЕНИЕ ОБ ЭПИЛЕПСИИ" in text and "вспышек света" in text
    assert warning.property("theme")==theme
    footer=page.findChild(QLabel,"AboutFooter")
    assert "text-decoration:underline" in footer.text() and "https://tmbsir.ru/" in footer.text()
    assert not footer.autoFillBackground() and footer.openExternalLinks()


def test_tab_switch_does_not_grab_renderer_and_keeps_opaque_frame(glass,app,monkeypatch):
    owner,_,_=glass
    def forbidden(*_):raise AssertionError("A tab switch must not capture the renderer")
    monkeypatch.setattr(owner.tabs.widget(0),"grab",forbidden)
    owner._capture_tab_frame(1);assert owner._tab_frame is None
    for index in (1,2,3,5,6,0):
        owner.tabs.setCurrentIndex(index);app.processEvents()
    owner._publish_glass_state(force=True)
    drain(app,lambda:owner._glass.page().backgroundColor().alpha()==255)
    assert javascript(app,owner,'getComputedStyle(document.body).backgroundImage.startsWith("url(\\\"data:image/png;base64,")')
    assert javascript(app,owner,'getComputedStyle(document.body).backgroundColor')!="rgba(0, 0, 0, 0)"
