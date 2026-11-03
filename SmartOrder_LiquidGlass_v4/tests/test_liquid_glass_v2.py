"""Layout, glass popovers and restored motion on the actual Chromium 83 page."""
import pytest
from PyQt5.QtCore import QDate, QEvent

from test_liquid_glass import app, system, glass, javascript, drain


@pytest.mark.parametrize("width,zoom", [(1452,100),(1280,100),(1452,200),(680,200)])
def test_window_fills_viewport_and_all_filters_stay_on_one_line(glass, app, width, zoom):
    window, _, _ = glass
    window.resize(width, 789)
    window._glass_command("zoom", {"value": zoom})
    drain(app, lambda: not window._rc18_zoom_timer.isActive())
    window._publish_glass_state(force=True)
    geometry = javascript(app, window, '''(() => {
      const shell=document.getElementById("app-shell").getBoundingClientRect();
      return {width:innerWidth,height:innerHeight,x:shell.x,y:shell.y,w:shell.width,h:shell.height,
       filterY:Array.from(document.querySelectorAll(".filter-cell")).map(e=>e.getBoundingClientRect().y),
       status:document.getElementById("connection-state"),outsideImage:getComputedStyle(document.body).backgroundImage};
    })()''')
    assert geometry["x"] == geometry["y"] == 0
    assert abs(geometry["w"] - geometry["width"]) < 1
    assert abs(geometry["h"] - geometry["height"]) < 1
    assert max(geometry["filterY"]) - min(geometry["filterY"]) < 1
    assert geometry["status"] is None and geometry["outsideImage"] == "none"


def test_label_and_theme_spacing_works_without_flex_gap(glass, app):
    window, _, _ = glass
    result = javascript(app, window, '''(() => {
      const a=document.getElementById("account").getBoundingClientRect(),t=document.querySelector(".theme-control").getBoundingClientRect();
      return {theme:a.left-t.right,labels:Array.from(document.querySelectorAll(".filter-cell")).map(e=>{
        const label=e.querySelector(".filter-label").getBoundingClientRect(),field=e.querySelector("button").getBoundingClientRect();return field.left-label.right;
      })};
    })()''')
    assert window.titlebar.badge.x() - (window.theme.x() + window.theme.width()) >= 16
    assert all(gap >= 9 for gap in result["labels"])


def test_custom_glass_list_keyboard_selection_and_escape(glass, app):
    window, _, _ = glass
    javascript(app, window, 'document.getElementById("shift-trigger").click()')
    popup = javascript(app, window, '''(() => {
      const p=document.getElementById("glass-popup"),s=getComputedStyle(p);
      return {visible:!p.hidden,blur:s.backdropFilter,background:s.backgroundColor,options:document.querySelectorAll("#glass-listbox [role=option]").length};
    })()''')
    assert popup["visible"] and "blur" in popup["blur"] and popup["options"] == 3
    assert popup["background"] == "rgba(0, 0, 0, 0)"
    javascript(app, window, 'document.dispatchEvent(new KeyboardEvent("keydown",{key:"ArrowDown",bubbles:true}));document.dispatchEvent(new KeyboardEvent("keydown",{key:"Enter",bubbles:true}));')
    drain(app, lambda: window.order_filter_shift.currentText() == "Ночная")
    javascript(app, window, 'document.getElementById("master-trigger").click();document.dispatchEvent(new KeyboardEvent("keydown",{key:"Escape",bubbles:true}));')
    assert not window.isFullScreen()
    assert javascript(app, window, 'document.getElementById("glass-popup").hidden') is True


def test_glass_workshop_menu_uses_real_authorized_workshops(glass, app):
    window, _, _ = glass
    javascript(app, window, 'document.getElementById("account").click()')
    assert javascript(app, window, 'document.querySelectorAll("#glass-listbox [role=option]").length') == 6
    assert javascript(app, window, 'document.querySelector("#glass-listbox [aria-selected=true]").textContent') == "Упаковка"
    assert javascript(app, window, 'document.getElementById("account").getAttribute("aria-expanded")') == "true"


def test_glass_calendar_commits_real_date_range_and_rejects_invalid_input(glass, app):
    window, _, _ = glass
    window.order_filter_date.setDate(QDate(2026,10,29))
    window._publish_glass_state(force=True)
    javascript(app, window, 'document.getElementById("date").click()')
    assert javascript(app, window, '!document.getElementById("glass-calendar").hidden') is True
    javascript(app, window, 'document.querySelector("[data-cal-date=\\\"2026-10-22\\\"]").click();document.querySelector("[data-cal-date=\\\"2026-10-15\\\"]").click();document.querySelector("[data-cal=apply]").click();')
    drain(app, lambda: window.order_filter_date.startDate() == QDate(2026,10,15))
    assert window.order_filter_date.endDate() == QDate(2026,10,22)
    window._glass_command("date_range", {"start":"2026-02-30","end":"2026-10-29"})
    assert window.order_filter_date.startDate() == QDate(2026,10,15)


