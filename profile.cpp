#include "profile.h"

#include <algorithm>
#include <array>
#include <map>
#include <string>
#include <utility>

#ifdef _WIN32
#include <windows.h>
#endif

namespace {
using namespace viper;
constexpr wchar_t signature[] = L"Viper8K.Profile/1";
constexpr size_t maxFileBytes = 16384;
constexpr std::pair<Effect, const wchar_t*> effects[] = {
    {Effect::Off, L"off"}, {Effect::Static, L"static"}, {Effect::Spectrum, L"spectrum"},
    {Effect::BreathOne, L"breathing-one"}, {Effect::BreathTwo, L"breathing-two"},
    {Effect::BreathRandom, L"breathing-random"}, {Effect::Reactive, L"reactive"}
};

const wchar_t* effectName(Effect value) {
    for (const auto& entry : effects) if (entry.first == value) return entry.second;
    return nullptr;
}

bool validProfile(const MouseProfile& p, std::wstring& error) {
    const auto& d = p.performance;
    const auto& l = p.lighting;
    constexpr int rates[] = {125, 500, 1000, 2000, 4000, 8000};
    const auto validDpi = [](int n) { return n >= 100 && n <= 20000; };
    if (p.name.empty() || p.name.size() > 128 || std::any_of(p.name.begin(), p.name.end(),
            [](wchar_t c) { return c < 32 || (c >= 0x7f && c <= 0x9f); })) {
        error = L"Имя профиля должно содержать от 1 до 128 символов без переносов строк и управляющих знаков.";
    } else if (d.count < 1 || d.count > 5 || d.active < 1 || d.active > d.count) {
        error = L"Проверьте количество уровней DPI (от 1 до 5) и номер активного уровня.";
    } else if (!std::all_of(d.x.begin(), d.x.end(), validDpi) || !std::all_of(d.y.begin(), d.y.end(), validDpi)) {
        error = L"Каждое значение DPI должно быть в диапазоне от 100 до 20 000.";
    } else if (std::find(std::begin(rates), std::end(rates), d.hz) == std::end(rates)) {
        error = L"Недопустимая частота опроса в профиле.";
    } else if (!effectName(l.effect) || l.brightness < 0 || l.brightness > 100 ||
               l.speed < 1 || l.speed > 3 || l.color1 > 0xffffff || l.color2 > 0xffffff) {
        error = L"Проверьте эффект, яркость, скорость и цвета подсветки в профиле.";
    } else if (!validCalibration(p.calibration)) {
        error = L"Проверьте режим калибровки и расстояния отрыва и посадки сенсора.";
    } else {
        return true;
    }
    return false;
}

std::wstring formatDpi(const std::array<int, 5>& axis) {
    std::wstring result;
    for (int value : axis) {
        if (!result.empty()) result += L',';
        result += std::to_wstring(value);
    }
    return result;
}

std::wstring formatColor(unsigned rgb) {
    constexpr wchar_t hex[] = L"0123456789ABCDEF";
    std::wstring result = L"#000000";
    for (int i = 6; i > 0; --i) { result[i] = hex[rgb & 15]; rgb >>= 4; }
    return result;
}

std::wstring serialize(const MouseProfile& p) {
    const auto& d = p.performance;
    const auto& l = p.lighting;
    std::wstring result = signature;
    auto add = [&](const wchar_t* key, const std::wstring& value) {
        result += L"\r\n"; result += key; result += L'='; result += value;
    };
    add(L"name", p.name);
    add(L"stages", std::to_wstring(d.count));
    add(L"active", std::to_wstring(d.active));
    add(L"dpi-x", formatDpi(d.x));
    add(L"dpi-y", formatDpi(d.y));
    add(L"polling-hz", std::to_wstring(d.hz));
    add(L"effect", effectName(l.effect));
    add(L"brightness", std::to_wstring(l.brightness));
    add(L"reactive-speed", std::to_wstring(l.speed));
    add(L"color-1", formatColor(l.color1));
    add(L"color-2", formatColor(l.color2));
    add(L"calibration-mode", std::to_wstring(static_cast<int>(p.calibration.mode)));
    add(L"calibration-lift", std::to_wstring(p.calibration.lift));
    add(L"calibration-land", std::to_wstring(p.calibration.land));
    return result + L"\r\n";
}

bool number(const std::wstring& s, int& out) {
    if (s.empty() || s.size() > 5) return false;
    int n = 0;
    for (wchar_t ch : s) {
        if (ch < L'0' || ch > L'9') return false;
        n = n * 10 + int(ch - L'0');
    }
    out = n;
    return true;
}

bool parseDpi(const std::wstring& s, std::array<int, 5>& axis) {
    size_t pos = 0;
    for (size_t i = 0; i < axis.size(); ++i) {
        const size_t end = s.find(L',', pos);
        if ((end == s.npos) != (i + 1 == axis.size())) return false;
        if (!number(s.substr(pos, end - pos), axis[i])) return false;
        if (end != s.npos) pos = end + 1;
    }
    return true;
}

bool parseColor(const std::wstring& s, unsigned& rgb) {
    if (s.size() != 7 || s[0] != L'#') return false;
    rgb = 0;
    for (size_t i = 1; i < s.size(); ++i) {
        wchar_t c = s[i];
        if (c >= L'a' && c <= L'f') c -= L'a' - L'A';
        int digit;
        if (c >= L'A' && c <= L'F') digit = 10 + int(c - L'A');
        else if (c >= L'0' && c <= L'9') digit = int(c - L'0');
        else return false;
        rgb = (rgb << 4) | unsigned(digit);
    }
    return true;
}

bool parse(const std::wstring& input, MouseProfile& result, std::wstring& error) {
    const std::array<std::wstring, 14> keys = {L"name", L"stages", L"active", L"dpi-x", L"dpi-y",
        L"polling-hz", L"effect", L"brightness", L"reactive-speed", L"color-1", L"color-2",
        L"calibration-mode", L"calibration-lift", L"calibration-land"};
    std::map<std::wstring, std::wstring> fields;
    size_t pos = !input.empty() && input.front() == 0xfeff ? 1 : 0;
    bool header = true;
    while (pos < input.size()) {
        size_t end = input.find(L'\n', pos);
        auto line = input.substr(pos, end - pos);
        if (!line.empty() && line.back() == L'\r') line.pop_back();
        if (header) {
            if (line != signature) {
                error = L"Неизвестный формат или версия файла профиля Viper 8KHz.";
                return false;
            }
            header = false;
        } else {
            const size_t sep = line.find(L'=');
            const auto key = line.substr(0, sep);
            if (sep == line.npos || std::find(keys.begin(), keys.end(), key) == keys.end()) {
                error = L"Файл профиля содержит неизвестное поле или повреждённую строку.";
                return false;
            }
            if (!fields.emplace(key, line.substr(sep + 1)).second) {
                error = L"В профиле повторяется поле «" + key + L"».";
                return false;
            }
        }
        if (end == input.npos) break;
        pos = end + 1;
    }
    for (const auto& key : keys) {
        if (!fields.count(key)) { error = L"В профиле отсутствует поле «" + key + L"»."; return false; }
    }
    MouseProfile p;
    auto& d = p.performance;
    auto& l = p.lighting;
    p.name = fields.at(L"name");
    if (!number(fields.at(L"stages"), d.count) || !number(fields.at(L"active"), d.active) ||
        !number(fields.at(L"polling-hz"), d.hz) || !number(fields.at(L"brightness"), l.brightness) ||
        !number(fields.at(L"reactive-speed"), l.speed) || !parseDpi(fields.at(L"dpi-x"), d.x) ||
        !parseDpi(fields.at(L"dpi-y"), d.y) || !parseColor(fields.at(L"color-1"), l.color1) ||
        !parseColor(fields.at(L"color-2"), l.color2)) {
        error = L"В профиле повреждены числа, уровни DPI или цвета (#RRGGBB).";
        return false;
    }
    const auto effect = std::find_if(std::begin(effects), std::end(effects), [&](const auto& pair) {
        return fields.at(L"effect") == pair.second;
    });
    if (effect == std::end(effects)) { error = L"Неизвестный эффект подсветки в профиле."; return false; }
    l.effect = effect->first;
    int mode = 0;
    if (!number(fields.at(L"calibration-mode"), mode) || mode > 3 ||
        !number(fields.at(L"calibration-lift"), p.calibration.lift) ||
        !number(fields.at(L"calibration-land"), p.calibration.land)) {
        error = L"В профиле повреждены параметры калибровки.";
        return false;
    }
    p.calibration.mode = static_cast<CalibrationMode>(mode);
    if (!validProfile(p, error)) return false;
    result = std::move(p);
    return true;
}

#ifdef _WIN32
struct File {
    HANDLE handle = INVALID_HANDLE_VALUE;
    ~File() { close(); }
    void close() {
        if (handle != INVALID_HANDLE_VALUE) { CloseHandle(handle); handle = INVALID_HANDLE_VALUE; }
    }
};

bool ioError(std::wstring& error, const wchar_t* message, DWORD code = GetLastError()) {
    error = std::wstring(message) + L" (код Windows " + std::to_wstring(code) + L").";
    return false;
}
#endif
} // namespace

