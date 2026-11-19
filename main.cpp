#include <windows.h>
#include <windowsx.h>
#include <commdlg.h>
#include <commctrl.h>
#include <shellapi.h>
#include <dwmapi.h>
#include <process.h>
#include "panels.h"
#include "factory_reset.h"
#include "windows_tab.h"
#include "device_pages.h"
#include <algorithm>
#include <array>
#include <memory>
#include <string>
#include <vector>

namespace {
using viper::Result;
constexpr COLORREF board=RGB(32,34,32), strip=RGB(23,26,23), green=RGB(68,214,44),
    white=RGB(242,245,241), gray=RGB(177,186,175);
const wchar_t* names[]={L"Настройка",L"Производительность",L"Подсветка",L"Калибровка",L"Память",L"Windows"};
enum Tab{Setup,Performance,Lighting,Calibration,Memory,Windows,TabCount};
enum class Op {Initial,ViewMemory,GetPerformance,GetBrightness,GetCalibration,SetPerformance,SetLighting,SetCalibration,SetLive,Restore,Format};
const UINT StartMessage=WM_APP+11, DoneMessage=WM_APP+12;
constexpr int Nav=220,Secondary=250,Primary=251;
struct App {
    HWND h{},sub[TabCount]{},tabs[TabCount]{},left{},right{};
    int dpi=96, tab=Performance; bool busy=false,closing=false,online=false;
    std::wstring status=L"Подключение…", path;
    MouseProfile profile;MouseSnapshot snapshot;
    HFONT title{},font{},small{}; HBRUSH background=CreateSolidBrush(board), chrome=CreateSolidBrush(strip);
    ~App(){for(auto f:{title,font,small})DeleteObject(f);DeleteObject(background);DeleteObject(chrome);}
    int s(int n)const{return MulDiv(n,dpi,96);}
};
struct Job{
    HWND h{}; Op op{};MouseProfile data; int x=0,y=0,brightness=0;MouseSnapshot snapshot;
    bool connected=false;Result result{false,{}};
};
HFONT font(int dpi,int px,int weight){return CreateFontW(-MulDiv(px,dpi,96),0,0,0,weight,0,0,0,DEFAULT_CHARSET,OUT_DEFAULT_PRECIS,CLIP_DEFAULT_PRECIS,CLEARTYPE_QUALITY,DEFAULT_PITCH,L"Segoe UI");}
void message(App& a,const std::wstring& t,UINT icon=MB_ICONINFORMATION){a.status=t;InvalidateRect(a.h,nullptr,FALSE);MessageBoxW(a.h,t.c_str(),L"Viper Control",MB_OK|icon);}
void fillEditors(App& a){SetProfileName(a.sub[Setup],a.profile.name);LoadDevicePage(a.sub[Performance],a.profile);LoadDevicePage(a.sub[Lighting],a.profile);SetCalibrationPage(a.sub[Calibration],a.profile.calibration);}
bool collect(App& a,MouseProfile& p,bool all){
    p.name=ProfileName(a.sub[Setup]);std::wstring error;
    if((all||a.tab==Performance)&&!ReadDevicePage(a.sub[Performance],p,error)){message(a,error,MB_ICONWARNING);return false;}
    if((all||a.tab==Lighting)&&!ReadDevicePage(a.sub[Lighting],p,error)){message(a,error,MB_ICONWARNING);return false;}
    p.calibration=GetCalibrationPage(a.sub[Calibration]);return true;
}
void updateMemory(App& a,bool copy){
    MouseProfile draft=a.profile; std::wstring error;
    bool valid=ReadDevicePage(a.sub[Performance],draft,error);
    ShowMemory(a.sub[Memory],a.snapshot,valid?&draft.performance:nullptr,copy);
}
void selectTab(App& a,int tab){
    a.tab=tab;
    for(int i=0;i<TabCount;i++){ShowWindow(a.sub[i],i==tab?SW_SHOW:SW_HIDE);InvalidateRect(a.tabs[i],nullptr,TRUE);}
    if(tab==Memory)updateMemory(a,false);
    static const wchar_t* primary[]={L"Сохранить файл…",L"Записать в мышь",L"Применить подсветку",L"Применить калибровку",L"Прочитать с мыши",L""};
    static const wchar_t* secondary[]={L"Открыть файл…",L"Прочитать с мыши",L"Считать яркость",L"Прочитать с мыши",L"",L""};
    SetWindowTextW(a.right,primary[tab]);SetWindowTextW(a.left,secondary[tab]);
    ShowWindow(a.right,tab!=Windows?SW_SHOW:SW_HIDE);ShowWindow(a.left,tab!=Windows&&tab!=Memory?SW_SHOW:SW_HIDE);
    InvalidateRect(a.h,nullptr,FALSE);
}
HWND button(App& a,int id,const wchar_t* name){
    HWND h=CreateWindowExW(0,L"BUTTON",name,WS_CHILD|WS_VISIBLE|WS_TABSTOP|BS_OWNERDRAW,0,0,0,0,a.h,reinterpret_cast<HMENU>(static_cast<INT_PTR>(id)),GetModuleHandleW(nullptr),nullptr);
    SendMessageW(h,WM_SETFONT,reinterpret_cast<WPARAM>(a.font),FALSE);return h;
}
void layout(App& a){
    RECT r;GetClientRect(a.h,&r);int top=a.s(101),w=r.right,foot=a.s(90);
    auto dy=[&](int n){return a.s(n);};
    int start=dy(20),usable=w-dy(40);int units[]={105,201,109,135,96,104};
    int cumulative=0;
    for(int i=0;i<TabCount;i++){
        int from=start+MulDiv(usable,cumulative,750);cumulative+=units[i];
        int to=start+MulDiv(usable,cumulative,750);
        MoveWindow(a.tabs[i],from,dy(57),to-from-dy(4),dy(34),TRUE);
        int height=std::max(1,(int)r.bottom-top-(i==Windows?0:foot));
        if(i==Windows)ResizeWindowsTab(a.sub[i],0,top,w,height);
        else MoveWindow(a.sub[i],0,top,w,height,TRUE);
    }
    MoveWindow(a.right,w-dy(247),r.bottom-dy(44),dy(225),dy(33),TRUE);
    MoveWindow(a.left,w-dy(456),r.bottom-dy(44),dy(198),dy(33),TRUE);
    InvalidateRect(a.h,nullptr,TRUE);
}
void draw(App& a,const DRAWITEMSTRUCT& d){
    int id=GetDlgCtrlID(d.hwndItem);bool nav=id>=Nav&&id<Nav+TabCount,active=(nav&&id==Nav+a.tab)||id==Primary;
    COLORREF bg=active?green:nav?strip:RGB(53,59,52);
    if(d.itemState&ODS_SELECTED)bg=active?RGB(60,184,45):RGB(63,71,63);
    if(d.itemState&ODS_DISABLED)bg=RGB(60,65,59);
    HBRUSH b=CreateSolidBrush(bg);FillRect(d.hDC,&d.rcItem,b);DeleteObject(b);
    SelectObject(d.hDC,a.font);SetBkMode(d.hDC,TRANSPARENT);SetTextColor(d.hDC,active?RGB(15,29,12):white);
    wchar_t t[100]{};GetWindowTextW(d.hwndItem,t,100);RECT pos=d.rcItem;DrawTextW(d.hDC,t,-1,&pos,DT_SINGLELINE|DT_CENTER|DT_VCENTER|DT_NOPREFIX);
    if(d.itemState&ODS_FOCUS){InflateRect(&pos,-3,-3);DrawFocusRect(d.hDC,&pos);}
}
void paint(App& a){
    PAINTSTRUCT ps;HDC dc=BeginPaint(a.h,&ps);RECT r;GetClientRect(a.h,&r);
    FillRect(dc,&ps.rcPaint,a.background);RECT header{0,0,r.right,a.s(100)};FillRect(dc,&header,a.chrome);
    auto drawText=[&](std::wstring t,HFONT f,COLORREF c,RECT rect,UINT mode){SelectObject(dc,f);SetBkMode(dc,TRANSPARENT);SetTextColor(dc,c);DrawTextW(dc,t.c_str(),-1,&rect,mode|DT_NOPREFIX);};
    if(HICON ico=(HICON)GetClassLongPtrW(a.h,GCLP_HICON))DrawIconEx(dc,a.s(21),a.s(12),ico,a.s(30),a.s(30),0,nullptr,DI_NORMAL);
    drawText(L"VIPER 8KHz",a.title,white,{a.s(62),a.s(6),a.s(280),a.s(49)},DT_VCENTER|DT_SINGLELINE);
    drawText(L"Viper Control",a.small,gray,{a.s(251),a.s(10),a.s(425),a.s(48)},DT_VCENTER|DT_SINGLELINE);
    auto conn=a.busy?L"Обмен с мышью…":a.online?L"Мышь подключена":L"Мышь недоступна";
    drawText(conn,a.font,a.online?green:gray,{r.right-a.s(258),a.s(6),r.right-a.s(23),a.s(51)},DT_RIGHT|DT_SINGLELINE|DT_VCENTER);
    if(a.tab!=Windows){
        RECT footer{0,r.bottom-a.s(90),r.right,r.bottom};FillRect(dc,&footer,a.chrome);
        drawText(a.status,a.small,gray,{a.s(23),r.bottom-a.s(83),r.right-a.s(22),r.bottom-a.s(45)},DT_WORDBREAK|DT_END_ELLIPSIS);
        std::wstring name=ProfileName(a.sub[Setup]);
        drawText(L"Профиль  ·  "+name,a.font,gray,{a.s(22),r.bottom-a.s(45),r.right-a.s(465),r.bottom-a.s(10)},DT_SINGLELINE|DT_VCENTER|DT_END_ELLIPSIS);
    }
    EndPaint(a.h,&ps);
}
void enable(App& a,bool on){
    for(HWND h:a.tabs)EnableWindow(h,on);
    for(HWND h:a.sub)EnableWindow(h,on);
    EnableWindow(a.right,on);EnableWindow(a.left,on);InvalidateRect(a.h,nullptr,TRUE);
}
Result snapshot(Job& j){
    viper::Performance p;int x=0,y=0;
    auto stages=viper::readPerformance(p);
    if(stages.ok){j.snapshot.stages=p;j.snapshot.rateKnown=true;}
    else {
        auto table=viper::readStages(p);
        if(table.ok)j.snapshot.stages=p;
    }
    auto current=viper::readCurrentDpi(x,y);
    if(current.ok)j.snapshot.current=std::make_pair(x,y);
    if(j.op==Op::ViewMemory||j.op==Op::Format){
        std::array<bool,6> slots{};
        if(viper::readOnboardSlots(slots).ok)j.snapshot.slots=slots;
    }
    if(!stages.ok)return {false,(j.snapshot.stages?std::wstring(L"Ступени DPI считаны. "):std::wstring())+stages.message+(current.ok?L" Текущий DPI считан.":L"")};
    if(!current.ok)return {false,L"Ступени считаны. Текущий DPI: "+current.message};
    return {true,L"Считаны все активные ступени, частота опроса и текущий DPI сенсора."};
}
unsigned __stdcall worker(void* raw){
    std::unique_ptr<Job> p(static_cast<Job*>(raw));auto& j=*p;
    j.result=viper::probe();j.connected=j.result.ok;
    if(j.connected){
        switch(j.op){
            case Op::Initial:case Op::ViewMemory:case Op::GetPerformance:j.result=snapshot(j);break;
            case Op::GetBrightness:j.result=viper::readBrightness(j.brightness);break;
            case Op::GetCalibration:j.result=viper::readCalibration(j.data.calibration);break;
            case Op::SetPerformance:j.result=viper::writePerformance(j.data.performance);break;
            case Op::SetLighting:j.result=viper::writeLighting(j.data.lighting);break;
            case Op::SetCalibration:j.result=viper::applyCalibration(j.data.calibration);break;
            case Op::SetLive:j.result=viper::writeCurrentDpi(j.x,j.y);break;
            case Op::Format:j.result=viper::formatOnboardMemory();break;
            case Op::Restore:{
                viper::Performance factory;j.result=viper::writeStages(factory);
                break;
            }
        }
        if(j.op==Op::SetPerformance||j.op==Op::SetLive||j.op==Op::Restore||j.op==Op::Format){
            auto read=snapshot(j);
            if(!read.ok)j.result={false,j.result.message+L" Повторное чтение: "+read.message};
        }
    }
    Job* payload=p.release();if(!PostMessageW(j.h,DoneMessage,0,reinterpret_cast<LPARAM>(payload)))delete payload;
    return 0;
}
void start(App& a,Op op){
    if(a.busy)return;
    auto job=std::make_unique<Job>();job->h=a.h;job->op=op;job->data=a.profile;
    if((op==Op::SetPerformance||op==Op::SetLighting||op==Op::SetCalibration)&&!collect(a,job->data,false))return;
    if(op==Op::SetLive&&!GetCurrentFields(a.sub[Memory],job->x,job->y)){
        message(a,L"Введите DPI для обеих осей от 100 до 20000.",MB_ICONWARNING);return;
    }
    a.busy=true;a.status=L"Обмен с мышью…";enable(a,false);
    Job* payload=job.release();
    uintptr_t thread=_beginthreadex(nullptr,0,worker,payload,0,nullptr);
    if(thread)CloseHandle(reinterpret_cast<HANDLE>(thread));
    else{delete payload;a.busy=false;enable(a,true);message(a,L"Не удалось начать обмен с мышью.",MB_ICONERROR);}
}
void finish(App& a,std::unique_ptr<Job> job){
    a.busy=false;enable(a,true);a.online=job->connected;a.status=job->result.message;
    auto op=job->op;
    if(!a.online||op==Op::ViewMemory||op==Op::Initial||op==Op::GetPerformance||op==Op::SetLive||op==Op::SetPerformance||op==Op::Restore||op==Op::Format){
        a.snapshot=job->snapshot;
        if(a.snapshot.stages&&(op==Op::Initial||op==Op::GetPerformance||op==Op::SetPerformance||op==Op::Restore)){
            int previousHz=a.profile.performance.hz;
            a.profile.performance=*a.snapshot.stages;
            if(!a.snapshot.rateKnown)a.profile.performance.hz=previousHz;
            LoadDevicePage(a.sub[Performance],a.profile);
        }
        updateMemory(a,true);
    }
    if(job->result.ok){
        if(op==Op::GetBrightness){
            // Keep any edited effect and colours while replacing only brightness.
            MouseProfile p=a.profile;std::wstring error;
            if(ReadDevicePage(a.sub[Lighting],p,error)){p.lighting.brightness=job->brightness;a.profile.lighting=p.lighting;LoadDevicePage(a.sub[Lighting],p);}
            a.status=L"Яркость с мыши: "+std::to_wstring(job->brightness)+L"%. Эффект и цвета взяты из редактора.";
        }
        if(op==Op::GetCalibration){a.profile.calibration=job->data.calibration;SetCalibrationPage(a.sub[Calibration],a.profile.calibration);}
    }
    if(a.status.empty())a.status=job->result.ok?L"Мышь подтвердила операцию.":L"Операция не выполнена.";
    InvalidateRect(a.h,nullptr,FALSE);
    if(a.closing){DestroyWindow(a.h);return;}
    if(!job->result.ok&&op!=Op::Initial)message(a,a.status,MB_ICONWARNING);
}
void configFile(App& a,bool save){
    MouseProfile p=a.profile;
    if(save&&!collect(a,p,true))return;
    std::vector<wchar_t> file(32768);
    if(save){std::wstring defaultName=L"Viper8KHz.viper";if(!a.path.empty())defaultName=a.path;wcsncpy(file.data(),defaultName.c_str(),file.size()-1);}
    OPENFILENAMEW f{};f.lStructSize=sizeof(f);f.hwndOwner=a.h;f.lpstrFilter=L"Профиль Viper (*.viper)\0*.viper\0Все файлы\0*.*\0";f.lpstrFile=file.data();
    f.nMaxFile=static_cast<DWORD>(file.size());f.lpstrDefExt=L"viper";f.Flags=OFN_EXPLORER|OFN_NOCHANGEDIR|OFN_PATHMUSTEXIST|(save?OFN_OVERWRITEPROMPT:OFN_FILEMUSTEXIST);
    if(!(save?GetSaveFileNameW(&f):GetOpenFileNameW(&f))){if(CommDlgExtendedError())message(a,L"Не удалось открыть окно выбора файла.",MB_ICONERROR);return;}
    std::wstring error,path=file.data();bool ok=save?SaveMouseProfile(path,p,error):LoadMouseProfile(path,p,error);
    if(!ok){message(a,error,MB_ICONWARNING);return;}
    a.path=path;a.profile=p;
    if(!save){fillEditors(a);updateMemory(a,false);}
    a.status=(save?L"Профиль сохранён: ":L"Профиль открыт в редакторе: ")+path;InvalidateRect(a.h,nullptr,FALSE);
}
void command(App& a,int id){
    if(a.busy)return;
    if(id>=Nav&&id<Nav+TabCount){selectTab(a,id-Nav);return;}
    if(id==Primary){id=a.tab==Setup?CmdSave:a.tab==Memory?CmdRead:CmdApply;}
    if(id==Secondary){id=a.tab==Setup?CmdLoad:CmdRead;}
    if(id==CmdSave||id==CmdLoad){configFile(a,id==CmdSave);return;}
    if(id==CmdGuide){ShellExecuteW(a.h,L"open",L"https://mysupport.razer.com/app/answers/detail/a_id/14741",nullptr,nullptr,SW_SHOWNORMAL);return;}
    if(id==CmdSynapse){OpenSynapse(a.h);return;}
    if(id==CmdFormat){
        const wchar_t* warning=L"Очистить пользовательскую память подключённой Razer Viper 8KHz?\n\nПользовательские слоты 2–5 будут удалены. Базовый слот 1 остаётся. При форматировании также могут быть утрачены сохранённые макросы. Восстановить удалённые данные этой утилитой нельзя.\n\nДля резервной копии назначений кнопок и макросов сначала экспортируйте профиль через Synapse. Перед очисткой закройте Synapse.";
        if(MessageBoxW(a.h,warning,L"Очистка встроенной памяти",MB_YESNO|MB_ICONWARNING|MB_DEFBUTTON2)==IDYES)start(a,Op::Format);
        return;
    }
    if(id==CmdRestore){
        if(MessageBoxW(a.h,L"Записать на подключённую мышь заводские ступени 400, 800, 1600, 2400 и 3200 DPI? Активной станет третья ступень (1600 DPI). Прежняя таблица DPI будет заменена.\n\nТекущую таблицу можно предварительно считать на вкладке «Производительность» и сохранить в файл.",L"Восстановление ступеней DPI",MB_ICONWARNING|MB_YESNO|MB_DEFBUTTON2)==IDYES)start(a,Op::Restore);
        return;
    }
    if(id==CmdRead){
        if(a.tab==Windows){RefreshWindowsTab(a.sub[Windows]);return;}
        start(a,a.tab==Lighting?Op::GetBrightness:a.tab==Calibration?Op::GetCalibration:a.tab==Performance?Op::GetPerformance:Op::ViewMemory);return;
    }
    if(id==CmdSetCurrent){start(a,Op::SetLive);return;}
    if(id==CmdApply){start(a,a.tab==Performance?Op::SetPerformance:a.tab==Lighting?Op::SetLighting:Op::SetCalibration);}
}
LRESULT CALLBACK wnd(HWND h,UINT m,WPARAM w,LPARAM l){
    if(m==WM_NCCREATE){auto* c=(CREATESTRUCTW*)l;auto* a=(App*)c->lpCreateParams;a->h=h;SetWindowLongPtrW(h,GWLP_USERDATA,reinterpret_cast<LONG_PTR>(a));return DefWindowProcW(h,m,w,l);}
    auto* a=(App*)GetWindowLongPtrW(h,GWLP_USERDATA);if(!a)return DefWindowProcW(h,m,w,l);
    switch(m){
        case WM_CREATE:{
            a->dpi=GetDpiForWindow(h);if(!a->dpi)a->dpi=96;
            a->title=font(a->dpi,27,FW_SEMIBOLD);a->font=font(a->dpi,15,FW_SEMIBOLD);a->small=font(a->dpi,14,FW_NORMAL);
            auto inst=GetModuleHandleW(nullptr);
            for(int i=0;i<TabCount;i++)a->tabs[i]=button(*a,Nav+i,names[i]);
            a->sub[Setup]=CreatePanel(h,Panel::Setup);
            a->sub[Performance]=CreateDevicePage(h,inst,false);a->sub[Lighting]=CreateDevicePage(h,inst,true);
            a->sub[Calibration]=CreatePanel(h,Panel::Calibration);a->sub[Memory]=CreatePanel(h,Panel::Memory);a->sub[Windows]=CreateWindowsTab(h,inst);
            for(HWND page:a->sub)if(!page)return -1;
            a->left=button(*a,Secondary,L"");a->right=button(*a,Primary,L"");
            fillEditors(*a);selectTab(*a,Performance);PostMessageW(h,StartMessage,0,0);return 0;
        }
        case StartMessage:start(*a,Op::Initial);return 0;
        case DoneMessage:finish(*a,std::unique_ptr<Job>((Job*)l));return 0;
        case WM_GETMINMAXINFO:{auto* info=(MINMAXINFO*)l;info->ptMinTrackSize={a->s(830),a->s(525)};return 0;}
        case WM_SIZE:if(a->right)layout(*a);return 0;
        case WM_DRAWITEM:draw(*a,*reinterpret_cast<DRAWITEMSTRUCT*>(l));return TRUE;
        case WM_ERASEBKGND:return 1;
        case WM_PAINT:paint(*a);return 0;
        case WM_COMMAND:command(*a,LOWORD(w));return 0;
        case WM_CLOSE:if(a->busy){a->closing=true;a->status=L"Ожидание окончания операции перед выходом…";InvalidateRect(h,nullptr,FALSE);}else DestroyWindow(h);return 0;
        case WM_DESTROY:PostQuitMessage(0);return 0;
    }
    return DefWindowProcW(h,m,w,l);
}
}
int WINAPI wWinMain(HINSTANCE inst,HINSTANCE,PWSTR,int show){
    INITCOMMONCONTROLSEX controls{sizeof(controls),ICC_BAR_CLASSES|ICC_STANDARD_CLASSES|ICC_WIN95_CLASSES};InitCommonControlsEx(&controls);
    App app;auto dpi=GetDpiForSystem();if(dpi)app.dpi=dpi;
    WNDCLASSEXW c{};c.cbSize=sizeof(c);c.hInstance=inst;c.lpfnWndProc=wnd;c.lpszClassName=L"ViperControlWindow";c.hCursor=LoadCursorW(nullptr,IDC_ARROW);c.hIcon=LoadIconW(inst,MAKEINTRESOURCEW(101));c.hIconSm=c.hIcon;RegisterClassExW(&c);
    RECT r{};SystemParametersInfoW(SPI_GETWORKAREA,0,&r,0);
    int w=std::min<int>(app.s(1040),r.right-r.left),ht=std::min<int>(app.s(790),r.bottom-r.top);
    HWND h=CreateWindowExW(WS_EX_CONTROLPARENT,c.lpszClassName,L"Viper Control  ·  Razer Viper 8KHz",WS_OVERLAPPEDWINDOW|WS_CLIPCHILDREN,r.left+(r.right-r.left-w)/2,r.top+(r.bottom-r.top-ht)/2,w,ht,nullptr,nullptr,inst,&app);
    if(!h)return 1;
    BOOL dark=TRUE;DwmSetWindowAttribute(h,20,&dark,sizeof(dark));
    ShowWindow(h,show);UpdateWindow(h);
    ACCEL keys[]={{FCONTROL|FVIRTKEY,'S',CmdSave},{FCONTROL|FVIRTKEY,'O',CmdLoad},{FVIRTKEY,VK_F5,CmdRead}};
    HACCEL accel=CreateAcceleratorTableW(keys,3);MSG msg{};
    while(GetMessageW(&msg,nullptr,0,0)>0){
        if(!TranslateAcceleratorW(h,accel,&msg)&&!IsDialogMessageW(h,&msg)){TranslateMessage(&msg);DispatchMessageW(&msg);}
    }
    DestroyAcceleratorTable(accel);return static_cast<int>(msg.wParam);
}
