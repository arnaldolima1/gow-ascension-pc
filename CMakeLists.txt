# Ascension: from ps3recomp's templates/project, with its defaults pointed at
# ../ps3recomp, src/recomp and src/spu.
cmake_minimum_required(VERSION 3.20)
project(AscensionRecomp
    VERSION 0.1.0
    LANGUAGES C CXX
    DESCRIPTION "God of War: Ascension (PS3), recompiled on ps3recomp"
)

# ---------------------------------------------------------------------------
# Standards
# ---------------------------------------------------------------------------
set(CMAKE_C_STANDARD 17)
set(CMAKE_C_STANDARD_REQUIRED ON)
set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# Prefer Ninja if available
if(NOT CMAKE_GENERATOR MATCHES "Ninja" AND NOT DEFINED ENV{CMAKE_GENERATOR})
    message(STATUS "Tip: use -G Ninja for faster builds")
endif()

# ---------------------------------------------------------------------------
# The two directories this project is built from
# ---------------------------------------------------------------------------
# PS3RECOMP_DIR is the toolkit checkout: include/, runtime/, libs/, tools/.
# RECOMP_DIR is where the lifter's output for THIS game lives. They are
# separate on purpose -- a port keeps its generated code in its own tree and
# points at whatever toolkit checkout it is building against:
#
#   cmake -B build -G Ninja \
#         -DPS3RECOMP_DIR=/path/to/ps3recomp \
#         -DRECOMP_DIR=/path/to/my_game/recompiled
#
if(NOT DEFINED PS3RECOMP_DIR)
    # Default: the toolkit checked out beside this repository, as ps3kit (the
    # fork's current name) or ps3recomp.
    if(EXISTS "${CMAKE_CURRENT_SOURCE_DIR}/../ps3kit/CMakeLists.txt")
        get_filename_component(PS3RECOMP_DIR "${CMAKE_CURRENT_SOURCE_DIR}/../ps3kit" ABSOLUTE)
    else()
        get_filename_component(PS3RECOMP_DIR "${CMAKE_CURRENT_SOURCE_DIR}/../ps3recomp" ABSOLUTE)
    endif()
endif()
get_filename_component(PS3RECOMP_DIR "${PS3RECOMP_DIR}" ABSOLUTE)

set(RECOMP_DIR "${CMAKE_CURRENT_SOURCE_DIR}/src/recomp" CACHE PATH
    "Directory holding the lifter's output: ppu_recomp.h and the lifted sources")
get_filename_component(RECOMP_DIR "${RECOMP_DIR}" ABSOLUTE)

message(STATUS "ps3recomp SDK:   ${PS3RECOMP_DIR}")
message(STATUS "Lifted output:   ${RECOMP_DIR}")

if(NOT EXISTS "${RECOMP_DIR}/ppu_recomp.h")
    message(FATAL_ERROR
        "No ppu_recomp.h in ${RECOMP_DIR}.\n"
        "That header and the lifted sources beside it are what "
        "tools/ppu_lifter.py writes. Run the lifter, drop its output there, "
        "or point -DRECOMP_DIR= at wherever it already is.")
endif()

# The lifted translation units. A game's lift is hundreds of generated files,
# so they are globbed rather than listed; re-run CMake after a fresh lift.
file(GLOB RECOMP_SOURCES CONFIGURE_DEPENDS
    "${RECOMP_DIR}/*.c"
    "${RECOMP_DIR}/*.cpp"
)
if(NOT RECOMP_SOURCES)
    message(FATAL_ERROR
        "${RECOMP_DIR} has a ppu_recomp.h but no .c or .cpp beside it. The "
        "lifted functions and the function table live in those; without them "
        "there is nothing to run.")
endif()
list(LENGTH RECOMP_SOURCES RECOMP_SOURCE_COUNT)
message(STATUS "Lifted sources:  ${RECOMP_SOURCE_COUNT} file(s)")

# ---------------------------------------------------------------------------
# ps3recomp runtime library
# ---------------------------------------------------------------------------
# Built from source as a subdirectory rather than imported as a prebuilt
# archive. A static library carries none of its own link requirements, so an
# imported one arrives without SDL2, pthreads, the Metal frameworks or the
# Winsock/XInput imports -- the link then fails on every platform for a
# different reason. add_subdirectory hands all of that over with the target.
# With RPCS3's RSX linked (ASCENSION_RPCS3_RSX, below), ps3kit's own Vulkan
# renderer (PS3RECOMP_RSX_VULKAN, PS3_RSX=vulkan) translates shaders with that
# build's glslang: one copy in the binary.
if(ASCENSION_RPCS3_RSX AND ASCENSION_RPCS3_BUILD)
    set(PS3RECOMP_GLSLANG_RPCS3_BUILD "${ASCENSION_RPCS3_BUILD}" CACHE PATH "" FORCE)
