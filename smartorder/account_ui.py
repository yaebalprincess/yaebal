"""Scrollable account editor with explicit action grants and scheduled activation."""
from PyQt5.QtCore import Qt, QDateTime
from PyQt5.QtWidgets import (QDialog,QVBoxLayout,QHBoxLayout,QFormLayout,QLineEdit,
    QLabel,QListWidget,QListWidgetItem,QAbstractItemView,QCheckBox,QDateTimeEdit,
    QScrollArea,QWidget,QGroupBox,QGridLayout,QDialogButtonBox,QPushButton)
from .security import ROLES,ALL_PERMISSIONS,PERMISSION_LABELS,DEFAULT_ROLE_PERMISSIONS,Permission,split_roles
from .i18n import tr,apply_language


class AccountDialog(QDialog):
    def __init__(self,username="",role="",require_password=True,parent=None,options=None):
        super().__init__(parent);self.require_password=require_password;self.options=options or {}
        self.setWindowTitle(tr("Создание нового пользователя" if require_password else "Редактирование пользователя"))
        self.setObjectName("ModalDialog");self.resize(820,760);self.setMinimumSize(560,460)
        root=QVBoxLayout(self);root.setContentsMargins(20,16,20,16)
        scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setFrameShape(QScrollArea.NoFrame)
        content=QWidget();body=QVBoxLayout(content);scroll.setWidget(content);root.addWidget(scroll,1)
        note=QLabel(tr("Заполните данные для нового пользователя" if require_password else "Измените данные пользователя"))
        note.setObjectName("UserDialogSubtitle");note.setProperty("fontRole","subtitle");note.setWordWrap(True);body.addWidget(note)
        form=QFormLayout();self.username=QLineEdit(username);self.username.setPlaceholderText(tr("Логин"))
        self.password=QLineEdit();self.password.setEchoMode(QLineEdit.Password)
        self.password.setPlaceholderText(tr("Пароль должен содержать не менее 8 символов." if require_password else "Оставьте пустым, чтобы не менять"))
        self.role_list=QListWidget();self.role_list.setObjectName("UserRoleList");self.role_list.setSelectionMode(QAbstractItemView.NoSelection);self.role_list.setMaximumHeight(155)
        selected=set(split_roles(role))
        for name in ROLES:
            item=QListWidgetItem(tr(name));item.setData(Qt.UserRole,name);item.setFlags(item.flags()|Qt.ItemIsUserCheckable);item.setCheckState(Qt.Checked if name in selected else Qt.Unchecked);self.role_list.addItem(item)
        form.addRow(tr("Логин:"),self.username);form.addRow(tr("Пароль:"),self.password);form.addRow(tr("Роли:"),self.role_list);body.addLayout(form)
        self.custom=QCheckBox(tr("Индивидуальные права доступа"));self.custom.setObjectName("CustomPermissions")
        self.custom.setChecked(self.options.get("permissions") is not None);body.addWidget(self.custom)
        explanation=QLabel(tr("Если флажок снят, действуют права выбранных ролей. Если установлен — только отмеченные ниже разрешения."));explanation.setWordWrap(True);body.addWidget(explanation)
        self.permission_box=QGroupBox(tr("Просмотр вкладок и действия"));grid=QGridLayout(self.permission_box);self.permission_checks={}
        for i,code in enumerate(ALL_PERMISSIONS):
            check=QCheckBox(tr(PERMISSION_LABELS[code]));check.setObjectName("Grant_"+code.replace(".","_"));check.setProperty("permissionCode",code)
            check.toggled.connect(lambda yes,c=code:self._permission_toggled(c,yes));grid.addWidget(check,i//2,i%2);self.permission_checks[code]=check
        body.addWidget(self.permission_box)
        role_defaults=QPushButton(tr("Использовать права роли"));role_defaults.clicked.connect(lambda:self.custom.setChecked(False));body.addWidget(role_defaults)
        self.schedule=QCheckBox(tr("Отложенная активация учётной записи"));self.schedule.setObjectName("ScheduleActivation")
        self.activation=QDateTimeEdit(QDateTime.currentDateTime().addDays(1));self.activation.setObjectName("AccountActivationDate");self.activation.setDisplayFormat("dd.MM.yyyy HH:mm")
        if self.options.get("activate_at"):
            self.schedule.setChecked(True);self.activation.setDateTime(QDateTime.fromString(self.options["activate_at"],Qt.ISODate))
        self.activation.setEnabled(self.schedule.isChecked());self.schedule.toggled.connect(self.activation.setEnabled)
        row=QHBoxLayout();row.addWidget(self.schedule);row.addWidget(self.activation);body.addLayout(row)
        hint=QLabel(tr("До указанного времени вход отключён. Учётная запись активируется автоматически при обращении к общей базе."));hint.setWordWrap(True);body.addWidget(hint);body.addStretch()
        self.validation=QLabel();self.validation.setObjectName("AccountValidation");self.validation.setWordWrap(True);root.addWidget(self.validation)
        buttons=QDialogButtonBox(QDialogButtonBox.Ok|QDialogButtonBox.Cancel);self.ok=buttons.button(QDialogButtonBox.Ok);self.ok.setText(tr("ОК"));self.ok.setObjectName("PrimaryButton")
        buttons.button(QDialogButtonBox.Cancel).setText(tr("Отмена"));buttons.accepted.connect(self.accept);buttons.rejected.connect(self.reject);root.addWidget(buttons)
        self.custom.toggled.connect(self._mode_changed);self.role_list.itemChanged.connect(self._role_changed)
        self.username.textChanged.connect(self._validate);self.password.textChanged.connect(self._validate)
        self.activation.dateTimeChanged.connect(self._validate);self.schedule.toggled.connect(self._validate)
        for code,check in self.permission_checks.items():check.setChecked(code in set(self.options.get("permissions") or ()))
        self._mode_changed(self.custom.isChecked());self._validate()
        if parent is not None and not parent.can(Permission.PERMISSIONS_MANAGE):
            self.custom.setEnabled(False);self.permission_box.setEnabled(False);role_defaults.setEnabled(False)
            if not require_password:self.role_list.setEnabled(False)
        from .heavy_ui import _apply_modal_theme
        _apply_modal_theme(self,parent);apply_language(self)

    def selected_roles(self):
        return ";".join(str(self.role_list.item(i).data(Qt.UserRole)) for i in range(self.role_list.count()) if self.role_list.item(i).checkState()==Qt.Checked)

    def _role_changed(self,*_):
        if not self.custom.isChecked():self._fill_defaults()
        self._validate()

    def _fill_defaults(self):
        permissions=set().union(*(DEFAULT_ROLE_PERMISSIONS.get(role,set()) for role in split_roles(self.selected_roles())))
        for code,check in self.permission_checks.items():
            old=check.blockSignals(True);check.setChecked(code in permissions);check.blockSignals(old)

    def _mode_changed(self,custom):
        self.permission_box.setEnabled(custom)
        if not custom:self._fill_defaults()

    def _permission_toggled(self,code,checked):
        group=code.split(".")[0];view=group+".view"
        if checked and view in self.permission_checks and code!=view:self.permission_checks[view].setChecked(True)
        if not checked and code==view:
            for other,check in self.permission_checks.items():
                if other.startswith(group+".") and other!=view:check.setChecked(False)

    def _validate(self,*_):
        valid=bool(self.username.text().strip() and self.selected_roles() and (len(self.password.text())>=8 or not self.require_password and not self.password.text()))
        past=self.schedule.isChecked() and self.activation.dateTime()<=QDateTime.currentDateTime()
        if past:valid=False
        if hasattr(self,"ok"):self.ok.setEnabled(valid)
        self.validation.setText(tr("Дата активации должна быть в будущем") if past else tr("Пароль должен содержать не менее 8 символов.") if self.password.text() and len(self.password.text())<8 else "")

    def account_options(self):
        return {"permissions":[code for code,check in self.permission_checks.items() if check.isChecked()] if self.custom.isChecked() else None,
                "activate_at":self.activation.dateTime().toPyDateTime().isoformat(timespec="seconds") if self.schedule.isChecked() else None}
