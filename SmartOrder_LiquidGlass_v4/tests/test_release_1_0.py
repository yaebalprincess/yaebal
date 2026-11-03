"""Regression checks for real synchronization, durable files and responsive UI."""
import json
import subprocess
import sys
import time
from datetime import date
from pathlib import Path
from decimal import Decimal

import pytest
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import QWidget, QScrollArea, QTextBrowser, QTableWidget
from smartorder.analytics import build_report
from smartorder.analytics_ui import fill_table, table
from smartorder.config import SettingsStore, UiSettings
from smartorder.db import Database, StaleOrderError, DatabaseError
from smartorder.desktop_live import load_order_file
from smartorder.news_ui import NewsDialog
from smartorder.order_files import ArchivePublisher, file_path, read_order_file, encode_order
from smartorder.workshops import WorkshopManager
from test_rc19_ui import app, ui, drain
from test_rc19_workshops_analytics import order


def test_file_outbox_retry_atomic_versions_and_authoritative_open(ui,monkeypatch,tmp_path):
    create,manager,admin,_=ui
    monkeypatch.setattr(manager.archive_publisher,'request',lambda *args:None)
    db,ident,line,m,d=order(manager,admin,'packaging',day='08-10-2026')
    # Use a raw backend so this test controls publication timing precisely.
    raw=db.backend
    next_id=raw.save_order(admin,'08-10-2026','Ночная',m,d,[line],comment='Правка',parent_id=ident)
    publisher=ArchivePublisher(manager.root)
    import smartorder.order_files as files
    original=files.atomic_write
    with monkeypatch.context() as patch:
        patch.setattr(files,'atomic_write',lambda *args:(_ for _ in ()).throw(PermissionError('test unavailable share')))
        with pytest.raises(PermissionError):publisher.publish_pending('packaging',raw)
    assert raw.get_order(next_id)['info']['version']=='1.1'
    publisher.publish_pending('packaging',raw)
    path=file_path(manager.root,'packaging',raw.get_order(next_id)['info'])
    assert path.relative_to(manager.root).parts==('Наряды','Упаковка','2026-10','08','Наряд № 1.1.sorder')
    payload=read_order_file(path)
    assert payload['order']['lines'][0].fixed_total==Decimal('20')
    opened=load_order_file(manager,admin,path)
    assert opened['live'] and opened['latest'] and opened['order']['info']['id']==next_id
    # A syntactically valid changed copy must never inject values into an editor.
    payload['order']['lines'][0].fixed_boxes=Decimal('999')
    copied=tmp_path/'changed.sorder'
    copied.write_bytes(encode_order('packaging',payload['order'],payload['source_uuid']))
    assert load_order_file(manager,admin,copied)['order']['lines'][0].fixed_boxes!=Decimal('999')
    old=file_path(manager.root,'packaging',raw.get_order(ident)['info'])
    result=load_order_file(manager,admin,old)
    assert not result['latest'] and result['latest_order']['info']['version']=='1.1'
    with pytest.raises(StaleOrderError):raw.save_order(admin,'08-10-2026','Ночная',m,d,[line],parent_id=ident)
    with raw.read_conn() as conn:
        assert conn.execute('SELECT COUNT(*) FROM order_file_exports WHERE published_path IS NULL').fetchone()[0]==0


def test_outbox_rolls_back_with_save_and_seeds_old_database(ui,monkeypatch):
    _,manager,admin,_=ui
    monkeypatch.setattr(manager.archive_publisher,'request',lambda *args:None)
    db,ident,line,m,d=order(manager,admin,'packaging')
    raw=db.backend
    import smartorder.order_files as files
    with monkeypatch.context() as patch:
        patch.setattr(files,'enqueue_conn',lambda *args:(_ for _ in ()).throw(RuntimeError('test rollback')))
        with pytest.raises(RuntimeError):raw.save_order(admin,'08-10-2026','Ночная',m,d,[line])
    assert len(raw.list_orders())==1
    # Simulate a database made by a pre-file release without deleting its orders.
    with raw.write_conn() as conn:conn.execute('DROP TABLE order_file_exports')
    publisher=ArchivePublisher(manager.root)
    publisher.publish_pending('packaging',raw)
    assert read_order_file(file_path(manager.root,'packaging',raw.get_order(ident)['info']))['order']['info']['id']==ident


def test_order_file_role_scope_is_enforced(ui):
    _,manager,admin,_=ui
    db,ident,*_=order(manager,admin,'smoking')
    ArchivePublisher(manager.root).publish_pending('smoking',db.backend)
    path=file_path(manager.root,'smoking',db.get_order(ident)['info'])
    manager.auth.add_user(admin,'packing_user','password123','Мастер Упаковка')
    user=manager.auth.authenticate('packing_user','password123')
    with pytest.raises(DatabaseError):load_order_file(manager,user,path)


