from __future__ import annotations

from PyQt5.QtWidgets import QApplication, QWidget

APPLE_QSS = '/*\n SmartOrder Apple-style design system for PyQt5.\n Apply on QApplication, then set objectName/dynamic properties where noted:\n - root window: objectName="SmartOrderWindow", property theme="light" or "dark"\n - major surfaces: objectName="AppShell", "GlassPanel", "Toolbar", "StatusBar"\n - buttons: objectName="PrimaryButton", "SecondaryButton", "DangerButton", "GhostButton", "IconButton"\n - login: objectName="LoginDialog", "LoginCard"\n - toast: objectName="Toast", property type="success|warning|error|info"\n\n Qt QSS does not support CSS transitions, transform/scale, box-shadow, or backdrop-filter.\n Use QPropertyAnimation and QGraphicsEffect for motion, blur, and real shadows.\n*/\n\n/* Base */\nQMainWindow#SmartOrderWindow,\nQDialog,\nQWidget#AppShell {\n    background-color: #F5F5F7;\n    color: #1D1D1F;\n    font-family: "SF Pro Display", "Inter", "Segoe UI", "Arial";\n    font-size: 13px;\n}\n\nQWidget[theme="dark"],\nQMainWindow#SmartOrderWindow[theme="dark"],\nQWidget#AppShell[theme="dark"],\nQDialog[theme="dark"] {\n    background-color: #1C1C1E;\n    color: #F5F5F7;\n}\n\nQLabel {\n    color: #1D1D1F;\n    background: transparent;\n}\n\nQWidget[theme="dark"] QLabel,\nQDialog[theme="dark"] QLabel {\n    color: #F5F5F7;\n}\n\nQLabel#TitleLabel {\n    font-size: 22px;\n    font-weight: 700;\n}\n\nQLabel#SubtitleLabel,\nQLabel#MutedLabel {\n    color: #6E6E73;\n    font-size: 12px;\n}\n\nQWidget[theme="dark"] QLabel#SubtitleLabel,\nQWidget[theme="dark"] QLabel#MutedLabel,\nQDialog[theme="dark"] QLabel#SubtitleLabel,\nQDialog[theme="dark"] QLabel#MutedLabel {\n    color: #A1A1AA;\n}\n\n/* Premium surfaces */\nQWidget#GlassPanel,\nQFrame#GlassPanel,\nQWidget#LoginCard,\nQFrame#LoginCard {\n    background-color: rgba(255, 255, 255, 218);\n    border: 1px solid rgba(255, 255, 255, 150);\n    border-radius: 16px;\n}\n\nQWidget[theme="dark"] QWidget#GlassPanel,\nQWidget[theme="dark"] QFrame#GlassPanel,\nQDialog[theme="dark"] QWidget#LoginCard,\nQDialog[theme="dark"] QFrame#LoginCard {\n    background-color: rgba(44, 44, 46, 220);\n    border: 1px solid rgba(255, 255, 255, 32);\n}\n\nQWidget#Toolbar,\nQFrame#Toolbar {\n    background-color: rgba(255, 255, 255, 190);\n    border-bottom: 1px solid rgba(60, 60, 67, 35);\n}\n\nQWidget[theme="dark"] QWidget#Toolbar,\nQWidget[theme="dark"] QFrame#Toolbar {\n    background-color: rgba(28, 28, 30, 205);\n    border-bottom: 1px solid rgba(255, 255, 255, 24);\n}\n\nQStatusBar,\nQWidget#StatusBar {\n    background-color: rgba(255, 255, 255, 170);\n    color: #6E6E73;\n    border-top: 1px solid rgba(60, 60, 67, 28);\n}\n\nQWidget[theme="dark"] QStatusBar,\nQWidget[theme="dark"] QWidget#StatusBar {\n    background-color: rgba(28, 28, 30, 190);\n    color: #A1A1AA;\n    border-top: 1px solid rgba(255, 255, 255, 22);\n}\n\n/* Buttons */\nQPushButton {\n    min-height: 34px;\n    padding: 7px 16px;\n    border: 1px solid rgba(60, 60, 67, 32);\n    border-radius: 10px;\n    background-color: rgba(255, 255, 255, 210);\n    color: #1D1D1F;\n    font-weight: 600;\n}\n\nQPushButton:hover {\n    background-color: rgba(255, 255, 255, 245);\n    border-color: rgba(0, 122, 255, 105);\n    color: #007AFF;\n}\n\nQPushButton:pressed {\n    background-color: rgba(0, 122, 255, 30);\n    border-color: rgba(0, 122, 255, 150);\n    padding-top: 8px;\n    padding-bottom: 6px;\n}\n\nQPushButton:disabled {\n    background-color: rgba(120, 120, 128, 24);\n    border-color: rgba(120, 120, 128, 28);\n    color: rgba(60, 60, 67, 80);\n}\n\nQWidget[theme="dark"] QPushButton,\nQDialog[theme="dark"] QPushButton {\n    background-color: rgba(58, 58, 60, 220);\n    border-color: rgba(255, 255, 255, 28);\n    color: #F5F5F7;\n}\n\nQWidget[theme="dark"] QPushButton:hover,\nQDialog[theme="dark"] QPushButton:hover {\n    background-color: rgba(72, 72, 74, 245);\n    border-color: rgba(10, 132, 255, 140);\n    color: #0A84FF;\n}\n\nQPushButton#PrimaryButton {\n    background-color: #007AFF;\n    border-color: #007AFF;\n    color: white;\n}\n\nQPushButton#PrimaryButton:hover {\n    background-color: #0A84FF;\n    border-color: #0A84FF;\n    color: white;\n}\n\nQPushButton#PrimaryButton:pressed {\n    background-color: #0066D6;\n    border-color: #0066D6;\n}\n\nQPushButton#SecondaryButton {\n    background-color: rgba(0, 122, 255, 18);\n    border-color: rgba(0, 122, 255, 80);\n    color: #007AFF;\n}\n\nQPushButton#DangerButton {\n    background-color: rgba(255, 59, 48, 18);\n    border-color: rgba(255, 59, 48, 95);\n    color: #FF3B30;\n}\n\nQPushButton#DangerButton:hover {\n    background-color: #FF3B30;\n    border-color: #FF3B30;\n    color: white;\n}\n\nQPushButton#GhostButton,\nQPushButton#IconButton {\n    background-color: transparent;\n    border-color: transparent;\n    color: #007AFF;\n}\n\nQPushButton#IconButton {\n    min-width: 32px;\n    max-width: 32px;\n    min-height: 32px;\n    max-height: 32px;\n    padding: 0px;\n    border-radius: 8px;\n}\n\nQPushButton#GhostButton:hover,\nQPushButton#IconButton:hover {\n    background-color: rgba(0, 122, 255, 18);\n}\n\n/* Inputs */\nQLineEdit,\nQTextEdit,\nQPlainTextEdit,\nQSpinBox,\nQDoubleSpinBox,\nQDateEdit,\nQComboBox {\n    min-height: 34px;\n    padding: 6px 10px;\n    border: 1px solid rgba(60, 60, 67, 32);\n    border-radius: 10px;\n    background-color: rgba(255, 255, 255, 235);\n    color: #1D1D1F;\n    selection-background-color: #007AFF;\n    selection-color: white;\n}\n\nQLineEdit:hover,\nQTextEdit:hover,\nQPlainTextEdit:hover,\nQSpinBox:hover,\nQDoubleSpinBox:hover,\nQDateEdit:hover,\nQComboBox:hover {\n    border-color: rgba(0, 122, 255, 95);\n}\n\nQLineEdit:focus,\nQTextEdit:focus,\nQPlainTextEdit:focus,\nQSpinBox:focus,\nQDoubleSpinBox:focus,\nQDateEdit:focus,\nQComboBox:focus {\n    border: 2px solid #007AFF;\n    padding: 5px 9px;\n    background-color: white;\n}\n\nQLineEdit:disabled,\nQTextEdit:disabled,\nQPlainTextEdit:disabled,\nQComboBox:disabled,\nQDateEdit:disabled {\n    background-color: rgba(120, 120, 128, 18);\n    color: rgba(60, 60, 67, 80);\n}\n\nQWidget[theme="dark"] QLineEdit,\nQWidget[theme="dark"] QTextEdit,\nQWidget[theme="dark"] QPlainTextEdit,\nQWidget[theme="dark"] QSpinBox,\nQWidget[theme="dark"] QDoubleSpinBox,\nQWidget[theme="dark"] QDateEdit,\nQWidget[theme="dark"] QComboBox,\nQDialog[theme="dark"] QLineEdit,\nQDialog[theme="dark"] QTextEdit,\nQDialog[theme="dark"] QPlainTextEdit,\nQDialog[theme="dark"] QSpinBox,\nQDialog[theme="dark"] QDoubleSpinBox,\nQDialog[theme="dark"] QDateEdit,\nQDialog[theme="dark"] QComboBox {\n    background-color: rgba(58, 58, 60, 235);\n    border-color: rgba(255, 255, 255, 30);\n    color: #F5F5F7;\n}\n\nQComboBox::drop-down,\nQDateEdit::drop-down {\n    width: 28px;\n    border: none;\n    border-left: 1px solid rgba(60, 60, 67, 22);\n}\n\nQComboBox QAbstractItemView {\n    padding: 6px;\n    border: 1px solid rgba(60, 60, 67, 36);\n    border-radius: 10px;\n    background-color: white;\n    selection-background-color: rgba(0, 122, 255, 24);\n    selection-color: #007AFF;\n    outline: 0;\n}\n\n/* Xcode-like tabs */\nQTabWidget::pane {\n    border: none;\n    top: -1px;\n    background: transparent;\n}\n\nQTabBar {\n    background: transparent;\n}\n\nQTabBar::tab {\n    min-height: 34px;\n    padding: 8px 16px;\n    margin-right: 4px;\n    border: none;\n    border-bottom: 2px solid transparent;\n    background: transparent;\n    color: #6E6E73;\n    font-weight: 700;\n}\n\nQTabBar::tab:hover {\n    color: #007AFF;\n    background-color: rgba(0, 122, 255, 12);\n    border-radius: 9px;\n}\n\nQTabBar::tab:selected {\n    color: #007AFF;\n    border-bottom: 2px solid #007AFF;\n}\n\nQWidget[theme="dark"] QTabBar::tab,\nQDialog[theme="dark"] QTabBar::tab {\n    color: #A1A1AA;\n}\n\nQWidget[theme="dark"] QTabBar::tab:selected,\nQDialog[theme="dark"] QTabBar::tab:selected {\n    color: #0A84FF;\n    border-bottom-color: #0A84FF;\n}\n\n/* Tables */\nQTableView,\nQTableWidget {\n    gridline-color: rgba(60, 60, 67, 22);\n    border: 1px solid rgba(60, 60, 67, 28);\n    border-radius: 12px;\n    background-color: rgba(255, 255, 255, 225);\n    alternate-background-color: rgba(242, 242, 247, 150);\n    color: #1D1D1F;\n    selection-background-color: rgba(0, 122, 255, 34);\n    selection-color: #1D1D1F;\n    outline: 0;\n}\n\nQTableView::item,\nQTableWidget::item {\n    min-height: 32px;\n    padding: 6px 10px;\n    border: none;\n}\n\nQTableView::item:hover,\nQTableWidget::item:hover {\n    background-color: rgba(0, 122, 255, 14);\n}\n\nQTableView::item:selected,\nQTableWidget::item:selected {\n    background-color: rgba(0, 122, 255, 42);\n    color: #1D1D1F;\n}\n\nQHeaderView {\n    background: transparent;\n}\n\nQHeaderView::section {\n    min-height: 34px;\n    padding: 7px 10px;\n    border: none;\n    border-bottom: 1px solid rgba(60, 60, 67, 28);\n    background-color: rgba(242, 242, 247, 230);\n    color: #6E6E73;\n    font-weight: 700;\n}\n\nQHeaderView::section:first {\n    border-top-left-radius: 12px;\n}\n\nQHeaderView::section:last {\n    border-top-right-radius: 12px;\n}\n\nQWidget[theme="dark"] QTableView,\nQWidget[theme="dark"] QTableWidget,\nQDialog[theme="dark"] QTableView,\nQDialog[theme="dark"] QTableWidget {\n    background-color: rgba(44, 44, 46, 235);\n    alternate-background-color: rgba(58, 58, 60, 150);\n    border-color: rgba(255, 255, 255, 26);\n    gridline-color: rgba(255, 255, 255, 18);\n    color: #F5F5F7;\n    selection-background-color: rgba(10, 132, 255, 48);\n    selection-color: #F5F5F7;\n}\n\nQWidget[theme="dark"] QHeaderView::section,\nQDialog[theme="dark"] QHeaderView::section {\n    background-color: rgba(58, 58, 60, 235);\n    color: #A1A1AA;\n    border-bottom-color: rgba(255, 255, 255, 24);\n}\n\n/* Dialogs and toast */\nQDialog#LoginDialog {\n    background-color: rgba(245, 245, 247, 245);\n    border-radius: 16px;\n}\n\nQDialog#ModalDialog,\nQMessageBox {\n    background-color: #F5F5F7;\n    border-radius: 16px;\n}\n\nQWidget#Toast {\n    padding: 10px 14px;\n    border-radius: 12px;\n    background-color: rgba(44, 44, 46, 235);\n    color: white;\n    border: 1px solid rgba(255, 255, 255, 34);\n}\n\nQWidget#Toast[type="success"] {\n    background-color: rgba(52, 199, 89, 235);\n}\n\nQWidget#Toast[type="warning"] {\n    background-color: rgba(255, 149, 0, 235);\n}\n\nQWidget#Toast[type="error"] {\n    background-color: rgba(255, 59, 48, 235);\n}\n\nQWidget#Toast[type="info"] {\n    background-color: rgba(0, 122, 255, 235);\n}\n\n/* Controls */\nQCheckBox,\nQRadioButton {\n    spacing: 8px;\n    color: #1D1D1F;\n}\n\nQWidget[theme="dark"] QCheckBox,\nQWidget[theme="dark"] QRadioButton,\nQDialog[theme="dark"] QCheckBox,\nQDialog[theme="dark"] QRadioButton {\n    color: #F5F5F7;\n}\n\nQCheckBox::indicator,\nQRadioButton::indicator {\n    width: 18px;\n    height: 18px;\n}\n\nQCheckBox::indicator {\n    border-radius: 5px;\n    border: 1px solid rgba(60, 60, 67, 60);\n    background-color: rgba(255, 255, 255, 220);\n}\n\nQCheckBox::indicator:checked {\n    background-color: #007AFF;\n    border-color: #007AFF;\n}\n\nQRadioButton::indicator {\n    border-radius: 9px;\n    border: 1px solid rgba(60, 60, 67, 60);\n    background-color: rgba(255, 255, 255, 220);\n}\n\nQRadioButton::indicator:checked {\n    border: 5px solid #007AFF;\n    background-color: white;\n}\n\nQSlider::groove:horizontal {\n    height: 5px;\n    border-radius: 3px;\n    background-color: rgba(120, 120, 128, 45);\n}\n\nQSlider::sub-page:horizontal {\n    border-radius: 3px;\n    background-color: #007AFF;\n}\n\nQSlider::handle:horizontal {\n    width: 18px;\n    height: 18px;\n    margin: -7px 0px;\n    border-radius: 9px;\n    background-color: white;\n    border: 1px solid rgba(60, 60, 67, 35);\n}\n\n/* Scrollbars */\nQScrollBar:vertical,\nQScrollBar:horizontal {\n    background: transparent;\n    border: none;\n    margin: 2px;\n}\n\nQScrollBar:vertical {\n    width: 12px;\n}\n\nQScrollBar:horizontal {\n    height: 12px;\n}\n\nQScrollBar::handle:vertical,\nQScrollBar::handle:horizontal {\n    min-height: 28px;\n    min-width: 28px;\n    border-radius: 6px;\n    background-color: rgba(60, 60, 67, 38);\n}\n\nQScrollBar::handle:vertical:hover,\nQScrollBar::handle:horizontal:hover {\n    background-color: rgba(60, 60, 67, 72);\n}\n\nQScrollBar::add-line,\nQScrollBar::sub-line,\nQScrollBar::add-page,\nQScrollBar::sub-page {\n    width: 0px;\n    height: 0px;\n    background: transparent;\n}\n\n/* Lists */\nQListWidget,\nQTreeWidget {\n    border: 1px solid rgba(60, 60, 67, 28);\n    border-radius: 12px;\n    background-color: rgba(255, 255, 255, 225);\n    outline: 0;\n}\n\nQListWidget::item,\nQTreeWidget::item {\n    min-height: 30px;\n    padding: 6px 10px;\n    border-radius: 8px;\n}\n\nQListWidget::item:selected,\nQTreeWidget::item:selected {\n    background-color: rgba(0, 122, 255, 34);\n    color: #007AFF;\n}\n\n/* Utility object names */\nQFrame#Divider {\n    min-height: 1px;\n    max-height: 1px;\n    background-color: rgba(60, 60, 67, 28);\n    border: none;\n}\n\nQWidget[theme="dark"] QFrame#Divider {\n    background-color: rgba(255, 255, 255, 24);\n}\n\n\nQGroupBox {\n    border: 1px solid rgba(60, 60, 67, 28);\n    border-radius: 14px;\n    margin-top: 12px;\n    padding: 14px;\n    background-color: rgba(255, 255, 255, 170);\n    font-weight: 700;\n}\nQGroupBox::title {\n    subcontrol-origin: margin;\n    left: 14px;\n    padding: 0 8px;\n    color: #007AFF;\n}\nQWidget[theme="dark"] QGroupBox, QDialog[theme="dark"] QGroupBox {\n    background-color: rgba(44, 44, 46, 180);\n    border-color: rgba(255, 255, 255, 28);\n}\nQDialogButtonBox QPushButton {\n    min-width: 96px;\n}\n\n/* Every interactive row should visibly react on hover in both themes */\nQTableWidget::item:hover, QTableView::item:hover, QListWidget::item:hover, QTreeWidget::item:hover {\n    background-color: rgba(0, 122, 255, 26);\n    color: #007AFF;\n}\nQWidget[theme="dark"] QTableWidget::item:hover,\nQWidget[theme="dark"] QTableView::item:hover,\nQWidget[theme="dark"] QListWidget::item:hover,\nQWidget[theme="dark"] QTreeWidget::item:hover,\nQDialog[theme="dark"] QTableWidget::item:hover,\nQDialog[theme="dark"] QListWidget::item:hover {\n    background-color: rgba(10, 132, 255, 46);\n    color: #F5F5F7;\n}\nQTableWidget::item:selected, QTableView::item:selected, QListWidget::item:selected {\n    background-color: rgba(0, 122, 255, 44);\n    color: #007AFF;\n}\nQWidget[theme="dark"] QTableWidget::item:selected,\nQWidget[theme="dark"] QTableView::item:selected,\nQWidget[theme="dark"] QListWidget::item:selected,\nQDialog[theme="dark"] QTableWidget::item:selected,\nQDialog[theme="dark"] QListWidget::item:selected {\n    background-color: rgba(10, 132, 255, 64);\n    color: #FFFFFF;\n}\n/* Buttons: same hover/pressed feedback in light and dark */\nQPushButton:hover {\n    background-color: rgba(0, 122, 255, 30);\n    border-color: rgba(0, 122, 255, 150);\n    color: #007AFF;\n}\nQWidget[theme="dark"] QPushButton:hover, QDialog[theme="dark"] QPushButton:hover {\n    background-color: rgba(10, 132, 255, 38);\n    border-color: rgba(10, 132, 255, 170);\n    color: #0A84FF;\n}\nQPushButton:pressed {\n    background-color: rgba(0, 122, 255, 62);\n    padding-top: 9px;\n    padding-bottom: 5px;\n}\n/* Work order group boxes: title no longer intersects the border */\nQGroupBox {\n    margin-top: 26px;\n    padding: 24px 14px 14px 14px;\n    border: 1px solid rgba(60, 60, 67, 34);\n    border-radius: 14px;\n    background-color: rgba(255, 255, 255, 205);\n    color: #1D1D1F;\n    font-weight: 700;\n}\nQGroupBox::title {\n    subcontrol-origin: margin;\n    subcontrol-position: top left;\n    left: 14px;\n    top: 5px;\n    padding: 2px 10px;\n    border-radius: 8px;\n    background-color: #F5F5F7;\n    color: #007AFF;\n}\nQWidget[theme="dark"] QGroupBox, QDialog[theme="dark"] QGroupBox {\n    background-color: rgba(44, 44, 46, 226);\n    border-color: rgba(255, 255, 255, 34);\n    color: #F5F5F7;\n}\nQWidget[theme="dark"] QGroupBox::title, QDialog[theme="dark"] QGroupBox::title {\n    background-color: #1C1C1E;\n    color: #0A84FF;\n}\nQGroupBox#BackupGroup {\n    background-color: rgba(255, 255, 255, 94);\n}\nQWidget[theme="dark"] QGroupBox#BackupGroup {\n    background-color: rgba(58, 58, 60, 78);\n    border-color: rgba(255, 255, 255, 22);\n}\nQGroupBox#BackupGroup QPushButton#GhostButton,\nQGroupBox#BackupGroup QLabel {\n    background-color: transparent;\n}\n/* QMessageBox must be readable even when parent window is dark */\nQMessageBox, QMessageBox QWidget {\n    background-color: #FFFFFF;\n    color: #1D1D1F;\n}\nQMessageBox QLabel {\n    color: #1D1D1F;\n    background-color: transparent;\n}\nQMessageBox QPushButton {\n    color: #1D1D1F;\n    background-color: #FFFFFF;\n    min-width: 104px;\n    border: 1px solid rgba(60, 60, 67, 50);\n    border-radius: 9px;\n}\nQMessageBox QPushButton:hover {\n    color: #007AFF;\n    background-color: rgba(0, 122, 255, 18);\n    border-color: #007AFF;\n}\nQLabel#SessionLabel {\n    color: #8E8E93;\n    font-size: 11px;\n    background: transparent;\n}\nQLabel#EditModeLabel {\n    color: #30D158;\n    font-weight: 900;\n    background: transparent;\n}\n\nQMessageBox, QMessageBox QWidget {\n    background-color: #FFFFFF;\n    color: #1D1D1F;\n}\nQMessageBox QLabel {\n    color: #1D1D1F;\n    background-color: transparent;\n    font-size: 13px;\n}\nQMessageBox QPushButton {\n    min-width: 110px;\n    min-height: 34px;\n    color: #1D1D1F;\n    background-color: #FFFFFF;\n    border: 1px solid rgba(60,60,67,50);\n    border-radius: 9px;\n}\nQMessageBox QPushButton:hover {\n    color: #007AFF;\n    border-color: #007AFF;\n    background-color: rgba(0,122,255,18);\n}\nQWidget[theme="dark"] QGroupBox#BackupGroup,\nQGroupBox#BackupGroup {\n    background-color: transparent;\n}\nQGroupBox#BackupGroup QPushButton#GhostButton,\nQGroupBox#BackupGroup QLabel {\n    background-color: transparent;\n}\nQTableWidget::item:hover,\nQTableView::item:hover,\nQListWidget::item:hover {\n    background-color: rgba(0,122,255,24);\n}\nQWidget[theme="dark"] QTableWidget::item:hover,\nQWidget[theme="dark"] QTableView::item:hover,\nQWidget[theme="dark"] QListWidget::item:hover {\n    background-color: rgba(10,132,255,38);\n}\n\n/* v12: compact admin, readable dialogs, gray order header in dark theme */\nQGroupBox#OrderInfoGroup {\n    background-color: rgba(255,255,255,205);\n    border-color: rgba(60,60,67,34);\n    margin-top: 28px;\n    padding-top: 26px;\n}\nQGroupBox#OrderInfoGroup::title {\n    background-color: #F5F5F7;\n    color: #007AFF;\n    padding: 3px 10px;\n    border-radius: 8px;\n}\nQDialog[theme="dark"] QGroupBox#OrderInfoGroup,\nQWidget[theme="dark"] QGroupBox#OrderInfoGroup {\n    background-color: rgba(58,58,60,220);\n    border-color: rgba(255,255,255,34);\n    color: #F5F5F7;\n}\nQDialog[theme="dark"] QGroupBox#OrderInfoGroup::title,\nQWidget[theme="dark"] QGroupBox#OrderInfoGroup::title {\n    background-color: #2C2C2E;\n    color: #0A84FF;\n}\nQTableWidget::item:hover,\nQTableView::item:hover,\nQListWidget::item:hover,\nQComboBox QAbstractItemView::item:hover {\n    background-color: rgba(0,122,255,30);\n    color: #007AFF;\n}\nQWidget[theme="dark"] QTableWidget::item:hover,\nQWidget[theme="dark"] QTableView::item:hover,\nQWidget[theme="dark"] QListWidget::item:hover,\nQDialog[theme="dark"] QTableWidget::item:hover,\nQDialog[theme="dark"] QTableView::item:hover,\nQDialog[theme="dark"] QListWidget::item:hover {\n    background-color: rgba(10,132,255,46);\n    color: #FFFFFF;\n}\nQGroupBox#BackupGroup {\n    padding: 10px;\n    margin-top: 18px;\n    background-color: rgba(255,255,255,80);\n}\nQWidget[theme="dark"] QGroupBox#BackupGroup {\n    background-color: rgba(58,58,60,64);\n}\nQGroupBox#BackupGroup QPushButton,\nQGroupBox#BackupGroup QComboBox {\n    min-height: 30px;\n    padding-top: 4px;\n    padding-bottom: 4px;\n}\nQGroupBox#BackupGroup QPushButton#GhostButton,\nQGroupBox#BackupGroup QLabel {\n    background-color: transparent;\n}\nQTextEdit#HistoryTextEdit {\n    border: 1px solid rgba(60,60,67,32);\n    border-radius: 14px;\n    padding: 14px;\n    background-color: rgba(255,255,255,235);\n    color: #1D1D1F;\n    font-size: 13px;\n}\nQDialog[theme="dark"] QTextEdit#HistoryTextEdit,\nQWidget[theme="dark"] QTextEdit#HistoryTextEdit {\n    background-color: rgba(44,44,46,235);\n    color: #F5F5F7;\n    border-color: rgba(255,255,255,28);\n}\n\n\n/* v27 final polish */\nQPushButton#LinkButton {\n    background: transparent;\n    border: 1px solid transparent;\n    color: #007AFF;\n    font-weight: 800;\n    padding: 4px 8px;\n    min-height: 28px;\n    border-radius: 8px;\n}\nQPushButton#LinkButton:hover {\n    background-color: rgba(0,122,255,24);\n    border-color: rgba(0,122,255,80);\n    color: #005CCB;\n}\nQLabel#AuditTitleLabel, QLabel#AuditHelpLabel {\n    color: #007AFF;\n    font-weight: 900;\n    background: transparent;\n}\nQLabel#AuditHelpLabel {\n    border-radius: 9px;\n    padding: 1px 6px;\n}\nQLabel#AuditHelpLabel:hover {\n    background-color: rgba(0,122,255,24);\n}\nQGroupBox#AuditGroup, QWidget#AuditPanel {\n    background-color: #E9E9EE;\n    border: 1px solid rgba(60,60,67,32);\n    border-radius: 14px;\n}\nQWidget[theme="dark"] QGroupBox#AuditGroup, QWidget[theme="dark"] QWidget#AuditPanel {\n    background-color: #3A3A3C;\n    border-color: rgba(255,255,255,32);\n}\nQTableWidget#AuditTable {\n    background-color: #EFEFF4;\n    alternate-background-color: #F7F7FA;\n    border-radius: 12px;\n}\nQWidget[theme="dark"] QTableWidget#AuditTable {\n    background-color: #3A3A3C;\n    alternate-background-color: #444446;\n}\nQLabel#GlobalEditModeLabel, QLabel#WorkTypeFixedEditLabel, QLabel#EmployeeFixedEditLabel {\n    color: #30D158;\n    font-weight: 900;\n    background: transparent;\n}\nQLineEdit#Win10DateRangeEdit {\n    min-width: 260px;\n    padding-right: 54px;\n    font-weight: 700;\n}\nQFrame#Win10CalendarPopup {\n    background: #FFFFFF;\n    border: 1px solid #C8C8C8;\n    border-radius: 2px;\n}\nQFrame#Win10CalendarPopup QLabel {\n    color: #1D1D1F;\n    background: transparent;\n}\nQFrame#Win10CalendarPopup QPushButton {\n    min-height: 28px;\n    padding: 4px 10px;\n    border-radius: 2px;\n    background: #FFFFFF;\n    color: #1D1D1F;\n    border: 1px solid transparent;\n}\nQFrame#Win10CalendarPopup QPushButton:hover {\n    background: #E5F1FB;\n    border-color: #99D1FF;\n    color: #0067B8;\n}\nQCalendarWidget#Win10Calendar QWidget {\n    background: #FFFFFF;\n    color: #1D1D1F;\n}\nQCalendarWidget#Win10Calendar QAbstractItemView {\n    background: #FFFFFF;\n    color: #1D1D1F;\n    selection-background-color: #0078D7;\n    selection-color: white;\n    outline: 0;\n    border: none;\n}\nQCalendarWidget#Win10Calendar QAbstractItemView::item:hover {\n    background-color: #E5F1FB;\n    color: #1D1D1F;\n}\nQCalendarWidget#Win10Calendar QToolButton {\n    background: #FFFFFF;\n    color: #1D1D1F;\n    border: 1px solid transparent;\n    border-radius: 2px;\n    padding: 4px 8px;\n}\nQCalendarWidget#Win10Calendar QToolButton:hover {\n    background: #E5F1FB;\n    border-color: #99D1FF;\n}\nQCalendarWidget#Win10Calendar QSpinBox {\n    background: #FFFFFF;\n    color: #1D1D1F;\n    border: 1px solid #C8C8C8;\n}\nQTableWidget#WorkTypeSelectTable {\n    background: #FFFFFF;\n    color: #1D1D1F;\n    border-radius: 10px;\n}\nQTableWidget#WorkTypeSelectTable::item:hover {\n    background: rgba(0,122,255,26);\n}\n\n\n/* v31 stable UI */\nQTableWidget#UsersTableV31 {\n    background-color: rgba(255,255,255,235);\n    alternate-background-color: #F7F7FA;\n}\nQTableWidget#AuditTable {\n    background-color: #ECECF1;\n    alternate-background-color: #F7F7FA;\n    border: 1px solid rgba(60,60,67,32);\n    border-radius: 12px;\n}\nQWidget[theme="dark"] QTableWidget#AuditTable {\n    background-color: #3A3A3C;\n    alternate-background-color: #444446;\n    border-color: rgba(255,255,255,28);\n}\nQDialog QGroupBox#OrderInfoGroup,\nQDialog[theme="light"] QGroupBox#OrderInfoGroup {\n    background-color: #F5F5F7;\n    border: 1px solid rgba(60,60,67,30);\n}\nQDialog QGroupBox#OrderInfoGroup QLabel,\nQDialog[theme="light"] QGroupBox#OrderInfoGroup QLabel {\n    background: transparent;\n    color: #1D1D1F;\n    padding: 0px;\n}\nQDialog[theme="dark"] QGroupBox#OrderInfoGroup {\n    background-color: #3A3A3C;\n    border-color: rgba(255,255,255,30);\n}\nQDialog[theme="dark"] QGroupBox#OrderInfoGroup QLabel {\n    background: transparent;\n    color: #F5F5F7;\n}\nQComboBox#ShiftTypeComboV31 {\n    min-width: 360px;\n}\nQComboBox#ShiftTypeComboV31 QAbstractItemView {\n    min-width: 360px;\n    font-size: 14px;\n    padding: 6px;\n}\nQPushButton#ThemeToggleButtonV31, QCheckBox#ThemeToggleButtonV31 {\n    border-radius: 12px;\n}\nQPushButton#ThemeToggleButtonV31:hover, QCheckBox#ThemeToggleButtonV31:hover {\n    background-color: rgba(0,122,255,28);\n}\nQScrollBar:vertical {\n    width: 13px;\n}\nQScrollBar::handle:vertical {\n    min-height: 34px;\n    border-radius: 6px;\n    background-color: rgba(60,60,67,58);\n}\nQWidget[theme="dark"] QScrollBar::handle:vertical {\n    background-color: rgba(255,255,255,70);\n}\n\n\n/* v32: admin action buttons must fit into the action column */\nQTableWidget#UsersTableV32 {\n    background-color: rgba(255,255,255,235);\n    alternate-background-color: #F7F7FA;\n}\nQTableWidget#UsersTableV32 QPushButton {\n    min-height: 32px;\n    max-height: 34px;\n    padding: 5px 8px;\n    font-size: 12px;\n    border-radius: 9px;\n}\nQTableWidget#UsersTableV32 QWidget {\n    background: transparent;\n}\nQWidget[theme="dark"] QTableWidget#UsersTableV32 {\n    background-color: rgba(44,44,46,235);\n    alternate-background-color: rgba(58,58,60,150);\n}\nQComboBox#OrderDialogComboV32 {\n    min-width: 390px;\n}\nQComboBox#OrderFilterComboV32 {\n    min-width: 230px;\n}\n'

