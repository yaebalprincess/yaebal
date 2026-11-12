from __future__ import annotations

import re
import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from xml.sax.saxutils import escape

from .domain import OrderLine, fmt

_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
_DOC_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"


def _col_name(index: int) -> str:
    result = ""
    while index:
        index, rem = divmod(index - 1, 26)
        result = chr(65 + rem) + result
    return result


def _cell(ref: str, value, style: int = 0, number: bool = False) -> str:
    style_attr = f' s="{style}"' if style else ""
    if value is None or value == "":
        return f'<c r="{ref}"{style_attr}/>'
    if number:
        return f'<c r="{ref}"{style_attr}><v>{escape(str(value))}</v></c>'
    return f'<c r="{ref}" t="inlineStr"{style_attr}><is><t>{escape(str(value))}</t></is></c>'


def order_rows(order: dict):
    info = order["info"]
    lines: list[OrderLine] = order["lines"]
    headers = [
        "ФИО работника", "Часы работы", "Работы", "Код работы", "Стоимость в рублях",
        "ФИКС Кол-во коробок", "ФИКС Вес коробок кг.", "ФИКС Итоговый вес",
        "ФАКТ часы/кг/шт", "ФАКТ Оплата",
    ]
    row_records: list[tuple[list, tuple[int | None, str]]] = []
    totals = [0.0] * len(headers)
    for line in lines:
        fixed_payment = line.fixed_payment
        fact_payment = line.total_payment
        row = [
            line.employee_name,
            fmt(line.hours),
            line.work_name,
            line.work_code,
            fmt(line.price),
            fmt(line.fixed_boxes),
            fmt(line.fixed_weight),
            fmt(line.fixed_total),
            fmt(line.actual_value),
            fmt(fact_payment, 2),
        ]
        employee_key = (line.employee_id, str(line.employee_name or ""))
        row_records.append((row, employee_key))
        for idx in (5, 6, 7, 8, 9):
            try:
                totals[idx] += float(str(row[idx]).replace(",", ".")) if row[idx] != "" else 0.0
            except Exception:
                pass

    # Department names no longer change the calculation/export mode. The
    # separate-worker behavior is an explicit checkbox in the editor; old
    # orders without that flag use the regular layout.
    grouped_display = bool(info.get("separate_worker", False))
    subtotal_group = grouped_display

    export_rows: list[tuple[list, bool]] = []
    if subtotal_group:
        current_key = None
        current_name = ""
        group: list[list] = []

        def flush_group():
            nonlocal group, current_key, current_name
            if not group:
                return
            export_rows.extend((row, False) for row in group)
            has_employee = bool(current_key and (current_key[0] is not None or str(current_key[1] or "").strip()))
            if has_employee:
                subtotal = [""] * len(headers)
                subtotal[0] = f"ИТОГО по {current_name or 'сотруднику'}:"
                for idx in (5, 6, 7, 8, 9):
                    total = 0.0
                    has_value = False
                    for row in group:
                        try:
                            if row[idx] != "":
                                total += float(str(row[idx]).replace(",", "."))
                                has_value = True
                        except Exception:
                            pass
                    if has_value:
                        subtotal[idx] = round(total, 4)
                export_rows.append((subtotal, True))
            group = []

        for source_row, key in row_records:
            row = list(source_row)
            if current_key is None:
                current_key = key
                current_name = str(key[1] or "")
            elif key != current_key:
                flush_group()
                current_key = key
                current_name = str(key[1] or "")
            if grouped_display and group and key == current_key and (key[0] is not None or str(key[1] or "").strip()):
                row[0] = ""
            group.append(row)
        flush_group()
    else:
        last_key = None
        for source_row, key in row_records:
            row = list(source_row)
            has_employee = key[0] is not None or bool(str(key[1] or "").strip())
            if grouped_display and has_employee and last_key == key:
                row[0] = ""
            export_rows.append((row, False))
            last_key = key if has_employee else None

    return headers, export_rows, totals


