from pathlib import Path

from smartorder.db import department_sort_key

ROOT = Path(__file__).resolve().parents[1]
HEAVY = (ROOT / "smartorder" / "heavy_ui.py").read_text(encoding="utf-8")
CONFIG = (ROOT / "smartorder" / "config.py").read_text(encoding="utf-8")
DB = (ROOT / "smartorder" / "db.py").read_text(encoding="utf-8")


def test_rc15_version():
    assert 'APP_VERSION = "1.0"' in CONFIG


def test_department_numbering_matches_uploaded_workbook_order():
    departments = [
        "1. Адыгейский сыр",
        "2. Контроль, нарезка",
        "3. Косоплёты",
        "4. Кужорка",
        "5. Мастера",
        "6. Новая фасовка",
        "7. Слесаря",
        "8. Студенты",
        "9. Студенты ночь",
        "10. Суточные",
        "11. Хачемзий",
        "12. РАЗНОРАБОЧИЕ",
        "13. Отдельный работник",
        "14. АРАБЫ",
        "15. УЧИТЕЛЯ",
    ]
    shuffled = [departments[0], departments[9], departments[10], departments[1], *departments[2:9], *departments[11:]]
    assert sorted(shuffled, key=department_sort_key) == departments
    assert "department_sort_key(row[1])" in DB


def test_calendar_dark_theme_and_custom_navigation():
    assert "class RC15DateRangeDialog" in HEAVY
    assert "Qt.WindowContextHelpButtonHint, False" in HEAVY
    assert 'qt_calendar_prevmonth' in HEAVY
    assert 'qt_calendar_nextmonth' in HEAVY
    assert 'btn.setToolButtonStyle(Qt.ToolButtonTextOnly)' in HEAVY
    assert 'background:#1C1C1E' in HEAVY
    assert 'background:#2C2C2E' in HEAVY
    assert "_RC15CalendarNavMotion" in HEAVY


def test_people_mode_controls_have_smooth_custom_theme():
    assert 'PeopleModeRadio' in HEAVY
    assert 'btn.setFocusPolicy(Qt.NoFocus)' in HEAVY
    assert 'background:#636366' in HEAVY
    assert 'border:1px solid #007AFF' in HEAVY


def test_locked_cells_use_danger_red():
    assert 'class RC15WorkOrderDialog' in HEAVY
    assert 'QColor("#FF3B30")' in HEAVY
    assert 'locked = {5, 6, 7, 8} if has_actual' in HEAVY


def test_about_help_two_columns_and_shared_print_steps():
    assert 'instruction_html("Все остальные", ordinary)' in HEAVY
    assert 'instruction_html("Студенты / Ночь, Суточные", special)' in HEAVY
    assert '7. При необходимости откройте, отредактируйте или выгрузите наряд в Excel.' in HEAVY
    assert 'Вписать лист на одну страницу' in HEAVY
    assert '8. При выгрузке в Excel и для отправки на печать' in HEAVY


def test_rc15_final_aliases():
    assert 'HeavyWorkOrderDialog = RC15WorkOrderDialog' in HEAVY
    assert 'HeavyMainWindow = RC15MainWindow' in HEAVY
    assert 'DateRangeDialog = RC15DateRangeDialog' in HEAVY