endif()
add_subdirectory("${PS3RECOMP_DIR}" "${CMAKE_BINARY_DIR}/ps3recomp_sdk"
                 EXCLUDE_FROM_ALL)

# ---------------------------------------------------------------------------
# The HLE NID table
# ---------------------------------------------------------------------------
# Maps each firmware import NID onto the handler in the runtime that answers
# it. A port may keep a hand-curated one beside its lift; otherwise generate
# the canonical every-module table, which is what the toolkit's own boot
# harness uses.
if(EXISTS "${RECOMP_DIR}/ppu_hle_nids.cpp")
    set(HLE_NID_TABLE "${RECOMP_DIR}/ppu_hle_nids.cpp")
    message(STATUS "HLE NID table:   ${HLE_NID_TABLE}")
else()
    find_package(Python3 COMPONENTS Interpreter REQUIRED)
    set(HLE_NID_TABLE "${CMAKE_CURRENT_BINARY_DIR}/ppu_hle_nids.cpp")
    # The table is made from the handlers the library sources define, so a
    # handler added there must regenerate it, not only a change to the tools.
    file(GLOB_RECURSE HLE_LIB_SOURCES CONFIGURE_DEPENDS "${PS3RECOMP_DIR}/libs/*.c")
    add_custom_command(
        OUTPUT "${HLE_NID_TABLE}"
        COMMAND "${Python3_EXECUTABLE}"
                "${PS3RECOMP_DIR}/tools/gen_hle_nids.py"
                --out "${HLE_NID_TABLE}" --all
        DEPENDS "${PS3RECOMP_DIR}/tools/gen_hle_nids.py"
                "${PS3RECOMP_DIR}/tools/nid_database.py"
                ${HLE_LIB_SOURCES}
        COMMENT "Generating the HLE NID -> handler table")
    message(STATUS "HLE NID table:   generated (every module)")
endif()

# ---------------------------------------------------------------------------
# The game executable
# ---------------------------------------------------------------------------
# The PPU boot scaffold is compiled here rather than taken from the runtime
# library: every one of these files #includes the lifter's per-game
# ppu_recomp.h, so they can only be built against a particular lift.
set(PS3RECOMP_SCAFFOLD
    "${PS3RECOMP_DIR}/runtime/ppu/ppu_loader.cpp"
    "${PS3RECOMP_DIR}/runtime/ppu/ppu_hle.cpp"
    "${PS3RECOMP_DIR}/runtime/ppu/ppu_fs.cpp"
    "${PS3RECOMP_DIR}/runtime/ppu/ppu_sysprx.cpp"
)

# ---------------------------------------------------------------------------
# Lifted SPU images (optional)
# ---------------------------------------------------------------------------
# A title that runs SPU work gets its images lifted into <SPU_DIR>/<image>/ by
# tools/spu_lifter.py, with a registration TU generated by
# tools/build_spu_workloads.py. cellSpurs dispatches them by content
# fingerprint, so the generated table is keyed to the images THIS build ships:
# a table generated from another release registers signatures that can never
# match, which is worse than shipping none. Both the table and the job-module
# registry self-register from constructors and are therefore optional -- a tree
# that has not lifted its SPU images yet configures and links without them.
set(SPU_DIR "${CMAKE_CURRENT_SOURCE_DIR}/src/spu" CACHE PATH
    "Directory holding the lifted SPU images (<SPU_DIR>/<image>/spu_recomp.c)")
option(PORT_ENABLE_SPU "Compile and register the title's lifted SPU images" ON)

