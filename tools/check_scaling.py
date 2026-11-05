"""Headless scaling matrix for SmartOrder.

The helper exercises the real enterprise window at 15 desktop viewport sizes
and every value accepted by the zoom slider (105 viewport/zoom states). It reports controls that
overlap, leave the window, or are narrower than their own minimum size hint.
It is intentionally a standalone diagnostic so it can be run on a build
machine without adding another fixture to the functional test suite::

    QT_QPA_PLATFORM=offscreen python tools/check_scaling.py --strict

PyQt5 and pytest are supplied by ``requirements-dev.txt``.  A temporary
database is used; no production/network path is touched.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from PyQt5.QtCore import QPoint, QRect, QTimer
from PyQt5.QtWidgets import (
    QApplication,
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDateEdit,
    QHeaderView,
    QLineEdit,
    QListView,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSlider,
    QTabBar,
    QTableView,
    QWidget,
)


# The matrix follows the reference brief (15 common Windows resolutions),
# with the two additional 50/75% values accepted by the current slider.
VIEWPORTS = (
    (1920, 1080), (1680, 1050), (1600, 900), (1440, 900), (1400, 1050),
    (1366, 768), (1360, 768), (1280, 1024), (1280, 960), (1280, 800),
    (1280, 768), (1280, 720), (1280, 600), (1152, 864), (1024, 768),
)
ZOOMS = (50, 75, 100, 125, 150, 175, 200)
INTERACTIVE = (QPushButton, QComboBox, QDateEdit, QLineEdit, QCheckBox, QRadioButton, QSlider, QTabBar)
# Item-view descendants (table cells, delegates and combo popups) are managed
# by their view and can legitimately share geometry.  A QScrollArea is *not*
# skipped: the responsive orders page lives inside one and its controls still
# need to be checked against one another.
SKIP_PARENTS = (QAbstractItemView, QHeaderView)


def _ancestor(widget: QWidget, klasses: tuple[type, ...]) -> bool:
    parent = widget.parentWidget()
    while parent is not None:
        if isinstance(parent, klasses):
            return True
        parent = parent.parentWidget()
    return False


def _controls(window: QWidget) -> list[QWidget]:
    """Return visible controls that participate in normal page layout.

    Item views and their children are excluded because their own delegates and
    header sections intentionally share geometry and are governed by scrolling.
    """
    result: list[QWidget] = []
    for widget in window.findChildren(QWidget):
        if not widget.isVisible() or not isinstance(widget, INTERACTIVE):
            continue
        if _ancestor(widget, SKIP_PARENTS):
            continue
        if widget.width() <= 0 or widget.height() <= 0:
            continue
        result.append(widget)
    return result


def _window_rect(window: QWidget) -> QRect:
    return QRect(QPoint(0, 0), window.size())


def _mapped_rect(window: QWidget, widget: QWidget) -> QRect:
    return QRect(window.mapFromGlobal(widget.mapToGlobal(QPoint(0, 0))), widget.size())


def inspect(window: QWidget, viewport: tuple[int, int], zoom: int) -> list[dict[str, object]]:
    """Collect geometry violations for one viewport/zoom state."""
    issues: list[dict[str, object]] = []
    requested_width, requested_height = viewport
    if window.width() > requested_width + 4 or window.height() > requested_height + 4:
        issues.append({
            "kind": "viewport-clamped",
            "requested": [requested_width, requested_height],
            "actual": [window.width(), window.height()],
        })
    controls = _controls(window)
    rects = {id(w): _mapped_rect(window, w) for w in controls}
    frame = _window_rect(window)

    for widget in controls:
        rect = rects[id(widget)]
        # A control clipped by the page is a scaling regression.  Ignore the
        # native titlebar area (our custom titlebar is part of the client rect).
        if (not frame.contains(rect.topLeft()) or not frame.contains(rect.bottomRight())) and not _ancestor(widget, (QScrollArea,)):
            issues.append({
                "kind": "outside-window",
                "widget": widget.objectName() or widget.__class__.__name__,
                "geometry": [rect.x(), rect.y(), rect.width(), rect.height()],
            })
        if rect.width() < widget.minimumSizeHint().width() - 2:
            issues.append({
                "kind": "below-minimum-size-hint",
                "widget": widget.objectName() or widget.__class__.__name__,
                "width": rect.width(),
                "minimum_hint": widget.minimumSizeHint().width(),
            })

    # Compare only siblings.  Nested widgets commonly overlap their parent,
    # but two visible controls managed by one layout must never overlap.
    for index, first in enumerate(controls):
        for second in controls[index + 1 :]:
            if first.parentWidget() is not second.parentWidget():
                continue
            overlap = rects[id(first)].intersected(rects[id(second)])
            if overlap.width() * overlap.height() <= 4:
                continue
            issues.append({
                "kind": "sibling-overlap",
                "first": first.objectName() or first.__class__.__name__,
                "second": second.objectName() or second.__class__.__name__,
                "area": overlap.width() * overlap.height(),
            })
    return issues


def _build_window(tmp: Path):
    from smartorder.db import Database
    from smartorder.enterprise_ui import MainWindow
    from smartorder.workshops import WorkshopManager

    shared = tmp / "shared"
    shared.mkdir(parents=True, exist_ok=True)
    db = Database(shared / "work_orders.db")
    db.create_first_admin("scaling-admin", "password123")
    manager = WorkshopManager(db, shared)
    user = manager.auth.authenticate("scaling-admin", "password123")
    window = MainWindow(db, user, manager)
    return window


def run(strict: bool = False) -> int:
    app = QApplication.instance() or QApplication([])
    # Prevent diagnostics from blocking on QMessageBox for an empty database.
    from PyQt5.QtWidgets import QMessageBox
    QMessageBox.warning = staticmethod(lambda *args, **kwargs: QMessageBox.Ok)
    QMessageBox.critical = staticmethod(lambda *args, **kwargs: QMessageBox.Ok)

    result: dict[str, object] = {"viewports": VIEWPORTS, "zooms": ZOOMS, "states": [], "issues": []}
    with tempfile.TemporaryDirectory(prefix="smartorder-scaling-") as raw:
        tmp = Path(raw)
        os.environ["SMARTORDER_NETWORK_ROOT"] = str(tmp / "network")
        os.environ["LOCALAPPDATA"] = str(tmp / "local")
        os.environ["XDG_CACHE_HOME"] = str(tmp / "cache")
        window = _build_window(tmp)
        window.show()
        for width, height in VIEWPORTS:
            for zoom in ZOOMS:
                window.showNormal()
                window.resize(width, height)
                if hasattr(window, "zoom"):
                    window.zoom.setValue(zoom)
                # Zoom is debounced in RC18; allow one event-loop turn and the
                # 85 ms commit timer before measuring the final geometry.
                deadline = time.monotonic() + 0.18
                while time.monotonic() < deadline:
                    app.processEvents()
                    time.sleep(0.005)
                state_issues = inspect(window, (width, height), zoom)
                state = {"viewport": [width, height], "zoom": zoom, "issue_count": len(state_issues)}
                result["states"].append(state)
                for issue in state_issues:
                    result["issues"].append({**state, **issue})
        window._rc4_exit_confirmed = True
        window.close()
        app.processEvents()

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if strict and result["issues"] else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--strict", action="store_true", help="return non-zero when any geometry issue is found")
    args = parser.parse_args()
    return run(strict=args.strict)


if __name__ == "__main__":
    raise SystemExit(main())
