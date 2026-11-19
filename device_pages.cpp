#include "device_pages.h"

#include <commctrl.h>
#include <commdlg.h>
#include <windowsx.h>

#include <algorithm>
#include <array>
#include <cwchar>
#include <cstring>
#include <new>
#include <vector>

namespace {

constexpr wchar_t pageClass[] = L"ViperDeviceSettingsPage";
constexpr COLORREF background = RGB(32, 34, 32);
constexpr COLORREF panel = RGB(20, 23, 20);
constexpr COLORREF field = RGB(38, 42, 38);
constexpr COLORREF line = RGB(60, 66, 60);
constexpr COLORREF accent = RGB(68, 214, 44);
constexpr COLORREF words = RGB(236, 239, 235);
constexpr COLORREF muted = RGB(177, 186, 177);
constexpr COLORREF disabled = RGB(116, 125, 116);
constexpr int rates[] = {125, 500, 1000, 2000, 4000, 8000};
constexpr viper::Effect effects[] = {
    viper::Effect::Off, viper::Effect::Static, viper::Effect::Spectrum,
    viper::Effect::BreathOne, viper::Effect::BreathTwo,
    viper::Effect::BreathRandom, viper::Effect::Reactive,
};
constexpr const wchar_t* effectLabels[] = {
    L"Выключена", L"Постоянный цвет", L"Спектр", L"Дыхание · один цвет",
    L"Дыхание · два цвета", L"Дыхание · случайный цвет", L"Отклик на нажатие",
};
constexpr int contentHeight = 422;

enum ControlId {
    Count = 100, Axes, Rate, Interval, FirstStage = 140, FirstX = 150,
    FirstY = 160, FirstDpi = 170, Mode = 200, Brightness, BrightValue,
    Color1, Color2, Speed, Title1 = 300, Title2, Caption1, Caption2,
    Caption3, Caption4, Caption5, Caption6, Caption7
};

enum class TextRole { Normal, Heading, Caption };
struct Item {
    HWND hwnd;
    TextRole role;
};
struct Page {
    HWND hwnd = nullptr;
    bool lighting = false;
    bool loading = false;
    int active = 2;
    int dpi = 96;
    int scroll = 0;
    int left = 16;
    int width = 700;
    std::array<unsigned, 2> colors{};
    COLORREF customColors[16]{};
    HFONT font = nullptr, titleFont = nullptr;
    HBRUSH panelBrush = CreateSolidBrush(panel);
    HBRUSH fieldBrush = CreateSolidBrush(field);
    std::vector<Item> controls;
    ~Page() {
        DeleteObject(font); DeleteObject(titleFont);
        DeleteObject(panelBrush); DeleteObject(fieldBrush);
    }
    HWND control(int id) const { return GetDlgItem(hwnd, id); }
    int scale(int logical) const { return MulDiv(logical, dpi, 96); }
    int logical(int pixels) const { return MulDiv(pixels, 96, dpi); }
};

int windowDpi(HWND hwnd) {
    using GetDpi = UINT(WINAPI*)(HWND);
    static auto user32 = GetModuleHandleW(L"user32.dll");
    static GetDpi getDpi = [] {
        auto entry = GetProcAddress(user32, "GetDpiForWindow");
        GetDpi function = nullptr;
        static_assert(sizeof(function) == sizeof(entry));
        std::memcpy(&function, &entry, sizeof(function));
        return function;
    }();
    if (getDpi) return static_cast<int>(getDpi(hwnd));
    HDC dc = GetDC(hwnd);
    int dpi = GetDeviceCaps(dc, LOGPIXELSY);
    ReleaseDC(hwnd, dc);
    return dpi;
}

void fonts(Page& p) {
    HFONT oldNormal = p.font, oldTitle = p.titleFont;
    p.font = CreateFontW(-p.scale(15), 0, 0, 0, FW_NORMAL, FALSE, FALSE, FALSE,
        DEFAULT_CHARSET, OUT_DEFAULT_PRECIS, CLIP_DEFAULT_PRECIS, CLEARTYPE_QUALITY,
        DEFAULT_PITCH, L"Segoe UI");
    p.titleFont = CreateFontW(-p.scale(21), 0, 0, 0, FW_SEMIBOLD, FALSE, FALSE, FALSE,
        DEFAULT_CHARSET, OUT_DEFAULT_PRECIS, CLIP_DEFAULT_PRECIS, CLEARTYPE_QUALITY,
        DEFAULT_PITCH, L"Segoe UI");
    for (const auto& item : p.controls)
        SendMessageW(item.hwnd, WM_SETFONT,
            reinterpret_cast<WPARAM>(item.role == TextRole::Heading ? p.titleFont : p.font), TRUE);
    DeleteObject(oldNormal); DeleteObject(oldTitle);
}

HWND add(Page& p, int id, LPCWSTR cls, LPCWSTR text, DWORD style,
         TextRole role = TextRole::Normal, DWORD ex = 0) {
    HWND result = CreateWindowExW(ex, cls, text, WS_CHILD | WS_VISIBLE | style, 0, 0, 1, 1,
        p.hwnd, reinterpret_cast<HMENU>(static_cast<INT_PTR>(id)),
        reinterpret_cast<HINSTANCE>(GetWindowLongPtrW(p.hwnd, GWLP_HINSTANCE)), nullptr);
    p.controls.push_back({result, role});
    return result;
}
void label(Page& p, int id, LPCWSTR text, TextRole role = TextRole::Caption) {
    add(p, id, L"STATIC", text, SS_LEFT | SS_CENTERIMAGE | SS_NOPREFIX, role);
}
HWND combo(Page& p, int id, LPCWSTR name) {
    return add(p, id, L"COMBOBOX", name, WS_TABSTOP | WS_VSCROLL | CBS_DROPDOWNLIST | CBS_HASSTRINGS);
}
void addChoice(HWND list, const std::wstring& text) {
    SendMessageW(list, CB_ADDSTRING, 0, reinterpret_cast<LPARAM>(text.c_str()));
}
int selected(const Page& p, int id) {
    return static_cast<int>(SendMessageW(p.control(id), CB_GETCURSEL, 0, 0));
}
void select(const Page& p, int id, int ix) { SendMessageW(p.control(id), CB_SETCURSEL, ix, 0); }
void enable(const Page& p, int id, bool enabled) { EnableWindow(p.control(id), enabled); }
void setNumber(const Page& p, int id, int number) {
    SetDlgItemInt(p.hwnd, id, static_cast<UINT>(number), FALSE);
}
void slider(Page& p, int id, LPCWSTR name, int min, int max, int step, int page) {
    HWND track = add(p, id, TRACKBAR_CLASSW, name, WS_TABSTOP | TBS_HORZ | TBS_NOTICKS | TBS_BOTH);
    SendMessageW(track, TBM_SETRANGE, FALSE, MAKELPARAM(min, max));
    SendMessageW(track, TBM_SETLINESIZE, 0, step);
    SendMessageW(track, TBM_SETPAGESIZE, 0, page);
}

void makePerformance(Page& p) {
    label(p, Title1, L"Чувствительность", TextRole::Heading);
    label(p, Caption1, L"Число уровней");
    HWND count = combo(p, Count, L"Число уровней DPI");
    for (int i = 1; i <= 5; ++i) addChoice(count, std::to_wstring(i));
    add(p, Axes, L"BUTTON", L"Одинаковый DPI по осям X и Y", WS_TABSTOP | BS_AUTOCHECKBOX);
    label(p, Caption2, L"Активный");
    label(p, Caption3, L"DPI по X");
    label(p, Caption4, L"DPI по Y");
    label(p, Caption5, L"Чувствительность по X · 100–20 000 DPI");
    for (int i = 0; i < 5; ++i) {
        add(p, FirstStage + i, L"BUTTON", std::to_wstring(i + 1).c_str(),
            BS_RADIOBUTTON | WS_TABSTOP | (i == 0 ? WS_GROUP : 0));
        for (int axis : {FirstX, FirstY}) {
            HWND edit = add(p, axis + i, L"EDIT", L"", WS_TABSTOP | WS_BORDER |
                ES_NUMBER | ES_CENTER | ES_AUTOHSCROLL, TextRole::Normal);
            SendMessageW(edit, EM_SETLIMITTEXT, 5, 0);
        }
        auto name = L"DPI по X, уровень " + std::to_wstring(i + 1);
        slider(p, FirstDpi + i, name.c_str(), 100, 20000, 50, 500);
    }
    label(p, Title2, L"Частота опроса", TextRole::Heading);
    label(p, Caption6, L"Частота USB");
    HWND r = combo(p, Rate, L"Частота опроса USB");
    for (int hz : rates) addChoice(r, std::to_wstring(hz) + L" Гц");
    label(p, Interval, L"", TextRole::Normal);
}

void makeLighting(Page& p) {
    label(p, Title1, L"Яркость логотипа", TextRole::Heading);
    label(p, Caption1, L"Яркость");
    slider(p, Brightness, L"Яркость логотипа, проценты", 0, 100, 1, 10);
    label(p, BrightValue, L"", TextRole::Normal);
    label(p, Title2, L"Эффекты", TextRole::Heading);
    label(p, Caption2, L"Готовый эффект");
    HWND mode = combo(p, Mode, L"Готовый эффект подсветки");
    for (auto name : effectLabels) addChoice(mode, name);
    label(p, Caption3, L"Цвет 1");
    label(p, Caption4, L"Цвет 2");
    for (int id : {Color1, Color2})
        add(p, id, L"BUTTON", id == Color1 ? L"Выбрать первый цвет" : L"Выбрать второй цвет",
            WS_TABSTOP | BS_OWNERDRAW);
    label(p, Caption5, L"Длительность отклика");
    HWND speed = combo(p, Speed, L"Длительность отклика");
    for (auto name : {L"Короткая", L"Средняя", L"Длительная"}) addChoice(speed, name);
}

void place(Page& p, int id, int x, int y, int w, int h) {
    MoveWindow(p.control(id), p.scale(p.left + x), p.scale(y) - p.scroll,
        p.scale(std::max(1, w)), p.scale(h), TRUE);
}
void layout(Page& p) {
    RECT rect{};
    GetClientRect(p.hwnd, &rect);
    int dw = p.logical(rect.right);
    int width = (std::min)(1050, dw - 24);
    p.left = (dw - width) / 2;
    p.width = width;
    SCROLLINFO info{sizeof(info), SIF_PAGE | SIF_RANGE | SIF_POS, 0, 0, 0, 0, 0};
    info.nMax = p.scale(contentHeight) - 1;
    info.nPage = static_cast<UINT>(rect.bottom);
    info.nPos = p.scroll;
    p.scroll = SetScrollInfo(p.hwnd, SB_VERT, &info, TRUE);
    if (!p.lighting) {
        place(p, Title1, 22, 21, width - 270, 31);
        place(p, Caption1, width - 218, 24, 117, 24);
        place(p, Count, width - 95, 22, 70, 185);
        place(p, Axes, 24, 57, width - 48, 26);
        place(p, Caption2, 24, 95, 78, 20);
        place(p, Caption3, 110, 95, 82, 20);
        place(p, Caption4, 204, 95, 82, 20);
        place(p, Caption5, 300, 95, width - 324, 20);
        for (int i = 0; i < 5; ++i) {
            const int y = 122 + i * 33;
            place(p, FirstStage + i, 27, y, 62, 25);
            place(p, FirstX + i, 110, y, 77, 25);
            place(p, FirstY + i, 204, y, 77, 25);
            place(p, FirstDpi + i, 298, y, width - 322, 26);
        }
        place(p, Title2, 22, 321, width - 48, 31);
        place(p, Caption6, 24, 364, 110, 24);
        place(p, Rate, 144, 362, 138, 205);
        place(p, Interval, 305, 364, width - 328, 24);
    } else {
        place(p, Title1, 22, 20, width - 46, 33);
        place(p, Caption1, 24, 70, 89, 26);
        place(p, Brightness, 125, 70, width - 225, 28);
        place(p, BrightValue, width - 78, 70, 60, 26);
        place(p, Title2, 22, 161, width - 46, 33);
        place(p, Caption2, 24, 214, 140, 24);
        place(p, Mode, 184, 211, 264, 254);
        place(p, Caption3, 24, 264, 140, 25);
        place(p, Color1, 24, 294, 151, 33);
        place(p, Caption4, 194, 264, 135, 25);
        place(p, Color2, 194, 294, 151, 33);
        place(p, Caption5, 374, 264, 210, 25);
        place(p, Speed, 374, 294, 174, 155);
    }
    InvalidateRect(p.hwnd, nullptr, TRUE);
}

void roundBox(HDC dc, RECT r, COLORREF fill, COLORREF edge, int radius) {
    HBRUSH brush = CreateSolidBrush(fill);
    HPEN pen = CreatePen(PS_SOLID, 1, edge);
    auto oldBrush = SelectObject(dc, brush);
    auto oldPen = SelectObject(dc, pen);
    RoundRect(dc, r.left, r.top, r.right, r.bottom, radius, radius);
    SelectObject(dc, oldPen); SelectObject(dc, oldBrush);
    DeleteObject(pen); DeleteObject(brush);
}
void paint(Page& p, HDC dc) {
    RECT all{};
    GetClientRect(p.hwnd, &all);
    SetDCBrushColor(dc, background);
    FillRect(dc, &all, reinterpret_cast<HBRUSH>(GetStockObject(DC_BRUSH)));
    auto card = [&](int top, int bottom) {
        RECT r{p.scale(p.left), p.scale(top) - p.scroll, p.scale(p.left + p.width),
            p.scale(bottom) - p.scroll};
        roundBox(dc, r, panel, RGB(45, 50, 45), p.scale(10));
    };
    if (p.lighting) { card(8, 127); card(145, 366); }
    else { card(8, 298); card(309, 404); }
}
COLORREF rgbFromHex(unsigned c) { return RGB((c >> 16) & 255, (c >> 8) & 255, c & 255); }
unsigned hexFromRgb(COLORREF c) {
    return (static_cast<unsigned>(GetRValue(c)) << 16) |
        (static_cast<unsigned>(GetGValue(c)) << 8) | GetBValue(c);
}
void paintColor(Page& p, const DRAWITEMSTRUCT& item) {
    int index = item.CtlID - Color1;
    const bool on = (item.itemState & ODS_DISABLED) == 0;
    COLORREF ink = on ? words : disabled;
    RECT r = item.rcItem;
    auto dc = item.hDC;
    roundBox(dc, r, (item.itemState & ODS_SELECTED) ? line : field,
        item.itemState & ODS_FOCUS ? accent : line, p.scale(6));
    RECT chip{r.left + p.scale(9), r.top + p.scale(7), r.left + p.scale(28), r.bottom - p.scale(7)};
    roundBox(dc, chip, on ? rgbFromHex(p.colors[index]) : field, line, p.scale(4));
    auto old = SelectObject(dc, p.font);
    SetBkMode(dc, TRANSPARENT);
    SetTextColor(dc, ink);
    r.left += p.scale(39);
    wchar_t rgb[10]{};
    swprintf(rgb, 10, L"#%06X", p.colors[index] & 0xffffff);
    DrawTextW(dc, rgb, -1, &r, DT_LEFT | DT_SINGLELINE | DT_VCENTER | DT_NOPREFIX);
    SelectObject(dc, old);
}

void lightingControls(Page& p) {
    int ix = selected(p, Mode);
    if (ix < 0 || ix >= static_cast<int>(std::size(effects))) return;
    auto effect = effects[ix];
    bool first = effect == viper::Effect::Static || effect == viper::Effect::BreathOne ||
        effect == viper::Effect::BreathTwo || effect == viper::Effect::Reactive;
    enable(p, Color1, first); enable(p, Caption3, first);
    bool second = effect == viper::Effect::BreathTwo;
    enable(p, Color2, second); enable(p, Caption4, second);
    bool speed = effect == viper::Effect::Reactive;
    enable(p, Speed, speed); enable(p, Caption5, speed);
    InvalidateRect(p.control(Color1), nullptr, TRUE);
    InvalidateRect(p.control(Color2), nullptr, TRUE);
}
void chooseColor(Page& p, int id) {
    CHOOSECOLORW pick{};
    pick.lStructSize = sizeof(pick);
    pick.hwndOwner = p.hwnd;
    pick.rgbResult = rgbFromHex(p.colors[id - Color1]);
    pick.lpCustColors = p.customColors;
    pick.Flags = CC_RGBINIT | CC_FULLOPEN;
    if (ChooseColorW(&pick)) {
        p.colors[id - Color1] = hexFromRgb(pick.rgbResult);
        InvalidateRect(p.control(id), nullptr, TRUE);
    }
}
bool validDpi(const Page& p, int id, int& value) {
    wchar_t raw[8]{};
    int len = GetDlgItemTextW(p.hwnd, id, raw, static_cast<int>(std::size(raw)));
    if (!len || !std::all_of(raw, raw + len, [](wchar_t c){ return c >= L'0' && c <= L'9'; })) return false;
    value = static_cast<int>(wcstol(raw, nullptr, 10));
    return value >= 100 && value <= 20000;
}
bool linked(const Page& p) { return IsDlgButtonChecked(p.hwnd, Axes) == BST_CHECKED; }
void copyX(const Page& p, int i) {
    wchar_t raw[8]{};
    GetDlgItemTextW(p.hwnd, FirstX + i, raw, static_cast<int>(std::size(raw)));
    SetDlgItemTextW(p.hwnd, FirstY + i, raw);
}
void stageControls(Page& p) {
    int count = selected(p, Count) + 1;
    p.active = std::max(1, std::min(p.active, count));
    for (int i = 0; i < 5; ++i) {
        bool enabled = i < count;
        if (enabled && linked(p)) copyX(p, i);
        enable(p, FirstStage + i, enabled);
        enable(p, FirstX + i, enabled);
        enable(p, FirstY + i, enabled && !linked(p));
        enable(p, FirstDpi + i, enabled);
        CheckDlgButton(p.hwnd, FirstStage + i, p.active == i + 1 ? BST_CHECKED : BST_UNCHECKED);
    }
}
void interval(const Page& p) {
    constexpr const wchar_t* times[] = {L"8", L"2", L"1", L"0,5", L"0,25", L"0,125"};
    int ix = selected(p, Rate);
    if (ix >= 0 && ix < static_cast<int>(std::size(times))) {
        std::wstring text = std::wstring(L"Интервал отчётов USB · ") + times[ix] + L" мс";
        SetDlgItemTextW(p.hwnd, Interval, text.c_str());
    }
}
void brightValue(const Page& p) {
    int value = static_cast<int>(SendMessageW(p.control(Brightness), TBM_GETPOS, 0, 0));
    auto text = std::to_wstring(value) + L" %";
    SetDlgItemTextW(p.hwnd, BrightValue, text.c_str());
}

void command(Page& p, int id, int code) {
    if (p.loading) return;
    if (p.lighting) {
        if (id == Mode && code == CBN_SELCHANGE) lightingControls(p);
        if ((id == Color1 || id == Color2) && code == BN_CLICKED) chooseColor(p, id);
        return;
    }
    if (id == Count && code == CBN_SELCHANGE) stageControls(p);
    if (id == Rate && code == CBN_SELCHANGE) interval(p);
    if (id == Axes && code == BN_CLICKED) {
        if (linked(p)) for (int i = 0; i < 5; ++i) copyX(p, i);
        stageControls(p);
    }
    if (id >= FirstStage && id < FirstStage + 5 && code == BN_CLICKED) {
        p.active = id - FirstStage + 1;
        stageControls(p);
    }
    if (id >= FirstX && id < FirstX + 5 && code == EN_CHANGE) {
        int i = id - FirstX, value = 0;
        if (validDpi(p, id, value))
            SendMessageW(p.control(FirstDpi + i), TBM_SETPOS, TRUE, value);
        if (linked(p)) copyX(p, i);
    }
}
void trackMoved(Page& p, HWND control) {
    int id = GetDlgCtrlID(control);
    if (id == Brightness) { brightValue(p); return; }
    if (id < FirstDpi || id >= FirstDpi + 5) return;
    int value = static_cast<int>(SendMessageW(control, TBM_GETPOS, 0, 0));
    setNumber(p, FirstX + id - FirstDpi, ((value + 25) / 50) * 50);
}

LRESULT drawTrack(Page& p, const NMCUSTOMDRAW& cd) {
    bool on = IsWindowEnabled(cd.hdr.hwndFrom) != FALSE;
    HDC dc = cd.hdc;
    if (cd.dwDrawStage == CDDS_PREPAINT) {
        RECT r{}; GetClientRect(cd.hdr.hwndFrom, &r);
        FillRect(dc, &r, p.panelBrush);
        return CDRF_NOTIFYITEMDRAW | CDRF_NOTIFYPOSTPAINT;
    }
    if (cd.dwDrawStage == CDDS_POSTPAINT) {
        if (GetFocus() == cd.hdr.hwndFrom) {
            RECT r{}; GetClientRect(cd.hdr.hwndFrom, &r); DrawFocusRect(dc, &r);
        }
        return CDRF_DODEFAULT;
    }
    if (cd.dwDrawStage != CDDS_ITEMPREPAINT) return CDRF_DODEFAULT;
    RECT r = cd.rc;
    if (cd.dwItemSpec == TBCD_CHANNEL) {
        const int cy = (r.top + r.bottom) / 2;
        r.top = cy - p.scale(2); r.bottom = cy + p.scale(2);
        roundBox(dc, r, line, line, p.scale(4));
        RECT thumb{}; SendMessageW(cd.hdr.hwndFrom, TBM_GETTHUMBRECT, 0, reinterpret_cast<LPARAM>(&thumb));
        r.right = (thumb.left + thumb.right) / 2;
        if (r.right > r.left) roundBox(dc, r, on ? accent : disabled, on ? accent : disabled, p.scale(4));
    } else if (cd.dwItemSpec == TBCD_THUMB) {
        int x = (r.left + r.right) / 2, y = (r.top + r.bottom) / 2, radius = p.scale(7);
        RECT dot{x - radius, y - radius, x + radius + 1, y + radius + 1};
        roundBox(dc, dot, on ? accent : disabled, on ? accent : disabled, radius * 2);
    }
    return CDRF_SKIPDEFAULT;
}

void scrollTo(Page& p, int pos) {
    SCROLLINFO info{sizeof(info), SIF_ALL, 0, 0, 0, 0, 0};
    GetScrollInfo(p.hwnd, SB_VERT, &info);
    int max = std::max(0, info.nMax - static_cast<int>(info.nPage) + 1);
    int value = std::max(0, std::min(pos, max));
    if (value != p.scroll) { p.scroll = value; layout(p); }
}

LRESULT CALLBACK pageProc(HWND hwnd, UINT msg, WPARAM wp, LPARAM lp) {
    Page* pp = reinterpret_cast<Page*>(GetWindowLongPtrW(hwnd, GWLP_USERDATA));
    if (msg == WM_NCCREATE) {
        auto init = reinterpret_cast<CREATESTRUCTW*>(lp);
        pp = new (std::nothrow) Page;
        if (!pp) return FALSE;
        pp->hwnd = hwnd;
        pp->lighting = init->lpCreateParams != nullptr;
        SetWindowLongPtrW(hwnd, GWLP_USERDATA, reinterpret_cast<LONG_PTR>(pp));
    }
    if (!pp) return DefWindowProcW(hwnd, msg, wp, lp);
    Page& p = *pp;
    switch (msg) {
    case WM_CREATE:
        if (p.lighting) makeLighting(p); else makePerformance(p);
        p.dpi = windowDpi(hwnd);
        fonts(p);
        return 0;
    case WM_SIZE:
        if (!p.controls.empty()) layout(p);
        return 0;
    case 0x02E3: // WM_DPICHANGED_AFTERPARENT
        p.dpi = windowDpi(hwnd); fonts(p); layout(p); return 0;
    case WM_MOUSEWHEEL:
        scrollTo(p, p.scroll - MulDiv(GET_WHEEL_DELTA_WPARAM(wp), p.scale(48), WHEEL_DELTA)); return 0;
    case WM_VSCROLL: {
        SCROLLINFO info{sizeof(info), SIF_ALL, 0, 0, 0, 0, 0};
        GetScrollInfo(hwnd, SB_VERT, &info);
        int pos = p.scroll;
        switch (LOWORD(wp)) {
            case SB_TOP: pos = 0; break; case SB_BOTTOM: pos = info.nMax; break;
            case SB_LINEUP: pos -= p.scale(28); break; case SB_LINEDOWN: pos += p.scale(28); break;
            case SB_PAGEUP: pos -= static_cast<int>(info.nPage); break;
            case SB_PAGEDOWN: pos += static_cast<int>(info.nPage); break;
            case SB_THUMBTRACK: case SB_THUMBPOSITION: pos = info.nTrackPos; break;
            default: return 0;
        }
        scrollTo(p, pos); return 0;
    }
    case WM_ERASEBKGND: return 1;
    case WM_PAINT: {
        PAINTSTRUCT ps{};
        HDC dc = BeginPaint(hwnd, &ps); paint(p, dc); EndPaint(hwnd, &ps); return 0;
    }
    case WM_CTLCOLORSTATIC: case WM_CTLCOLORBTN:
    case WM_CTLCOLOREDIT: case WM_CTLCOLORLISTBOX: {
        HWND control = reinterpret_cast<HWND>(lp);
        HDC dc = reinterpret_cast<HDC>(wp);
        int id = GetDlgCtrlID(control);
        bool edit = id >= FirstX && id < FirstY + 5;
        bool input = msg == WM_CTLCOLOREDIT || msg == WM_CTLCOLORLISTBOX || edit;
        COLORREF ink = words;
        for (const auto& item : p.controls)
            if (item.hwnd == control && item.role == TextRole::Caption) { ink = muted; break; }
        if (!IsWindowEnabled(control)) ink = disabled;
        SetTextColor(dc, ink); SetBkColor(dc, input ? field : panel);
        return reinterpret_cast<LRESULT>(input ? p.fieldBrush : p.panelBrush);
    }
    case WM_COMMAND: command(p, LOWORD(wp), HIWORD(wp)); return 0;
    case WM_HSCROLL: if (lp) trackMoved(p, reinterpret_cast<HWND>(lp)); return 0;
    case WM_NOTIFY: {
        auto nm = reinterpret_cast<NMHDR*>(lp);
        int id = static_cast<int>(nm->idFrom);
        if (nm->code == NM_CUSTOMDRAW && ((id >= FirstDpi && id < FirstDpi + 5) || id == Brightness))
            return drawTrack(p, *reinterpret_cast<NMCUSTOMDRAW*>(lp));
        break;
    }
    case WM_DRAWITEM: {
        auto item = reinterpret_cast<DRAWITEMSTRUCT*>(lp);
        if (item && (item->CtlID == Color1 || item->CtlID == Color2)) {
            paintColor(p, *item); return TRUE;
        }
        break;
    }
    case WM_NCDESTROY:
        SetWindowLongPtrW(hwnd, GWLP_USERDATA, 0); delete pp; break;
    }
    return DefWindowProcW(hwnd, msg, wp, lp);
}
} // namespace

