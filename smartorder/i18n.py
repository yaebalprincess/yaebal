"""UI translations; database values, names and typed text are never translated."""
from PyQt5.QtCore import Qt, QLocale
from PyQt5.QtWidgets import QApplication, QWidget, QLabel, QAbstractButton, QComboBox, QGroupBox, QLineEdit, QTabWidget, QListWidget, QTableWidget
LANGUAGES = {"ru":"Русский", "en":"English", "es":"Español", "kk":"Қазақша", "fr":"Français", "de":"Deutsch", "ja":"日本語", "tt":"Татарча"}
SOURCE_ROLE = int(Qt.UserRole)+901
_TEXT = '''Наряд|Work order|Orden de trabajo
Наряды|Work orders|Órdenes de trabajo
Номенклатура|Catalog|Catálogo
Сотрудники|Employees|Empleados
Администрирование|Administration|Administración
Аналитика|Analytics|Análisis
Персонализация|Personalization|Personalización
О приложении|About|Acerca de
Smart Order — Формирование нарядов на работу|Smart Order — Work orders|Smart Order — Órdenes de trabajo
Масштаб:|Scale:|Escala:
В данной вкладке функция масштаба недоступна|Scaling is unavailable on this tab|La escala no está disponible en esta pestaña
Светлая тема|Light theme|Tema claro
Тёмная тема|Dark theme|Tema oscuro
Язык интерфейса:|Interface language:|Idioma de la interfaz:
Применять сохраненные настройки персонализации при запуске|Apply saved personalization settings at startup|Aplicar la personalización guardada al iniciar
Настройки сохраняются в вашем профиле. Этот флажок определяет, применять ли их при следующем запуске.|Settings are saved in your profile. This checkbox controls their application at startup.|La configuración se guarda en su perfil. Esta casilla controla su aplicación al iniciar.
Шрифты, фон и тема для вашего рабочего пространства. Окна входа и первого запуска используют прежнее оформление.|Fonts, wallpaper and theme for your workspace. Sign-in and first-run windows keep their original design.|Fuentes, fondo y tema de su espacio de trabajo. El acceso y el primer inicio mantienen su diseño original.
Автоматически менять тему по времени суток (светлая с 08:00 до 17:00)|Switch theme automatically (light from 08:00 to 17:00)|Cambiar el tema automáticamente (claro de 08:00 a 17:00)
Шрифты|Fonts|Fuentes
Фон|Wallpaper|Fondo
Элемент|Element|Elemento
Шрифт|Font|Fuente
Размер, пкс|Size, px|Tamaño, px
Жирность|Weight|Grosor
Курсив|Italic|Cursiva
Образец|Preview|Vista previa
Заголовок окна|Window title|Título de ventana
Подписи верхней панели|Top bar labels|Etiquetas de la barra superior
Заголовки разделов|Section headings|Títulos de sección
Текст и подписи|Text and labels|Texto y etiquetas
Кнопки|Buttons|Botones
Поля ввода и списки|Inputs and lists|Campos y listas
Строки таблиц|Table rows|Filas de tabla
Заголовки таблиц|Table headers|Encabezados de tabla
Вкладки|Tabs|Pestañas
Тонкий|Thin|Fino
Сверхлёгкий|Extra light|Extra ligero
Лёгкий|Light|Ligero
Обычный|Regular|Normal
Средний|Medium|Medio
Полужирный|Semibold|Seminegrita
Жирный|Bold|Negrita
Сверхжирный|Extra bold|Extranegrita
Чёрный|Black|Grueso
Стандартный фон|Default wallpaper|Fondo predeterminado
Без фонового изображения|No wallpaper|Sin imagen de fondo
Своё изображение|Custom image|Imagen personalizada
Выбрать изображение…|Choose an image…|Elegir imagen…
Убрать своё изображение|Remove custom image|Eliminar imagen personalizada
Своё изображение не выбрано|No custom image selected|No se ha elegido una imagen
Фон приложения|Application wallpaper|Fondo de la aplicación
Тема страницы «О приложении»|About page theme|Tema de la página Acerca de
Тема 1 — прежняя, с GIF|Theme 1 — original, with GIF|Tema 1 — original, con GIF
Тема 2 — текущая, Liquid Glass|Theme 2 — current, Liquid Glass|Tema 2 — actual, Liquid Glass
По умолчанию|Reset to defaults|Restablecer
Применить|Apply|Aplicar
Настройки применены и сохранены в вашем профиле.|Settings applied and saved to your profile.|Configuración aplicada y guardada en su perfil.
Настройки сохранены. Применение при запуске отключено.|Settings saved. Applying them at startup is disabled.|Configuración guardada. Su aplicación al iniciar está desactivada.
Настройки по умолчанию подготовлены. Нажмите «Применить».|Default settings are ready. Click Apply.|La configuración predeterminada está lista. Pulse Aplicar.
Сначала выберите изображение.|Choose an image first.|Elija primero una imagen.
Система|System|Sistema
Документация|Documentation|Documentación
Помощь|Help|Ayuda
Формирование нарядов на работу · Liquid Glass|Work orders · Liquid Glass|Órdenes de trabajo · Liquid Glass
Общая база, история изменений и рабочие пространства цехов.|Shared database, change history and workshop workspaces.|Base de datos compartida, historial y espacios de talleres.
Положение об использовании ПО|Software usage policy|Política de uso del programa
Инструкции по работе с нарядами, справочниками и общими данными.|Instructions for work orders, catalogs and shared data.|Instrucciones para órdenes, catálogos y datos compartidos.
Как работать в программе?|How to use the application?|¿Cómo utilizar el programa?
Возможные проблемы при работе|Troubleshooting|Solución de problemas
Новости обновлений|Update news|Novedades
Контакты поддержки и восстановление доступа к программе.|Support contacts and account recovery.|Contacto de soporte y recuperación de acceso.
Забыли пароль?|Forgot password?|¿Olvidó la contraseña?
Прочие вопросы|Other questions|Otras consultas
Текущая сессия:|Current session:|Sesión actual:
Создать наряд|Create work order|Crear orden
Редактировать|Edit|Editar
Выгрузить в EXCEL|Export to Excel|Exportar a Excel
Выгрузить в Excel|Export to Excel|Exportar a Excel
Удалить черновик|Delete draft|Eliminar borrador
Просмотреть наряд|View work order|Ver orden
Недоступно|Unavailable|No disponible
Для начала работы создайте наряд.|Create a work order to get started.|Cree una orden de trabajo para comenzar.
Для начала работы добавьте номенклатуру или загрузите её из Excel.|Add catalog items or import them from Excel to get started.|Añada artículos o impórtelos desde Excel para comenzar.
Для начала работы добавьте сотрудников или загрузите их из Excel.|Add employees or import them from Excel to get started.|Añada empleados o impórtelos desde Excel para comenzar.
По вашему запросу ничего не найдено.|No results match your search.|No se encontraron resultados.
Наряды пока не созданы.|No work orders yet.|Todavía no hay órdenes de trabajo.
Загрузка…|Loading…|Cargando…
Загрузка рабочего пространства…|Loading workspace…|Cargando espacio de trabajo…
Дата наряда:|Work order date:|Fecha de la orden:
Мастер:|Supervisor:|Supervisor:
Смена:|Shift:|Turno:
Подразделение:|Department:|Departamento:
Все мастера|All supervisors|Todos los supervisores
Все смены|All shifts|Todos los turnos
Все подразделения|All departments|Todos los departamentos
Ночная|Night|Noche
Дневная|Day|Día
Дата наряда|Work order date|Fecha de la orden
Тип смены|Shift|Turno
Мастер|Supervisor|Supervisor
Подразделение|Department|Departamento
Дата регистрации|Created|Fecha de registro
Дата редактирования|Modified|Fecha de modificación
ИСТОРИЯ РЕДАКТИРОВАНИЙ|EDIT HISTORY|HISTORIAL DE CAMBIOS
Добавить|Add|Añadir
Загрузить из Excel|Import from Excel|Importar desde Excel
Недавно удалённые|Recently deleted|Eliminados recientemente
← Текущие|← Current|← Actuales
Наименование:|Name:|Nombre:
Код работы:|Work code:|Código de trabajo:
Стоимость:|Rate:|Tarifa:
Поиск:|Search:|Buscar:
Найдено:|Found:|Encontrados:
Недавно удалено:|Recently deleted:|Eliminados recientemente:
ФИО:|Full name:|Nombre completo:
ФИО / Название|Full name / Name|Nombre completo / Nombre
Наименование|Name|Nombre
Код работы|Work code|Código de trabajo
Стоимость в рублях|Rate, RUB|Tarifa, RUB
Удалено|Deleted|Eliminado
Сохранить|Save|Guardar
Удалить|Delete|Eliminar
Работники|Workers|Trabajadores
Мастера|Supervisors|Supervisores
Подразделения|Departments|Departamentos
Введите ФИО|Enter full name|Introduzca el nombre completo
Введите название|Enter name|Introduzca el nombre
Введите название подразделения|Enter department name|Introduzca el nombre del departamento
Введите название или код работы|Enter a name or work code|Introduzca un nombre o código de trabajo
Создание нового пользователя|Create user|Crear usuario
Редактирование пользователя|Edit user|Editar usuario
Заполните данные для нового пользователя|Enter the new user's details|Introduzca los datos del nuevo usuario
Измените данные пользователя|Edit the user's details|Modifique los datos del usuario
Логин:|Username:|Usuario:
Логин|Username|Usuario
Пароль:|Password:|Contraseña:
Пароль|Password|Contraseña
Роли:|Roles:|Roles:
Введите пароль не менее 8-ми символов|Enter a password of at least 8 characters|Introduzca una contraseña de al menos 8 caracteres
Оставьте пустым, чтобы не менять|Leave blank to keep unchanged|Deje vacío para no cambiarla
Пароль должен содержать не менее 8 символов.|Password must contain at least 8 characters.|La contraseña debe tener al menos 8 caracteres.
Пароль слишком длинный.|Password is too long.|La contraseña es demasiado larga.
Пользователь|User|Usuario
Пользователи|Users|Usuarios
Роль|Role|Rol
Администратор|Administrator|Administrador
Бухгалтер|Accountant|Contable
Экономист|Economist|Economista
Аналитик|Analyst|Analista
Мастер Коптильный Цех|Smoking workshop supervisor|Supervisor de ahumado
Мастер Адыгейский Цех|Adyghe workshop supervisor|Supervisor de Adyghe
Упаковка|Packaging|Envasado
Коптильный|Smoking|Ahumado
Сушка|Drying|Secado
Сычужный|Rennet|Cuajo
Сыр цех|Cheese workshop|Taller de queso
Адыгейский|Adyghe|Adyghe
Выбор цеха|Select workshop|Seleccionar taller
Рабочее пространство|Workspace|Espacio de trabajo
Перейти в цех|Open workshop|Abrir taller
Выбрать цех|Select workshop|Seleccionar taller
Синхронизация|Synchronize|Sincronizar
Журнал действий|Audit log|Registro de acciones
Период:|Period:|Período:
Пользователь:|User:|Usuario:
Все пользователи|All users|Todos los usuarios
Дата/Время|Date/Time|Fecha/Hora
Действие|Action|Acción
Объект|Object|Objeto
Подробности|Details|Detalles
Резервная копия|Backup|Copia de seguridad
Создать бэкап|Create backup|Crear copia
Восстановить|Restore|Restaurar
Архивный снимок|Archive snapshot|Instantánea de archivo
Открыть архивные снимки|Open snapshots|Abrir instantáneas
Собрать логи|Collect logs|Recopilar registros
Центр диагностики|Diagnostics|Diagnóstico
Резервная копия учётных записей и сессий|Back up accounts and sessions|Copiar cuentas y sesiones
▣ Резервное копирование и архивы|▣ Backups and archives|▣ Copias de seguridad y archivos
Аналитика производства|Production analytics|Análisis de producción
Цеха · работы и коды · подразделения · сотрудники на сменах · мастера|Workshops · work codes · departments · employees · supervisors|Talleres · códigos · departamentos · empleados · supervisores
Цех:|Workshop:|Taller:
Все цеха|All workshops|Todos los talleres
Все|All|Todos
Обновить|Refresh|Actualizar
Графики в Excel|Charts in Excel|Gráficos en Excel
Экспорт в Excel|Export to Excel|Exportar a Excel
Работа / код:|Work / code:|Trabajo / código:
Произвольный период|Custom period|Período personalizado
Этот месяц|This month|Este mes
Этот год|This year|Este año
Прошлый год|Last year|Año anterior
Единицы ФАКТ|ACTUAL units|Unidades REALES
Показатель графиков:|Chart metric:|Indicador del gráfico:
Помесячная гистограмма:|Monthly histogram:|Histograma mensual:
Уникальные сотрудники|Unique employees|Empleados únicos
Выходы сотрудников на смены|Employee shift attendance|Asistencia a turnos
ФИКС Итоговый вес, кг|FIXED total weight, kg|Peso total FIJO, kg
Цех|Workshop|Taller
Цеха / Min–Max|Workshops / Min–Max|Talleres / Mín–Máx
Сотрудник|Employee|Empleado
Работы / коды|Work / codes|Trabajos / códigos
Работа / вид продукции|Work / product type|Trabajo / tipo de producto
Методика|Methodology|Metodología
Методика аналитики|Analytics methodology|Metodología de análisis
Сохранить единицы|Save units|Guardar unidades
ОК|OK|Aceptar
Отмена|Cancel|Cancelar
Закрыть|Close|Cerrar
Закрыть окно|Close window|Cerrar ventana
Свернуть|Minimize|Minimizar
Развернуть / восстановить|Maximize / restore|Maximizar / restaurar
Да|Yes|Sí
Нет|No|No
Ошибка|Error|Error
Предупреждение|Warning|Advertencia
Подтверждение|Confirmation|Confirmación
Выход|Exit|Salir
Поиск…|Search…|Buscar…
Поиск в списке…|Search the list…|Buscar en la lista…
Ничего не найдено|No results|Sin resultados
Сегодня|Today|Hoy
Пн|Mon|Lun
Вт|Tue|Mar
Ср|Wed|Mié
Чт|Thu|Jue
Пт|Fri|Vie
Сб|Sat|Sáb
Вс|Sun|Dom
Выберите дату или начало периода|Select a date or period start|Seleccione una fecha o inicio del período
Esc — для полноэкранного режима|Esc — enter full screen|Esc — pantalla completa
Esc — выйти из полноэкранного режима|Esc — exit full screen|Esc — salir de pantalla completa
Информация о наряде|Work order information|Información de la orden
Дата:|Date:|Fecha:
Смена|Shift|Turno
Работники и работы|Employees and work|Empleados y trabajos
Добавить работников|Add employees|Añadir empleados
Добавить работы|Add work|Añadir trabajos
Выбор работников|Select employees|Seleccionar empleados
Выбор работ|Select work|Seleccionar trabajos
ФИО|Full name|Nombre completo
Часы|Hours|Horas
Итого|Total|Total
Оплата|Payment|Pago
Сохранить наряд|Save work order|Guardar orden
Действие недоступно.|Action unavailable.|Acción no disponible.
Smart Order · Создание нового пользователя|Smart Order · Create a new user|Smart Order · Crear un nuevo usuario
Главное окно · Пользователь и цех · Масштаб|Main window · User and workshop · Scale|Ventana principal · Usuario y taller · Escala
Наряд · Номенклатура · Администрирование|Work order · Catalog · Administration|Orden · Catálogo · Administración
Создание наряда · Дата, смена, мастер|Create work order · Date, shift, supervisor|Crear orden · Fecha, turno, supervisor
Наряд · Создать наряд · Сохранить|Work order · Create work order · Save|Orden · Crear orden · Guardar
Автор наряда · Выбор мастера и подразделения|Work order author · Supervisor and department|Autor de la orden · Supervisor y departamento
Наряд · Таблица работ и сотрудников|Work order · Work and employees table|Orden · Tabla de trabajos y empleados
Журнал действий · Дата/Время · Пользователь|Activity log · Date/Time · User|Registro · Fecha/Hora · Usuario
Наряд · Аналитика · Персонализация|Work order · Analytics · Personalization|Orden · Análisis · Personalización
Без изображения останется спокойный однотонный фон. Всплывающие окна размывают содержимое под собой при любом фоне.|Without an image, a plain background is used. Pop-up windows blur the content underneath with any wallpaper.|Sin imagen se utiliza un fondo liso. Las ventanas emergentes difuminan el contenido inferior con cualquier fondo.
Тема 1 использует loading2.gif или login_background.gif из папки resources прежней установки. Если файла нет, отображается спокойный градиент.|Theme 1 uses loading2.gif or login_background.gif from the resources folder of the previous installation. A gradient is used if the file is missing.|El tema 1 utiliza loading2.gif o login_background.gif de la carpeta resources de la instalación anterior. Si falta el archivo, se muestra un degradado.
Часы работы|Work hours|Horas de trabajo
ФИКС Итоговый вес, кг|FIXED Total weight, kg|FIJO Peso total, kg
ФАКТ часы|ACTUAL hours|Horas REALES
ФАКТ Оплата, ₽|ACTUAL Payment, ₽|Pago REAL, ₽
Динамика ФИКС по дням|FIXED production by day|Producción FIJA por día
Профиль 3D · ведущий цех|3D profile · leading workshop|Perfil 3D · taller principal
Объём по цехам|Volume by workshop|Volumen por taller
Доля объёма по цехам|Volume share by workshop|Cuota de volumen por taller
Сотрудники по месяцам|Employees by month|Empleados por mes
Показатель графиков:|Chart metric:|Indicador de gráficos:
Уникальные сотрудники|Unique employees|Empleados únicos
Цеха / Min–Max|Workshops / Min–Max|Talleres / Mín–Máx
Период:|Period:|Período:
Год:|Year:|Año:
По дням|By day|Por día
По месяцам|By month|Por mes
По годам|By year|Por año'''
CATALOG={r.split('|')[0]:tuple(r.split('|')[1:]) for r in _TEXT.splitlines()}
from .locales_v7 import EXTRA,BASE_NEW
CATALOG.update(BASE_NEW);CATALOG.pop("Аналитик",None)
TRANSLATIONS={"en":{k:v[0] for k,v in CATALOG.items()},"es":{k:v[1] for k,v in CATALOG.items()},**EXTRA}
from .security import PERMISSION_LABELS
for label in PERMISSION_LABELS.values():
    head,tail=label.split(": ",1)
    for translations in TRANSLATIONS.values():translations[label]=translations.get(head,head)+": "+translations.get(tail,tail)
    CATALOG[label]=(TRANSLATIONS["en"][label],TRANSLATIONS["es"][label])
