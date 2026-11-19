#pragma once

#include <windows.h>
#include <string>
#include "profile.h"

HWND CreateDevicePage(HWND parent, HINSTANCE instance, bool lighting);
void LoadDevicePage(HWND page, const MouseProfile& profile);
bool ReadDevicePage(HWND page, MouseProfile& profile, std::wstring& error);
