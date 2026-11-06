// host/skeleton_native.cpp against the lifted func_002A434C, on x86 (Rosetta on a
// Mac): the same input through both, then every byte of the output, each call of
// func_002A2290 and the registers a caller may rely on must be identical.
// usage (tools/test_skel_native.sh): test_skel_native <capture|-> [random cases]
#include "ppu_recomp.h"
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <vector>
#include <sys/mman.h>

#include "../host/skeleton_native.cpp"

extern "C" void lifted_002A434C(ppu_context* ctx);
extern "C" PPU_THREAD_LOCAL void (*g_trampoline_fn)(void*) = nullptr;

// the guest memory and what the lift needs of the runtime
extern "C" {
uint8_t* vm_base;
int vm_inline_ok = 1, vm_store_inline_ok = 1, g_spu_coh_armed = 0;
unsigned char g_spu_coh_bitmap[1];
uint32_t g_barrier_sync_watch = 0, ppu_vm_size = 0, ppu_hle_inject_base = 0xD0000000u;
volatile int g_causal_on = 1;
int ps3_causal_tested(const char*) { return 0; }
#undef vm_read8
#undef vm_read16
#undef vm_read32
#undef vm_read64
#undef vm_write8
#undef vm_write16
#undef vm_write32
#undef vm_write64
uint8_t  vm_read8(uint64_t a) { return vm_base[(uint32_t)a]; }
uint16_t vm_read16(uint64_t a) { uint16_t v; memcpy(&v, vm_base + (uint32_t)a, 2); return __builtin_bswap16(v); }
uint32_t vm_read32(uint64_t a) { uint32_t v; memcpy(&v, vm_base + (uint32_t)a, 4); return __builtin_bswap32(v); }
uint64_t vm_read64(uint64_t a) { uint64_t v; memcpy(&v, vm_base + (uint32_t)a, 8); return __builtin_bswap64(v); }
void vm_write8(uint64_t a, uint8_t x) { vm_base[(uint32_t)a] = x; }
void vm_write16(uint64_t a, uint16_t x) { x = __builtin_bswap16(x); memcpy(vm_base + (uint32_t)a, &x, 2); }
void vm_write32(uint64_t a, uint32_t x) { x = __builtin_bswap32(x); memcpy(vm_base + (uint32_t)a, &x, 4); }
void vm_write64(uint64_t a, uint64_t x) { x = __builtin_bswap64(x); memcpy(vm_base + (uint32_t)a, &x, 8); }
}

