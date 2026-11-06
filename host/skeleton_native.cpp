// func_002A434C natively, the one function of the main PPU thread's own work
// that stands out (6.4 % of it, the rest is flat; ps3kit docs/ASCENSION_PERF.md).
// It walks a skeleton: for each bone, parent matrix x local matrix, 16 vmaddfp.
// The lifted form swaps the bytes of three operands and of the result on every
// vmaddfp; here a matrix is converted once.
//
// r3 the skeleton (+0x04 the bone table, 8 bytes each: +0 flags, +2 first bone,
// +6 parent; +0x14 the bone count, +0x28 a byte per bone, +0x2C flags), r4 the
// output matrices, r5 the local ones, r6 the root, r7 nonzero: every bone.
//
// GOWA_SKEL_NATIVE=1 turns it on (follows CAUSAL_TOGGLE_S). Off, on a target
// that is not x86 or with VSCR.NJ set (600 of 600 calls in the level have it clear), the lift runs: tools/ppu_native_gates.json
// puts gowa_skel_gate at its entry. What differs from the lift on return:
// the volatile registers, and the guest stack below r1 unless a bone's flags call
// func_002A2290. Proved by tools/test_skel_native.sh against the lift.
//
// GOWA_SKEL_CAP=<file>[,<max>[,<every>]] records calls for that test.
#include "ppu_recomp.h"
#include "ps3emu/causal_gate.h"
#include <cstdio>
#include <cstdlib>
#include <cstring>

#if (defined(__x86_64__) || defined(_M_X64)) && (defined(__clang__) || defined(__GNUC__))
#define SKEL_X86 1
#include <immintrin.h>

void func_002A2290(ppu_context* ctx);
extern "C" PPU_THREAD_LOCAL void (*g_trampoline_fn)(void*);

namespace {

#define SK_FN static inline __attribute__((always_inline, target("sse4.1,fma")))

SK_FN __m128i sk_bs(__m128i v)
{
    return _mm_shuffle_epi8(v, _mm_set_epi8(12, 13, 14, 15, 8, 9, 10, 11, 4, 5, 6, 7, 0, 1, 2, 3));
}
SK_FN __m128i sk_load(uint32_t ea)
{
    return sk_bs(_mm_load_si128((const __m128i*)(vm_base + (ea & ~15u))));
}
SK_FN void sk_store(uint32_t ea, __m128i v)
{
    _mm_store_si128((__m128i*)(vm_base + (ea & ~15u)), sk_bs(v));
}
// vmaddfp with VSCR.NJ clear: a * c + b, one rounding, a NaN result the default NaN
SK_FN __m128 sk_madd(__m128 a, __m128 c, __m128 b)
{
    __m128i r = _mm_castps_si128(_mm_fmadd_ps(a, c, b));
    const __m128i nan = _mm_cmpgt_epi32(_mm_and_si128(r, _mm_set1_epi32(0x7FFFFFFF)), _mm_set1_epi32(0x7F800000));
    r = _mm_blendv_epi8(r, _mm_set1_epi32(0x7FC00000), nan);
    return _mm_castsi128_ps(r);
}
// parent p x a row of the local matrix, in the lift's order
SK_FN __m128i sk_row(const __m128 p[4], __m128i l)
{
    __m128 r = sk_madd(p[0], _mm_castsi128_ps(_mm_shuffle_epi32(l, 0x00)), _mm_setzero_ps());
    r = sk_madd(p[1], _mm_castsi128_ps(_mm_shuffle_epi32(l, 0x55)), r);
    r = sk_madd(p[2], _mm_castsi128_ps(_mm_shuffle_epi32(l, 0xAA)), r);
    r = sk_madd(p[3], _mm_castsi128_ps(_mm_shuffle_epi32(l, 0xFF)), r);
    return _mm_castps_si128(r);
}

__attribute__((target("sse4.1,fma"))) void skel_native(ppu_context* ctx)
{
    const uint32_t skel = (uint32_t)ctx->gpr[3], out = (uint32_t)ctx->gpr[4], local = (uint32_t)ctx->gpr[5];
    const uint32_t root = (uint32_t)ctx->gpr[6];
    const int32_t every = (int32_t)ctx->gpr[7];
    const uint64_t r1 = ctx->gpr[1], frame = r1 - 0x190;
    const uint32_t table = vm_read32(skel + 0x4), bytes = vm_read32(skel + 0x28);

    __m128i rows[4];
    for (uint32_t i = 0; i < 4; i++) rows[i] = sk_load(root + i * 0x10);
    int32_t bone = (int16_t)vm_read16(table + 0x2);
    for (uint32_t i = 0; i < 4; i++) sk_store(out + i * 0x10, rows[i]);
    if (bone <= -1) return;
    const int32_t count = (int32_t)(uint32_t)vm_read16(skel + 0x14);
    if (bone >= count) return;

    __m128 p[4];                  // the parent's matrix
    for (uint32_t i = 0; i < 4; i++) p[i] = _mm_castsi128_ps(rows[i]);
    int32_t cached = 0, prev_bone = -2;
    __m128i prev[4];              // the last bone's result, or what the stack held
    for (uint32_t i = 0; i < 4; i++) prev[i] = sk_load((uint32_t)frame + 0x70 + i * 0x10);

    for (; bone < count; bone++) {
        if (every == 0 && !(vm_read16(skel + 0x2C) & 0x400) && (vm_read8(bytes + bone) & 3) != 3)
            continue;
        const uint32_t entry = (uint32_t)(((uint64_t)(int64_t)bone << 3) + table);
        const int32_t parent = (int16_t)vm_read16(entry + 0x6);
        if (parent != cached) {
            if (parent == prev_bone) {
                for (uint32_t i = 0; i < 4; i++) p[i] = _mm_castsi128_ps(prev[i]);
            } else {
                const uint32_t ea = (uint32_t)(((uint64_t)(int64_t)parent << 6) + out);
                for (uint32_t i = 0; i < 4; i++) p[i] = _mm_castsi128_ps(sk_load(ea + i * 0x10));
            }
            cached = parent;
        }
        const uint32_t off = (uint32_t)((int64_t)bone << 6), src = local + off;
        for (uint32_t i = 0; i < 4; i++) prev[i] = sk_row(p, sk_load(src + i * 0x10));
        prev_bone = bone;

        const uint32_t flags = vm_read16(entry);
        if (flags & 0x6000) {
            const uint64_t lr = ctx->lr;
            for (uint32_t i = 0; i < 4; i++) sk_store((uint32_t)frame + 0x70 + i * 0x10, prev[i]);
            vm_write64(frame, r1);
            vm_write64(frame + 0x1A0, lr);
            ctx->gpr[1] = frame;
            ctx->gpr[3] = frame + 0x70;
            ctx->gpr[4] = flags;
            ctx->lr = 0x002A4604;
            func_002A2290(ctx);
            while (g_trampoline_fn) {
                void (*fn)(void*) = g_trampoline_fn;
                g_trampoline_fn = nullptr;
                fn(ctx);
            }
            ctx->gpr[1] = r1;
            ctx->lr = lr;
            for (uint32_t i = 0; i < 4; i++) prev[i] = sk_load((uint32_t)frame + 0x70 + i * 0x10);
        }
        const uint32_t dst = out + off;
        for (uint32_t i = 0; i < 4; i++) sk_store(dst + i * 0x10, prev[i]);
    }
}

}  // namespace
#endif  // x86