def runtime_qss(zoom: int = 100) -> str:
    z=max(0.50,min(2.00,float(zoom)/100.0))
    base=max(11,int(13*z))
    tab=max(12,int(14*z))
    table=max(11,int(13*z))
    # RC18: zoom grows text, not dead space.  At large zoom levels old builds
    # doubled button paddings/heights as well as the font and caused Admin/History
    # panels to collide.  Keep controls compact while still scaling typography.
    # Keep control boxes derived from the base values.  At high zoom the
    # larger font needs a taller input/button, while ResponsiveGrid handles
    # the horizontal reflow so controls never overlap.
    compact=min(z,1.50)
    btn_h=max(34,int(36*compact))
    # Typography grows with zoom while the empty horizontal padding shrinks;
    # this keeps action buttons readable without pushing the last table
    # columns off-screen at 150–200%.
    btn_pad=max(5,int(11/(0.75+0.25*z)))
    input_pad=max(5,int(10/(0.75+0.25*z)))
    input_h=max(34,int(34*compact))
    tab_h=max(36,int(38*compact))
    tab_min=max(130,int(130*z))
    return f"""
QMainWindow#SmartOrderWindow, QDialog, QWidget#AppShell {{ font-size:{base}px; }}
QPushButton,QLineEdit,QDateEdit,QComboBox,QRadioButton,QCheckBox {{ font-size:{base}px; }}
QPushButton {{ min-height:{btn_h}px; padding-left:{btn_pad}px; padding-right:{btn_pad}px; }}
QLineEdit,QDateEdit,QComboBox,QSpinBox,QDoubleSpinBox {{ min-height:{input_h}px; padding-left:{input_pad}px; padding-right:{input_pad}px; }}
QTabBar::tab {{ min-width:{tab_min}px; min-height:{tab_h}px; padding-left:{max(8,int(10*compact))}px; padding-right:{max(8,int(10*compact))}px; font-size:{tab}px; font-weight:800; }}
QTableWidget,QTableView,QListWidget {{ font-size:{table}px; }}
QLabel#DbStateOk {{ color:#30D158; font-weight:800; }}
QLabel#DbStateSlow {{ color:#FF9F0A; font-weight:800; }}
QLabel#DbStateBad {{ color:#FF453A; font-weight:800; }}
QPushButton#ScrollTopButton {{ min-width:54px; max-width:54px; min-height:54px; max-height:54px; padding:0; }}
"""

