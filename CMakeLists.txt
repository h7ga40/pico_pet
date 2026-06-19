# == DO NOT EDIT THE FOLLOWING LINES for the Raspberry Pi Pico VS Code Extension to work ==
if(WIN32)
    set(USERHOME $ENV{USERPROFILE})
else()
    set(USERHOME $ENV{HOME})
endif()

find_package(Python3 REQUIRED COMPONENTS Interpreter)

file(GLOB TTS_USER_WAV_FILES CONFIGURE_DEPENDS ${CMAKE_CURRENT_LIST_DIR}/tts/user/*.wav)
if(TTS_USER_WAV_FILES)
    set(TTS_WAV_FILES ${TTS_USER_WAV_FILES})
    set(TTS_WAV_SOURCE_DESCRIPTION "user WAV files")
else()
    file(GLOB TTS_WAV_FILES CONFIGURE_DEPENDS ${CMAKE_CURRENT_LIST_DIR}/tts/generated/phrase_*.wav)
    set(TTS_WAV_SOURCE_DESCRIPTION "generated OpenJTalk WAV files")
endif()
if(NOT TTS_WAV_FILES)
    message(FATAL_ERROR "No TTS WAV files found. Add WAV files to tts/user or run scripts/generate_tts_wavs.py first.")
endif()
list(SORT TTS_WAV_FILES)
set(TTS_WAV_ARGS)
foreach(TTS_WAV_FILE IN LISTS TTS_WAV_FILES)
    list(APPEND TTS_WAV_ARGS --wav ${TTS_WAV_FILE})
endforeach()
set(TTS_PCM_SOURCE ${CMAKE_CURRENT_BINARY_DIR}/generated/tts_phrase_pcm.c)
set(TTS_PCM_HEADER ${CMAKE_CURRENT_BINARY_DIR}/generated/tts_phrase_pcm.h)
set(TTS_NORMALIZED_DIR ${CMAKE_CURRENT_BINARY_DIR}/generated/tts_normalized)
add_custom_command(
    OUTPUT ${TTS_PCM_SOURCE} ${TTS_PCM_HEADER}
    COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_LIST_DIR}/scripts/generate_tts_pcm.py
        ${TTS_WAV_ARGS}
        --source ${TTS_PCM_SOURCE}
        --header ${TTS_PCM_HEADER}
        --normalized-dir ${TTS_NORMALIZED_DIR}
    DEPENDS
        ${CMAKE_CURRENT_LIST_DIR}/scripts/generate_tts_pcm.py
        ${TTS_WAV_FILES}
    COMMENT "Generating embedded 16 kHz TTS phrase table from ${TTS_WAV_SOURCE_DESCRIPTION}"
    VERBATIM
)
set(sdkVersion 2.2.0)
set(toolchainVersion 14_2_Rel1)
set(picotoolVersion 2.2.0-a4)
set(picoVscode ${USERHOME}/.pico-sdk/cmake/pico-vscode.cmake)
if (EXISTS ${picoVscode})
    include(${picoVscode})
endif()
# ====================================================================================

set(PICO_BOARD waveshare_rp2350_plus_16mb CACHE STRING "Board type")

set(PET_NAME zundamon CACHE STRING "Pet asset directory under pets/")

cmake_minimum_required(VERSION 3.27)

# Pull in Raspberry Pi Pico SDK (must be before project)
include(pico_sdk_import.cmake)

project(main C CXX ASM)

# Initialise the Raspberry Pi Pico SDK
pico_sdk_init()

if(WIN32)
    set(Python3_EXECUTABLE "${CMAKE_SOURCE_DIR}/.venv/Scripts/python.exe")
else()
    set(Python3_EXECUTABLE "${CMAKE_SOURCE_DIR}/.venv/Scripts/python")
endif()

# Add executable. Default name is the project name, version 0.1

add_executable(main)

pico_generate_pio_header(main ${CMAKE_CURRENT_LIST_DIR}/lib/QSPI_PIO/qspi.pio
                        OUTPUT_DIR ${CMAKE_CURRENT_LIST_DIR}/lib/QSPI_PIO)

target_sources(main PRIVATE
    main.c
    src/kws_model.c
    src/kws_model_weights.c
    src/wakeword_stub.c
    ${TTS_PCM_SOURCE}
)

# Add compilation subdirectory
add_subdirectory(./lib/audio_pio)
add_subdirectory(./lib/Config)
add_subdirectory(./lib/es8311)
add_subdirectory(./lib/QSPI_PIO)
add_subdirectory(./lib/AMOLED)
add_subdirectory(./lib/GUI)
add_subdirectory(./lib/Fonts)
add_subdirectory(./lib/QMI8658)
add_subdirectory(./lib/Touch)
add_subdirectory(./pets)
add_dependencies(main generate_pet_images)

# Add header file directory
include_directories(./lib/audio_pio)
include_directories(./lib/Config)
include_directories(./lib/es8311)
include_directories(./lib/QSPI_PIO)
include_directories(./lib/AMOLED)
include_directories(./lib/GUI)
include_directories(./lib/Fonts)
include_directories(./lib/QMI8658)
include_directories(./lib/Touch)
include_directories(./include)
include_directories(${CMAKE_CURRENT_BINARY_DIR}/generated)

target_link_libraries(main PRIVATE 
    audio_pio
    Config
    es8311
    QSPI_PIO
    AMOLED
    GUI
    Fonts
    QMI8658
    Touch
    pet_images
    pico_stdlib 
    hardware_pio 
    hardware_pwm 
    hardware_dma
    hardware_spi
    hardware_i2c
    hardware_gpio
    hardware_adc
)

# enable usb output, disable uart output
pico_enable_stdio_usb(main 1)
pico_enable_stdio_uart(main 0)

pico_add_extra_outputs(main)

# add url via pico_set_program_url

