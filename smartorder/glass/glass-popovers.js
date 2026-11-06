"use strict";
(() => {
  const $ = id => document.getElementById(id);
  let state = null, dispatch = null, opened = null, anchor = null;
  let options = [], shown = [], active = -1, listSignature = "", typeAhead = "", typeTimer;
  let calendar = null, positionFrame = 0;
  function replace(node, fragment) { node.textContent = ""; node.appendChild(fragment); }
  function icon(name) {
    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    const use = document.createElementNS(svg.namespaceURI, "use");
    use.setAttribute("href", "#i-" + name); svg.appendChild(use); return svg;
  }
  function send(action, payload) { if (dispatch) dispatch(action, payload); }
  function close(restoreFocus = false) {
    const previous = anchor;
    if (previous) { previous.setAttribute("aria-expanded", "false"); previous.removeAttribute("aria-activedescendant"); }
    $("glass-popup").hidden = true; $("glass-calendar").hidden = true;
    opened = null; anchor = null; calendar = null;
    if (restoreFocus && previous && document.contains(previous)) previous.focus({preventScroll: true});
  }
  function currentValue() { return opened === "workshop" ? state.workshopKey : state.filters[opened].value; }
  function choose(index) {
    const option = shown[index]; if (!option || option.enabled === false) return;
    const kind = opened, value = option.value;
    close(true);
    if (kind === "workshop") send("workshop", {key: value});
    else {
      const select = $(kind);
      select.value = value === null ? "" : String(value);
      select.dispatchEvent(new Event("change", {bubbles: true}));
    }
  }
  function setActive(index, scroll = true) {
    if (index < 0 || !shown[index] || shown[index].enabled === false) return;
    const previous = $("glass-option-" + active); if (previous) previous.classList.remove("is-active");
    active = index;
    const item = $("glass-option-" + index);
    if (item) {
      item.classList.add("is-active"); anchor.setAttribute("aria-activedescendant", item.id);
      if (scroll) item.scrollIntoView({block: "nearest"});
    }
  }
  function renderOptions() {
    const query = $("popup-search").value.trim().toLocaleLowerCase("ru").replace(/ё/g, "е");
    shown = options.filter(o => !query || o.label.toLocaleLowerCase("ru").replace(/ё/g, "е").includes(query));
    const fragment = document.createDocumentFragment();
    shown.forEach((option, index) => {
      const button = document.createElement("button");
      button.className = "glass-option"; button.id = "glass-option-" + index;
      button.dataset.optionIndex = index; button.type = "button"; button.tabIndex = -1;
      button.setAttribute("role", "option");
      button.setAttribute("aria-selected", option.value === currentValue() ? "true" : "false");
      button.disabled = option.enabled === false;
      const label = document.createElement("span"); label.className = "option-label"; label.textContent = option.label;
      button.appendChild(label);
      if (option.value === currentValue()) button.appendChild(icon("check"));
      fragment.appendChild(button);
    });
    replace($("glass-listbox"), fragment);
    $("popup-empty").hidden = shown.length > 0;
    active = -1;
    let first = shown.findIndex(o => o.value === currentValue() && o.enabled !== false);
    if (first < 0) first = shown.findIndex(o => o.enabled !== false);
    setActive(first, false); schedulePosition();
  }
  function showList(kind, button) {
    if (!state || button.disabled) return;
    if (opened === kind) { close(true); return; }
    close(); opened = kind; anchor = button;
    options = (kind === "workshop" ? state.workshops : state.filters[kind].options).map(o => Object.assign({}, o));
    listSignature = JSON.stringify(options);
    $("popup-heading").hidden = kind !== "workshop";
    $("popup-heading").textContent = kind === "workshop" ? state.username + " · " + state.role : "";
    $("popup-search").hidden = options.length < 9;
    $("popup-search").value = "";
    $("glass-listbox").setAttribute("aria-label", kind === "workshop" ? "Выбор цеха" : button.getAttribute("aria-label") || ({master:"Мастер",shift:"Смена",department:"Подразделение"}[kind]));
    $("glass-popup").hidden = false; anchor.setAttribute("aria-expanded", "true");
    renderOptions(); position();
    if (!$("popup-search").hidden) $("popup-search").focus({preventScroll: true});
    else button.focus({preventScroll: true});
  }
  function position() {
    positionFrame = 0;
    if (!opened || !anchor || !document.contains(anchor)) return;
    const popup = opened === "calendar" ? $("glass-calendar") : $("glass-popup");
    const bounds = anchor.getBoundingClientRect(), scale = state ? state.zoom / 100 : 1;
    const width = opened === "calendar" ? Math.max(330, 350 * Math.min(1.4, scale)) : Math.max(bounds.width, opened === "workshop" ? 265 : 230);
    popup.style.width = Math.min(width, window.innerWidth - 16) + "px";
    const below = window.innerHeight - bounds.bottom - 14, above = bounds.top - 14;
    if (opened !== "calendar") {
      const chrome = 20 + ($("popup-heading").hidden ? 0 : $("popup-heading").offsetHeight + 4) + ($("popup-search").hidden ? 0 : $("popup-search").offsetHeight + 6);
      $("glass-listbox").style.maxHeight = Math.max(44, Math.min(320 * scale, Math.max(below, above) - chrome)) + "px";
    }
    popup.style.maxHeight = Math.max(90, window.innerHeight - 16) + "px";
    const height = popup.offsetHeight;
    let top = below >= height || below >= above ? bounds.bottom + 6 : bounds.top - height - 6;
    top = Math.max(8, Math.min(top, window.innerHeight - height - 8));
    popup.style.top = top + "px";
    popup.style.left = Math.max(8, Math.min(bounds.left, window.innerWidth - popup.offsetWidth - 8)) + "px";
  }
  function schedulePosition() { if (!positionFrame) positionFrame = requestAnimationFrame(position); }
  function dateObject(value) { const a = value.split("-").map(Number); return new Date(Date.UTC(a[0], a[1] - 1, a[2])); }
  function iso(date) { return date.getUTCFullYear() + "-" + String(date.getUTCMonth() + 1).padStart(2, "0") + "-" + String(date.getUTCDate()).padStart(2, "0"); }
  function displayDate(value) { return value.split("-").reverse().join("."); }
  function addDays(value, delta) { const d = dateObject(value); d.setUTCDate(d.getUTCDate() + delta); return iso(d); }
  function renderCalendar() {
    if (!calendar) return;
    const first = new Date(Date.UTC(calendar.year, calendar.month, 1));
    $("calendar-month").textContent = first.toLocaleDateString(({ru:"ru-RU",en:"en-US",es:"es-ES",kk:"kk-KZ",fr:"fr-FR",de:"de-DE",ja:"ja-JP",tt:"tt-RU"}[state.language]||"ru-RU"), {month: "long", year: "numeric", timeZone: "UTC"});
    $("calendar-hint").textContent = window.SmartOrderI18n(calendar.waiting ? "Выберите конец периода или нажмите «Применить»" : "Выберите дату или начало периода");
    $("calendar-period").textContent = calendar.start === calendar.end ? displayDate(calendar.start) : displayDate(calendar.start) + " — " + displayDate(calendar.end);
    const monday = new Date(first); monday.setUTCDate(1 - ((first.getUTCDay() + 6) % 7));
    const fragment = document.createDocumentFragment();
    for (let index = 0; index < 42; index++) {
      const day = new Date(monday); day.setUTCDate(day.getUTCDate() + index);
      const value = iso(day), button = document.createElement("button");
      button.type = "button"; button.dataset.calDate = value; button.textContent = day.getUTCDate();
      button.tabIndex = value === calendar.focus ? 0 : -1;
      button.classList.toggle("other-month", day.getUTCMonth() !== calendar.month);
      button.classList.toggle("in-range", value > calendar.start && value < calendar.end);
      button.classList.toggle("range-edge", value === calendar.start || value === calendar.end);
      button.classList.toggle("today", value === state.filters.today);
      button.setAttribute("aria-label", day.toLocaleDateString(({ru:"ru-RU",en:"en-US",es:"es-ES",kk:"kk-KZ",fr:"fr-FR",de:"de-DE",ja:"ja-JP",tt:"tt-RU"}[state.language]||"ru-RU"), {day: "numeric", month: "long", year: "numeric", timeZone: "UTC"}));
      button.setAttribute("aria-pressed", value >= calendar.start && value <= calendar.end ? "true" : "false");
      fragment.appendChild(button);
    }
    replace($("calendar-days"), fragment); schedulePosition();
  }
  function focusCalendar(value) {
    calendar.focus = value;
    const d = dateObject(value); calendar.month = d.getUTCMonth(); calendar.year = d.getUTCFullYear(); renderCalendar();
    const button = $("calendar-days").querySelector('[data-cal-date="' + value + '"]');
    if (button) button.focus({preventScroll: true});
  }
  function showCalendar(button) {
    if (!state || button.disabled) return;
    if (opened === "calendar") { close(true); return; }
    close(); opened = "calendar"; anchor = button;
    const start = state.filters.dateStart || state.filters.today, end = state.filters.dateEnd || start;
    const date = dateObject(start);
    calendar = {start, end, year: date.getUTCFullYear(), month: date.getUTCMonth(), waiting: false, focus: start};
    $("glass-calendar").hidden = false; anchor.setAttribute("aria-expanded", "true");
    renderCalendar(); position();
    requestAnimationFrame(() => { if (calendar) focusCalendar(calendar.focus); });
  }
  function calendarAction(action) {
    if (!calendar) return;
    if (action === "cancel") { close(true); return; }
    if (action === "apply") { const payload = {start: calendar.start, end: calendar.end}; close(true); send("date_range", payload); return; }
    if (action === "today") {
      calendar.start = calendar.end = state.filters.today; calendar.waiting = false;
      focusCalendar(state.filters.today); return;
    }
    const d = new Date(Date.UTC(calendar.year, calendar.month + (action === "next" ? 1 : -1), 1));
    calendar.year = d.getUTCFullYear(); calendar.month = d.getUTCMonth(); calendar.focus = iso(d); renderCalendar();
  }
  function update(current, sender) {
    state = current; dispatch = sender;
    for (const name of ["master", "shift", "department"]) {
      const filter = state.filters[name], option = filter.options.find(o => o.value === filter.value);
      $(name + "-value").textContent = option ? option.label : "";
      $(name + "-trigger").title = option ? option.label : "";
      $(name + "-trigger").disabled = !state.allowed || state.busy;
    }
    if (opened && (state.busy || (opened !== "workshop" && !state.allowed) || (opened === "workshop" && !state.workshopEnabled))) { close(); return; }
    if (opened && opened !== "calendar") {
      const refreshed = opened === "workshop" ? state.workshops : state.filters[opened].options;
      const signature = JSON.stringify(refreshed);
      if (signature !== listSignature) { listSignature = signature; options = refreshed.map(o => Object.assign({},o)); renderOptions(); }
    }
  }
  document.addEventListener("click", event => {
    const combo = event.target.closest("[data-combo]");
    if (combo) { showList(combo.dataset.combo, combo); return; }
    const picker = event.target.closest("[data-calendar]");
    if (picker) { showCalendar(picker); return; }
    const option = event.target.closest("[data-option-index]");
    if (option && opened) { choose(Number(option.dataset.optionIndex)); return; }
    const day = event.target.closest("[data-cal-date]");
    if (day && calendar) {
      const value = day.dataset.calDate;
      if (!calendar.waiting) { calendar.start = calendar.end = value; calendar.waiting = true; }
      else { const first = calendar.start; calendar.start = first < value ? first : value; calendar.end = first < value ? value : first; calendar.waiting = false; }
      focusCalendar(value); return;
    }
    const control = event.target.closest("[data-cal]");
    if (control) { calendarAction(control.dataset.cal); return; }
    if (!event.target.closest(".glass-popover")) close();
  });
  $("popup-search").addEventListener("input", renderOptions);
  $("glass-listbox").addEventListener("pointermove", event => { const item = event.target.closest("[data-option-index]"); if (item) setActive(Number(item.dataset.optionIndex), false); });
  document.addEventListener("keydown", event => {
    const target = event.target.closest ? event.target : document.activeElement || document.body;
    if (!opened) {
      const trigger = target.closest("[data-combo]");
      if (trigger && ["ArrowDown", "ArrowUp", "Enter", " "].includes(event.key)) {
        event.preventDefault(); event.stopImmediatePropagation(); showList(trigger.dataset.combo, trigger);
      }
      return;
    }
    if (event.key === "Escape") { event.preventDefault(); event.stopImmediatePropagation(); close(true); return; }
    if (event.key === "Tab" && opened !== "calendar") { close(true); return; }
    if (opened === "calendar") {
      const day = target.closest("[data-cal-date]");
      if (day && ["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"].includes(event.key)) {
        event.preventDefault(); event.stopImmediatePropagation();
        focusCalendar(addDays(day.dataset.calDate, {ArrowLeft:-1,ArrowRight:1,ArrowUp:-7,ArrowDown:7}[event.key]));
      }
      return;
    }
    const enabled = shown.map((o,i) => o.enabled !== false ? i : -1).filter(i => i >= 0);
    let next = active;
    if (["ArrowDown", "ArrowUp", "Home", "End", "PageDown", "PageUp"].includes(event.key)) {
      event.preventDefault(); event.stopImmediatePropagation();
      const at = enabled.indexOf(active);
      if (event.key === "Home") next = enabled[0];
      else if (event.key === "End") next = enabled[enabled.length - 1];
      else next = enabled[Math.max(0,Math.min(enabled.length - 1,at + ({ArrowDown:1,ArrowUp:-1,PageDown:6,PageUp:-6}[event.key])))];
      setActive(next); return;
    }
    if (event.key === "Enter" || (event.key === " " && target.tagName !== "INPUT")) {
      event.preventDefault(); event.stopImmediatePropagation(); choose(active); return;
    }
    if (event.key.length === 1 && target.tagName !== "INPUT" && !event.ctrlKey && !event.metaKey) {
      event.preventDefault(); event.stopImmediatePropagation(); clearTimeout(typeTimer);
      typeAhead += event.key.toLocaleLowerCase("ru"); typeTimer = setTimeout(() => {typeAhead = "";}, 700);
      const found = shown.findIndex(o => o.enabled !== false && o.label.toLocaleLowerCase("ru").startsWith(typeAhead));
      setActive(found);
    }
  });
  window.addEventListener("resize", schedulePosition);
  window.addEventListener("blur", () => close());
  document.addEventListener("scroll", schedulePosition, true);
  window.GlassPopovers = Object.freeze({update, close});
})();