def set_theme_recursive(widget: QWidget, theme: str) -> None:
    try:
        changed = widget.property("theme") != theme
        widget.setProperty("theme", theme)
        if hasattr(widget, "setTheme"):
            try: widget.setTheme(theme)
            except Exception: pass
        if changed:widget.style().unpolish(widget); widget.style().polish(widget); widget.update()
    except Exception:
        pass
    try:
        for child in widget.findChildren(QWidget):
            changed = child.property("theme") != theme
            child.setProperty("theme", theme)
            if hasattr(child, "setTheme"):
                try: child.setTheme(theme)
                except Exception: pass
            try:
                if changed:child.style().unpolish(child); child.style().polish(child); child.update()
            except Exception:
                pass
    except Exception:
        pass

def apply_apple_design(root=None, theme: str = "light", zoom: int = 100) -> None:
    import json
    from .liquid_style import liquid_qss
    from .liquid_effects import install_liquid_effects
    from .appearance import appearance_of, font_for
    app=QApplication.instance()
    if app is not None:
        # Setting an identical application stylesheet still re-polishes every
        # widget, including hidden combo containers. Change it only for new fonts.
        appearance = appearance_of(root)
        font_key=json.dumps(appearance["fonts"],sort_keys=True)
        key = font_key
        changed = getattr(app, "_smartorder_stylesheet_key", None) != key
        app._liquid_appearance = appearance
        if getattr(app, "_smartorder_stylesheet_key", None) != key:
            app.setStyleSheet(liquid_qss(100, appearance))
            if getattr(app,"_smartorder_font_key",None)!=font_key:
                app.setFont(font_for("body",100,appearance));app._smartorder_font_key=font_key
            app._smartorder_stylesheet_key = key
            app._smartorder_stylesheet_zoom = 100
        if getattr(app,"_liquid_theme",None)!=theme:
            from PyQt5.QtGui import QPalette,QColor
            from .liquid_style import colors
            pal=app.palette();base=QColor(colors(theme=="dark")["base"])
            for role in (QPalette.Window,QPalette.Base,QPalette.Button):pal.setColor(role,base)
            app.setPalette(pal)
        app._liquid_theme = theme
        controller = install_liquid_effects(app)
    if root is not None:
        try: root.setObjectName("SmartOrderWindow")
        except Exception: pass
        if app is not None:
            if changed or root.property("theme") != theme or not root.property("liquidGlass"):
                controller.apply(root,theme)
            from PyQt5.QtWidgets import QMainWindow
            if not isinstance(root, QMainWindow):
                from .workspace_ui import apply_page_scale
                apply_page_scale(root, appearance, zoom)

