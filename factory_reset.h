#pragma once
#include "device.h"

namespace viper {
Result readOnboardSlots(std::array<bool, 6>& slots);
// Call only after the user confirms erasure of onboard profiles and macros.
Result formatOnboardMemory();
}
