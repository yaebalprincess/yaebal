"""Shared Liquid Glass tokens for Qt surfaces.

The orders page uses the same colours in glass/orders.css.  Widget geometry,
models, delegates and business signals remain owned by the existing Qt UI.
"""
from __future__ import annotations


def colors(dark=False):
    return {
        "ink": "#e7f2ff" if dark else "#102b50",
        "muted": "#b1c6df" if dark else "#425f80",
        "blue": "#63b4ff" if dark else "#007aff",
        "base": "#15273e" if dark else "#dcebf7",
        "glass": "rgba(24,45,69,174)" if dark else "rgba(222,240,255,145)",
        "field": "rgba(26,48,74,218)" if dark else "rgba(251,254,255,202)",
        "table": "rgba(17,35,56,222)" if dark else "rgba(241,249,255,224)",
        "header": "rgba(40,65,94,230)" if dark else "rgba(223,237,253,220)",
        "edge": "rgba(167,205,241,85)" if dark else "rgba(255,255,255,237)",
        "line": "rgba(120,166,213,95)" if dark else "rgba(102,148,196,79)",
        "hover": "rgba(66,131,193,90)" if dark else "rgba(212,235,255,180)",
        "selected": "rgba(44,132,216,125)" if dark else "rgba(131,196,255,150)",
        "disabled": "#7892ae" if dark else "#7f9bbb",
    }