namespace {

struct Region { uint32_t ea, len; std::vector<uint8_t> bytes; };
struct Case { uint32_t r1, r3, r4, r5, r6, r7, vscr; std::vector<Region> regions; };
struct Call { uint64_t r1, r3, r4, lr; uint32_t vscr; uint8_t matrix[64]; };

std::vector<Call> g_calls;
uint64_t g_mix;
long g_total_calls;

uint64_t mix(uint64_t x) { x ^= x >> 33; x *= 0xff51afd7ed558ccdull; x ^= x >> 33; return x; }
uint32_t rnd() { static uint64_t s = 0x9E3779B97F4A7C15ull; s += 0x9E3779B97F4A7C15ull; return (uint32_t)(mix(s) >> 13); }

void wr32(uint32_t ea, uint32_t v) { v = __builtin_bswap32(v); memcpy(vm_base + ea, &v, 4); }
void wr16(uint32_t ea, uint32_t v) { const uint16_t x = __builtin_bswap16((uint16_t)v); memcpy(vm_base + ea, &x, 2); }

const uint32_t kSpecial[] = { 0, 0x80000000u, 0x00000001u, 0x80000001u, 0x007FFFFFu, 0x00800000u, 0x7F800000u, 0xFF800000u,
                              0x7FC00000u, 0x7F800001u, 0xFFC12345u, 0x3F800000u, 0xBF800000u, 0x7F7FFFFFu, 0x0DA24260u, 0x1E3CE508u };

uint32_t rnd_float(int kind)
{
    const uint32_t r = rnd();
    if (kind == 0) {  // an ordinary transform
        const uint32_t e = 110 + (r >> 8) % 30;
        return (r & 0x80000000u) | e << 23 | (rnd() & 0x7FFFFFu);
    }
    if (kind == 1) return (r % 3) ? (r & 0x80000000u) | (0x3F800000u) : 0;   // identity-like
    if (r % 4 == 0) return kSpecial[(r >> 8) % (sizeof kSpecial / sizeof kSpecial[0])];
    return r & 0x807FFFFFu | (((rnd() % 4) ? 90 + rnd() % 80 : rnd() % 3) << 23);    // tiny products too
}

Case make_random()
{
    Case c{};
    const uint32_t skel = 0x20000000u, table = 0x20010000u, bytes = 0x20020000u, local = 0x20100000u;
    const uint32_t out = 0x20200000u + 0x40, root = 0x20300000u, stack = 0x10100000u;
    const uint32_t count = rnd() % 90;
    const int kind = rnd() % 3;
    c.r1 = stack; c.r3 = skel; c.r4 = out & ~15u; c.r5 = local; c.r6 = root; c.r7 = rnd() % 2 ? rnd() | 1 : 0;
    c.vscr = rnd() % 16 ? 0 : 0x00010000u;   // with NJ the gate leaves it to the lift
    c.regions.reserve(8);
    auto add = [&](uint32_t ea, uint32_t len) {
        Region r; r.ea = ea; r.len = len; r.bytes.resize(len);
        for (auto& b : r.bytes) b = (uint8_t)rnd();
        c.regions.push_back(r);
        return &c.regions.back();
    };
    Region* s = add(skel, 0x30);
    Region* t = add(table, 8 * (count + 1));
    Region* b = add(bytes, count);
    Region* l = add(local, 64 * count + 16);
    add((c.r4) - 64 - 16, 64 * (count + 3));
    Region* m = add(root, 64);
    add(stack - 0x190, 0x1B0);
    auto be32 = [](uint8_t* p, uint32_t v) { p[0] = v >> 24; p[1] = v >> 16; p[2] = v >> 8; p[3] = v; };
    auto be16 = [](uint8_t* p, uint32_t v) { p[0] = v >> 8; p[1] = v; };
    be32(&s->bytes[0x4], table);
    be32(&s->bytes[0x28], bytes);
    be16(&s->bytes[0x14], count);
    be16(&s->bytes[0x2C], rnd() % 2 ? 0x400 : rnd() & ~0x400u & 0xFFFF);
    const int32_t first = count && rnd() % 8 ? (rnd() % 3 == 0 ? 0 : (int32_t)(rnd() % 3)) : (rnd() % 2 ? -1 : (int32_t)count);
    be16(&t->bytes[2], (uint32_t)first);
    for (uint32_t i = 0; i < count; i++) {
        int32_t parent;
        const uint32_t r = rnd() % 16;
        if (i == 0) parent = -1;
        else if (r < 8) parent = (int32_t)i - 1;             // the last bone
        else if (r < 11 && i > 1) parent = (int32_t)i - 2;
        else if (r == 15) parent = -2 + (int32_t)(rnd() % 3);
        else parent = (int32_t)(rnd() % i);
        be16(&t->bytes[8 * i + 6], (uint32_t)parent);
        be16(&t->bytes[8 * i], (rnd() % 5 == 0) ? (rnd() & 0xFFFF) : (rnd() & 0x9FFF));
        if (i < count) b->bytes[i] = (uint8_t)rnd();
    }
    for (uint32_t i = 0; i < l->len / 4; i++) be32(&l->bytes[i * 4], rnd_float(kind));
    for (uint32_t i = 0; i < 16; i++) be32(&m->bytes[i * 4], rnd_float(kind));
    return c;
}

void load(const Case& c, ppu_context* ctx, uint32_t seed)
{
    for (const auto& r : c.regions) memcpy(vm_base + r.ea, r.bytes.data(), r.len);
    memset(ctx, 0, sizeof *ctx);
    uint64_t s = seed;
    for (int i = 0; i < 32; i++) {
        ctx->gpr[i] = mix(s += 0x9E37);
        ctx->vr[i].d[0] = mix(s += 0x9E37);
        ctx->vr[i].d[1] = mix(s += 0x9E37);
    }
    ctx->gpr[1] = c.r1; ctx->gpr[3] = c.r3; ctx->gpr[4] = c.r4; ctx->gpr[5] = c.r5; ctx->gpr[6] = c.r6; ctx->gpr[7] = c.r7;
    ctx->cr = (uint32_t)mix(s += 7); ctx->lr = 0x00123450; ctx->vscr = c.vscr;
}

// what a caller may rely on, and all guest memory but the stack below r1
struct Result {
    std::vector<std::vector<uint8_t>> mem;
    std::vector<Call> calls;
    ppu_context ctx;
};
Result run(const Case& c, bool native, uint32_t seed)
{
    static ppu_context* ctx = (ppu_context*)aligned_alloc(4096, (sizeof(ppu_context) + 4095) & ~size_t(4095));
    load(c, ctx, seed);
    g_calls.clear();
    g_mix = seed;
    const bool nj = (c.vscr & 0x00010000u) != 0;
    if (native) {
        const int took = gowa_skel_gate(ctx);
        if (took == nj) { fprintf(stderr, "the gate %s, vscr %08X\n", took ? "took it" : "did not take it", c.vscr); exit(2); }
        if (!took) lifted_002A434C(ctx);
    } else {
        lifted_002A434C(ctx);
        while (g_trampoline_fn) { void (*f)(void*) = g_trampoline_fn; g_trampoline_fn = nullptr; f(ctx); }
    }
    Result r;
    r.ctx = *ctx;
    r.calls = g_calls;
    for (const auto& reg : c.regions) {
        if (reg.ea + reg.len == c.r1 + 0x20 || reg.ea == ((c.r1 - 0x190) & ~15u)) continue;  // the stack
        r.mem.emplace_back(vm_base + reg.ea, vm_base + reg.ea + reg.len);
    }
    return r;
}

bool same_float_or_print(const char* what, long n, const std::vector<uint8_t>& a, const std::vector<uint8_t>& b)
{
    if (a == b) return true;
    for (size_t i = 0; i < a.size(); i++)
        if (a[i] != b[i]) {
            size_t w = i & ~size_t(3);
            fprintf(stderr, "case %ld: %s differs at +0x%zX: lifted %02X%02X%02X%02X native %02X%02X%02X%02X\n", n, what, w,
                    a[w], a[w + 1], a[w + 2], a[w + 3], b[w], b[w + 1], b[w + 2], b[w + 3]);
            return false;
        }
    return false;
}

bool compare(const Case& c, long n)
{
    const uint32_t seed = (uint32_t)n * 2654435761u;
    Result a = run(c, false, seed), b = run(c, true, seed);
    bool ok = true;
    for (size_t i = 0; i < a.mem.size(); i++)
        ok &= same_float_or_print("memory region", n, a.mem[i], b.mem[i]);
    if (a.calls.size() != b.calls.size()) {
        fprintf(stderr, "case %ld: %zu calls lifted, %zu native\n", n, a.calls.size(), b.calls.size());
        ok = false;
    } else {
        for (size_t i = 0; i < a.calls.size(); i++)
            if (memcmp(&a.calls[i], &b.calls[i], sizeof(Call))) {
                fprintf(stderr, "case %ld: call %zu differs (r3 %llX/%llX r4 %llX/%llX lr %llX/%llX r1 %llX/%llX)\n", n, i,
                        (unsigned long long)a.calls[i].r3, (unsigned long long)b.calls[i].r3,
                        (unsigned long long)a.calls[i].r4, (unsigned long long)b.calls[i].r4,
                        (unsigned long long)a.calls[i].lr, (unsigned long long)b.calls[i].lr,
                        (unsigned long long)a.calls[i].r1, (unsigned long long)b.calls[i].r1);
                ok = false;
                break;
            }
    }
    g_total_calls += (long)a.calls.size();
    // r1, r2, r13-r31, v20-v31, lr, the nonvolatile CR fields, VSCR
    for (int i = 0; i < 32; i++) {
        if ((i == 1 || i == 2 || i >= 13) && a.ctx.gpr[i] != b.ctx.gpr[i]) { fprintf(stderr, "case %ld: r%d\n", n, i); ok = false; }
        if (i >= 20 && memcmp(&a.ctx.vr[i], &b.ctx.vr[i], 16)) { fprintf(stderr, "case %ld: v%d\n", n, i); ok = false; }
    }
    if (a.ctx.lr != b.ctx.lr) { fprintf(stderr, "case %ld: lr %llX / %llX\n", n, (unsigned long long)a.ctx.lr, (unsigned long long)b.ctx.lr); ok = false; }
    if ((a.ctx.cr & 0x00FFF000u) != (b.ctx.cr & 0x00FFF000u)) { fprintf(stderr, "case %ld: cr %08X %08X\n", n, a.ctx.cr, b.ctx.cr); ok = false; }
    if (a.ctx.vscr != b.ctx.vscr) { fprintf(stderr, "case %ld: vscr\n", n); ok = false; }
    return ok;
}

std::vector<Case> read_capture(const char* path)
{
    std::vector<Case> out;
    FILE* f = fopen(path, "rb");
    if (!f) { fprintf(stderr, "no capture %s\n", path); exit(2); }
    uint32_t h[9];
    while (fread(h, sizeof h, 1, f) == 1) {
        if (h[0] != 0x534B454Cu) { fprintf(stderr, "bad record\n"); exit(2); }
        Case c{};
        c.r1 = h[1]; c.r3 = h[2]; c.r4 = h[3]; c.r5 = h[4]; c.r6 = h[5]; c.r7 = h[6]; c.vscr = h[7];
        for (uint32_t i = 0; i < h[8]; i++) {
            Region r;
            if (fread(&r.ea, 4, 1, f) != 1 || fread(&r.len, 4, 1, f) != 1) exit(2);
            r.bytes.resize(r.len);
            if (r.len && fread(r.bytes.data(), 1, r.len, f) != r.len) exit(2);
            c.regions.push_back(std::move(r));
        }
        out.push_back(std::move(c));
    }
    fclose(f);
    return out;
}

}  // namespace