set(SPU_SOURCES "")
if(PORT_ENABLE_SPU)
    file(GLOB SPU_LIFTED CONFIGURE_DEPENDS "${SPU_DIR}/*/spu_recomp.c")
    if(SPU_LIFTED)
        list(LENGTH SPU_LIFTED SPU_IMAGE_COUNT)
        message(STATUS "Lifted SPU:      ${SPU_IMAGE_COUNT} image(s)")
        # The musttail indirect-branch fast path. Excluded from the runtime
        # library on purpose (see the SDK root CMakeLists): it must be built
        # here, by clang, or the tail call degrades to a plain call and a guest
        # loop that branches indirectly walks the thread stack off its guard
        # page a few thousand iterations in.
        list(APPEND SPU_SOURCES ${SPU_LIFTED}
             "${PS3RECOMP_DIR}/runtime/spu/spu_dispatch_mt.c")
        # Generated beside the lift; each is present only once its generator
        # has been run, so each is included only if it is actually here.
        foreach(gen IN ITEMS spu_workloads.c jobmods_register.c pic_register.c taskset_policy_bytes.c)
            if(EXISTS "${SPU_DIR}/${gen}")
                list(APPEND SPU_SOURCES "${SPU_DIR}/${gen}")
            else()
                message(STATUS "  (no ${gen} -- not registered)")
            endif()
        endforeach()
    else()
        message(STATUS "Lifted SPU:      none found in ${SPU_DIR}")
    endif()
endif()

add_executable(${PROJECT_NAME}
    # ps3recomp's full boot harness, as the Twisted Metal port builds it, not
    # the template's minimal main.cpp: it adds the vblank ticker the GCM
    # waits need, the hang watchdog, the PS3_DEBUG console and the
    # PARAM.SFO read at boot.
    "${PS3RECOMP_DIR}/runtime/ppu/tests/boot_main.cpp"
    # Runtime switches this title needs on by default (live draw engine,
    # host Edge Zlib).
    "${CMAKE_CURRENT_SOURCE_DIR}/host/ascension_defaults.cpp"
    ${PS3RECOMP_SCAFFOLD}
    ${HLE_NID_TABLE}
    ${RECOMP_SOURCES}
    ${SPU_SOURCES}
)