def test_two_independent_clients_receive_new_order_and_new_version(ui,app):
    create,manager,admin,_=ui
    first=create()
    second_manager=WorkshopManager(manager.auth,manager.root)
    from smartorder.enterprise_ui import MainWindow
    second=MainWindow(second_manager.database('packaging',admin),admin,second_manager)
    second.show()
    try:
        db,ident,line,m,d=order(manager,admin,'packaging',day=date.today().strftime('%d-%m-%Y'))
        second._rc12_watch_tick()
        drain(app,lambda:second.orders_table.rowCount()==1,timeout=8)
        assert second.orders_table.item(0,0).text()=='1'
        db.save_order(admin,date.today().strftime('%d-%m-%Y'),'Дневная',m,d,[line],comment='новая версия',parent_id=ident)
        second._rc12_watch_tick()
        drain(app,lambda:any(second.orders_table.item(i,0).text()=='1.1' for i in range(second.orders_table.rowCount())),timeout=8)
        first._rc12_watch_tick()
        drain(app,lambda:first.orders_table.rowCount()==2,timeout=8)
    finally:
        second._rc4_exit_confirmed=True;second.close();second.deleteLater()


def test_slow_network_reads_do_not_block_gui_timer(ui,app,monkeypatch):
    create,manager,admin,_=ui
    w=create()
    drain(app,lambda:not w._orders_running,timeout=5)
    backend=w.db.backend;original=backend.list_orders
    def slow(*args,**kwargs):time.sleep(.3);return original(*args,**kwargs)
    monkeypatch.setattr(backend,'list_orders',slow)
    ticks=[];timer=QTimer(w);timer.setInterval(10);timer.timeout.connect(lambda:ticks.append(time.monotonic()));timer.start()
    start=time.monotonic();w.refresh_orders();call_seconds=time.monotonic()-start
    drain(app,lambda:not w._orders_running,timeout=5)
    timer.stop()
    assert call_seconds<.15 and len(ticks)>=10


def test_dark_start_and_lazy_admin_page_are_dark_without_toggle(ui,app):
    create,manager,admin,_=ui
    SettingsStore().save(UiSettings('dark',100))
    w=create();w.tabs.setCurrentIndex(3);app.processEvents()
    assert w.ui_settings.theme=='dark'
    page=w.tabs.currentWidget();assert isinstance(page,QScrollArea)
    assert all(child.property('theme')=='dark' for child in page.findChildren(QWidget))
    image=page.viewport().grab().toImage()
    assert max(image.pixelColor(image.width()-25,15).getRgb()[:3])<120
    assert w.centralWidget().layout().contentsMargins().left()==0
    assert w.titlebar.layout().contentsMargins().right()==0


def test_large_analytics_table_is_virtual_and_tab_switch_does_not_restyle(ui,app,monkeypatch):
    create,manager,admin,_=ui
    order(manager,admin,'packaging');w=create();w.tabs.setCurrentIndex(4)
    drain(app,lambda:w.analytics and w.analytics.report)
    view=table([('work','Работа'),('fixed_kg','Килограммы')]);view.show()
    rows=[{'work':f'Работа {i}','fixed_kg':i,'order_id':i} for i in range(50000)]
    children=len(view.findChildren(QWidget));start=time.monotonic();fill_table(view,rows)
    assert time.monotonic()-start<1 and view.rowCount()==50000
    assert view.item(49999,1).text()=='49 999' and len(view.findChildren(QWidget))==children
    calls=[];original=app.setStyleSheet
    monkeypatch.setattr(app,'setStyleSheet',lambda value:calls.append(value) or original(value))
    for _ in range(10):w.tabs.setCurrentIndex(0);w.tabs.setCurrentIndex(4)
    assert not calls
    view.close();view.deleteLater()


def test_analytics_counter_is_today_even_for_other_year_and_search_is_inside_popup(ui,app):
    create,manager,admin,_=ui
    today=date.today().strftime('%d-%m-%Y')
    order(manager,admin,'packaging',day=today)
    report=build_report(manager,admin,date(2025,1,1),date(2025,12,31))
    assert not report.orders and len(report.today_orders)==1 and len(report.today_details)==1
    w=create();w.tabs.setCurrentIndex(4);drain(app,lambda:w.analytics and w.analytics.report)
    page=w.analytics
    assert page.status.text().startswith('За сегодня: 1 нарядов · 1 уникальных') and 'без единицы' not in page.status.text()
    combo=page.production_filters['code'];combo.showPopup();app.processEvents()
    assert combo.search_popup.isVisible() and combo.search.isVisible()
    combo.search.setText('несуществующая работа');app.processEvents();assert combo.proxy.rowCount()==0
    combo.search.clear();assert combo.proxy.rowCount()>0
    combo.hidePopup()
    assert page.period.startDate()==page.start.date() and page.period.endDate()==page.end.date()


