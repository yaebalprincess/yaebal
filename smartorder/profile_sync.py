"""Single-file local exports and asynchronous per-account shared preferences."""
import base64
from copy import deepcopy
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import threading
from PyQt5.QtCore import QObject,QTimer,pyqtSignal
from .config import UiSettings,SettingsStore,local_state_dir,settings_to_data,settings_from_data
from .i18n import tr


def pending_path(user):return local_state_dir()/("profile_sync_pending_"+str(int(user.id)))


def portable_config(settings):
    data={"format":"SmartOrder personalization","version":1,"settings":settings_to_data(settings)}
    appearance=data["settings"]["appearance"]
    if appearance["background_mode"]=="custom" and appearance["background_file"]:
        from .appearance import wallpaper_path
        path=wallpaper_path(settings.appearance)
        if path is not None:
            raw=path.read_bytes()
            if len(raw)>4*1024*1024:raise ValueError("Для синхронизации выберите фон размером до 4 МБ.")
            data["wallpaper"]={"extension":path.suffix.lower(),"data":base64.b64encode(raw).decode("ascii")}
            appearance["background_file"]=""
        else:appearance.update(background_mode="none",background_file="")
    return data


def read_config(payload):
    if not isinstance(payload,dict) or payload.get("format")!="SmartOrder personalization" or payload.get("version")!=1:
        raise ValueError("Неподдерживаемая конфигурация персонализации")
    settings=settings_from_data(payload.get("settings"));wallpaper=payload.get("wallpaper")
    if wallpaper:
        encoded=wallpaper.get("data","")
        if not isinstance(encoded,str) or len(encoded)>6*1024*1024:raise ValueError("Изображение слишком большое")
        raw=base64.b64decode(encoded,validate=True)
        extension=wallpaper.get("extension")
        if extension not in {".png",".jpg",".jpeg",".webp",".bmp"}:raise ValueError("Неподдерживаемое изображение")
        path=local_state_dir()/"appearance"/"sync_sources"/(hashlib.sha256(raw).hexdigest()+extension)
        path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
        from .appearance import import_wallpaper
        settings.appearance["background_file"]=str(import_wallpaper(path));settings.appearance["background_mode"]="custom"
        path.unlink(missing_ok=True)
    elif settings.appearance["background_mode"]=="custom":
        from .appearance import wallpaper_path
        if wallpaper_path(settings.appearance) is None:settings.appearance.update(background_mode="none",background_file="")
    return settings


def load_shared_settings(auth,user,local):
    if user.id<=0:
        local.sync_personalization=False;return local,""
    if pending_path(user).exists():return local,""
    try:
        saved=auth.get_personalization(user)
        if saved and saved["enabled"]:
            settings=read_config(saved["payload"]);settings.sync_personalization=True
            if not settings.remember_personalization:
                return UiSettings(remember_personalization=False,sync_personalization=True),""
            store=SettingsStore(user.id,user.username);store.save(settings)
            return settings,""
        if saved:local.sync_personalization=False
        return local,""
    except Exception as exc:return local,str(exc)


def export_current_config(user,settings):
    folder=local_state_dir()/"personalization_exports"/str(int(user.id));folder.mkdir(parents=True,exist_ok=True)
    filename="SmartOrder_"+datetime.now().strftime("%Y-%m-%d_%H-%M-%S")+".json";path=folder/filename
    tmp=folder/".export.tmp";tmp.write_text(json.dumps(portable_config(settings),ensure_ascii=False,indent=2),encoding="utf-8");os.replace(tmp,path)
    for previous in folder.glob("SmartOrder_*.json"):
        if previous!=path:previous.unlink()
    return path


class ProfileSync(QObject):
    finished=pyqtSignal(object,str)
    def __init__(self,owner):
        super().__init__(owner);self.owner=owner;self.pending=None;self.running=False;self.was_enabled=owner.ui_settings.sync_personalization
        self.timer=QTimer(self);self.timer.setSingleShot(True);self.timer.timeout.connect(self._start)
        self.finished.connect(self._complete);owner.settings_store.on_save=self.queue
        if pending_path(owner.user).exists():
            self.pending=deepcopy(owner.ui_settings);self.timer.start(0)
    def queue(self,settings):
        if not settings.sync_personalization and not self.was_enabled:return
        self.was_enabled=settings.sync_personalization;self.pending=deepcopy(settings);self.timer.start(250)
        pending_path(self.owner.user).touch()
    def status(self,message):
        self.owner._profile_sync_status=message
        panel=getattr(self.owner,"appearance_panel",None)
        if panel is not None and hasattr(panel,"sync_status"):panel.sync_status.setText(message)
    def _start(self):
        if self.running or self.pending is None:return
        settings=self.pending;self.pending=None;self.running=True
        auth,user=self.owner.workshop_manager.auth,self.owner.user
        self.status(tr("Синхронизация персонализации…"))
        def worker():
            try:auth.save_personalization(user,settings.sync_personalization,portable_config(settings));error=""
            except Exception as exc:error=str(exc)
            try:self.finished.emit(settings,error)
            except RuntimeError:pass
        threading.Thread(target=worker,name="SmartOrderProfileSync",daemon=True).start()
    def _complete(self,settings,error):
        self.running=False
        if error:
            self.status(tr("Не удалось синхронизировать персонализацию: ")+error)
            if self.pending is None:self.pending=settings
            self.timer.start(5000)
        else:
            if self.pending is None:pending_path(self.owner.user).unlink(missing_ok=True)
            self.status(tr("Персонализация синхронизирована.") if settings.sync_personalization else tr("Синхронизация отключена. Локальный конфиг сохранён."))
            if self.pending is not None:self.timer.start(0)
