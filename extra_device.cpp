#include "extra_device.h"
#include "transport.h"

#include <algorithm>
#include <array>
#include <initializer_list>

namespace viper {
namespace {

using Mode = CalibrationMode;
using EightBytes = std::array<Byte, 8>;

struct Preset {
    Mode mode;
    int lift;
    int land;
    EightBytes data;
};

// Successful Synapse transactions for PID 0091. The levels are unitless.
// https://github.com/openrazer/openrazer/issues/1426#issuecomment-877648691
constexpr Preset presets[]{
    {Mode::Preset, 3, 3, {0x2a, 0x30, 0x0b, 0x08, 0x0b, 0x05, 0x0f, 0x0a}},
    {Mode::Preset, 4, 4, {0x25, 0x30, 0x0e, 0x08, 0x0e, 0x05, 0x0f, 0x0a}},
    {Mode::Preset, 5, 5, {0x20, 0x30, 0x11, 0x08, 0x11, 0x05, 0x0f, 0x0a}},
    {Mode::Preset, 7, 7, {0x16, 0x38, 0x17, 0x08, 0x17, 0x00, 0x0e, 0x08}},
    {Mode::PresetAsymmetric, 4, 3, {0x25, 0x30, 0x0e, 0x88, 0x0e, 0x0f, 0x0f, 0x0a}},
    {Mode::PresetAsymmetric, 7, 3, {0x16, 0x38, 0x17, 0x88, 0x17, 0x00, 0x0e, 0x08}},
    {Mode::PresetAsymmetric, 8, 3, {0x11, 0x38, 0x1a, 0x88, 0x1a, 0x00, 0x0e, 0x08}}
};
constexpr std::array<Byte, 5> landingLevel3{0x2a, 0x30, 0x0b, 0x0b, 0x0a};

const Preset* presetFor(const Calibration& value) {
    for (const auto& preset : presets) {
        if (value.mode == preset.mode && value.lift == preset.lift && value.land == preset.land)
            return &preset;
    }
    return nullptr;
}

Command sensor(Byte id, Byte size) {
    Command cmd{0x1f, 0x0b, id, size};
    cmd.args[1] = 0x04; // Sensor addressing prefix in the 0091 captures.
    return cmd;
}

Result readSensor(const Exchange& send, Byte id, Byte size, Command& reply) {
    const Command req = sensor(id, size);
    auto result = send(req, reply);
    if (result.ok && (reply.size != size || reply.args[0] != 0 || reply.args[1] != 4))
        return {false, L"Сенсор вернул неизвестный формат ответа."};
    return result;
}

Result writeSensor(const Exchange& send, const Command& request) {
    Command ack{};
    auto result = send(request, ack);
    if (result.ok && (ack.size != request.size ||
                      !std::equal(request.args.begin(), request.args.begin() + request.size,
                                  ack.args.begin())))
        return {false, L"Мышь не подтвердила параметры команды калибровки."};
    return result;
}

// Read shape and Smart encodings corroborated for Focus+ by these captures:
// https://github.com/openrazer/openrazer/issues/783#issuecomment-651574555
// https://github.com/geezmolycos/razerqdhid/blob/main/docs/cmd_sensor-en.md
struct SensorMode { Byte enabled, mode, index; };

Result readMode(const Exchange& send, SensorMode& out) {
    Command state{}, mode{};
    auto result = readSensor(send, 0x83, 3, state);
    if (!result.ok) return result;
    result = readSensor(send, 0x8b, 4, mode);
    if (!result.ok) return result;
    out = {state.args[2], mode.args[2], mode.args[3]};
    // Requiring a recognized, nonzero mode also rules out a device simply
    // echoing the zero-filled GET. Unknown firmware must get no Smart writes.
    if ((out.enabled == 0 && (out.mode == 1 || out.mode == 2) && out.index < 3) ||
        (out.enabled == 1 && out.mode >= 3 && out.mode <= 6 && out.index == 0))
        return {true, {}};
    return {false, L"Мышь не подтвердила известный режим сенсора Focus+."};
}

constexpr std::array<Calibration, 3> asymmetricSmart{{
    {Mode::SmartAsymmetric, 2, 1}, {Mode::SmartAsymmetric, 3, 1},
    {Mode::SmartAsymmetric, 3, 2}
}};

bool isSmart(Mode mode) { return mode == Mode::Smart || mode == Mode::SmartAsymmetric; }

SensorMode encoding(const Calibration& value) {
    if (value.mode == Mode::Smart) return {0, 1, static_cast<Byte>(value.lift - 1)};
    if (value.mode == Mode::SmartAsymmetric) {
        for (Byte i = 0; i < asymmetricSmart.size(); ++i) {
            if (value.lift == asymmetricSmart[i].lift && value.land == asymmetricSmart[i].land)
                return {0, 2, i};
        }
    }
    return {1, static_cast<Byte>(value.mode == Mode::Preset ? 3 : 4), 0};
}

Result readValue(const Exchange& send, Calibration& out) {
    SensorMode mode{};
    auto result = readMode(send, mode);
    if (!result.ok) return result;
    if (mode.mode == 1) {
        out = {Mode::Smart, mode.index + 1, mode.index + 1};
    } else if (mode.mode == 2) {
        out = asymmetricSmart[mode.index];
    } else if (mode.mode == 4) {
        Command land{}, lift{};
        result = readSensor(send, 0x8c, 7, land);
        if (!result.ok) return result;
        result = readSensor(send, 0x8d, 10, lift);
        if (!result.ok) return result;
        if (std::equal(landingLevel3.begin(), landingLevel3.end(), land.args.begin() + 2)) {
            for (const auto& p : presets) {
                if (p.mode == Mode::PresetAsymmetric &&
                    std::equal(p.data.begin(), p.data.end(), lift.args.begin() + 2)) {
                    out = {p.mode, p.lift, p.land};
                    return {true, L"Расстояния отрыва и посадки прочитаны из мыши."};
                }
            }
        }
        return {false, L"Мышь использует асимметричные уровни вне доступного набора."};
    } else if (mode.mode == 3) {
        // 0b/85 reads acquisition data, not the table written with 0b/05.
        return {false, L"Мышь сообщает о ручном пресете. Его симметричный уровень нельзя считать отдельно."};
    } else {
        return {false, L"На мыши активна индивидуальная калибровка поверхности."};
    }
    return {true, L"Расстояния отслеживания прочитаны из мыши."};
}

Result setValue(const Exchange& send, const Calibration& value) {
    const bool smart = isSmart(value.mode);
    const auto target = encoding(value);
    if (smart) {
        SensorMode current{};
        auto result = readMode(send, current);
        if (!result.ok)
            return {false, L"Smart Tracking требует распознаваемого ответа сенсора. " + result.message};
        if (current.enabled == target.enabled && current.mode == target.mode && current.index == target.index)
            return {true, L"Выбранные расстояния Smart Tracking уже действуют."};
    }

    Command enable = sensor(0x03, 3);
    enable.args[2] = target.enabled;
    auto result = writeSensor(send, enable);
    if (result.ok && !smart)
        result = writeSensor(send, enable); // Repeated in every captured manual sequence.
    Command mode = sensor(0x0b, 4);
    mode.args[2] = target.mode;
    mode.args[3] = target.index;
    if (result.ok) result = writeSensor(send, mode);
    if (result.ok && !smart) {
        const auto& preset = *presetFor(value); // Input validated by applyCalibration.
        if (value.mode == Mode::PresetAsymmetric) {
            Command land = sensor(0x0c, 7);
            std::copy(landingLevel3.begin(), landingLevel3.end(), land.args.begin() + 2);
            result = writeSensor(send, land);
        }
        if (result.ok) {
            Command lift = sensor(value.mode == Mode::Preset ? 0x05 : 0x0d, 10);
            std::copy(preset.data.begin(), preset.data.end(), lift.args.begin() + 2);
            result = writeSensor(send, lift);
        }
    }
    if (!result.ok)
        return {false, L"Последовательность калибровки могла примениться частично. " + result.message};
    if (smart) {
        SensorMode actual{};
        result = readMode(send, actual);
        if (!result.ok || actual.enabled != target.enabled || actual.mode != target.mode || actual.index != target.index)
            return {false, L"Команды отправлены, но чтение из сенсора не подтвердило выбранные расстояния. " + result.message};
        return {true, L"Smart Tracking применён и проверен чтением из сенсора. Настройка действует до отключения мыши."};
    }
    return {true, L"Мышь подтвердила все команды ручного пресета. Настройка действует до отключения мыши."};
}

} // namespace

bool validCalibration(const Calibration& value) {
    if (value.mode == Mode::Smart)
        return value.lift >= 1 && value.lift <= 3 && value.lift == value.land;
    if (value.mode == Mode::SmartAsymmetric)
        return value.land >= 1 && value.lift <= 3 && value.land < value.lift;
    return presetFor(value) != nullptr;
}

Result readCalibration(Calibration& value) {
    return withMouse([&](const Exchange& send) { return readValue(send, value); });
}

Result applyCalibration(const Calibration& value) {
    if (!validCalibration(value)) return {false, L"Эта пара расстояний калибровки не поддерживается."};
    return withMouse([&](const Exchange& send) { return setValue(send, value); });
}

} // namespace viper
