#pragma once

#include "device.h"

namespace viper {

enum class CalibrationMode { Smart, SmartAsymmetric, Preset, PresetAsymmetric };
struct Calibration {
    CalibrationMode mode = CalibrationMode::Smart;
    int lift = 2;
    int land = 2;
};

bool validCalibration(const Calibration& settings);
Result readCalibration(Calibration& settings);
Result applyCalibration(const Calibration& settings);

} // namespace viper