#ifdef _WIN32
bool LoadMouseProfile(const std::wstring& path, MouseProfile& profile, std::wstring& error) {
    error.clear();
    File f;
    f.handle = CreateFileW(path.c_str(), GENERIC_READ, FILE_SHARE_READ, nullptr, OPEN_EXISTING,
                           FILE_ATTRIBUTE_NORMAL, nullptr);
    if (f.handle == INVALID_HANDLE_VALUE) return ioError(error, L"Не удалось открыть профиль");
    LARGE_INTEGER size{};
    if (!GetFileSizeEx(f.handle, &size)) return ioError(error, L"Не удалось узнать размер файла");
    if (size.QuadPart <= 0 || size.QuadPart > static_cast<LONGLONG>(maxFileBytes)) {
        error = L"Файл профиля пуст или превышает 16 КБ.";
        return false;
    }
    std::string bytes(static_cast<size_t>(size.QuadPart), '\0');
    DWORD read = 0;
    if (!ReadFile(f.handle, bytes.data(), static_cast<DWORD>(bytes.size()), &read, nullptr))
        return ioError(error, L"Не удалось прочитать профиль");
    if (read != bytes.size()) { error = L"Файл профиля прочитан не полностью."; return false; }
    std::wstring input(bytes.size(), L'\0');
    const int n = MultiByteToWideChar(CP_UTF8, MB_ERR_INVALID_CHARS, bytes.data(), int(bytes.size()),
                                      input.data(), int(input.size()));
    if (n == 0) { error = L"Файл профиля должен быть в кодировке UTF-8."; return false; }
    input.resize(n);
    return parse(input, profile, error);
}

