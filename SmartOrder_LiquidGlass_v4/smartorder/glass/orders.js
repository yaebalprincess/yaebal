"use strict";
(() => {
  const $ = id => document.getElementById(id);
  let state = null, transport = null, selected = null;
  let rowSignature = "", historySignature = "", tabSignature = "";
  let toastTimer, lastZoom = 100;
  const rowNodes = new Map();
  // Qt 5.15.2 ships Chromium 83, before Element.replaceChildren.
  function replaceContent(node, fragment) { node.textContent = ""; node.appendChild(fragment); }

  function send(action, payload = {}) {
    if (!transport) return;
    transport(action, JSON.stringify(payload), accepted => {
      if (accepted === false) toast("Действие недоступно.");
    });
  }
  function toast(message) {
    $("toast").textContent = String(message);
    $("toast").hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => { $("toast").hidden = true; }, 4500);
  }
  function selectRow(key, notify = true) {
    if (selected && rowNodes.has(selected)) {
      rowNodes.get(selected).classList.remove("selected");
      rowNodes.get(selected).setAttribute("aria-selected", "false");
    }
    selected = key;
    if (key && rowNodes.has(key)) {
      rowNodes.get(key).classList.add("selected");
      rowNodes.get(key).setAttribute("aria-selected", "true");
    }
    if (notify) send("select", {key});
  }
  function renderRows(rows) {
    const signature = JSON.stringify(rows);
    if (signature === rowSignature) return;
    rowSignature = signature;
    const scroll = $("table-scroll"), top = scroll.scrollTop, left = scroll.scrollLeft;
    const fragment = document.createDocumentFragment();
    rowNodes.clear();
    for (const record of rows) {
      const tr = document.createElement("tr");
      tr.dataset.key = record.key;
      tr.classList.toggle("draft", record.draft);
      tr.setAttribute("aria-selected", "false");
      for (const value of record.cells) {
        const td = document.createElement("td");
        td.textContent = value; // names and DB text must never become HTML
        td.title = value;
        tr.appendChild(td);
      }
      fragment.appendChild(tr);
      rowNodes.set(record.key, tr);
    }
    replaceContent($("order-rows"), fragment);
    scroll.scrollTop = top; scroll.scrollLeft = left;
  }
  function renderSelect(id, filter) {
    const control = $(id), signature = JSON.stringify(filter.options);
    if (control.dataset.signature !== signature) {
      const fragment = document.createDocumentFragment();
      for (const option of filter.options) {
        const node = document.createElement("option");
        node.value = option.value === null ? "" : String(option.value);
        node.textContent = option.label;
        fragment.appendChild(node);
      }
      replaceContent(control, fragment);
      control.dataset.signature = signature;
    }
    const value = filter.value === null ? "" : String(filter.value);
    if (control.value !== value) control.value = value;
    control.disabled = !state.allowed || state.busy;
  }
  function render(raw) {
    state = typeof raw === "string" ? JSON.parse(raw) : raw;
    document.documentElement.dataset.theme = state.theme;
    document.documentElement.dataset.embedded = state.embedded ? "true" : "false";
    const fonts = state.appearance && state.appearance.fonts || {};
    for (const [role, spec] of Object.entries(fonts)) {
      const prefix = "--font-" + role.replace(/_/g, "-");
      document.documentElement.style.setProperty(prefix + "-family", JSON.stringify(spec.family));
      document.documentElement.style.setProperty(prefix + "-size", spec.size + "px");
      document.documentElement.style.setProperty(prefix + "-weight", String(spec.weight));
      document.documentElement.style.setProperty(prefix + "-style", spec.italic ? "italic" : "normal");
    }
    document.documentElement.style.setProperty("--ui-scale", String(state.zoom / 100));
    $("theme").checked = state.theme !== "dark";
    $("theme").setAttribute("aria-label", "Светлая тема");
    $("theme-label").textContent = state.theme === "dark" ? "Тёмная тема" : "Светлая тема";
    $("account-label").textContent = state.username + " · " + state.workshop;
    $("account").title = state.role + "\nВыбрать цех";
    $("account").disabled = !state.workshopEnabled;
    $("notifications").hidden = !state.showNotifications;
    $("notification-count").textContent = state.notifications || "";
    $("zoom").value = state.zoom; lastZoom = state.zoom;
    updateZoom(state.zoom);
    $("maximize-icon").setAttribute("href", state.maximized ? "#i-restore" : "#i-max");
    $("fullscreen-hint").textContent = state.fullscreen ? "Esc — выйти из полноэкранного режима" : "Esc — для полноэкранного режима";
    const tabsKey = JSON.stringify(state.tabs);
    if (tabsKey !== tabSignature) {
      tabSignature = tabsKey;
      const fragment = document.createDocumentFragment();
      state.tabs.forEach((tab, index) => {
        const button = document.createElement("button");
        button.className = "tab" + (index === 0 ? " active" : "");
        button.textContent = tab.label;
        button.disabled = !tab.enabled;
        button.dataset.tab = index;
        if (index === 0) button.setAttribute("aria-current", "page");
        fragment.appendChild(button);
      });
      replaceContent($("tabs"), fragment);
    }
    for (const name of ["master", "shift", "department"]) renderSelect(name, state.filters[name]);
    $("date-value").textContent = state.filters.date;
    $("date").title = state.filters.date + " · Выбрать дату или период";
    $("date").disabled = !state.allowed || state.busy;
    for (const [name, action] of Object.entries(state.actions)) {
      $(name).hidden = !action.visible;
      $(name).disabled = !action.enabled;
    }
    $("order-actions").style.setProperty("grid-template-columns", "");
    const visibleActions = Object.values(state.actions).filter(a => a.visible).length;
    if (window.innerWidth > 1000) $("order-actions").style.gridTemplateColumns = "repeat(" + Math.max(1, visibleActions) + ", minmax(0, 1fr))";
    renderRows(state.rows);
    selectRow(state.selected, false);
    const historyKey = JSON.stringify(state.history);
    if (historyKey !== historySignature) {
      historySignature = historyKey;
      const fragment = document.createDocumentFragment();
      state.history.forEach((text, index) => {
        const li = document.createElement("li");
        li.textContent = text; li.dataset.index = index;
        li.title = text + "\nДвойной щелчок — подробности";
        fragment.appendChild(li);
      });
      replaceContent($("history"), fragment);
    }
    $("access-overlay").hidden = state.allowed;
    $("table-panel").setAttribute("aria-busy", state.busy ? "true" : "false");
    window.GlassPopovers.update(state, send);
  }
  function updateZoom(value) {
    $("zoom-value").textContent = value + "%";
    const percent = (value - 50) / 1.5;
    $("zoom").style.background = "linear-gradient(to right, #0781ff 0%, #0781ff " + percent + "%, rgba(112,151,193,.30) " + percent + "%, rgba(112,151,193,.30) 100%)";
  }
  document.addEventListener("click", event => {
    const tab = event.target.closest("[data-tab]");
    if (tab && !tab.disabled) { send("tab", {index: Number(tab.dataset.tab)}); return; }
    const action = event.target.closest("button[data-action]");
    if (action && !action.disabled) {
      send(action.dataset.action, {key: selected});
      $("context-menu").hidden = true;
      return;
    }
    const row = event.target.closest("tr[data-key]");
    if (row) selectRow(row.dataset.key);
    if (!event.target.closest("#context-menu")) $("context-menu").hidden = true;
  });
  $("order-rows").addEventListener("dblclick", event => {
    const row = event.target.closest("tr[data-key]");
    if (row) { selectRow(row.dataset.key); send("open", {key: row.dataset.key}); }
  });
  $("history").addEventListener("dblclick", event => {
    const item = event.target.closest("li[data-index]");
    if (item) send("history", {index: Number(item.dataset.index)});
  });
  $("order-rows").addEventListener("contextmenu", event => {
    const row = event.target.closest("tr[data-key]");
    if (!row || !state) return;
    event.preventDefault(); selectRow(row.dataset.key);
    const menu = $("context-menu");
    for (const name of ["edit", "export", "delete"]) {
      $("context-" + name).hidden = !state.actions[name].visible;
      $("context-" + name).disabled = state.busy || !state.actions[name].visible || (name === "export" && row.classList.contains("draft")) || (name === "delete" && !row.classList.contains("draft"));
    }
    menu.querySelector('[data-action="view"]').hidden = row.classList.contains("draft");
    menu.hidden = false;
    menu.style.left = Math.max(5, Math.min(event.clientX, window.innerWidth - menu.offsetWidth - 8)) + "px";
    menu.style.top = Math.max(5, Math.min(event.clientY, window.innerHeight - menu.offsetHeight - 8)) + "px";
  });
  document.addEventListener("change", event => {
    const filter = event.target.dataset.filter;
    if (filter) send("filter", {name: filter, value: filter === "shift" ? event.target.value : event.target.value === "" ? null : Number(event.target.value)});
  });
  $("theme").addEventListener("change", event => send("theme", {dark: !event.target.checked}));
  $("zoom").addEventListener("input", event => updateZoom(Number(event.target.value)));
  $("zoom").addEventListener("change", event => send("zoom", {value: Number(event.target.value)}));
  $("titlebar").addEventListener("mousedown", event => {
    if (event.button === 0 && !event.target.closest("button, input, label")) { event.preventDefault(); send("move"); }
  });
  $("titlebar").addEventListener("dblclick", event => {
    if (!event.target.closest("button, input, label")) send("maximize");
  });
  $("resize-corner").addEventListener("mousedown", event => { if (event.button === 0) send("resize"); });
  document.addEventListener("keydown", event => {
    const target = event.target.closest ? event.target : document.activeElement || document.body;
    const inField = !!target.closest("input, select, textarea");
    if (event.key === "Escape" && !$("context-menu").hidden) { $("context-menu").hidden = true; event.preventDefault(); return; }
    if ((event.key === "Escape" && !inField) || event.key === "F11") { event.preventDefault(); if (!event.repeat) send("fullscreen"); return; }
    if (event.key === "F5") { event.preventDefault(); send("refresh"); }
    if ((event.ctrlKey || event.metaKey) && ["+", "=", "-", "0"].includes(event.key)) {
      event.preventDefault(); send("zoom", {value: event.key === "0" ? 100 : Math.max(50, Math.min(200, lastZoom + (event.key === "-" ? -10 : 10)))});
    }
    if (inField || !state || !state.allowed) return;
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      const index = state.rows.findIndex(row => row.key === selected);
      const next = state.rows[Math.max(0, Math.min(state.rows.length - 1, index + (event.key === "ArrowDown" ? 1 : -1)))];
      if (next) { selectRow(next.key); rowNodes.get(next.key).scrollIntoView({block: "nearest"}); }
    }
    if (event.key === "Enter" && selected && !target.closest("button")) { event.preventDefault(); send("open", {key: selected}); }
    if (event.key === "Delete" && selected && state.actions.delete.enabled) { event.preventDefault(); send("delete", {key: selected}); }
  });
  window.addEventListener("blur", () => { $("context-menu").hidden = true; });
  window.addEventListener("resize", () => {
    if (state) render(state);
    $("context-menu").hidden = true;
  });
  // Also used by the local screenshot/interaction checks. No sample records
  // or fake account are loaded by the production page.
  window.SmartOrderView = Object.freeze({render, bindTransport(callback) { transport = callback; }});
  if (window.qt && window.qt.webChannelTransport && typeof QWebChannel !== "undefined") {
    new QWebChannel(window.qt.webChannelTransport, channel => {
      const bridge = channel.objects.orders;
      transport = bridge.dispatch.bind(bridge);
      bridge.stateChanged.connect(render);
      bridge.message.connect(toast);
      send("ready");
    });
  }
})();
