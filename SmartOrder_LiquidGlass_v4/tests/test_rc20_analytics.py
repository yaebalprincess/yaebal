from datetime import date
from decimal import Decimal
from openpyxl import load_workbook
import pytest
from smartorder.domain import OrderLine
from smartorder.analytics import build_report,filter_report
from smartorder.analytics_breakdown import minmax_rows,calendar_months,grouped
from smartorder.excel import export_order_xlsx,read_simple_xlsx
from smartorder.db import DatabaseError
from test_rc19_workshops_analytics import system,order


def row(day,employee,weight,ident,shift='Дневная'):
    return dict(date=day,employee_key=employee,employee=employee,workshop_key='packaging',workshop='Упаковка',order_id=ident,shift=shift,assigned=True,code='001',work='Сыр',hours=2,fixed_kg=weight,actual=0,actual_hours=0,fixed_pay=weight*2,actual_pay=0,total_pay=weight*2)


def test_unique_workers_and_shifts_do_not_count_works_or_documents_twice():
    rows=[row('2026-01-01','A',10,1,'Ночная'),row('2026-01-01','A',20,2,'Ночная'),row('2026-01-02','A',0,3),row('2026-01-02','B',40,3),row('2026-02-01','A',50,4)]
    total=grouped(rows,[])[0]
    assert total['employees']==2 and total['employee_shifts']==4 and total['fixed_kg']==120
    months=calendar_months(rows,date(2026,1,1),date(2026,3,31))
    assert [(r['employees'],r['employee_shifts']) for r in months]==[(2,3),(1,1),(0,0)]
    limits=minmax_rows(rows,[])[0]
    assert limits['day_min_kg']==30 and limits['day_min_kg_when']=='2026-01-01'
    assert limits['day_max_kg']==50 and limits['day_max_kg_when']=='2026-02-01'
    assert limits['month_min_kg']==50 and limits['month_max_kg']==70
    assert limits['day_min_people']==1 and limits['day_max_people']==2
    assert '2026-03' not in limits['month_min_kg_when']


def test_full_calendar_year_is_distinct_from_selected_production_period(system,tmp_path):
    manager,admin=system
    db,first,line,m,d=order(manager,admin,'packaging',10,day='07-01-2026')
    line.fixed_boxes=Decimal(15);db.save_order(admin,'07-02-2026','Ночная',m,d,[line])
    r=build_report(manager,admin,date(2026,1,1),date(2026,1,31))
    assert r.employees[0]['fixed_kg']==20 and len(r.details)==1
    assert len(r.annual_details)==2
    annual=r.breakdown['annual_employee_works'][0]
    assert annual['fixed_kg']==50 and annual['month_min_kg']==20 and annual['month_max_kg']==30
    out=tmp_path/'year.xlsx';from smartorder.analytics import export_report
    export_report(out,r,True);wb=load_workbook(out)
    assert 'Работы сотрудников за год' in wb.sheetnames and len(wb['Графики']._charts)==6
    assert wb['Работы сотрудников за год'].max_row==2
    assert not any('фикс' in str(c.value).lower() and 'оплата' in str(c.value).lower() for ws in wb for c in ws[1])


def test_fact_hours_units_and_combined_payment_leave_original_components(system,tmp_path):
    manager,admin=system
    db,first,line,m,d=order(manager,admin,'packaging',10)
    line.actual_value=Decimal(3)
    ident=db.save_order(admin,'07-10-2026','Дневная',m,d,[line],parent_id=first)
    r=build_report(manager,admin,date(2026,10,1),date(2026,10,31))
    assert r.details[0]['actual_hours']==0 and r.details[0]['total_pay']==46
    db.set_work_fact_unit(admin,line.work_type_id,'h')
    r=build_report(manager,admin,date(2026,10,1),date(2026,10,31))
    assert r.details[0]['actual_hours']==3 and r.details[0]['total_pay']==46
    db.set_work_fact_unit(admin,line.work_type_id,'kg')
    r=build_report(manager,admin,date(2026,10,1),date(2026,10,31));assert r.details[0]['actual_hours']==0
    loaded=db.get_order(ident)['lines'][0]
    assert loaded.fixed_payment==Decimal(40) and loaded.actual_payment==Decimal(6) and loaded.total_payment==Decimal(46)
    out=tmp_path/'order.xlsx';export_order_xlsx(out,db.get_order(ident));rows=read_simple_xlsx(out)
    header=next(r for r in rows if 'ФИО работника' in r)
    assert 'ФИКС Оплата' not in header and header[-1]=='ФАКТ Оплата' and len(header)==10
    data=next(r for r in rows if r and r[0]==line.employee_name)
    assert Decimal(data[-1])==46


def test_slice_filters_dept_code_master_shift_and_recomputes_unique_people(system):
    manager,admin=system
    db,first,line,m,d=order(manager,admin,'packaging',10)
    other_work=db.add_work_type(admin,'Сыр Б','002','2')
    other=OrderLine(line.employee_id,line.employee_name,other_work,'Сыр Б','002',Decimal(2),Decimal(3),Decimal(5),Decimal(2))
    db.save_order(admin,'08-10-2026','Ночная',m,d,[other])
    r=build_report(manager,admin,date(2026,10,1),date(2026,10,31))
    sliced=filter_report(r,{'code':'002','shift':'Ночная','master':('packaging',m),'department':('packaging',r.details[0]['department'])})
    assert len(sliced.orders)==1 and sliced.employees[0]['fixed_kg']==10
    assert sliced.breakdown['attendance_months'][0]['employees']==1
    assert sliced.breakdown['master_shifts'][0]['shift']=='Ночная'
    assert all(x['code']=='002' for x in sliced.annual_details)


def test_production_worker_has_no_application_session_and_unit_edit_scope(system):
    manager,admin=system
    db,_,line,_,_=order(manager,admin,'packaging')
    r=build_report(manager,admin,date(2026,1,1),date(2026,12,31))
    assert r.employees and r.sessions==[]
    manager.auth.add_user(admin,'master','password123','Мастер Упаковка')
    user=manager.auth.authenticate('master','password123')
    with pytest.raises(DatabaseError):manager.database('packaging',user).set_work_fact_unit(user,line.work_type_id,'h')


def test_legacy_snapshot_fallback_rounds_each_payment_component(system):
    manager,admin=system
    db,first,line,m,d=order(manager,admin,'packaging')
    line.price=Decimal('.333');line.fixed_boxes=Decimal(3);line.fixed_weight=Decimal('.05');line.actual_value=Decimal('.1')
    ident=db.save_order(admin,'07-10-2026','Дневная',m,d,[line],parent_id=first)
    with db.backend.write_conn() as conn:
        conn.execute('UPDATE work_order_layout_rows SET fixed_payment=NULL,actual_payment=NULL WHERE order_id=?',(ident,))
    r=build_report(manager,admin,date(2026,10,1),date(2026,10,31))
    assert r.details[0]['fixed_pay']==.05 and r.details[0]['actual_pay']==.03
    assert r.details[0]['total_pay']==pytest.approx(.08)