REVERSE={value:key for translations in TRANSLATIONS.values() for key,value in translations.items()}

def language():
    return getattr(QApplication.instance(),"_smartorder_language","ru")

def set_language(code):
    if QApplication.instance() is not None:QApplication.instance()._smartorder_language=code if code in LANGUAGES else "ru"

def tr(text,code=None):
    code=code or language()
    if code=="ru":return text
    translations=TRANSLATIONS.get(code,TRANSLATIONS["en"])
    if text in translations:return translations[text]
    for prefix in ("Текущая сессия:","Найдено:","Недавно удалено:","Не удалось синхронизировать персонализацию: ","Конфиг сохранён: "):
        if text.startswith(prefix):return tr(prefix,code)+text[len(prefix):] if text!=prefix else translations.get(prefix,prefix)
    return TRANSLATIONS["en"].get(text,text)

def item_source(combo,index):
    return combo.itemData(index,SOURCE_ROLE) or combo.itemText(index)

def source_text(combo):return item_source(combo,combo.currentIndex())

def field(widget,key,value,setter,code):
    if not value:return
    sources=getattr(widget,"_i18n_sources",None)
    if sources is None:sources={};widget._i18n_sources=sources
    original=sources.get(key)
    if original is None or value not in tuple([original]+[tr(original,c) for c in LANGUAGES if c!="ru"]):
        original=REVERSE.get(value,value);sources[key]=original
    result=tr(original,code)
    if result!=value:setter(result)

