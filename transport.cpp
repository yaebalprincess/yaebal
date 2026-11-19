#include "transport.h"

#include <windows.h>
#include <hidsdi.h>
#include <setupapi.h>
#include <algorithm>
#include <cwctype>
#include <memory>
#include <vector>

namespace viper {
namespace {

using Frame = std::array<Byte, 91>; // Windows report ID followed by the 90-byte vendor payload.
constexpr USHORT vendorId = 0x1532, productId = 0x0091;

struct Handle {
    HANDLE value = INVALID_HANDLE_VALUE;
    Handle() = default;
    explicit Handle(HANDLE h) : value(h) {}
    Handle(const Handle&) = delete;
    Handle& operator=(const Handle&) = delete;
    ~Handle() { if (value && value != INVALID_HANDLE_VALUE) CloseHandle(value); }
};

struct DeviceList {
    HDEVINFO value;
    ~DeviceList() { if (value != INVALID_HANDLE_VALUE) SetupDiDestroyDeviceInfoList(value); }
};

Result systemFailure(const wchar_t* action, DWORD code) {
    return {false, std::wstring(action) + L" (Windows " + std::to_wstring(code) + L")."};
}

bool matchesDevice(HANDLE handle) {
    HIDD_ATTRIBUTES attributes{};
    attributes.Size = sizeof(attributes);
    if (!HidD_GetAttributes(handle, &attributes) ||
        attributes.VendorID != vendorId || attributes.ProductID != productId) return false;
    PHIDP_PREPARSED_DATA data{};
    if (!HidD_GetPreparsedData(handle, &data)) return false;
    HIDP_CAPS caps{};
    auto status = HidP_GetCaps(data, &caps);
    HidD_FreePreparsedData(data);
    return status == HIDP_STATUS_SUCCESS && caps.FeatureReportByteLength == Frame{}.size();
}

Result openMouse(Handle& mouse) {
    GUID guid{};
    HidD_GetHidGuid(&guid);
    DeviceList list{SetupDiGetClassDevsW(&guid, nullptr, nullptr, DIGCF_PRESENT | DIGCF_DEVICEINTERFACE)};
    if (list.value == INVALID_HANDLE_VALUE) return systemFailure(L"Ошибка поиска HID-устройств", GetLastError());

    bool recognized = false;
    DWORD accessError = 0;
    for (DWORD index = 0; ; ++index) {
        SP_DEVICE_INTERFACE_DATA entry{};
        entry.cbSize = sizeof(entry);
        if (!SetupDiEnumDeviceInterfaces(list.value, nullptr, &guid, index, &entry)) {
            DWORD error = GetLastError();
            if (error == ERROR_NO_MORE_ITEMS) break;
            return systemFailure(L"Ошибка перечисления HID-устройств", error);
        }
        DWORD size = 0;
        SetupDiGetDeviceInterfaceDetailW(list.value, &entry, nullptr, 0, &size, nullptr);
        if (size < sizeof(SP_DEVICE_INTERFACE_DETAIL_DATA_W)) continue;
        std::vector<Byte> buffer(size);
        auto detail = reinterpret_cast<SP_DEVICE_INTERFACE_DETAIL_DATA_W*>(buffer.data());
        detail->cbSize = sizeof(*detail);
        if (!SetupDiGetDeviceInterfaceDetailW(list.value, &entry, detail, size, nullptr, nullptr)) continue;

        std::wstring path = detail->DevicePath;
        std::transform(path.begin(), path.end(), path.begin(), [](wchar_t c) { return static_cast<wchar_t>(std::towlower(c)); });
        if (path.find(L"vid_1532&pid_0091") == std::wstring::npos) continue;
        recognized = true;
        if (path.find(L"&mi_00") == std::wstring::npos) continue;

        // Mouse input is reserved by Windows. Feature IOCTLs permit a zero-access handle.
        Handle candidate(CreateFileW(detail->DevicePath, 0, FILE_SHARE_READ | FILE_SHARE_WRITE,
                                     nullptr, OPEN_EXISTING, 0, nullptr));
        if (candidate.value == INVALID_HANDLE_VALUE) {
            accessError = GetLastError();
            continue;
        }
        if (!matchesDevice(candidate.value)) continue;
        if (mouse.value != INVALID_HANDLE_VALUE)
            return {false, L"Найдены две Viper 8KHz. Оставьте подключённой мышь, которую хотите настроить."};
        std::swap(mouse.value, candidate.value);
    }
    if (accessError) return systemFailure(L"Нет доступа к интерфейсу Viper 8KHz", accessError);
    if (mouse.value != INVALID_HANDLE_VALUE) return {true, L"Razer Viper 8KHz подключена."};
    if (recognized) return {false, L"Viper 8KHz обнаружена, но её интерфейс настройки HID недоступен."};
    return {false, L"Razer Viper 8KHz не подключена."};
}

Byte checksum(const Frame& frame) {
    Byte value = 0;
    for (size_t i = 3; i <= 88; ++i) value ^= frame[i];
    return value;
}

Result transfer(HANDLE mouse, const Command& request, Command& response) {
    if (request.size > request.args.size()) return {false, L"Недопустимая длина команды."};
    Frame frame{};
    frame[2] = request.transaction;
    frame[6] = request.size;
    frame[7] = request.group;
    frame[8] = request.id;
    std::copy_n(request.args.begin(), request.size, frame.begin() + 9);
    frame[89] = checksum(frame);
    if (!HidD_SetFeature(mouse, frame.data(), static_cast<ULONG>(frame.size())))
        return systemFailure(L"Мыши не удалось передать команду", GetLastError());

    Result last{false, L"Мышь не подтвердила команду. Закройте другие программы настройки мыши и повторите."};
    for (int attempt = 0; attempt < 6; ++attempt) {
        // A busy device gets another GET only. Replaying a mutating SET can repeat an operation.
        Sleep(attempt == 0 ? 2 : 10);
        Frame reply{};
        if (!HidD_GetFeature(mouse, reply.data(), static_cast<ULONG>(reply.size())))
            return systemFailure(L"Не удалось прочитать ответ мыши", GetLastError());

        if (reply[0] != 0 || reply[2] != frame[2] || reply[3] || reply[4] || reply[5] ||
            reply[7] != frame[7] || reply[8] != frame[8] || reply[6] > 80 ||
            reply[89] != checksum(reply)) {
            last = {false, L"Ответ HID не соответствует команде. Закройте Synapse и повторите операцию."};
            continue;
        }
        switch (reply[1]) {
        case 0x00: case 0x01:
            last = {false, L"Мышь занята и не подтвердила команду."};
            continue;
        case 0x02:
            response = {reply[2], reply[7], reply[8], reply[6]};
            std::copy_n(reply.begin() + 9, 80, response.args.begin());
            return {true, {}};
        case 0x03: return {false, L"Мышь отклонила команду."};
        case 0x04: return {false, L"Время ожидания ответа мыши истекло."};
        case 0x05: return {false, L"Прошивка мыши не поддерживает команду."};
        default: return {false, L"Неизвестный код ответа мыши."};
        }
    }
    return last;
}

} // namespace

Result withMouse(const std::function<Result(const Exchange&)>& operation) {
    Handle mutex(CreateMutexW(nullptr, FALSE, L"Local\\Viper8KHzConfig-HID-1532-0091"));
    if (!mutex.value) return systemFailure(L"Не удалось открыть блокировку HID", GetLastError());
    DWORD lock = WaitForSingleObject(mutex.value, 600);
    if (lock != WAIT_OBJECT_0 && lock != WAIT_ABANDONED)
        return {false, L"Другой экземпляр программы настраивает мышь. Повторите операцию позже."};
    struct Unlock { HANDLE mutex; ~Unlock() { ReleaseMutex(mutex); } } guard{mutex.value};

    Handle mouse;
    auto result = openMouse(mouse);
    if (!result.ok) return result;
    return operation([&](const Command& cmd, Command& reply) { return transfer(mouse.value, cmd, reply); });
}

} // namespace viper
