// Only linked into GENERATE builds. run.ps1 stops the process forcibly, so
// flush before that instead of relying on atexit. No guest data is modified.
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <thread>
extern "C" int __llvm_profile_write_file(void);
namespace {
struct PgoFlush {
    PgoFlush() {
        const char* value = std::getenv("ASCENSION_PGO_FLUSH_SECONDS");
        if (!value || !*value) return;
        char* end;
        const long seconds = std::strtol(value, &end, 10);
        if (*end || seconds < 1 || seconds > 3600) {
            std::fprintf(stderr, "[pgo] invalid flush interval\n");
            return;
        }
        std::fprintf(stderr, "[pgo] training build; profile flush after %ld seconds\n", seconds);
        std::thread([seconds] {
            std::this_thread::sleep_for(std::chrono::seconds(seconds));
            const int result = __llvm_profile_write_file();
            std::fprintf(stderr, "[pgo] profile write completed: result=%d\n", result);
            std::fflush(stderr);
        }).detach();
    }
} pgo_flush;
}