def test_live_plain_news_updates_two_open_windows_without_reopening(ui,app):
    create,manager,admin,_=ui
    w=create();source=manager.root/'UPDATE_NEWS.txt';source.write_text('',encoding='utf-8')
    dialogs=[NewsDialog(w,source),NewsDialog(w,source)]
    for dialog in dialogs:dialog.show();dialog.poll()
    drain(app,lambda:all(d.last_text=='' for d in dialogs))
    source.write_text('Новость <b>просто текст</b>',encoding='utf-8')
    for d in dialogs:d.poll()
    drain(app,lambda:all(d.body.toPlainText()=='Новость <b>просто текст</b>' for d in dialogs))
    temp=source.with_suffix('.tmp');temp.write_text('Изменено в Блокноте',encoding='cp1251');temp.replace(source)
    for d in dialogs:d.poll()
    drain(app,lambda:all(d.body.toPlainText()=='Изменено в Блокноте' for d in dialogs))
    for d in dialogs:d.close();d.deleteLater()


def test_second_process_passes_order_path_to_running_authenticated_window(app,tmp_path):
    from smartorder.open_requests import OpenRequestServer
    class Window:
        _file_loading=False
        def isMinimized(self):return False
        def raise_(self):pass
        def activateWindow(self):pass
        def open_order_file(self,path):received.append(path)
    received=[];old=getattr(app,'_smartorder_main_window',None);app._smartorder_main_window=Window()
    server=OpenRequestServer(app)
    path=tmp_path/'Папка с пробелом'/'Наряд № 1.sorder'
    code='from PyQt5.QtCore import QCoreApplication; from smartorder.open_requests import forward_to_running; import sys; app=QCoreApplication([]); sys.exit(0 if forward_to_running(sys.argv[1]) else 1)'
    process=subprocess.Popen([sys.executable,'-c',code,str(path)],cwd=Path(__file__).resolve().parents[1],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    try:
        drain(app,lambda:process.poll() is not None,timeout=8)
        assert process.returncode==0 and received==[str(path)]
    finally:
        if process.poll() is None:process.kill();process.wait()
        server.server.close();server.deleteLater();app._smartorder_main_window=old


def _five_client_worker(root,username,master,department,work_type,employee,barrier,queue):
    try:
        backend=Database(Path(root)/'databases'/'work_orders_ypak.db')
        manager=WorkshopManager(Database(Path(root)/'databases'/'identity.db'),Path(root))
        user=manager.auth.authenticate(username,'password123')
        from smartorder.workshops import SessionTracker
        from smartorder.domain import OrderLine
        tracker=SessionTracker(manager,user,'packaging')
        db=manager.database('packaging',user)
        barrier.wait(timeout=15)
        versions=[]
        for i in range(10):
            line=OrderLine(employee,'Сотрудник',work_type,'Работа','FIVE-001',Decimal('2.50'),Decimal('8'),Decimal('3'),Decimal('4'))
            ident=db.save_order(user,'09-10-2026','Дневная',master,department,[line],comment=username+':'+str(i))
            versions.append(db.get_order(ident)['info']['version'])
            # Read concurrently with the other four writers.
            assert db.list_orders(date='09-10-2026',limit=None)
        tracker.heartbeat(close=True)
        # Wait for this client's own background file publication before exit.
        thread=manager.archive_publisher._thread
        if thread:thread.join(8)
        queue.put({'username':username,'versions':versions,'error':''})
    except Exception as exc:queue.put({'username':username,'error':repr(exc)})


def test_five_independent_processes_save_read_and_publish_without_loss(ui):
    import multiprocessing
    _,manager,admin,_=ui
    db=manager.database('packaging',admin)
    master=db.add_employee(admin,'Мастер',True);employee=db.add_employee(admin,'Сотрудник',False)
    department=db.add_department(admin,'Производство');work_type=db.add_work_type(admin,'Работа','FIVE-001','2.50')
    names=['client_'+str(i) for i in range(5)]
    for name in names:manager.auth.add_user(admin,name,'password123','Мастер Упаковка')
    context=multiprocessing.get_context('spawn');barrier=context.Barrier(5);queue=context.Queue()
    processes=[context.Process(target=_five_client_worker,args=(str(manager.root),name,master,department,work_type,employee,barrier,queue)) for name in names]
    for process in processes:process.start()
    try:
        results=[queue.get(timeout=35) for _ in processes]
        for process in processes:process.join(5)
        assert all(p.exitcode==0 for p in processes)
        assert all(not r['error'] for r in results),results
        versions=[version for r in results for version in r['versions']]
        assert len(versions)==len(set(versions))==50
        orders=db.list_orders(limit=None)
        assert len(orders)==50 and all(len(db.get_order(r['id'])['lines'])==1 for r in orders)
        ArchivePublisher(manager.root).publish_pending('packaging',db.backend)
        copies=list((manager.root/'Наряды'/'Упаковка').rglob('*.sorder'))
        assert len(copies)==50
        assert {read_order_file(p)['order']['info']['version'] for p in copies}==set(versions)
        with manager.auth.read_conn() as conn:
            rows=conn.execute('SELECT username,ended_at FROM app_sessions').fetchall()
            assert {r[0] for r in rows}==set(names) and all(r[1] for r in rows)
    finally:
        for process in processes:
            if process.is_alive():process.terminate();process.join(5)


def test_double_click_file_flow_opens_editor_saves_revision_and_exports(ui,app,monkeypatch,tmp_path):
    from PyQt5.QtWidgets import QFileDialog,QMessageBox,QDialog
    from smartorder.heavy_ui import WorkOrderDialog
    from openpyxl import load_workbook
    create,manager,admin,_=ui
    db,ident,line,m,d=order(manager,admin,'packaging')
    ArchivePublisher(manager.root).publish_pending('packaging',db.backend)
    path=file_path(manager.root,'packaging',db.get_order(ident)['info'])
    w=create();seen=[];target=tmp_path/'from_editor.xlsx'
    monkeypatch.setattr(QFileDialog,'getSaveFileName',lambda *args:(str(target),'Excel (*.xlsx)'))
    monkeypatch.setattr(QMessageBox,'information',lambda *args:QMessageBox.Ok)
    import smartorder.heavy_ui as heavy_ui
    monkeypatch.setattr(heavy_ui,'info',lambda *args:QMessageBox.Ok)
    def unexpected_message(*args):
        pytest.fail(f'Unexpected editor message: {args[1:]}')
    monkeypatch.setattr(heavy_ui,'warn',unexpected_message)
    monkeypatch.setattr(heavy_ui,'error',unexpected_message)
    def edit(dialog):
        seen.append((dialog.view_only,dialog.order['info']['version']))
        dialog.comment.setText('Правка из папки нарядов')
        dialog._export_current_order()
        dialog._accept()
        return dialog.result()
    monkeypatch.setattr(WorkOrderDialog,'exec_',edit)
    w.open_order_file(path)
    drain(app,lambda:len(db.list_orders())==2,timeout=8)
    assert seen==[(False,'1')] and db.list_orders()[0]['version']=='1.1'
    book=load_workbook(target)
    assert any('ФАКТ Оплата'==cell.value for row in book.active.iter_rows() for cell in row)
    book.close()


def _five_edit_worker(path,user_data,master,department,line,ident,barrier,queue):
    from smartorder.security import SessionUser
    from smartorder.domain import OrderLine
    user=SessionUser(**user_data)
    db=Database(path)
    barrier.wait(timeout=15)
    try:
        result=db.save_order(user,'09-10-2026','Дневная',master,department,[OrderLine(**line)],comment=user.username,parent_id=ident)
        queue.put(('saved',result))
    except StaleOrderError:queue.put(('stale',None))
    except Exception as exc:queue.put(('error',repr(exc)))


def test_five_simultaneous_edits_of_one_version_keep_one_successful_revision(ui):
    import multiprocessing
    from dataclasses import asdict
    _,manager,admin,_=ui
    db,ident,line,m,d=order(manager,admin,'packaging')
    context=multiprocessing.get_context('spawn');barrier=context.Barrier(5);queue=context.Queue()
    processes=[context.Process(target=_five_edit_worker,args=(str(db.path),asdict(admin),m,d,asdict(line),ident,barrier,queue)) for _ in range(5)]
    for p in processes:p.start()
    try:
        results=[queue.get(timeout=30) for _ in processes]
        for p in processes:p.join(5)
        assert sum(r[0]=='saved' for r in results)==1 and sum(r[0]=='stale' for r in results)==4
        assert all(p.exitcode==0 for p in processes) and len(db.list_orders())==2
        assert db.list_orders()[0]['version']=='1.1'
    finally:
        for p in processes:
            if p.is_alive():p.terminate();p.join(5)
