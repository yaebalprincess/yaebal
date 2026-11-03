"use strict";
(() => {
  const positions = new WeakMap();
  let hovered = null, pressed = null;
  const reduced = () => window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  function buttonOf(event) { return event.target.closest && event.target.closest("button:not(:disabled)"); }
  function point(button, event) {
    const rect = button.getBoundingClientRect();
    let p = positions.get(button);
    if (!p) { p = {x: rect.width / 2, y: rect.height / 2, tx: 0, ty: 0, frame: 0, last: 0}; positions.set(button, p); }
    p.tx = Math.max(0, Math.min(rect.width, event.clientX - rect.left));
    p.ty = Math.max(0, Math.min(rect.height, event.clientY - rect.top));
    function flow(timestamp) {
      p.frame = 0;
      const elapsed = Math.max(8, timestamp - p.last); p.last = timestamp;
      const factor = reduced() ? 1 : 1 - Math.exp(-elapsed / 42);
      p.x += (p.tx - p.x) * factor; p.y += (p.ty - p.y) * factor;
      button.style.setProperty("--hover-x", p.x.toFixed(2) + "px");
      button.style.setProperty("--hover-y", p.y.toFixed(2) + "px");
      if (Math.abs(p.x - p.tx) + Math.abs(p.y - p.ty) > .2) p.frame = requestAnimationFrame(flow);
    }
    if (!p.frame) { p.last = performance.now(); p.frame = requestAnimationFrame(flow); }
  }
  function release() { if (pressed) pressed.classList.remove("is-pressed"); pressed = null; }
  function press(button, x, y) {
    release(); button.classList.add("liquid-motion", "is-pressed"); pressed = button;
    if (reduced()) return;
    const rect = button.getBoundingClientRect(), diameter = Math.max(rect.width, rect.height) * 2;
    const ripple = document.createElement("span"); ripple.className = "press-ripple";
    ripple.style.width = ripple.style.height = diameter + "px";
    ripple.style.left = x + "px"; ripple.style.top = y + "px";
    ripple.addEventListener("animationend", () => ripple.remove(), {once: true});
    button.appendChild(ripple);
  }
  document.addEventListener("pointerover", event => {
    const button = buttonOf(event);
    if (!button || event.pointerType === "touch" || button.contains(event.relatedTarget)) return;
    if (hovered && hovered !== button) hovered.classList.remove("is-hovered");
    hovered = button; button.classList.add("liquid-motion"); point(button, event);
    requestAnimationFrame(() => { if (hovered === button) button.classList.add("is-hovered"); });
  });
  document.addEventListener("pointermove", event => { const button = buttonOf(event); if (button) point(button, event); });
  document.addEventListener("pointerout", event => {
    const button = event.target.closest && event.target.closest("button");
    if (button && !button.contains(event.relatedTarget)) { button.classList.remove("is-hovered"); if (hovered === button) hovered = null; }
  });
  document.addEventListener("pointerdown", event => {
    const button = buttonOf(event); if (!button || event.button !== 0) return;
    const rect = button.getBoundingClientRect(); press(button, event.clientX - rect.left, event.clientY - rect.top);
  });
  document.addEventListener("pointerup", release);
  document.addEventListener("pointercancel", release);
  document.addEventListener("keydown", event => {
    const button = buttonOf(event); if (button && !event.repeat && (event.key === "Enter" || event.key === " ")) {
      const rect = button.getBoundingClientRect(); press(button, rect.width / 2, rect.height / 2);
    }
  });
  document.addEventListener("keyup", release);
  window.addEventListener("blur", () => { release(); if (hovered) hovered.classList.remove("is-hovered"); hovered = null; });
})();
