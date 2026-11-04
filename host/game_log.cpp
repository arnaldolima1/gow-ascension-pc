// The game's own debug printf (func_001B16E4, stripped in the retail build: it
// only spills its varargs) printed when GOWA_GAMELOG=1. Lifted as
// ps3_hle_call(0xA0C0DE01) through tools/ppu_hle_hooks.json (ppu_lifter
// --hle-hooks). Its callers pass (level r3, format r4, args r5...): the online
// configuration readers' "Parse error: ..." / "error in retrieving %s" lines,
// which say exactly which TSS field is missing or wrong (ascension-online SPEC
// 2.8). Integer and pointer arguments come from r5-r10 and then the caller's
// parameter save area; %f from f1 onward.
#include "ppu_recomp.h"
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>

extern "C" void ps3_hle_register_ctx(uint32_t nid, const char* name, void (*fn)(ppu_context*));

namespace {

std::string guest_str(uint32_t ea, size_t max = 256)
{
    std::string s;
    if (!ea) return "(null)";
    for (size_t i = 0; i < max; i++) {
        const char c = (char)vm_read8(ea + i);
        if (!c) break;
        s += c;
    }
    return s;
}

void game_log(ppu_context* ctx)
{
    static const bool on = [] { const char* e = std::getenv("GOWA_GAMELOG"); return e && *e && *e != '0'; }();
    if (!on) return;
    const std::string fmt = guest_str((uint32_t)ctx->gpr[4], 512);
    int gi = 5, fi = 1;
    const uint64_t sp = ctx->gpr[1];
    auto next_int = [&]() -> uint64_t {
        if (gi <= 10) return ctx->gpr[gi++];
        // parameter save area: arg n (0-based) at sp + 0x30 + 8*n; r5 is arg 2
        const uint64_t v = vm_read64((uint32_t)(sp + 0x30 + 8 * (uint64_t)(gi - 3)));
        gi++;
        return v;
    };
    std::string out;
    for (size_t i = 0; i < fmt.size(); i++) {
        if (fmt[i] != '%') { out += fmt[i]; continue; }
        size_t j = i + 1;
        std::string spec = "%";
        while (j < fmt.size() && std::strchr("-+ #0123456789.", fmt[j])) spec += fmt[j++];
        std::string len;
        while (j < fmt.size() && std::strchr("hlLqjzt", fmt[j])) len += fmt[j++];
        if (j >= fmt.size()) break;
        const char conv = fmt[j];
        char buf[512];
        switch (conv) {
        case '%': out += '%'; break;
        case 's': std::snprintf(buf, sizeof buf, (spec + "s").c_str(), guest_str((uint32_t)next_int()).c_str()); out += buf; break;
        case 'c': out += (char)next_int(); break;
        case 'd': case 'i': {
            const uint64_t v = next_int();
            std::snprintf(buf, sizeof buf, (spec + "lld").c_str(), len.find('l') != std::string::npos ? (long long)v : (long long)(int32_t)v);
            out += buf; break; }
        case 'u': case 'x': case 'X': case 'o': {
            const uint64_t v = next_int();
            std::snprintf(buf, sizeof buf, (spec + "ll" + conv).c_str(), len.find('l') != std::string::npos ? (unsigned long long)v : (unsigned long long)(uint32_t)v);
            out += buf; break; }
        case 'p': std::snprintf(buf, sizeof buf, "0x%08llx", (unsigned long long)(uint32_t)next_int()); out += buf; break;
        case 'f': case 'g': case 'e': {
            const double v = fi <= 13 ? ctx->fpr[fi++] : 0.0;
            next_int();   // a double vararg also takes a GPR / save-area slot
            std::snprintf(buf, sizeof buf, (spec + conv).c_str(), v);
            out += buf; break; }
        default: out += spec + len + conv; break;
        }
        i = j;
    }
    while (!out.empty() && (out.back() == '\n' || out.back() == '\r')) out.pop_back();
    std::fprintf(stderr, "[gamelog] %s\n", out.c_str());
}

struct Register {
    Register() { ps3_hle_register_ctx(0xA0C0DE01u, "game_debug_printf", game_log); }
} s_register;

} // namespace
