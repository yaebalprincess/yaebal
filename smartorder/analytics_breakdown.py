"""RC20 production periods, work-code detail and attendance inferred from orders."""
from __future__ import annotations
from collections import defaultdict
from datetime import date

METRIC_KEYS=("hours","fixed_kg","actual","actual_hours","fixed_pay","actual_pay","total_pay")


def grouped(rows, fields):
    out={}
    for r in rows:
        key=tuple(r.get(f,"") for f in fields)
        g=out.setdefault(key,{**{f:r.get(f,"") for f in fields},**dict.fromkeys(METRIC_KEYS,0.0),"_orders":set(),"_employees":set(),"_visits":set()})
        for f in METRIC_KEYS:g[f]+=r.get(f,0)
        g["_orders"].add((r["workshop_key"],r["order_id"]))
        if r.get("assigned",True) and r.get("employee_key") not in (None,"", "без назначения"):
            g["_employees"].add(r["employee_key"])
            g["_visits"].add((r["employee_key"],r["workshop_key"],r["date"],r.get("shift","")))
    for g in out.values():
        g["orders"]=len(g.pop("_orders"));g["employees"]=len(g.pop("_employees"));g["employee_shifts"]=len(g.pop("_visits"))
    return sorted(out.values(),key=lambda r:tuple(str(r.get(f,"")) for f in fields))


def period_rows(rows,grain="day",fields=()):
    length={"day":10,"month":7,"year":4,"period":0}[grain]
    prepared=[{**r,"period":r["date"][:length] if length else "Выбранный период"} for r in rows]
    return grouped(prepared,[*fields,"period"])


def _where_tied(items,key,value):
    labels=sorted(r["period"] for r in items if r[key]==value)
    return "; ".join(labels[:12])+(f"; ещё {len(labels)-12}" if len(labels)>12 else "")


def minmax_rows(rows,fields):
    buckets=defaultdict(list)
    for r in rows:buckets[tuple(r.get(f,"") for f in fields)].append(r)
    result=[]
    for items in buckets.values():
        total=grouped(items,fields)[0]
        for grain in ("day","month","year"):
            periods=period_rows(items,grain)
            for metric,short in (("fixed_kg","kg"),("employees","people"),("hours","hours"),("total_pay","pay")):
                low=min(p[metric] for p in periods);high=max(p[metric] for p in periods)
                total[f"{grain}_min_{short}"]=low;total[f"{grain}_max_{short}"]=high
                total[f"{grain}_min_{short}_when"]=_where_tied(periods,metric,low);total[f"{grain}_max_{short}_when"]=_where_tied(periods,metric,high)
        result.append(total)
    return sorted(result,key=lambda r:tuple(str(r.get(f,"")) for f in fields))


def calendar_months(rows,start,end):
    """Zero means no attendance registered in the selected order-date slice."""
    existing={r["period"]:r for r in period_rows(rows,"month")}
    current=date(start.year,start.month,1);out=[]
    while current<=end:
        label=current.strftime("%Y-%m")
        out.append(existing.get(label,{"period":label,"orders":0,"employees":0,"employee_shifts":0,**dict.fromkeys(METRIC_KEYS,0.0)}))
        current=date(current.year+1,1,1) if current.month==12 else date(current.year,current.month+1,1)
    return out


def employee_departments(rows):
    fields=["employee_key","employee","workshop_key","workshop","department"]
    return sorted(grouped(rows,fields),key=lambda r:(r["employee_key"],-r["employee_shifts"],-r["orders"],r["department"]))


def breakdowns(details,annual,start,end):
    work_fields=["workshop_key","workshop","code","work"]
    annual_with_year=[{**r,"year":r["date"][:4]} for r in annual]
    return {
        "months":period_rows(details,"month"),"years":period_rows(details,"year"),
        "work_codes":grouped(details,work_fields),
        "shop_limits":minmax_rows(details,["workshop_key","workshop"]),
        "department_limits":minmax_rows(details,["workshop_key","workshop","department"]),
        "work_limits":minmax_rows(details,work_fields),
        "department_work_limits":minmax_rows(details,["workshop_key","workshop","department","code","work"]),
        "master_limits":minmax_rows(details,["workshop_key","workshop","master_id","master"]),
        "master_shifts":minmax_rows(details,["workshop_key","workshop","master_id","master","shift"]),
        "master_work_limits":minmax_rows(details,["workshop_key","workshop","master_id","master","code","work"]),
        "attendance_months":calendar_months(details,start,end),
        "attendance_days":period_rows(details,"day",["workshop_key","workshop","shift"]),
        "employee_departments":employee_departments(annual),
        "annual_employee_works":minmax_rows(annual_with_year,["employee_key","employee","workshop_key","workshop","year","code","work"]),
        "monthly_employee_works":minmax_rows([{**r,"month":r["date"][:7]} for r in annual],["employee_key","employee","workshop_key","workshop","month","code","work"]),
    }
