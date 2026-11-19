#ifndef NOMINMAX
#define NOMINMAX
#endif
#include "windows_tab.h"
#include <commctrl.h>
#include <shellapi.h>
#include <algorithm>
#include <array>
#include <cstdint>
#include <cstring>
#include <limits>
#include <new>
#include <string>

#ifndef SPI_GETMOUSEWHEELROUTING
#define SPI_GETMOUSEWHEELROUTING 0x201C
#define SPI_SETMOUSEWHEELROUTING 0x201D
#endif

namespace {
constexpr wchar_t className[] = L"ViperLocalWindowsMouseTab";
constexpr COLORREF background = RGB(32,34,32), panel = RGB(20,23,20),
    foreground = RGB(242,244,240), muted = RGB(180,185,177), accent = RGB(68,214,44),
    input = RGB(42,46,41), edge = RGB(65,72,63);
constexpr UINT saveFlags = SPIF_UPDATEINIFILE | SPIF_SENDCHANGE;

enum Field { Speed, Precision, Snap, Vanish, Sonar, Trails, Swap, Lines, Chars, Route, Count };
constexpr const wchar_t* names[] = {
    L"Скорость указателя", L"Повышенная точность", L"Кнопка по умолчанию",
    L"Скрытие при вводе", L"Поиск по Ctrl", L"След указателя", L"Основная кнопка",
    L"Вертикальная прокрутка", L"Горизонтальная прокрутка", L"Прокрутка окон"
};
constexpr UINT queries[] = {
    SPI_GETMOUSESPEED, SPI_GETMOUSE, SPI_GETSNAPTODEFBUTTON, SPI_GETMOUSEVANISH,
    SPI_GETMOUSESONAR, SPI_GETMOUSETRAILS, 0, SPI_GETWHEELSCROLLLINES,
    SPI_GETWHEELSCROLLCHARS, SPI_GETMOUSEWHEELROUTING
};

bool readField(Field field, DWORD& value) {
    if (field == Swap) {
        value = GetSystemMetrics(SM_SWAPBUTTON) != 0;
        return true;
    }
    if (field == Precision) {
        int mouse[3]{};
        if (!SystemParametersInfoW(SPI_GETMOUSE, 0, mouse, 0)) return false;
        value = mouse[2] != 0;
        return true;
    }
    value = 0;
    if (!SystemParametersInfoW(queries[field], 0, &value, 0)) return false;
    if (field == Snap || field == Vanish || field == Sonar) value = value != 0;
    if (field == Trails && value < 2) value = 0;
    if ((field == Route && value > 2) || (field == Speed && (value < 1 || value > 20))) {
        SetLastError(ERROR_INVALID_DATA);
        return false;
    }
    return true;
}

bool writeField(Field field, DWORD value) {
    // Win32 passes some setters' scalar values in pvParam and others in uiParam.
    const auto scalar = reinterpret_cast<void*>(static_cast<UINT_PTR>(value));
    switch (field) {
        case Speed: return SystemParametersInfoW(SPI_SETMOUSESPEED, 0, scalar, saveFlags);
        case Precision: {
            int mouse[3]{};
            if (!SystemParametersInfoW(SPI_GETMOUSE, 0, mouse, 0)) return false;
            if (value && mouse[2] == 0) {
                if (mouse[0] == 0 && mouse[1] == 0) { mouse[0] = 6; mouse[1] = 10; }
                mouse[2] = 1;
            } else if (!value) mouse[2] = 0;
            return SystemParametersInfoW(SPI_SETMOUSE, 0, mouse, saveFlags);
        }
        case Snap: return SystemParametersInfoW(SPI_SETSNAPTODEFBUTTON, value, nullptr, saveFlags);
        case Vanish: return SystemParametersInfoW(SPI_SETMOUSEVANISH, 0, scalar, saveFlags);
        case Sonar: return SystemParametersInfoW(SPI_SETMOUSESONAR, 0, scalar, saveFlags);
        case Trails: return SystemParametersInfoW(SPI_SETMOUSETRAILS, value, nullptr, saveFlags);
        case Swap: return SystemParametersInfoW(SPI_SETMOUSEBUTTONSWAP, value, nullptr, saveFlags);
        case Lines: return SystemParametersInfoW(SPI_SETWHEELSCROLLLINES, value, nullptr, saveFlags);
        case Chars: return SystemParametersInfoW(SPI_SETWHEELSCROLLCHARS, value, nullptr, saveFlags);
        case Route: return SystemParametersInfoW(SPI_SETMOUSEWHEELROUTING, 0, scalar, saveFlags);
        default: return false;
    }
}

enum Control { LeftTitle = 100, SpeedLabel, SpeedValue, SpeedSlider, PrecisionCheck, SnapCheck,
    VanishCheck, SonarCheck, TrailsCheck, TrailsLabel, TrailsEdit, RightTitle, SwapLabel,
    SwapCombo, LinesLabel, LinesEdit, PageCheck, CharsLabel, CharsEdit, RouteLabel,
    RouteCombo, More, Status, Reload, Apply, ControlEnd };
constexpr int fieldControl[] = {SpeedSlider, PrecisionCheck, SnapCheck, VanishCheck, SonarCheck,
    TrailsCheck, SwapCombo, LinesEdit, CharsEdit, RouteCombo};

struct Page {
    HWND hwnd{};
    HINSTANCE instance{};
    std::array<HWND,ControlEnd-LeftTitle> controls{};
    std::array<DWORD,Count> original{};
    std::array<bool,Count> available{};
    HFONT font{}, titleFont{};
    HBRUSH bgBrush{}, panelBrush{}, inputBrush{};
    UINT dpi{96};
    int scroll{}, contentHeight{};
    RECT cards[2]{};
    bool updating{}, layingOut{};
    HWND at(int id) const { return controls.at(id-LeftTitle); }
    int px(int n) const { return MulDiv(n,dpi,96); }
    int logical(int pixels) const { return MulDiv(pixels,96,dpi); }
    void status(const wchar_t* value) const { SetWindowTextW(at(Status),value); }
    bool checked(int id) const { return SendMessageW(at(id),BM_GETCHECK,0,0) == BST_CHECKED; }
    void check(int id, bool value) const {
        SendMessageW(at(id),BM_SETCHECK,value ? BST_CHECKED : BST_UNCHECKED,0);
        InvalidateRect(at(id),nullptr,TRUE);
    }
};

UINT windowDpi(HWND hwnd) {
    using GetDpiFn = UINT (WINAPI*)(HWND);
    auto proc = GetProcAddress(GetModuleHandleW(L"user32.dll"),"GetDpiForWindow");
    GetDpiFn getDpi{};
    static_assert(sizeof getDpi == sizeof proc);
    std::memcpy(&getDpi,&proc,sizeof getDpi);
    if (getDpi) return getDpi(hwnd);
    HDC dc = GetDC(hwnd);
    UINT dpi = static_cast<UINT>(GetDeviceCaps(dc,LOGPIXELSX));
    ReleaseDC(hwnd,dc);
    return dpi ? dpi : 96;
}

void fill(HDC dc, RECT rc, COLORREF color) {
    SetDCBrushColor(dc,color);
    FillRect(dc,&rc,static_cast<HBRUSH>(GetStockObject(DC_BRUSH)));
}

LRESULT CALLBACK checkProc(HWND hwnd,UINT msg,WPARAM wp,LPARAM lp,UINT_PTR id,DWORD_PTR data) {
    auto& p = *reinterpret_cast<Page*>(data);
    if (msg == WM_PAINT || msg == WM_PRINTCLIENT) {
        PAINTSTRUCT ps{};
        HDC dc = msg == WM_PAINT ? BeginPaint(hwnd,&ps) : reinterpret_cast<HDC>(wp);
        RECT rc{};
        GetClientRect(hwnd,&rc);
        fill(dc,rc,panel);
        int size=p.px(16), top=(rc.bottom-size)/2;
        RECT box{0,top,size,top+size};
        bool on = SendMessageW(hwnd,BM_GETCHECK,0,0) == BST_CHECKED;
        bool enabled = IsWindowEnabled(hwnd);
        fill(dc,box,enabled && on ? accent : edge);
        InflateRect(&box,-p.px(1),-p.px(1));
        if (!on) fill(dc,box,panel);
        else {
            HPEN pen=CreatePen(PS_SOLID,p.px(2),panel);
            auto previous=SelectObject(dc,pen);
            MoveToEx(dc,p.px(3),top+p.px(8),nullptr);
            LineTo(dc,p.px(7),top+p.px(12));
            LineTo(dc,p.px(13),top+p.px(5));
            SelectObject(dc,previous);
            DeleteObject(pen);
        }
        wchar_t label[160]{};
        GetWindowTextW(hwnd,label,160);
        rc.left=size+p.px(8);
        HFONT old=static_cast<HFONT>(SelectObject(dc,p.font));
        SetBkMode(dc,TRANSPARENT);
        SetTextColor(dc,enabled ? foreground : muted);
        DrawTextW(dc,label,-1,&rc,DT_SINGLELINE|DT_VCENTER|DT_END_ELLIPSIS|DT_NOPREFIX);
        if (GetFocus()==hwnd) DrawFocusRect(dc,&rc);
        SelectObject(dc,old);
        if (msg==WM_PAINT) EndPaint(hwnd,&ps);
        return 0;
    }
    if (msg == WM_NCDESTROY) RemoveWindowSubclass(hwnd,checkProc,id);
    LRESULT result = DefSubclassProc(hwnd,msg,wp,lp);
    if (msg == WM_SETFOCUS || msg == WM_KILLFOCUS || msg == BM_SETCHECK || msg == WM_ENABLE)
        InvalidateRect(hwnd,nullptr,TRUE);
    return result;
}

bool createControls(Page& p) {
    auto add = [&](int id,const wchar_t* cls,const wchar_t* text,DWORD style,DWORD ex=0) {
        HWND hwnd=CreateWindowExW(ex,cls,text,WS_CHILD|WS_VISIBLE|style,0,0,1,1,p.hwnd,
            reinterpret_cast<HMENU>(static_cast<INT_PTR>(id)),p.instance,nullptr);
        p.controls[id-LeftTitle]=hwnd;
        return hwnd;
    };
    auto label = [&](int id,const wchar_t* text,DWORD style=SS_LEFT) {
        add(id,L"STATIC",text,style|SS_CENTERIMAGE|SS_NOPREFIX);
    };
    auto check = [&](int id,const wchar_t* text) {
        HWND ctrl=add(id,L"BUTTON",text,WS_TABSTOP|BS_AUTOCHECKBOX);
        if (ctrl) SetWindowSubclass(ctrl,checkProc,1,reinterpret_cast<DWORD_PTR>(&p));
    };
    auto edit = [&](int id) {
        HWND ctrl=add(id,L"EDIT",L"",WS_TABSTOP|ES_NUMBER|ES_CENTER|ES_AUTOHSCROLL,WS_EX_CLIENTEDGE);
        SendMessageW(ctrl,EM_SETLIMITTEXT,10,0);
    };
    auto combo = [&](int id,std::initializer_list<const wchar_t*> options) {
        HWND ctrl=add(id,L"COMBOBOX",L"",WS_TABSTOP|CBS_DROPDOWNLIST|WS_VSCROLL);
        for (auto s:options) SendMessageW(ctrl,CB_ADDSTRING,0,reinterpret_cast<LPARAM>(s));
    };
    label(LeftTitle,L"Указатель");
    label(SpeedLabel,L"Скорость указателя"); label(SpeedValue,L"",SS_RIGHT);
    HWND speed=add(SpeedSlider,TRACKBAR_CLASSW,L"Скорость указателя",WS_TABSTOP|TBS_NOTICKS);
    SendMessageW(speed,TBM_SETRANGE,FALSE,MAKELPARAM(1,20));
    SendMessageW(speed,TBM_SETPAGESIZE,0,2);
    check(PrecisionCheck,L"Повышенная точность указателя");
    check(SnapCheck,L"Перемещать к кнопке по умолчанию");
    check(VanishCheck,L"Скрывать указатель при вводе");
    check(SonarCheck,L"Показывать положение при нажатии Ctrl");
    check(TrailsCheck,L"Показывать след указателя");
    label(TrailsLabel,L"Длина следа"); edit(TrailsEdit);
    label(RightTitle,L"Кнопки и прокрутка");
    label(SwapLabel,L"Основная кнопка"); combo(SwapCombo,{L"Левая",L"Правая"});
    label(LinesLabel,L"Строк за шаг колеса"); edit(LinesEdit);
    check(PageCheck,L"Прокручивать по одному экрану");
    label(CharsLabel,L"Символов по горизонтали"); edit(CharsEdit);
    label(RouteLabel,L"Какое окно прокручивать");
    combo(RouteCombo,{L"Только активное",L"По умолчанию для приложения",L"Окно под указателем"});
    add(More,L"BUTTON",L"Другие свойства мыши…",BS_OWNERDRAW|WS_TABSTOP);
    label(Status,L"");
    add(Reload,L"BUTTON",L"Перечитать",BS_OWNERDRAW|WS_TABSTOP);
    add(Apply,L"BUTTON",L"Применить в Windows",BS_OWNERDRAW|WS_TABSTOP);
    return std::all_of(p.controls.begin(),p.controls.end(),[](HWND h){return h!=nullptr;});
}

void setFonts(Page& p,UINT dpi) {
    p.dpi=dpi;
    HFONT old=p.font,oldTitle=p.titleFont;
    auto make=[&](int height,int weight) {
        return CreateFontW(-p.px(height),0,0,0,weight,FALSE,FALSE,FALSE,DEFAULT_CHARSET,
            OUT_DEFAULT_PRECIS,CLIP_DEFAULT_PRECIS,CLEARTYPE_QUALITY,DEFAULT_PITCH,L"Segoe UI");
    };
    p.font=make(14,FW_NORMAL); p.titleFont=make(19,FW_SEMIBOLD);
    for (int i=LeftTitle;i<ControlEnd;++i)
        SendMessageW(p.at(i),WM_SETFONT,reinterpret_cast<WPARAM>(
            i==LeftTitle || i==RightTitle ? p.titleFont : p.font),FALSE);
    if (old) DeleteObject(old);
    if (oldTitle) DeleteObject(oldTitle);
}

void layout(Page& p) {
    if (p.layingOut || !p.at(Apply)) return;
    p.layingOut=true;
    UINT dpi=windowDpi(p.hwnd);
    if (dpi!=p.dpi) setFonts(p,dpi);
    RECT rc{},outer{}; GetClientRect(p.hwnd,&rc); GetWindowRect(p.hwnd,&outer);
    bool two=p.logical(outer.right-outer.left)>=736;
    constexpr int gap=14, margin=12, height=351;
    int footer=margin+height+gap+(two ? 0 : height+gap);
    int fullHeight=footer+80;
    p.contentHeight=p.px(fullHeight);
    SCROLLINFO info{sizeof(info),SIF_RANGE|SIF_PAGE|SIF_POS,0,p.contentHeight-1,
        static_cast<UINT>(rc.bottom),p.scroll,0};
    SetScrollInfo(p.hwnd,SB_VERT,&info,TRUE);
    p.scroll=GetScrollPos(p.hwnd,SB_VERT);
    GetClientRect(p.hwnd,&rc);
    int w=p.logical(rc.right), span=std::max(1,w-margin*2);
    int first=two ? (span-gap)/2 : span;
    int left=margin, right=two ? left+first+gap : margin;
    int top=margin, rightTop=two ? top : top+height+gap;
    int second=two ? span-first-gap : span;
    auto rect=[&](int x,int y,int width,int h)->RECT {
        return {p.px(x),p.px(y)-p.scroll,p.px(x+width),p.px(y+h)-p.scroll};
    };
    auto pos=[&](int id,int x,int y,int width,int h) {
        RECT r=rect(x,y,std::max(1,width),h);
        MoveWindow(p.at(id),r.left,r.top,r.right-r.left,r.bottom-r.top,TRUE);
    };
    p.cards[0]=rect(left,top,first,height); p.cards[1]=rect(right,rightTop,second,height);
    constexpr int pad=18;
    int x=left+pad, y=top+12, cw=first-2*pad;
    pos(LeftTitle,x,y,cw,28);
    pos(SpeedLabel,x,y+43,cw-76,22); pos(SpeedValue,x+cw-76,y+43,76,22);
    pos(SpeedSlider,x,y+69,cw,26);
    pos(PrecisionCheck,x,y+105,cw,26); pos(SnapCheck,x,y+138,cw,26);
    pos(VanishCheck,x,y+171,cw,26); pos(SonarCheck,x,y+204,cw,26);
    pos(TrailsCheck,x,y+251,cw,26); pos(TrailsLabel,x,y+289,cw-82,26);
    pos(TrailsEdit,x+cw-78,y+287,78,28);
    x=right+pad; y=rightTop+12; cw=second-2*pad;
    pos(RightTitle,x,y,cw,28);
    pos(SwapLabel,x,y+47,cw-109,24); pos(SwapCombo,x+cw-105,y+45,105,96);
    pos(LinesLabel,x,y+92,cw-87,25); pos(LinesEdit,x+cw-78,y+90,78,28);
    pos(PageCheck,x,y+128,cw,26);
    pos(CharsLabel,x,y+175,cw-82,26); pos(CharsEdit,x+cw-78,y+173,78,28);
    pos(RouteLabel,x,y+216,cw,22); pos(RouteCombo,x,y+243,cw,108);
    pos(More,x,y+294,cw,31);
    pos(Status,margin,footer,span,22);
    int buttonWidth=std::min(172,std::max(126,span-118));
    pos(Reload,w-margin-buttonWidth-8-106,footer+34,106,34);
    pos(Apply,w-margin-buttonWidth,footer+34,buttonWidth,34);
    InvalidateRect(p.hwnd,nullptr,TRUE);
    p.layingOut=false;
}

void enabledStates(Page& p) {
    for (int i=0;i<Count;++i) EnableWindow(p.at(fieldControl[i]),p.available[i]);
    EnableWindow(p.at(PageCheck),p.available[Lines]);
    EnableWindow(p.at(LinesEdit),p.available[Lines] && !p.checked(PageCheck));
    EnableWindow(p.at(TrailsEdit),p.available[Trails] && p.checked(TrailsCheck));
}

void showSpeed(Page& p) {
    int speed=static_cast<int>(SendMessageW(p.at(SpeedSlider),TBM_GETPOS,0,0));
    SetWindowTextW(p.at(SpeedValue),(std::to_wstring(speed)+L" / 20").c_str());
}

void loadPage(Page& p,const wchar_t* status=nullptr) {
    p.updating=true;
    int missing=0;
    for (int i=0;i<Count;++i) {
        p.available[i]=readField(static_cast<Field>(i),p.original[i]);
        if (!p.available[i]) ++missing;
    }
    auto val=[&](Field f){return p.original[f];};
    SendMessageW(p.at(SpeedSlider),TBM_SETPOS,TRUE,val(Speed));
    showSpeed(p);
    if (!p.available[Speed]) SetWindowTextW(p.at(SpeedValue),L"—");
    for (Field f:{Precision,Snap,Vanish,Sonar,Trails}) p.check(fieldControl[f],p.available[f] && val(f)!=0);
    auto number=[&](int id,DWORD value,bool valid) {
        SetWindowTextW(p.at(id),valid ? std::to_wstring(value).c_str() : L"");
    };
    number(TrailsEdit,val(Trails) ? val(Trails) : 3,p.available[Trails]);
    p.check(PageCheck,p.available[Lines] && val(Lines)==WHEEL_PAGESCROLL);
    number(LinesEdit,val(Lines)==WHEEL_PAGESCROLL ? 3 : val(Lines),p.available[Lines]);
    number(CharsEdit,val(Chars),p.available[Chars]);
    for (Field f:{Swap,Route})
        SendMessageW(p.at(fieldControl[f]),CB_SETCURSEL,p.available[f] ? static_cast<int>(val(f)) : -1,0);
    enabledStates(p);
    EnableWindow(p.at(Apply),FALSE);
    if (missing) p.status(L"Часть параметров недоступна в этой системе.");
    else p.status(status ? status : L"Параметры текущего пользователя Windows.");
    p.updating=false;
}

bool readNumber(HWND field,DWORD low,DWORD high,DWORD& value) {
    wchar_t text[12]{};
    int length=GetWindowTextW(field,text,12);
    if (length<1 || length>10) return false;
    std::uint64_t parsed=0;
    for (int i=0;i<length;++i) {
        if (text[i]<L'0' || text[i]>L'9') return false;
        parsed=10*parsed+static_cast<unsigned>(text[i]-L'0');
    }
    if (parsed<low || parsed>high) return false;
    value=static_cast<DWORD>(parsed);
    return true;
}

bool draft(Page& p,std::array<DWORD,Count>& values,int& invalid) {
    values=p.original;
    for (int i=0;i<Count;++i) {
        if (!p.available[i]) continue;
        int ctrl=fieldControl[i];
        if (i==Speed) values[i]=static_cast<DWORD>(SendMessageW(p.at(ctrl),TBM_GETPOS,0,0));
        else if (i==Swap || i==Route) values[i]=static_cast<DWORD>(SendMessageW(p.at(ctrl),CB_GETCURSEL,0,0));
        else if (i==Lines && p.checked(PageCheck)) values[i]=WHEEL_PAGESCROLL;
        else if (i==Trails && !p.checked(TrailsCheck)) values[i]=0;
        else if (i==Lines || i==Chars || i==Trails) {
            if (i==Trails) ctrl=TrailsEdit;
            DWORD min=i==Trails ? 2 : 0;
            // The standard Windows slider covers 2–7 trails. Preserve larger existing values.
            DWORD max=i==Trails ? std::max<DWORD>(7,p.original[Trails]) :
                (i==Lines ? WHEEL_PAGESCROLL-1u : std::numeric_limits<DWORD>::max());
            if (!readNumber(p.at(ctrl),min,max,values[i])) {invalid=ctrl;return false;}
        } else values[i]=p.checked(ctrl);
    }
    return true;
}

void changed(Page& p) {
    if (p.updating) return;
    bool enable=p.available[Lines] && !p.checked(PageCheck);
    EnableWindow(p.at(LinesEdit),enable);
    EnableWindow(p.at(TrailsEdit),p.available[Trails] && p.checked(TrailsCheck));
    std::array<DWORD,Count> values{};
    int invalid=0;
    bool valid=draft(p,values,invalid);
    bool dirty=!valid || values!=p.original;
    EnableWindow(p.at(Apply),dirty);
    p.status(dirty ? L"Изменения ожидают применения." : L"Параметры текущего пользователя Windows.");
}

void applyPage(Page& p) {
    std::array<DWORD,Count> values{};
    int invalid=0;
    if (!draft(p,values,invalid)) {
        std::wstring error;
        if (invalid==TrailsEdit)
            error=L"Допустимая длина следа — от 2 до "+std::to_wstring(std::max<DWORD>(7,p.original[Trails]))+L".";
        else error=L"Введите целое число от 0 до "+std::to_wstring(invalid==LinesEdit ?
            WHEEL_PAGESCROLL-1u : std::numeric_limits<DWORD>::max())+L".";
        MessageBoxW(p.hwnd,error.c_str(),L"Параметры Windows",MB_OK|MB_ICONINFORMATION);
        SetFocus(p.at(invalid));
        SendMessageW(p.at(invalid),EM_SETSEL,0,-1);
        return;
    }
    std::wstring failed;
    int count=0;
    for (int i=0;i<Count;++i) {
        if (!p.available[i] || values[i]==p.original[i]) continue;
        Field f=static_cast<Field>(i);
        DWORD actual=0;
        SetLastError(ERROR_SUCCESS);
        bool ok=readField(f,actual);
        if (ok && actual!=values[i]) {
            SetLastError(ERROR_SUCCESS);
            ok=writeField(f,values[i]);
            if (ok) ok=readField(f,actual) && actual==values[i];
        }
        if (ok) {p.original[i]=values[i];++count;continue;}
        DWORD code=GetLastError();
        failed+=L"\n• "; failed+=names[i];
        if (code) failed+=L" (код "+std::to_wstring(code)+L")";
    }
    if (failed.empty()) loadPage(p,count ? L"Windows подтвердила изменения." : L"Параметры уже применены.");
    else {
        changed(p);
        p.status(L"Windows не подтвердила часть изменений.");
        std::wstring message=L"Следующие изменения не подтверждены системой. Их можно повторить.\n"+failed;
        MessageBoxW(p.hwnd,message.c_str(),L"Параметры Windows",MB_ICONWARNING|MB_OK);
    }
}

void drawButton(Page& p,const DRAWITEMSTRUCT& d) {
    bool primary=d.CtlID==Apply, enabled=(d.itemState&ODS_DISABLED)==0, pressed=(d.itemState&ODS_SELECTED)!=0;
    RECT rc=d.rcItem;
    COLORREF color=primary && enabled ? accent : edge;
    fill(d.hDC,rc,color);
    InflateRect(&rc,-p.px(1),-p.px(1));
    fill(d.hDC,rc,primary && enabled ? (pressed ? RGB(56,181,36) : accent) : (pressed ? edge : input));
    SetBkMode(d.hDC,TRANSPARENT);
    SetTextColor(d.hDC,!enabled ? muted : primary ? panel : foreground);
    HFONT old=static_cast<HFONT>(SelectObject(d.hDC,p.font));
    wchar_t title[100]{};
    GetWindowTextW(d.hwndItem,title,100);
    DrawTextW(d.hDC,title,-1,&rc,DT_SINGLELINE|DT_VCENTER|DT_CENTER|DT_NOPREFIX);
    if (d.itemState&ODS_FOCUS) {InflateRect(&rc,-p.px(3),-p.px(3)); DrawFocusRect(d.hDC,&rc);}
    SelectObject(d.hDC,old);
}

void scrollTo(Page& p,int position) {
    SetScrollPos(p.hwnd,SB_VERT,position,TRUE);
    int newPos=GetScrollPos(p.hwnd,SB_VERT);
    if (newPos!=p.scroll) {p.scroll=newPos;layout(p);}
}

LRESULT CALLBACK pageProc(HWND hwnd,UINT msg,WPARAM wp,LPARAM lp) {
    auto* p=reinterpret_cast<Page*>(GetWindowLongPtrW(hwnd,GWLP_USERDATA));
    if (msg==WM_NCCREATE) {
        auto cs=reinterpret_cast<CREATESTRUCTW*>(lp);
        p=new(std::nothrow) Page;
        if (!p) return FALSE;
        p->hwnd=hwnd; p->instance=cs->hInstance;
        SetWindowLongPtrW(hwnd,GWLP_USERDATA,reinterpret_cast<LONG_PTR>(p));
    }
    if (!p) return DefWindowProcW(hwnd,msg,wp,lp);
    switch (msg) {
        case WM_CREATE:
            p->bgBrush=CreateSolidBrush(background); p->panelBrush=CreateSolidBrush(panel); p->inputBrush=CreateSolidBrush(input);
            p->updating=true;
            if (!createControls(*p)) return -1;
            setFonts(*p,windowDpi(hwnd));
            loadPage(*p); layout(*p);
            return 0;
        case WM_DPICHANGED_AFTERPARENT:
        case WM_SIZE: layout(*p);return 0;
        case WM_ERASEBKGND: return 1;
        case WM_PAINT: {
            PAINTSTRUCT ps{};
            HDC dc=BeginPaint(hwnd,&ps);
            FillRect(dc,&ps.rcPaint,p->bgBrush);
            for (auto& c:p->cards) FillRect(dc,&c,p->panelBrush);
            EndPaint(hwnd,&ps);
            return 0;
        }
        case WM_CTLCOLORBTN: case WM_CTLCOLORSTATIC: case WM_CTLCOLOREDIT: case WM_CTLCOLORLISTBOX: {
            HDC dc=reinterpret_cast<HDC>(wp);
            int id=GetDlgCtrlID(reinterpret_cast<HWND>(lp));
            bool status=id==Status, box=msg==WM_CTLCOLOREDIT || msg==WM_CTLCOLORLISTBOX ||
                id==TrailsEdit || id==LinesEdit || id==CharsEdit;
            COLORREF bg=status ? background : box ? input : panel;
            SetBkColor(dc,bg);
            SetTextColor(dc,status ? muted : (id==LeftTitle || id==RightTitle) ? accent : foreground);
            return reinterpret_cast<LRESULT>(status ? p->bgBrush : box ? p->inputBrush : p->panelBrush);
        }
        case WM_DRAWITEM: drawButton(*p,*reinterpret_cast<DRAWITEMSTRUCT*>(lp));return TRUE;
        case WM_NOTIFY: {
            auto* hdr=reinterpret_cast<NMHDR*>(lp);
            if (hdr->idFrom!=SpeedSlider || hdr->code!=NM_CUSTOMDRAW) break;
            auto* cd=reinterpret_cast<NMCUSTOMDRAW*>(lp);
            if (cd->dwDrawStage==CDDS_PREPAINT) {
                RECT rc{}; GetClientRect(hdr->hwndFrom,&rc);
                FillRect(cd->hdc,&rc,p->panelBrush);
                RECT thumb{}; SendMessageW(hdr->hwndFrom,TBM_GETTHUMBRECT,0,reinterpret_cast<LPARAM>(&thumb));
                int center=(thumb.left+thumb.right)/2, y=(rc.bottom-rc.top)/2;
                RECT bar{p->px(5),y-p->px(1),rc.right-p->px(5),y+p->px(2)};
                fill(cd->hdc,bar,edge); bar.right=center;fill(cd->hdc,bar,accent);
                auto previous=SelectObject(cd->hdc,GetStockObject(DC_BRUSH));
                auto pen=SelectObject(cd->hdc,GetStockObject(NULL_PEN));
                SetDCBrushColor(cd->hdc,IsWindowEnabled(hdr->hwndFrom) ? accent : muted);
                Ellipse(cd->hdc,center-p->px(6),y-p->px(6),center+p->px(7),y+p->px(7));
                SelectObject(cd->hdc,pen);SelectObject(cd->hdc,previous);
                if (GetFocus()==hdr->hwndFrom) DrawFocusRect(cd->hdc,&rc);
                return CDRF_SKIPDEFAULT;
            }
            break;
        }
        case WM_COMMAND: {
            int id=LOWORD(wp), code=HIWORD(wp);
            if (p->updating) return 0;
            if (id==Apply && code==BN_CLICKED) applyPage(*p);
            else if (id==Reload && code==BN_CLICKED) loadPage(*p,L"Текущие параметры перечитаны.");
            else if (id==More && code==BN_CLICKED) {
                wchar_t directory[MAX_PATH]{};
                UINT len=GetSystemDirectoryW(directory,MAX_PATH);
                std::wstring path=std::wstring(directory)+L"\\control.exe";
                if (!len || len>=MAX_PATH || reinterpret_cast<INT_PTR>(ShellExecuteW(hwnd,L"open",path.c_str(),L"main.cpl",nullptr,SW_SHOWNORMAL))<=32)
                    MessageBoxW(hwnd,L"Не удалось открыть системные свойства мыши.",L"Параметры Windows",MB_OK|MB_ICONWARNING);
            } else if (code==BN_CLICKED || code==CBN_SELCHANGE || code==EN_CHANGE) changed(*p);
            return 0;
        }
        case WM_HSCROLL:
            if (reinterpret_cast<HWND>(lp)==p->at(SpeedSlider)) {showSpeed(*p);changed(*p);}
            return 0;
        case WM_VSCROLL: {
            SCROLLINFO s{sizeof(s),SIF_ALL,0,0,0,0,0};
            GetScrollInfo(hwnd,SB_VERT,&s);
            int pos=p->scroll;
            switch (LOWORD(wp)) {
                case SB_LINEUP:pos-=p->px(24);break;
                case SB_LINEDOWN:pos+=p->px(24);break;
                case SB_PAGEUP:pos-=static_cast<int>(s.nPage);break;
                case SB_PAGEDOWN:pos+=static_cast<int>(s.nPage);break;
                case SB_THUMBTRACK:case SB_THUMBPOSITION:pos=s.nTrackPos;break;
                case SB_TOP:pos=0;break;
                case SB_BOTTOM:pos=s.nMax;break;
                default:return 0;
            }
            scrollTo(*p,pos);return 0;
        }
        case WM_MOUSEWHEEL: scrollTo(*p,p->scroll-MulDiv(GET_WHEEL_DELTA_WPARAM(wp),p->px(45),WHEEL_DELTA));return 0;
        case WM_NCDESTROY:
            SetWindowLongPtrW(hwnd,GWLP_USERDATA,0);
            DeleteObject(p->font); DeleteObject(p->titleFont);
            DeleteObject(p->bgBrush); DeleteObject(p->panelBrush); DeleteObject(p->inputBrush);
            delete p;break;
    }
    return DefWindowProcW(hwnd,msg,wp,lp);
}
} // namespace

HWND CreateWindowsTab(HWND parent,HINSTANCE instance) {
    INITCOMMONCONTROLSEX cc{sizeof(cc),ICC_BAR_CLASSES};
    InitCommonControlsEx(&cc);
    WNDCLASSW wc{};
    wc.lpfnWndProc=pageProc; wc.hInstance=instance; wc.hCursor=LoadCursorW(nullptr,IDC_ARROW); wc.lpszClassName=className;
    if (!RegisterClassW(&wc) && GetLastError()!=ERROR_CLASS_ALREADY_EXISTS) return nullptr;
    return CreateWindowExW(WS_EX_CONTROLPARENT,className,L"Параметры мыши Windows",
        WS_CHILD|WS_CLIPCHILDREN|WS_CLIPSIBLINGS|WS_VSCROLL,0,0,1,1,parent,nullptr,instance,nullptr);
}

void ResizeWindowsTab(HWND tab,int x,int y,int width,int height) {
    if (tab) MoveWindow(tab,x,y,width,height,TRUE);
}

void RefreshWindowsTab(HWND tab) {
    auto p=reinterpret_cast<Page*>(GetWindowLongPtrW(tab,GWLP_USERDATA));
    if (p) loadPage(*p);
}
