#pragma once

#include "device.h"
#include <functional>

namespace viper {

using Byte = unsigned char;
struct Command {
    Byte transaction, group, id, size;
    std::array<Byte, 80> args{};
};
using Exchange = std::function<Result(const Command&, Command&)>;

// Shares one device handle and one cross-process lock for a complete operation.
// The callback must finish before the handle and lock are released.
Result withMouse(const std::function<Result(const Exchange&)>& operation);

} // namespace viper
