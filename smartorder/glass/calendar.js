"use strict";
// One date-grid implementation for the main filters and the order editor.
window.SmartOrderCalendar = function (root, callbacks) {
  const $ = id => root.querySelector("#" + id);
  let selection = null, config = null;
  const parse = value => {const a=value.split("-").map(Number);return new Date(Date.UTC(a[0],a[1]-1,a[2]));};
  const iso = d => d.getUTCFullYear()+"-"+String(d.getUTCMonth()+1).padStart(2,"0")+"-"+String(d.getUTCDate()).padStart(2,"0");
  const display = value => value.split("-").reverse().join(".");
  const locale = () => ({ru:"ru-RU",en:"en-US",es:"es-ES",kk:"kk-KZ",fr:"fr-FR",de:"de-DE",ja:"ja-JP",tt:"tt-RU"}[config.language]||"ru-RU");
  const t = value => callbacks.translate ? callbacks.translate(value) : value;
  function render() {
    if (!selection) return;
    const first=new Date(Date.UTC(selection.year,selection.month,1));
    $("calendar-month").textContent=first.toLocaleDateString(locale(),{month:"long",year:"numeric",timeZone:"UTC"});
    root.querySelectorAll(".calendar-weekdays span").forEach((node,index)=>{
      const label=new Date(Date.UTC(2026,10,9+index)).toLocaleDateString(locale(),{weekday:"short",timeZone:"UTC"});
      node.textContent=label.charAt(0).toLocaleUpperCase()+label.slice(1);
    });
    $("calendar-hint").textContent=t(config.single ? "Выберите дату наряда" : selection.waiting ? "Выберите конец периода или нажмите «Применить»" : "Выберите дату или начало периода");
    $("calendar-period").textContent=selection.start===selection.end ? display(selection.start) : display(selection.start)+" — "+display(selection.end);
    const monday=new Date(first);monday.setUTCDate(1-((first.getUTCDay()+6)%7));
    const fragment=document.createDocumentFragment();
    for (let index=0;index<42;index++) {
      const day=new Date(monday);day.setUTCDate(day.getUTCDate()+index);
      const value=iso(day),button=document.createElement("button");
      button.type="button";button.dataset.calDate=value;button.textContent=day.getUTCDate();button.tabIndex=value===selection.focus?0:-1;
      button.classList.toggle("other-month",day.getUTCMonth()!==selection.month);
      button.classList.toggle("in-range",value>selection.start&&value<selection.end);
      button.classList.toggle("range-edge",value===selection.start||value===selection.end);
      button.classList.toggle("today",value===config.today);
      button.setAttribute("aria-label",day.toLocaleDateString(locale(),{day:"numeric",month:"long",year:"numeric",timeZone:"UTC"}));
      button.setAttribute("aria-pressed",value>=selection.start&&value<=selection.end?"true":"false");
      fragment.appendChild(button);
    }
    $("calendar-days").textContent="";$("calendar-days").appendChild(fragment);
    if(callbacks.rendered)callbacks.rendered();
  }
  function focus(value) {
    if(!selection)return;
    selection.focus=value;const day=parse(value);selection.year=day.getUTCFullYear();selection.month=day.getUTCMonth();render();
    const button=root.querySelector('[data-cal-date="'+value+'"]');if(button)button.focus({preventScroll:true});
  }
  return {
    open(start,end,options) {
      config=options;const day=parse(start);
      selection={start,end:config.single?start:end,year:day.getUTCFullYear(),month:day.getUTCMonth(),waiting:false,focus:start};
      render();return selection;
    },
    reset(){selection=null;},
    focus,
    pick(value) {
      if(!selection)return;
      if(config.single||!selection.waiting){selection.start=selection.end=value;selection.waiting=!config.single;}
      else{const first=selection.start;selection.start=first<value?first:value;selection.end=first<value?value:first;selection.waiting=false;}
      focus(value);
    },
    action(action) {
      if(!selection)return;
      if(action==="cancel"){callbacks.cancel();return;}
      if(action==="apply"){callbacks.apply({start:selection.start,end:selection.end});return;}
      if(action==="today"){selection.start=selection.end=config.today;selection.waiting=false;focus(config.today);return;}
      const day=new Date(Date.UTC(selection.year,selection.month+(action==="next"?1:-1),1));
      selection.year=day.getUTCFullYear();selection.month=day.getUTCMonth();selection.focus=iso(day);render();
    },
    keydown(event) {
      const day=event.target.closest("[data-cal-date]");
      if(!selection||!day||!["ArrowLeft","ArrowRight","ArrowUp","ArrowDown"].includes(event.key))return;
      event.preventDefault();event.stopImmediatePropagation();const next=parse(day.dataset.calDate);
      next.setUTCDate(next.getUTCDate()+({ArrowLeft:-1,ArrowRight:1,ArrowUp:-7,ArrowDown:7}[event.key]));focus(iso(next));
    }
  };
};
