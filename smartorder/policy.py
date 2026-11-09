from __future__ import annotations
from pathlib import Path
from .config import local_root
SOFTWARE_USAGE_POLICY_HTML = r"""<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<title>Положение об использовании ПО SmartOrder</title>
<style>
    body { font-family: Arial, sans-serif; max-width: 920px; margin: 40px auto; padding: 0 28px; color: #1d1d1f; line-height: 1.55; }
    h1 { font-size: 24px; margin-bottom: 24px; }
    h2 { font-size: 18px; margin-top: 24px; color: #0A84FF; }
    p { margin: 8px 0; }
    ul { margin-top: 8px; }
    .footer { margin-top: 36px; padding-top: 18px; border-top: 1px solid #d2d2d7; }
    .note { color: #6e6e73; font-size: 13px; }
</style>
</head>
<body>
<h1>Положение об использовании ПО</h1>
<h2>1. Общие положения</h2>
<p>Программный продукт «SmartOrder» (далее – SmartOrder) создан авторами Pestretsov.A.A и Шилова А.А. в рамках выполнения трудовых обязанностей перед «ООО ТАМБОВСКИЙ МОЛОЧНЫЙ ЗАВОД» и в соответствии со ст. 1295 Гражданского кодекса РФ признается служебным произведением.</p>
<h2>2. Правообладатель</h2>
<p>Исключительное право на SmartOrder во всем объеме (включая исходный код, исполняемые файлы, базы данных и графические элементы) принадлежит работодателю – «ООО ТАМБОСКИЙ МОЛОЧНЫЙ ЗАВОД» (далее – Правообладатель).</p>
<p>Авторство (право признаваться создателями) сохраняется за Pestretsov.A.A и Шилова А.А.</p>
<h2>3. Целевое назначение</h2>
<p>SmartOrder создан исключительно для внутренних производственных нужд Правообладателя и предназначена для использования в технологических процессах на заводе.</p>
<h2>4. Условия использования (лицензионный режим)</h2>
<p>4.1. SmartOrder предоставляется сотрудникам Правообладателя в пользование на условиях простой (неисключительной) лицензии в пределах, необходимых для выполнения их трудовых функций.</p>
<p>4.2. Использование SmartOrder разрешается только на пк, расположенных на территории завода, и только в составе локальной вычислительной сети предприятия, не имеющей выхода в открытый Интернет (либо с ограниченным доступом).</p>
<h2>5. Запрет на распространение и передачу (абсолютный запрет)</h2>
<p>5.1. SmartOrder не принадлежит к числу свободно распространяемого ПО.</p>
<p>5.2. Любая передача SmartOrder или ее копий третьим лицам (включая аффилированные структуры, контрагентов и физических лиц) строго запрещена без письменного разрешения генерального директора Правообладателя.</p>
<p>5.3. Сотрудникам запрещается:</p>
<ul>
<li>Копировать SmartOrder на внешние носители (флеш-карты, диски, облачные хранилища) в личных целях;</li>
<li>Передавать SmartOrder по электронной почте или через мессенджеры;</li>
<li>Выносить исходные коды или исполняемые файлы за территорию завода.</li>
</ul>
<h2>6. Ответственность за нарушение</h2>
<p>Нарушение условий настоящего положения, выразившееся в несанкционированном распространении, передаче или копировании SmartOrder, влечет за собой ответственность в соответствии с Трудовым кодексом РФ (вплоть до увольнения по п.п. "в" п. 6 ч. 1 ст. 81) и Гражданским кодексом РФ (взыскание убытков и компенсации за нарушение исключительных прав в размере от 10 000 до 5 000 000 рублей согласно ст. 1301 ГК РФ).</p>
<h2>7. Срок действия исключительного права</h2>
<p>Исключительное право на SmartOrder действует в течение всей жизни автора и 70 лет после его смерти. При этом Правообладатель обязан приступить к использованию SmartOrder в течение 3 (Трех) лет с момента подписания акта приема-передачи, в противном случае право может перейти к автору в порядке, установленном п. 2 ст. 1295 ГК РФ.</p>
<div class="footer">
<p>Разработчики (Авторы): Pestretsov.A.A / Шилова А.А.</p>
<p>Дата: «»______ 2026 г.</p>
<p class="note">Для внутреннего использования. Коммерческое распространение запрещено.</p>
</div>
</body>
</html>
"""