def export_order_xlsx(path: str | Path, order: dict) -> Path:
    path = Path(path)
    if path.suffix.lower() != ".xlsx":
        path = path.with_suffix(".xlsx")
    path.parent.mkdir(parents=True, exist_ok=True)

    info = order["info"]
    headers, export_rows, totals = order_rows(order)

    sheet_rows: list[str] = []
    r = 1
    sheet_rows.append(f'<row r="{r}" ht="26"><c r="A{r}" t="inlineStr" s="1"><is><t>НАРЯД НА СДЕЛЬНУЮ РАБОТУ № {escape(str(info.get("version", "")))}</t></is></c></row>')
    r += 2
    meta = [
        ("Дата наряда", info.get("order_date", ""), "Тип смены", info.get("shift_type", "")),
        ("Мастер", info.get("master", ""), "Подразделение", info.get("department", "")),
        ("Дата регистрации", info.get("registration_date", ""), "Редактор", info.get("edited_by", "")),
        ("Комментарий", info.get("comment", ""), "", ""),
    ]
    for left_name, left_value, right_name, right_value in meta:
        cells = [
            _cell(f"A{r}", left_name, 2), _cell(f"B{r}", left_value, 3),
            _cell(f"F{r}", right_name, 2), _cell(f"G{r}", right_value, 3),
        ]
        sheet_rows.append(f'<row r="{r}">{"".join(cells)}</row>')
        r += 1
    r += 1
    header_row = r
    sheet_rows.append(
        f'<row r="{r}" ht="44">' + "".join(_cell(f"{_col_name(i+1)}{r}", h, 4) for i, h in enumerate(headers)) + "</row>"
    )
    r += 1
    for row, is_subtotal in export_rows:
        cells = []
        for i, value in enumerate(row):
            numeric = i in {1, 4, 5, 6, 7, 8, 9} and value != "" and i != 0
            if is_subtotal:
                cells.append(_cell(f"{_col_name(i+1)}{r}", value, 7, numeric))
            else:
                cells.append(_cell(f"{_col_name(i+1)}{r}", value, 5 if not numeric else 6, numeric))
        sheet_rows.append(f'<row r="{r}">{"".join(cells)}</row>')
        r += 1
    total_cells = []
    for i in range(len(headers)):
        ref = f"{_col_name(i+1)}{r}"
        if i == 0:
            total_cells.append(_cell(ref, "ИТОГО:", 7))
        elif i in {5, 6, 7, 8, 9}:
            total_cells.append(_cell(ref, round(totals[i], 4), 7, True))
        else:
            total_cells.append(_cell(ref, "", 7))
    sheet_rows.append(f'<row r="{r}">{"".join(total_cells)}</row>')

    widths = [28, 12, 36, 16, 16, 18, 18, 18, 18, 18]
    cols = "".join(f'<col min="{i+1}" max="{i+1}" width="{w}" customWidth="1"/>' for i, w in enumerate(widths))
    sheet = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="{_NS}"><cols>{cols}</cols><sheetData>{''.join(sheet_rows)}</sheetData>
<mergeCells count="1"><mergeCell ref="A1:J1"/></mergeCells>
<pageMargins left="0.3" right="0.3" top="0.5" bottom="0.5" header="0.2" footer="0.2"/>
<pageSetup orientation="landscape" fitToWidth="1" fitToHeight="0"/>
</worksheet>'''

    styles = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="{_NS}">
<fonts count="4"><font><sz val="11"/><name val="Calibri"/></font><font><b/><sz val="16"/><name val="Calibri"/></font><font><b/><sz val="11"/></font><font><b/><sz val="10"/></font></fonts>
<fills count="3"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill><fill><patternFill patternType="solid"><fgColor rgb="FFEDEDF2"/><bgColor indexed="64"/></patternFill></fill></fills>
<borders count="2"><border/><border><left style="thin"/><right style="thin"/><top style="thin"/><bottom style="thin"/></border></borders>
<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
<cellXfs count="8">
<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>
<xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0"><alignment horizontal="center"/></xf>
<xf numFmtId="0" fontId="2" fillId="0" borderId="0" xfId="0"/>
<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>
<xf numFmtId="0" fontId="3" fillId="2" borderId="1" xfId="0"><alignment horizontal="center" vertical="center" wrapText="1"/></xf>
<xf numFmtId="0" fontId="0" fillId="0" borderId="1" xfId="0"><alignment vertical="center" wrapText="1"/></xf>
<xf numFmtId="4" fontId="0" fillId="0" borderId="1" xfId="0"><alignment horizontal="right" vertical="center"/></xf>
<xf numFmtId="4" fontId="2" fillId="2" borderId="1" xfId="0"><alignment horizontal="right" vertical="center"/></xf>
</cellXfs>
</styleSheet>'''

    workbook = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="{_NS}" xmlns:r="{_DOC_REL_NS}"><sheets><sheet name="Наряд" sheetId="1" r:id="rId1"/></sheets></workbook>'''
    workbook_rels = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="{_REL_NS}"><Relationship Id="rId1" Type="{_DOC_REL_NS}/worksheet" Target="worksheets/sheet1.xml"/><Relationship Id="rId2" Type="{_DOC_REL_NS}/styles" Target="styles.xml"/></Relationships>'''
    rels = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="{_REL_NS}"><Relationship Id="rId1" Type="{_DOC_REL_NS}/officeDocument" Target="xl/workbook.xml"/></Relationships>'''
    content_types = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/><Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/><Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/></Types>'''
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    core = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"><dc:creator>SmartOrder</dc:creator><dcterms:created xsi:type="dcterms:W3CDTF">{now}</dcterms:created></cp:coreProperties>'''

    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", content_types)
        zf.writestr("_rels/.rels", rels)
        zf.writestr("docProps/core.xml", core)
        zf.writestr("xl/workbook.xml", workbook)
        zf.writestr("xl/_rels/workbook.xml.rels", workbook_rels)
        zf.writestr("xl/styles.xml", styles)
        zf.writestr("xl/worksheets/sheet1.xml", sheet)
    return path


