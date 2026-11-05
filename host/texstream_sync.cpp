// Restore the PPU/SPU streaming-table handoff for BCES01741 1.00.
// Related diagnosis (different executable/addresses):
// https://github.com/otavix010/gow-ascension-pc/blob/main/port/gowa_offline.cpp
// Addresses and sites here are checked against this port's own generated code.
#include "ppu_recomp.h"
#include "texstream_sync.h"
#include <atomic>
#include <cstdio>
#include <cstdlib>
#include <thread>
#if defined(_M_X64) || defined(__x86_64__)
#include <immintrin.h>
#endif

extern "C" unsigned long long ps3_qpc_us(void);

namespace
{
std::uint32_t load_word(std::uint32_t address)
{
    auto& word = *reinterpret_cast<std::uint32_t*>(vm_base + address);
    return __builtin_bswap32(std::atomic_ref<std::uint32_t>(word).load(std::memory_order_acquire));
}

bool enabled()
{
    static const bool on = [] {
        // On with GOWA_TEXSTREAM_SYNC=1 (host/ascension_defaults.cpp sets it once
        // validated); =0 or unset: the original waits, for a bisection.
        const char* value = std::getenv("GOWA_TEXSTREAM_SYNC");
        const bool active = value && value[0] == '1';
        std::fprintf(stderr, "[texstream-sync] %s; BCES01741 1.00 counter=00967024 legacy=00967028\n",
            active ? "enabled" : "disabled");
        return active;
    }();
    return on;
}
}

extern "C" void ascension_texstream_wait(ppu_context* ctx, std::uint32_t site)
{
    using namespace ascension::texstream;
    if (!enabled() || !vm_base)
        return;
    const auto pending = load_word(counter_address) >> 16;
    if (!pending)
        return;

    const auto legacy = load_word(legacy_counter_address) >> 16;
    const auto start = ps3_qpc_us();
    const bool completed = wait_idle(
        [] { return load_word(counter_address) >> 16; },
        [] { return ps3_qpc_us(); },
        [](unsigned turns) {
#if defined(_M_X64) || defined(__x86_64__)
            if (turns < 128) { _mm_pause(); return; }
#endif
            std::this_thread::yield();
        },
        2000000);

    if (!completed)
    {
        // Continuing here would knowingly allow the original table overwrite.
        // Stop with the actual counter/site, rather than conceal the hang.
        std::fprintf(stderr, "[texstream-sync] TIMEOUT site=%08X lr=%08X pending=%u legacy=%u table=%08X\n",
            site, ctx ? static_cast<unsigned>(ctx->lr) : 0,
            load_word(counter_address) >> 16, load_word(legacy_counter_address) >> 16,
            load_word(table_pointer_address));
        std::fflush(stderr);
        std::abort();
    }

    static std::atomic<unsigned> reports{0};
    if (reports.fetch_add(1, std::memory_order_relaxed) < 32)
    {
        std::fprintf(stderr, "[texstream-sync] site=%08X lr=%08X pending=%u legacy=%u waited=%llu us table=%08X\n",
            site, ctx ? static_cast<unsigned>(ctx->lr) : 0, pending, legacy,
            ps3_qpc_us() - start, load_word(table_pointer_address));
    }
}
