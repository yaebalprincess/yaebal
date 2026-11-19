#pragma once
#include <windows.h>

// The parent owns this initially hidden WS_CHILD page. Position it in client pixels.
HWND CreateWindowsTab(HWND parent, HINSTANCE instance);
void ResizeWindowsTab(HWND tab, int x, int y, int width, int height);
// Reloads current Windows settings and replaces the edits on this page.
void RefreshWindowsTab(HWND tab);
