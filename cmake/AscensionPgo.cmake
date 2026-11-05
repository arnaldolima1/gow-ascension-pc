# PPU-only instrumentation PGO; normal builds retain their existing flags.
set(ASCENSION_PPU_PGO "OFF" CACHE STRING "PPU PGO: OFF, GENERATE, USE")
set_property(CACHE ASCENSION_PPU_PGO PROPERTY STRINGS OFF GENERATE USE)
set(ASCENSION_PPU_PROFILE "" CACHE FILEPATH "Merged LLVM profile for PPU PGO USE")
# ASCENSION_PGO_SPU=ON: the lifted SPU sources and the ps3recomp runtime library
# (the SPU dispatch, DMA, the gowa natives) too, from the same profile. Their
# counters are not atomic (six SPU worker threads would fight over the shared
# counter lines and crawl): a few counts lost to races, which PGO tolerates.
option(ASCENSION_PGO_SPU "PGO also for the lifted SPU code and the runtime library" OFF)
if(NOT ASCENSION_PPU_PGO MATCHES "^(OFF|GENERATE|USE)$")
    message(FATAL_ERROR "ASCENSION_PPU_PGO must be OFF, GENERATE or USE")
endif()
if(NOT ASCENSION_PPU_PGO STREQUAL "OFF")
    if(NOT MSVC OR NOT CMAKE_CXX_COMPILER_ID MATCHES "Clang")
        message(FATAL_ERROR "This PPU PGO workflow currently requires Windows clang-cl")
    endif()
    if(ASCENSION_PPU_PGO STREQUAL "GENERATE")
        execute_process(COMMAND "${CMAKE_CXX_COMPILER}" -print-resource-dir
            OUTPUT_VARIABLE _pgo_resource OUTPUT_STRIP_TRAILING_WHITESPACE
            RESULT_VARIABLE _pgo_resource_status)
        if(NOT _pgo_resource_status EQUAL 0)
            message(FATAL_ERROR "Cannot resolve clang profiling runtime")
        endif()
        set(_pgo_lib "${_pgo_resource}/lib/windows/clang_rt.profile-x86_64.lib")
        if(NOT EXISTS "${_pgo_lib}")
            message(FATAL_ERROR "Missing profiling runtime: ${_pgo_lib}")
        endif()
        get_filename_component(_pgo_libdir "${_pgo_lib}" DIRECTORY)
        target_link_directories(${PROJECT_NAME} PRIVATE "${_pgo_libdir}")
        target_link_libraries(${PROJECT_NAME} PRIVATE "${_pgo_lib}")
        set_property(SOURCE ${RECOMP_SOURCES} APPEND PROPERTY COMPILE_OPTIONS
            "/clang:-fprofile-instr-generate" "/clang:-fprofile-update=atomic")
        if(ASCENSION_PGO_SPU)
            if(SPU_SOURCES)
                set_property(SOURCE ${SPU_SOURCES} APPEND PROPERTY COMPILE_OPTIONS
                    "/clang:-fprofile-instr-generate" "/clang:-fprofile-update=single")
            endif()
            target_compile_options(ps3recomp_runtime PRIVATE
                "/clang:-fprofile-instr-generate" "/clang:-fprofile-update=single")
        endif()
        target_sources(${PROJECT_NAME} PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}/host/pgo_flush.cpp")
    else()
        if(NOT EXISTS "${ASCENSION_PPU_PROFILE}" OR IS_DIRECTORY "${ASCENSION_PPU_PROFILE}")
            message(FATAL_ERROR "PGO USE requires an existing merged ASCENSION_PPU_PROFILE")
        endif()
        set_property(SOURCE ${RECOMP_SOURCES} APPEND PROPERTY COMPILE_OPTIONS
            "/clang:-fprofile-instr-use=${ASCENSION_PPU_PROFILE}")
        if(ASCENSION_PGO_SPU)
            if(SPU_SOURCES)
                set_property(SOURCE ${SPU_SOURCES} APPEND PROPERTY COMPILE_OPTIONS
                    "/clang:-fprofile-instr-use=${ASCENSION_PPU_PROFILE}")
            endif()
            target_compile_options(ps3recomp_runtime PRIVATE
                "/clang:-fprofile-instr-use=${ASCENSION_PPU_PROFILE}")
        endif()
    endif()
    message(STATUS "PPU-only PGO: ${ASCENSION_PPU_PGO}")
endif()