bool SaveMouseProfile(const std::wstring& path, const MouseProfile& profile, std::wstring& error) {
    error.clear();
    if (!validProfile(profile, error)) return false;
    auto input = serialize(profile);
    std::string bytes(input.size() * 4, '\0');
    int n = WideCharToMultiByte(CP_UTF8, WC_ERR_INVALID_CHARS, input.data(), int(input.size()),
                                bytes.data(), int(bytes.size()), nullptr, nullptr);
    if (!n) { error = L"Имя профиля содержит повреждённый символ Unicode."; return false; }
    bytes.resize(n);

    const DWORD size = GetFullPathNameW(path.c_str(), 0, nullptr, nullptr);
    if (!size) return ioError(error, L"Не удалось определить путь к профилю");
    std::wstring dest(size, L'\0');
    const DWORD used = GetFullPathNameW(path.c_str(), size, dest.data(), nullptr);
    if (!used || used >= size) return ioError(error, L"Не удалось определить путь к профилю");
    dest.resize(used);
    const std::wstring parent = dest.substr(0, dest.find_last_of(L"\\/") + 1);
    static LONG counter = 0;
    File f;
    std::wstring temp;
    for (int i = 0; i < 64; ++i) {
        temp = parent + L".viper-" + std::to_wstring(GetCurrentProcessId()) + L"-" +
               std::to_wstring(InterlockedIncrement(&counter)) + L".tmp";
        if (!lstrcmpiW(temp.c_str(), dest.c_str())) continue;
        f.handle = CreateFileW(temp.c_str(), GENERIC_WRITE, 0, nullptr, CREATE_NEW, FILE_ATTRIBUTE_NORMAL, nullptr);
        if (f.handle != INVALID_HANDLE_VALUE) break;
        if (GetLastError() != ERROR_FILE_EXISTS) return ioError(error, L"Не удалось создать временный профиль");
    }
    if (f.handle == INVALID_HANDLE_VALUE) { error = L"Не удалось создать временный профиль в этой папке."; return false; }
    DWORD written = 0;
    bool ok = true;
    if (!WriteFile(f.handle, bytes.data(), static_cast<DWORD>(bytes.size()), &written, nullptr))
        ok = ioError(error, L"Не удалось записать профиль");
    else if (written != bytes.size()) { error = L"Профиль записан не полностью."; ok = false; }
    else if (!FlushFileBuffers(f.handle)) ok = ioError(error, L"Не удалось завершить запись профиля");
    f.close();
    if (ok && !MoveFileExW(temp.c_str(), dest.c_str(), MOVEFILE_REPLACE_EXISTING | MOVEFILE_WRITE_THROUGH))
        ok = ioError(error, L"Не удалось заменить файл профиля");
    if (!ok) DeleteFileW(temp.c_str());
    return ok;
}
#endif
