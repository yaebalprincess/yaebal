"use strict";
(() => {
  const root = document.createElement("div"); root.id = "training-layer"; root.hidden = true;
  const veils = document.createElement("div"); root.appendChild(veils);
  const ring = document.createElement("div"); ring.className = "training-spotlight";
  const number = document.createElement("span"); number.className = "training-step-number"; ring.appendChild(number); root.appendChild(ring);
  const rowRing = document.createElement("div"); rowRing.className = "training-row-highlight"; root.appendChild(rowRing);
  const card = document.createElement("section"); card.className = "training-card";
  card.setAttribute("role", "dialog"); card.setAttribute("aria-label", "Обучение мастера");
  const copy = document.createElement("div"); copy.className = "training-copy";
  const tag = document.createElement("div"); tag.className = "training-kicker";
  const title = document.createElement("h2"); const body = document.createElement("p");
  copy.appendChild(tag); copy.appendChild(title); copy.appendChild(body); card.appendChild(copy);
  const stop = document.createElement("button"); stop.type = "button"; stop.textContent = "Завершить обучение";
  stop.addEventListener("click", () => window.SmartOrderView.command("training_stop"));
  card.appendChild(stop); root.appendChild(card); document.body.appendChild(root);
  let lesson = null;
  document.addEventListener("click",event=>{
    if (!lesson || lesson.passive || event.target.closest(".training-card")) return;
    const target=document.querySelector(lesson.target || "#create");
    if (target && (target===event.target || target.contains(event.target))) {
      event.preventDefault();event.stopImmediatePropagation();
      window.SmartOrderView.command(lesson.action);
    }
  },true);
  function rect(element) {
    const r = element.getBoundingClientRect();
    return {x:Math.max(0,r.x),y:Math.max(0,r.y),right:Math.min(innerWidth,r.right),bottom:Math.min(innerHeight,r.bottom)};
  }
  function subtract(regions, hole) {
    const output = [];
    for (const r of regions) {
      const x = Math.max(r.x,hole.x), y = Math.max(r.y,hole.y);
      const right = Math.min(r.right,hole.right), bottom = Math.min(r.bottom,hole.bottom);
      if (x>=right || y>=bottom) {output.push(r);continue;}
      output.push({x:r.x,y:r.y,right:r.right,bottom:y}, {x:r.x,y:bottom,right:r.right,bottom:r.bottom},
                  {x:r.x,y,right:x,bottom}, {x:right,y,right:r.right,bottom});
    }
    return output.filter(r => r.right>r.x && r.bottom>r.y);
  }
  function place(element, r) {
    Object.assign(element.style,{left:r.x+"px",top:r.y+"px",width:(r.right-r.x)+"px",height:(r.bottom-r.y)+"px"});
  }
  function refresh() {
    if (!lesson) return;
    const target = !lesson.passive && !lesson.external && document.querySelector(lesson.target || "#create");
    const row = !lesson.passive && lesson.row && document.querySelector("#order-rows tr");
    const holes = [];
    ring.hidden = !target; rowRing.hidden = !row; card.hidden = !!lesson.passive;
    if (target) {const r = rect(target);holes.push(r);place(ring,r);}
    if (row) {const r=rect(row);holes.push(r);place(rowRing,r);}
    let regions = [{x:0,y:0,right:innerWidth,bottom:innerHeight}];
    for (const hole of holes) regions = subtract(regions,hole);
    veils.textContent = "";
    for (const region of regions) {const node=document.createElement("div");node.className="training-veil";place(node,region);veils.appendChild(node);}
    if (!target && !lesson.external || lesson.passive) return;
    const a=lesson.anchor||[16,0,150,0];
    const r = target ? rect(target) : {x:a[0],y:0,right:a[0]+a[2],bottom:0};
    const width = Math.min(480,innerWidth-32);
    card.style.width=width+"px"; card.style.maxHeight=Math.max(140,innerHeight-32)+"px";
    const height = card.getBoundingClientRect().height;
    const clamp = (x,a,b)=>Math.max(a,Math.min(b,x));
    const candidates = [[r.x,r.bottom+18],[r.right+18,r.y],[r.x,r.y-height-18],[r.x-width-18,r.y]];
    const overlap = p=>Math.max(0,Math.min(p[0]+width,r.right)-Math.max(p[0],r.x))*Math.max(0,Math.min(p[1]+height,r.bottom)-Math.max(p[1],r.y));
    const positions=candidates.map(p=>[clamp(p[0],16,innerWidth-width-16),clamp(p[1],16,innerHeight-height-16)]);
    const best=positions.reduce((a,b)=>overlap(b)<overlap(a)?b:a);
    card.style.left=best[0]+"px";card.style.top=best[1]+"px";
  }
  window.SmartOrderCoach = Object.freeze({
    show(data) {
      lesson=data; root.hidden=false;
      number.textContent=String(data.number); tag.textContent="ШАГ "+data.number+" ИЗ "+data.total+" · ОБУЧЕНИЕ МАСТЕРА";
      title.textContent=data.title;body.textContent=data.text;
      refresh(); requestAnimationFrame(refresh);
    },
    refresh,
    hide() {lesson=null;root.hidden=true;}
  });
  document.addEventListener("scroll",refresh,true);window.addEventListener("resize",refresh);
})();