def test_cursor_gradient_moves_toward_pointer_and_press_is_animated(glass, app):
    window, _, _ = glass
    javascript(app, window, '''(() => {
      const b=document.getElementById("create"),r=b.getBoundingClientRect();
      b.dispatchEvent(new PointerEvent("pointerover",{bubbles:true,clientX:r.left+8,clientY:r.top+8}));
      b.dispatchEvent(new PointerEvent("pointermove",{bubbles:true,clientX:r.left+8,clientY:r.top+8}));
    })()''')
    drain(app, lambda: javascript(app, window, 'document.getElementById("create").classList.contains("is-hovered")'))
    drain(app, lambda: javascript(app, window, 'parseFloat(document.getElementById("create").style.getPropertyValue("--hover-x"))') < 20)
    javascript(app, window, '''(() => {const b=document.getElementById("create"),r=b.getBoundingClientRect();b.dispatchEvent(new PointerEvent("pointerdown",{bubbles:true,button:0,clientX:r.left+8,clientY:r.top+8}));})()''')
    assert javascript(app, window, 'document.getElementById("create").classList.contains("is-pressed")') is True
    assert javascript(app, window, 'document.querySelector("#create .press-ripple") !== null') is True
    javascript(app, window, 'document.dispatchEvent(new PointerEvent("pointerup",{bubbles:true}));')
    assert javascript(app, window, 'document.getElementById("create").classList.contains("is-pressed")') is False


def test_escape_preserves_feedback_timing_with_transparent_background(glass, app):
    window, _, _ = glass
    javascript(app, window, 'document.dispatchEvent(new KeyboardEvent("keydown",{key:"Escape",bubbles:true}));')
    drain(app, lambda: window.isFullScreen() and getattr(window,"_fullscreen_feedback",None) is not None)
    feedback = window._fullscreen_feedback
    assert "background:transparent" in feedback.styleSheet()
    from smartorder.heavy_ui import _RC4FullscreenIcon
    assert feedback.findChild(_RC4FullscreenIcon).property("iconColor") == "#007AFF"
    assert feedback.fade_in.duration() == 300 and feedback.fade_out.duration() == 620
    javascript(app, window, 'document.dispatchEvent(new KeyboardEvent("keydown",{key:"Escape",repeat:true,bubbles:true}));')
    assert window.isFullScreen()


def test_long_master_list_search_commits_authoritative_employee_id(glass, app):
    window, _, admin = glass
    identifiers = [window.db.add_employee(admin, "Мастер списка " + str(i), True) for i in range(12)]
    window._refresh_reference_filters()
    window._publish_glass_state(force=True)
    javascript(app, window, 'document.getElementById("master-trigger").click();const search=document.getElementById("popup-search");search.value="списка 8";search.dispatchEvent(new Event("input",{bubbles:true}));')
    assert javascript(app, window, 'document.getElementById("popup-search").hidden') is False
    assert javascript(app, window, 'document.querySelectorAll("#glass-listbox [role=option]").length') == 1
    javascript(app, window, 'document.querySelector("#glass-listbox [role=option]").click()')
    drain(app, lambda: window.order_filter_master.currentData() == identifiers[8])


def test_calendar_and_list_stay_inside_small_viewport_at_200_percent(glass, app):
    window, _, _ = glass
    window.resize(680,620)
    window._glass_command("zoom", {"value":200})
    drain(app, lambda: not window._rc18_zoom_timer.isActive())
    window._publish_glass_state(force=True)
    for trigger, popup in [("shift-trigger","glass-popup"),("date","glass-calendar")]:
        javascript(app, window, 'document.getElementById("' + trigger + '").scrollIntoView({block:"nearest",inline:"nearest"});document.getElementById("' + trigger + '").click()')
        box = javascript(app, window, '(() => {const b=document.getElementById("' + popup + '").getBoundingClientRect();return {left:b.left,right:b.right,top:b.top,bottom:b.bottom,w:innerWidth,h:innerHeight};})()')
        assert box["left"] >= 0 and box["right"] <= box["w"]
        assert box["top"] >= 0 and box["bottom"] <= box["h"]
        javascript(app, window, 'document.dispatchEvent(new KeyboardEvent("keydown",{key:"Escape",bubbles:true}));')