# RC3 final: popup/dialog theme parity and edit-mode visibility.
APPLE_QSS += r'''
QWidget[theme="dark"] QComboBox QAbstractItemView,
QDialog[theme="dark"] QComboBox QAbstractItemView {
    background-color: #2C2C2E;
    color: #F5F5F7;
    border: 1px solid rgba(255,255,255,35);
    selection-background-color: #0A84FF;
    selection-color: #FFFFFF;
    outline: 0;
}
QWidget[theme="light"] QComboBox QAbstractItemView,
QDialog[theme="light"] QComboBox QAbstractItemView {
    background-color: #FFFFFF;
    color: #1D1D1F;
    selection-background-color: #E5F1FB;
    selection-color: #007AFF;
}
QDialog[theme="dark"] QListWidget,
QDialog[theme="dark"] QTableWidget,
QDialog[theme="dark"] QTableView {
    background-color: #2C2C2E;
    alternate-background-color: #333336;
    color: #F5F5F7;
    gridline-color: rgba(255,255,255,22);
}
QDialog[theme="dark"] QListWidget::item:selected,
QDialog[theme="dark"] QTableWidget::item:selected,
QDialog[theme="dark"] QTableView::item:selected {
    background-color: #0A5A9C;
    color: #FFFFFF;
}
QDialog[theme="dark"] QHeaderView::section {
    background-color: #3A3A3C;
    color: #E5E5EA;
    border-color: rgba(255,255,255,24);
}
QDialog[theme="dark"] QCheckBox,
QDialog[theme="dark"] QRadioButton {
    color: #F5F5F7;
    background: transparent;
}
QDialog[theme="dark"] QDialogButtonBox QPushButton {
    background-color: #3A3A3C;
    color: #F5F5F7;
    border: 1px solid rgba(255,255,255,32);
}
QDialog[theme="dark"] QDialogButtonBox QPushButton:hover {
    border-color: #0A84FF;
    color: #0A84FF;
    background-color: #48484A;
}
QFrame#EditModeBanner {
    background-color: rgba(48,209,88,22);
    border: 1px solid rgba(48,209,88,110);
    border-radius: 10px;
}
QLabel#EditModeLabel {
    color: #248A3D;
    font-size: 13px;
    font-weight: 900;
    padding: 6px 10px;
}
QDialog[theme="dark"] QLabel#EditModeLabel {
    color: #30D158;
}
'''

