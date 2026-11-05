"""Headless smoke of main(), real login, production data, analytics and Excel.

Uses a disposable database. Example names/values are synthetic. Never connect
this helper to a production share. Pass --output-dir for screenshots/Excel.
"""
from __future__ import annotations
import argparse
import json
import os
import sys
import tempfile
from pathlib import Path
from decimal import Decimal

parser=argparse.ArgumentParser();parser.add_argument("--output-dir",type=Path,default=Path(tempfile.gettempdir())/"smartorder-smoke");args=parser.parse_args()
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("QT_QPA_PLATFORM","offscreen")
temp=tempfile.TemporaryDirectory(prefix="smartorder-smoke-");root=Path(temp.name)
os.environ["SMARTORDER_NETWORK_ROOT"]=str(root/"share");os.environ["LOCALAPPDATA"]=str(root/"local");os.environ.pop("SMARTORDER_DB_PATH",None)
os.environ["XDG_CACHE_HOME"]=str(root/"cache")
args.output_dir.mkdir(parents=True,exist_ok=True)

from PyQt5.QtCore import QTimer,QDate
from PyQt5.QtWidgets import QApplication,QMessageBox
from smartorder import app as entry
from smartorder import heavy_ui
from smartorder.ui import FirstAdminDialog
from smartorder.domain import OrderLine
from smartorder.analytics import export_report
from smartorder.analytics_ui import EmployeeAnalyticsDialog, AnimatedChart
from smartorder.workshops import WORKSHOPS
from smartorder.live_ui import LiveDiagnosticsDialog,notifications,unread_count

result={"synthetic_data":True,"errors":[]}
for name in ("critical","warning"):
    setattr(QMessageBox,name,lambda *a,_kind=name:result["errors"].append({"kind":_kind,"message":str(a[2])}) or QMessageBox.Ok)

def first(dialog):
    dialog.username.setText("smokeadmin");dialog.password.setText("password123");dialog.password2.setText("password123");dialog._create();return dialog.result()
FirstAdminDialog.exec_=first
def login(dialog):
    dialog.username_edit.setText("smokeadmin");dialog.password_edit.setText("password123");dialog._login();return dialog.result()
heavy_ui.LoginDialog.exec_=login

class SmokeApplication(QApplication):
    def __init__(self,*a):super().__init__(*a);QTimer.singleShot(800,seed)
entry.QApplication=SmokeApplication

def seed():
    w=QApplication.instance()._smartorder_main_window
    try:
        for shop_index,key in enumerate(WORKSHOPS):
            db=w.workshop_manager.database(key,w.user)
            master=db.add_employee(w.user,"Тестовый мастер "+str(shop_index+1),True)
            employees=[db.add_employee(w.user,name) for name in ("Тестовый Иванов И.И.","Тестовый Петров П.П.","Тестовый Сидоров С.С.")]
            dep=db.add_department(w.user,"1. Производство");work=db.add_work_type(w.user,"Тестовая работа "+key,"DEMO-001",str(2+shop_index))
            db.set_work_fact_unit(w.user,work,"h")
            for day in range(1,8):
                lines=[OrderLine(e,name,work,"Тестовая работа "+key,"DEMO-001",Decimal(2+shop_index),Decimal(4+(day+i)%5),Decimal((day*7+shop_index*9+i*5)%45+15),Decimal('1.5')) for i,(e,name) in enumerate(zip(employees,("Тестовый Иванов И.И.","Тестовый Петров П.П.","Тестовый Сидоров С.С.")))]
                if day%3==0:
                    lines[1].actual_value=Decimal("2.5");lines[1].fixed_boxes=None;lines[1].fixed_weight=None
                db.save_order(w.user,f"{day:02}-10-2026","Дневная",master,dep,lines)
        manager=w.workshop_manager
        manager.auth.add_user(w.user,"Тестовый Иван","password123","Мастер Упаковка")
        manager.auth.add_user(w.user,"Тестовый Пётр","password123","Мастер Упаковка")
        owner=manager.auth.authenticate("Тестовый Иван","password123");editor=manager.auth.authenticate("Тестовый Пётр","password123")
        pack=manager.database("packaging",owner);sample=pack.get_order(pack.list_orders()[0]["id"])
        info=sample["info"];own=pack.save_order(owner,info["order_date"],info["shift_type"],info["master_id"],info["department_id"],sample["lines"])
        manager.database("packaging",editor).save_order(editor,info["order_date"],info["shift_type"],info["master_id"],info["department_id"],sample["lines"],comment="Тестовый комментарий: уточнена смена.",parent_id=own)
        w.tabs.setCurrentIndex(4);QTimer.singleShot(1100,capture)
    except Exception as exc:result["errors"].append(str(exc));finish()