namespace {

// GOWA_SKEL_CAP: one record per call kept: magic, r1 r3..r7 vscr, the number of
// regions, then each one's EA, length and bytes.
void skel_capture(const ppu_context* ctx)
{
    static const char* s_path = nullptr;
    static FILE* s_f = nullptr;
    static long s_max = 400, s_every = 64;
    static volatile long s_n;
    static int s_init;
    if (!s_init) {
        s_init = 1;
        if (const char* e = getenv("GOWA_SKEL_CAP")) {
            static char path[1024];
            snprintf(path, sizeof path, "%s", e);
            if (char* c = strchr(path, ',')) {
                *c = 0;
                s_max = atol(c + 1);
                if (const char* d = strchr(c + 1, ',')) s_every = atol(d + 1);
            }
            s_path = path;
            s_f = fopen(path, "wb");
        }
    }
    if (!s_f) return;
    const long n = __atomic_fetch_add(&s_n, 1, __ATOMIC_RELAXED);
    if (s_every > 1 && n % s_every) return;
    if (n / (s_every > 0 ? s_every : 1) >= s_max) return;

    const uint32_t r1 = (uint32_t)ctx->gpr[1], skel = (uint32_t)ctx->gpr[3], out = (uint32_t)ctx->gpr[4];
    const uint32_t local = (uint32_t)ctx->gpr[5], root = (uint32_t)ctx->gpr[6];
    const auto be32 = [](uint32_t ea) { const uint8_t* p = vm_base + ea; return (uint32_t)p[0] << 24 | (uint32_t)p[1] << 16 | (uint32_t)p[2] << 8 | p[3]; };
    const auto be16 = [](uint32_t ea) { const uint8_t* p = vm_base + ea; return (uint32_t)p[0] << 8 | p[1]; };
    const uint32_t table = be32(skel + 4), bytes = be32(skel + 0x28), count = be16(skel + 0x14);
    if (count > 4096) return;
    const struct { uint32_t ea, len; } regions[] = {
        { skel, 0x30 }, { table, 8 * (count + 1) }, { bytes, count }, { local & ~15u, 64 * count + 16 },
        { (out & ~15u) - 64, 64 * (count + 2) }, { root & ~15u, 64 }, { (r1 - 0x190) & ~15u, 0x1B0 },
    };
    const uint32_t head[] = { 0x534B454Cu, r1, skel, out, local, root, (uint32_t)ctx->gpr[7], ctx->vscr,
                              (uint32_t)(sizeof regions / sizeof regions[0]) };
    static volatile long s_lock;
    while (__atomic_exchange_n(&s_lock, 1, __ATOMIC_ACQUIRE)) {}
    fwrite(head, sizeof head, 1, s_f);
    for (const auto& r : regions) {
        fwrite(&r.ea, 4, 1, s_f);
        fwrite(&r.len, 4, 1, s_f);
        fwrite(vm_base + r.ea, 1, r.len, s_f);
    }
    fflush(s_f);
    __atomic_store_n(&s_lock, 0, __ATOMIC_RELEASE);
}

}  // namespace

// 1: done here, the lifted body does not run
int gowa_skel_gate(ppu_context* ctx)
{
    static int s_cap = -1, s_on = -1;
    if (__builtin_expect(s_cap < 0, 0)) s_cap = getenv("GOWA_SKEL_CAP") != nullptr;
    if (__builtin_expect(s_cap, 0)) skel_capture(ctx);
#ifdef SKEL_X86
    if (__builtin_expect(s_on < 0, 0)) { const char* e = getenv("GOWA_SKEL_NATIVE"); s_on = e && *e == '1'; }
    if (s_on && PS3_CAUSAL("GOWA_SKEL_NATIVE") && !(ctx->vscr & 0x00010000u)) {
        skel_native(ctx);
        return 1;
    }
#else
    (void)s_on;
#endif
    return 0;
}
