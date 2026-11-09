"""An illustrated explanation rendered inside the analytics dialog."""
from html import escape
import re

from .analytics import METHODOLOGY
from .liquid_style import colors


def methodology_html(report, dark=False):
    palette = colors(dark)
    card = "#203a55" if dark else "#e8f4ff"
    hero = "#143554"
    rules = report.methodology if report is not None else METHODOLOGY
    paragraphs = "".join(f"<p>{escape(part)}</p>" for part in re.split(r"(?<=\.)\s+(?=[А-ЯЁ])", rules))
    period = ""
    if report is not None:
        period = f'<p>Текущий отчёт · {report.start:%d.%m.%Y} — {report.end:%d.%m.%Y}</p>'
    return f'''<!doctype html><html lang="ru"><head><meta charset="utf-8">
<style>
body {{color:{palette['ink']}; font-family:"Segoe UI",sans-serif; font-size:12pt;}}
h2 {{color:{palette['blue']}; font-size:18pt;}}
p {{margin:10px 0;}}
a {{color:{palette['blue']};}}
</style></head><body>
<table width="100%" cellpadding="18" bgcolor="{hero}"><tr><td>
<p style="color:#9ed8ff;font-size:10pt;">SMART ORDER · АНАЛИТИКА</p>
<p style="color:#ffffff;font-size:27pt;font-weight:700;">Как читать отчёт</p>
<p style="color:#d9edff;">Проследите путь от строки наряда до итогов по цехам и сотрудникам.</p>
</td></tr></table>
{period}
<p><a href="#weight">Вес и доли</a> &nbsp; · &nbsp; <a href="#attendance">Выходы сотрудников</a> &nbsp; · &nbsp; <a href="#rules">Правила отчёта</a></p>

<h2><a name="weight"></a>1. От коробок к доле цеха</h2>
<p>В примере упаковка записала <b>24 коробки по 2,5 кг</b>. В отчёт попадут <b>60 кг ФИКС</b>.
Если цех сушки за тот же период записал 40 кг, общий вес составит 100 кг.</p>
<table width="100%" cellspacing="0" cellpadding="12"><tr>
<td width="60%" bgcolor="#196397"><span style="color:white;font-weight:700;">Упаковка · 60 кг · 60%</span></td>
<td width="40%" bgcolor="#5756a1"><span style="color:white;font-weight:700;">Сушка · 40 кг · 40%</span></td>
</tr></table>
<p style="color:{palette['muted']};font-size:10pt;">Демонстрационные числа. В отчёте кольцо делит итоговый вес между выбранными цехами.</p>

<h2><a name="attendance"></a>2. Строки, люди и смены</h2>
<table width="100%" cellpadding="12" cellspacing="5"><tr>
<td width="50%" bgcolor="{card}"><b>Один выход</b><p>У сотрудника три работы за одну дневную смену в одном цехе. В отчёте это один выход.</p></td>
<td width="50%" bgcolor="{card}"><b>Два выхода</b><p>Тот же сотрудник отработал две разные смены. В отчёте это два выхода и один уникальный сотрудник.</p></td>
</tr></table>
<p>Время открытой программы смотрите отдельно в разделе «Логины / сессии программы».</p>

<h2>3. Сверка с нарядом</h2>
<ol><li>Выберите период и цех. Откройте «Детализация», чтобы увидеть работы и исходные наряды.</li>
<li>Сверьте номер последней сохранённой версии. Производственный итог использует её строки.</li>
<li>Для ФАКТ сверяйте единицу работы: часы, килограммы и штуки читаются отдельно.</li></ol>
<h2><a name="rules"></a>Правила и границы данных</h2>
{paragraphs}
</body></html>'''