# The lifted SPU sources use bare #include "spu_context.h". Scope that include
# directory (and their flags) to those TUs alone: adding it to the whole target
# changes the compile command of every lifted PPU TU, and those are large enough
# that the needless rebuild is measured in tens of minutes.
#   SPU_USE_DISPATCH_MT -- route SPU_IB_DISPATCH through the musttail path.
#   -O2                 -- the target-wide -O1 exists for the huge PPU TUs; the
#                          SPU sources are small and decode-hot, so they get
#                          full optimization. The last -O on the line wins.
if(SPU_SOURCES)
    # SPU_XFLOAT_APPROX: float add/sub/mul/fma are one SSE instruction with no
    # SPU extended-range check, as RPCS3's default "Approximate" xfloat (see
    # spu_helpers.h). 1.64x on module 218's vertex stage, outputs unchanged on
    # its 48 captures.
    option(ASCENSION_SPU_XFLOAT_APPROX "Lifted SPU float ops without the extended-range check" ON)
    # SPU_LS_NO_HOOKS: no LS diagnostics in lifted code (SPU_LS_WATCH,
    # SPU_SMC_WATCH, SPU_LS_LOWREAD stop working there; spu_context.h).
    option(ASCENSION_SPU_LS_HOOKS "Keep the LS diagnostic hooks in lifted SPU code" OFF)
    set(SPU_DEFS "SPU_USE_DISPATCH_MT;SPU_ASSUME_SPU_FP")
    if(ASCENSION_SPU_XFLOAT_APPROX)
        string(APPEND SPU_DEFS ";SPU_XFLOAT_APPROX")
    endif()
    if(NOT ASCENSION_SPU_LS_HOOKS)
        string(APPEND SPU_DEFS ";SPU_LS_NO_HOOKS")
    endif()
    set_source_files_properties(${SPU_SOURCES} PROPERTIES
        INCLUDE_DIRECTORIES "${PS3RECOMP_DIR}/runtime/spu"
        # SPU_ASSUME_SPU_FP: lifted code always runs in the SPU float mode
        # (spu_run_with_halt), so the float ops skip reading MXCSR each time.
        COMPILE_DEFINITIONS "${SPU_DEFS}")
    if(NOT MSVC OR CMAKE_CXX_COMPILER_ID MATCHES "Clang")
        # SSE4.1 as well (any x86-64 since ~2008): spu_shufb is pshufb/blendv
        # only under __SSE4_1__, and without it every shufb in lifted code is
        # a 16-byte loop (a third of the job worker in Ascension's profile).
        # The runtime gets the same flag; probed, as Apple arm64 clang rejects it.
        include(CheckCCompilerFlag)
        check_c_compiler_flag(-msse4.1 PORT_HAS_MSSE41)
        # The SPU float fast path (spu_helpers.h) runs with MXCSR rounding toward
        # zero; -frounding-math keeps the compiler from folding float ops on
        # constants under round-to-nearest. clang-cl takes it as /clang:.
        if(MSVC)
            set(SPU_ROUNDING_MATH "/clang:-frounding-math")
        else()
            set(SPU_ROUNDING_MATH "-frounding-math")
        endif()
        # FMA3 (Haswell / Zen and later): spu_fma/fms/fnms are one vfmadd in the
        # SPU float mode instead of the exact double path, and the menu's job
        # list (16 jobs on one SPU per frame) is mostly matrix fma.
        option(ASCENSION_SPU_FMA "Lifted SPU code uses FMA3 (needs a CPU with FMA)" ON)
        check_c_compiler_flag(-mfma PORT_HAS_MFMA)
        set(SPU_FMA_FLAG "")
        if(ASCENSION_SPU_FMA AND PORT_HAS_MFMA)
            # -ffp-contract=off: with FMA available clang would otherwise fuse
            # every a*b+c in the helpers' scalar paths, which the SPU rounds twice.
            set(SPU_FMA_FLAG ";-mfma;-ffp-contract=off")
        endif()
        # AVX2 (Haswell / Zen and later): the helpers' per-lane variable shifts
        # and their four-lane estimate, interpolate and conversion forms
        # (spu_helpers.h, upstream ps3recomp #512 and #500); without it those
        # stay scalar. .env SPU_AVX2=1.
        option(ASCENSION_SPU_AVX2 "Lifted SPU code built for AVX2 (needs such a CPU)" OFF)
        if(ASCENSION_SPU_AVX2)
            set(SPU_FMA_FLAG "${SPU_FMA_FLAG};-mavx2")
        endif()
        # Built for the compiling CPU (AVX-512 on Zen 4/5): the exe then runs
        # only on that machine or one like it. .env NATIVE=1.
        option(ASCENSION_NATIVE "Lifted SPU and PPU code built with -march=native" OFF)
        if(ASCENSION_NATIVE)
            if(MSVC)
                set(SPU_FMA_FLAG "${SPU_FMA_FLAG};/clang:-march=native")
            else()
                set(SPU_FMA_FLAG "${SPU_FMA_FLAG};-march=native")
            endif()
        endif()
        # No warnings for generated SPU code: with registers promoted to locals
        # (SPU_LIFT_PROMOTE) a line flushes dozens of them, every warning
        # reprints its line, and the gigabytes of text stalled ninja for an
        # hour with the compilers idle.
        if(MSVC)
            set(SPU_NOWARN "/w")
        else()
            set(SPU_NOWARN "-w")
        endif()
        if(PORT_HAS_MSSE41)
            set_source_files_properties(${SPU_SOURCES} PROPERTIES COMPILE_OPTIONS "-O2;-msse4.1${SPU_FMA_FLAG};${SPU_ROUNDING_MATH};${SPU_NOWARN}")
            # Code generation experiments on module 218's lift alone (measured
            # with the job replay): extra flags for that one TU, empty by default.
            set(ASCENSION_SPU_LAB_FLAGS "" CACHE STRING "Extra compile flags for module 218's lifted TU (experiments)")
            set(SPU_LAB_FILE "${SPU_DIR}/jobmod_7868e9b847d1_e6D98/spu_recomp.c")
            if(ASCENSION_SPU_LAB_FLAGS AND EXISTS "${SPU_LAB_FILE}")
                set_source_files_properties("${SPU_LAB_FILE}" PROPERTIES COMPILE_OPTIONS "-O2;-msse4.1${SPU_FMA_FLAG};${SPU_ROUNDING_MATH};${SPU_NOWARN};${ASCENSION_SPU_LAB_FLAGS}")
            endif()
        else()
            set_source_files_properties(${SPU_SOURCES} PROPERTIES COMPILE_OPTIONS "-O2;${SPU_ROUNDING_MATH};${SPU_NOWARN}")
        endif()
    endif()
endif()

