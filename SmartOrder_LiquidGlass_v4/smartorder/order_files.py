"""Durable order files. SQLite is authoritative; the outbox survives a crash.

File writes happen after the business transaction and are retried by any client.
Concurrent publishers replace identical files atomically; no Excel is generated
on the save path. A file can never inject edits into a live order.
"""
from __future__ import annotations
import hashlib
import json
import logging
import os
import threading
import uuid
from dataclasses import asdict
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from .domain import OrderLine
from .workshops import WORKSHOPS

FORMAT = "SmartOrder.Order"


def ensure_outbox(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS order_file_exports (
        order_id INTEGER PRIMARY KEY,source_uuid TEXT NOT NULL UNIQUE,
        published_path TEXT,FOREIGN KEY(order_id) REFERENCES work_orders(id) ON DELETE CASCADE)""")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_order_file_pending ON order_file_exports(order_id) WHERE published_path IS NULL")


def enqueue_conn(conn, order_id):
    ensure_outbox(conn)
    conn.execute("INSERT OR IGNORE INTO order_file_exports(order_id,source_uuid) VALUES(?,?)", (order_id, uuid.uuid4().hex))


def file_path(root, workshop, info):
    day = datetime.strptime(info["order_date"], "%d-%m-%Y")
    version = str(info["version"])
    if not version or any(c not in "0123456789." for c in version):raise ValueError("Некорректный номер наряда")
    return Path(root)/"Наряды"/WORKSHOPS[workshop]/day.strftime("%Y-%m")/day.strftime("%d")/("Наряд № "+version+".sorder")


def encode_order(workshop, order, source_uuid):
    payload = {"format":FORMAT,"format_version":1,"workshop":workshop,"source_uuid":source_uuid,
        "order":{"info":order["info"],"lines":[asdict(line) for line in order["lines"]]}}
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str, separators=(",",":"))
    payload["sha256"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return json.dumps(payload, ensure_ascii=False, indent=2, default=str).encode("utf-8")


def read_order_file(path):
    path = Path(path)
    if path.suffix.casefold() != ".sorder":raise ValueError("Выберите файл наряда .sorder")
    with path.open("rb") as stream:raw = stream.read(20*1024*1024+1)
    if len(raw)>20*1024*1024:raise ValueError("Файл наряда больше 20 МБ")
    payload = json.loads(raw.decode("utf-8-sig"))
    if payload.get("format") != FORMAT or payload.get("format_version") != 1:raise ValueError("Неизвестный формат наряда")
    checksum = payload.pop("sha256", "")
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str, separators=(",",":"))
    if checksum != hashlib.sha256(canonical.encode("utf-8")).hexdigest():raise ValueError("Файл наряда повреждён")
    if payload.get("workshop") not in WORKSHOPS:raise ValueError("Неизвестный цех в файле")
    token = payload.get("source_uuid", "")
    if not isinstance(token,str) or len(token)!=32 or any(c not in "0123456789abcdef" for c in token):raise ValueError("Некорректный идентификатор наряда")
    order = payload["order"]
    info = order["info"]
    if not isinstance(info.get("id"),int) or info["id"]<1:raise ValueError("Некорректный номер записи")
    file_path(Path("."),payload["workshop"],info)
    if not isinstance(order["lines"],list) or len(order["lines"])>10000:raise ValueError("Слишком много строк наряда")
    lines = []
    for data in order["lines"]:
        data = dict(data)
        for field in ("price","hours","fixed_boxes","fixed_weight","actual_value"):
            value = data.get(field)
            if value is not None:
                value = Decimal(str(value))
                if not value.is_finite() or abs(value)>Decimal("1e15"):raise ValueError("Некорректное числовое значение")
                data[field] = value
        for field in ("employee_name","work_name","work_code"):
            if not isinstance(data.get(field,""),str):raise ValueError("Некорректная строка наряда")
        for field in ("employee_id","work_type_id"):
            if data.get(field) is not None and not isinstance(data[field],int):raise ValueError("Некорректный идентификатор строки")
        lines.append(OrderLine(**data))
    order["lines"] = lines
    return payload


def atomic_write(path, raw):
    path.parent.mkdir(parents=True,exist_ok=True)
    temp = path.with_name(path.name+"."+uuid.uuid4().hex+".tmp")
    try:
        with temp.open("wb") as stream:
            stream.write(raw);stream.flush();os.fsync(stream.fileno())
        os.replace(temp,path)
    finally:temp.unlink(missing_ok=True)


class ArchivePublisher:
    def __init__(self, root):
        self.root = Path(root)
        self._lock = threading.Lock()
        self._pending, self._seeded = {}, set()
        self._thread = None

    def request(self, key, backend):
        with self._lock:
            self._pending[key] = backend
            if self._thread is None:
                self._thread = threading.Thread(target=self._loop,name="SmartOrderOrderFiles",daemon=True)
                self._thread.start()

    def _loop(self):
        while True:
            with self._lock:
                if not self._pending:self._thread=None;return
                key = next(iter(self._pending));backend=self._pending.pop(key)
            try:self.publish_pending(key,backend)
            except Exception:logging.exception("Не удалось обновить папки нарядов цеха %s; повтор при синхронизации",key)

    def publish_pending(self,key,backend):
        ident = str(backend.path)
        if ident not in self._seeded:
            with backend.write_conn() as conn:
                ensure_outbox(conn)
                ids = [r[0] for r in conn.execute("SELECT id FROM work_orders WHERE COALESCE(status,'saved')='saved' AND id NOT IN (SELECT order_id FROM order_file_exports)")]
                for order_id in ids:enqueue_conn(conn,order_id)
            self._seeded.add(ident)
            # Repair missing files on startup; moved server roots are supported.
            with backend.read_conn() as conn:
                paths=list(conn.execute("SELECT order_id,published_path FROM order_file_exports WHERE published_path IS NOT NULL"))
            missing=[r[0] for r in paths if not Path(r[1]).is_file() or not str(r[1]).startswith(str(self.root))]
            if missing:
                with backend.write_conn() as conn:
                    conn.executemany("UPDATE order_file_exports SET published_path=NULL WHERE order_id=?",[(i,) for i in missing])
        published = 0
        while True:
            with backend.read_conn() as conn:
                jobs=list(conn.execute("SELECT order_id,source_uuid FROM order_file_exports WHERE published_path IS NULL ORDER BY order_id LIMIT 30"))
            if not jobs:return published
            done=[]
            for order_id,token in jobs:
                order = backend.get_order(order_id)
                if order is None:continue
                path = file_path(self.root,key,order["info"])
                atomic_write(path,encode_order(key,order,token))
                done.append((str(path),order_id,token));published+=1
            if not done:return published
            with backend.write_conn() as conn:
                conn.executemany("UPDATE order_file_exports SET published_path=? WHERE order_id=? AND source_uuid=?",done)