APPLE_QSS += r'''
/* RC3: QMessageBox is a QDialog but contains a separate QWidget hierarchy. */
QMessageBox[theme="dark"],
QMessageBox[theme="dark"] QWidget {
    background-color: #2C2C2E;
    color: #F5F5F7;
}
QMessageBox[theme="dark"] QLabel {
    background: transparent;
    color: #F5F5F7;
}
QMessageBox[theme="dark"] QPushButton {
    background-color: #3A3A3C;
    color: #F5F5F7;
    border: 1px solid rgba(255,255,255,36);
}
QMessageBox[theme="dark"] QPushButton:hover {
    background-color: #48484A;
    color: #0A84FF;
    border-color: #0A84FF;
}
QMessageBox[theme="light"],
QMessageBox[theme="light"] QWidget {
    background-color: #FFFFFF;
    color: #1D1D1F;
}
QMessageBox[theme="light"] QLabel { color: #1D1D1F; background: transparent; }
'''

APPLE_QSS += r'''
/* RC3 selectable-list indicators: never render as opaque black squares. */
QListWidget::indicator {
    width: 18px;
    height: 18px;
    border: 1px solid #8E8E93;
    border-radius: 4px;
    background-color: #FFFFFF;
}
QListWidget::indicator:hover {
    border-color: #007AFF;
    background-color: #EEF6FF;
}
QListWidget::indicator:checked {
    border: 2px solid #007AFF;
    background-color: #007AFF;
}
QDialog[theme="dark"] QListWidget::indicator {
    border-color: #8E8E93;
    background-color: #3A3A3C;
}
QDialog[theme="dark"] QListWidget::indicator:hover {
    border-color: #0A84FF;
    background-color: #48484A;
}
QDialog[theme="dark"] QListWidget::indicator:checked {
    border: 2px solid #0A84FF;
    background-color: #0A84FF;
}
'''