# app.rc carries the icon, the version block and the manifest, and needs a
# resource compiler. Listing it as a source on a host that has none is not a
# link error, it is a "no rule to make" for a file nothing can consume.
if(WIN32 AND EXISTS "${CMAKE_CURRENT_SOURCE_DIR}/app.rc")
    target_sources(${PROJECT_NAME} PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}/app.rc")
endif()

target_include_directories(${PROJECT_NAME} PRIVATE
    "${RECOMP_DIR}"                            # the generated ppu_recomp.h
    "${PS3RECOMP_DIR}/include"
    "${PS3RECOMP_DIR}/runtime/ppu"
    "${PS3RECOMP_DIR}/runtime/spu"
    "${PS3RECOMP_DIR}/runtime/memory"
    "${PS3RECOMP_DIR}/runtime/syscalls"
    "${PS3RECOMP_DIR}/runtime/platform"        # win32_compat.h and friends
    "${PS3RECOMP_DIR}/libs/video"
    "${CMAKE_CURRENT_SOURCE_DIR}"
)

target_link_libraries(${PROJECT_NAME} PRIVATE
    ps3recomp_runtime
)

# The runtime is C++, and on Apple also Objective-C. Letting CMake infer the
# link language from the generated C would leave the C++ standard library out.
set_target_properties(${PROJECT_NAME} PROPERTIES LINKER_LANGUAGE CXX)

# Windows system import libraries. dbghelp symbolizes crash-handler addresses
# against the PDB, user32 and gdi32 are what the backend's window and its GDI
# present are made of, and winmm is timeBeginPeriod. None of the four names
# anything a POSIX linker can find; the D3D12 backend's own imports come in
# through the #pragma comment(lib) in libs/video/rsx_d3d12_backend.c.
if(WIN32)
    target_link_libraries(${PROJECT_NAME} PRIVATE
        dbghelp
        user32
        gdi32
        winmm
        # The DXGI interface IDs (IID_IDXGIFactory6) the D3D12 backend asks
        # for; clang-cl's lld-link found no other library that defines them.
        dxguid
    )
endif()

# RPCS3's RSX as the renderer (ps3recomp gpu/, v2): links ps3rsx and RPCS3's
# emulator library, built beforehand with MSVC from ps3recomp/gpu.
# Off by default; when on, the game still draws with live draw unless run
# with PS3_RSX=rpcs3. The executable is then GPL-2.0, like RPCS3.
option(ASCENSION_RPCS3_RSX "Link RPCS3's RSX renderer (ps3rsx)" OFF)
set(ASCENSION_RPCS3_BUILD "${CMAKE_CURRENT_SOURCE_DIR}/../work/gpu-build" CACHE PATH
    "Build tree of ps3recomp/gpu")
if(ASCENSION_RPCS3_RSX)
    include("${PS3RECOMP_DIR}/gpu/ps3rsx.cmake")
    ps3rsx_link(${PROJECT_NAME} "${ASCENSION_RPCS3_BUILD}"
        SOURCES "${PS3RECOMP_DIR}/runtime/ppu/tests/boot_main.cpp")
endif()

# ---------------------------------------------------------------------------
# Compiler-specific flags
# ---------------------------------------------------------------------------
if(CMAKE_CXX_COMPILER_ID MATCHES "Clang|GNU")
    target_compile_options(${PROJECT_NAME} PRIVATE
        -Wall -Wextra -Wno-unused-parameter
        -fno-strict-aliasing
        # Explicit, as in the runtime's CMakeLists: a cache can carry
        # CMAKE_C/CXX_FLAGS_RELEASE="" (it did after a reconfigure on
        # 2026-10-21), and clang-cl with no /O flag compiles at /Od -- the
        # lifted PPU code ran unoptimised and the first level fell from ~15
        # to ~7 fps without a word.
        $<$<CONFIG:Release,RelWithDebInfo>:-O2>
    )
    target_compile_definitions(${PROJECT_NAME} PRIVATE $<$<CONFIG:Release>:NDEBUG>)
    if(CMAKE_CXX_COMPILER_FRONTEND_VARIANT STREQUAL "MSVC")
        # clang-cl links with lld-link: the map for the profiler, as below
        target_link_options(${PROJECT_NAME} PRIVATE /MAP)
    endif()
