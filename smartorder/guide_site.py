"""Build the offline help page from the printable manual and demo screenshots."""
import base64
from html import escape
import re

from .config import APP_VERSION, resource_path


SCREENSHOTS = {
    "create": ("create.jpg", "Редактор наряда. Сведения о смене сверху, работы в таблице, сохранение внизу."),
    "drafts": ("drafts.jpg", "Уведомление о черновиках. Нажмите на количество, чтобы увидеть список."),
    "versions": ("edit.jpg", "Редактор сохранённого наряда с отметкой режима в правой части шапки."),
    "analytics": ("analytics.jpg", "Аналитика. Период и фильтры над карточками отчёта, графики под итогами."),
    "support": ("training.jpg", "Обучение мастера. Номер с рябью показывает нужный элемент, следующий шаг открывается после действия."),
}


def screenshot(section):
    if section not in SCREENSHOTS:
        return ""
    filename, description = SCREENSHOTS[section]
    path = resource_path("smartorder/glass/assets/guide/" + filename)
    try:
        encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    except OSError:
        return ""
    caption = escape(description)
    return f'<figure><img src="data:image/jpeg;base64,{encoded}" loading="lazy" alt="{caption}"><figcaption>{caption}</figcaption></figure>'


def build_guide_site(reference_html):
    body = reference_html.split('<h2 id="access">', 1)[1].split('<div class="footer">', 1)[0]
    profile = reference_html.split('<h2>Изменения v7: права и персонализация</h2>', 1)[1].split('<h2>Содержание</h2>', 1)[0]
    parts = re.split(r'<h2 id="([a-z]+)">([^<]+)</h2>', '<h2 id="access">' + body)
    contents, chapters = [], []
    for section, title, text in zip(parts[1::3], parts[2::3], parts[3::3]):
        contents.append(f'<li><a href="#{section}">{title}</a></li>')
        if section == "admin":
            text += f"<details><summary>Подробнее о правах и переносе профиля</summary>{profile}</details>"
        chapters.append(f'<section class="chapter" id="{section}"><h2>{title}</h2>{screenshot(section)}{text}</section>')
    return f'''<!doctype html>
<html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Как работать в Smart Order</title>
<style>
:root {{color-scheme:light;--bg:#eaf2fa;--paper:#fff;--ink:#182e46;--muted:#4a647d;--blue:#135e9b;--edge:#cbdded;--tint:#edf6ff;}}
* {{box-sizing:border-box;}}
html {{scroll-behavior:smooth;}}
body {{margin:0;background:var(--bg);color:var(--ink);font:18px/1.65 "Segoe UI",Arial,sans-serif;}}
a {{color:var(--blue);}}
a:focus-visible {{outline:3px solid #4ea9fc;outline-offset:3px;}}
.hero {{color:#fff;background:radial-gradient(ellipse at 85% 15%,#2f72a2,transparent 55%),linear-gradient(125deg,#0c253e,#163e61 70%,#245a82);padding:64px max(24px,calc((100vw - 1240px)/2)) 54px;}}
.kicker {{font-size:13px;letter-spacing:.14em;font-weight:700;color:#b7ddff;}}
h1 {{font-size:clamp(38px,6vw,72px);line-height:1.04;letter-spacing:-.03em;margin:18px 0 20px;max-width:900px;}}
.hero p {{max-width:720px;color:#d9edff;font-size:clamp(18px,2.4vw,23px);}}
.start {{display:inline-block;border-radius:12px;background:#f5fbff;color:#123c64;text-decoration:none;padding:10px 19px;font-weight:700;margin-top:10px;}}
.page {{max-width:1280px;margin:auto;padding:28px 20px 56px;}}
.quick {{display:grid;grid-template-columns:repeat(3,1fr);gap:16px;margin-bottom:24px;}}
.quick a,.chapter,.rail {{background:var(--paper);border:1px solid var(--edge);border-radius:18px;}}
.quick a {{padding:18px 20px;text-decoration:none;}}
.quick b {{display:block;font-size:21px;color:var(--ink);}}
.quick span {{color:var(--muted);font-size:15px;}}
.layout {{display:grid;grid-template-columns:235px minmax(0,1fr);gap:24px;align-items:start;}}
.rail {{padding:20px;position:sticky;top:20px;font-size:14px;}}
.rail ul {{margin:10px 0 0;padding:0;list-style:none;}}
.rail a {{display:block;padding:5px 0;text-decoration:none;}}
.rail a:hover {{text-decoration:underline;}}
.chapter {{padding:24px clamp(18px,4vw,38px);margin-bottom:18px;scroll-margin-top:20px;overflow-wrap:anywhere;}}
.chapter:target {{border-color:#4a9de4;}}
h2 {{font-size:clamp(24px,3vw,34px);line-height:1.2;margin:4px 0 20px;}}
h3 {{font-size:21px;line-height:1.3;}}
details {{background:var(--tint);padding:12px 16px;border-radius:10px;margin-top:20px;}}
summary {{cursor:pointer;font-weight:700;}}
li {{margin:6px 0;}}
.note {{padding:14px 18px;background:var(--tint);border-left:4px solid #3d91d8;border-radius:8px;}}
table {{width:100%;border-collapse:collapse;font-size:.91em;}}
th,td {{padding:10px 12px;border:1px solid var(--edge);vertical-align:top;text-align:left;}}
th {{background:var(--tint);}}
figure {{margin:0 0 22px;overflow:hidden;border:1px solid var(--edge);border-radius:14px;background:var(--tint);}}
img {{display:block;max-width:100%;height:auto;margin:auto;}}
figcaption {{padding:10px 14px;color:var(--muted);font-size:14px;}}
footer {{color:var(--muted);font-size:14px;margin:18px 0;}}
@media (max-width:830px) {{.layout {{display:block;}} .rail {{position:static;margin-bottom:20px;}} .rail ul {{columns:2;}}}}
@media (max-width:590px) {{.quick {{grid-template-columns:1fr;}} .rail ul {{columns:1;}}}}
@media (prefers-color-scheme:dark) {{:root {{color-scheme:dark;--bg:#102237;--paper:#172d45;--ink:#edf5ff;--muted:#b3cbe1;--blue:#8acaff;--edge:#35536f;--tint:#203a55;}}}}
@media (prefers-reduced-motion:reduce) {{html {{scroll-behavior:auto;}}}}
</style></head><body>
<header class="hero" id="top"><span class="kicker">SMART ORDER · РУКОВОДСТВО · {APP_VERSION}</span>
<h1>От первой смены<br>до готового наряда</h1>
<p>Пошаговая инструкция с экранами программы. Создайте наряд, вернитесь к черновику или проверьте итог в аналитике.</p>
<a class="start" href="#create">Открыть редактор в инструкции ↓</a></header>
<div class="page"><nav class="quick" aria-label="Быстрые действия">
<a href="#create"><b>01 · Создать наряд</b><span>Смена, работы и сохранение</span></a>
<a href="#drafts"><b>02 · Найти черновик</b><span>Продолжите с того же места</span></a>
<a href="#analytics"><b>03 · Прочитать отчёт</b><span>Период, цех и показатели</span></a></nav>
<div class="layout"><nav class="rail" aria-label="Содержание"><b>Содержание</b><ul>{''.join(contents)}</ul><a href="#top">↑ К началу</a></nav>
<main>{''.join(chapters)}<footer>Smart Order · Снимки сделаны на демонстрационной базе. · <a href="#top">К началу</a></footer></main></div>
</div></body></html>'''
