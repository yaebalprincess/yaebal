#include "panels.h"
#include <windowsx.h>
#include <shellapi.h>
#include <commctrl.h>
#include <shlobj.h>
#include <vector>
#include <array>
#include <algorithm>
#include <string>
#include <cwchar>
#include <memory>
#include <initializer_list>

namespace {
constexpr COLORREF bg = RGB(32,34,32), card = RGB(20,23,20), fg = RGB(241,244,239),
    muted = RGB(177,186,175), accent = RGB(68,214,44), editbg = RGB(44,48,44);
constexpr int Name=150, Mode=151, Pair=152, LiveX=153,LiveY=154;
using ModeT = viper::CalibrationMode;
struct Item { HWND h; int x,y,w,hgt; bool stretch; bool right; };
struct Pane {
    Panel kind;
    int dpi=96, offset=0, content=0;
    HFONT font{},header{},small{};
    HBRUSH bgBrush=CreateSolidBrush(bg),cardBrush=CreateSolidBrush(card),editBrush=CreateSolidBrush(editbg);
    std::vector<Item> items;
    std::vector<RECT> cards;
    std::array<HWND,5> rows{};
    HWND live{}, summary{};
    explicit Pane(Panel p):kind(p){}
    ~Pane(){ for(auto f:{font,header,small}) DeleteObject(f); for(auto b:{bgBrush,cardBrush,editBrush}) DeleteObject(b); }
    int s(int v)const{return MulDiv(v,dpi,96);}
};
Pane& pane(HWND h){return *reinterpret_cast<Pane*>(GetWindowLongPtrW(h,GWLP_USERDATA));}
HFONT makeFont(int dpi,int size,int weight){
    return CreateFontW(-MulDiv(size,dpi,96),0,0,0,weight,0,0,0,DEFAULT_CHARSET,OUT_DEFAULT_PRECIS,CLIP_DEFAULT_PRECIS,CLEARTYPE_QUALITY,DEFAULT_PITCH,L"Segoe UI");
}
HWND add(HWND h,LPCWSTR cls,LPCWSTR t,DWORD style,int id,int x,int y,int w,int ht,HFONT font,bool stretch=false,bool right=false){
    auto& p=pane(h);
    HWND a=CreateWindowExW(0,cls,t,WS_CHILD|WS_VISIBLE|style,0,0,0,0,h,reinterpret_cast<HMENU>(static_cast<INT_PTR>(id)),GetModuleHandleW(nullptr),nullptr);
    SendMessageW(a,WM_SETFONT,reinterpret_cast<WPARAM>(font),TRUE);
    p.items.push_back({a,x,y,w,ht,stretch,right});return a;
}
HWND label(HWND h,LPCWSTR t,int x,int y,int w,int ht,bool head=false,bool stretch=true){
    return add(h,L"STATIC",t,SS_LEFT|SS_NOPREFIX,head?101:100,x,y,w,ht,head?pane(h).header:pane(h).font,stretch);
}
HWND edit(HWND h,int id,int x,int y,int w,bool number){
    HWND e=add(h,L"EDIT",L"",WS_BORDER|WS_TABSTOP|ES_AUTOHSCROLL|(number?ES_NUMBER:0),id,x,y,w,28,pane(h).font);
    SendMessageW(e,EM_SETLIMITTEXT,number?5:64,0);return e;
}
void button(HWND h,int id,LPCWSTR t,int x,int y,int w){
    add(h,L"BUTTON",t,WS_TABSTOP|BS_OWNERDRAW,id,x,y,w,31,pane(h).font);
}
void block(Pane& p,int x,int y,int w,int ht){p.cards.push_back({x,y,x+w,y+ht});}
HWND combo(HWND h,int id,int x,int y,int w){return add(h,L"COMBOBOX",L"",WS_VSCROLL|WS_TABSTOP|CBS_DROPDOWNLIST|CBS_HASSTRINGS,id,x,y,w,220,pane(h).font);}
std::vector<std::pair<int,int>> values(int mode){
    switch(mode){
        case 0: return {{1,1},{2,2},{3,3}};
        case 1: return {{2,1},{3,1},{3,2}};
        case 2: return {{3,3},{4,4},{5,5},{7,7}};
        default:return {{4,3},{7,3},{8,3}};
    }
}
void pairs(HWND h,int idx,int lift,int land){
    HWND c=GetDlgItem(h,Pair); ComboBox_ResetContent(c);int n=0,sel=0;
    for(auto v:values(idx)){
        std::wstring t=std::to_wstring(v.first);
        if(idx==1||idx==3)t+=L"  /  "+std::to_wstring(v.second);
        if(idx<2)t+=L" мм";
        ComboBox_AddString(c,t.c_str());if(v.first==lift&&v.second==land)sel=n;++n;
    }
    ComboBox_SetCurSel(c,sel);
}
void layout(HWND h){
    auto& p=pane(h);RECT r;GetClientRect(h,&r);
    SCROLLINFO si{sizeof(si),SIF_RANGE|SIF_PAGE|SIF_POS,0,p.s(p.content)-1,static_cast<UINT>(r.bottom),p.offset,0};
    SetScrollInfo(h,SB_VERT,&si,TRUE);p.offset=GetScrollPos(h,SB_VERT);GetClientRect(h,&r);
    int extra=r.right-p.s(820);
    for(const auto& i:p.items)MoveWindow(i.h,p.s(i.x)+(i.right?extra:0),p.s(i.y)-p.offset,std::max(1,p.s(i.w)+(i.stretch?extra:0)),p.s(i.hgt),TRUE);
    InvalidateRect(h,nullptr,TRUE);
}
void init(HWND h){
    auto& p=pane(h);p.dpi=GetDpiForWindow(h);if(!p.dpi)p.dpi=96;
    p.font=makeFont(p.dpi,15,FW_NORMAL);p.header=makeFont(p.dpi,20,FW_SEMIBOLD);p.small=makeFont(p.dpi,13,FW_NORMAL);
    if(p.kind==Panel::Setup){
        p.content=418;block(p,20,16,780,183);block(p,20,212,780,182);
        label(h,L"Локальный профиль",43,34,730,32,true);
        label(h,L"Название",43,86,140,22); edit(h,Name,43,111,360,false);
        label(h,L"Файл хранит ступени DPI, частоту опроса, подсветку и параметры калибровки.",43,156,728,41);
        label(h,L"Применение профиля",43,232,725,34,true);
        label(h,L"Откройте профиль, выберите вкладку с нужными параметрами и нажмите кнопку записи. Настройки Windows применяются отдельно.",43,276,729,52);
        label(h,L"На вкладке «Память» можно сравнить значения в файле с показаниями подключённой мыши.",43,340,727,46);
    } else if(p.kind==Panel::Calibration){
        p.content=383; block(p,20,16,780,340);
        label(h,L"Калибровка поверхности",43,35,727,34,true);
        label(h,L"Выберите, на какой высоте сенсор прекращает отслеживание при подъёме мыши и возобновляет его при опускании.",43,88,724,48);
        label(h,L"Режим отслеживания",43,158,374,23,false,false);
        label(h,L"Высота или уровень",442,158,300,23,false,false);
        HWND m=combo(h,Mode,43,188,374);combo(h,Pair,442,188,255);
        for(auto t:{L"Интеллектуальное",L"Интеллектуальное · раздельные высоты",L"Ручное · уровень",L"Ручное · раздельные уровни"})ComboBox_AddString(m,t);
        ComboBox_SetCurSel(m,0);pairs(h,0,2,2);
        label(h,L"В раздельном режиме первое число задаёт отрыв, второе — возврат. Для ручного режима указаны ступени сенсора.",43,252,725,50);
        label(h,L"После отключения питания калибровку может понадобиться применить снова.",43,311,725,34);
    } else {
        p.content=565;block(p,20,14,780,247);block(p,20,272,780,102); block(p,20,386,780,167);
        label(h,L"Ступени чувствительности",40,25,730,31,true);
        label(h,L"Уровень",42,70,104,21,false,false); label(h,L"В редакторе  ·  X / Y",150,70,240,21,false,false); label(h,L"С мыши  ·  X / Y",425,70,300,21,false,false);
        for(int i=0;i<5;i++) {
            label(h,(L"0"+std::to_wstring(i+1)).c_str(),43,101+i*28,60,22,false,false);
            add(h,L"STATIC",L"—",SS_LEFT,160+i,150,101+i*28,249,23,p.font);
            p.rows[i]=add(h,L"STATIC",L"Не считано",SS_LEFT,173+i,425,101+i*28,316,23,p.font);
        }
        p.summary=label(h,L"",42,239,728,20);
        label(h,L"Текущий DPI сенсора",41,284,345,30,true,false);
        p.live=label(h,L"Показания ещё не считаны",42,329,353,29,false,false);
        label(h,L"X",399,321,18,23,false,false);edit(h,LiveX,423,317,75,true);
        label(h,L"Y",515,321,19,23,false,false);edit(h,LiveY,539,317,75,true);
        button(h,CmdSetCurrent,L"Задать DPI",638,315,131);
        label(h,L"Сброс памяти",41,400,725,31,true);
        label(h,L"Можно восстановить заводские ступени DPI или очистить пользовательскую память мыши. Полный заводской сброс также доступен через Synapse.",42,441,724,48);
        button(h,CmdRestore,L"Восстановить DPI…",42,503,176);
        button(h,CmdFormat,L"Очистить память…",229,503,188);
        button(h,CmdSynapse,L"Открыть Synapse",428,503,157);
        button(h,CmdGuide,L"Инструкция Razer",596,503,172);
    }
}
LRESULT CALLBACK proc(HWND h,UINT m,WPARAM w,LPARAM l){
    if(m==WM_NCCREATE){
        auto* c=reinterpret_cast<CREATESTRUCTW*>(l);SetWindowLongPtrW(h,GWLP_USERDATA,reinterpret_cast<LONG_PTR>(c->lpCreateParams));return TRUE;
    }
    auto* p=reinterpret_cast<Pane*>(GetWindowLongPtrW(h,GWLP_USERDATA));if(!p)return DefWindowProcW(h,m,w,l);
    switch(m){
        case WM_CREATE:init(h);return 0;
        case WM_SIZE:layout(h);return 0;
        case WM_VSCROLL:{
            SCROLLINFO si{};si.cbSize=sizeof(si);si.fMask=SIF_ALL;GetScrollInfo(h,SB_VERT,&si);
            switch(LOWORD(w)){
                case SB_LINEUP:p->offset-=p->s(28);break;case SB_LINEDOWN:p->offset+=p->s(28);break;
                case SB_PAGEUP:p->offset-=si.nPage;break;case SB_PAGEDOWN:p->offset+=si.nPage;break;
                case SB_THUMBTRACK:case SB_THUMBPOSITION:p->offset=si.nTrackPos;break;
            }
            layout(h);return 0;
        }
        case WM_MOUSEWHEEL:p->offset-=GET_WHEEL_DELTA_WPARAM(w)*p->s(52)/WHEEL_DELTA;layout(h);return 0;
        case WM_COMMAND:
            if(LOWORD(w)==Mode&&HIWORD(w)==CBN_SELCHANGE){pairs(h,ComboBox_GetCurSel(GetDlgItem(h,Mode)),0,0);return 0;}
            if(LOWORD(w)>=CmdRead&&LOWORD(w)<=CmdFormat&&HIWORD(w)==BN_CLICKED)SendMessageW(GetParent(h),WM_COMMAND,w,l);
            return 0;
        case WM_ERASEBKGND:return 1;
        case WM_PAINT:{
            PAINTSTRUCT ps;HDC dc=BeginPaint(h,&ps);RECT r;GetClientRect(h,&r);FillRect(dc,&ps.rcPaint,p->bgBrush);
            for(auto a:p->cards){RECT q{p->s(a.left),p->s(a.top)-p->offset,r.right-p->s(820-a.right),p->s(a.bottom)-p->offset};FillRect(dc,&q,p->cardBrush);}
            EndPaint(h,&ps);return 0;
        }
        case WM_CTLCOLORSTATIC:{auto dc=reinterpret_cast<HDC>(w);SetBkColor(dc,card);SetTextColor(dc,GetDlgCtrlID(reinterpret_cast<HWND>(l))==101?accent:fg);return reinterpret_cast<LRESULT>(p->cardBrush);}
        case WM_CTLCOLORLISTBOX:case WM_CTLCOLOREDIT:{auto dc=reinterpret_cast<HDC>(w);SetBkColor(dc,editbg);SetTextColor(dc,fg);return reinterpret_cast<LRESULT>(p->editBrush);}
        case WM_DRAWITEM:{
            auto& d=*reinterpret_cast<DRAWITEMSTRUCT*>(l);const bool down=d.itemState&ODS_SELECTED;
            HBRUSH b=CreateSolidBrush(down?RGB(64,72,63):RGB(47,53,47));FillRect(d.hDC,&d.rcItem,b);DeleteObject(b);
            wchar_t t[128]{};GetWindowTextW(d.hwndItem,t,128);SetBkMode(d.hDC,TRANSPARENT);SetTextColor(d.hDC,fg);SelectObject(d.hDC,p->font);DrawTextW(d.hDC,t,-1,&d.rcItem,DT_CENTER|DT_VCENTER|DT_SINGLELINE|DT_NOPREFIX);
            if(d.itemState&ODS_FOCUS){RECT f=d.rcItem;InflateRect(&f,-3,-3);DrawFocusRect(d.hDC,&f);}return TRUE;
        }
        case WM_NCDESTROY:SetWindowLongPtrW(h,GWLP_USERDATA,0);delete p;break;
    }
    return DefWindowProcW(h,m,w,l);
}
}
HWND CreatePanel(HWND h,Panel type){
    WNDCLASSW c{};c.lpfnWndProc=proc;c.hInstance=GetModuleHandleW(nullptr);c.lpszClassName=L"VC_SettingsPane";c.hCursor=LoadCursorW(nullptr,IDC_ARROW);RegisterClassW(&c);
    return CreateWindowExW(WS_EX_CONTROLPARENT,c.lpszClassName,L"",WS_CHILD|WS_VSCROLL|WS_CLIPCHILDREN,0,0,0,0,h,nullptr,c.hInstance,new Pane(type));
}
std::wstring ProfileName(HWND page){wchar_t name[65]{};GetDlgItemTextW(page,Name,name,65);return name;}
void SetProfileName(HWND page,const std::wstring& t){SetDlgItemTextW(page,Name,t.c_str());}
void SetCalibrationPage(HWND h,const viper::Calibration& c){
    int mode=static_cast<int>(c.mode);ComboBox_SetCurSel(GetDlgItem(h,Mode),mode);pairs(h,mode,c.lift,c.land);
}
viper::Calibration GetCalibrationPage(HWND h){
    int mode=ComboBox_GetCurSel(GetDlgItem(h,Mode));auto list=values(mode);int n=ComboBox_GetCurSel(GetDlgItem(h,Pair));
    auto val=list.at(n>=0&&static_cast<size_t>(n)<list.size()?n:0);
    return {static_cast<ModeT>(mode),val.first,val.second};
}
void ShowMemory(HWND h,const MouseSnapshot& mouse,const viper::Performance* draft,bool copy){
    const auto format=[](const viper::Performance* v,int i){
        if(!v)return std::wstring(L"—");
        if(i>=v->count)return std::wstring(L"Отключён");
        return std::to_wstring(v->x[i])+L" / "+std::to_wstring(v->y[i])+(i+1==v->active?L"    ● Активный":L"");
    };
    for(int i=0;i<5;i++){
        SetDlgItemTextW(h,160+i,format(draft,i).c_str());
        SetWindowTextW(pane(h).rows[i],format(mouse.stages?&*mouse.stages:nullptr,i).c_str());
    }
    std::wstring details=mouse.rateKnown?L"Частота: "+std::to_wstring(mouse.stages->hz)+L" Гц":mouse.stages?L"Частота не считана":L"Данные с мыши ещё не считаны";
    if(mouse.slots){
        details+=L"      Занятые слоты: ";
        bool first=true;
        for(int i=1;i<=5;++i)if((*mouse.slots)[i]){if(!first)details+=L", ";details+=std::to_wstring(i);first=false;}
    }
    SetWindowTextW(pane(h).summary,details.c_str());
    std::wstring t=L"Показания ещё не считаны";if(mouse.current){
        auto [x,y]=*mouse.current;t=L"С мыши: "+std::to_wstring(x)+L" / "+std::to_wstring(y)+L" DPI";
        if(copy){SetDlgItemInt(h,LiveX,x,FALSE);SetDlgItemInt(h,LiveY,y,FALSE);}
    }
    SetWindowTextW(pane(h).live,t.c_str());
}
bool GetCurrentFields(HWND h,int& x,int& y){
    BOOL a{},b{};x=GetDlgItemInt(h,LiveX,&a,FALSE);y=GetDlgItemInt(h,LiveY,&b,FALSE);
    return a&&b&&x>=100&&x<=20000&&y>=100&&y<=20000;
}
void OpenSynapse(HWND parent){
    // Both Synapse versions ship a Start menu or an installation directory shortcut.
    const std::array<int,2> folders{CSIDL_COMMON_PROGRAMS,CSIDL_PROGRAMS};
    for(int id:folders){
        wchar_t menu[MAX_PATH]{};
        if(FAILED(SHGetFolderPathW(parent,id,nullptr,SHGFP_TYPE_CURRENT,menu)))continue;
        for(const wchar_t* sub:{L"\\Razer\\Razer Synapse.lnk",L"\\Razer\\Razer Synapse 4.lnk",L"\\Razer Synapse.lnk",L"\\Razer Synapse 4.lnk"}){
            std::wstring exe=std::wstring(menu)+sub;
            if(GetFileAttributesW(exe.c_str())!=INVALID_FILE_ATTRIBUTES&&reinterpret_cast<INT_PTR>(ShellExecuteW(parent,L"open",exe.c_str(),nullptr,nullptr,SW_SHOWNORMAL))>32)return;
        }
    }
    for(int id:{CSIDL_PROGRAM_FILESX86,CSIDL_PROGRAM_FILES}){
        wchar_t dir[MAX_PATH]{};if(FAILED(SHGetFolderPathW(parent,id,nullptr,SHGFP_TYPE_CURRENT,dir)))continue;
        for(const wchar_t* suffix:{L"\\Razer\\Razer Synapse 3\\WPFUI\\Framework\\Razer Synapse 3.exe",L"\\Razer\\RazerAppEngine\\RazerAppEngine.exe"}){
            std::wstring path=std::wstring(dir)+suffix;
            if(GetFileAttributesW(path.c_str())!=INVALID_FILE_ATTRIBUTES&&reinterpret_cast<INT_PTR>(ShellExecuteW(parent,L"open",path.c_str(),nullptr,nullptr,SW_SHOWNORMAL))>32)return;
        }
    }
    MessageBoxW(parent,L"Ярлык Synapse не найден. Если программа установлена, откройте её в меню «Пуск».\n\nSynapse 4: выберите Viper 8KHz → «?» → Reset → Delete.\nSynapse 3: «Настройки» → «Сброс» → Viper 8KHz.\n\nЗаводской сброс удаляет все профили во встроенной памяти.",L"Заводской сброс",MB_OK|MB_ICONINFORMATION);
}