def liquid_qss(zoom=100, appearance=None):
    scale = max(.5, min(2, int(zoom) / 100))
    size = max(6, round(12 * scale))
    height = max(28, round(30 * min(scale, 1.5)))
    qss = f"""
QWidget {{ font-family: 'Segoe UI', Arial, sans-serif; font-size:{size}px; }}
QMainWindow, QDialog, QWidget#AppShell, QStackedWidget, QTabWidget::pane {{ background:transparent; }}
QLabel {{ background:transparent; }}
QLabel#TitleLabel {{ font-size:{round(24 * scale)}px; font-weight:700; }}
QLabel#SectionTitle {{ font-size:{round(17 * scale)}px; font-weight:700; }}
QPushButton {{ min-height:{height}px; padding:6px 12px; border-radius:9px; font-weight:600; }}
QPushButton:focus, QToolButton:focus {{ border:2px solid #0785ff; }}
QToolButton {{ border-radius:6px; padding:4px; }}
QLineEdit, QComboBox, QDateEdit, QSpinBox, QDoubleSpinBox {{ min-height:{height}px; padding:4px 9px; border-radius:9px; }}
QTextEdit, QPlainTextEdit, QTextBrowser {{ padding:8px; border-radius:10px; }}
QComboBox::drop-down, QDateEdit::drop-down {{ width:28px; border:0; }}
QGroupBox {{ margin-top:22px; padding:18px 12px 12px; border-radius:14px; font-weight:600; }}
QGroupBox::title {{ subcontrol-origin:margin; subcontrol-position:top left; left:12px; top:4px; padding:0 7px; }}
QFrame#GlassPanel, QWidget#GlassPanel, QFrame#LoginCard, QFrame#LiquidCard {{ border-radius:15px; }}
QScrollArea {{ border:0; background:transparent; }}
QScrollArea>QWidget>QWidget, QScrollArea>QWidget {{ background:transparent; }}
QTabWidget::pane {{ border:0; top:0; }}
QTabBar {{ background:transparent; }}
QTabBar::tab {{ min-height:{height}px; padding:6px 18px; border-top-left-radius:8px; border-top-right-radius:8px; margin-right:0; font-weight:600; }}
QTableView, QTableWidget, QListView, QTreeView {{ border-radius:12px; outline:0; }}
QTableView::item, QTableWidget::item {{ padding:5px 8px; border:0; }}
QListView::item, QTreeView::item {{ padding:7px 9px; border-radius:6px; }}
QHeaderView::section {{ padding:8px; border:0; border-right:1px solid rgba(102,148,196,60); }}
QCheckBox, QRadioButton {{ spacing:8px; background:transparent; }}
QCheckBox::indicator, QRadioButton::indicator {{ width:17px; height:17px; }}
QCheckBox::indicator {{ border-radius:5px; }}
QRadioButton::indicator {{ border-radius:9px; }}
QSlider::groove:horizontal {{ height:4px; border-radius:2px; background:rgba(112,151,193,77); }}
QSlider::sub-page:horizontal {{ background:#0781ff; border-radius:2px; }}
QSlider::handle:horizontal {{ background:#fbfeff; border:1px solid rgba(170,202,233,160); border-radius:9px; width:18px; margin:-7px 0; }}
QScrollBar:vertical {{ width:10px; background:transparent; margin:2px; }}
QScrollBar:horizontal {{ height:10px; background:transparent; margin:2px; }}
QScrollBar::handle {{ background:rgba(95,140,187,95); border-radius:4px; min-height:24px; min-width:24px; }}
QScrollBar::handle:hover {{ background:rgba(50,130,210,150); }}
QScrollBar::add-line, QScrollBar::sub-line {{ width:0; height:0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background:transparent; }}
QMenu {{ padding:7px; border-radius:10px; }}
QMenu::item {{ padding:9px 24px; border-radius:6px; }}
QWidget[glassOverlay="true"] {{ background:transparent; }}
QFrame#GlassOverlayChrome {{ background:transparent; border:0; }}
QToolButton#OverlayClose {{ background:rgba(130,180,220,25); border:0; border-radius:9px; font-size:23px; padding:0; }}
QToolButton#OverlayClose:hover {{ background:rgba(235,80,110,160); color:white; }}
QProgressBar {{ border:0; border-radius:4px; background:rgba(112,151,193,55); text-align:center; }}
QProgressBar::chunk {{ border-radius:4px; background:#0785ff; }}
QDialogButtonBox QPushButton {{ min-width:96px; }}
QPushButton#ScrollTopButton {{ min-width:44px; max-width:44px; min-height:44px; max-height:44px; padding:0; }}
QLabel#DbStateOk, QLabel#EditModeLabel {{ color:#1aa77a; font-weight:700; }}
QLabel#DbStateSlow {{ color:#d18725; font-weight:700; }}
QLabel#DbStateBad {{ color:#e44f67; font-weight:700; }}
"""
    for theme in ("light", "dark"):
        c = colors(theme == "dark")
        # Every themed widget carries its own property. This also handles
        # parentless Qt.Popup windows and delegates created after a tab loads.
        def rule(selectors, body):
            return ",".join(f'{s}[theme="{theme}"]' for s in selectors.split(",")) + "{" + body + "}\n"
        qss += rule("QWidget", f'color:{c["ink"]};')
        qss += rule("QLabel", f'color:{c["ink"]};background:transparent;')
        qss += rule("QPushButton,QToolButton", f'color:{c["blue"]};border:1px solid {c["line"]};background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 {c["field"]},stop:1 {c["glass"]});')
        qss += f'QPushButton[theme="{theme}"]:hover,QToolButton[theme="{theme}"]:hover{{border-color:#65aff5;background:{c["hover"]};}}\n'
        qss += f'QPushButton[theme="{theme}"]:pressed,QToolButton[theme="{theme}"]:pressed{{background:{c["selected"]};}}\n'
        qss += f'QPushButton[theme="{theme}"]:disabled{{color:{c["disabled"]};border-color:{c["line"]};}}\n'
        qss += f'QPushButton#PrimaryButton[theme="{theme}"]{{color:white;border:1px solid #168aff;background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #279bff,stop:.53 #0785ff,stop:1 #0071f1);}}\n'
        qss += f'QPushButton#PrimaryButton[theme="{theme}"]:hover{{background:#178dff;}}\n'
        qss += f'QPushButton#DangerButton[theme="{theme}"],QPushButton#UserDeleteButton[theme="{theme}"]{{color:{"#ff93ad" if theme == "dark" else "#ed355b"};border-color:rgba(240,120,160,135);background:rgba(235,118,160,35);}}\n'
        qss += f'QPushButton#GhostButton[theme="{theme}"]{{border-color:transparent;background:transparent;}}\n'
        qss += rule("QLineEdit,QComboBox,QDateEdit,QSpinBox,QDoubleSpinBox,QTextEdit,QPlainTextEdit,QTextBrowser", f'color:{c["ink"]};background:{c["field"]};border:1px solid {c["line"]};selection-background-color:#168aff;selection-color:white;')
        qss += f'QLineEdit[theme="{theme}"]:focus,QComboBox[theme="{theme}"]:focus,QTextEdit[theme="{theme}"]:focus,QPlainTextEdit[theme="{theme}"]:focus{{border:1px solid #0785ff;}}\n'
        qss += f'QLineEdit[theme="{theme}"]:disabled,QComboBox[theme="{theme}"]:disabled{{color:{c["disabled"]};}}\n'
        qss += rule("QGroupBox,QFrame#GlassPanel,QWidget#GlassPanel,QFrame#LoginCard,QFrame#LiquidCard", f'color:{c["ink"]};background:{c["glass"]};border:1px solid {c["edge"]};')
        qss += f'QGroupBox[theme="{theme}"]::title{{color:{c["blue"]};background:transparent;}}\n'
        qss += f'QTabBar[theme="{theme}"]::tab{{color:{c["muted"]};border:1px solid {c["line"]};border-bottom:0;background:{c["glass"]};}}\n'
        qss += f'QTabBar[theme="{theme}"]::tab:selected{{color:{c["blue"]};background:{c["field"]};}}\n'
        qss += f'QTabBar[theme="{theme}"]::tab:hover{{background:{c["hover"]};}}\n'
        qss += rule("QTableView,QTableWidget,QListView,QTreeView", f'color:{c["ink"]};background:{c["table"]};alternate-background-color:{c["field"]};border:1px solid {c["edge"]};gridline-color:{c["line"]};selection-background-color:{c["selected"]};selection-color:{c["ink"]};')
        qss += f'QAbstractItemView[theme="{theme}"]::item:selected{{background:{c["selected"]};color:{c["ink"]};}}\n'
        qss += f'QAbstractItemView[theme="{theme}"]::item:hover{{background:{c["hover"]};}}\n'
        qss += f'QHeaderView[theme="{theme}"]::section{{background:{c["header"]};color:{c["muted"]};border-bottom:1px solid {c["line"]};}}\n'
        qss += rule("QLabel#MutedLabel,QLabel#SubtitleLabel,QLabel#SessionLabel", f'color:{c["muted"]};')
        qss += f'QCheckBox[theme="{theme}"]::indicator,QRadioButton[theme="{theme}"]::indicator{{border:1px solid {c["line"]};background:{c["field"]};}}\n'
        qss += f'QCheckBox[theme="{theme}"]::indicator:checked{{background:#0785ff;border-color:#0785ff;image:url(:/qt-project.org/styles/commonstyle/images/standardbutton-apply-16.png);}}\n'
        qss += f'QRadioButton[theme="{theme}"]::indicator:checked{{border:5px solid #0785ff;background:{c["field"]};}}\n'
        qss += rule("QMenu", f'background:{c["table"]};color:{c["ink"]};border:1px solid {c["edge"]};')
        qss += f'QMenu[theme="{theme}"]::item:selected{{background:{c["selected"]};}}\n'
        qss += f'QCalendarWidget[theme="{theme}"] QWidget{{background:{c["table"]};color:{c["ink"]};}}\n'
    from .appearance import typography_qss
    qss += '''
QMenu[glassOverlay="true"]{background:rgba(242,250,255,30);}
QMenu[glassOverlay="true"][theme="dark"]{background:rgba(18,35,55,30);}
QWidget[glassOverlay="true"] QScrollArea{background:transparent;}
QWidget[glassOverlay="true"] QTextBrowser{background:rgba(246,252,255,80);}
QWidget[glassOverlay="true"][theme="dark"] QTextBrowser{background:rgba(20,39,62,85);}
'''
    return qss + typography_qss(appearance, zoom)
