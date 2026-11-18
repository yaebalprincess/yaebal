"""Real renderer coordinates, target contours and shared master completions."""
import json

import pytest
from PyQt5.QtCore import QPoint, QRect, Qt, QTimer
from PyQt5.QtWidgets import QApplication, QDialogButtonBox, QMessageBox

from smartorder.account_store import complete_master_training
from smartorder.context_help import start_training
from smartorder.db import Database
from test_liquid_glass import app, drain, glass, javascript, system


def stage(app, tour, key):
    tour.index = tour.keys.index(key)
    tour.present()
    drain(app, lambda: not tour.target.isEmpty())


# Assert visual and hit-target coordinates in the actual embedded viewport.
# Chromium 83 silently ignores the CSS inset shorthand.
GEOMETRY = """selector => {
  const get = s => document.querySelector(s);
  const rect = s => get(s).getBoundingClientRect();
  const inside = r => r.width>1 && r.height>1 && r.x>=-1 && r.y>=-1 &&
                      r.right<=innerWidth+1 && r.bottom<=innerHeight+1;
  const matches = (a,b) => ['x','y','width','height'].every(k => Math.abs(a[k]-b[k])<1);
  const at = r => document.elementFromPoint(r.x+r.width/2,r.y+r.height/2);
  const step = get('.training-step-number'), stop = rect('.training-card button');
  const root = rect('#training-layer'), target = rect(selector);
  const row = get('#order-rows tr[data-key="practice"]');
  const ripple = getComputedStyle(step,'::before').animationName;
  return {
    full:root.x===0 && root.y===0 && root.width===innerWidth && root.height===innerHeight,
    ring:matches(rect('.training-spotlight'),target),
    number:inside(step.getBoundingClientRect()) && ripple==='training-wave' ? step.textContent : '',
    card:inside(rect('.training-card')) && inside(stop) && at(stop)===get('.training-card button'),
    target:!!at(target) && get(selector).contains(at(target)),
    row:selector!=='#edit' || row && matches(rect('.training-row-highlight'),row.getBoundingClientRect()),
    blur:getComputedStyle(get('.training-veil')).backdropFilter
  };
}"""


@pytest.mark.parametrize("theme,width,height", [("light",1920,1030), ("dark",790,650), ("light",660,490)])
def test_main_steps_keep_badge_card_and_action_on_screen(glass, app, theme, width, height):
    owner, _, _ = glass
    owner.resize(width, height)
    owner.theme.setChecked(theme == "dark")
    drain(app, lambda: owner._glass_painted)
    start_training(owner)
    tour = owner._master_tour
    try:
        for key, selector in (("create","#create"), ("edit","#edit"), ("history","#history-panel")):
            stage(app, tour, key)
            result = javascript(app, owner, "("+GEOMETRY+")("+json.dumps(selector)+")")
            assert result == dict(full=True, ring=True, number=str(tour.index+1), card=True,
                                  target=True, row=True, blur="blur(3px)"), (key,result)
        javascript(app, owner, 'document.querySelector("#history-panel").click()')
        drain(app, lambda: getattr(owner, "_history_details_dialog", None) and owner._history_details_dialog.isVisible())
        owner._history_details_dialog.reject()
        drain(app, lambda: tour.key=="administration")
    finally:
        tour.finish()


def test_picker_whole_item_and_editable_cells_under_employee(glass, app):
    owner, _, _ = glass
    start_training(owner)
    tour = owner._master_tour
    try:
        stage(app,tour,"works")
        tour._ensure_data(seed=True)
        tour.editor._load_order(tour.demo_order)
        captured = []
        def inspect():
            if tour.picker is None:
                QTimer.singleShot(15,inspect)
                return
            listing = tour.picker.list
            r = listing.visualItemRect(listing.item(0)).intersected(listing.viewport().rect())
            expected = QRect(listing.viewport().mapTo(tour.picker,r.topLeft()),r.size())
            captured.append((tour.coach.target,expected,r.width()))
            tour.picker.reject()
        QTimer.singleShot(50,inspect)
        tour.editor.add_work_btn.click()
        assert captured and captured[0][0] == captured[0][1] and captured[0][2]>400
        stage(app,tour,"edit_any")
        editor, coach = tour.editor, tour.coach
        table = editor.table
        def cell(col):
            r=table.visualItemRect(table.item(tour.work_row(),col))
            return QRect(table.viewport().mapTo(editor,r.topLeft()),r.size())
        drain(app, lambda: coach.target==cell(0) and not editor.editor_columns.fit_timer.isActive())
        assert coach.target==cell(0)
        assert 0 < coach.card.y()-cell(0).bottom() <= 16
        assert abs(coach.card.x()-cell(0).x())<=12
        for col in (1,2,5,6):
            assert cell(col) in coach.cell_holes
            assert not coach.card.geometry().intersects(cell(col))
        for col in (3,4,7,10):
            assert cell(col) not in coach.cell_holes
        assert all(not coach.card.geometry().intersects(rect) for rect in coach.extra_holes)
    finally:
        tour.finish()