attempts=0
def capture():
    global attempts
    w=QApplication.instance()._smartorder_main_window
    if w.analytics.report is None:
        attempts+=1
        if attempts>20:result["errors"].append("Analytics did not finish");finish();return
        QTimer.singleShot(250,capture);return
    try:
        w.resize(1540,1000);w.showNormal();QApplication.processEvents();
        for c in w.analytics.findChildren(AnimatedChart):c.anim.setCurrentTime(650)
        QApplication.processEvents();w.grab().save(str(args.output_dir/"Analytics_Light_DEMO.png"))
        w.theme.setChecked(True);QApplication.processEvents();w.grab().save(str(args.output_dir/"Analytics_Dark_DEMO.png"))
        r=w.analytics.report
        export_report(args.output_dir/"Analytics_DEMO.xlsx",r,True)
        profile=EmployeeAnalyticsDialog(w.analytics,r.employees[0]);profile.show();QApplication.processEvents();profile.radar.anim.setCurrentTime(650);profile.line.anim.setCurrentTime(650);profile.scatter.anim.setCurrentTime(650);profile.grab().save(str(args.output_dir/"Employee_Profile_DEMO.png"));profile.close()
        # Real editor and admin screen exercise the requested theme fixes.
        from smartorder.heavy_ui import WorkOrderDialog
        edit=WorkOrderDialog(w.db,w.user,w.db.get_order(w.db.list_orders()[0]["id"]),parent=w);edit.resize(1420,880);edit.show();QApplication.processEvents();edit.showNormal();edit.resize(1420,880);QApplication.processEvents();edit.grab().save(str(args.output_dir/"Order_Dark_DEMO.png"));edit.close()
        w.tabs.setCurrentIndex(3);QApplication.processEvents();w.grab().save(str(args.output_dir/"Administration_Dark_DEMO.png"));w.tabs.setCurrentIndex(4)
        from smartorder.analytics_ui import ProductionAnalyticsDialog
        prod=ProductionAnalyticsDialog(w.analytics,r.breakdown["shop_limits"][0],"shop");prod.show();QApplication.processEvents();prod.grab().save(str(args.output_dir/"Workshop_Profile_DEMO.png"));prod.close()
        result.update(orders=len(r.orders),employees=len(r.employees),details=len(r.details),workshops=len(r.workshops),databases=[w.workshop_manager.path_for(k).name for k in WORKSHOPS],excel_charts=6,main_entrypoint="passed")
        w.tabs.setCurrentIndex(5);QApplication.processEvents();w.grab().save(str(args.output_dir/"About_DEMO.png"))
        from smartorder.enterprise_ui import MainWindow
        owner=w.workshop_manager.auth.authenticate("Тестовый Иван","password123")
        master_window=MainWindow(w.workshop_manager.database("packaging",owner),owner,w.workshop_manager);master_window.show()
        master_window._notifications_loaded(notifications(w.workshop_manager,owner),unread_count(w.workshop_manager,owner),"")
        master_window.show_notifications();QApplication.processEvents();master_window.notification_popup.grab().save(str(args.output_dir/"Notifications_DEMO.png"));master_window.notification_popup.hide()
        diag=LiveDiagnosticsDialog(w);diag.show();diag._probe_worker(True,True);QApplication.processEvents();diag.grab().save(str(args.output_dir/"Diagnostics_DEMO.png"))
        result["active_instances"]=diag.active_table.rowCount();result["unread_notifications"]=master_window._notification_count
        diag.close();master_window._rc4_exit_confirmed=True;master_window.close()
        w.tabs.setCurrentIndex(0)
        w.order_filter_date.setDateRange(QDate(2026,10,1),QDate(2026,10,9))
        QTimer.singleShot(500,capture_orders)
    except Exception as exc:result["errors"].append(str(exc))
    if result["errors"]:finish()

def capture_orders():
    w=QApplication.instance()._smartorder_main_window
    if w._orders_running:
        QTimer.singleShot(100,capture_orders);return
    try:
        QApplication.processEvents()
        w.grab().save(str(args.output_dir/"Orders_List_Dark_DEMO.png"))
        w.theme.setChecked(False);QApplication.processEvents()
        w.grab().save(str(args.output_dir/"Orders_List_Light_DEMO.png"))
        result['caption_buttons']=len(w.titlebar.controls)
        result['visible_orders']=w.orders_table.rowCount()
        result['order_column_widths']=[w.orders_table.columnWidth(i) for i in range(w.orders_table.columnCount())]
    except Exception as exc:result["errors"].append(str(exc))
    finish()

def finish():
    app=QApplication.instance();w=getattr(app,"_smartorder_main_window",None)
    if w:w._rc4_exit_confirmed=True;w.close()
    app.quit()

code=entry.main()
(args.output_dir/"smoke_result.json").write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
print(json.dumps(result,ensure_ascii=False));temp.cleanup()
sys.exit(1 if result["errors"] or code else 0)