HWND CreateDevicePage(HWND parent, HINSTANCE instance, bool lighting) {
    INITCOMMONCONTROLSEX common{sizeof(common), ICC_BAR_CLASSES};
    InitCommonControlsEx(&common);
    WNDCLASSW cls{};
    cls.hInstance = instance;
    cls.lpfnWndProc = pageProc;
    cls.lpszClassName = pageClass;
    cls.hCursor = LoadCursorW(nullptr, IDC_ARROW);
    if (!RegisterClassW(&cls) && GetLastError() != ERROR_CLASS_ALREADY_EXISTS) return nullptr;
    HWND page = CreateWindowExW(WS_EX_CONTROLPARENT, pageClass,
        lighting ? L"Подсветка" : L"Производительность",
        WS_CHILD | WS_CLIPCHILDREN | WS_VSCROLL, 0, 0, 1, 1, parent, nullptr, instance,
        lighting ? reinterpret_cast<void*>(1) : nullptr);
    if (page) LoadDevicePage(page, MouseProfile{});
    return page;
}

void LoadDevicePage(HWND page, const MouseProfile& profile) {
    auto pp = reinterpret_cast<Page*>(GetWindowLongPtrW(page, GWLP_USERDATA));
    if (!pp) return;
    auto& p = *pp;
    p.loading = true;
    if (!p.lighting) {
        const auto& d = profile.performance;
        p.active = d.active;
        select(p, Count, d.count - 1);
        bool same = std::equal(d.x.begin(), d.x.begin() + std::clamp(d.count, 0, 5), d.y.begin());
        CheckDlgButton(page, Axes, same ? BST_CHECKED : BST_UNCHECKED);
        for (int i = 0; i < 5; ++i) {
            setNumber(p, FirstX + i, d.x[i]); setNumber(p, FirstY + i, d.y[i]);
            SendMessageW(p.control(FirstDpi + i), TBM_SETPOS, TRUE, d.x[i]);
        }
        auto ix = std::find(std::begin(rates), std::end(rates), d.hz);
        select(p, Rate, ix == std::end(rates) ? -1 : static_cast<int>(ix - std::begin(rates)));
        stageControls(p); interval(p);
    } else {
        const auto& l = profile.lighting;
        auto ix = std::find(std::begin(effects), std::end(effects), l.effect);
        select(p, Mode, ix == std::end(effects) ? -1 : static_cast<int>(ix - std::begin(effects)));
        SendMessageW(p.control(Brightness), TBM_SETPOS, TRUE, l.brightness);
        p.colors = {l.color1, l.color2};
        select(p, Speed, l.speed - 1);
        brightValue(p); lightingControls(p);
    }
    p.loading = false;
}