def apply_widget(w,code=None):
    code=code or language()
    if getattr(w,"_i18n_language",None)==code or w.property("legacyAppearance") or w.property("plainSurface"):return
    field(w,"tooltip",w.toolTip(),w.setToolTip,code)
    if w.isWindow():field(w,"title",w.windowTitle(),w.setWindowTitle,code)
    if isinstance(w,(QLabel,QAbstractButton)):field(w,"text",w.text(),w.setText,code)
    if isinstance(w,QLineEdit):field(w,"placeholder",w.placeholderText(),w.setPlaceholderText,code)
    if isinstance(w,QGroupBox):field(w,"group",w.title(),w.setTitle,code)
    if isinstance(w,QComboBox) and not w.objectName().startswith("FontFamily_") and w.objectName()!="InterfaceLanguage":
        blocked=w.blockSignals(True)
        for i in range(w.count()):
            data=w.itemData(i)
            if data is not None and not isinstance(data,str) and not w.objectName().startswith("FontWeight_"):continue
            source=w.itemData(i,SOURCE_ROLE) or REVERSE.get(w.itemText(i),w.itemText(i))
            if source in CATALOG:w.setItemData(i,source,SOURCE_ROLE);w.setItemText(i,tr(source,code))
        w.blockSignals(blocked)
    if isinstance(w,QTabWidget):
        for i in range(w.count()):field(w,"tab"+str(i),w.tabText(i),lambda s,j=i:w.setTabText(j,s),code)
    if isinstance(w,QListWidget) and w.objectName()=="UserRoleList":
        for i in range(w.count()):
            item=w.item(i);item.setText(tr(item.data(Qt.UserRole),code))
    if isinstance(w,QTableWidget):
        for i in range(w.columnCount()):
            item=w.horizontalHeaderItem(i)
            if item:field(w,"header"+str(i),item.text(),item.setText,code)
    if hasattr(w,"report_model"):w.report_model.headerDataChanged.emit(Qt.Horizontal,0,max(0,len(w.report_model.columns)-1))
    locale=QLocale({"ru":"ru_RU","en":"en_US","es":"es_ES","kk":"kk_KZ","fr":"fr_FR","de":"de_DE","ja":"ja_JP","tt":"tt_RU"}[code])
    if w.locale()!=locale:w.setLocale(locale)
    w._i18n_language=code

def apply_language(root,code=None):
    if root is None:return
    code=code or language()
    if getattr(root,"_translated_language",None)==code:return
    apply_widget(root,code)
    for w in root.findChildren(QWidget):apply_widget(w,code)
    root._translated_language=code

def web_catalog(code=None):return {key:tr(key,code) for key in CATALOG}
