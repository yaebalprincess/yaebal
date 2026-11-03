"""Production analytics from immutable order snapshots, never Excel formula guesses."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field, replace
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
import sqlite3

from .domain import dec, money
from .analytics_breakdown import grouped, breakdowns, METRIC_KEYS
from .security import SessionUser, Permission, ANALYTICS_ROLES, split_roles
from .workshops import WORKSHOPS, WorkshopManager


def canonical_name(name):
    return " ".join(str(name or "").casefold().replace("ё", "е").split())


def number(value):
    return float(dec(value) or Decimal(0))


def order_day(text):
    for fmt in ("%d-%m-%Y", "%Y-%m-%d", "%d-%m-%Y %H:%M:%S"):
        try:
            return datetime.strptime(str(text), fmt).date()
        except ValueError:
            pass
    return None


def _row_metrics(r):
    fixed = number(r.get("fixed_total")) if r.get("fixed_total") is not None else number(r.get("fixed_boxes"))*number(r.get("fixed_weight"))
    price = dec(r.get("price_snapshot")) or Decimal(0)
    fixed_decimal = dec(r.get("fixed_total")) if r.get("fixed_total") is not None else (dec(r.get("fixed_boxes")) or Decimal(0))*(dec(r.get("fixed_weight")) or Decimal(0))
    metrics = {
        "hours": number(r.get("hours")), "fixed_kg": fixed,
        "actual": number(r.get("actual_value")),
        "actual_hours": number(r.get("actual_value")) if r.get("actual_unit", "unknown") == "h" else 0,
        "fixed_pay": number(r.get("fixed_payment")) if r.get("fixed_payment") is not None else float(money(fixed_decimal*price)),
        "actual_pay": number(r.get("actual_payment")) if r.get("actual_payment") is not None else float(money((dec(r.get("actual_value")) or Decimal(0))*price)),
    }
    metrics["total_pay"] = metrics["fixed_pay"] + metrics["actual_pay"]
    return metrics



def aggregate(rows, fields):
    return sorted(grouped(rows,fields),key=lambda r:(-r["fixed_kg"],-r["hours"],str(r)))


def employee_aggregates(rows):
    names={r["employee_key"]:r["employee"] for r in rows}
    return [{**r,"employee":names[r["employee_key"]]} for r in aggregate(rows,["employee_key"])]


@dataclass
class AnalyticsReport:
    start: date
    end: date
    workshop: str | None
    details: list[dict]
    employees: list[dict]
    workshops: list[dict]
    departments: list[dict]
    masters: list[dict]
    accounts: list[dict]
    sessions: list[dict]
    daily: list[dict]
    orders: list[dict]
    missing_workshops: list[str]
    methodology: str
    annual_details: list[dict] = field(default_factory=list)
    breakdown: dict = field(default_factory=dict)
    events: list[dict] = field(default_factory=list)
    selection: str = ""
    today_details: list[dict] = field(default_factory=list)
    today_orders: list[dict] = field(default_factory=list)
    totals: dict = field(default_factory=dict)
    filter_choices: dict = field(default_factory=dict)


METHODOLOGY = (
    "Выход сотрудника — уникальная комбинация ФИО + дата + смена + цех из наряда, а не сеанс программы. "
    "Уникальные сотрудники за месяц/год/период не равны сумме сотрудников отдельных дней. "
    "Min/Max рассчитываются только по дням, месяцам и годам с нарядами; даты без записей не означают нулевое производство. "
    "Годовые работы сотрудников охватывают полные календарные годы, затронутые фильтром периода, и помечены отдельно. "
    "ФИКС вес используется как показатель сырья/выработки; отдельного расхода входного сырья в старой базе нет. "
    "Вид продукции определяется работой и её кодом. ФАКТ часы включают только работы с выбранной единицей «часы»; кг/шт и неуказанные единицы исключены из часов. Настройка «Единицы ФАКТ» трактует исторические значения выбранного кода, не меняя их и оплату. "
    "Производственные показатели рассчитаны по последней сохранённой версии каждого наряда. "
    "Наряды отбираются по дате наряда; создание и правки — по времени сохранения версии. "
    "Мастер наряда — сотрудник, выбранный в документе; автор создания или правки определяется отдельно по логину. "
    "Время работы сотрудника — сумма введённых часов строк, без оценки присутствия или простоев. "
    "ФИКС — кг; ФАКТ может быть часами, кг или штуками: итог ФАКТ сравнивайте только внутри одного вида работы. "
    "ФАКТ Оплата = оплата ФИКС + оплата ФАКТ по строкам; исходные компоненты сохранены в базе. "
    "Работы без сотрудника отмечены как «Без назначения». Между цехами сотрудники сопоставляются по полному ФИО: "
    "совпадающие ФИО нужно проверять. Профиль показывает измеренные показатели, без оценок личности. "
    "Сессия измеряет время открытого приложения, включая бездействие; при аварии учитывается только время до "
    "последнего heartbeat (до 60 секунд потери). Фильтр дат для сессий использует UTC, для нарядов — дату документа. "
    "Длительность сессий в выбранном цехе — время посещения этого цеха. История до обновления не восстанавливается. "
    "Данные из архивных снимков и удалённые политикой хранения наряды в отчёт не входят. "
    "Каждый цех читается в согласованной транзакции, общей транзакции между базами нет."
)


def _snapshot(path: Path):
    # Preserve UNC compatibility: native sqlite path, no file://authority URI.
    conn = sqlite3.connect(str(path), timeout=4)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA query_only=ON")
        conn.execute("BEGIN")
        orders = [dict(r) for r in conn.execute("""SELECT wo.*,e.name AS master,d.name AS department
            FROM work_orders wo LEFT JOIN employees e ON e.id=wo.master_id
            LEFT JOIN departments d ON d.id=wo.department_id""")]
        layout = [dict(r) for r in conn.execute("SELECT * FROM work_order_layout_rows ORDER BY order_id,row_index")]
        has_layout = {r["order_id"] for r in layout}
        old = [dict(r) for r in conn.execute("""SELECT i.*,e.name AS employee_name_snapshot,
            COALESCE(i.work_name_snapshot,w.name) AS resolved_work_name,
            COALESCE(i.work_code_snapshot,w.code) AS resolved_work_code,
            COALESCE(i.price_snapshot,w.price) AS resolved_price
            FROM work_order_items i LEFT JOIN employees e ON e.id=i.employee_id
            LEFT JOIN work_types w ON w.id=i.work_type_id ORDER BY i.order_id,i.id""")]
        for r in old:
            if r["order_id"] not in has_layout:
                r.update(work_name_snapshot=r["resolved_work_name"], work_code_snapshot=r["resolved_work_code"], price_snapshot=r["resolved_price"])
                layout.append(r)
        units = {r[0].removeprefix("rc20_fact_unit_"):r[1] for r in conn.execute("SELECT key,value FROM db_meta WHERE key LIKE 'rc20_fact_unit_%'")}
        for r in layout:r["actual_unit"] = units.get(str(r.get("work_type_id")), "unknown")
        return orders, layout
    finally:
        conn.close()


def report_choices(rows):
    names=defaultdict(set)
    for row in rows:names[row['code']].add(row['work'])
    return {
        'department':[(WORKSHOPS[k]+' · '+name,(k,name)) for k,name in sorted({(r['workshop_key'],r['department']) for r in rows})],
        'code':[(code+' · '+' / '.join(sorted(values)),code) for code,values in sorted(names.items()) if code],
        'master':[(name+' · '+WORKSHOPS[k],(k,ident)) for k,ident,name in sorted({(r['workshop_key'],r['master_id'],r['master']) for r in rows},key=str)],
        'shift':[(shift,shift) for shift in sorted({r['shift'] for r in rows})]}


def report_totals(details,orders,today_details,today_orders):
    totals=grouped(details,[])
    today=grouped(today_details,[])
    result=totals[0] if totals else dict.fromkeys(('orders','employees','hours','fixed_kg','actual_hours','total_pay'),0)
    result['orders']=len(orders)
    result['today_orders']=len(today_orders);result['today_employees']=today[0]['employees'] if today else 0
    return result


def build_report(manager: WorkshopManager, user: SessionUser, start: date, end: date, workshop=None) -> AnalyticsReport:
    manager.require(user, Permission.ANALYTICS_VIEW)
    if not any(role in ANALYTICS_ROLES for role in split_roles(user.role)):
        raise PermissionError("Аналитика доступна администратору, бухгалтеру и экономисту")
    if start > end:
        raise ValueError("Дата начала позже даты окончания")
    keys = [workshop] if workshop else list(WORKSHOPS)
    if any(k not in WORKSHOPS for k in keys):
        raise ValueError("Неизвестный цех")
    details, annual_details, order_records, missing = [], [], [], []
    today_details,today_orders=[],[]
    master_events, account_events, events = {}, {}, []
    for key in keys:
        path = manager.path_for(key)
        if not path.exists():
            missing.append(WORKSHOPS[key])
            continue
        try:
            orders, layout = _snapshot(path)
        except Exception as exc:
            raise RuntimeError(f"Не удалось прочитать цех «{WORKSHOPS[key]}»: {exc}") from exc
        rows_by_order = defaultdict(list)
        for row in layout:rows_by_order[row["order_id"]].append(row)
        latest = {}
        creators = {}
        for o in orders:
            base, _, rev = str(o["version"]).partition(".")
            if o.get("parent_id") is None and not rev:creators[base]=o.get("edited_by") or "Неизвестный автор"
            rank = (int(rev) if rev.isdigit() else 0, int(o["id"]))
            if base not in latest or rank > latest[base][0]:
                latest[base] = (rank, o)
            event_day = order_day(o.get("registration_date"))
            if event_day and start <= event_day <= end:
                events.append({"workshop_key":key,"workshop":WORKSHOPS[key],"master_id":o.get("master_id"),"master":o.get("master") or "Удалённый мастер","department":o.get("department") or "Удалённое подразделение","shift":o.get("shift_type") or "Не указана","username":o.get("edited_by") or "Неизвестный автор (старые данные)","created":not (o.get("parent_id") is not None or "." in str(o["version"])),"codes":{str(r.get("work_code_snapshot") or "") for r in rows_by_order[o["id"]]}})
                mkey = (key, o["master_id"])
                event = master_events.setdefault(mkey,{"workshop_key":key,"workshop":WORKSHOPS[key],"master":o.get("master") or "Удалённый мастер","master_id":o.get("master_id"),"created":0,"edits":0})
                event["edits" if o.get("parent_id") is not None or "." in str(o["version"]) else "created"] += 1
                username = o.get("edited_by") or "Неизвестный автор (старые данные)"
                a = account_events.setdefault(username, {"username":username,"created":0,"edits":0})
                a["edits" if o.get("parent_id") is not None or "." in str(o["version"]) else "created"] += 1
        yearly = {o["id"]:o for _,o in latest.values() if (d:=order_day(o["order_date"])) and start.year<=d.year<=end.year}
        todays = {o["id"]:o for _,o in latest.values() if order_day(o["order_date"])==date.today()}
        today_orders.extend({**o,"workshop_key":key,"workshop":WORKSHOPS[key]} for o in todays.values())
        selected = {ident:o for ident,o in yearly.items() if start<=order_day(o["order_date"])<=end}
        for o in selected.values():
            order_records.append({**o,"workshop_key":key,"workshop":WORKSHOPS[key]})
        for r in layout:
            o = yearly.get(r["order_id"]) or todays.get(r["order_id"])
            if not o:
                continue
            employee = str(r.get("employee_name_snapshot") or "Без назначения")
            detail = {"workshop_key":key,"workshop":WORKSHOPS[key],"order_id":o["id"],"version":o["version"],
                "date":order_day(o["order_date"]).isoformat(),"master":o.get("master") or "Удалённый мастер",
                "department":o.get("department") or "Удалённое подразделение",
                "department_id":o.get("department_id"),"master_id":o.get("master_id"),"shift":o.get("shift_type") or "Не указана",
                "creator":creators.get(str(o["version"]).partition(".")[0],"Неизвестный автор"),
                "assigned":employee!="Без назначения",
                "employee_id":r.get("employee_id"),"employee":employee,"employee_key":canonical_name(employee),
                "work":str(r.get("work_name_snapshot") or "Без работы"),"code":str(r.get("work_code_snapshot") or ""),
                "work_type_id":r.get("work_type_id"),"actual_unit":r.get("actual_unit", "unknown"),
                **_row_metrics(r)}
            if r["order_id"] in yearly:annual_details.append(detail)
            if r["order_id"] in todays:today_details.append(detail)
            if r["order_id"] in selected:details.append(detail)
    sessions = session_rows(manager, start, end, workshop)
    accounts = {**{a["username"]:a for a in session_summary(sessions)}, **{}}
    for name,a in account_events.items():
        accounts.setdefault(name, {"username":name,"sessions":0,"total_seconds":0,"longest_seconds":0,"shortest_seconds":0,"last_seconds":0,"last_started":""}).update(a)
    for a in accounts.values():
        a.setdefault("created",0); a.setdefault("edits",0)
    return AnalyticsReport(start,end,workshop,details,employee_aggregates(details),
        aggregate(details,["workshop_key","workshop"]), aggregate(details,["workshop_key","workshop","department"]),
        list(master_events.values()),list(accounts.values()),sessions,aggregate(details,["date"]),order_records,missing,METHODOLOGY,annual_details,breakdowns(details,annual_details,start,end),events,today_details=today_details,today_orders=today_orders,totals=report_totals(details,order_records,today_details,today_orders),filter_choices=report_choices(annual_details or details))


def matches_filters(row,filters):
    return ((not filters.get("department") or (row.get("workshop_key"),row.get("department"))==tuple(filters["department"]))
        and (not filters.get("code") or row.get("code")==filters["code"] or filters["code"] in row.get("codes",set()))
        and (not filters.get("master") or (row.get("workshop_key"),row.get("master_id"))==tuple(filters["master"]))
        and (not filters.get("shift") or row.get("shift")==filters["shift"]))


def filter_report(report,filters):
    if not any(filters.values()):return report
    details=[r for r in report.details if matches_filters(r,filters)]
    annual=[r for r in report.annual_details if matches_filters(r,filters)]
    order_keys={(r["workshop_key"],r["order_id"]) for r in details}
    masters={};accounts={r["username"]:r for r in session_summary(report.sessions)}
    events=[r for r in report.events if matches_filters(r,filters)]
    for e in events:
        m=masters.setdefault((e["workshop_key"],e["master_id"]),{k:e[k] for k in ("workshop_key","workshop","master_id","master")}|{"created":0,"edits":0})
        m["created" if e["created"] else "edits"]+=1
        a=accounts.setdefault(e["username"],{"username":e["username"]})
        a["created" if e["created"] else "edits"]=a.get("created" if e["created"] else "edits",0)+1
    for a in accounts.values():
        for field in ("created","edits","sessions","total_seconds","longest_seconds","shortest_seconds","last_seconds"):a.setdefault(field,0)
    description="; ".join(f"{field}: {value}" for field,value in filters.items() if value)
    today_details=[r for r in report.today_details if matches_filters(r,filters)]
    today_ids={(r['workshop_key'],r['order_id']) for r in today_details}
    today_orders=[o for o in report.today_orders if (o['workshop_key'],o['id']) in today_ids]
    orders=[o for o in report.orders if (o['workshop_key'],o['id']) in order_keys]
    return replace(report,selection=description,details=details,annual_details=annual,employees=employee_aggregates(details),workshops=aggregate(details,['workshop_key','workshop']),departments=aggregate(details,['workshop_key','workshop','department']),daily=aggregate(details,['date']),orders=orders,masters=list(masters.values()),accounts=list(accounts.values()),breakdown=breakdowns(details,annual,report.start,report.end),events=events,today_details=today_details,today_orders=today_orders,totals=report_totals(details,orders,today_details,today_orders))


def session_rows(manager, start, end, workshop=None):
    begin = datetime.combine(start, datetime.min.time(), timezone.utc)
    finish = datetime.combine(end+timedelta(days=1), datetime.min.time(), timezone.utc)
    clauses="v.started_at<? AND COALESCE(v.ended_at,v.heartbeat_at)>=?"
    parameters=[finish.isoformat(timespec="seconds"),begin.isoformat(timespec="seconds")]
    if workshop:clauses+=" AND v.workshop=?";parameters.append(workshop)
    with manager.auth.read_conn() as conn:
        rows = [dict(r) for r in conn.execute("""SELECT s.id,s.username,s.role,s.started_at AS session_started,
            s.ended_at AS session_ended,s.heartbeat_at AS session_heartbeat,s.duration_seconds AS session_seconds,
            v.workshop,v.started_at,v.ended_at,v.heartbeat_at,v.duration_seconds
            FROM app_sessions s JOIN app_session_segments v ON v.session_id=s.id WHERE """+clauses,parameters)]
    result = []
    for r in rows:
        if workshop and r["workshop"]!=workshop:
            continue
        left = datetime.fromisoformat(r["started_at"])
        right = datetime.fromisoformat(r["ended_at"] or r["heartbeat_at"])
        if right<begin or left>=finish:
            continue
        # Stored monotonic duration is authoritative; proportionally clip the visit.
        wall = max(0,(right-left).total_seconds())
        overlap = max(0,(min(right,finish)-max(left,begin)).total_seconds())
        clipped = r["duration_seconds"]*(overlap/wall) if wall else r["duration_seconds"]
        stale = datetime.now(timezone.utc)-datetime.fromisoformat(r["session_heartbeat"]) > timedelta(seconds=150)
        result.append({**r,"workshop_name":WORKSHOPS.get(r["workshop"],r["workshop"]),
            "seconds_in_period":clipped,"state":"Завершена" if r["session_ended"] else "Прервана / нет связи" if stale else "Открыта"})
    return result


def session_summary(rows):
    visits = {}
    for r in rows:
        s = visits.setdefault((r["username"],r["id"]),{"username":r["username"],"seconds":0.0,"started":r["session_started"],"state":r["state"]})
        s["seconds"] += r["seconds_in_period"]
    by_user = defaultdict(list)
    for s in visits.values():by_user[s["username"]].append(s)
    out=[]
    for name,items in by_user.items():
        completed=[s["seconds"] for s in items if s["state"]!="Открыта"]
        last=max(items,key=lambda s:s["started"])
        out.append({"username":name,"sessions":len(items),"total_seconds":sum(s["seconds"] for s in items),
            "longest_seconds":max(completed,default=0),"shortest_seconds":min(completed,default=0),
            "last_seconds":last["seconds"],"last_started":last["started"],"last_state":last["state"]})
    return out


def export_report(path: Path, report: AnalyticsReport, charts=True):
    from openpyxl import Workbook
    from openpyxl.chart import BarChart, LineChart, RadarChart, Reference
    from openpyxl.styles import Font, PatternFill, Alignment
    from openpyxl.utils import get_column_letter
    import os, tempfile
    wb=Workbook();wb.remove(wb.active)
    def sheet(title, columns, rows):
        ws=wb.create_sheet(title);ws.append([label for _,label in columns])
        for r in rows:
            # Force untrusted names/comments to Excel strings, preventing formula execution.
            for col,(key,_) in enumerate(columns,1):
                value=r.get(key,"")
                cell=ws.cell(ws.max_row+1 if col==1 else ws.max_row,col,value)
                if isinstance(value,str):cell.data_type="s"
        ws.freeze_panes="A2";ws.auto_filter.ref=ws.dimensions
        for c in ws[1]:c.font=Font(color="FFFFFF",bold=True);c.fill=PatternFill("solid",fgColor="18324D");c.alignment=Alignment(wrap_text=True)
        for i,(_,label) in enumerate(columns,1):
            ws.column_dimensions[get_column_letter(i)].width=min(48,max(17,len(label)+3))
        for row in ws.iter_rows(min_row=2):
            for c in row:
                if isinstance(c.value,(float,int)):c.number_format="#,##0.00"
                if c.row%2==0:c.fill=PatternFill("solid",fgColor="EEF5FB")
        return ws
    metrics=[("orders","Наряды"),("hours","Часы работы"),("fixed_kg","ФИКС Итоговый вес, кг"),("actual_hours","ФАКТ часы"),("total_pay","ФАКТ Оплата")]
    summary=sheet("Цеха",[("workshop","Цех"),*metrics],report.workshops)
    employees=sheet("Сотрудники",[("employee","ФИО"),*metrics],report.employees)
    sheet("Подразделения",[("workshop","Цех"),("department","Подразделение"),*metrics],report.departments)
    sheet("Мастера",[("workshop","Цех"),("master","Мастер наряда"),("created","Наряды мастера"),("edits","Правки нарядов")],report.masters)
    sheet("Пользователи",[("username","Логин"),("created","Создал"),("edits","Изменил"),("sessions","Сессии"),("total_seconds","Всего, сек"),("longest_seconds","Длинная, сек"),("shortest_seconds","Короткая, сек"),("last_seconds","Последняя, сек"),("last_started","Начало последней, UTC"),("last_state","Статус последней")],report.accounts)
    sheet("Сессии",[("username","Логин"),("role","Роль"),("id","ID сеанса"),("workshop_name","Цех"),("session_started","Начало сеанса, UTC"),("started_at","Начало посещения, UTC"),("heartbeat_at","Последняя связь, UTC"),("ended_at","Конец посещения, UTC"),("seconds_in_period","В цехе за период, сек"),("state","Статус")],report.sessions)
    sheet("Детализация",[("workshop","Цех"),("version","Наряд"),("date","Дата"),("employee","ФИО"),("employee_id","Локальный ID"),("department","Подразделение"),("master","Мастер"),("work","Работа"),("code","Код"),("hours","Часы работы"),("fixed_kg","ФИКС, кг"),("actual_hours","ФАКТ часы"),("total_pay","ФАКТ Оплата"),("actual","ФАКТ исходное значение"),("actual_unit","Единица ФАКТ"),("shift","Смена"),("creator","Автор создания")],report.details)
    daily=sheet("По дням",[("date","Дата"),*metrics],sorted(report.daily,key=lambda r:r["date"]))
    sheet("Методика",[("text","Правила расчёта")],[{"text":f"Период: {report.start} — {report.end}; цех: {WORKSHOPS.get(report.workshop,'Все цеха')}"},{"text":report.methodology},{"text":"Дополнительный срез: "+report.selection},{"text":"Не созданы базы: "+", ".join(report.missing_workshops)}])
    limits=[]
    for grain,title in (("day","день"),("month","месяц"),("year","год")):
        limits.extend([(f"{grain}_min_kg",f"Min кг/{title}"),(f"{grain}_min_kg_when",f"Периоды Min кг/{title}"),(f"{grain}_max_kg",f"Max кг/{title}"),(f"{grain}_max_kg_when",f"Периоды Max кг/{title}")])
    people_limits=[]
    for grain,title in (("day","день"),("month","месяц")):
        people_limits.extend([(f"{grain}_min_people",f"Min сотрудников/{title}"),(f"{grain}_min_people_when",f"Когда Min сотрудников/{title}"),(f"{grain}_max_people",f"Max сотрудников/{title}"),(f"{grain}_max_people_when",f"Когда Max сотрудников/{title}")])
    b=report.breakdown or breakdowns(report.details,report.annual_details,report.start,report.end)
    base=[("workshop","Цех")];work=[("code","Код работы"),("work","Работа / вид продукции")]
    workforce=sheet("Выходы по месяцам",[("period","Месяц"),("employees","Уникальные сотрудники"),("employee_shifts","Выходы на смены"),*metrics],b["attendance_months"])
    sheet("Выходы на смены",[*base,("period","Дата"),("shift","Смена"),("employees","Уникальные сотрудники"),("employee_shifts","Выходы"),*metrics],b["attendance_days"])
    sheet("По годам",[("period","Год в выбранном периоде"),*metrics,("employees","Уникальные сотрудники")],b["years"])
    sheet("MinMax цехов",[*base,*metrics,("employees","Уникальные сотрудники"),*limits,*people_limits],b["shop_limits"])
    sheet("MinMax подразделений",[*base,("department","Подразделение"),*metrics,*limits],b["department_limits"])
    sheet("MinMax работ",[*base,*work,*metrics,*limits],b["work_limits"])
    sheet("Работы подразделений",[*base,("department","Подразделение"),*work,*metrics,*limits],b["department_work_limits"])
    sheet("Мастера смены",[*base,("master","Мастер в наряде"),("shift","Смена"),*metrics,*limits,*people_limits],b["master_shifts"])
    sheet("Мастера работы",[*base,("master","Мастер в наряде"),*work,*metrics,*limits,*people_limits],b["master_work_limits"])
    sheet("Работы сотрудников за год",[("year","Полный календарный год"),("employee","Сотрудник"),*base,*work,*metrics,*limits],b["annual_employee_works"])
    sheet("Работы сотрудников по месяцам",[("month","Месяц календарного года"),("employee","Сотрудник"),*base,*work,*metrics,*limits[:4]],b["monthly_employee_works"])
    sheet("Подразделения сотрудников",[("employee","Сотрудник"),*base,("department","Подразделение"),("employee_shifts","Смен с этим подразделением"),("orders","Наряды"),("fixed_kg","ФИКС, кг")],b["employee_departments"])
    if charts:
        graph=wb.create_sheet("Графики")
        for ws,cls,col,title,pos in [(summary,BarChart,4,"ФИКС по цехам, кг","A1"),(daily,LineChart,4,"ФИКС по дням, кг","A18"),(daily,LineChart,3,"Введённые часы по дням","L18"),(employees,BarChart,3,"Часы сотрудников","L1")]:
            if ws.max_row<2:continue
            c=cls();c.title=title;c.style=13;c.width=24;c.height=10
            c.add_data(Reference(ws,min_col=col,min_row=1,max_row=ws.max_row),titles_from_data=True)
            c.set_categories(Reference(ws,min_col=1,min_row=2,max_row=ws.max_row));graph.add_chart(c,pos)
        if workforce.max_row>1:
            c=BarChart();c.title="Уникальные сотрудники по месяцам";c.style=13;c.width=24;c.height=10
            c.add_data(Reference(workforce,min_col=2,min_row=1,max_row=workforce.max_row),titles_from_data=True);c.set_categories(Reference(workforce,min_col=1,min_row=2,max_row=workforce.max_row));graph.add_chart(c,"L35")
        radar=sheet("Профиль 5 осей",[("metric","Показатель"),("value","Доля ведущего цеха, %")],[])
        for field,label in metrics:
            vals=[r[field] for r in report.workshops];radar.append([label,100*max(vals,default=0)/sum(vals) if sum(vals) else 0])
        c=RadarChart();c.type="filled";c.title="Пять показателей: доля ведущего цеха";c.style=13
        c.add_data(Reference(radar,min_col=2,min_row=1,max_row=6),titles_from_data=True);c.set_categories(Reference(radar,min_col=1,min_row=2,max_row=6));graph.add_chart(c,"A35")
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    fd,tmp=tempfile.mkstemp(prefix=".smartorder-",suffix=".xlsx",dir=str(path.parent));os.close(fd)
    try:wb.save(tmp);os.replace(tmp,path)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)
