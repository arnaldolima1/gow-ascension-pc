#pragma once
#include <cstdint>

namespace ascension::texstream
{
// BCES01741 1.00: func_00366C24 passes this word in r10 to
// func_003B37C0, which atomically adds (job_count << 16).
inline constexpr std::uint32_t counter_address = 0x00967024;
inline constexpr std::uint32_t legacy_counter_address = 0x00967028;
inline constexpr std::uint32_t table_pointer_address = 0x0096E174;

// Shared by the production guard and the deterministic delayed-job regression.
// A failed wait must never authorize a write to the shared streaming table.
template<class ReadPending, class Clock, class Pause>
bool wait_idle(ReadPending read_pending, Clock clock, Pause pause, std::uint64_t timeout_us)
{
    const auto start = clock();
    unsigned turns = 0;
    while (read_pending())
    {
        if (clock() - start >= timeout_us)
            return false;
        pause(++turns);
    }
    return true;
}
}
