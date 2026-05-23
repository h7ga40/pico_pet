find_package(Python3 REQUIRED COMPONENTS Interpreter)

if(NOT DEFINED PET_NAME)
    set(PET_NAME zundamon)
endif()

set(PET_SOURCE_DIR ${CMAKE_CURRENT_SOURCE_DIR}/${PET_NAME})
set(PET_SPRITESHEET ${PET_SOURCE_DIR}/spritesheet.webp)
if(NOT EXISTS "${PET_SPRITESHEET}")
    message(FATAL_ERROR "Pet spritesheet not found: ${PET_SPRITESHEET}")
endif()

set(PET_GENERATED_DIR ${CMAKE_CURRENT_BINARY_DIR}/${PET_NAME}/generated)
set(PET_IMAGES_HEADER ${PET_GENERATED_DIR}/pet_images.h)
set(PET_IMAGES_SOURCE ${PET_GENERATED_DIR}/pet_images.c)
set(PET_IMAGES_ARCHIVE ${PET_GENERATED_DIR}/libpet_image_data.a)

add_custom_command(
    OUTPUT
        ${PET_IMAGES_HEADER}
        ${PET_IMAGES_SOURCE}
        ${PET_IMAGES_ARCHIVE}
    COMMAND
        ${Python3_EXECUTABLE}
        ${CMAKE_SOURCE_DIR}/scripts/pet_spritesheet_to_bins.py
        --input ${PET_SPRITESHEET}
        --output-dir ${PET_GENERATED_DIR}
        --object-dir ${PET_GENERATED_DIR}
        --header ${PET_IMAGES_HEADER}
        --source ${PET_IMAGES_SOURCE}
        --archive ${PET_IMAGES_ARCHIVE}
        --objcopy ${CMAKE_OBJCOPY}
        --objcopy-output-format elf32-littlearm
        --objcopy-architecture armv8-m.main
        --objcopy-section .rodata
        --ar ${CMAKE_AR}
        --clean
    DEPENDS
        ${PET_SPRITESHEET}
        ${CMAKE_SOURCE_DIR}/scripts/pet_spritesheet_to_bins.py
    VERBATIM
)

add_custom_target(generate_pet_images
    DEPENDS
        ${PET_IMAGES_HEADER}
        ${PET_IMAGES_SOURCE}
        ${PET_IMAGES_ARCHIVE}
)

add_library(pet_images STATIC
    ${PET_IMAGES_SOURCE}
)
add_dependencies(pet_images generate_pet_images)
target_include_directories(pet_images PUBLIC
    ${PET_GENERATED_DIR}
)

add_library(pet_image_data STATIC IMPORTED GLOBAL)
set_target_properties(pet_image_data PROPERTIES
    IMPORTED_LOCATION ${PET_IMAGES_ARCHIVE}
)
add_dependencies(pet_image_data generate_pet_images)

target_link_libraries(pet_images PUBLIC
    pet_image_data
)
