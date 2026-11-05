"""Read-only synchronization work, kept off the GUI thread."""
import json
from pathlib import Path
from PyQt5.QtCore import QObject, pyqtSignal


class DesktopSignals(QObject):
    section = pyqtSignal(str, int, object, str)
    orders = pyqtSignal(int, object, str)
    history = pyqtSignal(int, object, str)
    watch = pyqtSignal(object, str)
    order_file = pyqtSignal(object, str)


def drafts_folder(root, key):
    return (Path(root) if key == "packaging" else Path(root)/"workshops"/key)/"drafts"


def load_orders(db, root, key, local_drafts, query):
    rows = db.list_orders(date_from=query["start"],date_to=query["end"],master_id=query["master"],department_id=query["department"],shift=query["shift"],limit=None)
    display = [(int(r[0]),str(r[1]),str(r[2]),str(r[3]),str(r[4] or ""),str(r[5] or ""),str(r[6] or ""),False) for r in rows]
    masters = {int(r[0]):str(r[1]) for r in db.get_employees(True)}
    deps = {int(r[0]):str(r[1]) for r in db.get_departments()}
    paths = set(drafts_folder(root,key).glob("*.json")) | set(Path(local_drafts).glob("*.json"))
    from datetime import datetime
    for path in sorted(paths):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            raw_day = str(data.get("order_date",""))
            day = datetime.strptime(raw_day,"%d-%m-%Y").date().isoformat()
            if not query["start"]<=day<=query["end"]:continue
            if query["shift"] and data.get("shift_type")!=query["shift"]:continue
            if query["master"] is not None and data.get("master_id")!=query["master"]:continue
            if query["department"] is not None and data.get("department_id")!=query["department"]:continue
            owner = str(data.get("draft_owner_username") or "")
            display.insert(0,(str(path),"Черновик"+(" · "+owner if owner else ""),raw_day,str(data.get("shift_type","")),masters.get(data.get("master_id"),""),deps.get(data.get("department_id"),""),str(data.get("updated_at","")),True))
        except (ValueError,OSError,TypeError):continue
    return display


def load_order_file(manager,user,path):
    from .order_files import read_order_file
    from .security import Permission
    payload = read_order_file(path)
    manager.require(user,Permission.ORDERS_VIEW)
    db = manager.database(payload["workshop"],user)
    saved = None
    with db.read_conn() as conn:
        exists = conn.execute("SELECT 1 FROM sqlite_master WHERE name='order_file_exports'").fetchone()
        if exists:
            row = conn.execute("SELECT order_id FROM order_file_exports WHERE source_uuid=?",(payload["source_uuid"],)).fetchone()
            if row:saved = db.get_order(row[0])
    if saved is not None:
        # Always display authoritative database data; a modified snapshot can
        # never replace employee names, prices or quantities in an edited order.
        if str(saved["info"]["version"])!=str(payload["order"]["info"]["version"]):
            raise ValueError("Версия файла не соответствует записи в базе")
    latest = db.is_latest_order(saved["info"]["id"]) if saved else False
    latest_order = None
    if saved and not latest:
        history = db.order_history(saved["info"]["id"])
        if history:latest_order = db.get_order(history[0]["id"])
    return {"db":db,"order":saved or payload["order"],"live":saved is not None,"latest":latest,"latest_order":latest_order}