# RC4 visual parity: user actions, admin DB status and fullscreen feedback.
APPLE_QSS += r'''
QPushButton#UserEditButton,
QPushButton#UserToggleButton {
    background-color: rgba(0,122,255,18);
    color: #007AFF;
    border: 1px solid #007AFF;
    border-radius: 10px;
    font-weight: 800;
    min-height: 34px;
    padding: 5px 14px;
}
QPushButton#UserEditButton:hover,
QPushButton#UserToggleButton:hover {
    background-color: #007AFF;
    color: #FFFFFF;
}
QPushButton#UserDeleteButton {
    background-color: rgba(255,59,48,14);
    color: #FF3B30;
    border: 1px solid #FF3B30;
    border-radius: 10px;
    font-weight: 800;
    min-height: 34px;
    padding: 5px 14px;
}
QPushButton#UserDeleteButton:hover {
    background-color: #FF3B30;
    color: #FFFFFF;
}
QWidget[theme="dark"] QPushButton#UserEditButton,
QWidget[theme="dark"] QPushButton#UserToggleButton,
QDialog[theme="dark"] QPushButton#UserEditButton,
QDialog[theme="dark"] QPushButton#UserToggleButton {
    background-color: rgba(10,132,255,22);
    color: #0A84FF;
    border-color: #0A84FF;
}
QWidget[theme="dark"] QPushButton#UserDeleteButton,
QDialog[theme="dark"] QPushButton#UserDeleteButton {
    background-color: rgba(255,69,58,20);
    color: #FF453A;
    border-color: #FF453A;
}
QPushButton#AdminSyncIconButton {
    min-width: 44px; max-width: 44px;
    min-height: 44px; max-height: 44px;
    padding: 0px;
    font-size: 29px;
    font-weight: 500;
    border-radius: 11px;
    background-color: rgba(255,255,255,235);
    border: 1px solid rgba(60,60,67,42);
    color: #1D1D1F;
}
QPushButton#AdminSyncIconButton:hover {
    color: #007AFF;
    border-color: #007AFF;
    background-color: #EEF6FF;
}
QWidget[theme="dark"] QPushButton#AdminSyncIconButton {
    background-color: #2C2C2E;
    color: #F5F5F7;
    border-color: rgba(255,255,255,38);
}
QWidget[theme="dark"] QPushButton#AdminSyncIconButton:hover {
    color: #0A84FF;
    border-color: #0A84FF;
    background-color: #3A3A3C;
}
QLabel#AdminLastSyncLabel {
    color: #3A3A3C;
    font-size: 12px;
    background: transparent;
}
QWidget[theme="dark"] QLabel#AdminLastSyncLabel {
    color: #D1D1D6;
}
QLabel#AdminDbPulseDot {
    color: #30D158;
    font-size: 15px;
    font-weight: 900;
    background: transparent;
}
QLabel#AdminDbStateText {
    font-size: 12px;
    font-weight: 800;
    background: transparent;
}
QPushButton#RestoreBackupButton {
    color: #007AFF;
    border-color: rgba(0,122,255,90);
    background-color: rgba(0,122,255,14);
}
QWidget[theme="dark"] QPushButton#RestoreBackupButton {
    color: #0A84FF;
    border-color: rgba(10,132,255,120);
    background-color: rgba(10,132,255,18);
}
QLabel#AuditHelpBadge {
    color: #007AFF;
    border: 1px solid rgba(0,122,255,110);
    border-radius: 11px;
    background-color: rgba(0,122,255,12);
    font-weight: 900;
}
QWidget[theme="dark"] QLabel#AuditHelpBadge {
    color: #0A84FF;
    border-color: rgba(10,132,255,140);
    background-color: rgba(10,132,255,20);
}
QFrame#FullscreenFeedback {
    background-color: rgba(20,20,22,178);
    border: 1px solid rgba(255,255,255,44);
    border-radius: 22px;
}
QLabel#FullscreenFeedbackText {
    color: #FFFFFF;
    font-size: 22px;
    font-weight: 900;
    background: transparent;
}
QLabel#FullscreenFeedbackHint {
    color: rgba(255,255,255,185);
    font-size: 12px;
    font-weight: 700;
    background: transparent;
}
'''


