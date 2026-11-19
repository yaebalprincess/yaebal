#pragma once

#include "device.h"
#include "extra_device.h"
#include <string>

struct MouseProfile {
    std::wstring name = L"Мой профиль";
    viper::Performance performance;
    viper::Lighting lighting;
    viper::Calibration calibration;
};

// Read a complete, validated profile before modifying the caller's state.
bool LoadMouseProfile(const std::wstring& path, MouseProfile& profile, std::wstring& error);
// Write a UTF-8 text file using a temporary sibling and a single replacement.
bool SaveMouseProfile(const std::wstring& path, const MouseProfile& profile, std::wstring& error);