bool ReadDevicePage(HWND page, MouseProfile& profile, std::wstring& error) {
    error.clear();
    auto pp = reinterpret_cast<Page*>(GetWindowLongPtrW(page, GWLP_USERDATA));
    if (!pp) { error = L"Не удалось открыть вкладку устройства."; return false; }
    auto& p = *pp;
    if (p.lighting) {
        int mode = selected(p, Mode), speed = selected(p, Speed) + 1;
        if (mode < 0 || mode >= static_cast<int>(std::size(effects)) || speed < 1 || speed > 3) {
            error = L"Выберите эффект и длительность отклика."; return false;
        }
        profile.lighting.effect = effects[mode];
        profile.lighting.brightness = static_cast<int>(SendMessageW(p.control(Brightness), TBM_GETPOS, 0, 0));
        profile.lighting.speed = speed;
        profile.lighting.color1 = p.colors[0]; profile.lighting.color2 = p.colors[1];
    } else {
        auto d = profile.performance;
        int rate = selected(p, Rate);
        d.count = selected(p, Count) + 1;
        d.active = p.active;
        if (d.count < 1 || d.count > 5 || rate < 0 || rate >= static_cast<int>(std::size(rates))) {
            error = L"Выберите число уровней DPI и частоту опроса."; return false;
        }
        d.hz = rates[rate];
        for (int i = 0; i < 5; ++i) {
            int x = 0, y = 0;
            bool xok = validDpi(p, FirstX + i, x);
            bool yok = validDpi(p, FirstY + i, y);
            if (i < d.count && (!xok || (!linked(p) && !yok))) {
                error = L"Уровень " + std::to_wstring(i + 1) +
                    (xok ? L", ось Y" : L", ось X") + L". Введите целое число от 100 до 20 000 DPI.";
                HWND edit = p.control((xok ? FirstY : FirstX) + i);
                if (IsWindowVisible(edit)) { SetFocus(edit); SendMessageW(edit, EM_SETSEL, 0, -1); }
                return false;
            }
            if (xok) d.x[i] = x;
            if (i < d.count && linked(p)) d.y[i] = d.x[i];
            else if (yok) d.y[i] = y;
        }
        profile.performance = d;
    }
    return true;
}