# RC5: cornerless tables and a blue outlined scroll-to-top button in both themes.
APPLE_QSS += r"""
QPushButton#ScrollTopButton {
    color:#007AFF;
    background-color:rgba(255,255,255,238);
    border:2px solid #007AFF;
    border-radius:27px;
    font-size:24px;
    font-weight:900;
}
QPushButton#ScrollTopButton:hover {
    background-color:rgba(0,122,255,22);
    border-color:#0A84FF;
    color:#0A84FF;
}
QWidget[theme="dark"] QPushButton#ScrollTopButton,
QDialog[theme="dark"] QPushButton#ScrollTopButton {
    color:#0A84FF;
    background-color:rgba(44,44,46,238);
    border:2px solid #0A84FF;
}
QWidget[theme="dark"] QPushButton#ScrollTopButton:hover,
QDialog[theme="dark"] QPushButton#ScrollTopButton:hover {
    background-color:rgba(10,132,255,28);
}
QTableCornerButton::section {
    background:transparent;
    border:none;
}
"""

# Stronger field/table boundaries keep dense reference and admin pages
# distinguishable in both themes, including when the OS/DPI softens 1px lines.
APPLE_QSS += r"""
QLineEdit,QTextEdit,QPlainTextEdit,QDateEdit,QComboBox,QSpinBox,QDoubleSpinBox {
    border:1px solid #AEB6C2;
}
QTableWidget,QTableView,QListWidget,QTreeWidget,QGroupBox {
    border:1px solid #AEB6C2;
}
QHeaderView::section {
    border-right:1px solid #C4CBD5;
    border-bottom:1px solid #AEB6C2;
}
QComboBox QAbstractItemView,QAbstractItemView {
    border:1px solid #9BA6B5;
    background:#FFFFFF;
    color:#1D1D1F;
}
QWidget[theme="dark"] QLineEdit,QWidget[theme="dark"] QTextEdit,
QWidget[theme="dark"] QPlainTextEdit,QWidget[theme="dark"] QDateEdit,
QWidget[theme="dark"] QComboBox,QWidget[theme="dark"] QSpinBox,
QWidget[theme="dark"] QDoubleSpinBox {
    border-color:#68758A;
}
QWidget[theme="dark"] QTableWidget,QWidget[theme="dark"] QTableView,
QWidget[theme="dark"] QListWidget,QWidget[theme="dark"] QTreeWidget,
QWidget[theme="dark"] QGroupBox {
    border-color:#68758A;
}
QWidget[theme="dark"] QHeaderView::section {
    border-right-color:#59667A;
    border-bottom-color:#68758A;
}
QWidget[theme="dark"] QComboBox QAbstractItemView,
QWidget[theme="dark"] QAbstractItemView,
QDialog[theme="dark"] QComboBox QAbstractItemView,
QDialog[theme="dark"] QAbstractItemView {
    border-color:#68758A;
    background:#2C2C2E;
    color:#F5F5F7;
}
"""
