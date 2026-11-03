from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HEAVY = (ROOT / "smartorder" / "heavy_ui.py").read_text(encoding="utf-8")
CONFIG = (ROOT / "smartorder" / "config.py").read_text(encoding="utf-8")


def _rc13_work_block():
    return HEAVY.split("class RC13WorkOrderDialog", 1)[1].split("class RC13MainWindow", 1)[0]


def test_rc13_grouped_delete_snapshots_identity_before_removing_totals():
    block = _rc13_work_block()
    capture = block.index("identities: set")
    remove = block.index("self._remove_totals()")
    assert capture < remove
    assert "key in identities" in block
    assert "Exactly one rebuild after the semantic mutation" in block


def test_rc13_edit_cancel_does_not_create_draft_and_autosave_is_stopped():
    block = _rc13_work_block()
    assert "self._draft_timer.stop()" in block
    assert "if self.order_id is not None or self.order is not None:" in block
    assert "if self._rc13_loaded_draft_parent_id is not None:" in block
    assert "return super()._save_draft()" in block


def test_rc13_about_backing_is_inline_not_card_background():
    block = HEAVY.split("class RC13MainWindow", 1)[1]
    assert "Inline span means the translucent backing follows only the rendered text" in block
    assert "background-color:rgba(0,0,0,0.52)" in block
    assert 'AboutTransparentCard{background:rgba(0,0,0,0);border:none;}' in block
    assert "selection-background-color:#FFD60A" in HEAVY


def test_rc13_version():
    assert 'APP_VERSION = "1.0"' in CONFIG