elseif(MSVC)
    target_compile_options(${PROJECT_NAME} PRIVATE
        /W3 /wd4100 /wd4244 /wd4267
        /Zc:__cplusplus         # report correct __cplusplus value
        # ppu_recomp.h defines PPU_FENCE, the lowering of the guest's
        # sync/lwsync/eieio/isync, and in C that is <stdatomic.h>. The lifter
        # writes C++ by default, but --single-file writes ppu_recomp.c, and a
        # port that took it would not compile without this. The runtime's own
        # build already carries the same flag for the same reason.
        /experimental:c11atomics
    )
    target_compile_definitions(${PROJECT_NAME} PRIVATE
        _CRT_SECURE_NO_WARNINGS
    )
    # AscensionRecomp.map beside the executable: the runtime's sampling
    # profiler (PS3_DEBUG's `prof`) prints module offsets, and a release build
    # has no other way to name them.
    target_link_options(${PROJECT_NAME} PRIVATE /MAP)
endif()

# The lifted translation units are machine-generated and can run to hundreds of
# thousands of lines each, so they get their own flags:
#
#   - warnings off. They are about generated code and nobody will act on them,
#     and at this volume they bury the diagnostics that matter.
#   - no floating-point contraction. arm64 fuses a multiply and an add by
#     default; a PPC fmadd is spelt as one where the lifter means one.
#   - /bigobj on MSVC. A single lifted file routinely passes the 65,536-section
#     limit of the default object format.
#   - no math errno. The lifted code never reads errno, and with it sqrtf (the
#     VMX estimate helpers) was a call into the C runtime and ldexp(1.0, 0)
#     (vctsxs with no scale) was never folded.
#   - ASCENSION_PPU_AVX2: built for AVX2, BMI2 and FMA3 (Haswell / Zen and
#     later), so the PPU's rotate-and-mask, shifts and float ops get the
#     newer encodings. clang-cl takes -ffp-contract=off as /clang: and gets it
#     in every case, as the other compilers do: with FMA it would otherwise
#     fuse a*b+c the PPU rounds twice.
option(ASCENSION_PPU_AVX2 "Lifted PPU code built for AVX2, BMI2 and FMA3 (needs such a CPU)" OFF)
if(MSVC)
    set(PPU_RECOMP_OPTIONS "/w;/bigobj")
    if(CMAKE_CXX_COMPILER_ID MATCHES "Clang")
        string(APPEND PPU_RECOMP_OPTIONS ";/clang:-ffp-contract=off;/clang:-fno-math-errno")
        if(ASCENSION_PPU_AVX2)
            string(APPEND PPU_RECOMP_OPTIONS ";-mavx2;-mbmi2;-mfma")
        endif()
        if(ASCENSION_NATIVE)
            string(APPEND PPU_RECOMP_OPTIONS ";/clang:-march=native")
        endif()
    endif()
    set_source_files_properties(${RECOMP_SOURCES} PROPERTIES
        COMPILE_OPTIONS "${PPU_RECOMP_OPTIONS}")
else()
    set_source_files_properties(${RECOMP_SOURCES} PROPERTIES
        COMPILE_OPTIONS "-w;-ffp-contract=off;-fno-math-errno")
endif()

# ---------------------------------------------------------------------------
# rrc_replay: draws an RPCS3 frame capture (.rrc) with the live-draw engine,
# so a frame can be compared with RPCS3 on identical inputs. A dev tool, not
# part of the game; it builds only when asked (ninja RrcReplay).
# ---------------------------------------------------------------------------
if(WIN32)
    add_executable(RrcReplay EXCLUDE_FROM_ALL
        "${PS3RECOMP_DIR}/libs/video/tests/rrc_replay_main.c"
        "${PS3RECOMP_DIR}/runtime/host/host_stubs.c")
    target_include_directories(RrcReplay PRIVATE
        "${PS3RECOMP_DIR}/include"
        "${PS3RECOMP_DIR}/runtime"
        "${PS3RECOMP_DIR}/libs/video")
    target_link_libraries(RrcReplay PRIVATE ps3recomp_runtime
        dbghelp user32 gdi32 winmm dxguid d3d12 dxgi d3dcompiler)
    target_compile_definitions(RrcReplay PRIVATE _CRT_SECURE_NO_WARNINGS)
    set_target_properties(RrcReplay PROPERTIES LINKER_LANGUAGE CXX)
endif()

# ---------------------------------------------------------------------------
# Install
# ---------------------------------------------------------------------------
install(TARGETS ${PROJECT_NAME} RUNTIME DESTINATION bin)
