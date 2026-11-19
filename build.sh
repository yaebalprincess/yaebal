#!/usr/bin/env bash
# Build a portable 64-bit Windows executable using MinGW-w64 on Linux.
set -euo pipefail
source_dir=$(cd -- "$(dirname -- "$0")" && pwd)
build_dir=${1:-"$source_dir/../build"}
mkdir -p -- "$build_dir"
build_dir=$(cd -- "$build_dir" && pwd)
cd -- "$source_dir"

compiler=${CXX:-x86_64-w64-mingw32-g++}
resource_compiler=${WINDRES:-x86_64-w64-mingw32-windres}
for tool in "$compiler" "$resource_compiler"; do
    if ! command -v "$tool" >/dev/null; then
        echo "Install MinGW-w64 with the x86_64 Windows C++ compiler and binutils." >&2
        exit 1
    fi
done

"$resource_compiler" --codepage=65001 -DUNICODE -D_UNICODE app.rc -O coff -o "$build_dir/app.res"
sources=(./*.cpp)
"$compiler" -std=c++17 -Os -DNDEBUG -DUNICODE -D_UNICODE -DWIN32_LEAN_AND_MEAN \
    -D_WIN32_WINNT=0x0A00 -Wall -Wextra -ffunction-sections -fdata-sections \
    -municode -mwindows -static -s -Wl,--gc-sections,--no-insert-timestamp \
    "${sources[@]}" "$build_dir/app.res" \
    -lcomctl32 -lcomdlg32 -lhid -lsetupapi -luxtheme -ldwmapi -lshell32 -lshlwapi \
    -ladvapi32 -lole32 -luuid -lgdi32 -luser32 -o "$build_dir/ViperControl.exe"
