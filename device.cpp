#include "transport.h"

#include <algorithm>

namespace viper {
namespace {

constexpr Byte stored = 1, logo = 4;
constexpr int rates[] = {125, 500, 1000, 2000, 4000, 8000};

bool validRate(int hz) {
    return std::find(std::begin(rates), std::end(rates), hz) != std::end(rates);
}
bool validDpi(int value) { return value >= 100 && value <= 20000; }
bool validStages(const Performance& value) {
    if (value.count < 1 || value.count > 5 || value.active < 1 || value.active > value.count) return false;
    for (int i = 0; i < value.count; ++i)
        if (!validDpi(value.x[i]) || !validDpi(value.y[i])) return false;
    return true;
}
bool sameStages(const Performance& a, const Performance& b) {
    return a.count == b.count && a.active == b.active &&
           std::equal(a.x.begin(), a.x.begin() + a.count, b.x.begin()) &&
           std::equal(a.y.begin(), a.y.begin() + a.count, b.y.begin());
}

int get16(const Command& packet, int at) {
    return (static_cast<int>(packet.args[at]) << 8) | packet.args[at + 1];
}
void put16(Command& packet, int at, int value) {
    packet.args[at] = static_cast<Byte>(value >> 8);
    packet.args[at + 1] = static_cast<Byte>(value);
}
void putColor(Command& packet, int at, unsigned color) {
    packet.args[at] = static_cast<Byte>(color >> 16);
    packet.args[at + 1] = static_cast<Byte>(color >> 8);
    packet.args[at + 2] = static_cast<Byte>(color);
}

Result explain(const wchar_t* context, const Result& error) {
    return {false, std::wstring(context) + L" " + error.message};
}

Result fetchStages(const Exchange& send, Performance& value) {
    Command reply{};
    auto r = send({0xff, 0x04, 0x86, 0x26, {stored}}, reply);
    if (!r.ok) return explain(L"Чтение таблицы DPI.", r);
    Performance read = value;
    read.active = reply.args[1];
    read.count = reply.args[2];
    if (reply.size < 3 || read.count < 1 || read.count > 5 || reply.size < 1 + read.count * 7)
        return {false, L"Мышь вернула неполную таблицу DPI."};
    for (int i = 0; i < read.count; ++i) {
        read.x[i] = get16(reply, 4 + 7 * i);
        read.y[i] = get16(reply, 6 + 7 * i);
    }
    if (!validStages(read)) return {false, L"Мышь вернула неизвестные значения уровней DPI."};
    value = read;
    return {true, {}};
}

Result fetchRate(const Exchange& send, int& hz) {
    Command reply{};
    auto r = send({0x1f, 0x00, 0xc0, 0x01}, reply);
    if (!r.ok) return explain(L"Чтение частоты опроса.", r);
    // The GET request declares one byte, but this model returns the divisor in argument 1.
    for (int candidate : rates) {
        if (reply.size >= 1 && reply.args[1] == 8000 / candidate) {
            hz = candidate;
            return {true, {}};
        }
    }
    return {false, L"Мышь вернула неизвестный код частоты опроса."};
}

Result fetchDpi(const Exchange& send, int& x, int& y) {
    Command reply{};
    auto r = send({0xff, 0x04, 0x85, 7, {0}}, reply);
    if (!r.ok) return explain(L"Чтение текущего DPI.", r);
    int liveX = get16(reply, 1), liveY = get16(reply, 3);
    if (reply.size < 5 || !validDpi(liveX) || !validDpi(liveY))
        return {false, L"Мышь вернула некорректное текущее DPI."};
    x = liveX;
    y = liveY;
    return {true, {}};
}

Result applyDpi(const Exchange& send, int x, int y) {
    Command cmd{0xff, 0x04, 0x05, 7, {stored}}, reply{};
    put16(cmd, 1, x);
    put16(cmd, 3, y);
    auto r = send(cmd, reply);
    if (!r.ok) return explain(L"Мышь не подтвердила запись текущего DPI.", r);
    int actualX = 0, actualY = 0;
    r = fetchDpi(send, actualX, actualY);
    if (!r.ok) return explain(L"Команда DPI принята. Проверка чтением не завершена.", r);
    if (actualX != x || actualY != y) {
        return {false, L"После записи мышь вернула DPI X " + std::to_wstring(actualX) +
                       L", Y " + std::to_wstring(actualY) + L"."};
    }
    return {true, L"Текущее DPI подтверждено чтением из мыши."};
}

Result applyStages(const Exchange& send, const Performance& value) {
    Command cmd{0xff, 0x04, 0x06, 0x26, {stored}}, reply{};
    cmd.args[1] = static_cast<Byte>(value.active);
    cmd.args[2] = static_cast<Byte>(value.count);
    for (int i = 0; i < value.count; ++i) {
        const int at = 3 + 7 * i;
        cmd.args[at] = static_cast<Byte>(i);
        put16(cmd, at + 1, value.x[i]);
        put16(cmd, at + 3, value.y[i]);
    }
    auto r = send(cmd, reply);
    if (!r.ok) return explain(L"Запись таблицы DPI не подтверждена.", r);
    Performance check;
    r = fetchStages(send, check);
    if (!r.ok) return explain(L"Команда записи уровней принята. Проверка чтением не завершена.", r);
    if (!sameStages(check, value)) return {false, L"Прочитанная из памяти таблица DPI отличается от отправленной."};
    int x = 0, y = 0;
    r = fetchDpi(send, x, y);
    if (!r.ok) return explain(L"Уровни в памяти подтверждены. Не удалось проверить текущий DPI.", r);
    const int stage = value.active - 1;
    if (x != value.x[stage] || y != value.y[stage]) {
        r = applyDpi(send, value.x[stage], value.y[stage]);
        if (!r.ok) return explain(L"Уровни записаны. Не удалось применить активный DPI.", r);
        // Some firmware couples live X/Y and the active record. Verify both after the last write.
        r = fetchStages(send, check);
        if (!r.ok) return explain(L"Текущее DPI применено. Повторная проверка таблицы не завершена.", r);
        if (!sameStages(check, value)) return {false, L"После изменения текущего DPI таблица мыши изменилась."};
    }
    return {true, L"Уровни в памяти мыши и текущий DPI подтверждены чтением."};
}

Result fetchBrightness(const Exchange& send, Byte& value) {
    Command reply{};
    auto r = send({0x1f, 0x0f, 0x84, 3, {stored, logo}}, reply);
    if (!r.ok) return explain(L"Чтение яркости.", r);
    if (reply.size < 3) return {false, L"Ответ мыши не содержит значения яркости."};
    value = reply.args[2];
    return {true, {}};
}

Command makeEffect(const Lighting& value) {
    Command cmd{0x1f, 0x0f, 0x02, 6, {stored, logo}};
    int colors = 0;
    switch (value.effect) {
    case Effect::Off: break;
    case Effect::Static: cmd.args[2] = 1; colors = 1; break;
    case Effect::Spectrum: cmd.args[2] = 3; break;
    case Effect::BreathRandom: cmd.args[2] = 2; break;
    case Effect::BreathOne: cmd.args[2] = 2; cmd.args[3] = 1; colors = 1; break;
    case Effect::BreathTwo: cmd.args[2] = 2; cmd.args[3] = 2; colors = 2; break;
    case Effect::Reactive:
        cmd.args[2] = 5;
        cmd.args[4] = static_cast<Byte>(value.speed);
        colors = 1;
        break;
    }
    cmd.args[5] = static_cast<Byte>(colors);
    cmd.size = static_cast<Byte>(6 + colors * 3);
    if (colors >= 1) putColor(cmd, 6, value.color1);
    if (colors == 2) putColor(cmd, 9, value.color2);
    return cmd;
}

} // namespace

Result probe() {
    return withMouse([](const Exchange&) -> Result { return {true, L"Razer Viper 8KHz подключена."}; });
}
Result readCurrentDpi(int& x, int& y) {
    return withMouse([&](const Exchange& send) { return fetchDpi(send, x, y); });
}
Result writeCurrentDpi(int x, int y) {
    if (!validDpi(x) || !validDpi(y)) return {false, L"Укажите DPI от 100 до 20 000 для каждой оси."};
    return withMouse([&](const Exchange& send) { return applyDpi(send, x, y); });
}
Result readStages(Performance& out) {
    return withMouse([&](const Exchange& send) { return fetchStages(send, out); });
}
Result readPerformance(Performance& out) {
    return withMouse([&](const Exchange& send) -> Result {
        Performance value = out;
        auto r = fetchStages(send, value);
        if (!r.ok) return r;
        r = fetchRate(send, value.hz);
        if (!r.ok) return r;
        out = value;
        return {true, L"Уровни DPI, активный уровень и частота прочитаны из мыши."};
    });
}
Result writeStages(const Performance& value) {
    if (!validStages(value)) return {false, L"Проверьте значения и активный уровень DPI."};
    return withMouse([&](const Exchange& send) { return applyStages(send, value); });
}
Result writePerformance(const Performance& value) {
    if (!validRate(value.hz) || !validStages(value)) return {false, L"Проверьте уровни DPI и частоту опроса."};
    return withMouse([&](const Exchange& send) -> Result {
        auto r = applyStages(send, value);
        if (!r.ok) return r;

        // Both passes, including transaction 0x1f for each, are present in Synapse traces
        // on the physical 0091 (OpenRazer issue 1426, Captures.zip).
        Command cmd{0x1f, 0x00, 0x40, 2, {0, static_cast<Byte>(8000 / value.hz)}}, reply{};
        r = send(cmd, reply);
        if (!r.ok) return explain(L"DPI записан. Первая команда частоты не подтверждена.", r);
        cmd.args[0] = 1;
        r = send(cmd, reply);
        if (!r.ok) return explain(L"DPI записан. Вторая команда частоты не подтверждена.", r);
        int actual = 0;
        r = fetchRate(send, actual);
        if (!r.ok) return explain(L"DPI записан. Команды частоты приняты, проверка не завершена.", r);
        if (actual != value.hz)
            return {false, L"DPI записан. Мышь вернула частоту " + std::to_wstring(actual) + L" Гц."};
        return {true, L"Уровни DPI записаны в память мыши. Текущий DPI и частота подтверждены чтением."};
    });
}
Result readBrightness(int& percent) {
    return withMouse([&](const Exchange& send) -> Result {
        Byte value = 0;
        auto r = fetchBrightness(send, value);
        if (r.ok) percent = (value * 100 + 127) / 255;
        return r;
    });
}
Result writeLighting(const Lighting& value) {
    if (value.brightness < 0 || value.brightness > 100 || value.speed < 1 || value.speed > 3 ||
        value.color1 > 0xffffff || value.color2 > 0xffffff ||
        value.effect < Effect::Off || value.effect > Effect::Reactive)
        return {false, L"Проверьте параметры подсветки."};
    return withMouse([&](const Exchange& send) -> Result {
        Command reply{};
        auto r = send(makeEffect(value), reply);
        if (!r.ok) return explain(L"Эффект не подтверждён мышью.", r);
        Byte brightness = static_cast<Byte>((value.brightness * 255 + 50) / 100);
        r = send({0x1f, 0x0f, 0x04, 3, {stored, logo, brightness}}, reply);
        if (!r.ok) return explain(L"Мышь приняла эффект. Яркость не подтверждена.", r);
        Byte check = 0;
        r = fetchBrightness(send, check);
        if (!r.ok) return explain(L"Мышь приняла настройки подсветки. Проверка яркости не завершена.", r);
        if (check != brightness) return {false, L"Мышь приняла эффект, но прочитанная яркость отличается."};
        return {true, L"Мышь приняла эффект подсветки. Яркость подтверждена чтением."};
    });
}

} // namespace viper
