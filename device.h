#pragma once

#include <array>
#include <string>

namespace viper {

struct Performance {
    int count = 5;
    int active = 3; // Physical stage numbers start at 1.
    std::array<int, 5> x{400, 800, 1600, 2400, 3200};
    std::array<int, 5> y{400, 800, 1600, 2400, 3200};
    int hz = 8000;
};

enum class Effect { Off, Static, Spectrum, BreathOne, BreathTwo, BreathRandom, Reactive };

struct Lighting {
    Effect effect = Effect::Static;
    unsigned color1 = 0x44d62c;
    unsigned color2 = 0x00aaff;
    int brightness = 70;
    int speed = 2;
};

struct Result {
    bool ok;
    std::wstring message;
};

Result probe();
Result readStages(Performance& out);
Result readPerformance(Performance& out);
Result writePerformance(const Performance& value);
Result writeStages(const Performance& value);
Result readCurrentDpi(int& x, int& y);
Result writeCurrentDpi(int x, int y);
Result readBrightness(int& percent);
Result writeLighting(const Lighting& value);

} // namespace viper
