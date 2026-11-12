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
  const calendarEngine = window.SmartOrderCalendar($("glass-calendar"), {
    translate:value=>window.SmartOrderI18n ? window.SmartOrderI18n(value) : value,
    rendered:schedulePosition,
    cancel:()=>close(true),
    apply:value=>{close(true);send("date_range",value);}
  });
  function showCalendar(button) {
    if (!state || button.disabled) return;
    if (opened === "calendar") { close(true); return; }
    close(); opened="calendar"; anchor=button;
    const start=state.filters.dateStart||state.filters.today;
    $("glass-calendar").hidden=false;anchor.setAttribute("aria-expanded","true");
    calendar=calendarEngine.open(start,state.filters.dateEnd||start,{single:false,today:state.filters.today,language:state.language});
    position();requestAnimationFrame(()=>{if(calendar)calendarEngine.focus(calendar.focus);});
  }
  function calendarAction(action) {calendarEngine.action(action);}
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
      calendarEngine.pick(day.dataset.calDate); return;
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
      calendarEngine.keydown(event);return;
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
