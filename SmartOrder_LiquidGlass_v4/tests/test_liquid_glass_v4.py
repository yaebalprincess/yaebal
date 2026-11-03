"""Personalization, one persistent shell, live rounded glass and current guide."""
from PyQt5.QtCore import QEvent, QPoint, QRect, Qt
from PyQt5.QtGui import QColor, QFont, QFontDatabase, QImage, QPainter
from PyQt5.QtWidgets import (QApplication, QDialog, QFileDialog, QLabel,
    QMessageBox, QPushButton, QToolButton, QVBoxLayout, QWidget)

from smartorder.appearance import import_wallpaper, wallpaper_path
from smartorder.appearance_config import FONT_ROLES, normalize_appearance
from smartorder.config import SettingsStore, UiSettings
from smartorder.glass_about import DownloadGuideButton
from smartorder.heavy_styles import apply_apple_design
from smartorder.liquid_effects import GlassBackdrop
from smartorder.live_glass import LiveGlassBackdrop
from smartorder.user_guide import USER_GUIDE_HTML
from test_liquid_glass import app, system, glass, javascript, drain


def test_old_settings_migrate_and_typography_background_round_trip(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("SMARTORDER_NETWORK_ROOT", str(tmp_path / "shared"))
    store = SettingsStore()
    store.path.write_text('{"theme":"dark","zoom":113}', encoding="utf-8")
    settings = store.load()
    assert settings.zoom == 113 and set(settings.appearance["fonts"]) == set(FONT_ROLES)
    settings.appearance["fonts"]["body"].update(family="Courier New", size=17.5, weight=700, italic=True)
    settings.appearance["background_mode"] = "none"
    store.save(settings)
    assert store.load() == settings


def test_all_installed_fonts_and_independent_roles_apply_to_qt_and_web(glass, app):
    window, _, _ = glass
    window.tabs.setCurrentIndex(3)
    panel = window.appearance_panel
    assert set(panel.font_controls) == set(FONT_ROLES)
    families = QFontDatabase().families()
    family = next((f for f in families if "Mono" in f), families[-1])
    controls = panel.font_controls["buttons"]
    controls[0].setCurrentFont(QFont(family))
    controls[1].setValue(19)
    controls[2].setCurrentIndex(controls[2].findData(800))
    controls[3].setChecked(True)
    body = panel.font_controls["body"]
    body[1].setValue(15)
    panel.save()
    assert window.settings_store.load().appearance["fonts"]["buttons"]["family"] == family
    assert window.settings_store.load().appearance["fonts"]["body"]["size"] == 15
    assert panel.status.font().pixelSize() == 15
    window.tabs.setCurrentIndex(0)
    window._publish_glass_state(force=True)
    drain(app, lambda: javascript(app, window, 'getComputedStyle(document.getElementById("create")).fontSize') == "19px")
    style = javascript(app, window, '''(() => {const s=getComputedStyle(document.getElementById("create"));return {family:s.fontFamily,weight:s.fontWeight,italic:s.fontStyle};})()''')
    assert family in style["family"] and style["weight"] == "800" and style["italic"] == "italic"


def test_one_header_navigation_and_scale_survive_every_tab_at_113_percent(glass, app):
    window, _, _ = glass
    window.resize(1452, 900)
    window.zoom.setValue(113)
    drain(app, lambda: not window._rc18_zoom_timer.isActive())
    measurements = []
    for index in (0, 1, 2, 3, 4, 5, 0):
        window.tabs.setCurrentIndex(index)
        app.processEvents()
        measurements.append((window.size(), window.titlebar.geometry(), window.zoom.mapTo(window,window.zoom.rect().topLeft()), window.tabs.tabBar().geometry()))
        assert window.zoom.isVisible() and window.zoom.isEnabled() and window.zoom.value() == 113
    assert all(value == measurements[0] for value in measurements)
    assert javascript(app, window, 'getComputedStyle(document.getElementById("titlebar")).display') == "none"
    assert javascript(app, window, 'getComputedStyle(document.getElementById("tabs")).display') == "none"
    assert window.centralWidget() is window._legacy_shell
    window.zoom.setValue(200)
    drain(app, lambda: not window._rc18_zoom_timer.isActive())
    window.resize(680,620);app.processEvents()
    assert window.width() == 680
    assert all(button.x()+button.width() <= window.titlebar.width() for button in window.titlebar.controls)


def test_saved_title_font_size_survives_new_workspace_window(glass, app):
    from PyQt5 import sip
    window, _, _ = glass
    appearance=normalize_appearance(window.ui_settings.appearance)
    appearance["fonts"]["window_title"]["size"]=32
    window.set_appearance(appearance)
    new=window._switch_to_workshop("smoking")
    try:
        drain(app,lambda:new._glass_ready,timeout=12)
        assert new.titlebar.height() >= 52
        assert new.titlebar.title.font().pixelSize() == 32
    finally:
        if not sip.isdeleted(new):
            new._rc4_exit_confirmed=True;new.close();new.deleteLater()
            app.sendPostedEvents(None,QEvent.DeferredDelete);app.processEvents()


def test_no_wallpaper_custom_wallpaper_and_restart_are_consistent(glass, app, tmp_path):
    window, _, _ = glass
    appearance = normalize_appearance(window.ui_settings.appearance)
    appearance["background_mode"] = "none"
    window.set_appearance(appearance)
    assert wallpaper_path(window.ui_settings.appearance) is None
    source = tmp_path / "user-photo.png"
    image = QImage(360,240,QImage.Format_ARGB32);image.fill(QColor("#dd66aa"));assert image.save(str(source))
    managed = import_wallpaper(source)
    assert managed != source and managed.exists()
    appearance.update(background_mode="custom", background_file=str(managed))
    window.set_appearance(appearance)
    assert wallpaper_path(window.settings_store.load().appearance) == managed
    window._legacy_shell._liquid_backdrop.repaint()
    assert window._legacy_shell._liquid_backdrop._cache_key[-1] == str(managed)
    window.tabs.setCurrentIndex(1)
    assert wallpaper_path(window.ui_settings.appearance) == managed


class PatternWindow(QWidget):
    phase = False
    def paintEvent(self, event):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor("#3344cc" if self.phase else "#dd4433"))
        p.fillRect(QRect(self.width()//2,0,self.width()//2,self.height()), QColor("#dd4433" if self.phase else "#3344cc"))
        p.setPen(QColor("white"));p.drawText(60,140,"Content below the overlay")


def test_dialog_blurs_live_interface_moves_updates_and_has_real_alpha_corners(app):
    source = PatternWindow();source.resize(1000,650);source.show()
    apply_apple_design(source)
    dialog = QDialog(source);dialog.setWindowTitle("Резервная копия")
    layout = QVBoxLayout(dialog);layout.addWidget(QLabel("Создана резервная копия"));layout.addWidget(QPushButton("OK"))
    dialog.resize(260,200);dialog.move(source.mapToGlobal(source.rect().topLeft())+QPoint(40,180));dialog.show()
    try:
        layer = dialog._liquid_backdrop
        assert isinstance(layer, LiveGlassBackdrop)
        assert not dialog.findChildren(GlassBackdrop)
        assert dialog.testAttribute(Qt.WA_TranslucentBackground)
        assert bool(dialog.windowFlags() & Qt.FramelessWindowHint)
        assert not dialog.mask().contains(dialog.rect().topLeft())
        drain(app, lambda: layer.capture_count > 1 and not layer.blurred.isNull())
        first = layer.raw.toImage().pixelColor(layer.raw.width()//2,layer.raw.height()//2)
        dialog.move(source.mapToGlobal(source.rect().topLeft())+QPoint(650,180))
        drain(app, lambda: layer.source_rect.left() > 500)
        second = layer.raw.toImage().pixelColor(layer.raw.width()//2,layer.raw.height()//2)
        assert first != second
        source.phase=True;source.update()
        drain(app,lambda:layer.raw.toImage().pixelColor(layer.raw.width()//2,layer.raw.height()//2) != second)
        corners=dialog.grab().toImage()
        assert corners.pixelColor(0,0).alpha() == 0
        assert dialog.windowOpacity() == 1.0
        dialog.hide();assert not layer.timer.isActive()
    finally:
        dialog.deleteLater();source.close();source.deleteLater()
        app.sendPostedEvents(None,QEvent.DeferredDelete);app.processEvents()


def test_backup_notice_uses_live_glass_and_no_repeated_factory_picture(glass, app):
    window, _, _ = glass
    box = QMessageBox(QMessageBox.Information,"Резервная копия","Создано: backup.db",QMessageBox.Ok,window)
    box.show();app.processEvents()
    assert isinstance(box._liquid_backdrop,LiveGlassBackdrop)
    assert not box.findChildren(GlassBackdrop)
    assert box.testAttribute(Qt.WA_TranslucentBackground) and box._glass_chrome.isVisible()
    box.close();box.deleteLater();app.sendPostedEvents(None,QEvent.DeferredDelete);app.processEvents()


def test_file_chooser_uses_the_same_translucent_rounded_window(glass, app, tmp_path):
    window, _, _ = glass
    assert QApplication.testAttribute(Qt.AA_DontUseNativeDialogs)
    picker=QFileDialog(window,"Выбрать изображение",str(tmp_path))
    picker.setFileMode(QFileDialog.ExistingFile)
    picker.show();app.processEvents()
    assert isinstance(picker._liquid_backdrop,LiveGlassBackdrop)
    assert picker.testAttribute(Qt.WA_TranslucentBackground)
    assert picker.windowFlags() & Qt.FramelessWindowHint
    picker.close();picker.deleteLater();app.sendPostedEvents(None,QEvent.DeferredDelete);app.processEvents()


def test_guide_download_icon_saves_current_official_manual(glass, app, monkeypatch, tmp_path):
    window, _, _ = glass
    window.tabs.setCurrentIndex(5);app.processEvents()
    page=window.tabs.currentWidget()
    icons=page.findChildren(DownloadGuideButton)
    assert len(icons)==1 and icons[0].text()==""
    assert not any(b.text()=="Скачать руководство в PDF" for b in page.findChildren(QPushButton))
    output=tmp_path/'SmartOrder_guide.pdf'
    monkeypatch.setattr(QFileDialog,'getSaveFileName',lambda *args,**kwargs:(str(output),'PDF'))
    notices=[];monkeypatch.setattr(QMessageBox,'information',lambda *args:notices.append(args[2]))
    icons[0].click()
    assert output.read_bytes().startswith(b'%PDF-') and output.stat().st_size>10000 and notices
    assert 'Руководство пользователя' in USER_GUIDE_HTML
    assert 'Название подразделения' in USER_GUIDE_HTML and 'само по себе этот режим не включает' in USER_GUIDE_HTML
    assert 'Персонализация' in USER_GUIDE_HTML and '.sorder' in USER_GUIDE_HTML
