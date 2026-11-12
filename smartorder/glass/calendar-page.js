"use strict";
(() => {
  let bridge=null;
  let translations={};
  const root=document.getElementById("glass-calendar");
  const picker=window.SmartOrderCalendar(root,{
    translate:value=>translations[value]||value,
    apply:value=>{if(bridge)bridge.select(value.start);},
    cancel:()=>{if(bridge)bridge.cancel();}
  });
  window.setCalendarState=current=>{
    translations=current.translations||{};
    for(const [action,source] of [["today","Сегодня"],["cancel","Отмена"],["apply","Применить"]]){
      root.querySelector('[data-cal="'+action+'"]').textContent=translations[source]||source;
    }
    document.documentElement.dataset.theme=current.theme;
    document.documentElement.lang=current.language;
    document.documentElement.style.setProperty("--ui-scale",current.scale);
    for(const [role,spec] of Object.entries(current.appearance&&current.appearance.fonts||{})){
      const prefix="--font-"+role.replace(/_/g,"-");
      document.documentElement.style.setProperty(prefix+"-family",JSON.stringify(spec.family));
      document.documentElement.style.setProperty(prefix+"-size",spec.size+"px");
      document.documentElement.style.setProperty(prefix+"-weight",String(spec.weight));
      document.documentElement.style.setProperty(prefix+"-style",spec.italic?"italic":"normal");
    }
    picker.open(current.date,current.date,{single:true,today:current.today,language:current.language});
    requestAnimationFrame(()=>requestAnimationFrame(()=>{if(bridge)bridge.painted();}));
  };
  document.addEventListener("click",event=>{
    const day=event.target.closest("[data-cal-date]");if(day){picker.pick(day.dataset.calDate);return;}
    const action=event.target.closest("[data-cal]");if(action)picker.action(action.dataset.cal);
  });
  document.addEventListener("keydown",event=>{if(event.key==="Escape"){event.preventDefault();if(bridge)bridge.cancel();}else picker.keydown(event);});
  new QWebChannel(qt.webChannelTransport,channel=>{bridge=channel.objects.calendar;bridge.ready();});
})();