def _cell_col(ref: str) -> int:
    letters = re.match(r"[A-Z]+", ref or "")
    if not letters:
        return 0
    n = 0
    for char in letters.group(0):
        n = n * 26 + (ord(char) - 64)
    return n - 1


def read_simple_xlsx(path: str | Path) -> list[list[str]]:
    """Reads first sheet using stdlib only. Enough for simple import tables."""
    path = Path(path)
    # Imports are user-selected files. Bound both the container and the
    # resulting XML before handing it to ElementTree so a crafted XLSX/ZIP
    # cannot consume unbounded memory or CPU (zip-bomb/huge XML payload).
    _MAX_INPUT_BYTES = 20 * 1024 * 1024
    _MAX_UNCOMPRESSED_BYTES = 50 * 1024 * 1024
    _MAX_ENTRY_BYTES = 20 * 1024 * 1024
    _MAX_ENTRIES = 256
    try:
        if not path.is_file() or path.stat().st_size > _MAX_INPUT_BYTES:
            raise ValueError("Файл импорта слишком большой (максимум 20 МБ)")
    except OSError as exc:
        raise ValueError("Не удалось прочитать файл импорта") from exc
    if path.suffix.lower() == ".csv":
        import csv
        with path.open("r", encoding="utf-8-sig", newline="") as fh:
            result = []
            for row in csv.reader(fh, delimiter=";"):
                if len(result) >= 100_000 or len(row) > 256 or any(len(str(cell)) > 16_384 for cell in row):
                    raise ValueError("Файл импорта содержит слишком много данных")
                result.append(list(row))
            return result
    try:
        zf_ctx = zipfile.ZipFile(path, "r")
    except (OSError, zipfile.BadZipFile) as exc:
        raise ValueError("Файл XLSX повреждён или имеет неверный формат") from exc
    with zf_ctx as zf:
        infos = zf.infolist()
        if len(infos) > _MAX_ENTRIES:
            raise ValueError("Файл XLSX содержит слишком много элементов")
        total_uncompressed = 0
        for info in infos:
            # Reject encrypted entries and suspiciously large expansion before
            # reading any member. XLSX imports only need a few small XML parts.
            if info.flag_bits & 0x1 or info.file_size > _MAX_ENTRY_BYTES:
                raise ValueError("Файл XLSX содержит недопустимый или слишком большой элемент")
            total_uncompressed += max(0, int(info.file_size))
            if total_uncompressed > _MAX_UNCOMPRESSED_BYTES:
                raise ValueError("Распакованный XLSX слишком большой")
        shared: list[str] = []
        if "xl/sharedStrings.xml" in zf.namelist():
            shared_xml = zf.read("xl/sharedStrings.xml")
            if len(shared_xml) > _MAX_ENTRY_BYTES:
                raise ValueError("Слишком большой список строк XLSX")
            root = ET.fromstring(shared_xml)
            for si in root.findall(f"{{{_NS}}}si"):
                shared.append("".join(t.text or "" for t in si.iter(f"{{{_NS}}}t")))
        sheet_name = "xl/worksheets/sheet1.xml"
        try:
            sheet_xml = zf.read(sheet_name)
        except KeyError as exc:
            raise ValueError("В XLSX отсутствует первый лист") from exc
        if len(sheet_xml) > _MAX_ENTRY_BYTES:
            raise ValueError("Слишком большой первый лист XLSX")
        root = ET.fromstring(sheet_xml)
        result: list[list[str]] = []
        for row in root.findall(f".//{{{_NS}}}row"):
            if len(result) >= 100_000:
                raise ValueError("Файл импорта содержит слишком много строк")
            values: dict[int, str] = {}
            for cell in row.findall(f"{{{_NS}}}c"):
                if len(values) >= 256:
                    raise ValueError("Строка XLSX содержит слишком много столбцов")
                col = _cell_col(cell.attrib.get("r", "A1"))
                cell_type = cell.attrib.get("t")
                if cell_type == "inlineStr":
                    value = "".join(t.text or "" for t in cell.iter(f"{{{_NS}}}t"))
                else:
                    v = cell.find(f"{{{_NS}}}v")
                    raw = v.text if v is not None and v.text is not None else ""
                    if cell_type == "s" and raw.isdigit() and int(raw) < len(shared):
                        value = shared[int(raw)]
                    else:
                        value = raw
                if len(value) > 16_384:
                    raise ValueError("Ячейка XLSX содержит слишком длинный текст")
                values[col] = value
            if values:
                width = max(values) + 1
                result.append([values.get(i, "") for i in range(width)])
        return result