def ensure_usage_policy_document() -> Path | None:
    try:
        docs=local_root()/"documents"; docs.mkdir(parents=True,exist_ok=True)
        path=docs/"polozhenie_ob_ispolzovanii_po_smartorder.html"
        path.write_text(SOFTWARE_USAGE_POLICY_HTML,encoding="utf-8")
        return path
    except Exception:
        return None

from .user_guide import USER_GUIDE_HTML

TROUBLESHOOTING_HTML = r"""<!doctype html>
<html lang="ru"><head><meta charset="utf-8"><title>Возможные проблемы при работе с SmartOrder V 1.0</title>
<style>
body{font-family:Arial,sans-serif;max-width:980px;margin:40px auto;padding:0 28px;color:#1d1d1f;line-height:1.55}
h1{font-size:25px}h2{font-size:18px;color:#007aff;margin-top:26px}.box{border:1px solid #d2d2d7;border-radius:12px;padding:14px 16px;margin:12px 0;background:#fafafa}.muted{color:#6e6e73}
code{background:#eee;padding:2px 5px;border-radius:4px}ul{margin-top:6px}
</style></head><body>
<h1>Возможные проблемы при работе с SmartOrder V 1.0</h1>
<p class="muted">Ниже перечислены наиболее частые ситуации и безопасные действия пользователя.</p>
<div class="box"><h2>Программа долго запускается</h2><ul><li>Запускайте SmartOrder через установленный ярлык или сетевой <code>SmartOrder.exe</code>, а не <code>SmartOrderApp.exe</code> напрямую с сетевого диска.</li><li>Дождитесь окна авторизации; первый запуск новой версии может обновлять локальный кэш.</li><li>Если задержка повторяется, откройте «Администрирование» → «Собрать логи» и передайте архив IT.</li></ul></div>
<div class="box"><h2>БД недоступна / высокий отклик БД</h2><ul><li>Проверьте подключение к локальной сети предприятия.</li><li>Нажмите «Синхронизация» во вкладке «Администрирование».</li><li>Не открывайте и не копируйте <code>work_orders.db</code> вручную во время работы пользователей.</li></ul></div>
<div class="box"><h2>Не видно наряд, черновик или действие другого пользователя</h2><ul><li>Подождите несколько секунд: открытые клиенты обновляют изменения в фоне.</li><li>При необходимости нажмите «Синхронизация».</li><li>Убедитесь, что оба ПК работают с одним и тем же сетевым корнем SmartOrder.</li></ul></div>
<div class="box"><h2>Не удаётся редактировать наряд</h2><ul><li>Наряд может быть открыт другим пользователем; дождитесь освобождения блокировки.</li><li>Редактировать можно только последнюю версию семейства наряда.</li></ul></div>
<div class="box"><h2>Не удаётся удалить сотрудника или работу</h2><ul><li>Если запись уже использовалась в сохранённом наряде, SmartOrder сохраняет её для целостности истории и помечает «Помечено на удаление ❌».</li><li>Такая запись остаётся видимой в справочнике, но больше не предлагается при создании новых нарядов.</li></ul></div>
<div class="box"><h2>Excel выглядит крупно при печати</h2><p>Откройте <b>Файл → Печать</b> и в масштабировании выберите <b>«Вписать лист на одну страницу»</b>.</p></div>
<div class="box"><h2>Интерфейс отображается некорректно</h2><ul><li>Закройте SmartOrder и запустите заново через ярлык.</li><li>Если проблема повторяется после смены темы или масштаба, соберите логи.</li><li>При белом/пустом окне или аварийном завершении приложите скриншот и архив логов.</li></ul></div>
<div class="box"><h2>Не удаётся войти</h2><p>Проверьте раскладку клавиатуры и Caps Lock. Для сброса пароля используйте ссылку «Забыли пароль?» в окне авторизации и обратитесь в IT-отдел. Bitrix24: <a href="https://sir01.bitrix24.ru/company/personal/user/1292/">Написать</a>.</p></div>
</body></html>"""


def _ensure_html_document(filename: str, content: str) -> Path | None:
    try:
        docs = local_root() / "documents"
        docs.mkdir(parents=True, exist_ok=True)
        path = docs / filename
        path.write_text(content, encoding="utf-8")
        return path
    except Exception:
        return None


def ensure_user_guide_document() -> Path | None:
    from .guide_site import build_guide_site

    return _ensure_html_document("smartorder_kak_rabotat.html", build_guide_site(USER_GUIDE_HTML))


def ensure_troubleshooting_document() -> Path | None:
    return _ensure_html_document("smartorder_vozmozhnye_problemy.html", TROUBLESHOOTING_HTML)
