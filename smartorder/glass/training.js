"use strict";
(() => {
  function node(tag, parent, className) {
    const element = document.createElement(tag);
    if (className) element.className = className;
    parent.appendChild(element);
    return element;
  }
  const layer = node("div", document.body);
  layer.id = "training-layer";
  layer.hidden = true;
  const veil = node("div", layer, "training-veil");
  const svgNS = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(svgNS, "svg");
  svg.setAttribute("width", "0");
  svg.setAttribute("height", "0");
  svg.setAttribute("aria-hidden", "true");
  layer.appendChild(svg);
  const clip = document.createElementNS(svgNS, "clipPath");
  clip.id = "training-cutouts";
  svg.appendChild(clip);
  const cutouts = document.createElementNS(svgNS, "path");
  cutouts.setAttribute("clip-rule", "evenodd");
  clip.appendChild(cutouts);
  veil.style.clipPath = "url(#training-cutouts)";
  const ring = node("div", layer, "training-spotlight");
  const rowRing = node("div", layer, "training-row-highlight");
  const number = node("span", layer, "training-step-number");
  const card = node("section", layer, "training-card");
  card.setAttribute("role", "dialog");
  card.setAttribute("aria-label", "Обучение мастера");
  const copy = node("div", card, "training-copy");
  const kicker = node("div", copy, "training-kicker");
  const title = node("h2", copy);
  const body = node("p", copy);
  const stop = node("button", card);
  stop.type = "button";
  stop.textContent = "Завершить обучение";
  stop.addEventListener("click", () => window.SmartOrderView.command("training_stop"));

  let lesson = null, frame = 0;
  const clamp = (value, min, max) => Math.max(min, Math.min(max, value));
  const bounds = element => element.getBoundingClientRect();
  const overlap = (a, b) => Math.max(0, Math.min(a.right, b.right) - Math.max(a.left, b.left))
                         * Math.max(0, Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top));
  function contour(r, radius) {
    const k = Math.min(radius || 0, r.width/2, r.height/2);
    const l = r.left, t = r.top, b = r.bottom, x = r.right;
    return "M"+(l+k)+" "+t+" H"+(x-k)+" Q"+x+" "+t+" "+x+" "+(t+k)+
           " V"+(b-k)+" Q"+x+" "+b+" "+(x-k)+" "+b+
           " H"+(l+k)+" Q"+l+" "+b+" "+l+" "+(b-k)+
           " V"+(t+k)+" Q"+l+" "+t+" "+(l+k)+" "+t+" Z";
  }
  function place(element, r) {
    Object.assign(element.style, {left:r.left+"px", top:r.top+"px",
      width:(r.right-r.left)+"px", height:(r.bottom-r.top)+"px"});
  }
  function spotlight(element, outline, holes) {
    outline.hidden = !element;
    if (!element) return;
    const r = bounds(element);
    holes.push(r);
    place(outline, r);
    outline.style.borderRadius = getComputedStyle(element).borderRadius;
  }
  function layout() {
    if (!lesson) return;
    const target = !lesson.passive && lesson.target && document.querySelector(lesson.target);
    const row = !lesson.passive && lesson.row && document.querySelector('#order-rows tr[data-key="practice"]');
    const holes = [];
    spotlight(target, ring, holes);
    spotlight(row, rowRing, holes);
    const viewport = bounds(layer);
    const paths = [contour(viewport, 0)];
    if (target) paths.push(contour(bounds(target), parseFloat(getComputedStyle(target).borderTopLeftRadius)));
    if (row) paths.push(contour(bounds(row), 0));
    cutouts.setAttribute("d", paths.join(" "));

    number.hidden = !target;
    card.hidden = lesson.passive || (!target && !lesson.external);
    if (card.hidden) return;
    const a = lesson.anchor || [16, 0, 1, 0];
    const r = target ? bounds(target) : {left:a[0], right:a[0]+a[2], top:0, bottom:0};
    if (target) {
      // Keep the entire number visible even when History starts at the top edge.
      number.style.left = clamp(r.left+4, 8, viewport.width-42)+"px";
      number.style.top = clamp(r.top-28, 5, viewport.height-39)+"px";
    }
    const gap = 12;
    const width = Math.min(480, viewport.width-2*gap);
    card.style.width = width+"px";
    card.style.maxHeight = (viewport.height-2*gap)+"px";
    const avoid = target ? holes.concat([bounds(number)]) : holes;
    const sizes = [bounds(card)];
    // On short windows leave a free band for the target. Only the text
    // scrolls within a shortened card; Stop always remains on screen.
    const bands = [r.top-2*gap, viewport.height-r.bottom-2*gap];
    if (row) bands.push(viewport.height-bounds(row).bottom-2*gap);
    for (const height of bands) {
      if (height >= 112 && height < sizes[0].height)
        sizes.push({width, height});
    }
    let best, least = Infinity;
    for (const size of sizes) {
      const candidates = [[r.left,r.bottom+gap],[r.right+gap,r.top],
                          [r.left,r.top-size.height-gap],[r.left-size.width-gap,r.top]];
      if (row) candidates.push([r.left,bounds(row).bottom+gap]);
      for (const [x,y] of candidates) {
        const left = clamp(x,gap,viewport.width-size.width-gap);
        const top = clamp(y,gap,viewport.height-size.height-gap);
        const rect = {left,top,right:left+size.width,bottom:top+size.height};
        const area = avoid.reduce((sum,hole) => sum+overlap(rect,hole), 0);
        if (area < least) { best = {left,top,height:size.height}; least = area; }
      }
    }
    card.style.maxHeight = best.height+"px";
    card.style.left = best.left+"px";
    card.style.top = best.top+"px";
  }
  function refresh() {
    if (!lesson || frame) return;
    frame = requestAnimationFrame(() => { frame = 0; layout(); });
  }
  function show(data) {
    const changed = !lesson || lesson.action !== data.action || lesson.passive !== data.passive;
    lesson = data;
    layer.hidden = false;
    if (changed) {
      number.textContent = String(data.number);
      kicker.textContent = "ШАГ "+data.number+" ИЗ "+data.total+" · ОБУЧЕНИЕ МАСТЕРА";
      title.textContent = data.title;
      body.textContent = data.text;
      copy.scrollTop = 0;
      const target = !data.passive && data.target && document.querySelector(data.target);
      if (target) target.scrollIntoView({block:"nearest", inline:"nearest"});
    }
    layout();
    refresh();
  }
  function hide() {
    lesson = null;
    layer.hidden = true;
    if (frame) cancelAnimationFrame(frame);
    frame = 0;
  }
  document.addEventListener("click", event => {
    if (!lesson || lesson.passive || !lesson.target || card.contains(event.target)) return;
    const target = document.querySelector(lesson.target);
    if (target && target.contains(event.target)) {
      event.preventDefault();
      event.stopImmediatePropagation();
      window.SmartOrderView.command(lesson.action);
    }
  }, true);
  document.addEventListener("keydown", event => {
    if (!lesson || lesson.passive || !["Tab", "Enter", " "].includes(event.key)) return;
    const target = lesson.target && document.querySelector(lesson.target);
    if (event.key === "Tab") {
      event.preventDefault();
      event.stopImmediatePropagation();
      if (target && document.activeElement !== target) {
        if (!target.hasAttribute("tabindex") && target.tagName !== "BUTTON") target.tabIndex = -1;
        target.focus();
      } else stop.focus();
    } else if (event.target !== stop) {
      event.preventDefault();
      event.stopImmediatePropagation();
      if (target) window.SmartOrderView.command(lesson.action);
    }
  }, true);
  document.addEventListener("scroll", refresh, true);
  window.addEventListener("resize", refresh);
  window.SmartOrderCoach = Object.freeze({show, refresh, hide});
})();
