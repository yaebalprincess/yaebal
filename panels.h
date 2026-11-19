#pragma once
#include <windows.h>
#include "profile.h"
#include <optional>
#include <utility>

enum class Panel { Setup, Calibration, Memory };
struct MouseSnapshot {
    std::optional<viper::Performance> stages;
    bool rateKnown=false;
    std::optional<std::array<bool,6>> slots;
    std::optional<std::pair<int,int>> current;
};
enum LocalCommand { CmdRead = 400, CmdReadCurrent, CmdSetCurrent, CmdRestore, CmdGuide, CmdSynapse, CmdLoad, CmdSave, CmdApply, CmdFormat };
HWND CreatePanel(HWND parent, Panel kind);
std::wstring ProfileName(HWND setup);
void SetProfileName(HWND setup, const std::wstring& name);
void SetCalibrationPage(HWND page, const viper::Calibration& cal);
viper::Calibration GetCalibrationPage(HWND page);
void ShowMemory(HWND page, const MouseSnapshot& mouse, const viper::Performance* draft, bool copyCurrent);
bool GetCurrentFields(HWND page,int& x,int& y);
void OpenSynapse(HWND parent);
