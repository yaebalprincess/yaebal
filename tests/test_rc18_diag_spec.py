from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HEAVY = (ROOT / 'smartorder' / 'heavy_ui.py').read_text(encoding='utf-8')
DB = (ROOT / 'smartorder' / 'db.py').read_text(encoding='utf-8')
BUILD = (ROOT / 'Build_SmartOrder.ps1').read_text(encoding='ascii')
NATIVE = (ROOT / 'NativeLauncher.cs').read_text(encoding='utf-8')


def test_diagnostics_center_is_admin_button_and_maximized_dialog():
    assert 'class DiagnosticsCenterDialog' in HEAVY
    assert 'QPushButton("Центр диагностики")' in HEAVY
    assert 'Qt.WindowMaximized' in HEAVY


def test_diagnostics_center_uses_background_probes_and_live_graphs():
    assert 'threading.Thread(target=self._probe_worker' in HEAVY
    assert 'Отклик SQLite / SMB' in HEAVY
    assert 'Задержка UI event loop' in HEAVY
    assert 'def quick_check(self)' in DB


def test_build_requires_and_copies_original_gif_and_icon_assets():
    for name in ('login_background.gif', 'loading2.gif', 'smartorder_app_icon.ico'):
        assert name in BUILD
    assert '--icon' in BUILD
    assert '/win32icon:' in BUILD
    assert 'Copy-Item (Join-Path $ResourcesDir "*") $DistResources -Recurse -Force' in BUILD


def test_launcher_fallback_matches_current_release():
    assert '1.0' in NATIVE
    assert '3.12.0-rc13' not in NATIVE
