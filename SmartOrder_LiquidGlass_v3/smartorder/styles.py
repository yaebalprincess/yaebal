LIGHT_QSS = """
QMainWindow, QDialog, QWidget { background:#f5f5f7; color:#1d1d1f; }
QTabWidget::pane { border:0; }
QTabBar::tab { padding:9px 16px; margin-right:3px; font-weight:600; color:#6e6e73; }
QTabBar::tab:selected { color:#007aff; border-bottom:2px solid #007aff; }
QPushButton { min-height:32px; padding:5px 13px; border:1px solid #d2d2d7; border-radius:8px; background:#ffffff; }
QPushButton:hover { border-color:#007aff; color:#007aff; }
QPushButton#primary { background:#007aff; color:white; border-color:#007aff; font-weight:600; }
QPushButton#danger { color:#c62828; border-color:#ef9a9a; }
QLineEdit, QComboBox, QDateEdit, QSpinBox, QDoubleSpinBox, QTextEdit { min-height:31px; padding:3px 8px; border:1px solid #d2d2d7; border-radius:7px; background:white; }
QLineEdit:focus, QComboBox:focus, QDateEdit:focus, QTextEdit:focus { border:1px solid #007aff; }
QTableWidget, QTableView { background:white; alternate-background-color:#f8f8fa; border:1px solid #e1e1e6; gridline-color:#ececf0; selection-background-color:#dbeeff; selection-color:#1d1d1f; }
QHeaderView::section { padding:6px; background:#ededf2; border:0; border-bottom:1px solid #d2d2d7; font-weight:600; }
QGroupBox { border:1px solid #dedee3; border-radius:9px; margin-top:10px; padding:12px; font-weight:600; }
QGroupBox::title { subcontrol-origin:margin; left:10px; padding:0 5px; }
QLabel#muted { color:#6e6e73; }
QLabel#db_ok { color:#188038; font-weight:600; }
QLabel#db_bad { color:#c5221f; font-weight:600; }
QLabel#db_slow { color:#b26a00; font-weight:600; }
QFrame#aboutGlass { background:rgba(255,255,255,18); border:1px solid rgba(255,255,255,90); border-radius:18px; }
QFrame#aboutGlass QLabel { background:transparent; }
"""

DARK_QSS = """
QMainWindow, QDialog, QWidget { background:#1c1c1e; color:#f5f5f7; }
QTabWidget::pane { border:0; }
QTabBar::tab { padding:9px 16px; margin-right:3px; font-weight:600; color:#a1a1aa; }
QTabBar::tab:selected { color:#0a84ff; border-bottom:2px solid #0a84ff; }
QPushButton { min-height:32px; padding:5px 13px; border:1px solid #4a4a4f; border-radius:8px; background:#2c2c2e; color:#f5f5f7; }
QPushButton:hover { border-color:#0a84ff; color:#0a84ff; }
QPushButton#primary { background:#0a84ff; color:white; border-color:#0a84ff; font-weight:600; }
QPushButton#danger { color:#ff6961; border-color:#8b3f3c; }
QLineEdit, QComboBox, QDateEdit, QSpinBox, QDoubleSpinBox, QTextEdit { min-height:31px; padding:3px 8px; border:1px solid #4a4a4f; border-radius:7px; background:#2c2c2e; color:#f5f5f7; }
QLineEdit:focus, QComboBox:focus, QDateEdit:focus, QTextEdit:focus { border:1px solid #0a84ff; }
QComboBox QAbstractItemView { background:#2c2c2e; color:#f5f5f7; selection-background-color:#0a84ff; }
QTableWidget, QTableView { background:#242426; alternate-background-color:#2c2c2e; border:1px solid #45454a; gridline-color:#35353a; selection-background-color:#0a4c80; selection-color:white; }
QHeaderView::section { padding:6px; background:#323235; border:0; border-bottom:1px solid #4a4a4f; color:#f5f5f7; font-weight:600; }
QGroupBox { border:1px solid #45454a; border-radius:9px; margin-top:10px; padding:12px; font-weight:600; }
QGroupBox::title { subcontrol-origin:margin; left:10px; padding:0 5px; }
QLabel#muted { color:#a1a1aa; }
QLabel#db_ok { color:#30d158; font-weight:600; }
QLabel#db_bad { color:#ff453a; font-weight:600; }
QLabel#db_slow { color:#ff9f0a; font-weight:600; }
QFrame#aboutGlass { background:rgba(0,0,0,0); border:1px solid rgba(255,255,255,65); border-radius:18px; }
QFrame#aboutGlass QLabel { background:transparent; }
"""
