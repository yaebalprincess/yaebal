from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HEAVY = (ROOT / "smartorder/heavy_ui.py").read_text(encoding="utf-8")
DB = (ROOT / "smartorder/db.py").read_text(encoding="utf-8")
APP = (ROOT / "smartorder/app.py").read_text(encoding="utf-8")
POLICY = (ROOT / "smartorder/policy.py").read_text(encoding="utf-8")


def test_no_invalid_qevent_destroy():
    assert "QEvent.Destroy" not in HEAVY


def test_loaded_tab_switch_has_no_refresh_calls():
    block = HEAVY.split("def _tab_changed", 1)[1].split("def _fade_current_tab", 1)[0]
    else_part = block.split("else:", 1)[1]
    assert "refresh_orders()" not in else_part
    assert "refresh_work_types()" not in else_part
    assert "refresh_people()" not in else_part


def test_about_uses_selectable_text_browser():
    assert "QTextBrowser" in HEAVY
    assert "selection-background-color:#FFD60A" in HEAVY
    assert "Qt.TextSelectableByMouse" in HEAVY


def test_heavy_policy_retained():
    assert "Положение об использовании ПО" in POLICY
    assert "Pestretsov.A.A" in POLICY
    assert "Шилова А.А." in POLICY


def test_access_control_is_real_setting():
    assert "def is_access_control_enabled" in DB
    assert "def set_access_control" in DB
    assert "UPDATE settings SET access_control_enabled=1 WHERE id=1" not in DB
    assert "login-bypassed" in APP


def test_forgot_password_text_matches_heavy_contact():
    assert "+7 995-552-85-13" in HEAVY
    assert "+7 999 660-45-62" not in HEAVY
    assert "artem.pestretsov@tmbsir.ru" in HEAVY