def test_shared_master_status_only_for_completed_accounts(glass,app):
    owner, manager, admin = glass
    auth = manager.auth
    auth.add_user(admin,"master","password123","Мастер Упаковка;Мастер Сыр цех")
    master = auth.authenticate("master","password123")
    auth.add_user(admin,"other","password123","Мастер Цех Сушки")
    owner.tabs.setCurrentIndex(3)
    def status(name):
        for row in range(owner.users_table.rowCount()):
            item=owner.users_table.item(row,0)
            if item and item.text()==name:
                return owner.users_table.item(row,2).text()
    drain(app, lambda: status("master"))
    assert status("master") == "Активен\nОбучение  □"
    assert status("admin") == "Активен"
    token=auth.change_token()
    complete_master_training(auth, master)
    assert auth.change_token()>token
    token=auth.change_token()
    complete_master_training(auth, master)
    assert auth.change_token()==token
    owner.refresh_users()
    drain(app,lambda:status("master")=="Активен\nОбучение  ■")
    assert status("other") == "Активен\nОбучение  □"
    reopened=Database(auth.path)
    row=next(row for row in reopened.list_users() if row["id"]==master.id)
    assert row["training_completed_at"]


def test_old_identity_upgrades_without_counting_welcome_as_a_completion(system):
    manager, admin=system
    manager.auth.add_user(admin,"old_master","password123","Мастер Упаковка")
    with manager.auth.write_conn() as conn:
        conn.execute("DROP TABLE master_training")
        conn.execute("DELETE FROM db_meta WHERE key='master_training_v13'")
    auth=Database(manager.auth.path)
    row=next(row for row in auth.list_users() if row["username"]=="old_master")
    assert row["training_completed_at"] is None
    assert auth.authenticate("old_master","password123").id==row["id"]


def test_stop_confirmation_antialiased_and_cancel_does_not_complete(glass,app):
    owner, _, _ = glass
    start_training(owner)
    tour = owner._master_tour
    seen = []
    def inspect():
        box = QApplication.activeModalWidget()
        if not isinstance(box,QMessageBox):
            QTimer.singleShot(15,inspect)
            return
        image=box.grab().toImage()
        corner=[image.pixelColor(x,y).alpha() for y in range(23) for x in range(23)]
        seen.append((box.testAttribute(Qt.WA_TranslucentBackground),box.mask().isEmpty(),
                     min(corner),len({a for a in corner if 0<a<255}),max(corner)))
        box.button(QMessageBox.No).click()
    QTimer.singleShot(30,inspect)
    try:
        tour.request_finish()
        assert tour.running and len(seen)==1
        alpha, unmasked, clear, levels, opaque = seen[0]
        assert alpha and unmasked and clear==0 and levels>=4 and opaque==255, seen
    finally:
        tour.finish()


def test_orders_theme_updates_without_resampling_wallpaper(glass, app, monkeypatch):
    owner,_,_=glass
    for tab in (1,2,0):
        owner.tabs.setCurrentIndex(tab)
        app.processEvents()
    backdrop=owner._legacy_shell._liquid_backdrop
    # Paint may request the native frame. The renderer must never sample it.
    from unittest.mock import patch
    original=owner._renderer_background
    def reject_sample(*_): raise AssertionError("renderer requested a snapshot")
    def checked_background():
        with patch.object(backdrop,"frame",reject_sample):
            original()
    monkeypatch.setattr(owner,"_renderer_background",checked_background)
    for dark in (True, False, True):
        owner.theme.setChecked(dark)
        theme="dark" if dark else "light"
        drain(app,lambda:owner.titlebar.property("theme")==theme and
              javascript(app,owner,"document.documentElement.dataset.theme")==theme)
        image=javascript(app,owner,'getComputedStyle(document.body,"::before").backgroundImage')
        assert "factory-glass.png" in image and "linear-gradient" in image
        javascript(app, owner,'window.SmartOrderView.applyTheme("stale",0)')
        assert javascript(app,owner,"document.documentElement.dataset.theme")==theme
    owner.choose_workshop()
    assert owner.workshop_menu.switch_account_button.text()=="Сменить пользователя"
