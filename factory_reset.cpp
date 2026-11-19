#include "factory_reset.h"
#include "transport.h"

#include <algorithm>
#include <array>
#include <chrono>
#include <cstdint>
#include <thread>

namespace viper {
namespace {

// RzCtl_0091.dll's Storage_Protocol25: see PROTOCOL.md for model and version.
constexpr Byte transaction = 0x1f;
using Slots = std::array<bool, 6>;

Result profiles(const Exchange& send, Slots& slots) {
    Command capacity{}, count{}, list{};
    auto result = send({transaction, 0x05, 0x8a, 1}, capacity);
    if (!result.ok) return result;
    if (capacity.size != 1 || capacity.args[0] != 5)
        return {false, L"Прошивка не подтвердила пять слотов памяти."};
    result = send({transaction, 0x05, 0x80, 1}, count);
    if (!result.ok) return result;
    if (count.size != 1 || count.args[0] < 1 || count.args[0] > 5)
        return {false, L"Не удалось подтвердить количество занятых слотов."};

    // The native module requests 65 bytes. Depending on the firmware, the
    // reported length can be trimmed to the occupied records.
    result = send({transaction, 0x05, 0x81, 65}, list);
    if (!result.ok) return result;
    const Byte used = count.args[0];
    if (list.size < used + 1 || list.size > 65 ||
        (list.args[0] != used && list.args[0] != capacity.args[0]))
        return {false, L"Прошивка вернула несогласованный список профилей."};
    slots.fill(false);
    for (Byte i = 1; i <= used; ++i) {
        Byte slot = list.args[i];
        if (slot < 1 || slot > 5 || slots[slot])
            return {false, L"Прошивка вернула неизвестные номера профилей."};
        slots[slot] = true;
    }
    if (!slots[1]) return {false, L"Базовый слот 1 не обнаружен."};
    return {true, {}};
}

std::uint32_t number(const Byte* p) {
    return std::uint32_t(p[0]) << 24 | std::uint32_t(p[1]) << 16 |
           std::uint32_t(p[2]) << 8 | std::uint32_t(p[3]);
}

Result storageInfo(const Exchange& send) {
    Command reply{};
    auto result = send({transaction, 0x06, 0x8e, 14}, reply);
    if (!result.ok) return result;
    auto total = number(&reply.args[2]);
    auto free = number(&reply.args[6]);
    auto reclaimed = number(&reply.args[10]);
    if (reply.size != 14 || total == 0 || free > total || reclaimed > total - free)
        return {false, L"Мышь не подтвердила параметры флеш-памяти."};
    return {true, {}};
}

Result resetStorage(const Exchange& send) {
    Slots original{};
    auto result = profiles(send, original);
    if (result.ok) result = storageInfo(send);
    if (!result.ok) return {false, L"Очистка не начата. " + result.message};

    // Query the format-status register before any write and reject an unknown
    // shape. Expect an idle or completed operation, never a pending operation.
    Command query{transaction, 0x06, 0x8a, 6}, reply{};
    result = send(query, reply);
    if (!result.ok) return {false, L"Очистка не начата. " + result.message};
    if (reply.size != 6 || reply.args[0] || reply.args[1] || reply.args[4] || reply.args[5] ||
        (reply.args[2] != 0 && reply.args[2] != 2) ||
        (reply.args[3] != 0 && reply.args[3] != 2))
        return {false, L"Очистка не начата. Неизвестный статус хранилища."};

    for (Byte slot = 2; slot <= 5; ++slot) {
        if (!original[slot]) continue;
        Command remove{transaction, 0x05, 0x03, 1};
        remove.args[0] = slot;
        result = send(remove, reply);
        if (!result.ok || reply.size != 1 || reply.args[0] != slot)
            return {false, L"Удаление слота " + std::to_wstring(slot) +
                           L" не подтверждено. Память могла измениться частично. " + result.message};
    }
    Slots remaining{};
    result = profiles(send, remaining);
    if (!result.ok || std::any_of(remaining.begin() + 2, remaining.end(), [](bool used){return used;}))
        return {false, L"Не удалось проверить удаление пользовательских слотов. Форматирование не начато. " + result.message};

    // One format write, then separate read commands. Never replay the write.
    Command format{transaction, 0x06, 0x0a, 6};
    format.args[3] = 2;
    result = send(format, reply);
    if (!result.ok)
        return {false, L"Мышь не подтвердила команду форматирования. Память могла измениться. " + result.message};
    query.args[3] = 2;
    constexpr std::array<Byte, 6> completed{0, 0, 2, 2, 0, 0};
    bool finished = false;
    for (int i = 0; i < 20; ++i) {
        std::this_thread::sleep_for(std::chrono::milliseconds(100));
        result = send(query, reply);
        if (!result.ok)
            return {false, L"Команда отправлена, но состояние форматирования не удалось прочитать. " + result.message};
        if (reply.size == completed.size() && std::equal(completed.begin(), completed.end(), reply.args.begin())) {
            finished = true;
            break;
        }
    }
    if (!finished) return {false, L"Мышь не подтвердила завершение форматирования. Команда повторно не отправлялась."};

    result = profiles(send, remaining);
    if (!result.ok || std::any_of(remaining.begin() + 2, remaining.end(), [](bool used){return used;}))
        return {false, L"Мышь завершила форматирование, но итоговый список слотов не подтверждён. " + result.message};
    return {true, L"Мышь подтвердила форматирование памяти. Повторное чтение обнаружило только базовый слот 1."};
}

} // namespace

Result readOnboardSlots(std::array<bool, 6>& slots) {
    return withMouse([&](const Exchange& send) {
        Slots current{};
        auto result = profiles(send, current);
        if (result.ok) slots = current;
        return result;
    });
}

Result formatOnboardMemory() { return withMouse(resetStorage); }

} // namespace viper