// the callback, with its effect on the matrix decided by its input: what a lift
// or a native does with the result must show, and the volatile registers are lost
void func_002A2290(ppu_context* ctx)
{
    Call c{};
    c.r1 = ctx->gpr[1]; c.r3 = ctx->gpr[3]; c.r4 = ctx->gpr[4]; c.lr = ctx->lr; c.vscr = ctx->vscr;
    memcpy(c.matrix, vm_base + (uint32_t)c.r3, 64);
    g_calls.push_back(c);
    uint64_t s = g_mix ^ c.r4;
    for (int i = 0; i < 64; i++) s = mix(s + c.matrix[i]);
    g_mix = s;
    for (int i = 0; i < 4; i++) {
        // a low mantissa bit per row, as a real transform would change it
        vm_base[(uint32_t)c.r3 + i * 16 + 3] ^= (uint8_t)(s >> (i * 8));
    }
    for (int i = 3; i <= 12; i++) ctx->gpr[i] = mix(s + i);
    for (int i = 0; i <= 13; i++) { ctx->vr[i].d[0] = mix(s + 100 + i); ctx->vr[i].d[1] = mix(s + 200 + i); }
    ctx->lr = 0xDEAD0000u;
    ctx->cr ^= 0xFF000FFFu;
}

int main(int argc, char** argv)
{
    vm_base = (uint8_t*)mmap(nullptr, 1ull << 32, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANON | MAP_NORESERVE, -1, 0);
    if (vm_base == MAP_FAILED) { perror("mmap"); return 2; }
    setenv("GOWA_SKEL_NATIVE", "1", 1);
    long bad = 0, n = 0;
    if (strcmp(argv[1], "-")) {
        const std::vector<Case> cases = read_capture(argv[1]);
        long bones = 0;
        for (const auto& c : cases) {
            bones += c.regions[3].len / 64;
            if (!compare(c, n++)) bad++;
            if (bad > 5) break;
        }
        printf("captured: %ld calls, %ld bones, %ld callback calls, %ld differ\n", n, bones, g_total_calls, bad);
    }
    const long rand_n = argc > 2 ? atol(argv[2]) : 20000;
    long rbad = 0;
    g_total_calls = 0;
    for (long i = 0; i < rand_n; i++) {
        if (!compare(make_random(), 1000000 + i)) rbad++;
        if (rbad > 5) break;
    }
    printf("random: %ld cases, %ld callback calls, %ld differ\n", rand_n, g_total_calls, rbad);
    return bad || rbad;
}
